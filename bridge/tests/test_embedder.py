"""Adversarial tests for the bridge embedder contract.

Test Engineer (Commandment #7): structurally separate from the
Bridge Engineer who wrote the impl. These tests target the locked
contract, not the impl details.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure `bridge/` is on the path regardless of how pytest is
# invoked (from repo root or from bridge/).
_BRIDGE_ROOT = Path(__file__).resolve().parents[1]
if str(_BRIDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_ROOT))


def test_embedder_module_imports_without_sentence_transformers() -> None:
    """The bridge module must be importable without sentence-transformers
    installed. Lazy-import discipline is part of the contract."""
    from moneta_bridge import Embedder, SentenceTransformersEmbedder

    assert Embedder is not None
    assert SentenceTransformersEmbedder is not None


def test_default_embedder_constructs_and_reports_384_dim() -> None:
    pytest.importorskip("sentence_transformers")
    from moneta_bridge import SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder()
    assert e.dim == 384


def test_embed_returns_list_of_float_length_384() -> None:
    pytest.importorskip("sentence_transformers")
    from moneta_bridge import SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder()
    result = e.embed("hello world")

    assert isinstance(result, list)
    assert len(result) == 384
    for x in result:
        assert isinstance(x, float)


def test_embed_batch_returns_correct_shape() -> None:
    pytest.importorskip("sentence_transformers")
    from moneta_bridge import SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder()
    result = e.embed_batch(["a", "b", "c"])

    assert isinstance(result, list)
    assert len(result) == 3
    for row in result:
        assert isinstance(row, list)
        assert len(row) == 384
        for x in row:
            assert isinstance(x, float)


def test_embeddings_are_l2_normalized() -> None:
    pytest.importorskip("sentence_transformers")
    from moneta_bridge import SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder()
    vec = e.embed("normalization test")
    norm_sq = sum(x * x for x in vec)
    assert abs(norm_sq - 1.0) < 1e-3, (
        f"expected L2-normalized embedding (norm^2 ~= 1.0), "
        f"got norm^2 = {norm_sq}"
    )


def test_protocol_runtime_checkable_or_structural_match() -> None:
    pytest.importorskip("sentence_transformers")
    from moneta_bridge import Embedder, SentenceTransformersEmbedder

    e = SentenceTransformersEmbedder()
    try:
        assert isinstance(e, Embedder)
    except TypeError:
        # Non-runtime_checkable Protocol — fall back to structural check.
        assert hasattr(e, "dim")
        assert hasattr(e, "embed")
        assert hasattr(e, "embed_batch")
