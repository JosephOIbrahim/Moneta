"""moneta-bridge — Comfy-Cozy <-> Moneta adapter package.

Re-exports the embedder Protocol and the default
SentenceTransformersEmbedder. The default embedder lazily imports
sentence-transformers at construction, so this module is importable
without sentence-transformers installed.
"""
from .embedder import Embedder, SentenceTransformersEmbedder

__all__ = ["Embedder", "SentenceTransformersEmbedder"]
