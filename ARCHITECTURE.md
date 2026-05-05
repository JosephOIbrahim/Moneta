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

The entire agent-facing surface consists of exactly these four operations, exposed as **methods on a `Moneta(config)` handle**. No fifth public method on the agent surface may be added without §9 escalation.

```python
class Moneta:
    def deposit(self, payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID
    def query(self, embedding: List[float], limit: int = 5) -> List[Memory]
    def signal_attention(self, weights: Dict[UUID, float]) -> None
    def get_consolidation_manifest(self) -> List[Memory]
```

Agents have zero knowledge of ECS, USD, vector indices, decay, or consolidation. All internals are implementation concerns.

**Round 4 closure (Ruling 1):** the v1.1.0 surgery converted the pre-existing module-level free functions into methods on a per-`storage_uri` handle. Round 4 ratified the handle pattern as the canonical surface — the pre-v1.1.0 module-level singleton conflated the substrate (a per-`storage_uri` handle) with the module (singleton by definition) and prevented an agent process from holding more than one substrate at a time. The four-op type signatures are locked verbatim from MONETA.md §2.1; the dispatch (method vs. free function) is implementation. See `docs/rounds/round-4.md` Ruling 1.

**Conformance:** `Moneta` must expose exactly these four methods with these signatures. Import-time introspection is a Test Engineer harness.

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

**Round 4 closure (Ruling 2 — Pinning):** Selection criteria do not run against entities with `protected_floor > 0`. The decay clamp pins `utility ≥ floor` and the attention-write clamp (`apply_attention`) does the same, so the staging gate (`utility < 0.3`) is unreachable for any entity with `protected_floor ≥ 0.3` by construction. Protected memories are pinned in the hot tier; their consolidation to USD is the explicit Phase 3 unpin tool's responsibility, not the automatic selection. See `docs/rounds/round-4.md` Ruling 2.

**Authoring targets (Phase 3 reference; Phase 1 mock shape must match):**

- **Rolling sublayer:** `cortex_YYYY_MM_DD.usda`, one per day, never per pass.
- **Gist emergence:** background LLM summarizes payload, authors an `over` on the rolling sublayer, adds a `gist` variant, switches `VariantSelection` to `gist`.
- **Protected memory:** `cortex_protected.usda`, pinned to the strongest Root stack position. Routed only by the explicit Phase 3 unpin tool, never by automatic selection (Ruling 2).

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

This is a Phase 1 Persistence Engineer invariant — it is *not* specified in MONETA.md §2.7, and was added during Phase 1 Pass 3 (Persistence Engineer judgment call #2, approved in Pass 4). Rationale: a shadow vector index cannot meaningfully rank vectors produced by different embedders, and silently accepting mixed dimensions would produce subtly-wrong query rankings. Callers that need to switch embedders must construct a fresh `Moneta(config)` handle.

**Locked invariant:** the vector index rejects dim-mismatched upserts. Dim-homogeneity is enforced at upsert time, not at query time, and the error is a hard `ValueError` — not a silent skip.

### 7.2 Dual-authority across restart (Round 4 closure, Ruling 3)

The vector index is **runtime-authoritative** within a session: the sequential-write protocol's no-2PC argument relies on vector being the last writer, so an interrupted deposit (ECS add succeeded, vector upsert raised) leaves a benign "doesn't exist" state at runtime. The vector wins.

Across a **restart boundary**, the ECS snapshot in `durability.py` is the durable record; the vector index begins as a faithful shadow reconstructed from the hydrated ECS. Within-session authority is restored once construction completes.

**Locked invariant:** the §7 atomicity guarantee is a within-session property. The hydrate path's ECS-first ordering does NOT degrade the within-session no-2PC argument; it is a deliberate consequence of Phase 1's in-memory shadow-only `VectorIndex`. Phase 2 LanceDB persistence is the path to making vector authoritative across restart, if needed.

A deposit that raised mid-construction in a prior session re-emerges in the new session as a consistent ECS row + vector record (the vector is rebuilt to match the ECS). There is no entity in a torn state across restart.

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

**Default cap: 100 protected entries per substrate handle. Per-handle override permitted up to a ceiling of 1000.** On quota full, the agent must explicitly call an unpin tool before adding more. The quota is a backstop against agents flagging everything as protected.

**Round 4 closure (Rulings 5–6):** "Per agent" is disambiguated to "per substrate handle." A substrate is identified by `storage_uri`; each `Moneta(config)` handle is distinct, with its own quota. An agent process holding multiple handles on distinct URIs gets multiple independent quotas — this is by design (Ruling 6). The override is bounded: `MonetaConfig.quota_override` outside `1 ≤ q ≤ 1000` raises `ValueError` at construction (Ruling 5). See `docs/rounds/round-4.md`.

**Note:** The unpin tool is not part of the four-op API. It is a Phase 3 operator-facing tool. Phase 1 enforces the quota at deposit time and raises `ProtectedQuotaExceededError` if a `protected_floor > 0` deposit would exceed `MonetaConfig.quota_override`. The protected-quota check is held under a per-handle deposit lock so concurrent protected deposits at quota-1 cannot both succeed.

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

**Authorized by:** Pass 5 Q6 investigation (commit 500b1dd). Empirical basis: 2,000 stress-test iterations, 70,010,000 concurrent prim-attribute read assertions, zero failures on OpenUSD 0.25.5. See `docs/patent-evidence/pass5-usd-threadsafety-review.md`.

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

- [ ] `src/moneta/api.py` exposes `Moneta` with public methods `deposit`, `query`, `signal_attention`, `get_consolidation_manifest` whose signatures match §2 exactly (parameter names, defaults, annotations, return types). No fifth public agent-facing method on `Moneta`.
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

## 17. Handle exclusivity model (Round 4 closure, Ruling 4)

The v1.1.0 surgery introduced a per-process exclusivity registry. Round 4 ratified this as a locked architectural element. The five sub-clauses below specify the model.

### 17.1 Registry and lifecycle

`src/moneta/api.py` holds a module-level `_ACTIVE_URIS: set[str]` of currently-held storage URIs. Two live `Moneta(config)` handles cannot share the same `storage_uri` within one process. Construction does **check-then-add**: if `config.storage_uri ∈ _ACTIVE_URIS`, construction raises `MonetaResourceLockedError`; otherwise the URI is added to the set and construction proceeds. Release happens at `Moneta.close()` (and via `__exit__` when used as a context manager) — the URI is `discard`-ed so it may be re-acquired by a fresh handle.

If a partial construction raises after the URI was added, the `try/except BaseException` block in `__init__` discards the URI before re-raising, so the lock is never leaked.

### 17.2 TOCTOU under CPython GIL

Under CPython 3.11 / 3.12 with the GIL enabled, `set.__contains__` and `set.add` are atomic at the bytecode level. The check-then-add is therefore sequential within a process: two concurrent `Moneta(config)` constructions on the same URI cannot both observe `uri ∉ _ACTIVE_URIS` and both add. The losing thread observes the winning thread's add and raises.

### 17.3 Behavior under `fork()`

The child inherits the parent's `_ACTIVE_URIS` set. If both parent and child attempt to construct on the same URI, both raise `MonetaResourceLockedError` against their respective copies — but they have separate sets, so cross-process exclusion is **not** enforced by `_ACTIVE_URIS`. Cross-process exclusion is the bridge layer's concern (`bridge/`, flock-based, see PR #1 on `claude/audit-moneta-api-nvUfG`).

### 17.4 Behavior under PEP 703 free-threading

The GIL atomicity argument in §17.2 does not hold under free-threaded CPython. A check-then-add race becomes possible across threads. Migration to PEP 703 is a §9 Trigger 2 (spec-level surprise): the registry would need an explicit `threading.Lock` around the check-then-add critical section. Phase 1 explicitly targets the GIL-enabled CPython model; do not silently rely on PEP 703 semantics.

### 17.5 SIGTERM cleanup ordering

When `SIGTERM` arrives mid-`with` block, Python's signal handling runs `__exit__` as part of the bytecode interpreter's frame unwind. `Moneta.__exit__` calls `close()`, which calls `_ACTIVE_URIS.discard(self.config.storage_uri)`. If `__exit__` itself raises (e.g. durability flush failure), `discard` still runs because it lives in the `finally` portion of the cleanup. The lock is never leaked across a clean SIGTERM.

If the process is killed with `SIGKILL` (`kill -9`), Python never runs `__exit__`. The `_ACTIVE_URIS` registry is process-local and dies with the process; the next process starts with an empty registry. The bridge layer's flock is the path to surviving `kill -9` for cross-process exclusion.

---

*Locked 2026-04-11. §15 added 2026-04-12 (Phase 3 Pass 2). §7.2 and §17 added 2026-05-04 (Round 4 closure). Source: MONETA.md. Changes require MONETA.md §9 escalation.*
