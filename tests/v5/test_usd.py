"""USD adapters: composed policy must equal the plain control; projections are derived."""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("pxr")

from pxr import Sdf, Usd  # noqa: E402

from moneta.v5 import PlainPolicyResolver  # noqa: E402
from moneta.v5.usd import UsdPolicyResolver, author_policy_layers, project_generation  # noqa: E402

from .fixture import ORACLE, QUERY, T0, policy_spec  # noqa: E402


def _both(ids, directory=None):
    spec = policy_spec(ids)
    return PlainPolicyResolver(spec), UsdPolicyResolver.from_spec(spec, directory)


@pytest.mark.parametrize("on_disk", [False, True])
def test_usd_composition_equals_plain_control(world, tmp_path, on_disk):
    s, ids = world
    plain, usd = _both(ids, tmp_path / "policy" if on_disk else None)
    assert usd.contexts() == plain.contexts()
    for ctx in plain.contexts():
        a, b = plain.resolve(ctx), usd.resolve(ctx)
        assert a.semantic() == b.semantic(), ctx
        assert a.fingerprint == b.fingerprint, ctx


@pytest.mark.parametrize("context", sorted(ORACLE))
def test_recall_is_identical_under_either_resolver(world, context):
    s, ids = world
    plain, usd = _both(ids)
    s.use_policy(plain)
    a = s.recall(QUERY, 20, context=context, t=T0)
    s.use_policy(usd)
    b = s.recall(QUERY, 20, context=context, t=T0)
    assert [(i.memory.entity_id, i.score) for i in a.items] == [
        (i.memory.entity_id, i.score) for i in b.items
    ]
    assert a.generation == b.generation


def test_session_layer_is_an_ordinary_sublayer_stack(world, tmp_path):
    s, ids = world
    _, usd = _both(ids, tmp_path / "policy")
    stage = Usd.Stage.Open(usd.layer("projA.review"))
    stack = [
        dict(layer.customLayerData).get("monetaContext")
        for layer in stage.GetLayerStack(includeSessionLayers=False)
    ]
    assert stack == ["projA.review", "projA", "default"]
    # The session layer authors only the exclusion; scopes come from projA.
    attr = stage.GetPrimAtPath("/Policy").GetAttribute("includeScopes")
    assert sorted(attr.Get()) == ["projA", "projA.scratch", "shared"]
    assert usd.layer("projA.review").GetAttributeAtPath("/Policy.includeScopes") is None


def test_slot_prims_are_not_named_from_natural_language(world):
    s, ids = world
    _, usd = _both(ids)
    text = usd.layer("projB").ExportToString()
    assert "answer_style" in text  # as an attribute value...
    assert 'def "answer_style"' not in text  # ...never as a prim name


def test_editing_a_layer_on_disk_is_picked_up(world, tmp_path):
    s, ids = world
    directory = tmp_path / "policy"
    _, usd = _both(ids, directory)
    s.use_policy(usd)
    before = s.recall(QUERY, 20, context="projA", t=T0)
    # Another tool (a Solaris session, say) edits projA's layer file.
    other = Sdf.Layer.OpenAsAnonymous(str(usd.layer("projA").realPath))
    other.GetAttributeAtPath("/Policy.excludeScopes").default = []
    other.Export(usd.layer("projA").realPath)
    usd.reload()
    after = s.recall(QUERY, 20, context="projA", t=T0)
    assert ids["A3"] not in [i.memory.entity_id for i in before.items]
    assert ids["A3"] in [i.memory.entity_id for i in after.items]
    assert before.generation.policy_fingerprint != after.generation.policy_fingerprint


def test_from_directory_round_trip(world, tmp_path):
    s, ids = world
    plain, _ = _both(ids, tmp_path / "policy")
    loaded = UsdPolicyResolver.from_directory(tmp_path / "policy")
    for ctx in plain.contexts():
        assert loaded.resolve(ctx).fingerprint == plain.resolve(ctx).fingerprint


def test_projection_is_derived_and_rebuildable(world, tmp_path):
    s, ids = world
    first = project_generation(s, tmp_path / "proj", context="projA", t=T0)
    assert first["records"] == len(ORACLE["projA"])

    def prims(directory):
        stage = Usd.Stage.Open(str(directory / "cortex_root.usda"))
        found = {}
        for prim in stage.Traverse():
            if prim.GetTypeName() == "MonetaMemory":
                found[prim.GetName()] = prim.GetAttribute("payload").Get()
        return found, dict(stage.GetRootLayer().customLayerData)

    got, meta = prims(tmp_path / "proj")
    assert set(got) == {f"Memory_{ids[n].hex}" for n in ORACLE["projA"]}
    assert meta["monetaGenerationSeq"] == s.seq
    assert meta["monetaPolicyFingerprint"] == s.describe_context("projA").fingerprint

    shutil.rmtree(tmp_path / "proj")
    project_generation(s, tmp_path / "proj", context="projA", t=T0)
    assert prims(tmp_path / "proj")[0] == got

    with pytest.raises(FileExistsError):
        project_generation(s, tmp_path / "proj", context="projA", t=T0)


def test_author_policy_layers_rejects_bad_specs():
    with pytest.raises(ValueError):
        author_policy_layers({"a": {"parent": "b"}, "b": {"parent": "a"}})
    with pytest.raises(ValueError):
        author_policy_layers({"a": {"exclude_records": ["not-a-uuid"]}})
