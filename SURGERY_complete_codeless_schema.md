# SURGERY complete — Codeless Schema Migration

**Surgery:** USD codeless schema migration. Untyped `def` memory prims become typed `MonetaMemory` prims registered through USD's plugin system.
**Design source of truth:** `DEEP_THINK_BRIEF_codeless_schema.md` §§7.1–7.6 (locked verdicts) + §7.7 (pressure valve).
**Operating contract:** `EXECUTION_constitution_codeless_schema.md` (4 roles, halt conditions, commit cadence).
**Status:** §10 conjunctively green. Tagged `v1.2.0-rc1`. RC suffix preserved per Joe's pre-tag ruling — promotion to `v1.2.0` final after the June send window.

---

## What changed

- **Schema artifacts under `schema/`.**
  - `MonetaSchema.usda` — declares `class MonetaMemory "MonetaMemory"` (concrete typed) with six attributes in USD camelCase plus `priorState` as a token with four `allowedTokens`.
  - `plugInfo.json` — codeless registration. `LibraryPath=""`, `ResourcePath="."`, `Root="."`. Plugin name `"moneta"`.
  - `generatedSchema.usda` — produced by `usdGenSchema` (no `--skipCodeGeneration` CLI flag in this version; the customData `bool skipCodeGeneration = true` on the GLOBAL prim suffices).
- **`src/moneta/usd_target.py` writer changes (handoff §6).**
  - `prim_spec.typeName = "MonetaMemory"` set at every prim-creation site.
  - Six `_set_attr` calls renamed to USD camelCase: `attendedCount`, `protectedFloor`, `lastEvaluated`, `priorState`. The remaining two (`payload`, `utility`) were already camelCase-clean.
  - `priorState` migrates from `Sdf.ValueTypeNames.Int` (`int(m.state)`) to `Sdf.ValueTypeNames.Token` (`_state_to_token(m.state)`).
  - Module-level helpers `_state_to_token` / `_token_to_state` plus the `_STATE_TO_TOKEN` / `_TOKEN_TO_STATE` dicts. The reverse helper raises `ValueError` on tokens outside the substrate-producible set, including the schema-reserved `"pruned"`.
- **Plugin discovery via `PXR_PLUGINPATH_NAME`.** Set per-subprocess in `tests/test_schema_acceptance_gate.py`. The substrate does not register the plugin itself — Sdf-level authoring is schema-blind, so writes succeed regardless. Schema-aware behavior (`FindConcretePrimDefinition`, typed `usdview` rendering) only matters for the gate test and operator inspection. Both work with the env-var pattern.
- **Test fixtures updated for the new attribute names.** `tests/unit/test_usd_target.py` lines 122-127 and 372-378 — seven reads converted from snake_case + int to camelCase + token. No other tests touched (`test_real_usd_end_to_end.py` only reads `payload` and `typeName`-related state, both compatible).
- **`.gitignore` amended** to re-include `schema/*.usda` after the existing runtime-USD-artifact exclusion. The first commit at step 3 silently dropped two of the three schema files; the fixup commit landed them.
- **`pyproject.toml`: 1.1.0 → 1.2.0rc1.** Schema is an additive externally-visible contract. Minor bump per semver. RC suffix gives a clean promotion path.

---

## Audit findings (Auditor, step 1)

`SCHEMA_read_path_audit.md` at `86d6ed9`. Verdict: **substrate-side reads of `prior_state` do not exist in the Moneta repo.** The substrate's only USD-content-entry call sites (`UsdTarget.__init__` at `usd_target.py:154/156/178`) open layers and stages but never call `GetAttribute()` on resulting prims. All `prior_state` reads were in test fixtures (`tests/unit/test_usd_target.py:127, 378`).

Implication for handoff §7 (read-path branching): collapsed to test-fixture-only. The substrate code is untouched beyond the writes in §6. The `_token_to_state` helper still gets authored at step 5 — exported for test consumers.

---

## Surprising findings

1. **`EntityState.PRUNED` does not exist.** The handoff §6 `_STATE_TO_TOKEN` dict literal references `EntityState.PRUNED`; the brief §7.2 verdict and `MonetaSchema.usda` `allowedTokens` both include `"pruned"`; but `src/moneta/types.py:18-29` has only three enum members. Pruned entities are removed from the ECS rather than transitioning to a PRUNED state, so the substrate cannot author the token. Resolved per the Auditor's pre-G1 interpretation (a): schema reserves `"pruned"` as forward-looking; `_STATE_TO_TOKEN` only contains the three currently-extant members; `_token_to_state("pruned")` raises `ValueError` rather than silently returning a wrong state.
2. **Cross-binary plugin discovery worked first try.** Constitution §"Halt Conditions" specifically lists *"Plugin registration succeeds for `pxr` Python but `usdview` (which may use a different `pxr` install) cannot find the schema"*. Joe's manual verification confirmed usdview displays `MonetaMemory` typed prims with `PXR_PLUGINPATH_NAME` set. No fork between the gate-test runtime and the usdview runtime under this Houdini install.
3. **`usdGenSchema` produced three cosmetic warnings about missing C++ build files** (`__init__.py`, `CMakeLists.txt`, `module.cpp`). These are expected for codeless schemas — the C++ build path is intentionally absent, but the warning fires regardless. Not a halt condition.
4. **`usdGenSchema --skipCodeGeneration` CLI flag is not recognized in OpenUSD 0.25.5 / Houdini 21.0.512.** The codeless behavior is driven by the `bool skipCodeGeneration = true` customData on the GLOBAL prim of `MonetaSchema.usda`, which DOES work. The handoff's literal `--skipCodeGeneration` invocation was inaccurate for this OpenUSD version; the customData approach is canonical.
5. **Concrete schema requires `class TypeName "Name"` syntax**, not `class "Name"`. The handoff's example used the abstract form. First `usdGenSchema` run produced `schemaKind = "abstractTyped"` in `plugInfo.json`. Updating `MonetaSchema.usda` to the concrete form (`class MonetaMemory "MonetaMemory"`) fixed it.

---

## Limitations carried forward

| Limitation | Why it's parked |
|---|---|
| `_STATE_TO_TOKEN` cannot map `"pruned"` because `EntityState` has no `PRUNED` member | Adding `EntityState.PRUNED` is out of scope per handoff §11. A future PRUNED-as-tombstone surgery owns this — it would be the surgery that introduces a state for "pruned but retained in the ECS for audit/replay" and the corresponding writer path. The schema is forward-compatible. |
| Cross-session USD hydration | Phase 1 non-goal per `MONETA.md` §7. The substrate authors USD but does not read it back to populate the ECS. Independent of this surgery. |
| `moneta-admin upgrade-stages` CLI for offline re-authoring of legacy typeless stages | Recorded in handoff §2 as deferred. Resolves dual-format on-disk debt. Not in scope. |
| `plugInfo.json` `LibraryPath` is empty + `ResourcePath`/`Root` are `"."` | Standard codeless-schema substitution for `@PLUG_INFO_*@` placeholders. If Moneta later ships a C++ host, these need to point at the install location. Out of scope for v1.2.0-rc1. |

---

## Test count

| Surface | Before | After |
|---|---|---|
| Plain Python passing | 107 | **107** (unchanged — all new tests are pxr-gated) |
| Plain Python skipped (pxr-gated, properly) | 4 | **7** (added 3 new pxr-gated test modules) |
| Hython total passing | 132 | **147** |
| Net new pxr-gated tests | — | **+15** (1 acceptance gate + 3 §8.3 read-path branching + 11 §8.4 round-trip) |

Constitution §2 ("Net-positive test count is mandatory; final test count must be `132 + (3 to 4 new) + (any tests required by audit findings)`"): satisfied (132 + 15 = 147).

**Regression preservation:** all 132 prior tests remained green at every surgery step boundary. The 17 `test_usd_target.py` tests had 7 fixture reads updated to camelCase + token; the structural assertions are unchanged.

---

## Gate trail

| Gate | Cleared by | Artifact |
|---|---|---|
| Pre-flight | Harness | `8b4609a` — 4 governing docs on `origin/main` |
| **G1** — post-audit human gate | Joe (`proceed`) | `pre-implementation` tag at `987be52`; surfaced schema content + plugin mechanism + audit verdict + reversal cost |
| **§10** — conjunctive acceptance | Crucible structural + Joe's usdview manual check | 9 of 9 bullets green (8 programmatic + 1 operator-confirmed) |

---

## Surgery sequence — final commit map

| Step | Commit | Role |
|---|---|---|
| Pre-flight | `8b4609a` | docs |
| 1 — §3 audit | `86d6ed9` | Auditor |
| 2 — gate test (watched-fail) | `00270f1` | Crucible |
| 3 — schema artifacts | `bf1ead0` + `987be52` (fixup) | Schema Author |
| 4 — plugin discovery | (subsumed by step 2 env-var wiring) | — |
| 5 — Forge typeName + token | `f7b6253` | Forge |
| 6 — read-path branching | (no-op per audit; helpers in step 5) | — |
| 7 — §8.3 + §8.4 tests | `41d5385` | Crucible |
| 8 — full regression | (verified in-place at f7b6253 / 41d5385) | — |
| 9 — clean-subprocess gate | (verified in-place; subprocess isolation by design) | — |
| Closure | (this commit) — version bump + summary + tag `v1.2.0-rc1` | Crucible |

---

## Files touched

**Production:** `src/moneta/usd_target.py` (typeName, token, camelCase, helpers), `pyproject.toml` (version bump), `.gitignore` (re-include `schema/*.usda`).

**Schema artifacts:** `schema/MonetaSchema.usda`, `schema/plugInfo.json`, `schema/generatedSchema.usda`.

**Tests added:** `tests/test_schema_acceptance_gate.py`, `tests/_schema_gate_subprocess.py`, `tests/unit/test_schema_read_branching.py`, `tests/unit/test_state_token_roundtrip.py`.

**Tests modified (fixture-only):** `tests/unit/test_usd_target.py` (7 reads updated to camelCase + token).

**Surgery process artifacts:** `KICKOFF_codeless_schema.md`, `EXECUTION_constitution_codeless_schema.md`, `HANDOFF_codeless_schema_moneta.md`, `DEEP_THINK_BRIEF_codeless_schema.md`, `SCHEMA_read_path_audit.md`, this file.

**Untouched per handoff §11 scope boundaries:** `Memory` dataclass, `EntityState` enum, `ECS`, `vector_index`, `consolidation`, `attention_log`, `durability`, `sequential_writer`, `mock_usd_target`, the four-op API surface, `Moneta` handle.

---

## Version

**Bumped to `1.2.0rc1` (PEP 440 canonical) / git tag `v1.2.0-rc1`.** Rationale (locked, not a question):

- Schema is an additive externally-visible contract: `MonetaMemory` typeName + camelCase attrs + `priorState` token enumeration are now visible to anyone who clones the repo or opens a Moneta-authored stage.
- Four-op API consumers are unaffected — the schema is below the four-op layer.
- `priorState` int → token IS a breaking change at the on-disk-USD-format layer, but the `§3 audit` confirmed no substrate consumers read it; only test fixtures, which were updated in lock-step.
- Minor bump (1.2.0) is correct semver. RC suffix gives a clean post-June promotion path: pin v1.2.0-rc1 for the send window, promote to v1.2.0 final after operator soak.

---

*Crucible, surgery complete. `v1.2.0-rc1` tagged.*
