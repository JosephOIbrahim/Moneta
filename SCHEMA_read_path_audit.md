# SCHEMA_read_path_audit

**Step 1 of `HANDOFF_codeless_schema_moneta.md` §9.**
**Role:** Auditor (read-only).
**Scope:** Every `Usd.Stage.Open` call site in `src/` and `tests/`, plus the related `Sdf.Layer.FindOrOpen` fallbacks that materialize existing on-disk USD content into the runtime.
**Format:** file:line, classification, reads `prior_state`? (yes/no), notes — per handoff §3.

---

## Verdict (handoff §3 lookup)

> **Substrate-path reads of `prior_state` do not exist in the Moneta repo as of `8b4609a`.**
>
> Per handoff §3 verdict table: **read-tolerance lives in test fixtures only. The substrate hydration layer is untouched by this surgery.**

This means handoff §7 ("Read-Path Branching, Conditional on §3 Audit") collapses to its second clause: *"If the audit finds no substrate-side reads, this branching lives only in test fixtures that read written stages back. The substrate code is untouched beyond the writes in §6."*

The `_token_to_state` helper from handoff §7 is **still authored** by Forge — it is needed by `tests/unit/test_usd_target.py` after the schema migration switches `prior_state` (int) → `priorState` (token). It lives in `src/moneta/usd_target.py` as a module-level helper next to `_state_to_token`, but is not invoked from any substrate code path. Test fixtures import it from `usd_target`.

---

## Audit table — every USD-content-entry call site

`Usd.Stage.Open` plus `Sdf.Layer.FindOrOpen`. (Layer creation calls — `Sdf.Layer.CreateAnonymous` and `Sdf.Layer.CreateNew` — are excluded: they produce empty layers and cannot be a read entry-point. They are noted at the bottom of this section for completeness only.)

| File:line | Call | Classification | Reads `prior_state`? | Notes |
|---|---|---|---|---|
| `src/moneta/usd_target.py:154` | `Sdf.Layer.FindOrOpen(root_path)` | **Substrate path** | **no** | Fallback when `Sdf.Layer.CreateNew(root_path)` returns `None` (the file already exists). Reached when a Moneta handle constructs against a `usd_target_path` that already holds a `cortex_root.usda`. The opened layer object is assigned to `self._root_layer` and used only to compose the sublayer stack and to receive subsequent writes. The substrate never iterates the loaded PrimSpecs. |
| `src/moneta/usd_target.py:156` | `Usd.Stage.Open(self._root_layer)` | **Substrate path** | **no** | Wraps the root layer in a `UsdStage`. The stage object is held on `self._stage` for the lifetime of the handle and exposed via the `stage` property (`usd_target.py:302-305`) for test inspection. The substrate never calls `stage.Traverse()`, `stage.GetPrimAtPath()`, or any other prim-fetching method on this stage. (`stage.Traverse()` is used inside the benchmark script, not in `src/`.) |
| `src/moneta/usd_target.py:178` | `Sdf.Layer.FindOrOpen(layer_path)` | **Substrate path** | **no** | Fallback for non-root sublayers (`cortex_protected.usda`, `cortex_YYYY_MM_DD.usda`, rotation continuations). Same posture as line 154 — opened, registered in `self._layers`, used for writes only. |
| `tests/unit/test_usd_target.py:310` | `reloaded_stage = Usd.Stage.Open(str(root_file))` | **Test fixture** | **yes (transitively)** | Reload-and-inspect test for the round-trip path. The reloaded stage is iterated and `GetAttribute("prior_state").Get()` is asserted at `tests/unit/test_usd_target.py:127`. **This call site is exactly the read-tolerance surface that needs to learn about typed/typeless branching after the schema migration.** |
| `tests/unit/test_usd_target.py:467` | `reloaded = Usd.Stage.Open(str(root_file))` | **Test fixture** | **yes (transitively)** | Same posture as line 310 — round-trip reload, with the corresponding `prior_state` assertion at `tests/unit/test_usd_target.py:378`. |
| `scripts/usd_metabolism_bench_v2.py:235` | `stage = Usd.Stage.Open(primary_layer)` | **Diagnostic / debug** | **no** | Phase 2 / Pass 5 benchmark harness. Out of scope: the benchmark script is not on any release path, has no production consumer, and authors its own benchmark prims (`Xform`, not `MonetaMemory`). The schema migration does not touch this script. |

**Excluded (layer-creation, not entry-points):**
- `src/moneta/usd_target.py:148` — `Sdf.Layer.CreateAnonymous("cortex_root")` (in-memory mode root)
- `src/moneta/usd_target.py:152` — `Sdf.Layer.CreateNew(root_path)` (fresh disk-backed root)
- `src/moneta/usd_target.py:173` — `Sdf.Layer.CreateAnonymous(name)` (in-memory sublayer)
- `src/moneta/usd_target.py:176` — `Sdf.Layer.CreateNew(layer_path)` (fresh disk-backed sublayer)

These produce empty layers, never load existing PrimSpecs, and cannot be a read path for `prior_state`.

**No `AMBIGUOUS` rows.** Every call site classifies cleanly.

---

## Where `prior_state` is actually read in the repo today

The audit's primary purpose (handoff §3) is to locate the `prior_state` read surface. It is exclusively test-side:

| File:line | Read shape | Exercises the substrate? |
|---|---|---|
| `tests/unit/test_usd_target.py:127` | `prim.GetAttribute("prior_state").Get() == int(EntityState.STAGED_FOR_SYNC)` | Reads a freshly-authored prim from the in-test stage. Substrate write → test read. |
| `tests/unit/test_usd_target.py:378` | Same shape, different test | Same posture. |
| `tests/integration/test_end_to_end_flow.py:266, 276` | Reads `entry["prior_state"]` from `MockUsdTarget` JSONL buffer | **Not a USD read.** MockUsdTarget serializes to JSON; the `prior_state` key is a JSONL field, not a USD attribute. Out of scope for this surgery. |

**Test-fixture read sites Crucible / Forge will update during step 6+ for the int→token migration:**
- `tests/unit/test_usd_target.py:127`
- `tests/unit/test_usd_target.py:378`

**Test-fixture sites that stay unchanged:**
- `tests/integration/test_end_to_end_flow.py:266, 276` — MockUsdTarget JSONL key remains `prior_state` (Python-side snake_case stays per handoff §6 mapping table). The MockUsdTarget JSONL contract is independent of the USD camelCase schema; mock target is not a `MonetaMemory` authoring path.

---

## Substrate write-path attribute names today (reference)

For the boundary-mapping helpers Forge will author at step 5. The substrate currently writes these attribute names via `Sdf.AttributeSpec` at `src/moneta/usd_target.py:252-263`:

| Substrate write-side (snake_case, today) | Schema-mandated (camelCase, post-step 3) |
|---|---|
| `payload` | `payload` |
| `utility` | `utility` |
| `attended_count` | `attendedCount` |
| `protected_floor` | `protectedFloor` |
| `last_evaluated` | `lastEvaluated` |
| `prior_state` (`Sdf.ValueTypeNames.Int`) | `priorState` (`Sdf.ValueTypeNames.Token`) |

All six rewrites are in handoff §6. Confirmed against `src/moneta/usd_target.py:252-263` lines verbatim.

---

## Notes & cross-cutting findings

Per constitution §5: *"If the Auditor finds something interesting outside the audit scope, it goes in `notes:` on the audit doc, not into action."* These are flagged for the receiving roles, not acted on by the Auditor.

1. **`EntityState.PRUNED` is referenced in handoff §6's `_STATE_TO_TOKEN` example, but does not exist in `src/moneta/types.py`.** The current enum at `types.py:18-29` has exactly three members: `VOLATILE = 0`, `STAGED_FOR_SYNC = 1`, `CONSOLIDATED = 2`. There is no `PRUNED` member; pruned entities are removed from the ECS entirely (`ecs.py:110-134`, `consolidation.py:166-169`) rather than transitioning to a `PRUNED` state. The `_STATE_TO_TOKEN` literal as written in handoff §6 would raise `AttributeError: PRUNED` at module import time. **Forge surfacing required at step 5.** The brief (§7.2) and the schema spec (handoff §4 — `allowedTokens = ["volatile", "staged_for_sync", "consolidated", "pruned"]`) both include `"pruned"` as a token, which is consistent with each other but inconsistent with the runtime enum. Possible reconciliations the Forge / Schema Author will need a ruling on (Auditor surfaces, does not propose):

   - (a) Schema's `allowedTokens` keeps `"pruned"` as a forward-looking value; `_STATE_TO_TOKEN` only contains the three currently-extant enum members. No write path produces `"pruned"` in v1.2.0; the token is reserved for a future PRUNED-as-tombstone surgery. *Within scope per handoff §11 (no `EntityState` change).*
   - (b) `EntityState` gains a `PRUNED = 3` member to match the schema. *Out of scope per handoff §11 — would be a constitution halt-and-report at step 5.*
   - (c) Schema's `allowedTokens` drops `"pruned"` to three values matching the enum. *Conflicts with the brief's locked verdict at §7.2 — would require a §1 brief amendment.*

   The Schema Author proceeds with the schema as-specified (four tokens) at step 3. The Forge resolves at step 5 — most likely (a). Halt-and-report applies if (b) or (c) is the right answer.

2. **`stage.Traverse()` in the substrate is referenced in a docstring only.** `src/moneta/usd_target.py:14` mentions `stage.Traverse()` in the writer-lock-scope docstring as the read pattern that the narrow lock allows concurrent with `Save()`. There is no actual `Traverse()` call in `src/`. The docstring describes the *contract* the narrow lock provides for hypothetical concurrent readers; today's "concurrent reader" is exclusively test code (`tests/unit/test_usd_target.py:380` and `tests/integration/test_real_usd_end_to_end.py:393` use `target.stage.Traverse()`). Confirms substrate-write-only posture.

3. **`UsdTarget.stage` property is exposed as a public attribute** (`src/moneta/usd_target.py:302-305`). Tests and external callers can access the live stage and call any `pxr` method on it. The schema migration's read-tolerance posture relies on the convention that the substrate itself does not iterate prims; it does not enforce that consumers don't either. Out of scope, noted.

4. **The `Memory` dataclass exposes `usd_link: Optional[object]`** (`src/moneta/types.py:72`). This field is populated by the substrate (currently always `None`; ECS keeps the slot for forward-looking USD-path linking). It is **not** read from USD on the substrate path; ECS rows arrive at `Memory` projection via `_row_to_memory` (`ecs.py:311-323`) which sources from internal arrays. No read-tolerance implication.

5. **The pre-existing `dist/` directory was emptied during the v1.1.0 surgery**; no v1.1.0 wheel was regenerated (deferred per `SURGERY_complete.md`). Independent of this surgery.

---

## Constraints lifted by this audit

For the receiving roles' planning:

- **Schema Author (step 3):** authors `schema/MonetaSchema.usda`, `schema/plugInfo.json`, runs `usdGenSchema --skipCodeGeneration` to produce `schema/generatedSchema.usda`. No Python touches. Free to commit `schema/` artifacts without coordination on substrate code.
- **Forge (step 5):** modifies `src/moneta/usd_target.py` per handoff §6. Authors `_state_to_token` and `_token_to_state` helpers at module scope. Updates the six `_set_attr` calls to camelCase + token. Does **not** add a substrate read path; the `_token_to_state` helper is exported for test consumers only, not invoked from substrate code. Resolves the `EntityState.PRUNED` discrepancy (Note 1 above) at start-of-step.
- **Forge (step 6):** read-path branching collapses to test-fixture branching only, per the audit's verdict. The two tests at `tests/unit/test_usd_target.py:127` and `:378` are the only sites where the typed/typeless decision lives.
- **Crucible (step 2 + step 7):** writes the §8.1 acceptance gate test as the first commit after this audit. The gate test reads from a freshly-authored stage in a clean subprocess; it always sees a typed `MonetaMemory` prim (substrate writes only the new shape), so the gate test does not need typeless-branch coverage. The §8.3 read-path branching tests cover the typeless legacy path against synthetic untyped prims authored directly by the test, since no substrate code path produces them after step 5.

---

## Audit completeness check (constitution §4)

- [x] Every `Usd.Stage.Open` call site in `src/` and `tests/` is in the table.
- [x] Every related `Sdf.Layer.FindOrOpen` call site is in the table (read entry-points beyond `Stage.Open`).
- [x] Each row classified as Substrate / Test fixture / Diagnostic.
- [x] Each row marks `prior_state` read (yes / no, with transitive flag where the read happens via a separate line in the same test).
- [x] No row left `TBD`. No row marked `AMBIGUOUS`.
- [x] Layer-creation calls (excluded as non-entry-points) listed for completeness.
- [x] Cross-cutting findings recorded in `notes:` per role-isolation discipline.

---

*Auditor, step 1 complete. Handing off to Crucible (step 2 — write the §8.1 acceptance gate test, watch it fail).*
