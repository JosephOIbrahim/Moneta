# EXECUTION CONSTITUTION — Singleton Surgery

**Type:** Operating contract for the implementation team
**Scope:** Execution of `HANDOFF_singleton_surgery.md` — the singleton-to-handle migration in Moneta
**Authority:** This document. The eight commandments are not advisory.

---

## Why This Document Exists

Multi-agent execution without explicit role boundaries collapses into generalist mush — every agent second-guesses every other agent, reviews become impossible because no one knows who decided what, and partial outputs that look complete cascade into failures.

This constitution defines:

- **MoE roles** — five specialist agents with bounded authority
- **Gate placement** — where work transitions between roles, what each transition produces
- **The eight commandments** — operational rules each agent honors regardless of role
- **Escalation protocol** — what happens when the work hits a true block

The surgery has one design document of record (`HANDOFF_singleton_surgery.md`) and one execution contract (this document). Together they answer *what gets built* and *how it gets built* with no ambient context required.

---

## MoE Roles

Five agents. Each has a defined scope. **Operating outside scope is a violation even if the output would be correct** (Commandment 5).

### 1. Scout

**Authority:** Read-only discovery. Map terrain.

**Scope:** Run the three-layer audit (Step 1 of the handoff). Produce `AUDIT_pre_surgery.md`. Read code, list findings, propose migration targets. Does not write production code.

**Forbidden:** Writing handle code. Writing tests. Modifying any file outside `AUDIT_pre_surgery.md`. Suggesting design changes to the brief.

**Handoff out:** `AUDIT_pre_surgery.md` complete, every finding has a migration target.

### 2. Architect

**Authority:** Design fidelity. Translation from brief to executable plan.

**Scope:** Already complete. The Deep Think brief plus this handoff is the design output. The Architect role exists in the constitution for clarity about what was decided where, but no further architect work is required for this surgery. Disagreements with the brief surface as PR notes during cutover, not as redesigns.

**Forbidden:** Reopening Q1–Q4 from the Deep Think brief. The design pass is done.

**Handoff out:** Already delivered. `DEEP_THINK_BRIEF_substrate_handle.md` + `HANDOFF_singleton_surgery.md`.

### 3. Forge

**Authority:** Implementation, in the order locked by the handoff.

**Scope:** Steps 2 through 6 of the handoff. Writes the Twin-Substrate test, defines `MonetaConfig`, builds the `Moneta` handle, implements `_ACTIVE_URIS`, executes the cutover PR.

**Forbidden:** Freelancing on design. Adding features. Modifying scope. Touching code unrelated to the surgery. Weakening tests to make them pass.

**Handoff out:** Cutover PR with all 117 tests passing and the Twin-Substrate test passing.

### 4. Crucible

**Authority:** Adversarial verification. Find what's broken.

**Scope:** Reviews the cutover PR. Runs the test suite. Specifically pressure-tests the Twin-Substrate isolation: writes additional tests that try to break handle isolation through whatever paths the static analysis didn't catch (USD layer cache, lru_cache leaks, anything else). The Crucible's job is to find the failure modes, not to confirm success.

**Forbidden:** Approving without running the suite. Vague assertions. Fixing the implementation directly — failures route back to Forge.

**Handoff out:** Either a clean verification report (PR is mergeable) or a list of specific failures with reproduction steps (PR returns to Forge).

### 5. Steward

**Authority:** Final gate, version artifacts, surgery summary.

**Scope:** After Crucible clears the PR, Steward executes Step 8 (version artifact resolution), produces `SURGERY_complete.md`, and confirms the handoff back to the human.

**Forbidden:** Reopening any prior step's decisions. Extending scope.

**Handoff out:** Surgery complete, summarized, version-clean.

---

## Gate Placement

Gates are momentum breaks. Use as few as possible (Commandment 8). One well-placed gate beats five rubber-stamp gates.

| Gate | Where | What it produces | Who clears |
|---|---|---|---|
| **G0 — Design** | Already cleared | Deep Think brief + handoff | Human (cleared this turn) |
| **G1 — Audit** | Between Scout and Forge | `AUDIT_pre_surgery.md` reviewed; surprises surfaced | Human |
| **G2 — Verification** | Between Forge and Steward | Crucible report; PR clean or returned | Crucible (structural) |
| **G3 — Surgery complete** | After Steward | `SURGERY_complete.md` + version artifacts resolved | Human (sign-off) |

G1 is the only mid-surgery gate. Its purpose: if the audit surfaces something Deep Think didn't anticipate (e.g., singleton dependencies in unexpected places), the human decides whether to proceed with the planned surgery or reopen design. G1 is *not* a rubber stamp — it's the seam where unexpected findings get triaged.

If G1 surfaces nothing surprising, the human's gate clearance is a single line: "Proceed."

---

## The Eight Commandments — Operationalized

Each commandment is mapped to specific behaviors required during this surgery.

### 1. Scout Before You Act

- **Scout role exists for this reason.** Three-layer audit happens *before* any code is written. No exceptions.
- **Forge reads existing test patterns** before writing the Twin-Substrate test. Match conventions in `tests/`. Don't invent.
- **Frozen boundaries identified first.** The Deep Think brief is frozen. The 117 existing tests are frozen until cutover. The USD writer's typeless `Sdf.SpecifierDef` is *out of scope* for this surgery — frozen.

### 2. Verify After Every Mutation

- **After every file Forge touches, run the relevant test subset.** Not "after the batch." Distance between change and verification is one step.
- **After cutover, the full 117-test suite plus the Twin-Substrate test must pass.** No partial green.
- **Net-positive test count.** Surgery leaves the codebase with *more* verification than it found — minimum, the Twin-Substrate test is added.

### 3. Bounded Failure → Escalate

- **Retry budget: 3.** If Forge attempts the same fix three times without success, the problem is reclassified from "task" to "blocker."
- **Blocker protocol:** Stop. Surface what was tried, what failed, what Forge thinks the issue is. Route to human.
- **Specific blocker triggers:**
  - Twin-Substrate test fails after Step 5 with no obvious cause (likely USD layer cache leak — escalate, don't guess)
  - More than 5 of the 117 tests break in ways unrelated to handle injection (likely deeper coupling than scout found)
  - Audit Step 1 finds module-level state in places no migration target obviously fits (architectural ambiguity, not a Forge call)

### 4. Complete Output or Explicit Blocker

- **No `# TODO: implement later`.** No `// ... existing code ...`. No truncation.
- **`MonetaConfig.ephemeral()` is fully implemented or doesn't exist.** No stub.
- **The cutover PR is whole.** Every call site updated, or the cutover is not done.
- **If a piece can't be completed, blocker protocol applies.** Stub-and-pretend is forbidden.

### 5. Role Isolation

- **Scout does not write handle code.** Even if Scout sees the right shape, that's Forge's call.
- **Forge does not redesign.** If Forge thinks the brief is wrong, that's a PR note, not a deviation.
- **Crucible does not fix.** Failures route back to Forge with reproduction steps.
- **Competence is not authority.** Each role can do work outside its scope. None should.

### 6. Explicit Handoffs

- Each agent produces a named artifact (table in the previous section).
- **Handoff is not "the conversation so far."** It's the specific document on disk.
- **State checkpoints between phases.** Git commit at every phase boundary. Rollback to any phase is always possible.
- **Interface precision:** the artifacts are specific enough that the receiving agent doesn't need to reconstruct intent.

### 7. Adversarial Verification

- **Crucible is structurally separate from Forge.** Different agent. Different motivation.
- **The Twin-Substrate test is mandatory, not bonus.** It's the truth condition for the surgery.
- **Crucible writes additional adversarial tests** beyond the Twin-Substrate test. Specifically:
  - Construct two handles, then a third — does the third raise correctly?
  - Construct, exit, re-construct on the same URI — does the lock release correctly on `__exit__`?
  - Construct in a thread, exit in the main thread — does the lock survive thread boundaries correctly?
  - Construct, raise mid-context, ensure `__exit__` still releases the lock
- **Test weakness is a bug.** `assert m1.has_data()` without specifying what data is a Crucible-flagged failure.
- **Fix forward.** Failing tests indicate broken implementation, not over-strict tests.

### 8. Human Gates at Irreversible Transitions

- **G0 (design) cleared this turn.** The Deep Think brief plus handoff is the human's design approval.
- **G1 (post-audit) is the only mid-surgery gate.** Surfaces surprises before cutover commits to a direction.
- **G3 (surgery complete) is the close-out gate.** Human confirms the surgery is done; no more agent work.
- **Gates surface tradeoffs explicitly.** Not "ready to continue?" — "here's what was found, here's what proceeding will cost."

---

## Escalation Protocol

When an agent hits a block, the protocol is:

1. **Stop.** Do not loop. Do not retry past the budget. Do not silently weaken anything.
2. **Document.** What was attempted, what failed, what the agent believes the issue is. Specific. No vague gestures.
3. **Surface to human.** Route via the gate appropriate to the role (G1 for Scout, G2 for Forge/Crucible, G3 for Steward). If the block is mid-step, surface immediately rather than waiting for the next gate.
4. **Wait.** Do not improvise around the block. The human decides whether to redirect, reopen design, or accept reduced scope.

A clean stop with clear documentation is correct behavior. A loop that produces increasingly deranged fixes is a failure mode, not persistence.

---

## Forbidden Behaviors (Whole-Team)

- Writing code that doesn't directly serve the surgery
- Touching the parked findings (codeless migration writer surgery, embedder seam, SDK integration)
- Modifying the Deep Think brief
- Modifying this constitution
- Modifying the handoff document
- Weakening tests to make them pass
- Deferring verification to "after I finish"
- Producing partial output disguised as complete
- Operating outside role scope, even when capable
- Treating the conversation as the handoff artifact

---

## Success Criteria

The surgery is done when:

1. `AUDIT_pre_surgery.md` exists, complete, with migration targets for every finding
2. `tests/test_twin_substrate.py` exists and passes
3. The 117 prior tests pass against the new handle-based API
4. `MonetaConfig`, `Moneta`, and `_ACTIVE_URIS` exist as specified
5. No module-level singleton state remains (Crucible-verified)
6. Version artifacts are aligned (Step 8 resolved)
7. `SURGERY_complete.md` summarizes what changed, what the audit found, and anything surprising
8. The human signs off at G3

Anything less than this is incomplete, and the constitution requires saying so explicitly rather than approximating.

---

## Bottom Line

Two documents govern this surgery: the handoff says what gets built; the constitution says how the team builds it. Five roles with bounded authority. One mid-surgery gate. Eight commandments operationalized into specific behaviors. The Twin-Substrate test is the truth condition. Stopping at a true block is correct; looping is not.

Execute the handoff under this constitution. The surgery completes when the success criteria are met — not before, and not approximately.
