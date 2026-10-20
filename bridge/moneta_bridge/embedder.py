"""Embedder Protocol + default SentenceTransformersEmbedder.

The bridge does not assume Comfy-Cozy provides embeddings; the
default path is "bridge embeds the payload itself" using a local
sentence-transformers model.

Choice rationale (Architect-on-deck decision, locked):
- Offline: no API key, no network, no PII egress to a third party.
- Deterministic given a fixed model version + seed.
- 384-dim is cheap for cosine similarity in Moneta's vector index.
- The de facto standard in the agent-memory ecosystem
  (mem0, llama-index, langchain).

The Embedder Protocol allows callers to swap in any embedder without
patching bridge code — useful for offline/air-gapped deployments
that ship a different model, or for callers who want OpenAI / BGE
embeddings.

The sentence-transformers import is deferred to construction time so
this module is importable on machines that do not have
sentence-transformers installed (e.g., CI workers running pure-Python
tests against the Protocol shape).
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Contract for any embedder usable by the bridge.

    Implementations must:
      - Expose ``dim`` as the integer embedding dimensionality.
      - Implement ``embed(text)`` returning a ``List[float]`` of
        length ``dim``.
      - Implement ``embed_batch(texts)`` returning a list of
        vectors, each ``List[float]`` of length ``dim``.

    Embeddings should be L2-normalized so cosine similarity reduces
    to dot product (matches Moneta's vector_index expectations).
    """

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> List[float]: ...

    def embed_batch(self, texts: List[str]) -> List[List[float]]: ...


class SentenceTransformersEmbedder:
    """Default embedder: sentence-transformers/all-MiniLM-L6-v2.

    384-dim, L2-normalized. Lazy-imports sentence-transformers on
    construction so the module is importable without the dep.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> List[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec.tolist()]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        mat = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in row] for row in mat.tolist()]
