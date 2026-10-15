"""Moneta v5: the journal is the database.

Status: reference implementation for the Round 4 (§9) escalation. It
lives beside v1 and changes nothing in v1; ``moneta.Moneta`` is still the
v1 handle. See ``docs/v5/BLUEPRINT.md``.

Quick start::

    from moneta.v5 import Substrate, Config

    with Substrate(Config(path="memory.v5.journal")) as m:
        eid = m.deposit("prefers concise answers", embedding, scope="projA")
        hits = m.recall(embedding, context="projA")
        m.signal_attention({eid: 0.3})
        print(m.explain(eid, context="projA").detail)

Existing v1 consumers use :class:`moneta.v5.compat.Moneta` with their
unchanged ``MonetaConfig``.
"""

from .journal import JournalCorruptError, JournalLockedError, repair
from .model import DimensionMismatchError, Status
from .policy import (
    DEFAULT_CONTEXT,
    PlainPolicyResolver,
    PolicyResolver,
    ResolvedPolicy,
    UnknownContextError,
)
from .substrate import (
    VERSION,
    AttentionReceipt,
    Clock,
    Config,
    Explanation,
    Generation,
    IdempotencyConflictError,
    ManualClock,
    MemoryProjector,
    Projector,
    RecallItem,
    RecallResult,
    SleepPassResult,
    Substrate,
    SubstrateClosedError,
    SystemClock,
    UnknownEntityError,
    Verdict,
)

__all__ = [
    "VERSION",
    "Substrate",
    "Config",
    "Clock",
    "SystemClock",
    "ManualClock",
    "Projector",
    "MemoryProjector",
    "Generation",
    "RecallItem",
    "RecallResult",
    "AttentionReceipt",
    "SleepPassResult",
    "Explanation",
    "Verdict",
    "Status",
    "PolicyResolver",
    "PlainPolicyResolver",
    "ResolvedPolicy",
    "DEFAULT_CONTEXT",
    "UnknownContextError",
    "UnknownEntityError",
    "IdempotencyConflictError",
    "DimensionMismatchError",
    "SubstrateClosedError",
    "JournalCorruptError",
    "JournalLockedError",
    "repair",
]
