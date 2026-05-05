# STATE_OF_MONETA

Read-only audit. No proposals. No roadmap. The current gap, on paper.

**HEAD:** `83549dd` (main · 2026-05-05).
**Scope:** Moneta repo at `C:\Users\User\Moneta`.
**Inputs read:** `README.md`, `MONETA.md`, `ARCHITECTURE.md`, `CLAUDE.md`,
`docs/*.md` (api, decay-tuning, substrate-conventions, agent-commandments,
testing, CLAUDE-phase3, phase2-benchmark-results, phase2-closure,
phase3-closure, pass5-q6-findings), `docs/rounds/{1,2,3}.md`,
`SCOUT_MONETA_v0_3.md`, `MISSION_scout_moneta_v0_3.md`,
surgery records (`SURGERY_complete*.md`, handoffs, execution constitutions,
deep-think briefs). No `CHANGELOG.md` exists at repo root.
Source tree walked: `src/moneta/*.py` (13 modules), `schema/`, `tests/`,
`scripts/`.

---

## 1. CURRENT STATE

What is actually in the codebase.

### 1.1 Public API surface

The entire agent-facing surface is the four-op API plus a handle and a
harness operator. Source: `src/moneta/__init__.py`.

| Name | Kind | File:line | Notes |
|---|---|---|---|
| `Moneta` | class (handle) | `api.py:177` | Constructed via `Moneta(MonetaConfig)`. Context-manager protocol (`__enter__/__exit__/close`) at `api.py:293/296/300`. |
| `MonetaConfig` | frozen kw-only dataclass | `api.py:91` | `storage_uri` is the only required field; `ephemeral()` factory at `api.py:143`. |
| `Moneta.deposit` | method | `api.py:328` | Four-op #1. |
| `Moneta.query` | method | `api.py:379` | Four-op #2. |
| `Moneta.signal_attention` | method | `api.py:419` | Four-op #3. |
| `Moneta.get_consolidation_manifest` | method | `api.py:438` | Four-op #4. |
| `Moneta.run_sleep_pass` | method | `api.py:452` | Harness-level operator (not part of the four-op contract). |
| `Memory` | frozen dataclass | `types.py:32` | Nine fields: `entity_id`, `payload`, `semantic_vector`, `utility`, `attended_count`, `protected_floor`, `last_evaluated`, `state`, `usd_link`. |
| `EntityState` | IntEnum | `types.py:18` | Three members: `VOLATILE=0`, `STAGED_FOR_SYNC=1`, `CONSOLIDATED=2`. No `PRUNED` member. |
| `MonetaResourceLockedError` | exception | `api.py:74` | Subclass of `RuntimeError`. |
| `ProtectedQuotaExceededError` | exception | `api.py:65` | Subclass of `RuntimeError`. |
| `smoke_check` | function | `api.py:480` | End-to-end self-test. |
| `_ACTIVE_URIS` | module-level `set[str]` | `api.py:169` | Process-level URI exclusivity registry. Not exported. |

### 1.2 Hot tier (in-RAM)

| Module | Class | File | What it is |
|---|---|---|---|
| ECS | `ECS` | `ecs.py:37` | Struct-of-arrays. Nine parallel Python lists (`_ids`, `_payloads`, `_embeddings`, `_utility`, `_attended`, `_protected_floor`, `_last_evaluated`, `_state`, `_usd_link`) plus an `_id_to_row: dict[UUID, int]` index. Single-writer per docstring (`ecs.py:14-18`). |
| Decay | `decay_value` | `decay.py:48` | Pure function: `max(floor, U * exp(-λ * Δt))` with a non-negative-Δt clamp. Constants: `DEFAULT_HALF_LIFE_SECONDS = 6 * 3600` at `decay.py:31`. |
| Attention log | `AttentionLog` | `attention_log.py:56` | Append (`append`, line 71-73) + drain-by-swap (`drain`, line 75-83) on a Python `list` (`self._buffer`). **Not a deque.** No `maxlen`. Constructor (`__init__`, line 63-69) raises `RuntimeError` under `sys._is_gil_enabled() is False`. |
| Vector index (shadow) | `VectorIndex` | `vector_index.py:63` | `dict[UUID, tuple[list[float], EntityState]]`. Linear-scan cosine. In-memory only; `vector_persist_path` config field is logged-and-ignored at `vector_index.py:75-81`. |

### 1.3 Cold tier (USD)

| Module | Class | File:line | What it is |
|---|---|---|---|
| Real USD writer | `UsdTarget` | `usd_target.py:180` | `pxr/Sdf` Sdf-level authoring. `Sdf.ChangeBlock` only inside `author_stage_batch`; `layer.Save()` runs outside the lock in `flush()`. Sublayer rotation cap `DEFAULT_ROTATION_CAP = 50_000` at `usd_target.py:103`. Schema-blind authoring: `prim_spec.typeName = "MonetaMemory"` set at `usd_target.py:319` regardless of registry. |
| Mock USD writer | `MockUsdTarget` | `mock_usd_target.py:84` | JSONL log; same `AuthoringTarget` Protocol. `SCHEMA_VERSION = 1` at line 70. |
| Sequential writer | `SequentialWriter` | `sequential_writer.py:84` | Protocol-typed orchestrator: `AuthoringTarget` Protocol at line 49, `VectorIndexTarget` Protocol at line 68. Order: USD first (line 111), vector second (line 121). |
| Consolidation runner | `ConsolidationRunner` | `consolidation.py:69` | Trigger constants: `DEFAULT_MAX_ENTITIES = 10000`, `DEFAULT_IDLE_TRIGGER_MS = 5000`, `MAX_BATCH_SIZE = 500`, `PRUNE_UTILITY_THRESHOLD = 0.1`, `STAGE_UTILITY_THRESHOLD = 0.3` (`consolidation.py:49-56`). |
| Manifest | `build_manifest` | `manifest.py:21` | Function. Filters ECS rows in `STAGED_FOR_SYNC` and projects to `Memory`. |
| Durability | snapshot + WAL | `durability.py` | `SNAPSHOT_VERSION = 1`, `WAL_VERSION = 1` (lines 57-58). Optional 30-second snapshot daemon thread (`start_background`, line 231). |

### 1.4 Schema artifacts (codeless, v1.2.0-rc1+)

- `schema/MonetaSchema.usda` — concrete typed schema, 6 attributes, `priorState` Token with 4 `allowedTokens` (`volatile`, `staged_for_sync`, `consolidated`, `pruned`). `bool skipCodeGeneration = true` at customData.
- `schema/plugInfo.json` — `schemaKind = concreteTyped`, `schemaIdentifier = MonetaMemory`, `LibraryPath = ""` (codeless).
- `schema/generatedSchema.usda` — produced by `usdGenSchema`.

### 1.5 Patterns in actual use

- **Two-tier hot/cold** (ECS in RAM, USD on disk). The shadow vector index is a third in-RAM structure but is a *shadow*, not a tier per docstrings.
- **Append-only attention log** with sleep-pass reduce. No locks.
- **Sequential write** USD-first / vector-second (atomicity protocol per `MONETA.md` §2.7).
- **Sublayer-stack ordering** as the only LIVRPS arc actually composed (per `SCOUT_MONETA_v0_3.md:63`: *"only Local + Sublayer-stack ordering. Inherits, Variants, References, Payloads, Specializes are never authored."*).
- **`Sdf.ChangeBlock` for batch writes**, narrow lock scope (Pass 6 ruling).
- **UUID-based prim naming** (`/Memory_<entity_id_hex>` only — no parent xform, no spine prim).
- **WAL-lite + periodic snapshot** durability.
- **Codeless typed schema** registration via `PXR_PLUGINPATH_NAME`.
- **Free-threading guard** at `attention_log.py:64-68` raising `RuntimeError` under PEP 703.
- **Process-level URI exclusivity** via `_ACTIVE_URIS` set.

### 1.6 Test surface

109 plain-Python tests passing + 7 properly-gated pxr skips under plain
Python; 149 total under hython per CLAUDE.md. No dedicated
`test_consolidation.py` or `test_vector_index.py`; both covered only
incidentally through end-to-end tests (`SCOUT_MONETA_v0_3.md:409-411`).

### 1.7 What is **not** in the codebase

| Concept | Search | Result |
|---|---|---|
| `collections.deque` | grep `deque` in `src/` | zero hits |
| Bounded `maxlen` queue | grep `maxlen` in `src/` | zero hits |
| Monotonic step counter | grep `+= 1` for class attributes | zero (only `updated += 1` local var at `ecs.py:215`) |
| Step / tick / sequence index | grep `step|tick|counter` in `src/` | zero (one docstring "step 1" word in `consolidation.py:23`) |
| State Spine class | grep `StateSpine|state_spine` | zero hits in `src/` |
| Spine prim or spine indexing | grep `spine` in `src/` | zero hits |
| `async def` / `await` / `asyncio` | grep | zero hits |
| Network surface (http/grpc/socket) | grep | zero hits |
| Identity (tenant/user/agent/principal) | grep | zero hits |
| Cost / token / budget tracking | grep `token|cost|budget` | only TfToken (USD), GPU budget docstring, asymptotic-cost docstrings |
| Eval set | `evals/` or `eval/` | zero |
| Anthropic SDK / MCP integration | grep `anthropic|mcp` | zero hits in `src/` |
| Embedder | any embedding production code | zero — `embedding: List[float]` is consumer-supplied |

---

## 2. DOCUMENTED VISION

What the docs explicitly say Moneta is.

### 2.1 Project identity (`MONETA.md` §1)

> Moneta is a memory substrate that implements working and consolidated
> memory for LLM agents using OpenUSD's composition engine **as the
> cortex layer**.

- A hot/cold tiered memory system with an Entity Component System (ECS)
  hot tier and an OpenUSD cold tier (`MONETA.md:29`).
- A four-operation agent API that hides all USD internals from the
  calling agent (`MONETA.md:30`).
- The memory half of a unified cognitive substrate platform shared with
  Octavius (`MONETA.md:31`).

### 2.2 Locked foundations (`MONETA.md` §2 / `ARCHITECTURE.md` §2-§10)

Six locked decisions, repeated almost verbatim across `MONETA.md`,
`ARCHITECTURE.md`, `CLAUDE.md`, and `README.md`:

1. **Four-op API** (`deposit`, `query`, `signal_attention`,
   `get_consolidation_manifest`) — `MONETA.md:55-64`. No fifth op.
2. **Decay math** `U_now = max(floor, U_last * exp(-λ * Δt))` — lazy,
   memoryless, exponential, three eval points, no background tick
   (`MONETA.md:80-95`).
3. **Concurrency primitive** — append-only attention log, reduced at
   sleep pass; no spinlocks, no CAS (`MONETA.md:107-109`).
4. **Atomicity** — sequential write USD-first/vector-second, no 2PC
   (`MONETA.md:123-125`).
5. **Handle, not singleton** (`v1.1.0`) — `Moneta(config)` only;
   process-level URI exclusivity (`README.md` §"Locked decisions" #5).
6. **Codeless typed schema** (`v1.2.0-rc1`) — `typeName="MonetaMemory"`,
   USD camelCase attrs, `priorState` as token (`README.md` #6).

### 2.3 Substrate novelty claims (`MONETA.md` §3)

Four structural claims, framed as patent claims:

1. OpenUSD composition arcs as cognitive state substrate (LIVRPS
   resolution order encodes decay priority).
2. USD variant selection as fidelity LOD primitive (detail→gist via
   `VariantSelection`).
3. Pcp-based resolution as implicit multi-fidelity fallback.
4. Protected memory as root-pinned strong-position sublayer.

### 2.4 Substrate conventions shared with Octavius (`docs/substrate-conventions.md`)

The doc heading says *"five conventions"* but six are listed:

1. UUID-based prim naming.
2. LIVRPS as the priority primitive.
3. The stage is the interface.
4. Strong-position sublayers for invariants.
5. `Sdf.ChangeBlock` for batch writes.
6. UTC sublayer date routing.

### 2.5 Scope explicitly out (`MONETA.md` §7)

Phase 1 non-goals — note Phase 3 has lifted some:

- No `pxr` imports outside `src/moneta/` (Phase 3 lifts).
- No real USD authoring (Phase 3 lifts).
- **No gist generation via LLM calls** — still out.
- **No multi-agent shared stage coordination** — still out (Octavius territory).
- **No cross-session USD hydration at cold start** — still out.
- **No Cognitive Twin integration** — still out.
- **No Cognitive Bridge MCP server implementation** — still out.
- No fifth operation to the agent API.

### 2.6 Vision-keyword check against the documented vision

User-supplied vision keywords searched across the entire repo (case-insensitive):

| Keyword | Hits in Moneta docs | What the hits actually mean |
|---|---|---|
| **LIVRPS State Spine** (immutable layer composition, monotonic step indexing) | `LIVRPS` — yes, as **convention #2** in `docs/substrate-conventions.md:33-37`. **State Spine** as a class/concept — **zero hits**. "Spine" appears in surgery records (`HANDOFF_singleton_surgery.md:20`, `HANDOFF_codeless_schema_moneta.md:23`, `AUDIT_pre_surgery.md:222,281,312`) and `SURGERY_complete.md:19` — used colloquially for "the spine table" of a handoff document, **not architectural**. Authoritative finding from Moneta's own scout: `SCOUT_MONETA_v0_3.md:93` — *"There is **no monotonic step counter and no spine prim**."* | LIVRPS exists as a discipline/convention, not as a class. There is no documented "State Spine" class in Moneta. |
| **Experience Cerebellum** | **Zero hits** in any file. | Not a Moneta concept at the documentation level. |
| **FORESIGHT / predictive composition** | **Zero hits** for `FORESIGHT`, `foresight`, or `predictive` in the architectural sense. ("Predictive" appears nowhere in `src/` or `docs/`.) | Not a Moneta concept at the documentation level. |
| **USD-native cognitive substrate** | **Yes — central thesis.** `MONETA.md:25` (cortex-layer framing), `MONETA.md:42` (parent thesis: *"OpenUSD's composition engine, designed for scene description, is a general-purpose prioritization-and-visibility substrate for agent state that is not geometry"*), `MONETA.md` §3 (four novelty claims), `README.md` tagline, `docs/substrate-conventions.md` §1. | Real, documented, repeatedly. Anchor of Moneta's identity. |
| **Three-layer metaphor (State Spine L1, Cerebellum L2, Cortex L3)** | "Three-layer" appears in `DEEP_THINK_BRIEF_substrate_handle.md:98`, `HANDOFF_singleton_surgery.md:42,114`, `EXECUTION_constitution_singleton_surgery.md:32,103`, `SURGERY_complete.md:19` — all referring to a **scout audit procedure** (three layers of audit), not an L1/L2/L3 architecture. `SCOUT_MONETA_v0_3.md:133` describes "State is stored in three layers" as **hot tier (RAM) / shadow vector index (RAM) / cold tier (disk USD)** — not the State Spine / Cerebellum / Cortex framing. **`L1`/`L2`/`L3` as architectural strata: zero hits.** | Moneta is documented as a **two-tier** (hot ECS / cold USD) substrate with a *shadow* index. "Cortex" is real (USD layer naming, `cortex_*.usda`). Spine and Cerebellum are not documented strata. |

---

## 3. GAP

### 3.1 Vision items with no code

Documented in Moneta's own vision but absent from the implementation:

| Vision element | Where documented | Code status |
|---|---|---|
| **Gist generation via LLM** (`MONETA.md` §2.6, novelty claim #2) | `MONETA.md:120` (consolidation mechanics), `MONETA.md:152-159` (claim #2), risk #2 | **No code.** Repo-wide grep for `gist` in `src/` returns zero implementation hits. The `over` spec authoring + `VariantSelection` cursor described in claim #2 has no writer. |
| **USD variant selection as fidelity LOD primitive** (novelty claim #2) | `MONETA.md:155`, `README.md` §"Novelty claims" was previously, now removed | **No code.** Grep for `VariantSelection`, `VariantSet`, `Variants` in `src/`: zero hits in `usd_target.py`. `SCOUT_MONETA_v0_3.md:63` confirms only L of LIVRPS is composed. |
| **Pcp-based multi-fidelity fallback** (novelty claim #3) | `MONETA.md:157` | **Structurally present, behaviorally absent.** The sublayer stack is in place, but no fidelity tiers are authored that would exercise Pcp resolution. `SCOUT_MONETA_v0_3.md:95`: *"the novelty claim ... is currently structural — the sublayer stack is in place — but no fidelity tiers are authored that would actually exercise it."* |
| **Cross-session USD hydration at cold start** (`MONETA.md` §7 non-goal but vision-shape) | Listed as Phase 1 non-goal still in scope-out | **No code.** No reader path on the substrate side; `usd_target.py` has `Sdf.Layer.FindOrOpen` (existence check) but no traversal that hydrates ECS rows from prim attributes. Read-tolerance lives only in test fixtures (`SCHEMA_read_path_audit.md:28`). |
| **Cognitive Twin integration** (`MONETA.md` §7) | Listed as scope-out | No code. |
| **Cognitive Bridge MCP server implementation** (`MONETA.md` §7) | Listed as scope-out | No code. Zero `mcp`, `anthropic`, or SDK imports in `src/`. |
| **Octavius coordination via shared stage** (`MONETA.md:44`, substrate-conventions §3) | "The stage is the interface" | No code on Moneta's side touches Octavius. (Correctly so per discipline — but the "shared stage" promise has no exercise yet.) |
| **`vector_persist_path` activation (LanceDB)** | `MonetaConfig.vector_persist_path` field documented as Phase 2/v1.1 LanceDB hook | **Wired but dead.** Field is accepted by config and logged-and-ignored at `vector_index.py:75-81`. Module docstring (`vector_index.py:8-48`) discusses LanceDB rationale but uses in-memory implementation. |
| **Pruned EntityState member** | Schema reserves `"pruned"` token in `priorState` `allowedTokens` | **No `EntityState.PRUNED` member** in `types.py:18-29`. Schema reserves the token; substrate cannot produce it. `_token_to_state("pruned")` raises (per `README.md` previous note). |

### 3.2 Code items with no vision documentation

Built and present, but not described in the documented vision:

| Code element | File:line | Documentation status |
|---|---|---|
| **Free-threading guard** at `AttentionLog.__init__` raising under PEP 703 | `attention_log.py:64-68` | Surfaced in module docstring (`attention_log.py:21-28`), `README.md` Status table, `CLAUDE.md` hard rule (added 2026-05-05), `docs/api.md` runtime requirements section (added 2026-05-05). **Not in `MONETA.md` or `ARCHITECTURE.md`.** |
| **Process-level URI exclusivity** (`_ACTIVE_URIS` registry, `MonetaResourceLockedError`) | `api.py:169` (registry), `api.py:74` (error), `api.py:198-203` (collision check) | Documented in `README.md`, `docs/api.md`, surgery records. **Not in `ARCHITECTURE.md` §1-§14**; lives in §5.4 of the singleton-surgery deep-think brief but not promoted to the locked spec. |
| **`ConsolidationRunner.mark_activity`** (idle-trigger heartbeat) | `api.py:376` calls it on every `deposit` | Implementation detail of the 5000ms idle trigger; not surfaced in `MONETA.md` §2.6 or `ARCHITECTURE.md`. |
| **Sublayer rotation continuation suffix** (`_001`, `_002`) | `usd_target.py:158-161, 277-283` | Mentioned in `usd_target.py` module docstring; not in `ARCHITECTURE.md` §15.2. |
| **`MockUsdTarget` JSONL `SCHEMA_VERSION = 1`** | `mock_usd_target.py:70` | Not in vision docs. Test asserts the value (`tests/integration/test_end_to_end_flow.py:239`); no reader in production code. |
| **`SequentialWriter.commit_staging`** + `AuthoringTarget` / `VectorIndexTarget` Protocols | `sequential_writer.py:49,68,84` | Discussed in `MONETA.md` §2.7 atomicity protocol *narratively*; the Protocol-typed seam itself is not documented as a public extension point. `MonetaConfig.use_real_usd: bool` is the only public swap. |
| **Sdf.Layer C++ registry (path-keyed) collision risk** | `usd_target.py:148-180` (creation paths) | Surfaced in `AUDIT_pre_surgery.md:185-200` and `SCHEMA_read_path_audit.md:28-36`. Not in `MONETA.md` or `ARCHITECTURE.md`. |
| **Quota override (`MonetaConfig.quota_override`, default 100)** | `api.py:126`, replaces module-level `PROTECTED_QUOTA` | Documented in `docs/api.md` and surgery records. `MONETA.md` §2.10 still names "100 protected entries per agent" — implementation makes it per-handle, not per-agent. |
| **`AttentionLog.aggregate` weight summation + `signal_count` semantics** | `attention_log.py:89-105` | `ARCHITECTURE.md` §5 mentions write semantics. The exact `(summed_weight, signal_count)` tuple shape and the AttendedCount-by-signals (not by entities) rule live only in code + docstring. |

### 3.3 Partially aligned items

Documented and implemented, but with measurable distance between description and reality:

| Item | Documented | Actual | Gap |
|---|---|---|---|
| **LIVRPS arcs** | `docs/substrate-conventions.md` §2 documents all six (L, I, V, R, P, S) as the priority primitive Moneta should use | Only **L** (sub-Layer stack ordering) is exercised. I, V, R, P, S never authored. (`SCOUT_MONETA_v0_3.md:63`, also stated in `usd_target.py` writer code) | 1 of 6 arcs in use. The composition story is "stronger sublayer position wins"; nothing else is exercised. |
| **Protected memory quota** | `MONETA.md` §2.10: *"Hard cap: 100 protected entries **per agent**."* | `MonetaConfig.quota_override: int = 100` is **per-handle**. Per-handle ≈ per-instance, not per-agent (an agent owning multiple handles, or multiple agents sharing a handle, both diverge). | Concept-vs-implementation mismatch on the unit of accounting. |
| **Decay evaluation points** | `MONETA.md` §2.3 lists three: (a) before retrieval, (b) after attention write, (c) during consolidation scan | `consolidation.py:153-161` runs (b) inside `attention.drain_and_reduce` and (c) explicit; (a) is the `query` path's decay. Three points in code match three points in spec. | Aligned. (Listed for completeness — code says "redundant with #1 under normal flow" at `consolidation.py:23-25`.) |
| **`MonetaConfig.use_real_usd` as A/B flag** | Spec describes Mock/Real swap | Implemented as a single boolean. `AuthoringTarget` Protocol exists internally but no `factory: Callable[[], AuthoringTarget]` extension point is exposed. (`SCOUT_MONETA_v0_3.md:125`) | Two backends, not N. |
| **Substrate conventions count** | `docs/substrate-conventions.md` heading: "The five conventions" (line 13) | Six numbered entries (1-6) — convention #6 *"Sublayer date routing uses UTC"* added later, heading not updated. | Off-by-one in the doc itself. |
| **Test count claim** | `MONETA.md` §6 Phase 1 gate language references the original 94-test bar | Current state: 109 plain Python passing + 7 pxr-gated skips (149 total under hython), per `README.md` Status. `MONETA.md` was not updated. | Drift. |
| **Cortex framing** | `MONETA.md:25`: "OpenUSD's composition engine **as the cortex layer**" | Implementation uses "cortex" only as **file-naming convention** (`cortex_protected.usda`, `cortex_YYYY_MM_DD.usda`, `cortex_root.usda`). There is no `Cortex` class, no module called cortex, no abstraction labeled "cortex layer." | "Cortex" exists as a metaphor/naming convention, not an architectural element. |
| **Stage is the interface** | `MONETA.md:47`, substrate-conventions §3: cross-project composition happens at the stage layer | No second consumer ever uses Moneta's stage today. `SCOUT_MONETA_v0_3.md:374`: *"substrate is substantiated by interface shape ... but **not** substantiated by a second consumer ever using it. Today's only consumer is the test suite + benchmark harness."* | Promise without exercise. |
| **Patent filing as "next post-`v1.0.0` action"** | `README.md` (previous wording, removed 2026-05-05) | Five provisional patents already filed at USPTO 2026-03-23 (per private records — not in repo). | The repo's patent-pending notice is now stripped to "Proprietary. Patents pending." (`README.md` License). The vision doc's "next action" language was ahead of where the codebase claimed to be. |

---

## Annex A — Vision keywords supplied with this audit, item by item

For traceability against the audit's input request.

### LIVRPS State Spine (immutable layer composition, monotonic step indexing)

- **LIVRPS:** documented as substrate convention #2 (`docs/substrate-conventions.md:33-37`); only L is composed.
- **State Spine class:** does not exist. Zero `StateSpine`, `state_spine`, or "spine prim" hits in `src/`. Authoritative scout finding: `SCOUT_MONETA_v0_3.md:93` says no monotonic step counter, no spine prim.
- **Immutable layer composition:** the `Sdf.Layer` objects are mutable in the writer; what's "immutable" is the locked spec, not a runtime data structure.
- **Monotonic step indexing:** absent. Confirmed by Q1 LIVRPS Odometer Invariant Verification (verdict `FALLBACK_REQUIRED`, recorded at `G:/Comfy-Cozy/docs/substrate-egress-v1.1/Q1_VERIFICATION_VERDICT.md`).

### Experience Cerebellum

- Zero hits across the entire repo. Not a Moneta concept.

### FORESIGHT / predictive composition

- Zero hits across the entire repo. Not a Moneta concept.

### USD-native cognitive substrate

- Documented as Moneta's central thesis: `MONETA.md:25, 42`, the four novelty claims at `MONETA.md:151-159`, `docs/substrate-conventions.md` §1.
- Implemented partially: composition arcs (only L), protected sublayer (yes — `cortex_protected.usda` at strongest Root position), variant LOD (no), Pcp fallback (structural only).

### Three-layer metaphor (State Spine L1, Cerebellum L2, Cortex L3)

- Moneta's documented architecture is **two-tier** (hot ECS / cold USD), not three-layer with the supplied L1/L2/L3 framing.
- "Three-layer" appears in Moneta only as the name of a *scout audit procedure* (`HANDOFF_singleton_surgery.md:42`, etc.) — three layers of audit, not three architectural strata.
- "Cortex" exists as a metaphor + file-naming convention for the cold USD layer, not as L3 of a Spine/Cerebellum/Cortex stack.
- "Spine" appears colloquially in surgery handoff "spine tables", not as an architectural stratum.
- "Cerebellum" does not appear at all.

The supplied vision keywords (with the exception of *USD-native cognitive substrate*) are not present in Moneta's documented vision. They appear to be terminology from a sibling project's design surface; this audit reports their absence factually rather than treating them as commitments Moneta has made.
