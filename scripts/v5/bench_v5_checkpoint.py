"""Reopen time with and without a journal checkpoint (Round 4 E3 condition 3).

Builds a journal of ``--events`` events (``--records`` deposits at
``--dim``, the rest single-id attention events: the SYNAPSE shape, where
attention dominates the journal), then times ``Substrate(Config(...))``
(the whole open: journal read and validation, fold, index rebuild):

- ``checkpoint``: after ``Substrate.checkpoint()`` plus a ``--tail``-event
  tail written after it;
- ``full``: the same journal with its snapshots deleted, a replay from genesis.

Also times taking the checkpoint and its writer-lock hold (the state copy).
Generation runs with fsync off (1.4 ms per append otherwise); open does not
depend on it.

    PYTHONPATH=src python scripts/v5/bench_v5_checkpoint.py --events 100000 1000000
    PYTHONPATH=src python scripts/v5/bench_v5_checkpoint.py --events 100000 --records 100000 --dim 64
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from moneta.v5 import Config, Substrate
from moneta.v5 import checkpoint as ckpt
from moneta.v5.index import native_enabled
from moneta.v5.substrate import ManualClock

H = 6 * 3600.0
T0 = 1_000_000.0


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _cfg(path: Path) -> Config:
    return Config(path=path, half_life_seconds=H, fsync=False, clock=ManualClock(T0 + 1e7))


def _open_s(path: Path, reps: int) -> tuple[list[float], int, int | None]:
    times = []
    replayed = 0
    covers = None
    for _ in range(reps):
        started = time.perf_counter()
        m = Substrate(_cfg(path))
        times.append(time.perf_counter() - started)
        replayed, covers = m.replayed_at_open, m.opened_from_checkpoint
        m.close()
    return times, replayed, covers


def run(events: int, records: int, dim: int, tail: int, reps: int, label: str) -> dict:
    rng = random.Random(7)
    work = Path(tempfile.mkdtemp(prefix="moneta-ckpt-"))
    path = work / "m.v5.journal"
    try:
        started = time.perf_counter()
        with Substrate(_cfg(path)) as m:
            ids = [
                m.deposit(f"memory {i}", [rng.uniform(-1, 1) for _ in range(dim)], t=T0 + i)
                for i in range(records)
            ]
            attends = max(0, events - 1 - records - 1 - tail)
            for i in range(attends):
                m.signal_attention({ids[rng.randrange(records)]: 0.01}, t=T0 + records + i)
            pre_ckpt_seq = m.seq
        build_s = time.perf_counter() - started

        with Substrate(_cfg(path)) as m:
            lock_holds: list[float] = []
            real_capture = ckpt.capture

            def timed_capture(fold):
                t0 = time.perf_counter()
                out = real_capture(fold)
                lock_holds.append(time.perf_counter() - t0)
                return out

            ckpt.capture = timed_capture
            try:
                t0 = time.perf_counter()
                m.checkpoint()
                checkpoint_s = time.perf_counter() - t0
            finally:
                ckpt.capture = real_capture
            for i in range(tail):
                m.signal_attention({ids[rng.randrange(records)]: 0.01}, t=T0 + events + i)
            seq = m.seq
        snap = next(ckpt.checkpoint_dir(path).glob("*.fold"))
        snapshot_mb = round(snap.stat().st_size / 1e6, 2)
        ck_s, ck_replayed, covers = _open_s(path, reps)
        # The same journal with its snapshots deleted: a replay from genesis.
        shutil.rmtree(ckpt.checkpoint_dir(path))
        full_s, full_replayed, _ = _open_s(path, reps)
        return {
            "bench": "v5_checkpoint_reopen",
            "label": label,
            "commit": _commit(),
            "python": platform.python_version(),
            "executable": Path(sys.executable).name,
            "moneta_native_env": os.environ.get("MONETA_NATIVE", "1"),
            "native_index": native_enabled(),
            "events": seq,
            "events_before_checkpoint": pre_ckpt_seq,
            "records": records,
            "dim": dim,
            "tail_events": tail,
            "journal_mb": round(path.stat().st_size / 1e6, 1),
            "snapshot_mb": snapshot_mb,
            "build_s": round(build_s, 1),
            "open_full_s": [round(x, 3) for x in full_s],
            "open_full_replayed": full_replayed,
            "checkpoint_s": round(checkpoint_s, 3),
            "checkpoint_lock_hold_ms": round(lock_holds[0] * 1000, 2),
            "open_checkpoint_s": [round(x, 3) for x in ck_s],
            "open_checkpoint_replayed": ck_replayed,
            "opened_from_checkpoint_covers": covers,
            "open_full_median_s": round(sorted(full_s)[len(full_s) // 2], 3),
            "open_checkpoint_median_s": round(sorted(ck_s)[len(ck_s) // 2], 3),
            "target_s": 1.0,
            "within_target": sorted(ck_s)[len(ck_s) // 2] < 1.0,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, nargs="+", default=[100_000])
    ap.add_argument("--records", type=int, default=1000)
    ap.add_argument("--dim", type=int, default=768)
    ap.add_argument("--tail", type=int, default=1000)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", default="results/bench_v5_checkpoint.jsonl")
    args = ap.parse_args()
    for n in args.events:
        row = run(n, args.records, args.dim, args.tail, args.reps, args.label)
        print(json.dumps(row))
        with open(args.out, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
