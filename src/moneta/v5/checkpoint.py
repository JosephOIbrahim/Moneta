"""Fold checkpoints: open replays only the journal's tail.

Round 4 E3 blocking condition 3 and the E1 before-5.0.0 checkpoint item.

A checkpoint is two things, written in this order:

1. A **fold snapshot file**: the complete fold state after event ``covers``,
   content-addressed by its sha256 and stored beside the journal as
   ``<journal>.checkpoints/<covers:012d>-<sha256>.fold``.
2. A journaled ``checkpoint`` event naming that file, its sha256 and
   ``covers``. A crash between the two leaves an orphan file and no event,
   which is harmless.

On open the journal walks backward from its end to the newest
``checkpoint`` event whose snapshot verifies (file present, sha256 equal,
it decodes, it covers what the event says) and replays only the events
after ``covers``. A missing or damaged snapshot is logged and the walk
falls back to an older checkpoint, and finally to a full replay from
genesis. A snapshot is derived state: deleting every one of them loses
nothing but open time.

What a checkpoint changes about open
------------------------------------
Events at or before ``covers`` are vouched for by the content-addressed
snapshot instead of being re-read: their CRCs are not re-checked at open.
Every event after ``covers`` is validated exactly as before, and a
damaged line there still raises :class:`JournalCorruptError`.
:meth:`moneta.v5.Substrate.verify` (and :func:`moneta.v5.journal.repair`)
re-read the whole journal; ``verify`` also proves that a replay from
genesis equals the live state.

Erasure
-------
A snapshot taken before an ``erase`` holds the erased payload and vector,
so it is a derived copy the erase must reach (Round 4 E4 condition 2):
``erase`` and ``compact`` delete every snapshot file. Their checkpoint
events stay in the journal, point at nothing, and open falls back.

File format
-----------
One JSON header line; one JSON line holding an array with a row per
record in fold (deposit) order; then a binary block of float64s: per
record, its vector (little-endian, the journal codec's exact values) and,
when it has one, its unit vector (native order). Unit vectors are stored
together with the summation mode that produced them; an interpreter that
sums differently (CPython <= 3.11 vs >= 3.12, see :mod:`moneta.v5.index`)
recomputes them, so a snapshot opened anywhere equals that interpreter's
own replay bit for bit.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import logging
import operator
import os
import re
import struct
import sys
from array import array
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from .model import RECALLABLE, Fold, Record, Status, _unit

_logger = logging.getLogger(__name__)

SNAPSHOT_FORMAT = "moneta.v5.fold/2"
CHECKPOINT_DIR_SUFFIX = ".checkpoints"
_COMPENSATED_SUM = sys.version_info >= (3, 12)
_NAME = re.compile(r"^(\d{12})-([0-9a-f]{64})\.fold$")
_CHUNK_BYTES = 1 << 20


class CheckpointError(RuntimeError):
    """A snapshot file failed verification."""


def checkpoint_dir(journal: Path) -> Path:
    return journal.with_name(journal.name + CHECKPOINT_DIR_SUFFIX)


def snapshot_name(covers: int, sha: str) -> str:
    return f"{covers:012d}-{sha}.fold"


# ----------------------------------------------------------------------
# Capture (under the writer lock) and encode (with it released)
# ----------------------------------------------------------------------


# Every Record field, in declaration order: a captured row is exactly
# ``Record(*row)``.
_FIELDS = tuple(f.name for f in dataclasses.fields(Record))
_row_of = operator.attrgetter(*_FIELDS)


@dataclass(frozen=True)
class FoldImage:
    """A consistent copy of fold state, cheap enough to take under the writer lock.

    Records are captured as tuples of their field values (one C-level
    ``attrgetter`` call each, ~0.2 us): attention mutates a record in
    place, but every field object a tuple shares (vector tuple, unit
    array, strings) is immutable or only ever rebound, never mutated.
    """

    header: dict[str, Any]
    records: list[tuple[Any, ...]]

    @property
    def covers(self) -> int:
        return int(self.header["covers"])


def capture(fold: Fold) -> FoldImage:
    header = {
        "format": SNAPSHOT_FORMAT,
        "covers": fold.last_seq,
        "lam": fold.lam,
        "half_life_seconds": fold.half_life_seconds,
        "dim": fold.dim if fold.dim_journaled else None,
        "dim_journaled": fold.dim_journaled,
        "live_removed": fold._live_removed,
        "repacks": fold.repacks,
        "by_key": [[k, str(v)] for k, v in fold.by_key.items()],
        "attended_since_pass": sorted(str(e) for e in fold.attended_since_pass),
        "half_life_change_pending": copy.deepcopy(fold.half_life_change_pending),
        "snapshot_shas": sorted(fold.snapshot_shas),
        "last_checkpoint": copy.deepcopy(fold.last_checkpoint),
        "compensated_sum": _COMPENSATED_SUM,
        "byteorder": sys.byteorder,
        "records": len(fold.records),
    }
    return FoldImage(header, list(map(_row_of, fold.records.values())))


_STRUCTS: dict[int, struct.Struct] = {}


def _le(n: int) -> struct.Struct:
    st = _STRUCTS.get(n)
    if st is None:
        st = _STRUCTS[n] = struct.Struct(f"<{n}d")
    return st


def _row(r: tuple[Any, ...]) -> list[Any]:
    """The JSON half of a record. Vector and unit go to the binary block."""
    return [
        str(r[0]),  # entity_id
        r[1],  # seq
        r[2],  # deposited_at
        r[3],  # payload
        None if r[4] is None else len(r[4]),  # vector length
        r[5] is not None,  # has a unit vector
        *r[6:13],  # protected_floor .. attended
        r[13].value,  # status
        *r[14:],  # status_reason, status_t, status_seq
    ]


def encode(image: FoldImage) -> Iterator[bytes]:
    """The snapshot bytes in ~1 MB chunks (one ``json.dumps`` per row).

    Encoding row by row keeps any single C call short, so a checkpoint
    taken beside live readers never holds the GIL for the whole store.
    """

    def dumps(obj: Any) -> str:
        return json.dumps(
            obj, separators=(",", ":"), sort_keys=True, allow_nan=False, ensure_ascii=False
        )

    parts: list[str] = [dumps(image.header), "\n["]
    size = 0
    for i, rec in enumerate(image.records):
        piece = dumps(_row(rec))
        parts.append(piece if i == 0 else "," + piece)
        size += len(piece)
        if size >= _CHUNK_BYTES:
            yield "".join(parts).encode("utf-8")
            parts, size = [], 0
    parts.append("]\n")
    yield "".join(parts).encode("utf-8")
    block: list[bytes] = []
    size = 0
    for rec in image.records:
        vector, unit = rec[4], rec[5]
        if vector is None:
            continue
        block.append(_le(len(vector)).pack(*vector))
        if unit is not None:
            block.append(array("d", unit).tobytes())
        size += 16 * len(vector)
        if size >= _CHUNK_BYTES:
            yield b"".join(block)
            block, size = [], 0
    yield b"".join(block)


def snapshot_bytes(fold: Fold) -> bytes:
    """The full encoded state of ``fold``. Equal bytes mean equal fold state."""
    return b"".join(encode(capture(fold)))


def write(journal: Path, image: FoldImage, *, fsync: bool = True) -> tuple[str, str]:
    """Write ``image`` content-addressed beside ``journal``. Returns ``(file name, sha256)``.

    tmp -> fsync -> atomic replace -> directory fsync. Runs with no
    substrate lock held.
    """
    directory = checkpoint_dir(journal)
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f"{image.covers:012d}.fold.tmp"
    digest = hashlib.sha256()
    try:
        with open(tmp, "wb") as fp:
            for chunk in encode(image):
                digest.update(chunk)
                fp.write(chunk)
            fp.flush()
            if fsync:
                os.fsync(fp.fileno())
        sha = digest.hexdigest()
        name = snapshot_name(image.covers, sha)
        os.replace(tmp, directory / name)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    if fsync and os.name != "nt":  # pragma: no cover - directory fsync is POSIX only
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return name, sha


# ----------------------------------------------------------------------
# Decode and load
# ----------------------------------------------------------------------


def decode(data: bytes) -> Fold:
    """Rebuild a :class:`Fold` from snapshot bytes. Raises CheckpointError."""
    try:
        head_end = data.index(b"\n")
        header = json.loads(data[:head_end].decode("utf-8"))
        if not isinstance(header, dict) or header.get("format") != SNAPSHOT_FORMAT:
            raise CheckpointError(f"not a {SNAPSHOT_FORMAT} snapshot")
        rows_end = data.index(b"\n", head_end + 1)
        rows = json.loads(data[head_end + 1 : rows_end].decode("utf-8"))
        block = memoryview(data)[rows_end + 1 :]
        if len(rows) != header["records"]:
            raise CheckpointError("record count does not match the header")
        reuse_units = (
            header["compensated_sum"] == _COMPENSATED_SUM and header["byteorder"] == sys.byteorder
        )
        fold = Fold()
        fold.lam = header["lam"]
        fold.half_life_seconds = header["half_life_seconds"]
        fold.dim = header["dim"]
        fold.dim_journaled = bool(header["dim_journaled"])
        fold.last_seq = int(header["covers"])
        fold._live_removed = int(header["live_removed"])
        fold.repacks = int(header["repacks"])
        fold.by_key = {k: UUID(v) for k, v in header["by_key"]}
        fold.attended_since_pass = {UUID(e) for e in header["attended_since_pass"]}
        fold.half_life_change_pending = header["half_life_change_pending"]
        fold.snapshot_shas = set(header["snapshot_shas"])
        fold.last_checkpoint = header["last_checkpoint"]
        records = fold.records
        live = fold.live
        statuses = {s.value: s for s in Status}
        off = 0
        for row in rows:
            n, has_unit = row[4], row[5]
            if n is None:
                vector = unit = None
            else:
                vector = _le(n).unpack_from(block, off)
                off += 8 * n
                if not has_unit:
                    unit = None
                elif reuse_units:
                    unit = array("d")
                    unit.frombytes(block[off : off + 8 * n])
                else:
                    unit = _unit(vector)
                if has_unit:
                    off += 8 * n
            status = statuses[row[13]]
            rec = Record(UUID(row[0]), *row[1:4], vector, unit, *row[6:13], status, *row[14:])
            records[rec.entity_id] = rec
            # ``live`` is exactly the recallable records in deposit order
            # (no transition ever leads back to RECALLABLE).
            if status in RECALLABLE:
                live[rec.entity_id] = rec
        if off != len(block):
            raise CheckpointError("vector block length does not match the records")
    except CheckpointError:
        raise
    except (ValueError, KeyError, TypeError, IndexError, UnicodeDecodeError, struct.error) as exc:
        raise CheckpointError(f"snapshot does not decode: {exc}") from None
    return fold


def load(journal: Path, event: dict[str, Any]) -> Fold | None:
    """The fold a ``checkpoint`` event names, verified; None (with a warning) if unusable."""
    try:
        covers = int(event["covers"])
        sha = str(event["sha256"])
        name = str(event["file"])
        if name != snapshot_name(covers, sha) or not 0 < covers < int(event["seq"]):
            raise CheckpointError("the event does not describe a snapshot it could have written")
        path = checkpoint_dir(journal) / name
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise CheckpointError("sha256 mismatch")
        fold = decode(data)
        if fold.last_seq != covers:
            raise CheckpointError(f"snapshot covers seq {fold.last_seq}, the event says {covers}")
        return fold
    except FileNotFoundError:
        _logger.warning(
            "moneta.v5 checkpoint at seq %s: snapshot %s is missing; replaying further back",
            event.get("seq"),
            event.get("file"),
        )
    except (CheckpointError, OSError, KeyError, TypeError, ValueError) as exc:
        _logger.warning(
            "moneta.v5 checkpoint at seq %s unusable (%s); replaying further back",
            event.get("seq"),
            exc,
        )
    return None


def remove_all(journal: Path, *, keep: frozenset[str] = frozenset()) -> int:
    """Delete snapshot files beside ``journal`` except ``keep``. Returns how many."""
    directory = checkpoint_dir(journal)
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.iterdir():
        if path.name in keep:
            continue
        if _NAME.match(path.name):
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                pass
    return removed
