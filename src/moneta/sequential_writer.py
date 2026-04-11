"""Sequential writer — USD-first, vector-second atomicity.

ARCHITECTURE.md §7. The ordering discipline is:

  1. USD authoring target is called first (for Phase 1, this is the mock
     consolidation target; for Phase 3, it is the real pxr/Sdf-based
     writer). The target's `flush()` is awaited before step 2.
  2. Vector index is updated second — this is the authoritative source
     for "what exists".
  3. If the vector-index update fails, the authoring-target state is
     NOT rolled back. Per §7, USD orphans from interrupted writes are
     benign: Pcp never traverses unreferenced prims, so they cost zero
     RAM and zero compute. Healing is implicit — the next scan either
     finds the entity in the vector index (live) or not (orphan ignored).

No 2PC. No rollback. The ordering IS the protocol.

Phase 3 drop-in
---------------

Both the Phase 1 mock target (`mock_usd_target.MockUsdTarget`) and any
Phase 3 real-USD authoring module implement the `AuthoringTarget`
Protocol defined here. `SequentialWriter` accepts an instance via
constructor injection, so replacing mock with real USD in Phase 3 is a
single construction-site swap. Neither this file nor any consumer of it
needs to change at the Protocol boundary.
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Protocol
from uuid import UUID

from .types import EntityState, Memory

_logger = logging.getLogger(__name__)


class AuthoringResult(NamedTuple):
    """Per-batch result from an `AuthoringTarget`."""

    entity_ids: List[UUID]
    authored_at: float  # wall-clock unix seconds
    target: str  # "mock" (Phase 1) or "usd" (Phase 3)
    batch_id: str  # UUID string for this batch


class AuthoringTarget(Protocol):
    """The 'USD side' of the sequential write.

    Phase 1 implementation: `mock_usd_target.MockUsdTarget` (JSONL log).
    Phase 3 implementation: pxr/Sdf-based writer (not in this repo).

    Both must satisfy this Protocol so `SequentialWriter` can swap them
    without code changes.
    """

    def author_stage_batch(self, entities: List[Memory]) -> AuthoringResult:
        """Author a batch of staged entities to the underlying target."""
        ...

    def flush(self) -> None:
        """Ensure all pending authorings are durable (e.g. fsync, Save)."""
        ...


class VectorIndexTarget(Protocol):
    """The 'vector side' of the sequential write.

    Implemented by `vector_index.VectorIndex`. Protocol-typed here so that
    `SequentialWriter` has no import dependency on the concrete class.
    """

    def upsert(
        self, entity_id: UUID, vector: List[float], state: EntityState
    ) -> None: ...

    def update_state(self, entity_id: UUID, state: EntityState) -> None: ...

    def delete(self, entity_id: UUID) -> None: ...


class SequentialWriter:
    """Coordinates USD-first, vector-second commits per ARCHITECTURE.md §7.

    Deposit-path note
    -----------------
    In Phase 1, deposits do NOT flow through the sequential writer — the
    "USD side" is only written at consolidation time, so deposits write
    directly to the vector index. This coordinator is used only by
    `consolidation.ConsolidationRunner.run_pass` when a staging batch is
    ready to commit.
    """

    def __init__(
        self,
        authoring_target: AuthoringTarget,
        vector_index: VectorIndexTarget,
    ) -> None:
        self._target = authoring_target
        self._vector = vector_index

    def commit_staging(self, staged: List[Memory]) -> AuthoringResult:
        """Commit a staging batch. Authoring first, vector second.

        Returns the `AuthoringResult` from the authoring target. If the
        vector-index update raises, the authoring-target state is left
        intact (benign orphan per §7), and the exception propagates.
        """
        result = self._target.author_stage_batch(staged)
        self._target.flush()
        _logger.info(
            "sequential_writer.author count=%d target=%s batch=%s",
            len(staged),
            result.target,
            result.batch_id,
        )

        for memory in staged:
            self._vector.update_state(memory.entity_id, EntityState.CONSOLIDATED)
        _logger.info("sequential_writer.vector_update count=%d", len(staged))

        return result
