"""Shadow vector index — Phase 1 in-memory implementation.

ARCHITECTURE.md §7. The vector index is the authoritative record of
"what exists" — the sequential-write atomicity protocol puts USD
authoring first, vector second, precisely so that the vector side is
the last writer for any given entity.

Backend rationale (LanceDB vs FAISS)
------------------------------------

Persistence Engineer role contract (MONETA.md §6 Role 3) says:
"FAISS or LanceDB wrapper (choose one; recommend LanceDB for simpler
persistence story, but justify in code comment)."

LanceDB would be the production target because:

  1. Lance columnar format persists natively — no separate snapshot
     logic for the index itself, which dovetails with `durability.py`'s
     WAL-lite pattern.
  2. LanceDB supports upsert/delete in-place; FAISS requires a rebuild
     for deletes, which compounds with the accumulated-layer
     serialization tax flagged in MONETA.md §5 risk #11.
  3. LanceDB's Arrow-backed storage keeps interop open if Phase 2
     profiling decides to promote the ECS to an Arrow-backed column
     store.
  4. FAISS has GPU variants but Phase 1 has no GPU budget; LanceDB's
     CPU performance is sufficient for the expected hot-tier query
     patterns.

Phase 1 deliberately ships an in-memory stdlib backend instead of
wrapping LanceDB directly. Reasoning:

  - Phase 1 has correctness targets, not performance targets. An
    in-memory cosine-similarity index is correct and easy to audit.
  - Adding lancedb/pyarrow as runtime dependencies introduces wheel-
    availability risk on Python 3.14 Windows (the observed development
    environment) without a Phase 1 benefit.
  - Adoption of LanceDB is a Phase 2 decision driven by the benchmark
    results, not a Phase 1 architectural lock-in.
  - The Phase 1 interface (`VectorIndex` class below) is shaped to match
    what a LanceDB wrapper would expose, so the Phase 2 swap is a
    surgical backend replacement behind this file's public surface.

If a LanceDB backend is required before Phase 2, add a `_LanceDBBackend`
alongside the current in-memory path behind the same `VectorIndex`
facade. The interface contract — `upsert`, `query`, `delete`,
`update_state`, `snapshot`, `restore`, `__len__` — is the stable edge.

Native scan seam
----------------

Measured 2026-10-15 (scripts/bench_query.py and bench_arm_p.py, 10k x 384,
N=200 queries, two runs each; results/bench_query_fair_matrix.jsonl), with
every arm using the same exact early-stop rerank (ECS.rank_hits):

    pure-Python oracle   ~215 ms p50, 227-313 ms p95, ~185 MB
    numpy scan (arm P)   ~8.5 ms p50, 27-29 ms p95,  ~184 MB, and 75% of
                         cosines differ from the oracle in the last bit
    native scan + decay  ~3-6 ms p50, 3.1-6.7 ms p95, ~69 MB, bit-identical

Arm P meets the 50 ms gate, so D1's latency gate did not fire. The native
scan is admitted under the v5/v6 seam rule (a pure seam with an exact
oracle, where it buys speed or a guarantee; owner confirmation pending,
O27 in docs/v7/BLUEPRINT_v7.md). The guarantee is one numpy can't give:
bit-exact parity with this oracle (BLAS reorders the sum). It also keeps
the zero-runtime-dependency rule, where numpy would add a dependency.

The optional ``moneta_native`` extension (rust/moneta_native) stores
vectors contiguously and reproduces :func:`_oracle_scan` bit for bit.
It is never required: without the wheel, or with ``MONETA_NATIVE=0``,
the oracle runs exactly as in Phase 1.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple
from uuid import UUID

from .types import EntityState

try:  # Optional native seam (seam rule, O27). Moneta never requires it.
    import moneta_native as _native
except ImportError:  # pragma: no cover - exercised when the wheel is absent
    _native = None

_logger = logging.getLogger(__name__)

_BACKENDS = ("auto", "python", "native")

# Compact the native store once dead slots exceed both this floor and the
# live count, so a delete-heavy workload never holds more than ~2x its rows.
_COMPACT_MIN_DEAD = 1024

# First top-k window for iter_query; later windows grow 8x.
_ITER_FIRST_WINDOW = 256


def native_available() -> bool:
    """True when the optional ``moneta_native`` extension is importable."""
    return _native is not None


def _resolve_backend(backend: str) -> str:
    if backend not in _BACKENDS:
        raise ValueError(f"unknown vector index backend {backend!r}; expected one of {_BACKENDS}")
    if backend == "python":
        return "python"
    if backend == "native":
        if _native is None:
            raise RuntimeError("backend='native' requested but moneta_native is not installed")
        return "native"
    # auto: native when installed, unless MONETA_NATIVE=0 forces the oracle.
    if _native is not None and os.environ.get("MONETA_NATIVE", "1") != "0":
        return "native"
    return "python"


def _oracle_scan(
    items: Iterable[Tuple[UUID, List[float]]],
    vector: List[float],
    k: int,
) -> List[Tuple[UUID, float]]:
    """The exact oracle: sequential-sum cosine, stable sort descending.

    This is the Phase 1 scan, unchanged. The native seam is required to
    reproduce its output bit for bit (tests/unit/test_native_scan_conformance.py).
    """
    if k <= 0:
        return []
    q_norm_sq = 0.0
    for x in vector:
        q_norm_sq += x * x
    if q_norm_sq == 0.0:
        return []
    q_norm = math.sqrt(q_norm_sq)
    dim = len(vector)
    scored: list[tuple[UUID, float]] = []
    for eid, vec in items:
        if len(vec) != dim:
            continue
        dot = 0.0
        v_norm_sq = 0.0
        for a, b in zip(vec, vector):
            dot += a * b
            v_norm_sq += a * a
        if v_norm_sq == 0.0:
            continue
        cos_sim = dot / (math.sqrt(v_norm_sq) * q_norm)
        scored.append((eid, cos_sim))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:k]


def _all_finite(vector: List[float]) -> bool:
    try:
        return all(math.isfinite(x) for x in vector)
    except TypeError:
        return False


class VectorIndex:
    """Shadow vector index (Phase 1 in-memory implementation).

    Authoritative for "what exists" per ARCHITECTURE.md §7.

    Two interchangeable backends behind one facade:

    ``python``
        The Phase 1 dict-of-lists store and :func:`_oracle_scan`. This is
        the exact oracle.
    ``native``
        Vectors in a contiguous ``moneta_native.ScanIndex`` (f64, cached
        squared norms), scanned in Rust. Required to be bit-identical to
        the oracle, ties included. Holds 8 bytes per component instead of
        a Python list of float objects. Anything outside its exactness
        envelope (non-finite values, non-numeric components, zero-dim
        vectors) permanently demotes that index to the oracle.

    ``backend="auto"`` (the default) picks native when the wheel is
    installed, unless ``MONETA_NATIVE=0``.
    """

    def __init__(
        self,
        embedding_dim: Optional[int] = None,
        persist_path: Optional[Path] = None,
        backend: str = "auto",
    ) -> None:
        self._dim: Optional[int] = embedding_dim
        self._persist_path = persist_path
        if persist_path is not None:
            _logger.warning(
                "vector_index persist_path=%s ignored: Phase 1 ships in-memory "
                "backend (see module docstring for the LanceDB rationale)",
                persist_path,
            )
        self.backend = _resolve_backend(backend)
        self._reset()
        _logger.info("vector_index initialized (%s backend)", self.backend)

    def _reset(self) -> None:
        # python backend
        self._records: dict[UUID, tuple[list[float], EntityState]] = {}
        # native backend: slot order == dict insertion order of the oracle
        self._store = None
        self._slot: dict[UUID, int] = {}
        self._slot_ids: list[Optional[UUID]] = []
        self._states: dict[UUID, EntityState] = {}
        self._dead = 0

    def _demote(self, reason: str) -> None:
        """Move every row to the oracle backend, preserving order and values."""
        if self.backend == "python":
            return
        _logger.warning("vector_index demoted to python backend: %s", reason)
        records = {eid: (vec, state) for eid, vec, state in self._native_rows()}
        self._reset()
        self._records = records
        self.backend = "python"

    def _native_rows(self):
        for slot, eid in enumerate(self._slot_ids):
            if eid is not None:
                yield eid, self._store.get(slot), self._states[eid]

    def native_slots(self) -> int:
        """Slots held by the native store, live or dead (0 for python)."""
        return 0 if self._store is None else self._store.slots()

    # ------------------------------------------------------------------

    def __len__(self) -> int:
        if self.backend == "python":
            return len(self._records)
        return len(self._slot)

    def contains(self, entity_id: UUID) -> bool:
        if self.backend == "python":
            return entity_id in self._records
        return entity_id in self._states

    def get_state(self, entity_id: UUID) -> Optional[EntityState]:
        if self.backend == "python":
            rec = self._records.get(entity_id)
            if rec is None:
                return None
            return rec[1]
        return self._states.get(entity_id)

    # --- mutations ----------------------------------------------------

    def upsert(
        self,
        entity_id: UUID,
        vector: List[float],
        state: EntityState,
    ) -> None:
        """Insert or replace an entity's vector and state."""
        if self._dim is None:
            self._dim = len(vector)
        elif len(vector) != self._dim:
            raise ValueError(
                f"embedding dim mismatch: expected {self._dim}, got {len(vector)}"
            )
        vec = list(vector)
        if self.backend == "native":
            # The native store validates (finite f64, dim > 0) and raises
            # before mutating anything; on refusal, demote to the oracle.
            try:
                if self._store is None:
                    self._store = _native.ScanIndex(len(vec))
                slot = self._slot.get(entity_id)
                if slot is None:
                    self._slot[entity_id] = self._store.push(vec)
                    self._slot_ids.append(entity_id)
                else:
                    self._store.set(slot, vec)
                self._states[entity_id] = state
                return
            except (TypeError, ValueError, OverflowError):
                self._demote("non-finite, non-numeric or empty vector upserted")
        self._records[entity_id] = (vec, state)

    def update_state(self, entity_id: UUID, state: EntityState) -> None:
        """Change the state on an existing entity without touching its vector.

        Silently no-ops if the entity is absent (matches §5.1's
        "eventually consistent" discipline for missing entities).
        """
        if self.backend == "python":
            rec = self._records.get(entity_id)
            if rec is None:
                return
            vec, _ = rec
            self._records[entity_id] = (vec, state)
            return
        if entity_id in self._states:
            self._states[entity_id] = state

    def delete(self, entity_id: UUID) -> None:
        """Remove an entity from the index. Idempotent."""
        if self.backend == "python":
            self._records.pop(entity_id, None)
            return
        slot = self._slot.pop(entity_id, None)
        if slot is None:
            return
        self._store.kill(slot)
        self._slot_ids[slot] = None
        del self._states[entity_id]
        self._dead += 1
        if self._dead > _COMPACT_MIN_DEAD and self._dead > len(self._slot):
            self._compact()

    def _compact(self) -> None:
        mapping = self._store.compact()
        ids: list[Optional[UUID]] = [None] * len(self._slot)
        for old, new in enumerate(mapping):
            if new >= 0:
                ids[new] = self._slot_ids[old]
        self._slot_ids = ids
        self._slot = {eid: i for i, eid in enumerate(ids)}
        self._dead = 0

    # --- queries ------------------------------------------------------

    def query(
        self,
        vector: List[float],
        k: int,
    ) -> List[Tuple[UUID, float]]:
        """Return top-k `(entity_id, cosine_similarity)` pairs.

        Ordered by descending cosine similarity, ties in insertion order.
        Entities with zero-norm vectors are silently skipped. Dim-mismatched
        entries are also skipped (defensive; should never happen under the
        upsert guard).
        """
        if self.backend == "python":
            if not self._records or k <= 0:
                return []
            return _oracle_scan(
                ((eid, vec) for eid, (vec, _s) in self._records.items()), vector, k
            )
        if not self._slot or k <= 0:
            return []
        q = list(vector)
        if not _all_finite(q):
            # Outside the native envelope: answer with the oracle itself.
            return _oracle_scan(
                ((eid, vec) for eid, vec, _s in self._native_rows()), q, k
            )
        try:
            window = self._store.scan(q, k)
        except ArithmeticError:
            # A NaN cosine (overflow from huge finite components): only the
            # oracle's own sort reproduces its ordering, so let it answer.
            return _oracle_scan(
                ((eid, vec) for eid, vec, _s in self._native_rows()), q, k
            )
        ids = self._slot_ids
        return [(ids[slot], cos) for slot, cos in window]

    def iter_query(self, vector: List[float]) -> Iterator[Tuple[UUID, float]]:
        """Yield every hit lazily, in exactly :meth:`query`'s order.

        Lets a consumer that can stop early (``ECS.rank_hits``) avoid
        materializing all n hits. The native backend scans in growing
        top-k windows; each window is a prefix of the full order, so only
        the new tail is yielded (prefix property: the Rust test
        ``topk_equals_full_sort_prefix`` and the conformance suite).

        Single-writer rule: do not mutate the index while a generator is
        live (a compaction would remap slots under it).
        """
        if self.backend == "python" or not _all_finite(list(vector)):
            yield from self.query(vector, len(self))
            return
        total = len(self._slot)
        if total == 0:
            return
        q = list(vector)
        ids = self._slot_ids
        done = 0
        k = min(total, _ITER_FIRST_WINDOW)
        while done < total:
            try:
                window = self._store.scan(q, k)
            except ArithmeticError:
                # NaN cosine: replay the oracle's full order and skip what
                # was already yielded (the windows are its prefixes).
                yield from self.query(q, total)[done:]
                return
            for slot, cos in window[done:]:
                yield ids[slot], cos
            if len(window) < k:
                return  # zero-norm rows exhausted the scan early
            done = len(window)
            k = min(total, k * 8)

    # --- snapshot / restore (used by durability.py) -------------------

    def snapshot(self) -> dict:
        """Serializable snapshot of the in-memory state.

        Identical for both backends (same keys, same record order).
        """
        if self.backend == "python":
            rows = ((eid, vec, state) for eid, (vec, state) in self._records.items())
        else:
            rows = self._native_rows()
        return {
            "backend": "in_memory",
            "embedding_dim": self._dim,
            "records": [
                {
                    "entity_id": str(eid),
                    "vector": list(vec),
                    "state": int(state),
                }
                for eid, vec, state in rows
            ],
        }

    def restore(self, snapshot: dict) -> None:
        """Replace current state with a snapshot produced by `snapshot()`."""
        self._dim = snapshot.get("embedding_dim")
        if self.backend == "native" and not self._dim and snapshot.get("records"):
            self._demote("restoring records without an embedding_dim")
        self._reset()
        records = snapshot.get("records", [])
        if self.backend == "native" and any(
            len(rec["vector"]) != self._dim or not _all_finite(rec["vector"])
            for rec in records
        ):
            _logger.warning("vector_index demoted to python backend: snapshot outside native envelope")
            self.backend = "python"
        for rec in records:
            eid = UUID(rec["entity_id"])
            vec = list(rec["vector"])
            state = EntityState(rec["state"])
            if self.backend == "python":
                self._records[eid] = (vec, state)
            else:
                if self._store is None:
                    self._store = _native.ScanIndex(self._dim)
                slot = self._slot.get(eid)
                if slot is None:  # a repeated id keeps its first position, like a dict
                    self._slot[eid] = self._store.push(vec)
                    self._slot_ids.append(eid)
                else:
                    self._store.set(slot, vec)
                self._states[eid] = state
