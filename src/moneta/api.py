"""Moneta substrate handle — dependency-injected, URI-locked, context-managed.

DEEP_THINK_BRIEF_substrate_handle.md §5.1 (Q1 shape), §5.3 (Q3 signature),
§5.4 (Q4 seam), and §6 (G1 ruling clarifications) are the design source
of truth. This module:

  - Defines :class:`MonetaConfig` (frozen, ``kw_only=True``) with
    ``storage_uri`` and ``quota_override`` added per §5.3, all existing
    fields preserved per §6.1.
  - Defines :class:`Moneta`, the handle. The four-op surface from
    ARCHITECTURE.md §2 lives as instance methods. Signatures otherwise
    verbatim from MONETA.md §2.1 (only the receiver changes —
    ``self`` is added; param names, types, defaults, and return types
    are untouched).
  - Defines ``_ACTIVE_URIS`` and :class:`MonetaResourceLockedError`,
    the in-memory exclusivity registry from §5.4. Two handles
    constructed against the same ``storage_uri`` collide synchronously
    at the second constructor call.

What this module is not
-----------------------
- Not a singleton. There is no ``_state``. There is no ``init()``. There
  is no ``_reset_state()``. There is no ``MonetaNotInitializedError`` —
  in handle world, "not initialized" is unrepresentable.
- Not a concurrency framework. ``_ACTIVE_URIS`` is an in-memory set
  intentionally without a lock; per §5.4 the next surgery turns
  exclusivity into coordination, this one only establishes ownership.
- Not the cloud surgery. ``tenant_id`` and ``sync_strategy`` appear as
  commented placeholders only; their implementation is downstream.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from .attention_log import AttentionEntry, AttentionLog
from .consolidation import (
    DEFAULT_MAX_ENTITIES,
    ConsolidationResult,
    ConsolidationRunner,
)
from .decay import DEFAULT_HALF_LIFE_SECONDS, DecayConfig
from .durability import DurabilityManager
from .ecs import ECS
from .manifest import build_manifest
from .mock_usd_target import MockUsdTarget
from .sequential_writer import SequentialWriter
from .types import EntityState, Memory
from .vector_index import VectorIndex

_logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class ProtectedQuotaExceededError(RuntimeError):
    """Raised when a protected deposit would exceed ``config.quota_override``.

    Phase 1 enforcement per ARCHITECTURE.md §10: ``deposit`` raises on
    overflow. Phase 3 adds an operator-facing unpin tool (explicitly NOT
    part of the four-op API) that lets operators reclaim slots.
    """


class MonetaResourceLockedError(RuntimeError):
    """Raised when a :class:`Moneta` is constructed against a ``storage_uri``
    already held by another live handle in this process.

    Per DEEP_THINK_BRIEF_substrate_handle.md §5.4, the in-memory
    ``_ACTIVE_URIS`` registry physically prevents two handles from
    pointing at the same underlying state. Release is via the holding
    handle's :meth:`Moneta.close` (or context-manager exit).
    """


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class MonetaConfig:
    """Frozen, keyword-only handle configuration.

    Per §5.3 (Q3 signature) the constructor accepts exactly one argument
    of this type. Per §6.1 (G1 ruling) the existing field set is
    preserved and ``storage_uri`` / ``quota_override`` are additive — the
    consolidation of path-style fields into ``storage_uri`` semantics is
    a separate, downstream pass.

    Fields
    ------
    storage_uri:
        Irreducible. The handle's logical identity. Anticipates
        ``s3://`` or ``moneta://`` routing; today, two handles with the
        same ``storage_uri`` collide synchronously at the second
        constructor call (``MonetaResourceLockedError``).
    quota_override:
        Per-handle protected-deposit quota. Replaces the module-level
        ``PROTECTED_QUOTA`` constant from the singleton era.
    half_life_seconds, embedding_dim, max_entities,
    snapshot_path, wal_path, vector_persist_path,
    mock_target_log_path, use_real_usd, usd_target_path:
        Preserved from the singleton-era ``MonetaConfig``. Semantics
        unchanged.

    Cloud-anticipated fields appear as commented placeholders; their
    implementation is out of scope for this surgery.

    Test ergonomics
    ---------------
    Use :meth:`MonetaConfig.ephemeral` for short-lived in-process tests.
    """

    # Irreducible.
    storage_uri: str
    quota_override: int = 100

    # Preserved from singleton-era config (semantics unchanged).
    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS
    embedding_dim: Optional[int] = None
    max_entities: int = DEFAULT_MAX_ENTITIES
    snapshot_path: Optional[Path] = None
    wal_path: Optional[Path] = None
    vector_persist_path: Optional[Path] = None
    mock_target_log_path: Optional[Path] = None
    use_real_usd: bool = False
    usd_target_path: Optional[Path] = None

    # Cloud-anticipated (do not implement logic yet — see §5.3):
    # tenant_id: Optional[str] = None
    # sync_strategy: Optional[str] = None

    @classmethod
    def ephemeral(cls, **overrides: Any) -> "MonetaConfig":
        """Construct a config with a freshly-minted unique ``storage_uri``.

        Test-ergonomics factory per §5.3. Each call returns a config
        whose URI does not collide with any prior or concurrent
        ``ephemeral()`` call in the same process. Pass other config
        fields as keyword overrides (``snapshot_path=...``,
        ``half_life_seconds=...``); ``storage_uri`` may be overridden
        as well, in which case the auto-generated URI is replaced.
        """
        if "storage_uri" not in overrides:
            overrides["storage_uri"] = (
                f"moneta-ephemeral://{_uuid.uuid4().hex}"
            )
        return cls(**overrides)


# ----------------------------------------------------------------------
# Process-level URI registry (§5.4)
# ----------------------------------------------------------------------


# In-memory only. Per §5.4: "an ephemeral lock singleton" — structurally
# correct for single-process exclusivity. Replaced by distributed
# coordination in the next surgery.
_ACTIVE_URIS: set[str] = set()


# ----------------------------------------------------------------------
# Moneta — the handle
# ----------------------------------------------------------------------


class Moneta:
    """Moneta substrate handle.

    Constructor acquires a process-level lock on ``config.storage_uri``;
    :meth:`close` (or context-manager exit) releases it. Two live
    handles on the same ``storage_uri`` is a runtime error
    (:class:`MonetaResourceLockedError`).

    The handle owns all substrate state — ECS, decay config, attention
    log, shadow vector index, consolidation runner, sequential writer,
    authoring target, and (optionally) durability. Methods read these
    via ``self``; there is no module-level fallback.

    Calling :class:`Moneta` with no arguments is a ``TypeError`` by
    construction (§5.3 — "the no-arg trap"). Pass a
    :class:`MonetaConfig`.
    """

    def __init__(self, config: MonetaConfig) -> None:
        # Acquire URI lock first so a partial init below cannot leak the
        # lock to a concurrent caller.
        if config.storage_uri in _ACTIVE_URIS:
            raise MonetaResourceLockedError(
                f"storage_uri {config.storage_uri!r} is already held by "
                f"another live Moneta handle in this process; release it "
                f"via close() or context-manager exit before reconstructing"
            )
        _ACTIVE_URIS.add(config.storage_uri)

        try:
            self.config: MonetaConfig = config
            self._closed: bool = False

            # Protects the protected-quota count-then-add critical section in
            # deposit(). Without this, two concurrent protected deposits at
            # quota-1 can both observe count<quota and both succeed, breaking
            # the §10 hard cap. See review finding
            # substrate-L2-protected-quota-count-then-add-toctou.
            self._deposit_lock: threading.Lock = threading.Lock()

            self.decay: DecayConfig = DecayConfig(
                half_life_seconds=config.half_life_seconds
            )
            self.attention: AttentionLog = AttentionLog()

            self.vector_index: VectorIndex = VectorIndex(
                embedding_dim=config.embedding_dim,
                persist_path=config.vector_persist_path,
            )

            self.durability: Optional[DurabilityManager] = None
            if (
                config.snapshot_path is not None
                and config.wal_path is not None
            ):
                self.durability = DurabilityManager(
                    snapshot_path=config.snapshot_path,
                    wal_path=config.wal_path,
                )
                self.ecs, wal_replay = self.durability.hydrate()
                # Rebuild vector index from hydrated ECS (shadow rebuild).
                for memory in self.ecs.iter_rows():
                    self.vector_index.upsert(
                        memory.entity_id,
                        memory.semantic_vector,
                        memory.state,
                    )
                # Replay WAL entries into the attention log for next reduce.
                for entry in wal_replay:
                    self.attention.append(
                        entry.entity_id, entry.weight, entry.timestamp
                    )
                _logger.info(
                    "Moneta.hydrate uri=%s n=%d wal_replay=%d",
                    config.storage_uri,
                    self.ecs.n,
                    len(wal_replay),
                )
            else:
                self.ecs = ECS()

            # Authoring target: real USD (Phase 3) or mock (Phase 1 / dev).
            # UsdTarget imported function-level so api.py stays importable
            # under plain Python where pxr is unavailable.
            self.mock_target: Optional[MockUsdTarget] = None
            if config.use_real_usd:
                from .usd_target import UsdTarget

                self.authoring_target: object = UsdTarget(
                    log_path=config.usd_target_path
                )
            else:
                self.mock_target = MockUsdTarget(
                    log_path=config.mock_target_log_path
                )
                self.authoring_target = self.mock_target

            self.sequential_writer: SequentialWriter = SequentialWriter(
                self.authoring_target, self.vector_index
            )
            self.consolidation: ConsolidationRunner = ConsolidationRunner(
                max_entities=config.max_entities
            )
        except BaseException:
            # Partial init — release the lock so the consumer can retry.
            _ACTIVE_URIS.discard(config.storage_uri)
            raise

        _logger.info(
            "Moneta.init uri=%s half_life=%.1fs max_entities=%d "
            "durability=%s target=%s quota=%d",
            config.storage_uri,
            config.half_life_seconds,
            config.max_entities,
            "on" if self.durability is not None else "off",
            "usd" if config.use_real_usd else "mock",
            config.quota_override,
        )

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "Moneta":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.close()
        return False  # do not suppress exceptions

    def close(self) -> None:
        """Release native resources and the URI lock. Idempotent.

        Order matters: shut the snapshot daemon thread before closing
        the authoring target, then discard the URI from
        ``_ACTIVE_URIS``. Reverse order would let a re-construct on the
        same URI race against an in-flight snapshot or open file handle.
        """
        if self._closed:
            return
        self._closed = True
        try:
            if self.durability is not None:
                self.durability.close()
            if hasattr(self.authoring_target, "close"):
                self.authoring_target.close()
        finally:
            _ACTIVE_URIS.discard(self.config.storage_uri)
            _logger.info(
                "Moneta.close uri=%s", self.config.storage_uri
            )

    # ------------------------------------------------------------------
    # The four operations (ARCHITECTURE.md §2 / MONETA.md §2.1)
    # Signatures verbatim from the spec; only the receiver (``self``)
    # is added for the OO migration.
    # ------------------------------------------------------------------

    def deposit(
        self,
        payload: str,
        embedding: List[float],
        protected_floor: float = 0.0,
    ) -> UUID:
        """Deposit a new memory and return its EntityID.

        Phase 1 convention: fresh memories start at ``Utility = 1.0``.

        Persistence wiring: in addition to the ECS row, the shadow
        vector index receives an upsert of
        ``(entity_id, embedding, VOLATILE)``. Per ARCHITECTURE.md §7
        the vector index is authoritative for "what exists," so this
        upsert is the primary record of the deposit.

        Raises
        ------
        ProtectedQuotaExceededError
            If ``protected_floor > 0.0`` and the ECS already holds
            ``self.config.quota_override`` protected entries.
        """
        entity_id = uuid4()
        now = time.time()

        # Hold the deposit lock across count_protected() + ecs.add() so two
        # concurrent protected deposits at quota-1 cannot both observe a
        # count below quota and both succeed (§10 hard cap). The lock scope
        # is intentionally narrow: vector_index.upsert runs outside it so
        # the §7 sequential-write ordering is unaffected.
        with self._deposit_lock:
            if (
                protected_floor > 0.0
                and self.ecs.count_protected() >= self.config.quota_override
            ):
                raise ProtectedQuotaExceededError(
                    f"protected quota of {self.config.quota_override} "
                    f"exceeded; Phase 3 unpin tool required "
                    f"(ARCHITECTURE.md §10)"
                )

            self.ecs.add(
                entity_id=entity_id,
                payload=payload,
                embedding=embedding,
                utility=1.0,
                protected_floor=protected_floor,
                state=EntityState.VOLATILE,
                now=now,
            )

        self.vector_index.upsert(
            entity_id, embedding, EntityState.VOLATILE
        )

        self.consolidation.mark_activity(now * 1000)
        return entity_id

    def query(
        self, embedding: List[float], limit: int = 5
    ) -> List[Memory]:
        """Retrieve the top-k memories by relevance to ``embedding``.

        ARCHITECTURE.md §4 evaluation point 1: lazy decay is applied
        to every live entity before scoring.

        Retrieval flow (Phase 1):
          1. Decay all (eval point 1).
          2. Over-fetch by cosine similarity from the shadow vector
             index.
          3. Project hits to ``Memory`` via ECS (source of truth for
             utility, attended_count, etc.).
          4. Rerank by ``cosine_similarity * utility`` so decayed
             memories are naturally demoted. Phase 1 convention;
             Phase 2 benchmark work may refine.
          5. Return the top ``limit`` after reranking.
        """
        now = time.time()

        self.ecs.decay_all(self.decay.lambda_, now)

        if self.ecs.n == 0:
            return []

        over_fetch_k = max(len(self.vector_index), 1)
        hits = self.vector_index.query(embedding, over_fetch_k)

        ranked: list[tuple[float, Memory]] = []
        for entity_id, cos_sim in hits:
            memory = self.ecs.get_memory(entity_id)
            if memory is None:
                continue
            ranked.append((cos_sim * memory.utility, memory))
        ranked.sort(key=lambda t: t[0], reverse=True)

        self.consolidation.mark_activity(now * 1000)
        return [m for _, m in ranked[:limit]]

    def signal_attention(self, weights: Dict[UUID, float]) -> None:
        """Record agent attention for the given entities.

        Writes go to the append-only attention log (ARCHITECTURE.md
        §5.1). If durability is enabled, each signal is also fsync'd to
        the WAL so that a kill -9 after the return does not lose the
        signal. The ECS update happens when the sleep-pass reducer
        drains the log.
        """
        now = time.time()
        for entity_id, weight in weights.items():
            w = float(weight)
            self.attention.append(entity_id, w, now)
            if self.durability is not None:
                self.durability.wal_append(
                    AttentionEntry(entity_id, w, now)
                )
        self.consolidation.mark_activity(now * 1000)

    def get_consolidation_manifest(self) -> List[Memory]:
        """Return the list of entities currently staged for USD consolidation.

        ARCHITECTURE.md §2 surface. Delegates to
        :func:`manifest.build_manifest`. Entities become
        ``STAGED_FOR_SYNC`` only when a sleep pass has run and selected
        them per §6 criteria.
        """
        return build_manifest(self.ecs)

    # ------------------------------------------------------------------
    # Harness-level operators (not part of the agent-facing surface)
    # ------------------------------------------------------------------

    def run_sleep_pass(self) -> ConsolidationResult:
        """Execute one consolidation sleep pass. Harness-level operator.

        Not part of the agent-facing four-op API. Harnesses, tests, and
        the Consolidation Engineer's scheduler call this. Agents never
        do.
        """
        now = time.time()
        result = self.consolidation.run_pass(
            ecs=self.ecs,
            decay=self.decay,
            attention_log=self.attention,
            vector_index=self.vector_index,
            sequential_writer=self.sequential_writer,
            now=now,
        )
        if self.durability is not None:
            # Snapshot after a successful pass so the next restart
            # doesn't need to replay an unbounded WAL.
            self.durability.snapshot_ecs(self.ecs)
        return result


# ----------------------------------------------------------------------
# Smoke check — Substrate / Persistence / Consolidation handoff cover
# ----------------------------------------------------------------------


def smoke_check() -> None:
    """End-to-end exercise of the four-op API + a consolidation pass.

    Pass 3 coverage: deposit -> query -> attention -> sleep pass ->
    manifest. Constructs its own ephemeral handle so callers do not
    need to manage lifecycle. Raises on any deviation.
    """
    with Moneta(MonetaConfig.ephemeral()) as m:
        assert m.query([0.0, 0.0, 0.0]) == []
        assert m.get_consolidation_manifest() == []

        eid = m.deposit("hello world", [1.0, 0.0, 0.0])
        assert isinstance(eid, UUID)

        results = m.query([1.0, 0.0, 0.0], limit=5)
        assert len(results) == 1
        assert isinstance(results[0], Memory)
        assert results[0].entity_id == eid
        assert results[0].state == EntityState.VOLATILE
        assert 0.99 <= results[0].utility <= 1.0, (
            f"expected utility ~ 1.0, got {results[0].utility}"
        )
        assert results[0].attended_count == 0

        m.signal_attention({eid: 0.2})
        result = m.run_sleep_pass()
        assert result.attention_updated == 1
        assert result.pruned == 0
        assert result.staged == 0

        results2 = m.query([1.0, 0.0, 0.0], limit=5)
        assert len(results2) == 1
        assert results2[0].attended_count == 1, (
            f"expected attended_count=1, got {results2[0].attended_count}"
        )

        manifest = m.get_consolidation_manifest()
        assert manifest == [], (
            f"fresh high-utility memory must not stage, got {len(manifest)}"
        )

    _logger.info("moneta.api.smoke_check OK")
