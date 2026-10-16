"""V-EXP analogue: the native decay kernel against ``decay.decay_value``.

The kernel must return the exact same doubles as the Phase 1 per-row
function, including the negative-dt clamp (decay.py) and the floor branch.
Compared with ``==`` on the bit pattern; NaN compared by pattern too.
"""
from __future__ import annotations

import math
import random
import struct

import pytest

from moneta.decay import decay_value
from moneta.ecs import ECS
from moneta.types import EntityState

# Needs the real wheel; skips visibly through the conftest native harness.
pytestmark = pytest.mark.native


def _bits(x: float) -> bytes:
    return struct.pack("<d", x)


def _oracle(u, last, floor, lam, now):
    return [decay_value(u[i], last[i], floor[i], lam, now) for i in range(len(u))]


def test_random_columns_bit_identical():
    import moneta_native

    rng = random.Random(0)
    for trial in range(40):
        n = 5000
        now = rng.uniform(1e9, 2e9)
        lam = math.log(2) / rng.choice([60.0, 3600.0, 6 * 3600.0, 86400.0, rng.uniform(1, 1e6)])
        u = [rng.random() for _ in range(n)]
        last = [now - rng.expovariate(1 / 7200.0) for _ in range(n)]
        floor = [rng.choice([0.0, 0.0, 0.1, rng.random()]) for _ in range(n)]
        got = moneta_native.decay_batch(u, last, floor, lam, now)
        want = _oracle(u, last, floor, lam, now)
        assert list(map(_bits, got)) == list(map(_bits, want)), f"trial {trial}"


def test_edges_bit_identical():
    import moneta_native

    now = 1_700_000_000.0
    lam = math.log(2) / 21600.0
    cases = [
        # (utility, last_evaluated, floor)
        (1.0, now, 0.0),                 # dt = 0
        (1.0, now + 50.0, 0.0),          # negative dt clamps to 0
        (0.5, now - 1e12, 0.0),          # underflow to 0
        (0.5, now - 1e12, 0.25),         # floor wins
        (5e-324, now - 1.0, 0.0),        # subnormal utility
        (0.3, now - 3600.0, 0.3),        # decayed < floor exactly at floor
        (math.nan, now - 1.0, 0.1),      # NaN > floor is false -> floor
        (1.0, math.nan, 0.0),            # NaN dt propagates
        (1.0, -math.inf, 0.0),           # infinite dt -> 0
        (-0.0, now - 1.0, 0.0),          # signed zero
    ]
    u = [c[0] for c in cases]
    last = [c[1] for c in cases]
    floor = [c[2] for c in cases]
    for lam_ in (lam, 0.0, 1e-300, 1e300):
        got = moneta_native.decay_batch(u, last, floor, lam_, now)
        want = _oracle(u, last, floor, lam_, now)
        assert list(map(_bits, got)) == list(map(_bits, want))


def test_length_mismatch_rejected():
    import moneta_native

    with pytest.raises(ValueError):
        moneta_native.decay_batch([1.0], [0.0, 0.0], [0.0], 0.1, 1.0)


def test_ecs_decay_all_native_equals_oracle():
    rng = random.Random(3)
    a, b = ECS(native=True), ECS(native=False)
    assert a.native_decay and not b.native_decay
    now = 1e9
    for i in range(3000):
        args = (f"p{i}", [1.0], rng.random(), rng.choice([0.0, 0.2]), EntityState.VOLATILE, now - rng.uniform(-10, 1e5))
        from uuid import uuid4

        eid = uuid4()
        a.add(eid, *args)
        b.add(eid, *args)
    lam = math.log(2) / 3600.0
    for t in (now, now + 10.0, now + 1e4):
        a.decay_all(lam, t)
        b.decay_all(lam, t)
        assert list(map(_bits, a._utility)) == list(map(_bits, b._utility))
        assert a._last_evaluated == b._last_evaluated
