"""The v5 native decay seam against ``Record.utility_at`` (Round 4 E2 condition 4).

``utilities_at`` sends recall's and the sleep pass's utility columns through
``moneta_native.decay_batch`` when the seam is on. It must give the exact
doubles of the per-record oracle, so every RecallItem score and every
retention verdict is bit-for-bit the same with MONETA_NATIVE=1 and =0.
Marked ``native``: skips visibly when ``moneta_native`` is not loaded.
"""

from __future__ import annotations

import random
import shutil
import struct

import pytest

from moneta.v5 import Config, Substrate
from moneta.v5.model import RECALLABLE, utilities_at

pytestmark = pytest.mark.native

DIM = 16
T0 = 1_000_000.0


def _bits(x: float) -> bytes:
    return struct.pack("<d", x)


def _journal(path, rng):
    """Records with spread anchors, attention, protected floors and zero vectors."""
    with Substrate(Config(path=str(path), half_life_seconds=3600.0, protected_quota=50)) as m:
        ids = []
        for i in range(600):
            v = [rng.gauss(0, 1) for _ in range(DIM)] if i % 11 else [0.0] * DIM
            floor = rng.choice([0.05, 0.3, 0.9]) if i % 17 == 0 else 0.0
            ids.append(m.deposit(f"d{i}", v, floor, t=T0 + rng.uniform(0, 20_000)))
        for _ in range(60):
            picks = rng.sample(ids, 5)
            m.signal_attention({e: rng.random() for e in picks}, t=T0 + rng.uniform(0, 40_000))
    return ids


def _open(path, monkeypatch, flag):
    monkeypatch.setenv("MONETA_NATIVE", flag)
    m = Substrate(Config(path=str(path), half_life_seconds=3600.0, protected_quota=50))
    assert m.native_decay is (flag == "1"), "the parity test would be vacuous"
    return m


def test_utilities_column_bit_identical(tmp_path, monkeypatch):
    rng = random.Random(1)
    path = tmp_path / "u.v5.journal"
    _journal(path, rng)
    with _open(path, monkeypatch, "1") as m:
        recs = [r for r in m._fold.live.values() if r.status in RECALLABLE]
        # Earlier than some anchors (negative-dt clamp), inside, and far after (floor branch).
        for t in (T0 - 5.0, T0 + 10_000.0, T0 + 30_000.0, T0 + 1e6, T0 + 1e9):
            native = utilities_at(recs, m.lam, t, True)
            oracle = [r.utility_at(m.lam, t) for r in recs]
            assert [_bits(u) for u in native] == [_bits(u) for u in oracle]
        assert utilities_at([], m.lam, T0, True) == []
        with pytest.raises(TypeError):  # unset λ keeps the oracle's error
            utilities_at(recs, None, T0, True)


def test_recall_items_bit_identical_native_on_off(tmp_path, monkeypatch):
    rng = random.Random(2)
    path = tmp_path / "r.v5.journal"
    _journal(path, rng)
    queries = [[rng.gauss(0, 1) for _ in range(DIM)] for _ in range(6)]
    times = (T0 + 1_000.0, T0 + 25_000.0, T0 + 50_000.0, T0 + 5e5)
    results = {}
    for flag in ("1", "0"):
        with _open(path, monkeypatch, flag) as m:
            results[flag] = [
                [
                    (
                        i.memory.entity_id,
                        i.seq,
                        _bits(i.score),
                        _bits(i.cosine),
                        _bits(i.memory.utility),
                    )
                    for i in m.recall(q, 600, t=t).items
                ]
                for q in queries
                for t in times
            ]
    assert results["1"] == results["0"]
    assert sum(len(r) for r in results["1"]) > 1000


def test_sleep_pass_verdicts_identical_native_on_off(tmp_path, monkeypatch):
    rng = random.Random(3)
    src = tmp_path / "s.v5.journal"
    _journal(src, rng)
    outcomes = {}
    for flag in ("1", "0"):
        path = tmp_path / f"s{flag}.v5.journal"
        shutil.copyfile(src, path)
        with _open(path, monkeypatch, flag) as m:
            res = m.run_sleep_pass(t=T0 + 60_000.0)
            after = m.recall([1.0] + [0.0] * (DIM - 1), 600, t=T0 + 60_001.0)
            outcomes[flag] = (
                res.pruned_ids,
                res.staged_ids,
                [(i.memory.entity_id, _bits(i.score)) for i in after.items],
            )
    assert outcomes["1"] == outcomes["0"]
    assert outcomes["1"][0] or outcomes["1"][1], "the pass should prune or stage something"
