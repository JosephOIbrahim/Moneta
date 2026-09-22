"""Derived exact vector index.

Rebuilt from the fold at every open; never persisted, never authoritative.
Deleting it (there is nothing on disk to delete) cannot change a result,
which is invariant I1 by construction rather than by test discipline.

Scoring matches v1 at commit c4a6218: ``max(cosine, 0) * utility``.
Stdlib only, preserving the zero-runtime-dependency hot path. A native
or Rust kernel replaces :meth:`ExactIndex.cosines` behind the same shape.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from uuid import UUID

from .model import DimensionMismatchError


class ExactIndex:
    def __init__(self) -> None:
        self._units: dict[UUID, tuple[float, ...]] = {}
        self.dim: int | None = None

    def __len__(self) -> int:
        return len(self._units)

    def add(self, entity_id: UUID, unit: tuple[float, ...]) -> None:
        if self.dim is None:
            self.dim = len(unit)
        self._units[entity_id] = unit

    def remove(self, entity_id: UUID) -> None:
        self._units.pop(entity_id, None)

    def contains(self, entity_id: UUID) -> bool:
        return entity_id in self._units

    def cosines(self, query: Sequence[float], ids: Iterable[UUID]) -> list[tuple[UUID, float]]:
        """Exact cosine between ``query`` and each id. Raises on dim mismatch."""
        if self.dim is not None and len(query) != self.dim:
            raise DimensionMismatchError(self.dim, len(query))
        norm = math.sqrt(sum(x * x for x in query))
        if norm == 0.0:
            raise ValueError("query embedding has zero norm")
        q = [x / norm for x in query]
        out: list[tuple[UUID, float]] = []
        for eid in ids:
            unit = self._units.get(eid)
            if unit is None:
                raise KeyError(f"index has no vector for recallable record {eid}")
            out.append((eid, sum(a * b for a, b in zip(unit, q, strict=False))))
        return out
