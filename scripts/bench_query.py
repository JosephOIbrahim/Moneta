"""Query-path latency and memory benchmark for the Moneta hot tier.

Measures the agent-facing ``query`` op end to end (decay at eval point 1,
vector scan, rerank) plus the resident memory held by the embeddings.
This is D1's gate measurement: the 50 ms p95 query gate (MONETA.md Phase 2
plan; v6 §10).

Usage::

    PYTHONPATH=src python scripts/bench_query.py --n 1000 10000 --dim 384
"""
from __future__ import annotations

import argparse
import gc
import json
import random
import statistics
import sys
import time

from moneta import Moneta, MonetaConfig


def _rss_mb() -> float:
    """Process resident set size in MB (sees native allocations too)."""
    try:
        import psutil  # type: ignore

        return psutil.Process().memory_info().rss / 2**20
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.WorkingSetSize / 2**20
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _vec(rng: random.Random, dim: int) -> list[float]:
    return [rng.gauss(0.0, 1.0) for _ in range(dim)]


def bench(
    n: int,
    dim: int,
    queries: int,
    limit: int,
    seed: int,
    spread: bool = False,
    native_decay: bool = True,
) -> dict:
    rng = random.Random(seed)
    probes = [_vec(rng, dim) for _ in range(queries)]
    with Moneta(MonetaConfig.ephemeral()) as m:
        m.ecs.native_decay = m.ecs.native_decay and native_decay
        gc.collect()
        rss0 = _rss_mb()
        # Vectors arrive from the host and are dropped after deposit, so the
        # RSS delta is what Moneta itself keeps alive (floats included).
        vecs = [_vec(rng, dim) for _ in range(n)]
        for i, v in enumerate(vecs):
            m.deposit(f"memory {i}", v)
        del vecs, v
        gc.collect()
        rss1 = _rss_mb()
        if spread:
            # Aged store: utilities spread over [0.01, 1] (log-uniform), so
            # high-cosine records are often stale and the rerank must dig.
            urng = random.Random(seed + 1)
            u = m.ecs._utility
            for i in range(len(u)):
                u[i] = 10 ** urng.uniform(-2.0, 0.0)
        m.query(probes[0], limit)  # warm
        lat = []
        for q in probes:
            t0 = time.perf_counter()
            m.query(q, limit)
            lat.append((time.perf_counter() - t0) * 1000.0)
        backend = getattr(m.vector_index, "backend", "python")
    lat.sort()
    return {
        "n": n,
        "dim": dim,
        "backend": backend,
        "utilities": "spread" if spread else "fresh",
        "decay": "native" if m.ecs.native_decay else "python",
        "queries": queries,
        "p50_ms": round(statistics.median(lat), 3),
        "p95_ms": round(lat[int(0.95 * (len(lat) - 1))], 3),
        "rss_delta_mb": round(rss1 - rss0, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[1000, 10000])
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--queries", type=int, default=50)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--spread", action="store_true", help="log-uniform utilities in [0.01, 1]")
    ap.add_argument("--python-decay", action="store_true", help="keep the decay loop in Python")
    args = ap.parse_args()
    for n in args.n:
        r = bench(n, args.dim, args.queries, args.limit, args.seed, args.spread, not args.python_decay)
        print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
