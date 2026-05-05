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

    def author_stage_batch(self, entities: list[Memory]) -> AuthoringResult:
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


# ---------------------------------------------------------------------
# Per-batch ECS state transition (no rollback after partial commit)
# ---------------------------------------------------------------------


class TestPerBatchStateTransition:
    """Regression for review finding
    ``consolidation-L2-stage-partial-batch-atomicity-break``.

    Prior bug: ``ConsolidationRunner.run_pass`` committed batches in one
    loop and then transitioned ECS state to CONSOLIDATED in a separate
    post-batch loop. A mid-loop ``commit_staging`` failure left the
    successfully-committed earlier batches stuck in STAGED_FOR_SYNC
    permanently — ``classify()`` only re-considers VOLATILE entities, so
    those entities could never be retried, and the §7 atomicity protocol's
    recoverability invariant ("the durable artifact and the ECS bookkeeping
    converge") was broken.

    Fix: hoist the CONSOLIDATED transition INSIDE the batch loop so a
    later-batch failure leaves the earlier-batch entities at CONSOLIDATED
    (matching disk + vector reality) and only the failing batch + its
    successors at STAGED_FOR_SYNC (correctly recoverable on the next pass
    once the underlying failure clears).
    """

    def test_partial_batch_failure_preserves_committed_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Batch 1 commits successfully, batch 2 raises — assert state."""
        from moneta import consolidation as consolidation_module
        from moneta.attention_log import AttentionLog
        from moneta.consolidation import ConsolidationRunner
        from moneta.decay import DecayConfig
        from moneta.ecs import ECS
        from moneta.types import EntityState
        from moneta.vector_index import VectorIndex

        # Shrink batch cap so 5 staged memories span 3 batches: [2, 2, 1].
        monkeypatch.setattr(consolidation_module, "MAX_BATCH_SIZE", 2)

        # Build five entities ALREADY in STAGED_FOR_SYNC-eligible shape:
        # utility 0.0 < 0.3, attended_count >= 3 → classify() will stage them.
        ecs = ECS()
        memories: list[Memory] = []
        now = time.time()
        for i in range(5):
            eid = uuid4()
            ecs.add(
                entity_id=eid,
                payload=f"m{i}",
                embedding=[float(i), 1.0],
                utility=0.0,
                protected_floor=0.0,
                state=EntityState.VOLATILE,
                now=now,
            )
            # Bump attended count past the §6 staging threshold.
            ecs.apply_attention({eid: (0.0, 5)}, now=now)
            mem = ecs.get_memory(eid)
            assert mem is not None
            memories.append(mem)

        captured_first_batch: list[UUID] = []
        captured_second_batch: list[UUID] = []
        call_log: list[str] = []

        class _FlakyTarget:
            """Succeeds on the first commit_staging, raises on the second."""

            def author_stage_batch(self, entries):
                if not call_log:
                    captured_first_batch.extend(e.entity_id for e in entries)
                    call_log.append("ok")
                    return AuthoringResult(
                        target="flaky",
                        batch_id="b1",
                        authored_at=time.time(),
                        entity_ids=[e.entity_id for e in entries],
                    )
                else:
                    captured_second_batch.extend(e.entity_id for e in entries)
                    call_log.append("raise")
                    raise RuntimeError("simulated disk full on batch 2")

            def flush(self) -> None:
                pass

        class _Vec:
            def upsert(self, *a, **kw) -> None: pass
            def update_state(self, *a, **kw) -> None: pass
            def delete(self, *a, **kw) -> None: pass

        writer = SequentialWriter(_FlakyTarget(), _Vec())
        runner = ConsolidationRunner(max_entities=100)

        with pytest.raises(RuntimeError, match="simulated disk full on batch 2"):
            runner.run_pass(
                ecs=ecs,
                decay=DecayConfig(),
                attention_log=AttentionLog(),
                vector_index=VectorIndex(),
                sequential_writer=writer,
                now=now,
            )

        # First batch's entities reached CONSOLIDATED (durable on the
        # flaky target, vector committed, ECS state advanced).
        for eid in captured_first_batch:
            mem = ecs.get_memory(eid)
            assert mem is not None
            assert mem.state == EntityState.CONSOLIDATED, (
                "successfully-committed batch entities must be CONSOLIDATED "
                "in ECS after a later batch raises"
            )

        # Second batch's entities (the ones that raised) remain in
        # STAGED_FOR_SYNC, recoverable on a subsequent pass once the
        # underlying failure clears.
        assert len(captured_second_batch) > 0
        for eid in captured_second_batch:
            mem = ecs.get_memory(eid)
            assert mem is not None
            assert mem.state == EntityState.STAGED_FOR_SYNC, (
                "failed-batch entities must remain STAGED_FOR_SYNC, not "
                "be silently advanced to CONSOLIDATED"
            )

    def test_full_success_advances_all_to_consolidated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sanity: when no batch fails, every staged entity reaches CONSOLIDATED."""
        from moneta import consolidation as consolidation_module
        from moneta.attention_log import AttentionLog
        from moneta.consolidation import ConsolidationRunner
        from moneta.decay import DecayConfig
        from moneta.ecs import ECS
        from moneta.types import EntityState
        from moneta.vector_index import VectorIndex

        monkeypatch.setattr(consolidation_module, "MAX_BATCH_SIZE", 2)

        ecs = ECS()
        ids: list[UUID] = []
        now = time.time()
        for i in range(5):
            eid = uuid4()
            ecs.add(
                entity_id=eid,
                payload=f"m{i}",
                embedding=[float(i), 1.0],
                utility=0.0,
                protected_floor=0.0,
                state=EntityState.VOLATILE,
                now=now,
            )
            ecs.apply_attention({eid: (0.0, 5)}, now=now)
            ids.append(eid)

        target = MockUsdTarget(log_path=None)

        class _Vec:
            def upsert(self, *a, **kw) -> None: pass
            def update_state(self, *a, **kw) -> None: pass
            def delete(self, *a, **kw) -> None: pass

        writer = SequentialWriter(target, _Vec())
        runner = ConsolidationRunner(max_entities=100)

        runner.run_pass(
            ecs=ecs,
            decay=DecayConfig(),
            attention_log=AttentionLog(),
            vector_index=VectorIndex(),
            sequential_writer=writer,
            now=now,
        )

        for eid in ids:
            mem = ecs.get_memory(eid)
            assert mem is not None
            assert mem.state == EntityState.CONSOLIDATED
