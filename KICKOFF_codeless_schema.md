# KICKOFF — Codeless Schema Migration

**Single-prompt entry point for the implementation harness.**
**Invocation:** `Read KICKOFF_codeless_schema.md and execute.`
**Disposition:** Local-only post-creation. Stays in the repo as the historical kickoff record for this surgery.

---

## Pre-flight

Four documents govern this surgery. They must be committed to `origin/main` before step 1 begins:

1. `KICKOFF_codeless_schema.md` (this file)
2. `EXECUTION_constitution_codeless_schema.md`
3. `HANDOFF_codeless_schema_moneta.md`
4. `DEEP_THINK_BRIEF_codeless_schema.md`

**First action — commit pre-flight:**

If the four documents above are not yet committed to `origin/main`, the harness's first action is:

```
git add KICKOFF_codeless_schema.md \
        EXECUTION_constitution_codeless_schema.md \
        HANDOFF_codeless_schema_moneta.md \
        DEEP_THINK_BRIEF_codeless_schema.md
git commit -m "docs: codeless schema surgery design + handoff + constitution"
git push
```

The harness verifies all four files are tracked and the commit is on `origin/main` before reading the constitution. If the commit pre-flight fails (e.g., one document is missing from disk, git push is rejected, network is unavailable), the harness halts and reports — no work begins on a half-committed surgery.

---

## Document priority

```
EXECUTION_constitution_codeless_schema.md  →  governs HOW
HANDOFF_codeless_schema_moneta.md          →  governs WHAT
DEEP_THINK_BRIEF_codeless_schema.md        →  governs WHY
```

Read the constitution first. Read the handoff second. Read the brief once for context — do not re-litigate verdicts.

When the documents disagree, the constitution outranks the handoff outranks the brief. (This should not happen. If it does, halt and report per constitution.)

---

## Operating rules

These rules sit on top of the constitution. The constitution defines the universal posture; these are the surgery-specific specifics that the harness applies as it begins.

1. **Surgery sequence is locked at handoff §9.** Execute in order. Do not start step N+1 until step N's gate passes.

2. **Step 1 is the §3 audit (handoff).** Auditor role. Output: `SCHEMA_read_path_audit.md`. Read-only repo traversal. No schema code authored at this stage.

3. **The acceptance gate test (handoff §8.1) is written FIRST, watched FAIL, then made to pass.** Do not skip the watch-it-fail step. The first failure mode must be `FindConcretePrimDefinition returns None`. This proves the test is real and not a rubber stamp.

4. **One human gate.** Between Schema Author's commit and the Forge's first mutation to `usd_target.py`. The harness surfaces the gate content per constitution §8 and waits for explicit approval.

5. **Halt conditions are non-negotiable.** Constitution §"Halt Conditions Specific to This Surgery" lists seven cases. When one of those conditions is met, the harness halts and reports. It does not absorb, guess, or work around.

6. **Commit cadence: one commit per surgery-sequence step.** Commit messages are role-tagged: `[<Role>] step <N>: <one-line summary>`. Push after every commit.

7. **Tag two checkpoints:**
   - `pre-implementation` — after Schema Author's final commit, before the human gate
   - `v1.2.0-rc1` (or alternate version per Joe's confirmation at the final gate) — after acceptance gate §10 is conjunctively green

8. **Patent posture during execution:** schema artifacts are committed (visible). Design rationale stays local-only. Commit messages stay technical. No cognitive-architecture framing in code or commit history.

9. **Roles are isolated per constitution §5.** Auditor, Schema Author, Forge, Crucible. No freelancing. The Forge does not author schemas. The Schema Author does not modify Python. Crucible does not relax tests.

10. **The harness never silently degrades.** Tests are not weakened. Scope is not silently expanded. `# TODO` comments are not committed. If the harness wants to leave any of these, that is signal — halt and report instead.

---

## Begin

When the four pre-flight documents are committed to `origin/main` and verified:

> **Begin step 1: the §3 audit.**
> **Role: Auditor. Output: `SCHEMA_read_path_audit.md`.**
> **Read-only. No mutations to source code or tests.**

The audit's findings determine where read-tolerance lives in the implementation. Audit format and contents are specified in handoff §3. When the audit is complete and committed, the harness proceeds to step 2 of the surgery sequence.

---

**End of kickoff. Constitution governs from this point forward.**
