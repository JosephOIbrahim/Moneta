"""The v5 native dot seam against ``ExactIndex``'s own Python loop.

Bit-for-bit on whatever interpreter runs the suite: the Rust sum
reproduces CPython's ``sum()`` (sequential on <= 3.11, Neumaier on >= 3.12).
Marked ``native``: skips visibly when ``moneta_native`` is not loaded.
"""

from __future__ import annotations

import importlib
import random
import struct
import sys
from uuid import uuid4

import pytest

from moneta.v5 import Config, Substrate
from moneta.v5.index import ExactIndex
from moneta.v5.model import _unit

pytestmark = pytest.mark.native


@pytest.fixture
def native():
    """The wheel module, imported only inside a (native-marked) test."""
    return importlib.import_module("moneta_native")


def _bits(pairs):
    return [(eid, struct.pack("<d", c)) for eid, c in pairs]


def _pair(rng, n, dim):
    a, b = ExactIndex(native=True), ExactIndex(native=False)
    ids = []
    for _ in range(n):
        u = _unit(tuple(rng.gauss(0, 1) for _ in range(dim)))
        eid = uuid4()
        a.add(eid, u)
        b.add(eid, u)
        ids.append(eid)
    return a, b, ids


def test_sum_kernel_matches_builtin_sum(native):
    rng = random.Random(0)
    comp = sys.version_info >= (3, 12)
    for _ in range(3000):
        xs = [rng.choice([1e16, -1e16, 1.0, rng.gauss(0, 1), 1e-300, -0.0]) for _ in range(rng.randint(1, 50))]
        assert struct.pack("<d", native.py_sum_list(xs, comp)) == struct.pack("<d", sum(xs))


@pytest.mark.parametrize("dim", [3, 64, 384])
def test_cosines_bit_identical(dim):
    rng = random.Random(dim)
    a, b, ids = _pair(rng, 500, dim)
    for _ in range(5):
        q = [rng.gauss(0, 1) for _ in range(dim)]
        sub = rng.sample(ids, 300)
        assert _bits(a.cosines(q, sub)) == _bits(b.cosines(q, sub))


def test_remove_readd_and_compaction_keep_parity():
    rng = random.Random(5)
    a, b, ids = _pair(rng, 3000, 8)
    for eid in ids[:2500]:
        a.remove(eid)
        b.remove(eid)
    for eid in ids[:100]:
        u = _unit(tuple(rng.gauss(0, 1) for _ in range(8)))
        a.add(eid, u)
        b.add(eid, u)
    a.add(ids[2900], b._units[ids[2900]])  # re-add existing id (revector path)
    assert a._store.slots() < 3000
    live = list(b._units)
    q = [rng.gauss(0, 1) for _ in range(8)]
    assert _bits(a.cosines(q, live)) == _bits(b.cosines(q, live))


def test_errors_match_python_path():
    rng = random.Random(6)
    a, b, ids = _pair(rng, 10, 4)
    for idx in (a, b):
        with pytest.raises(KeyError):
            idx.cosines([1.0, 0.0, 0.0, 0.0], [uuid4()])
        with pytest.raises(ValueError):
            idx.cosines([0.0, 0.0, 0.0, 0.0], ids)
        with pytest.raises(ValueError):
            idx.cosines([1.0, 0.0], ids)


def test_substrate_recall_identical_with_and_without_native(tmp_path, monkeypatch):
    rng = random.Random(9)
    path = tmp_path / "p.v5.journal"
    with Substrate(Config(path=str(path), half_life_seconds=3600.0)) as m:
        for i in range(400):
            v = [rng.gauss(0, 1) for _ in range(16)] if i % 9 else [0.0] * 16
            m.deposit(f"p{i}", v)
        ids = [r.memory.entity_id for r in m.recall([1.0] + [0.0] * 15, 50).items]
        m.signal_attention({ids[0]: 0.7, ids[3]: 0.2})
    queries = [[rng.gauss(0, 1) for _ in range(16)] for _ in range(5)]
    results = {}
    for flag in ("1", "0"):
        monkeypatch.setenv("MONETA_NATIVE", flag)
        with Substrate(Config(path=str(path), half_life_seconds=3600.0)) as m:
            assert m._index.native is (flag == "1")
            results[flag] = [
                [(i.memory.entity_id, struct.pack("<d", i.score), struct.pack("<d", i.cosine)) for i in m.recall(q, 40, t=5e6).items]
                for q in queries
            ]
    assert results["1"] == results["0"]
