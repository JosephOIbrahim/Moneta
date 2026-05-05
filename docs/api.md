# Moneta Four-Op API reference

**Status:** as of `v1.2.0-rc1`. Reflects the v1.1.0 singleton surgery
(`Moneta(config)` handle replaces the prior module-level `moneta.init()`
+ free-function API). The four operations themselves (signatures, locked
in `ARCHITECTURE.md` §2 and `MONETA.md` §2.1) are unchanged — what
changed is that they now live as methods on a per-substrate handle.

This document describes the four agent-facing operations exposed by
`moneta`. Their signatures are verbatim from `MONETA.md` §2.1 and remain
the locked interface — changes require §9 escalation.

## Imports

```python
from moneta import Moneta, MonetaConfig, Memory, EntityState
from moneta import MonetaResourceLockedError, ProtectedQuotaExceededError
```

`smoke_check()` is also exported as the lowest-friction end-to-end
sanity check; it constructs an ephemeral handle internally and exercises
deposit → query → signal_attention → run_sleep_pass → manifest. It is
not part of the agent surface (`ARCHITECTURE.md` §2.1).

## Setup — handle lifecycle

A Moneta substrate is constructed by handing a `MonetaConfig` to
`Moneta(config)`. Every consumer declares its storage boundary on line
one — there is no implicit default. The canonical form is the
`with`-block pattern, which guarantees the in-process URI lock and any
durability resources are released on exit:

```python
from moneta import Moneta, MonetaConfig

with Moneta(MonetaConfig.ephemeral()) as m:
    eid = m.deposit("hello", [1.0, 0.0])
    ...
```

Common config patterns:

```python
# Ephemeral, in-memory (test default).
MonetaConfig.ephemeral()

# Minutes-scale half-life, otherwise default.
MonetaConfig(
    storage_uri="moneta://prod/agent-A",
    half_life_seconds=60,
)

# Persistent: durability snapshot + WAL on disk.
MonetaConfig(
    storage_uri="moneta://prod/agent-A",
    half_life_seconds=3600,
    snapshot_path="/var/moneta/ecs.json",
    wal_path="/var/moneta/wal.jsonl",
    mock_target_log_path="/var/moneta/usd_authorings.jsonl",
)
```

### Handle exclusivity (`MonetaResourceLockedError`)

Two live `Moneta` handles cannot share the same `storage_uri` in one
process. Constructing a second handle on a URI already held by a live
first handle raises `MonetaResourceLockedError`:

```python
cfg = MonetaConfig(storage_uri="moneta://prod/agent-A", ...)
with Moneta(cfg) as _m1:
    with pytest.raises(MonetaResourceLockedError):
        Moneta(cfg)  # collision: uri already held
```

After `m.close()` (or after the `with` block exits), the URI is released
and may be re-acquired by a fresh handle. This is the in-process
exclusivity model; it is enforced by the module-level `_ACTIVE_URIS`
registry and intentionally does NOT cover cross-process exclusion (which
is the bridge layer's concern — see `bridge/` if you need cross-process
flock).

### No-arg trap

`Moneta()` (no argument) raises `TypeError` by design. There is no
implicit default config. Use `MonetaConfig.ephemeral()` for tests. This
makes the storage boundary visible at every construction site.

## The four operations

Each is a method on the handle returned by `Moneta(config)`. Below, `m`
is the handle.

### `m.deposit(payload, embedding, protected_floor=0.0) -> UUID`

Deposit a new memory. Returns a newly minted `EntityID` (UUID).

```python
eid = m.deposit(
    payload="The user prefers concise explanations.",
    embedding=[0.12, -0.45, 0.78, ...],   # from your embedder
    protected_floor=0.0,                  # 0.0 = ephemeral, >0 = pinned
)
```

Fresh memories start at `Utility = 1.0` (Phase 1 convention). If
`protected_floor > 0.0` and the handle already holds
`MonetaConfig.quota_override` (default `100`) protected memories,
`deposit` raises `ProtectedQuotaExceededError` — Phase 3 adds an
operator-facing unpin tool to reclaim slots.

The protected-quota check is atomic with respect to the ECS write under
a per-handle deposit lock — concurrent protected deposits cannot both
observe count=quota-1 and both succeed. (Regression test in
`tests/unit/test_api.py::TestProtectedQuota::test_concurrent_protected_deposits_respect_quota`.)

### `m.query(embedding, limit=5) -> List[Memory]`

Retrieve the top-k memories most relevant to `embedding`. The retrieval
flow is:

1. Decay all live entities (`ARCHITECTURE.md` §4 eval point 1)
2. Fetch from the shadow vector index (cosine similarity)
3. Rerank by `cosine_similarity × utility` so decayed memories are
   naturally demoted
4. Return the top `limit` `Memory` objects

```python
results = m.query(embedding=[0.12, -0.45, 0.78, ...], limit=5)
for memory in results:
    print(memory.payload, memory.utility, memory.attended_count)
```

### `m.signal_attention(weights) -> None`

Register agent attention for one or more entities. This is an
**append-only log write** — the ECS is not updated synchronously
(`ARCHITECTURE.md` §5.1). Updates apply at the sleep pass.

```python
m.signal_attention({
    eid_a: 0.3,
    eid_b: 0.1,
})
```

If durability is enabled (`snapshot_path` + `wal_path` in
`MonetaConfig`), each signal is fsync'd to the WAL before return.

Negative weights are accepted but **cannot drive a protected entity's
utility below its `protected_floor`** — the floor clamp applies to
attention writes as well as decay, preserving the `ARCHITECTURE.md` §10
"Utility never drops below ProtectedFloor" invariant.

### `m.get_consolidation_manifest() -> List[Memory]`

Return every memory currently in `STAGED_FOR_SYNC` state — i.e.
memories that a sleep pass has selected for USD authoring but not yet
committed. Phase 1 returns the staged subset as `Memory` objects; Phase
3 also surfaces the intended USD target sublayer via the `usd_link`
field.

```python
pending = m.get_consolidation_manifest()
print(f"{len(pending)} memories pending USD commit")
```

## Memory type (`ARCHITECTURE.md` §3)

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
    usd_link: Optional[object]     # Phase 1: opaque tag; Phase 3: SdfPath
```

Frozen — mutations flow through `signal_attention`, never through this
object.

## EntityState lifecycle

```
VOLATILE         — fresh deposit, fully in hot tier
  ↓
STAGED_FOR_SYNC  — Consolidation has selected for USD authoring
  ↓
CONSOLIDATED     — successfully authored (Phase 3); in hot tier until pruned
```

The `STAGED_FOR_SYNC → CONSOLIDATED` transition is per-batch: a
consolidation pass that succeeds for batch 1 but raises on batch 2
leaves batch 1 entities at `CONSOLIDATED` (matching disk + vector
reality) and batch 2 entities at `STAGED_FOR_SYNC` (recoverable on the
next pass once the underlying failure clears).

## Durability guarantees

Phase 1's durability model is WAL-lite + periodic snapshot, per
`MONETA.md` §5 risk #4 mitigation. The target is: survive `kill -9`
with at most ~30 seconds of volatile state lost.

### Coverage by operation

| Operation                  | Durability coverage          | Medium                                                                          |
| -------------------------- | ---------------------------- | ------------------------------------------------------------------------------- |
| `m.deposit`                | Snapshot-covered             | Captured by the next `run_sleep_pass` that writes the ECS snapshot              |
| `m.signal_attention`       | WAL-covered                  | Every call fsync'd to the JSONL WAL when durability is enabled                  |
| `m.query`                  | Not applicable (read-only)   | —                                                                               |
| `m.get_consolidation_manifest` | Not applicable (read-only) | —                                                                              |
| Attention reducer (sleep pass) | Snapshot-covered         | ECS state is snapshotted at the end of each pass                                |

### The volatility window

Deposits made after the last successful snapshot and before a `kill -9`
are **lost** on restart. The window width is:

- `~30 seconds` under the default 30-second background-thread snapshot
  interval (when `m.durability.start_background(m.ecs)` is running).
- Whatever wall-clock time elapsed since the last `m.run_sleep_pass()`
  under a sleep-pass-driven cadence (the common pattern in Phase 1).

This is a deliberately accepted risk: signals (high-frequency, cheap)
are fully durable; deposits (low-frequency, expensive) accept a small
loss window. `MONETA.md` §5 risk #4 explicitly documents this trade-off
as "WAL-lite periodic snapshot, accept small volatility window." The
design choice trades deposit durability for WAL write amplification —
writing every deposit to the WAL would double the hot-tier write volume
for a guarantee clients do not usually need.

### What happens on hydrate

When a `Moneta(config)` is constructed with `snapshot_path` and
`wal_path` set and those files exist on disk:

1. The latest snapshot is loaded into a fresh ECS.
2. The shadow vector index is rebuilt from the hydrated ECS rows — the
   vector index does not persist independently in Phase 1; it is a pure
   shadow.
3. WAL entries with `timestamp > snapshot_created_at` are replayed into
   the attention log. They are NOT immediately applied to the ECS —
   they apply on the next `m.run_sleep_pass()`, which is also when
   decay eval point 2 fires.
4. Pre-snapshot WAL entries are filtered out (they are already captured
   by the snapshot; replaying would double-count).

If no snapshot exists (cold start, or `kill -9` before the first
successful pass), the handle starts with an empty ECS.

### Recommended durability cadence

For production usage that wants the full ~30-second guarantee, call
`m.durability.start_background(m.ecs)` after construction. For test
harnesses and unit work, explicit `m.run_sleep_pass()` calls drive
snapshotting on demand and avoid a background thread. The
`tests/integration/test_durability_roundtrip.py` suite exercises the
explicit-pass flow end-to-end, including the `kill -9` scenario AND the
WAL race regression test from review finding
`persistence-L1-wal-truncation-race`.

## Example: minimal end-to-end

```python
from moneta import Moneta, MonetaConfig

with Moneta(MonetaConfig.ephemeral()) as m:
    eid = m.deposit("hello world", [1.0, 0.0, 0.0])
    results = m.query([1.0, 0.0, 0.0], limit=5)
    assert results[0].entity_id == eid

    m.signal_attention({eid: 0.5})

    # A sleep pass applies the attention and runs selection.
    result = m.run_sleep_pass()
    assert result.attention_updated == 1

    print(m.get_consolidation_manifest())  # []  (fresh memory, not staged)
```

See `smoke_check()` in `src/moneta/api.py` for the Substrate-authored
version of this flow.

## Errors

- **`TypeError`** — raised when `Moneta()` is constructed with no
  argument. By design: every consumer declares its storage boundary
  explicitly. Use `MonetaConfig.ephemeral()` for tests.
- **`MonetaResourceLockedError`** — raised when constructing a second
  `Moneta` handle on a `storage_uri` already held by a live first
  handle in the same process. Resolved by closing the first handle
  before reconstructing.
- **`ProtectedQuotaExceededError`** — raised when a protected deposit
  would exceed the per-handle quota (`MonetaConfig.quota_override`,
  default 100, per `ARCHITECTURE.md` §10). Phase 1: `deposit` raises.
  Phase 3: operator-facing unpin tool.

## Related docs

- `ARCHITECTURE.md` — locked spec
- `MONETA.md` — blueprint (phasing, lineage, risks)
- `docs/decay-tuning.md` — λ tuning guide
- `docs/substrate-conventions.md` — shared conventions with Octavius
- `docs/review/synthesis.md` — multi-agent review findings (pinned to
  the same v1.2.0-rc1 surface this doc describes)
