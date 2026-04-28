"""Append-only attention log with swap-and-drain reducer.

ARCHITECTURE.md §5.1. The concurrency primitive for Moneta is a lock-free,
eventually-consistent attention log. Writes append; the sleep-pass reducer
drains the current buffer in a single atomic swap and applies the
aggregated result to the ECS.

Lock-free under CPython GIL
---------------------------

`list.append` is atomic at the bytecode level under the CPython GIL. The
drain uses a single tuple assignment::

    drained, self._buffer = self._buffer, []

which rebinds `self._buffer` to a fresh list in one `STORE_ATTR`. A
concurrent `append` either lands in the old list (and is drained this
window) or in the new list (and is drained next window). Entries cannot
be lost.

This analysis holds for CPython 3.11 / 3.12 with the GIL enabled. It does
not hold under free-threaded Python (PEP 703) or sub-interpreters with
per-interpreter GILs. Phase 1 targets CPython GIL; escalate per MONETA.md
§9 Trigger 2 if that assumption changes.

The `AttentionLog.__init__` constructor enforces the GIL invariant at
runtime via `sys._is_gil_enabled()` — converting a silent correctness
failure under free-threaded Python into a loud escalation.

Single-reducer rule
-------------------

Only one reducer may drain the log at a time. Multi-reducer drain is not
supported — two concurrent `drain()` calls would both swap, and one would
see an already-empty buffer. Consolidation Engineer's sleep-pass trigger
is the only caller of `drain()` in the production data path.
"""
from __future__ import annotations

import sys
from typing import NamedTuple
from uuid import UUID

# Forward imports resolved at call time to keep the module import-light.
# `reduce_attention_log` takes concrete types from .ecs and .decay.


class AttentionEntry(NamedTuple):
    """A single `signal_attention` mention for one entity."""

    entity_id: UUID
    weight: float
    timestamp: float  # wall-clock unix seconds at signal time


class AttentionLog:
    """Append-only log with single-reducer drain.

    No locks. No CAS. See module docstring for the CPython-GIL correctness
    argument. The constructor enforces the GIL invariant at runtime.
    """

    def __init__(self) -> None:
        if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled():
            raise RuntimeError(
                "AttentionLog lock-free drain requires CPython GIL; "
                "free-threaded Python is not supported (MONETA.md §9 Trigger 2)"
            )
        self._buffer: list[AttentionEntry] = []

    def append(self, entity_id: UUID, weight: float, timestamp: float) -> None:
        """Record one attention signal. Non-blocking, lock-free."""
        self._buffer.append(AttentionEntry(entity_id, weight, timestamp))

    def drain(self) -> list[AttentionEntry]:
        """Atomically swap out the current buffer and return its contents.

        Subsequent appends land in a fresh buffer. The caller owns the
        returned list and is expected to pass it to `aggregate` and then
        into the ECS reducer.
        """
        drained, self._buffer = self._buffer, []
        return drained

    def __len__(self) -> int:
        return len(self._buffer)


def aggregate(entries: list[AttentionEntry]) -> dict[UUID, tuple[float, int]]:
    """Sum weights and count signals per entity.

    Returns a mapping from `entity_id` to `(summed_weight, signal_count)`.
    Per ARCHITECTURE.md §5, `AttendedCount` increments by the *number of
    signals* (i.e. entries) targeting the entity, not by the number of
    distinct entities — see `ECS.apply_attention` for the semantics.
    """
    agg: dict[UUID, tuple[float, int]] = {}
    for entry in entries:
        prev = agg.get(entry.entity_id)
        if prev is None:
            agg[entry.entity_id] = (entry.weight, 1)
        else:
            w_sum, count = prev
            agg[entry.entity_id] = (w_sum + entry.weight, count + 1)
    return agg


def reduce_attention_log(log: "AttentionLog", ecs, decay, now: float) -> int:
    """Drain the attention log into the ECS and run decay eval point 2.

    Sleep-pass reducer. Called by Consolidation Engineer's sleep-pass
    trigger (Phase 1 Role 4). Implements ARCHITECTURE.md §5 write semantics
    followed by §4 evaluation point 2 (decay immediately after the
    attention-write phase).

    Args:
        log: the attention log to drain.
        ecs: the ECS instance to update (typed loosely to avoid a circular
            import; see type checker note).
        decay: a DecayConfig instance whose `.lambda_` drives the decay pass.
        now: wall-clock timestamp at reduce time.

    Returns:
        The number of entities actually updated by the attention pass
        (drained entries may reference pruned entities, which are skipped).
    """
    entries = log.drain()
    agg = aggregate(entries)
    updated = ecs.apply_attention(agg, now)
    # Evaluation point 2 per ARCHITECTURE.md §4.
    ecs.decay_all(decay.lambda_, now)
    return updated
