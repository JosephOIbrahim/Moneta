# DEEP_THINK_BRIEF_codeless_schema.md

**Subject:** USD codeless schema migration for Moneta memory prims
**Repo:** Moneta v1.1.0 (handle architecture on `origin/main`, commit `bc65bf5`)
**Status:** Substrate gate cleared. Next surgery in queue.
**Use:** Adversarial design validation prior to implementation handoff.
**Disposition:** This document was sent to Gemini Deep Think for one round only. The response is appended at §7. After commit to `origin/main`, the document is local-only and not pasted into other cloud-hosted tools.

---

## 1. Context

Moneta is a Python library that authors USD memory state to disk via `pxr` Sdf-level APIs. v1.1.0 shipped a singleton-to-handle migration as a separate surgery (closed). 132 tests pass. The library is in production-readiness phase preparing for an external send window in early June.

Today, memory prims are authored as **untyped `def` prims** with six attributes. The next surgery is a USD codeless schema migration to give these prims a typed schema (`MonetaMemory`), registered through USD's plugin system, queryable via `prim.GetTypeName()`, and legible in `usdview` as typed prims.

The schema migration is bounded: no new attributes, no removed attributes, no change to authoring code beyond the type assignment, no change to read-side semantics for existing well-formed prims.

---

## 2. Locked Premises

**These are not up for re-litigation. The pressure valve in §7.7 covers the case where a locked premise is structurally wrong.**

1. **v1.1.0 substrate is correct as shipped.** Handle architecture, four-op API, sublayer routing, and ChangeBlock authoring discipline are out of scope. This brief is about the *type system* layered onto already-correct authoring.

2. **The six attributes are locked in name, type, and semantic.** They are:

   | Attribute | Current SDF type | Semantic |
   |---|---|---|
   | `payload` | `String` | Opaque text content of the memory |
   | `utility` | `Float` | Decay-driven [0.0, 1.0] retention score |
   | `attended_count` | `Int` | Cumulative attention signals received |
   | `protected_floor` | `Float` | Minimum utility floor; 0.0 = unprotected |
   | `last_evaluated` | `Double` | Wall-clock unix seconds of last decay |
   | `prior_state` | `Int` (cast from enum) | Lifecycle state at authoring time |

   No additions. No removals. No semantic changes.

3. **Codeless schema family.** No C++ stubs, no `usdGenSchema` C++ output, no build step. Schema is consumed at runtime via `plugInfo.json` + `generatedSchema.usda`. This is the migration target by constraint.

4. **IsA schema, not API schema, is the working assumption.** Memory prims are *typed* (`MonetaMemory`); they are not typeless prims with an applied API schema. This is open to reversal in Q4 below.

5. **`MonetaMemory` is the working schema typeName.** Open to reversal if a stronger name is proposed in Q4.

6. **Existing on-disk stages must remain readable.** Pre-schema typeless `def` prims authored by current Moneta builds must hydrate correctly under the new schema-aware code path. Migration safety is Q5; the constraint that pre-schema stages do not become unreadable is locked.

7. **The send window is early June.** Schema work has a 1–2 day implementation budget under the current plan. Designs that demand more than that budget surface in Q3 or Q5 — they are not silently absorbed.

8. **Patent posture.** Design rationale that touches structural novelty is *not* in this brief. The questions below are USD schema design choices framed against an existing implementation. Adversarial reasoning about cognitive-architecture implications is out of scope.

---

## 3. Current Authoring Code — Relevant Facts

The schema migration sits on top of the following authoring shape, which is fixed:

- All writes use **Sdf-level API** inside `Sdf.ChangeBlock`. Specifically: `Sdf.CreatePrimInLayer(layer, path)` followed by `prim_spec.specifier = Sdf.SpecifierDef` and per-attribute `Sdf.AttributeSpec(...)`. UsdStage.DefinePrim is *not* used — there is a documented OpenUSD 0.25.5 incompatibility with DefinePrim-inside-ChangeBlock-with-sublayers (stage.cpp:3889).

- Prim paths are `/Memory_<hex>` where `<hex>` is a uuid4 hex string. Prim names are never derived from payload content — this is a substrate convention to avoid `TfToken` registry pressure.

- Layers route by `protected_floor`:
  - `protected_floor > 0.0` → `cortex_protected.usda` (strongest sublayer position)
  - else → `cortex_YYYY_MM_DD.usda` (rolling daily; rotates to `_001`, `_002` at 50k prims)
  - Root layer is `cortex_root.usda`. All sublayers are subLayers of root.

- `layer.Save()` is deferred to a separate `flush()` method called after authoring (narrow-lock pattern; allows concurrent traversal during Save).

- A shadow `VectorIndex` is the authoritative record of *what exists*. USD stores cognitive-state metadata; the vector index stores the entity-id-to-vector mapping. Schema work does not touch the vector index.

- Read path: ECS rehydration on handle construction reads from a separate snapshot (`durability.snapshot_ecs`), not from USD directly. USD is currently write-only at the substrate level; reads come from the ECS hot tier. (Cross-session USD hydration is a Phase 1 non-goal and not in scope for this surgery.)

This means the schema migration affects **the write path of `usd_target.py` and the type system contract**, but does not affect reads from USD (because there are none today on the substrate-API path).

---

## 4. Research Questions

Six questions follow. Each has a concrete trade-off space and a narrow set of acceptable answers. The questions are ordered by independence — earlier answers do not constrain later ones unless explicitly noted.

### Q1 — Codeless vs codegen

Is **codeless IsA** (no C++ stubs, runtime registration via `plugInfo.json` + `generatedSchema.usda`) the correct migration target, or should the schema use **full `usdGenSchema` codegen** with C++ stubs?

**Trade-offs as I see them:**

- *Codeless wins on:* zero build step, faster iteration, no platform-specific compile, no Python↔C++ ABI surface for the schema itself.
- *Codegen wins on:* compile-time validation of attribute access from C++, slightly faster runtime registration, idiomatic for shipping schemas in commercial DCCs.
- *Both produce the same on-disk format* and the same Python-side `prim.GetAttribute("utility")` API.

The locked premise is codeless. Push back if codegen is structurally correct *for this specific codebase* despite the budget constraint — and if so, identify the regret cost of starting codeless and migrating later.

**Verdict expected:** confirm codeless, OR identify the specific failure mode that makes codeless a regret-purchase here.

### Q2 — State as token vs int

Today `prior_state` is authored as `Sdf.ValueTypeNames.Int` with values `int(EntityState.<n>)`. The schema migration could preserve this as `int`, or migrate to a **token** with allowed values:
`"volatile"`, `"staged_for_sync"`, `"consolidated"`, `"pruned"`.

**Trade-offs:**

- *Token wins on:* USD-idiomatic (USD's preferred enum encoding), `usdview` legibility, queryable via string predicates, schema-validation of allowed values via `allowedTokens` metadata.
- *Int wins on:* zero migration friction (existing on-disk stages remain valid), no enum-value-to-token mapping at the boundary, smaller on-disk footprint per prim (negligible).
- *Mixed cost:* if token, the read path needs to map `"volatile"` → `EntityState.VOLATILE` somewhere; if int, USD inspection tools show meaningless integers.

**Verdict expected:** token or int, with reasoning that addresses (a) `usdview` legibility weighting, (b) migration safety implications for existing stages, (c) read-path mapping cost.

### Q3 — Container hierarchy

Today, memory prims are **flat at the layer root**: `/Memory_<hex>`. Three options for the schema migration:

| Option | Path shape | Implication |
|---|---|---|
| **A — Flat** | `/Memory_<hex>` | Status quo. Zero hierarchy work. |
| **B — Scope container** | `/Memories/Memory_<hex>` | Adds a `Scope`-typed parent prim per layer. Pure organizational. |
| **C — Typed session container** | `/MonetaSession/Memory_<hex>` | Adds a `MonetaSession` schema. Each layer has one root MonetaSession prim. Memory prims are children. |

**Trade-offs:**

- *Flat:* zero work, zero locked-in hierarchy decisions, but reads as a `def`-soup in `usdview`.
- *Scope:* small win on legibility, but the `/Memories/` scope is a wasted level if a future container surgery lands a *different* hierarchy.
- *MonetaSession:* USD-idiomatic, paves the way for future scoping (per-session URIs, multi-session stages), but introduces a second schema type and forces decisions about what `MonetaSession` *is* before the substrate has a coherent session abstraction.

**Locked constraint:** the answer must respect the budget (1–2 day implementation). Container options that require redesigning the routing in `usd_target.py` exceed budget.

**Verdict expected:** flat / scope / session, with reasoning that addresses (a) regret cost of locking the hierarchy now, (b) `usdview` legibility weighting, (c) implementation budget fit.

### Q4 — Schema family

The locked working assumption is **IsA schema** — `MonetaMemory` is a typed prim that inherits from `Typed`. Two alternatives:

| Family | Shape | Trade-off |
|---|---|---|
| **IsA** *(working)* | `def MonetaMemory "Memory_<hex>"` | Strong type identity; one-of-many-types is awkward |
| **API schema** | `def "Memory_<hex>" (apiSchemas = ["MonetaMemoryAPI"])` | Composable; weaker type identity (prim is `def`, not `MonetaMemory`) |
| **Multiple-Apply API** | `def "Memory_<hex>" (apiSchemas = ["MonetaMemoryAPI:default"])` | Multiple instances per prim; almost certainly wrong here |

**Trade-offs:**

- *IsA:* `prim.GetTypeName() == "MonetaMemory"` is the canonical query. usdview shows the type. One memory = one type. Clean.
- *API:* allows future composition (e.g. `MonetaMemoryAPI` + `ProtectedAPI` + `ConsolidatedAPI`). But: introduces an applied-API construct that may never be used. YAGNI risk.
- *Multiple-Apply:* a prim can have N memories applied. There is no use case for this in Moneta. Listed for completeness; expected to be ruled out.

**Verdict expected:** IsA, API, or Multiple-Apply, with reasoning that weighs current shape against speculative future composition.

Also: confirm or reject `MonetaMemory` as the schema typeName. Acceptable alternatives: `Memory`, `CognitiveMemory`, `MnMemory`. The name is on-disk and externally visible in any stage Mike opens.

### Q5 — Migration safety for pre-schema stages

Existing on-disk Moneta stages contain typeless `def` prims at `/Memory_<hex>` with the six attributes authored directly. After the schema migration, those stages must remain readable. Three options:

| Option | Behavior |
|---|---|
| **A — Read-tolerant** | New code reads typeless `def` AND typed `MonetaMemory` interchangeably. Zero migration. Pre-schema stages keep their original prim types forever. |
| **B — One-shot upgrade** | First handle construction against a pre-schema stage re-authors all prims with the new typeName, saves once, then proceeds normally. Stages converge to typed over time. |
| **C — Refuse pre-schema** | Handle raises on pre-schema stages, requires an explicit `migrate_stage()` call. Sharp boundary; no silent upgrades. |

**Trade-offs:**

- *A:* zero friction, but the on-disk format has two valid shapes forever. usdview legibility for old stages stays poor.
- *B:* upgrades happen automatically. But: the first read after upgrade is silently mutating, which violates the "read does not mutate" expectation. Risk of corruption if the upgrade pass crashes mid-way. Locked premise 6 says pre-schema stages must remain readable — *automatic mutation on read* is a legitimately contested interpretation.
- *C:* explicit, safe, but adds an operator step.

**Verdict expected:** A, B, or C, with reasoning that weighs (a) zero-friction migration, (b) on-disk format hygiene, (c) crash safety during upgrade, (d) operator-step ergonomics.

### Q6 — Acceptance gate truth condition

The singleton surgery had the **Twin-Substrate test** as its truth condition: written first, watched fail, then made to pass. The schema migration needs an analogous single test that proves the migration is complete and correct.

**My proposed gate:**

> *Round-trip integrity test:* author one memory prim of each lifecycle state via `Moneta.deposit` and `run_sleep_pass`; save the stage; reopen the stage from a fresh process; assert (a) every prim has `prim.GetTypeName() == "MonetaMemory"`, (b) all six attributes round-trip with type and value fidelity, (c) the lifecycle state attribute round-trips correctly under the encoding chosen in Q2.

**Question:** is round-trip integrity the right truth condition? Alternatives:

- *Schema validation only:* `usdGenSchema` runs clean against the spec. Necessary but not sufficient — proves the schema is well-formed, not that authoring uses it.
- *usdview-visible:* a human opens the resulting stage in usdview and confirms typed prims display. Subjective.
- *Existing 132 tests still green:* necessary regression check, but doesn't prove the migration *added* anything.

**Verdict expected:** the *one* test that, if green, proves the schema migration is done. Round-trip integrity, or a sharper alternative.

---

## 5. Hard Operating Rules

These governed Deep Think's response. Violations would have made the response unusable for the implementation handoff.

1. **Do not re-litigate the locked premises in §2.** The pressure valve in §7.7 exists for the case where a premise is structurally wrong. Use it. Do not silently re-open premises in the answers to Q1–Q6.

2. **Do not propose scope additions.** If the right answer to a question is "also add this thing," that goes in the pressure valve, not in the answer. The answer to "should we use IsA or API schema" is "IsA" or "API," not "IsA and also add a `MonetaMemoryHistory` schema."

3. **Verdict-first format.** Each question's answer leads with a one-line verdict. Reasoning follows. Reasoning is bounded — typically 200–400 words per question. Bullet-padding and "you might also consider" tangents are explicitly out of bounds.

4. **No re-statement of trade-offs as analysis.** The trade-offs are stated in the brief. The job is to *resolve* them, not catalog them back.

5. **Identify the regret cost on every verdict.** What is the specific failure mode that would make this verdict wrong? What signal would surface it? This is the part of adversarial validation that matters.

6. **Cite USD primary sources where the verdict turns on USD specifics.** OpenUSD documentation, Pixar tutorials, AOUSD spec — name the source. Do not cite from training data without identifying it as such.

7. **One brief, one round.** Follow-up clarification rounds are not part of this engagement. If a question is ambiguous, answer the most defensible interpretation and flag the ambiguity in the pressure valve.

---

## 6. Deliverable Format

The response is appended to this document as **Section 7 — Deep Think Response**, with subsections:

- 7.1 — Q1 Verdict and reasoning
- 7.2 — Q2 Verdict and reasoning
- 7.3 — Q3 Verdict and reasoning
- 7.4 — Q4 Verdict and reasoning
- 7.5 — Q5 Verdict and reasoning
- 7.6 — Q6 Verdict and reasoning
- 7.7 — Pressure valve

**Pressure valve guidance.** Use §7.7 to flag:

- *Premise corrections:* any locked premise in §2 that is structurally wrong. Identify the premise and the correction.
- *Ambiguity flags:* any question in §4 where the most defensible interpretation was non-obvious. Identify the interpretation chosen and the alternative.
- *Scope additions deferred:* anything that would have been the right answer to a question if the budget allowed it. Not for inclusion in this surgery, but worth recording for the next pass.
- *Cross-question coupling:* any case where the answer to one question changes the right answer to another. The brief assumes independence; flag where that breaks.

§7.7 is the only section where structural pushback on the brief itself is allowed.

---

## 7. Deep Think Response

*Appended verbatim from the Gemini Deep Think round, 2026-04-27. Locked verdicts; do not re-litigate.*

### 7.1 — Q1 Verdict and reasoning

**Verdict:** Confirm codeless IsA via `plugInfo.json` + `generatedSchema.usda`.

**Reasoning:**
We resolve this tradeoff by recognizing Moneta's architecture natively sidesteps the benefits of C++ codegen. Since Moneta strictly utilizes Sdf-level APIs for authoring (`Sdf.ChangeBlock`, `Sdf.CreatePrimInLayer`, `Sdf.AttributeSpec`), the C++ getter/setter stubs and `Define` creation methods generated by full `usdGenSchema` are structurally bypassed during the write cycle. Generating them provides zero runtime utility for Moneta's authoring loop. A codeless schema registered dynamically via `plugInfo.json` achieves the exact goals required by the brief: `prim.GetTypeName()` queryability, schema metadata validation, and `usdview` type legibility. This approach successfully delivers schema awareness to the OpenUSD runtime without introducing a heavyweight C++ build toolchain, linking dependencies, or platform-specific Application Binary Interface (ABI) management. This perfectly respects the rigid 1–2 day implementation budget while maintaining the deployment ergonomics of a Python library.

**Regret cost:**
If a downstream C++ host application (such as a game engine or custom Hydra delegate) directly consumes Moneta's stages in the future, developers will lack compiled `MonetaMemory` headers. They will be forced to use weakly-typed string lookups (`prim.GetAttribute(TfToken("utility"))`), losing compile-time safety. The signal will be friction and error-proneness raised by C++ consumers.
*Source: OpenUSD Documentation > "Generating New Schema Classes" (Codeless Schemas).*

### 7.2 — Q2 Verdict and reasoning

**Verdict:** Migrate to token with schema-enforced `allowedTokens`.

**Reasoning:**
We resolve this by prioritizing the primary objective of the schema migration: establishing self-describing structural legibility within the broader USD ecosystem. Storing categorical state as an integer completely subverts this objective, rendering the `prior_state` attribute opaque in `usdview` and forcing operators to manually cross-reference Python source code to decipher the data. OpenUSD designates `TfToken` as the canonical semantic type for enumerations. By migrating to a token, Moneta can embed data validation directly into the schema definition via the `allowedTokens` metadata field (e.g., `["volatile", "staged_for_sync", "consolidated", "pruned"]`). The implementation cost is isolated and minimal: casting the Python `EntityState` enum to its string representation on the Sdf write path, and mapping it back during read rehydration. The resulting alignment with professional USD authoring standards heavily outweighs the negligible dictionary mapping cost.

**Regret cost:**
Cross-question coupling with Q5 introduces legacy format friction. Existing stages contain `int`, so the ECS hydration logic must now gracefully branch to handle a union type (`int` for untyped prims, `str`/`TfToken` for `MonetaMemory` prims). The signal of failure will be `Tf Notice` type-mismatch warnings in the console and potential `TypeError` crashes if the read path fails to accommodate the historical integer format.
*Source: OpenUSD Schema Design Guidelines & API Documentation > `TfToken`.*

### 7.3 — Q3 Verdict and reasoning

**Verdict:** Option A — Flat (`/Memory_<hex>`).

**Reasoning:**
We resolve this strictly via the 1–2 day budget constraint and the locked Sdf authoring pattern. Because Sdf manipulates data directly and bypasses the high-level `UsdStage` composition engine, creating nested hierarchical containers (Options B and C) requires manually constructing parent `Sdf.PrimSpec` instances for every sublayer. Furthermore, it introduces complex synchronization logic to prevent concurrent authoring collisions when multiple writers attempt to establish the same parent container. This mandates a fundamental rewrite of the sublayer routing loop in `usd_target.py`, blowing the budget constraint and directly violating the "no change to authoring code beyond type assignment" rule. A flat hierarchy perfectly isolates the schema rollout from premature organizational refactors. The new typed schema and `usdview` UI filtering solve the namespace legibility problem without imposing structural nesting changes.

**Regret cost:**
Qt-based outliners like `usdview` scale poorly with massive flat hierarchies. While OpenUSD resolves millions of flat prims efficiently in memory, expanding a root layer with 50,000 flat memory prims will cause severe UI lag and frame-rate drops. The signal will be operator frustration and UI unresponsiveness when manually inspecting production stages during the send window.
*Source: Pixar OpenUSD Performance Guidelines > "Hierarchy vs Flat Lists".*

### 7.4 — Q4 Verdict and reasoning

**Verdict:** IsA schema, named `MonetaMemory`.

**Reasoning:**
We resolve this by aligning the Moneta domain ontology with OpenUSD's established schema design rules. A cognitive memory is a primary domain entity; it dictates the fundamental identity and existential purpose of the prim. This strictly meets the definition and criteria for an IsA (Typed) schema. Applied API schemas, conversely, are designed to compose orthogonal traits onto existing primary entities (e.g., applying `UsdPhysicsMassAPI` to a generic `UsdGeomSphere`). Utilizing an API schema on a typeless `def` implies the prim is an ambiguous container that merely possesses memory-like traits, which violates the conceptual integrity of the memory substrate. The `typeName` must be `MonetaMemory` to explicitly namespace the schema. This isolates the stage from catastrophic type-registry collisions if a host application or downstream DCC implements its own generic `Memory` concept (such as a hardware cache or RAM footprint profiler).

**Regret cost:**
IsA schemas enforce strict single inheritance; a prim cannot have multiple IsA types. If a future architectural phase dictates that cognitive memories should be attached directly to existing spatial scene geometry (e.g., tagging a character's `UsdGeomMesh` with a memory), the IsA decision structurally blocks this composition. The signal will be the inability to cleanly apply memory semantics to external typed prims.
*Source: OpenUSD Schema Design Guidelines > "API Schemas vs. Typed Schemas".*

### 7.5 — Q5 Verdict and reasoning

**Verdict:** Option A — Read-tolerant.

**Reasoning:**
We resolve this by enforcing the core systems engineering contract of persistent storage layers: read operations must be strictly idempotent and non-destructive. Option B (One-shot upgrade) violates this by mutating the layer during a read operation. If a crash or file-lock conflict occurs mid-save, it risks irreversible stage corruption and violates the narrow-lock pattern established in the write path. Option C (Refusal) explicitly violates Locked Premise 6 and requires building an out-of-band CLI tool, immediately exceeding the budget. Option A safely isolates the migration burden to the Python ECS hydration layer. By branching the rehydration logic to gracefully accept both `GetTypeName() == "MonetaMemory"` and `GetTypeName() == ""` (typeless), legacy data is preserved immutably, and new writes instantly comply with the schema constraint.

**Regret cost:**
Permanent technical debt in the hydration logic and a persistent dual-state format on disk. Pre-schema stages will continue to render as untyped `def` soup in `usdview` until they age out or are manually re-authored. The fallback conditional block (`if typeless else typed`) will remain in the codebase indefinitely. The signal will be lingering developer friction when parsing historical layers.

### 7.6 — Q6 Verdict and reasoning

**Verdict:** Subprocess-isolated round-trip integrity test + Explicit Schema Registry validation.

**Reasoning:**
We resolve this by recognizing that Sdf-level authoring is intentionally schema-blind and un-validated. `Sdf.CreatePrimInLayer` and `Sdf.AttributeSpec` will successfully write the raw string `"MonetaMemory"` to the `typeName` field and round-trip all six attributes perfectly even if the codeless schema plugin is missing, malformed, or failed to load. Therefore, the proposed pure round-trip test represents a dangerous false-positive hazard. To rigorously prove the schema migration is operational, the test must execute in a clean subprocess to avoid local environment contamination. It must dynamically bind `PXR_PLUGINPATH_NAME` and explicitly assert that `Usd.SchemaRegistry().FindConcretePrimDefinition("MonetaMemory") is not None` *before* proceeding with the round-trip attribute checks. This is the only way to mathematically prove the OpenUSD runtime recognizes the typed schema.

**Regret cost:**
False positives in the CI pipeline. If explicit registry validation is omitted, the test will blindly pass on raw string serialization, but the plugin configuration could be broken in production. The signal will be a successful deployment that fundamentally fails in the wild because downstream tools treat the prims as untyped.
*Source: OpenUSD Documentation > "Plugin Discovery (plugInfo.json)".*

### 7.7 — Pressure valve

- **Premise correction (Read Path vs Premise 6):** Premise 3 states "USD is currently write-only at the substrate level... reads come from ECS hot tier". Premise 6 states "pre-schema stages do not become unreadable". I am operating under the assumption that the ECS hydration layer *does* read the USD stage once to populate its snapshot. If Moneta never reads USD via Python at all, Q5 is moot. Option A assumes the ECS hydrator requires read-tolerance.

- **Cross-question coupling (Q2 + Q5):** Choosing `token` (Q2) and `Read-tolerant` (Q5) heavily couples the ECS read path. Because legacy files remain un-mutated, the hydration logic must be explicitly patched to parse a union type for `prior_state`: `int` from untyped prims, and `str`/`TfToken` from `MonetaMemory` prims. A naive string cast will crash the reader.

- **Scope additions deferred (Stage Upgrader):** While Option A safely handles Q5 within budget, a standalone CLI utility (e.g., `moneta-admin upgrade-stages`) should be ticketed for the post-June window. This allows operators to execute the Option B upgrade safely offline, eventually clearing the `usdview` legacy tech debt without mutating data during hot session reads.

---

**End of brief. Locked verdicts at §§7.1–7.6, pressure valve at §7.7. Implementation contract is `HANDOFF_codeless_schema_moneta.md`.**
