"""The v1 defect register, as executable evidence.

Each defect is a pair of tests:

- ``test_v1_*`` reproduces the defect on v1 at HEAD (``moneta.Moneta``).
  It passes *because the defect exists*. If v1 is ever fixed, it fails,
  and the register must be updated. This is documentation that runs.
- ``test_v5_*`` shows v5 does the right thing in the same scenario.

Probe ids P1..P11 match docs/v5/BLUEPRINT.md.
"""

from __future__ import annotations

import json
import math
import time
from unittest import mock
from uuid import uuid4

import pytest

from moneta import Moneta, MonetaConfig
from moneta.types import EntityState
from moneta.v5 import (
    Config,
    DimensionMismatchError,
    JournalLockedError,
    Status,
    Substrate,
    UnknownEntityError,
)

T0 = 1_000_000.0
H = 3600.0


def v1_at(clock_list):
    return mock.patch("moneta.api.time.time", side_effect=lambda: clock_list[0])


# P1 -------------------------------------------------------------------


def test_v1_p1_deposit_is_lost_without_a_sleep_pass(tmp_path):
    cfg = MonetaConfig(storage_uri="p1", snapshot_path=tmp_path / "s.json", wal_path=tmp_path / "w")
    with Moneta(cfg) as m:
        m.deposit("remember me", [1.0, 0.0])
    with Moneta(cfg) as m:
        assert m.ecs.n == 0


def test_v5_p1_deposit_is_durable_on_return(tmp_path):
    with Substrate(Config(path=tmp_path / "m")) as m:
        m.deposit("remember me", [1.0, 0.0])
    with Substrate(Config(path=tmp_path / "m")) as m:
        assert [x.payload for x in m.records()] == ["remember me"]


# P2 -------------------------------------------------------------------


def test_v1_p2_rejected_deposit_leaves_an_orphan_row(monkeypatch):
    # Guard: the defect lives in the default (auto/off) handle. Under
    # MONETA_NATIVE=require, v1's deposit envelope pre-check (SPEC 3) rejects
    # a wrong-dim vector with NativeSeamError before any mutation, so this
    # reproduction is pinned to the env-unset default.
    monkeypatch.delenv("MONETA_NATIVE", raising=False)
    with Moneta(MonetaConfig.ephemeral()) as m:
        m.deposit("a", [1.0, 0.0])
        with pytest.raises(ValueError):
            m.deposit("b", [1.0, 0.0, 0.0])
        assert (m.ecs.n, len(m.vector_index)) == (2, 1)


def test_v5_p2_rejected_deposit_leaves_nothing():
    with Substrate(Config.ephemeral()) as m:
        m.deposit("a", [1.0, 0.0])
        with pytest.raises(DimensionMismatchError):
            m.deposit("b", [1.0, 0.0, 0.0])
        assert (m.recallable_count(), m.seq) == (1, 2)


# P3 -------------------------------------------------------------------


def test_v1_p3_wrong_dimension_query_is_a_silent_empty_success():
    with Moneta(MonetaConfig.ephemeral()) as m:
        m.deposit("a", [1.0, 0.0])
        assert m.query([1.0, 0.0, 0.0]) == []


def test_v5_p3_wrong_dimension_query_raises():
    with Substrate(Config.ephemeral()) as m:
        m.deposit("a", [1.0, 0.0])
        with pytest.raises(DimensionMismatchError):
            m.query([1.0, 0.0, 0.0])


# P4 -------------------------------------------------------------------


def test_v1_p4_attention_reduce_erases_decay():
    now = [T0]
    with v1_at(now):
        m = Moneta(MonetaConfig.ephemeral(half_life_seconds=H))
        eid = m.deposit("a", [1.0, 0.0])
        now[0] = T0 + H
        m.signal_attention({eid: 0.0})  # a zero-weight signal
        now[0] = T0 + 3 * H
        m.run_sleep_pass()
        assert m.ecs.get_memory(eid).utility == 1.0  # three half-lives, no decay
        m.close()


def test_v5_p4_attention_applies_at_its_own_time():
    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        eid = m.deposit("a", [1.0, 0.0], t=T0)
        m.signal_attention({eid: 0.0}, t=T0 + H)
        m.run_sleep_pass(t=T0 + 3 * H)
        assert m.explain(eid, t=T0 + 3 * H).utility == pytest.approx(0.125)


# P5 -------------------------------------------------------------------


@pytest.mark.parametrize("weight", [-5.0, math.nan])
def test_v1_p5_one_bad_weight_deletes_a_fresh_memory(weight):
    with Moneta(MonetaConfig.ephemeral()) as m:
        eid = m.deposit("a", [1.0, 0.0])
        m.signal_attention({eid: weight})
        assert m.run_sleep_pass().pruned == 1
        assert m.ecs.get_memory(eid) is None


@pytest.mark.parametrize("weight", [-5.0, math.nan, 1.5])
def test_v5_p5_bad_weights_are_rejected(weight):
    with Substrate(Config.ephemeral()) as m:
        eid = m.deposit("a", [1.0, 0.0])
        with pytest.raises(ValueError):
            m.signal_attention({eid: weight})
        assert m.run_sleep_pass().pruned == 0


# P6 -------------------------------------------------------------------


def test_v1_p6_one_malformed_wal_line_stops_the_store_opening(tmp_path):
    cfg = MonetaConfig(storage_uri="p6", snapshot_path=tmp_path / "s.json", wal_path=tmp_path / "w")
    with Moneta(cfg) as m:
        m.signal_attention({uuid4(): 0.1})  # unknown id, accepted
    with open(tmp_path / "w", "a") as fp:
        fp.write(
            json.dumps(
                {
                    "wal_version": 1,
                    "entity_id": "not-a-uuid",
                    "weight": 0.1,
                    "timestamp": time.time(),
                }
            )
            + "\n"
        )
    with pytest.raises(ValueError):
        Moneta(
            MonetaConfig(
                storage_uri="p6b", snapshot_path=tmp_path / "s.json", wal_path=tmp_path / "w"
            )
        )


def test_v5_p6_unknown_ids_never_reach_the_journal():
    with Substrate(Config.ephemeral()) as m:
        with pytest.raises(UnknownEntityError):
            m.signal_attention({uuid4(): 0.1})
        assert m.seq == 1  # genesis only


# P7 -------------------------------------------------------------------


def test_v1_p7_consolidated_rows_never_leave_ram_and_usd_is_never_read():
    now = [T0]
    with v1_at(now):
        m = Moneta(MonetaConfig.ephemeral(half_life_seconds=H))
        eid = m.deposit("a", [1.0, 0.0])
        for _ in range(3):
            m.signal_attention({eid: 0.0})
        m.run_sleep_pass()
        now[0] += 2.5 * H
        assert m.run_sleep_pass().staged == 1
        now[0] += 30 * 24 * H
        m.run_sleep_pass()
        row = m.ecs.get_memory(eid)
        assert row is not None and row.state == EntityState.CONSOLIDATED
        m.close()


def test_v5_p7_consolidation_is_a_journaled_status_not_a_copy():
    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        eid = m.deposit("a", [1.0, 0.0], t=T0)
        for i in range(3):
            m.signal_attention({eid: 0.0}, t=T0 + i)
        r = m.run_sleep_pass(t=T0 + 2.5 * H)
        assert r.staged_ids == (eid,) and r.consolidated_ids == (eid,)
        assert m.status_of(eid) == Status.CONSOLIDATED
        assert m.explain(eid).status_reason == "none"  # no projector configured: nothing written


# P8 -------------------------------------------------------------------


class _Boom:
    name = "boom"

    def author_stage_batch(self, entities):
        raise OSError("disk full")

    def project(self, memories, t):
        raise OSError("disk full")

    def flush(self):
        pass

    def close(self):
        pass


def test_v1_p8_failed_commit_strands_records_forever():
    now = [T0]
    with v1_at(now):
        m = Moneta(MonetaConfig.ephemeral(half_life_seconds=H))
        m.sequential_writer._target = _Boom()
        eid = m.deposit("a", [1.0, 0.0])
        for _ in range(3):
            m.signal_attention({eid: 0.0})
        m.run_sleep_pass()
        now[0] += 2.5 * H
        with pytest.raises(OSError):
            m.run_sleep_pass()
        m.sequential_writer._target = m.authoring_target  # the disk recovers
        now[0] += 60
        assert m.run_sleep_pass().staged == 0
        assert m.ecs.get_memory(eid).state == EntityState.STAGED_FOR_SYNC
        m.close()


def test_v5_p8_failed_projection_is_retried_next_pass():
    from moneta.v5 import MemoryProjector

    good = MemoryProjector()
    m = Substrate(Config.ephemeral(half_life_seconds=H, projector=_Boom()))
    eid = m.deposit("a", [1.0, 0.0], t=T0)
    for i in range(3):
        m.signal_attention({eid: 0.0}, t=T0 + i)
    r = m.run_sleep_pass(t=T0 + 2.5 * H)
    assert r.projection_error and m.status_of(eid) == Status.STAGED
    m._projector = good  # the disk recovers
    r2 = m.run_sleep_pass(t=T0 + 2.5 * H + 60)
    assert r2.consolidated_ids == (eid,) and m.status_of(eid) == Status.CONSOLIDATED
    assert len(good.batches) == 1
    m.close()


# P9 -------------------------------------------------------------------


def test_v1_p9_query_writes_state():
    now = [T0]
    with v1_at(now):
        m = Moneta(MonetaConfig.ephemeral(half_life_seconds=H))
        eid = m.deposit("a", [1.0, 0.0])
        now[0] += 100
        m.query([1.0, 0.0])
        assert m.ecs.get_memory(eid).last_evaluated == T0 + 100
        m.close()


def test_v5_p9_query_is_pure():
    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        eid = m.deposit("a", [1.0, 0.0], t=T0)
        seq = m.seq
        m.query([1.0, 0.0], t=T0 + 100)
        assert m.seq == seq and m._fold.records[eid].anchor_t == T0


# P10 ------------------------------------------------------------------


def test_v1_p10_prune_reports_only_a_count():
    now = [T0]
    with v1_at(now):
        m = Moneta(MonetaConfig.ephemeral(half_life_seconds=H))
        m.deposit("forget me", [1.0, 0.0])
        now[0] += 10 * H
        r = m.run_sleep_pass()
        assert r.pruned == 1 and not hasattr(r, "pruned_ids")
        m.close()


def test_v5_p10_prune_names_what_it_removed_and_keeps_it_inspectable():
    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        eid = m.deposit("forget me", [1.0, 0.0], t=T0)
        r = m.run_sleep_pass(t=T0 + 10 * H)
        assert r.pruned_ids == (eid,)
        e = m.explain(eid)
        assert (e.status, e.payload) == ("tombstoned", "forget me")


# P11 ------------------------------------------------------------------


def test_v1_p11_two_uris_on_one_snapshot_lose_writes(tmp_path):
    kw = dict(snapshot_path=tmp_path / "shared.json", wal_path=tmp_path / "shared.wal")
    a = Moneta(MonetaConfig(storage_uri="A", **kw))
    b = Moneta(MonetaConfig(storage_uri="B", **kw))
    a.deposit("from A", [1.0, 0.0])
    b.deposit("from B", [0.0, 1.0])
    a.run_sleep_pass()
    b.run_sleep_pass()
    a.close()
    b.close()
    with Moneta(MonetaConfig(storage_uri="C", **kw)) as c:
        assert sorted(x.payload for x in c.ecs.iter_rows()) == ["from B"]


def test_v5_p11_one_journal_one_owner(tmp_path):
    with Substrate(Config(path=tmp_path / "shared")):
        with pytest.raises(JournalLockedError):
            Substrate(Config(path=tmp_path / "shared"))
