"""Sequential writer ordering tests — ARCHITECTURE.md §7 atomicity.

Verifies:
  1. Authoring target is called before vector index (USD first, vector second)
  2. Vector-index failure does NOT roll back the authoring target
     (orphans are benign per §7)
  3. Multi-entity batches preserve entry ordering end-to-end
  4. `flush()` happens between authoring and vector update
"""
from __future__ import annotations

import time
from typing import List
from uuid import UUID, uuid4

import pytest

from moneta.mock_usd_target import MockUsdTarget
from moneta.sequential_writer import AuthoringResult, SequentialWriter
from moneta.types import EntityState, Memory


# ---------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------


class _Timeline:
    """Shared event log for ordering assertions."""

    def __init__(self) -> None:
        self.events: list[str] = []


class _TimelineMockTarget(MockUsdTarget):
    """MockUsdTarget that also logs call boundaries to a Timeline."""

    def __init__(self, timeline: _Timeline) -> None:
        super().__init__(log_path=None)
        self._timeline = timeline

    def author_stage_batch(self, entities: List[Memory]) -> AuthoringResult:
        self._timeline.events.append("author_start")
        result = super().author_stage_batch(entities)
        self._timeline.events.append("author_end")
        return result

    def flush(self) -> None:
        self._timeline.events.append("flush")
        super().flush()


class _TimelineVector:
    """Vector target that logs call boundaries (satisfies the Protocol)."""

    def __init__(self, timeline: _Timeline) -> None:
        self._timeline = timeline

    def upsert(self, entity_id: UUID, vector, state: EntityState) -> None:
        self._timeline.events.append("upsert")

    def update_state(self, entity_id: UUID, state: EntityState) -> None:
        self._timeline.events.append("update_state")

    def delete(self, entity_id: UUID) -> None:
        self._timeline.events.append("delete")


class _FailingVector:
    """Vector target whose update_state always raises."""

    def upsert(self, *args, **kwargs) -> None:
        pass

    def update_state(self, *args, **kwargs) -> None:
        raise RuntimeError("simulated vector-index failure")

    def delete(self, *args, **kwargs) -> None:
        pass


def _make_memory(protected_floor: float = 0.0) -> Memory:
    return Memory(
        entity_id=uuid4(),
        payload="test",
        semantic_vector=[1.0, 0.0],
        utility=0.2,
        attended_count=3,
        protected_floor=protected_floor,
        last_evaluated=time.time(),
        state=EntityState.STAGED_FOR_SYNC,
    )


# ---------------------------------------------------------------------
# Ordering invariant
# ---------------------------------------------------------------------


class TestOrdering:
    def test_author_happens_before_vector_update(self) -> None:
        """§7: 1. USD authored. 2. Save returns. 3. Vector committed second."""
        timeline = _Timeline()
        target = _TimelineMockTarget(timeline)
        vec = _TimelineVector(timeline)
        writer = SequentialWriter(target, vec)

        writer.commit_staging([_make_memory()])

        assert timeline.events == [
            "author_start",
            "author_end",
            "flush",
            "update_state",
        ]

    def test_ordering_preserved_across_multi_entity_batch(self) -> None:
        timeline = _Timeline()
        target = _TimelineMockTarget(timeline)
        vec = _TimelineVector(timeline)
        writer = SequentialWriter(target, vec)

        memories = [_make_memory() for _ in range(5)]
        writer.commit_staging(memories)

        # author_start/end/flush happen exactly once for the batch
        assert timeline.events.count("author_start") == 1
        assert timeline.events.count("author_end") == 1
        assert timeline.events.count("flush") == 1
        # update_state happens once per memory
        assert timeline.events.count("update_state") == 5

        # And authoring still precedes ALL vector updates
        last_author_idx = max(
            i for i, e in enumerate(timeline.events) if e == "flush"
        )
        first_vector_idx = min(
            i for i, e in enumerate(timeline.events) if e == "update_state"
        )
        assert last_author_idx < first_vector_idx


# ---------------------------------------------------------------------
# Vector-index failure leaves authoring intact
# ---------------------------------------------------------------------


class TestVectorFailure:
    def test_vector_failure_does_not_rollback_authoring(self) -> None:
        """§7: 'USD orphans from interrupted writes are benign.'

        The sequential writer must NOT attempt to undo the authoring
        write when the vector index fails. The orphan is the protocol.
        """
        target = MockUsdTarget(log_path=None)
        vec = _FailingVector()
        writer = SequentialWriter(target, vec)

        mem = _make_memory()

        with pytest.raises(RuntimeError, match="simulated"):
            writer.commit_staging([mem])

        # Authoring side still has the record — this is §7's "benign orphan"
        buffer = target.get_ephemeral_buffer()
        assert len(buffer) == 1
        assert buffer[0]["entries"][0]["entity_id"] == str(mem.entity_id)


# ---------------------------------------------------------------------
# Multi-entity batch contents
# ---------------------------------------------------------------------


class TestBatchContents:
    def test_multi_entity_batch_authored_as_one_log_entry(self) -> None:
        target = MockUsdTarget(log_path=None)

        class _NoopVector:
            def upsert(self, *a, **kw) -> None: pass
            def update_state(self, *a, **kw) -> None: pass
            def delete(self, *a, **kw) -> None: pass

        writer = SequentialWriter(target, _NoopVector())

        memories = [_make_memory() for _ in range(5)]
        result = writer.commit_staging(memories)

        # One log entry per commit_staging call, containing all 5 entries
        buffer = target.get_ephemeral_buffer()
        assert len(buffer) == 1
        batch = buffer[0]
        assert len(batch["entries"]) == 5

        # AuthoringResult reflects the same
        assert len(result.entity_ids) == 5
        assert result.target == "mock"
        assert result.batch_id == batch["batch_id"]
        assert result.authored_at == batch["authored_at"]

    def test_entity_ids_preserved_in_order(self) -> None:
        target = MockUsdTarget(log_path=None)

        class _NoopVector:
            def upsert(self, *a, **kw) -> None: pass
            def update_state(self, *a, **kw) -> None: pass
            def delete(self, *a, **kw) -> None: pass

        writer = SequentialWriter(target, _NoopVector())

        memories = [_make_memory() for _ in range(3)]
        expected_ids = [m.entity_id for m in memories]
        result = writer.commit_staging(memories)

        assert result.entity_ids == expected_ids
        buffer_ids = [
            UUID(entry["entity_id"])
            for entry in target.get_ephemeral_buffer()[0]["entries"]
        ]
        assert buffer_ids == expected_ids
