# Decay tuning guide

This document is the operator's reference for Moneta's lazy-decay
parameter λ. It is a companion to `ARCHITECTURE.md §4` (the locked
spec) and `src/moneta/decay.py` (the implementation).

## TL;DR

- **Starting half-life:** 6 hours (MONETA.md §2.3).
- **Tuning range:** 1 minute ≤ half-life ≤ 24 hours.
- **Production default:** NOT committed until Phase 1 load testing
  produces curves. Do not bake a production default into deployment
  code until the synthetic session harness has run and Test Engineer
  has published the curves.
- **λ is instrumented:** every `DecayConfig.set_half_life` call logs at
  INFO level. Tail the log during tuning experiments.

## The math (verbatim from ARCHITECTURE.md §4)

```
U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))
```

λ is derived from the half-life by closed form:

```
λ = ln(2) / half_life_seconds
```

Half-life is the human-readable tuning unit. Never configure λ
directly — always go through `DecayConfig(half_life_seconds=...)` or
`DecayConfig.set_half_life(...)`.

## Evaluation points (exactly three)

ARCHITECTURE.md §4 locks the evaluation points. Decay runs **only** at
these three locations:

1. **Before context retrieval**, inside `query()` — `api.query` calls
   `ecs.decay_all` before searching the vector index.
2. **Immediately after the attention-write phase**, inside the reducer
   — `attention_log.reduce_attention_log` calls `ecs.decay_all` after
   applying the aggregated attention batch.
3. **During the consolidation scan**, inside the sleep pass —
   `consolidation.ConsolidationRunner.run_pass` calls `ecs.decay_all`
   explicitly between the reducer call and the selection classifier.

Point 3 is redundant with point 2 in the normal flow (both see Δt = 0
for recently-touched entities), but it is called explicitly to preserve
literal spec conformance. The spec says three points, and the
conformance checklist asserts no fourth call site.

**A fourth call site is a §9 Trigger 2 (spec-level surprise), not a
local optimization.**

## The ProtectedFloor clamp

Every decayed value is clamped from below to the per-entity
`protected_floor`:

```python
U_now = max(protected_floor, U_last * exp(-λ * Δt))
```

- `protected_floor = 0.0` (default): entities decay toward zero and are
  eventually pruned by the consolidation selector (`Utility < 0.1 AND
  AttendedCount < 3`).
- `protected_floor > 0.0`: entities decay toward the floor and never
  below. Protected-floor entities count against the 100-entry quota in
  `ARCHITECTURE.md §10`.

Setting the floor high enough to prevent consolidation staging
(`floor ≥ 0.3`) effectively pins the entity in the hot tier.

## Tuning experiments

When tuning λ, change `half_life_seconds` and observe:

- **How long it takes for a deposited memory to reach `Utility < 0.3`**
  (the stage threshold) and `Utility < 0.1` (the prune threshold), with
  no reinforcement.
- **How much attention reinforcement is needed** to keep a memory above
  the thresholds across a realistic session.
- **Behavior under the synthetic 30-minute session harness**
  (`tests/load/synthetic_session.py`) at different half-lives.

At the starting 6-hour half-life:

| Time since deposit | Utility (no reinforcement) |
|---|---|
| 0 minutes | 1.000 |
| 30 minutes | 0.944 |
| 1 hour | 0.891 |
| 3 hours | 0.707 |
| 6 hours | 0.500 (one half-life) |
| 12 hours | 0.250 |
| 24 hours | 0.063 |
| 36 hours | 0.016 |

(Rounded closed-form values; the implementation matches these to 1e-9
relative tolerance per the Test Engineer reference test in
`tests/unit/test_decay.py::TestDecayValue::test_matches_closed_form_1e9_tolerance`.)

Short half-lives (minutes) favor working-memory-like behavior — only
actively reinforced memories survive a session. Long half-lives (hours)
favor sleep-pass consolidation — memories survive idle periods and
transition to STAGED_FOR_SYNC before pruning.

## Observing λ at runtime

`decay.DecayConfig` logs at INFO level on construction and on every
`set_half_life` call:

```
INFO  moneta.decay: decay.config half_life=21600.000s lambda=3.209e-05
```

Grep for `moneta.decay` in logs to recover the effective λ history for
a process.

## MAX_ENTITIES

Related tunable: `consolidation.DEFAULT_MAX_ENTITIES` (default 10000,
ruling #5). When the live ECS volatile count reaches `MAX_ENTITIES`,
the next operation triggers a sleep pass regardless of idle time. This
is a pressure release valve, not a hard cap — deposits that land while
a sleep pass is running are still accepted. Runtime-configurable via
`MonetaConfig(max_entities=N)`.

## Related docs

- `ARCHITECTURE.md §4` — locked spec for decay semantics
- `ARCHITECTURE.md §6` — consolidation thresholds that interact with decay
- `ARCHITECTURE.md §10` — protected-memory quota
- `docs/api.md` — four-op API reference
- `src/moneta/decay.py` — implementation
- `tests/unit/test_decay.py` — reference-curve conformance tests
