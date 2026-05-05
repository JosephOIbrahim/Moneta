# Round 4 — Spec-level surprises surfaced by the v1.0.0 multi-agent review

**Source:** `docs/review/synthesis.md` (constitution hash `3b56e3ffae083c9b`),
multi-agent review run on `claude/multi-agent-codebase-review-A8WHg`.
Brief: `docs/round4-brief.md`. Authority: `MONETA.md` §9.

**Date:** 2026-05-04 (closed same day the synthesis was authored).

**Status:** CLOSED. Six rulings issued. Specs amended in lockstep
(`MONETA.md`, `ARCHITECTURE.md`). One code change applied
(`MonetaConfig.quota_override` bound). All other items resolved by spec
clarification — the implementation already matches the rulings.

**Do not re-open without §9 escalation.**

---

## Round 4 context

The v1.0.0 review surfaced 8 findings tagged
`requires_section9_escalation: true`. The adversarial reviewer correctly
downgraded 2 of them (attention-log race → impl + docstring fix;
api.md → doc rewrite). The remaining 6 were genuine Trigger 2 candidates
(spec-level surprise): the v1.1.0 singleton surgery and the Phase 3
narrow-lock work amended the implementation surface in ways that the
specs were not amended to mirror, and the multi-agent review caught the
drift across loops 1–3.

This round closes those 6 items. None of them surfaced new architectural
research (unlike Round 3 which validated a structural-not-temporal
novelty claim). They are post-implementation reconciliation work between
specs that locked at different times.

---

## Ruling 1 — Four-op API surface is method calls on a `Moneta` handle

**Origin:** `architect-L1-four-op-signatures-drift` (Critical, §9).
`ARCHITECTURE.md` §2 specified module-level callables with self-less
signatures. v1.1.0 surgery (`DEEP_THINK_BRIEF_substrate_handle.md`)
converted them to bound methods on the `Moneta` class. The two were in
conflict.

**Decision:** Adopt the handle pattern as the canonical agent surface.
The four-op type signatures are unchanged; the surface is now method
calls on `m: Moneta`, e.g. `m.deposit(...)`. The fifth-op rule still
applies — `Moneta` may not gain a fifth public method on the agent
surface.

**Reasoning:**

- The v1.1.0 surgery was a correctness fix. The pre-v1.1.0 module-level
  singleton conflated the substrate (a per-storage-uri handle) with the
  module (a singleton, by definition). It was untestable in parallel
  and prevented an agent process from holding more than one Moneta
  substrate at a time. Reverting to module-level callables would
  re-introduce both problems.
- The four-op spec contract is *what* the agent calls (signatures and
  semantics), not *how* it is dispatched. A method call and a free
  function call are isomorphic at the agent's level of abstraction.
- The `_ACTIVE_URIS` registry (Ruling 4) anchors the per-process
  exclusivity that the v1.1.0 surgery introduced.

**Spec amendments:**

- `MONETA.md` §2.1 — note that the four operations are method calls on
  a `Moneta(config)` handle in implementation; the type signatures
  remain locked verbatim.
- `ARCHITECTURE.md` §2 — replace "module-level callables" framing with
  "method calls on `Moneta(config)` handle." Update §16 conformance
  check #1 to verify `Moneta` exposes exactly these four methods with
  matching signatures.

**Code:** Already conformant (v1.1.0 surgery, commit history under
`claude/audit-moneta-api-nvUfG`).

---

## Ruling 2 — Protected memories are pinned, not consolidated

**Origin:** `architect-L3-protected-consolidation-contradiction`
(Critical, §9) + `consolidation-L3-protected-floor-stage-trap`
(Critical). `MONETA.md` §2.5 promised protected entities consolidate to
`cortex_protected.usda`. `ARCHITECTURE.md` §6 selection criteria
require `Utility < 0.3` to stage; the protected-floor clamp pins
utility ≥ floor; floor ≥ 0.3 ⇒ never stages.

**Decision:** Protected memories are PINNED in the hot tier. Automatic
consolidation does not run on them. The `cortex_protected.usda`
sublayer in `MONETA.md` §2.5 is reserved for **explicit operator
unpin** (the Phase 3 unpin tool routes there); it is NOT a destination
for the automatic prune/stage selection.

**Reasoning:**

- The semantic of "protected" is "agent flagged this as important; do
  not discard." The §6 staging gate is a discard path (cold-tier
  demotion). Auto-staging a protected memory would contradict the
  protection promise.
- The protected-floor clamp's effect — `floor ≥ 0.3` makes
  `utility < 0.3` unreachable — is therefore correct by construction,
  not a bug. Phase 3 closure §4 already documented this as a "known
  limitation"; this ruling elevates it to a deliberate spec choice.
- The `cortex_protected.usda` sublayer remains the destination for
  explicit unpin routing (Phase 3 operator tool). When an agent or
  operator decides a protected memory should be demoted, the unpin
  tool clears `protected_floor`, and the entity then becomes eligible
  for normal §6 selection on its next pass.

**Spec amendments:**

- `MONETA.md` §2.6 (consolidation mechanics) — add: "Protected
  memories (`protected_floor > 0`) are pinned and exempt from
  automatic prune/stage selection. They route to
  `cortex_protected.usda` only via the explicit Phase 3 unpin tool."
- `ARCHITECTURE.md` §6 — add: "Selection criteria do not run against
  entities with `protected_floor > 0`. These are pinned in the hot
  tier; routing them to USD is the explicit unpin tool's
  responsibility (Phase 3, not part of the four-op API)."
- `ARCHITECTURE.md` §10 — clarify: "The 100-entry hard cap is the
  budget for pinned entries; pinning prevents demotion, so the cap
  bounds hot-tier protected occupancy."

**Code:** Already conformant. The decay clamp in `decay.py` and the
new lower-bound clamp in `ecs.py:apply_attention` (review
remediation, this branch) together guarantee protected utility never
falls below floor; §6 selection naturally skips them.

---

## Ruling 3 — Vector index is runtime-authoritative; ECS snapshot is across-restart authoritative

**Origin:** `architect-L2-vector-authoritative-vs-hydrate-inversion`
(High, §9), confirmed by
`adversarial-L2-hydrate-inversion-spec-surprise-confirmed`. §7
declares the vector index "authoritative for what exists." The
hydrate path rebuilds vector from ECS snapshot, inverting authority.

**Decision:** Spec the dual-authority pattern explicitly. Vector
index is **runtime-authoritative**: within a session, the
sequential-write protocol's no-2PC argument relies on vector being
the last writer. ECS snapshot is **across-restart authoritative**: it
is the durable record persisted to disk; on hydrate it is read first
and the vector index is reconstructed from it.

The atomicity guarantee is therefore a *within-session* property.
Across a restart boundary, the vector index begins as a faithful
shadow of the hydrated ECS, and within-session authority is restored
once construction completes.

**Reasoning:**

- The Phase 1 in-memory `VectorIndex` does not persist independently;
  its docstring already documents this and anticipates a Phase 2
  LanceDB swap. The hydrate inversion is a consequence of the
  in-memory shadow choice, not a spec violation in spirit.
- Inverting back — making vector across-restart authoritative —
  requires a separate vector-index snapshot file. That is Phase 2
  scope (LanceDB persistence) and is not a Phase 1 fix.
- The deposit-interrupted-mid-construction worry the adversarial
  reviewer raised (an ECS-only entity re-emerging on hydrate, then
  vector receives it via rebuild) is benign: the entity has a
  consistent ECS row, and the vector rebuild produces a consistent
  vector record. There is no entity in a torn state across restart.
- Documenting the dual-authority pattern lets future reviewers
  verify that the across-restart authority does not silently degrade
  the within-session guarantees.

**Spec amendments:**

- `ARCHITECTURE.md` §7 — add §7.2 "Dual-authority across restart"
  documenting the pattern. Phase 2 LanceDB swap is the path to making
  vector authoritative across restart, if needed.

**Code:** No change. The hydrate path is correct as-is.

---

## Ruling 4 — Handle exclusivity is per-process via `_ACTIVE_URIS`

**Origin:**
`architect-L2-handle-exclusivity-concurrency-model-unspecified`
(High, §9). The v1.1.0 `_ACTIVE_URIS` registry is documented in
README and `DEEP_THINK_BRIEF_substrate_handle.md` but absent from
`ARCHITECTURE.md`.

**Decision:** Elevate the v1.1.0 substrate-handle brief into
`ARCHITECTURE.md` §17 with explicit concurrency-model sub-clauses.

**Reasoning:**

- An unspecified concurrency model leads to drift. The next
  maintainer would derive incompatible behavior from the
  implementation's accidental properties.
- The current implementation is GIL-correct: `set` operations are
  atomic at the bytecode level under CPython, so check-then-add is
  sequential within a single process.
- Cross-process exclusion is intentionally NOT in scope for
  `_ACTIVE_URIS`; it is the bridge layer's concern (`bridge/`,
  flock-based, PR #1 on `claude/audit-moneta-api-nvUfG`).
- PEP 703 free-threading would invalidate the GIL atomicity argument.
  Migration to PEP 703 is a §9 Trigger 2 (spec-level surprise) — the
  registry would need an explicit `Lock`.

**Spec amendments:**

- `ARCHITECTURE.md` — new §17 "Handle exclusivity model" with the
  five sub-clauses below.
- `MONETA.md` §2 — add §2.11 cross-referencing §17 (the handle
  exclusivity model is now a locked foundation).

**Code:** Already conformant. The flock test in `tests/unit/test_api_flock.py`
on PR #1 covers cross-process exclusion at the bridge layer.

---

## Ruling 5 — `quota_override` bounded by a process-level safety ceiling

**Origin:** `architect-L3-quota-override-bypasses-section10-cap`
(High, §9). `MonetaConfig.quota_override: int = 100` is unbounded;
any caller can set it to `10_000_000` and silently bypass the §10
hard cap.

**Decision:** `quota_override` is allowed but bounded:
`1 ≤ quota_override ≤ 1000`. The default remains 100. Construction
with a value outside this range raises `ValueError`.

**Reasoning:**

- A per-handle override is genuinely useful: a long-running agent
  may legitimately need more than 100 protected entries. Forcing 100
  as an immutable ceiling would push consumers toward
  multi-handle workarounds (Ruling 6 already cautions against
  treating multi-handle as a per-handle quota multiplier).
- An unbounded override defeats the §10 backstop entirely. "Hard
  cap" loses meaning.
- 1000 (10× the default) is a generous ceiling that accommodates
  legitimate use cases while still constraining the worst case.
  Phase 3 unpin tool is the path beyond 1000.

**Spec amendments:**

- `MONETA.md` §2.10 — amend "Hard cap: 100 protected entries per
  agent" to "Default cap: 100; per-handle override permitted up to a
  ceiling of 1000."
- `ARCHITECTURE.md` §10 — same.

**Code:** Add `MAX_QUOTA_OVERRIDE = 1000` constant to
`src/moneta/api.py`; validate `MonetaConfig.quota_override` in
`__post_init__`; raise `ValueError` on out-of-range. Add regression
tests.

---

## Ruling 6 — `_ACTIVE_URIS` enforces per-substrate-handle scope; multi-handle aggregation is by design

**Origin:** `adversarial-L1-multi-handle-protected-quota-aggregation`
(High, §9). One process × N handles × 100 protected entries each =
100N total. §10 "per agent" was ambiguous between "per process" and
"per substrate handle."

**Decision:** Disambiguate "per agent" to "per substrate handle." A
substrate is identified by `storage_uri`; each handle is a distinct
substrate; each substrate has its own quota.

Multi-handle aggregation is the explicit design: an agent that
constructs N substrates is doing N distinct memory tracks. The
process-level total (100N, capped at 1000N after Ruling 5) is a
property of the agent's deployment topology, not a property of any
single substrate.

**Reasoning:**

- A "substrate" is a memory track. An agent that wants two
  independent memory tracks (e.g. user-A vs user-B) constructs two
  handles and gets two independent quotas. Forcing them to share a
  100-entry budget would conflate the topology.
- A process-level cap is a different feature: a shared budget across
  all live handles. It is not a cleanup or correctness fix; it is a
  policy choice that should be opt-in if needed (e.g. a process-level
  `_TOTAL_PROTECTED_BUDGET` that all handles atomically check). Out
  of scope for Phase 3.
- The Ruling 5 ceiling (1000 per handle) limits the per-substrate
  worst case; the multi-handle aggregate is bounded by the number of
  active handles the process can sustain, which is bounded by the
  storage URI namespace and the bridge layer's flock semantics
  (PR #1).

**Spec amendments:**

- `MONETA.md` §2.10 — amend "per agent" to "per substrate handle"
  and add a note: "An agent process may hold multiple handles on
  distinct storage URIs; each handle's quota is independent."
- `ARCHITECTURE.md` §10 — same.

**Code:** No change. Already conformant: each `Moneta` handle holds
its own ECS, and `count_protected()` is per-handle.

---

## Lineage

- **Round 1** — initial scoping brief (Claude + Joseph Ibrahim).
- **Round 2** — Gemini Deep Think architectural plan.
- **Round 2.5** — Claude review (prior art, benchmark, four blockers).
- **Round 3** — Gemini Deep Think plan validation; structural-not-temporal
  novelty claim confirmed.
- **Round 3 Closure** — Joseph + Claude plan ratification, build
  authorized.
- **Round 4** — *this round*. Multi-agent review (Opus 4.7, MoE roles,
  5-loop) surfaces post-implementation spec drift between v1.1.0 surgery
  + Phase 3 narrow lock + Pass 6 closure and the locked specs. Six
  rulings issued. No new architectural research; reconciliation only.

---

## Process notes

This round did NOT go to Gemini Deep Think. The trigger types matter:

- Round 1–3 sought architectural input on open questions.
- Round 4 surfaced reconciliation work between specs that drifted
  internally as the implementation evolved through v1.0.0 → v1.1.0 →
  v1.2.0-rc1. None of the items required external scoping; each had
  a clear locally-correct ruling derivable from the existing
  artifacts plus the ratified implementation history.

The constitution's §9-inflation guard (`docs/review-constitution.md`
§6, §8) caught two mis-classifications during the review run itself
(adversarial-L2 attention-log, adversarial-L5 api.md collapse) — those
did NOT enter Round 4, demonstrating the routing layer works.

Round 5 will be a Gemini Deep Think round if and only if Phase 3
operational data, Phase 4 cross-substrate composition (Octavius
join), or PEP 703 free-threading migration produces an item that
*requires* external architectural input. None is anticipated at the
v1.0.0 horizon.

---

*Round 4 closed 2026-05-04 by Architect (Claude). Spec amendments
land in this commit. Brief: `docs/round4-brief.md` (now superseded by
this file).*
