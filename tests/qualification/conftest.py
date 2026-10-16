"""Qualification-suite fixtures.

``tests/unit/native_fakes.py`` is a plain module beside the unit tests (no
package), so it is importable here only if ``tests/unit`` is on ``sys.path``
regardless of which directories were collected first.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from moneta import _native

_UNIT = str(Path(__file__).resolve().parent.parent / "unit")
if _UNIT not in sys.path:
    sys.path.insert(0, _UNIT)


@pytest.fixture
def real(monkeypatch):
    """Real-wheel runtime: no MONETA_NATIVE (config alone decides), fresh
    loader cache, ``sys.modules`` untouched (a PyO3 extension cannot be
    initialised twice in one process)."""
    monkeypatch.delenv("MONETA_NATIVE", raising=False)
    _native._reset_for_tests()
    yield monkeypatch
    _native._reset_for_tests()
