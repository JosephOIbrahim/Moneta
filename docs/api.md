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
    # Native seams (optional moneta_native wheel)
    NativeConfigError,
    NativeUnavailableError,
    NativeSeamError,
    NativeStatus,
    SeamStatus,
    NativeWheel,
    build_info,
    BuildInfo,
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

Under native mode `require` (see [Native seams](#native-seams-config-and-status)),
`deposit` first checks `embedding` against the native envelope: finite,
numeric, non-empty, and the index's dimension. Outside it, `deposit`
raises `NativeSeamError` before any mutation: no ECS row, no index row,
no WAL line, no attention change. In auto and off modes the check is a
no-op, and the signature and return type are unchanged in every mode.

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

`MONETA_NATIVE=0` (or `false`, `off`, `no`) forces the pure-Python path.
See [Native seams](#native-seams-config-and-status) for the full switch.

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

## Native seams: config and status

The optional `moneta_native` wheel runs the scan (`query` step 2) and the
decay pass in Rust, bit-identical to the Python oracles. Nothing here is
an agent operation; the four-op API is unchanged.

### `MonetaConfig.native`

`native: Optional[Literal["auto", "off", "require"]] = None`. Any other
value raises `ValueError` when the config is built. The handle combines it
with `MONETA_NATIVE` once, in `Moneta.__init__`, before the store lock is
taken.

`MONETA_NATIVE` is stripped and lower-cased, then classed:

| Class | Values |
|---|---|
| UNSET | variable not set |
| AUTO | `""`, `1`, `true`, `on`, `yes`, `auto` |
| OFF | `0`, `false`, `off`, `no` |
| REQUIRE | `require` |
| UNKNOWN | anything else (one `RuntimeWarning` per process; treated like AUTO) |

> **Behaviour change:** `false`, `off` and `no` used to mean native ON.
> They now mean OFF. `1` still means auto.

| config ↓ / env → | UNSET | AUTO | OFF | REQUIRE | UNKNOWN |
|---|---|---|---|---|---|
| `None` | auto (default) | auto (env) | off (env) | require (env) | auto (env, warns) |
| `"auto"` | auto (config) | auto (config) | **off (env kill switch)** | **require (env tightens)** | auto (config, warns) |
| `"off"` | off (config) | off (config) | off (config) | **`NativeConfigError`** | off (config, warns) |
| `"require"` | require (config) | require (config) | **`NativeConfigError`** | require (config) | require (config, warns) |

The word in parentheses is the recorded `requested_source`.

- **auto:** native when the wheel loads, otherwise Python, with the reason recorded.
- **off:** Python. The handle never imports `moneta_native`.
- **require:** native or an error. A wheel that is absent, broken or
  incompatible raises `NativeUnavailableError`. Under require, demotion is
  forbidden: an out-of-envelope `deposit`, an out-of-envelope stored vector
  at hydrate, and a native decay failure each raise `NativeSeamError`.
  Two per-query oracle answers are permitted and counted, because the
  answer is exact and the trigger is the query: `query_nonfinite` and
  `cosine_overflow`. Dim-mismatch and zero-norm queries return `[]` on
  both backends and are not fallbacks.

**v5 divergence:** `moneta.v5` is unchanged and still treats only
`MONETA_NATIVE=0` as off.

### `Moneta.native_status -> NativeStatus`

A read-only handle property, not an agent operation. Each access returns
a new frozen record.

```python
st = m.native_status
st.scan.active          # "native" | "python"
st.decay.native_calls   # Rust invocations so far
st.require_satisfied    # None unless the mode is require
```

| `NativeStatus` field | Meaning |
|---|---|
| `scan`, `decay` | `SeamStatus` for each seam |
| `wheel` | `NativeWheel` (process-wide probe result) |
| `source` | `moneta.build_info()` |
| `require_satisfied` | `None` unless require; then True only if both seams are active native, neither is demoted, and decay has 0 fallbacks (scan per-query fallbacks are allowed and listed) |

| `SeamStatus` field | Meaning |
|---|---|
| `seam` | `"scan"` or `"decay"` |
| `requested` | `auto`, `off` or `require` |
| `requested_source` | `config`, `env`, `default`, or `explicit` (a direct `ECS(native=…)` / `VectorIndex(backend=…)`) |
| `env_raw` | raw `MONETA_NATIVE`, or `None` |
| `active` | `native` or `python` |
| `reason` | why Python is active, else `None` |
| `demoted` | the component left native for good (auto only) |
| `native_calls` | Rust invocations, not queries: each `ScanIndex.scan` return (each window of one `iter_query` counts), each `decay_batch` return |
| `fallbacks` | `{reason: count}` of oracle runs by a component that was native at call time: `query_nonfinite`, `cosine_overflow`, `decay_error:<ExcType>`, `demoted:<reason>` |
| `all_native` | `active == "native"`, no fallbacks, not demoted |

| `NativeWheel` field | Meaning |
|---|---|
| `state` | `loaded`, `absent`, `broken`, `incompatible`, or `not_probed` (an off handle never probes) |
| `reason`, `version` | why not loaded; the wheel's `__version__` |
| `api` | `NATIVE_API`, or `None` for the legacy 0.1.0 wheel |
| `path`, `sha256` | the extension `.pyd` and its sha256 |
| `record_match` | `True`/`False` when the sha256 was compared with an adjacent dist-info `RECORD`, else `None` |
| `direct_url` | the wheel's `direct_url.json`, or `None` |

### `moneta.build_info() -> BuildInfo`

Frozen, stdlib only, no subprocess, cached per process. Fields: `path`,
`mode` (`git-src`, `editable`, `vcs`, `wheel`, `unknown`), `commit`,
`ref`, `dirty` (always `"unknown"`), `version`, `version_mismatch`,
`src_digest`, `python`.

`src_digest` is sha256 over the sorted relative POSIX paths of
`src/moneta/**/*.py` (no `__pycache__`), each fed as
`path + b"\0" + content` with CRLF normalized to LF, so one commit gives
one digest on any checkout.

**Verify a running process by `commit` + `src_digest` + the `.pyd`
sha256, never by version.** The version is `1.3.0rc1` on both rc1 and the
`harden/native-observability` branch. Measured runs on that branch and
how to read the suite's verdict line are in the README, "Optional native
seams (Rust)".

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

> **UNRESOLVED DEFECT (B and D): undrained attention is currently lost by
> a bare snapshot.** Step 4's premise holds for applied attention only.
> The snapshot holds ECS rows, not the undrained attention log, and every
> snapshot deletes the WAL. So a `signal_attention` that no sleep pass has
> applied yet is lost when a bare snapshot
> (`m.durability.snapshot_ecs(m.ecs)`) is followed by a restart (path B),
> or when it lands between a sleep pass's drain and that pass's snapshot
> (path D). This also limits the "signals survive process death via the
> flushed WAL" statement above. It is not fixed. Both paths are pinned as
> strict xfail in `tests/integration/test_attention_snapshot_regression.py`;
> the repair design is `docs/design/R1-attention-durability.md`.

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
  With the real target, reopening an existing `usd_target_path` keeps
  its authored sublayer stack, prim counts and opinions: an existing
  layer is opened, never re-created, and one that cannot be opened
  raises (ce45). A layer whose save fails (a `False` result or a raise)
  makes `run_sleep_pass` raise `moneta.usd_target.UsdSaveError` (a
  `RuntimeError`) before that batch's vector commit; the layer stays
  dirty and the next flush retries it. A store layer that something else
  in the process already loaded (a Houdini LOP network shares Sdf's
  layer registry) is logged at WARNING as `Sdf registry sharing`, and
  Moneta then authors into that shared layer; nothing is refused, and a
  holder that loads the layer later is not detected.
- **`moneta_native` (optional)**: an abi3 wheel built from
  `rust/moneta_native` that serves Python 3.11+, hython included. It is
  required only when a handle resolves to native mode `require`. See
  [Native seams](#native-seams-config-and-status) and CLAUDE.md,
  "Optional native seams".
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
- `NativeConfigError` — raised by `Moneta(config)` when `config.native`
  and `MONETA_NATIVE` conflict: `"require"` with an OFF env value, or
  `"off"` with `MONETA_NATIVE=require`. The message names both values.
  Subclass of `ValueError`.
- `NativeUnavailableError` — raised by `Moneta(config)` when the handle
  resolves to `require` and the wheel is absent, broken or incompatible.
  Names the wheel state and reason. Subclass of `RuntimeError`.
- `NativeSeamError` — native `require` only: an out-of-envelope `deposit`
  (nothing mutated), an out-of-envelope stored vector during hydrate (lock
  released, no file modified), or a native decay failure (columns
  unchanged; in a sleep pass no snapshot is written and the WAL keeps the
  signal). Subclass of `RuntimeError`.
- When any of the three is raised during construction, the `storage_uri`
  lock is released and no file is modified: the next construct on the
  same `storage_uri` succeeds.
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
