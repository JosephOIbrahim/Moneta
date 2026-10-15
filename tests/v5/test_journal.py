"""Journal framing, recovery, exclusivity and rollback."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from moneta.v5 import Config, JournalCorruptError, JournalLockedError, Substrate, repair
from moneta.v5.journal import FileJournal, encode_frame, scan


def test_frames_are_checksummed_and_sequenced(tmp_path):
    j = FileJournal(tmp_path / "j")
    assert j.append({"op": "note", "t": 1.0}) == 1
    assert j.append({"op": "note", "t": 2.0}) == 2
    j.close()
    events, good, torn = scan((tmp_path / "j").read_bytes(), tmp_path / "j")
    assert [e["seq"] for e in events] == [1, 2] and torn == 0


def test_nan_is_rejected_before_any_byte_is_written(tmp_path):
    j = FileJournal(tmp_path / "j")
    with pytest.raises(ValueError):
        j.append({"op": "note", "t": float("nan")})
    assert (tmp_path / "j").read_bytes() == b""
    assert j.last_seq == 0
    j.close()


def test_torn_tail_is_truncated_and_reported(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(Config(path=path)) as m:
        m.deposit("kept", [1.0, 0.0], t=1.0)
    good = path.read_bytes()
    with open(path, "ab") as fp:
        fp.write(encode_frame({"op": "deposit", "seq": 3, "t": 2.0})[:-7])  # crash mid-append
    with Substrate(Config(path=path)) as m:
        assert m.recovered_tail_bytes > 0
        assert [x.payload for x in m.records()] == ["kept"]
        m.deposit("after recovery", [0.0, 1.0], t=3.0)
    assert path.read_bytes().startswith(good)


def test_complete_corrupt_line_refuses_to_open(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(Config(path=path)) as m:
        m.deposit("one", [1.0, 0.0], t=1.0)
        m.deposit("two", [0.0, 1.0], t=2.0)
    data = bytearray(path.read_bytes())
    lines = bytes(data).split(b"\n")
    lines[1] = lines[1].replace(b"one", b"ONE")  # payload tampered, checksum stale
    path.write_bytes(b"\n".join(lines))
    with pytest.raises(JournalCorruptError) as err:
        Substrate(Config(path=path))
    assert err.value.line_no == 2


def test_repair_quarantines_the_damaged_suffix(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(Config(path=path)) as m:
        m.deposit("one", [1.0, 0.0], t=1.0)
        m.deposit("two", [0.0, 1.0], t=2.0)
    lines = path.read_bytes().split(b"\n")
    lines[2] = lines[2].replace(b"two", b"TWO")
    path.write_bytes(b"\n".join(lines))
    report = repair(path)
    assert report["events"] == 2 and report["quarantined_bytes"] > 0
    assert os.path.exists(report["quarantine_file"])
    with Substrate(Config(path=path)) as m:
        assert [x.payload for x in m.records()] == ["one"]


def test_failed_append_rolls_the_file_back(tmp_path, monkeypatch):
    path = tmp_path / "m.v5.journal"
    m = Substrate(Config(path=path))
    m.deposit("before", [1.0, 0.0], t=1.0)
    size = path.stat().st_size
    real_write = os.write
    calls = {"n": 0}

    def flaky_write(fd, data):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_write(fd, data[:10])  # partial write...
        raise OSError(28, "No space left on device")  # ...then the disk fills

    monkeypatch.setattr(os, "write", flaky_write)
    with pytest.raises(OSError):
        m.deposit("lost", [0.0, 1.0], t=2.0)
    monkeypatch.setattr(os, "write", real_write)
    assert path.stat().st_size == size
    assert m.recallable_count() == 1
    m.deposit("after", [0.0, 1.0], t=3.0)
    m.close()
    with Substrate(Config(path=path)) as again:
        assert [x.payload for x in again.records()] == ["before", "after"]


def test_second_handle_in_process_is_refused(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(Config(path=path)):
        with pytest.raises(JournalLockedError):
            Substrate(Config(path=path))
        with pytest.raises(JournalLockedError):
            Substrate(Config(path=tmp_path / "." / "m.v5.journal"))  # same file, other spelling
    Substrate(Config(path=path)).close()  # released on close


def test_second_process_is_refused(tmp_path):
    path = tmp_path / "m.v5.journal"
    code = textwrap.dedent(f"""
        from moneta.v5 import Substrate, Config, JournalLockedError
        try:
            Substrate(Config(path={str(path)!r}))
            print("OPENED")
        except JournalLockedError:
            print("LOCKED")
    """)
    with Substrate(Config(path=path)):
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
    assert out.stdout.strip().splitlines()[-1] == "LOCKED"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == "OPENED"
