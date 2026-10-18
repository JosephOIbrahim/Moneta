"""WAL-lite durability for Moneta ECS and attention log.

ARCHITECTURE.md §11 deliverable list (Phase 1). MONETA.md §5 risk #4
("ECS durability on crash") mitigation.

Target: survive `kill -9` with at most 30 seconds of volatile state lost.
That bound needs a save at least every 30 seconds. ``Moneta`` saves at the
end of every ``run_sleep_pass`` and never starts the optional saver thread
(``start_background``). An embedder can also save with
``m.durability.snapshot_ecs(m.ecs)``, which is SYNAPSE's save.

Design (R1′, docs/design/R1-attention-durability.md §2)
--------------------------------------------------------

1. **Snapshot** — the ECS is serialized to a JSON file atomically
   (tmp-file + fsync + `os.replace` + directory fsync where supported).
   Snapshot replaces the previous file.
   ``start_background`` runs a daemon thread that saves every
   ``snapshot_interval`` seconds (default 30), but only once a caller
   starts it. With an attention log attached, the snapshot also records
   ``wal_applied_seqs`` (the WAL sequence numbers whose effects its rows
   hold) and ``wal_next_seq`` (an allocator hint). Both keys are optional;
   a snapshot without them is "keyless".

2. **WAL** — every `signal_attention` on a durable handle writes one line
   per entity to a write-ahead log (JSONL, each line carrying a ``seq``)
   BEFORE the signal is buffered, as one unbuffered ``os.write`` followed
   by an ``os.fsync``: a line is on disk before `signal_attention` returns
   (Round 4 F1, below). A keyed save compacts
   the WAL: it keeps every line whose seq is not in the snapshot's
   ``wal_applied_seqs``, that is, every signal the reducer has not recorded
   as applied, so undrained attention survives the save (defects B and D).
   The WAL file is removed only when a keyed save keeps no line. rc1
   deleted the whole WAL at every save, on the premise that the snapshot
   had captured its entries; that was false for undrained attention.

3. **Hydrate** — on restart, load the latest snapshot, then decide each WAL
   line once. Under a keyed snapshot, a line with a seq replays iff its seq
   is not in ``wal_applied_seqs``. A line without a seq, and every line
   under a keyless snapshot, replays iff its timestamp is strictly after
   ``snapshot_created_at`` (the rc1 rule). With no snapshot file, every
   entry line replays. The first occurrence of a duplicate seq wins
   (WARNING), and a ``wal_applied_seqs`` that is not a list of valid seqs
   counts as absent (WARNING). Hydrate writes nothing; the first save
   normalizes the WAL (step 0), and the first append terminates a torn
   tail.

4. **Consistent read** — a save pairs ``applied_seqs`` with the rows only
   if no reducer was in flight (the log's in-flight set and apply epoch).
   The reducer never takes a lock.

5. **Failure paths** — a step 0 failure, or a read still contended after
   ``SEQLOCK_READ_TIMEOUT_S``, takes the DEGRADED save: a keyless snapshot
   with rc1 semantics that leaves the WAL whole, logs ERROR and counts
   ``degraded_saves``. Deposits are saved. But a reopen while that
   snapshot is current judges every line by timestamp, so it loses every
   line whose effect the snapshot's rows lack and whose timestamp is not
   after the snapshot's (defect B, rc1-equal), until a keyed save follows.
   A compaction failure (the K path) re-raises after the keyed snapshot is
   written; the WAL keeps its applied lines, and the next save retries. A
   manager with no attached log keeps rc1's save: a keyless snapshot, then
   the WAL is unlinked, undrained attention included.

Round 4 F1: the log is forced to disk
-------------------------------------
Joe approved "forcing the log to disk"; gate 2 ruled the tier: **fsync
every WAL append**. A line is written, then fsynced, before
``signal_attention`` returns (measured on the seat box at 1.16 ms median and
2.1 ms p95 per line, against 0.011 ms unsynced; a per-call group commit was
the alternative shown). A failed fsync rejects the signal: its line is
truncated away, as for a failed write. Every tmp file a save publishes (the
snapshot's, step 0's and step 3's) is fsynced BEFORE its ``os.replace``, so
a rename never reaches the disk ahead of its data. Each ``os.replace``,
step 3's unlink and the open that may create the WAL are followed by a
directory fsync where the platform has one (``_DIR_FSYNC_SUPPORTED``). A
failed fsync inside a save raises from that save, as any save I/O failure
does: step 0 degrades the save, step 2 raises before compaction, and step 3
takes the K path (item 5).

Windows limitation: there is no directory fsync. ``os.open`` refuses a
directory, so the CRT has no handle to flush, and ``os.replace`` calls
``MoveFileExW`` without ``MOVEFILE_WRITE_THROUGH``. NTFS journals each
rename but may not have flushed that journal record when a save returns,
so a power loss shortly after a save can roll back the save's renames.
Each published file is whole either way, because it was fsynced before its
rename. R1′ therefore still assumes, on Windows, that the filesystem keeps
metadata operations in order across a power loss (NTFS's journal does):
any rolled-back suffix of a save's renames then leaves a consistent store.
A signal appended after a save whose compaction rename is rolled back
landed in the rolled-back file and is lost; whether the append's own fsync
(FlushFileBuffers) forces the earlier rename's journal record first is not
verified here. On POSIX, the directory fsyncs remove the ordering
assumption.

The "lite" in WAL-lite: no transaction framing, no checksums, no page
boundaries. A Python dict gets JSON-dumped. Correct for Phase 1 scale;
Phase 2 profiling decides whether to upgrade.

Format stability
----------------
Snapshot and WAL files are versioned via `snapshot_version` and
`wal_version` keys. Phase 3 may re-use these formats when real USD
hydration joins the loop; in that case, a format bump is a §9 Trigger 2
(spec-level surprise), not a silent change. The R1′ keys (``seq`` on a WAL
line, ``wal_applied_seqs`` and ``wal_next_seq`` in the snapshot) are
additive and optional, which is not a format bump (design §1.2): rc1
readers ignore them. Every WAL line must stay a JSON object with a string
UUID ``entity_id``, a numeric ``weight`` and a numeric ``timestamp``, so no
header or marker line may ever be written.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from time import monotonic as _monotonic
from time import sleep as _sleep
from typing import Any, List, Optional, Tuple, Union
from uuid import UUID

from .attention_log import AttentionEntry, AttentionLog
from .ecs import ECS
from .types import EntityState, Memory

_logger = logging.getLogger(__name__)

# MONETA.md §5 risk #4 target: ≤30 seconds of volatile state lost.
DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 30.0

SNAPSHOT_VERSION = 1
WAL_VERSION = 1

# Design §2.4 step 1: bound on a save's optimistic consistent read. Read
# from the module globals at every save, so tests can patch it.
SEQLOCK_READ_TIMEOUT_S = 5.0

# Join timeout of stop_background() (rc1's literal 5 s), a module constant
# so tests can patch it.
BACKGROUND_JOIN_TIMEOUT_S = 5.0

# Design §1.2 / §2.5 step 5: a valid seq is an int in [0, 2**53); a seed
# leaves at least 2**40 allocations before that limit.
SEQ_LIMIT = 2**53
SEQ_MARGIN = 2**40
_RESEED_DRAWS = 64
_RESEED_WINDOWS = 2**12  # aligned 2**40 windows below 2**52

# Parse classes of one raw WAL line (design §1.2).
_BLANK = "blank"
_UNDECODABLE = "undecodable"
_INVALID = "invalid"
_ENTRY = "entry"

_LINESEP = os.linesep.encode("ascii")

# Round 4 F1: a directory fsync makes a rename, create or unlink in that
# directory durable. POSIX only: on Windows ``os.open`` refuses a directory,
# so there is no descriptor to fsync (module docstring, "Windows
# limitation"). Read from the module globals at every call, so tests can
# run the POSIX branch on any platform.
_DIR_FSYNC_SUPPORTED = os.name != "nt"


def _fsync_dir(directory: Path) -> None:
    """fsync ``directory`` where the platform supports it (Round 4 F1).

    A no-op where ``_DIR_FSYNC_SUPPORTED`` is false (Windows). Errors
    propagate, as in ``moneta.v5.journal._fsync_dir``; the descriptor is
    closed either way.
    """
    if not _DIR_FSYNC_SUPPORTED:
        return
    fd = os.open(str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def snapshot_tmp_path(snapshot_path: Union[str, Path]) -> Path:
    """The snapshot's tmp file, derived as rc1 derives it."""
    p = Path(snapshot_path)
    return p.with_suffix(p.suffix + ".tmp")


def wal_tmp_path(wal_path: Union[str, Path]) -> Path:
    """The WAL's compaction tmp file, next to it and named after it (§2.4)."""
    p = Path(wal_path)
    return p.with_name(p.name + ".tmp")


def _is_valid_seq(v: Any) -> bool:
    """Design §1.2: ``type(v) is int`` (so no bool) and ``0 <= v < 2**53``."""
    return type(v) is int and 0 <= v < SEQ_LIMIT


def _random_base() -> int:
    """A lineage base: a multiple of 2**20 below 2**52 (design §2.5 step 5)."""
    return secrets.randbits(32) << 20


def _split_raw_lines(data: bytes) -> List[bytes]:
    """The design §1.2 raw-line grammar, shared by hydrate, step 0 and step 3.

    A raw line is a maximal run of bytes ending in ``b"\\n"`` (included),
    plus, at the end, a final NON-EMPTY run with no ``\\n``. A trailing empty
    piece is not a line, and a lone ``\\r`` never splits one.
    """
    lines: List[bytes] = []
    start = 0
    n = len(data)
    while start < n:
        nl = data.find(b"\n", start)
        if nl == -1:
            lines.append(data[start:])
            break
        lines.append(data[start : nl + 1])
        start = nl + 1
    return lines


def _read_wal_bytes(path: Path) -> Optional[bytes]:
    """The WAL's bytes, or None if it does not exist (zero raw lines)."""
    try:
        with open(path, "rb") as fp:
            return fp.read()
    except FileNotFoundError:
        return None


def _classify(
    raw: bytes,
) -> Tuple[str, Optional[AttentionEntry], Optional[int], Optional[BaseException]]:
    """Class one raw line (design §1.2): ``(class, entry, seq, error)``.

    ``invalid`` covers every exception rc1's field parse can raise on a
    decodable line (KeyError, TypeError and ValueError as tabled; also
    AttributeError for a non-string UUID and OverflowError for a huge int
    weight), plus a UnicodeDecodeError. Hydrate re-raises it unchanged.
    """
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        return _INVALID, None, None, exc
    if not text:
        return _BLANK, None, None, None
    try:
        d = json.loads(text)
    except json.JSONDecodeError as exc:
        return _UNDECODABLE, None, None, exc
    try:
        entry = AttentionEntry(
            UUID(d["entity_id"]),
            float(d["weight"]),
            float(d["timestamp"]),
        )
    except Exception as exc:  # noqa: BLE001 - rc1 raised whatever this raises
        return _INVALID, None, None, exc
    seq = d.get("seq")
    return _ENTRY, entry, (seq if _is_valid_seq(seq) else None), None


def _serialize_line(entry: AttentionEntry, seq: int) -> bytes:
    """One WAL line: rc1's keys in rc1's order plus ``seq``, ``os.linesep``."""
    line = json.dumps(
        {
            "wal_version": WAL_VERSION,
            "entity_id": str(entry.entity_id),
            "weight": entry.weight,
            "timestamp": entry.timestamp,
            "seq": seq,
        }
    )
    return (line + os.linesep).encode("utf-8")


def _terminated(raw: bytes) -> bytes:
    """A raw line written back unchanged, with a terminator if it had none."""
    return raw if raw.endswith(b"\n") else raw + _LINESEP


def _unlink_quiet(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _build_rows(ecs: ECS) -> List[dict]:
    """Snapshot rows, exactly as rc1 builds them."""
    rows = []
    for memory in ecs.iter_rows():
        rows.append(
            {
                "entity_id": str(memory.entity_id),
                "payload": memory.payload,
                "semantic_vector": list(memory.semantic_vector),
                "utility": memory.utility,
                "attended_count": memory.attended_count,
                "protected_floor": memory.protected_floor,
                "last_evaluated": memory.last_evaluated,
                "state": int(memory.state),
                "usd_link": None
                if memory.usd_link is None
                else str(memory.usd_link),
            }
        )
    return rows


def _read_seq_keys(snapshot: dict) -> Tuple[bool, set, Optional[int]]:
    """Read ``wal_applied_seqs`` and ``wal_next_seq`` under the §1.2 type rules.

    Returns ``(key_present, A_valid, next_hint)``. Never raises: rc1 opens a
    store whatever these keys hold, and so must this.
    """
    a_valid: set = set()
    key_present = False
    if "wal_applied_seqs" in snapshot:
        raw = snapshot["wal_applied_seqs"]
        if isinstance(raw, list):
            valid = [v for v in raw if _is_valid_seq(v)]
            a_valid = set(valid)
            n_bad = len(raw) - len(valid)
            if n_bad == 0:
                key_present = True
            else:
                _logger.warning(
                    "durability.hydrate ignoring wal_applied_seqs: %d of %d "
                    "elements are not valid seqs; every WAL line is judged by "
                    "timestamp",
                    n_bad,
                    len(raw),
                )
        else:
            _logger.warning(
                "durability.hydrate ignoring wal_applied_seqs: not a list (%s); "
                "every WAL line is judged by timestamp",
                type(raw).__name__,
            )
    next_hint: Optional[int] = None
    if "wal_next_seq" in snapshot:
        v = snapshot["wal_next_seq"]
        if _is_valid_seq(v):
            next_hint = v
        else:
            _logger.warning(
                "durability.hydrate ignoring wal_next_seq=%r: not a valid seq", v
            )
    return key_present, a_valid, next_hint


def _reseed(taken: set) -> int:
    """Design §2.5 step 5: a base whose ``[b, b + 2**40)`` misses ``taken``."""
    for _ in range(_RESEED_DRAWS):
        b = _random_base()
        if not any(b <= s < b + SEQ_MARGIN for s in taken):
            return b
    occupied = {s // SEQ_MARGIN for s in taken}
    for k in range(_RESEED_WINDOWS):
        if k not in occupied:
            return k * SEQ_MARGIN
    raise RuntimeError("cannot reseed the WAL sequence allocator")


class _Step0Error(RuntimeError):
    """The WAL no longer lines up with the disposition recorded at hydrate."""


class DurabilityManager:
    """Coordinates ECS snapshots and attention-log WAL for crash recovery.

    Locks: ``_lock`` guards the WAL descriptor, the seq allocator, the
    tombstones and ``_closed``; ``_save_lock`` serializes ``snapshot_ecs``
    and ``close()``. The global order is ``_save_lock`` -> ``_lock``. The
    signal path takes only ``_lock``; the reducer takes neither.
    """

    def __init__(
        self,
        snapshot_path: Path,
        wal_path: Path,
        snapshot_interval: float = DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        self._wal_path = Path(wal_path)
        self._snapshot_tmp = snapshot_tmp_path(self._snapshot_path)
        self._wal_tmp = wal_tmp_path(self._wal_path)
        self._snapshot_interval = snapshot_interval
        self._last_snapshot_ts: float = 0.0
        # Raw append descriptor, opened lazily on the first append (§2.2).
        self._wal_fd: Optional[int] = None
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()
        # Seq allocator: read and incremented only under _lock (and by
        # hydrate, single-threaded, before the handle is published).
        self._next_seq: Optional[int] = None
        # Tombstoned seqs: failed appends and interrupted buffer appends.
        self._void_seqs: set[int] = set()
        self._closed: bool = False
        self._attached: Optional[Tuple[AttentionLog, ECS]] = None
        # Per raw line of the WAL as found at hydrate: None (drop) or
        # (seq, rewrite). Empty when nothing needs normalizing (§2.5 step 7).
        self._disposition: List[Optional[Tuple[int, bool]]] = []
        self.degraded_saves: int = 0
        self._stop_event: Optional[threading.Event] = None
        self._bg_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Attachment
    # ------------------------------------------------------------------

    def attach(self, log: AttentionLog, ecs: ECS) -> None:
        """Pair the handle's attention log with the ECS its reducer writes.

        Called by ``Moneta.__init__`` after hydrate. ``snapshot_ecs`` and
        ``start_background`` then accept only this ECS (design §2.4).
        """
        self._attached = (log, ecs)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot_ecs(self, ecs: ECS) -> None:
        """Atomically write ECS state to `snapshot_path`, then compact the WAL.

        With an attention log attached (design §2.4): step 0 normalizes the
        WAL found at hydrate, step 1 reads the rows and the applied seqs
        consistently, step 2 writes the keyed snapshot, step 3 keeps every
        WAL line whose seq it does not cover, step 4 releases the covered
        seqs. A step 0 failure or a step 1 timeout writes a keyless snapshot
        instead and leaves the WAL whole (``degraded_saves``). A step 3
        failure re-raises after the snapshot is written. Every tmp file is
        fsynced before its ``os.replace``, and each ``os.replace`` (and
        step 3's unlink) is followed by a directory fsync where supported
        (Round 4 F1).

        Raises ``ValueError`` if the manager is closed or if ``ecs`` is not
        the attached ECS, before writing anything. Without an attached log
        this is rc1's save: a keyless snapshot, then the WAL is unlinked.
        """
        with self._save_lock:
            if self._closed:
                raise ValueError("durability manager is closed")
            attached = self._attached
            if attached is None:
                self._snapshot_unattached(ecs)
                return
            log, attached_ecs = attached
            if ecs is not attached_ecs:
                raise ValueError(
                    "snapshot_ecs: ecs is not the ECS attached to this "
                    "handle's attention log; pass the handle's own ecs"
                )
            self._snapshot_attached(log, ecs)

    def _write_snapshot(self, snapshot: dict) -> None:
        """tmp -> fsync -> os.replace, as rc1, then a directory fsync (F1)."""
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._snapshot_tmp
        with open(tmp_path, "w", encoding="utf-8") as fp:
            json.dump(snapshot, fp)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, self._snapshot_path)
        self._last_snapshot_ts = snapshot["snapshot_created_at"]
        _fsync_dir(self._snapshot_path.parent)

    def _snapshot_unattached(self, ecs: ECS) -> None:
        """rc1's save, for a manager with no attached log (design §2.4)."""
        rows = _build_rows(ecs)
        now = time.time()
        self._write_snapshot(
            {
                "snapshot_version": SNAPSHOT_VERSION,
                "snapshot_created_at": now,
                "rows": rows,
            }
        )
        with self._lock:
            # This unlink drops every WAL line, undrained attention included
            # (defect B). rc1's comment here said "everything before `now`
            # is captured in the snapshot", which holds for applied
            # attention only. Moneta always attaches its log, so only a bare
            # DurabilityManager reaches this path.
            self._close_wal_fd_locked()
            try:
                os.unlink(self._wal_path)
            except FileNotFoundError:
                pass
            self._disposition = []
        _logger.info(
            "durability.snapshot path=%s n=%d", self._snapshot_path, ecs.n
        )

    def _snapshot_attached(self, log: AttentionLog, ecs: ECS) -> None:
        # Step 0: normalize the WAL as found at hydrate.
        if self._disposition:
            try:
                self._normalize_wal()
            except Exception as exc:  # noqa: BLE001 - degrade, never skip
                _logger.error(
                    "durability.snapshot step 0 (WAL normalization) failed: "
                    "%r; degrading this save",
                    exc,
                )
                self._degraded_save(ecs, f"step 0 failed: {exc!r}")
                return

        # Step 1: consistent read, optimistic and bounded.
        deadline = _monotonic() + SEQLOCK_READ_TIMEOUT_S
        while True:
            e1 = log._apply_epoch
            if not log._inflight:
                rows = _build_rows(ecs)
                with self._lock:
                    void = frozenset(self._void_seqs)
                applied = frozenset(log.applied_seqs) | void
                if not log._inflight and log._apply_epoch is e1:
                    break
            if _monotonic() >= deadline:
                in_flight = len(log._inflight)
                moved = log._apply_epoch is not e1
                _logger.error(
                    "durability.snapshot consistent read timed out after "
                    "%.3fs (%d reducer(s) in flight, epoch moved=%s)",
                    SEQLOCK_READ_TIMEOUT_S,
                    in_flight,
                    moved,
                )
                self._degraded_save(ecs, "step 1 timed out")
                return
            _sleep(0)
        with self._lock:
            if self._next_seq is None:  # never hydrated: seed a lineage base
                self._next_seq = _random_base()
            nxt = self._next_seq

        # Step 2: the keyed snapshot.
        now = time.time()
        self._write_snapshot(
            {
                "snapshot_version": SNAPSHOT_VERSION,
                "snapshot_created_at": now,
                "rows": rows,
                "wal_applied_seqs": sorted(applied),
                "wal_next_seq": nxt,
            }
        )

        # Step 3: compact. On failure: skip step 4 and re-raise (the K path).
        try:
            self._compact_wal(applied)
        except BaseException as exc:
            _logger.error(
                "durability.snapshot WAL compaction failed: %r; the snapshot "
                "is written, the WAL keeps its applied lines, and the next "
                "save retries",
                exc,
            )
            raise

        # Step 4: release, only after step 3 succeeded.
        log.applied_seqs.difference_update(applied)
        with self._lock:
            self._void_seqs.difference_update(applied)
        _logger.info(
            "durability.snapshot path=%s n=%d", self._snapshot_path, ecs.n
        )

    def _degraded_save(self, ecs: ECS, entry: str) -> None:
        """rc1 semantics: a keyless snapshot; the WAL, the disposition and
        ``applied_seqs`` are left as they stand (design §2.4)."""
        rows = _build_rows(ecs)
        now = time.time()
        self._write_snapshot(
            {
                "snapshot_version": SNAPSHOT_VERSION,
                "snapshot_created_at": now,
                "rows": rows,
            }
        )
        self.degraded_saves += 1
        _logger.error(
            "durability.snapshot DEGRADED (%s): wrote a keyless snapshot and "
            "left the WAL whole; until a keyed save, a reopen judges every WAL "
            "line by timestamp and loses pending lines with ts <= %.6f "
            "(degraded_saves=%d)",
            entry,
            now,
            self.degraded_saves,
        )

    def _normalize_wal(self) -> None:
        """Step 0 (design §2.4): apply the hydrate-time disposition."""
        with self._lock:
            self._close_wal_fd_locked()
            data = _read_wal_bytes(self._wal_path)
            if data is None:  # absent: nothing left to normalize
                self._disposition = []
                return
            raw_lines = _split_raw_lines(data)
            disposition = self._disposition
            prefix_len = len(disposition)
            if len(raw_lines) < prefix_len:
                raise _Step0Error(
                    f"the WAL has {len(raw_lines)} raw lines, fewer than the "
                    f"{prefix_len} found at hydrate; it was truncated outside "
                    f"this handle"
                )
            tmp = self._wal_tmp
            try:
                with open(tmp, "wb") as fp:
                    for i, raw in enumerate(raw_lines):
                        if i >= prefix_len:  # appended since hydrate
                            fp.write(_terminated(raw))
                            continue
                        action = disposition[i]
                        if action is None:
                            continue
                        seq, rewrite = action
                        if not rewrite:
                            fp.write(_terminated(raw))
                            continue
                        cls, entry, _old, _err = _classify(raw)
                        if cls != _ENTRY or entry is None:
                            raise _Step0Error(
                                f"raw line {i} is no longer an entry ({cls})"
                            )
                        fp.write(_serialize_line(entry, seq))
                    fp.flush()
                    os.fsync(fp.fileno())  # F1: the data before the rename
                os.replace(tmp, self._wal_path)
            except BaseException:
                _unlink_quiet(tmp)
                raise
            # Cleared before the directory fsync: the WAL is normalized now,
            # so a sync failure must not leave a disposition to re-apply.
            self._disposition = []
            _fsync_dir(self._wal_path.parent)

    def _compact_wal(self, applied: frozenset) -> None:
        """Step 3 (design §2.4): keep every entry line whose seq is not in
        ``applied``; drop blank, undecodable and invalid lines."""
        with self._lock:
            self._close_wal_fd_locked()
            data = _read_wal_bytes(self._wal_path)
            raw_lines = _split_raw_lines(data) if data is not None else []
            out: List[bytes] = []
            n_undecodable = n_invalid = n_foreign = 0
            for raw in raw_lines:
                cls, entry, seq, _err = _classify(raw)
                if cls == _BLANK:
                    continue
                if cls == _UNDECODABLE:
                    n_undecodable += 1
                    continue
                if cls == _INVALID or entry is None:
                    n_invalid += 1
                    continue
                if seq is None:  # only a foreign writer leaves one here
                    seq = self._alloc_seq_locked()
                    n_foreign += 1
                    out.append(_serialize_line(entry, seq))
                    continue
                if seq in applied:
                    continue
                out.append(_terminated(raw))
            if n_undecodable:
                _logger.warning(
                    "durability.snapshot dropped %d undecodable WAL line(s)",
                    n_undecodable,
                )
            if n_invalid:
                _logger.error(
                    "durability.snapshot dropped %d invalid WAL line(s) that no "
                    "reader can replay",
                    n_invalid,
                )
            if n_foreign:
                _logger.warning(
                    "durability.snapshot gave %d foreign WAL line(s) without a "
                    "seq a fresh seq; each replays once at the next reopen",
                    n_foreign,
                )
            if not out:
                try:
                    os.unlink(self._wal_path)
                except FileNotFoundError:
                    pass
                _fsync_dir(self._wal_path.parent)  # F1
                return
            tmp = self._wal_tmp
            try:
                with open(tmp, "wb") as fp:
                    fp.writelines(out)
                    fp.flush()
                    os.fsync(fp.fileno())  # F1: the data before the rename
                os.replace(tmp, self._wal_path)
            except BaseException:
                _unlink_quiet(tmp)
                raise
            _fsync_dir(self._wal_path.parent)  # F1

    # ------------------------------------------------------------------
    # WAL
    # ------------------------------------------------------------------

    def _close_wal_fd_locked(self) -> None:
        fd = self._wal_fd
        self._wal_fd = None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def _alloc_seq_locked(self) -> int:
        if self._next_seq is None:  # a manager that was never hydrated
            self._next_seq = _random_base()
        seq = self._next_seq
        self._next_seq = seq + 1
        return seq

    def _last_wal_byte(self) -> bytes:
        """The WAL's last byte, through a separate handle (design §2.2)."""
        with open(self._wal_path, "rb") as fp:
            fp.seek(-1, os.SEEK_END)
            return fp.read(1)

    def wal_append(self, entry: AttentionEntry) -> int:
        """Append one attention entry to the WAL; return its seq (design §2.2).

        One unbuffered ``os.write`` of the whole line, then ``os.fsync``,
        under ``_lock`` (Round 4 F1, gate 2 tier: every append), so the line
        is on disk before the signal is acknowledged. The open that may
        create the WAL also fsyncs its directory where supported. On any
        exception (a failed fsync included) or a short write the file is
        truncated back to its size before the write and the descriptor is
        closed, so a failed append leaves no line behind (if the truncate
        also fails, the seq is tombstoned). The original exception
        propagates.

        Raises ``ValueError("durability manager is closed")`` after
        ``close()``.
        """
        with self._lock:
            if self._closed:
                raise ValueError("durability manager is closed")
            if self._wal_fd is None:
                self._wal_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(
                    self._wal_path,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_APPEND
                    | getattr(os, "O_BINARY", 0),
                )
                try:  # nothing may leak fd before it is published
                    size = os.fstat(fd).st_size
                    if size > 0 and self._last_wal_byte() != b"\n":
                        os.write(fd, _LINESEP)  # terminate a torn tail first
                    # F1: this open may have created the WAL; its directory
                    # entry must be durable before any line in it is.
                    _fsync_dir(self._wal_path.parent)
                except BaseException:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    raise
                self._wal_fd = fd
            seq = self._alloc_seq_locked()  # allocated before the write
            data = _serialize_line(entry, seq)
            fd = self._wal_fd
            pre = os.fstat(fd).st_size
            ok = False
            try:
                n = os.write(fd, data)
                if n != len(data):
                    raise OSError(
                        f"short WAL write ({n} of {len(data)} bytes)"
                    )
                os.fsync(fd)  # F1: on disk before the signal is acknowledged
                ok = True
            finally:
                if not ok:  # any exception, including an async one
                    self._wal_fd = None  # FIRST: the next append reopens
                    try:
                        try:
                            os.ftruncate(fd, pre)
                        except OSError:
                            self._void_seqs.add(seq)
                            _logger.error(
                                "durability.wal_append truncate after a failed "
                                "write failed; seq %d tombstoned",
                                seq,
                            )
                    finally:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
            return seq

    def void_seq(self, seq: int) -> None:
        """Tombstone ``seq``: the next save lists it as applied (design §2.2).

        ``signal_attention`` calls this when the buffer append fails after
        the WAL write succeeded, so the line is never replayed.
        """
        with self._lock:
            self._void_seqs.add(seq)
        _logger.warning(
            "durability.void_seq seq=%d: signal interrupted after its WAL "
            "write; tombstoned",
            seq,
        )

    def wal_read(self) -> List[AttentionEntry]:
        """Read every entry line of the current WAL, in file order.

        rc1-compatible: blank lines are skipped, undecodable lines are
        skipped with a WARNING, and an invalid line raises its original
        exception. Hydrate uses the seq-aware reader instead.
        """
        data = _read_wal_bytes(self._wal_path)
        if data is None:
            return []
        entries: List[AttentionEntry] = []
        for raw in _split_raw_lines(data):
            cls, entry, _seq, err = _classify(raw)
            if cls == _INVALID and err is not None:
                raise err
            if cls == _UNDECODABLE:
                _logger.warning(
                    "skipping malformed WAL line: %s",
                    raw.decode("utf-8", "replace").strip()[:80],
                )
                continue
            if cls == _ENTRY and entry is not None:
                entries.append(entry)
        return entries

    # ------------------------------------------------------------------
    # Hydrate
    # ------------------------------------------------------------------

    def hydrate(
        self,
        native: Union[bool, str, None] = None,
        *,
        _source: Optional[str] = None,
    ) -> Tuple[ECS, List[AttentionEntry]]:
        """Load snapshot + replay WAL. Returns `(ECS, entries_to_replay)`.

        ``native`` is forwarded to both ``ECS()`` constructions (with
        ``_source``), so a reopened handle selects the decay seam exactly
        like a fresh one. The default (None) keeps the env-resolved
        behaviour for direct callers. Reads only; never writes a file.
        Delegates to ``_hydrate_with_seqs`` and drops the seqs.
        """
        ecs, replay = self._hydrate_with_seqs(native, _source=_source)
        return ecs, [entry for entry, _ in replay]

    def _hydrate_with_seqs(
        self,
        native: Union[bool, str, None] = None,
        *,
        _source: Optional[str] = None,
    ) -> Tuple[ECS, List[Tuple[AttentionEntry, int]]]:
        """Design §2.5: load the snapshot, decide every WAL line, seed the
        allocator and record the disposition for the first save's step 0.

        Returns ``(ECS, [(entry, seq), ...])`` in WAL order. Writes nothing.
        """
        # 1. The snapshot and its seq keys.
        snapshot_exists = self._snapshot_path.exists()
        if not snapshot_exists:
            _logger.info(
                "durability.hydrate no snapshot at %s; starting fresh",
                self._snapshot_path,
            )
            ecs = ECS(native, _source=_source)
            snapshot_ts = 0.0
            key_present = True
            a_valid: set = set()
            next_hint: Optional[int] = None
        else:
            with open(self._snapshot_path, "r", encoding="utf-8") as fp:
                snapshot = json.load(fp)

            ver = snapshot.get("snapshot_version")
            if ver != SNAPSHOT_VERSION:
                _logger.warning(
                    "snapshot_version=%s (expected %d); attempting best-effort load",
                    ver,
                    SNAPSHOT_VERSION,
                )

            ecs = ECS(native, _source=_source)
            snapshot_ts = float(snapshot.get("snapshot_created_at", 0.0))
            for row_data in snapshot.get("rows", []):
                memory = Memory(
                    entity_id=UUID(row_data["entity_id"]),
                    payload=row_data["payload"],
                    semantic_vector=list(row_data["semantic_vector"]),
                    utility=float(row_data["utility"]),
                    attended_count=int(row_data["attended_count"]),
                    protected_floor=float(row_data["protected_floor"]),
                    last_evaluated=float(row_data["last_evaluated"]),
                    state=EntityState(int(row_data["state"])),
                    usd_link=row_data.get("usd_link"),
                )
                ecs.hydrate_row(memory)
            key_present, a_valid, next_hint = _read_seq_keys(snapshot)

        # 2. The WAL, by raw line; an invalid line raises as in rc1.
        data = _read_wal_bytes(self._wal_path)
        raw_lines = _split_raw_lines(data) if data is not None else []
        parsed: List[Tuple[str, Optional[AttentionEntry], Optional[int]]] = []
        for raw in raw_lines:
            cls, entry, seq, err = _classify(raw)
            if cls == _INVALID and err is not None:
                raise err
            if cls == _UNDECODABLE:
                _logger.warning(
                    "skipping malformed WAL line: %s",
                    raw.decode("utf-8", "replace").strip()[:80],
                )
            parsed.append((cls, entry, seq))

        # 3 and 4. Decide each line; the first occurrence of a seq wins.
        wal_seqs: set = set()
        decisions: List[Optional[Tuple[AttentionEntry, Optional[int]]]] = []
        n_entries = n_dup = n_seq_lines = 0
        for cls, entry, seq in parsed:
            if cls != _ENTRY or entry is None:
                decisions.append(None)
                continue
            n_entries += 1
            if seq is not None:
                n_seq_lines += 1
                if seq in wal_seqs:
                    n_dup += 1
                    _logger.warning(
                        "durability.hydrate duplicate WAL seq %d dropped "
                        "(the first occurrence wins)",
                        seq,
                    )
                    decisions.append(None)
                    continue
                wal_seqs.add(seq)
            if key_present and seq is not None:
                replay_it = seq not in a_valid
            else:
                replay_it = entry.timestamp > snapshot_ts
            decisions.append((entry, seq) if replay_it else None)

        # 5. Seed the allocator.
        sources: List[int] = []
        if next_hint is not None:
            sources.append(next_hint)
        if a_valid:
            sources.append(max(a_valid) + 1)
        if wal_seqs:
            sources.append(max(wal_seqs) + 1)
        seed = max(sources) if sources else _random_base()
        if seed > SEQ_LIMIT - SEQ_MARGIN:
            _logger.error(
                "durability.hydrate WAL seq seed %d (from wal_next_seq=%r, "
                "max applied=%r, max WAL seq=%r) leaves fewer than 2**40 seqs "
                "below 2**53; reseeding from a random base",
                seed,
                next_hint,
                max(a_valid) if a_valid else None,
                max(wal_seqs) if wal_seqs else None,
            )
            seed = _reseed(a_valid | wal_seqs)
        next_seq = seed

        # 6 and 7. Fresh seqs for replayed lines without one; the disposition.
        replay: List[Tuple[AttentionEntry, int]] = []
        disposition: List[Optional[Tuple[int, bool]]] = []
        changed = False
        for decision in decisions:
            if decision is None:
                disposition.append(None)
                changed = True
                continue
            entry, seq = decision
            if seq is None:
                seq = next_seq
                next_seq += 1
                disposition.append((seq, True))
                changed = True
            else:
                disposition.append((seq, False))
            replay.append((entry, seq))
        self._next_seq = next_seq
        self._disposition = disposition if changed else []

        # 8. A keyless snapshot over seq-bearing lines.
        if snapshot_exists and not key_present and n_seq_lines:
            _logger.warning(
                "durability.hydrate snapshot has no usable wal_applied_seqs but "
                "%d WAL line(s) carry a seq: an rc1 save, a degraded save or a "
                "foreign rewrite happened; lines are judged by timestamp",
                n_seq_lines,
            )

        _logger.info(
            "durability.hydrate n=%d wal_total=%d wal_replay=%d "
            "wal_duplicates=%d keyed=%s",
            ecs.n,
            n_entries,
            len(replay),
            n_dup,
            key_present,
        )
        return ecs, replay

    # ------------------------------------------------------------------
    # Background thread (optional)
    # ------------------------------------------------------------------

    def start_background(self, ecs: ECS) -> None:
        """Start a daemon thread that snapshots every `snapshot_interval` seconds.

        Raises ``ValueError`` if the manager is closed or if ``ecs`` is not
        the attached ECS. Returns early only while a previous saver thread
        is still alive.
        """
        if self._closed:
            raise ValueError("durability manager is closed")
        attached = self._attached
        if attached is not None and ecs is not attached[1]:
            raise ValueError(
                "start_background: ecs is not the ECS attached to this "
                "handle's attention log; pass the handle's own ecs"
            )
        if self._bg_thread is not None and self._bg_thread.is_alive():
            return
        stop = threading.Event()  # captured: _run never reads _stop_event
        interval = self._snapshot_interval

        def _run() -> None:
            while not stop.wait(interval):
                try:
                    self.snapshot_ecs(ecs)
                except Exception:  # noqa: BLE001
                    _logger.exception("background snapshot failed")

        thread = threading.Thread(
            target=_run, daemon=True, name="moneta-snapshot"
        )
        self._stop_event = stop
        self._bg_thread = thread
        thread.start()
        _logger.info(
            "durability.start_background interval=%.1fs", self._snapshot_interval
        )

    def stop_background(self) -> None:
        """Signal the saver thread and join it for ``BACKGROUND_JOIN_TIMEOUT_S``.

        The thread and its event are cleared only once the thread has
        exited. After a timed-out join both stay set; the thread exits on
        its own event after its save returns.
        """
        stop = self._stop_event
        thread = self._bg_thread
        if stop is not None:
            stop.set()
        if thread is None:
            self._stop_event = None
            return
        thread.join(timeout=BACKGROUND_JOIN_TIMEOUT_S)
        if thread.is_alive():
            _logger.warning(
                "durability.stop_background: the snapshot thread is still "
                "running after %.1fs; it exits after its save returns",
                BACKGROUND_JOIN_TIMEOUT_S,
            )
            return
        self._bg_thread = None
        self._stop_event = None

    def close(self) -> None:
        """Stop the saver, then refuse every later append, save or start.

        Takes ``_save_lock`` (so a save in flight finishes first), then
        ``_lock``; sets ``_closed`` and closes the WAL descriptor.
        Idempotent.
        """
        self.stop_background()
        with self._save_lock:
            with self._lock:
                self._closed = True
                self._close_wal_fd_locked()
