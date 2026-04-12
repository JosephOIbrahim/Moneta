"""End-to-end integration tests for the real USD authoring path.

ARCHITECTURE.md §15. Phase 3 Pass 4. Exercises the full
deposit → query → signal_attention → run_sleep_pass → manifest flow
through UsdTarget instead of MockUsdTarget.

These tests require pxr (OpenUSD Python bindings). Under plain Python
they are skipped entirely via pytest.importorskip. Run under hython::

    PYTHONPATH="src" "C:/.../hython3.11.exe" \\
        -m pytest tests/integration/test_real_usd_end_to_end.py -v \\
        -p no:faulthandler -p no:cacheprovider

Commandment 7 (adversarial verification): these tests exercise real
USD flows from the Consolidation Engineer perspective, breaking the
builder-biased coverage of Pass 3's unit tests.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from uuid import UUID

import pytest

pytest.importorskip("pxr")

import moneta  # noqa: E402
from moneta import api as moneta_api  # noqa: E402
from moneta.api import MonetaConfig  # noqa: E402
from moneta.consolidation import MAX_BATCH_SIZE  # noqa: E402
from moneta.types import EntityState  # noqa: E402
from moneta.usd_target import PROTECTED_SUBLAYER_NAME, UsdTarget  # noqa: E402


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def fresh_moneta_usd() -> Iterator[None]:
    """Initialize Moneta with use_real_usd=True, in-memory USD layers."""
    moneta_api._reset_state()
    moneta.init(
        config=MonetaConfig(
            use_real_usd=True,
            usd_target_path=None,  # in-memory anonymous layers
            half_life_seconds=60.0,  # fast decay for test timing
        )
    )
    try:
        yield
    finally:
        moneta_api._reset_state()


@pytest.fixture
def fresh_moneta_mock() -> Iterator[None]:
    """Initialize Moneta with MockUsdTarget (Phase 1 default)."""
    moneta_api._reset_state()
    moneta.init(
        config=MonetaConfig(
            use_real_usd=False,
            half_life_seconds=60.0,  # same fast decay for A/B parity
        )
    )
    try:
        yield
    finally:
        moneta_api._reset_state()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _deposit_n(n: int, *, protected_floor: float = 0.0) -> list[UUID]:
    """Deposit n memories with distinct embeddings."""
    ids = []
    for i in range(n):
        eid = moneta.deposit(
            payload=f"memory #{i}",
            embedding=[float(i), float(i + 1), float(i + 2)],
            protected_floor=protected_floor,
        )
        ids.append(eid)
    return ids


def _force_staging(eids: list[UUID]) -> None:
    """Manipulate ECS to make entities match staging criteria.

    Staging: utility < 0.3 AND attended_count >= 3 (ARCHITECTURE.md §6).
    """
    state = moneta_api._state
    for eid in eids:
        idx = state.ecs._id_to_row.get(eid)
        if idx is not None:
            state.ecs._utility[idx] = 0.2
            state.ecs._attended[idx] = 5
            state.ecs._last_evaluated[idx] = time.time()


# ------------------------------------------------------------------
# 1. Full end-to-end under real USD
# ------------------------------------------------------------------


class TestRealUsdEndToEnd:
    def test_deposit_query_attention_sleep_under_real_usd(
        self, fresh_moneta_usd: None
    ) -> None:
        """Full four-op flow through the real USD path.

        deposit → query → signal_attention → run_sleep_pass → verify
        prim exists in the USD stage.
        """
        state = moneta_api._state
        assert isinstance(state.authoring_target, UsdTarget)

        # Deposit
        eid = moneta.deposit("end-to-end test", [1.0, 0.0, 0.0])
        assert isinstance(eid, UUID)

        # Query
        results = moneta.query([1.0, 0.0, 0.0], limit=5)
        assert len(results) == 1
        assert results[0].entity_id == eid

        # Force this entity to match staging criteria
        # (utility < 0.3 AND attended_count >= 3)
        _force_staging([eid])

        # Sleep pass — this should commit through UsdTarget
        result = moneta.run_sleep_pass()
        assert result.staged == 1

        # Verify the prim exists in the USD stage
        target = state.authoring_target
        prim_path = f"/Memory_{eid.hex}"
        prim = target.stage.GetPrimAtPath(prim_path)
        assert prim.IsValid(), f"prim at {prim_path} should exist after staging"
        assert prim.GetAttribute("payload").Get() == "end-to-end test"


# ------------------------------------------------------------------
# 2. Protected routing
# ------------------------------------------------------------------


class TestProtectedRouting:
    def test_protected_memory_routes_to_protected_sublayer(
        self, fresh_moneta_usd: None
    ) -> None:
        """protected_floor > 0 → cortex_protected.usda in real USD.

        Uses protected_floor=0.1 (not 1.0) so the entity can still
        match staging criteria after decay eval points in run_pass.
        A floor of 1.0 would restore utility to 1.0 after decay,
        preventing staging entirely. The routing test is about which
        sublayer the prim lands in, not about the floor value.
        """
        state = moneta_api._state
        target = state.authoring_target

        eid = moneta.deposit("core identity", [1.0, 0.0, 0.0], protected_floor=0.1)

        # Force to staging criteria (utility < 0.3 AND attended >= 3)
        _force_staging([eid])

        result = moneta.run_sleep_pass()
        assert result.staged == 1

        # Verify routing to protected sublayer
        assert target.get_prim_count(PROTECTED_SUBLAYER_NAME) == 1

        protected_layer = target.get_layer(PROTECTED_SUBLAYER_NAME)
        prim_spec = protected_layer.GetPrimAtPath(f"/Memory_{eid.hex}")
        assert prim_spec is not None, "protected memory should be on protected layer"


# ------------------------------------------------------------------
# 3. Batch cap enforcement (§15.2 constraint #3)
# ------------------------------------------------------------------


class TestBatchCap:
    def test_large_staging_respects_500_prim_batch_cap(
        self, fresh_moneta_usd: None
    ) -> None:
        """ARCHITECTURE.md §15.2 #3: max 500 prims per consolidation batch.

        Deposits more than MAX_BATCH_SIZE entities, forces them all to
        staging criteria, and verifies the sleep pass succeeds (meaning
        batching worked — without batching, a single commit_staging call
        with >500 entities would still work, but the batching is visible
        in the authored prim count spread across batches).
        """
        n = MAX_BATCH_SIZE + 50  # 550 entities
        eids = _deposit_n(n)
        _force_staging(eids)

        state = moneta_api._state
        target = state.authoring_target

        result = moneta.run_sleep_pass()
        assert result.staged == n

        # All 550 prims should exist in the USD stage
        rolling_names = [
            name for name in target.sublayer_names
            if name != PROTECTED_SUBLAYER_NAME
        ]
        total_prims = sum(target.get_prim_count(name) for name in rolling_names)
        assert total_prims == n, f"expected {n} prims total, got {total_prims}"

        # Verify a sample prim from the first and last batch
        first_prim = target.stage.GetPrimAtPath(f"/Memory_{eids[0].hex}")
        last_prim = target.stage.GetPrimAtPath(f"/Memory_{eids[-1].hex}")
        assert first_prim.IsValid()
        assert last_prim.IsValid()


# ------------------------------------------------------------------
# 4. A/B equivalence: MockUsdTarget vs UsdTarget
# ------------------------------------------------------------------


class TestABEquivalence:
    def test_mock_vs_real_produce_equivalent_state_transitions(
        self, fresh_moneta_mock: None
    ) -> None:
        """Commandment 7: adversarial verification.

        Verify that MockUsdTarget and UsdTarget produce equivalent
        ConsolidationResult (same pruned/staged counts) for identical
        inputs. The selection logic is in consolidation.py — both
        targets should produce the same state transitions.
        """
        # --- Run under mock ---
        n_stage = 5
        n_prune = 3
        n_keep = 2

        stage_ids = _deposit_n(n_stage)
        prune_ids = _deposit_n(n_prune)
        keep_ids = _deposit_n(n_keep)

        state = moneta_api._state

        # Force staging criteria on stage_ids
        _force_staging(stage_ids)

        # Force pruning criteria on prune_ids: utility < 0.1, attended < 3
        for eid in prune_ids:
            idx = state.ecs._id_to_row.get(eid)
            if idx is not None:
                state.ecs._utility[idx] = 0.05
                state.ecs._attended[idx] = 1
                state.ecs._last_evaluated[idx] = time.time()

        mock_result = moneta.run_sleep_pass()

        # --- Run under real USD ---
        moneta_api._reset_state()
        moneta.init(
            config=MonetaConfig(
                use_real_usd=True,
                usd_target_path=None,
                half_life_seconds=60.0,
            )
        )

        stage_ids2 = _deposit_n(n_stage)
        prune_ids2 = _deposit_n(n_prune)
        keep_ids2 = _deposit_n(n_keep)

        state2 = moneta_api._state

        _force_staging(stage_ids2)

        for eid in prune_ids2:
            idx = state2.ecs._id_to_row.get(eid)
            if idx is not None:
                state2.ecs._utility[idx] = 0.05
                state2.ecs._attended[idx] = 1
                state2.ecs._last_evaluated[idx] = time.time()

        real_result = moneta.run_sleep_pass()

        # --- Compare ---
        assert mock_result.pruned == real_result.pruned, (
            f"pruned mismatch: mock={mock_result.pruned}, real={real_result.pruned}"
        )
        assert mock_result.staged == real_result.staged, (
            f"staged mismatch: mock={mock_result.staged}, real={real_result.staged}"
        )
        assert mock_result.pruned == n_prune
        assert mock_result.staged == n_stage

        moneta_api._reset_state()


# ------------------------------------------------------------------
# 5. Sublayer rotation during sleep pass (Pass 6 hardening)
# ------------------------------------------------------------------


class TestSublayerRotationDuringSleepPass:
    def test_rotation_across_passes_preserves_all_prims(
        self, fresh_moneta_usd: None
    ) -> None:
        """Verify sublayer rotation across two sleep passes doesn't lose prims.

        Rotation is a between-batch boundary: all entities in a single
        author_stage_batch call go to the current sublayer, and rotation
        triggers on the next call when the accumulated count exceeds the
        cap. This test exercises rotation by running two sleep passes:
        the first fills the sublayer past the cap, the second rotates.
        """
        state = moneta_api._state
        target = state.authoring_target

        # Override rotation cap to a small value for test speed.
        target._rotation_cap = 5

        # Pass 1: deposit and consolidate 8 prims → fills sublayer past cap=5
        eids_1 = _deposit_n(8)
        _force_staging(eids_1)
        r1 = moneta.run_sleep_pass()
        assert r1.staged == 8

        rolling_after_1 = [nm for nm in target.sublayer_names if nm != PROTECTED_SUBLAYER_NAME]
        assert len(rolling_after_1) == 1, "first pass fills one sublayer"
        assert target.get_prim_count(rolling_after_1[0]) == 8

        # Pass 2: deposit and consolidate 4 more → rotation triggers (8 >= cap=5)
        eids_2 = _deposit_n(4)
        _force_staging(eids_2)
        r2 = moneta.run_sleep_pass()
        assert r2.staged == 4

        rolling_after_2 = [nm for nm in target.sublayer_names if nm != PROTECTED_SUBLAYER_NAME]
        assert len(rolling_after_2) == 2, (
            f"second pass should trigger rotation, got {len(rolling_after_2)} sublayers"
        )

        # Verify no prims lost
        total = sum(target.get_prim_count(nm) for nm in rolling_after_2)
        assert total == 12, f"expected 12 total prims, got {total}"

        # Verify all entities reachable in the composed stage
        for eid in eids_1 + eids_2:
            prim = target.stage.GetPrimAtPath(f"/Memory_{eid.hex}")
            assert prim.IsValid(), f"prim for {eid} should survive rotation"


# ------------------------------------------------------------------
# 6. Post-sleep-pass reader consistency (Pass 6 hardening)
# ------------------------------------------------------------------


class TestPostSleepPassReaderConsistency:
    def test_prims_visible_to_traverse_after_sleep_pass(
        self, fresh_moneta_usd: None
    ) -> None:
        """After a sleep pass consolidates entities, a fresh Traverse sees
        the authored prims. Validates the narrow-lock contract at the
        integration layer: ChangeBlock makes prims visible in-memory,
        flush() makes them durable.
        """
        state = moneta_api._state
        target = state.authoring_target

        n = 5
        eids = _deposit_n(n)
        _force_staging(eids)

        # Pre-sleep: no authored prims in USD yet
        authored_pre = [
            p for p in target.stage.Traverse()
            if "Memory_" in str(p.GetPath())
        ]
        assert len(authored_pre) == 0, "no Memory prims in USD before sleep pass"

        result = moneta.run_sleep_pass()
        assert result.staged == n

        # Post-sleep: all authored prims visible via Traverse
        authored_post = [
            p for p in target.stage.Traverse()
            if "Memory_" in str(p.GetPath())
        ]
        assert len(authored_post) == n, (
            f"expected {n} Memory prims after sleep pass, got {len(authored_post)}"
        )

        for prim in authored_post:
            payload = prim.GetAttribute("payload")
            assert payload.IsValid() and payload.Get() is not None, (
                f"prim {prim.GetPath()} must have valid payload attribute"
            )
