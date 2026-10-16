"""Round 4 E3 blocking conditions 1 and 2: the writer lock's scope.

1. A sleep pass projects with the writer lock released: it takes the batch
   under the lock, projects with no lock held, then appends ``consolidate``
   under the lock. Records that change meanwhile and failed batches keep
   their meaning; passes and close stay serialized.
2. The v1-format export copies rows under the lock and serializes, writes
   and fsyncs outside it.

Each "no lock held" test proves it from another thread: a recall that must
finish while the projector or the export writer is still blocked.
"""

from __future__ import annotations

import collections
import hashlib
import json
import threading
import time
from uuid import UUID

import pytest

from moneta.consolidation import MAX_BATCH_SIZE
from moneta.v5 import Config, MemoryProjector, Status, Substrate, SubstrateClosedError
from moneta.v5 import compat as _compat
from moneta.v5.compat import export_v1_snapshot

T0 = 1_000_000.0
H = 3600.0
T_PASS = T0 + 2 * H  # u = 0.25 after a full-strength anchor: staged when attended >= 3


def _stage(m: Substrate, n: int) -> list[UUID]:
    """Deposit ``n`` records that the pass at ``T_PASS`` stages (attended 3x)."""
    ids = [m.deposit(f"m{i}", [1.0, float(i % 7) + 0.5], t=T0) for i in range(n)]
    for _ in range(3):
        m.signal_attention({e: 1.0 for e in ids}, t=T0)
    return ids


def _recall_from_another_thread(m: Substrate, timeout: float = 5.0) -> bool:
    """True when a recall on another thread completes within ``timeout``."""
    done = threading.Event()

    def reader() -> None:
        m.recall([1.0, 0.5], 3, t=T_PASS)
        done.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout)
    return done.is_set()


def _consolidate_events(m: Substrate) -> list[dict]:
    return [e for e in m._journal.events() if e.get("op") == "consolidate"]


# -- condition 1: projection outside the writer lock ----------------------


class _ProbingProjector(MemoryProjector):
    """Records, from inside project(), whether readers can get through."""

    name = "probe"

    def __init__(self, m_ref: list[Substrate]) -> None:
        super().__init__()
        self.m_ref = m_ref
        self.reader_got_through: list[bool] = []
        self.lock_held_by_pass: list[bool] = []

    def project(self, memories, t):
        m = self.m_ref[0]
        self.lock_held_by_pass.append(m._lock._is_owned())
        self.reader_got_through.append(_recall_from_another_thread(m))
        return super().project(memories, t)


def test_projection_runs_with_the_writer_lock_released():
    holder: list[Substrate] = []
    proj = _ProbingProjector(holder)
    m = Substrate(Config.ephemeral(half_life_seconds=H, projector=proj))
    holder.append(m)
    ids = _stage(m, MAX_BATCH_SIZE + 3)
    r = m.run_sleep_pass(t=T_PASS)
    assert r.projection_error is None
    assert set(r.consolidated_ids) == set(ids)
    assert proj.lock_held_by_pass == [False, False]  # two batches, neither under the lock
    assert proj.reader_got_through == [True, True]
    m.close()


def test_records_that_die_during_projection_are_not_consolidated(tmp_path):
    holder: list[Substrate] = []

    class Killer(MemoryProjector):
        name = "killer"

        def project(self, memories, t):
            m = holder[0]
            # Legal now: the pass holds no substrate lock while projecting.
            m.tombstone([memories[0].entity_id], t=t)
            m.erase([memories[1].entity_id], t=t)
            return super().project(memories, t)

    path = tmp_path / "m.v5.journal"
    m = Substrate(Config(path=path, fsync=False, half_life_seconds=H, projector=Killer()))
    holder.append(m)
    ids = _stage(m, 5)
    r = m.run_sleep_pass(t=T_PASS)
    assert r.projection_error is None
    assert m.status_of(ids[0]) == Status.TOMBSTONED
    assert m.status_of(ids[1]) == Status.ERASED
    assert all(m.status_of(e) == Status.CONSOLIDATED for e in ids[2:])
    assert r.consolidated_ids == tuple(ids[2:])
    (event,) = _consolidate_events(m)
    assert event["ids"] == [str(e) for e in ids[2:]]
    # The derived copies already written for the two dead records stay named.
    assert event["projected_dead"] == [str(ids[0]), str(ids[1])]
    live = {e: m.status_of(e) for e in ids}
    m.close()
    with Substrate(Config(path=path, fsync=False, half_life_seconds=H)) as again:
        assert {e: again.status_of(e) for e in ids} == live  # replay == live


def test_a_failed_batch_keeps_earlier_batches_and_the_next_pass_retries_the_rest():
    class FailsSecond(MemoryProjector):
        name = "flaky"
        calls = 0

        def project(self, memories, t):
            self.calls += 1
            if self.calls == 2:
                raise OSError("disk full")
            return super().project(memories, t)

    flaky = FailsSecond()
    m = Substrate(Config.ephemeral(half_life_seconds=H, projector=flaky))
    ids = _stage(m, 2 * MAX_BATCH_SIZE + 200)
    r = m.run_sleep_pass(t=T_PASS)
    assert r.projection_error == "OSError: disk full"
    assert r.consolidated_ids == tuple(ids[:MAX_BATCH_SIZE])
    assert all(m.status_of(e) == Status.STAGED for e in ids[MAX_BATCH_SIZE:])
    assert r.seq == m.seq  # the last event the pass appended
    good = MemoryProjector()
    m._projector = good  # the disk recovers
    r2 = m.run_sleep_pass(t=T_PASS + 60)
    assert r2.projection_error is None
    assert r2.consolidated_ids == tuple(ids[MAX_BATCH_SIZE:])
    assert [len(b) for _, b in good.batches] == [MAX_BATCH_SIZE, 200]
    assert all(m.status_of(e) == Status.CONSOLIDATED for e in ids)
    m.close()


def test_concurrent_sleep_passes_project_each_record_once():
    class Slow(MemoryProjector):
        name = "slow"

        def project(self, memories, t):
            time.sleep(0.05)
            return super().project(memories, t)

    slow = Slow()
    m = Substrate(Config.ephemeral(half_life_seconds=H, projector=slow))
    ids = _stage(m, 2 * MAX_BATCH_SIZE + 10)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(m.run_sleep_pass(t=T_PASS)))
        for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seen = collections.Counter(mem.entity_id for _, batch in slow.batches for mem in batch)
    assert set(seen) == set(ids)
    assert set(seen.values()) == {1}
    assert sum(len(r.consolidated_ids) for r in results) == len(ids)
    m.close()


def test_close_waits_for_an_in_flight_projection():
    entered, release = threading.Event(), threading.Event()

    class Blocking(MemoryProjector):
        name = "blocking"
        closed = False
        closed_mid_project = False

        def project(self, memories, t):
            entered.set()
            release.wait(10)
            self.closed_mid_project = self.closed
            return super().project(memories, t)

        def close(self):
            self.closed = True

    proj = Blocking()
    m = Substrate(Config.ephemeral(half_life_seconds=H, projector=proj))
    _stage(m, 3)
    out: list = []
    passer = threading.Thread(target=lambda: out.append(m.run_sleep_pass(t=T_PASS)))
    passer.start()
    assert entered.wait(10)
    assert _recall_from_another_thread(m)  # readers are not blocked meanwhile
    closer = threading.Thread(target=m.close)
    closer.start()
    closer.join(0.2)
    assert closer.is_alive()  # close waits for the pass
    release.set()
    passer.join(10)
    closer.join(10)
    assert not closer.is_alive() and m.closed
    assert proj.closed and not proj.closed_mid_project
    assert out[0].projection_error is None and len(out[0].consolidated_ids) == 3


# -- condition 2: export outside the writer lock -------------------------


def test_export_writes_with_the_writer_lock_released(tmp_path, monkeypatch):
    m = Substrate(Config(path=tmp_path / "m.v5.journal", fsync=False, half_life_seconds=H))
    _stage(m, 20)
    real = _compat._write_export
    seen: list[tuple[bool, bool]] = []

    def probing(snap, path):
        seen.append((m._lock._is_owned(), _recall_from_another_thread(m)))
        return real(snap, path)

    monkeypatch.setattr(_compat, "_write_export", probing)
    export_v1_snapshot(m, tmp_path / "snapshot.json")
    assert seen == [(False, True)]
    m.close()


def test_chunked_export_is_byte_identical_to_one_json_dumps(tmp_path, monkeypatch):
    monkeypatch.setattr(_compat, "_EXPORT_CHUNK_BYTES", 64)  # many chunks
    m = Substrate(Config(path=tmp_path / "m.v5.journal", fsync=False, half_life_seconds=H))
    ids = _stage(m, 30)
    extra = m.deposit('café ☃ "quoted"', [0.25, -1.5], t=T0)
    m.tombstone([ids[3]], t=T0 + 1)  # not exported
    m.run_sleep_pass(t=T_PASS)  # mixed LIVE / CONSOLIDATED states
    snap = tmp_path / "snapshot.json"
    sha = export_v1_snapshot(m, snap)
    data = snap.read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha
    doc = json.loads(data)
    assert json.dumps(doc).encode("utf-8") == data
    assert [r["entity_id"] for r in doc["rows"]] == [str(e) for e in ids if e != ids[3]] + [
        str(extra)
    ]
    assert {r["state"] for r in doc["rows"]} == {0, 2}  # VOLATILE and CONSOLIDATED rows
    assert doc["moneta_v5"] == {"seq": m.seq, "format": "v1-export"}
    assert sha in _compat._read_known_shas(m.journal_path)
    m.close()


def test_exports_racing_writers_each_match_the_seq_they_claim(tmp_path):
    m = Substrate(Config(path=tmp_path / "m.v5.journal", fsync=False, half_life_seconds=H))
    m.deposit("seed", [1.0, 0.0], t=T0)
    stop = threading.Event()

    def writer() -> None:
        i = 0
        while not stop.is_set():
            m.deposit(f"w{i}", [1.0, float(i)], t=T0)
            i += 1

    w = threading.Thread(target=writer)
    w.start()
    try:
        for k in range(5):
            snap = tmp_path / f"s{k}.json"
            export_v1_snapshot(m, snap)
            doc = json.loads(snap.read_bytes())
            # Every deposit is one event after genesis, so seq pins the row count.
            assert len(doc["rows"]) == doc["moneta_v5"]["seq"] - 1
    finally:
        stop.set()
        w.join()
    m.close()


def test_export_of_a_closed_handle_raises_before_writing(tmp_path):
    m = Substrate(Config(path=tmp_path / "m.v5.journal", fsync=False, half_life_seconds=H))
    m.close()
    snap = tmp_path / "snapshot.json"
    with pytest.raises(SubstrateClosedError):
        export_v1_snapshot(m, snap)
    assert not snap.exists()
