"""Functional fakes of ``moneta_native`` for the C2 seam tests.

``FakeScanIndex`` behaves like the Rust store closely enough to run a real
``Moneta`` handle on it: it validates like the native store (finite,
numeric, non-empty, fixed dim; raise before mutating) and its ``scan``
reproduces ``_oracle_scan`` order (stable, cosine descending), raising
``ArithmeticError`` on a NaN cosine. ``decay_batch`` is the oracle per row,
and can be switched to fail in a chosen way.

These run in every matrix row (wheel loaded, absent, broken), because the
fake is injected into ``sys.modules`` after isolating the loader.
"""

from __future__ import annotations

import math
import sys
import types

from moneta import _native
from moneta.decay import decay_value

MOD = "moneta_native"
SUB = "moneta_native.moneta_native"


class FakeScanIndex:
    scans = 0  # class-wide count of successful scans (per test, reset by fixture)

    def __init__(self, dim):
        if int(dim) <= 0:
            raise ValueError("dim must be > 0")
        self.dim = int(dim)
        self._rows: list = []  # list[list[float] | None]

    def _check(self, vec):
        if len(vec) != self.dim or len(vec) == 0:
            raise ValueError("dim mismatch")
        out = [float(x) for x in vec]  # TypeError on non-numeric
        if not all(math.isfinite(x) for x in out):
            raise ValueError("non-finite")
        return out

    def push(self, vec):
        row = self._check(vec)
        self._rows.append(row)
        return len(self._rows) - 1

    def set(self, slot, vec):
        self._rows[slot] = self._check(vec)

    def get(self, slot):
        return list(self._rows[slot])

    def kill(self, slot):
        self._rows[slot] = None

    def compact(self):
        mapping, rows = [], []
        for r in self._rows:
            if r is None:
                mapping.append(-1)
            else:
                mapping.append(len(rows))
                rows.append(r)
        self._rows = rows
        return mapping

    def slots(self):
        return len(self._rows)

    def scan(self, q, k):
        if k <= 0:
            return []
        qn = 0.0
        for x in q:
            qn += x * x
        if qn == 0.0 or len(q) != self.dim:
            FakeScanIndex.scans += 1
            return []
        qn = math.sqrt(qn)
        scored = []
        for slot, vec in enumerate(self._rows):
            if vec is None:
                continue
            dot = 0.0
            vn = 0.0
            for a, b in zip(vec, q, strict=False):
                dot += a * b
                vn += a * a
            if vn == 0.0:
                continue
            cos = dot / (math.sqrt(vn) * qn)
            if cos != cos:
                raise ArithmeticError("NaN cosine")
            scored.append((slot, cos))
        scored.sort(key=lambda t: t[1], reverse=True)
        FakeScanIndex.scans += 1
        return scored[:k]


class DecayControl:
    """Switch for the fake ``decay_batch``: ``fail`` is None (oracle), an
    exception instance to raise, or ``"short"`` / ``"wrong_type"`` /
    ``"not_list"`` for a malformed result."""

    def __init__(self):
        self.fail = None
        self.calls = 0


def make_module(control: DecayControl | None = None, *, version="0.1.0", api=None):
    control = control if control is not None else DecayControl()
    mod = types.ModuleType(MOD)
    mod.__version__ = version
    if api is not None:
        mod.NATIVE_API = api

    def decay_batch(u, last, floor, lam, now):
        control.calls += 1
        u, last, floor = list(u), list(last), list(floor)  # owned copies, like Rust
        if len(u) != len(last) or len(u) != len(floor):
            raise ValueError("column length mismatch")
        f = control.fail
        if isinstance(f, BaseException):
            raise f
        out = [decay_value(u[i], last[i], floor[i], lam, now) for i in range(len(u))]
        if f == "short":
            return out[:-1]
        if f == "long":
            return out + [0.0]
        if f == "wrong_type":
            return [int(x) if i == 0 else x for i, x in enumerate(out)]
        if f == "not_list":
            return tuple(out)
        return out

    mod.decay_batch = decay_batch
    mod.ScanIndex = FakeScanIndex
    mod._control = control
    return mod


def isolate(monkeypatch):
    """Remove moneta_native from sys.modules and reset the loader."""
    monkeypatch.delitem(sys.modules, MOD, raising=False)
    monkeypatch.delitem(sys.modules, SUB, raising=False)
    monkeypatch.delenv("MONETA_NATIVE", raising=False)
    _native._reset_for_tests()
    FakeScanIndex.scans = 0


def install(monkeypatch, mod):
    monkeypatch.setitem(sys.modules, MOD, mod)
    return mod
