"""Durability round-trip tests — the kill -9 scenario.

MONETA.md §5 risk #4 target: survive `kill -9` with at most 30 seconds
of volatile state lost. Phase 1 Persistence Engineer mitigation:
WAL-lite periodic snapshot + JSONL attention-log WAL + hydrate path.

Volatility window accepted
--------------------------
Deposits that happen between snapshots but before a crash are LOST.
They are captured by the NEXT snapshot, not by the WAL. This is the
"small volatility window" risk #4 explicitly accepts. `signal_attention`
is covered by the WAL because it is the high-frequency mutation path;
deposits are lower-frequency and snapshot-captured.

This file verifies:
  1. No-snapshot fresh start does not error
  2. run_sleep_pass snapshots the ECS when durability is on
  3. Hydrate restores ECS state and rebuilds vector_index
  4. WAL entries made AFTER the snapshot are replayed on hydrate
  5. Pre-snapshot deposits that never made it to a snapshot are lost
     (documented volatility window)
"""
from __future__ import annotations

import pytest

import moneta
from moneta import MonetaConfig
from moneta import api as moneta_api
from moneta.types import EntityState


class TestDurabilityRoundTrip:
    def test_no_snapshot_fresh_start(self, tmp_path) -> None:
        snapshot_path = tmp_path / "s.json"
        wal_path = tmp_path / "w.jsonl"
        moneta_api._reset_state()
        moneta.init(
            config=MonetaConfig(
                snapshot_path=snapshot_path, wal_path=wal_path
            )
        )
        state = moneta_api._state
        assert state is not None
        assert state.ecs.n == 0
        assert state.durability is not None

        # No snapshot file exists yet — hydrate found nothing
        assert not snapshot_path.exists()
        moneta_api._reset_state()

    def test_hydrate_restores_ecs_from_snapshot(self, tmp_path) -> None:
        snapshot_path = tmp_path / "s.json"
        wal_path = tmp_path / "w.jsonl"

        moneta_api._reset_state()
        moneta.init(
            config=MonetaConfig(
                half_life_seconds=3600,
                snapshot_path=snapshot_path,
                wal_path=wal_path,
            )
        )
        eid_a = moneta.deposit("A", [1.0, 0.0])
        eid_b = moneta.deposit("B", [0.0, 1.0])

        # run_sleep_pass snapshots when durability is on
        moneta.run_sleep_pass()
        assert snapshot_path.exists()

        # kill -9 (forcible state reset, no graceful shutdown)
        moneta_api._reset_state()

        # Re-init with same paths → hydrate
        moneta.init(
            config=MonetaConfig(
                half_life_seconds=3600,
                snapshot_path=snapshot_path,
                wal_path=wal_path,
            )
        )
        state = moneta_api._state
        assert state is not None

        # ECS rehydrated
        assert state.ecs.n == 2
        assert state.ecs.contains(eid_a)
        assert state.ecs.contains(eid_b)

        # Vector index rebuilt from ECS rows at init time
        assert state.vector_index.contains(eid_a)
        assert state.vector_index.contains(eid_b)
        assert state.vector_index.get_state(eid_a) == EntityState.VOLATILE
        assert state.vector_index.get_state(eid_b) == EntityState.VOLATILE

        moneta_api._reset_state()

    def test_wal_replay_after_post_snapshot_signal(self, tmp_path) -> None:
        snapshot_path = tmp_path / "s.json"
        wal_path = tmp_path / "w.jsonl"

        moneta_api._reset_state()
        moneta.init(
            config=MonetaConfig(
                half_life_seconds=3600,
                snapshot_path=snapshot_path,
                wal_path=wal_path,
            )
        )
        eid = moneta.deposit("A", [1.0, 0.0])
        moneta.run_sleep_pass()  # snapshot: eid present, attended_count=0

        # Post-snapshot signal — goes to WAL as well as in-memory log
        moneta.signal_attention({eid: 0.5})
        assert wal_path.exists()

        # kill -9
        moneta_api._reset_state()

        # Hydrate
        moneta.init(
            config=MonetaConfig(
                half_life_seconds=3600,
                snapshot_path=snapshot_path,
                wal_path=wal_path,
            )
        )
        state = moneta_api._state
        assert state is not None

        # ECS from snapshot
        assert state.ecs.contains(eid)
        mem = state.ecs.get_memory(eid)
        assert mem is not None
        assert mem.attended_count == 0  # WAL entry not yet reduced

        # Attention log carries the replayed entry
        assert len(state.attention) == 1

        # Run a sleep pass — reduces the replayed signal
        moneta.run_sleep_pass()
        mem = state.ecs.get_memory(eid)
        assert mem is not None
        assert mem.attended_count == 1  # WAL replay applied

        moneta_api._reset_state()

    def test_pre_snapshot_deposit_is_lost_on_crash(self, tmp_path) -> None:
        """Documented volatility window: deposits before the first snapshot
        are lost on crash. This is MONETA.md §5 risk #4 acceptance.
        """
        snapshot_path = tmp_path / "s.json"
        wal_path = tmp_path / "w.jsonl"

        moneta_api._reset_state()
        moneta.init(
            config=MonetaConfig(
                snapshot_path=snapshot_path, wal_path=wal_path
            )
        )
        moneta.deposit("will be lost", [1.0])
        # kill -9 BEFORE any snapshot
        moneta_api._reset_state()

        moneta.init(
            config=MonetaConfig(
                snapshot_path=snapshot_path, wal_path=wal_path
            )
        )
        state = moneta_api._state
        assert state is not None
        # No snapshot → fresh ECS
        assert state.ecs.n == 0
        moneta_api._reset_state()

    def test_snapshot_file_is_atomic(self, tmp_path) -> None:
        """Snapshot writes go through a tmp file + os.replace.

        Verify the tmp file is cleaned up after a successful snapshot (no
        leftover .tmp file).
        """
        snapshot_path = tmp_path / "s.json"
        wal_path = tmp_path / "w.jsonl"

        moneta_api._reset_state()
        moneta.init(
            config=MonetaConfig(
                snapshot_path=snapshot_path, wal_path=wal_path
            )
        )
        moneta.deposit("x", [1.0])
        moneta.run_sleep_pass()

        assert snapshot_path.exists()
        # No leftover tmp file
        assert not (tmp_path / "s.json.tmp").exists()
        moneta_api._reset_state()
