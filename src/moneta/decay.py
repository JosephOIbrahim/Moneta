"""Moneta decay function — lazy exponential, runtime-tunable λ.

ARCHITECTURE.md §4. Locked invariants:

- `U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))`
- Evaluated at access time only. Never on a background tick. Never on a
  60 Hz loop.
- Exactly three evaluation points, owned by three different code paths:
    1. Before context retrieval, inside `query()`             (api.py)
    2. After the attention-write phase, inside the reducer    (attention_log.py)
    3. During the consolidation scan                           (consolidation.py — Phase 1 Role 4, not this pass)

The math itself lives here as a single pure function (`decay_value`). ECS
calls it per row; the reducer invokes it indirectly via `ECS.decay_all`.
Any future numpy vectorization of the inner loop can happen without
changing the signature.

λ is instrumented via the stdlib logger — "λ must be instrumented and
logged" per MONETA.md §2.3. A production default for half-life is NOT
committed until Phase 1 load testing produces curves. The 6-hour starting
value is explicitly provisional.
"""
from __future__ import annotations

import logging
import math

_logger = logging.getLogger(__name__)

# Starting half-life per MONETA.md §2.3. Provisional until Phase 1 load testing.
DEFAULT_HALF_LIFE_SECONDS: float = 6 * 60 * 60  # 6 hours

# Tuning range per MONETA.md §2.3 ("1 minute to 24 hours").
MIN_HALF_LIFE_SECONDS: float = 60.0
MAX_HALF_LIFE_SECONDS: float = 24 * 60 * 60.0


def lambda_from_half_life(half_life_seconds: float) -> float:
    """Return the decay constant λ such that U(Δt = half_life) = U(0) / 2.

    Closed-form: λ = ln(2) / half_life.
    """
    if half_life_seconds <= 0:
        raise ValueError(f"half_life_seconds must be > 0, got {half_life_seconds}")
    return math.log(2) / half_life_seconds


def decay_value(
    utility: float,
    last_evaluated: float,
    protected_floor: float,
    lam: float,
    now: float,
) -> float:
    """Apply lazy exponential decay to a single utility value.

    Per ARCHITECTURE.md §4:

        U_now = max(protected_floor, U_last * exp(-λ * (now - last_evaluated)))

    Defensive against clock skew: a negative Δt is clamped to zero rather than
    raising, so out-of-order timestamps cannot amplify utility above its
    stored value.
    """
    dt = now - last_evaluated
    if dt < 0.0:
        dt = 0.0
    decayed = utility * math.exp(-lam * dt)
    return decayed if decayed > protected_floor else protected_floor


class DecayConfig:
    """Runtime-tunable decay configuration.

    λ is derived from a half-life so that tuning conversations can stay in
    human-readable units (minutes, hours) rather than raw λ. The tuning range
    is enforced at set time to catch misconfigurations early (MONETA.md
    §5 risk #9).

    Thread-safety: not thread-safe for concurrent `set_half_life` calls, but
    reads of `.lambda_` are atomic (single attribute load under CPython GIL).
    """

    __slots__ = ("_half_life_seconds", "_lambda")

    def __init__(self, half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS) -> None:
        self._half_life_seconds = 0.0
        self._lambda = 0.0
        self.set_half_life(half_life_seconds)

    def set_half_life(self, half_life_seconds: float) -> None:
        if not (MIN_HALF_LIFE_SECONDS <= half_life_seconds <= MAX_HALF_LIFE_SECONDS):
            raise ValueError(
                f"half_life_seconds={half_life_seconds} outside tuning range "
                f"[{MIN_HALF_LIFE_SECONDS}, {MAX_HALF_LIFE_SECONDS}] "
                f"(MONETA.md §2.3)"
            )
        self._half_life_seconds = float(half_life_seconds)
        self._lambda = lambda_from_half_life(half_life_seconds)
        _logger.info(
            "decay.config half_life=%.3fs lambda=%.6e",
            self._half_life_seconds,
            self._lambda,
        )

    @property
    def lambda_(self) -> float:
        """The decay constant λ, in inverse seconds."""
        return self._lambda

    @property
    def half_life_seconds(self) -> float:
        return self._half_life_seconds
