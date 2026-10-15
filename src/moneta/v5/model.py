"""Records, events, and the fold that derives state from the journal.

The fold is the whole semantic core of v5. Every piece of record state is
a deterministic function of the journal prefix and the configured
half-life, so replaying the same journal with the same half-life always
reproduces the same state, bit for bit. (Changing the half-life
reinterprets history on purpose; the journal notes when that happens.)

Utility semantics (the fix for v1's decay skip)
-----------------------------------------------
v1 applied attention at the sleep pass as ``U = U_stored + w`` and then
set ``LastEvaluated = now``. That erased every second of decay between
the last evaluation and the pass (ARCHITECTURE.md §4/§5 as locked
actually mandates this order). v5 applies each attention event *at its
own timestamp*::

    U = decay(U_anchor, t_anchor -> t_signal)   # locked decay math, unchanged
    U = min(1.0, U + w)
    (U_anchor, t_anchor) = (U, t_signal)

and utility at any evaluation time is ``decay(U_anchor, t_anchor -> t)``.
Reading never writes. The locked formula ``U = max(floor, U·e^-λΔt)`` is
reused verbatim from :func:`moneta.decay.decay_value`.
"""

from __future__ import annotations

import base64
import math
import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from ..decay import decay_value
from ..types import EntityState, Memory


class Status(StrEnum):
    """Record lifecycle. Residency, eligibility and deletion are separate axes.

    LIVE / STAGED / CONSOLIDATED are *retained* and recallable.
    TOMBSTONED is retained in the journal but never recalled.
    ERASED has had payload and vector removed from all derived state; the
    bytes leave the journal at the next :meth:`compact`.
    Exclusion by context is not a status at all: it is a per-query verdict.
    """

    LIVE = "live"
    STAGED = "staged"
    CONSOLIDATED = "consolidated"
    TOMBSTONED = "tombstoned"
    ERASED = "erased"


RECALLABLE = frozenset({Status.LIVE, Status.STAGED, Status.CONSOLIDATED})

_V1_STATE = {
    Status.LIVE: EntityState.VOLATILE,
    Status.STAGED: EntityState.STAGED_FOR_SYNC,
    Status.CONSOLIDATED: EntityState.CONSOLIDATED,
}


# ----------------------------------------------------------------------
# Vector codec: exact float64 round trip, ~45% of the JSON-list size
# ----------------------------------------------------------------------


def encode_vector(vec: Iterable[float]) -> str:
    values = list(vec)
    return base64.b64encode(struct.pack(f"<{len(values)}d", *values)).decode("ascii")


def decode_vector(text: str) -> tuple[float, ...]:
    raw = base64.b64decode(text.encode("ascii"))
    return struct.unpack(f"<{len(raw) // 8}d", raw)


def validate_vector(vec: Any, dim: int | None, *, allow_zero: bool = False) -> tuple[float, ...]:
    """Return a tuple of finite floats or raise ValueError. Never partial.

    ``allow_zero`` admits a zero-norm vector. Deposits allow it: the memory
    is stored and enumerable but has no direction, so it is never ranked
    by similarity and :meth:`Substrate.explain` says so (verdict
    ``unrankable``). Queries never allow it.
    """
    if isinstance(vec, (str, bytes)) or not hasattr(vec, "__iter__"):
        raise ValueError("embedding must be a sequence of floats")
    try:
        values = tuple(float(x) for x in vec)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"embedding contains a non-numeric value: {exc}") from None
    if not values:
        raise ValueError("embedding is empty")
    if not all(math.isfinite(x) for x in values):
        raise ValueError("embedding contains NaN or infinity")
    if dim is not None and len(values) != dim:
        raise DimensionMismatchError(dim, len(values))
    if not allow_zero and sum(x * x for x in values) == 0.0:
        raise ValueError("embedding has zero norm")
    return values


class DimensionMismatchError(ValueError):
    """An embedding's length does not match the store's locked dimension."""

    def __init__(self, expected: int, got: int) -> None:
        self.expected = expected
        self.got = got
        super().__init__(f"embedding dim mismatch: store is {expected}, got {got}")


# ----------------------------------------------------------------------
# Record
# ----------------------------------------------------------------------


@dataclass(slots=True)
class Record:
    """Folded state of one memory. Mutated only by :class:`Fold` under the writer lock."""

    entity_id: UUID
    seq: int
    deposited_at: float
    payload: str
    vector: tuple[float, ...] | None
    unit: tuple[float, ...] | None
    protected_floor: float
    scope: str
    slot: str | None
    key: str | None
    anchor_u: float
    anchor_t: float
    attended: int
    status: Status
    status_reason: str | None = None
    status_t: float | None = None
    status_seq: int | None = None

    def utility_at(self, lam: float, t: float) -> float:
        return decay_value(self.anchor_u, self.anchor_t, self.protected_floor, lam, t)

    def to_memory(self, lam: float, t: float) -> Memory:
        """v1-shaped projection. ``last_evaluated`` is the evaluation time."""
        return Memory(
            entity_id=self.entity_id,
            payload=self.payload,
            semantic_vector=list(self.vector or ()),
            utility=self.utility_at(lam, t),
            attended_count=self.attended,
            protected_floor=self.protected_floor,
            last_evaluated=t,
            state=_V1_STATE.get(self.status, EntityState.VOLATILE),
            usd_link=None,
        )


def _unit(vec: tuple[float, ...]) -> tuple[float, ...] | None:
    """Unit vector, or None when the vector has no direction (zero or non-finite)."""
    if not all(math.isfinite(x) for x in vec):
        return None
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return None
    return tuple(x / norm for x in vec)


# ----------------------------------------------------------------------
# Fold
# ----------------------------------------------------------------------


class Fold:
    """Deterministic state machine over journal events.

    ``apply`` is the only mutator. The substrate calls it after the event
    has been durably appended, under its writer lock.
    """

    def __init__(self, lam: float) -> None:
        self.lam = lam
        self.records: dict[UUID, Record] = {}
        self.by_key: dict[str, UUID] = {}
        self.dim: int | None = None
        self.half_life_seconds: float | None = None
        self.last_seq = 0
        self.attended_since_pass: set = set()

    # -- replay --------------------------------------------------------

    def replay(self, events: Iterator[dict[str, Any]]) -> int:
        n = 0
        for event in events:
            self.apply(event)
            n += 1
        return n

    def apply(self, event: dict[str, Any]) -> None:
        op = event["op"]
        handler = getattr(self, "_op_" + op, None)
        if handler is None:
            raise ValueError(f"unknown journal op {op!r} at seq {event.get('seq')}")
        handler(event)
        self.last_seq = event["seq"]

    # -- handlers ------------------------------------------------------

    def _op_genesis(self, e: dict[str, Any]) -> None:
        if e.get("dim") is not None:
            self.dim = int(e["dim"])
        if e.get("half_life_seconds") is not None:
            self.half_life_seconds = float(e["half_life_seconds"])

    def _new_record(
        self, e: dict[str, Any], anchor_u: float, anchor_t: float, attended: int, status: Status
    ) -> Record:
        eid = UUID(e["id"])
        vec = decode_vector(e["emb"]) if e.get("emb") is not None else None
        if self.dim is None:
            if vec is not None:
                self.dim = len(vec)
            elif e.get("dim") is not None:  # a compacted (erased) deposit keeps its dim
                self.dim = int(e["dim"])
        rec = Record(
            entity_id=eid,
            seq=e["seq"],
            deposited_at=float(e["t"]),
            payload=e.get("payload", ""),
            vector=vec,
            unit=_unit(vec) if vec is not None else None,
            protected_floor=float(e.get("floor", 0.0)),
            scope=e.get("scope", ""),
            slot=e.get("slot"),
            key=e.get("key"),
            anchor_u=anchor_u,
            anchor_t=anchor_t,
            attended=attended,
            status=status,
        )
        if e.get("erased"):
            rec.status = Status.ERASED
            rec.payload = ""
            rec.vector = rec.unit = None
        self.records[eid] = rec
        if rec.key is not None:
            self.by_key[rec.key] = eid
        return rec

    def _op_deposit(self, e: dict[str, Any]) -> None:
        self._new_record(e, 1.0, float(e["t"]), 0, Status.LIVE)

    def _op_import(self, e: dict[str, Any]) -> None:
        """A v1 row migrated with its anchor state intact."""
        status = Status(e.get("status", "live"))
        rec = self._new_record(
            e, float(e["u"]), float(e["anchor_t"]), int(e.get("attended", 0)), status
        )
        if (
            rec.status in RECALLABLE
            and rec.vector is not None
            and not all(math.isfinite(x) for x in rec.vector)
        ):
            rec.status = Status.TOMBSTONED  # a v1 row whose vector holds NaN/inf
            rec.status_reason = "v1_import_invalid_vector"
        elif e.get("reason"):
            rec.status_reason = e["reason"]
        if rec.status_reason is not None:
            rec.status_t = float(e["t"])
            rec.status_seq = e["seq"]

    def _op_attend(self, e: dict[str, Any]) -> None:
        t = float(e["t"])
        for key, w in sorted(e["w"].items()):  # deterministic regardless of dict order
            rec = self.records.get(UUID(key))
            if rec is None or rec.status not in RECALLABLE:
                continue
            u = rec.utility_at(self.lam, t)
            u = u + float(w)
            rec.anchor_u = 1.0 if u > 1.0 else u
            rec.anchor_t = max(t, rec.anchor_t)
            rec.attended += 1
            self.attended_since_pass.add(rec.entity_id)

    def _set_status(
        self, ids: Iterable[str], status: Status, e: dict[str, Any], reason: str | None
    ) -> None:
        for key in ids:
            rec = self.records.get(UUID(key))
            if rec is None or rec.status == Status.ERASED:
                continue
            if status != Status.ERASED and rec.status == Status.TOMBSTONED:
                continue
            rec.status = status
            rec.status_reason = reason
            rec.status_t = float(e["t"])
            rec.status_seq = e["seq"]

    def _op_retain(self, e: dict[str, Any]) -> None:
        """One sleep pass's retention decisions, applied atomically."""
        self._set_status(e.get("tombstone", []), Status.TOMBSTONED, e, e.get("reason", "decay"))
        self._set_status(e.get("stage", []), Status.STAGED, e, "retention")
        self.attended_since_pass.clear()

    def _op_consolidate(self, e: dict[str, Any]) -> None:
        self._set_status(e["ids"], Status.CONSOLIDATED, e, e.get("target"))

    def _op_tombstone(self, e: dict[str, Any]) -> None:
        self._set_status(e["ids"], Status.TOMBSTONED, e, e.get("reason", "operator"))

    def _op_erase(self, e: dict[str, Any]) -> None:
        for key in e["ids"]:
            rec = self.records.get(UUID(key))
            if rec is None:
                continue
            rec.status = Status.ERASED
            rec.status_reason = e.get("reason", "erase")
            rec.status_t = float(e["t"])
            rec.status_seq = e["seq"]
            rec.payload = ""
            rec.vector = rec.unit = None

    def _op_revector(self, e: dict[str, Any]) -> None:
        """Re-embedding: new dimension, new vector for every recallable record.

        Records not in the event (tombstoned ones) lose their old-dimension
        vector; they were never going to be ranked again.
        """
        vectors = {UUID(k): decode_vector(v) for k, v in e["vectors"].items()}
        self.dim = int(e["dim"])
        for eid, rec in self.records.items():
            vec = vectors.get(eid)
            rec.vector = vec
            rec.unit = _unit(vec) if vec is not None else None

    def _op_note(self, e: dict[str, Any]) -> None:
        """Informational events (migration provenance, etc.). No state change
        except recording which half-life the journal was last run with."""
        if e.get("kind") == "half_life_change":
            self.half_life_seconds = float(e["half_life_seconds"])

    # -- queries -------------------------------------------------------

    def count_protected(self) -> int:
        return sum(
            1 for r in self.records.values() if r.status in RECALLABLE and r.protected_floor > 0.0
        )

    def recallable(self) -> list[Record]:
        return [r for r in self.records.values() if r.status in RECALLABLE]
