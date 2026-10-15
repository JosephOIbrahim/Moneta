"""Conformance: the native scan seam against the pure-Python oracle.

D1 admits Rust only behind a pure seam with an exact oracle. The oracle is
``VectorIndex(backend="python")``. Every check here compares with ``==``:
cosines must be bit-identical and orderings identical, ties included.

The native-vs-oracle tests skip when ``moneta_native`` is not installed;
the oracle self-checks always run.
"""
from __future__ import annotations

import json
import math
import random
from uuid import UUID, uuid4

import pytest

from moneta.types import EntityState
from moneta.vector_index import VectorIndex, native_available

needs_native = pytest.mark.skipif(not native_available(), reason="moneta_native not installed")

S = EntityState.VOLATILE


def _vec(rng: random.Random, dim: int) -> list[float]:
    return [rng.gauss(0.0, 1.0) for _ in range(dim)]


def _pair() -> tuple[VectorIndex, VectorIndex]:
    return VectorIndex(backend="python"), VectorIndex(backend="native")


def _apply(indexes, op, *args):
    for idx in indexes:
        getattr(idx, op)(*args)


def _assert_same(py: VectorIndex, nat: VectorIndex, q, k=None):
    k = len(py) if k is None else k
    assert nat.query(q, k) == py.query(q, k)


# ---------------------------------------------------------------------------
# oracle self-checks (always run)
# ---------------------------------------------------------------------------


def test_oracle_backend_is_python_when_forced():
    assert VectorIndex(backend="python").backend == "python"


def test_oracle_ties_keep_insertion_order():
    idx = VectorIndex(backend="python")
    ids = [uuid4() for _ in range(5)]
    for i in ids:
        idx.upsert(i, [1.0, 2.0, 3.0], S)
    assert [e for e, _ in idx.query([1.0, 2.0, 3.0], 5)] == ids


def test_unknown_backend_rejected():
    with pytest.raises(ValueError):
        VectorIndex(backend="gpu")


# ---------------------------------------------------------------------------
# native vs oracle
# ---------------------------------------------------------------------------


@needs_native
@pytest.mark.parametrize("seed", range(5))
def test_random_cosines_bit_identical(seed):
    rng = random.Random(seed)
    py, nat = _pair()
    for _ in range(300):
        _apply((py, nat), "upsert", uuid4(), _vec(rng, 64), S)
    for _ in range(10):
        _assert_same(py, nat, _vec(rng, 64))


@needs_native
@pytest.mark.parametrize("k", [0, 1, 7, 50, 299, 300, 1000])
def test_topk_prefix_matches(k):
    rng = random.Random(11)
    py, nat = _pair()
    for _ in range(300):
        _apply((py, nat), "upsert", uuid4(), _vec(rng, 16), S)
    _assert_same(py, nat, _vec(rng, 16), k)


@needs_native
def test_exact_ties_from_duplicate_vectors():
    rng = random.Random(3)
    py, nat = _pair()
    base = [_vec(rng, 8) for _ in range(4)]
    for i in range(80):
        _apply((py, nat), "upsert", uuid4(), list(base[i % 4]), S)
    for b in base:
        _assert_same(py, nat, b)
        _assert_same(py, nat, b, 13)


@needs_native
def test_upsert_existing_keeps_position_and_replaces_vector():
    rng = random.Random(4)
    py, nat = _pair()
    ids = [uuid4() for _ in range(20)]
    for i in ids:
        _apply((py, nat), "upsert", i, [1.0, 0.0, 0.0], S)
    _apply((py, nat), "upsert", ids[3], [1.0, 0.0, 0.0], EntityState.STAGED_FOR_SYNC)
    _apply((py, nat), "upsert", ids[5], _vec(rng, 3), S)
    _assert_same(py, nat, [1.0, 0.0, 0.0])
    assert [e for e, _ in nat.query([1.0, 0.0, 0.0], 20)][:4] == ids[:3] + [ids[3]]


@needs_native
def test_delete_then_reinsert_moves_to_end():
    py, nat = _pair()
    ids = [uuid4() for _ in range(10)]
    for i in ids:
        _apply((py, nat), "upsert", i, [0.5, 0.5], S)
    _apply((py, nat), "delete", ids[2])
    _apply((py, nat), "delete", uuid4())  # idempotent on absent ids
    _apply((py, nat), "upsert", ids[2], [0.5, 0.5], S)
    _assert_same(py, nat, [0.5, 0.5])
    assert [e for e, _ in nat.query([0.5, 0.5], 10)][-1] == ids[2]
    assert len(nat) == len(py) == 10


@needs_native
def test_compaction_preserves_order_and_values():
    rng = random.Random(5)
    py, nat = _pair()
    ids = [uuid4() for _ in range(3000)]
    for i in ids:
        _apply((py, nat), "upsert", i, _vec(rng, 4), S)
    for i in ids[::3] + ids[1::3]:  # kill two thirds, forcing compaction
        _apply((py, nat), "delete", i)
    for i in ids[:50]:
        _apply((py, nat), "upsert", i, _vec(rng, 4), S)
    assert nat.native_slots() < 3000 + 50
    for _ in range(5):
        _assert_same(py, nat, _vec(rng, 4))


@needs_native
def test_zero_norm_rows_and_zero_query():
    py, nat = _pair()
    _apply((py, nat), "upsert", uuid4(), [0.0, 0.0, 0.0], S)
    _apply((py, nat), "upsert", uuid4(), [1.0, 1.0, 0.0], S)
    _assert_same(py, nat, [1.0, 0.0, 0.0])
    assert nat.query([0.0, 0.0, 0.0], 5) == py.query([0.0, 0.0, 0.0], 5) == []


@needs_native
def test_query_dim_mismatch_returns_empty_like_oracle():
    py, nat = _pair()
    _apply((py, nat), "upsert", uuid4(), [1.0, 2.0], S)
    assert nat.query([1.0, 2.0, 3.0], 5) == py.query([1.0, 2.0, 3.0], 5)


@needs_native
def test_upsert_dim_mismatch_raises_like_oracle():
    for idx in _pair():
        idx.upsert(uuid4(), [1.0, 2.0], S)
        with pytest.raises(ValueError):
            idx.upsert(uuid4(), [1.0, 2.0, 3.0], S)


@needs_native
def test_non_finite_demotes_to_oracle_and_stays_exact():
    rng = random.Random(6)
    py, nat = _pair()
    for _ in range(20):
        _apply((py, nat), "upsert", uuid4(), _vec(rng, 4), S)
    bad = uuid4()
    _apply((py, nat), "upsert", bad, [math.inf, 0.0, 1.0, 0.0], S)
    assert nat.backend == "python"
    q = _vec(rng, 4)
    assert repr(nat.query(q, 30)) == repr(py.query(q, 30))


@needs_native
def test_non_finite_query_matches_oracle():
    rng = random.Random(7)
    py, nat = _pair()
    for _ in range(20):
        _apply((py, nat), "upsert", uuid4(), _vec(rng, 4), S)
    q = [math.nan, 1.0, 0.0, 0.0]
    assert repr(nat.query(q, 30)) == repr(py.query(q, 30))


@needs_native
def test_state_tracking_matches():
    py, nat = _pair()
    a, b = uuid4(), uuid4()
    _apply((py, nat), "upsert", a, [1.0, 0.0], S)
    _apply((py, nat), "update_state", a, EntityState.CONSOLIDATED)
    _apply((py, nat), "update_state", b, EntityState.CONSOLIDATED)  # absent: no-op
    for idx in (py, nat):
        assert idx.get_state(a) == EntityState.CONSOLIDATED
        assert idx.get_state(b) is None
        assert idx.contains(a) and not idx.contains(b)


@needs_native
def test_snapshot_restore_round_trip_byte_identical_across_backends():
    rng = random.Random(8)
    py, nat = _pair()
    ids = [uuid4() for _ in range(40)]
    for i in ids:
        _apply((py, nat), "upsert", i, _vec(rng, 6), S)
    for i in ids[5:15]:
        _apply((py, nat), "delete", i)
    _apply((py, nat), "update_state", ids[0], EntityState.STAGED_FOR_SYNC)
    s_py = json.dumps(py.snapshot(), sort_keys=True)
    s_nat = json.dumps(nat.snapshot(), sort_keys=True)
    assert s_nat == s_py
    for target_backend in ("python", "native"):
        for src in (s_py,):
            idx = VectorIndex(backend=target_backend)
            idx.restore(json.loads(src))
            assert json.dumps(idx.snapshot(), sort_keys=True) == s_py
            q = _vec(rng, 6)
            assert idx.query(q, 40) == py.query(q, 40)


@needs_native
def test_restore_empty_snapshot():
    nat = VectorIndex(backend="native")
    nat.upsert(uuid4(), [1.0], S)
    nat.restore({"backend": "in_memory", "embedding_dim": None, "records": []})
    assert len(nat) == 0 and nat.query([1.0], 3) == []


@needs_native
def test_ids_are_uuids():
    nat = VectorIndex(backend="native")
    i = uuid4()
    nat.upsert(i, [1.0, 0.0], S)
    (eid, cos), = nat.query([1.0, 0.0], 1)
    assert isinstance(eid, UUID) and eid == i and cos == 1.0


@needs_native
@pytest.mark.parametrize("seed", range(3))
def test_overflowing_finite_components_match_oracle_without_panic(seed):
    # Finite components near 1e308 overflow a norm or dot to inf, giving NaN
    # cosines. The native store must hand those queries to the oracle rather
    # than sort NaN keys (which panicked before the fix).
    rng = random.Random(seed)
    py, nat = _pair()
    for i in range(5000):
        v = _vec(rng, 4)
        if i % 50 == 0:
            v = [rng.choice([1e308, -1e308]) for _ in range(4)]
        _apply((py, nat), "upsert", uuid4(), v, S)
    assert nat.backend == "native"
    for q in (_vec(rng, 4), [1e308, 1e308, 0.0, 0.0], [1e200, -1e200, 1e200, 1e200]):
        for k in (1, 10, 5000):
            assert repr(nat.query(q, k)) == repr(py.query(q, k))
        assert repr(list(nat.iter_query(q))) == repr(py.query(q, len(py)))


@needs_native
def test_overflow_through_the_public_query_op():
    from moneta import Moneta, MonetaConfig

    rng = random.Random(9)
    with Moneta(MonetaConfig.ephemeral()) as m:
        for i in range(300):
            v = _vec(rng, 4) if i % 7 else [1e308, -1e308, 1e308, 1e308]
            m.deposit(f"p{i}", v)
        # Runs under either backend (MONETA_NATIVE may force the oracle);
        # what matters is that the public op neither panics nor short-returns.
        got = m.query([1e308, 1e308, 1.0, 0.0], 10)
        assert len(got) == 10
