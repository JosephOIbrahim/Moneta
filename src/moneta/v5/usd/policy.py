"""Context policy resolved by USD composition.

Each context is one USD layer. A context's parent is its (single)
sublayer, so ``session -> project -> default`` is an ordinary sublayer
stack and Pcp does the strongest-opinion-wins resolution. This is the
place in Moneta where composition is load-bearing: the answer to "which
memories may this session see, and which claim wins each slot" is
computed by USD, not by Python.

Layer content::

    #usda 1.0
    ( customLayerData = { string monetaContext = "projA.s12" }
      subLayers = [ @policy_projA.usda@ ] )

    def "Policy" {
        string[] includeScopes = ["projA", "shared"]   # authored only if the spec has it
        string[] excludeScopes = []
        string[] excludeRecords = ["<uuid>"]
        def "Slots" {
            def "s_<sha1 of slot name>" {               # never a natural-language prim name
                string slot = "answer_style"
                string selected = "<uuid>"
            }
        }
    }

The same dict spec drives :class:`moneta.v5.policy.PlainPolicyResolver`;
the conformance suite asserts both resolve identically.
"""

from __future__ import annotations

import copy
import hashlib
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pxr import Sdf, Usd

from ..policy import (
    DEFAULT_CONTEXT,
    ResolvedPolicy,
    UnknownContextError,
    context_chain,
    make_resolved,
    validate_spec,
)

POLICY_PATH = Sdf.Path("/Policy")
SLOTS_PATH = POLICY_PATH.AppendChild("Slots")
_ATTRS = {
    "include_scopes": "includeScopes",
    "exclude_scopes": "excludeScopes",
    "exclude_records": "excludeRecords",
}


def slot_prim_name(slot: str) -> str:
    """UUID-like prim name for a slot (substrate convention #1)."""
    return "s_" + hashlib.sha1(slot.encode("utf-8")).hexdigest()[:16]


def _safe_file_name(context: str) -> str:
    return "policy_" + hashlib.sha1(context.encode("utf-8")).hexdigest()[:12] + ".usda"


def _author_body(layer: Sdf.Layer, context: str, body: Mapping[str, Any]) -> None:
    with Sdf.ChangeBlock():
        if layer.GetPrimAtPath(POLICY_PATH):
            del layer.rootPrims["Policy"]
        prim = Sdf.CreatePrimInLayer(layer, POLICY_PATH)
        prim.specifier = Sdf.SpecifierDef
        for key, attr_name in _ATTRS.items():
            if key in body:
                attr = Sdf.AttributeSpec(prim, attr_name, Sdf.ValueTypeNames.StringArray)
                attr.default = [str(v) for v in body[key]]
        slots = body.get("slots") or {}
        if slots:
            slots_prim = Sdf.CreatePrimInLayer(layer, SLOTS_PATH)
            slots_prim.specifier = Sdf.SpecifierDef
            for slot, selected in sorted(slots.items()):
                sp = Sdf.CreatePrimInLayer(layer, SLOTS_PATH.AppendChild(slot_prim_name(slot)))
                sp.specifier = Sdf.SpecifierDef
                a = Sdf.AttributeSpec(sp, "slot", Sdf.ValueTypeNames.String)
                a.default = slot
                b = Sdf.AttributeSpec(sp, "selected", Sdf.ValueTypeNames.String)
                b.default = str(selected)
        data = dict(layer.customLayerData)
        data["monetaContext"] = context
        layer.customLayerData = data


def author_policy_layers(
    spec: Mapping[str, Mapping[str, Any]], directory: Path | None = None
) -> dict[str, Sdf.Layer]:
    """Author one layer per context. Anonymous layers when ``directory`` is None."""
    spec = copy.deepcopy(dict(spec))
    spec.setdefault(DEFAULT_CONTEXT, {})
    validate_spec(spec)
    layers: dict[str, Sdf.Layer] = {}

    def make(name: str) -> Sdf.Layer:
        if name in layers:
            return layers[name]
        parent = spec[name].get("parent")
        parent_layer = make(parent) if parent is not None else None
        if directory is None:
            layer = Sdf.Layer.CreateAnonymous(f"policy_{name}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / _safe_file_name(name)
            layer = Sdf.Layer.FindOrOpen(str(path)) or Sdf.Layer.CreateNew(str(path))
            layer.Clear()
        if parent_layer is not None:
            if directory is None:
                layer.subLayerPaths.append(parent_layer.identifier)
            else:
                layer.subLayerPaths.append("./" + Path(parent_layer.realPath).name)
        _author_body(layer, name, spec[name])
        if directory is not None:
            layer.Save()
        layers[name] = layer
        return layer

    for name in spec:
        make(name)
    return layers


class UsdPolicyResolver:
    """PolicyResolver whose answers come from composing USD layers."""

    def __init__(self, layers: Mapping[str, Sdf.Layer]) -> None:
        self._lock = threading.Lock()
        self._layers: dict[str, Sdf.Layer] = dict(layers)
        if DEFAULT_CONTEXT not in self._layers:
            self._layers.update(author_policy_layers({DEFAULT_CONTEXT: {}}))
        self._stages: dict[str, Usd.Stage] = {}
        self._directory: Path | None = None

    # -- construction --------------------------------------------------

    @classmethod
    def from_spec(
        cls, spec: Mapping[str, Mapping[str, Any]], directory: Path | None = None
    ) -> UsdPolicyResolver:
        resolver = cls(author_policy_layers(spec, directory))
        resolver._directory = directory
        return resolver

    @classmethod
    def from_directory(cls, directory: Path) -> UsdPolicyResolver:
        """Load every ``*.usda`` in ``directory`` that declares ``monetaContext``."""
        layers: dict[str, Sdf.Layer] = {}
        for path in sorted(Path(directory).glob("*.usda")):
            layer = Sdf.Layer.FindOrOpen(str(path))
            name = dict(layer.customLayerData).get("monetaContext") if layer else None
            if name:
                if name in layers:
                    raise ValueError(f"two layers declare context {name!r}")
                layers[name] = layer
        resolver = cls(layers)
        resolver._directory = Path(directory)
        return resolver

    # -- PolicyResolver ------------------------------------------------

    def contexts(self) -> list[str]:
        with self._lock:
            return sorted(self._layers)

    def layer(self, context: str) -> Sdf.Layer:
        return self._layers[context]

    def resolve(self, context: str | None) -> ResolvedPolicy:
        name = context or DEFAULT_CONTEXT
        with self._lock:
            layer = self._layers.get(name)
            if layer is None:
                raise UnknownContextError(name)
            stage = self._stages.get(name)
            if stage is None:
                stage = Usd.Stage.Open(layer, Usd.Stage.LoadNone)
                self._stages[name] = stage
            stack: list[str] = []
            for lyr in stage.GetLayerStack(includeSessionLayers=False):
                ctx = dict(lyr.customLayerData).get("monetaContext")
                if ctx is not None:
                    stack.append(ctx)
            values: dict[str, Any] = {}
            slots: dict[str, str] = {}
            prim = stage.GetPrimAtPath(POLICY_PATH)
            if prim:
                for key, attr_name in _ATTRS.items():
                    attr = prim.GetAttribute(attr_name)
                    if attr and attr.HasAuthoredValue():
                        values[key] = [str(v) for v in attr.Get()]
                slots_prim = stage.GetPrimAtPath(SLOTS_PATH)
                if slots_prim:
                    for child in slots_prim.GetChildren():
                        slot_attr = child.GetAttribute("slot")
                        sel_attr = child.GetAttribute("selected")
                        if slot_attr and sel_attr and sel_attr.HasAuthoredValue():
                            slots[str(slot_attr.Get())] = str(sel_attr.Get())
            return make_resolved(name, stack, values, slots)

    # -- authoring -----------------------------------------------------

    def _parent_of(self, name: str) -> str | None:
        paths = list(self._layers[name].subLayerPaths)
        if not paths:
            return None
        parent_layer = Sdf.Layer.FindOrOpenRelativeToLayer(self._layers[name], paths[0])
        return dict(parent_layer.customLayerData).get("monetaContext") if parent_layer else None

    def set_layer(self, name: str, body: Mapping[str, Any]) -> None:
        """Author (replace) one existing context's opinions.

        Unlike the plain resolver, this cannot create a context or re-parent
        one: those change the sublayer graph, so they go through
        :meth:`from_spec`. Both refusals raise rather than being ignored.
        """
        with self._lock:
            layer = self._layers.get(name)
            if layer is None:
                raise UnknownContextError(name)
            current_parent = self._parent_of(name)
            if "parent" in body and body["parent"] != current_parent:
                raise ValueError(
                    f"context {name!r} has parent {current_parent!r}; re-parenting to "
                    f"{body['parent']!r} needs UsdPolicyResolver.from_spec"
                )
            spec = {n: {} for n in self._layers}
            validate_spec({**spec, name: {k: v for k, v in body.items() if k != "parent"}})
            _author_body(layer, name, body)
            if not layer.anonymous:
                layer.Save()
            self._stages.clear()

    def reload(self) -> None:
        """Pick up edits made to the layer files by another tool (e.g. Solaris)."""
        with self._lock:
            for layer in self._layers.values():
                if not layer.anonymous:
                    layer.Reload(force=True)
            self._stages.clear()


def chain_for(spec: Mapping[str, Mapping[str, Any]], context: str) -> list[str]:
    return context_chain(spec, context)
