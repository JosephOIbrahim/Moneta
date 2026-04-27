"""Round-trip unit tests for ``_state_to_token`` / ``_token_to_state``.

``HANDOFF_codeless_schema_moneta.md`` §8.4. Standalone unit test for
the boundary helpers added in step 5 of the surgery. All
currently-extant ``EntityState`` members round-trip through
``_state_to_token`` and ``_token_to_state`` to identity; token strings
match the schema's ``allowedTokens`` list exactly.

The schema reserves ``"pruned"`` for a future PRUNED-as-tombstone
surgery; the substrate cannot author it today (no ``EntityState.PRUNED``
member). ``_token_to_state("pruned")`` raises ``ValueError`` rather
than silently returning a wrong state — the negative-space defense
mandated by constitution §7.

The helpers live in ``moneta.usd_target``, which imports ``pxr`` at
module load. The tests are therefore pxr-gated via ``importorskip``;
under plain Python the module is skipped cleanly.
"""
from __future__ import annotations

import pytest

pytest.importorskip(
    "pxr",
    reason=(
        "_state_to_token / _token_to_state live in moneta.usd_target; "
        "that module imports pxr at top-level"
    ),
)

from moneta.types import EntityState  # noqa: E402
from moneta.usd_target import (  # noqa: E402
    _STATE_TO_TOKEN,
    _TOKEN_TO_STATE,
    _state_to_token,
    _token_to_state,
)


# ``allowedTokens`` from MonetaSchema.usda. Anchored as test data so a
# schema drift here surfaces as a test failure with a clear diff.
_SCHEMA_ALLOWED_TOKENS = {
    "volatile",
    "staged_for_sync",
    "consolidated",
    "pruned",
}

# Tokens the substrate can produce today — the EntityState enum
# members map onto these via ``_state_to_token``. The remainder of
# ``_SCHEMA_ALLOWED_TOKENS`` is the reserved set.
_SUBSTRATE_PRODUCIBLE_TOKENS = {
    "volatile",
    "staged_for_sync",
    "consolidated",
}
_SCHEMA_RESERVED_TOKENS = (
    _SCHEMA_ALLOWED_TOKENS - _SUBSTRATE_PRODUCIBLE_TOKENS
)


class TestStateTokenRoundTrip:
    """The four sub-tests below collectively cover every cell of the
    ``_STATE_TO_TOKEN`` / ``_TOKEN_TO_STATE`` table plus the
    negative-space (reserved + truly unknown tokens)."""

    # ------------------------------------------------------------------
    # Positive — every extant state and producible token round-trips
    # ------------------------------------------------------------------

    def test_state_to_token_keys_match_extant_entity_state(self) -> None:
        """``_STATE_TO_TOKEN`` keys are exactly the live ``EntityState``
        members. If the enum gains a new member without a corresponding
        token, this test fires."""
        assert set(_STATE_TO_TOKEN.keys()) == set(EntityState)

    def test_state_to_token_values_match_substrate_producible_set(
        self,
    ) -> None:
        assert (
            set(_STATE_TO_TOKEN.values()) == _SUBSTRATE_PRODUCIBLE_TOKENS
        )

    def test_each_state_round_trips_through_helpers(self) -> None:
        for state in EntityState:
            token = _state_to_token(state)
            recovered = _token_to_state(token)
            assert recovered == state, (
                f"round-trip failed for {state!r}: "
                f"token={token!r}, recovered={recovered!r}"
            )

    def test_each_producible_token_round_trips_through_helpers(
        self,
    ) -> None:
        for token in _SUBSTRATE_PRODUCIBLE_TOKENS:
            state = _token_to_state(token)
            recovered = _state_to_token(state)
            assert recovered == token, (
                f"round-trip failed for token {token!r}: "
                f"state={state!r}, recovered={recovered!r}"
            )

    def test_state_token_table_is_exact_inverse(self) -> None:
        for state, token in _STATE_TO_TOKEN.items():
            assert _TOKEN_TO_STATE[token] == state, (
                f"_TOKEN_TO_STATE[{token!r}] = "
                f"{_TOKEN_TO_STATE[token]!r}, expected {state!r}"
            )
        assert len(_TOKEN_TO_STATE) == len(_STATE_TO_TOKEN), (
            f"table sizes diverge: STATE_TO_TOKEN has "
            f"{len(_STATE_TO_TOKEN)}, TOKEN_TO_STATE has "
            f"{len(_TOKEN_TO_STATE)}"
        )

    # ------------------------------------------------------------------
    # Substantive token-string anchoring — protects against silent
    # rename of any token value (which would corrupt on-disk stages).
    # ------------------------------------------------------------------

    def test_volatile_maps_to_literal_volatile(self) -> None:
        assert _state_to_token(EntityState.VOLATILE) == "volatile"

    def test_staged_for_sync_maps_to_literal_staged_for_sync(
        self,
    ) -> None:
        assert (
            _state_to_token(EntityState.STAGED_FOR_SYNC)
            == "staged_for_sync"
        )

    def test_consolidated_maps_to_literal_consolidated(self) -> None:
        assert (
            _state_to_token(EntityState.CONSOLIDATED) == "consolidated"
        )

    # ------------------------------------------------------------------
    # Negative-space — reserved + unknown tokens raise loudly
    # ------------------------------------------------------------------

    def test_reserved_pruned_token_raises_on_resolution(self) -> None:
        """The schema reserves ``"pruned"`` but ``EntityState`` has no
        ``PRUNED`` member; ``_token_to_state`` must raise rather than
        silently return a wrong state."""
        for token in _SCHEMA_RESERVED_TOKENS:
            with pytest.raises(
                ValueError, match="unknown priorState token"
            ):
                _token_to_state(token)

    def test_unknown_token_raises_with_useful_diagnostic(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            _token_to_state("garbage")
        msg = str(exc_info.value)
        assert "garbage" in msg, (
            "diagnostic must echo the offending token"
        )
        assert "expected one of" in msg, (
            "diagnostic must list the valid tokens"
        )

    def test_empty_string_raises(self) -> None:
        """A read-back of an unauthored token attribute returns ''. The
        helper must raise rather than silently treat it as ``volatile``
        or any other state."""
        with pytest.raises(ValueError):
            _token_to_state("")
