"""Durability round-trip tests — the kill -9 scenario.

MONETA.md §5 risk #4 target: survive ``kill -9`` with at most 30 seconds
of volatile state lost. Phase 1 Persistence Engineer mitigation:
WAL-lite periodic snapshot + JSONL attention-log WAL + hydrate path.

After the singleton surgery (DEEP_THINK_BRIEF_substrate_handle.md), each
``kill -9`` simulation is modeled as ``handle.close()`` followed by a
fresh ``Moneta(config)`` against the same ``storage_uri``. Closing
releases the URI from the in-memory ``_ACTIVE_URIS`` registry; the
re-construct succeeds because the prior holder is gone.

Volatility window accepted
--------------------------
Deposits that happen between snapshots but before a crash are LOST.
They are captured by the NEXT snapshot, not by the WAL. This is the
"small volatility window" risk #4 explicitly accepts.
``signal_attention`` is covered by the WAL because it is the
high-frequency mutation path; deposits are lower-frequency and
snapshot-captured.

This file verifies:
  1. No-snapshot fresh start does not error
  2. ``run_sleep_pass`` snapshots the ECS when durability is on
  3. Hydrate restores ECS state and rebuilds vector_index
  4. WAL entries made AFTER the snapshot are replayed on hydrate
  5. Pre-snapshot deposits that never made it to a snapshot are lost
     (documented volatility window)
"""
from __future__ import annotations

from pathlib import Path

from moneta import Moneta, MonetaConfig
from moneta.types import EntityState


def _config(
    tmp_path: Path,
    *,
    storage_uri: str,
    half_life_seconds: float | None = None,
) -> MonetaConfig:
    """Construct a durability-enabled config rooted at ``tmp_path``."""
    snapshot_path = tmp_path / "s.json"
    wal_path = tmp_path / "w.jsonl"
    kwargs: dict[str, object] = {
        "storage_uri": storage_uri,
        "snapshot_path": snapshot_path,
        "wal_path": wal_path,
    }
    if half_life_seconds is not None:
        kwargs["half_life_seconds"] = half_life_seconds
    return MonetaConfig(**kwargs)


class TestDurabilityRoundTrip:
    def test_no_snapshot_fresh_start(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path, storage_uri="moneta-test://dura/no-snap")
        with Moneta(cfg) as m:
            assert m.ecs.n == 0
            assert m.durability is not None
            # No snapshot file exists yet — hydrate found nothing
            assert not cfg.snapshot_path.exists()  # type: ignore[union-attr]

    def test_hydrate_restores_ecs_from_snapshot(
        self, tmp_path: Path
    ) -> None:
        uri = "moneta-test://dura/hydrate"
        cfg = _config(tmp_path, storage_uri=uri, half_life_seconds=3600)

        m1 = Moneta(cfg)
        eid_a = m1.deposit("A", [1.0, 0.0])
        eid_b = m1.deposit("B", [0.0, 1.0])

        # run_sleep_pass snapshots when durability is on
        m1.run_sleep_pass()
        assert cfg.snapshot_path.exists()  # type: ignore[union-attr]

        # kill -9 (handle.close releases the URI lock; new handle hydrates)
        m1.close()

        with Moneta(cfg) as m2:
            assert m2.ecs.n == 2
            assert m2.ecs.contains(eid_a)
            assert m2.ecs.contains(eid_b)

            assert m2.vector_index.contains(eid_a)
            assert m2.vector_index.contains(eid_b)
            assert m2.vector_index.get_state(eid_a) == EntityState.VOLATILE
            assert m2.vector_index.get_state(eid_b) == EntityState.VOLATILE

    def test_wal_replay_after_post_snapshot_signal(
        self, tmp_path: Path
    ) -> None:
        uri = "moneta-test://dura/wal-replay"
        cfg = _config(tmp_path, storage_uri=uri, half_life_seconds=3600)

        m1 = Moneta(cfg)
        eid = m1.deposit("A", [1.0, 0.0])
        m1.run_sleep_pass()  # snapshot: eid present, attended_count=0

        # Post-snapshot signal — goes to WAL as well as in-memory log
        m1.signal_attention({eid: 0.5})
        assert cfg.wal_path.exists()  # type: ignore[union-attr]

        # kill -9
        m1.close()

        with Moneta(cfg) as m2:
            # ECS from snapshot
            assert m2.ecs.contains(eid)
            mem = m2.ecs.get_memory(eid)
            assert mem is not None
            assert mem.attended_count == 0  # WAL entry not yet reduced

            # Attention log carries the replayed entry
            assert len(m2.attention) == 1

            # Run a sleep pass — reduces the replayed signal
            m2.run_sleep_pass()
            mem = m2.ecs.get_memory(eid)
            assert mem is not None
            assert mem.attended_count == 1  # WAL replay applied

    def test_pre_snapshot_deposit_is_lost_on_crash(
        self, tmp_path: Path
    ) -> None:
        """Documented volatility window: deposits before the first snapshot
        are lost on crash. This is MONETA.md §5 risk #4 acceptance.
        """
        uri = "moneta-test://dura/volatility-window"
        cfg = _config(tmp_path, storage_uri=uri)

        m1 = Moneta(cfg)
        m1.deposit("will be lost", [1.0])
        # kill -9 BEFORE any snapshot
        m1.close()

        with Moneta(cfg) as m2:
            # No snapshot → fresh ECS
            assert m2.ecs.n == 0

    def test_snapshot_file_is_atomic(self, tmp_path: Path) -> None:
        """Snapshot writes go through a tmp file + os.replace.

        Verify the tmp file is cleaned up after a successful snapshot (no
        leftover .tmp file).
        """
        uri = "moneta-test://dura/atomic"
        cfg = _config(tmp_path, storage_uri=uri)

        with Moneta(cfg) as m:
            m.deposit("x", [1.0])
            m.run_sleep_pass()

            assert cfg.snapshot_path.exists()  # type: ignore[union-attr]
            # No leftover tmp file
            assert not (tmp_path / "s.json.tmp").exists()
