"""USD reopen-first lifecycle (ce45), flush() failure reporting and Sdf
registry sharing. Disposable stores only.

Ported from Codex's isolated candidate ce45f133, prepared outside this
repository and not in its history (its
tests/unit/test_usd_target_reopen.py; REPAIR_REPORT.txt), which fixed rc1's
CreateNew-first open: rc1 reset the mirror's sublayer stack whenever a fresh
process reopened an existing store. Changes from the candidate:

- every Sdf stub also stubs ``Sdf.Layer.GetLoadedLayers`` (the
  registry-sharing scan) and ``Sdf.Layer.Find`` (the open's collision
  guard), which the target now calls before opening anything;
- the separate-process reopen follows this repo's nested-process rule
  (a4f2b0b): the parent's PYTHONPATH is inherited with the clone's src
  prepended, no ``-I``, and the child reports which moneta it imported. It
  also checks the protected count and prims, and resumes the rolling
  layer's persisted count;
- the gate's two conditions are pinned: flush() checks every ``Save()``
  (a False result and a raise) and reports failures as ``UsdSaveError``,
  and a layer another holder already loaded in this process (a LOP
  network) is detected and logged.

These use the interpreter's installed pxr (usd-core), never Houdini.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

pytest.importorskip("pxr")

from pxr import Sdf, Tf  # noqa: E402

import moneta.usd_target as usd_target  # noqa: E402
from moneta.types import EntityState, Memory  # noqa: E402
from moneta.usd_target import PROTECTED_SUBLAYER_NAME, UsdTarget  # noqa: E402

ROOT_NAME = "cortex_root.usda"
AUTHORED_AT = 1792152035.0  # 2026-10-16 12:00:35 UTC
ROLLING_NAME = "cortex_2026_10_16.usda"
SHARING = "Sdf registry sharing"
_LOGGER = "moneta.usd_target"


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usd_target, "time", SimpleNamespace(time=lambda: AUTHORED_AT))


def _memory(payload: str, *, protected: bool = False) -> Memory:
    return Memory(
        entity_id=uuid4(),
        payload=payload,
        semantic_vector=[1.0],
        utility=0.5,
        attended_count=2,
        protected_floor=0.5 if protected else 0.0,
        last_evaluated=AUTHORED_AT,
        state=EntityState.STAGED_FOR_SYNC,
    )


def _opinion(layer: Sdf.Layer, name: str, value: str) -> None:
    prim = Sdf.CreatePrimInLayer(layer, f"/{name}")
    prim.specifier = Sdf.SpecifierDef
    Sdf.AttributeSpec(prim, "sentinel", Sdf.ValueTypeNames.String).default = value


def _assert_uncached(store: Path) -> None:
    gc.collect()
    assert Sdf.Layer.Find(str(store / ROOT_NAME)) is None
    assert Sdf.Layer.Find(str(store / PROTECTED_SUBLAYER_NAME)) is None


def _sharing(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if SHARING in r.getMessage()]


def _seed_nonempty_store(store: Path) -> tuple[list[Memory], list[str], list[Sdf.LayerOffset]]:
    target = UsdTarget(store)
    memories = [
        _memory("protected-before-reopen", protected=True),
        _memory("rolling-before-reopen"),
    ]
    target.author_stage_batch(memories)
    root = target.stage.GetRootLayer()
    protected = target.get_layer(PROTECTED_SUBLAYER_NAME)
    root.customLayerData = {"sentinel": "root-metadata"}
    protected.customLayerData = {"sentinel": "protected-metadata"}
    _opinion(root, "RootOpinion", "root-opinion")
    _opinion(protected, "ProtectedOpinion", "protected-opinion")
    extra = Sdf.Layer.CreateNew(str(store / "external.usda"))
    _opinion(extra, "ExternalOpinion", "external-opinion")
    extra.Save()
    # Relative authored references and non-default offsets must survive as authored.
    paths = [Path(path).name for path in root.subLayerPaths] + ["external.usda"]
    root.subLayerPaths[:] = paths
    root.subLayerOffsets[0] = Sdf.LayerOffset(7.0, 2.0)
    root.subLayerOffsets[1] = Sdf.LayerOffset(3.0, 1.0)
    offsets = list(root.subLayerOffsets)
    target.flush()
    target.close()
    return memories, paths, offsets


def test_fresh_reopen_preserves_nonempty_opinions_stack_and_offsets_without_redeposit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = tmp_path / "store"
    memories, paths, offsets = _seed_nonempty_store(store)
    original = {path.name: path.read_bytes() for path in store.glob("*.usda")}
    for _ in range(3):
        _assert_uncached(store)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            target = UsdTarget(store)
        assert _sharing(caplog) == []  # an uncached reopen shares nothing
        assert list(target.stage.GetRootLayer().subLayerPaths) == paths
        assert list(target.stage.GetRootLayer().subLayerOffsets) == offsets
        assert target.stage.GetRootLayer().customLayerData == {"sentinel": "root-metadata"}
        assert target.get_layer(PROTECTED_SUBLAYER_NAME).customLayerData == {
            "sentinel": "protected-metadata"
        }
        assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 2
        for name, value in (
            ("RootOpinion", "root-opinion"),
            ("ProtectedOpinion", "protected-opinion"),
            ("ExternalOpinion", "external-opinion"),
        ):
            assert target.stage.GetPrimAtPath(f"/{name}").GetAttribute("sentinel").Get() == value
        for memory in memories:
            assert (
                target.stage.GetPrimAtPath(f"/Memory_{memory.entity_id.hex}")
                .GetAttribute("payload")
                .Get()
                == memory.payload
            )
        target.flush()
        assert {path.name: path.read_bytes() for path in store.glob("*.usda")} == original
        target.close()
        del target


def test_new_store_creates_root_and_protected_and_accepts_writes(tmp_path: Path) -> None:
    store = tmp_path / "absent" / "store"
    target = UsdTarget(store)
    assert (store / ROOT_NAME).is_file()
    assert (store / PROTECTED_SUBLAYER_NAME).is_file()
    assert list(target.stage.GetRootLayer().subLayerPaths) == [
        target.get_layer(PROTECTED_SUBLAYER_NAME).identifier
    ]
    memory = _memory("new-store-write", protected=True)
    target.author_stage_batch([memory])
    target.flush()
    assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 1
    target.close()


_CHILD = """
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import moneta
import moneta.usd_target as ut
from moneta.types import EntityState, Memory

store, expected = Path(sys.argv[1]), json.loads(sys.argv[2])
ut.time = SimpleNamespace(time=lambda: expected["authored_at"])
target = ut.UsdTarget(store)
root = target.stage.GetRootLayer()
protected = target.get_layer(ut.PROTECTED_SUBLAYER_NAME)
report = {
    "moneta": moneta.__file__,
    "paths": list(root.subLayerPaths),
    "protected_count": target.get_prim_count(ut.PROTECTED_SUBLAYER_NAME),
    "protected_prims": sorted(p.name for p in protected.rootPrims),
    "payloads": {
        h: target.stage.GetPrimAtPath("/Memory_" + h).GetAttribute("payload").Get()
        for h in expected["hexes"]
    },
}
more = Memory(
    entity_id=UUID(int=1),
    payload="authored-in-the-child",
    semantic_vector=[1.0],
    utility=0.5,
    attended_count=0,
    protected_floor=0.0,
    last_evaluated=expected["authored_at"],
    state=EntityState.STAGED_FOR_SYNC,
)
target.author_stage_batch([more])  # routes to the existing rolling layer; no flush
report["rolling_count"] = target.get_prim_count(expected["rolling"])
report["paths_after"] = list(root.subLayerPaths)
target.close()
print(json.dumps(report))
"""


def _norm(p: object) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def test_separate_process_reopen_keeps_stack_counts_and_protected_prims(
    tmp_path: Path, fixed_clock: None
) -> None:
    store = tmp_path / "separate-process"
    memories, paths, _ = _seed_nonempty_store(store)
    original = {path.name: path.read_bytes() for path in store.glob("*.usda")}
    protected_memory = memories[0]
    expected = {
        "authored_at": AUTHORED_AT,
        "rolling": ROLLING_NAME,
        "hexes": [memory.entity_id.hex for memory in memories],
    }
    # The nested-process rule (a4f2b0b): inherit the parent's import roots
    # with this clone's src first, and make the child say what it imported.
    src = Path(usd_target.__file__).resolve().parents[1]
    env = os.environ.copy()
    inherited = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    env["PYTHONPATH"] = os.pathsep.join([str(src), *inherited])
    result = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, str(store), json.dumps(expected)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert _norm(report["moneta"]) == _norm(src / "moneta" / "__init__.py")
    assert report["paths"] == paths
    assert report["paths_after"] == paths  # no duplicate stack entry
    assert report["protected_count"] == 2  # the protected memory + ProtectedOpinion
    assert report["protected_prims"] == sorted(
        [f"Memory_{protected_memory.entity_id.hex}", "ProtectedOpinion"]
    )
    assert report["payloads"] == {m.entity_id.hex: m.payload for m in memories}
    assert report["rolling_count"] == 2  # 1 persisted + 1 authored in the child
    assert {path.name: path.read_bytes() for path in store.glob("*.usda")} == original


def test_missing_protected_layer_preserves_existing_root_opinions(tmp_path: Path) -> None:
    root = Sdf.Layer.CreateNew(str(tmp_path / ROOT_NAME))
    _opinion(root, "RootOpinion", "keep-root")
    root.subLayerPaths[:] = [PROTECTED_SUBLAYER_NAME]
    root.Save()
    original_root = (tmp_path / ROOT_NAME).read_bytes()
    del root
    _assert_uncached(tmp_path)
    target = UsdTarget(tmp_path)
    assert list(target.stage.GetRootLayer().subLayerPaths) == [PROTECTED_SUBLAYER_NAME]
    assert target.stage.GetPrimAtPath("/RootOpinion").GetAttribute("sentinel").Get() == "keep-root"
    target.flush()
    assert (tmp_path / ROOT_NAME).read_bytes() == original_root
    assert (tmp_path / PROTECTED_SUBLAYER_NAME).is_file()
    target.close()


def test_missing_root_reuses_nonempty_protected_layer(tmp_path: Path) -> None:
    layer = Sdf.Layer.CreateNew(str(tmp_path / PROTECTED_SUBLAYER_NAME))
    _opinion(layer, "ProtectedOpinion", "keep-protected")
    layer.Save()
    original_protected = (tmp_path / PROTECTED_SUBLAYER_NAME).read_bytes()
    del layer
    _assert_uncached(tmp_path)
    target = UsdTarget(tmp_path)
    assert target.stage.GetPrimAtPath("/ProtectedOpinion").GetAttribute("sentinel").Get() == (
        "keep-protected"
    )
    assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 1
    target.flush()
    assert (tmp_path / PROTECTED_SUBLAYER_NAME).read_bytes() == original_protected
    target.close()


@pytest.mark.parametrize("filename", [ROOT_NAME, PROTECTED_SUBLAYER_NAME])
def test_unreadable_existing_layer_fails_without_replacing_bytes(
    tmp_path: Path,
    filename: str,
) -> None:
    if filename == PROTECTED_SUBLAYER_NAME:
        (tmp_path / ROOT_NAME).write_text('#usda 1.0\n\ndef "RootOpinion" {}\n')
    broken = tmp_path / filename
    original = b"unreadable existing USD -- retain these bytes\n"
    broken.write_bytes(original)
    with pytest.raises((Tf.ErrorException, RuntimeError)):
        UsdTarget(tmp_path)
    assert broken.read_bytes() == original


@pytest.mark.parametrize("open_error", [None, OSError("unreadable existing layer")])
def test_existing_open_none_or_exception_never_falls_back_to_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    open_error: OSError | None,
) -> None:
    (tmp_path / ROOT_NAME).write_bytes(b"existing layer sentinel")
    find = Mock(return_value=None)
    find_or_open = Mock(return_value=None, side_effect=open_error)
    create = Mock(side_effect=AssertionError("must not create an existing file"))
    monkeypatch.setattr(
        usd_target,
        "Sdf",
        SimpleNamespace(
            Layer=SimpleNamespace(
                GetLoadedLayers=Mock(return_value=[]),
                Find=find,
                FindOrOpen=find_or_open,
                CreateNew=create,
            )
        ),
    )
    with pytest.raises((RuntimeError, OSError), match="existing.*layer"):
        UsdTarget(tmp_path)
    find.assert_called_once_with(str(tmp_path / ROOT_NAME))
    find_or_open.assert_called_once_with(str(tmp_path / ROOT_NAME))
    create.assert_not_called()
    assert (tmp_path / ROOT_NAME).read_bytes() == b"existing layer sentinel"


def test_failed_new_layer_creation_is_not_returned_as_a_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        usd_target,
        "Sdf",
        SimpleNamespace(
            Layer=SimpleNamespace(
                GetLoadedLayers=Mock(return_value=[]),
                Find=Mock(return_value=None),
                CreateNew=Mock(return_value=None),
            )
        ),
    )
    with pytest.raises(RuntimeError, match="create USD layer"):
        UsdTarget(tmp_path)


def test_failed_stage_open_is_not_returned_as_a_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        usd_target, "Usd", SimpleNamespace(Stage=SimpleNamespace(Open=lambda _: None))
    )
    with pytest.raises(RuntimeError, match="open USD stage"):
        UsdTarget(tmp_path)


def test_reopen_with_cached_layers_does_not_duplicate_stack_entries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    first = UsdTarget(tmp_path)
    first.flush()
    original = list(first.stage.GetRootLayer().subLayerPaths)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        second = UsdTarget(tmp_path)
    assert list(second.stage.GetRootLayer().subLayerPaths) == original
    # Both of second's disk layers are first's: detected and logged.
    shared = [r.getMessage() for r in _sharing(caplog)]
    assert len(shared) == 2
    assert any(first.stage.GetRootLayer().identifier in m for m in shared)
    assert any(first.get_layer(PROTECTED_SUBLAYER_NAME).identifier in m for m in shared)
    second.close()
    first.close()


def _seed_rotated_store(store: Path) -> list[Memory]:
    target = UsdTarget(store, rotation_cap=2)
    memories = [_memory(f"before-{index}") for index in range(5)]
    target.author_stage_batch(memories[:2])
    target.author_stage_batch(memories[2:4])
    target.author_stage_batch(memories[4:])
    target.stage.GetRootLayer().subLayerOffsets[1] = Sdf.LayerOffset(4.0, 2.0)
    target.flush()
    target.close()
    return memories


def test_reopen_continues_latest_rotation_and_rotates_after_existing_count(
    tmp_path: Path, fixed_clock: None
) -> None:
    store = tmp_path / "rotated"
    memories = _seed_rotated_store(store)
    _assert_uncached(store)
    base = "cortex_2026_10_16"
    old_files = {name: (store / name).read_bytes() for name in (f"{base}.usda", f"{base}_001.usda")}
    target = UsdTarget(store, rotation_cap=2)
    original_stack = list(target.stage.GetRootLayer().subLayerPaths)
    original_offsets = list(target.stage.GetRootLayer().subLayerOffsets)
    continuing = _memory("after-reopen-fill")
    target.author_stage_batch([continuing])
    assert target.get_prim_count(f"{base}_002.usda") == 2
    assert len(target.get_layer(f"{base}_002.usda").rootPrims) == 2
    assert list(target.stage.GetRootLayer().subLayerPaths) == original_stack
    overflow = _memory("after-reopen-rotate")
    target.author_stage_batch([overflow])
    new_stack = list(target.stage.GetRootLayer().subLayerPaths)
    assert new_stack[0] == original_stack[0]
    assert Path(new_stack[1]).name == f"{base}_003.usda"
    assert new_stack[2:] == original_stack[1:]
    new_offsets = list(target.stage.GetRootLayer().subLayerOffsets)
    assert new_offsets[0] == original_offsets[0]
    assert new_offsets[2:] == original_offsets[1:]
    assert target.get_prim_count(f"{base}_003.usda") == 1
    assert len(set(new_stack)) == len(new_stack)
    target.flush()
    assert {name: (store / name).read_bytes() for name in old_files} == old_files
    target.close()
    del target
    _assert_uncached(store)
    reopened = UsdTarget(store, rotation_cap=2)
    for memory in [*memories, continuing, overflow]:
        assert (
            reopened.stage.GetPrimAtPath(f"/Memory_{memory.entity_id.hex}")
            .GetAttribute("payload")
            .Get()
            == memory.payload
        )
    reopened.close()


@pytest.mark.parametrize("cap", [0, -1])
def test_invalid_rotation_cap_fails_before_store_creation(tmp_path: Path, cap: int) -> None:
    store = tmp_path / "not-created"
    with pytest.raises(ValueError, match="rotation_cap"):
        UsdTarget(store, rotation_cap=cap)
    assert not store.exists()


# ------------------------------------------- gate condition: flush() checks Save()


class _UnsavableLayer:
    """One managed layer whose Save() reports failure by returning False
    (usd-core 26.5's own Save() raises instead, which the next test covers)."""

    identifier = "moneta-test:unsavable.usda"
    dirty = True

    def __init__(self) -> None:
        self.saves = 0

    def Save(self) -> bool:  # noqa: N802 - Sdf.Layer's name
        self.saves += 1
        return False


def test_flush_reports_a_save_that_returns_false(tmp_path: Path) -> None:
    target = UsdTarget(tmp_path)
    memory = _memory("saved-despite-a-failed-layer", protected=True)
    target.author_stage_batch([memory])
    bad = _UnsavableLayer()
    target._layers["unsavable.usda"] = bad  # white-box: one more managed layer
    with pytest.raises(usd_target.UsdSaveError) as info:
        target.flush()
    assert isinstance(info.value, RuntimeError)
    assert bad.saves == 1
    assert info.value.failures == {bad.identifier: "Save() returned False"}
    assert bad.identifier in str(info.value)
    # Every other layer was still saved: the failure is reported, not contagious.
    assert not target.get_layer(PROTECTED_SUBLAYER_NAME).dirty
    protected_text = (tmp_path / PROTECTED_SUBLAYER_NAME).read_text(encoding="utf-8")
    assert f"Memory_{memory.entity_id.hex}" in protected_text
    del target._layers["unsavable.usda"]
    target.close()


def test_flush_reports_a_save_that_raises_then_retries(tmp_path: Path) -> None:
    target = UsdTarget(tmp_path)
    memory = _memory("saved-on-retry", protected=True)
    target.author_stage_batch([memory])
    layer = target.get_layer(PROTECTED_SUBLAYER_NAME)
    protected = tmp_path / PROTECTED_SUBLAYER_NAME
    protected.unlink()
    protected.mkdir()  # a directory in the way: the layer's Save() raises
    with pytest.raises(usd_target.UsdSaveError) as info:
        target.flush()
    assert list(info.value.failures) == [layer.identifier]
    assert isinstance(info.value.__cause__, Tf.ErrorException)
    assert layer.dirty  # still pending, so the next flush retries it
    protected.rmdir()
    target.flush()
    assert not layer.dirty
    assert f"Memory_{memory.entity_id.hex}" in protected.read_text(encoding="utf-8")
    target.close()


# --------------------------------- gate condition: registry sharing is detected


def test_layer_another_holder_loaded_is_detected_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = tmp_path / "store"
    seed = UsdTarget(store)
    seed.flush()
    seed.close()
    del seed
    _assert_uncached(store)
    # A LOP network in this process has loaded the store's protected layer:
    # Sdf keeps one layer registry per process, so the identifier is taken.
    lop_held = Sdf.Layer.FindOrOpen(str(store / PROTECTED_SUBLAYER_NAME))
    assert lop_held is not None
    # A same-named layer from another directory is not this store's.
    elsewhere = Sdf.Layer.CreateNew(str(tmp_path / "elsewhere" / PROTECTED_SUBLAYER_NAME))
    assert elsewhere is not None
    with caplog.at_level(logging.ERROR, logger=_LOGGER):
        target = UsdTarget(store)
    shared = _sharing(caplog)
    assert len(shared) == 1 and shared[0].levelno == logging.ERROR
    assert lop_held.identifier in shared[0].getMessage()
    assert elsewhere.identifier not in shared[0].getMessage()
    # Detected and logged, not refused: Moneta authors into the very layer
    # the other holder sees.
    assert target.get_layer(PROTECTED_SUBLAYER_NAME) == lop_held
    memory = _memory("visible-to-the-other-holder", protected=True)
    target.author_stage_batch([memory])
    assert lop_held.GetPrimAtPath(f"/Memory_{memory.entity_id.hex}") is not None
    target.close()
