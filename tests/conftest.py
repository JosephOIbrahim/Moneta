"""Shared pytest fixtures for Moneta unit and integration tests.

Owned by Test Engineer per MONETA.md §6 Role 5. Per the singleton
surgery (DEEP_THINK_BRIEF_substrate_handle.md), each test that needs a
live substrate takes the ``fresh_moneta`` fixture which yields a fully
constructed :class:`Moneta` handle. The fixture's ``with`` block
guarantees the URI lock is released on teardown so subsequent tests can
re-acquire freely.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from moneta import Moneta, MonetaConfig


@pytest.fixture
def fresh_moneta() -> Iterator[Moneta]:
    """Yield a freshly-constructed in-memory Moneta handle, closed on teardown.

    Each call generates a unique ``storage_uri`` via
    :meth:`MonetaConfig.ephemeral`, so tests cannot collide on the
    process-level URI registry.
    """
    with Moneta(MonetaConfig.ephemeral()) as substrate:
        yield substrate
