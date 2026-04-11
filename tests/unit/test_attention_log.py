"""Unit tests for `moneta.attention_log`.

Covers ARCHITECTURE.md §5.1: append-reduce-clear cycle, aggregation,
and the lock-free discipline.

Lock-freedom note
-----------------
"Lock-free" in the spec means the module must not use `threading.Lock`
or `threading.RLock` in its write path. We verify this structurally via
an AST scan — the correctness proof under CPython GIL is an invariant,
not a test. If the assumption breaks (e.g. under PEP 703 free-threaded
Python), it is a §9 Trigger 2, not a local fix.
"""
from __future__ import annotations

import ast
from uuid import uuid4

import pytest

from moneta.attention_log import (
    AttentionEntry,
    AttentionLog,
    aggregate,
    reduce_attention_log,
)
from moneta.decay import DecayConfig
from moneta.ecs import ECS
from moneta.types import EntityState


# ---------------------------------------------------------------------
# AttentionLog — append / drain / clear
# ---------------------------------------------------------------------


class TestAttentionLogCycle:
    def test_empty_drain_returns_empty_list(self) -> None:
        log = AttentionLog()
        assert log.drain() == []
        assert len(log) == 0

    def test_append_then_drain(self) -> None:
        log = AttentionLog()
        eid = uuid4()
        log.append(eid, 0.2, 100.0)
        log.append(eid, 0.3, 101.0)
        assert len(log) == 2
        drained = log.drain()
        assert len(drained) == 2
        assert all(isinstance(e, AttentionEntry) for e in drained)
        # After drain, buffer is empty
        assert len(log) == 0

    def test_drain_is_atomic_swap(self) -> None:
        """After drain, new appends land in a fresh buffer."""
        log = AttentionLog()
        eid = uuid4()
        log.append(eid, 0.1, 0.0)
        drained = log.drain()
        log.append(eid, 0.2, 1.0)
        # drained[0] is the first append; new buffer has only the second
        assert len(drained) == 1
        assert drained[0].weight == 0.1
        drained2 = log.drain()
        assert len(drained2) == 1
        assert drained2[0].weight == 0.2


# ---------------------------------------------------------------------
# aggregate — signal count semantics
# ---------------------------------------------------------------------


class TestAggregate:
    def test_empty_aggregate(self) -> None:
        assert aggregate([]) == {}

    def test_single_entry(self) -> None:
        eid = uuid4()
        agg = aggregate([AttentionEntry(eid, 0.5, 0.0)])
        assert agg == {eid: (0.5, 1)}

    def test_multiple_entries_same_entity_sum_and_count(self) -> None:
        eid = uuid4()
        entries = [
            AttentionEntry(eid, 0.2, 0.0),
            AttentionEntry(eid, 0.3, 1.0),
            AttentionEntry(eid, 0.1, 2.0),
        ]
        agg = aggregate(entries)
        assert agg[eid][0] == 0.6  # sum of weights
        assert agg[eid][1] == 3  # count of signals (not 1!)

    def test_multiple_entities_separate(self) -> None:
        a = uuid4()
        b = uuid4()
        entries = [
            AttentionEntry(a, 0.5, 0.0),
            AttentionEntry(b, 0.2, 0.0),
            AttentionEntry(a, 0.1, 1.0),
        ]
        agg = aggregate(entries)
        assert agg[a] == (0.6, 2)
        assert agg[b] == (0.2, 1)


# ---------------------------------------------------------------------
# reduce_attention_log — end-to-end
# ---------------------------------------------------------------------


class TestReduceAttentionLog:
    def _setup(self) -> tuple[ECS, AttentionLog, DecayConfig]:
        ecs = ECS()
        log = AttentionLog()
        decay = DecayConfig()
        return ecs, log, decay

    def test_reduce_empty_log_returns_zero(self) -> None:
        ecs, log, decay = self._setup()
        updated = reduce_attention_log(log, ecs, decay, now=100.0)
        assert updated == 0

    def test_reduce_updates_ecs_utility_and_attended(self) -> None:
        ecs, log, decay = self._setup()
        eid = uuid4()
        ecs.add(
            entity_id=eid,
            payload="x",
            embedding=[1.0],
            utility=0.5,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=100.0,
        )
        log.append(eid, 0.3, 100.0)
        log.append(eid, 0.1, 100.0)
        updated = reduce_attention_log(log, ecs, decay, now=100.0)
        assert updated == 1
        memory = ecs.get_memory(eid)
        assert memory is not None
        assert memory.utility == pytest.approx(0.9)  # 0.5 + 0.3 + 0.1
        assert memory.attended_count == 2

    def test_reduce_runs_decay_eval_point_2(self) -> None:
        """After reduce, untouched entities should have decayed."""
        ecs, log, _ = self._setup()
        # Use a fast 1-minute half-life
        decay = DecayConfig(half_life_seconds=60.0)
        eid_untouched = uuid4()
        ecs.add(
            entity_id=eid_untouched,
            payload="untouched",
            embedding=[1.0],
            utility=1.0,
            protected_floor=0.0,
            state=EntityState.VOLATILE,
            now=0.0,
        )
        # reduce at t = 60 (one half-life later)
        reduce_attention_log(log, ecs, decay, now=60.0)
        memory = ecs.get_memory(eid_untouched)
        assert memory is not None
        assert memory.utility == pytest.approx(0.5, rel=1e-9)


# ---------------------------------------------------------------------
# Lock-free structural assertion
# ---------------------------------------------------------------------


class TestLockFreeDiscipline:
    def test_no_threading_lock_imports_in_attention_log(self) -> None:
        """The concurrency primitive is an append-only log (ARCHITECTURE §5.1).

        The module must not import `threading.Lock` or `threading.RLock`.
        This is a structural invariant — if it breaks, it is a §9 Trigger 2
        (spec-level surprise), not a local fix.
        """
        import moneta.attention_log as mod

        source = open(mod.__file__, "r", encoding="utf-8").read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "threading":
                imported = {alias.name for alias in node.names}
                assert "Lock" not in imported, (
                    "attention_log must not import threading.Lock (§5.1 lock-free)"
                )
                assert "RLock" not in imported, (
                    "attention_log must not import threading.RLock (§5.1 lock-free)"
                )


