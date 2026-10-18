"""Append-only attention log with swap-and-drain reducer.

ARCHITECTURE.md §5.1. The concurrency primitive for Moneta is a lock-free,
eventually-consistent attention log. Writes append; the sleep-pass reducer
drains the current buffer in a single atomic swap and applies the
aggregated result to the ECS.

Lock-free under CPython GIL
---------------------------

`list.append` is atomic at the bytecode level under the CPython GIL. The
drain uses a single tuple assignment::

    old, self._buffer = self._buffer, []

which rebinds `self._buffer` to a fresh list in one `STORE_ATTR`.

An append can still land in a list that was already swapped out (path L,
``docs/design/R1-attention-durability.md`` §0 root cause 6). ``append``
loads ``self._buffer`` (capturing the current list) before it calls
``list.append``, and CPython can switch threads between the two. If the
reducer's swap runs in that gap, the entry lands in the old list after the
swap. The rc1 text here said "Entries cannot be lost"; that was false.

What the log guarantees instead (R1′, design §2.3):

- The reducer takes ONE snapshot (``tuple(old)``) of each swapped-out list
  and uses that same tuple for the aggregate and for the record of applied
  WAL sequence numbers (``applied_seqs``). A seq is recorded only together
  with its own entry; an entry that lands after the snapshot is in neither.
- Entries that land in a swapped-out list after its snapshot are carried to
  the next pass (``_carry``), which applies them and records their seqs.
- An entry whose appender stalls past the next pass as well is applied by no
  pass in this process. Its seq is never recorded, so under durability its
  WAL line survives every save and it is applied exactly once at the next
  reopen. Without durability there is no WAL, and it is lost, as in rc1.

So the log stays eventually consistent (ARCHITECTURE.md §5.1), but for a
worst-case straggler "eventually" can now mean "at the next reopen".

Seqs are recorded BEFORE ``apply_attention`` runs (gate 3 ruling: a stated
loss over a silent double). If ``apply_attention`` raises, the drained seqs
stay recorded while their effects may be missing from the rows, so the next
save drops their WAL lines. That loss is logged at ERROR as
"torn attention apply"; it is never a double apply.

This analysis holds for CPython with the GIL enabled. It does not hold
under free-threaded Python (PEP 703) or sub-interpreters with
per-interpreter GILs. Phase 1 targets CPython GIL; escalate per MONETA.md
§9 Trigger 2 if that assumption changes.

The `AttentionLog.__init__` constructor enforces the GIL invariant at
runtime via `sys._is_gil_enabled()` — converting a silent correctness
failure under free-threaded Python into a loud escalation.

Single-reducer rule
-------------------

Only one reducer may drain the log at a time. Concurrent reducers are not
supported: their row updates can interleave. The reducer takes no lock. It
registers a token in ``_inflight`` and stores a fresh object in
``_apply_epoch`` at its start and at its end; a save reads the rows and
``applied_seqs`` only when no token is present and the epoch has not moved
(``DurabilityManager.snapshot_ecs``, design §2.4 step 1). A reducer that sees
another reducer's token, or an epoch it did not write, logs ERROR and
carries on. Detection is diagnostic only and never raises.
Consolidation Engineer's sleep-pass trigger is the only production caller
of the reducer.
"""
from __future__ import annotations

import logging
import sys
from typing import NamedTuple, Optional
from uuid import UUID

# Forward imports resolved at call time to keep the module import-light.
# `reduce_attention_log` takes concrete types from .ecs and .decay.

_logger = logging.getLogger(__name__)


class AttentionEntry(NamedTuple):
    """A single `signal_attention` mention for one entity."""

    entity_id: UUID
    weight: float
    timestamp: float  # wall-clock unix seconds at signal time


class AttentionLog:
    """Append-only log with single-reducer drain.

    No locks. No CAS. See the module docstring for the CPython-GIL argument
    and its path L amendment. The constructor enforces the GIL invariant at
    runtime.

    Each buffered item is ``(AttentionEntry, seq)``, where ``seq`` is the
    entry's WAL sequence number, or ``None`` without durability.
    """

    def __init__(self) -> None:
        if hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled():
            raise RuntimeError(
                "AttentionLog lock-free drain requires CPython GIL; "
                "free-threaded Python is not supported (MONETA.md §9 Trigger 2)"
            )
        self._buffer: list[tuple[AttentionEntry, Optional[int]]] = []
        # WAL seqs whose effects the reducer put into the ECS rows and that
        # no save has released yet (DurabilityManager.snapshot_ecs step 4).
        # Mutated in place only; never rebound.
        self.applied_seqs: set[int] = set()
        # One token per running reducer; empty means idle (design §1.3).
        self._inflight: set[object] = set()
        # A fresh object at every reducer start and end (design §2.3).
        self._apply_epoch: object = object()
        # (the list the last reducer swapped out, how many items it took).
        # One attribute, so it is stored and read in one step.
        self._carry: Optional[
            tuple[list[tuple[AttentionEntry, Optional[int]]], int]
        ] = None
        # Late entries taken from a previous swap (path L), for tests and logs.
        self.stragglers_carried: int = 0

    def append(
        self,
        entity_id: UUID,
        weight: float,
        timestamp: float,
        seq: Optional[int] = None,
    ) -> None:
        """Record one attention signal. Non-blocking, lock-free.

        The item is built before ``self._buffer`` is loaded, which narrows
        (but does not close) the path L window; nothing relies on it.
        """
        item = (AttentionEntry(entity_id, weight, timestamp), seq)
        self._buffer.append(item)

    def drain(self) -> list[AttentionEntry]:
        """Swap out the current buffer and return its entries.

        Subsequent appends land in a fresh buffer. The returned list is
        built from one snapshot of the swapped-out list; an append that
        lands in that list after the snapshot is not returned (path L, see
        the module docstring). Not used by the reducer, which calls
        ``_drain_with_seqs``; this method does not touch the carry-over.
        """
        old, self._buffer = self._buffer, []
        return [entry for entry, _ in tuple(old)]

    def _drain_with_seqs(
        self,
    ) -> tuple[tuple[AttentionEntry, Optional[int]], ...]:
        """Reducer only: swap, snapshot, and take the previous swap's stragglers.

        Returns one immutable tuple: the late entries of the PREVIOUS swap
        (those that landed after its snapshot), then one snapshot of this
        swap. The reducer uses that tuple for both the aggregate and the
        seq record, so recorded == applied (design §2.3).
        """
        carry = self._carry
        old, self._buffer = self._buffer, []
        late = tuple(carry[0][carry[1]:]) if carry is not None else ()
        items = tuple(old)
        self._carry = (old, len(items))
        if late:
            self.stragglers_carried += len(late)
            _logger.warning(
                "attention log: %d late entr%s carried over from the previous "
                "swap (path L); applied this pass",
                len(late),
                "y" if len(late) == 1 else "ies",
            )
        return late + items

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

    Lock-free (ARCHITECTURE.md §340): the reducer adds and discards its
    token in ``log._inflight`` and stores fresh objects in
    ``log._apply_epoch``; it never blocks or waits. The drain, the seq
    record and the apply all happen while the token is registered, so a
    save never pairs rows and ``applied_seqs`` from the middle of a pass.
    Seqs are recorded before ``apply_attention`` (gate 3 ruling); if the
    apply raises, an ERROR "torn attention apply" names how many recorded
    seqs may lack their effects, and the exception propagates unchanged.
    Concurrent-reducer detection logs ERROR and never raises.

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
    if log._inflight:  # best-effort, diagnostic only: log, never raise
        _logger.error(
            "concurrent attention reducer at entry (%d in flight)",
            len(log._inflight),
        )
    tok = object()
    clash = False
    updated = 0
    try:
        log._inflight.add(tok)  # inside the try: nothing stranded before it
        mine = object()
        log._apply_epoch = mine  # a value no other reducer can write
        items = log._drain_with_seqs()  # ONE tuple: stragglers + this swap
        agg = aggregate([entry for entry, _ in items])
        seqs = [seq for _, seq in items if seq is not None]
        log.applied_seqs.update(seqs)  # recorded BEFORE the apply (gate 3)
        try:
            updated = ecs.apply_attention(agg, now)
        except BaseException:
            _logger.error(
                "torn attention apply: apply_attention raised after %d drained "
                "WAL seq(s) were recorded as applied; their effects may be "
                "missing from the rows, and the next save drops their WAL "
                "lines (a stated loss, never a double apply)",
                len(seqs),
            )
            raise
        clash = log._apply_epoch is not mine or len(log._inflight) > 1
    finally:
        try:
            log._inflight.discard(tok)  # idempotent; cannot raise
        finally:
            log._inflight.discard(tok)  # again: stranding needs two faults
        log._apply_epoch = object()  # end-of-apply epoch
    # Evaluation point 2 per ARCHITECTURE.md §4.
    ecs.decay_all(decay.lambda_, now)
    if clash:
        _logger.error("concurrent attention reducer detected")  # never raise
    return updated
