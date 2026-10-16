"""v5 recall latency with and without dead (tombstoned) records.

Round 4 E4 blocking condition 1: recall p95 with 100k dead records must be
within 10% of recall p95 with zero dead records, over the same live set.

Two in-memory stores share one live set (same seed, same vectors, same
timestamps). The dead arm also holds ``--dead`` records, deposited
interleaved with the live ones and then tombstoned in one operator call.
Each arm runs ``--queries`` recalls per repetition; the arms alternate for
``--reps`` repetitions and the reported p95 is the median over them, so
one noisy repetition cannot decide the gate.

    MONETA_NATIVE=0 PYTHONPATH=src python scripts/v5/bench_dead_records.py \
        --out results/bench_v5_dead_records.jsonl
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from moneta.v5 import Config, Substrate  # noqa: E402

T0 = 1_000_000.0


def _build(live: int, dead: int, dim: int, seed: int) -> Substrate:
    rng_live = random.Random(seed)
    rng_dead = random.Random(seed + 1000)
    m = Substrate(Config.ephemeral(half_life_seconds=21600.0, fsync=False))
    per = dead // live if live else 0
    extra = dead - per * live
    doomed = []
    for i in range(live):
        for _ in range(per + (1 if i < extra else 0)):
            doomed.append(m.deposit("dead", [rng_dead.gauss(0, 1) for _ in range(dim)], t=T0))
        m.deposit(f"memory {i}", [rng_live.gauss(0, 1) for _ in range(dim)], t=T0)
    if doomed:
        m.tombstone(doomed, t=T0)
    return m


def _p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[int(0.95 * (len(xs) - 1))]


def _run(m: Substrate, probes: list[list[float]]) -> list[float]:
    for q in probes[:20]:  # warm-up
        m.recall(q, 10, t=T0 + 60.0)
    lat = []
    for q in probes:
        t1 = time.perf_counter()
        m.recall(q, 10, t=T0 + 60.0)
        lat.append((time.perf_counter() - t1) * 1000.0)
    return lat


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", type=int, default=2_000)
    ap.add_argument("--dead", type=int, default=100_000)
    ap.add_argument("--dim", type=int, default=128)
    ap.add_argument("--queries", type=int, default=500)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", help="append the JSON line to this file")
    args = ap.parse_args()

    zero = _build(args.live, 0, args.dim, args.seed)
    dead = _build(args.live, args.dead, args.dim, args.seed)
    prng = random.Random(args.seed + 1)
    probes = [[prng.gauss(0, 1) for _ in range(args.dim)] for _ in range(args.queries)]
    # Same live set => same answers. A dead record must never change a result.
    for q in probes[:25]:
        a = [(i.memory.entity_id, i.score) for i in zero.recall(q, 10, t=T0 + 60.0).items]
        b = [(i.memory.payload, i.score) for i in dead.recall(q, 10, t=T0 + 60.0).items]
        pa = [(zero.explain(e, t=T0 + 60.0).payload, s) for e, s in a]
        assert pa == b, "dead records changed a recall result"

    p95_zero, p95_dead, p50_zero, p50_dead = [], [], [], []
    for _ in range(args.reps):
        for store, p95s, p50s in ((zero, p95_zero, p50_zero), (dead, p95_dead, p50_dead)):
            gc.collect()
            lat = _run(store, probes)
            p95s.append(_p95(lat))
            p50s.append(statistics.median(lat))
    stats = dead.stats()
    zp95 = statistics.median(p95_zero)
    dp95 = statistics.median(p95_dead)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        commit = ""
    row = {
        "bench": "v5_recall_dead_records",
        "label": args.label,
        "commit": commit,
        "python": sys.version.split()[0],
        "index": "native" if dead._index.native else "python",
        "moneta_native_env": os.environ.get("MONETA_NATIVE", "1"),
        "live": args.live,
        "dead": args.dead,
        "dim": args.dim,
        "queries": args.queries,
        "reps": args.reps,
        "dead_store_records": stats["records"],
        "p50_ms_zero_dead": round(statistics.median(p50_zero), 3),
        "p50_ms_dead": round(statistics.median(p50_dead), 3),
        "p95_ms_zero_dead": round(zp95, 3),
        "p95_ms_dead": round(dp95, 3),
        "p95_ratio": round(dp95 / zp95, 3),
        "gate_within_10pct": dp95 <= 1.10 * zp95,
    }
    line = json.dumps(row)
    print(line, flush=True)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    zero.close()
    dead.close()


if __name__ == "__main__":
    main()
