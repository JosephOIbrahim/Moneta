# moneta-bridge

External adapter package wiring Comfy-Cozy session emissions into the
Moneta substrate. Comfy-Cozy is "frozen as law" — zero edits to that
repo. All wiring lives here.

**Status:** v0.1.0a0 — codeless USD schema and embedder landed.
`ingest.py` and `egress.py` not yet implemented.

## Layout

- `moneta_bridge/embedder.py` — `Embedder` Protocol + default
  `SentenceTransformersEmbedder`.
- `schema/CozySchema.usda` — codeless USD schema for Comfy-Cozy
  emissions (`CozyRoom`, `CozyMemory`).
- `schema/plugInfo.json` — schema registration.
- `tests/` — unit tests.

See [`../docs/bridge-readiness.md`](../docs/bridge-readiness.md) for
the readiness assessment that scoped this package.

## Embedder

Default: `sentence-transformers/all-MiniLM-L6-v2`, 384-dim,
`normalize_embeddings=True`. Chosen because it is offline (no API
key, no PII egress), deterministic given a fixed model version,
small (~80MB RAM, 384-dim cheap for cosine), and the de facto
standard in the agent-memory ecosystem. The embedder is exposed
behind a `Protocol` so swapping is one line.

```python
from moneta_bridge import SentenceTransformersEmbedder

embedder = SentenceTransformersEmbedder()
vec = embedder.embed("the user prefers concise answers")
assert len(vec) == 384
```

## Usage with Moneta

```python
import moneta
from moneta_bridge import SentenceTransformersEmbedder

embedder = SentenceTransformersEmbedder()
with moneta.Moneta(moneta.MonetaConfig.ephemeral()) as m:
    text = "remember this fact"
    eid = m.deposit(text, embedder.embed(text))
    hits = m.query(embedder.embed("what do I know about facts?"))
```
