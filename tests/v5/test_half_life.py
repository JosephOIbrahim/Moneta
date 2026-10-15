"""Round 4 half-life ruling, blocking conditions 1 and 2.

1. The journal owns λ as it owns dim: ``fold.lam`` comes from genesis and
   journaled change events, never from Config. A mismatched open raises
   unless the caller names a mode; opens that are not asked to change
   anything never append.
2. The first sleep pass after a change is a dry run returning the
   would-prune set unless explicitly confirmed.

The probe from docs/v7/ROUND4_BRIEF.md ("Half-life call"): a 24 h store,
30 deposits over 45 h, half-life changed to 1 h, one pass. Reinterpreting
history would tombstone all 30; applying the change forward at the same
instant prunes none.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from moneta import MonetaConfig
from moneta.v5 import (
    Config,
    HalfLifeMismatchError,
    ManualClock,
    Status,
    Substrate,
)
from moneta.v5.compat import BEHAVIOR_CHANGES, Moneta, journal_path_for
from moneta.v5.journal import FORMAT, encode_frame, scan
from moneta.v5.model import Fold, encode_vector

T0 = 1_000_000.0
HOUR = 3600.0
DAY = 24 * HOUR


def _events(path: Path) -> list[dict]:
    events, _, _ = scan(path.read_bytes(), path)
    return events


def _probe_store(path: Path, clock: ManualClock) -> list:
    """24 h half-life, 30 deposits spread over the first 40 h of a 45 h window."""
    ids = []
    with Substrate(Config(path=path, half_life_seconds=DAY, clock=clock)) as m:
        for i in range(30):
            ids.append(m.deposit(f"m{i}", [1.0, float(i)], t=T0 + i * (40 * HOUR / 29)))
    clock.t = T0 + 45 * HOUR
    return ids


# -- the probe -------------------------------------------------------------


def test_probe_reinterpret_would_prune_30_of_30_and_only_on_confirmation(tmp_path):
    path = tmp_path / "m"
    clock = ManualClock(T0)
    ids = _probe_store(path, clock)
    with Substrate(
        Config(path=path, half_life_seconds=HOUR, clock=clock), half_life_change="reinterpret"
    ) as m:
        dry = m.run_sleep_pass()
        assert dry.dry_run and dry.pruned == 0 and dry.pruned_ids == ()
        assert sorted(dry.would_prune_ids) == sorted(ids)  # 30 of 30
        assert m.recallable_count() == 30  # nothing happened
        done = m.run_sleep_pass(confirm_half_life_change=True)
        assert not done.dry_run and done.pruned == 30
        assert done.half_life_change_seq == dry.half_life_change_seq
        # Reverting the half-life cannot bring them back: tombstones are one-way.
        m.set_half_life(DAY, mode="reinterpret")
        assert m.recallable_count() == 0


def test_probe_forward_at_the_same_instant_prunes_0_of_30(tmp_path):
    path = tmp_path / "m"
    clock = ManualClock(T0)
    _probe_store(path, clock)
    with Substrate(
        Config(path=path, half_life_seconds=HOUR, clock=clock), half_life_change="forward"
    ) as m:
        dry = m.run_sleep_pass()
        assert dry.dry_run and dry.would_prune_ids == ()
        done = m.run_sleep_pass(confirm_half_life_change=True)
        assert done.pruned == 0 and m.recallable_count() == 30


# -- condition 1: the journal owns λ --------------------------------------


def test_default_config_open_on_a_non_default_store_refuses_and_writes_nothing(tmp_path):
    path = tmp_path / "m"
    with Substrate(Config(path=path, half_life_seconds=HOUR)) as m:
        m.deposit("a", [1.0, 0.0], t=T0)
    before = path.read_bytes()
    with pytest.raises(HalfLifeMismatchError) as err:
        Substrate(Config(path=path))  # library default: 6 h
    assert err.value.journal_half_life_seconds == HOUR
    assert "half_life_change" in str(err.value)
    assert path.read_bytes() == before
    # The refused open released the journal: the right value opens it.
    with Substrate(Config(path=path, half_life_seconds=HOUR)) as m:
        assert m.half_life_seconds == HOUR
    assert path.read_bytes() == before  # a matching open appends nothing


def test_bad_mode_is_rejected_before_the_journal_is_touched(tmp_path):
    with pytest.raises(ValueError, match="half_life_change"):
        Substrate(Config(path=tmp_path / "m"), half_life_change="silently")
    assert not (tmp_path / "m").exists()


def test_mode_with_an_unchanged_value_appends_nothing(tmp_path):
    path = tmp_path / "m"
    with Substrate(Config(path=path, half_life_seconds=HOUR)):
        pass
    before = path.read_bytes()
    with Substrate(Config(path=path, half_life_seconds=HOUR), half_life_change="forward") as m:
        assert m.set_half_life(HOUR, mode="reinterpret") is None
        assert m.half_life_change_pending is None
    assert path.read_bytes() == before


def test_set_half_life_validates(tmp_path):
    with Substrate(Config.ephemeral(half_life_seconds=HOUR)) as m:
        with pytest.raises(ValueError):
            m.set_half_life(10.0, mode="forward")  # below the 1 min floor
        with pytest.raises(ValueError):
            m.set_half_life(2 * HOUR, mode="both")
        assert m.half_life_seconds == HOUR


def test_replay_is_identical_without_the_original_config(tmp_path):
    path = tmp_path / "m"
    clock = ManualClock(T0)
    with Substrate(Config(path=path, half_life_seconds=HOUR, clock=clock)) as m:
        a = m.deposit("a", [1.0, 0.0], t=T0)
        b = m.deposit("b", [0.0, 1.0], t=T0 + HOUR)
        m.signal_attention({a: 0.4}, t=T0 + 2 * HOUR)
        m.set_half_life(4 * HOUR, mode="forward", t=T0 + 3 * HOUR)
        m.signal_attention({b: 0.2}, t=T0 + 4 * HOUR)
        m.set_half_life(2 * HOUR, mode="reinterpret", t=T0 + 5 * HOUR)
        m.run_sleep_pass(t=T0 + 6 * HOUR, confirm_half_life_change=True)
        t_eval = T0 + 8 * HOUR
        live = {e: m.explain(e, t=t_eval) for e in (a, b)}
        live_lam = m.lam
    before = path.read_bytes()

    # A bare fold over the journal: no Config anywhere.
    fold = Fold()
    fold.replay(iter(_events(path)))
    assert fold.lam == live_lam and fold.half_life_seconds == 2 * HOUR
    for e in (a, b):
        rec = fold.records[e]
        assert rec.utility_at(fold.lam, t_eval) == live[e].utility
        assert (rec.anchor_t, rec.status.value) == (live[e].anchor_t, live[e].status)

    # Reopening with the journal's current value gives the same state ...
    with Substrate(Config(path=path, half_life_seconds=2 * HOUR, clock=clock)) as m:
        for e in (a, b):
            assert m.explain(e, t=t_eval).utility == live[e].utility
    # ... and the value the store was created with is now a mismatch.
    with pytest.raises(HalfLifeMismatchError):
        Substrate(Config(path=path, half_life_seconds=HOUR, clock=clock))
    assert path.read_bytes() == before


# -- forward vs reinterpret -------------------------------------------------


def _two_records(mode: str):
    m = Substrate(Config.ephemeral(half_life_seconds=HOUR))
    a = m.deposit("never attended", [1.0, 0.0], t=T0)
    b = m.deposit("attended", [0.0, 1.0], t=T0)
    m.signal_attention({b: 0.5}, t=T0 + HOUR)  # 0.5 + 0.5 -> anchor 1.0 at T0+H
    m.set_half_life(4 * HOUR, mode=mode, t=T0 + 2 * HOUR)
    return m, a, b


def test_forward_keeps_history_and_applies_the_new_value_after_the_change():
    m, a, b = _two_records("forward")
    t = T0 + 3 * HOUR  # one hour after the change
    with m:
        assert math.isclose(m.explain(a, t=t).utility, 0.25 * 2 ** -0.25, rel_tol=1e-12)
        assert math.isclose(m.explain(b, t=t).utility, 0.5 * 2 ** -0.25, rel_tol=1e-12)
        assert m.explain(a, t=t).anchor_t == T0 + 2 * HOUR  # rebased at the change


def test_reinterpret_applies_the_new_value_from_each_records_last_anchor():
    m, a, b = _two_records("reinterpret")
    t = T0 + 3 * HOUR
    with m:
        # Never attended: as if 4 h had held since deposit (3 h old).
        assert math.isclose(m.explain(a, t=t).utility, 2 ** -0.75, rel_tol=1e-12)
        # Attended at T0+H (anchor 1.0 folded under the old value): 2 h at 4 h.
        assert math.isclose(m.explain(b, t=t).utility, 2 ** -0.5, rel_tol=1e-12)
        assert m.explain(a, t=t).anchor_t == T0


# -- condition 2: the first pass after a change is a dry run --------------


def test_change_then_dry_run_then_confirm(tmp_path):
    path = tmp_path / "m"
    clock = ManualClock(T0)
    with Substrate(Config(path=path, half_life_seconds=DAY, clock=clock)) as m:
        old = m.deposit("old", [1.0, 0.0], t=T0)
        fresh = m.deposit("fresh", [0.0, 1.0], t=T0 + 9 * HOUR)
        m.signal_attention({fresh: 0.1}, t=T0 + 9 * HOUR)
        assert not m.run_sleep_pass(t=T0 + 9 * HOUR).dry_run  # no change yet: a real pass
    clock.t = T0 + 10 * HOUR
    with Substrate(
        Config(path=path, half_life_seconds=HOUR, clock=clock), half_life_change="reinterpret"
    ) as m:
        change = m.half_life_change_pending
        assert change["from"] == DAY and change["half_life_seconds"] == HOUR
        assert change["mode"] == "reinterpret"
        seq = m.seq
        first = m.run_sleep_pass()
        assert first.dry_run and first.would_prune_ids == (old,)
        assert first.half_life_change_seq == change["seq"]
        assert (first.pruned, first.staged, first.pruned_ids, first.authored_at) == (0, 0, (), None)
        assert m.seq == seq and m.status_of(old) == Status.LIVE  # journaled nothing
        assert m.run_sleep_pass().dry_run  # still held until confirmed
    # The hold is journal state: it survives a reopen.
    with Substrate(Config(path=path, half_life_seconds=HOUR, clock=clock)) as m:
        assert m.run_sleep_pass().dry_run
        done = m.run_sleep_pass(confirm_half_life_change=True)
        assert done.pruned_ids == (old,) and m.status_of(old) == Status.TOMBSTONED
        assert m.half_life_change_pending is None
        assert not m.run_sleep_pass().dry_run  # back to normal
    retains = [e for e in _events(path) if e["op"] == "retain"]
    assert retains[-2]["half_life_change_seq"] == change["seq"]  # the audit names the cause
    assert "half_life_change_seq" not in retains[-1]


def test_legacy_half_life_note_replays_as_a_reinterpret_change(tmp_path):
    # Journals written before the ruling carry the implicit note instead of
    # a half_life event; they replay as a reinterpret at the note's seq.
    path = tmp_path / "m"
    eid = "00000000-0000-0000-0000-000000000001"
    events = [
        {"op": "genesis", "format": FORMAT, "version": "x", "t": T0, "dim": None,
         "half_life_seconds": HOUR},
        {"op": "deposit", "id": eid, "t": T0, "payload": "a", "emb": encode_vector([1.0, 0.0]),
         "floor": 0.0, "scope": ""},
        {"op": "note", "t": T0 + HOUR, "kind": "half_life_change", "from": HOUR,
         "half_life_seconds": 2 * HOUR},
    ]
    path.write_bytes(b"".join(encode_frame(dict(e, seq=i + 1)) for i, e in enumerate(events)))
    with Substrate(Config(path=path, half_life_seconds=2 * HOUR)) as m:
        rec = next(iter(m.records(t=T0 + 2 * HOUR)))
        assert math.isclose(rec.utility, 0.5, rel_tol=1e-12)
        assert m.run_sleep_pass(t=T0 + 2 * HOUR).dry_run


# -- the v1 facade ------------------------------------------------------------


def _facade_cfg(tmp_path: Path, **kw) -> MonetaConfig:
    return MonetaConfig(
        storage_uri="moneta-file://hl",
        snapshot_path=tmp_path / "snapshot.json",
        wal_path=tmp_path / "wal.log",
        **kw,
    )


def test_facade_refuses_a_changed_half_life_unless_a_mode_is_named(tmp_path):
    clock = ManualClock(T0)
    with Moneta(_facade_cfg(tmp_path, half_life_seconds=DAY), clock=clock) as m:
        m.deposit("a", [1.0, 0.0])
    journal = journal_path_for(_facade_cfg(tmp_path))
    before = journal.read_bytes()
    with pytest.raises(HalfLifeMismatchError):
        Moneta(_facade_cfg(tmp_path), clock=clock)  # MonetaConfig default: 6 h
    assert journal.read_bytes() == before
    clock.t = T0 + 10 * HOUR
    with Moneta(
        _facade_cfg(tmp_path, half_life_seconds=HOUR), clock=clock, half_life_change="reinterpret"
    ) as m:
        dry = m.run_sleep_pass()
        assert dry.dry_run and dry.pruned == 0 and len(dry.would_prune_ids) == 1
        assert m.ecs.n == 1
        assert m.run_sleep_pass(confirm_half_life_change=True).pruned == 1
    assert {"half_life_owned_by_journal", "half_life_change_dry_run"} <= set(BEHAVIOR_CHANGES)
