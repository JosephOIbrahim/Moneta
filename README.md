# Moneta

**Memory substrate for LLM agents built on OpenUSD's composition engine.**

---

## TL;DR

You build an LLM agent. It needs memory that:

- **Survives the conversation** — facts the agent learned in turn 3 are still there in turn 30.
- **Decays gracefully** — old, unused memories fade; reinforced ones stick.
- **Doesn't drown the prompt** — retrieval ranks by *relevance × utility*, not just similarity.
- **Has a clean handoff** between hot working memory and durable cold storage.

That's Moneta. It's a Python library. You construct a `Moneta` handle, you `deposit`, you `query`, you `signal_attention` when a memory was useful, and a sleep pass periodically consolidates the survivors to disk.

```python
import moneta

with moneta.Moneta(moneta.MonetaConfig.ephemeral()) as m:
    eid = m.deposit("the user prefers concise answers", embedding=[...])
    results = m.query(embedding=[...], limit=5)
    m.signal_attention({eid: 0.3})       # this memory was useful
    m.run_sleep_pass()                   # consolidate survivors
```

That's it. Four operations. No background threads, no daemons, no LLM calls inside the substrate.

> The name invokes **Juno Moneta** — Roman goddess of warning and memory, whose temple housed the mint because she also *reminded*. Memory as advisory, not just storage.

---

## Status

| Phase | Tag | What landed |
|---|---|---|
| **Phase 1** — ECS + four-op API | `v0.1.0` | 94 tests green, 30-min synthetic session clean |
| **Phase 2** — USD benchmark | `v0.2.0` | 243-config sweep, Yellow tier verdict |
| **Phase 3** — Real USD integration | `v1.0.0` | Real USD writer, narrow lock, 775M-assertion safety verification |
| **Singleton surgery** — handle API | **`v1.1.0`** | Module-level singleton replaced by `Moneta(config)` handle. Multi-instance per process. |

**Current version:** `v1.1.0`. **Test count:** 107 plain Python passing + 4 properly-gated pxr cases (run under hython, OpenUSD 0.25.5).

Sibling project: [Octavius](https://github.com/JosephOIbrahim) (coordination substrate on the same USD thesis). Moneta is memory; Octavius is coordination. They share [substrate conventions](docs/substrate-conventions.md) but not Python code — the stage is the interface.

---

## Quick start (60 seconds)

### 1. Install

```bash
git clone https://github.com/JosephOIbrahim/Moneta.git
cd Moneta
pip install -e .[dev]
```

Python ≥ 3.11. **Zero runtime dependencies** — no numpy, torch, or DB drivers. Just stdlib.

### 2. Smoke check

```bash
python -c "import moneta; moneta.smoke_check(); print('OK')"
```

If you see `OK`, the four ops, decay math, attention reducer, sleep pass, and consolidation are all wired correctly.

### 3. Run the tests (optional)

```bash
pytest
```

You should see **107 passed**, 4 skipped (pxr-gated USD tests). The skipped ones run under hython if you have OpenUSD 0.25.5 installed.

### Stuck?

| Symptom | Fix |
|---|---|
| `python: command not found` | Try `python3`, or install Python from [python.org](https://www.python.org/downloads/) |
| `No module named 'moneta'` | Run `pip install -e .[dev]` from the Moneta directory |
| `pytest: command not found` | Run `python -m pytest` |
| `TypeError: Moneta() missing 1 required ... 'config'` | That's by design (§5.3 of the design brief — no implicit defaults). Pass `MonetaConfig.ephemeral()` for tests. |

---

## The four-op API

The entire agent-facing surface. Agents have **zero knowledge** of ECS, USD, vector indices, decay, or consolidation.

| Operation | Signature | Returns |
|---|---|---|
| `deposit` | `(payload: str, embedding: List[float], protected_floor: float = 0.0)` | `UUID` |
| `query` | `(embedding: List[float], limit: int = 5)` | `List[Memory]` |
| `signal_attention` | `(weights: Dict[UUID, float])` | `None` |
| `get_consolidation_manifest` | `()` | `List[Memory]` |

These are methods on the `Moneta` handle. Plus one harness-level operator:

| Operation | Signature | What it does |
|---|---|---|
| `run_sleep_pass` | `()` | Drains attention log, applies decay, prunes/stages survivors |

### Hello world

```python
import moneta

# Construct a handle. Each handle owns one storage_uri; two handles
# on the same URI raise MonetaResourceLockedError.
with moneta.Moneta(moneta.MonetaConfig.ephemeral()) as m:
    eid = m.deposit(
        payload="The user prefers concise explanations.",
        embedding=[0.12, -0.45, 0.78, ...],   # from your embedder
    )

    # Retrieve by semantic similarity (utility-weighted)
    results = m.query(embedding=[0.12, -0.45, 0.78, ...], limit=5)
    for memory in results:
        print(memory.payload, f"u={memory.utility:.2f}", f"a={memory.attended_count}")

    # Tell Moneta this memory was useful (async — applied at next sleep pass)
    m.signal_attention({eid: 0.3})

    # Periodic consolidation (drain attention log, decay, prune/stage)
    result = m.run_sleep_pass()
    print(f"pruned={result.pruned} staged={result.staged}")
```

### Why a handle?

Before `v1.1.0` Moneta exposed module-level functions backed by a singleton — one substrate per process. The handle (`v1.1.0`) lifts that limit:

- **Multiple instances per process.** Run two agents side-by-side, or one substrate per tenant in a hosted setup.
- **Explicit lifecycle.** `with Moneta(config) as m:` is the canonical form. `__exit__` releases all resources and the in-process URI lock.
- **No-arg trap.** `Moneta()` raises `TypeError` by design — every consumer declares its storage boundary on line one. Use `MonetaConfig.ephemeral()` for tests.
- **Two handles on the same `storage_uri` raise.** In-memory `_ACTIVE_URIS` registry. No silent sharing.

Full design rationale: [`DEEP_THINK_BRIEF_substrate_handle.md`](DEEP_THINK_BRIEF_substrate_handle.md). Surgery record: [`SURGERY_complete.md`](SURGERY_complete.md).

Full API reference with usage examples: [`docs/api.md`](docs/api.md).

---

## How it works (architecture)

### System overview

```mermaid
graph TB
    consumer["<b>Consumer</b><br/>(your agent / app)"]
    handle["<b>Moneta(config)</b> handle<br/>with __exit__ → lock release"]
    registry["<b>_ACTIVE_URIS</b><br/>process-level lock<br/>by storage_uri"]

    subgraph hot["Hot Tier — owned by handle"]
        ECS["ECS<br/>struct-of-arrays"]
        Decay["Lazy Exponential Decay<br/>U = max(floor, U·e⁻ᵏᵗ)"]
        AttLog["Attention Log<br/>lock-free append<br/>sleep-pass reduce"]
    end

    subgraph shadow["Shadow Index — owned by handle"]
        VecIdx["VectorIndex<br/>in-memory (v1.1)<br/>LanceDB future"]
    end

    subgraph consolidation["Consolidation Engine — owned by handle"]
        Runner["ConsolidationRunner<br/>pressure + idle trigger<br/>500-prim batch cap"]
        SeqWriter["SequentialWriter<br/>USD-first / vector-second"]
    end

    subgraph targets["Authoring Targets"]
        Real["UsdTarget<br/>pxr/Sdf · narrow lock<br/>ChangeBlock-only scope"]
        Mock["MockUsdTarget<br/>JSONL log (A/B fallback)"]
    end

    subgraph cold["Cold Tier — durable"]
        Rolling["cortex_YYYY_MM_DD.usda<br/>rolling daily sublayers"]
        Protected["cortex_protected.usda<br/>root-pinned strongest"]
    end

    consumer -->|"with Moneta(cfg) as m:"| handle
    handle -.->|"acquire URI"| registry
    handle --> ECS
    handle --> AttLog
    handle --> VecIdx
    handle --> Runner
    Runner --> AttLog
    Runner --> Decay
    Runner --> SeqWriter
    SeqWriter -->|"1. USD first"| Real
    SeqWriter -->|"2. vector second"| VecIdx
    Real --> Rolling
    Real --> Protected
    Mock -.->|"A/B swap via<br/>MonetaConfig.use_real_usd"| Real

    style consumer fill:#1a1a2e,color:#e0e0e0
    style handle fill:#0984e3,color:#fff
    style registry fill:#d63031,color:#fff
    style hot fill:#16213e,color:#e0e0e0
    style shadow fill:#0f3460,color:#e0e0e0
    style consolidation fill:#533483,color:#e0e0e0
    style targets fill:#2c2c54,color:#e0e0e0
    style cold fill:#1e3a5f,color:#e0e0e0
```

### Handle lifecycle (`v1.1.0`)

```mermaid
stateDiagram-v2
    [*] --> Constructed: Moneta(config)<br/>acquires _ACTIVE_URIS

    Constructed --> Live: __enter__<br/>(returns self)
    Live --> Live: deposit / query / signal_attention<br/>get_consolidation_manifest / run_sleep_pass

    Live --> Closing: __exit__<br/>OR raise inside with block<br/>OR explicit close()
    Closing --> Released: durability.close →<br/>authoring_target.close →<br/>_ACTIVE_URIS.discard
    Released --> [*]

    note right of Constructed
        Two handles on the same
        storage_uri → MonetaResourceLockedError.
        Verified by test_twin_substrate.py
        and adversarial Crucible suite.
    end note

    note left of Released
        Idempotent. Order matters:
        snapshot daemon thread first,
        file pointers second,
        URI lock last.
    end note
```

### Memory lifecycle

```mermaid
stateDiagram-v2
    [*] --> VOLATILE: deposit()
    VOLATILE --> VOLATILE: signal_attention()<br/>reinforces utility
    VOLATILE --> VOLATILE: query()<br/>applies decay

    VOLATILE --> Pruned: sleep pass<br/>U < 0.1 AND AC < 3
    VOLATILE --> STAGED_FOR_SYNC: sleep pass<br/>U < 0.3 AND AC ≥ 3

    STAGED_FOR_SYNC --> CONSOLIDATED: sequential write<br/>USD first → vector second

    Pruned --> [*]: removed from ECS + vector index

    note right of VOLATILE
        Utility decays via lazy exponential:
        U_now = max(floor, U_last · exp(-λ · Δt))
        Default half-life: 6 hours
        Tuning range: 1 min – 24 hours
    end note

    note right of CONSOLIDATED
        Written to cortex_YYYY_MM_DD.usda
        via UsdTarget (pxr/Sdf)
        Narrow lock: ChangeBlock-only scope
        Sublayer rotation at 50k prims
    end note
```

### Consolidation sleep-pass flow

```mermaid
flowchart TD
    trigger{"Trigger?<br/>ECS > MAX_ENTITIES<br/>OR idle > 5000ms"} -->|yes| drain["1. Drain attention log"]
    drain --> reduce["2. Apply aggregated attention<br/>Utility += Σweights<br/>AttendedCount += signal_count"]
    reduce --> decay2["3. Decay eval point 2<br/>(all entities)"]
    decay2 --> decay3["4. Decay eval point 3<br/>(explicit, per spec)"]
    decay3 --> classify["5. Classify volatile entities"]

    classify --> prune{"U < 0.1 AND<br/>AC < 3?"}
    classify --> stage{"U < 0.3 AND<br/>AC ≥ 3?"}
    classify --> keep{"Otherwise"}

    prune -->|prune| remove["Remove from<br/>ECS + vector index"]
    stage -->|stage| seqwrite["Sequential write (≤500/batch):<br/>1. UsdTarget.author_stage_batch()<br/>    Sdf.ChangeBlock (narrow lock)<br/>2. UsdTarget.flush() → layer.Save()<br/>3. VectorIndex.update_state()"]
    keep -->|keep| volatile["Stays VOLATILE<br/>re-evaluated next pass"]

    seqwrite --> consolidated["State → CONSOLIDATED"]

    style trigger fill:#e17055,color:#fff
    style remove fill:#d63031,color:#fff
    style consolidated fill:#00b894,color:#fff
    style volatile fill:#fdcb6e,color:#000
```

### Protocol injection — dual-target architecture

```mermaid
graph LR
    subgraph mock["MockUsdTarget (A/B fallback)"]
        SW1["SequentialWriter"]
        MT["MockUsdTarget<br/><i>JSONL log</i>"]
        VI1["VectorIndex<br/><i>in-memory stdlib</i>"]
        SW1 -->|AuthoringTarget| MT
        SW1 -->|VectorIndexTarget| VI1
    end

    subgraph real["UsdTarget (default, v1.0.0+)"]
        SW2["SequentialWriter<br/><b>unchanged</b>"]
        RT["UsdTarget<br/><i>pxr/Sdf · narrow lock</i>"]
        VI2["VectorIndex<br/><i>in-memory (LanceDB future)</i>"]
        SW2 -->|AuthoringTarget| RT
        SW2 -->|VectorIndexTarget| VI2
    end

    MT -. "same AuthoringTarget Protocol<br/>MonetaConfig.use_real_usd swap" .-> RT

    style mock fill:#2d3436,color:#dfe6e9
    style real fill:#0984e3,color:#fff
```

### Substrate family

```mermaid
graph TB
    thesis["<b>Parent thesis</b><br/>OpenUSD's composition engine is a general-purpose<br/>prioritization-and-visibility substrate for agent state<br/>that is not geometry"]

    moneta["<b>Moneta</b> (memory)<br/>· Decay via sublayer stack position<br/>· Consolidation via variant transitions<br/>· Fallback via Pcp resolution<br/>· Protected memory via root-pinned sublayer"]

    octavius["<b>Octavius</b> (coordination)<br/>· Visibility via LIVRPS shadowing<br/>· Coordination via shared stage<br/>· Priority via composition arc strength"]

    thesis --> moneta
    thesis --> octavius

    moneta <-. "stage-level composition<br/>no Python imports<br/>UUID-based prim naming<br/>LIVRPS priority discipline<br/>Sdf.ChangeBlock for batch writes<br/>UTC sublayer date routing" .-> octavius

    style thesis fill:#6c5ce7,color:#fff
    style moneta fill:#00b894,color:#fff
    style octavius fill:#0984e3,color:#fff
```

---

## Decay model

Lazy memoryless exponential, evaluated at access time only — never on a background tick.

```
U_now = max(ProtectedFloor, U_last · exp(-λ · (t_now - t_last)))
```

| Time since deposit | Utility (no reinforcement, 6h half-life) |
|--------------------|------------------------------------------|
| 0 min | 1.000 |
| 30 min | 0.944 |
| 1 hour | 0.891 |
| 3 hours | 0.707 |
| 6 hours | 0.500 |
| 12 hours | 0.250 |
| 24 hours | 0.063 |

`signal_attention()` boosts utility and increments attended count. Memories that are actively reinforced survive; unreinforced memories decay toward pruning.

Tuning guide: [docs/decay-tuning.md](docs/decay-tuning.md)

---

## Project structure

```
src/moneta/
├── api.py                 # Moneta handle + MonetaConfig + _ACTIVE_URIS + smoke_check
├── types.py               # Memory, EntityState
├── ecs.py                 # flat struct-of-arrays hot tier
├── decay.py               # lazy exponential decay
├── attention_log.py       # lock-free append + sleep-pass reducer
├── vector_index.py        # shadow vector index (in-memory; LanceDB future)
├── durability.py          # WAL-lite snapshot + JSONL WAL
├── sequential_writer.py   # USD-first, vector-second Protocol
├── consolidation.py       # sleep-pass trigger + selection + 500-prim batch cap
├── usd_target.py          # Phase 3 real USD writer (narrow lock, OpenUSD 0.25.5)
├── mock_usd_target.py     # Phase 1 JSONL authoring target (A/B fallback)
├── manifest.py            # get_consolidation_manifest delegate
└── __init__.py            # re-exports

tests/
├── unit/                          # 70 plain-Python + 17 hython USD
├── integration/                   # 22 plain-Python + 6 hython USD
├── load/                          # 2 — 30-min synthetic session gate
├── test_twin_substrate.py         # 3 mock disk-backed + 1 hython real USD (Forge truth condition)
└── test_twin_substrate_adversarial.py  # 10 always-run + 1 hython (Crucible adversarial)

scripts/
└── usd_metabolism_bench_v2.py    # Phase 2 benchmark + Pass 5 stress test harness

docs/
├── api.md                       # four-op reference
├── decay-tuning.md              # λ tuning guide
├── substrate-conventions.md     # 6 conventions shared with Octavius
├── agent-commandments.md        # MoE agent discipline (8 commandments)
├── phase2-benchmark-results.md  # Phase 2 analyst interpretation
├── phase2-closure.md            # Phase 2 rulings + operational envelope
├── phase3-closure.md            # Phase 3 closure record
├── pass5-q6-findings.md         # Q6 thread-safety ruling
├── patent-evidence/             # dated evidence entries for counsel
└── rounds/                      # Gemini Deep Think scoping outputs
```

---

## Locked decisions

These cannot be re-opened without [§9 escalation](MONETA.md):

1. **Four-op API** — `deposit`, `query`, `signal_attention`, `get_consolidation_manifest`. No fifth op.
2. **Decay math** — `U = max(floor, U·exp(-λ·Δt))`. Three evaluation points, no fourth.
3. **Concurrency primitive** — append-only attention log, reduced at sleep pass. No locks.
4. **Atomicity** — sequential write (USD first, vector second). No 2PC. Orphans benign.
5. **Handle, not singleton** (`v1.1.0`) — `Moneta(config)` is the only constructor. `Moneta()` raises `TypeError`. Two handles on the same `storage_uri` raise `MonetaResourceLockedError`. In-memory `_ACTIVE_URIS` registry, not file locks.

---

## Phase 2 verdict

**YELLOW — clean in the operational envelope, with documented graceful degradation beyond it.**

The USD benchmark measured lock-and-rebuild tax across 243 configs in 52.9 minutes on a Threadripper PRO 7965WX with OpenUSD 0.25.5. Key finding: the bottleneck is `Save()` serialization against accumulated sublayer content, not Pcp rebuild (which is effectively free at 0.1–2.6ms).

| Accumulated prims | Shadow commit | p95 stall (median) | Verdict |
|-------------------|--------------|-------------------|---------|
| 0 | 5ms | 8ms | Green |
| 0 | 50ms | 56ms | Yellow |
| 25,000 | 15ms | 78ms | Yellow |
| 100,000 | 15ms | 213ms | Yellow |
| 100,000 | 50ms | 251ms | Yellow (max 370ms) |

Phase 3 operational envelope: sublayer rotation at 50k prims, idle-window consolidation, batch cap 500, shadow commit budget ≤15ms. Within this envelope, steady-state p95 stall sits in the 50–170ms band.

Full results: [docs/phase2-benchmark-results.md](docs/phase2-benchmark-results.md) | Rulings: [docs/phase2-closure.md](docs/phase2-closure.md)

---

## Phase 3 verdict

**GREEN-ADJACENT — narrow writer lock, ChangeBlock-only scope.**

Phase 3 shipped real USD integration against OpenUSD 0.25.5. The Q6 concurrent Traverse + Save investigation (Pass 5) ruled DETERMINISTIC SAFE: 10,000 iterations, 775M prim-level concurrent read assertions, zero failures. The writer lock was shrunk from full-width (ChangeBlock + Save) to ChangeBlock-only scope (Pass 6).

| Batch size | Wide-lock p95 stall | Narrow-lock p95 stall | Reduction |
|------------|--------------------|-----------------------|-----------|
| 10 (typical) | 127–176ms | 0.6–0.8ms | **99.5%** |
| 100 | ~130ms | ~13ms | ~90% |
| 1000 | 152–217ms | 148–257ms | ~0% (ChangeBlock dominates) |

At Moneta's operational point (batch ≤ 500, accumulated ≤ 50k prims), the reader stall drops from the Phase 2 Yellow steady-state (~131ms) to a projected 10–30ms.

Full closure: [docs/phase3-closure.md](docs/phase3-closure.md) | Patent evidence: [docs/patent-evidence/](docs/patent-evidence/)

---

## v1.1.0 — singleton surgery verdict

**SHIPPED — handle replaces singleton, multi-instance per process.**

The `v1.1.0` surgery replaced the module-level singleton (`_state` at `api.py:124` plus `PROTECTED_QUOTA = 100`) with a dependency-injected `Moneta` handle. Mixture-of-experts execution: Scout audit, Forge implementation, Crucible adversarial pass, Steward sign-off.

| Surface | Before | After |
|---|---|---|
| Plain-Python passing | 94 | **107** |
| Pxr-gated (run under hython) | 23 | **25** |
| Substrates per process | 1 | **N** |
| Two handles same URI | shared, undefined | **`MonetaResourceLockedError`** |

Empirical TOCTOU stress: 480 concurrent-construction attempts on the same URI under CPython GIL, zero double-acquisitions. Evidence under documented runtime, not proof under PEP 703 free-threading. Free-threaded TOCTOU and same-path/different-URI registry collapse are explicitly carried forward to the next surgery.

Surgery record: [SURGERY_complete.md](SURGERY_complete.md) | Audit: [AUDIT_pre_surgery.md](AUDIT_pre_surgery.md) | Design brief: [DEEP_THINK_BRIEF_substrate_handle.md](DEEP_THINK_BRIEF_substrate_handle.md)

---

## Novelty claims

Moneta is not novel as a tiered memory architecture. It is novel as a **substrate choice**:

1. **OpenUSD composition arcs as cognitive state substrate** — LIVRPS resolution order implicitly encodes decay priority
2. **USD variant selection as fidelity LOD primitive** — detail-to-gist transitions via `VariantSelection`
3. **Pcp-based resolution as implicit multi-fidelity fallback** — highest surviving fidelity served without routing logic
4. **Protected memory as root-pinned strong-position sublayer** — non-decaying state falls out of composition, not runtime checks

These four claims are **structural, not temporal** — they hold across Green, Yellow, and Red integration tiers. Empirically evidenced in [docs/patent-evidence/](docs/patent-evidence/). Patent filing is the next post-`v1.0.0` action.

---

## Lineage

Round 1 (scoping brief) → Round 2 (Gemini Deep Think architectural spec) → Round 2.5 (Claude prior-art review) → Round 3 (Gemini Deep Think validation) → **Phase 1** (5 passes, 94 tests, `v0.1.0`) → **Phase 2** (benchmark, `v0.2.0`) → **Phase 3** (7 passes, narrow lock, 775M-assertion safety, `v1.0.0`) → **Singleton surgery** (Scout / Forge / Crucible / Steward, `v1.1.0`).

---

## Related docs

| Document | Purpose |
|---|---|
| [MONETA.md](MONETA.md) | Build blueprint — phasing, risks, roles, escalation |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Locked spec — source of truth for implementation |
| [docs/api.md](docs/api.md) | Four-op API reference with examples |
| [docs/decay-tuning.md](docs/decay-tuning.md) | λ tuning guide with curves |
| [docs/substrate-conventions.md](docs/substrate-conventions.md) | 6 conventions shared with Octavius |
| [docs/phase2-closure.md](docs/phase2-closure.md) | Phase 2 verdict + operational envelope |
| [docs/phase3-closure.md](docs/phase3-closure.md) | Phase 3 closure + pass-by-pass record |
| [SURGERY_complete.md](SURGERY_complete.md) | `v1.1.0` singleton-to-handle surgery record |
| [docs/patent-evidence/](docs/patent-evidence/) | Dated evidence for patent counsel |

---

## License

Proprietary. 3 patents pending (USD cognitive state, digital injection, Cosmos predictive lighting).

---

*Built from the inside out. Substrate-first. Ship Moneta.*
