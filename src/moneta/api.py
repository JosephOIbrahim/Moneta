"""Moneta agent-facing API — the four operations.

ARCHITECTURE.md §2. The entire agent-facing surface consists of exactly
these four callables:

    deposit
    query
    signal_attention
    get_consolidation_manifest

No fifth operation may be added without MONETA.md §9 escalation. The
signatures below are verbatim from MONETA.md §2.1; parameter names,
defaults, and type annotations must not drift.

`init()`, `smoke_check()`, `run_sleep_pass()`, and `MonetaConfig` are
harness-level, not agent-facing. They exist to bootstrap the module-level
substrate and to satisfy the Persistence / Consolidation handoff
contracts. Agents call the four operations; harnesses call `init()` first
and `run_sleep_pass()` when they decide to consolidate.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from .attention_log import AttentionEntry, AttentionLog, reduce_attention_log
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

# ARCHITECTURE.md §10: 100 protected entries per agent, hard cap.
PROTECTED_QUOTA: int = 100


class MonetaNotInitializedError(RuntimeError):
    """Raised when an agent-facing operation runs before `init()`."""


class ProtectedQuotaExceededError(RuntimeError):
    """Raised when a protected deposit would exceed `PROTECTED_QUOTA`.

    Phase 1 enforcement per ARCHITECTURE.md §10: `deposit` raises on
    overflow. Phase 3 adds an operator-facing unpin tool (explicitly NOT
    part of the four-op API) that lets operators reclaim slots.
    """


# ----------------------------------------------------------------------
# Harness-level configuration
# ----------------------------------------------------------------------


@dataclass
class MonetaConfig:
    """Harness-level configuration for `init()`. Not part of the agent API.

    Sensible defaults let `init()` work with no arguments, producing an
    in-memory substrate suitable for unit tests and the smoke check.
    Populate the `*_path` fields to enable durability and persistent
    mock-USD logging.
    """

    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS
    embedding_dim: Optional[int] = None  # None → inferred on first deposit
    max_entities: int = DEFAULT_MAX_ENTITIES

    # Durability (None → ephemeral, no crash recovery)
    snapshot_path: Optional[Path] = None
    wal_path: Optional[Path] = None

    # Vector index persistence path — currently ignored (Phase 1 backend
    # is in-memory). Retained for Phase 2+ LanceDB adoption.
    vector_persist_path: Optional[Path] = None

    # Mock USD log destination. None → in-memory ephemeral buffer.
    mock_target_log_path: Optional[Path] = None

    # Phase 3 real USD target (ARCHITECTURE.md §15).
    # use_real_usd=True routes consolidation writes through UsdTarget
    # instead of MockUsdTarget. Default False preserves Phase 1 behavior.
    use_real_usd: bool = False
    # Rolling sublayer directory for UsdTarget. None → in-memory anonymous
    # layers (useful for tests). Only used when use_real_usd=True.
    usd_target_path: Optional[Path] = None


# ----------------------------------------------------------------------
# Unified module state
# ----------------------------------------------------------------------


@dataclass
class _ModuleState:
    """All Moneta substrate state lives here. Replaces the Pass 2 globals."""

    ecs: ECS
    decay: DecayConfig
    attention: AttentionLog
    vector_index: VectorIndex
    consolidation: ConsolidationRunner
    sequential_writer: SequentialWriter
    authoring_target: object  # MockUsdTarget or UsdTarget (AuthoringTarget Protocol)
    mock_target: Optional[MockUsdTarget] = None  # set only when mock is active; test compat
    durability: Optional[DurabilityManager] = None


_state: Optional[_ModuleState] = None


def _require_state() -> _ModuleState:
    """Return the module state or raise `MonetaNotInitializedError`."""
    if _state is None:
        raise MonetaNotInitializedError(
            "moneta.api is not initialized; call moneta.init() first"
        )
    return _state


def _reset_state() -> None:
    """Test-harness hook: discard module state. Not part of the agent API.

    Closes any open files (durability WAL, mock-USD log). Safe to call on
    uninitialized state.
    """
    global _state
    if _state is not None:
        if _state.durability is not None:
            _state.durability.close()
        if hasattr(_state.authoring_target, "close"):
            _state.authoring_target.close()
    _state = None


# ----------------------------------------------------------------------
# init — harness bootstrap
# ----------------------------------------------------------------------


def init(
    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
    *,
    config: Optional[MonetaConfig] = None,
) -> None:
    """Initialize the Moneta substrate. Harness-level, NOT agent-facing.

    Two call styles:

        init()                               # defaults, in-memory only
        init(half_life_seconds=600)          # quick half-life override
        init(config=MonetaConfig(...))       # full configuration

    Calling `init()` replaces any existing state. Safe to call multiple
    times in test harnesses; do not call mid-session in production.
    """
    global _state

    if config is None:
        config = MonetaConfig(half_life_seconds=half_life_seconds)
    elif half_life_seconds != DEFAULT_HALF_LIFE_SECONDS:
        # Caller passed both — config wins but flag the conflict.
        _logger.warning(
            "init() received both half_life_seconds and config; config wins"
        )

    _reset_state()

    decay = DecayConfig(half_life_seconds=config.half_life_seconds)
    attention = AttentionLog()

    vector_index = VectorIndex(
        embedding_dim=config.embedding_dim,
        persist_path=config.vector_persist_path,
    )

    durability: Optional[DurabilityManager] = None
    if config.snapshot_path is not None and config.wal_path is not None:
        durability = DurabilityManager(
            snapshot_path=config.snapshot_path,
            wal_path=config.wal_path,
        )
        ecs, wal_replay = durability.hydrate()
        # Rebuild vector index from hydrated ECS (shadow rebuild).
        for memory in ecs.iter_rows():
            vector_index.upsert(
                memory.entity_id, memory.semantic_vector, memory.state
            )
        # Replay WAL entries into attention log for reduction.
        for entry in wal_replay:
            attention.append(entry.entity_id, entry.weight, entry.timestamp)
        _logger.info(
            "init.hydrate n=%d wal_replay=%d", ecs.n, len(wal_replay)
        )
    else:
        ecs = ECS()

    # Target selection: real USD (Phase 3) or mock (Phase 1 / dev / test).
    # UsdTarget imported function-level to keep api.py importable under
    # plain Python 3.14 where pxr is unavailable. Phase 1 tests never
    # set use_real_usd=True, so the import never fires for them.
    mock_target: Optional[MockUsdTarget] = None
    if config.use_real_usd:
        from .usd_target import UsdTarget

        authoring_target = UsdTarget(log_path=config.usd_target_path)
    else:
        mock_target = MockUsdTarget(log_path=config.mock_target_log_path)
        authoring_target = mock_target

    sequential_writer = SequentialWriter(authoring_target, vector_index)
    consolidation = ConsolidationRunner(max_entities=config.max_entities)

    _state = _ModuleState(
        ecs=ecs,
        decay=decay,
        attention=attention,
        vector_index=vector_index,
        consolidation=consolidation,
        sequential_writer=sequential_writer,
        authoring_target=authoring_target,
        mock_target=mock_target,
        durability=durability,
    )
    _logger.info(
        "moneta.init complete half_life=%.1fs max_entities=%d durability=%s target=%s",
        config.half_life_seconds,
        config.max_entities,
        "on" if durability is not None else "off",
        "usd" if config.use_real_usd else "mock",
    )


# ----------------------------------------------------------------------
# The four operations (ARCHITECTURE.md §2)
# Signatures are verbatim from MONETA.md §2.1 — do not drift.
# ----------------------------------------------------------------------


def deposit(payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID:
    """Deposit a new memory and return its EntityID.

    Phase 1 convention: fresh memories start at `Utility = 1.0`.

    Persistence wiring: in addition to the ECS row, the shadow vector
    index receives an upsert of `(entity_id, embedding, VOLATILE)`. Per
    ARCHITECTURE.md §7 the vector index is authoritative for "what
    exists," so this upsert is the primary record of the deposit.

    Raises:
        ProtectedQuotaExceededError: if `protected_floor > 0.0` and the
            ECS already holds `PROTECTED_QUOTA` protected entries.
    """
    state = _require_state()

    if protected_floor > 0.0 and state.ecs.count_protected() >= PROTECTED_QUOTA:
        raise ProtectedQuotaExceededError(
            f"protected quota of {PROTECTED_QUOTA} exceeded; "
            f"Phase 3 unpin tool required (ARCHITECTURE.md §10)"
        )

    entity_id = uuid4()
    now = time.time()

    state.ecs.add(
        entity_id=entity_id,
        payload=payload,
        embedding=embedding,
        utility=1.0,
        protected_floor=protected_floor,
        state=EntityState.VOLATILE,
        now=now,
    )
    state.vector_index.upsert(entity_id, embedding, EntityState.VOLATILE)

    state.consolidation.mark_activity(now * 1000)
    return entity_id


def query(embedding: List[float], limit: int = 5) -> List[Memory]:
    """Retrieve the top-k memories by relevance to `embedding`.

    ARCHITECTURE.md §4 evaluation point 1: lazy decay is applied to every
    live entity before scoring.

    Retrieval flow (Phase 1):
      1. Decay all (eval point 1).
      2. Over-fetch by cosine similarity from the shadow vector index.
      3. Project hits to `Memory` via ECS (source of truth for utility,
         attended_count, etc.).
      4. Rerank by `cosine_similarity * utility` so decayed memories are
         naturally demoted. This is a Phase 1 convention; Phase 2
         benchmark work may refine.
      5. Return the top `limit` after reranking.
    """
    state = _require_state()
    now = time.time()

    # Eval point 1: decay before retrieval.
    state.ecs.decay_all(state.decay.lambda_, now)

    if state.ecs.n == 0:
        return []

    # Over-fetch the entire index so reranking cannot clip high-utility
    # entries below the similarity cutoff. Acceptable at Phase 1 scales
    # (MAX_ENTITIES default 10000); Phase 2 profiling may introduce a
    # bounded over-fetch heuristic.
    over_fetch_k = max(len(state.vector_index), 1)
    hits = state.vector_index.query(embedding, over_fetch_k)

    ranked: list[tuple[float, Memory]] = []
    for entity_id, cos_sim in hits:
        memory = state.ecs.get_memory(entity_id)
        if memory is None:
            # Orphan in the vector index — benign per §7.
            continue
        ranked.append((cos_sim * memory.utility, memory))
    ranked.sort(key=lambda t: t[0], reverse=True)

    state.consolidation.mark_activity(now * 1000)
    return [m for _, m in ranked[:limit]]


def signal_attention(weights: Dict[UUID, float]) -> None:
    """Record agent attention for the given entities.

    Writes go to the append-only attention log (ARCHITECTURE.md §5.1).
    If durability is enabled, each signal is also fsync'd to the WAL so
    that a kill -9 after the return does not lose the signal. The ECS
    update happens when the sleep-pass reducer drains the log.
    """
    state = _require_state()
    now = time.time()
    for entity_id, weight in weights.items():
        w = float(weight)
        state.attention.append(entity_id, w, now)
        if state.durability is not None:
            state.durability.wal_append(AttentionEntry(entity_id, w, now))
    state.consolidation.mark_activity(now * 1000)


def get_consolidation_manifest() -> List[Memory]:
    """Return the list of entities currently staged for USD consolidation.

    ARCHITECTURE.md §2 surface. Delegates to
    `manifest.build_manifest(ecs)`. Entities become `STAGED_FOR_SYNC`
    only when a sleep pass has run and selected them per §6 criteria.
    """
    state = _require_state()
    return build_manifest(state.ecs)


# ----------------------------------------------------------------------
# Harness-level operators (not part of the agent-facing surface)
# ----------------------------------------------------------------------


def run_sleep_pass() -> ConsolidationResult:
    """Execute one consolidation sleep pass. Harness-level operator.

    Not part of the agent-facing four-op API. Harnesses, tests, and
    Consolidation Engineer's scheduler call this. Agents never do.
    """
    state = _require_state()
    now = time.time()
    result = state.consolidation.run_pass(
        ecs=state.ecs,
        decay=state.decay,
        attention_log=state.attention,
        vector_index=state.vector_index,
        sequential_writer=state.sequential_writer,
        now=now,
    )
    if state.durability is not None:
        # Snapshot after a successful pass so the next restart doesn't
        # need to replay an unbounded WAL.
        state.durability.snapshot_ecs(state.ecs)
    return result


# ----------------------------------------------------------------------
# Smoke check — Substrate / Persistence / Consolidation handoff cover
# ----------------------------------------------------------------------


def smoke_check() -> None:
    """End-to-end exercise of the four-op API + consolidation pass.

    Pass 3 coverage: deposit → query → attention → sleep pass → manifest.
    Exercises every module in src/moneta/ that does not depend on
    external runtime deps. Raises on any deviation.
    """
    init()

    assert query([0.0, 0.0, 0.0]) == []
    assert get_consolidation_manifest() == []

    eid = deposit("hello world", [1.0, 0.0, 0.0])
    assert isinstance(eid, UUID)

    results = query([1.0, 0.0, 0.0], limit=5)
    assert len(results) == 1
    assert isinstance(results[0], Memory)
    assert results[0].entity_id == eid
    assert results[0].state == EntityState.VOLATILE
    # Utility decays by ~1e-10 between deposit and query at 6-hour
    # half-life (eval point 1). Anything ≥ 0.99 is fine.
    assert 0.99 <= results[0].utility <= 1.0, (
        f"expected utility ≈ 1.0, got {results[0].utility}"
    )
    assert results[0].attended_count == 0

    signal_attention({eid: 0.2})
    # Sleep pass: drain log, reduce, classify, (no prune/stage for a
    # fresh single-entity case), return.
    result = run_sleep_pass()
    assert result.attention_updated == 1
    assert result.pruned == 0
    assert result.staged == 0

    # After attention reducer: attended_count should be 1.
    results2 = query([1.0, 0.0, 0.0], limit=5)
    assert len(results2) == 1
    assert results2[0].attended_count == 1, (
        f"expected attended_count=1, got {results2[0].attended_count}"
    )

    manifest = get_consolidation_manifest()
    assert manifest == [], (
        f"fresh high-utility memory must not stage, got {len(manifest)}"
    )

    _logger.info("moneta.api.smoke_check OK")
