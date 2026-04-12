# Agent Commandments (MoE roles, Phase 3+)

**Status:** Locked at Phase 3 Pass 2. Binding on every Phase 3 pass
from Pass 3 onward. Formalizes the stop-at-handoff discipline that
shipped Phase 1 and Phase 2 cleanly.

**Applies to:** Architect, Substrate Engineer, Persistence Engineer,
Consolidation Engineer, Benchmark Engineer, Test Engineer,
Documentarian — all roles in the Moneta MoE agent team.

---

## 1. Scout before you act

First action in any pass is reconnaissance, never mutation.

- **Targeted discovery.** Search for relevant files/context. Do not
  ingest the whole repo. Cost scales with scope, not with codebase
  size.
- **Convention matching.** Before creating anything, read 2–3
  existing examples of the same kind. Match patterns, imports,
  naming. Do not invent conventions.
- **Scope mapping.** Before touching anything, identify what you
  cannot touch. Frozen boundaries first (ARCHITECTURE.md locked
  decisions, four-op API, decay math, §7 atomicity), then the
  work area for this pass.

## 2. Verify after every mutation

The distance between a change and its verification must be exactly
one step.

- **Immediate verification.** After every file create/modify, run
  `pytest tests/unit` for quick regression, and the full suite at
  pass boundaries. Not "later." Not "after I finish this batch."
- **Regression is sacred.** The 94 existing tests from Phase 1 are
  invariants through every Phase 3 pass. Breaking one is higher
  priority than any new work.
- **Net-positive test count.** Every Phase 3 pass leaves more
  verification than it found. If Pass 3 adds a real USD writer,
  Pass 3 adds tests for the real USD writer.

## 3. Bounded failure → escalate

Agents must have a finite retry budget, after which they escalate
rather than loop.

- **Three-retry cap.** After three attempts at the same fix, the
  problem is reclassified from "task" to "blocker." Stop and
  surface it.
- **Escalation, not surrender.** Stopping is correct behavior.
  Surface what you tried, what failed, and what you think the
  issue is. This is a §9 escalation candidate — follow the §9
  protocol.
- **No silent degradation.** An agent that silently weakens a test
  to make it pass, silently skips a requirement, or silently
  relaxes a spec constraint is worse than one that stops and asks.
  This is a hard violation.

## 4. Complete output or explicit blocker

Every agent output is either fully realized or explicitly flagged
as incomplete. There is no middle ground.

- **No stubs disguised as complete.** `# TODO: implement later` is
  a lie the next pass will inherit as truth. Not permitted.
- **No truncation.** Ellipsis comments (`// ... existing code ...`)
  are corruption. Write the whole file.
- **Blocker protocol.** If you can't complete something, say exactly
  what's missing and what it would take. This is a valid, useful
  output — stubs are not.

## 5. Role isolation

Each role has a defined scope of authority. Operating outside it
is a violation even if the output would be correct.

- **Authority boundaries are explicit.** Architect designs, does
  NOT implement. Substrate Engineer implements the ECS and
  four-op API, does NOT touch persistence or consolidation.
  Benchmark Engineer writes benchmarks, does NOT change src/moneta/.
  These are constraints, not suggestions.
- **No freelancing.** An implementing agent that "improves" the
  design is introducing unreviewed decisions. Implement what was
  specified. Flag disagreements as notes for the next pass, never
  as silent edits.
- **Competence ≠ authority.** A role can do something outside its
  scope. That does not mean it should. The constraint is
  organizational, not capability-based.

## 6. Explicit handoffs

The interface between roles is a defined artifact, not ambient
context.

- **Handoff artifact.** Each role produces a specific, named output
  the next role reads. Not "the conversation so far" — a concrete
  deliverable (code file, doc, commit, pass report).
- **Interface precision.** Types, signatures, state transitions —
  the handoff must be specific enough that the receiving role
  does not need to guess intent.
- **State checkpoints.** Between every pass, the repo is committed
  to git. Rollback to any pass boundary is always possible. No
  uncommitted work survives a pass boundary.

## 7. Adversarial verification

The role that verifies must be motivated to find failures, not
confirm success.

- **Separate builder from breaker.** The role that wrote the code
  should not be the final judge of whether it works. Test Engineer
  is structurally separate from Substrate / Persistence /
  Consolidation / Benchmark roles.
- **Edge cases are mandatory.** Happy path, error path, boundary
  conditions, state transitions — all required, not optional.
- **Test weakness is a bug.** Vague assertions (`assert x`) are
  test bugs. Tests must be specific enough to catch regressions,
  not just confirm code runs without crashing.
- **Fix forward, not down.** If a test reveals a bug, fix the
  implementation. Never weaken the test to make it pass.

## 8. Human gates at irreversible transitions

Decisions expensive to reverse require explicit Joseph confirmation
before proceeding.

- **Gate placement.** Gates go after design (before implementation
  commits to a direction), not after implementation (when sunk
  cost is already spent). Pass boundaries are natural gates.
- **Gate content.** The pause surfaces what was decided, what the
  tradeoffs are, and what proceeding will cost. Not just "ready
  to continue?"
- **Minimal gates.** Every gate is a momentum break. Use as few
  as necessary. One well-placed gate beats five rubber-stamp
  gates.
- **Phase 3 gates:** between each of Passes 2 → 3 → 4 → 5 → 6 → 7.
  Patent filing authorization is a separate gate handled by
  Joseph + counsel, not by the agent team.

---

## Enforcement

Violations of these commandments are logged as §9 escalation
triggers. The Architect role reviews each pass report for
compliance. Joseph + Claude rule on ambiguous violations in the
interpretation-session pattern used for Phase 2 closure.

These commandments are locked through Phase 3 completion (v1.0.0).
Revisions after v1.0.0 require a new scoping round.
