"""Reader stall during a v5 sleep pass and a v1-format export (Round 4 E3 conditions 1-2).

Two scenarios, each with a reader thread hammering ``recall`` while the
writer works:

``--mode sleep``  One sleep pass that stages ``--staged`` records and projects
                  them through the real ``UsdTarget`` (pxr required: run under
                  hython) in 500-prim batches (``MAX_BATCH_SIZE``).
``--mode export`` ``export_v1_snapshot`` of ``--n`` x ``--dim`` records (the
                  SYNAPSE path after every sleep pass), ``--reps`` times.

The writer thread's own holds of the substrate writer lock are timed
directly (``HoldTimer``): ``writer_lock_hold_max_ms`` is the lock-scope
stall the Round 4 conditions are about. Three probes run while the writer
works, and the same probes run for a baseline window with the writer idle:

- ``recall``: a thread calling ``recall(q, 10)`` back to back. Its latency is
  what an agent sees. ``stall_excess_p95_ms`` = p95 during - p95 baseline.
- ``lock``: a thread that only acquires and releases the substrate's writer
  lock. Its wait is the lock-scope stall alone.
- ``gil``: a thread that only reads ``perf_counter`` in a loop. Its largest
  gap is how long the interpreter itself (GIL, not the substrate lock) kept
  a Python thread from running. A recall stall that the lock probe does not
  show but this one does is the interpreter, not the lock scope.

    PYTHONPATH=src hython3.11 scripts/v5/bench_v5_lockscope.py --mode sleep --label after
    PYTHONPATH=src hython3.11 scripts/v5/bench_v5_lockscope.py --mode sleep --live 0  # no prunes
    PYTHONPATH=src python scripts/v5/bench_v5_lockscope.py --mode export --label after
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
import threading
import time
from pathlib import Path

from moneta.consolidation import MAX_BATCH_SIZE
from moneta.v5 import Config, Substrate
from moneta.v5.compat import TargetProjector, export_v1_snapshot
from moneta.v5.substrate import ManualClock

H = 6 * 3600.0
T0 = 1_000_000.0


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))] * 1000.0, 3)


class Probes:
    """Recall, lock and GIL probes; ``window()`` collects one measurement window."""

    def __init__(self, m: Substrate, query: list[float], t_eval: float) -> None:
        self.m = m
        self.query = query
        self.t_eval = t_eval
        self._stop = threading.Event()
        self._rec: list[float] = []
        self._lock_w: list[float] = []
        self._gil_gap = 0.0
        self._threads: list[threading.Thread] = []

    def _recall(self) -> None:
        while not self._stop.is_set():
            a = time.perf_counter()
            self.m.recall(self.query, 10, t=self.t_eval)
            self._rec.append(time.perf_counter() - a)

    def _lock(self) -> None:
        lock = self.m._lock
        while not self._stop.is_set():
            a = time.perf_counter()
            with lock:
                pass
            self._lock_w.append(time.perf_counter() - a)
            time.sleep(0.0005)

    def _gil(self) -> None:
        # Overshoot of a 1 ms sleep: the time this thread waited to get the
        # interpreter back (plus the OS timer's own slack, seen in baseline).
        while not self._stop.is_set():
            a = time.perf_counter()
            time.sleep(0.001)
            gap = time.perf_counter() - a - 0.001
            if gap > self._gil_gap:
                self._gil_gap = gap

    def reset(self) -> None:
        self._rec, self._lock_w, self._gil_gap = [], [], 0.0

    def start(self) -> None:
        self._stop.clear()
        self._threads = [
            threading.Thread(target=f, daemon=True) for f in (self._recall, self._lock, self._gil)
        ]
        for t in self._threads:
            t.start()

    def halt(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join()

    def stop(self) -> dict:
        self.halt()
        return self.collect()

    def collect(self) -> dict:
        return {
            "recalls": len(self._rec),
            "recall_p50_ms": _pct(self._rec, 0.50),
            "recall_p95_ms": _pct(self._rec, 0.95),
            "recall_p99_ms": _pct(self._rec, 0.99),
            "recall_max_ms": _pct(self._rec, 1.0),
            "lock_wait_p95_ms": _pct(self._lock_w, 0.95),
            "lock_wait_max_ms": _pct(self._lock_w, 1.0),
            "gil_max_overshoot_ms": round(self._gil_gap * 1000.0, 3),
        }


class HoldTimer:
    """Stands in for the substrate's RLock and times the writer thread's holds.

    Only outermost holds taken by ``writer`` while ``enabled`` are recorded:
    that is exactly how long the pass or export kept every reader out.
    """

    def __init__(self, lock: threading.RLock, writer: threading.Thread) -> None:
        self._inner = lock
        self._writer = writer
        self._depth = 0
        self._since = 0.0
        self.enabled = False
        self.holds: list[float] = []

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        ok = self._inner.acquire(blocking, timeout)
        if ok and threading.current_thread() is self._writer:
            if self._depth == 0:
                self._since = time.perf_counter()
            self._depth += 1
        return ok

    def release(self) -> None:
        if threading.current_thread() is self._writer:
            self._depth -= 1
            if self._depth == 0 and self.enabled:
                self.holds.append(time.perf_counter() - self._since)
        self._inner.release()

    __enter__ = acquire

    def __exit__(self, *exc: object) -> None:
        self.release()

    def _is_owned(self) -> bool:
        return self._inner._is_owned()

    def summary(self) -> dict:
        return {
            "writer_lock_holds": len(self.holds),
            "writer_lock_hold_p95_ms": _pct(self.holds, 0.95),
            "writer_lock_hold_max_ms": _pct(self.holds, 1.0),
        }


def _vec(rng: random.Random, dim: int) -> list[float]:
    return [rng.gauss(0, 1) for _ in range(dim)]


def _baseline(p: Probes, seconds: float) -> dict:
    p.reset()
    p.start()
    time.sleep(seconds)
    return p.stop()


def bench_sleep(args: argparse.Namespace, work: Path) -> dict:
    from moneta.usd_target import UsdTarget  # pxr: hython

    rng = random.Random(args.seed)
    clock = ManualClock(T0)
    usd_dir = work / "usd"
    projector = TargetProjector(lambda: UsdTarget(log_path=usd_dir), "usd")
    m = Substrate(
        Config(
            path=work / "s.v5.journal",
            fsync=False,
            half_life_seconds=H,
            clock=clock,
            projector=projector,
        )
    )
    timer = HoldTimer(m._lock, threading.current_thread())
    m._lock = timer
    p: Probes | None = None
    base: dict = {}
    pass_s: list[float] = []
    for k in range(args.passes):
        # Round k: deposit at tk, attend the to-be-staged ones 3x (attended >= 3
        # means staged, never pruned, once u < 0.3), pass at tk + 2H (u = 0.25).
        # The previous round's unstaged records are pruned in the same pass.
        tk = T0 + k * 10 * H
        clock.t = tk
        staged = [m.deposit(f"s{k}-{i}", _vec(rng, args.dim), t=tk) for i in range(args.staged)]
        for i in range(args.live):
            m.deposit(f"l{k}-{i}", _vec(rng, args.dim), t=tk)
        for _ in range(3):
            for start in range(0, len(staged), 1000):
                m.signal_attention({e: 1.0 for e in staged[start : start + 1000]}, t=tk)
        t_pass = tk + 2 * H
        clock.t = t_pass
        if p is None:
            p = Probes(m, _vec(rng, args.dim), t_pass)
            m.recall(p.query, 10, t=t_pass)  # warm
            base = _baseline(p, args.baseline_s)
            p.reset()
        p.t_eval = t_pass
        p.start()
        timer.enabled = True
        a = time.perf_counter()
        r = m.run_sleep_pass(t=t_pass)
        pass_s.append(time.perf_counter() - a)
        timer.enabled = False
        p.halt()
        if r.projection_error or len(r.consolidated_ids) != args.staged:
            raise SystemExit(f"pass did not project every staged record: {r.projection_error}")
    assert p is not None
    during = p.collect()  # every pass window, accumulated
    m.close()
    return {
        "staged": args.staged,
        "live_unstaged": args.live,
        "batch_size": MAX_BATCH_SIZE,
        "batches_per_pass": -(-args.staged // MAX_BATCH_SIZE),
        "passes": args.passes,
        "pass_s": [round(x, 3) for x in pass_s],
        "baseline": base,
        "during": during,
        **timer.summary(),
    }


def bench_export(args: argparse.Namespace, work: Path) -> dict:
    rng = random.Random(args.seed)
    m = Substrate(Config(path=work / "e.v5.journal", fsync=False, half_life_seconds=H))
    for i in range(args.n):
        m.deposit(f"memory {i}", _vec(rng, args.dim), t=T0)
    timer = HoldTimer(m._lock, threading.current_thread())
    m._lock = timer
    p = Probes(m, _vec(rng, args.dim), T0)
    m.recall(p.query, 10, t=T0)
    base = _baseline(p, args.baseline_s)
    snap = work / "snapshot.json"
    export_s = []
    p.start()
    timer.enabled = True
    for _ in range(args.reps):
        a = time.perf_counter()
        export_v1_snapshot(m, snap)
        export_s.append(time.perf_counter() - a)
        time.sleep(0.05)
    timer.enabled = False
    during = p.stop()
    m.close()
    return {
        "n": args.n,
        "reps": args.reps,
        "export_s": [round(x, 3) for x in export_s],
        "snapshot_mb": round(snap.stat().st_size / 1e6, 1),
        "baseline": base,
        "during": during,
        **timer.summary(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("sleep", "export"), required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--dim", type=int, default=768)
    ap.add_argument("--staged", type=int, default=2500)
    ap.add_argument("--live", type=int, default=1000)
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--baseline-s", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="results/bench_v5_lockscope.jsonl")
    ap.add_argument("--target-ms", type=float, default=30.0)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="moneta_lockscope_"))
    try:
        body = bench_sleep(args, work) if args.mode == "sleep" else bench_export(args, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    from moneta.v5 import index as _index

    base, during = body["baseline"], body["during"]
    excess = None
    if during["recall_p95_ms"] is not None and base["recall_p95_ms"] is not None:
        excess = round(during["recall_p95_ms"] - base["recall_p95_ms"], 3)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        commit = ""
    row = {
        "bench": f"v5_lockscope_{args.mode}",
        "label": args.label,
        "commit": commit,
        "python": platform.python_version(),
        "executable": Path(sys.executable).name,
        "moneta_native_env": os.environ.get("MONETA_NATIVE", ""),
        "native_index": _index.native_enabled(),
        "dim": args.dim,
        **body,
        "stall_recall_p95_ms": during["recall_p95_ms"],
        "stall_excess_p95_ms": excess,
        "stall_writer_lock_hold_max_ms": body["writer_lock_hold_max_ms"],
        "target_ms": args.target_ms,
        "within_target_recall_p95": during["recall_p95_ms"] is not None
        and during["recall_p95_ms"] <= args.target_ms,
        "within_target_writer_lock_hold_max": body["writer_lock_hold_max_ms"] is not None
        and body["writer_lock_hold_max_ms"] <= args.target_ms,
    }
    line = json.dumps(row)
    print(line)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as fp:
            fp.write(line + "\n")


if __name__ == "__main__":
    main()
