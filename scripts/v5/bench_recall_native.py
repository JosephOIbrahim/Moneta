"""v5 recall latency and RSS, oracle vs native seams (dot + decay), on one journal.

Builds one v5 journal (n records x dim), then reopens it with
MONETA_NATIVE=0 and =1 in turn and times ``recall(q, 10)``. Reports p50 and
p95 over N queries, plus the RSS growth of opening (fold + index rebuild).

    PYTHONPATH=src python scripts/v5/bench_recall_native.py --n 10000 --queries 200
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench_query import _rss_mb  # noqa: E402

from moneta.v5 import Config, Substrate  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--modes", default="0,1", help="MONETA_NATIVE values to run; one per process for honest RSS")
    ap.add_argument("--journal", help="reuse an existing journal instead of building one")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    build_s = 0.0
    if args.journal:
        path = Path(args.journal)
    else:
        path = Path(tempfile.mkdtemp()) / "bench.v5.journal"
        t0 = time.perf_counter()
        with Substrate(Config(path=str(path), half_life_seconds=21600.0)) as m:
            for i in range(args.n):
                m.deposit(f"memory {i}", [rng.gauss(0, 1) for _ in range(args.dim)])
        build_s = time.perf_counter() - t0
    prng = random.Random(args.seed + 1)
    probes = [[prng.gauss(0, 1) for _ in range(args.dim)] for _ in range(args.queries)]
    for flag in args.modes.split(","):
        os.environ["MONETA_NATIVE"] = flag
        gc.collect()
        rss0 = _rss_mb()
        t0 = time.perf_counter()
        with Substrate(Config(path=str(path), half_life_seconds=21600.0)) as m:
            open_s = time.perf_counter() - t0
            gc.collect()
            rss1 = _rss_mb()
            m.recall(probes[0], 10)
            lat = []
            for q in probes:
                t1 = time.perf_counter()
                m.recall(q, 10)
                lat.append((time.perf_counter() - t1) * 1000.0)
            native = m._index.native
            decay = getattr(m, "native_decay", False)  # absent before Round 4 E2 condition 4
        lat.sort()
        print(json.dumps({
            "n": args.n, "dim": args.dim, "queries": args.queries,
            "python": sys.version.split()[0],
            "index": "native" if native else "python",
            "decay": "native" if decay else "python",
            "p50_ms": round(statistics.median(lat), 3),
            "p95_ms": round(lat[int(0.95 * (len(lat) - 1))], 3),
            "open_s": round(open_s, 3),
            "open_rss_delta_mb": round(rss1 - rss0, 2),
            "build_s": round(build_s, 2),
            "journal": str(path),
        }), flush=True)


if __name__ == "__main__":
    main()
