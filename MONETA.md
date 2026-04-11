# Moneta — Build Blueprint

**Project:** Moneta
**Status:** Phase 1 ready to begin. Architecture locked. Agent team execution authorized.
**Lineage:** Round 1 scoping brief → Round 2 architectural spec (Gemini Deep Think) → Round 3 plan validation (Gemini Deep Think) → This blueprint
**Codename during scoping:** CLS Hybrid (retain for historical search only; this project is Moneta)
**Sibling project:** Octavius (coordination substrate on the same USD thesis)

---

## How to use this document

This blueprint is both a human-readable architecture document and a drop-in execution prompt for Claude Code agent teams operating in Mixture-of-Experts mode. If you are an agent encountering this document fresh:

1. **Read the entire document before claiming any role.** The foundations section contains locked decisions that cannot be re-litigated without invalidating the novelty claim.
2. **Identify which role you are taking.** Role contracts are in §6. Only one agent per role at a time. Cross-role coordination happens through the artifacts each role delivers, not through direct messaging.
3. **Do not re-open architectural decisions made in Round 2 or Round 3.** Those rounds are closed. If implementation surfaces a decision that appears wrong, escalate per §9 rather than patching silently.
4. **Hold the line on scope.** §8 lists what is explicitly not in Phase 1. Agent teams will be tempted to build ahead. Resist.
5. **Documentarian runs continuously.** Every role's output must land in docs as it is produced, not retroactively.

---

## 1. Project identity

Moneta is a memory substrate that implements working and consolidated memory for LLM agents using OpenUSD's composition engine as the cortex layer. The name invokes Juno Moneta — Roman goddess of warning and memory, whose temple housed the mint because she also *reminded*. Memory as advisory, not just storage.

### What Moneta is

- A hot/cold tiered memory system with an Entity Component System (ECS) hot tier and an OpenUSD cold tier
- A four-operation agent API that hides all USD internals from the calling agent
- The memory half of a unified cognitive substrate platform shared with Octavius
- A substrate-level capability that unlocks memory systems with native composition against spatial and world state, which no other memory architecture can provide

### What Moneta is not

- A drop-in replacement for Mem0, Letta, Zep, or HippoRAG. The agent memory subfield consolidated in Q1 2026 around graph-based and vector-based substrates. Competing on their benchmarks is a losing move.
- A standalone product. Moneta is a substrate. Applications compose on top.
- An experimental framework. v1 ships working, or it does not ship.

### Product family positioning

Octavius and Moneta are siblings, not cousins. Both inherit from the same parent thesis: **OpenUSD's composition engine, designed for scene description, is a general-purpose prioritization-and-visibility substrate for agent state that is not geometry.**

- **Octavius** applies this thesis to **coordination state** — agents coordinate through compositional awareness on a shared stage, with LIVRPS shadowing determining visibility
- **Moneta** applies this thesis to **memory state** — memory decays through sublayer stack position, consolidates through variant transitions, and resolves through Pcp fallback

Both repositories write to USD stages following a shared prim naming discipline (UUID-based, per TfToken registry rules). Cross-project composition happens at the stage layer, not at the code layer. The stage is the interface.

---

## 2. Locked foundations

The following decisions are final. Implementations must conform. Re-opening any of these requires escalation per §9 and almost certainly a new Gemini Deep Think round.

### 2.1 The four-operation API

```python
def deposit(payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID
def query(embedding: List[float], limit: int = 5) -> List[Memory]
def signal_attention(weights: Dict[UUID, float]) -> None
def get_consolidation_manifest() -> List[Memory]
```

These four operations are the entire agent-facing surface. No other methods are exposed. Agents have zero knowledge of USD, ECS, vector indices, or consolidation mechanics.

### 2.2 Hot substrate schema (ECS)

Flat, vectorizable, struct-of-arrays or DataFrame-backed. Component fields:

- `EntityID` — UUID
- `SemanticVector` — float array, used for O(1) miss detection
- `Payload` — uncompressed content
- `Utility` — float 0.0 to 1.0, sole target of decay
- `AttendedCount` — int, cumulative reinforcement counter, separate from Utility
- `ProtectedFloor` — float, default 0.0, decay floor
- `LastEvaluated` — wall-clock timestamp
- `State` — enum: `VOLATILE`, `STAGED_FOR_SYNC`, `CONSOLIDATED`
- `UsdLink` — nullable SdfPath, populated when entity was hydrated from USD

### 2.3 Decay function

Lazy memoryless exponential, evaluated at access time only. No background tick loop.

```
U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))
```

**λ is configurable at runtime.** Starting value: half-life of 6 hours. Tuning range: 1 minute to 24 hours. λ is instrumented and logged — do not commit to a production default until Phase 1 load testing produces curves.

Evaluation happens:
- Immediately before context retrieval
- Immediately after the attention-write phase
- During consolidation scan

Never on a background tick. Never in a 60Hz loop.

### 2.4 Attention interface

Explicit agent signaling only. No KV cache extraction, no post-hoc prompt analysis. The agent calls `signal_attention(weights)` and the hot substrate updates:

```
Utility = min(1.0, Utility + weights[UUID])
AttendedCount += 1
LastEvaluated = now()
```

### 2.5 Concurrency primitive

**Append-only attention log, reduced at sleep pass.** This is the committed choice. Not per-entity spinlocks, not CAS loops. The log is lock-free, eventually consistent, and has the simplest failure mode. Sleep pass reads the log, applies reductions, and clears.

### 2.6 Consolidation mechanics (Phase 3 target)

For reference during Phase 1, so mock targets emit the right shape:

- **Trigger conditions:** ECS volatile count exceeds `MAX_ENTITIES`, or inference queue idle > 5000ms
- **`MAX_ENTITIES`:** Default 10000. Runtime-configurable, tuning deferred to Phase 1 load testing per Test Engineer's synthetic session harness.
- **Pruning:** Utility < 0.1 and AttendedCount < 3 → delete entirely
- **Staging:** Utility < 0.3 and AttendedCount >= 3 → flag for USD authoring
- **Rolling sublayer:** `cortex_YYYY_MM_DD.usda`, one per day, never per pass
- **Gist emergence:** background LLM summarizes payload, authors an `over` on rolling sublayer, adds `gist` variant, switches VariantSelection to `gist`
- **Protected memory:** dedicated `cortex_protected.usda` pinned to strongest Root stack position

### 2.7 Atomicity protocol

**Sequential write, not two-phase commit.** USD authored first via `Sdf.ChangeBlock`, `UsdStage.Save()` returns, then vector index committed. The vector index is authoritative for "what exists." USD orphans from interrupted writes are benign — Pcp never traverses unreferenced prims, so they cost zero RAM and zero compute. Healing is implicit.

### 2.8 Cache warming discipline

Retrieving a memory from USD does **not** promote it to ECS. Query spam must not thrash working memory. If the agent subsequently calls `signal_attention()` on a USD-retrieved entity, only then does it hydrate into ECS as a new VOLATILE entity with `UsdLink` populated.

### 2.9 Split-brain resolution

When a concept hits in both ECS and USD:
1. ECS wins if ECS timestamp is newer than the last USD consolidation of that concept
2. USD wins otherwise

Never blanket "ECS is authoritative." Timestamp tiebreaker required.

### 2.10 Protected memory quota

Hard cap: 100 protected entries per agent. On quota full, the agent must explicitly call an unpin tool before adding more. Agents will try to flag everything as protected; the quota is the backstop.

**Phase 1:** `deposit` raises on overflow. **Phase 3:** operator-facing unpin tool, not part of the four-op API.

---

## 3. Novelty claim

Moneta is not novel as a tiered memory architecture. The agent memory subfield published heavily in Q1 2026 and the architectural pattern (hot/cold tiers, gist transitions, multi-path retrieval) is fully occupied.

Moneta is novel as a **substrate choice**. The following four claims are defensible and should be reflected in patent filings when filing begins in Stage 3:

1. **OpenUSD composition arcs as cognitive state substrate.** Mapping memory consolidation onto LIVRPS resolution order such that sublayer stack position implicitly encodes decay priority, and stronger arcs naturally serve higher-fidelity state.

2. **USD variant selection as fidelity LOD primitive.** Detail → gist variant transitions authored as `over` specs on rolling sublayers, with `VariantSelection` acting as the runtime cursor between episodic and semantic representations of a single concept prim.

3. **Pcp-based resolution as implicit multi-fidelity fallback.** Using UsdStage's composition engine to automatically serve the highest surviving fidelity variant without explicit routing logic.

4. **Protected memory as root-pinned strong-position sublayer.** Non-decaying state implemented as a dedicated sublayer at the strongest Root stack position, such that protection semantics fall out of composition resolution rather than runtime checks.

These four claims do not overlap with any Q1 2026 agent memory paper because none of them use a composition-based substrate. The domain impedance mismatch between VFX pipeline engineering and AI agent research is the moat.

---

## 4. Phased build sequence

Three phases, hard decision gates between them. Phase 1 begins immediately. Phases 2 and 3 are gated on their predecessors.

### Phase 1 — ECS + Four-Op API (mock USD target)

**Goal:** Working hot substrate with zero USD dependency. Standalone memory system that would function correctly even if Phase 3 never shipped.

**Deliverables:** See §6 role assignments for breakdown.

**Gate to Phase 2:**
- All four ops working end-to-end
- Decay math verified against reference implementation
- Shadow index consistent under simulated load
- Mock consolidation log shows stable selection behavior under test load (not pruning everything, not pruning nothing)
- Full unit test suite green
- Documentation in sync

**Phase 1 is complete when an agent can run a 30-minute synthetic session producing realistic deposit/query/attention patterns and the system survives it.**

### Phase 2 — USD Benchmark

**Goal:** Measure the lock and rebuild tax under realistic accumulated load, producing decision-gate numbers that determine Phase 3 integration depth.

**Deliverables:**
- `usd_metabolism_bench_v2.py` with fixes applied per Round 3:
  - Reader and writer lock scopes separated where possible
  - Pcp rebuild measured as a distribution, not a single sample
  - Real disk path via `Save()`, not anonymous in-memory layers
  - Small batches use small stages, not inflated baselines
  - `shadow_index_commit_ms ∈ [5, 15, 50]` — blocking sleep inside writer's lock, simulating vector DB commit
  - `accumulated_layer_size ∈ [0, 25000, 100000]` — pre-populated dummy prims before benchmark loop, measuring end-of-day stall
- CSV output with full permutation sweep
- Interpretation document mapping results to integration depth decision

**Decision gate criteria (evaluated against accumulated layer state):**

- **Green:** p95 concurrent read stall < 50ms across all realistic batch sizes with `accumulated_layer_size = 100000` and `shadow_index_commit_ms = 15`. Phase 3 implements full consolidation translator at 1Hz background ticks.
- **Yellow:** p95 stall 50–300ms under accumulated load. Phase 3 runs only during idle windows > 5s with smaller batches. **Sublayer rotation policy required** — cut rolling sublayer at ~50K prims to cap serialization tax.
- **Red:** p95 stall > 300ms under any realistic accumulated load. Phase 3 rescopes to once-per-session archival consolidation, not runtime partner.
- **Kill:** p95 > 500ms at minimum viable batch. Pivot off USD as runtime substrate. (Not expected given target hardware, but the gate exists so the project cannot get trapped in sunk-cost mode.)

### Phase 3 — USD Integration at Measured Depth

Scope scales to Phase 2 verdict. Full consolidation translator, rolling sublayer management, protected layer pinning, Sdf.ChangeBlock-wrapped writes, gist generation job queue, TfToken-safe prim naming, timestamp-based split-brain resolution. Patent filing runs in parallel during this phase.

---

## 5. Risk matrix

| # | Risk | Source | Phase | Mitigation |
|---|------|--------|-------|------------|
| 1 | Shadow vector / USD index drift | Gemini R2 §6.1 | 3 | Sequential write: USD first, vector second. Vector index authoritative. Orphans benign. No 2PC. |
| 2 | Gist generation compute contention | Gemini R2 §6.2 | 3 | Bounded job queue, fallback to keep-detail on failure, quantized local LLM on background GPU |
| 3 | TfToken registry OOM | Gemini R2 §6.3 | 3 | Writer-enforced UUID-only prim names, natural language content strictly in string attributes |
| 4 | ECS durability on crash | Claude R2.5 | 1 | WAL-lite periodic snapshot, accept small volatility window |
| 5 | Concurrency primitive gap | Claude R2.5 | 1 | Committed: append-only attention log reduced at sleep pass |
| 6 | Lock/rebuild tax exceeds assumption | Claude R2.5 | 2 | Benchmark is the gate, decision criteria are the safety net |
| 7 | Split-brain with stale ECS vs fresh gist | Claude R2.5 | 3 | Timestamp tiebreaker on concept-level merge |
| 8 | Prior art invalidation | Claude R2.5 | 0 | Novelty claim narrowed to substrate per §3 |
| 9 | Decay λ misconfigured | Claude R2.5 | 1 | Runtime tunable, start at 6-hour half-life, instrument before defaulting |
| 10 | Benchmark morning-baseline only | Gemini R3 Q3 | 2 | Accumulated layer size added as sweep parameter |
| 11 | Accumulated sublayer serialization tax | Gemini R3 Q3 | 2/3 | Sublayer rotation policy in Yellow tier |

---

## 6. Phase 1 MoE role assignments

Phase 1 is executed by an agent team operating in Mixture-of-Experts mode. Six roles, with defined contracts and handoff artifacts. Only one agent per role at a time. Roles coordinate through artifacts, not direct messaging.

### Role 1: Architect

**Responsibility:** Holds the locked spec. Reviews all other roles' output for architectural drift. Does not write implementation code. Escalates to §9 triggers when implementation surfaces spec-level surprise.

**Inputs:** This blueprint. Round 2 and Round 3 Gemini Deep Think outputs (in repo as `docs/rounds/`).

**Outputs:**
- `ARCHITECTURE.md` — locked spec document, ported from this blueprint with Moneta-specific framing
- `CLAUDE.md` — repo-level context for Claude Code sessions, including substrate conventions shared with Octavius
- PR review comments on all other roles' work, focused on spec conformance
- Escalation tickets when §9 triggers fire

**Does not:**
- Write production code
- Make unilateral changes to the four-op API, decay math, or concurrency primitive
- Expand scope beyond Phase 1

**Handoff contract:** Architect's `ARCHITECTURE.md` must exist before any other role begins. All other roles depend on it as their source of truth.

---

### Role 2: Substrate Engineer

**Responsibility:** Implements the ECS core, decay function, and four-op API. This is the foundation everything else sits on.

**Inputs:** `ARCHITECTURE.md` from Architect.

**Outputs:**
- `src/moneta/ecs.py` — flat ECS, struct-of-arrays or DataFrame-backed
- `src/moneta/decay.py` — lazy exponential decay, runtime-tunable λ
- `src/moneta/api.py` — the four operations: `deposit`, `query`, `signal_attention`, `get_consolidation_manifest`
- `src/moneta/types.py` — `Memory`, `EntityState`, enums
- `src/moneta/attention_log.py` — append-only log, sleep-pass reducer

**Does not:**
- Touch persistence, vector indices, consolidation, or any `pxr` imports
- Write tests (that is Test Engineer's job — Substrate Engineer writes minimal smoke checks only)

**Handoff contract:** API must be importable and the four operations must return correctly typed results (even if downstream is mocked) before Persistence Engineer and Consolidation Engineer begin their work. The API is the handoff surface.

---

### Role 3: Persistence Engineer

**Responsibility:** Shadow vector index, WAL-lite durability, sequential-write discipline. Makes sure that crashes do not lose unconsolidated state and that the vector index stays consistent with whatever the source of truth is.

**Inputs:** `ARCHITECTURE.md`, Substrate Engineer's API and types.

**Outputs:**
- `src/moneta/vector_index.py` — FAISS or LanceDB wrapper (choose one; recommend LanceDB for simpler persistence story, but justify in code comment)
- `src/moneta/durability.py` — WAL-lite snapshot logic, periodic flush, restart hydration
- `src/moneta/sequential_writer.py` — wraps the USD-first, vector-second discipline *even though Phase 1 has no USD*, using the mock target as the USD side. This ensures Phase 3's real USD integration drops in cleanly.

**Does not:**
- Implement the actual USD writes (Phase 3)
- Build consolidation logic (that is Consolidation Engineer)

**Handoff contract:** Vector index must accept deposits from the four-op API and return query results. Durability layer must survive a kill -9 with no more than the last 30 seconds of volatile state lost.

---

### Role 4: Consolidation Engineer

**Responsibility:** Mock consolidation target, selection criteria, manifest generation. Phase 1 does not write to USD, but it does produce a structured log of what it *would* write, using the exact shape the real consolidation translator will use in Phase 3.

**Inputs:** `ARCHITECTURE.md`, Substrate Engineer's ECS, Persistence Engineer's sequential writer.

**Outputs:**
- `src/moneta/consolidation.py` — sleep pass trigger, selection criteria (prune/stage), manifest builder
- `src/moneta/mock_usd_target.py` — emits structured JSON logs of intended USD authoring operations. Log format must match what Phase 3's real authoring code will consume as its input, so Phase 3 is a drop-in replacement.
- `src/moneta/manifest.py` — `get_consolidation_manifest` implementation

**Does not:**
- Call `pxr` or author real USD
- Make LLM calls for gist generation (Phase 3)
- Tune selection thresholds (that is empirical work in Phase 1 load testing)

**Handoff contract:** Mock target must produce a manifest that a hypothetical Phase 3 USD writer could consume without transformation. Test Engineer uses this to verify selection behavior is sane under load.

---

### Role 5: Test Engineer

**Responsibility:** Unit and integration tests for all other roles' output. Also builds the synthetic session harness that Phase 1's completion gate depends on.

**Inputs:** Everything from Architect, Substrate, Persistence, Consolidation.

**Outputs:**
- `tests/unit/` — decay math reference, attention log reducer, selection criteria, API contract tests
- `tests/integration/` — end-to-end deposit → query → attention → consolidation flow
- `tests/load/synthetic_session.py` — 30-minute synthetic session harness with realistic patterns (research burst, conversation, context switch, recall, consolidation cycles)
- `tests/conftest.py` — shared fixtures

**Does not:**
- Write implementation code
- Modify other roles' source files

**Handoff contract:** Phase 1 is complete when the synthetic session harness runs to completion without error and selection behavior over the 30 minutes is within documented expected bounds.

---

### Role 6: Documentarian

**Responsibility:** Keeps `README.md`, `MONETA.md` (this document, as it evolves), `CLAUDE.md`, and inline docstrings in sync with what is actually in the repo. Runs continuously throughout Phase 1, not as a final pass.

**Inputs:** All other roles' outputs, as they land.

**Outputs:**
- `README.md` — project identity, install, quickstart, link to ARCHITECTURE.md
- `docs/api.md` — four-op API reference with usage examples
- `docs/decay-tuning.md` — λ tuning guide with curves from load tests
- `docs/substrate-conventions.md` — shared conventions with Octavius (UUID prim naming, LIVRPS priority discipline, stage-as-interface principle)
- Inline docstrings in all public modules

**Does not:**
- Write code
- Make architectural decisions

**Handoff contract:** Documentation must never lag implementation by more than one PR. If a feature lands without docs, the Documentarian opens a blocking review.

---

### Role dependency graph

```
Architect (ARCHITECTURE.md)
    │
    ▼
Substrate Engineer (ECS, decay, API, attention log)
    │
    ├─────────────────┬──────────────────┐
    ▼                 ▼                  ▼
Persistence      Consolidation      Test Engineer
(vector, WAL,    (mock target,      (unit tests
sequential       selection,         start early,
writer)          manifest)          integration
                                    after handoffs)
    │                 │                  │
    └─────────────────┴──────────────────┘
                      │
                      ▼
              Test Engineer
         (integration + synthetic session)
                      │
                      ▼
                Phase 1 complete

Documentarian runs continuously across all roles.
```

**Critical path:** Architect → Substrate → (Persistence ∥ Consolidation) → Test integration → Phase 1 complete

**Parallelism:** Persistence and Consolidation run in parallel after Substrate's handoff. Documentarian runs continuously. Test Engineer writes unit harnesses early, plugs them in as pieces land.

---

## 7. Non-goals (explicit scope limits)

Phase 1 does not include any of the following. Agent teams attempting to build these will be reverted:

- Any `pxr`, `Usd`, `Sdf`, or `Pcp` imports
- Real USD authoring, variant creation, or sublayer management
- Gist generation via LLM calls
- Multi-agent shared stage coordination (that is Octavius territory)
- Cross-session USD hydration at cold start
- Cognitive Twin integration
- Cognitive Bridge MCP server implementation
- Benchmark work (that is Phase 2)
- Patent filing (that is Stage 3, parallel to Phase 3 build)
- Renaming, rebranding, or re-scoping
- Framework edits to this blueprint without §9 escalation
- Adding a fifth operation to the agent API

---

## 8. Substrate conventions shared with Octavius

Both Moneta and Octavius write to USD stages. Both inherit the substrate thesis. The following conventions are shared and must not drift between projects:

1. **Prim naming is UUID-based.** Never construct prim names from natural language content. Natural language goes inside string attribute values. This avoids the TfToken registry OOM trap.
2. **LIVRPS is the priority primitive.** Stronger arcs override weaker arcs. Stack position encodes priority. Use this intentionally, not incidentally.
3. **The stage is the interface.** Cross-project composition happens at the USD stage layer, not the Python code layer. Moneta and Octavius should be able to compose on a shared stage without importing each other's Python modules.
4. **Strong-position sublayers for invariants.** Protected memory in Moneta, critical coordination state in Octavius — both live in dedicated sublayers pinned to the strongest Root stack position.
5. **Sdf.ChangeBlock for batch writes.** Always. No exceptions. Python-side notification fan-out dominates otherwise.

These conventions should be ported into Moneta's `docs/substrate-conventions.md` and cross-linked from Octavius's equivalent document.

---

## 9. Gemini Deep Think escalation triggers

Moneta's build is operating under the assumption that Rounds 1 through 3 of Gemini Deep Think closed cleanly. The following conditions fire a Round 4 escalation. When any trigger fires, stop implementation and draft a scoping brief before proceeding.

**Trigger 1 (primary):** Phase 2 benchmark results land in the ambiguous zone — p95 stalls in the 200–400ms range under accumulated load, or `shadow_index_commit_ms × accumulated_layer_size` interactions do not map cleanly to Green/Yellow/Red. Clean numbers do not require Gemini. Ambiguous numbers do.

**Trigger 2 (emergency):** Phase 1 or Phase 3 implementation surfaces an architectural assumption that turns out wrong. Specifically: the four-op API needs a fifth operation; the append-only attention log has a failure mode not anticipated in Round 2; the lazy decay math produces a pathology under realistic load; the sequential-write atomicity pattern from Round 3 does not cover a discovered edge case. Python debugging and implementation bugs are not triggers. **Spec-level surprise** is a trigger.

**Trigger 3 (distant):** Phase 3 USD integration hits an atomicity edge case the sequential-write pattern does not cover.

**Escalation protocol:** When a trigger fires, the Architect role drafts a Round 4 brief following the format of Round 3. Brief goes to Joseph Ibrahim for review before being sent to Gemini Deep Think. No implementation proceeds on the affected subsystem until the round closes.

---

## 10. Lineage

- **Round 1** (previous session, Claude + Joseph Ibrahim): Initial scoping brief authored for Gemini Deep Think. Adversarial framing stripped, 24-48 hour shipping window specified, section 2.3 (consolidation translator) and section 4 (prior art) flagged as load-bearing.
- **Round 2** (Gemini Deep Think): Architectural scoping document with four-op API, ECS/USD split, lazy decay math, consolidation translator spec, sizing benchmark, prior art verification pass, and three scoping-phase risks.
- **Round 2.5** (Claude review): Prior art section identified as overconfident; Q1 2026 wave (MemFly, HyMem, VimRAG, CogitoRAG, From Verbatim to Gist, HippoRAG) surfaced as closer adjacent work than Gemini located. Benchmark flagged with four distorting issues. Four implementation blockers added (λ, durability, concurrency primitive, gist queue).
- **Round 3** (Gemini Deep Think): Narrowed novelty claim confirmed. Key insight: four substrate claims are *structural not temporal*, decoupling patent validity from benchmark results. Benchmark gaps identified: shadow index commit time and accumulated layer serialization. Atomicity protocol replaced with sequential-write pattern.
- **Round 3 Closure** (Claude + Joseph Ibrahim): Plan validated, amendments applied, build sequence locked. Project named Moneta. Repository separated from Octavius. Phase 1 authorized.

---

## 11. Next action

Phase 1 begins. Architect role claims first, delivers `ARCHITECTURE.md`, and Substrate Engineer follows. Documentarian runs parallel to all.

When Phase 1 completion gate is met — synthetic 30-minute session runs clean, selection behavior stable, all tests green — update this document's status header and begin Phase 2.

**Do not re-open Round 3 decisions. Do not expand Phase 1 scope. Do not skip the Documentarian. Escalate per §9 when triggers fire.**

Ship Moneta.
