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
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from .types import EntityState

_logger = logging.getLogger(__name__)


class VectorIndex:
    """Shadow vector index (Phase 1 in-memory implementation).

    Authoritative for "what exists" per ARCHITECTURE.md §7.
    """

    def __init__(
        self,
        embedding_dim: Optional[int] = None,
        persist_path: Optional[Path] = None,
    ) -> None:
        self._dim: Optional[int] = embedding_dim
        self._persist_path = persist_path
        if persist_path is not None:
            _logger.warning(
                "vector_index persist_path=%s ignored: Phase 1 ships in-memory "
                "backend (see module docstring for the LanceDB rationale)",
                persist_path,
            )
        self._records: dict[UUID, tuple[list[float], EntityState]] = {}
        _logger.info("vector_index initialized (in-memory backend)")

    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._records)

    def contains(self, entity_id: UUID) -> bool:
        return entity_id in self._records

    def get_state(self, entity_id: UUID) -> Optional[EntityState]:
        rec = self._records.get(entity_id)
        if rec is None:
            return None
        return rec[1]

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
        self._records[entity_id] = (list(vector), state)

    def update_state(self, entity_id: UUID, state: EntityState) -> None:
        """Change the state on an existing entity without touching its vector.

        Silently no-ops if the entity is absent (matches §5.1's
        "eventually consistent" discipline for missing entities).
        """
        rec = self._records.get(entity_id)
        if rec is None:
            return
        vec, _ = rec
        self._records[entity_id] = (vec, state)

    def delete(self, entity_id: UUID) -> None:
        """Remove an entity from the index. Idempotent."""
        self._records.pop(entity_id, None)

    # --- queries ------------------------------------------------------

    def query(
        self,
        vector: List[float],
        k: int,
    ) -> List[Tuple[UUID, float]]:
        """Return top-k `(entity_id, cosine_similarity)` pairs.

        Ordered by descending cosine similarity. Entities with zero-norm
        vectors are silently skipped. Dim-mismatched entries are also
        skipped (defensive; should never happen under the upsert guard).
        """
        if not self._records or k <= 0:
            return []
        q_norm_sq = 0.0
        for x in vector:
            q_norm_sq += x * x
        if q_norm_sq == 0.0:
            return []
        q_norm = math.sqrt(q_norm_sq)
        dim = len(vector)
        scored: list[tuple[UUID, float]] = []
        for eid, (vec, _state) in self._records.items():
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

    # --- snapshot / restore (used by durability.py) -------------------

    def snapshot(self) -> dict:
        """Serializable snapshot of the in-memory state."""
        return {
            "backend": "in_memory",
            "embedding_dim": self._dim,
            "records": [
                {
                    "entity_id": str(eid),
                    "vector": list(vec),
                    "state": int(state),
                }
                for eid, (vec, state) in self._records.items()
            ],
        }

    def restore(self, snapshot: dict) -> None:
        """Replace current state with a snapshot produced by `snapshot()`."""
        self._dim = snapshot.get("embedding_dim")
        self._records.clear()
        for rec in snapshot.get("records", []):
            self._records[UUID(rec["entity_id"])] = (
                list(rec["vector"]),
                EntityState(rec["state"]),
            )
