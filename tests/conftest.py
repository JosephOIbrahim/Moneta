"""Shared pytest fixtures for Moneta unit and integration tests.

Owned by Test Engineer per MONETA.md §6 Role 5. Keeps fixtures small and
scope-explicit; fixtures that reach into private module state live here
so individual test files can stay focused on their clause coverage.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

import moneta
from moneta import api as moneta_api


@pytest.fixture
def fresh_moneta() -> Iterator[None]:
    """Initialize Moneta with in-memory defaults, reset on teardown.

    Each test that needs a live substrate takes this fixture. The reset
    uses the private `_reset_state` hook so tests cannot leak state
    across runs. `moneta.init()` is called inside the fixture so tests
    see a clean substrate on entry.
    """
    moneta_api._reset_state()
    moneta.init()
    try:
        yield
    finally:
        moneta_api._reset_state()


@pytest.fixture
def uninitialized_moneta() -> Iterator[None]:
    """Ensure the substrate is uninitialized for the duration of a test.

    Used by contract tests that assert `MonetaNotInitializedError` is
    raised when ops are called before `init()`.
    """
    moneta_api._reset_state()
    try:
        yield
    finally:
        moneta_api._reset_state()
