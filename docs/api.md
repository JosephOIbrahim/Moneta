# Moneta four-op API reference

This document describes the four agent-facing operations exposed by the
`Moneta` handle (ARCHITECTURE.md §2). The signatures are verbatim from
MONETA.md §2.1 and are the locked interface — changes require §9
escalation.

This doc reflects the **v1.1.0+ handle API**. Pre-v1.1.0 module-level
calls (`moneta.init()`, `moneta.deposit(...)`) are gone — see
`SURGERY_complete.md` for the singleton → handle migration record.

## Imports

```python
import moneta
from moneta import (
    Moneta,
    MonetaConfig,
    Memory,
    EntityState,
    MonetaResourceLockedError,
    ProtectedQuotaExceededError,
)
```

`smoke_check` is also exported as a harness-level diagnostic — it is not
part of the agent surface.

## Setup — the `Moneta` handle

Every Moneta consumer constructs a handle from a `MonetaConfig` and
holds it for the lifetime of its substrate boundary:

```python
import moneta

# Test / ephemeral usage — auto-generated unique storage_uri
with moneta.Moneta(moneta.MonetaConfig.ephemeral()) as m:
    ...

# Production / explicit storage boundary
config = moneta.MonetaConfig(
    storage_uri="moneta-local:///var/moneta/agent-a",
    half_life_seconds=3600,
    snapshot_path=Path("/var/moneta/ecs.json"),
    wal_path=Path("/var/moneta/wal.jsonl"),
    use_real_usd=True,
    usd_target_path=Path("/var/moneta/cortex"),
)
with moneta.Moneta(config) as m:
    ...
```

`Moneta()` (no args) raises `TypeError` by design — every consumer
declares its storage boundary on line one. There are no implicit
defaults (Round 3 §5.3 ruling).

Two handles on the same `storage_uri` raise `MonetaResourceLockedError`
synchronously at the second constructor call. The collision check is
in-memory (`_ACTIVE_URIS` set), not file-locks. Different `storage_uri`
values yield physically distinct substrates — see
[Multi-instance](#multi-instance) below.

## The four operations

### `deposit(payload, embedding, protected_floor=0.0) -> UUID`

Deposit a new memory. Returns a newly minted `EntityID` (UUID).

```python
eid = m.deposit(
    payload="The user prefers concise explanations.",
    embedding=[0.12, -0.45, 0.78, ...],  # from your embedder
    protected_floor=0.0,                 # 0.0 = ephemeral, >0 = pinned
)
```

Fresh memories start at `Utility = 1.0` (Phase 1 convention, Pass 2
judgment call #2). If `protected_floor > 0.0` and the handle already
holds `config.quota_override` protected memories (default 100), `deposit`
raises `ProtectedQuotaExceededError`. The quota is per-handle in v1.1.0+
(it was a module-level constant in the singleton era).

### `query(embedding, limit=5) -> List[Memory]`

Retrieve the top-k memories most relevant to `embedding`. The retrieval
flow is:

1. Decay all live entities (ARCHITECTURE.md §4 eval point 1)
2. Fetch from the shadow vector index (cosine similarity)
3. Rerank by `max(cosine_similarity, 0) × utility` so decayed memories are
   naturally demoted. Equal scores keep the index's order (cosine
   descending, then insertion order). The rerank stops early once no
   remaining hit can enter the top `limit`; the result is identical to
   ranking every hit.
4. Return the top `limit` `Memory` objects (only those are projected)

**Performance (optional native seams).** With the `moneta_native` wheel
installed, steps 1 and 2 run in Rust. They are bit-identical to the Python
path, which stays the oracle. Measured on the owner's workstation at
10k memories × 384 dims, N=200 queries (`results/bench_query_fair_matrix.jsonl`):

- Pure Python: p95 227–313 ms, about 185 MB resident.
- Native: p95 3.1–6.7 ms, about 69 MB resident.

`MONETA_NATIVE=0` forces the pure-Python path.

```python
results = m.query(embedding=[0.12, -0.45, 0.78, ...], limit=5)
for memory in results:
    print(memory.payload, memory.utility, memory.attended_count)
```

### `signal_attention(weights) -> None`

Register agent attention for one or more entities. This is an
**append-only log write** — the ECS is not updated synchronously
(ARCHITECTURE.md §5.1). Updates apply at the sleep pass.

```python
m.signal_attention({
    eid_a: 0.3,
    eid_b: 0.1,
})
```

If durability is enabled (`snapshot_path` + `wal_path` set on the
config), each signal is also appended to the WAL and flushed to the OS
before return. The WAL is not fsync'd: a flushed signal survives a
process `kill -9`, but an OS crash or power loss can lose recently
acknowledged signals (Round 4 F1).

### `get_consolidation_manifest() -> List[Memory]`

Return every memory currently in `STAGED_FOR_SYNC` state — i.e.
memories that a sleep pass has selected for USD authoring but not yet
committed. Phase 3 also surfaces the intended USD target sublayer via
`Memory.usd_link` once authored.

```python
pending = m.get_consolidation_manifest()
print(f"{len(pending)} memories pending USD commit")
```

## Harness-level operator

### `run_sleep_pass() -> SleepPassResult`

Drains the attention log, applies decay (eval points 2 + 3), classifies
volatile entities (prune / stage / keep), executes sequential writes for
staged batches (≤ 500 prims per batch). Returns counts of pruned and
staged entities for the pass.

```python
result = m.run_sleep_pass()
print(f"pruned={result.pruned} staged={result.staged}")
```

`run_sleep_pass()` is the harness's lever — it is not one of the four
agent operations and is not part of the locked agent surface.

## `Memory` type (ARCHITECTURE.md §3)

```python
@dataclass(frozen=True)
class Memory:
    entity_id: UUID
    payload: str
    semantic_vector: list[float]   # snake_case of SemanticVector
    utility: float                 # [0.0, 1.0], decay target
    attended_count: int            # cumulative reinforcement
    protected_floor: float         # decay floor
    last_evaluated: float          # wall-clock unix seconds
    state: EntityState             # VOLATILE / STAGED_FOR_SYNC / CONSOLIDATED
    usd_link: Optional[object] = None  # Phase 3: SdfPath when consolidated
```

Frozen — mutations flow through `signal_attention`, never through this
object.

## `EntityState` lifecycle

```
VOLATILE         — fresh deposit, fully in hot tier
  ↓
STAGED_FOR_SYNC  — Consolidation has selected for USD authoring
  ↓
CONSOLIDATED     — successfully authored to disk; in hot tier until pruned
```

There is no `PRUNED` member — pruned entities are removed from the ECS
and the vector index outright. The codeless schema reserves a `"pruned"`
token in `priorState` `allowedTokens` for forward use, but no current
code path produces it.

## Multi-instance

`v1.1.0` lifted the singleton constraint — N substrates per Python
process is now first-class:

```python
# Two agents in the same process, each with its own substrate
with moneta.Moneta(moneta.MonetaConfig(storage_uri="moneta-local:///agent-a")) as m_a, \
     moneta.Moneta(moneta.MonetaConfig(storage_uri="moneta-local:///agent-b")) as m_b:
    m_a.deposit(...)   # invisible to m_b
    m_b.deposit(...)   # invisible to m_a
```

Each handle owns its own `ecs`, `attention`, `vector_index`, and
`authoring_target` — they are physically distinct objects. A
protected-quota slot consumed in `m_a` does not consume `m_b`'s quota.
Tests covering multi-instance: `tests/test_twin_substrate.py` and
`tests/test_twin_substrate_adversarial.py`.

## Durability guarantees

Moneta's durability model is WAL-lite + periodic snapshot, per the
MONETA.md §5 risk #4 mitigation. The target is: survive `kill -9` with
at most ~30 seconds of volatile state lost.

### Coverage by operation

| Operation | Durability coverage | Medium |
|---|---|---|
| `deposit` | Snapshot-covered | Captured by the next `run_sleep_pass` that writes the ECS snapshot |
| `signal_attention` | WAL-covered | Every call appended to the JSONL WAL and flushed to the OS (not fsync'd) when durability is enabled |
| `query` | Not applicable (read-only) | — |
| `get_consolidation_manifest` | Not applicable (read-only) | — |

### The volatility window

Deposits made after the last successful snapshot and before a `kill -9`
are **lost** on restart. The window width is whatever wall-clock time
elapsed since the last `run_sleep_pass` (sleep-pass-driven cadence) or
~30 seconds (background-snapshot cadence).

This is a deliberately accepted risk: signals (high-frequency, cheap)
survive process death via the flushed WAL (but not OS crash or power
loss, since the WAL is not fsync'd); deposits (low-frequency,
expensive) accept a small loss window. MONETA.md §5 risk #4
documents this trade-off as "WAL-lite periodic snapshot, accept
small volatility window."

### What happens on hydrate

When `Moneta(config)` is constructed with `snapshot_path` and `wal_path`
set on the config and those files exist on disk:

1. The latest snapshot is loaded into a fresh ECS.
2. The shadow vector index is rebuilt from the hydrated ECS rows — the
   vector index does not persist independently in v1.x; it is a pure
   shadow.
3. WAL entries with `timestamp > snapshot_created_at` are replayed into
   the attention log. They apply on the next `run_sleep_pass`.
4. Pre-snapshot WAL entries are filtered out (they are already captured
   by the snapshot).

If no snapshot exists (cold start, or `kill -9` before the first
successful pass), construction returns an empty ECS.

## Runtime requirements

- **Python ≥ 3.11** — required by `pyproject.toml`.
- **CPython with the GIL enabled** — `AttentionLog.__init__` raises
  `RuntimeError` on free-threaded interpreters (PEP 703). The lock-free
  swap-and-drain correctness argument depends on the GIL; the guard
  converts a silent correctness failure into a loud construction-time
  error. Verified by `tests/test_attention_log_gil_guard.py`. A
  free-threaded port is carried forward to a future surgery — track via
  MONETA.md §9 Trigger 2.
- **OpenUSD 0.25.5 (`pxr` Python bindings)** — required only when
  `MonetaConfig.use_real_usd=True`. Without `pxr`, the `MockUsdTarget`
  fallback is selected and 7 pxr-gated tests skip rather than fail.
  Run pxr-gated tests under `hython` (or any pxr-capable interpreter).
- **`moneta_native` (optional)**: an abi3 wheel built from
  `rust/moneta_native` that serves Python 3.11+, hython included. It is
  never required. See CLAUDE.md, "Optional native seams".
- **Codeless schema registration** — for typed-prim recognition in
  `usdview` and downstream consumers, set
  `PXR_PLUGINPATH_NAME=path/to/Moneta/schema` before launching. The
  schema is otherwise schema-blind on write but unrecognized on read.

## Errors

- `MonetaResourceLockedError` — raised when constructing a second
  handle on a `storage_uri` that is already held by a live handle in
  the same process. Subclass of `RuntimeError`.
- `ProtectedQuotaExceededError` — raised when a protected `deposit`
  (`protected_floor > 0`) would exceed `config.quota_override`
  (default 100). Subclass of `RuntimeError`.
- `TypeError` — raised by `Moneta()` (no args) and by any `deposit` /
  `query` / `signal_attention` call with a missing required argument.

## Example: minimal end-to-end

```python
import moneta

with moneta.Moneta(moneta.MonetaConfig.ephemeral()) as m:
    eid = m.deposit("hello world", [1.0, 0.0, 0.0])
    results = m.query([1.0, 0.0, 0.0], limit=5)
    assert results[0].entity_id == eid

    m.signal_attention({eid: 0.5})

    # A sleep pass applies the attention and runs selection.
    result = m.run_sleep_pass()
    print(f"pruned={result.pruned} staged={result.staged}")

    print(m.get_consolidation_manifest())  # [] — single fresh memory, not staged
```

`smoke_check()` in `src/moneta/api.py` exercises the full canonical
flow end-to-end and is the lowest-friction way to sanity-check after a
change. It is NOT a substitute for the test suite.

## Related docs

- `ARCHITECTURE.md` — locked spec
- `MONETA.md` — blueprint (phasing, lineage, risks)
- `docs/decay-tuning.md` — λ tuning guide
- `docs/substrate-conventions.md` — shared conventions with Octavius
- `SURGERY_complete.md` — `v1.1.0` singleton → handle migration record
- `SURGERY_complete_codeless_schema.md` — `v1.2.0-rc1` codeless schema migration
