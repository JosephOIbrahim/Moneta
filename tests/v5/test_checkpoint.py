"""Journal checkpoints: open replays only the tail (Round 4 E3 condition 3).

The contract under test: a fold snapshot plus the events after it is the
same state, bit for bit, as a replay from genesis. A missing or damaged
snapshot is never fatal; open falls back to an older checkpoint or to a
full replay. Erase and compact reach the snapshots (Round 4 E4 condition 2).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest import mock
from uuid import UUID

import pytest

from moneta.v5 import Config, JournalCorruptError, ManualClock, Substrate
from moneta.v5 import checkpoint as ckpt
from moneta.v5.journal import FileJournal, encode_frame, scan
from moneta.v5.model import Fold
from moneta.v5.substrate import MemoryProjector

T0 = 1_000_000.0
H = 3600.0


def _cfg(path: Path, clock: ManualClock | None = None, **kw) -> Config:
    kw.setdefault("half_life_seconds", H)
    kw.setdefault("fsync", False)
    return Config(path=path, clock=clock or ManualClock(T0), **kw)


def _genesis_fold(path: Path) -> Fold:
    """The reference: every event, validated, replayed from seq 1."""
    events, _, _ = scan(path.read_bytes(), path)
    fold = Fold()
    fold.replay(iter(events))
    return fold


def _same_state(a: Fold, b: Fold) -> bool:
    return ckpt.snapshot_bytes(a) == ckpt.snapshot_bytes(b)


def _snapshots(path: Path) -> list[Path]:
    d = ckpt.checkpoint_dir(path)
    return sorted(d.glob("*.fold")) if d.is_dir() else []


def _rich_store(path: Path, clock: ManualClock) -> list[UUID]:
    """A journal that touches every fold field a checkpoint must carry."""
    ids: list[UUID] = []
    with Substrate(_cfg(path, clock, projector=MemoryProjector())) as m:
        for i in range(40):
            clock.advance(60)
            ids.append(
                m.deposit(
                    f"m{i}",
                    [1.0, float(i % 7), float(i % 3) - 1.0],
                    0.3 if i % 9 == 0 else 0.0,
                    scope="s" if i % 2 else "",
                    slot=f"slot{i % 4}" if i % 5 == 0 else None,
                    key=f"k{i}" if i % 4 == 0 else None,
                )
            )
        for i in range(0, 40, 3):
            clock.advance(30)
            m.signal_attention({ids[i]: 0.2, ids[(i + 1) % 40]: 0.05})
        for i in range(1, 40, 5):  # repeat attention: some become stage candidates
            for _ in range(3):
                clock.advance(10)
                m.signal_attention({ids[i]: 0.01})
        clock.advance(6 * 3600)
        m.run_sleep_pass()
        m.tombstone([ids[3], ids[4]], reason="operator")
        clock.advance(60)
        m.signal_attention({ids[2]: 0.5})
    return ids


def _reopen_from_genesis_and_checkpoint(path: Path, clock: ManualClock, half_life: float):
    with Substrate(_cfg(path, clock, half_life_seconds=half_life)) as m:
        live = m._fold
        from_ckpt = m.opened_from_checkpoint
        replayed = m.replayed_at_open
        assert m.verify()["matches"]
    return live, from_ckpt, replayed


def test_checkpoint_plus_tail_equals_replay_from_genesis(tmp_path):
    path = tmp_path / "m.v5.journal"
    clock = ManualClock(T0)
    ids = _rich_store(path, clock)
    with Substrate(_cfg(path, clock)) as m:
        seq = m.checkpoint()
        covers = m._fold.last_checkpoint["covers"]
        assert seq == m.seq and covers == seq - 1
        # Writes after the checkpoint: the tail open must replay.
        clock.advance(60)
        m.deposit("after", [0.0, 1.0, 0.0], key="k4")  # a dead key reused after the snapshot
        m.signal_attention({ids[5]: 0.3, ids[1]: 0.1})
        total = m.seq
    with Substrate(_cfg(path, clock, half_life_seconds=2 * H), half_life_change="forward") as m:
        pass  # an unconfirmed half-life change after the checkpoint: pending state
    live, from_ckpt, replayed = _reopen_from_genesis_and_checkpoint(path, clock, 2 * H)
    assert from_ckpt == covers
    assert replayed == total + 1 - covers  # the tail only, not the whole journal
    ref = _genesis_fold(path)
    assert ref.half_life_change_pending is not None
    statuses = {r.status.value for r in ref.records.values()}
    assert {"live", "tombstoned", "consolidated"} <= statuses
    assert ref.attended_since_pass and ref.by_key and ref.repacks >= 1
    assert _same_state(live, ref)
    # And field by field, for a readable failure if the encoder ever hides one.
    assert list(live.records) == list(ref.records)
    assert list(live.live) == list(ref.live)
    assert live.by_key == ref.by_key
    assert live.attended_since_pass == ref.attended_since_pass
    assert live.half_life_change_pending == ref.half_life_change_pending
    assert (live.lam, live.dim, live.last_seq) == (ref.lam, ref.dim, ref.last_seq)
    for eid, rec in ref.records.items():
        assert live.records[eid] == rec


def test_recall_is_identical_from_a_checkpoint_and_from_genesis(tmp_path):
    path = tmp_path / "m.v5.journal"
    clock = ManualClock(T0)
    _rich_store(path, clock)
    with Substrate(_cfg(path, clock)) as m:
        m.checkpoint()
        m.deposit("tail", [0.5, 0.5, 0.5])
    q = [1.0, 2.0, -1.0]
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint is not None
        a = [(i.memory.entity_id, i.score, i.memory.utility) for i in m.recall(q, 20).items]
        b = [(e.entity_id, e.verdict) for e in map(m.explain, [x[0] for x in a])]
    for f in _snapshots(path):
        f.unlink()
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint is None
        assert [(i.memory.entity_id, i.score, i.memory.utility) for i in m.recall(q, 20).items] == a
        assert [(e.entity_id, e.verdict) for e in map(m.explain, [x[0] for x in a])] == b


def test_newest_valid_checkpoint_wins_and_damage_falls_back(tmp_path, caplog):
    path = tmp_path / "m.v5.journal"
    clock = ManualClock(T0)
    with Substrate(_cfg(path, clock)) as m:
        for i in range(5):
            m.deposit(f"a{i}", [1.0, float(i)])
        first = m.checkpoint() - 1
        for i in range(5):
            m.deposit(f"b{i}", [float(i), 1.0])
        second = m.checkpoint() - 1
        m.deposit("c", [1.0, 1.0])
    assert len(_snapshots(path)) == 2
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint == second
    newest = ckpt.checkpoint_dir(path) / next(
        f.name for f in _snapshots(path) if f.name.startswith(f"{second:012d}-")
    )
    raw = bytearray(newest.read_bytes())
    raw[len(raw) // 2] ^= 0x01  # one flipped bit
    newest.write_bytes(bytes(raw))
    with caplog.at_level(logging.WARNING, logger="moneta.v5.checkpoint"):
        with Substrate(_cfg(path, clock)) as m:
            assert m.opened_from_checkpoint == first
            assert m.verify()["matches"]
    assert "sha256 mismatch" in caplog.text
    for f in _snapshots(path):
        f.unlink()
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint is None
        assert m.replayed_at_open == m.seq
        assert m.recallable_count() == 11


def test_snapshot_that_claims_other_coverage_is_refused(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        m.deposit("a", [1.0, 0.0])
        m.checkpoint()
        m.deposit("b", [0.0, 1.0])
        m.checkpoint()
    # Swap the newer snapshot's bytes for the older one's: the sha in the
    # name and in the event no longer match the content.
    old, new = _snapshots(path)
    new.write_bytes(old.read_bytes())
    with Substrate(_cfg(path)) as m:
        assert m.opened_from_checkpoint == int(old.name[:12])
        assert m.verify()["matches"]


def test_tail_corruption_after_a_checkpoint_still_raises(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        m.deposit("a", [1.0, 0.0])
        m.checkpoint()
        for i in range(3):
            m.deposit(f"t{i}", [1.0, float(i)])
    lines = path.read_bytes().split(b"\n")[:-1]
    lines[-2] = lines[-2][:-3] + b"xx}"  # a complete line, bad CRC, in the tail
    path.write_bytes(b"\n".join(lines) + b"\n")
    with pytest.raises(JournalCorruptError) as err:
        Substrate(_cfg(path))
    assert err.value.line_no == len(lines) - 1  # the forward scan names the line


def test_prefix_damage_is_skipped_at_open_and_caught_by_verify(tmp_path):
    """The documented trade: a checkpoint vouches for its prefix; verify() re-reads it."""
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        for i in range(3):
            m.deposit(f"a{i}", [1.0, float(i)])
        m.checkpoint()
        m.deposit("tail", [0.0, 1.0])
    lines = path.read_bytes().split(b"\n")[:-1]
    lines[1] = lines[1][:-3] + b"xx}"
    path.write_bytes(b"\n".join(lines) + b"\n")
    with Substrate(_cfg(path)) as m:
        assert m.recallable_count() == 4
        with pytest.raises(JournalCorruptError):
            m.verify()
    for f in _snapshots(path):
        f.unlink()
    with pytest.raises(JournalCorruptError):
        Substrate(_cfg(path))


def test_torn_tail_after_a_checkpoint_is_recovered(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        m.deposit("kept", [1.0, 0.0])
        m.checkpoint()
        m.deposit("tail", [0.0, 1.0])
        seq = m.seq
    with open(path, "ab") as fp:
        fp.write(encode_frame({"op": "note", "seq": seq + 1, "t": 1.0})[:-5])
    with Substrate(_cfg(path)) as m:
        assert m.recovered_tail_bytes > 0
        assert m.opened_from_checkpoint is not None
        m.deposit("after", [1.0, 1.0])
    with Substrate(_cfg(path)) as m:
        assert [x.payload for x in m.records()] == ["kept", "tail", "after"]
        assert m.verify()["matches"]


def test_erase_and_compact_remove_every_snapshot(tmp_path):
    path = tmp_path / "m.v5.journal"
    clock = ManualClock(T0)
    with Substrate(_cfg(path, clock)) as m:
        secret = m.deposit("secret payload", [1.0, 0.0])
        keep = m.deposit("kept", [0.0, 1.0])
        m.signal_attention({secret: 0.4})
        m.checkpoint()
        assert any(b"secret payload" in f.read_bytes() for f in _snapshots(path))
        m.erase([secret])
        assert _snapshots(path) == []  # the derived copy is gone with the erase
        m.checkpoint()
        assert not any(b"secret payload" in f.read_bytes() for f in _snapshots(path))
        m.compact()
        assert _snapshots(path) == []
        assert m.checkpoint() is None  # this handle's fold predates the rewrite
    assert b"secret payload" not in path.read_bytes()
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint is None
        assert m.checkpoint() is not None  # not short-circuited to the deleted one
        assert len(_snapshots(path)) == 1
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint is not None
        assert [x.entity_id for x in m.records()] == [keep]
        assert m.verify()["matches"]


def test_an_erase_during_a_checkpoint_discards_it(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        secret = m.deposit("secret payload", [1.0, 0.0])
        real_write = ckpt.write

        def write_then_erase(journal, image, *, fsync=True):
            out = real_write(journal, image, fsync=fsync)
            m.erase([secret])  # lands while the snapshot is outside the lock
            return out

        with mock.patch.object(ckpt, "write", write_then_erase):
            assert m.checkpoint() is None
        assert _snapshots(path) == []
        assert m._fold.last_checkpoint is None


def test_sleep_pass_checkpoints_when_configured(tmp_path):
    path = tmp_path / "m.v5.journal"
    clock = ManualClock(T0)
    with Substrate(_cfg(path, clock, checkpoint_every=10)) as m:
        for i in range(3):
            m.deposit(f"a{i}", [1.0, float(i)])
        assert m.run_sleep_pass().checkpoint_seq is None  # 5 events: not due
        for i in range(10):
            m.deposit(f"b{i}", [float(i), 1.0])
        r = m.run_sleep_pass()
        assert r.checkpoint_seq == m.seq
        assert m.run_sleep_pass().checkpoint_seq is None  # 1 event since: not due
    with Substrate(_cfg(path, clock)) as m:
        assert m.opened_from_checkpoint == r.checkpoint_seq - 1
        assert m.verify()["matches"]
    with pytest.raises(ValueError, match="checkpoint_every"):
        Substrate(_cfg(tmp_path / "x", checkpoint_every=0))


def test_checkpoint_is_idempotent_and_ephemeral_stores_have_none(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        m.deposit("a", [1.0, 0.0])
        seq = m.checkpoint()
        assert m.checkpoint() == seq  # nothing written since
        assert len(_snapshots(path)) == 1
    with Substrate(Config.ephemeral()) as m:
        m.deposit("a", [1.0, 0.0])
        assert m.checkpoint() is None


def test_configured_dim_is_not_baked_into_a_snapshot(tmp_path):
    """A dim from Config (not the journal) must not become journal state."""
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        pass  # genesis without a dim
    with Substrate(_cfg(path, embedding_dim=4)) as m:
        assert m.dim == 4
        m.checkpoint()
    with Substrate(_cfg(path)) as m:
        assert m.opened_from_checkpoint is not None
        assert m.dim is None
        assert _same_state(m._fold, _genesis_fold(path))
        m.deposit("wide", [1.0, 0.0, 0.0, 0.0, 0.0])


def test_old_and_new_units_reload_exactly_across_summation_modes(tmp_path):
    """A snapshot from an interpreter that sums differently recomputes unit vectors."""
    path = tmp_path / "m.v5.journal"
    with Substrate(_cfg(path)) as m:
        for i in range(20):
            m.deposit(f"r{i}", [0.1 * i + 0.3, 1e-3 * i, 7.0 / (i + 1), -0.2])
        m.checkpoint()
    with mock.patch.object(ckpt, "_COMPENSATED_SUM", not ckpt._COMPENSATED_SUM):
        with Substrate(_cfg(path)) as m:
            assert m.opened_from_checkpoint is not None
            assert _same_state(m._fold, _genesis_fold(path))


def test_facade_open_never_scans_the_journal_for_snapshot_hashes(tmp_path):
    """compat._journal_known_shas answers from fold state, not a full journal scan."""
    from moneta.v5.compat import Moneta, journal_path_for

    from .test_compat import H as COMPAT_H
    from .test_compat import _build_v1_store
    from .test_compat import _cfg as compat_cfg

    _build_v1_store(tmp_path)
    with Moneta(compat_cfg(tmp_path, half_life_seconds=COMPAT_H), fsync=False) as m:
        m.v5.close()  # a crash: no close-time export, so snapshot.json is the migrated v1 one
        m.durability = None
    journal = journal_path_for(compat_cfg(tmp_path))
    journal.with_name(journal.name + ".v1export").unlink()  # and no sidecar
    with mock.patch.object(FileJournal, "events", side_effect=AssertionError("full scan")):
        with Moneta(compat_cfg(tmp_path, half_life_seconds=COMPAT_H)) as m:
            assert m.ecs.n == 3


def test_reopen_budget_with_a_checkpoint(tmp_path):
    """The tested reopen budget: 50k events, checkpoint near the end, open << 1 s."""
    path = tmp_path / "m.v5.journal"
    clock = ManualClock(T0)
    with Substrate(_cfg(path, clock)) as m:
        ids = [m.deposit(f"r{i}", [1.0, float(i % 13), float(i % 5)]) for i in range(200)]
        for i in range(50_000):
            m.signal_attention({ids[i % 200]: 0.01}, t=T0 + i)
        m.checkpoint()
        for i in range(100):
            m.signal_attention({ids[i]: 0.01}, t=T0 + 60_000 + i)
    started = time.perf_counter()
    with Substrate(_cfg(path, clock)) as m:
        elapsed = time.perf_counter() - started
        assert m.replayed_at_open == 101  # checkpoint event + the 100-event tail
        assert m.seq > 50_000
    assert elapsed < 1.0, f"reopen took {elapsed:.3f}s"
