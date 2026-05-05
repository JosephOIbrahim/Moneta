"""Unit tests for `moneta.vector_index`.

Locked clauses verified here:
  - ARCHITECTURE.md §7.1 — shadow vector index dim-homogeneity invariant
    ("the vector index rejects dim-mismatched upserts ... a hard
    ValueError — not a silent skip")
  - ARCHITECTURE.md §5.1 — eventually consistent: ``update_state``/``delete``
    are silent no-ops on missing entities
  - ARCHITECTURE.md §7   — VectorIndex is "authoritative for what exists"

Coverage gap closed by review finding test-L3-vector-index-no-unit-tests.
Until this file landed, the §7.1 hard-raise contract was exercised only
transitively via deposit/query integration tests and could regress
silently to a no-op without any unit-level alarm.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from moneta.types import EntityState
from moneta.vector_index import VectorIndex

# ---------------------------------------------------------------------
# constructor + dim-homogeneity (§7.1)
# ---------------------------------------------------------------------


class TestUpsertAndDimHomogeneity:
    def test_first_upsert_auto_sets_dim_when_constructor_dim_none(self) -> None:
        idx = VectorIndex(embedding_dim=None)
        idx.upsert(uuid4(), [1.0, 2.0, 3.0], EntityState.VOLATILE)
        assert idx._dim == 3  # noqa: SLF001 — testing the locked invariant

    def test_constructor_dim_is_authoritative(self) -> None:
        idx = VectorIndex(embedding_dim=4)
        idx.upsert(uuid4(), [1.0, 0.0, 0.0, 0.0], EntityState.VOLATILE)
        assert idx._dim == 4  # noqa: SLF001

    def test_dim_mismatch_raises_against_auto_set_dim(self) -> None:
        """§7.1: dim-mismatched upsert is a HARD raise, not a silent skip."""
        idx = VectorIndex(embedding_dim=None)
        idx.upsert(uuid4(), [1.0, 0.0], EntityState.VOLATILE)  # auto-sets dim=2
        with pytest.raises(ValueError, match="embedding dim mismatch"):
            idx.upsert(uuid4(), [1.0, 0.0, 0.0], EntityState.VOLATILE)

    def test_dim_mismatch_raises_against_constructor_dim(self) -> None:
        idx = VectorIndex(embedding_dim=2)
        with pytest.raises(ValueError, match="expected 2, got 5"):
            idx.upsert(uuid4(), [0.0] * 5, EntityState.VOLATILE)

    def test_upsert_overwrites_existing_entry(self) -> None:
        idx = VectorIndex()
        eid = uuid4()
        idx.upsert(eid, [1.0, 0.0], EntityState.VOLATILE)
        idx.upsert(eid, [0.0, 1.0], EntityState.STAGED_FOR_SYNC)
        assert idx.get_state(eid) == EntityState.STAGED_FOR_SYNC
        assert len(idx) == 1


# ---------------------------------------------------------------------
# eventually-consistent no-ops (§5.1)
# ---------------------------------------------------------------------


class TestEventualConsistencyNoOps:
    def test_update_state_on_missing_entity_is_silent_noop(self) -> None:
        """§5.1: missing entity → silent no-op, no exception, no length change."""
        idx = VectorIndex()
        ghost = uuid4()
        idx.update_state(ghost, EntityState.CONSOLIDATED)  # must not raise
        assert len(idx) == 0
        assert idx.get_state(ghost) is None

    def test_update_state_preserves_vector(self) -> None:
        idx = VectorIndex()
        eid = uuid4()
        idx.upsert(eid, [0.5, 0.5], EntityState.VOLATILE)
        idx.update_state(eid, EntityState.STAGED_FOR_SYNC)
        # vector untouched (state-only mutation): query against it returns it.
        results = idx.query([0.5, 0.5], k=1)
        assert results and results[0][0] == eid
        assert idx.get_state(eid) == EntityState.STAGED_FOR_SYNC

    def test_delete_idempotent_on_missing_entity(self) -> None:
        idx = VectorIndex()
        idx.delete(uuid4())  # must not raise
        idx.delete(uuid4())  # second time still must not raise
        assert len(idx) == 0

    def test_delete_actually_removes(self) -> None:
        idx = VectorIndex()
        eid = uuid4()
        idx.upsert(eid, [1.0, 0.0], EntityState.VOLATILE)
        assert idx.contains(eid)
        idx.delete(eid)
        assert not idx.contains(eid)
        assert len(idx) == 0


# ---------------------------------------------------------------------
# query semantics (zero-norm guards, k bounds)
# ---------------------------------------------------------------------


class TestQuerySemantics:
    def test_query_with_zero_norm_query_returns_empty(self) -> None:
        """A zero-norm query vector cannot produce a valid cosine — empty."""
        idx = VectorIndex()
        idx.upsert(uuid4(), [1.0, 0.0], EntityState.VOLATILE)
        assert idx.query([0.0, 0.0], k=5) == []

    def test_query_skips_zero_norm_stored_vectors(self) -> None:
        """A stored zero-norm vector is silently skipped (cannot rank)."""
        idx = VectorIndex()
        zero_eid = uuid4()
        live_eid = uuid4()
        idx.upsert(zero_eid, [0.0, 0.0], EntityState.VOLATILE)
        idx.upsert(live_eid, [1.0, 0.0], EntityState.VOLATILE)
        results = idx.query([1.0, 0.0], k=5)
        assert len(results) == 1
        assert results[0][0] == live_eid

    def test_query_k_zero_returns_empty(self) -> None:
        idx = VectorIndex()
        idx.upsert(uuid4(), [1.0, 0.0], EntityState.VOLATILE)
        assert idx.query([1.0, 0.0], k=0) == []

    def test_query_k_greater_than_n_returns_all(self) -> None:
        idx = VectorIndex()
        for _ in range(3):
            idx.upsert(uuid4(), [1.0, 0.0], EntityState.VOLATILE)
        results = idx.query([1.0, 0.0], k=100)
        assert len(results) == 3

    def test_query_orders_by_descending_cosine(self) -> None:
        idx = VectorIndex()
        eid_a = uuid4()
        eid_b = uuid4()
        eid_c = uuid4()
        idx.upsert(eid_a, [1.0, 0.0], EntityState.VOLATILE)  # exact match
        idx.upsert(eid_b, [0.5, 0.5], EntityState.VOLATILE)  # 45 deg
        idx.upsert(eid_c, [0.0, 1.0], EntityState.VOLATILE)  # orthogonal
        results = idx.query([1.0, 0.0], k=3)
        ids = [r[0] for r in results]
        assert ids == [eid_a, eid_b, eid_c]

    def test_query_on_empty_index_returns_empty(self) -> None:
        assert VectorIndex().query([1.0, 0.0], k=5) == []


# ---------------------------------------------------------------------
# snapshot / restore round-trip (used by durability.py)
# ---------------------------------------------------------------------


class TestSnapshotRestore:
    def test_snapshot_restore_preserves_records(self) -> None:
        idx = VectorIndex(embedding_dim=2)
        eid_a = uuid4()
        eid_b = uuid4()
        idx.upsert(eid_a, [1.0, 0.0], EntityState.VOLATILE)
        idx.upsert(eid_b, [0.0, 1.0], EntityState.CONSOLIDATED)
        snap = idx.snapshot()

        fresh = VectorIndex()
        fresh.restore(snap)
        assert len(fresh) == 2
        assert fresh.get_state(eid_a) == EntityState.VOLATILE
        assert fresh.get_state(eid_b) == EntityState.CONSOLIDATED
        assert fresh._dim == 2  # noqa: SLF001
