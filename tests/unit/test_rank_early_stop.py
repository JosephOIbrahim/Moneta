"""Exactness of the query fast path against the Phase 1 reference.

``ECS.rank_hits`` stops early on a utility bound and ``VectorIndex.iter_query``
yields hits lazily. Both must reproduce the Phase 1 query result exactly:
project every hit, stable-sort by ``max(cos, 0) * utility``, slice ``[:limit]``.
"""
from __future__ import annotations

import math
import random
from uuid import uuid4

import pytest

from moneta.ecs import ECS
from moneta.types import EntityState
from moneta.vector_index import VectorIndex, native_available

BACKENDS = ["python"] + (["native"] if native_available() else [])


def _reference(ecs: ECS, hits, limit):
    ranked = []
    for eid, cos in hits:
        m = ecs.get_memory(eid)
        if m is None:
            continue
        ranked.append((max(cos, 0.0) * m.utility, m))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return [m.entity_id for _, m in ranked[:limit]]


def _world(seed, backend, n=400, dim=12, dup_every=0, utilities=None):
    rng = random.Random(seed)
    ecs, idx = ECS(), VectorIndex(backend=backend)
    base = [rng.gauss(0, 1) for _ in range(dim)]
    for i in range(n):
        v = list(base) if dup_every and i % dup_every == 0 else [rng.gauss(0, 1) for _ in range(dim)]
        eid = uuid4()
        u = utilities(rng, i) if utilities else rng.uniform(0.0, 1.0)
        ecs.add(eid, f"p{i}", v, u, 0.0, EntityState.VOLATILE, 0.0)
        idx.upsert(eid, v, EntityState.VOLATILE)
    return rng, ecs, idx, base


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("limit", [-3, 0, 1, 5, 10, 399, 400, 1000])
def test_rank_hits_matches_reference(backend, limit):
    rng, ecs, idx, _ = _world(1, backend)
    for _ in range(5):
        q = [rng.gauss(0, 1) for _ in range(12)]
        full = idx.query(q, len(idx))
        got = [m.entity_id for m in ecs.rank_hits(idx.iter_query(q), limit)]
        assert got == _reference(ecs, full, limit)


@pytest.mark.parametrize("backend", BACKENDS)
def test_iter_query_equals_full_query(backend):
    rng, _, idx, _ = _world(2, backend, n=3000, dim=8)
    for _ in range(3):
        q = [rng.gauss(0, 1) for _ in range(8)]
        assert list(idx.iter_query(q)) == idx.query(q, len(idx))


@pytest.mark.parametrize("backend", BACKENDS)
def test_score_ties_and_duplicate_vectors(backend):
    # Equal utilities plus duplicate vectors produce many exact score ties.
    rng, ecs, idx, base = _world(3, backend, dup_every=3, utilities=lambda r, i: 0.5)
    for limit in (1, 4, 50):
        full = idx.query(base, len(idx))
        got = [m.entity_id for m in ecs.rank_hits(idx.iter_query(base), limit)]
        assert got == _reference(ecs, full, limit)


@pytest.mark.parametrize("backend", BACKENDS)
def test_stale_high_cosine_low_utility_forces_deep_scan(backend):
    # Top cosines carry tiny utility, so the true winners sit deep in the
    # cosine order and the early stop must not fire too soon.
    rng, ecs, idx, base = _world(
        4, backend, n=2000, dim=6, dup_every=0, utilities=lambda r, i: 1e-6 if i % 2 else 1.0
    )
    full = idx.query(base, len(idx))
    for limit in (3, 25):
        got = [m.entity_id for m in ecs.rank_hits(idx.iter_query(base), limit)]
        assert got == _reference(ecs, full, limit)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("bad", [math.nan, math.inf, -0.25])
def test_non_finite_or_negative_utility_disables_early_stop_exactly(backend, bad):
    rng, ecs, idx, _ = _world(5, backend, n=200)
    ecs._utility[17] = bad
    q = [rng.gauss(0, 1) for _ in range(12)]
    full = idx.query(q, len(idx))
    for limit in (1, 10):
        got = [m.entity_id for m in ecs.rank_hits(idx.iter_query(q), limit)]
        assert got == _reference(ecs, full, limit)


@pytest.mark.parametrize("backend", BACKENDS)
def test_hits_missing_from_ecs_are_skipped(backend):
    rng, ecs, idx, _ = _world(6, backend, n=100)
    for eid in list(ecs._ids)[:30]:
        ecs.remove(eid)
    q = [rng.gauss(0, 1) for _ in range(12)]
    full = idx.query(q, len(idx))
    got = [m.entity_id for m in ecs.rank_hits(idx.iter_query(q), 10)]
    assert got == _reference(ecs, full, 10)
