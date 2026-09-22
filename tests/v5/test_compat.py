"""The v1-shaped facade: same config class, same four signatures, v5 underneath."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock
from uuid import UUID

import pytest

import moneta
from moneta import MonetaConfig, MonetaResourceLockedError
from moneta.types import EntityState, Memory
from moneta.v5 import ManualClock, Status
from moneta.v5.compat import BEHAVIOR_CHANGES, Moneta, journal_path_for

T0 = 1_000_000.0
H = 3600.0


def _cfg(tmp_path: Path, uri: str = "moneta-file://store", **kw) -> MonetaConfig:
    return MonetaConfig(
        storage_uri=uri,
        snapshot_path=tmp_path / "snapshot.json",
        wal_path=tmp_path / "wal.log",
        **kw,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v1_smoke_flow_runs_unchanged_on_the_facade():
    # moneta.api.smoke_check, line for line, against the facade.
    with Moneta(MonetaConfig.ephemeral()) as m:
        assert m.query([0.0, 0.0, 0.0]) == []
        assert m.get_consolidation_manifest() == []
        eid = m.deposit("hello world", [1.0, 0.0, 0.0])
        assert isinstance(eid, UUID)
        results = m.query([1.0, 0.0, 0.0], limit=5)
        assert len(results) == 1 and isinstance(results[0], Memory)
        assert results[0].entity_id == eid
        assert results[0].state == EntityState.VOLATILE
        assert 0.99 <= results[0].utility <= 1.0
        assert results[0].attended_count == 0
        assert m.signal_attention({eid: 0.2}) is None
        result = m.run_sleep_pass()
        assert (result.attention_updated, result.pruned, result.staged) == (1, 0, 0)
        assert m.query([1.0, 0.0, 0.0], limit=5)[0].attended_count == 1
        assert m.get_consolidation_manifest() == []


def test_synapse_shaped_handle_surface(tmp_path):
    cfg = _cfg(tmp_path, embedding_dim=2, quota_override=5)
    with Moneta(cfg) as m:
        a = m.deposit("a", [1.0, 0.0], protected_floor=0.5)
        m.deposit("b", [0.0, 1.0])
        assert m.durability is not None
        m.durability.snapshot_ecs(m.ecs)  # SYNAPSE's save()
        assert m.ecs.n == 2 and len(m.ecs) == 2 and len(m.vector_index) == 2
        assert m.ecs.count_protected() == 1
        assert [r.payload for r in m.ecs.iter_rows()] == ["a", "b"]
        assert m.ecs.get_memory(a).protected_floor == 0.5
        with pytest.raises(MonetaResourceLockedError):
            Moneta(cfg)
    assert journal_path_for(cfg) == tmp_path / "snapshot.v5.journal"


def test_ephemeral_has_no_durability_like_v1():
    with Moneta(MonetaConfig.ephemeral()) as m:
        assert m.durability is None


def test_deposit_survives_restart_without_save_or_sleep(tmp_path):
    with Moneta(_cfg(tmp_path)) as m:
        eid = m.deposit("kept", [1.0, 0.0])
    with Moneta(_cfg(tmp_path)) as m:
        assert [r.entity_id for r in m.ecs.iter_rows()] == [eid]


def test_behavior_changes_are_enumerated():
    assert set(BEHAVIOR_CHANGES) >= {
        "deposit_durability",
        "query_dimension",
        "attention_timing",
        "attention_validation",
        "prune_audit",
        "projection_retry",
        "exclusivity",
        "free_threading",
    }


# ----------------------------------------------------------------------
# Migration from a real v1 store
# ----------------------------------------------------------------------


def _build_v1_store(tmp_path: Path):
    """Create a store with the real v1 code, including v1's quirks."""
    now = [T0]
    cfg = _cfg(tmp_path, uri="v1-writer", half_life_seconds=H)
    with mock.patch("moneta.api.time.time", side_effect=lambda: now[0]):
        m = moneta.Moneta(cfg)
        a = m.deposit("alpha", [1.0, 0.0])
        b = m.deposit("beta", [0.0, 1.0], protected_floor=0.3)
        c = m.deposit("gamma", [1.0, 1.0])
        for _ in range(3):
            m.signal_attention({c: 0.0})
        now[0] += 60
        m.run_sleep_pass()  # snapshot written here; WAL truncated
        now[0] += 60
        m.signal_attention({a: 0.2})  # WAL entry after the snapshot
        m.signal_attention({UUID(int=7): 0.1})  # v1 accepts unknown ids
        m.close()
    with open(tmp_path / "wal.log", "a", encoding="utf-8") as fp:
        fp.write('{"wal_version": 1, "entity_id": "not-a-uuid", "weight": 0.1, "timestamp": 2e9}\n')
    snapshot = json.loads((tmp_path / "snapshot.json").read_text())
    return {"a": a, "b": b, "c": c}, snapshot


def test_migration_imports_v1_rows_and_wal_tail(tmp_path):
    ids, snapshot = _build_v1_store(tmp_path)
    before = {p: _sha(tmp_path / p) for p in ("snapshot.json", "wal.log")}
    clock = ManualClock(T0 + 1000)
    with Moneta(_cfg(tmp_path, half_life_seconds=H), clock=clock) as m:
        report = m.migration
        assert report["rows"] == 3
        assert report["wal_applied"] == 1
        assert report["wal_unknown_id"] == 1
        assert report["wal_malformed"] == 1
        rows = {r["entity_id"]: r for r in snapshot["rows"]}
        for name, eid in ids.items():
            e = m.v5.explain(eid, t=rows[str(eid)]["last_evaluated"])
            assert e.payload == rows[str(eid)]["payload"]
            if name != "a":  # 'a' also received the post-snapshot WAL signal
                assert e.utility == pytest.approx(rows[str(eid)]["utility"], abs=1e-12)
                assert e.attended == rows[str(eid)]["attended_count"]
        assert m.v5.explain(ids["a"], t=T0 + 1000).attended == 1
        assert m.ecs.count_protected() == 1
    # v1 files are inputs only.
    assert {p: _sha(tmp_path / p) for p in before} == before
    # A second open replays the journal; it does not migrate again.
    with Moneta(_cfg(tmp_path, half_life_seconds=H), clock=clock) as m:
        assert m.migration is None
        assert m.ecs.n == 3


def test_failed_migration_leaves_no_half_journal(tmp_path):
    (tmp_path / "snapshot.json").write_text(
        json.dumps(
            {
                "snapshot_version": 1,
                "snapshot_created_at": T0,
                "rows": [
                    {
                        "entity_id": str(UUID(int=1)),
                        "payload": "x",
                        "semantic_vector": [1.0, 0.0],
                        "utility": 1.0,
                        "attended_count": 0,
                        "protected_floor": 0.0,
                        "last_evaluated": T0,
                        "state": 0,
                        "usd_link": None,
                    },
                    {
                        "entity_id": str(UUID(int=2)),
                        "payload": "y",
                        "semantic_vector": [1.0, 0.0, 0.0],
                        "utility": 1.0,
                        "attended_count": 0,
                        "protected_floor": 0.0,
                        "last_evaluated": T0,
                        "state": 0,
                        "usd_link": None,
                    },
                ],
            }
        )
    )
    with pytest.raises(ValueError):
        Moneta(_cfg(tmp_path))
    assert not journal_path_for(_cfg(tmp_path)).exists()
    assert (tmp_path / "snapshot.v5.journal.failed-migration").exists()
    # The URI is released after the failure.
    (tmp_path / "snapshot.json").unlink()
    Moneta(_cfg(tmp_path)).close()


def test_use_real_usd_projects_typed_prims(tmp_path):
    pytest.importorskip("pxr")
    from pxr import Usd

    cfg = _cfg(tmp_path, half_life_seconds=H, use_real_usd=True, usd_target_path=tmp_path / "usd")
    clock = ManualClock(T0)
    with Moneta(cfg, clock=clock) as m:
        eid = m.deposit("consolidate me", [1.0, 0.0])
        for _ in range(3):
            m.signal_attention({eid: 0.0})
        clock.advance(2.5 * H)
        r = m.run_sleep_pass()
        assert r.consolidated_ids == (eid,)
        assert m.v5.status_of(eid) == Status.CONSOLIDATED
    stage = Usd.Stage.Open(str(tmp_path / "usd" / "cortex_root.usda"))
    prim = stage.GetPrimAtPath(f"/Memory_{eid.hex}")
    assert prim and prim.GetTypeName() == "MonetaMemory"
    assert prim.GetAttribute("payload").Get() == "consolidate me"
