"""Round 4 F1: the attention log is forced to disk.

The owner approved forcing the log to disk with the risk B fix, and gate 2
ruled the tier: fsync every WAL append (measured on one Windows
workstation at 1.16 ms median per line). These tests pin what that tier
promises in ``moneta.durability``:

- an acknowledged signal's WAL line was written, then fsynced, before
  ``signal_attention`` returned, and a failed fsync rejects the signal;
- every tmp file a save writes (the snapshot's, step 0's and step 3's) is
  fsynced BEFORE the ``os.replace`` that publishes it;
- every ``os.replace``, the WAL's creation and step 3's unlink are followed
  by a directory fsync where the platform has one. Windows has none
  (``_DIR_FSYNC_SUPPORTED`` is false there), so these tests force the POSIX
  branch on and fake its directory descriptor, which runs it on every
  platform.

``_Fs`` stands in for ``moneta.durability.os`` only, as the R1′ suite's
``_Os`` does: everything it does not override is the real module. It records
the calls in order and doubles as a power-loss model with two variants:

- ``ordered-metadata`` (NTFS-like, the worst case for data): every rename,
  create and unlink survives, but a file keeps only the bytes it held at its
  last fsync, so a rename can reach the disk before its data does;
- ``posix``: as above, and the directory keeps only the entries it held at
  its last directory fsync.

A reopen of the power-loss image must still hold every acknowledged signal.
Before F1 both variants lose it: the WAL and the compaction tmp were flushed,
never fsynced, and no directory was ever synced.
"""
from __future__ import annotations

import errno
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

import moneta.durability as dur_mod
from moneta import Moneta, MonetaConfig
from moneta.durability import snapshot_tmp_path, wal_tmp_path

_DIR_FD_BASE = 1 << 30  # far above any real descriptor


def _store(root: Path) -> MonetaConfig:
    root.mkdir(parents=True, exist_ok=True)
    return MonetaConfig(
        storage_uri=f"moneta-test://f1/{uuid4().hex}",
        snapshot_path=root / "snapshot.json",
        wal_path=root / "attention.wal.jsonl",
        half_life_seconds=3600.0,
    )


def _store_files(cfg: MonetaConfig) -> set[str]:
    assert cfg.snapshot_path is not None and cfg.wal_path is not None
    return {
        cfg.snapshot_path.name,
        snapshot_tmp_path(cfg.snapshot_path).name,
        cfg.wal_path.name,
        wal_tmp_path(cfg.wal_path).name,
    }


class _Fs:
    """Stands in for ``moneta.durability.os``; see the module docstring."""

    def __init__(self, store: Path) -> None:
        self.store = store
        self.events: list[tuple[str, ...]] = []
        self.data: dict[int, bytes] = {}  # inode -> bytes at its last fsync
        self.entries: dict[str, int] = {}  # name -> inode at the last dir fsync
        self.dir_fds: dict[int, Path] = {}
        self._next_dir_fd = _DIR_FD_BASE

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)

    def _listing(self) -> dict[str, int]:
        return {
            p.name: os.stat(p).st_ino for p in self.store.iterdir() if p.is_file()
        }

    def _name(self, fd: int) -> str:
        ino = os.fstat(fd).st_ino
        for name, i in self._listing().items():
            if i == ino:
                return name
        raise AssertionError(f"descriptor {fd} is not a file in {self.store}")

    def open(self, path: Any, flags: int, mode: int = 0o777, **kw: Any) -> int:
        if Path(path).is_dir():  # Windows cannot open one: fake its descriptor
            fd = self._next_dir_fd
            self._next_dir_fd += 1
            self.dir_fds[fd] = Path(path)
            return fd
        return os.open(path, flags, mode, **kw)

    def close(self, fd: int) -> None:
        if self.dir_fds.pop(fd, None) is None:
            os.close(fd)

    def fsync(self, fd: int) -> None:
        directory = self.dir_fds.get(fd)
        if directory is not None:
            assert directory == self.store, directory
            self.entries = self._listing()
            self.events.append(("dirsync", directory.name))
            return
        os.fsync(fd)
        name = self._name(fd)
        self.data[os.fstat(fd).st_ino] = (self.store / name).read_bytes()
        self.events.append(("fsync", name))

    def write(self, fd: int, data: bytes) -> int:
        n = os.write(fd, data)
        self.events.append(("write", self._name(fd)))
        return n

    def replace(self, src: Any, dst: Any) -> None:
        self.events.append(("replace", Path(src).name, Path(dst).name))
        os.replace(src, dst)

    def unlink(self, path: Any) -> None:
        self.events.append(("unlink", Path(path).name))
        os.unlink(path)

    def image(self, cfg: MonetaConfig, dest: Path, *, posix: bool) -> MonetaConfig:
        """What a power loss now leaves of ``cfg``'s files, as a store at ``dest``."""
        new = _store(dest)
        entries = self.entries if posix else self._listing()
        for name, ino in entries.items():
            if name in _store_files(cfg):
                (dest / name).write_bytes(self.data.get(ino, b""))
        return new


@pytest.fixture
def fs_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[MonetaConfig, _Fs]]:
    cfg = _store(tmp_path / "live")
    assert cfg.wal_path is not None
    fs = _Fs(cfg.wal_path.parent)
    monkeypatch.setattr(dur_mod, "os", fs)
    monkeypatch.setattr(dur_mod, "_DIR_FSYNC_SUPPORTED", True, raising=False)
    yield cfg, fs


def _real_fs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Back to the real ``os`` and the platform's own directory-sync rule."""
    monkeypatch.setattr(dur_mod, "os", os)
    monkeypatch.setattr(
        dur_mod, "_DIR_FSYNC_SUPPORTED", os.name != "nt", raising=False
    )


def _publish(tmp: str, final: str, directory: str) -> list[tuple[str, ...]]:
    """tmp fsynced, then renamed over ``final``, then the directory synced."""
    return [("fsync", tmp), ("replace", tmp, final), ("dirsync", directory)]


# ------------------------------------------------------------------ ordering


def test_F1_signal_is_fsynced_before_it_returns(
    fs_store: tuple[MonetaConfig, _Fs],
) -> None:
    cfg, fs = fs_store
    assert cfg.wal_path is not None
    wal, d = cfg.wal_path.name, fs.store.name
    with Moneta(cfg) as m:
        eid = m.deposit("attended", [1.0, 0.0])
        fs.events.clear()
        m.signal_attention({eid: 0.5})
        first = list(fs.events)
        fs.events.clear()
        m.signal_attention({eid: 0.25})
        second = list(fs.events)
    # The first append opens (and so may create) the WAL: its directory
    # entry is synced before any line can count as durable.
    assert first == [("dirsync", d), ("write", wal), ("fsync", wal)]
    assert second == [("write", wal), ("fsync", wal)]


def test_F1_save_fsyncs_each_tmp_before_its_replace_then_the_directory(
    fs_store: tuple[MonetaConfig, _Fs],
) -> None:
    cfg, fs = fs_store
    assert cfg.snapshot_path is not None and cfg.wal_path is not None
    snap, wal, d = cfg.snapshot_path, cfg.wal_path, fs.store.name
    with Moneta(cfg) as m:
        eid = m.deposit("attended", [1.0, 0.0])
        m.signal_attention({eid: 0.5})  # undrained: step 3 keeps its line
        fs.events.clear()
        m.durability.snapshot_ecs(m.ecs)  # SYNAPSE's bare save
        events = list(fs.events)
    assert events == [
        *_publish(snapshot_tmp_path(snap).name, snap.name, d),  # step 2
        *_publish(wal_tmp_path(wal).name, wal.name, d),  # step 3
    ]


def test_F1_step0_normalization_publishes_the_same_way(
    fs_store: tuple[MonetaConfig, _Fs],
) -> None:
    cfg, fs = fs_store
    assert cfg.snapshot_path is not None and cfg.wal_path is not None
    snap, wal, d = cfg.snapshot_path, cfg.wal_path, fs.store.name
    # An rc1 line (no seq): hydrate gives it a seq; the first save's step 0
    # rewrites the WAL with it.
    rc1 = {
        "wal_version": 1,
        "entity_id": str(uuid4()),
        "weight": 0.5,
        "timestamp": time.time(),
    }
    wal.write_bytes((json.dumps(rc1) + "\n").encode("utf-8"))
    with Moneta(cfg) as m:
        assert len(m.attention) == 1
        fs.events.clear()
        m.durability.snapshot_ecs(m.ecs)
        events = list(fs.events)
    wtmp = wal_tmp_path(wal).name
    assert events == [
        *_publish(wtmp, wal.name, d),  # step 0
        *_publish(snapshot_tmp_path(snap).name, snap.name, d),  # step 2
        *_publish(wtmp, wal.name, d),  # step 3 keeps the pending line
    ]


def test_F1_compaction_that_keeps_nothing_syncs_the_directory_after_unlink(
    fs_store: tuple[MonetaConfig, _Fs],
) -> None:
    cfg, fs = fs_store
    assert cfg.snapshot_path is not None and cfg.wal_path is not None
    snap, wal, d = cfg.snapshot_path, cfg.wal_path, fs.store.name
    with Moneta(cfg) as m:
        eid = m.deposit("attended", [1.0, 0.0])
        m.signal_attention({eid: 0.5})
        fs.events.clear()
        m.run_sleep_pass()  # applies the signal, then saves
        events = list(fs.events)
        assert m.ecs.get_memory(eid).attended_count == 1  # type: ignore[union-attr]
    assert not wal.exists()
    assert events == [
        *_publish(snapshot_tmp_path(snap).name, snap.name, d),
        ("unlink", wal.name),
        ("dirsync", d),
    ]


def test_F1_failed_fsync_rejects_the_signal_and_leaves_no_line(
    fs_store: tuple[MonetaConfig, _Fs], monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg, fs = fs_store
    assert cfg.wal_path is not None
    wal = cfg.wal_path
    real_fsync = fs.fsync

    def failing(fd: int) -> None:
        if fd not in fs.dir_fds and fs._name(fd) == wal.name:
            raise OSError(errno.EIO, "injected fsync failure")
        real_fsync(fd)

    with Moneta(cfg) as m:
        eid = m.deposit("attended", [1.0, 0.0])
        monkeypatch.setattr(fs, "fsync", failing)
        with pytest.raises(OSError, match="injected fsync failure"):
            m.signal_attention({eid: 0.5})
        assert len(m.attention) == 0  # never acknowledged, never buffered
        assert wal.read_bytes() == b""  # the written line was truncated away
        monkeypatch.setattr(fs, "fsync", real_fsync)
        m.signal_attention({eid: 0.25})  # the next append reopens and works
        assert len(m.attention) == 1
    lines = [ln for ln in wal.read_bytes().splitlines() if ln.strip()]
    assert len(lines) == 1 and json.loads(lines[0])["weight"] == 0.25


# ------------------------------------------------------- the directory sync


def test_F1_directory_fsync_is_posix_only() -> None:
    assert getattr(dur_mod, "_DIR_FSYNC_SUPPORTED", None) is (os.name != "nt")


def test_F1_directory_fsync_is_a_no_op_where_unsupported(
    fs_store: tuple[MonetaConfig, _Fs], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, fs = fs_store
    monkeypatch.setattr(dur_mod, "_DIR_FSYNC_SUPPORTED", False)
    dur_mod._fsync_dir(fs.store)
    assert fs.events == [] and fs.dir_fds == {}


def test_F1_directory_fsync_syncs_then_closes_even_on_error(
    fs_store: tuple[MonetaConfig, _Fs], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, fs = fs_store
    dur_mod._fsync_dir(fs.store)
    assert fs.events == [("dirsync", fs.store.name)] and fs.dir_fds == {}

    def boom(fd: int) -> None:
        raise OSError(errno.EIO, "injected directory fsync failure")

    monkeypatch.setattr(fs, "fsync", boom)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        dur_mod._fsync_dir(fs.store)
    assert fs.dir_fds == {}  # closed on the error path too


# --------------------------------------------------------- power-loss model


@pytest.mark.parametrize("posix", [False, True], ids=["ordered-metadata", "posix"])
def test_F1_power_loss_after_a_bare_save_keeps_pending_attention(
    fs_store: tuple[MonetaConfig, _Fs],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    posix: bool,
) -> None:
    """The compaction path: SYNAPSE's bare save republishes the WAL from
    step 3's tmp, and the power fails as the save returns."""
    cfg, fs = fs_store
    if not posix:  # the platform's own rule (no directory sync on Windows)
        monkeypatch.setattr(dur_mod, "_DIR_FSYNC_SUPPORTED", os.name != "nt")
    with Moneta(cfg) as m:
        attended = m.deposit("attended", [1.0, 0.0])
        m.durability.snapshot_ecs(m.ecs)  # save-on-add
        m.signal_attention({attended: 0.5})  # acknowledged, undrained
        m.durability.snapshot_ecs(m.ecs)  # bare save: step 3 rewrites the WAL
        after = fs.image(cfg, tmp_path / "after-power-loss", posix=posix)
    _real_fs(monkeypatch)
    with Moneta(after) as m2:
        assert m2.ecs.contains(attended)
        assert len(m2.attention) == 1  # the pending line survived
        m2.run_sleep_pass()
        assert m2.ecs.get_memory(attended).attended_count == 1  # type: ignore[union-attr]


@pytest.mark.parametrize("posix", [False, True], ids=["ordered-metadata", "posix"])
def test_F1_power_loss_right_after_a_signal_keeps_it(
    fs_store: tuple[MonetaConfig, _Fs],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    posix: bool,
) -> None:
    cfg, fs = fs_store
    if not posix:
        monkeypatch.setattr(dur_mod, "_DIR_FSYNC_SUPPORTED", os.name != "nt")
    with Moneta(cfg) as m:
        attended = m.deposit("attended", [1.0, 0.0])
        m.durability.snapshot_ecs(m.ecs)
        m.signal_attention({attended: 0.5})  # returned: acknowledged
        after = fs.image(cfg, tmp_path / "after-power-loss", posix=posix)
    _real_fs(monkeypatch)
    with Moneta(after) as m2:
        assert len(m2.attention) == 1
        m2.run_sleep_pass()
        assert m2.ecs.get_memory(attended).attended_count == 1  # type: ignore[union-attr]
