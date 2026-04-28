"""Test for the free-threading guard in AttentionLog.__init__.

Drop this into the existing tests/test_attention_log.py (or wherever
attention log tests live in Moneta's suite). It validates the runtime
GIL invariant added per MONETA.md §9 Trigger 2.
"""
import sys

import pytest

from moneta.attention_log import AttentionLog  # adjust import path to match repo


def test_attention_log_constructs_under_gil():
    """Sanity: with the GIL enabled (default CPython), construction succeeds."""
    log = AttentionLog()
    assert len(log) == 0


def test_attention_log_refuses_free_threaded_python(monkeypatch):
    """Under simulated free-threaded Python, AttentionLog must refuse to construct.

    PEP 703 free-threading invalidates the lock-free swap-and-drain
    correctness argument (module docstring). The guard converts a silent
    correctness failure into a loud RuntimeError at construction time.
    """
    # Simulate free-threaded interpreter by forcing _is_gil_enabled() -> False.
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False, raising=False)

    with pytest.raises(RuntimeError, match="GIL"):
        AttentionLog()
