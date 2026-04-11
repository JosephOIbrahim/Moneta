# Moneta Four-Op API reference

This document describes the four agent-facing operations exposed by
`moneta` (ARCHITECTURE.md §2). The signatures below are verbatim from
MONETA.md §2.1 and are the locked interface — changes require §9
escalation.

## Imports

```python
import moneta
from moneta import Memory, EntityState
```

The module also exposes `init`, `run_sleep_pass`, `smoke_check`, and
`MonetaConfig` — these are harness-level bootstraps, not part of the
agent surface (ARCHITECTURE.md §2.1).

## Setup

Every Moneta process must call `init()` once before any agent operation:

```python
import moneta
moneta.init()                         # defaults (in-memory, 6h half-life)
moneta.init(half_life_seconds=60)     # minutes-scale half-life
moneta.init(config=moneta.MonetaConfig(
    half_life_seconds=3600,
    snapshot_path="/var/moneta/ecs.json",
    wal_path="/var/moneta/wal.jsonl",
    mock_target_log_path="/var/moneta/usd_authorings.jsonl",
))
```

Calling `init()` a second time resets all substrate state.

## The four operations

### `deposit(payload, embedding, protected_floor=0.0) -> UUID`

Deposit a new memory. Returns a newly minted `EntityID` (UUID).

```python
eid = moneta.deposit(
    payload="The user prefers concise explanations.",
    embedding=[0.12, -0.45, 0.78, ...],  # from your embedder
    protected_floor=0.0,                 # 0.0 = ephemeral, >0 = pinned
)
```

Fresh memories start at `Utility = 1.0` (Phase 1 convention, Pass 2
judgment call #2). If `protected_floor > 0.0` and the agent already
holds `PROTECTED_QUOTA` (100) protected memories, `deposit` raises
`ProtectedQuotaExceededError` — Phase 3 adds an operator-facing unpin
tool to reclaim slots (Ruling #4, Pass 2).

### `query(embedding, limit=5) -> List[Memory]`

Retrieve the top-k memories most relevant to `embedding`. The retrieval
flow is:

1. Decay all live entities (ARCHITECTURE.md §4 eval point 1)
2. Fetch from the shadow vector index (cosine similarity)
3. Rerank by `cosine_similarity × utility` so decayed memories are
   naturally demoted
4. Return the top `limit` `Memory` objects

```python
results = moneta.query(embedding=[0.12, -0.45, 0.78, ...], limit=5)
for m in results:
    print(m.payload, m.utility, m.attended_count)
```

### `signal_attention(weights) -> None`

Register agent attention for one or more entities. This is an
**append-only log write** — the ECS is not updated synchronously
(ARCHITECTURE.md §5.1). Updates apply at the sleep pass, which is
Consolidation Engineer's trigger.

```python
moneta.signal_attention({
    eid_a: 0.3,
    eid_b: 0.1,
})
```

If durability is enabled (snapshot_path + wal_path in `MonetaConfig`),
each signal is also fsync'd to the WAL before return.

### `get_consolidation_manifest() -> List[Memory]`

Return every memory currently in `STAGED_FOR_SYNC` state — i.e.
memories that a sleep pass has selected for USD authoring but not yet
committed. Phase 1 returns the staged subset as `Memory` objects; Phase
3 will also surface the intended USD target sublayer.

```python
pending = moneta.get_consolidation_manifest()
print(f"{len(pending)} memories pending USD commit")
```

## Memory type (ARCHITECTURE.md §3)

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

## Durability guarantees

Moneta's Phase 1 durability model is WAL-lite + periodic snapshot, per the MONETA.md §5 risk #4 mitigation. The target is: survive `kill -9` with at most ~30 seconds of volatile state lost.

### Coverage by operation

| Operation | Durability coverage | Medium |
|---|---|---|
| `deposit` | Snapshot-covered | Captured by the next `run_sleep_pass` that writes the ECS snapshot |
| `signal_attention` | WAL-covered | Every call fsync'd to the JSONL WAL when durability is enabled |
| `query` | Not applicable (read-only) | — |
| `get_consolidation_manifest` | Not applicable (read-only) | — |
| Attention reducer (inside `run_sleep_pass`) | Snapshot-covered | ECS state is snapshotted at the end of each pass |

### The volatility window

Deposits made after the last successful snapshot and before a `kill -9` are **lost** on restart. The window width is:

- `~30 seconds` under the default 30-second background-thread snapshot interval (when `durability.start_background(ecs)` is running).
- Whatever wall-clock time elapsed since the last `run_sleep_pass` under a sleep-pass-driven cadence (when no background thread is running — this is the common pattern in Phase 1).

This is a deliberately accepted risk: signals (high-frequency, cheap) are fully durable; deposits (low-frequency, expensive) accept a small loss window. MONETA.md §5 risk #4 explicitly documents this trade-off as "WAL-lite periodic snapshot, accept small volatility window." The design choice trades deposit durability for WAL write amplification: writing every deposit to the WAL would double the write volume of the hot-tier path for a guarantee clients do not usually need.

### What happens on hydrate

When `init()` is called with `snapshot_path` and `wal_path` and those files exist on disk:

1. The latest snapshot is loaded into a fresh ECS.
2. The shadow vector index is rebuilt from the hydrated ECS rows — the vector index does not persist independently in Phase 1; it is a pure shadow.
3. WAL entries with `timestamp > snapshot_created_at` are replayed into the attention log. They are NOT immediately applied to the ECS — they apply on the next `run_sleep_pass`, which is the point at which decay eval point 2 also fires.
4. Pre-snapshot WAL entries are filtered out (they are already captured by the snapshot and replaying them would double-count).

If no snapshot exists (cold start, or `kill -9` before the first successful pass), `init()` returns an empty ECS. Any deposits or signals made before the crash are gone.

### Recommended durability cadence

For production usage that wants the full ~30-second guarantee, call `durability.start_background(ecs)` after `init()`. For test harnesses and unit work, explicit `run_sleep_pass()` calls drive snapshotting on demand and avoid a background thread. The `tests/integration/test_durability_roundtrip.py` suite exercises the explicit-pass flow end-to-end including the `kill -9` scenario.

## Example: minimal end-to-end

```python
import moneta

moneta.init()

eid = moneta.deposit("hello world", [1.0, 0.0, 0.0])
results = moneta.query([1.0, 0.0, 0.0], limit=5)
assert results[0].entity_id == eid

moneta.signal_attention({eid: 0.5})

# A sleep pass applies the attention and runs selection.
result = moneta.run_sleep_pass()
assert result.attention_updated == 1

print(moneta.get_consolidation_manifest())  # []  (fresh memory, not staged)
```

See `smoke_check()` in `src/moneta/api.py` for the Substrate-authored
version of this flow.

## Errors

- `MonetaNotInitializedError` — raised when an operation is called
  before `init()`.
- `ProtectedQuotaExceededError` — raised when a protected deposit would
  exceed the 100-entry quota (ARCHITECTURE.md §10). Phase 1: `deposit`
  raises. Phase 3: operator-facing unpin tool.

## Related docs

- `ARCHITECTURE.md` — locked spec
- `MONETA.md` — blueprint (phasing, lineage, risks)
- `docs/decay-tuning.md` — λ tuning guide
- `docs/substrate-conventions.md` — shared conventions with Octavius
