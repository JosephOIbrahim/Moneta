"""Attention durability across snapshot and restart: the B/D regression and R1′.

Deposits and attention are tested separately on purpose. Deposits are
snapshot-covered (docs/api.md volatility table); attention is WAL-covered.

SYNAPSE's save() is ``m.durability.snapshot_ecs(m.ecs)``
(tests/v5/test_compat.py:66). ``Moneta.close()`` does NOT snapshot and
writes nothing to the store's files, so close() + Moneta(cfg) models a
restart / kill -9. Where the first handle has to stay alive, a crash is
modelled by copying the store's files as they are and opening the copies
(``_crash_copy``).

Characterization, first pinned at v1.3.0-rc1:
  A  deposit -> snapshot -> reopen: memory present             PASS
  A2 deposit after the last snapshot -> reopen: memory absent  PASS (documented window)
  B  attention -> snapshot (no sleep pass) -> reopen -> sleep  PASS under R1′ (was strict XFAIL, defect B)
  C  attention -> reopen (no intervening snapshot) -> sleep    PASS (WAL replay works)
  D  attention landing between drain and snapshot in a pass    PASS under R1′ (was strict XFAIL, defect D)
  E  hydrate's ts filter drops pre-snapshot no-seq WAL lines   PASS (the rc1 rule still governs no-seq lines)

B and D were unresolved defects pinned with ``xfail(strict=True)``. R1′
(docs/design/R1-attention-durability.md §2) fixes both, so the marks are
gone and both must pass as written.

Everything after E is the R1′ suite of design §4.2, one test (or one
parametrized family) per table row, named ``test_<ID>_...``. The gate 6
acceptance rows are H, Q (a-c) and J. Gate 3 ruled that the reducer records
seqs BEFORE ``apply_attention`` (a stated loss over a silent double), so
AB(c) asserts that loss rather than the table's apply-then-record wording.
Every fault is injected into ``moneta.durability`` only (its ``os``, its
``time``, its ``_sleep``), never into the process-wide modules.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

import moneta.api as api_mod
import moneta.attention_log as attn_mod
import moneta.durability as dur_mod
from moneta import Moneta, MonetaConfig, MonetaResourceLockedError
from moneta.attention_log import AttentionEntry, reduce_attention_log
from moneta.durability import _split_raw_lines, snapshot_tmp_path, wal_tmp_path
from moneta.ecs import ECS


def _cfg(tmp_path: Path, name: str) -> MonetaConfig:
    return MonetaConfig(
        storage_uri=f"moneta-test://attn-snap/{name}",
        snapshot_path=tmp_path / "snapshot.json",
        wal_path=tmp_path / "attention.wal.jsonl",
        half_life_seconds=60.0,  # MIN_HALF_LIFE_SECONDS; makes decay visible
    )


def _save(m: Moneta) -> None:
    """SYNAPSE's save(): the bare snapshot call, no sleep pass."""
    assert m.durability is not None
    m.durability.snapshot_ecs(m.ecs)


# ---------------------------------------------------------------- deposits


def test_A_deposit_survives_snapshot_and_reopen(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "A")
    with Moneta(cfg) as m1:
        eid = m1.deposit("mem_A", [1.0, 0.0])
        _save(m1)
    with Moneta(cfg) as m2:
        mem = m2.ecs.get_memory(eid)
        assert mem is not None and mem.payload == "mem_A"
        assert m2.vector_index.contains(eid)


def test_A2_deposit_after_last_snapshot_is_lost(tmp_path: Path) -> None:
    """Characterization of the documented deposit volatility window."""
    cfg = _cfg(tmp_path, "A2")
    with Moneta(cfg) as m1:
        a = m1.deposit("saved", [1.0, 0.0])
        _save(m1)
        b = m1.deposit("unsaved", [0.0, 1.0])
    with Moneta(cfg) as m2:
        assert m2.ecs.contains(a)
        assert not m2.ecs.contains(b)  # no deposit journal in v1


# --------------------------------------------------------------- attention


def test_B_undrained_attention_survives_snapshot_and_reopen(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path, "B")
    with Moneta(cfg) as m1:
        attended = m1.deposit("attended", [1.0, 0.0])
        control = m1.deposit("control", [0.0, 1.0])
        _save(m1)                                # save-on-add
        m1.signal_attention({attended: 0.5})     # WAL-appended, undrained
        _save(m1)                                # save again, no sleep pass
    time.sleep(0.05)  # let the control row decay measurably
    with Moneta(cfg) as m2:                      # restart
        result = m2.run_sleep_pass()
        a = m2.ecs.get_memory(attended)
        c = m2.ecs.get_memory(control)
        assert a is not None and c is not None
        # utility reflects the attention: min(1, U + 0.5) = 1.0, then Δt=0 decay
        assert a.utility == 1.0 and c.utility < 1.0, (a.utility, c.utility)
        assert a.attended_count == 1
        assert result.attention_updated == 1


def test_C_attention_wal_replay_without_intervening_snapshot(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path, "C")
    with Moneta(cfg) as m1:
        attended = m1.deposit("attended", [1.0, 0.0])
        control = m1.deposit("control", [0.0, 1.0])
        _save(m1)
        m1.signal_attention({attended: 0.5})
        # no second snapshot
    time.sleep(0.05)
    with Moneta(cfg) as m2:
        result = m2.run_sleep_pass()
        a = m2.ecs.get_memory(attended)
        c = m2.ecs.get_memory(control)
        assert a is not None and c is not None
        assert a.utility == 1.0 and c.utility < 1.0, (a.utility, c.utility)
        assert a.attended_count == 1
        assert result.attention_updated == 1


def test_D_attention_between_drain_and_pass_snapshot_survives(
    tmp_path: Path,
) -> None:
    """A signal that lands after run_pass drained the log but before
    run_sleep_pass's snapshot_ecs (api.py:455-467). Simulated by wrapping
    the runner; in production this is a concurrent signal_attention."""
    cfg = _cfg(tmp_path, "D")
    with Moneta(cfg) as m1:
        eid = m1.deposit("late", [1.0, 0.0])
        _save(m1)
        orig = m1.consolidation.run_pass

        def run_pass_then_signal(**kw):
            r = orig(**kw)
            m1.signal_attention({eid: 0.5})  # in buffer + WAL, after drain
            return r

        m1.consolidation.run_pass = run_pass_then_signal  # type: ignore[method-assign]
        m1.run_sleep_pass()  # snapshot_ecs then unlinks the WAL
        assert len(m1.attention) == 1  # still undrained in memory
    with Moneta(cfg) as m2:
        m2.run_sleep_pass()
        mem = m2.ecs.get_memory(eid)
        assert mem is not None
        assert mem.attended_count == 1


def test_E_hydrate_filters_wal_entries_older_than_snapshot(
    tmp_path: Path,
) -> None:
    """Pins durability.py:218. Matters for repair option (a): rewriting
    undrained entries into the WAL with their original timestamps would
    be silently filtered out on hydrate."""
    cfg = _cfg(tmp_path, "E")
    with Moneta(cfg) as m1:
        eid = m1.deposit("x", [1.0, 0.0])
        _save(m1)
    snap_ts = json.loads(cfg.snapshot_path.read_text())["snapshot_created_at"]  # type: ignore[union-attr]
    line = {"wal_version": 1, "entity_id": str(eid), "weight": 0.5}
    cfg.wal_path.write_text(  # type: ignore[union-attr]
        json.dumps({**line, "timestamp": snap_ts - 1.0}) + "\n"
        + json.dumps({**line, "entity_id": str(uuid4()), "timestamp": snap_ts + 1.0})
        + "\n"
    )
    with Moneta(cfg) as m2:
        assert len(m2.attention) == 1  # only the post-snapshot entry replays


# =====================================================================
# R1′ (design §4.2): helpers
# =====================================================================

_REAL_TIME = time.time
_WAIT = 10.0  # every Event.wait and Thread.join in this file is bounded
_KEYS = ("wal_applied_seqs", "wal_next_seq")


class _Crash(BaseException):
    """SystemExit-like: the process dies here. Not an ``Exception``."""


class _Clock:
    """Stands in for one module's ``time``: ``time()`` is shifted."""

    def __init__(self, offset: float) -> None:
        self.offset = offset

    def time(self) -> float:
        return _REAL_TIME() + self.offset

    def __getattr__(self, name: str) -> Any:
        return getattr(time, name)


class _Os:
    """Stands in for ``moneta.durability.os``: the named functions are
    replaced, everything else is the real module."""

    def __init__(self, **overrides: Callable[..., Any]) -> None:
        self.__dict__.update(overrides)

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


def _store(root: Path, name: str = "s") -> MonetaConfig:
    root.mkdir(parents=True, exist_ok=True)
    return MonetaConfig(
        storage_uri=f"moneta-test://r1p/{name}/{uuid4().hex}",
        snapshot_path=root / "snapshot.json",
        wal_path=root / "attention.wal.jsonl",
        half_life_seconds=3600.0,
    )


def _crash_copy(cfg: MonetaConfig, dest: Path) -> MonetaConfig:
    """kill -9 now: copy the store's files as they are into ``dest`` and
    return a config on the copies. The live handle keeps its own files."""
    new = _store(dest, "crash")
    assert not new.snapshot_path.exists() and not new.wal_path.exists()
    for src, dst in (
        (cfg.snapshot_path, new.snapshot_path),
        (cfg.wal_path, new.wal_path),
    ):
        if src.exists():
            shutil.copyfile(src, dst)
    return new


def _snap(cfg: MonetaConfig) -> dict:
    return json.loads(cfg.snapshot_path.read_text(encoding="utf-8"))


def _wal(cfg: MonetaConfig) -> bytes | None:
    return cfg.wal_path.read_bytes() if cfg.wal_path.exists() else None


def _wal_lines(cfg: MonetaConfig) -> list[dict]:
    """Every non-blank raw line of a clean WAL, parsed."""
    data = _wal(cfg)
    if data is None:
        return []
    return [json.loads(raw) for raw in _split_raw_lines(data) if raw.strip()]


def _wal_seqs(cfg: MonetaConfig) -> list[int]:
    return [d["seq"] for d in _wal_lines(cfg)]


def _buffer_seqs(m: Moneta) -> list[int | None]:
    return [seq for _, seq in m.attention._buffer]


def _attended(m: Moneta, eid: UUID) -> int:
    mem = m.ecs.get_memory(eid)
    assert mem is not None, eid
    return mem.attended_count


def _row_attended(snapshot: dict, eid: UUID) -> int:
    rows = [r for r in snapshot["rows"] if r["entity_id"] == str(eid)]
    assert len(rows) == 1, (eid, len(rows))
    return rows[0]["attended_count"]


def _apply_now(m: Moneta) -> Any:
    """The sleep pass without its save: drain, record, apply, decay and
    classify. The applied lines stay in the WAL until the next save."""
    return m.consolidation.run_pass(
        ecs=m.ecs,
        decay=m.decay,
        attention_log=m.attention,
        vector_index=m.vector_index,
        sequential_writer=m.sequential_writer,
        now=api_mod.time.time(),
    )


def _line(eid: UUID, ts: float, seq: Any = None, weight: float = 0.5) -> bytes:
    """One WAL line in rc1's key order, plus ``seq`` when given; os.linesep."""
    d: dict[str, Any] = {
        "wal_version": 1,
        "entity_id": str(eid),
        "weight": weight,
        "timestamp": ts,
    }
    if seq is not None:
        d["seq"] = seq
    return (json.dumps(d) + os.linesep).encode("utf-8")


def _strip_keys(cfg: MonetaConfig) -> dict:
    """A foreign rewrite (or an rc1 save) that drops the R1′ snapshot keys."""
    snap = _snap(cfg)
    for k in _KEYS:
        snap.pop(k, None)
    cfg.snapshot_path.write_text(json.dumps(snap), encoding="utf-8")
    return snap


def _write_snap(cfg: MonetaConfig, snap: dict) -> None:
    cfg.snapshot_path.write_text(json.dumps(snap), encoding="utf-8")


def _messages(caplog: pytest.LogCaptureFixture, level: int, needle: str) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == level and needle in r.getMessage()
    ]


def _fail_replace_of(path: Path) -> tuple[Callable[..., Any], list[str]]:
    """An ``os.replace`` for ``_Os`` that refuses to install ``path``, as a
    foreign handle without share-delete would on Windows."""
    calls: list[str] = []

    def replace(src: Any, dst: Any, *a: Any, **k: Any) -> None:
        if Path(src) == Path(path):
            calls.append(str(src))
            raise PermissionError(13, "simulated: destination held open", str(dst))
        os.replace(src, dst, *a, **k)

    return replace, calls


def _crash_at_step_3(applied: frozenset) -> None:
    """Stands in for ``_compact_wal``: the process dies after step 2."""
    raise _Crash("process died after the snapshot replace, before step 3")


def _rc1_read(
    snapshot_path: Path, wal_path: Path
) -> tuple[dict[UUID, int], list[AttentionEntry]]:
    """FROZEN copy of rc1's reader (v1.3.0-rc1 c33bbd9, durability.py
    ``wal_read`` plus hydrate's ``timestamp > snapshot_created_at`` filter),
    returning ``({entity: attended_count}, replayed entries)``. Do not
    update it: it is what an rc1 build runs on an R1′ store."""
    entries: list[AttentionEntry] = []
    if wal_path.exists():
        with open(wal_path, encoding="utf-8") as fp:
            for raw in fp:
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entries.append(
                    AttentionEntry(
                        UUID(d["entity_id"]),
                        float(d["weight"]),
                        float(d["timestamp"]),
                    )
                )
    if not snapshot_path.exists():
        return {}, entries
    with open(snapshot_path, encoding="utf-8") as fp:
        snapshot = json.load(fp)
    snapshot_ts = float(snapshot.get("snapshot_created_at", 0.0))
    rows = {
        UUID(r["entity_id"]): int(r["attended_count"])
        for r in snapshot.get("rows", [])
    }
    replay = [e for e in entries if e.timestamp > snapshot_ts]
    return rows, replay


def _rc1_attended(cfg: MonetaConfig, eid: UUID) -> int:
    """``eid``'s attended_count after an rc1 build opens these files and
    runs one sleep pass: its row's count plus every replayed entry."""
    rows, replay = _rc1_read(cfg.snapshot_path, cfg.wal_path)
    return rows[eid] + sum(1 for e in replay if e.entity_id == eid)


def _run(errors: list, fn: Callable[[], Any]) -> Callable[[], None]:
    """A thread target that records any exception instead of losing it."""

    def target() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - asserted by the test
            errors.append(exc)

    return target


# =====================================================================
# Gate 6 acceptance: H, Q (a-c), J
# =====================================================================


def test_H_rc1_store_replays_by_timestamp_then_lines_gain_seqs(tmp_path: Path) -> None:
    """§4.2 H: an rc1 store reopens exactly as rc1 reads it, and after the
    first save every WAL line carries a seq."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
    t = _strip_keys(cfg)["snapshot_created_at"]  # an rc1 snapshot
    cfg.wal_path.write_bytes(_line(x, t - 1.0) + _line(x, t + 1.0) + _line(y, t + 2.0))
    _, rc1_replay = _rc1_read(cfg.snapshot_path, cfg.wal_path)
    assert [(e.entity_id, e.timestamp) for e in rc1_replay] == [(x, t + 1.0), (y, t + 2.0)]

    with Moneta(cfg) as m:
        assert [e for e, _ in m.attention._buffer] == rc1_replay  # identical to rc1
        seqs = _buffer_seqs(m)
        assert all(type(s) is int for s in seqs) and len(set(seqs)) == 2
        assert m.durability._disposition == [None, (seqs[0], True), (seqs[1], True)]
        _save(m)  # first save: step 0 normalizes, then a keyed snapshot
        assert m.durability._disposition == []
        assert _snap(cfg)["wal_applied_seqs"] == []
        assert [
            (UUID(d["entity_id"]), d["timestamp"], d["seq"]) for d in _wal_lines(cfg)
        ] == [(x, t + 1.0, seqs[0]), (y, t + 2.0, seqs[1])]
    with Moneta(cfg) as m:  # membership decides now: each line exactly once
        assert _buffer_seqs(m) == seqs
        m.run_sleep_pass()
        assert (_attended(m, x), _attended(m, y)) == (1, 1)
    with Moneta(cfg) as m:
        assert len(m.attention) == 0
        assert (_attended(m, x), _attended(m, y)) == (1, 1)


def test_Q_a_rc1_reader_after_a_clean_save(tmp_path: Path) -> None:
    """§4.2 Q(a): an rc1 reader never double-applies after a clean R1′ save;
    it loses the pending ``ts <= T`` lines (characterization)."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
        m.signal_attention({x: 0.5})
        m.run_sleep_pass()  # applied, and its save compacts the line away
        m.signal_attention({x: 0.5})  # pending
        m.signal_attention({y: 0.5})  # pending
        time.sleep(0.002)
        _save(m)
    snap = _snap(cfg)
    lines = _wal_lines(cfg)
    assert snap["wal_applied_seqs"] == [] and len(lines) == 2
    assert all(d["timestamp"] <= snap["snapshot_created_at"] for d in lines)
    _, replay = _rc1_read(cfg.snapshot_path, cfg.wal_path)
    assert replay == []
    assert _rc1_attended(cfg, x) == 1  # true count 2: one lost, none doubled
    assert _rc1_attended(cfg, y) == 0  # true count 1: lost
    with Moneta(cfg) as m:  # R1′ on the same files keeps both
        m.run_sleep_pass()
        assert (_attended(m, x), _attended(m, y)) == (2, 1)


def _applied_and_pending(m: Moneta) -> tuple[UUID, int, int]:
    """x deposited and saved; s1 applied in memory (line still in the WAL),
    s2 pending. Returns ``(x, s1, s2)``."""
    x = m.deposit("x", [1.0, 0.0])
    _save(m)
    m.signal_attention({x: 0.5})
    (s1,) = _buffer_seqs(m)
    _apply_now(m)
    m.signal_attention({x: 0.5})
    (s2,) = _buffer_seqs(m)
    time.sleep(0.002)
    return x, s1, s2


def _assert_rc1_view_of_s1_applied_s2_pending(cfg: MonetaConfig, x: UUID, s1: int, s2: int) -> None:
    snap = _snap(cfg)
    assert snap["wal_applied_seqs"] == [s1] and _row_attended(snap, x) == 1
    assert _wal_seqs(cfg) == [s1, s2]
    assert all(d["timestamp"] <= snap["snapshot_created_at"] for d in _wal_lines(cfg))
    _, replay = _rc1_read(cfg.snapshot_path, cfg.wal_path)
    assert replay == []  # s1 filtered (no double), s2 filtered (lost)
    assert _rc1_attended(cfg, x) == 1  # true count 2
    with Moneta(cfg) as r:  # R1′ on the same files: exactly once each
        assert _buffer_seqs(r) == [s2]
        r.run_sleep_pass()
        assert _attended(r, x) == 2


def test_Q_b_rc1_reader_after_a_crash_between_steps_2_and_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 Q(b): the applied line is still in the WAL; rc1 filters it."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1, s2 = _applied_and_pending(m)
        with monkeypatch.context() as mp:
            mp.setattr(m.durability, "_compact_wal", _crash_at_step_3)
            with pytest.raises(_Crash):
                _save(m)
    finally:
        m.close()  # writes nothing: the files are the crash state
    _assert_rc1_view_of_s1_applied_s2_pending(cfg, x, s1, s2)


def test_Q_c_rc1_reader_after_a_K_path_save_then_a_clean_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 Q(c): compaction failed (K path), then a clean close."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1, s2 = _applied_and_pending(m)
        replace, calls = _fail_replace_of(wal_tmp_path(cfg.wal_path))
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(replace=replace))
            with pytest.raises(PermissionError):
                _save(m)
        assert len(calls) == 1
    finally:
        m.close()
    _assert_rc1_view_of_s1_applied_s2_pending(cfg, x, s1, s2)


def test_Q_d_rc1_reader_double_applies_when_the_signal_clock_runs_ahead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 Q(d): as (b), with ``moneta.api.time`` ahead of durability's
    clock. rc1 double-applies (characterization of the broken clock
    precondition); R1′ decides by membership and does not."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        with monkeypatch.context() as mp:
            mp.setattr(api_mod, "time", _Clock(100.0))
            m.signal_attention({x: 0.5})
            (s1,) = _buffer_seqs(m)
            _apply_now(m)
        with monkeypatch.context() as mp:
            mp.setattr(m.durability, "_compact_wal", _crash_at_step_3)
            with pytest.raises(_Crash):
                _save(m)
    finally:
        m.close()
    snap = _snap(cfg)
    (line,) = _wal_lines(cfg)
    assert line["seq"] == s1 and snap["wal_applied_seqs"] == [s1]
    assert line["timestamp"] > snap["snapshot_created_at"]  # precondition broken
    assert _row_attended(snap, x) == 1
    _, replay = _rc1_read(cfg.snapshot_path, cfg.wal_path)
    assert len(replay) == 1
    assert _rc1_attended(cfg, x) == 2  # rc1: DOUBLE apply
    with Moneta(cfg) as r:
        assert len(r.attention) == 0
        r.run_sleep_pass()
        assert _attended(r, x) == 1


def test_J_step0_failure_degrades_and_still_persists_the_deposit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 J (gate 6): a step 0 failure writes a keyless snapshot with the
    new deposit, leaves the WAL untouched, and the next save recovers."""
    caplog.set_level(logging.INFO, logger="moneta")
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    t = _snap(cfg)["snapshot_created_at"]
    # test E's shape: a filtered legacy line, then a replayed legacy line
    cfg.wal_path.write_bytes(_line(x, t - 1.0) + _line(x, t + 0.001))
    m = Moneta(cfg)
    try:
        dm = m.durability
        (seq,) = _buffer_seqs(m)
        assert dm._disposition == [None, (seq, True)]
        reduce_attention_log(m.attention, m.ecs, m.decay, time.time())
        assert _attended(m, x) == 1 and m.attention.applied_seqs == {seq}
        y = m.deposit("y", [0.0, 1.0])
        time.sleep(0.01)  # T_new > t + 0.001: the clock precondition holds
        wal_before = _wal(cfg)
        replace, calls = _fail_replace_of(wal_tmp_path(cfg.wal_path))
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(replace=replace))
            _save(m)  # returns: degraded, not raised
        assert len(calls) == 1
        snap = _snap(cfg)
        assert not any(k in snap for k in _KEYS)
        assert {r["entity_id"] for r in snap["rows"]} == {str(x), str(y)}
        assert _row_attended(snap, x) == 1
        assert dm.degraded_saves == 1
        assert len(_messages(caplog, logging.ERROR, "step 0 (WAL normalization) failed")) == 1
        assert len(_messages(caplog, logging.ERROR, "DEGRADED")) == 1
        assert _wal(cfg) == wal_before
        assert not wal_tmp_path(cfg.wal_path).exists()
        assert dm._disposition == [None, (seq, True)] and m.attention.applied_seqs == {seq}

        crash = _crash_copy(cfg, tmp_path / "crash1")
        with Moneta(crash) as r:  # a reopen now: the deposit, and no double
            assert r.ecs.contains(y)
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 1

        _save(m)  # unpatched: step 0 runs, then a keyed snapshot
        assert dm.degraded_saves == 1 and dm._disposition == []
        assert _snap(cfg)["wal_applied_seqs"] == [seq]
        assert _wal(cfg) is None  # its only kept line was applied
        crash = _crash_copy(cfg, tmp_path / "crash2")
        with Moneta(crash) as r:
            assert r.ecs.contains(y) and len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 1
    finally:
        m.close()


# =====================================================================
# §4.2: seq membership, the consistent read, the reducer
# =====================================================================


def test_F_non_prefix_drain_replays_exactly_the_unapplied_seq(tmp_path: Path) -> None:
    """§4.2 F: seqs 5 and 6 allocated, 6 applied, 5 arrives after the drain."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        a = m.deposit("a", [1.0, 0.0])
        b = m.deposit("b", [0.0, 1.0])
        _save(m)
        dm = m.durability
        dm._next_seq = 5
        now = time.time()
        assert dm.wal_append(AttentionEntry(a, 0.5, now)) == 5
        assert dm.wal_append(AttentionEntry(b, 0.5, now)) == 6
        m.attention.append(b, 0.5, now, seq=6)
        reduce_attention_log(m.attention, m.ecs, m.decay, time.time())
        m.attention.append(a, 0.5, now, seq=5)  # after the drain
        assert m.attention.applied_seqs == {6}
        time.sleep(0.002)
        _save(m)
        snap = _snap(cfg)
        assert snap["wal_applied_seqs"] == [6] and snap["wal_next_seq"] == 7
        assert _wal_seqs(cfg) == [5]  # 5's ts <= T: only membership keeps it
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert _buffer_seqs(r) == [5]  # 5 replays, 6 does not
            r.run_sleep_pass()
            assert (_attended(r, a), _attended(r, b)) == (1, 1)
        m.run_sleep_pass()
        assert (_attended(m, a), _attended(m, b)) == (1, 1)
    finally:
        m.close()
    with Moneta(cfg) as r:
        assert len(r.attention) == 0
        assert (_attended(r, a), _attended(r, b)) == (1, 1)


def test_F2_save_retries_while_a_reducer_is_mid_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 F2: the save runs on another thread, sees the reducer's token,
    retries, and pairs rows and seqs only after the apply."""
    monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 5.0)
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    entered, release, spun = threading.Event(), threading.Event(), threading.Event()
    spins: list[float] = []
    errors: list = []
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (seq,) = _buffer_seqs(m)
        orig_apply = m.ecs.apply_attention

        def blocking_apply(agg: Any, now: float) -> int:
            entered.set()
            assert release.wait(_WAIT)
            return orig_apply(agg, now)

        def counting_sleep(s: float) -> None:
            spins.append(s)
            spun.set()
            time.sleep(s)

        monkeypatch.setattr(m.ecs, "apply_attention", blocking_apply)
        monkeypatch.setattr(dur_mod, "_sleep", counting_sleep)
        reducer = threading.Thread(
            target=_run(errors, lambda: reduce_attention_log(m.attention, m.ecs, m.decay, time.time()))
        )
        saver = threading.Thread(target=_run(errors, lambda: _save(m)))
        reducer.start()
        assert entered.wait(_WAIT)
        assert len(m.attention._inflight) == 1
        saver.start()
        assert spun.wait(_WAIT)  # the save saw the token and retried
        release.set()
        reducer.join(_WAIT)
        saver.join(_WAIT)
        assert not reducer.is_alive() and not saver.is_alive()
        assert errors == []
        assert len(spins) >= 1
        assert m.durability.degraded_saves == 0
        snap = _snap(cfg)
        assert snap["wal_applied_seqs"] == [seq] and _row_attended(snap, x) == 1
        assert _wal(cfg) is None
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 1
    finally:
        release.set()
        m.close()


def test_F2_a_whole_pass_inside_the_row_build_forces_a_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 F2, the window check (§2.4 step 1): a reducer that starts and
    ends while the save builds its rows moves the epoch, so the save refuses
    to pair those rows with the seqs recorded after them, and reads again."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (seq,) = _buffer_seqs(m)
        real_build = dur_mod._build_rows
        builds: list[int] = []

        def build(ecs: Any) -> list:
            rows = real_build(ecs)  # rows without the signal's effect
            builds.append(1)
            if len(builds) == 1:  # then a whole pass, inside the window
                reduce_attention_log(m.attention, m.ecs, m.decay, time.time())
            return rows

        monkeypatch.setattr(dur_mod, "_build_rows", build)
        _save(m)
        assert len(builds) == 2  # the first read was refused
        assert m.durability.degraded_saves == 0
        snap = _snap(cfg)
        assert snap["wal_applied_seqs"] == [seq] and _row_attended(snap, x) == 1
        assert _wal(cfg) is None
    finally:
        m.close()


def test_AB_a_a_stuck_token_degrades_the_save_within_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AB(a): a token with no reducer behind it never hangs a save."""
    monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 0.2)
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        m.deposit("x", [1.0, 0.0])
        _save(m)
        stray = object()
        m.attention._inflight.add(stray)
        z = m.deposit("z", [0.0, 1.0])  # just before the save
        t0 = time.monotonic()
        _save(m)
        assert time.monotonic() - t0 < 3.0
        snap = _snap(cfg)
        assert not any(k in snap for k in _KEYS)
        assert str(z) in {r["entity_id"] for r in snap["rows"]}
        assert m.durability.degraded_saves == 1
        assert len(_messages(caplog, logging.ERROR, "consistent read timed out")) == 1
        m.attention._inflight.discard(stray)
        _save(m)
        assert m.durability.degraded_saves == 1
        assert _snap(cfg)["wal_applied_seqs"] == []


def test_AB_b_a_second_reducer_logs_and_still_runs_its_whole_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AB(b): a reducer that starts while another is mid-apply logs
    ERROR at entry, drains and applies its own swap, and its pass, including
    the pass's save, completes without raising."""
    monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 0.2)
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    entered, release = threading.Event(), threading.Event()
    r1_ident: list[int] = []
    errors: list = []
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        orig_apply = m.ecs.apply_attention

        def apply(agg: Any, now: float) -> int:
            if threading.get_ident() in r1_ident:
                entered.set()
                assert release.wait(_WAIT)
            return orig_apply(agg, now)

        monkeypatch.setattr(m.ecs, "apply_attention", apply)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)

        def r1() -> None:
            r1_ident.append(threading.get_ident())
            reduce_attention_log(m.attention, m.ecs, m.decay, time.time())

        t1 = threading.Thread(target=_run(errors, r1))
        t1.start()
        assert entered.wait(_WAIT)
        m.signal_attention({x: 0.5})
        (s2,) = _buffer_seqs(m)
        result = m.run_sleep_pass()  # R2, on this thread
        assert result.attention_updated == 1
        assert _attended(m, x) == 1  # R2's swap only; R1 is still blocked
        assert len(_messages(caplog, logging.ERROR, "concurrent attention reducer at entry")) == 1
        assert m.durability.degraded_saves == 1  # the pass's save ran, R1 in flight
        release.set()
        t1.join(_WAIT)
        assert not t1.is_alive() and errors == []
        assert _attended(m, x) == 2
        assert len(_messages(caplog, logging.ERROR, "concurrent attention reducer detected")) == 2
        _save(m)
        snap = _snap(cfg)
        assert snap["wal_applied_seqs"] == sorted([s1, s2]) and _row_attended(snap, x) == 2
        assert _wal(cfg) is None
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 2
    finally:
        release.set()
        m.close()


def test_AB_c_an_interrupt_inside_apply_is_a_stated_loss_not_a_double(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AB(c) under the gate 3 ruling: seqs are recorded before the
    apply, so an interrupted apply leaves its seq recorded without its
    effect; the next save drops the line (a stated loss, never a double)."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (seq,) = _buffer_seqs(m)
        epoch0 = m.attention._apply_epoch

        def apply(agg: Any, now: float) -> int:
            raise KeyboardInterrupt

        with monkeypatch.context() as mp:
            mp.setattr(m.ecs, "apply_attention", apply)
            with pytest.raises(KeyboardInterrupt):
                m.run_sleep_pass()
        assert m.attention._inflight == set()
        assert m.attention._apply_epoch is not epoch0
        assert len(_messages(caplog, logging.ERROR, "torn attention apply")) == 1
        assert m.attention.applied_seqs == {seq} and _attended(m, x) == 0
        _save(m)
        assert m.durability.degraded_saves == 0
        assert _snap(cfg)["wal_applied_seqs"] == [seq]  # keyed
        assert _wal(cfg) is None  # the line is gone: the stated loss
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 0  # lost, never doubled
    finally:
        m.close()


def test_AB_c2_an_interrupt_right_after_the_seq_record_is_a_logged_torn_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Design revision 6 (the reducer nit from the Architect review): the
    inner `try` opens before `applied_seqs.update`, so an async exception
    landing right after the record, before `apply_attention` runs, is
    logged as a torn apply and propagates. Before the fix that window was
    silent: the seq stayed recorded with no effect and no ERROR line."""

    class _RecordThenInterrupt(set):
        def update(self, *others: Any) -> None:
            super().update(*others)
            raise KeyboardInterrupt  # stands in for an async exception

    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (seq,) = _buffer_seqs(m)
        applied: list[Any] = []

        def apply(agg: Any, now: float) -> int:
            applied.append(agg)
            return 0

        with monkeypatch.context() as mp:
            mp.setattr(m.attention, "applied_seqs", _RecordThenInterrupt())
            mp.setattr(m.ecs, "apply_attention", apply)
            with pytest.raises(KeyboardInterrupt):
                m.run_sleep_pass()
            assert set(m.attention.applied_seqs) == {seq}
        torn = _messages(caplog, logging.ERROR, "torn attention apply")
        assert len(torn) == 1 and "1 of 1 drained WAL seq(s) recorded" in torn[0]
        assert applied == []  # the apply never ran
        assert m.attention._inflight == set()
        assert _attended(m, x) == 0
    finally:
        m.close()


def test_AB_d_overlapping_reducers_never_produce_a_torn_keyed_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AB(d): the revision 3 torn-read interleaving, driven step by step.
    R1 passes its entry check and stalls before registering; R2 registers,
    drains and blocks mid-apply; R1 registers, drains and blocks mid-apply;
    R2 finishes; a save runs while R1 is still in flight."""
    caplog.set_level(logging.INFO, logger="moneta")
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    names = ("r1_at_add", "r1_go", "r2_in_apply", "r2_go", "r1_in_apply", "r1_finish", "spun")
    ev = {k: threading.Event() for k in names}
    idents: dict[str, int] = {}
    errors: list = []
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        log = m.attention

        class GatedSet(set):
            def add(self, item: object) -> None:
                if threading.get_ident() == idents.get("r1"):
                    ev["r1_at_add"].set()
                    assert ev["r1_go"].wait(_WAIT)
                super().add(item)

        log._inflight = GatedSet()
        orig_apply = m.ecs.apply_attention

        def apply(agg: Any, now: float) -> int:
            me = threading.get_ident()
            if me == idents.get("r2"):
                ev["r2_in_apply"].set()
                assert ev["r2_go"].wait(_WAIT)
            elif me == idents.get("r1"):
                ev["r1_in_apply"].set()
                assert ev["r1_finish"].wait(_WAIT)
            return orig_apply(agg, now)

        monkeypatch.setattr(m.ecs, "apply_attention", apply)

        def reducer(name: str) -> Callable[[], None]:
            def body() -> None:
                idents[name] = threading.get_ident()
                reduce_attention_log(log, m.ecs, m.decay, time.time())

            return _run(errors, body)

        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        t1 = threading.Thread(target=reducer("r1"))
        t1.start()
        assert ev["r1_at_add"].wait(_WAIT)  # R1: entry check passed, not registered
        t2 = threading.Thread(target=reducer("r2"))
        t2.start()
        assert ev["r2_in_apply"].wait(_WAIT)  # R2: registered, drained s1
        m.signal_attention({x: 0.5})
        (s2,) = _buffer_seqs(m)
        ev["r1_go"].set()
        assert ev["r1_in_apply"].wait(_WAIT)  # R1: registered, drained s2
        ev["r2_go"].set()
        t2.join(_WAIT)
        assert not t2.is_alive()
        assert _attended(m, x) == 1 and len(log._inflight) == 1  # R1 in flight

        # A save on a third thread while R1 is in flight never accepts a read.
        monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 0.2)
        saver = threading.Thread(target=_run(errors, lambda: _save(m)))
        saver.start()
        saver.join(_WAIT)
        assert not saver.is_alive()
        assert m.durability.degraded_saves == 1
        assert not any(k in _snap(cfg) for k in _KEYS)

        # Again, releasing R1 during the spin: keyed, rows and seqs agree.
        monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 5.0)

        def spin(s: float) -> None:
            ev["spun"].set()
            time.sleep(s)

        monkeypatch.setattr(dur_mod, "_sleep", spin)
        saver = threading.Thread(target=_run(errors, lambda: _save(m)))
        saver.start()
        assert ev["spun"].wait(_WAIT)
        ev["r1_finish"].set()
        t1.join(_WAIT)
        saver.join(_WAIT)
        assert not t1.is_alive() and not saver.is_alive()
        assert errors == []
        assert m.durability.degraded_saves == 1
        snap = _snap(cfg)
        assert snap["wal_applied_seqs"] == sorted([s1, s2]) and _row_attended(snap, x) == 2
        assert len(_messages(caplog, logging.ERROR, "concurrent attention reducer detected")) == 2
        assert _messages(caplog, logging.ERROR, "concurrent attention reducer at entry") == []
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 2
    finally:
        for e in ev.values():
            e.set()
        m.close()


class _FaultySet(set):
    """An in-flight set whose first ``faults`` discards raise KeyboardInterrupt."""

    def __init__(self, faults: int) -> None:
        super().__init__()
        self.faults = faults

    def discard(self, item: object) -> None:
        if self.faults > 0:
            self.faults -= 1
            raise KeyboardInterrupt
        super().discard(item)


def test_AB_e_one_fault_in_the_reducer_finally_strands_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AB(e), one injected fault: the repeated discard removes the token."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.attention._inflight = _FaultySet(1)
        m.signal_attention({x: 0.5})
        with pytest.raises(KeyboardInterrupt):
            m.run_sleep_pass()
        assert len(m.attention._inflight) == 0
        assert _attended(m, x) == 1  # applied before the finally faulted
        caplog.clear()
        for expected in (2, 3):
            m.signal_attention({x: 0.5})
            m.run_sleep_pass()
            assert _attended(m, x) == expected
        _save(m)
        assert _messages(caplog, logging.ERROR, "concurrent attention reducer") == []
        assert m.durability.degraded_saves == 0
        assert len(_snap(cfg)["wal_applied_seqs"]) == 0 and _wal(cfg) is None
    with Moneta(cfg) as r:
        assert len(r.attention) == 0 and _attended(r, x) == 3


def test_AB_e_two_faults_strand_the_token_and_every_save_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AB(e), two injected faults: the token is stranded. Passes still
    apply and reach their saves; every save degrades; nothing escapes."""
    monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 0.1)
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.attention._inflight = _FaultySet(2)
        m.signal_attention({x: 0.5})
        with pytest.raises(KeyboardInterrupt):
            m.run_sleep_pass()
        assert len(m.attention._inflight) == 1  # stranded
        assert _attended(m, x) == 1
        for expected in (2, 3):
            caplog.clear()
            m.signal_attention({x: 0.5})
            wal_before = _wal(cfg)
            m.run_sleep_pass()  # no exception escapes
            assert _attended(m, x) == expected
            assert len(_messages(caplog, logging.ERROR, "concurrent attention reducer at entry")) == 1
            assert m.durability.degraded_saves == expected - 1
            assert not any(k in _snap(cfg) for k in _KEYS)
            assert _wal(cfg) == wal_before  # the WAL is kept whole
        _save(m)
        assert m.durability.degraded_saves == 3
    with Moneta(cfg) as m:  # a reopen clears the token
        assert m.attention._inflight == set()
        assert len(m.attention) == 0  # every line ts <= T_new: no double
        assert _attended(m, x) == 3
        _save(m)
        assert m.durability.degraded_saves == 0
        assert _snap(cfg)["wal_applied_seqs"] == []
        assert _wal(cfg) is None
    with Moneta(cfg) as r:
        assert len(r.attention) == 0 and _attended(r, x) == 3


# =====================================================================
# §4.2: crash points, legacy stores, foreign rewrites
# =====================================================================


def _crash_between_steps_2_and_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[MonetaConfig, UUID, UUID, int, int]:
    """G's state: x's signal s1 applied (in S); y's signal s2 lands after the
    drain (pending); the pass's save dies after its snapshot replace."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        orig = m.consolidation.run_pass

        def run_pass_then_signal(**kw: Any) -> Any:
            r = orig(**kw)
            m.signal_attention({y: 0.5})
            return r

        with monkeypatch.context() as mp:
            mp.setattr(m.consolidation, "run_pass", run_pass_then_signal)
            mp.setattr(m.durability, "_compact_wal", _crash_at_step_3)
            with pytest.raises(_Crash):
                m.run_sleep_pass()
        (s2,) = _buffer_seqs(m)
    finally:
        m.close()
    snap = _snap(cfg)
    assert snap["wal_applied_seqs"] == [s1] and _wal_seqs(cfg) == [s1, s2]
    return cfg, x, y, s1, s2


def test_G_crash_between_steps_2_and_3_replays_only_the_pending_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 G."""
    cfg, x, y, s1, s2 = _crash_between_steps_2_and_3(tmp_path, monkeypatch)
    with Moneta(cfg) as r:
        assert _buffer_seqs(r) == [s2]
        r.run_sleep_pass()
        assert (_attended(r, x), _attended(r, y)) == (1, 1)


def test_G2_every_signal_counts_once_through_later_saves_and_reopens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 G2: G, then pass + save, reopen, pass + save, reopen."""
    cfg, x, y, s1, s2 = _crash_between_steps_2_and_3(tmp_path, monkeypatch)
    with Moneta(cfg) as r:
        r.run_sleep_pass()
        _save(r)
        assert sorted(_snap(cfg)["wal_applied_seqs"]) == [] and _wal(cfg) is None
    with Moneta(cfg) as r:
        assert len(r.attention) == 0
        r.signal_attention({x: 0.5})
        (s3,) = _buffer_seqs(r)
        r.run_sleep_pass()
        assert _snap(cfg)["wal_applied_seqs"] == [s3]
        _save(r)
        assert _wal(cfg) is None  # no line of S survives a save
    with Moneta(cfg) as r:
        assert len(r.attention) == 0
        assert (_attended(r, x), _attended(r, y)) == (2, 1)


def test_H2_stripped_keys_lose_exactly_the_pending_lines_at_or_before_T(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 H2: a key-stripping rewrite over k applied + p pending ``ts <= T``
    lines and one pending ``ts > T`` line, clock precondition held."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        z = m.deposit("z", [1.0, 1.0])
        _save(m)
        m.signal_attention({x: 0.5})
        m.signal_attention({x: 0.5})  # k = 2, applied below
        _apply_now(m)
        m.signal_attention({y: 0.5})
        m.signal_attention({y: 0.5})  # p = 2, pending
        time.sleep(0.002)
        with monkeypatch.context() as mp:
            mp.setattr(m.durability, "_compact_wal", _crash_at_step_3)
            with pytest.raises(_Crash):
                _save(m)
    finally:
        m.close()
    snap = _snap(cfg)
    t = snap["snapshot_created_at"]
    seqs = _wal_seqs(cfg)
    assert len(snap["wal_applied_seqs"]) == 2 and len(seqs) == 4
    assert set(snap["wal_applied_seqs"]) == set(seqs[:2])
    assert all(d["timestamp"] <= t for d in _wal_lines(cfg))  # precondition held
    late = max(seqs) + 1
    with open(cfg.wal_path, "ab") as fp:
        fp.write(_line(z, t + 1.0, seq=late))  # the one pending ts > T line
    _strip_keys(cfg)
    with Moneta(cfg) as r:
        assert len(_messages(caplog, logging.WARNING, "carry a seq")) == 1
        assert [(e.entity_id, s) for e, s in r.attention._buffer] == [(z, late)]
        r.run_sleep_pass()
        # x: no double; y: exactly the p = 2 lines lost; z: replayed once
        assert (_attended(r, x), _attended(r, y), _attended(r, z)) == (2, 0, 1)


def test_H3_old_seq_lines_under_a_keyless_snapshot_never_resurrect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 H3: an rc1 save whose unlink failed (keyless snapshot plus old
    seq lines). Step 0 drops them before any keyed snapshot exists."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        _apply_now(m)  # its effect is in the rows the next snapshot writes
        m.signal_attention({x: 0.5})  # pending; rc1's reopen would drop it
        time.sleep(0.002)
        with monkeypatch.context() as mp:
            mp.setattr(m.durability, "_compact_wal", _crash_at_step_3)
            with pytest.raises(_Crash):
                _save(m)
    finally:
        m.close()
    _strip_keys(cfg)
    old = _wal_seqs(cfg)
    assert len(old) == 2
    with Moneta(cfg) as r:
        assert len(r.attention) == 0
        assert r.durability._disposition == [None, None]
        _save(r)
        assert _snap(cfg)["wal_applied_seqs"] == []
        assert _wal(cfg) is None  # step 0 dropped both old lines
    with Moneta(cfg) as r:
        assert len(r.attention) == 0
        r.run_sleep_pass()
        assert _attended(r, x) == 1


def test_I_signal_crash_reopen_pass_save_crash_reopen(tmp_path: Path) -> None:
    """§4.2 I."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
    with Moneta(cfg) as m:
        assert len(m.attention) == 1
        m.run_sleep_pass()
        _save(m)
        assert _wal(cfg) is None  # empty after the second save
    with Moneta(cfg) as m:
        assert len(m.attention) == 0
        assert _attended(m, x) == 1


def test_K_compaction_failure_raises_after_the_snapshot_and_keeps_S(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 K: step 3's replace fails. The snapshot already holds the
    deposits, step 4 is skipped, and the next save writes S again."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1, s2 = _applied_and_pending(m)
        y = m.deposit("y", [0.0, 1.0])
        replace, calls = _fail_replace_of(wal_tmp_path(cfg.wal_path))
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(replace=replace))
            with pytest.raises(PermissionError):
                _save(m)
        assert len(calls) == 1
        snap = _snap(cfg)
        assert snap["wal_applied_seqs"] == [s1]
        assert str(y) in {r["entity_id"] for r in snap["rows"]}
        assert _row_attended(snap, x) == 1
        assert m.attention.applied_seqs >= {s1}
        assert _wal_seqs(cfg) == [s1, s2]
        assert not wal_tmp_path(cfg.wal_path).exists()
        crash = _crash_copy(cfg, tmp_path / "crash1")
        with Moneta(crash) as r:
            assert _buffer_seqs(r) == [s2]
            r.run_sleep_pass()
            assert _attended(r, x) == 2 and r.ecs.contains(y)
        _save(m)  # unpatched
        assert _snap(cfg)["wal_applied_seqs"] == [s1]
        assert _wal_seqs(cfg) == [s2]
        assert m.attention.applied_seqs == set()
        crash = _crash_copy(cfg, tmp_path / "crash2")
        with Moneta(crash) as r:
            assert _buffer_seqs(r) == [s2]
            r.run_sleep_pass()
            assert _attended(r, x) == 2
    finally:
        m.close()


def test_L_allocator_seeds_above_the_applied_set(tmp_path: Path) -> None:
    """§4.2 L: ``wal_applied_seqs=[0..9]``, no ``wal_next_seq``, no WAL."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    snap = _snap(cfg)
    snap["wal_applied_seqs"] = list(range(10))
    del snap["wal_next_seq"]
    _write_snap(cfg, snap)
    assert _wal(cfg) is None
    with Moneta(cfg) as m:
        m.signal_attention({x: 0.5})
        assert _wal_seqs(cfg) == [10]
    with Moneta(cfg) as m:  # crash and reopen
        assert _buffer_seqs(m) == [10]
        m.run_sleep_pass()
        assert _attended(m, x) == 1


def test_M_duplicate_seq_first_occurrence_wins(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 M."""
    caplog.set_level(logging.INFO, logger="moneta")
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    snap = _snap(cfg)
    t, s = snap["snapshot_created_at"], snap["wal_next_seq"]
    cfg.wal_path.write_bytes(_line(x, t + 1.0, seq=s) + _line(x, t + 2.0, seq=s))
    with Moneta(cfg) as m:
        assert [(e.timestamp, q) for e, q in m.attention._buffer] == [(t + 1.0, s)]
        assert len(_messages(caplog, logging.WARNING, "duplicate WAL seq")) == 1
        assert len(_messages(caplog, logging.INFO, "wal_duplicates=1")) == 1
        m.run_sleep_pass()
        assert _attended(m, x) == 1
    with Moneta(cfg) as m:
        assert len(m.attention) == 0 and _attended(m, x) == 1


def test_N_signal_clock_ahead_keyed_lines_unaffected_legacy_and_keyless_as_rc1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 N, signal stamps ahead of the snapshot clock: a keyed snapshot
    decides seq lines by membership (no double); legacy no-seq lines and a
    keyless snapshot reproduce rc1, which double-applies (characterization)."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        with monkeypatch.context() as mp:
            mp.setattr(api_mod, "time", _Clock(100.0))
            m.signal_attention({x: 0.5})
            _apply_now(m)  # s1 applied
            m.signal_attention({x: 0.5})  # s2 pending
        with monkeypatch.context() as mp:
            mp.setattr(m.durability, "_compact_wal", _crash_at_step_3)
            with pytest.raises(_Crash):
                _save(m)
    finally:
        m.close()
    snap = _snap(cfg)
    s1, s2 = _wal_seqs(cfg)
    assert snap["wal_applied_seqs"] == [s1]
    assert all(d["timestamp"] > snap["snapshot_created_at"] for d in _wal_lines(cfg))
    keyless = _crash_copy(cfg, tmp_path / "keyless")
    _strip_keys(keyless)
    legacy = _crash_copy(cfg, tmp_path / "legacy")  # keyed snapshot, no-seq lines
    legacy.wal_path.write_bytes(
        b"".join(_line(UUID(d["entity_id"]), d["timestamp"]) for d in _wal_lines(cfg))
    )
    for c in (keyless, legacy):
        expected = _rc1_attended(c, x)
        assert expected == 3  # rc1 replays both: s1 doubled
        with Moneta(c) as r:
            assert len(r.attention) == 2
            r.run_sleep_pass()
            assert _attended(r, x) == expected
    with Moneta(cfg) as r:
        assert _buffer_seqs(r) == [s2]
        r.run_sleep_pass()
        assert _attended(r, x) == 2


def test_N_backward_step_after_the_snapshot_keyed_keeps_the_pending_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 N, the other direction: the snapshot clock is ahead (as after a
    backward wall-clock step), so a pending signal has ``ts < T``. Keyed:
    membership replays it. Keyless: rc1's loss (characterization)."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "time", _Clock(100.0))
            _save(m)
            m.signal_attention({x: 0.5})
            _save(m)
    snap = _snap(cfg)
    (d,) = _wal_lines(cfg)
    assert d["timestamp"] < snap["snapshot_created_at"]
    assert d["seq"] not in snap["wal_applied_seqs"]
    keyless = _crash_copy(cfg, tmp_path / "keyless")
    _strip_keys(keyless)
    assert _rc1_attended(keyless, x) == 0
    with Moneta(keyless) as r:
        assert len(r.attention) == 0
        r.run_sleep_pass()
        assert _attended(r, x) == 0
    with Moneta(cfg) as r:
        assert _buffer_seqs(r) == [d["seq"]]
        r.run_sleep_pass()
        assert _attended(r, x) == 1


# =====================================================================
# §4.2: the WAL writer and its failure paths
# =====================================================================


def _write_fault(kind: str, dm: Any) -> Callable[[int, bytes], int]:
    """An ``os.write`` for ``_Os`` that fails the first WAL line written
    through the append descriptor: (a) raises before writing, (b) lands half
    the bytes and returns their count, (c) lands all of them, then raises."""
    state = {"fired": False}

    def write(fd: int, data: bytes) -> int:
        if not state["fired"] and fd == dm._wal_fd and data.startswith(b'{"wal_version"'):
            state["fired"] = True
            if kind == "a":
                raise OSError(5, "simulated write failure")
            if kind == "b":
                return os.write(fd, data[: len(data) // 2])
            os.write(fd, data)
            raise OSError(5, "simulated failure after writing")
        return os.write(fd, data)

    return write


def _pending_line_in_wal(m: Moneta) -> tuple[UUID, int]:
    """x saved; s1 applied in memory, its line still in the WAL; empty buffer."""
    x = m.deposit("x", [1.0, 0.0])
    _save(m)
    m.signal_attention({x: 0.5})
    (s1,) = _buffer_seqs(m)
    _apply_now(m)
    assert len(m.attention) == 0
    return x, s1


@pytest.mark.parametrize("kind", ["a", "b", "c"])
def test_O_a_to_c_a_failed_wal_append_leaves_no_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """§4.2 O(a)-(c): the signal is in neither the WAL nor the buffer."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1 = _pending_line_in_wal(m)
        dm = m.durability
        before = _wal(cfg)
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(write=_write_fault(kind, dm)))
            with pytest.raises(OSError) as ei:
                m.signal_attention({x: 0.5})
        if kind == "b":
            assert "short WAL write" in str(ei.value)
        assert len(m.attention) == 0
        assert _wal(cfg) == before
        assert dm._wal_fd is None and dm._void_seqs == set()
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert _buffer_seqs(r) == [s1]  # nothing from the failed call
        m.signal_attention({x: 0.5})
        (s3,) = _buffer_seqs(m)
    finally:
        m.close()
    with Moneta(cfg) as r:
        assert _buffer_seqs(r) == [s1, s3]


def test_O_d_a_failed_truncate_tombstones_the_seq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 O(d): (c) plus a failing ``os.ftruncate``."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1 = _pending_line_in_wal(m)
        dm = m.durability

        def ftruncate(fd: int, size: int) -> None:
            raise OSError(5, "simulated truncate failure")

        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(write=_write_fault("c", dm), ftruncate=ftruncate))
            with pytest.raises(OSError, match="after writing"):
                m.signal_attention({x: 0.5})
        seqs = _wal_seqs(cfg)
        assert len(seqs) == 2 and seqs[0] == s1
        s_void = seqs[1]
        assert dm._void_seqs == {s_void} and len(m.attention) == 0 and dm._wal_fd is None
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == sorted([s1, s_void])
        assert _wal(cfg) is None and dm._void_seqs == set()
        crash = _crash_copy(cfg, tmp_path / "crash")
        with Moneta(crash) as r:
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 1
    finally:
        m.close()


def test_O_e_a_close_error_never_replaces_the_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 O(e): (a) plus ``os.close`` raising after it closed the fd."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1 = _pending_line_in_wal(m)
        dm = m.durability

        def close(fd: int) -> None:
            os.close(fd)
            raise OSError(9, "close failed")

        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(write=_write_fault("a", dm), close=close))
            with pytest.raises(OSError) as ei:
                m.signal_attention({x: 0.5})
        assert "simulated write failure" in str(ei.value)
        assert "close failed" not in str(ei.value)
        assert dm._wal_fd is None
        m.signal_attention({x: 0.5})  # a fresh descriptor
        assert dm._wal_fd is not None and len(m.attention) == 1
        (s3,) = _buffer_seqs(m)
        assert _wal_seqs(cfg) == [s1, s3]
    finally:
        m.close()


@pytest.mark.parametrize("kind", ["c", "b"], ids=["whole_leftover", "torn_leftover"])
def test_O_f_an_interrupt_in_the_failure_path_forces_a_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """§4.2 O(f): ``os.ftruncate`` raises KeyboardInterrupt after a failed
    write. ``_wal_fd`` is cleared first, so the next append reopens the file
    and terminates a torn leftover before writing its own line."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x, s1 = _pending_line_in_wal(m)
        dm = m.durability

        def ftruncate(fd: int, size: int) -> None:
            raise KeyboardInterrupt

        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(write=_write_fault(kind, dm), ftruncate=ftruncate))
            with pytest.raises(KeyboardInterrupt):
                m.signal_attention({x: 0.5})
        assert dm._wal_fd is None and len(m.attention) == 0 and dm._void_seqs == set()
        raw = _split_raw_lines(_wal(cfg))
        assert len(raw) == 2 and raw[1].endswith(b"\n") == (kind == "c")
        leftover_seq = s1 + 1
        m.signal_attention({x: 0.5})
        (s_new,) = _buffer_seqs(m)
        raw = _split_raw_lines(_wal(cfg))
        assert len(raw) == 3
        assert raw[1].endswith(b"\n")  # terminated before the new line
        assert json.loads(raw[2])["seq"] == s_new  # the new line is its own raw line
    finally:
        m.close()
    with Moneta(cfg) as r:
        if kind == "b":  # the torn half is undecodable: the new signal once
            assert _buffer_seqs(r) == [s1, s_new]
        else:  # a whole leftover replays once, untombstoned (async residual)
            assert _buffer_seqs(r) == [s1, leftover_seq, s_new]


def test_R_hydrate_writes_nothing(tmp_path: Path) -> None:
    """§4.2 R: even with a step 0 disposition pending and a torn tail."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    t = _snap(cfg)["snapshot_created_at"]
    cfg.wal_path.write_bytes(_line(x, t + 1.0) + _line(x, t + 2.0)[:25])
    files = (cfg.snapshot_path, cfg.wal_path)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    m = Moneta(cfg)
    try:
        assert m.durability._disposition != [] and len(m.attention) == 1
    finally:
        m.close()
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == before
    assert sorted(p.name for p in cfg.snapshot_path.parent.iterdir()) == [
        "attention.wal.jsonl",
        "snapshot.json",
    ]


@pytest.mark.parametrize("cut", ["undecodable", "after_brace", "between_cr_lf"])
def test_U_a_torn_tail_from_power_loss(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, cut: str
) -> None:
    """§4.2 U: the WAL ends in a fragment of an acknowledged line."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
    snap = _snap(cfg)
    s0 = snap["wal_next_seq"]
    body = _line(y, snap["snapshot_created_at"] - 1.0, seq=s0).rstrip(b"\r\n")
    frag = {"undecodable": body[:30], "after_brace": body, "between_cr_lf": body + b"\r"}[cut]
    cfg.wal_path.write_bytes(frag)
    with Moneta(cfg) as m:
        if cut == "undecodable":
            assert _buffer_seqs(m) == []
            assert len(_messages(caplog, logging.WARNING, "malformed WAL line")) == 1
        else:
            assert _buffer_seqs(m) == [s0]
        m.signal_attention({x: 0.5})
        s_new = _buffer_seqs(m)[-1]
        raw = _split_raw_lines(_wal(cfg))
        assert raw == [frag + os.linesep.encode(), raw[1]]  # terminator first
        assert json.loads(raw[1])["seq"] == s_new and raw[1].endswith(b"\n")
    with Moneta(cfg) as m:  # reopen without a save
        assert _buffer_seqs(m) == ([s_new] if cut == "undecodable" else [s0, s_new])
        m.run_sleep_pass()
        assert _attended(m, x) == 1
        assert _attended(m, y) == (0 if cut == "undecodable" else 1)


def test_V_stale_tmp_files_and_two_stores_in_one_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 V."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    snap_tmp, wal_tmp = snapshot_tmp_path(cfg.snapshot_path), wal_tmp_path(cfg.wal_path)
    assert (snap_tmp.name, wal_tmp.name) == ("snapshot.json.tmp", "attention.wal.jsonl.tmp")
    t = _snap(cfg)["snapshot_created_at"]
    snap_tmp.write_text("{stale", encoding="utf-8")
    wal_tmp.write_bytes(_line(x, t + 1.0, seq=12345))
    with Moneta(cfg) as m:
        assert len(m.attention) == 0 and m.ecs.contains(x)  # stale files unread
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        _save(m)
        assert not snap_tmp.exists() and not wal_tmp.exists()
        assert _wal_seqs(cfg) == [s1]

    d = tmp_path / "shared"
    d.mkdir()
    ca = MonetaConfig.ephemeral(snapshot_path=d / "a.json", wal_path=d / "a.wal", half_life_seconds=3600.0)
    cb = MonetaConfig.ephemeral(snapshot_path=d / "b.json", wal_path=d / "b.wal", half_life_seconds=3600.0)
    replaced: list[str] = []

    def replace(src: Any, dst: Any, *a: Any, **k: Any) -> None:
        replaced.append(Path(src).name)
        os.replace(src, dst, *a, **k)

    with Moneta(ca) as a, Moneta(cb) as b:
        ea = a.deposit("a", [1.0, 0.0])
        eb = b.deposit("b", [0.0, 1.0])
        a.signal_attention({ea: 0.5})
        a.signal_attention({ea: 0.5})
        b.signal_attention({eb: 0.5})
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(replace=replace))
            _save(a)
            _save(b)
        assert "a.wal.tmp" in replaced and "b.wal.tmp" in replaced
        la, lb = _wal_lines(ca), _wal_lines(cb)
        assert [UUID(d["entity_id"]) for d in la] == [ea, ea]
        assert [UUID(d["entity_id"]) for d in lb] == [eb]
        assert [d["seq"] for d in la] == _buffer_seqs(a)
        assert [d["seq"] for d in lb] == _buffer_seqs(b)
        assert sorted(p.name for p in d.iterdir()) == ["a.json", "a.wal", "b.json", "b.wal"]


@pytest.mark.skipif(os.name != "nt", reason="Windows open-handle (share-delete) semantics")
def test_W_open_handles_on_windows(tmp_path: Path) -> None:
    """§4.2 W: the in-process append descriptor never blocks a save; a
    foreign handle without share-delete sends step 3 to the K path and
    step 0 to the degraded save."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        assert m.durability._wal_fd is not None
        _save(m)  # the save closes the in-process descriptor first
        assert m.durability._wal_fd is None and _wal_seqs(cfg) == [s1]
        with open(cfg.wal_path, "rb"):
            with pytest.raises(PermissionError):
                _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == []  # the snapshot came first
        assert not wal_tmp_path(cfg.wal_path).exists()
        _save(m)
        assert _wal_seqs(cfg) == [s1]
    finally:
        m.close()

    cfg2 = _store(tmp_path / "s2")
    with Moneta(cfg2) as m2:
        y = m2.deposit("y", [0.0, 1.0])
        _save(m2)
    t = _snap(cfg2)["snapshot_created_at"]
    cfg2.wal_path.write_bytes(_line(y, t + 1.0))
    with Moneta(cfg2) as m2:
        assert m2.durability._disposition != []
        before = _wal(cfg2)
        with open(cfg2.wal_path, "rb"):
            _save(m2)  # step 0 cannot replace: degraded, returns
        assert m2.durability.degraded_saves == 1
        assert not any(k in _snap(cfg2) for k in _KEYS)
        assert _wal(cfg2) == before
        _save(m2)
        assert m2.durability._disposition == [] and "wal_applied_seqs" in _snap(cfg2)


def test_X_cold_start_without_a_snapshot_replays_every_line_once(tmp_path: Path) -> None:
    """§4.2 X."""
    cfg = _store(tmp_path / "s")
    x = uuid4()
    now = time.time()
    cfg.wal_path.write_bytes(
        _line(x, now, seq=100) + _line(x, now, seq=101) + _line(x, now, seq=102) + _line(x, now)
    )
    with Moneta(cfg) as m:
        assert m.ecs.n == 0
        assert _buffer_seqs(m) == [100, 101, 102, 103]  # the legacy line gets 103
        assert m.durability._next_seq == 104
        _save(m)
    assert _wal_seqs(cfg) == [100, 101, 102, 103]
    with Moneta(cfg) as m:
        assert _buffer_seqs(m) == [100, 101, 102, 103]  # once per open
        m.run_sleep_pass()
    assert _snap(cfg)["wal_applied_seqs"] == [100, 101, 102, 103]
    assert _wal(cfg) is None
    with Moneta(cfg) as m:
        assert len(m.attention) == 0


@pytest.mark.parametrize(
    "case", ["same_wal", "same_snapshot", "snapshot_is_other_wal", "wal_is_other_wal_tmp"]
)
def test_Y_two_live_handles_on_shared_store_paths_are_refused(tmp_path: Path, case: str) -> None:
    """§4.2 Y: distinct URIs, overlapping store paths."""
    d = tmp_path
    first = MonetaConfig.ephemeral(snapshot_path=d / "a.json", wal_path=d / "a.wal", half_life_seconds=3600.0)
    snap2, wal2 = {
        "same_wal": (d / "b.json", d / "a.wal"),
        "same_snapshot": (d / "a.json", d / "b.wal"),
        "snapshot_is_other_wal": (d / "a.wal", d / "b.wal"),
        "wal_is_other_wal_tmp": (d / "b.json", d / "a.wal.tmp"),
    }[case]
    second = MonetaConfig.ephemeral(snapshot_path=snap2, wal_path=wal2, half_life_seconds=3600.0)
    assert first.storage_uri != second.storage_uri
    own_first = set(api_mod._store_paths(first))
    own_second = set(api_mod._store_paths(second))
    a = Moneta(first)
    try:
        with pytest.raises(MonetaResourceLockedError):
            Moneta(second)
        assert second.storage_uri not in api_mod._ACTIVE_URIS  # the refusal holds nothing
        assert not (own_second - own_first) & api_mod._ACTIVE_STORE_PATHS
        assert own_first <= api_mod._ACTIVE_STORE_PATHS
    finally:
        a.close()
    assert not own_first & api_mod._ACTIVE_STORE_PATHS
    with Moneta(second) as b:
        assert b.durability is not None


def test_Y_self_colliding_config_and_a_failed_construct_release_their_paths(tmp_path: Path) -> None:
    """§4.2 Y: one config whose own paths collide; a construct that fails
    after registering releases its paths."""
    same = MonetaConfig.ephemeral(
        snapshot_path=tmp_path / "x.json", wal_path=tmp_path / "x.json", half_life_seconds=3600.0
    )
    with pytest.raises(ValueError, match="pairwise distinct"):
        Moneta(same)
    assert same.storage_uri not in api_mod._ACTIVE_URIS
    assert not set(api_mod._store_paths(same)) & api_mod._ACTIVE_STORE_PATHS

    cfg = _store(tmp_path / "s")
    cfg.wal_path.write_bytes(
        b'{"wal_version": 1, "entity_id": "not-a-uuid", "weight": 0.5, "timestamp": 1.0}'
        + os.linesep.encode()
    )
    with pytest.raises(ValueError):
        Moneta(cfg)  # hydrate raises after the paths were registered
    assert cfg.storage_uri not in api_mod._ACTIVE_URIS
    assert not set(api_mod._store_paths(cfg)) & api_mod._ACTIVE_STORE_PATHS
    cfg.wal_path.unlink()
    other = MonetaConfig.ephemeral(
        snapshot_path=tmp_path / "o.json", wal_path=cfg.wal_path, half_life_seconds=3600.0
    )
    with Moneta(other) as o:  # the released WAL path is free
        assert o.durability is not None


def test_AA_snapshot_and_background_refuse_a_foreign_ecs(tmp_path: Path) -> None:
    """§4.2 AA."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        before = (cfg.snapshot_path.read_bytes(), _wal(cfg))
        with pytest.raises(ValueError, match="not the ECS attached"):
            m.durability.snapshot_ecs(ECS())
        with pytest.raises(ValueError, match="not the ECS attached"):
            m.durability.start_background(ECS())
        assert m.durability._bg_thread is None
        assert (cfg.snapshot_path.read_bytes(), _wal(cfg)) == before


def test_AC_a_foreign_no_seq_line_at_step_3_gets_a_fresh_seq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AC: a no-seq line appended between steps 2 and 3."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        dm = m.durability
        orig = dm._compact_wal

        def compact(applied: frozenset) -> None:
            with open(cfg.wal_path, "ab") as fp:  # a foreign writer
                fp.write(_line(y, time.time()))
            orig(applied)

        monkeypatch.setattr(dm, "_compact_wal", compact)
        _save(m)
        snap = _snap(cfg)
        lines = _wal_lines(cfg)
        assert [UUID(d["entity_id"]) for d in lines] == [x, y]
        fresh = lines[1]["seq"]
        assert type(fresh) is int and fresh not in snap["wal_applied_seqs"]
        assert fresh >= snap["wal_next_seq"]
        assert len(_messages(caplog, logging.WARNING, "gave 1 foreign WAL line")) == 1
    with Moneta(cfg) as r:
        assert _buffer_seqs(r) == [s1, fresh]
        r.run_sleep_pass()
        assert (_attended(r, x), _attended(r, y)) == (1, 1)


def _blocked_background_save(
    monkeypatch: pytest.MonkeyPatch, m: Moneta
) -> tuple[threading.Event, list]:
    """Patch the bounds small, record excepthook calls, and start a
    background saver whose save spins in step 1 on a stray token."""
    monkeypatch.setattr(dur_mod, "SEQLOCK_READ_TIMEOUT_S", 0.6)
    monkeypatch.setattr(dur_mod, "BACKGROUND_JOIN_TIMEOUT_S", 0.1)
    hooked: list = []
    monkeypatch.setattr(threading, "excepthook", hooked.append)
    spun = threading.Event()

    def spin(s: float) -> None:
        spun.set()
        time.sleep(s)

    monkeypatch.setattr(dur_mod, "_sleep", spin)
    m.attention._inflight.add(object())  # the save spins until its bound
    m.durability._snapshot_interval = 0.01
    m.durability.start_background(m.ecs)
    return spun, hooked


def test_AD_close_waits_for_an_in_flight_background_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 AD: close() returns after the save and closes the descriptor
    after its last write; the saver exits on its own captured event."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    dm = m.durability
    marks: dict[str, Any] = {}
    orig_degraded = dm._degraded_save

    def degraded(ecs: Any, entry: str) -> None:
        orig_degraded(ecs, entry)
        marks["save_done"] = time.monotonic()
        marks["fd_at_save_end"] = dm._wal_fd

    monkeypatch.setattr(dm, "_degraded_save", degraded)
    try:
        x = m.deposit("x", [1.0, 0.0])
        m.signal_attention({x: 0.5})  # opens the append descriptor
        assert dm._wal_fd is not None
        spun, hooked = _blocked_background_save(monkeypatch, m)
        thread = dm._bg_thread
        assert thread is not None and spun.wait(_WAIT)
        m.close()
        marks["close_done"] = time.monotonic()
        assert "save_done" in marks and marks["close_done"] >= marks["save_done"]
        assert marks["fd_at_save_end"] is not None and dm._wal_fd is None
        thread.join(_WAIT)
        assert not thread.is_alive()
        assert hooked == []
    finally:
        m.close()


def test_AD_a_timed_out_stop_never_leads_to_two_savers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 AD: stop_background() times out on a blocked save; a restart
    before the save finishes starts nothing, and one after it does."""

    def savers() -> set:
        return {t for t in threading.enumerate() if t.name == "moneta-snapshot" and t.is_alive()}

    baseline = savers()
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    dm = m.durability
    try:
        m.deposit("x", [1.0, 0.0])
        spun, hooked = _blocked_background_save(monkeypatch, m)
        old = dm._bg_thread
        assert old is not None and spun.wait(_WAIT)
        dm.stop_background()  # the join times out: the save is spinning
        assert dm._bg_thread is old and old.is_alive() and dm._stop_event is not None
        dm.start_background(m.ecs)  # before the save finishes
        assert dm._bg_thread is old
        assert savers() - baseline == {old}
        old.join(_WAIT)
        assert not old.is_alive()  # it exited on its own event
        m.attention._inflight.clear()
        dm.start_background(m.ecs)  # after it finished
        new = dm._bg_thread
        assert new is not None and new is not old and new.is_alive()
        assert savers() - baseline == {new}
        assert hooked == []
    finally:
        m.close()


def test_Z_fresh_stores_draw_a_random_lineage_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 Z."""
    draws = iter([7, 9])
    calls: list[int] = []

    def randbits(k: int) -> int:
        calls.append(k)
        return next(draws)

    with monkeypatch.context() as mp:
        mp.setattr(dur_mod.secrets, "randbits", randbits)
        c1, c2 = _store(tmp_path / "one"), _store(tmp_path / "two")
        with Moneta(c1) as m1, Moneta(c2) as m2:
            assert m1.durability._next_seq == 7 << 20
            assert m2.durability._next_seq == 9 << 20
            x = m1.deposit("x", [1.0, 0.0])
            m1.signal_attention({x: 0.5})
            assert _wal_seqs(c1) == [7 << 20]
    assert calls == [32, 32]
    with Moneta(_store(tmp_path / "three")) as m3:
        seed = m3.durability._next_seq
        assert seed % 2**20 == 0 and 0 <= seed < 2**52


@pytest.mark.slow
def test_T_stress_every_signal_counts_exactly_once(tmp_path: Path) -> None:
    """§4.2 T: a signal loop, a sleep-pass loop with quiet gaps and a save
    loop, then close, reopen and drain."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    stop = threading.Event()
    errors: list = []
    counts = {"signals": 0, "passes": 0, "saves": 0}
    try:
        eids = [m.deposit(f"e{i}", [1.0, float(i)]) for i in range(5)]
        _save(m)

        def signals() -> None:
            i = 0
            while not stop.is_set():
                m.signal_attention({eids[i % len(eids)]: 0.01})
                counts["signals"] += 1
                i += 1
                if i % 20 == 0:
                    time.sleep(0.001)

        def passes() -> None:
            while not stop.is_set():
                m.run_sleep_pass()
                counts["passes"] += 1
                time.sleep(0.01)  # a quiet gap longer than one row build

        def saves() -> None:
            while not stop.is_set():
                _save(m)
                counts["saves"] += 1
                time.sleep(0.002)

        threads = [threading.Thread(target=_run(errors, f)) for f in (signals, passes, saves)]
        for t in threads:
            t.start()
        time.sleep(1.5)
        stop.set()
        for t in threads:
            t.join(_WAIT)
        assert not any(t.is_alive() for t in threads)
        assert errors == []
        degraded = m.durability.degraded_saves
        stragglers = m.attention.stragglers_carried
    finally:
        stop.set()
        m.close()
    if degraded:
        pytest.fail(
            f"T: {degraded} degraded save(s) under load; a degraded save "
            f"reintroduces the rc1 loss, so the count check is meaningless"
        )
    with Moneta(cfg) as r:
        r.run_sleep_pass()
        total = sum(_attended(r, e) for e in eids)
    print(f"T: {counts} stragglers_carried={stragglers}")
    assert counts["signals"] > 0 and counts["passes"] > 0 and counts["saves"] > 0
    assert total == counts["signals"], (total, counts, stragglers)


def test_AE_raw_line_grammar() -> None:
    """§4.2 AE, the reader."""
    assert _split_raw_lines(b"a\r\nb\r\n") == [b"a\r\n", b"b\r\n"]
    assert _split_raw_lines(b"a\r\nb") == [b"a\r\n", b"b"]
    assert _split_raw_lines(b"a\rb\n") == [b"a\rb\n"]
    assert _split_raw_lines(b"a\n") == [b"a\n"]  # no trailing empty piece
    assert _split_raw_lines(b"") == []


def test_AE_the_first_append_lands_at_prefix_len(tmp_path: Path) -> None:
    """§4.2 AE: a WAL ending in a terminator, with a pending disposition."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
    t = _snap(cfg)["snapshot_created_at"]
    cfg.wal_path.write_bytes(_line(y, t + 0.001))  # legacy, ts > T, terminated
    m = Moneta(cfg)
    try:
        dm = m.durability
        (s_legacy,) = _buffer_seqs(m)
        assert dm._disposition == [(s_legacy, True)]
        prefix_len = len(dm._disposition)
        m.signal_attention({x: 0.5})
        s_new = _buffer_seqs(m)[-1]
        raw = _split_raw_lines(_wal(cfg))
        assert len(raw) == prefix_len + 1
        assert json.loads(raw[prefix_len])["seq"] == s_new
        new_line = raw[prefix_len]
        _save(m)
        raw = _split_raw_lines(_wal(cfg))
        assert raw[1] == new_line  # step 0 copied it unchanged
        assert json.loads(raw[0])["seq"] == s_legacy
        crash = _crash_copy(cfg, tmp_path / "crash")
    finally:
        m.close()
    with Moneta(crash) as r:
        assert _buffer_seqs(r) == [s_legacy, s_new]
        r.run_sleep_pass()
        assert (_attended(r, x), _attended(r, y)) == (1, 1)


def test_AF_a_closed_manager_refuses_every_store_operation(tmp_path: Path) -> None:
    """§4.2 AF."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    x = m.deposit("x", [1.0, 0.0])
    _save(m)
    m.signal_attention({x: 0.5})
    m.run_sleep_pass()
    m.close()
    dm = m.durability
    before = (cfg.snapshot_path.read_bytes(), _wal(cfg))
    stale = [
        lambda: m.signal_attention({x: 0.5}),
        lambda: dm.wal_append(AttentionEntry(x, 0.5, time.time())),
        lambda: dm.snapshot_ecs(m.ecs),
        lambda: dm.start_background(m.ecs),
    ]
    for call in stale:
        with pytest.raises(ValueError, match="^durability manager is closed$"):
            call()
    assert len(m.attention) == 0 and dm._bg_thread is None
    assert (cfg.snapshot_path.read_bytes(), _wal(cfg)) == before
    with Moneta(cfg) as m2:  # the store's new owner
        m2.signal_attention({x: 0.5})
        m2.signal_attention({x: 0.5})
        _save(m2)
        own = _buffer_seqs(m2)
        wal_before = _wal(cfg)
        with pytest.raises(ValueError, match="^durability manager is closed$"):
            m.signal_attention({x: 0.5})
        assert len(m.attention) == 0 and _wal(cfg) == wal_before
        seqs = _wal_seqs(cfg)
        assert seqs == own and len(set(seqs)) == 2


def test_AG_an_interrupt_after_the_wal_write_tombstones_the_seq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 AG."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        orig = m.attention.append
        fired: list[int] = []

        def append(*a: Any, **k: Any) -> None:
            if not fired:
                fired.append(1)
                raise KeyboardInterrupt
            orig(*a, **k)

        monkeypatch.setattr(m.attention, "append", append)
        with pytest.raises(KeyboardInterrupt):
            m.signal_attention({x: 0.5})
        (seq,) = _wal_seqs(cfg)
        assert m.durability._void_seqs == {seq} and len(m.attention) == 0
        crash = _crash_copy(cfg, tmp_path / "before_save")
        with Moneta(crash) as r:  # a crash before the next save: once (residual)
            assert _buffer_seqs(r) == [seq]
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == [seq] and _wal(cfg) is None
        assert m.durability._void_seqs == set()
        crash = _crash_copy(cfg, tmp_path / "after_save")
        with Moneta(crash) as r:
            assert len(r.attention) == 0
            r.run_sleep_pass()
            assert _attended(r, x) == 0
    finally:
        m.close()


def test_AH_a_blank_and_undecodable_lines_are_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AH(a)."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    t = _snap(cfg)["snapshot_created_at"]
    nl = os.linesep.encode()
    cfg.wal_path.write_bytes(nl + b"{not json" + nl + _line(x, t + 1.0))
    with Moneta(cfg) as m:
        assert len(m.attention) == 1
        assert len(_messages(caplog, logging.WARNING, "malformed WAL line")) == 1
        m.run_sleep_pass()
        assert _attended(m, x) == 1
    with Moneta(cfg) as m:
        assert len(m.attention) == 0 and _attended(m, x) == 1


@pytest.mark.parametrize(
    "line, exc",
    [
        (b'{"wal_version": 1, "entity_id": "not-a-uuid", "weight": 0.5, "timestamp": 1.0}', ValueError),
        (b'{"wal_version": 1, "entity_id": "@", "weight": null, "timestamp": 1.0}', TypeError),
        (b"[1]", TypeError),
    ],
    ids=["bad_uuid", "null_weight", "non_object"],
)
def test_AH_b_an_invalid_line_refuses_the_store_and_changes_nothing(
    tmp_path: Path, line: bytes, exc: type
) -> None:
    """§4.2 AH(b): the original exception, the lock released, no file touched."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    cfg.wal_path.write_bytes(line.replace(b"@", str(x).encode()) + os.linesep.encode())
    files = (cfg.snapshot_path, cfg.wal_path)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    with pytest.raises(exc) as ei:
        Moneta(cfg)
    assert type(ei.value) is exc
    assert cfg.storage_uri not in api_mod._ACTIVE_URIS
    assert not set(api_mod._store_paths(cfg)) & api_mod._ACTIVE_STORE_PATHS
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == before
    assert sorted(p.name for p in cfg.wal_path.parent.iterdir()) == [
        "attention.wal.jsonl",
        "snapshot.json",
    ]


def test_AH_c_foreign_bad_lines_after_hydrate_are_dropped_at_step_3(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AH(c)."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        nl = os.linesep.encode()
        with open(cfg.wal_path, "ab") as fp:
            fp.write(b"{broken" + nl)
            fp.write(
                b'{"wal_version": 1, "entity_id": "not-a-uuid", "weight": 0.5, "timestamp": 1.0}' + nl
            )
        _save(m)
        assert len(_messages(caplog, logging.WARNING, "dropped 1 undecodable")) == 1
        assert len(_messages(caplog, logging.ERROR, "dropped 1 invalid")) == 1
        assert _wal_seqs(cfg) == [s1]
    with Moneta(cfg) as r:  # the store still opens
        assert _buffer_seqs(r) == [s1]


@pytest.mark.parametrize("bad", [True, 1.5, -1], ids=["true", "float", "negative"])
def test_AH_d_an_invalid_seq_value_counts_as_no_seq(tmp_path: Path, bad: Any) -> None:
    """§4.2 AH(d): judged by timestamp, then given a fresh seq by step 0."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    snap = _snap(cfg)
    t = snap["snapshot_created_at"]
    cfg.wal_path.write_bytes(_line(x, t - 1.0, seq=bad) + _line(x, t + 1.0, seq=bad))
    with Moneta(cfg) as m:
        assert [e.timestamp for e, _ in m.attention._buffer] == [t + 1.0]
        (fresh,) = _buffer_seqs(m)
        assert fresh == snap["wal_next_seq"]
        assert m.durability._disposition == [None, (fresh, True)]
        _save(m)
        assert _wal_seqs(cfg) == [fresh]


# =====================================================================
# §4.2: path L, snapshot key types, the absent WAL
# =====================================================================


def _late_landing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[MonetaConfig, Moneta, UUID, UUID, int, int]:
    """Probe part 1's shape, deterministic: while the reducer aggregates,
    an entry whose WAL line is already written lands in the list the
    reducer has just swapped out and snapshotted."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    x = m.deposit("x", [1.0, 0.0])
    y = m.deposit("y", [0.0, 1.0])
    _save(m)
    m.signal_attention({x: 0.5})
    (s1,) = _buffer_seqs(m)
    late = AttentionEntry(y, 0.5, time.time())
    s_late = m.durability.wal_append(late)  # written, not yet buffered
    log = m.attention
    real_aggregate = attn_mod.aggregate
    fired: list[int] = []

    def aggregate(entries: Any) -> Any:
        if not fired:
            fired.append(1)
            old, _taken = log._carry
            old.append((late, s_late))  # after the reducer's snapshot of it
        return real_aggregate(entries)

    monkeypatch.setattr(attn_mod, "aggregate", aggregate)
    reduce_attention_log(log, m.ecs, m.decay, time.time())
    assert fired == [1]
    assert s1 in log.applied_seqs and s_late not in log.applied_seqs
    assert (_attended(m, x), _attended(m, y)) == (1, 0)
    return cfg, m, x, y, s1, s_late


def test_AI_a_late_landing_is_never_recorded_and_replays_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 AI, first case: save, crash, reopen."""
    cfg, m, x, y, s1, s_late = _late_landing(tmp_path, monkeypatch)
    try:
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == [s1]
        assert _wal_seqs(cfg) == [s_late]  # its line survives compaction
        crash = _crash_copy(cfg, tmp_path / "crash")
    finally:
        m.close()
    with Moneta(crash) as r:
        assert _buffer_seqs(r) == [s_late]
        r.run_sleep_pass()
        assert (_attended(r, x), _attended(r, y)) == (1, 1)


def test_AI_c_late_landing_is_carried_into_the_next_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 AI, third case: a second pass before the save applies it."""
    cfg, m, x, y, s1, s_late = _late_landing(tmp_path, monkeypatch)
    try:
        reduce_attention_log(m.attention, m.ecs, m.decay, time.time())
        assert m.attention.stragglers_carried == 1
        assert s_late in m.attention.applied_seqs
        assert (_attended(m, x), _attended(m, y)) == (1, 1)
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == sorted([s1, s_late])
        assert _wal(cfg) is None
        crash = _crash_copy(cfg, tmp_path / "crash")
    finally:
        m.close()
    with Moneta(crash) as r:
        assert len(r.attention) == 0
        r.run_sleep_pass()
        assert (_attended(r, x), _attended(r, y)) == (1, 1)


def test_AI_b_a_blocked_appender_lands_in_exactly_one_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§4.2 AI, second case, the probe's own shape: the appender blocks
    inside ``AttentionEntry`` while a pass runs on this thread."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    blocked, release = threading.Event(), threading.Event()
    appender: dict[str, int] = {}
    errors: list = []
    try:
        x = m.deposit("x", [1.0, 0.0])
        y = m.deposit("y", [0.0, 1.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        real_entry = attn_mod.AttentionEntry

        def entry(*a: Any) -> AttentionEntry:
            if threading.get_ident() == appender.get("id"):
                blocked.set()
                assert release.wait(_WAIT)
            return real_entry(*a)

        monkeypatch.setattr(attn_mod, "AttentionEntry", entry)

        def signal() -> None:
            appender["id"] = threading.get_ident()
            m.signal_attention({y: 0.5})

        t = threading.Thread(target=_run(errors, signal))
        t.start()
        assert blocked.wait(_WAIT)
        (s_late,) = [d["seq"] for d in _wal_lines(cfg) if d["entity_id"] == str(y)]
        reduce_attention_log(m.attention, m.ecs, m.decay, time.time())
        release.set()
        t.join(_WAIT)
        assert not t.is_alive() and errors == []
        log = m.attention
        assert s1 in log.applied_seqs and s_late not in log.applied_seqs
        old, taken = log._carry
        in_live = sum(1 for _, q in log._buffer if q == s_late)
        in_swapped = sum(1 for _, q in old[taken:] if q == s_late)
        assert in_live + in_swapped == 1  # whichever list it landed in
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == [s1]
        assert _wal_seqs(cfg) == [s_late]
        crash = _crash_copy(cfg, tmp_path / "crash")
    finally:
        release.set()
        m.close()
    with Moneta(crash) as r:
        assert _buffer_seqs(r) == [s_late]
        r.run_sleep_pass()
        assert (_attended(r, x), _attended(r, y)) == (1, 1)


def _aj_store(tmp_path: Path) -> tuple[MonetaConfig, UUID, dict]:
    """A keyed store whose WAL holds one pending line, seq 2000, ``ts < T``:
    it replays only if membership decides."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    snap = _snap(cfg)
    cfg.wal_path.write_bytes(_line(x, snap["snapshot_created_at"] - 1.0, seq=2000))
    return cfg, x, snap


_BAD_APPLIED = [None, "abc", {}, [1, True], [1, 1.5], [1, -1], [1, 2**53], [1, "2"], [[1]]]
_BAD_APPLIED_IDS = ["null", "str", "dict", "bool", "float", "negative", "2p53", "numstr", "nested"]


@pytest.mark.parametrize("value", _BAD_APPLIED, ids=_BAD_APPLIED_IDS)
def test_AJ_a_malformed_wal_applied_seqs_counts_as_absent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: Any
) -> None:
    """§4.2 AJ: the store opens (rc1 opens it); one WARNING; timestamps decide."""
    cfg, x, snap = _aj_store(tmp_path)
    snap["wal_applied_seqs"] = value
    _write_snap(cfg, snap)
    with Moneta(cfg) as m:
        assert len(_messages(caplog, logging.WARNING, "ignoring wal_applied_seqs")) == 1
        assert len(m.attention) == 0  # ts < T: dropped by the timestamp rule


@pytest.mark.parametrize("value", [None, "x", True, -1, 2**60], ids=["null", "str", "bool", "negative", "2p60"])
def test_AJ_b_invalid_wal_next_seq_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: Any
) -> None:
    """§4.2 AJ: one WARNING; membership still decides; the seed ignores it."""
    cfg, x, snap = _aj_store(tmp_path)
    snap["wal_applied_seqs"] = [1000]
    snap["wal_next_seq"] = value
    _write_snap(cfg, snap)
    with Moneta(cfg) as m:
        assert len(_messages(caplog, logging.WARNING, "ignoring wal_next_seq")) == 1
        assert _buffer_seqs(m) == [2000]
        assert m.durability._next_seq == 2001


def test_AJ_c_a_near_limit_seed_reseeds_from_a_disjoint_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AJ: ``wal_next_seq = 2**53 - 5`` with a valid applied set."""
    cfg, x, snap = _aj_store(tmp_path)
    snap["wal_applied_seqs"] = [1000]
    snap["wal_next_seq"] = 2**53 - 5
    _write_snap(cfg, snap)
    draws = iter([0, 5])  # base 0 holds 1000 and 2000, so it is drawn again
    calls: list[int] = []

    def randbits(k: int) -> int:
        calls.append(k)
        return next(draws)

    with monkeypatch.context() as mp:
        mp.setattr(dur_mod.secrets, "randbits", randbits)
        m = Moneta(cfg)
    try:
        seed = 5 << 20
        assert calls == [32, 32]
        assert m.durability._next_seq == seed
        assert seed % 2**20 == 0 and seed < 2**52
        assert not any(seed <= s < seed + 2**40 for s in (1000, 2000))
        assert len(_messages(caplog, logging.ERROR, "reseeding from a random base")) == 1
        assert _buffer_seqs(m) == [2000]
        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "time", _Clock(100.0))  # T ahead: a backward step
            m.signal_attention({x: 0.5})
            assert _buffer_seqs(m) == [2000, seed]
            _save(m)
        snap2 = _snap(cfg)
        assert snap2["wal_applied_seqs"] == [] and snap2["wal_next_seq"] == seed + 1
        assert _wal_seqs(cfg) == [2000, seed]
        assert all(d["timestamp"] < snap2["snapshot_created_at"] for d in _wal_lines(cfg))
        crash = _crash_copy(cfg, tmp_path / "crash")
    finally:
        m.close()
    with Moneta(crash) as r:  # membership, not timestamp
        assert _buffer_seqs(r) == [2000, seed]


def test_AK_a_saves_of_a_fresh_store_never_create_a_wal(tmp_path: Path) -> None:
    """§4.2 AK(a)."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        m.deposit("x", [1.0, 0.0])
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == [] and _wal(cfg) is None
    with Moneta(cfg) as m:
        _save(m)
        assert _snap(cfg)["wal_applied_seqs"] == [] and _wal(cfg) is None


def test_AK_b_a_save_with_everything_applied_leaves_no_wal(tmp_path: Path) -> None:
    """§4.2 AK(b): rc1's on-disk shape."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        m.run_sleep_pass()
        _save(m)
        assert _wal(cfg) is None and not cfg.wal_path.exists()


def test_AK_c_a_missing_wal_directory_is_created(tmp_path: Path) -> None:
    """§4.2 AK(c)."""
    wal_dir = tmp_path / "deep" / "er"
    cfg = MonetaConfig.ephemeral(
        snapshot_path=tmp_path / "snapshot.json",
        wal_path=wal_dir / "attention.wal.jsonl",
        half_life_seconds=3600.0,
    )
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        assert not wal_dir.exists()
        m.signal_attention({x: 0.5})
        assert cfg.wal_path.exists()
    with Moneta(cfg) as m:  # durable
        assert len(m.attention) == 1
        m.run_sleep_pass()
        assert _attended(m, x) == 1


@pytest.mark.parametrize("fault", [OSError, KeyboardInterrupt], ids=["oserror", "keyboardinterrupt"])
def test_AK_d_a_failure_in_the_open_path_closes_the_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: type
) -> None:
    """§4.2 AK(d): the last-byte read fails. The original exception escapes,
    the descriptor is closed (a later save's ``os.replace`` succeeds on
    Windows), and the next append succeeds."""
    cfg = _store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
        m.signal_attention({x: 0.5})
        (s1,) = _buffer_seqs(m)
        _save(m)  # closes the descriptor; s1 is a kept line
        dm = m.durability
        assert dm._wal_fd is None and _wal_seqs(cfg) == [s1]

        def last_byte() -> bytes:
            raise fault()

        with monkeypatch.context() as mp:
            mp.setattr(dm, "_last_wal_byte", last_byte)
            with pytest.raises(fault):
                m.signal_attention({x: 0.5})
        assert dm._wal_fd is None and len(m.attention) == 1
        assert _wal_seqs(cfg) == [s1]
        _save(m)  # would raise PermissionError on Windows had the fd leaked
        assert _wal_seqs(cfg) == [s1]
        m.signal_attention({x: 0.5})
        assert _wal_seqs(cfg) == [s1, _buffer_seqs(m)[-1]]
    finally:
        m.close()


def test_AK_e_a_wal_deleted_before_the_first_save_clears_the_disposition(tmp_path: Path) -> None:
    """§4.2 AK(e)."""
    cfg = _store(tmp_path / "s")
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    t = _snap(cfg)["snapshot_created_at"]
    cfg.wal_path.write_bytes(_line(x, t + 1.0))
    with Moneta(cfg) as m:
        assert m.durability._disposition != []
        cfg.wal_path.unlink()
        _save(m)
        assert m.durability._disposition == []
        assert "wal_applied_seqs" in _snap(cfg)
        assert _wal(cfg) is None


# =====================================================================
# §4.2 AL (revision 6, Persistence-Substrate cross-review): step 0 applies
# the hydrate-time disposition only to the WAL hydrate read
# =====================================================================


def _al_store(root: Path) -> tuple[MonetaConfig, UUID, int]:
    """A keyed store whose WAL gives the disposition [None, (s5, False)]:
    raw line 0, a legacy line filtered by timestamp, is dropped at step 0;
    raw line 1, pending seq s5, is kept unchanged."""
    cfg = _store(root)
    with Moneta(cfg) as m:
        x = m.deposit("x", [1.0, 0.0])
        _save(m)
    snap = _snap(cfg)
    t, s5 = snap["snapshot_created_at"], snap["wal_next_seq"]
    cfg.wal_path.write_bytes(_line(x, t - 1.0) + _line(x, t + 0.001, seq=s5))
    return cfg, x, s5


def test_AL_a_an_interrupt_after_step_0s_replace_never_reapplies_the_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§4.2 AL(a): a BaseException after step 0's ``os.replace`` and before
    it clears the disposition leaves a normalized WAL and the hydrate-time
    disposition. Re-applied by index, that disposition dropped the pending
    s5 line silently (cross-review probe: [s5, s6, s7] became [s6, s7] with
    no ERROR). The WAL no longer starts with the bytes hydrate read, so
    step 0 fails closed: this save degrades, and so does every later save
    of the handle until it is reopened."""
    caplog.set_level(logging.INFO, logger="moneta")
    cfg, x, s5 = _al_store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        dm = m.durability
        assert dm._disposition == [None, (s5, False)]
        m.signal_attention({x: 0.5})
        m.signal_attention({x: 0.5})
        s_first, s6, s7 = _buffer_seqs(m)
        assert s_first == s5
        wal_tmp = wal_tmp_path(cfg.wal_path)

        def replace_then_interrupt(src: Any, dst: Any, *a: Any, **k: Any) -> None:
            os.replace(src, dst, *a, **k)
            if Path(src) == wal_tmp:
                raise KeyboardInterrupt("after step 0's os.replace")

        with monkeypatch.context() as mp:
            mp.setattr(dur_mod, "os", _Os(replace=replace_then_interrupt))
            with pytest.raises(KeyboardInterrupt):
                _save(m)
        assert _wal_seqs(cfg) == [s5, s6, s7]  # normalized: raw line 0 is gone
        assert dm._disposition == [None, (s5, False)]  # the clear was skipped
        normalized = _wal(cfg)
        for n in (1, 2):  # this save, and every later save of the handle
            _save(m)
            assert dm.degraded_saves == n
            assert _wal(cfg) == normalized  # s5 kept; nothing applied by index
            assert not any(k in _snap(cfg) for k in _KEYS)
            assert dm._disposition == [None, (s5, False)]
        failed = _messages(caplog, logging.ERROR, "step 0 (WAL normalization) failed")
        assert len(failed) == 2
        assert all("no longer starts with" in msg for msg in failed)
    finally:
        m.close()


@pytest.mark.parametrize("change", ["truncated", "rewritten"])
def test_AL_b_a_wal_changed_outside_the_handle_fails_step_0(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, change: str
) -> None:
    """§4.2 AL(b): the bytes hydrate read are the only WAL the disposition
    fits. A WAL truncated outside the handle (§2.4, "shortened WAL") or
    rewritten in place with the same line count fails step 0: the save
    degrades and the WAL is left as found."""
    caplog.set_level(logging.INFO, logger="moneta")
    cfg, x, s5 = _al_store(tmp_path / "s")
    m = Moneta(cfg)
    try:
        dm = m.durability
        assert dm._disposition == [None, (s5, False)]
        lines = _split_raw_lines(_wal(cfg) or b"")
        if change == "truncated":
            foreign = lines[0]
        else:  # raw line 0 now carries a pending seq the disposition would drop
            t = _snap(cfg)["snapshot_created_at"]
            foreign = _line(x, t + 0.002, seq=s5 - 1) + lines[1]
        cfg.wal_path.write_bytes(foreign)
        _save(m)
        assert dm.degraded_saves == 1
        assert _wal(cfg) == foreign
        assert not any(k in _snap(cfg) for k in _KEYS)
        assert dm._disposition == [None, (s5, False)]
        failed = _messages(caplog, logging.ERROR, "step 0 (WAL normalization) failed")
        assert len(failed) == 1 and "no longer starts with" in failed[0]
    finally:
        m.close()
