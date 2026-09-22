"""v1-shaped facade over the v5 substrate.

Existing consumers (SYNAPSE's ``MonetaBackedStore`` is the live one) keep
constructing ``Moneta(MonetaConfig(...))`` with the unchanged v1 config
class, call the four operations with v1 signatures, and read the handle
attributes they already read: ``ecs.n``, ``ecs.iter_rows()``,
``ecs.count_protected()`` and ``durability.snapshot_ecs(...)``.

Underneath, everything is v5: a journal next to the v1 snapshot, durable
deposits, pure reads. The first open of a store that has only v1 files
migrates the v1 snapshot and WAL into the journal. v1 files are read and
never modified or deleted, so rolling back means pointing the consumer at
v1 again.

Where v1 behavior was a defect, the facade keeps the v5 fix. Each such
difference is listed in :data:`BEHAVIOR_CHANGES`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

from .. import api as _v1api
from ..api import MonetaConfig, MonetaResourceLockedError
from ..types import EntityState, Memory
from .model import DimensionMismatchError, Status, encode_vector
from .policy import PolicyResolver
from .substrate import (
    Clock,
    Config,
    MemoryProjector,
    SleepPassResult,
    Substrate,
    SystemClock,
)

_logger = logging.getLogger(__name__)

JOURNAL_SUFFIX = ".v5.journal"

BEHAVIOR_CHANGES = {
    "deposit_durability": "deposit() is fsync'd to the journal before it returns; no sleep pass needed.",
    "deposit_validation": "invalid or wrong-dimension embeddings raise and leave no trace.",
    "query_dimension": "a wrong-dimension query raises DimensionMismatchError instead of returning [].",
    "attention_timing": "attention applies at the signal's timestamp and is visible to the next query.",
    "attention_validation": "weights must be finite and in [0, 1]; never-deposited ids raise.",
    "prune_audit": "run_sleep_pass() returns pruned_ids; pruned payloads stay readable via .v5.explain().",
    "projection_retry": "a failed USD projection leaves records staged and is retried next pass.",
    "exclusivity": "a second handle on the same journal path fails even under a different storage_uri.",
    "free_threading": "no GIL assumption; the PEP 703 sentinel does not apply.",
}


def journal_path_for(config: MonetaConfig) -> Path | None:
    anchor = config.snapshot_path or config.wal_path
    if anchor is None:
        return None
    anchor = Path(anchor)
    return anchor.with_name(anchor.stem + JOURNAL_SUFFIX)


class TargetProjector:
    """Adapts any v1 ``AuthoringTarget`` (UsdTarget, MockUsdTarget) to a v5 projector.

    Reusing v1's writers keeps the on-disk USD layout byte-compatible with
    v1: typed ``MonetaMemory`` prims under ``cortex_*.usda`` sublayers.
    """

    def __init__(self, target: Any, name: str) -> None:
        self.target = target
        self.name = name

    def project(self, memories: list[Memory], t: float) -> str:
        result = self.target.author_stage_batch(memories)
        self.target.flush()
        return result.batch_id

    def close(self) -> None:
        if hasattr(self.target, "close"):
            self.target.close()


class _EcsView:
    """Read-only stand-in for v1's ``handle.ecs``."""

    def __init__(self, substrate: Substrate) -> None:
        self._s = substrate

    @property
    def n(self) -> int:
        return self._s.recallable_count()

    def __len__(self) -> int:
        return self.n

    def iter_rows(self) -> Iterator[Memory]:
        return self._s.records()

    def count_protected(self) -> int:
        return self._s.count_protected()

    def contains(self, entity_id: UUID) -> bool:
        status = self._s.status_of(entity_id)
        return status is not None and status not in (Status.TOMBSTONED, Status.ERASED)

    def get_memory(self, entity_id: UUID) -> Memory | None:
        for m in self._s.records():
            if m.entity_id == entity_id:
                return m
        return None

    def staged_entities(self) -> list[Memory]:
        return self._s.get_consolidation_manifest()


class _DurabilityView:
    """Stand-in for v1's ``handle.durability``. Every write is already durable."""

    def __init__(self, substrate: Substrate) -> None:
        self._s = substrate

    def snapshot_ecs(self, ecs: Any = None) -> None:
        self._s.sync()

    def start_background(self, ecs: Any = None) -> None:
        """No-op: there is nothing to snapshot periodically."""

    def stop_background(self) -> None:
        pass

    def close(self) -> None:
        pass


class _IndexView:
    def __init__(self, substrate: Substrate) -> None:
        self._s = substrate

    def __len__(self) -> int:
        return self._s.recallable_count()


class Moneta:
    """Drop-in for ``moneta.Moneta`` backed by the v5 journal."""

    def __init__(
        self,
        config: MonetaConfig,
        *,
        policy: PolicyResolver | None = None,
        clock: Clock | None = None,
        fsync: bool = True,
    ) -> None:
        if config.storage_uri in _v1api._ACTIVE_URIS:
            raise MonetaResourceLockedError(
                f"storage_uri {config.storage_uri!r} is already held by another live handle"
            )
        _v1api._ACTIVE_URIS.add(config.storage_uri)
        self.config = config
        self._closed = False
        try:
            if config.use_real_usd:
                from ..usd_target import UsdTarget

                projector: Any = TargetProjector(UsdTarget(log_path=config.usd_target_path), "usd")
            elif config.mock_target_log_path is not None:
                from ..mock_usd_target import MockUsdTarget

                projector = TargetProjector(
                    MockUsdTarget(log_path=config.mock_target_log_path), "mock"
                )
            else:
                projector = MemoryProjector()
            path = journal_path_for(config)
            fresh = path is None or not path.exists()
            self.v5 = Substrate(
                Config(
                    path=path,
                    half_life_seconds=config.half_life_seconds,
                    embedding_dim=config.embedding_dim,
                    protected_quota=config.quota_override,
                    fsync=fsync,
                    clock=clock or SystemClock(),
                    policy=policy,
                    projector=projector,
                )
            )
            self.migration: dict[str, Any] | None = None
            try:
                if (
                    fresh
                    and config.snapshot_path is not None
                    and Path(config.snapshot_path).exists()
                ):
                    self.migration = migrate_v1(
                        self.v5,
                        Path(config.snapshot_path),
                        None if config.wal_path is None else Path(config.wal_path),
                    )
            except BaseException:
                self.v5.close()
                if path is not None and path.exists():
                    # A half-migrated journal must not be mistaken for a migrated one.
                    path.rename(path.with_name(path.name + ".failed-migration"))
                raise
        except BaseException:
            _v1api._ACTIVE_URIS.discard(config.storage_uri)
            raise
        self.ecs = _EcsView(self.v5)
        self.vector_index = _IndexView(self.v5)
        self.durability = _DurabilityView(self.v5) if self.v5.journal_path is not None else None

    # -- lifecycle -----------------------------------------------------

    def __enter__(self) -> Moneta:
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.v5.close()
        finally:
            _v1api._ACTIVE_URIS.discard(self.config.storage_uri)

    # -- the four operations (v1 signatures) ---------------------------

    def deposit(self, payload: str, embedding: list[float], protected_floor: float = 0.0) -> UUID:
        return self.v5.deposit(payload, embedding, protected_floor)

    def query(self, embedding: list[float], limit: int = 5) -> list[Memory]:
        # v1 returned [] for a zero query vector; that is a direction-less
        # question rather than a storage fault, so the facade keeps it.
        try:
            values = [float(x) for x in embedding]
        except (TypeError, ValueError):
            values = []
        if values and all(math.isfinite(x) for x in values) and not any(values):
            return []
        return self.v5.query(embedding, limit)

    def signal_attention(self, weights: dict[UUID, float]) -> None:
        self.v5.signal_attention(weights)

    def get_consolidation_manifest(self) -> list[Memory]:
        return self.v5.get_consolidation_manifest()

    def run_sleep_pass(self) -> SleepPassResult:
        return self.v5.run_sleep_pass()


# ----------------------------------------------------------------------
# v1 -> v5 migration
# ----------------------------------------------------------------------

_V1_STATUS = {
    int(EntityState.VOLATILE): Status.LIVE,
    int(EntityState.STAGED_FOR_SYNC): Status.STAGED,
    int(EntityState.CONSOLIDATED): Status.CONSOLIDATED,
}


def migrate_v1(substrate: Substrate, snapshot_path: Path, wal_path: Path | None) -> dict[str, Any]:
    """Import a v1 snapshot (+ WAL tail) into an empty v5 journal.

    Rows keep their entity ids, payloads, vectors, utility anchors,
    attended counts and states. WAL entries newer than the snapshot become
    attention events at their own timestamps. Anything unusable is counted
    and recorded in a journaled ``note`` event; nothing is dropped silently.
    """
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw.decode("utf-8"))
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("rows"), list):
        raise ValueError(f"{snapshot_path} is not a v1 snapshot")
    snap_ts = float(snapshot.get("snapshot_created_at", 0.0))
    report: dict[str, Any] = {
        "kind": "v1_migration",
        "snapshot": str(snapshot_path),
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_version": snapshot.get("snapshot_version"),
        "rows": 0,
        "rows_invalid_vector": 0,
        "wal_applied": 0,
        "wal_malformed": 0,
        "wal_unknown_id": 0,
        "wal_invalid_weight": 0,
        "wal_before_snapshot": 0,
    }
    dim = substrate.dim
    for row in snapshot["rows"]:
        vec = [float(x) for x in row["semantic_vector"]]
        if dim is None:
            dim = len(vec)
        if len(vec) != dim:
            raise DimensionMismatchError(dim, len(vec))
        valid = bool(vec) and all(math.isfinite(x) for x in vec) and any(vec)
        status = _V1_STATUS.get(int(row["state"]), Status.LIVE)
        u = float(row["utility"])
        event = {
            "op": "import",
            "id": str(UUID(row["entity_id"])),
            "t": float(row["last_evaluated"]),
            "payload": row["payload"],
            "emb": encode_vector(vec),
            "floor": float(row.get("protected_floor", 0.0)),
            "scope": "",
            "u": u if math.isfinite(u) else 0.0,
            "anchor_t": float(row["last_evaluated"]),
            "attended": int(row.get("attended_count", 0)),
            "status": status.value,
        }
        if not valid:
            report["rows_invalid_vector"] += 1
        substrate._append(event)
        rec = substrate._fold.records[UUID(event["id"])]
        if rec.unit is not None and rec.status.value in ("live", "staged", "consolidated"):
            substrate._index.dim = substrate._fold.dim
            substrate._index.add(rec.entity_id, rec.unit)
        report["rows"] += 1

    if wal_path is not None and wal_path.exists():
        for line in wal_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                eid = UUID(entry["entity_id"])
                weight = float(entry["weight"])
                ts = float(entry["timestamp"])
            except (ValueError, KeyError, TypeError):
                report["wal_malformed"] += 1
                continue
            if ts <= snap_ts:
                report["wal_before_snapshot"] += 1
                continue
            if eid not in substrate._fold.records:
                report["wal_unknown_id"] += 1
                continue
            if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
                report["wal_invalid_weight"] += 1
                continue
            substrate.signal_attention({eid: weight}, t=ts)
            report["wal_applied"] += 1

    substrate._append({"op": "note", "t": substrate._t(None), **report})
    substrate.sync()
    skipped = sum(
        report[k]
        for k in ("rows_invalid_vector", "wal_malformed", "wal_unknown_id", "wal_invalid_weight")
    )
    log = _logger.warning if skipped else _logger.info
    log("moneta.v5 migrated v1 store %s: %s", snapshot_path, report)
    return report
