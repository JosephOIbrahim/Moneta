"""The journal: Moneta v5's only source of truth.

Every state change is one framed, checksummed line appended to a single
file. Everything else in v5 (record state, utility anchors, the vector
index, USD projections) is *derived* by folding this file, and can be
thrown away and rebuilt from it.

Frame format (one event per line)::

    <crc32 as 8 lowercase hex> <canonical JSON>\\n

The JSON always carries ``"seq"``, a gap-free integer starting at 1. The
CRC covers the JSON bytes only.

Recovery rules on open
----------------------
- A final line with **no trailing newline** is an interrupted append. It
  is truncated away and the handle reports ``recovered_tail_bytes``.
- Any *complete* line that fails its CRC, fails to parse, or breaks the
  seq sequence is corruption. Opening raises :class:`JournalCorruptError`
  naming the line. Nothing is skipped silently. :func:`repair` is the
  explicit operator tool: it keeps the valid prefix and moves everything
  from the first bad line onward into a quarantine file beside it.

Exclusivity
-----------
A :class:`FileJournal` takes an OS-level exclusive lock on a sidecar
``<journal>.lock`` file (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on
Windows) plus an in-process registry keyed by the *resolved path*. Two
handles, in one process or two, cannot open the same journal. This
replaces v1's URI-keyed registry, which let two URIs share one snapshot
file and silently lose writes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

FORMAT = "moneta.v5.journal/1"

_OPEN_PATHS: set = set()
_OPEN_PATHS_LOCK = threading.Lock()


class JournalError(RuntimeError):
    """Base class for journal failures."""


class JournalCorruptError(JournalError):
    """A complete journal line failed validation. Nothing was skipped."""

    def __init__(self, path: Path, line_no: int, offset: int, reason: str) -> None:
        self.path = path
        self.line_no = line_no
        self.offset = offset
        self.reason = reason
        super().__init__(
            f"journal {path} is corrupt at line {line_no} (byte {offset}): {reason}. "
            f"Use moneta.v5.journal.repair() to quarantine the damaged suffix."
        )


class JournalLockedError(JournalError):
    """Another live handle, in this process or another, holds this journal."""


# ----------------------------------------------------------------------
# Framing
# ----------------------------------------------------------------------


def encode_frame(event: dict[str, Any]) -> bytes:
    body = json.dumps(
        event, separators=(",", ":"), sort_keys=True, allow_nan=False, ensure_ascii=False
    ).encode("utf-8")
    return b"%08x " % zlib.crc32(body) + body + b"\n"


def decode_frame(line: bytes) -> dict[str, Any]:
    """Decode one complete line (without its newline). Raises ValueError."""
    if len(line) < 10 or line[8:9] != b" ":
        raise ValueError("malformed frame header")
    try:
        expected = int(line[:8], 16)
    except ValueError as exc:
        raise ValueError("malformed checksum") from exc
    body = line[9:]
    if zlib.crc32(body) != expected:
        raise ValueError("checksum mismatch")
    event = json.loads(body.decode("utf-8"))
    if not isinstance(event, dict) or not isinstance(event.get("seq"), int):
        raise ValueError("event is not an object with an integer seq")
    return event


def scan(data: bytes, path: Path) -> tuple[list[dict[str, Any]], int, int]:
    """Validate a journal byte string.

    Returns ``(events, good_length, torn_tail_bytes)``. ``good_length`` is
    the byte length of the valid prefix. Raises JournalCorruptError on
    any complete bad line.
    """
    events: list[dict[str, Any]] = []
    offset = 0
    line_no = 0
    expected_seq = 1
    n = len(data)
    while offset < n:
        nl = data.find(b"\n", offset)
        if nl == -1:
            # Interrupted append: bytes with no terminating newline.
            return events, offset, n - offset
        line_no += 1
        line = data[offset:nl]
        try:
            event = decode_frame(line)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JournalCorruptError(path, line_no, offset, str(exc)) from None
        if event["seq"] != expected_seq:
            raise JournalCorruptError(
                path, line_no, offset, f"seq {event['seq']} where {expected_seq} expected"
            )
        events.append(event)
        expected_seq += 1
        offset = nl + 1
    return events, offset, 0


# ----------------------------------------------------------------------
# OS lock helpers
# ----------------------------------------------------------------------


def _lock_fd(fd: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows only
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise JournalLockedError(str(exc)) from exc
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise JournalLockedError(str(exc)) from exc


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":  # pragma: no cover
        import msvcrt

        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":  # pragma: no cover - directory fsync is not available on Windows
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# ----------------------------------------------------------------------
# Journals
# ----------------------------------------------------------------------


class MemoryJournal:
    """Ephemeral journal for tests and throwaway handles. Same contract, no disk."""

    path: Path | None = None
    recovered_tail_bytes = 0

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def last_seq(self) -> int:
        return len(self._events)

    def events(self) -> Iterator[dict[str, Any]]:
        return iter(list(self._events))

    def append(self, event: dict[str, Any]) -> int:
        with self._lock:
            seq = len(self._events) + 1
            framed = dict(event, seq=seq)
            encode_frame(framed)  # same validation as the file journal (rejects NaN etc.)
            self._events.append(json.loads(json.dumps(framed)))
            return seq

    def rewrite(self, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        with self._lock:
            out = []
            for e in self._events:
                new = transform(dict(e))
                new["seq"] = e["seq"]
                encode_frame(new)
                out.append(new)
            self._events = out

    def sync(self) -> None:
        pass

    def close(self) -> None:
        pass


class FileJournal:
    """Append-only, checksummed, fsync'd journal file with exclusive ownership."""

    def __init__(self, path: Path, *, fsync: bool = True) -> None:
        self.path = Path(path).resolve()
        self._fsync = fsync
        self._lock = threading.Lock()
        self._fd: int | None = None
        self._lock_fd: int | None = None
        self._registered = False
        self._broken: str | None = None
        self.recovered_tail_bytes = 0

        key = str(self.path)
        with _OPEN_PATHS_LOCK:
            if key in _OPEN_PATHS:
                raise JournalLockedError(f"journal {self.path} is already open in this process")
            _OPEN_PATHS.add(key)
            self._registered = True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.path.with_name(self.path.name + ".lock")
            self._lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                _lock_fd(self._lock_fd)
            except JournalLockedError as exc:
                raise JournalLockedError(
                    f"journal {self.path} is locked by another process ({exc})"
                ) from None

            data = self.path.read_bytes() if self.path.exists() else b""
            initial, good, torn = scan(data, self.path)
            self._last_seq = len(initial)
            # Handed to the first events() call (the fold at open), then
            # dropped: the journal never holds a second copy of the store.
            self._initial: list[dict[str, Any]] | None = initial
            self._fd = os.open(
                str(self.path), os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644
            )
            if torn:
                os.ftruncate(self._fd, good)
                os.fsync(self._fd)
                self.recovered_tail_bytes = torn
                _logger.warning(
                    "journal %s: truncated %d bytes of an interrupted append", self.path, torn
                )
            os.lseek(self._fd, 0, os.SEEK_END)
            self._size = good
            if data == b"" and fsync:
                _fsync_dir(self.path.parent)
        except BaseException:
            self._release()
            raise

    # -- reading -------------------------------------------------------

    @property
    def last_seq(self) -> int:
        return self._last_seq

    def events(self) -> Iterator[dict[str, Any]]:
        """Every event in order, validated. Re-reads the file after open."""
        with self._lock:
            if self._initial is not None and len(self._initial) == self._last_seq:
                events, self._initial = self._initial, None
                return iter(events)
            self._initial = None
            data = self.path.read_bytes()[: self._size]
            events, _, _ = scan(data, self.path)
            return iter(events)

    # -- writing -------------------------------------------------------

    def _writable(self) -> int:
        if self._broken is not None:
            raise JournalError(
                f"journal {self.path} refused further writes: {self._broken}. "
                f"Close and reopen it; recovery on open will repair the tail."
            )
        if self._fd is None:
            raise JournalError("journal is closed")
        return self._fd

    def append(self, event: dict[str, Any]) -> int:
        with self._lock:
            self._writable()
            seq = self._last_seq + 1
            framed = dict(event, seq=seq)
            frame = encode_frame(framed)  # raises before any byte is written
            start = self._size
            try:
                written = 0
                while written < len(frame):
                    written += os.write(self._fd, frame[written:])
                if self._fsync:
                    os.fsync(self._fd)
            except BaseException:
                # Roll the file back so a failed append can never become
                # mid-file corruption for the next append.
                try:
                    os.ftruncate(self._fd, start)
                    os.lseek(self._fd, start, os.SEEK_SET)
                except OSError as rollback_error:
                    # The file may now end in a partial frame. Appending after
                    # it would turn a torn tail into mid-file corruption, so
                    # this handle stops writing; reopening truncates the tail.
                    self._broken = f"rollback after a failed append failed ({rollback_error})"
                    _logger.exception("journal %s: %s", self.path, self._broken)
                raise
            self._size = start + len(frame)
            self._last_seq = seq
            return seq

    def sync(self) -> None:
        with self._lock:
            os.fsync(self._writable())

    def rewrite(self, transform: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        """Atomically rewrite every event through ``transform`` (seq preserved).

        Used only by compaction, e.g. to physically remove erased payloads.
        Writes a temp file, fsyncs it, replaces the journal, fsyncs the dir.
        """
        with self._lock:
            self._writable()
            self._initial = None
            old, _, _ = scan(self.path.read_bytes()[: self._size], self.path)
            new_events = []
            for event in old:
                seq = event["seq"]
                out = transform(dict(event))
                out["seq"] = seq
                new_events.append(out)
            tmp = self.path.with_name(self.path.name + ".compact.tmp")
            try:
                with open(tmp, "wb") as fp:
                    for e in new_events:
                        fp.write(encode_frame(e))
                    fp.flush()
                    os.fsync(fp.fileno())
                # Windows cannot replace a file that is open; POSIX can, and
                # keeping the old descriptor there means a failed replace
                # leaves the handle exactly as it was.
                if os.name == "nt":  # pragma: no cover
                    os.close(self._fd)
                    self._fd = None
                os.replace(tmp, self.path)
            except BaseException:
                if self._fd is None:  # pragma: no cover - Windows path
                    self._fd = os.open(str(self.path), os.O_RDWR | getattr(os, "O_BINARY", 0))
                    os.lseek(self._fd, 0, os.SEEK_END)
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            # The replace succeeded: from here on the new file is the journal.
            old_fd, self._fd = self._fd, None
            try:
                self._fd = os.open(str(self.path), os.O_RDWR | getattr(os, "O_BINARY", 0))
                self._size = os.lseek(self._fd, 0, os.SEEK_END)
            finally:
                if old_fd is not None:
                    os.close(old_fd)
            _fsync_dir(self.path.parent)

    def close(self) -> None:
        with self._lock:
            self._release()

    def _release(self) -> None:
        """Release everything; one failure never skips the rest."""
        fd, self._fd = self._fd, None
        lock_fd, self._lock_fd = self._lock_fd, None
        try:
            if fd is not None:
                os.close(fd)
        finally:
            try:
                if lock_fd is not None:
                    try:
                        _unlock_fd(lock_fd)
                    finally:
                        os.close(lock_fd)
            finally:
                if self._registered:
                    with _OPEN_PATHS_LOCK:
                        _OPEN_PATHS.discard(str(self.path))
                    self._registered = False


def repair(path: Path) -> dict[str, Any]:
    """Operator tool: keep the valid prefix, quarantine the rest.

    Never deletes bytes. The damaged suffix is moved to
    ``<journal>.quarantine-<n>`` and the journal is truncated to the last
    valid line. Returns a report. Must not be called while a handle has
    the journal open.
    """
    path = Path(path).resolve()
    data = path.read_bytes()
    try:
        events, good, torn = scan(data, path)
        return {"path": str(path), "events": len(events), "quarantined_bytes": 0, "torn_tail": torn}
    except JournalCorruptError as err:
        bad_offset = err.offset
    n = 1
    while path.with_name(f"{path.name}.quarantine-{n}").exists():
        n += 1
    quarantine = path.with_name(f"{path.name}.quarantine-{n}")
    with open(quarantine, "wb") as fp:
        fp.write(data[bad_offset:])
        fp.flush()
        os.fsync(fp.fileno())
    with open(path, "r+b") as fp:
        fp.truncate(bad_offset)
        fp.flush()
        os.fsync(fp.fileno())
    events, _, _ = scan(data[:bad_offset], path)
    return {
        "path": str(path),
        "events": len(events),
        "quarantined_bytes": len(data) - bad_offset,
        "quarantine_file": str(quarantine),
    }
