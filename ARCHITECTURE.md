# Moneta — Architecture (Locked Spec)

**Status:** LOCKED. This document is the source of truth for all implementation roles.
**Derived from:** `MONETA.md` (build blueprint), §1–§2.
**Lineage:** Round 1 scoping brief → Round 2 architectural spec (Gemini Deep Think) → Round 3 plan validation (Gemini Deep Think) → this document.
**Escalation:** Any proposed change to the locked foundations below must follow MONETA.md §9. Do not patch silently.

---

## 0. How to read this document

ARCHITECTURE.md is the *spec*. MONETA.md is the *blueprint* — it carries the narrative, phasing, lineage, and risk matrix. When the two disagree, MONETA.md wins for history and phasing; ARCHITECTURE.md wins for the interface contract. If a real contradiction is found, it is a §9 trigger, not an edit.

Roles depend on this document as follows:

- **Substrate Engineer** implements §2–§5 to the letter.
- **Persistence Engineer** implements §7 (atomicity) and §8 (cache warming) against the interfaces in §2–§3.
- **Consolidation Engineer** implements §6 as a mock target whose log shape matches the Phase 3 authoring contract.
- **Test Engineer** verifies every numbered clause below has at least one test citing its clause number.

---

## 1. System identity

Moneta is a memory substrate for LLM agents. It exposes a four-operation agent API and hides every internal mechanism. Internals are: a flat, vectorizable ECS hot tier; a lazy exponential decay function; an append-only attention log; a shadow vector index; and (in Phase 3) an OpenUSD cold tier whose composition engine is used as a cognitive-state substrate.

Moneta is the memory sibling to **Octavius**, the coordination sibling. Both inherit the same parent thesis: OpenUSD's composition engine is a general-purpose prioritization-and-visibility substrate for agent state that is not geometry. The two projects share substrate conventions (`docs/substrate-conventions.md`); they do not share Python code.

---

## 2. The four-operation API (locked — MONETA.md §2.1)

The entire agent-facing surface consists of exactly these four operations. No fifth operation may be added without §9 escalation.

```python
def deposit(payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID
def query(embedding: List[float], limit: int = 5) -> List[Memory]
def signal_attention(weights: Dict[UUID, float]) -> None
def get_consolidation_manifest() -> List[Memory]
```

Agents have zero knowledge of ECS, USD, vector indices, decay, or consolidation. All internals are implementation concerns.

**Conformance:** `src/moneta/api.py` must export exactly these four callables with exactly these signatures. Import-time introspection is a Test Engineer harness.

### 2.1 Harness-level bootstrap (not part of the agent API)

The module also exposes `init()`, `run_sleep_pass()`, `smoke_check()`, and `MonetaConfig`. **These are not part of the agent-facing four-op surface.** They are harness-level entry points used by test fixtures, operator scripts, and Consolidation Engineer's sleep-pass scheduler. Agents never call them; fifth-op rules do not apply.

Ruling B (Pass 2 closure) locked this split: expanding the module's callable surface with bootstrap helpers does not constitute adding a fifth agent operation, because the agent-facing surface is defined by what an agent calls at runtime, not by what is importable from the module.

---

## 3. Hot substrate schema (locked — MONETA.md §2.2)

The hot tier is flat, vectorizable, struct-of-arrays or DataFrame-backed. An entity is a row; each component field below is a column.

| Field | Type | Purpose |
|---|---|---|
| `EntityID` | UUID | Primary key. |
| `SemanticVector` | float array | Used for O(1) miss detection on queries. |
| `Payload` | str | Uncompressed content. |
| `Utility` | float ∈ [0.0, 1.0] | Sole target of decay. |
| `AttendedCount` | int | Cumulative reinforcement counter. Independent of `Utility`. |
| `ProtectedFloor` | float, default 0.0 | Per-entity decay floor. |
| `LastEvaluated` | timestamp | Wall-clock of last decay evaluation. |
| `State` | enum | One of `VOLATILE`, `STAGED_FOR_SYNC`, `CONSOLIDATED`. |
| `UsdLink` | `SdfPath \| None` | Populated only when the entity was hydrated from USD. **Phase 1 treats this as an opaque tag; no `pxr` import is permitted.** |

**Locked invariant:** `AttendedCount` and `Utility` are independent signals. Consolidation selection (§6) uses both. Do not collapse one into the other.

---

## 4. Decay function (locked — MONETA.md §2.3)

Lazy memoryless exponential. Evaluated at access time only. **Never** on a background tick or 60 Hz loop.

```
U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))
```

**λ is runtime-configurable.** Starting value: half-life of 6 hours. Tuning range: 1 minute to 24 hours. λ must be instrumented and logged. **A production default must not be committed until Phase 1 load testing produces curves.**

Evaluation points (exactly three):

1. Immediately before context retrieval (inside `query`).
2. Immediately after the attention-write phase (inside the attention-log reducer).
3. During the consolidation scan (inside the sleep pass).

**Locked invariant:** No fourth evaluation point. No scheduled decay task. A test asserts the absence of a fourth call site.

---

## 5. Attention interface (locked — MONETA.md §2.4)

Explicit agent signaling only. No KV cache extraction. No post-hoc prompt analysis.

When `signal_attention(weights)` is called, each entity referenced in `weights` is updated as:

```
Utility       = min(1.0, Utility + weights[UUID])
AttendedCount = AttendedCount + 1
LastEvaluated = now()
```

Writes go to the append-only attention log (§5.1). The reducer at the sleep pass applies them and clears the log.

### 5.1 Concurrency primitive (locked — MONETA.md §2.5)

**Append-only attention log, reduced at sleep pass.** Not per-entity spinlocks. Not CAS loops. The log is lock-free, eventually consistent, and has the simplest failure mode. The sleep pass reads the log, applies reductions to the ECS, then clears the log.

**Locked invariant:** No per-entity locking primitive may be introduced. If a failure mode is found that the append-log pattern cannot absorb, it is a §9 Trigger 2 (spec-level surprise), not a local fix.

---

## 6. Consolidation mechanics (Phase 3 target, mocked in Phase 1 — MONETA.md §2.6)

Phase 1 does not author USD. Phase 1's `mock_usd_target` emits structured log entries whose shape must match what Phase 3's real authoring code will consume as input. This guarantees Phase 3 is a drop-in replacement for the mock.

**Trigger conditions:**

- ECS volatile count exceeds `MAX_ENTITIES`, **or**
- Inference queue idle > 5000 ms.

**Selection criteria:**

- `Utility < 0.1 AND AttendedCount < 3` → **prune** (delete entirely).
- `Utility < 0.3 AND AttendedCount >= 3` → **stage for USD authoring**.

**Authoring targets (Phase 3 reference; Phase 1 mock shape must match):**

- **Rolling sublayer:** `cortex_YYYY_MM_DD.usda`, one per day, never per pass.
- **Gist emergence:** background LLM summarizes payload, authors an `over` on the rolling sublayer, adds a `gist` variant, switches `VariantSelection` to `gist`.
- **Protected memory:** `cortex_protected.usda`, pinned to the strongest Root stack position.

**Phase 1 Consolidation Engineer constraint:** Do not tune the 0.1 / 0.3 / 3 thresholds. They are the Round 2 committed defaults and will be empirically adjusted during Phase 1 load testing by Test Engineer's synthetic session harness.

---

## 7. Atomicity protocol (locked — MONETA.md §2.7)

**Sequential write, not two-phase commit.**

1. USD is authored first via `Sdf.ChangeBlock`. `UsdStage.Save()` returns.
2. The vector index is committed second.
3. The vector index is authoritative for "what exists."

USD orphans from interrupted writes are benign: Pcp never traverses unreferenced prims, so they cost zero RAM and zero compute. Healing is implicit.

**Phase 1 applicability:** The mock USD target stands in for step 1. Persistence Engineer's `sequential_writer.py` wraps both steps so that Phase 3 replaces step 1 without touching the ordering discipline.

**Locked invariant:** No 2PC. No rollback on vector-index failure. The ordering is the protocol.

### 7.1 Shadow vector index dim-homogeneity invariant

Once the first embedding is upserted into the shadow vector index, its dimension is locked for the lifetime of the instance. Subsequent upserts with a mismatched dimension raise `ValueError`.

This is a Phase 1 Persistence Engineer invariant — it is *not* specified in MONETA.md §2.7, and was added during Phase 1 Pass 3 (Persistence Engineer judgment call #2, approved in Pass 4). Rationale: a shadow vector index cannot meaningfully rank vectors produced by different embedders, and silently accepting mixed dimensions would produce subtly-wrong query rankings. Callers that need to switch embedders must construct a fresh `VectorIndex` — typically via `api.init()`, which replaces the module-level state.

**Locked invariant:** the vector index rejects dim-mismatched upserts. Dim-homogeneity is enforced at upsert time, not at query time, and the error is a hard `ValueError` — not a silent skip.

---

## 8. Cache warming discipline (locked — MONETA.md §2.8)

Retrieving a memory from USD does **not** promote it to the ECS. Query spam must not thrash working memory.

**Promotion rule:** if the agent subsequently calls `signal_attention()` on a USD-retrieved entity, the entity hydrates into the ECS as a new `VOLATILE` row with `UsdLink` populated. Until that attention signal arrives, the USD row is served in-place without mutation of the hot tier.

---

## 9. Split-brain resolution (locked — MONETA.md §2.9)

When a concept hits in both ECS and USD:

1. **ECS wins** if the ECS timestamp is newer than the last USD consolidation of that concept.
2. **USD wins** otherwise.

No blanket "ECS is authoritative" rule. The timestamp tiebreaker is required.

---

## 10. Protected memory quota (locked — MONETA.md §2.10)

Hard cap: **100 protected entries per agent.** On quota full, the agent must explicitly call an unpin tool before adding more. The quota is a backstop against agents flagging everything as protected.

**Note:** The unpin tool is not part of the four-op API. It is a Phase 3 operator-facing tool. Phase 1 enforces the quota at deposit time and raises if a `protected_floor > 0` deposit would exceed 100.

---

## 11. Phase 1 scope boundary

Phase 1 ships:

- Flat ECS hot tier (§3)
- Lazy decay (§4)
- Four-op API (§2)
- Append-only attention log and sleep-pass reducer (§5.1)
- Shadow vector index + WAL-lite durability
- Sequential-writer wrapper around a mock USD target (§7 discipline without `pxr`)
- Mock consolidation target producing a manifest log in Phase 3 shape (§6)
- Synthetic 30-minute session harness as the completion gate

Phase 1 does **not** ship any of the items in MONETA.md §7 (non-goals). In particular: **no `pxr`, `Usd`, `Sdf`, or `Pcp` imports.** The `UsdLink` field in §3 is an opaque tag in Phase 1.

---

## 12. Role handoff surfaces

| From → To | Surface |
|---|---|
| Architect → all | This document. |
| Substrate → Persistence, Consolidation | `src/moneta/api.py` (four-op), `src/moneta/types.py` (`Memory`, `EntityState`, enums), `src/moneta/ecs.py` (read interface). |
| Substrate → Consolidation | `src/moneta/attention_log.py` reducer interface. |
| Persistence → Consolidation | `src/moneta/sequential_writer.py` (USD-first, vector-second ordering). |
| Consolidation → Phase 3 | Mock-target log shape in `src/moneta/mock_usd_target.py`. |
| All → Test Engineer | Importable modules under `src/moneta/`. |

---

## 13. Anticipated module map

Per MONETA.md §6 role outputs, the Phase 1 module layout is:

```
src/moneta/
├── __init__.py
├── api.py                 # four-op API                        (Substrate)
├── types.py               # Memory, EntityState, enums         (Substrate)
├── ecs.py                 # flat ECS                           (Substrate)
├── decay.py               # lazy exponential                   (Substrate)
├── attention_log.py       # append-only log + reducer          (Substrate)
├── vector_index.py        # FAISS or LanceDB wrapper           (Persistence)
├── durability.py          # WAL-lite snapshot / hydrate        (Persistence)
├── sequential_writer.py   # USD-first, vector-second discipline (Persistence)
├── consolidation.py       # sleep pass, selection, trigger     (Consolidation)
├── mock_usd_target.py     # structured JSON log of would-be USD writes (Consolidation)
└── manifest.py            # get_consolidation_manifest impl    (Consolidation)
```

No other files may be added to `src/moneta/` in Phase 1 without Architect review.

---

## 14. Escalation protocol (MONETA.md §9)

Three triggers:

1. **Primary** — Ambiguous Phase 2 benchmark results. (Not a Phase 1 concern.)
2. **Emergency** — Spec-level surprise. Specifically: the four-op API needs a fifth operation; the append-only attention log has a failure mode not anticipated in Round 2; lazy decay produces a pathology under realistic load; sequential-write atomicity does not cover a discovered edge case. **Python debugging and implementation bugs are not triggers. Spec-level surprise is.**
3. **Distant** — Phase 3 USD atomicity edge case.

When a trigger fires, the Architect drafts a Round 4 brief following the Round 3 format. Brief goes to Joseph Ibrahim for review before being sent to Gemini Deep Think. No implementation proceeds on the affected subsystem until the round closes.

---

## 15. Phase 3 hard rules and operational envelope

Phase 3 is USD integration at measured depth, ending at v1.0.0. It begins with real `pxr` imports at Pass 3 and ships a working consolidation translator writing to actual OpenUSD stages.

### 15.1 pxr import authorization

`pxr`, `Usd`, `Sdf`, and `Pcp` imports become legal inside `src/moneta/` starting **Phase 3 Pass 3** (real USD writer scaffolding). They remain illegal in Pass 2 (Architect re-brief) and in all test files that do not explicitly require USD. No `pxr` imports outside `src/moneta/`.

### 15.2 Operational envelope (from Phase 2 closure §3)

Phase 3 ships in **Yellow tier** with the following hard constraints, derived from the Phase 2 benchmark (243-config sweep, 52.9 min, OpenUSD 0.25.5 on Threadripper PRO 7965WX) and the interpretation session rulings in `docs/phase2-closure.md`.

**Hard constraints (enforced at build time):**

1. **Sublayer rotation at 50k prims per sublayer.** When `cortex_YYYY_MM_DD.usda` reaches 50k prims, cut a new sublayer and pin the old one in position. Rotation is the primary lever against accumulated serialization tax.
2. **Consolidation runs only during inference idle windows > 5 seconds.** Not a 1Hz background tick. Yellow-tier scheduling per Round 3.
3. **Maximum batch size per consolidation pass: 500 prims.** Half of the benchmark's worst-batch test point. Well inside the operational envelope at accumulated ≤ 50k.
4. **LanceDB shadow commit budget: ≤ 15ms p99.** The 50ms shadow_commit case is where 6/9 Red excursions live. If the 15ms budget cannot be met with LanceDB defaults, the Persistence Engineer surfaces it as a §9 Trigger 2 escalation, not a silent acceptance.

**Cost model assumptions (capacity planning):**

5. **Steady-state p95 stall: ~131ms median** (benchmark's attribute-case global mean, per Phase 2 closure Q5 ruling). This is the number Phase 3 plans against, not the optimistic bare-prim mean.
6. **Reader throughput under contention: ~41Hz achieved vs 60Hz requested** (68% of target) during worst-case consolidation windows. Readers are starved but not dead.
7. **Pcp rebuild cost: effectively free** (0.1–2.6ms across the entire sweep). Phase 3 does not need to optimize for Pcp invalidation avoidance, composition graph depth, or variant complexity caps.

### 15.3 Investigation tasks (during Phase 3 execution)

8. **Q6: Concurrent Traverse + Save safety.** Can the writer lock release after `Sdf.ChangeBlock` exits but before `Save()` returns? If safe, reduces stall by ~80% and moves the Green test point into reach. If unsafe, Phase 3 ships at constraints 1–7 unchanged. If ambiguous (USD docs silent, race detector produces intermittent warnings without deterministic failures), that is the Round 4 trigger — convene Gemini Deep Think scoped tightly to the USD concurrency question. See `docs/phase2-closure.md` §2 Q6.
9. **Per-sublayer size distribution benchmark.** Extend `usd_metabolism_bench_v2.py` with a `(primary_layer_size, secondary_layer_size)` dimension to empirically confirm the sublayer rotation hypothesis.
10. **Benchmark v3: spec-count vs semantic-type separation.** Optional, low priority. Only if Phase 3 benchmark work surfaces a reason to disambiguate more cleanly.

### 15.4 Pass structure (reference, not contract)

| Pass | Role | Deliverable |
|------|------|-------------|
| 1 | Documentarian | Orphan migration (done — commit b1803c7) |
| 2 | Architect | Re-brief: hard rules, operational envelope, agent commandments (this pass) |
| 3 | Substrate + Persistence | Real USD writer scaffolding. First `pxr` imports. Mock target kept alongside for A/B validation. |
| 4 | Consolidation + Persistence | Sublayer rotation + consolidation wiring against real USD. |
| 5 | Benchmark Engineer | Q6 thread-safety investigation (concurrent Traverse + Save). |
| 6 | Test Engineer | Integration tests + synthetic session re-run against real USD target. |
| 7 | Architect + Test Engineer | Completion gate. Tag v1.0.0. |

Human gates between every pair of consecutive passes. Pass boundaries are commit boundaries.

### 15.5 Cross-references

- **Agent discipline:** `docs/agent-commandments.md` governs all Phase 3 passes from Pass 3 onward.
- **Benchmark data:** `docs/phase2-benchmark-results.md` (analyst interpretation) and `docs/phase2-closure.md` (rulings).
- **Gemini outputs:** `docs/rounds/round-2.md` and `docs/rounds/round-3.md`.

### 15.6 Pass 5/6 update: narrow writer lock

**Authorized by:** Pass 5 Q6 investigation (commit 500b1dd). Empirical basis: 2,000 stress-test iterations, 70,010,000 concurrent prim-attribute read assertions, zero failures on OpenUSD 0.25.5.

**Change (Pass 6):** The writer lock in `src/moneta/usd_target.py` covers `Sdf.ChangeBlock` only. `layer.Save()` runs outside the lock, concurrent with readers. The sequential-write ordering from §7 is preserved: ChangeBlock completes (prims authored in-memory) → Save completes (prims durable on disk) → vector index committed. Only the reader-blocking scope changes.

**Revised cost model:** The steady-state p95 reader stall drops from ~131ms (Phase 2 attribute-case mean, §15.2 constraint #5) to a projected ~10–30ms at Moneta's operational batch sizes (≤500 prims, ≤50k accumulated). At batch=10 (typical), the stall drops to sub-1ms. These are projections from the Pass 5 narrow-lock benchmark comparison, not re-measured production numbers. The Phase 2 cost model number (131ms) is superseded for planning purposes but retained as the conservative fallback if the narrow lock is ever reverted.

**What this does NOT change:**
- §7 sequential-write ordering (locked)
- §15.2 constraints #1–#4 (sublayer rotation, idle-window scheduling, batch cap, shadow commit budget)
- The four substrate novelty claims (structural, not temporal)

### 15.7 What stays locked from Phase 1 and Phase 2

All locked invariants from §2–§10 remain in force through Phase 3. Additionally:

- 94 existing tests must stay green through every Phase 3 pass.
- Mock USD target (`mock_usd_target.py`) is retained alongside the real target through Phase 3 for A/B validation.
- Protocol-based dependency inversion in `sequential_writer.py` is the Phase 3 swap mechanism. The writer itself is not modified; the real USD target drops in via `AuthoringTarget` Protocol.
- The four substrate novelty claims (MONETA.md §3) are structural, not temporal — invariant across Green/Yellow/Red integration tiers.

---

## 16. Conformance checklist

Before Phase 1 ships, Test Engineer verifies:

- [ ] `src/moneta/api.py` exports `deposit`, `query`, `signal_attention`, `get_consolidation_manifest` with signatures matching §2 exactly (parameter names, defaults, annotations, return types).
- [ ] `Memory` type in `src/moneta/types.py` carries every field in §3.
- [ ] Decay reference test: closed-form `U_last * exp(-λ * Δt)` matches implementation to 1e-9 relative tolerance.
- [ ] Decay evaluation points: exactly three (§4). A test asserts no fourth call site.
- [ ] Attention-log reducer is lock-free (no mutex, no CAS).
- [ ] Cache-warming (§8): querying a USD-sourced entity does not mutate the ECS until `signal_attention` fires on it.
- [ ] Split-brain (§9): timestamp tiebreaker is exercised in both directions.
- [ ] Protected quota (§10): the 101st `protected_floor > 0` deposit raises.
- [ ] Sequential-writer (§7): a vector-index commit failure leaves mock-USD state intact and reports correctly.
- [ ] Synthetic 30-minute session completes with selection behavior inside documented bounds.

---

*Locked 2026-04-11. §15 added 2026-04-12 (Phase 3 Pass 2). Source: MONETA.md. Changes require MONETA.md §9 escalation.*
