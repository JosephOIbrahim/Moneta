"""Unit tests for `moneta.ecs`.

Covers ARCHITECTURE.md §3 (schema) and §5 (attention reducer semantics).
Exercises:
  - add / remove / iter_rows / hydrate_row / get_memory round-trips
  - Memory projection field completeness vs §3
  - apply_attention aggregation semantics (count per signal, not per entity)
  - top_k_by_similarity ordering (utility-weighted)
  - staged_entities selection
  - Note on the Substrate #8 bug pattern: exact-equality on freshly-deposited
    utility is fragile because query() runs decay first — tests assert
    ≥ 0.99 rather than == 1.0.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from moneta.ecs import ECS
from moneta.types import EntityState, Memory


# ---------------------------------------------------------------------
# Basic lifecycle
# ---------------------------------------------------------------------


class TestEcsLifecycle:
    def test_empty_ecs_has_n_zero(self) -> None:
        ecs = ECS()
        assert ecs.n == 0
        assert len(ecs) == 0
        assert ecs.count_protected() == 0

    def test_add_single_entity(self) -> None:
        ecs = ECS()
        eid = uuid4()
        row = ecs.add(
            entity_id=eid,
            payload="hello",
            embedding=[1.0, 0.0, 0.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=100.0,
        )
        assert row == 0
        assert ecs.n == 1
        assert ecs.contains(eid)

    def test_add_duplicate_raises(self) -> None:
        ecs = ECS()
        eid = uuid4()
        ecs.add(
            entity_id=eid,
            payload="a",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        with pytest.raises(ValueError, match="already present"):
            ecs.add(
                entity_id=eid,
                payload="b",
                embedding=[1.0],
                utility=1.0,
                protected_floor=0.0,
                state=EntityState.VOLATILE,
                now=0.0,
            )

    def test_remove_swap_and_pop(self) -> None:
        ecs = ECS()
        ids = []
        for i in range(3):
            eid = uuid4()
            ids.append(eid)
            ecs.add(
                entity_id=eid,
                payload=f"p{i}",
                embedding=[float(i)],
                utility=1.0,
                protected_floor=0.0,
                state=EntityState.VOLATILE,
                now=0.0,
            )
        assert ecs.n == 3
        ecs.remove(ids[0])
        assert ecs.n == 2
        assert not ecs.contains(ids[0])
        assert ecs.contains(ids[1])
        assert ecs.contains(ids[2])

    def test_remove_last_entity(self) -> None:
        ecs = ECS()
        eid = uuid4()
        ecs.add(
            entity_id=eid,
            payload="solo",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        ecs.remove(eid)
        assert ecs.n == 0

    def test_count_protected(self) -> None:
        ecs = ECS()
        ecs.add(
            entity_id=uuid4(),
            payload="protected",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.2,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        ecs.add(
            entity_id=uuid4(),
            payload="ephemeral",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        assert ecs.count_protected() == 1


# ---------------------------------------------------------------------
# iter_rows / hydrate_row round-trip
# ---------------------------------------------------------------------


class TestIterAndHydrate:
    def test_iter_rows_yields_memories(self) -> None:
        ecs = ECS()
        eid = uuid4()
        ecs.add(
            entity_id=eid,
            payload="x",
            embedding=[0.1, 0.2],
            utility=0.8,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=42.0,
        )
        rows = list(ecs.iter_rows())
        assert len(rows) == 1
        assert isinstance(rows[0], Memory)
        assert rows[0].entity_id == eid
        assert rows[0].payload == "x"
        assert rows[0].semantic_vector == [0.1, 0.2]
        assert rows[0].utility == 0.8
        assert rows[0].attended_count == 0
        assert rows[0].last_evaluated == 42.0
        assert rows[0].state == EntityState.VOLATILE

    def test_memory_projection_carries_all_section_3_fields(self) -> None:
        """ARCHITECTURE.md §3: Memory must project every schema column."""
        ecs = ECS()
        eid = uuid4()
        ecs.add(
            entity_id=eid,
            payload="probe",
            embedding=[1.0, 2.0, 3.0],
            utility=0.7,
            protected_floor=0.1,
            state=EntityState.VOLATILE,
            now=100.0,
        )
        memory = next(ecs.iter_rows())
        # Spec columns → snake_case projections
        assert hasattr(memory, "entity_id")
        assert hasattr(memory, "semantic_vector")
        assert hasattr(memory, "payload")
        assert hasattr(memory, "utility")
        assert hasattr(memory, "attended_count")
        assert hasattr(memory, "protected_floor")
        assert hasattr(memory, "last_evaluated")
        assert hasattr(memory, "state")
        assert hasattr(memory, "usd_link")

    def test_hydrate_row_preserves_attended_count(self) -> None:
        ecs = ECS()
        eid = uuid4()
        memory = Memory(
            entity_id=eid,
            payload="restored",
            semantic_vector=[0.5, 0.5],
            utility=0.3,
            attended_count=7,
            protected_floor=0.0,
            last_evaluated=500.0,
            state=EntityState.VOLATILE,
            usd_link=None,
        )
        ecs.hydrate_row(memory)
        rehydrated = ecs.get_memory(eid)
        assert rehydrated is not None
        assert rehydrated.attended_count == 7
        assert rehydrated.last_evaluated == 500.0
        assert rehydrated.utility == 0.3

    def test_hydrate_row_duplicate_raises(self) -> None:
        ecs = ECS()
        eid = uuid4()
        memory = Memory(
            entity_id=eid,
            payload="m",
            semantic_vector=[1.0],
            utility=1.0,
            attended_count=0,
            protected_floor=0.0,
            last_evaluated=0.0,
            state=EntityState.VOLATILE,
        )
        ecs.hydrate_row(memory)
        with pytest.raises(ValueError):
            ecs.hydrate_row(memory)

    def test_get_memory_missing_returns_none(self) -> None:
        ecs = ECS()
        assert ecs.get_memory(uuid4()) is None


# ---------------------------------------------------------------------
# apply_attention — aggregation semantics
# ---------------------------------------------------------------------


class TestApplyAttention:
    def _seed(self, ecs: ECS, count: int = 3) -> list:
        ids = []
        for i in range(count):
            eid = uuid4()
            ids.append(eid)
            ecs.add(
                entity_id=eid,
                payload=f"p{i}",
                embedding=[float(i), 1.0],
                utility=0.5,
                protected_floor=0.0,
                state=EntityState.VOLATILE,
                now=0.0,
            )
        return ids

    def test_apply_attention_sums_weights(self) -> None:
        ecs = ECS()
        ids = self._seed(ecs, 1)
        agg = {ids[0]: (0.3, 1)}  # sum_weight, signal_count
        updated = ecs.apply_attention(agg, now=10.0)
        assert updated == 1
        memory = ecs.get_memory(ids[0])
        assert memory is not None
        assert memory.utility == pytest.approx(0.8)
        assert memory.attended_count == 1

    def test_apply_attention_signal_count_not_one(self) -> None:
        """AttendedCount must increment by signal_count, not by 1.

        This is the spec fidelity point from ARCHITECTURE.md §5: a single
        reducer pass may carry many signals for the same entity and each
        one counts.
        """
        ecs = ECS()
        ids = self._seed(ecs, 1)
        agg = {ids[0]: (1.5, 5)}  # 5 signals batched together
        ecs.apply_attention(agg, now=10.0)
        memory = ecs.get_memory(ids[0])
        assert memory is not None
        assert memory.attended_count == 5

    def test_apply_attention_clamps_utility_at_one(self) -> None:
        ecs = ECS()
        ids = self._seed(ecs, 1)
        agg = {ids[0]: (10.0, 1)}  # massive weight → should cap at 1.0
        ecs.apply_attention(agg, now=10.0)
        memory = ecs.get_memory(ids[0])
        assert memory is not None
        assert memory.utility == 1.0

    def test_apply_attention_skips_missing(self) -> None:
        """§5.1 eventually consistent: missing entities silently skipped."""
        ecs = ECS()
        missing = uuid4()
        agg = {missing: (0.5, 1)}
        updated = ecs.apply_attention(agg, now=10.0)
        assert updated == 0


# ---------------------------------------------------------------------
# top_k_by_similarity and staging
# ---------------------------------------------------------------------


class TestRetrievalAndStaging:
    def test_top_k_orders_by_similarity(self) -> None:
        ecs = ECS()
        eid_near = uuid4()
        eid_far = uuid4()
        ecs.add(
            entity_id=eid_near,
            payload="near",
            embedding=[1.0, 0.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        ecs.add(
            entity_id=eid_far,
            payload="far",
            embedding=[0.0, 1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        results = ecs.top_k_by_similarity([1.0, 0.0], k=2)
        assert results[0].entity_id == eid_near
        assert results[1].entity_id == eid_far

    def test_top_k_utility_weighted(self) -> None:
        """Low-utility entities are demoted even with perfect similarity."""
        ecs = ECS()
        eid_decayed = uuid4()
        eid_fresh = uuid4()
        ecs.add(
            entity_id=eid_decayed,
            payload="decayed",
            embedding=[1.0, 0.0],
            utility=0.1,  # low utility
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        ecs.add(
            entity_id=eid_fresh,
            payload="fresh",
            embedding=[0.9, 0.1],  # slightly lower sim
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        results = ecs.top_k_by_similarity([1.0, 0.0], k=2)
        assert results[0].entity_id == eid_fresh

    def test_top_k_empty_ecs(self) -> None:
        ecs = ECS()
        assert ecs.top_k_by_similarity([1.0], k=5) == []

    def test_top_k_zero_query(self) -> None:
        ecs = ECS()
        ecs.add(
            entity_id=uuid4(),
            payload="x",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        assert ecs.top_k_by_similarity([0.0], k=5) == []

    def test_staged_entities_returns_only_staged(self) -> None:
        ecs = ECS()
        eid_volatile = uuid4()
        eid_staged = uuid4()
        ecs.add(
            entity_id=eid_volatile,
            payload="v",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        ecs.add(
            entity_id=eid_staged,
            payload="s",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.STAGED_FOR_SYNC,
            now=0.0,
        )
        staged = ecs.staged_entities()
        assert len(staged) == 1
        assert staged[0].entity_id == eid_staged
