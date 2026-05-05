"""Unit tests for `moneta.decay`.

Covers ARCHITECTURE.md §4:
  - Closed-form reference curves
  - λ tuning-range enforcement
  - ProtectedFloor clamp
  - Edge cases: Δt = 0, Δt < 0 (clock skew), very old LastEvaluated
"""
from __future__ import annotations

import math

import pytest

from moneta.decay import (
    DEFAULT_HALF_LIFE_SECONDS,
    MAX_HALF_LIFE_SECONDS,
    MIN_HALF_LIFE_SECONDS,
    DecayConfig,
    decay_value,
    lambda_from_half_life,
)

# ---------------------------------------------------------------------
# lambda_from_half_life
# ---------------------------------------------------------------------


class TestLambdaFromHalfLife:
    def test_6_hour_half_life_matches_closed_form(self) -> None:
        lam = lambda_from_half_life(6 * 60 * 60)
        assert lam == pytest.approx(math.log(2) / (6 * 60 * 60), rel=1e-12)

    def test_1_minute_half_life(self) -> None:
        lam = lambda_from_half_life(60)
        assert lam == pytest.approx(math.log(2) / 60, rel=1e-12)

    def test_24_hour_half_life(self) -> None:
        lam = lambda_from_half_life(24 * 60 * 60)
        assert lam == pytest.approx(math.log(2) / (24 * 60 * 60), rel=1e-12)

    def test_zero_half_life_raises(self) -> None:
        with pytest.raises(ValueError):
            lambda_from_half_life(0)

    def test_negative_half_life_raises(self) -> None:
        with pytest.raises(ValueError):
            lambda_from_half_life(-1)


# ---------------------------------------------------------------------
# decay_value — reference curves
# ---------------------------------------------------------------------


class TestDecayValue:
    def test_dt_zero_no_decay(self) -> None:
        """At Δt = 0, decay_value returns the input utility unchanged."""
        lam = lambda_from_half_life(DEFAULT_HALF_LIFE_SECONDS)
        assert decay_value(1.0, 100.0, 0.0, lam, 100.0) == pytest.approx(1.0)
        assert decay_value(0.5, 100.0, 0.0, lam, 100.0) == pytest.approx(0.5)

    def test_one_half_life_halves_utility(self) -> None:
        """At Δt = half_life, utility halves."""
        half_life = 60.0
        lam = lambda_from_half_life(half_life)
        result = decay_value(1.0, 0.0, 0.0, lam, half_life)
        assert result == pytest.approx(0.5, rel=1e-12)

    def test_two_half_lives_quarters_utility(self) -> None:
        half_life = 60.0
        lam = lambda_from_half_life(half_life)
        result = decay_value(1.0, 0.0, 0.0, lam, 2 * half_life)
        assert result == pytest.approx(0.25, rel=1e-12)

    def test_matches_closed_form_1e9_tolerance(self) -> None:
        """Conformance checklist: decay matches closed form to 1e-9 rel tol."""
        half_life = 3600.0
        lam = lambda_from_half_life(half_life)
        for dt in [1.0, 10.0, 100.0, 1000.0, 3600.0, 7200.0]:
            expected = 1.0 * math.exp(-lam * dt)
            actual = decay_value(1.0, 0.0, 0.0, lam, dt)
            assert actual == pytest.approx(expected, rel=1e-9)

    def test_protected_floor_clamps(self) -> None:
        """Decayed utility never drops below protected_floor."""
        lam = lambda_from_half_life(60.0)
        # Δt = 100 half-lives — decayed value is near zero
        result = decay_value(1.0, 0.0, 0.5, lam, 6000.0)
        assert result == pytest.approx(0.5)

    def test_protected_floor_zero_no_clamp(self) -> None:
        lam = lambda_from_half_life(60.0)
        result = decay_value(1.0, 0.0, 0.0, lam, 600.0)
        assert 0.0 < result < 0.01  # decayed but above zero

    def test_negative_dt_guarded_to_zero(self) -> None:
        """Clock skew: last_evaluated in the future → no amplification."""
        lam = lambda_from_half_life(60.0)
        # "now" is 100s earlier than last_evaluated
        result = decay_value(0.8, 100.0, 0.0, lam, 0.0)
        # Δt clamps to 0 → utility unchanged, not amplified
        assert result == pytest.approx(0.8)

    def test_very_old_last_evaluated_decays_to_floor(self) -> None:
        """A memory last evaluated days ago should decay to its floor."""
        lam = lambda_from_half_life(3600.0)  # 1-hour half-life
        # 7 days later
        result = decay_value(1.0, 0.0, 0.1, lam, 7 * 24 * 3600.0)
        assert result == pytest.approx(0.1)  # clamped to floor


# ---------------------------------------------------------------------
# DecayConfig — tuning bounds
# ---------------------------------------------------------------------


class TestDecayConfig:
    def test_default_half_life_is_6_hours(self) -> None:
        cfg = DecayConfig()
        assert cfg.half_life_seconds == DEFAULT_HALF_LIFE_SECONDS
        assert cfg.half_life_seconds == 6 * 60 * 60

    def test_lambda_property_matches_half_life(self) -> None:
        cfg = DecayConfig(half_life_seconds=3600.0)
        assert cfg.lambda_ == pytest.approx(math.log(2) / 3600.0, rel=1e-12)

    def test_set_half_life_updates_lambda(self) -> None:
        cfg = DecayConfig(half_life_seconds=3600.0)
        cfg.set_half_life(60.0)
        assert cfg.half_life_seconds == 60.0
        assert cfg.lambda_ == pytest.approx(math.log(2) / 60.0, rel=1e-12)

    def test_below_tuning_range_raises(self) -> None:
        with pytest.raises(ValueError, match="tuning range"):
            DecayConfig(half_life_seconds=MIN_HALF_LIFE_SECONDS - 1)

    def test_above_tuning_range_raises(self) -> None:
        with pytest.raises(ValueError, match="tuning range"):
            DecayConfig(half_life_seconds=MAX_HALF_LIFE_SECONDS + 1)

    def test_min_tuning_range_accepted(self) -> None:
        cfg = DecayConfig(half_life_seconds=MIN_HALF_LIFE_SECONDS)
        assert cfg.half_life_seconds == MIN_HALF_LIFE_SECONDS

    def test_max_tuning_range_accepted(self) -> None:
        cfg = DecayConfig(half_life_seconds=MAX_HALF_LIFE_SECONDS)
        assert cfg.half_life_seconds == MAX_HALF_LIFE_SECONDS


# ---------------------------------------------------------------------
# Structural invariant: exactly three decay evaluation points
# ---------------------------------------------------------------------


class TestDecayEvaluationPoints:
    """ARCHITECTURE.md §16 conformance gate: 'Decay evaluation points:
    exactly three (§4). A test asserts no fourth call site.'

    The three sanctioned sites are:
      1. ``api.py``                — query path (pre-retrieval)
      2. ``attention_log.py``      — reducer (post-aggregate, before set-state)
      3. ``consolidation.py``      — sleep pass (pre-classification)

    Any new call to ``ecs.decay_all`` (or to ``decay.decay_value``) outside
    those three modules — or a fourth call inside any sanctioned module —
    constitutes spec-level surprise and must be escalated per §9, not
    silenced by adjusting the assertion. Regression for review finding
    ``test-L1-decay-fourth-callsite-test-missing``.
    """

    SANCTIONED_MODULES: frozenset[str] = frozenset(
        {"api.py", "attention_log.py", "consolidation.py"}
    )

    def _decay_invocations(self) -> list[tuple[str, int, str]]:
        """Walk every module under src/moneta/ and return (file, line, callee)
        for each call to ``decay_all`` or ``decay_value``.

        Implementation files (``ecs.py``, ``decay.py``) are excluded — they
        host the decay machinery; only *callers* count toward the §16 limit.
        """
        import ast
        from pathlib import Path

        import moneta

        moneta_root = Path(moneta.__file__).parent
        sites: list[tuple[str, int, str]] = []
        for py in sorted(moneta_root.glob("*.py")):
            if py.name in {"ecs.py", "decay.py", "__init__.py"}:
                continue
            source = py.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # Match attribute calls: ``ecs.decay_all(...)`` /
                # ``decay_value(...)`` (rare; bare-name fallback).
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                else:
                    continue
                if name in {"decay_all", "decay_value"}:
                    sites.append((py.name, node.lineno, name))
        return sites

    def test_decay_call_sites_count_exactly_three(self) -> None:
        sites = self._decay_invocations()
        assert len(sites) == 3, (
            "ARCHITECTURE.md §16 locks 'exactly three' decay evaluation "
            f"points; found {len(sites)} call site(s) outside ecs.py/decay.py: "
            f"{sites!r}. A fourth site is §9 Trigger 2 (spec-level surprise), "
            f"not a local fix."
        )

    def test_decay_call_sites_in_sanctioned_modules_only(self) -> None:
        sites = self._decay_invocations()
        offending = [s for s in sites if s[0] not in self.SANCTIONED_MODULES]
        assert offending == [], (
            f"decay called from non-sanctioned module(s): {offending!r}. "
            f"Sanctioned: {sorted(self.SANCTIONED_MODULES)}. Adding a new "
            f"site is §9 Trigger 2, not a local fix."
        )
