"""Moneta v5 substrate handle.

One idea: **the journal is the database.** Every operation that changes
anything appends one checksummed event to the journal first, and only
then updates derived state. Every read is a pure function of
``(journal prefix, policy, context, t_eval)`` and never writes.

What changed from v1 and why (each is a probe in tests/v5/test_v1_defects.py)
------------------------------------------------------------------------------
- Deposits are durable on return (v1 lost them unless a sleep pass ran).
- Validation happens before the journal append, so a rejected deposit
  leaves no trace (v1 left an ECS row the index did not have).
- A wrong-dimension query raises (v1 returned an empty success).
- Attention is applied at the signal's own timestamp (v1 erased decay).
- Attention weights must be finite and in [0, 1]; unknown ids raise
  (v1 let one negative or NaN weight delete a memory).
- Pruning is a tombstone event that names what was removed; payloads stay
  inspectable through :meth:`explain` (v1 deleted silently).
- A failed projection leaves records STAGED and the next pass retries
  (v1 stranded them in STAGED_FOR_SYNC forever).
- Exclusivity is an OS lock on the journal path (v1 keyed on a URI string,
  so two URIs could share one snapshot and lose writes).
- Free-threaded Python is supported: one writer lock orders the journal;
  there is no GIL-dependent swap.

The four agent operations keep their v1 names and positional signatures.
Everything added is keyword-only.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid as _uuid
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    NamedTuple,
    Protocol,
)
from uuid import UUID

from ..api import ProtectedQuotaExceededError
from ..consolidation import (
    MAX_BATCH_SIZE,
    PRUNE_ATTENDED_THRESHOLD,
    PRUNE_UTILITY_THRESHOLD,
    STAGE_ATTENDED_THRESHOLD,
    STAGE_UTILITY_THRESHOLD,
)
from ..decay import DEFAULT_HALF_LIFE_SECONDS, DecayConfig
from ..types import Memory
from .index import ExactIndex
from .journal import FORMAT, FileJournal, MemoryJournal
from .model import (
    RECALLABLE,
    DimensionMismatchError,
    Fold,
    Record,
    Status,
    encode_vector,
    validate_vector,
)
from .policy import PlainPolicyResolver, PolicyResolver, ResolvedPolicy

_logger = logging.getLogger(__name__)

VERSION = "5.0.0a1"


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class UnknownEntityError(KeyError):
    """An id that was never deposited in this store."""


class IdempotencyConflictError(ValueError):
    """A deposit reused an idempotency key with different content."""


class SubstrateClosedError(RuntimeError):
    """The handle has been closed."""


# ----------------------------------------------------------------------
# Clock
# ----------------------------------------------------------------------


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    def now(self) -> float:
        return time.time()


class ManualClock:
    """Deterministic clock for tests and replays."""

    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = float(t)

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += float(seconds)
        return self.t


# ----------------------------------------------------------------------
# Projection port (the USD cold tier is one implementation)
# ----------------------------------------------------------------------


class Projector(Protocol):
    """Writes staged records somewhere durable and derived (e.g. USD layers)."""

    name: str

    def project(self, memories: list[Memory], t: float) -> str:
        """Author a batch; return a batch/target identifier. Raise on failure."""
        ...

    def close(self) -> None: ...


class MemoryProjector:
    """In-process projector: keeps batches in a list. Parity with v1's MockUsdTarget."""

    name = "memory"

    def __init__(self) -> None:
        self.batches: list[tuple[str, list[Memory]]] = []

    def project(self, memories: list[Memory], t: float) -> str:
        batch_id = str(_uuid.uuid4())
        self.batches.append((batch_id, list(memories)))
        return batch_id

    def close(self) -> None:
        pass


# ----------------------------------------------------------------------
# Config and results
# ----------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Config:
    """v5 handle configuration.

    ``path`` is the journal file. ``None`` means an in-memory journal.
    The handle takes ownership of ``projector`` and closes it.
    """

    path: Path | None = None
    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS
    embedding_dim: int | None = None
    protected_quota: int = 100
    fsync: bool = True
    clock: Clock = field(default_factory=SystemClock)
    policy: PolicyResolver | None = None
    projector: Projector | None = None

    @classmethod
    def ephemeral(cls, **overrides: Any) -> Config:
        overrides.setdefault("path", None)
        return cls(**overrides)


@dataclass(frozen=True)
class Generation:
    """What a read was pinned to. Echoed on every result."""

    seq: int
    t_eval: float
    context: str
    policy_fingerprint: str


@dataclass(frozen=True)
class RecallItem:
    memory: Memory
    score: float
    cosine: float
    scope: str
    slot: str | None
    seq: int


@dataclass(frozen=True)
class RecallResult:
    items: tuple[RecallItem, ...]
    generation: Generation
    policy: ResolvedPolicy

    @property
    def memories(self) -> list[Memory]:
        return [i.memory for i in self.items]


@dataclass(frozen=True)
class AttentionReceipt:
    seq: int | None
    applied: tuple[UUID, ...]
    ignored: tuple[UUID, ...]


class SleepPassResult(NamedTuple):
    """First four fields match v1's ConsolidationResult by name and position."""

    attention_updated: int
    pruned: int
    staged: int
    authored_at: float | None
    pruned_ids: tuple[UUID, ...] = ()
    staged_ids: tuple[UUID, ...] = ()
    consolidated_ids: tuple[UUID, ...] = ()
    projection_error: str | None = None
    seq: int = 0


class Verdict:
    ELIGIBLE = "eligible"
    NOT_ALLOWED = "not_allowed_for_caller"
    EXCLUDED_SCOPE = "excluded_scope"
    EXCLUDED_RECORD = "excluded_record"
    SLOT_LOSER = "slot_loser"
    TOMBSTONED = "tombstoned"
    ERASED = "erased"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Explanation:
    entity_id: UUID
    verdict: str
    detail: str
    generation: Generation
    status: str | None = None
    status_reason: str | None = None
    scope: str | None = None
    slot: str | None = None
    slot_winner: UUID | None = None
    utility: float | None = None
    attended: int | None = None
    protected_floor: float | None = None
    deposited_at: float | None = None
    anchor_t: float | None = None
    seq: int | None = None
    payload: str | None = None


# ----------------------------------------------------------------------
# The handle
# ----------------------------------------------------------------------


def _finite(name: str, value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not math.isfinite(v):
        raise ValueError(f"{name} must be finite")
    return v


class Substrate:
    """Moneta v5. Construct with a :class:`Config`; use as a context manager."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._decay = DecayConfig(half_life_seconds=config.half_life_seconds)  # range-checked
        self._lock = threading.RLock()
        self._closed = False
        self._clock = config.clock
        self._policy: PolicyResolver = config.policy or PlainPolicyResolver()
        self._projector: Projector | None = config.projector
        if config.protected_quota < 0:
            raise ValueError("protected_quota must be >= 0")

        self._journal = (
            FileJournal(Path(config.path), fsync=config.fsync)
            if config.path is not None
            else MemoryJournal()
        )
        try:
            self._fold = Fold(self._decay.lambda_)
            replayed = self._fold.replay(self._journal.events())
            if config.embedding_dim is not None:
                if self._fold.dim is not None and self._fold.dim != config.embedding_dim:
                    raise DimensionMismatchError(self._fold.dim, config.embedding_dim)
                self._fold.dim = config.embedding_dim
            if self._journal.last_seq == 0:
                self._append(
                    {
                        "op": "genesis",
                        "format": FORMAT,
                        "version": VERSION,
                        "t": self._clock.now(),
                        "dim": config.embedding_dim,
                        "half_life_seconds": config.half_life_seconds,
                    }
                )
            self._index = ExactIndex()
            self._index.dim = self._fold.dim
            for rec in self._fold.records.values():
                if rec.status in RECALLABLE and rec.unit is not None:
                    self._index.add(rec.entity_id, rec.unit)
        except BaseException:
            self._journal.close()
            raise
        _logger.info(
            "moneta.v5 open path=%s events=%d records=%d tail_recovered=%d",
            config.path,
            replayed,
            len(self._fold.records),
            self._journal.recovered_tail_bytes,
        )

    # -- lifecycle -----------------------------------------------------

    def __enter__(self) -> Substrate:
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self._projector is not None and hasattr(self._projector, "close"):
                    self._projector.close()
            finally:
                self._journal.close()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def lam(self) -> float:
        return self._decay.lambda_

    @property
    def seq(self) -> int:
        return self._journal.last_seq

    @property
    def journal_path(self) -> Path | None:
        return self._journal.path

    @property
    def dim(self) -> int | None:
        return self._fold.dim

    @property
    def policy(self) -> PolicyResolver:
        return self._policy

    @property
    def recovered_tail_bytes(self) -> int:
        return self._journal.recovered_tail_bytes

    # -- internals -----------------------------------------------------

    def _check_open(self) -> None:
        if self._closed:
            raise SubstrateClosedError("Moneta v5 handle is closed")

    def _t(self, t: float | None) -> float:
        return self._clock.now() if t is None else _finite("t", t)

    def _append(self, event: dict[str, Any]) -> int:
        """Journal first, then fold. The only write path in v5."""
        seq = self._journal.append(event)
        self._fold.apply(dict(event, seq=seq))
        return seq

    def _resolve(self, context: str | None) -> ResolvedPolicy:
        return self._policy.resolve(context)

    def _verdicts(
        self, policy: ResolvedPolicy, allowed: frozenset[str] | None
    ) -> tuple[dict[UUID, str], dict[str, UUID]]:
        verdicts: dict[UUID, str] = {}
        candidates: list[Record] = []
        for rec in self._fold.records.values():
            if rec.status == Status.ERASED:
                verdicts[rec.entity_id] = Verdict.ERASED
            elif rec.status == Status.TOMBSTONED:
                verdicts[rec.entity_id] = Verdict.TOMBSTONED
            elif allowed is not None and rec.scope not in allowed:
                verdicts[rec.entity_id] = Verdict.NOT_ALLOWED
            elif not policy.admits_scope(rec.scope):
                verdicts[rec.entity_id] = Verdict.EXCLUDED_SCOPE
            elif rec.entity_id in policy.exclude_records:
                verdicts[rec.entity_id] = Verdict.EXCLUDED_RECORD
            else:
                candidates.append(rec)
        by_slot: dict[str, list[Record]] = {}
        for rec in candidates:
            if rec.slot is not None:
                by_slot.setdefault(rec.slot, []).append(rec)
        selections = policy.slots
        winners: dict[str, UUID] = {}
        for slot, recs in by_slot.items():
            chosen = None
            sel = selections.get(slot)
            if sel is not None:
                chosen = next((r for r in recs if r.entity_id == sel), None)
            if chosen is None:
                chosen = max(recs, key=lambda r: r.seq)
            winners[slot] = chosen.entity_id
        for rec in candidates:
            if rec.slot is not None and winners[rec.slot] != rec.entity_id:
                verdicts[rec.entity_id] = Verdict.SLOT_LOSER
            else:
                verdicts[rec.entity_id] = Verdict.ELIGIBLE
        return verdicts, winners

    @staticmethod
    def _allowed(allowed_scopes: Iterable[str] | None) -> frozenset[str] | None:
        if allowed_scopes is None:
            return None
        if isinstance(allowed_scopes, str):
            raise TypeError("allowed_scopes must be a collection of scope names, not a string")
        return frozenset(allowed_scopes)

    # ------------------------------------------------------------------
    # The four agent operations
    # ------------------------------------------------------------------

    def deposit(
        self,
        payload: str,
        embedding: list[float],
        protected_floor: float = 0.0,
        *,
        scope: str = "",
        slot: str | None = None,
        key: str | None = None,
        t: float | None = None,
    ) -> UUID:
        """Record a memory. Returns only after the event is durably journaled."""
        with self._lock:
            self._check_open()
            if not isinstance(payload, str):
                raise TypeError("payload must be a str")
            if not isinstance(scope, str):
                raise TypeError("scope must be a str")
            if slot is not None and (not isinstance(slot, str) or not slot):
                raise ValueError("slot must be a non-empty str or None")
            if key is not None and (not isinstance(key, str) or not key):
                raise ValueError("key must be a non-empty str or None")
            floor = _finite("protected_floor", protected_floor)
            if not 0.0 <= floor <= 1.0:
                raise ValueError("protected_floor must be in [0, 1]")
            vec = validate_vector(embedding, self._fold.dim)
            when = self._t(t)

            if key is not None and key in self._fold.by_key:
                existing = self._fold.records[self._fold.by_key[key]]
                if existing.status != Status.ERASED and (
                    existing.payload != payload or existing.vector != vec
                ):
                    raise IdempotencyConflictError(
                        f"key {key!r} already names {existing.entity_id} with different content"
                    )
                return existing.entity_id

            if floor > 0.0 and self._fold.count_protected() >= self.config.protected_quota:
                raise ProtectedQuotaExceededError(
                    f"protected quota of {self.config.protected_quota} exceeded"
                )

            entity_id = _uuid.uuid4()
            event: dict[str, Any] = {
                "op": "deposit",
                "id": str(entity_id),
                "t": when,
                "payload": payload,
                "emb": encode_vector(vec),
                "floor": floor,
                "scope": scope,
            }
            if slot is not None:
                event["slot"] = slot
            if key is not None:
                event["key"] = key
            self._append(event)
            rec = self._fold.records[entity_id]
            self._index.dim = self._fold.dim
            self._index.add(entity_id, rec.unit)
            return entity_id

    def query(self, embedding: list[float], limit: int = 5, **kwargs: Any) -> list[Memory]:
        """v1-shaped recall: the top ``limit`` memories. See :meth:`recall`."""
        return self.recall(embedding, limit, **kwargs).memories

    def recall(
        self,
        embedding: Sequence[float],
        limit: int = 5,
        *,
        context: str | None = None,
        allowed_scopes: Iterable[str] | None = None,
        t: float | None = None,
    ) -> RecallResult:
        """Rank eligible memories by ``max(cosine, 0) * utility`` at ``t``.

        Pins one generation: the journal seq, the resolved policy and the
        evaluation time are fixed for the whole call and echoed back.
        Ties break by deposit order, so equal inputs give equal outputs.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative int")
        allowed = self._allowed(allowed_scopes)
        with self._lock:
            self._check_open()
            when = self._t(t)
            policy = self._resolve(context)
            generation = Generation(self.seq, when, policy.context, policy.fingerprint)
            query_vec = validate_vector(embedding, self._fold.dim)
            if self._fold.dim is None:
                return RecallResult((), generation, policy)
            verdicts, _ = self._verdicts(policy, allowed)
            eligible = [eid for eid, v in verdicts.items() if v == Verdict.ELIGIBLE]
            cosines = self._index.cosines(query_vec, eligible)
            scored = []
            for eid, cos in cosines:
                rec = self._fold.records[eid]
                u = rec.utility_at(self.lam, when)
                scored.append((max(cos, 0.0) * u, rec.seq, cos, rec))
            scored.sort(key=lambda s: (-s[0], s[1]))
            items = tuple(
                RecallItem(rec.to_memory(self.lam, when), score, cos, rec.scope, rec.slot, seq)
                for score, seq, cos, rec in scored[:limit]
            )
            return RecallResult(items, generation, policy)

    def signal_attention(
        self, weights: dict[UUID, float], *, t: float | None = None
    ) -> AttentionReceipt:
        """Reinforce memories. All-or-nothing validation, then one journal event.

        Weights must be finite and in [0, 1]. Ids never deposited raise
        :class:`UnknownEntityError`. Tombstoned or erased ids are accepted
        and reported as ignored.
        """
        with self._lock:
            self._check_open()
            when = self._t(t)
            clean: dict[str, float] = {}
            applied: list[UUID] = []
            ignored: list[UUID] = []
            for raw_id, raw_w in weights.items():
                eid = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
                w = _finite(f"weight for {eid}", raw_w)
                if not 0.0 <= w <= 1.0:
                    raise ValueError(f"weight for {eid} must be in [0, 1], got {w}")
                rec = self._fold.records.get(eid)
                if rec is None:
                    raise UnknownEntityError(str(eid))
                if rec.status in RECALLABLE:
                    clean[str(eid)] = w
                    applied.append(eid)
                else:
                    ignored.append(eid)
            if not clean:
                return AttentionReceipt(None, (), tuple(ignored))
            seq = self._append({"op": "attend", "t": when, "w": clean})
            return AttentionReceipt(seq, tuple(applied), tuple(ignored))

    def get_consolidation_manifest(self, *, t: float | None = None) -> list[Memory]:
        """Records the retention policy has staged but not yet projected."""
        with self._lock:
            self._check_open()
            when = self._t(t)
            staged = [r for r in self._fold.records.values() if r.status == Status.STAGED]
            staged.sort(key=lambda r: r.seq)
            return [r.to_memory(self.lam, when) for r in staged]

    # ------------------------------------------------------------------
    # Harness / operator operations (not part of the agent surface)
    # ------------------------------------------------------------------

    def run_sleep_pass(self, *, t: float | None = None) -> SleepPassResult:
        """Retention and projection at ``t``.

        Retention thresholds are v1's locked Round 2 defaults. Every pass
        appends one ``retain`` event recording exactly what it pruned and
        staged, even when that is nothing. Staged records (including ones
        a previous failed pass left behind) are then projected in batches;
        each successful batch appends a ``consolidate`` event.
        """
        with self._lock:
            self._check_open()
            when = self._t(t)
            attention_updated = len(self._fold.attended_since_pass)
            prune: list[UUID] = []
            stage: list[UUID] = []
            for rec in sorted(self._fold.records.values(), key=lambda r: r.seq):
                if rec.status != Status.LIVE:
                    continue
                u = rec.utility_at(self.lam, when)
                if u < PRUNE_UTILITY_THRESHOLD and rec.attended < PRUNE_ATTENDED_THRESHOLD:
                    prune.append(rec.entity_id)
                elif u < STAGE_UTILITY_THRESHOLD and rec.attended >= STAGE_ATTENDED_THRESHOLD:
                    stage.append(rec.entity_id)
            seq = self._append(
                {
                    "op": "retain",
                    "t": when,
                    "reason": "decay",
                    "tombstone": [str(e) for e in prune],
                    "stage": [str(e) for e in stage],
                }
            )
            for eid in prune:
                self._index.remove(eid)

            pending = sorted(
                (r for r in self._fold.records.values() if r.status == Status.STAGED),
                key=lambda r: r.seq,
            )
            consolidated: list[UUID] = []
            error: str | None = None
            authored_at: float | None = None
            for start in range(0, len(pending), MAX_BATCH_SIZE):
                batch = pending[start : start + MAX_BATCH_SIZE]
                memories = [r.to_memory(self.lam, when) for r in batch]
                if self._projector is None:
                    target, batch_id = "none", None
                else:
                    try:
                        batch_id = self._projector.project(memories, when)
                        target = self._projector.name
                    except Exception as exc:  # noqa: BLE001 - reported, and retried next pass
                        error = f"{type(exc).__name__}: {exc}"
                        _logger.error(
                            "moneta.v5 projection failed; %d records stay staged: %s",
                            len(pending) - start,
                            error,
                        )
                        break
                ids = [str(r.entity_id) for r in batch]
                seq = self._append(
                    {
                        "op": "consolidate",
                        "t": when,
                        "ids": ids,
                        "target": target,
                        "batch": batch_id,
                    }
                )
                consolidated.extend(r.entity_id for r in batch)
                authored_at = when
            return SleepPassResult(
                attention_updated=attention_updated,
                pruned=len(prune),
                staged=len(stage),
                authored_at=authored_at,
                pruned_ids=tuple(prune),
                staged_ids=tuple(stage),
                consolidated_ids=tuple(consolidated),
                projection_error=error,
                seq=seq,
            )

    def explain(
        self,
        entity_id: UUID,
        *,
        context: str | None = None,
        allowed_scopes: Iterable[str] | None = None,
        t: float | None = None,
    ) -> Explanation:
        """Why a memory would or would not be recalled, in one pinned generation."""
        allowed = self._allowed(allowed_scopes)
        with self._lock:
            self._check_open()
            when = self._t(t)
            policy = self._resolve(context)
            generation = Generation(self.seq, when, policy.context, policy.fingerprint)
            eid = entity_id if isinstance(entity_id, UUID) else UUID(str(entity_id))
            rec = self._fold.records.get(eid)
            if rec is None:
                return Explanation(
                    eid, Verdict.UNKNOWN, "never deposited in this store", generation
                )
            verdicts, winners = self._verdicts(policy, allowed)
            verdict = verdicts[eid]
            winner = winners.get(rec.slot) if rec.slot is not None else None
            detail = {
                Verdict.ELIGIBLE: "recallable in this context",
                Verdict.NOT_ALLOWED: f"scope {rec.scope!r} is outside the caller's allowed scopes",
                Verdict.EXCLUDED_SCOPE: f"context {policy.context!r} does not admit scope {rec.scope!r}",
                Verdict.EXCLUDED_RECORD: f"context {policy.context!r} excludes this record",
                Verdict.SLOT_LOSER: f"slot {rec.slot!r} resolves to {winner} in context {policy.context!r}",
                Verdict.TOMBSTONED: f"tombstoned ({rec.status_reason}) at seq {rec.status_seq}",
                Verdict.ERASED: f"erased at seq {rec.status_seq}; payload and vector removed",
            }[verdict]
            if rec.slot is not None and verdict in (Verdict.ELIGIBLE, Verdict.SLOT_LOSER):
                selected = policy.slots.get(rec.slot)
                if selected is None:
                    detail += "; no selection authored, latest eligible claim wins"
                elif selected != winner:
                    detail += f"; authored selection {selected} is not eligible here, latest wins"
            return Explanation(
                entity_id=eid,
                verdict=verdict,
                detail=detail,
                generation=generation,
                status=rec.status.value,
                status_reason=rec.status_reason,
                scope=rec.scope,
                slot=rec.slot,
                slot_winner=winner,
                utility=None if rec.status == Status.ERASED else rec.utility_at(self.lam, when),
                attended=rec.attended,
                protected_floor=rec.protected_floor,
                deposited_at=rec.deposited_at,
                anchor_t=rec.anchor_t,
                seq=rec.seq,
                payload=None if rec.status == Status.ERASED else rec.payload,
            )

    def use_policy(self, resolver: PolicyResolver) -> None:
        """Swap the policy source (host-owned). Takes effect for the next read."""
        with self._lock:
            self._check_open()
            self._policy = resolver

    def describe_context(self, context: str | None = None) -> ResolvedPolicy:
        with self._lock:
            self._check_open()
            return self._resolve(context)

    def tombstone(
        self, ids: Iterable[UUID], *, reason: str = "operator", t: float | None = None
    ) -> int | None:
        """Retire memories from recall. They stay in the journal and in explain()."""
        with self._lock:
            self._check_open()
            keys = self._known(ids)
            if not keys:
                return None
            seq = self._append({"op": "tombstone", "t": self._t(t), "ids": keys, "reason": reason})
            for k in keys:
                self._index.remove(UUID(k))
            return seq

    def erase(
        self, ids: Iterable[UUID], *, reason: str = "erase", t: float | None = None
    ) -> int | None:
        """Remove payload and vector from all derived state now.

        The bytes remain in the journal's deposit event until
        :meth:`compact` rewrites it. ``erase`` + ``compact`` is the
        physical-deletion path.
        """
        with self._lock:
            self._check_open()
            keys = self._known(ids)
            if not keys:
                return None
            seq = self._append({"op": "erase", "t": self._t(t), "ids": keys, "reason": reason})
            for k in keys:
                self._index.remove(UUID(k))
            return seq

    def compact(self) -> dict[str, Any]:
        """Physically remove erased payloads and vectors from the journal."""
        with self._lock:
            self._check_open()
            erased = {
                str(r.entity_id) for r in self._fold.records.values() if r.status == Status.ERASED
            }
            scrubbed = 0

            def transform(event: dict[str, Any]) -> dict[str, Any]:
                nonlocal scrubbed
                if event.get("op") in ("deposit", "import") and event.get("id") in erased:
                    if event.get("payload") or event.get("emb") is not None:
                        scrubbed += 1
                    event["payload"] = ""
                    event["emb"] = None
                    event["erased"] = True
                return event

            self._journal.rewrite(transform)
            return {"erased_records": len(erased), "events_scrubbed": scrubbed, "seq": self.seq}

    def _known(self, ids: Iterable[UUID]) -> list[str]:
        keys: list[str] = []
        for raw in ids:
            eid = raw if isinstance(raw, UUID) else UUID(str(raw))
            if eid not in self._fold.records:
                raise UnknownEntityError(str(eid))
            if str(eid) not in keys:
                keys.append(str(eid))
        return keys

    def sync(self) -> int:
        """Force the journal to stable storage. Returns the durable seq."""
        with self._lock:
            self._check_open()
            self._journal.sync()
            return self.seq

    # -- operator views ------------------------------------------------

    def records(
        self, *, t: float | None = None, include: Iterable[Status] = RECALLABLE
    ) -> Iterator[Memory]:
        """Snapshot of records (v1 Memory shape) in deposit order."""
        with self._lock:
            self._check_open()
            when = self._t(t)
            wanted = set(include)
            rows = sorted(
                (r for r in self._fold.records.values() if r.status in wanted), key=lambda r: r.seq
            )
            snapshot = [r.to_memory(self.lam, when) for r in rows]
        return iter(snapshot)

    def status_of(self, entity_id: UUID) -> Status | None:
        with self._lock:
            rec = self._fold.records.get(entity_id)
            return None if rec is None else rec.status

    def count_protected(self) -> int:
        with self._lock:
            return self._fold.count_protected()

    def recallable_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._fold.records.values() if r.status in RECALLABLE)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            counts: dict[str, int] = {}
            for r in self._fold.records.values():
                counts[r.status.value] = counts.get(r.status.value, 0) + 1
            return {
                "version": VERSION,
                "seq": self.seq,
                "dim": self._fold.dim,
                "records": counts,
                "index": len(self._index),
                "journal": None if self.journal_path is None else str(self.journal_path),
                "half_life_seconds": self._decay.half_life_seconds,
                "projector": None if self._projector is None else self._projector.name,
            }
