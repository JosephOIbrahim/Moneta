"""Sleep-pass trigger + selection criteria + commit coordinator.

ARCHITECTURE.md §6. Phase 3 target, active in Phase 1 against the mock
USD authoring target.

Trigger conditions (MONETA.md §2.6)
-----------------------------------
- ECS volatile count exceeds `MAX_ENTITIES` (default 10000, ruling #5)
- Inference queue idle > 5000 ms (opportunistic)

Selection criteria (locked Round 2 defaults; do not tune)
---------------------------------------------------------
- **Prune** (delete entirely):
    `Utility < 0.1 AND AttendedCount < 3`
- **Stage** (flag for USD authoring):
    `Utility < 0.3 AND AttendedCount >= 3`

Pass flow
---------
`ConsolidationRunner.run_pass` executes:

  1. Drain + reduce the attention log (also runs decay eval point 2)
  2. Apply decay eval point 3 (idempotent with step 1 under normal flow,
     but explicit per ARCHITECTURE.md §4 — the spec mandates three
     distinct evaluation points, not two)
  3. Classify volatile entities into prune / stage
  4. Prune: remove from ECS and vector index
  5. Stage: transition to STAGED_FOR_SYNC, commit via sequential writer,
     transition to CONSOLIDATED on success
  6. Return a summary tuple
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Optional, Tuple
from uuid import UUID

from .attention_log import AttentionLog, reduce_attention_log
from .decay import DecayConfig
from .ecs import ECS
from .sequential_writer import SequentialWriter, VectorIndexTarget
from .types import EntityState, Memory

_logger = logging.getLogger(__name__)

# Defaults ---------------------------------------------------------

DEFAULT_MAX_ENTITIES = 10000  # ruling #5, MONETA.md §2.6
DEFAULT_IDLE_TRIGGER_MS = 5000  # MONETA.md §2.6

# Locked Round 2 selection thresholds (ARCHITECTURE.md §6).
PRUNE_UTILITY_THRESHOLD = 0.1
PRUNE_ATTENDED_THRESHOLD = 3
STAGE_UTILITY_THRESHOLD = 0.3
STAGE_ATTENDED_THRESHOLD = 3


class ConsolidationResult(NamedTuple):
    """Summary of a single sleep-pass execution."""

    attention_updated: int
    pruned: int
    staged: int
    authored_at: Optional[float]


class ConsolidationRunner:
    """Coordinates sleep-pass trigger + selection + commit."""

    def __init__(
        self,
        max_entities: int = DEFAULT_MAX_ENTITIES,
        idle_trigger_ms: int = DEFAULT_IDLE_TRIGGER_MS,
    ) -> None:
        self._max_entities = max_entities
        self._idle_trigger_ms = idle_trigger_ms
        self._last_activity_ms: float = 0.0

    # --- trigger ------------------------------------------------------

    def mark_activity(self, now_ms: float) -> None:
        """Reset the idle clock. Called on each agent operation."""
        self._last_activity_ms = now_ms

    def should_run(self, ecs: ECS, now_ms: float) -> bool:
        """Pressure (MAX_ENTITIES) or opportunistic (idle) trigger."""
        if ecs.n >= self._max_entities:
            return True
        if self._last_activity_ms == 0.0:
            return False
        if now_ms - self._last_activity_ms >= self._idle_trigger_ms:
            return True
        return False

    # --- classification ----------------------------------------------

    def classify(self, ecs: ECS) -> Tuple[List[UUID], List[UUID]]:
        """Classify volatile entities into `(prune_ids, stage_ids)`.

        Callers must have run decay recently — typically immediately
        before calling this — so the utility values reflect current time.
        """
        prune_ids: List[UUID] = []
        stage_ids: List[UUID] = []
        for memory in ecs.iter_rows():
            if memory.state != EntityState.VOLATILE:
                continue
            if (
                memory.utility < PRUNE_UTILITY_THRESHOLD
                and memory.attended_count < PRUNE_ATTENDED_THRESHOLD
            ):
                prune_ids.append(memory.entity_id)
            elif (
                memory.utility < STAGE_UTILITY_THRESHOLD
                and memory.attended_count >= STAGE_ATTENDED_THRESHOLD
            ):
                stage_ids.append(memory.entity_id)
        return prune_ids, stage_ids

    # --- pass execution ----------------------------------------------

    def run_pass(
        self,
        ecs: ECS,
        decay: DecayConfig,
        attention_log: AttentionLog,
        vector_index: VectorIndexTarget,
        sequential_writer: Optional[SequentialWriter],
        now: float,
    ) -> ConsolidationResult:
        """Execute one full sleep pass.

        Arguments
        ---------
        ecs, decay, attention_log, vector_index:
            Required substrate handles.
        sequential_writer:
            Optional. If `None`, staging is classified but NOT committed —
            staged entities remain in VOLATILE state and will be
            re-classified on the next pass. Used for dry-run inspection.
            **Pruning is asymmetric**: prune still happens in dry-run
            mode because prune has no USD side (it is a local ECS +
            vector delete), so the sequential writer is not on the
            prune path. Dry-run is therefore classify-only for staging
            but state-mutating for pruning. Callers wanting a true
            read-only preview should use `classify()` directly instead
            of passing `sequential_writer=None`.
        now:
            Wall-clock unix seconds.
        """
        # 1. Drain + reduce attention log (runs decay eval point 2).
        attention_updated = reduce_attention_log(
            attention_log, ecs, decay, now
        )

        # 2. Decay eval point 3. Redundant with #1 under normal flow (Δt=0),
        # but explicit per ARCHITECTURE.md §4: the spec mandates three
        # evaluation points, not two.
        ecs.decay_all(decay.lambda_, now)

        # 3. Classify.
        prune_ids, stage_ids = self.classify(ecs)

        # 4. Prune: ECS + vector index delete.
        for eid in prune_ids:
            ecs.remove(eid)
            vector_index.delete(eid)

        # 5. Stage: flag, commit, advance to CONSOLIDATED.
        authoring_at: Optional[float] = None
        if stage_ids and sequential_writer is not None:
            staged_memories: List[Memory] = []
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.STAGED_FOR_SYNC)
                memory = ecs.get_memory(eid)
                if memory is not None:
                    staged_memories.append(memory)
            result = sequential_writer.commit_staging(staged_memories)
            authoring_at = result.authored_at
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.CONSOLIDATED)

        summary = ConsolidationResult(
            attention_updated=attention_updated,
            pruned=len(prune_ids),
            staged=len(stage_ids),
            authored_at=authoring_at,
        )
        _logger.info(
            "consolidation.run_pass attended=%d pruned=%d staged=%d",
            summary.attention_updated,
            summary.pruned,
            summary.staged,
        )
        return summary
