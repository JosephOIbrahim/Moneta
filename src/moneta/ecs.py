"""Moneta hot-tier ECS — flat struct-of-arrays, list-backed.

ARCHITECTURE.md §3. The hot tier stores one row per entity; each component
field is a parallel column. Phase 1 uses stdlib lists for every column,
accepting O(n) scan cost in exchange for zero runtime dependencies and a
single-file implementation the Test Engineer can reason about directly.

This choice is a Substrate Engineer judgment call, not a spec mandate.
MONETA.md §2.2 says the hot tier is "Flat, vectorizable, struct-of-arrays
or DataFrame-backed." The list-backed SoA satisfies "flat" and "struct-of-
arrays" literally, and remains "vectorizable" in the sense that the columns
can be wrapped as numpy views later without changing the interface. Phase 2
profiling decides whether to promote to numpy or pandas.

Concurrency: single-writer. Agent operations (`deposit`, `query`) and the
sleep-pass reducer (Consolidation Engineer's trigger) must not run
concurrently on the same instance. The attention log (ARCHITECTURE.md §5.1)
is the only lock-free entry point into Moneta; exclusion for the non-log
write paths is Consolidation Engineer's responsibility.

Row removal uses swap-and-pop for O(1) cost. The `_id_to_row` index is
maintained alongside every structural mutation.
"""
from __future__ import annotations

import logging
import math
from typing import Optional
from uuid import UUID

from .decay import decay_value
from .types import EntityState, Memory

_logger = logging.getLogger(__name__)


class ECS:
    """Struct-of-arrays ECS for Moneta's hot tier.

    Each component field from ARCHITECTURE.md §3 is stored as a parallel
    column. Entities are addressed by `EntityID` (UUID) and internally
    indexed by row position.
    """

    def __init__(self) -> None:
        # Parallel columns. Indices [0, n) are live; there are no holes.
        self._ids: list[UUID] = []
        self._payloads: list[str] = []
        self._embeddings: list[list[float]] = []
        self._utility: list[float] = []
        self._attended: list[int] = []
        self._protected_floor: list[float] = []
        self._last_evaluated: list[float] = []
        self._state: list[EntityState] = []
        self._usd_link: list[Optional[object]] = []

        # Index: entity_id -> row.
        self._id_to_row: dict[UUID, int] = {}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def n(self) -> int:
        """Number of live entities."""
        return len(self._ids)

    def contains(self, entity_id: UUID) -> bool:
        return entity_id in self._id_to_row

    def count_protected(self) -> int:
        """ARCHITECTURE.md §10 quota backstop."""
        return sum(1 for pf in self._protected_floor if pf > 0.0)

    # ------------------------------------------------------------------
    # Structural write operations
    # ------------------------------------------------------------------

    def add(
        self,
        entity_id: UUID,
        payload: str,
        embedding: list[float],
        utility: float,
        protected_floor: float,
        state: EntityState,
        now: float,
        usd_link: Optional[object] = None,
    ) -> int:
        """Append a new entity. Returns the row index."""
        if entity_id in self._id_to_row:
            raise ValueError(f"entity_id {entity_id} already present")
        row = len(self._ids)
        self._ids.append(entity_id)
        self._payloads.append(payload)
        self._embeddings.append(list(embedding))
        self._utility.append(float(utility))
        self._attended.append(0)
        self._protected_floor.append(float(protected_floor))
        self._last_evaluated.append(float(now))
        self._state.append(state)
        self._usd_link.append(usd_link)
        self._id_to_row[entity_id] = row
        return row

    def remove(self, entity_id: UUID) -> None:
        """Remove an entity via swap-and-pop. O(1)."""
        row = self._id_to_row.pop(entity_id)
        last = len(self._ids) - 1
        if row != last:
            swapped_id = self._ids[last]
            self._ids[row] = swapped_id
            self._payloads[row] = self._payloads[last]
            self._embeddings[row] = self._embeddings[last]
            self._utility[row] = self._utility[last]
            self._attended[row] = self._attended[last]
            self._protected_floor[row] = self._protected_floor[last]
            self._last_evaluated[row] = self._last_evaluated[last]
            self._state[row] = self._state[last]
            self._usd_link[row] = self._usd_link[last]
            self._id_to_row[swapped_id] = row
        self._ids.pop()
        self._payloads.pop()
        self._embeddings.pop()
        self._utility.pop()
        self._attended.pop()
        self._protected_floor.pop()
        self._last_evaluated.pop()
        self._state.pop()
        self._usd_link.pop()

    def set_state(self, entity_id: UUID, state: EntityState) -> None:
        row = self._id_to_row[entity_id]
        self._state[row] = state

    def iter_rows(self) -> "Iterator[Memory]":
        """Yield every live entity as a Memory snapshot.

        Used by durability (for snapshotting) and consolidation (for
        classification). Safe under single-writer conditions — do not
        mutate the ECS during iteration.
        """
        for i in range(len(self._ids)):
            yield self._row_to_memory(i)

    def hydrate_row(self, memory: Memory) -> int:
        """Insert a row from a durability snapshot, preserving all state.

        Distinct from `add()` because it carries `attended_count` and
        `last_evaluated` from the snapshot rather than initializing from
        scratch. Raises `ValueError` if the entity is already present.
        """
        if memory.entity_id in self._id_to_row:
            raise ValueError(f"entity_id {memory.entity_id} already present")
        row = len(self._ids)
        self._ids.append(memory.entity_id)
        self._payloads.append(memory.payload)
        self._embeddings.append(list(memory.semantic_vector))
        self._utility.append(float(memory.utility))
        self._attended.append(int(memory.attended_count))
        self._protected_floor.append(float(memory.protected_floor))
        self._last_evaluated.append(float(memory.last_evaluated))
        self._state.append(memory.state)
        self._usd_link.append(memory.usd_link)
        self._id_to_row[memory.entity_id] = row
        return row

    def get_memory(self, entity_id: UUID) -> "Optional[Memory]":
        """Return a Memory snapshot for an entity, or None if not present."""
        row = self._id_to_row.get(entity_id)
        if row is None:
            return None
        return self._row_to_memory(row)

    # ------------------------------------------------------------------
    # Attention reducer (ARCHITECTURE.md §5)
    # ------------------------------------------------------------------

    def apply_attention(
        self,
        agg: dict[UUID, tuple[float, int]],
        now: float,
    ) -> int:
        """Apply an aggregated attention batch from the attention log.

        `agg` maps entity_id to `(summed_weight, signal_count)`, produced by
        `attention_log.aggregate`. Per ARCHITECTURE.md §5:

            Utility       = min(1.0, Utility + summed_weight)
            AttendedCount = AttendedCount + signal_count
            LastEvaluated = now

        `signal_count` is the number of `signal_attention` calls in the
        drained window that mentioned this entity. It is summed (not capped
        at 1) so an entity signaled 5 times in one window sees
        AttendedCount += 5, matching the per-call semantics of §2.4.

        Missing entities — i.e. pruned between signal time and reduce time —
        are silently skipped; the attention log is "eventually consistent"
        per §2.5. Returns the count of entities actually updated.
        """
        updated = 0
        for entity_id, (sum_weight, count) in agg.items():
            row = self._id_to_row.get(entity_id)
            if row is None:
                continue
            new_u = self._utility[row] + sum_weight
            self._utility[row] = 1.0 if new_u > 1.0 else new_u
            self._attended[row] += count
            self._last_evaluated[row] = now
            updated += 1
        return updated

    # ------------------------------------------------------------------
    # Decay (ARCHITECTURE.md §4)
    # ------------------------------------------------------------------

    def decay_all(self, lam: float, now: float) -> None:
        """Lazy exponential decay across all live entities.

        Called at evaluation points 1 (before retrieval) and 2 (after
        attention reduce). Decayed values are clamped to `protected_floor`.
        """
        for i in range(len(self._ids)):
            self._utility[i] = decay_value(
                self._utility[i],
                self._last_evaluated[i],
                self._protected_floor[i],
                lam,
                now,
            )
            self._last_evaluated[i] = now

    def decay_one(self, entity_id: UUID, lam: float, now: float) -> None:
        """Decay a single entity in place. Used by narrow hydration paths."""
        row = self._id_to_row[entity_id]
        self._utility[row] = decay_value(
            self._utility[row],
            self._last_evaluated[row],
            self._protected_floor[row],
            lam,
            now,
        )
        self._last_evaluated[row] = now

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def top_k_by_similarity(
        self,
        query_vec: list[float],
        k: int,
    ) -> list[Memory]:
        """Utility-weighted cosine similarity, linear scan.

        Score = cosine_similarity(query, entity.embedding) * entity.utility.

        The utility weighting is a Phase 1 convention — it makes decayed
        memories naturally less retrievable even when their semantic
        similarity is high. Not mandated by MONETA.md §2.2; Persistence
        Engineer may revisit when wiring the shadow vector index.

        Linear-scan Phase 1 placeholder. Persistence Engineer replaces this
        with a shadow vector index in a later pass.
        """
        n = len(self._ids)
        if n == 0 or k <= 0:
            return []
        q_norm_sq = 0.0
        for x in query_vec:
            q_norm_sq += x * x
        if q_norm_sq == 0.0:
            return []
        q_norm = math.sqrt(q_norm_sq)
        dim = len(query_vec)
        scored: list[tuple[float, int]] = []
        for i, vec in enumerate(self._embeddings):
            if len(vec) != dim:
                # Dimension mismatch is a Persistence concern; skip silently
                # at Substrate layer to keep top_k robust.
                continue
            dot = 0.0
            v_norm_sq = 0.0
            for a, b in zip(vec, query_vec):
                dot += a * b
                v_norm_sq += a * a
            if v_norm_sq == 0.0:
                continue
            cos_sim = dot / (math.sqrt(v_norm_sq) * q_norm)
            scored.append((cos_sim * self._utility[i], i))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [self._row_to_memory(row) for _, row in scored[:k]]

    def staged_entities(self) -> list[Memory]:
        """Return every entity currently in STAGED_FOR_SYNC."""
        return [
            self._row_to_memory(i)
            for i, st in enumerate(self._state)
            if st == EntityState.STAGED_FOR_SYNC
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _row_to_memory(self, row: int) -> Memory:
        """Project an ECS row into an immutable Memory snapshot."""
        return Memory(
            entity_id=self._ids[row],
            payload=self._payloads[row],
            semantic_vector=list(self._embeddings[row]),
            utility=self._utility[row],
            attended_count=self._attended[row],
            protected_floor=self._protected_floor[row],
            last_evaluated=self._last_evaluated[row],
            state=self._state[row],
            usd_link=self._usd_link[row],
        )
