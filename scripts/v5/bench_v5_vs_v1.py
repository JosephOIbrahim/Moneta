"""Small, honest cost probe: v1 vs v5 on the same synthetic store.

Not the Blueprint-B benchmark. One machine, one run, medians of repeats.
It answers one question: where does v5 spend time relative to v1?

    python scripts/v5/bench_v5_vs_v1.py --n 10000 --dim 384
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
import time
from pathlib import Path


def vectors(n: int, dim: int, seed: int = 7):
    rng = random.Random(seed)
    return [[rng.gauss(0, 1) for _ in range(dim)] for _ in range(n)]


def timed(fn, repeats: int):
    samples = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    return statistics.median(samples)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--queries", type=int, default=20)
    args = ap.parse_args()

    import moneta
    from moneta.v5 import Config, Substrate

    vecs = vectors(args.n, args.dim)
    queries = vectors(args.queries, args.dim, seed=11)
    out = {"n": args.n, "dim": args.dim}
    tmp = Path(tempfile.mkdtemp())

    # -- v1: in-memory deposit, query, then snapshot as SYNAPSE does ----------
    cfg = moneta.MonetaConfig(
        storage_uri="bench-v1", snapshot_path=tmp / "v1.json", wal_path=tmp / "v1.wal"
    )
    v1 = moneta.Moneta(cfg)
    t = time.perf_counter()
    for i, v in enumerate(vecs):
        v1.deposit(f"memory {i}", v)
    out["v1_deposit_all_s"] = round(time.perf_counter() - t, 3)
    out["v1_query_ms_median"] = round(
        statistics.median(timed(lambda q=q: v1.query(q, 10), 1) for q in queries), 1
    )
    out["v1_snapshot_s"] = round(timed(lambda: v1.durability.snapshot_ecs(v1.ecs), 1) / 1000, 3)
    v1.close()
    t = time.perf_counter()
    moneta.Moneta(
        moneta.MonetaConfig(
            storage_uri="bench-v1b", snapshot_path=tmp / "v1.json", wal_path=tmp / "v1.wal"
        )
    ).close()
    out["v1_open_s"] = round(time.perf_counter() - t, 3)
    out["v1_bytes"] = (tmp / "v1.json").stat().st_size

    # -- v5: fsync'd journal deposit, pure query, replay on open ---------------
    for fsync in (False, True):
        path = tmp / f"v5_{int(fsync)}.journal"
        s = Substrate(Config(path=path, fsync=fsync))
        n = args.n if not fsync else min(args.n, 500)
        t = time.perf_counter()
        for i, v in enumerate(vecs[:n]):
            s.deposit(f"memory {i}", v)
        per = (time.perf_counter() - t) / n * 1000
        out[f"v5_deposit_ms_each_fsync_{fsync}"] = round(per, 3)
        if not fsync:
            out["v5_query_ms_median"] = round(
                statistics.median(timed(lambda q=q, s=s: s.query(q, 10), 1) for q in queries), 1
            )
            s.close()
            t = time.perf_counter()
            Substrate(Config(path=path)).close()
            out["v5_open_replay_s"] = round(time.perf_counter() - t, 3)
            out["v5_bytes"] = path.stat().st_size
        else:
            s.close()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
