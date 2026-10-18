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

Two live handles on the same `storage_uri` raise
`MonetaResourceLockedError` synchronously at the second constructor call.
So do two live durable handles whose store files coincide, even under
different `storage_uri` values. A handle's store files are the resolved
`snapshot_path`, `wal_path` and their two tmp files (each the same path
plus `.tmp`). A config whose own four store paths are not pairwise
distinct (for example `snapshot_path == wal_path`) raises `ValueError`.
Both checks are in-memory (the `_ACTIVE_URIS` and `_ACTIVE_STORE_PATHS`
sets), not file locks, so they cover one process only; two processes on
one store are unsupported. Different `storage_uri` values with distinct
store files yield physically distinct substrates — see
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
config), each signal's WAL line is written **first**, as one unbuffered
write that is fsync'd before return, and only then appended to the
attention log (Round 4 F1; gate 2 tier: fsync every append, about 1.2 ms
per line on the seat box). A returned signal survives a process
`kill -9`, an OS crash and a power loss, with one Windows caveat around
saves (see [Durability guarantees](#durability-guarantees)). A failed
fsync rejects the signal exactly like a failed write: the `OSError`
escapes and no line is left behind. The line stays in the WAL until a
save records the signal as applied.

**Behaviour change (R1′).** rc1 buffered the signal first and wrote the
WAL second. The signature, return type and exception types are
unchanged.

- **The WAL write fails:** the signal is now in **neither** place, and
  the same `OSError` escapes, so a caller that retries is not
  double-counted. In rc1 the signal was already applied in memory, and a
  line left in the buffer by a failed flush could still reach the file
  later and replay on reopen.
- **The call is interrupted after the WAL write** (for example by
  `KeyboardInterrupt`): the line's seq is tombstoned, so no reopen after
  the next save replays it. A crash before that save replays it once.
  Narrow windows remain in which an interrupted call still applies once
  at the next reopen; `docs/design/R1-attention-durability.md` §1.4
  describes them.
- **A closed durable handle:** `signal_attention` raises
  `ValueError("durability manager is closed")` and buffers nothing. A
  handle without durability is unchanged.
- For a multi-entity `weights` dict, the entities before a failing one
  stay recorded, as in rc1.

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

Run one sleep pass at a time; concurrent passes are unsupported, as in
rc1. A pass that finds another pass in flight logs ERROR (`concurrent
attention reducer ...`) and still drains and applies. It never raises
for this. On a durable handle the pass ends with a save, which raises
after its snapshot is written if WAL compaction fails (see
[Durability guarantees](#durability-guarantees)).

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
| `signal_attention` | WAL-covered | When durability is enabled, every call is written to the JSONL WAL before it is buffered (one unbuffered write, fsync'd before return; Round 4 F1). The line stays until a save records the signal as applied |
| `query` | Not applicable (read-only) | — |
| `get_consolidation_manifest` | Not applicable (read-only) | — |

### The volatility window

Deposits made after the last successful snapshot and before a `kill -9`
are **lost** on restart. The window width is whatever wall-clock time
elapsed since the last save: the end of the last `run_sleep_pass`, an
embedder's own `m.durability.snapshot_ecs(m.ecs)` (SYNAPSE's save), or
~30 seconds if the embedder started `m.durability.start_background(m.ecs)`.
`Moneta` never starts that background thread itself.

This is a deliberately accepted risk: signals (high-frequency, cheap)
survive process death via the WAL, and since Round 4 F1 an OS crash or
power loss too, because every append is fsync'd (Windows caveat below);
deposits (low-frequency, expensive)
accept a small loss window. MONETA.md §5 risk #4
documents this trade-off as "WAL-lite periodic snapshot, accept
small volatility window."

### What happens on hydrate

When `Moneta(config)` is constructed with `snapshot_path` and `wal_path`
set on the config and those files exist on disk:

1. The latest snapshot is loaded into a fresh ECS.
2. The shadow vector index is rebuilt from the hydrated ECS rows — the
   vector index does not persist independently in v1.x; it is a pure
   shadow.
3. Each WAL line is decided once. Under a **keyed** snapshot (one that
   carries `wal_applied_seqs`, as every non-degraded save writes), a
   line with a `seq` replays iff its seq is **not** in
   `wal_applied_seqs`, whatever its timestamp. A line without a `seq`
   (an rc1 line), and every line under a **keyless** snapshot (written
   by rc1, by a degraded save, or by a rewrite of `snapshot.json` that
   dropped the key), replays iff `timestamp > snapshot_created_at`, the
   rc1 rule. A `wal_applied_seqs` that is not a list of valid seqs
   counts as absent (WARNING). If a seq appears twice, the first line
   wins and the duplicate is dropped (WARNING).
4. Replayed lines go into the attention log with their seqs and apply
   on the next `run_sleep_pass`. Blank and undecodable lines are skipped
   (WARNING for undecodable). A line that is valid JSON but not a valid
   entry (no `entity_id`, a malformed UUID, a `null` weight) makes
   construction raise, as in rc1; the lock is released and no file is
   modified. Hydrate writes nothing: the first save normalizes the WAL,
   and the first append terminates a torn tail.

If no snapshot exists (cold start, or `kill -9` before the first
successful save), construction starts from an empty ECS, and every WAL
entry line still replays into the attention log.

Undrained attention now survives a save (defects B and D): a keyed save
keeps every WAL line whose signal the reducer has not recorded as
applied, and the next reopen replays it once. B and D pass unmarked in
all three matrix rows (native on, native off, wheel absent) at `b122a3a`
on branch `r1prime/attention-durability`. That change is not yet
accepted (design §6 gate 6) or released.

**What can still lose attention:**

- **A power loss on Windows shortly after a save.** Since Round 4 F1,
  every WAL append and every file a save publishes (the snapshot, the
  normalized WAL and the compacted WAL) is fsync'd before it counts, and
  on POSIX every rename, the WAL's creation and step 3's unlink are
  followed by a directory fsync. **Windows has no directory fsync**:
  `os.open` refuses a directory, and `os.replace` (`MoveFileExW` without
  `MOVEFILE_WRITE_THROUGH`) does not ask for write-through. Until NTFS
  flushes its journal, a power loss can roll back a save's renames. Each
  file is whole either way, and NTFS's ordered journal keeps the store
  consistent, but a signal appended after a save whose WAL rename is then
  rolled back is in the rolled-back file and is lost. Whether the
  append's own fsync forces that rename's journal record first is not
  verified.
- **A reopen while a keyless snapshot is current.** After a degraded save
  (logged at ERROR as `durability.snapshot DEGRADED`), an rc1 save, or a
  rewrite of `snapshot.json` that drops `wal_applied_seqs`, every line is
  judged by timestamp. Every line whose effect the snapshot's rows lack
  and whose timestamp is not after the snapshot's is lost: rc1's defect
  B. The next keyed save closes the exposure. A step 0 that fails because
  the WAL no longer starts with the bytes found at hydrate (changed
  outside the handle, or already normalized by a step 0 an interrupt cut
  short) fails at every save until the handle is reopened, so no keyed
  save follows on that handle: run a sleep pass, then reopen.
- **A torn attention apply.** If `apply_attention` raises inside a pass,
  the drained seqs are already recorded as applied (a stated loss is
  preferred to a silent double), so the next save drops their lines.
  Logged at ERROR as `torn attention apply`.
- **A switch to a reader that ignores `seq`** (rc1, or the v5
  migration). Both use the timestamp rule. Drain, then verify that the
  WAL is empty, before switching (`docs/OPERATOR_CARD_native.md`).

**What can double-apply:** only the timestamp rule replays an applied
line, and only when the line's timestamp is later than the
`snapshot_created_at` of a snapshot that already holds its effect. That
needs a broken clock precondition (a backward wall-clock step between
signal and save, or signal and snapshot stamped from different clocks)
plus a keyless reopen, or an rc1 reader of a store caught between a
keyed snapshot and its compaction (a crash, or a compaction that keeps
failing). Separately, a filesystem that did not keep metadata operations
in order across a power loss could reorder two saves' renames (design
§5). Since Round 4 F1 that needs Windows, which has no directory fsync,
and a filesystem other than NTFS, whose journal keeps them in order; on
POSIX every rename is directory-fsync'd. Concurrent sleep passes remain
unsupported.

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
  raises (ce45, Codex's candidate, prepared outside this repository). A
  layer whose save fails (a `False` result or a raise) stops that batch
  before its vector commit; the layer stays dirty and the next flush
  retries it. On the v1 handle, `run_sleep_pass` raises
  `moneta.usd_target.UsdSaveError` (a `RuntimeError`), and every entity
  that pass staged stays `STAGED_FOR_SYNC`: no later pass commits them
  again. On the v5 compat handle, the pass returns the error as
  `SleepPassResult.projection_error` with an ERROR log line, and the next
  pass projects the failed batch, and every later one, again; a prim that
  already exists is re-authored in place. A store layer that something else
  in the process already loaded (a Houdini LOP network shares Sdf's
  layer registry) is logged at ERROR as `Sdf registry sharing`, naming
  the layer, and
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
  handle on a `storage_uri`, or a second durable handle on a store file
  (snapshot, WAL or either tmp file), that a live handle in the same
  process already holds. Subclass of `RuntimeError`.
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
  lock and the store paths are released (or were never taken) and no
  file is modified: the next construct on the same store succeeds.
- `ValueError` — raised by `Moneta(config)` when the config's own store
  paths are not pairwise distinct; by `signal_attention` on a closed
  durable handle (`"durability manager is closed"`, nothing buffered);
  and by `m.durability.snapshot_ecs(ecs)` or
  `m.durability.start_background(ecs)` after `close()`, or when `ecs` is
  not the handle's own `m.ecs`. Each raises before anything is written.
- `RuntimeError("cannot reseed the WAL sequence allocator")` — raised by
  `Moneta(config)` only for a store whose recorded seqs leave no free
  allocator window. Only a hand-edited `snapshot.json` can produce one;
  no store this code writes reaches it. Construction fails cleanly: the
  lock and store paths are released and no file is modified.
- The sleep-pass reducer adds no exception: a concurrent pass is only
  logged at ERROR.
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
