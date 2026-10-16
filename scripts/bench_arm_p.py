"""D1 arm P: numpy-vectorized scan, measured without modifying src/.

Patches VectorIndex.query with a numpy scan over a cached matrix and runs
the same benchmark as bench_query.py. Also counts how often numpy's
cosines differ bit-for-bit from the sequential Python oracle, which is
the exactness argument for a native seam (BLAS reorders the summation).

Usage::

    PYTHONPATH=src python scripts/bench_arm_p.py --n 10000
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

import numpy as np

# Arm P patches the oracle backend's dict store; keep every native seam off
# so the measurement isolates the numpy scan.
os.environ["MONETA_NATIVE"] = "0"

sys.path.insert(0, str(Path(__file__).parent))
import bench_query  # noqa: E402

from moneta.vector_index import VectorIndex  # noqa: E402

_oracle_query = VectorIndex.query


def _numpy_query(self, vector, k):
    if not self._records or k <= 0:
        return []
    cache = getattr(self, "_np_cache", None)
    if cache is None or cache[0] != len(self._records):
        ids = list(self._records)
        mat = np.array([self._records[i][0] for i in ids], dtype=np.float64)
        norms = np.sqrt(np.einsum("ij,ij->i", mat, mat))
        cache = (len(ids), ids, mat, norms)
        self._np_cache = cache
    _, ids, mat, norms = cache
    q = np.asarray(vector, dtype=np.float64)
    qn = float(np.sqrt(q @ q))
    if qn == 0.0:
        return []
    cos = (mat @ q) / (norms * qn)
    order = np.argsort(-cos, kind="stable")[:k]
    return [(ids[i], float(cos[i])) for i in order if norms[i] != 0.0]


def exactness(n: int, dim: int, seed: int) -> dict:
    rng = random.Random(seed)
    idx = VectorIndex()
    from uuid import uuid4

    from moneta.types import EntityState

    for _ in range(n):
        idx.upsert(uuid4(), [rng.gauss(0, 1) for _ in range(dim)], EntityState.VOLATILE)
    q = [rng.gauss(0, 1) for _ in range(dim)]
    a = dict(_oracle_query(idx, q, n))
    b = dict(_numpy_query(idx, q, n))
    diff = sum(1 for k in a if a[k] != b[k])
    order_diff = [e for e, _ in _oracle_query(idx, q, n)] != [e for e, _ in _numpy_query(idx, q, n)]
    return {"n": n, "cosines_not_bit_equal": diff, "of": n, "order_differs": order_diff}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[1000, 10000])
    ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--spread", action="store_true")
    args = ap.parse_args()
    print(json.dumps({"arm_p_exactness": exactness(2000, args.dim, 3)}), flush=True)
    VectorIndex.query = _numpy_query
    for n in args.n:
        r = bench_query.bench(n, args.dim, args.queries, 10, 7, args.spread)
        r["backend"] = "arm_p_numpy"
        print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
