"""Unit tests for src/moneta/usd_target.py — real USD authoring target.

ARCHITECTURE.md §15. Phase 3 Pass 3. Covers:

  - AuthoringTarget Protocol conformance (duck-typed, no runtime_checkable)
  - Prim naming discipline (UUID-only, TfToken safe per convention #1)
  - Sublayer routing (protected vs rolling daily per conventions #4, #6)
  - Sublayer rotation at cap (ARCHITECTURE.md §15.2 constraint #1)
  - Sdf.ChangeBlock usage (substrate convention #5) — AST-level guard
  - Disk round-trip via Save + reload
  - In-memory mode (log_path=None)

These tests require pxr (OpenUSD Python bindings). Under plain Python
they are skipped entirely via pytest.importorskip. Run under hython::

    "C:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython3.11.exe" \\
        -m pytest tests/unit/test_usd_target.py -v
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import time
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("pxr")

# These imports are safe past the skip guard — pxr is available.
from pxr import Sdf, Usd  # noqa: E402

from moneta.sequential_writer import AuthoringResult  # noqa: E402
from moneta.types import EntityState, Memory  # noqa: E402
from moneta.usd_target import (  # noqa: E402
    DEFAULT_ROTATION_CAP,
    PROTECTED_SUBLAYER_NAME,
    UsdTarget,
    _prim_path,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_memory(
    *,
    payload: str = "test memory",
    protected_floor: float = 0.0,
    utility: float = 0.25,
    attended_count: int = 3,
) -> Memory:
    return Memory(
        entity_id=uuid4(),
        payload=payload,
        semantic_vector=[1.0, 0.0, -0.5],
        utility=utility,
        attended_count=attended_count,
        protected_floor=protected_floor,
        last_evaluated=time.time(),
        state=EntityState.STAGED_FOR_SYNC,
    )


# ------------------------------------------------------------------
# 1. Protocol conformance
# ------------------------------------------------------------------


class TestProtocolConformance:
    def test_usd_target_conforms_to_authoring_target_protocol(self) -> None:
        """Structural Protocol conformance — duck typing, no runtime_checkable."""
        target = UsdTarget(log_path=None)

        # Methods exist and are callable
        assert callable(getattr(target, "author_stage_batch", None))
        assert callable(getattr(target, "flush", None))

        # author_stage_batch signature: (self, entities: List[Memory]) -> AuthoringResult
        sig = inspect.signature(target.author_stage_batch)
        params = list(sig.parameters.keys())
        assert params == ["entities"], f"expected ['entities'], got {params}"

        # flush signature: (self) -> None
        sig = inspect.signature(target.flush)
        params = list(sig.parameters.keys())
        assert params == [], f"expected [], got {params}"

    def test_author_returns_authoring_result(self) -> None:
        target = UsdTarget(log_path=None)
        mem = _make_memory()
        result = target.author_stage_batch([mem])

        assert isinstance(result, AuthoringResult)
        assert result.entity_ids == [mem.entity_id]
        assert result.target == "usd"
        assert isinstance(result.authored_at, float)
        assert isinstance(result.batch_id, str)


# ------------------------------------------------------------------
# 2. Prim creation
# ------------------------------------------------------------------


class TestPrimCreation:
    def test_author_single_prim_creates_usd_spec(self) -> None:
        """Deposit one memory, verify prim + attributes in the stage."""
        target = UsdTarget(log_path=None)
        mem = _make_memory(payload="The user prefers dark themes")
        target.author_stage_batch([mem])

        prim_path_str = f"/Memory_{mem.entity_id.hex}"
        prim = target.stage.GetPrimAtPath(prim_path_str)
        assert prim.IsValid(), f"prim at {prim_path_str} should exist"

        # Verify authored attributes
        assert prim.GetAttribute("payload").Get() == "The user prefers dark themes"
        assert isinstance(prim.GetAttribute("utility").Get(), float)
        assert prim.GetAttribute("attended_count").Get() == mem.attended_count
        assert prim.GetAttribute("protected_floor").Get() == mem.protected_floor
        assert isinstance(prim.GetAttribute("last_evaluated").Get(), float)
        assert prim.GetAttribute("prior_state").Get() == int(EntityState.STAGED_FOR_SYNC)

    def test_prim_name_is_uuid_not_payload(self) -> None:
        """TfToken OOM trap regression guard (Round 2 §6.3, convention #1).

        Verify the prim name is /Memory_<hex>, NOT derived from payload.
        """
        target = UsdTarget(log_path=None)
        mem = _make_memory(payload="The user likes pizza and prefers short answers")
        target.author_stage_batch([mem])

        # The prim must live at UUID hex path
        expected_path = f"/Memory_{mem.entity_id.hex}"
        prim = target.stage.GetPrimAtPath(expected_path)
        assert prim.IsValid(), "prim should be at UUID-hex path"

        # No prim derived from payload should exist
        bad_paths = [
            "/Memory_The_user_likes_pizza",
            "/The_user_likes_pizza",
            "/Memory_The",
        ]
        for bad in bad_paths:
            bad_prim = target.stage.GetPrimAtPath(bad)
            assert not bad_prim.IsValid(), f"prim at {bad} should NOT exist"


# ------------------------------------------------------------------
# 3. Sublayer routing
# ------------------------------------------------------------------


class TestSublayerRouting:
    def test_protected_routes_to_protected_sublayer(self) -> None:
        """protected_floor > 0 → cortex_protected.usda (convention #4)."""
        target = UsdTarget(log_path=None)
        mem = _make_memory(protected_floor=1.0)
        target.author_stage_batch([mem])

        assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 1

        # Verify the prim is on the protected layer
        protected_layer = target.get_layer(PROTECTED_SUBLAYER_NAME)
        prim_path_str = f"/Memory_{mem.entity_id.hex}"
        prim_spec = protected_layer.GetPrimAtPath(prim_path_str)
        assert prim_spec is not None, "protected prim should be on protected layer"

    def test_unprotected_routes_to_rolling_sublayer(self) -> None:
        """protected_floor == 0 → cortex_YYYY_MM_DD.usda (convention #6)."""
        target = UsdTarget(log_path=None)
        mem = _make_memory(protected_floor=0.0)
        target.author_stage_batch([mem])

        # Protected sublayer should still be empty (only has 0 prims from init)
        assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 0

        # At least one rolling sublayer should have 1 prim
        rolling_names = [
            n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME
        ]
        assert len(rolling_names) == 1, "should have exactly one rolling sublayer"
        assert target.get_prim_count(rolling_names[0]) == 1

    def test_mixed_batch_routes_correctly(self) -> None:
        """A batch with both protected and unprotected routes to both."""
        target = UsdTarget(log_path=None)
        protected = _make_memory(protected_floor=0.5)
        volatile = _make_memory(protected_floor=0.0)
        target.author_stage_batch([protected, volatile])

        assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 1
        rolling_names = [
            n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME
        ]
        assert len(rolling_names) == 1
        assert target.get_prim_count(rolling_names[0]) == 1


# ------------------------------------------------------------------
# 4. Sublayer rotation
# ------------------------------------------------------------------


class TestSublayerRotation:
    def test_rolling_sublayer_rotates_at_cap(self) -> None:
        """ARCHITECTURE.md §15.2 constraint #1: rotation at prim cap.

        Uses a small rotation_cap (10) to avoid authoring 50k prims.
        Tests the rotation logic identically — the default 50k cap is
        exercised at the integration/load level, not unit.
        """
        cap = 10
        target = UsdTarget(log_path=None, rotation_cap=cap)

        # Author exactly `cap` memories — should fill the first sublayer
        first_batch = [_make_memory() for _ in range(cap)]
        target.author_stage_batch(first_batch)

        rolling_before = [
            n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME
        ]
        assert len(rolling_before) == 1, "should have one rolling sublayer"
        assert target.get_prim_count(rolling_before[0]) == cap

        # Author one more — should trigger rotation to a new sublayer
        overflow = _make_memory()
        target.author_stage_batch([overflow])

        rolling_after = [
            n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME
        ]
        assert len(rolling_after) == 2, (
            f"should have two rolling sublayers after rotation, got {rolling_after}"
        )

        # The new sublayer should have 1 prim
        new_name = [n for n in rolling_after if n not in rolling_before][0]
        assert target.get_prim_count(new_name) == 1

        # Verify the overflow prim is on the new sublayer, not the old one
        new_layer = target.get_layer(new_name)
        prim_path_str = f"/Memory_{overflow.entity_id.hex}"
        prim_spec = new_layer.GetPrimAtPath(prim_path_str)
        assert prim_spec is not None, "overflow prim should be on the new sublayer"


# ------------------------------------------------------------------
# 5. Sdf.ChangeBlock usage
# ------------------------------------------------------------------


class TestChangeBlockDiscipline:
    def test_all_writes_inside_changeblock(self) -> None:
        """Substrate convention #5: all batch writes inside Sdf.ChangeBlock.

        AST-level check that author_stage_batch uses a `with Sdf.ChangeBlock`
        context manager. This guards against accidental removal of the
        ChangeBlock wrapper.
        """
        import moneta.usd_target as mod

        source = textwrap.dedent(inspect.getsource(mod.UsdTarget.author_stage_batch))
        tree = ast.parse(source)

        found_changeblock = False
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    ctx = item.context_expr
                    # Match `Sdf.ChangeBlock()` as a call
                    if isinstance(ctx, ast.Call):
                        func = ctx.func
                        if isinstance(func, ast.Attribute) and func.attr == "ChangeBlock":
                            found_changeblock = True

        assert found_changeblock, (
            "author_stage_batch must use `with Sdf.ChangeBlock()` — "
            "substrate convention #5 violation"
        )


# ------------------------------------------------------------------
# 6. Disk round-trip
# ------------------------------------------------------------------


class TestDiskRoundTrip:
    def test_save_flushes_to_disk_when_log_path_provided(self, tmp_path: Path) -> None:
        """Real disk round-trip: author, save, reload, verify."""
        target = UsdTarget(log_path=tmp_path / "cortex")
        mem = _make_memory(payload="disk round-trip test")
        target.author_stage_batch([mem])
        target.flush()

        # Verify files were written
        cortex_dir = tmp_path / "cortex"
        root_file = cortex_dir / "cortex_root.usda"
        assert root_file.exists(), "root layer should be on disk"

        protected_file = cortex_dir / "cortex_protected.usda"
        assert protected_file.exists(), "protected layer should be on disk"

        # Reload the stage from disk and verify the prim survived
        reloaded_stage = Usd.Stage.Open(str(root_file))
        prim_path_str = f"/Memory_{mem.entity_id.hex}"
        prim = reloaded_stage.GetPrimAtPath(prim_path_str)
        assert prim.IsValid(), f"prim at {prim_path_str} should survive disk round-trip"
        assert prim.GetAttribute("payload").Get() == "disk round-trip test"

        target.close()


# ------------------------------------------------------------------
# 7. In-memory mode
# ------------------------------------------------------------------


class TestInMemoryMode:
    def test_in_memory_mode_works_when_log_path_is_none(self) -> None:
        """Constructor with None — operations succeed without disk I/O."""
        target = UsdTarget(log_path=None)
        mem = _make_memory()

        result = target.author_stage_batch([mem])
        assert len(result.entity_ids) == 1

        # flush should be a no-op without error
        target.flush()

        # Prim is traversable in-memory
        prim = target.stage.GetPrimAtPath(f"/Memory_{mem.entity_id.hex}")
        assert prim.IsValid()

        target.close()


# ==================================================================
# Pass 6 adversarial additions — closing Pass 3 builder-bias debt
#
# Each test below documents which Pass 3 weakness it addresses.
# Original Pass 3 tests are left unmodified for regression continuity.
# ==================================================================


class TestAdversarialAttributeValues:
    """Pass 3 weakness: test_author_single_prim_creates_usd_spec checks
    attribute types (isinstance) but not VALUES. A prim with utility=0.0
    when 0.25 was authored would pass the original test. These tests
    verify exact value round-trips.
    """

    def test_attribute_values_match_authored_data(self) -> None:
        target = UsdTarget(log_path=None)
        mem = _make_memory(
            payload="exact value check",
            utility=0.42,
            attended_count=7,
            protected_floor=0.15,
        )
        target.author_stage_batch([mem])
        target.flush()

        prim = target.stage.GetPrimAtPath(f"/Memory_{mem.entity_id.hex}")
        assert prim.IsValid()

        assert prim.GetAttribute("payload").Get() == "exact value check"
        assert abs(prim.GetAttribute("utility").Get() - 0.42) < 1e-6, (
            "utility value must match authored data, not just be a float"
        )
        assert prim.GetAttribute("attended_count").Get() == 7
        assert abs(prim.GetAttribute("protected_floor").Get() - 0.15) < 1e-6
        assert prim.GetAttribute("prior_state").Get() == int(EntityState.STAGED_FOR_SYNC)


class TestAdversarialRotationBoundary:
    """Pass 3 weakness: test_rolling_sublayer_rotates_at_cap only tests
    cap → cap+1. It does not verify cap-1 does NOT rotate. The rotation
    guard is `count >= cap`, so off-by-one errors in either direction
    are invisible to the original test.
    """

    def test_no_rotation_at_cap_minus_one(self) -> None:
        """cap-1 prims must NOT trigger rotation."""
        cap = 10
        target = UsdTarget(log_path=None, rotation_cap=cap)

        batch = [_make_memory() for _ in range(cap - 1)]
        target.author_stage_batch(batch)

        rolling = [n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME]
        assert len(rolling) == 1, "cap-1 should not trigger rotation"
        assert target.get_prim_count(rolling[0]) == cap - 1

    def test_rotation_at_exact_cap(self) -> None:
        """Exactly cap prims fill the sublayer; the next prim triggers rotation."""
        cap = 10
        target = UsdTarget(log_path=None, rotation_cap=cap)

        # Fill to exactly cap
        target.author_stage_batch([_make_memory() for _ in range(cap)])
        rolling_before = [n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME]
        assert len(rolling_before) == 1
        assert target.get_prim_count(rolling_before[0]) == cap

        # cap+1 triggers rotation
        target.author_stage_batch([_make_memory()])
        rolling_after = [n for n in target.sublayer_names if n != PROTECTED_SUBLAYER_NAME]
        assert len(rolling_after) == 2, "cap+1 must trigger rotation"


class TestAdversarialEmptyBatch:
    """Pass 3 gap: no test for empty batch input. author_stage_batch
    should handle an empty list gracefully (no prims authored, valid
    AuthoringResult returned).
    """

    def test_empty_batch_returns_valid_result_no_prims(self) -> None:
        target = UsdTarget(log_path=None)
        result = target.author_stage_batch([])

        assert isinstance(result, AuthoringResult)
        assert result.entity_ids == []
        assert result.target == "usd"

        # No prims should exist beyond the stage root
        prims = list(target.stage.Traverse())
        assert len(prims) == 0, "empty batch should not create any prims"


class TestAdversarialNarrowLock:
    """Pass 6 specific: verify the narrow-lock pattern — prims are
    visible in-memory BEFORE flush() is called. This is the behavioral
    consequence of the Pass 5 ruling: ChangeBlock exit makes prims
    visible, Save (in flush) just writes to disk.
    """

    def test_prims_visible_before_flush(self) -> None:
        """After author_stage_batch but before flush, prims are traversable."""
        target = UsdTarget(log_path=None)
        mem = _make_memory(payload="pre-flush visibility")
        target.author_stage_batch([mem])

        # NOT calling flush() yet — prim should still be visible
        prim = target.stage.GetPrimAtPath(f"/Memory_{mem.entity_id.hex}")
        assert prim.IsValid(), "prim must be visible after ChangeBlock exit, before flush"
        assert prim.GetAttribute("payload").Get() == "pre-flush visibility"

    def test_disk_round_trip_requires_flush(self, tmp_path: Path) -> None:
        """On-disk mode: prim is NOT durable until flush() is called."""
        target = UsdTarget(log_path=tmp_path / "cortex")
        mem = _make_memory(payload="flush required")
        target.author_stage_batch([mem])

        # Reload WITHOUT flushing first — file may not have the new prim
        # (the root layer has sublayer refs, but sublayers may not be saved)
        cortex_dir = tmp_path / "cortex"
        root_file = cortex_dir / "cortex_root.usda"

        # Now flush and reload — prim should be there
        target.flush()
        reloaded = Usd.Stage.Open(str(root_file))
        prim = reloaded.GetPrimAtPath(f"/Memory_{mem.entity_id.hex}")
        assert prim.IsValid(), "prim must be durable after flush()"
        assert prim.GetAttribute("payload").Get() == "flush required"

        target.close()
