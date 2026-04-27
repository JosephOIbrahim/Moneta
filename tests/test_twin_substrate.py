"""Twin-Substrate regression test — handle isolation under disk-backed paths.

DEEP_THINK_BRIEF_substrate_handle.md §5.2 (Q2 audit method) and §6.2
(disk-backed paths primary). This is the truth condition for the singleton
surgery: two handles on different `storage_uri` values must produce
isolated state, including when both write through disk-backed substrate
resources.

The C++ ``Sdf.Layer`` registry is what makes this test load-bearing —
two handles pointing to the same physical USD path would silently share
the same ``Sdf.Layer`` C++ pointer, recreating the singleton beneath
Python's awareness. The disk-backed Mock target exercise verifies the
broader ``snapshot``/``WAL``/``authoring-log`` filesystem isolation;
the pxr-gated real-USD exercise verifies the C++ registry isolation
specifically.

Anonymous-mode coverage is Crucible's responsibility per §6.2 — it is
complementary, not substitute. This file does not contain anonymous-mode
cases.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from moneta import Memory, Moneta, MonetaConfig


# ---------------------------------------------------------------------
# Always-run: disk-backed via MockUsdTarget
# ---------------------------------------------------------------------


class TestTwinSubstrateMockDiskBacked:
    """Two disk-backed handles on different storage_uris must be isolated."""

    def test_isolated_state_under_distinct_uris(self, tmp_path: Path) -> None:
        """Write to m1, read from both — only m1 sees the data."""
        config_a = MonetaConfig(
            storage_uri="moneta-test://twin/a",
            snapshot_path=tmp_path / "a" / "snapshot.json",
            wal_path=tmp_path / "a" / "wal.jsonl",
            mock_target_log_path=tmp_path / "a" / "authoring.jsonl",
        )
        config_b = MonetaConfig(
            storage_uri="moneta-test://twin/b",
            snapshot_path=tmp_path / "b" / "snapshot.json",
            wal_path=tmp_path / "b" / "wal.jsonl",
            mock_target_log_path=tmp_path / "b" / "authoring.jsonl",
        )

        with Moneta(config_a) as m1, Moneta(config_b) as m2:
            eid = m1.deposit("alpha", [1.0, 0.0, 0.0])

            results_a = m1.query([1.0, 0.0, 0.0])
            results_b = m2.query([1.0, 0.0, 0.0])

            assert len(results_a) == 1, "m1 must see its own deposit"
            assert isinstance(results_a[0], Memory)
            assert results_a[0].entity_id == eid
            assert results_b == [], "m2 must not see m1's deposit"

    def test_protected_quota_is_per_handle(self, tmp_path: Path) -> None:
        """A protected deposit on m1 must not consume m2's quota."""
        config_a = MonetaConfig(
            storage_uri="moneta-test://twin/quota-a",
            mock_target_log_path=tmp_path / "qa" / "authoring.jsonl",
        )
        config_b = MonetaConfig(
            storage_uri="moneta-test://twin/quota-b",
            mock_target_log_path=tmp_path / "qb" / "authoring.jsonl",
        )

        with Moneta(config_a) as m1, Moneta(config_b) as m2:
            m1.deposit("p1", [1.0, 0.0], protected_floor=0.1)

            assert m1.ecs.count_protected() == 1, (
                "m1's protected count must reflect the protected deposit"
            )
            assert m2.ecs.count_protected() == 0, (
                "m2's protected quota must be untouched"
            )

    def test_distinct_handles_have_distinct_substrate_objects(
        self, tmp_path: Path
    ) -> None:
        """Defense-in-depth: the underlying ECS / vector index / authoring
        target are physically distinct objects, not shared references."""
        config_a = MonetaConfig(
            storage_uri="moneta-test://twin/objs-a",
            mock_target_log_path=tmp_path / "oa" / "authoring.jsonl",
        )
        config_b = MonetaConfig(
            storage_uri="moneta-test://twin/objs-b",
            mock_target_log_path=tmp_path / "ob" / "authoring.jsonl",
        )

        with Moneta(config_a) as m1, Moneta(config_b) as m2:
            assert m1.ecs is not m2.ecs
            assert m1.vector_index is not m2.vector_index
            assert m1.attention is not m2.attention
            assert m1.authoring_target is not m2.authoring_target


# ---------------------------------------------------------------------
# pxr-gated: real USD writer — exercises the Sdf.Layer C++ registry
# ---------------------------------------------------------------------

# Per-class skip: module-level ``pytest.importorskip`` would skip the
# always-run mock-disk-backed cases above. Detect pxr availability at
# import time and decorate only the pxr-requiring class.
try:
    import pxr  # noqa: F401

    _HAS_PXR = True
except ImportError:
    _HAS_PXR = False


@pytest.mark.skipif(not _HAS_PXR, reason="pxr (OpenUSD bindings) not available")
class TestTwinSubstrateRealUsdDiskBacked:
    """Real USD authoring path. The C++ Sdf.Layer registry is the trap
    described in DEEP_THINK_BRIEF_substrate_handle.md §5.2; isolating
    two handles on distinct on-disk USD paths is the structural proof
    that handle migration did not collapse the registry under cover."""

    def test_real_usd_handles_are_isolated_on_disk(self, tmp_path: Path) -> None:
        usd_a = tmp_path / "usd_a"
        usd_b = tmp_path / "usd_b"
        config_a = MonetaConfig(
            storage_uri="moneta-test://twin/usd-a",
            use_real_usd=True,
            usd_target_path=usd_a,
        )
        config_b = MonetaConfig(
            storage_uri="moneta-test://twin/usd-b",
            use_real_usd=True,
            usd_target_path=usd_b,
        )

        with Moneta(config_a) as m1, Moneta(config_b) as m2:
            eid = m1.deposit("real-usd-alpha", [1.0, 0.0, 0.0])

            assert m1.query([1.0, 0.0, 0.0])[0].entity_id == eid
            assert m2.query([1.0, 0.0, 0.0]) == []

            # The two authoring targets must hold physically distinct
            # Sdf.Layer instances at the root layer level. If the C++
            # registry collapsed them, this assertion would fail.
            assert m1.authoring_target.stage is not m2.authoring_target.stage
            assert (
                m1.authoring_target._root_layer
                is not m2.authoring_target._root_layer
            )
