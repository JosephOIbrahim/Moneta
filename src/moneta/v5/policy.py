"""Policy: the part of Moneta that composes.

Records never compose. Two contradictory memories are two things with
their own provenance, not two opinions about one thing. *Policy* is where
competing opinions genuinely exist ("project A excludes scratch notes",
"this session prefers the newer answer"), so policy is where composition
lives.

A context is a named policy layer with an optional parent. Resolving a
context walks the chain strongest-first and, for every field, takes the
**strongest authored opinion** (USD sublayer semantics). Nothing merges:
an authored list replaces a weaker list outright. The same rule applies
per slot for slot selections.

:class:`PlainPolicyResolver` implements this in plain Python.
:class:`moneta.v5.usd.policy.UsdPolicyResolver` implements it with a real
USD sublayer stack. The conformance suite asserts the two produce
identical :class:`ResolvedPolicy` values for the same authored spec, so
the plain resolver is a faithful control for the USD one.

Layer spec (a plain dict, identical input for both resolvers)::

    {
      "default":  {},
      "projA":    {"parent": "default", "include_scopes": ["projA", "shared"]},
      "projA.s12":{"parent": "projA", "exclude_records": ["<uuid>"],
                   "slots": {"answer_style": "<uuid>"}},
    }

Fields: ``include_scopes`` (list; absent = every scope),
``exclude_scopes`` (list), ``exclude_records`` (list of UUID strings),
``slots`` (mapping slot name -> selected UUID string).
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

DEFAULT_CONTEXT = "default"
FIELDS = ("include_scopes", "exclude_scopes", "exclude_records")


class UnknownContextError(KeyError):
    """The requested context has no authored layer."""


@dataclass(frozen=True)
class ResolvedPolicy:
    """One context's policy after composition. Immutable and hashable."""

    context: str
    include_scopes: frozenset[str] | None
    exclude_scopes: frozenset[str]
    exclude_records: frozenset[UUID]
    slot_selections: tuple[tuple[str, UUID], ...]
    stack: tuple[str, ...]
    fingerprint: str = field(compare=False)

    @property
    def slots(self) -> dict[str, UUID]:
        return dict(self.slot_selections)

    def admits_scope(self, scope: str) -> bool:
        if scope in self.exclude_scopes:
            return False
        return self.include_scopes is None or scope in self.include_scopes

    def semantic(self) -> dict[str, Any]:
        """Resolver-independent content, used for equivalence checks."""
        return {
            "context": self.context,
            "include_scopes": None if self.include_scopes is None else sorted(self.include_scopes),
            "exclude_scopes": sorted(self.exclude_scopes),
            "exclude_records": sorted(str(u) for u in self.exclude_records),
            "slots": {k: str(v) for k, v in sorted(self.slot_selections)},
            "stack": list(self.stack),
        }


def make_resolved(
    context: str, stack: list[str], values: dict[str, Any], slots: dict[str, str]
) -> ResolvedPolicy:
    inc = values.get("include_scopes")
    body = {
        "context": context,
        "include_scopes": None if inc is None else sorted(set(inc)),
        "exclude_scopes": sorted(set(values.get("exclude_scopes") or [])),
        "exclude_records": sorted({str(UUID(u)) for u in values.get("exclude_records") or []}),
        "slots": {k: str(UUID(v)) for k, v in sorted(slots.items())},
        "stack": list(stack),
    }
    fingerprint = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return ResolvedPolicy(
        context=context,
        include_scopes=None if inc is None else frozenset(body["include_scopes"]),
        exclude_scopes=frozenset(body["exclude_scopes"]),
        exclude_records=frozenset(UUID(u) for u in body["exclude_records"]),
        slot_selections=tuple((k, UUID(v)) for k, v in body["slots"].items()),
        stack=tuple(stack),
        fingerprint=fingerprint,
    )


ADMIT_ALL = make_resolved(DEFAULT_CONTEXT, [DEFAULT_CONTEXT], {}, {})


class PolicyResolver(Protocol):
    """Port: anything that turns a context name into a ResolvedPolicy."""

    def resolve(self, context: str | None) -> ResolvedPolicy: ...

    def contexts(self) -> list[str]: ...


def context_chain(spec: Mapping[str, Mapping[str, Any]], context: str) -> list[str]:
    """Strongest-first chain of layer names. Raises on unknown names or cycles."""
    chain: list[str] = []
    name: str | None = context
    while name is not None:
        if name not in spec:
            raise UnknownContextError(name)
        if name in chain:
            raise ValueError(f"policy context cycle through {name!r}")
        chain.append(name)
        name = spec[name].get("parent")
    return chain


def validate_spec(spec: Mapping[str, Mapping[str, Any]]) -> None:
    allowed = set(FIELDS) | {"parent", "slots"}
    for name, layer in spec.items():
        if not isinstance(name, str) or not name:
            raise ValueError("context names must be non-empty strings")
        extra = set(layer) - allowed
        if extra:
            raise ValueError(f"context {name!r} has unknown fields {sorted(extra)}")
        parent = layer.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise ValueError(f"context {name!r} parent must be a str")
        for f in FIELDS:
            if f not in layer:
                continue
            if not isinstance(layer[f], (list, tuple)):
                raise ValueError(f"context {name!r} field {f} must be a list")
            if not all(isinstance(v, str) for v in layer[f]):
                raise ValueError(f"context {name!r} field {f} must contain only strings")
        for u in layer.get("exclude_records", []) or []:
            UUID(u)
        slots = layer.get("slots") or {}
        if not isinstance(slots, Mapping):
            raise ValueError(f"context {name!r} slots must be a mapping")
        for slot, u in slots.items():
            if not isinstance(slot, str) or not slot:
                raise ValueError(f"context {name!r} has an empty or non-string slot name")
            if not isinstance(u, str):
                raise ValueError(f"context {name!r} slot {slot!r} selection must be a UUID str")
            UUID(u)
        context_chain(spec, name)


class PlainPolicyResolver:
    """Strongest-opinion-wins resolution over a dict of layers, in Python."""

    def __init__(self, spec: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._lock = threading.Lock()
        spec = copy.deepcopy(dict(spec or {}))
        spec.setdefault(DEFAULT_CONTEXT, {})
        validate_spec(spec)
        self._spec: dict[str, dict[str, Any]] = spec
        self.revision = 1

    def contexts(self) -> list[str]:
        with self._lock:
            return sorted(self._spec)

    def spec(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._spec)

    def set_layer(self, name: str, layer: Mapping[str, Any]) -> None:
        """Author (replace) one context layer. Validated before it takes effect."""
        with self._lock:
            candidate = copy.deepcopy(self._spec)
            candidate[name] = copy.deepcopy(dict(layer))
            validate_spec(candidate)
            self._spec = candidate
            self.revision += 1

    def resolve(self, context: str | None) -> ResolvedPolicy:
        with self._lock:
            name = context or DEFAULT_CONTEXT
            chain = context_chain(self._spec, name)
            values: dict[str, Any] = {}
            for f in FIELDS:
                for layer_name in chain:  # strongest first
                    if f in self._spec[layer_name]:
                        values[f] = list(self._spec[layer_name][f])
                        break
            slots: dict[str, str] = {}
            for layer_name in reversed(chain):  # weakest first, stronger overwrite
                slots.update(self._spec[layer_name].get("slots") or {})
            return make_resolved(name, chain, values, slots)
