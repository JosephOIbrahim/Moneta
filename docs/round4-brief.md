# Round 4 escalation brief — surfaced by multi-agent review v1.0.0

**Status:** SUPERSEDED. Round 4 closed 2026-05-04; this brief is
historical. Closure document: `docs/rounds/round-4.md`. Spec amendments
landed in lockstep (`MONETA.md` §2.1 / §2.6 / §2.10 / §2.11;
`ARCHITECTURE.md` §2 / §6 / §7.2 / §10 / §16 / §17). One code change
applied: `MonetaConfig.quota_override` bound to `1 ≤ q ≤ 1000`
(`MAX_QUOTA_OVERRIDE`).

This file is retained as the authoring record — what the brief looked
like at the moment Round 4 was opened. The rulings themselves live in
`docs/rounds/round-4.md`.

---

**Original status (pre-closure):** Draft. The Architect role drafts this
brief per `MONETA.md` §9 protocol; Joseph Ibrahim reviews before it goes
to Gemini Deep Think. No implementation proceeds on the affected
subsystems until each numbered item closes.

**Source:** `docs/review/synthesis.md` (constitution hash
`3b56e3ffae083c9b`). Of 466 open findings, eight were tagged
`requires_section9_escalation: true`. They are summarised below. The
remaining 458 are local fixes; the Critical impl bugs among them have
already been addressed on this branch.

This brief intentionally separates spec-level surprise (Trigger 2) from
items that look §9-shaped but are actually impl + doc fixes — the
adversarial reviewer caught at least one mis-routing (loop 2's
attention-log loss, correctly reclassified as a Critical impl bug, not
§9).

---

## §9 candidates by trigger

### Trigger 2 (emergency — spec-level surprise) — 6 items

#### 1. Four-op API signature drift vs `ARCHITECTURE.md` §2

`architect-L1-four-op-signatures-drift` (Critical).
`ARCHITECTURE.md` §2 specifies the four-op API as module-level
callables with self-less signatures, but `src/moneta/api.py`
implements them as bound methods on a `Moneta` class. The §16
conformance check ("`api.py` must export exactly these four callables
with exactly these signatures") cannot pass against the current code.

The v1.1.0 singleton surgery converted the module-level free functions
into handle methods — a necessary correctness fix (per-handle URI
lock, no implicit globals). The spec was not amended in lockstep. The
two are now in conflict; either:
  - **Option A**: amend `ARCHITECTURE.md` §2 (and `MONETA.md` §2.1)
    to specify the handle pattern as the canonical surface, with §16
    conformance check rewritten to match.
  - **Option B**: restore module-level callables as a thin wrapper
    around a default-singleton handle, accepting the testability
    regression that prompted the v1.1.0 surgery.

Option A is the obviously correct path; this brief exists because the
amendment is a §9 spec change, not a local fix.

#### 2. Protected-floor consolidation contradiction (`MONETA.md` §2.5 vs `ARCHITECTURE.md` §6)

`architect-L3-protected-consolidation-contradiction` (Critical) +
`consolidation-L3-protected-floor-stage-trap` (Critical).
`MONETA.md` §2.5 promises protected entities consolidate to
`cortex_protected.usda` (a routing destination). But `ARCHITECTURE.md`
§6 selection criteria require `Utility < 0.3` to stage, and the
protected-floor clamp pins utility at the floor for any entity with
`protected_floor ≥ 0.3` — mathematically guaranteeing those entities
NEVER stage. `phase3-closure.md` §4 acknowledges this as a "known
limitation" but the contradiction at the spec layer is unresolved.

The choice is whether protected memories consolidate (per §2.5) or
remain pinned (per the consequence of §6 + the floor clamp). This is
a routing-vs-pinning decision that the Round 2/3 process did not
disambiguate. Round 4 input requested.

#### 3. Vector-authoritative inversion across the hydrate path

`architect-L2-vector-authoritative-vs-hydrate-inversion` (High,
confirmed by `adversarial-L2-hydrate-inversion-spec-surprise-confirmed`).
`ARCHITECTURE.md` §7 declares the vector index "authoritative for what
exists" — this is the keystone of the no-2PC sequential-write
atomicity argument. An interrupted deposit (ECS add succeeded, vector
upsert raised) leaves a benign "doesn't exist" state because vector
wins.

The hydrate path silently inverts this: ECS snapshot becomes the
source of truth, vector is reconstructed from it. A deposit that
raised mid-construction in the prior session re-emerges in the new
session via ECS hydrate, then vector receives it via the rebuild loop.
The atomicity argument's load-bearing assumption is broken across
restart.

Round 4 question: is the across-restart authority allowed to flip to
ECS, or must hydrate respect the runtime authority and exclude
ECS-only entities? The latter requires a hydrate-time vector
companion file (which `vector_index.py`'s docstring already anticipates
as a Phase 2 LanceDB swap).

#### 4. v1.1.0 handle exclusivity model absent from `ARCHITECTURE.md`

`architect-L2-handle-exclusivity-concurrency-model-unspecified`
(High). The v1.1.0 `_ACTIVE_URIS` exclusivity is documented in README
but not in `ARCHITECTURE.md`. Concurrency model is unspecified for:
  - TOCTOU under CPython GIL
  - behavior under `fork()`
  - behavior under PEP 703 free-threading
  - cleanup ordering when `SIGTERM` arrives mid-`with`-block

Without a spec anchor, the next maintainer will eventually derive
incompatible behavior. Round 4 input requested to elevate the v1.1.0
substrate-handle brief into a numbered ARCHITECTURE.md clause.

#### 5. `quota_override` field unbounded vs §10 hard cap

`architect-L3-quota-override-bypasses-section10-cap` (High).
`ARCHITECTURE.md` §10 declares "Hard cap: 100 protected entries per
agent" as locked, but `MonetaConfig.quota_override: int = 100` is
unbounded — any caller can construct
`MonetaConfig(quota_override=10_000_000)` and the §10 cap is silently
bypassed. The v1.1.0 surgery converted the singleton-era
`PROTECTED_QUOTA = 100` constant into a per-handle override without
amending §10's "hard cap" language.

Round 4 disambiguation: is the per-handle override authorized (then
§10 needs amending to "default cap, runtime-tunable per handle") or
not (then `quota_override` should clamp to ≤100 and the
`MonetaConfig` field documentation needs to declare the bound)?

#### 6. Multi-handle protected-quota aggregation

`adversarial-L1-multi-handle-protected-quota-aggregation` (High).
One process × N handles × 100 = 100N protected entries. The §10
backstop ("hard cap of 100 protected entries per agent") is per-handle
in the implementation; "per agent" in the spec is ambiguous between
"per process" and "per substrate handle." Adversarial reviewer flags
that an agent process can construct N handles on N storage URIs and
pin 100×N protected entries.

Round 4 disambiguation: at which boundary does §10 apply? If
per-process, the cap needs a process-level enforcement layer (which
the `_ACTIVE_URIS` registry could anchor). If per-handle, the spec
language needs to be tightened.

### Trigger 3 (distant — Phase 3 USD atomicity edge case) — 0 items

No findings in this category surfaced this run. The narrow-lock ruling
(§15.6) and the partial-flush-failure handling (now landed on this
branch as `FlushPartialFailureError`) cover the cases identified.

### Mis-classified §9 candidates that the review correctly downgraded

#### 7. Attention-log drain stale-buffer race (NOT §9)

`adversarial-L2-attention-log-loss-not-section9` correctly classified
the race as a Critical implementation finding + docstring softening,
NOT a §9 trigger. `ARCHITECTURE.md` §5.1 "lock-free, eventually
consistent, simplest failure mode" explicitly permits the loss
window. The "Entries cannot be lost" wording was an implementation
docstring overpromise. Resolution landed on this branch:
  - `apply_attention` floor clamp (`src/moneta/ecs.py`)
  - module docstring softening (`src/moneta/attention_log.py`)

This item is included in the brief only to demonstrate the constitution's
§9-inflation guard worked: the adversarial reviewer caught the
mis-route before it reached the Round 4 queue.

#### 8. api.md three-finding collapse (NOT §9)

`adversarial-L5-api-md-three-findings-collapse` correctly identified
that five separate findings on `docs/api.md` (Critical/High/Medium/Low
mix) should be one rewrite pass, not five piecemeal patches. Resolution
landed on this branch as a full `docs/api.md` rewrite to the v1.1.0+
handle pattern. Not §9.

---

## What landed on this branch (non-§9 Critical impl bugs)

For traceability — these are the items the review surfaced that did
NOT need §9 escalation and were fixed in place:

| Finding id | File | Resolution |
|---|---|---|
| `substrate-L3-signal-attention-bypasses-protected-floor` | `src/moneta/ecs.py` | Floor clamp added to `apply_attention` |
| `substrate-L2-protected-quota-count-then-add-toctou` | `src/moneta/api.py` | Per-handle `_deposit_lock` around count + ecs.add |
| `persistence-L1-wal-truncation-race` | `src/moneta/durability.py` | Lock held across timestamp capture, JSON dump, WAL unlink |
| `usd-L2-flush-partial-failure-breaks-sequential-write-atomicity` | `src/moneta/usd_target.py` | New `FlushPartialFailureError` raised; per-layer Save tracking |
| `consolidation-L2-stage-partial-batch-atomicity-break` | `src/moneta/consolidation.py` | CONSOLIDATED transition hoisted INSIDE the batch loop |
| `adversarial-L2-attention-log-loss-not-section9` | `src/moneta/attention_log.py` | Module docstring softened to match §5.1 wording |
| `documentarian-L5-api-md-pre-v110-singleton-everywhere` (collapse) | `docs/api.md` | Full rewrite to v1.1.0+ handle pattern |
| `test-L1-decay-fourth-callsite-test-missing` | `tests/unit/test_decay.py` | AST scan asserting exactly three decay eval points |
| `test-L3-vector-index-no-unit-tests` | `tests/unit/test_vector_index.py` | New file — 16 tests covering §7.1 invariants |
| `test-L3-quota-count-protected-toctou-no-stress` | `tests/unit/test_api.py` | 20-thread stress test for the quota lock |
| (race regression) | `tests/integration/test_durability_roundtrip.py` | Concurrent wal_append + snapshot_ecs hammering test |
| (per-batch state regression) | `tests/integration/test_sequential_writer_ordering.py` | Mid-batch failure preserves committed-batch state |

All 94 prior tests remain green; 21 new tests pass.

---

## Process notes

The constitution's §9-inflation guard worked: of the 23 findings the
reviewers initially tagged `requires_section9_escalation: true`, 6 are
genuine Trigger 2 candidates (this brief), and the rest were
correctly reclassified to Critical impl bugs by the adversarial
reviewer or filtered at synthesis. The cross-loop closure mechanism
(via the `closes` field) was underused — reviewers used the prose
"PRIOR FINDING X IS NOT VALID" pattern instead. Tightening the
reviewer prompt to require structured `closes` would sharpen the next
run's closure ledger.

This brief is itself review-artifact: it summarises the surface of
`docs/review/synthesis.md` for the Architect, who is the role that
owns §9 brief drafting per `MONETA.md` §6 Role 1. It does not
substitute for the synthesis; it is the routing layer between
synthesis and Round 4.
