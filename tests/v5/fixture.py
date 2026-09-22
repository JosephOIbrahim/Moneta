"""The twelve-record, two-project fixture and its hand-authored oracle.

Vectors are chosen so every cosine against the query ``e1`` is known in
closed form (1, 1/sqrt 2, 1/sqrt 3, 0, -1). Utilities are 1.0 except the
record deposited two half-lives early (0.25). The expected orderings
below were written by hand from those numbers, not produced by running
the implementation.
"""

from __future__ import annotations

import math
from uuid import UUID

HALF_LIFE = 3600.0
T0 = 1_000_000.0
QUERY = [1.0, 0.0, 0.0, 0.0]
INV_SQRT2 = 1.0 / math.sqrt(2.0)
INV_SQRT3 = 1.0 / math.sqrt(3.0)

# name, payload, scope, vector, extra kwargs, deposit time
RECORDS: list[tuple[str, str, str, list[float], dict, float]] = [
    ("A1", "projA: farm renders with Karma XPU", "projA", [1, 0, 0, 0], {}, T0),
    ("A2", "projA: lookdev notes", "projA", [1, 1, 0, 0], {}, T0),
    ("A3", "projA: scratch idea", "projA.scratch", [1, 0, 0, 0], {}, T0),
    ("B1", "projB: client prefers a warm grade", "projB", [1, 0, 0, 0], {}, T0),
    ("B2", "projB: plate notes", "projB", [1, 0, 1, 0], {}, T0),
    ("S1", "studio: OCIO is ACEScg", "shared", [1, 1, 1, 0], {}, T0),
    ("S2", "studio: unrelated", "shared", [0, 1, 0, 0], {}, T0),
    ("P", "legal hold: never delete", "shared", [1, 0, 0, 1], {"protected_floor": 0.9}, T0),
    ("C1", "user wants concise answers", "shared", [1, 0, 0, 0], {"slot": "answer_style"}, T0),
    ("C2", "user wants detailed answers", "shared", [1, 0, 0, 0], {"slot": "answer_style"}, T0),
    ("X", "projA: anti-correlated", "projA", [-1, 0, 0, 0], {}, T0),
    ("D", "projA: two half-lives old", "projA", [1, 0, 0, 0], {}, T0 - 2 * HALF_LIFE),
]

# Hand-computed scores against QUERY at T0.
SCORES: dict[str, float] = {
    "A1": 1.0,
    "A2": INV_SQRT2,
    "A3": 1.0,
    "B1": 1.0,
    "B2": INV_SQRT2,
    "S1": INV_SQRT3,
    "S2": 0.0,
    "P": INV_SQRT2,
    "C1": 1.0,
    "C2": 1.0,
    "X": 0.0,
    "D": 0.25,
}


def policy_spec(ids: dict[str, UUID]) -> dict[str, dict]:
    return {
        "default": {},
        "projA": {
            "parent": "default",
            "include_scopes": ["projA", "projA.scratch", "shared"],
            "exclude_scopes": ["projA.scratch"],
        },
        "projB": {
            "parent": "default",
            "include_scopes": ["projB", "shared"],
            "slots": {"answer_style": str(ids["C1"])},
        },
        "projA.review": {
            "parent": "projA",
            "exclude_records": [str(ids["A2"])],
        },
    }


# Expected orderings (score desc, then deposit order). Hand-authored.
ORACLE: dict[str, list[str]] = {
    "projA": ["A1", "C2", "A2", "P", "S1", "D", "S2", "X"],
    "projB": ["B1", "C1", "B2", "P", "S1", "S2"],
    "projA.review": ["A1", "C2", "P", "S1", "D", "S2", "X"],
    "default": ["A1", "A3", "B1", "C2", "A2", "B2", "P", "S1", "D", "S2", "X"],
}


def build(substrate, resolver_factory=None) -> dict[str, UUID]:
    """Deposit the fixture. Returns name -> entity id."""
    ids: dict[str, UUID] = {}
    for name, payload, scope, vec, extra, t in RECORDS:
        ids[name] = substrate.deposit(payload, [float(x) for x in vec], scope=scope, t=t, **extra)
    return ids
