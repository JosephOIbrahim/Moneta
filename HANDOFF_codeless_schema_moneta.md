# HANDOFF — Codeless Schema Migration

**Type:** Design handoff. Implementation phase.
**Repo:** `Moneta` v1.1.0 on `origin/main` (commit `bc65bf5`)
**Design source of truth:** `DEEP_THINK_BRIEF_codeless_schema.md` §§ 1–6 (brief) + §§ 7.1–7.7 (Deep Think response, locked verdicts)
**Companion document:** `EXECUTION_constitution_codeless_schema.md` — operating rules, MoE roles, gates, halt-conditions for the implementation harness
**Disposition:** Local-only post-creation. Patent surface. Do not paste into cloud-hosted tools beyond the harness session it runs in.

---

## 1. What This Is

The wart-scout (`SCOUT_MONETA_v0_3.md`-equivalent, in-session 2026-04-27) returned **Read A — demo-ready as-is** for v1.1.0's substrate API. The next surgery is a USD codeless schema migration: untyped `def` memory prims become typed `MonetaMemory` prims registered through USD's plugin system.

A design pass via Gemini Deep Think locked six verdicts (Q1–Q6) and surfaced two structural points (§7.7) that materially change implementation. The full reasoning lives in the brief. This handoff does not re-litigate the design. It executes it.

This handoff is paired with `EXECUTION_constitution_codeless_schema.md`, which is shared with the Harlo schema surgery (next in queue). The constitution carries operating posture; this handoff carries the implementation contract for *Moneta-side* schema work only.

---

## 2. What Was Decided (Summary, Not Source of Truth)

The full verdicts and reasoning live in the brief, §§ 7.1–7.6. This is the spine.

| Q | Locked verdict | Implementation impact |
|---|---|---|
| **Q1 — Codegen vs codeless** | Codeless IsA via `plugInfo.json` + `generatedSchema.usda` | No C++ stubs. No build step. Runtime registration only. |
| **Q2 — State encoding** | Token with `allowedTokens` metadata | `prior_state` becomes `Sdf.ValueTypeNames.Token`. Boundary mapping at write/read. |
| **Q3 — Container hierarchy** | Flat — `/Memory_<hex>` stays at root | Zero change to sublayer routing in `usd_target.py`. No parent prims. |
| **Q4 — Schema family** | IsA, schema typeName `MonetaMemory` | `prim_spec.typeName = "MonetaMemory"` at authoring time. |
| **Q5 — Migration safety** | Read-tolerant | Any USD read path branches on `prim.GetTypeName()` for typeless vs typed. See §3 below for substrate-vs-ecosystem framing. |
| **Q6 — Acceptance gate** | Subprocess-isolated SchemaRegistry validation + round-trip | The gate test runs in a clean subprocess, asserts `FindConcretePrimDefinition("MonetaMemory") is not None`, *then* round-trips all six attributes. |

**Deferred to post-June (recorded, not in scope):** `moneta-admin upgrade-stages` CLI for offline re-authoring of legacy typeless stages. Resolves dual-format on-disk debt; does not block the send window.

---

## 3. Q5 Framing — Pre-Implementation Check

The Deep Think pressure valve (§7.7) flagged that the read-tolerance verdict assumes Moneta has a USD read path. If USD is genuinely write-only on the substrate (ECS hydrates from `durability.snapshot_ecs`, not from USD), then read-tolerance is **ecosystem-side**, not substrate-side.

**Pre-implementation check, blocking — runs before any schema code is authored:**

> **Audit every `Usd.Stage.Open` call site in the Moneta repo (src + tests).** Classify each as:
> - **Substrate path** — runs as part of `Moneta(config)` construction or the four-op API
> - **Test fixture** — runs only inside `tests/`
> - **Diagnostic / debug** — explicit operator-facing inspection
>
> Output a one-page report: `SCHEMA_read_path_audit.md`. Format: file:line, classification, reads `prior_state`? (yes/no), notes.

This audit is the gate that decides where read-tolerance lives:

| Audit result | Read-tolerance location |
|---|---|
| Substrate path reads exist | Branching in the substrate hydration layer + test fixtures |
| Substrate path reads do not exist | Test fixtures only. Substrate untouched. |

Either result satisfies Q5's verdict. The audit determines the surface area, not the verdict.

---

## 4. The Schema Spec

Authored as `schema/MonetaSchema.usda` in the repo. Codeless IsA. Single concrete schema (`MonetaMemory`). No abstract base class beyond `Typed`.

**Required content (verbatim, unless USD-style adjustments are needed for codeless registration):**

```usda
#usda 1.0
(
    subLayers = [
        @usd/schema.usda@
    ]
)

over "GLOBAL" (
    customData = {
        string libraryName = "moneta"
        string libraryPath = "./"
        bool skipCodeGeneration = true
    }
)
{
}

class "MonetaMemory" (
    inherits = </Typed>
    customData = {
        string className = "MonetaMemory"
    }
    doc = """A single memory entity in the Moneta substrate.

Authored by Moneta's USD target during consolidation sleep passes.
The prim path is /Memory_<hex> where <hex> is a uuid4 hex string.
Six attributes capture the cognitive-state metadata for one memory.
The semantic vector is NOT stored on this prim — the shadow vector
index is authoritative for embeddings."""
)
{
    string payload (
        doc = "Opaque text content of the memory."
    )

    float utility (
        doc = "Decay-driven retention score, conventionally in [0.0, 1.0]."
    )

    int attendedCount (
        doc = "Cumulative attention signals received."
    )

    float protectedFloor (
        doc = "Minimum utility floor; 0.0 means unprotected."
    )

    double lastEvaluated (
        doc = "Wall-clock unix seconds of last decay evaluation."
    )

    token priorState (
        allowedTokens = ["volatile", "staged_for_sync", "consolidated", "pruned"]
        doc = "Lifecycle state at authoring time."
    )
}
```

**Attribute name discipline:** USD camelCase (`attendedCount`, `protectedFloor`, `lastEvaluated`, `priorState`). The current Python authoring code uses snake_case (`attended_count`, etc.). The schema is authored in USD-idiomatic camelCase; the boundary mapping in `usd_target.py` translates between Python attribute names and USD attribute names. **Do not break Python-side names.** Memory dataclass and ECS row schema are out of scope.

---

## 5. Plugin Registration

Authored as `schema/plugInfo.json` alongside the schema file. Codeless schemas register via the plugin system at USD initialization time.

**Required content:**

```json
{
    "Plugins": [
        {
            "Info": {
                "Types": {
                    "MonetaMemory": {
                        "bases": ["Typed"],
                        "autoApplyAPISchemas": [],
                        "schemaKind": "concreteTyped"
                    }
                }
            },
            "Name": "moneta",
            "Type": "resource",
            "ResourcePath": ".",
            "LibraryPath": "."
        }
    ]
}
```

**Plugin discovery:** the harness must verify USD finds the plugin at runtime. Two acceptable mechanisms — pick whichever fits the existing test infrastructure with less friction:

1. **`PXR_PLUGINPATH_NAME` environment variable** set to the absolute path of `schema/` before `pxr` import. Test fixtures and the schema gate test set this.
2. **`Plug.Registry().RegisterPlugins(...)`** called explicitly during Moneta handle construction or at `pxr` import time.

Mechanism choice is implementation latitude. Both are documented OpenUSD patterns. The choice is recorded in `SCHEMA_implementation_notes.md` so the constitution can verify consistency.

`generatedSchema.usda` is **generated from `MonetaSchema.usda`** by `usdGenSchema --skipCodeGeneration`. The generation step runs once during implementation; the generated file is committed to the repo as a normal source file. Re-running `usdGenSchema` is a development action, not a runtime action.

---

## 6. Authoring Code Changes — `usd_target.py`

The schema migration touches one method and one attribute write. All other code paths in `usd_target.py` are untouched.

**Change 1 — typeName at prim creation (in `author_stage_batch`):**

```python
prim_spec = Sdf.CreatePrimInLayer(layer, path)
prim_spec.specifier = Sdf.SpecifierDef
prim_spec.typeName = "MonetaMemory"   # NEW LINE
```

**Change 2 — `prior_state` becomes a token:**

The `_set_attr` call for `prior_state` changes from:

```python
_set_attr(prim_spec, "prior_state", Sdf.ValueTypeNames.Int, int(m.state))
```

to:

```python
_set_attr(prim_spec, "priorState", Sdf.ValueTypeNames.Token, _state_to_token(m.state))
```

Where `_state_to_token` is a new module-level helper:

```python
_STATE_TO_TOKEN = {
    EntityState.VOLATILE: "volatile",
    EntityState.STAGED_FOR_SYNC: "staged_for_sync",
    EntityState.CONSOLIDATED: "consolidated",
    EntityState.PRUNED: "pruned",
}

def _state_to_token(state: EntityState) -> str:
    return _STATE_TO_TOKEN[state]
```

**Change 3 — all attribute names migrate to USD camelCase at the Sdf layer:**

`_set_attr` calls update from snake_case to camelCase USD-side names. The Python-facing names on `Memory` and the ECS stay as they are. Translation is one direction (Python → USD) at the write boundary.

| Python-side | USD-side |
|---|---|
| `m.payload` | `payload` |
| `m.utility` | `utility` |
| `m.attended_count` | `attendedCount` |
| `m.protected_floor` | `protectedFloor` |
| `m.last_evaluated` | `lastEvaluated` |
| `m.state` (via `_state_to_token`) | `priorState` |

**Out of scope for this surgery:** changes to `Memory`, `EntityState`, `ECS`, `vector_index`, `consolidation`, `attention_log`, `durability`, `sequential_writer`, or any test that does not directly exercise the schema.

---

## 7. Read-Path Branching (Conditional on §3 Audit)

If the §3 audit finds substrate-side USD reads, the read path branches on `prim.GetTypeName()`:

```python
type_name = prim.GetTypeName()

if type_name == "MonetaMemory":
    # Typed prim: priorState is a token
    state = _token_to_state(prim.GetAttribute("priorState").Get())
elif type_name == "":
    # Legacy typeless prim: prior_state is an int
    state = EntityState(prim.GetAttribute("prior_state").Get())
else:
    raise ValueError(f"unknown prim type {type_name!r} at {prim.GetPath()}")
```

`_token_to_state` is the inverse of `_state_to_token`. Define both helpers in the same module.

If the audit finds **no substrate-side reads**, this branching lives only in test fixtures that read written stages back. The substrate code is untouched beyond the writes in §6.

---

## 8. Tests Required

### 8.1 — The acceptance gate (Q6)

A single test, written first, watched fail, then made to pass. Lives at `tests/test_schema_acceptance_gate.py`.

```
def test_schema_acceptance_gate():
    """Subprocess-isolated SchemaRegistry validation + round-trip.

    Per DEEP_THINK_BRIEF §7.6, this is the truth condition for
    the schema migration. Sdf authoring is schema-blind and will
    write typeName='MonetaMemory' even with a missing or broken
    plugin. The subprocess + registry assertion is what mathematically
    proves the OpenUSD runtime recognizes the schema.
    """

    # Spawn a clean subprocess with PXR_PLUGINPATH_NAME pointing at
    # schema/. Run a small payload that:
    #
    #   1. Asserts Usd.SchemaRegistry().FindConcretePrimDefinition(
    #        "MonetaMemory") is not None
    #   2. Constructs Moneta(MonetaConfig.ephemeral(use_real_usd=True, ...))
    #   3. Deposits one memory of each lifecycle state via the four-op API
    #   4. Triggers a sleep pass to author them to USD
    #   5. Saves and reopens the resulting stage in the same subprocess
    #   6. Asserts every memory prim has GetTypeName() == "MonetaMemory"
    #   7. Asserts each of the six attributes round-trips with the correct
    #      type and value, including priorState as a token with the right
    #      allowedTokens entry
    #
    # Assert subprocess return code == 0 and all stdout assertions pass.
```

The subprocess isolation is non-negotiable. Calling the test logic in the same process risks plugin-state contamination from earlier tests. The subprocess gives a clean USD runtime per assertion.

### 8.2 — Regression pack

All 132 existing tests (107 + 25) must remain green. The harness verifies green-before, green-after.

### 8.3 — Read-path branching (conditional)

If §3 audit finds substrate reads:
- One test per branch — typed prim read returns correct state, typeless prim read returns correct state, unknown typeName raises.

If §3 audit finds no substrate reads:
- One test in the test fixtures' read-back path covering the same three cases.

Either way: three small tests, total. Not a separate test file unless the existing structure points elsewhere.

### 8.4 — `_state_to_token` round-trip

Standalone unit test for the boundary helpers. All four enum values round-trip through `_state_to_token` and `_token_to_state` to identity. Token strings match the schema's `allowedTokens` list exactly.

---

## 9. Surgery Sequence (Locked Order)

The constitution governs *how* each step is executed (gates, halt-conditions, commit cadence). This handoff governs *what order*.

1. **§3 audit.** Before any schema code is authored. Output: `SCHEMA_read_path_audit.md`. Determines whether §7 read-path branching is substrate-side or test-side.

2. **Write the acceptance gate test (§8.1) first.** Watch it fail. The failure mode at this point should be "schema not registered" — `FindConcretePrimDefinition` returns `None`. This proves the test is real.

3. **Author the schema spec (§4) and `plugInfo.json` (§5).** Run `usdGenSchema --skipCodeGeneration` to produce `generatedSchema.usda`. Commit all three files.

4. **Wire plugin discovery.** Implement the chosen mechanism from §5. Verify the gate test (§8.1) now fails *only* on the round-trip assertions — schema registration assertion passes. This proves the plugin loads.

5. **Implement authoring changes (§6).** `_state_to_token` helper + the three changes in `usd_target.py`. Verify gate test now passes the typeName assertion.

6. **Implement read-path branching (§7) if audit dictates.** Plus the `_token_to_state` helper.

7. **Write remaining tests (§8.3, §8.4).** Verify all green.

8. **Run the full regression pack (§8.2).** All 132 + new tests green.

9. **Final assertion: gate test (§8.1) passes in a clean subprocess from a clean checkout.** No environment carry-over from the implementation session.

---

## 10. Acceptance Gates — Hard Boundaries

The surgery is done when **all** of these are simultaneously true:

- [ ] §3 audit complete and committed (`SCHEMA_read_path_audit.md`)
- [ ] `MonetaSchema.usda` + `plugInfo.json` + `generatedSchema.usda` committed
- [ ] `usdGenSchema --skipCodeGeneration` runs clean against the schema spec
- [ ] Gate test (§8.1) passes in a clean subprocess
- [ ] All 132 existing tests still green
- [ ] All new tests (§8.3, §8.4) green
- [ ] No new Python dependencies added
- [ ] No build step added (pure Python + pxr at runtime)
- [ ] `usdview` opens a freshly authored stage and displays prims as `MonetaMemory` typed

If any one of these is red, the surgery is not done. The harness halts and reports rather than declaring partial completion.

---

## 11. Scope Boundaries — Explicit Non-Goals

The following are **out of scope** for this surgery. Inclusion of any of these in the implementation is a constitution violation (halt + report, not silent absorption):

- New attributes on `MonetaMemory`. The six are locked.
- Removal or renaming of existing attributes (Python-side names stay snake_case).
- Container schemas (`MonetaSession`, `Memories`, etc.). Q3 verdict is flat.
- API schemas. Q4 verdict is IsA.
- Codegen toolchain. Q1 verdict is codeless.
- The `moneta-admin upgrade-stages` CLI. Recorded in §2 as deferred.
- Changes to `Memory` dataclass, `ECS`, `EntityState` enum.
- Changes to `vector_index`, `consolidation`, `attention_log`, `durability`, or `sequential_writer`.
- Changes to the four-op API surface or the `Moneta` handle.
- Performance optimization. The surgery is correctness-only.

---

## 12. Patent Posture

This handoff is local-only post-creation. It is consumed by the implementation harness in a single session and is not pasted into other cloud-hosted tools.

The schema spec itself (`MonetaSchema.usda`) is committed to the repo. The schema attribute set, the `MonetaMemory` typeName, the `priorState` token enumeration, and the codeless-IsA family are all on-disk and externally inspectable in any stage Mike opens. This is intentional and acceptable disclosure — it is the schema *interface*.

The design rationale (why these six attributes, why this lifecycle, why USD as the cold-tier substrate) is **not** in this handoff and **not** in the brief. It lives in local-only design files. Implementation does not require the rationale; the contract is sufficient.

---

**End of handoff. Constitution drafting is the next step in this session if energy permits.**
