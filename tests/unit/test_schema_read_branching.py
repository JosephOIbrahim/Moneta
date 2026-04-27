"""Read-path branching for typed (post-v1.2.0) vs typeless (legacy) prims.

``HANDOFF_codeless_schema_moneta.md`` §7 + §8.3.

The §3 audit (``SCHEMA_read_path_audit.md``) verified the substrate has
zero reads of ``prior_state`` from USD. Read-tolerance therefore lives
in test fixtures only — these tests demonstrate the branching pattern
that any consumer reading both typed (post-v1.2.0) and typeless
(pre-v1.2.0 legacy) prims must implement.

Three cases per handoff §8.3:

    1. Typed prim (``typeName == "MonetaMemory"``) — ``priorState`` is a
       token, resolves to ``EntityState`` via ``_token_to_state``.
    2. Typeless prim (``typeName == ""``) — legacy ``prior_state`` is
       an int, resolves directly via ``EntityState(int(...))``.
    3. Unknown ``typeName`` — raises ``ValueError`` rather than silently
       returning a wrong state (constitution §7 — negative-space
       defense).

The synthetic prims here are authored directly via ``Sdf.AttributeSpec``
and bypass the substrate's write path — this is intentional. The
substrate cannot produce typeless prims after step 5 of the surgery,
so the legacy branch is exercised only by tests that author the
legacy shape on purpose.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pxr")

from pxr import Sdf, Usd  # noqa: E402

from moneta.types import EntityState  # noqa: E402
from moneta.usd_target import _token_to_state  # noqa: E402


# ----------------------------------------------------------------------
# Synthetic prim authoring helpers (test fixtures only — never run by
# the substrate).
# ----------------------------------------------------------------------


def _author_typed_prim(
    layer: "Sdf.Layer", path: str, *, prior_token: str
) -> None:
    """Author a typed MonetaMemory prim with priorState as a token."""
    with Sdf.ChangeBlock():
        prim_spec = Sdf.CreatePrimInLayer(layer, Sdf.Path(path))
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "MonetaMemory"
        attr = Sdf.AttributeSpec(
            prim_spec, "priorState", Sdf.ValueTypeNames.Token
        )
        attr.default = prior_token


def _author_typeless_prim(
    layer: "Sdf.Layer", path: str, *, prior_int: int
) -> None:
    """Author a legacy typeless ``def`` prim with prior_state as an int."""
    with Sdf.ChangeBlock():
        prim_spec = Sdf.CreatePrimInLayer(layer, Sdf.Path(path))
        prim_spec.specifier = Sdf.SpecifierDef
        # NO typeName set — typeless legacy prim, the pre-v1.2.0 shape.
        attr = Sdf.AttributeSpec(
            prim_spec, "prior_state", Sdf.ValueTypeNames.Int
        )
        attr.default = prior_int


def _author_unknown_typed_prim(
    layer: "Sdf.Layer", path: str
) -> None:
    """Author a prim with a typeName that isn't MonetaMemory or empty."""
    with Sdf.ChangeBlock():
        prim_spec = Sdf.CreatePrimInLayer(layer, Sdf.Path(path))
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "SomeOtherType"


# ----------------------------------------------------------------------
# The branching pattern under test
# ----------------------------------------------------------------------


def _read_priorstate(prim: "Usd.Prim") -> EntityState:
    """Read a memory prim's lifecycle state with branching on typeName.

    This is the consumer-side pattern any future read-back path
    implements. Currently lives in tests because the §3 audit confirmed
    no substrate-side USD reads exist.
    """
    type_name = prim.GetTypeName()
    if type_name == "MonetaMemory":
        token = prim.GetAttribute("priorState").Get()
        return _token_to_state(token)
    elif type_name == "":
        legacy = prim.GetAttribute("prior_state").Get()
        return EntityState(legacy)
    else:
        raise ValueError(
            f"unknown prim type {type_name!r} at {prim.GetPath()}"
        )


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


class TestReadPathBranching:
    """Three cases per handoff §8.3 — all exercise the same
    ``_read_priorstate`` helper but against different on-disk shapes.
    """

    def test_typed_prim_resolves_to_correct_state(self) -> None:
        layer = Sdf.Layer.CreateAnonymous("typed.usda")
        _author_typed_prim(
            layer, "/Memory_typed", prior_token="staged_for_sync"
        )
        stage = Usd.Stage.Open(layer)

        prim = stage.GetPrimAtPath("/Memory_typed")
        assert prim.IsValid()
        assert prim.GetTypeName() == "MonetaMemory"
        assert _read_priorstate(prim) == EntityState.STAGED_FOR_SYNC

    def test_typeless_legacy_prim_resolves_to_correct_state(
        self,
    ) -> None:
        layer = Sdf.Layer.CreateAnonymous("typeless.usda")
        _author_typeless_prim(
            layer,
            "/Memory_legacy",
            prior_int=int(EntityState.CONSOLIDATED),
        )
        stage = Usd.Stage.Open(layer)

        prim = stage.GetPrimAtPath("/Memory_legacy")
        assert prim.IsValid()
        assert prim.GetTypeName() == "", (
            f"expected typeless (empty typeName), got "
            f"{prim.GetTypeName()!r}"
        )
        assert _read_priorstate(prim) == EntityState.CONSOLIDATED

    def test_unknown_typename_raises(self) -> None:
        layer = Sdf.Layer.CreateAnonymous("unknown.usda")
        _author_unknown_typed_prim(layer, "/Memory_unknown")
        stage = Usd.Stage.Open(layer)

        prim = stage.GetPrimAtPath("/Memory_unknown")
        assert prim.IsValid()
        assert prim.GetTypeName() == "SomeOtherType"
        with pytest.raises(ValueError, match="unknown prim type"):
            _read_priorstate(prim)
