"""Derived exact vector index.

Rebuilt from the fold at every open; never persisted, never authoritative.
Deleting it (there is nothing on disk to delete) cannot change a result,
which is invariant I1 by construction rather than by test discipline.

Scoring matches v1 at commit c4a6218: ``max(cosine, 0) * utility``.
Stdlib only, preserving the zero-runtime-dependency hot path. A native
or Rust kernel replaces :meth:`ExactIndex.cosines` behind the same shape.

Native seam (seam rule, O27): when the optional ``moneta_native`` wheel is
installed (and ``MONETA_NATIVE`` is not ``0``), unit vectors are mirrored
into a contiguous Rust store and only the dot products run natively. The
query is still normalized here, by the oracle code. The Rust sum
reproduces the running interpreter's ``sum()``: left to right on CPython
<= 3.11, Neumaier-compensated on >= 3.12. So native cosines are
bit-identical to this module's Python path on every interpreter
(tests/v5/test_native_index_parity.py). Python 3.11 and 3.14 can differ
from *each other* in the last bit, natively or not.
"""

from __future__ import annotations

import math
import os
import platform
import sys
from collections.abc import Iterable, Sequence
from uuid import UUID

from .model import DimensionMismatchError

try:  # Optional native seam; the Python loop in ``cosines`` is its oracle.
    import moneta_native as _native
except ImportError:  # pragma: no cover - exercised when the wheel is absent
    _native = None

# CPython >= 3.12 sums floats with Neumaier compensation (gh-100425).
_COMPENSATED_SUM = sys.version_info >= (3, 12)
_COMPACT_MIN_DEAD = 1024


def native_enabled() -> bool:
    return (
        _native is not None
        and platform.python_implementation() == "CPython"
        and os.environ.get("MONETA_NATIVE", "1") != "0"
    )


class ExactIndex:
    def __init__(self, native: bool | None = None) -> None:
        self._units: dict[UUID, tuple[float, ...]] = {}
        self.dim: int | None = None
        if native is None:
            native = native_enabled()
        elif native and _native is None:
            raise RuntimeError("native=True requested but moneta_native is not installed")
        self.native = bool(native)
        self._store = None
        self._slot: dict[UUID, int] = {}
        self._slot_ids: list[UUID | None] = []
        self._dead = 0

    def __len__(self) -> int:
        return len(self._units)

    def add(self, entity_id: UUID, unit: tuple[float, ...]) -> None:
        if self.dim is None:
            self.dim = len(unit)
        self._units[entity_id] = unit
        if self.native:
            if self._store is None:
                self._store = _native.ScanIndex(len(unit))
            slot = self._slot.get(entity_id)
            if slot is None:
                self._slot[entity_id] = self._store.push(list(unit))
                self._slot_ids.append(entity_id)
            else:
                self._store.set(slot, list(unit))

    def remove(self, entity_id: UUID) -> None:
        self._units.pop(entity_id, None)
        if self.native:
            slot = self._slot.pop(entity_id, None)
            if slot is None:
                return
            self._store.kill(slot)
            self._slot_ids[slot] = None
            self._dead += 1
            if self._dead > _COMPACT_MIN_DEAD and self._dead > len(self._slot):
                mapping = self._store.compact()
                ids: list[UUID | None] = [None] * len(self._slot)
                for old, new in enumerate(mapping):
                    if new >= 0:
                        ids[new] = self._slot_ids[old]
                self._slot_ids = ids
                self._slot = {eid: i for i, eid in enumerate(ids)}
                self._dead = 0

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
        ids = list(ids)
        use_native = self.native and self._store is not None
        lookup = self._slot if use_native else self._units
        found = []
        for eid in ids:
            hit = lookup.get(eid)
            if hit is None:
                raise KeyError(f"index has no vector for recallable record {eid}")
            found.append(hit)
        if use_native:
            return list(zip(ids, self._store.dots(q, found, _COMPENSATED_SUM), strict=False))
        return [
            (eid, sum(a * b for a, b in zip(unit, q, strict=False)))
            for eid, unit in zip(ids, found, strict=False)
        ]
