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

import heapq
import logging
import math
import os
from array import array
from typing import Iterable, Optional, Sequence
from uuid import UUID

from .decay import decay_value
from .types import EntityState, Memory

_logger = logging.getLogger(__name__)

try:  # Optional native seam (seam rule, O27); the Python loop below is its oracle.
    import moneta_native as _native
except ImportError:  # pragma: no cover - exercised when the wheel is absent
    _native = None


def _compact_vector(values: "Iterable[float]") -> "Sequence[float]":
    """Store a vector as packed doubles; fall back to a list for anything
    array('d') cannot hold (non-numeric or out-of-range components)."""
    try:
        return array("d", values)
    except (TypeError, OverflowError):
        return list(values)


class ECS:
    """Struct-of-arrays ECS for Moneta's hot tier.

    Each component field from ARCHITECTURE.md §3 is stored as a parallel
    column. Entities are addressed by `EntityID` (UUID) and internally
    indexed by row position.
    """

    def __init__(self, native: Optional[bool] = None) -> None:
        # Native decay kernel: on by default when moneta_native is installed
        # (MONETA_NATIVE=0 forces the oracle). Bit-identical to decay_value
        # (tests/unit/test_native_decay_parity.py).
        if native is None:
            native = _native is not None and os.environ.get("MONETA_NATIVE", "1") != "0"
        elif native and _native is None:
            raise RuntimeError("native=True requested but moneta_native is not installed")
        self.native_decay: bool = bool(native)

        # Parallel columns. Indices [0, n) are live; there are no holes.
        self._ids: list[UUID] = []
        self._payloads: list[str] = []
        # Embeddings are held as array('d') (8 bytes per component) rather
        # than lists of float objects (~32 bytes each). Memory snapshots
        # still hand out plain lists; values are the same doubles.
        self._embeddings: list[Sequence[float]] = []
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
        self._embeddings.append(_compact_vector(embedding))
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
        self._embeddings.append(_compact_vector(memory.semantic_vector))
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
        n = len(self._ids)
        if self.native_decay and n:
            self._utility[:] = _native.decay_batch(
                self._utility, self._last_evaluated, self._protected_floor, lam, now
            )
            self._last_evaluated[:] = [now] * n
            return
        for i in range(n):
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

    def rank_hits(
        self,
        hits: "Iterable[tuple[UUID, float]]",
        limit: int,
    ) -> list[Memory]:
        """Rerank vector-index hits by ``max(cosine, 0.0) * utility``.

        ``hits`` are ``(entity_id, cosine)`` pairs in the index's order
        (cosine descending); ids absent from the ECS are skipped. Equal
        scores keep hit order (stable sort). Only the returned top
        ``limit`` rows are projected to ``Memory``.

        Exact early stop: with ``u_max = max(utility) >= 0``, every later
        hit scores at most ``max(cos, 0) * u_max`` (IEEE multiplication by a
        non-negative factor is monotone), and that bound is non-increasing
        along the hits. Once it is ``<=`` the current ``limit``-th best
        score, no later hit can enter the top ``limit``: a strictly lower
        score loses, and an equal one sorts after the earlier holder. The
        result is identical to ranking every hit.
        """
        id_to_row = self._id_to_row
        utility = self._utility
        ranked: list[tuple[float, int]] = []
        # The bound needs every utility finite (NaN breaks ordering) and
        # u_max >= 0; otherwise rank every hit, exactly as before.
        can_stop = limit > 0 and bool(utility) and math.isfinite(sum(utility))
        u_max = max(utility) if can_stop else 0.0
        can_stop = can_stop and u_max >= 0.0
        best: list[float] = []  # min-heap of the top `limit` scores so far
        for entity_id, cos_sim in hits:
            pos = cos_sim if cos_sim > 0.0 else 0.0
            if can_stop and len(best) == limit and pos * u_max <= best[0]:
                break
            row = id_to_row.get(entity_id)
            if row is None:
                continue
            score = max(cos_sim, 0.0) * utility[row]
            ranked.append((score, row))
            if score != score:  # NaN cosine: fall back to ranking every hit
                can_stop = False
            if can_stop:
                if len(best) < limit:
                    heapq.heappush(best, score)
                elif score > best[0]:
                    heapq.heapreplace(best, score)
        ranked.sort(key=lambda t: t[0], reverse=True)
        return [self._row_to_memory(row) for _, row in ranked[:limit]]

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
