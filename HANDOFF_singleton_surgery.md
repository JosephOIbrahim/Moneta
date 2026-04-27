# HANDOFF: Singleton Surgery — Moneta Substrate Handle

**Type:** Design handoff. Implementation phase.
**Repo:** `C:\Users\User\Moneta`
**Design document of record:** `DEEP_THINK_BRIEF_substrate_handle.md` (at repo root, with the Deep Think response appended as Section 5)
**Companion document:** `EXECUTION_constitution_singleton_surgery.md` — operating rules for the implementation team

---

## What This Is

The scout pass (`SCOUT_MONETA_v0_3.md`) identified a module-level singleton at `api.py:124` (`_state`) plus process-wide `PROTECTED_QUOTA = 100` as the master substrate-leak — the single decision that makes Moneta a product instead of a substrate.

A design pass via Gemini Deep Think locked the architecture. The verdict and full reasoning are in `DEEP_THINK_BRIEF_substrate_handle.md`. This handoff does not re-litigate the design. It executes it.

---

## What Was Decided (Summary, Not Source of Truth)

The full reasoning lives in the brief. This is the spine.

| Decision | Locked answer |
|---|---|
| **Shape** | Dependency-injected handle — `Moneta(config)` returns a handle, methods hang off it |
| **Lifecycle** | Context manager from day one — `with Moneta(config) as substrate:` |
| **Configuration** | Frozen `MonetaConfig` dataclass, `kw_only=True`, single argument to constructor |
| **No-arg default** | Forbidden — `Moneta()` must raise `TypeError` |
| **Test ergonomics** | `MonetaConfig.ephemeral()` factory for test boilerplate |
| **Reconstruction policy** | Two handles on the same `storage_uri` raise `MonetaResourceLockedError` |
| **Exclusivity mechanism** | In-memory `_ACTIVE_URIS` registry. No file locks. No transactions. No retry queues. |
| **Migration path** | Hard cutover, single PR, 117 tests as the gate |
| **Verification gate** | Twin-Substrate test passes — written first, watched fail, then made to pass |

The Twin-Substrate test is the surgery's truth condition. The 117 passing tests are the regression net. Both must be green for the surgery to be done.

---

## Surgery Sequence (Locked Order)

The constitution document governs *how* each step is executed. This document governs *what order* they happen in.

**Step 1 — Three-layer audit, before any code is written.**

Run the audit procedure from the Deep Think brief, Q2:
- Configure `ruff` for `B006`, `B008`, `RUF012`. Run it. Resolve or document every finding.
- Grep for `@functools.lru_cache`, `@cache`, `@cached_property` at module level. List every hit. These migrate to instance-level dictionaries on the handle.
- Note: the USD `Sdf.Layer.FindOrOpen` C++ registry trap is invisible to static analysis. The Twin-Substrate test (Step 2) is the only catch.

Output: `AUDIT_pre_surgery.md` listing every finding from layers 1 and 2, plus the migration target for each.

**Step 2 — Write the Twin-Substrate regression test. Watch it fail.**

The test from the Deep Think brief, Q2:
- Construct `m1 = Moneta(uri_a)` and `m2 = Moneta(uri_b)` in the same process
- Write data to `m1`
- Assert `m1` contains the data, `m2` does not
- Assert `m1`'s quota is decremented, `m2`'s quota is untouched

The test will fail today. That's correct. It becomes the gate the surgery has to clear.

**Step 3 — Define `MonetaConfig`.**

Frozen dataclass, `kw_only=True`, fields per the Deep Think brief Q3:
- `storage_uri: str` (irreducible)
- `quota_override: int = 100` (irreducible, replaces `PROTECTED_QUOTA`)
- Cloud-anticipated fields (`tenant_id`, `sync_strategy`) commented but not implemented

Plus `MonetaConfig.ephemeral()` classmethod for test ergonomics.

**Step 4 — Build the `Moneta` handle class.**

Owns config. Owns state. Context-manager protocol (`__enter__`, `__exit__`). All operations that previously read `_state` now read `self.<field>`. All caches that were module-level migrate to instance attributes.

**Step 5 — Implement `_ACTIVE_URIS` exclusivity registry.**

Module-level set. `__enter__` checks membership, raises `MonetaResourceLockedError` on overlap, adds on success. `__exit__` removes. This is the Q4 invariant — in-memory exclusivity, nothing more.

**Step 6 — Hard cutover of all call sites.**

Single PR. Every consumer of the singleton becomes a consumer of an explicitly-passed handle. Tests update accordingly. The 117 tests are the gate — all green or the cutover is not done.

**Step 7 — Verify the Twin-Substrate test passes.**

If it doesn't, the surgery isn't done — even if the 117 tests are green. Green tests with a failing Twin-Substrate test means the singleton survived in some form the static audit didn't catch. Most likely candidate: a USD layer-cache leak. Fix it before declaring done.

**Step 8 — Update version artifacts.**

The scout flagged `dist/moneta-0.2.0` against `pyproject.toml v=1.0.0`. Resolve as part of the surgery PR. Version becomes whatever the surgery merits.

---

## Hard Constraints

1. **The Deep Think brief is the design source of truth.** Disagreements with the brief are flagged as notes in the PR — not implemented as deviations.

2. **Step order is locked.** Test before handle. Audit before test. The order encodes the safety properties — reordering forfeits them.

3. **No scope expansion.** Concurrency correctness, identity, auth, cloud deployment, observability — all explicitly downstream. If the implementation feels like it needs them, that's the seam from Q4 trying to creep. Honor the seam.

4. **No silent test weakening.** If a test breaks during cutover, the implementation is wrong — not the test. Fix forward.

5. **Twin-Substrate test is non-negotiable.** It's the only check on the USD C++ registry trap, which static analysis cannot see. Without it, "surgery complete" is unverifiable.

6. **The constitution governs execution.** `EXECUTION_constitution_singleton_surgery.md` is the operating contract for the team. The eight commandments are not advisory.

---

## Handoff Artifact Contract

This document hands off to the implementation team. The team's outputs:

| Artifact | Produced when | Contents |
|---|---|---|
| `AUDIT_pre_surgery.md` | After Step 1 | Three-layer audit findings, migration targets |
| `tests/test_twin_substrate.py` | After Step 2 | The regression test, failing initially |
| Cutover PR | After Step 6 | Single PR, 117 tests passing, Twin-Substrate test passing |
| `SURGERY_complete.md` | After Step 7 | One-page summary: what changed, what was found in audit, anything surprising |

If any step blocks, the team escalates per the constitution's bounded-failure protocol. Stopping is correct behavior at a true block. Looping is not.

---

## What This Surgery Is Not

- Not the cloud surgery. That's downstream and depends on this being clean.
- Not the codeless schema migration. Independent track, can run in parallel post-surgery.
- Not the inside-out SDK integration. Net-new work, no refactor needed, also independent.
- Not the benchmark/token-economics layer. Different scope entirely.
- Not a refactor pass for code quality. Touch only what the surgery requires touching.

The surgery is one thing: replacing the singleton with a handle, cleanly, in a way that doesn't foreclose what comes next. Discipline on scope is what makes the next surgeries possible.
