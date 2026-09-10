# Bridge readiness assessment (Moneta ↔ Comfy-Cozy)

**Status:** Authored 2026-05-03. Reflects Moneta v1.2.0rc1 (`pyproject.toml:version`, commit 9a46293). Doc artifact promoted from `/root/.claude/plans/`.

## Context

Joseph is scoping an external bridge to wire Moneta into Comfy-Cozy.
Comfy-Cozy is "frozen as law" — no edits to that repo. All wiring lives
Moneta-side or in a separate bridge package. Before scoping bridge
work, this document confirms what Moneta v1.x exposes today, and where
the gaps are between "current Moneta" and "Moneta consumable by a
Comfy-Cozy bridge daemon." Read-only investigation; nothing was
modified. Below is the 6-part assessment requested.

---

## 1. PUBLIC API SURFACE

The handle is `moneta.Moneta`, constructed with a single
`MonetaConfig` (frozen dataclass). Both are re-exported at package
root from `src/moneta/__init__.py:9-15`. Construction without args is
intentionally a `TypeError` (`src/moneta/api.py:190-193`); the
canonical pattern is `with Moneta(MonetaConfig.ephemeral()) as m:`
(`README.md:18-26`, `src/moneta/api.py:480-524` smoke_check). The four
agent-facing ops, signatures verbatim from
`src/moneta/api.py:328-446`:

```python
def deposit(self, payload: str, embedding: List[float],
            protected_floor: float = 0.0) -> UUID                # 328-377
def query(self, embedding: List[float],
          limit: int = 5) -> List[Memory]                        # 379-417
def signal_attention(self, weights: Dict[UUID, float]) -> None   # 419-436
def get_consolidation_manifest(self) -> List[Memory]             # 438-446
```

The sleep-pass / consolidation trigger is harness-level (not part of
the four-op spec, per ARCHITECTURE.md §2.1) and exposed as
`Moneta.run_sleep_pass(self) -> ConsolidationResult`
(`src/moneta/api.py:452-472`), delegating to
`ConsolidationRunner.run_pass(...)`
(`src/moneta/consolidation.py:124-132`).

## 2. EMBEDDING ASSUMPTION

Caller-provided. `deposit(payload, embedding, ...)` takes a
pre-computed `List[float]`; there is no internal embedder anywhere in
`src/moneta/`. Dimensionality is configurable via
`MonetaConfig.embedding_dim` (`src/moneta/api.py:130`,
`src/moneta/vector_index.py:74`) but optional: if unset, the first
`deposit` infers `_dim` from `len(vector)`
(`src/moneta/vector_index.py:109`); subsequent deposits with a
different length raise `ValueError`
(`src/moneta/vector_index.py:110-113`). The contract is documented in
the deposit docstring and README, but there is no canonical "use
embedder X" guidance — the bridge owns embedding choice.

## 3. USD INGESTION PATH

**None.** There is zero code path today that consumes an
externally-authored `.usda` file. No `from_usda`, `import_stage`,
`ingest`, or `load` helper exists in `src/moneta/api.py`,
`src/moneta/usd_target.py`, or `src/moneta/consolidation.py`. The only
`Sdf.Layer.FindOrOpen` / `Usd.Stage.Open` calls are at
`src/moneta/usd_target.py:222,224,246`, and they construct/recover
**Moneta's own** root and sublayers — they never read caller-supplied
stages. ARCHITECTURE.md §8 acknowledges a future `UsdLink` field for
hydrated entities but defers it (CLAUDE.md "non-goals" still lists
"Cross-session USD hydration at cold start"). A consumer handing
Moneta a `.usda` today must parse it themselves and call `deposit()`
per entity.

## 4. USD HYDRATION PATH

Partial, and not via `query`. Moneta authors `.usda` files only as a
side effect of `run_sleep_pass()` → `SequentialWriter.commit_staging`
→ `UsdTarget.author_stage_batch` + `flush`
(`src/moneta/usd_target.py:290-367`). Output is a fixed sublayer
structure rooted at `{log_path}/cortex_root.usda` with
`cortex_protected.usda` at strongest position and rolling
`cortex_YYYY_MM_DD[_NNN].usda` sublayers
(`src/moneta/usd_target.py:218-281`). Each memory is a `MonetaMemory`
prim at `/Memory_{hex}` carrying `payload`, `utility`,
`attendedCount`, `protectedFloor`, `lastEvaluated`, `priorState`
(`schema/MonetaSchema.usda:18-57`,
`src/moneta/usd_target.py:79-84,164-166,319`). `query()` itself
returns `List[Memory]` (Python objects), not a stage and not a
`.usda` file (`src/moneta/api.py:379-417`); there is no
`to_usda` / `serialize_to_usd` / `export_query` helper. Closest
existing capability for an external USD consumer: open
`cortex_root.usda` directly and traverse — the schema is documented
at `docs/substrate-conventions.md:23-99` and
`ARCHITECTURE.md:257-280`, but there is no consumer-facing
"query → ad-hoc usda" path.

## 5. CONCURRENCY / LIFECYCLE

Designed for long-running handles, **single-process only**. A handle
holds ECS, attention log, vector index, durability manager,
sequential writer, and authoring target for its full lifetime
(`src/moneta/api.py:195-287`); `close()` is idempotent and ordered
(`api.py:300-320`). Daemon restart is supported when
`MonetaConfig.snapshot_path` and `wal_path` are set — `__init__`
calls `DurabilityManager.hydrate()` to load snapshot + replay WAL
entries newer than the snapshot timestamp
(`src/moneta/api.py:220-247`,
`src/moneta/durability.py:181-225`). **Critical constraint:** the
exclusivity guard is an in-process Python set,
`_ACTIVE_URIS: set[str]` (`src/moneta/api.py:169,198-204`), with no
`fcntl`/`flock`/lockfile — a second OS process pointed at the same
`storage_uri` is **not** prevented and will silently corrupt state.
WAL writes are guarded by an internal `threading.Lock`
(`src/moneta/durability.py:75,147-149`); the attention log is
GIL-atomic lock-free
(`src/moneta/attention_log.py:63,72`); the USD writer takes a narrow
lock scoped to `Sdf.ChangeBlock` only
(`src/moneta/usd_target.py:314`, ARCHITECTURE.md §15.6). Sleep-pass
must be single-reducer (`src/moneta/attention_log.py:27-32`). For the
bridge: one daemon process holding one `Moneta` handle is fine; two
processes touching the same store is not.

## 6. WHAT'S MISSING

For a Comfy-Cozy bridge that (a) watches `.usda` session flushes,
(b) feeds them into Moneta, and (c) hands query results back as USD,
three concrete gaps exist:

1. **No USD ingestion at all** (§3). The bridge must own .usda
   parsing — open the stage, walk prims, extract whatever
   Comfy-Cozy's prim schema is, generate `(payload, embedding)`
   pairs, and call `deposit()` per entity. Moneta provides nothing
   here. If the bridge wants a "feed me a .usda path" entry point,
   it has to be built (likely bridge-side, since it's
   Comfy-Cozy-schema-specific, not Moneta-generic).

2. **No `query → .usda` egress** (§4). The bridge can read
   `cortex_root.usda` directly (schema is stable and documented),
   or it can call `query()` and synthesize a `.usda` from the
   returned `List[Memory]`. Moneta does not export query results
   as a stage. If Comfy-Cozy expects "give me a .usda of relevant
   memories," the bridge must serialize.

3. **No inter-process lock** (§5). `_ACTIVE_URIS` is in-memory.
   If the bridge architecture might ever have two processes (a
   watcher + a query server, say) pointed at the same store, the
   bridge needs to enforce single-process discipline itself
   (lockfile, supervisor, OS-level mutex), or this becomes a
   §9-Trigger-2 surprise the first time it ships.

Embedding is **not** a gap — it's an explicit caller responsibility,
documented; the bridge picks an embedder. Daemon lifecycle is **not**
a gap — `DurabilityManager.hydrate()` covers restart.

Net: Moneta's four-op surface is consumable as-is from a single
daemon process. The bridge work is real but bounded: a USD-side
adapter (parse Comfy-Cozy `.usda` → deposits; serialize query
results → `.usda`) plus a process-level lock guard. Nothing inside
Moneta needs to change for a v1 bridge unless the bridge wants USD
ingestion to live Moneta-side, which would re-open Phase 1
non-goals and likely warrant a §9 escalation.

---

## Verification

To validate the claims above end-to-end:

```bash
# Confirm public API + four-op flow
python -c "import moneta; moneta.smoke_check(); print('OK')"

# Confirm restart story
pytest tests/integration/test_durability_roundtrip.py -v

# Confirm USD authoring shape (requires pxr-capable interpreter)
pytest tests/integration/test_real_usd_end_to_end.py -v

# Inspect what Moneta writes to disk:
python -c "
import moneta, tempfile, pathlib
with tempfile.TemporaryDirectory() as d:
    cfg = moneta.MonetaConfig.ephemeral()  # mock target
    # for real USD: pass use_real_usd=True, usd_target_path=pathlib.Path(d)
    ...
"
# Then ls {log_path}/cortex_*.usda to see the sublayer structure
# described in §4.
```

No file in `src/moneta/` was modified during this investigation.

---

## Documentation drift flagged

This audit surfaced version drift between `CLAUDE.md` and the actual
codebase. Recording for the next Documentarian pass:

- **`CLAUDE.md` declares "v1.0.0 shipped. All three phases complete."** and frames Phase 3 as recently closed.
- **`pyproject.toml` declares `version = "1.2.0rc1"`,** with a "codeless schema" surgery between v1.0.0 and current (commits `9a46293`, `8eb0956`, `41d5385`, `f7b6253`).
- The Documentarian contract per `CLAUDE.md` ("do not let documentation lag implementation by more than one PR") is currently at risk.
- **Recommendation:** a follow-up Documentarian pass should update `CLAUDE.md` to reflect v1.2.0rc1 reality — including the codeless-schema surgery, the current schema layout at `schema/MonetaSchema.usda`, and any Phase-3-onwards changes that landed since v1.0.0. **Out of scope for this assessment** — flagging only.
