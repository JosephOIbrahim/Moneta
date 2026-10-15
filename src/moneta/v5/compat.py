"""v1-shaped facade over the v5 substrate.

Existing consumers (SYNAPSE's ``MonetaBackedStore`` is the live one) keep
constructing ``Moneta(MonetaConfig(...))`` with the unchanged v1 config
class, call the four operations with v1 signatures, and read the handle
attributes they already read: ``ecs.n``, ``ecs.iter_rows()``,
``ecs.count_protected()`` and ``durability.snapshot_ecs(...)``.

Underneath, everything is v5: a journal beside the v1 snapshot, durable
deposits, pure reads.

The v1 snapshot file
--------------------
Consumers read ``snapshot.json`` directly (SYNAPSE does, in its dim
reconcile, quarantine, export and backfill paths), so under the facade
that file becomes a **derived v1-format export**:

- The first open of a store that has only v1 files migrates the v1
  snapshot and WAL into the journal. Migration first copies the original
  snapshot byte-for-byte to ``snapshot.json.v1-original`` and never touches
  that copy or the WAL again.
- ``durability.snapshot_ecs()``, ``run_sleep_pass()`` and ``close()`` write
  a fresh v1-format export (tmp -> fsync -> atomic replace, as v1 did) and
  record its hash in ``<journal>.v1export``. Any v1-format reader,
  including v1 itself, can read it.
- On open, a ``snapshot.json`` whose hash is not the one v5 last wrote or
  migrated from means someone else wrote it. One such rewrite is accepted
  as input: the embedder-swap rewrite (same ids, same payloads, every
  vector at the configured new dimension) becomes a journaled
  ``revector``. Any other divergence raises :class:`SnapshotDivergedError`
  rather than letting two writers split the store.

Where v1 behavior was a defect, the facade keeps the v5 fix. Each such
difference is listed in :data:`BEHAVIOR_CHANGES`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

from .. import api as _v1api
from ..api import MonetaConfig, MonetaResourceLockedError
from ..types import EntityState, Memory
from .model import RECALLABLE, DimensionMismatchError, Status, encode_vector
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
EXPORT_SUFFIX = ".v1export"

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
    "snapshot_is_derived": "snapshot.json is a v1-format export; corrupting or deleting it loses nothing.",
    "snapshot_divergence": "a snapshot.json written by another writer is refused, except an embedder-swap rewrite.",
    "half_life_owned_by_journal": (
        "an existing store keeps the half-life it was created with; opening it with a different "
        "MonetaConfig.half_life_seconds raises HalfLifeMismatchError and writes nothing, unless "
        "Moneta(..., half_life_change='forward' | 'reinterpret') journals the change "
        "(v1 applied a new value silently from each row's last evaluation)."
    ),
    "half_life_change_dry_run": (
        "the first run_sleep_pass() after a half-life change is a dry run: it prunes, stages and "
        "projects nothing, returns pruned=0 with dry_run=True and the would-prune set in "
        "would_prune_ids, and repeats until run_sleep_pass(confirm_half_life_change=True)."
    ),
}


class SnapshotDivergedError(RuntimeError):
    """``snapshot.json`` was written by something other than this v5 store."""


def journal_path_for(config: MonetaConfig) -> Path | None:
    anchor = config.snapshot_path or config.wal_path
    if anchor is None:
        return None
    anchor = Path(anchor)
    return anchor.with_name(anchor.stem + JOURNAL_SUFFIX)


def _sidecar(journal: Path) -> Path:
    return journal.with_name(journal.name + EXPORT_SUFFIX)


def _atomic_write(path: Path, data: bytes) -> None:
    """tmp -> fsync -> os.replace, the same primitive v1's snapshot used."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fp:
        fp.write(data)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)


def _read_known_shas(journal: Path) -> list[str]:
    side = _sidecar(journal)
    if not side.exists():
        return []
    try:
        known = json.loads(side.read_text(encoding="utf-8"))["sha256"]
    except (ValueError, KeyError):
        return []
    return [known] if isinstance(known, str) else list(known)


def _write_known_sha(journal: Path, sha: str, source: str, seq: int) -> None:
    """Record ``sha`` as ours *before* the snapshot it names is replaced in.

    The previous hash is kept too, so a crash between this write and the
    snapshot's atomic replace leaves an accepted snapshot on disk either way.
    """
    known = [sha] + [k for k in _read_known_shas(journal) if k != sha][:1]
    _atomic_write(
        _sidecar(journal),
        json.dumps({"sha256": known, "source": source, "seq": seq}).encode("utf-8"),
    )


def export_v1_snapshot(substrate: Substrate, snapshot_path: Path) -> str:
    """Write the recallable records as a v1 ``snapshot.json``. Returns its sha256.

    Rows carry v5's utility *anchors* as v1's ``(utility, last_evaluated)``
    pair, which is exactly v1's lazy-decay state, so v1 hydrates them
    unchanged.
    """
    with substrate._lock:
        substrate._check_open()
        substrate.sync()
        rows = []
        for rec in sorted(substrate._fold.records.values(), key=lambda r: r.seq):
            if rec.status not in RECALLABLE:
                continue
            memory = rec.to_memory(substrate.lam, rec.anchor_t)
            rows.append(
                {
                    "entity_id": str(rec.entity_id),
                    "payload": rec.payload,
                    # A record left unembedded by a partial revector exports as
                    # a zero vector: v1 readers accept it and never rank it.
                    "semantic_vector": (
                        list(rec.vector) if rec.vector is not None else [0.0] * (substrate.dim or 0)
                    ),
                    "utility": rec.anchor_u,
                    "attended_count": rec.attended,
                    "protected_floor": rec.protected_floor,
                    "last_evaluated": rec.anchor_t,
                    "state": int(memory.state),
                    "usd_link": None,
                }
            )
        data = json.dumps(
            {
                "snapshot_version": 1,
                "snapshot_created_at": substrate._t(None),
                "rows": rows,
                "moneta_v5": {"seq": substrate.seq, "format": "v1-export"},
            }
        ).encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        if substrate.journal_path is not None:
            _write_known_sha(substrate.journal_path, sha, "export", substrate.seq)
        _atomic_write(snapshot_path, data)
        return sha


def _journal_known_shas(substrate: Substrate) -> set[str]:
    """Snapshot hashes the journal itself vouches for (migration source, accepted rewrites).

    Covers a crash between journaling a migration or revector and writing the
    sidecar, so v5 never refuses a snapshot it produced or consumed itself.
    """
    shas = set()
    for event in substrate._journal.events():
        if event.get("op") == "note" and event.get("snapshot_sha256"):
            shas.add(event["snapshot_sha256"])
    return shas


def _reconcile_snapshot(
    substrate: Substrate, snapshot_path: Path, configured_dim: int | None
) -> dict[str, Any] | None:
    """Guard against a second writer; accept what a consumer may legitimately do.

    Accepted, in order:
      1. a snapshot v5 wrote or migrated from (hash known to sidecar or journal);
      2. an unreadable snapshot (it is derived; the journal is intact). Warned,
         noted in the journal, and overwritten by the next export;
      3. an embedder-swap rewrite: every row is a journal record with the same
         payload, every vector is at the configured new dimension. Journal
         records missing from a stale export stay recallable but unrankable
         until re-embedded.
    Anything else is a second writer and raises SnapshotDivergedError.
    """
    journal = substrate.journal_path
    if journal is None or not snapshot_path.exists():
        return None
    raw = snapshot_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha in _read_known_shas(journal) or sha in _journal_known_shas(substrate):
        return None

    def diverged(why: str) -> SnapshotDivergedError:
        return SnapshotDivergedError(
            f"{snapshot_path} was written by another writer after v5 took over this store "
            f"({why}). The journal {journal.name} is the source of truth. Move the snapshot "
            f"aside to continue, or remove the journal to re-migrate from it."
        )

    try:
        snap = json.loads(raw.decode("utf-8"))
        rows = snap["rows"]
        by_id = {UUID(r["entity_id"]): r for r in rows}
        vectors = {eid: [float(x) for x in r["semantic_vector"]] for eid, r in by_id.items()}
        payloads = {eid: r["payload"] for eid, r in by_id.items()}
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError) as exc:
        substrate._append(
            {
                "op": "note",
                "t": substrate._t(None),
                "kind": "snapshot_unreadable",
                "snapshot_sha256": sha,
                "error": str(exc)[:200],
            }
        )
        _logger.warning(
            "moneta.v5 ignored an unreadable %s (%s); the journal is intact and the next "
            "export will replace it",
            snapshot_path,
            exc,
        )
        return {"ignored_unreadable_snapshot": True}

    live = {r.entity_id: r for r in substrate._fold.records.values() if r.status in RECALLABLE}
    unknown = set(by_id) - set(live)
    if unknown:
        raise diverged(f"it holds {len(unknown)} records the journal does not")
    if any(payloads[eid] != live[eid].payload for eid in by_id):
        raise diverged("payloads differ from the journal")
    dims = {len(v) for v in vectors.values()}
    target = dims.pop() if len(dims) == 1 else (configured_dim if not dims else None)
    if (
        target is None
        or configured_dim is None
        or target != configured_dim
        or configured_dim == substrate.dim
    ):
        raise diverged("it is not an embedder-swap rewrite to the configured dimension")
    unembedded = sorted(set(live) - set(by_id))
    seq = substrate.revector(vectors, dim=configured_dim, allow_missing=True)
    substrate._append(
        {
            "op": "note",
            "t": substrate._t(None),
            "kind": "consumer_revector",
            "snapshot_sha256": sha,
            "dim": configured_dim,
            "records": len(vectors),
            "unembedded": len(unembedded),
        }
    )
    _write_known_sha(journal, sha, "consumer_revector", substrate.seq)
    log = _logger.warning
    log(
        "moneta.v5 accepted an embedder-swap rewrite of %s: %d records re-embedded to dim %d%s",
        snapshot_path,
        len(vectors),
        configured_dim,
        f"; {len(unembedded)} journal records were not in the (stale) export and are "
        f"unrankable until re-embedded"
        if unembedded
        else "",
    )
    return {
        "revector_seq": seq,
        "dim": configured_dim,
        "records": len(vectors),
        "unembedded": [str(u) for u in unembedded],
    }


class TargetProjector:
    """Adapts any v1 ``AuthoringTarget`` (UsdTarget, MockUsdTarget) to a v5 projector.

    Reusing v1's writers keeps the on-disk USD layout byte-compatible with
    v1: typed ``MonetaMemory`` prims under ``cortex_*.usda`` sublayers.

    The target is built lazily on first use. Projection is derived state, so
    a USD problem surfaces as ``SleepPassResult.projection_error`` (and is
    retried) instead of preventing the store from opening.
    """

    def __init__(self, factory: Any, name: str) -> None:
        self._factory = factory
        self.target: Any = None
        self.name = name

    def project(self, memories: list[Memory], t: float) -> str:
        if self.target is None:
            self.target = self._factory()
        result = self.target.author_stage_batch(memories)
        self.target.flush()
        return result.batch_id

    def close(self) -> None:
        if self.target is not None and hasattr(self.target, "close"):
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
        return status is not None and status in RECALLABLE

    def get_memory(self, entity_id: UUID) -> Memory | None:
        for m in self._s.records():
            if m.entity_id == entity_id:
                return m
        return None

    def staged_entities(self) -> list[Memory]:
        return self._s.get_consolidation_manifest()


class _DurabilityView:
    """Stand-in for v1's ``handle.durability``.

    Every write is already durable in the journal; ``snapshot_ecs`` also
    refreshes the v1-format export for file-level readers.
    """

    def __init__(self, substrate: Substrate, snapshot_path: Path | None) -> None:
        self._s = substrate
        self._snapshot_path = snapshot_path

    def snapshot_ecs(self, ecs: Any = None) -> None:
        if self._snapshot_path is None:
            self._s.sync()
        else:
            export_v1_snapshot(self._s, self._snapshot_path)

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
        half_life_change: str | None = None,
    ) -> None:
        if config.storage_uri in _v1api._ACTIVE_URIS:
            raise MonetaResourceLockedError(
                f"storage_uri {config.storage_uri!r} is already held by another live handle"
            )
        _v1api._ACTIVE_URIS.add(config.storage_uri)
        self.config = config
        self._closed = False
        self.migration: dict[str, Any] | None = None
        self.revector: dict[str, Any] | None = None
        snapshot = None if config.snapshot_path is None else Path(config.snapshot_path)
        try:
            projector = self._make_projector(config)
            path = journal_path_for(config)
            fresh = path is None or not path.exists()
            try:
                self.v5 = Substrate(
                    Config(
                        path=path,
                        half_life_seconds=config.half_life_seconds,
                        # An existing journal owns its dimension; the configured
                        # one is checked after the snapshot guard below.
                        embedding_dim=config.embedding_dim if fresh else None,
                        protected_quota=config.quota_override,
                        fsync=fsync,
                        clock=clock or SystemClock(),
                        policy=policy,
                        projector=projector,
                    ),
                    # The journal owns the half-life; a different configured
                    # value is refused unless the caller names a change mode.
                    half_life_change=half_life_change,
                )
            except BaseException:
                projector.close()
                raise
            try:
                if fresh and snapshot is not None and snapshot.exists():
                    self.migration = migrate_v1(
                        self.v5,
                        snapshot,
                        None if config.wal_path is None else Path(config.wal_path),
                    )
            except BaseException:
                self.v5.close()
                if path is not None and path.exists():
                    # A half-migrated journal must not be mistaken for a migrated one.
                    path.rename(path.with_name(path.name + ".failed-migration"))
                raise
            try:
                if not fresh and snapshot is not None:
                    self.revector = _reconcile_snapshot(self.v5, snapshot, config.embedding_dim)
                if config.embedding_dim is not None:
                    if self.v5.dim is None:
                        self.v5._fold.dim = self.v5._index.dim = config.embedding_dim
                    elif self.v5.dim != config.embedding_dim:
                        raise DimensionMismatchError(self.v5.dim, config.embedding_dim)
            except BaseException:
                self.v5.close()
                raise
        except BaseException:
            _v1api._ACTIVE_URIS.discard(config.storage_uri)
            raise
        self.ecs = _EcsView(self.v5)
        self.vector_index = _IndexView(self.v5)
        self.durability = (
            _DurabilityView(self.v5, snapshot) if self.v5.journal_path is not None else None
        )

    @staticmethod
    def _make_projector(config: MonetaConfig) -> Any:
        if config.use_real_usd:
            from ..usd_target import UsdTarget

            return TargetProjector(lambda: UsdTarget(log_path=config.usd_target_path), "usd")
        if config.mock_target_log_path is not None:
            from ..mock_usd_target import MockUsdTarget

            return TargetProjector(
                lambda: MockUsdTarget(log_path=config.mock_target_log_path), "mock"
            )
        return MemoryProjector()

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
            if self.durability is not None and not self.v5.closed:
                try:
                    # Leave file-level readers a current export. Failure here
                    # loses nothing: the journal already holds every write.
                    self.durability.snapshot_ecs()
                except Exception:  # noqa: BLE001
                    _logger.warning("moneta.v5 export on close failed", exc_info=True)
        finally:
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

    def run_sleep_pass(self, *, confirm_half_life_change: bool = False) -> SleepPassResult:
        result = self.v5.run_sleep_pass(confirm_half_life_change=confirm_half_life_change)
        if self.durability is not None:
            self.durability.snapshot_ecs()  # v1 snapshotted after every pass
        return result


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
    The original snapshot is preserved as ``<snapshot>.v1-original`` before
    anything else happens; v1 files are never modified.
    """
    raw = snapshot_path.read_bytes()
    original = snapshot_path.with_name(snapshot_path.name + ".v1-original")
    if not original.exists():
        _atomic_write(original, raw)
    snapshot = json.loads(raw.decode("utf-8"))
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("rows"), list):
        raise ValueError(f"{snapshot_path} is not a v1 snapshot")
    snap_ts = float(snapshot.get("snapshot_created_at", 0.0))
    if not math.isfinite(snap_ts):
        snap_ts = 0.0
    sha = hashlib.sha256(raw).hexdigest()
    report: dict[str, Any] = {
        "kind": "v1_migration",
        "snapshot": str(snapshot_path),
        "snapshot_sha256": sha,
        "original_preserved_at": str(original),
        "snapshot_version": snapshot.get("snapshot_version"),
        "rows": 0,
        "rows_invalid_vector": 0,
        "rows_zero_vector": 0,
        "rows_repaired": 0,
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
        if not vec or not all(math.isfinite(x) for x in vec):
            report["rows_invalid_vector"] += 1
        elif not any(vec):
            report["rows_zero_vector"] += 1
        status = _V1_STATUS.get(int(row["state"]), Status.LIVE)
        u = float(row["utility"])
        floor = float(row.get("protected_floor", 0.0))
        anchor_t = float(row["last_evaluated"])
        repaired = False
        if not math.isfinite(u):
            u, repaired = 0.0, True
        if not math.isfinite(floor) or not 0.0 <= floor <= 1.0:
            floor, repaired = (min(max(floor, 0.0), 1.0) if math.isfinite(floor) else 0.0), True
        if not math.isfinite(anchor_t):
            anchor_t, repaired = snap_ts, True
        if repaired:
            report["rows_repaired"] += 1
        event = {
            "op": "import",
            "id": str(UUID(row["entity_id"])),
            "t": anchor_t,
            "payload": row["payload"],
            "emb": encode_vector(vec),
            "floor": floor,
            "scope": "",
            "u": u,
            "anchor_t": anchor_t,
            "attended": int(row.get("attended_count", 0)),
            "status": status.value,
        }
        substrate._append(event)
        rec = substrate._fold.records[UUID(event["id"])]
        substrate._index.dim = substrate._fold.dim
        if rec.unit is not None and rec.status in RECALLABLE:
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
                if not math.isfinite(ts):
                    raise ValueError("non-finite timestamp")
            except (ValueError, KeyError, TypeError, AttributeError):
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
    if substrate.journal_path is not None:
        _write_known_sha(substrate.journal_path, sha, "v1_migration", substrate.seq)
    skipped = sum(
        report[k]
        for k in (
            "rows_invalid_vector",
            "rows_repaired",
            "wal_malformed",
            "wal_unknown_id",
            "wal_invalid_weight",
        )
    )
    log = _logger.warning if skipped else _logger.info
    log("moneta.v5 migrated v1 store %s: %s", snapshot_path, report)
    return report
