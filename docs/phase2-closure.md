# Phase 2 Closure — Interpretation Session Rulings

**Status:** Phase 2 CLOSED. Verdict ruled. Phase 3 authorized on updated constraints, gated on a separate kickoff prompt.
**Date:** Phase 2 interpretation session, continuing from `docs/phase2-benchmark-results.md`.
**Participants:** Joseph Ibrahim + Claude, per the Phase 2 authorization protocol — *"If the result is Yellow or ambiguous, STOP and flag it for Joseph + Claude to interpret in a separate conversation. Do not force a verdict on ambiguous data."*
**Scope:** Rulings on the six questions flagged by the Phase 2 Results Analyst. No architectural re-opens, no §9 escalations, no Round 4 triggers.

---

## 1. Verdict

**Phase 2 verdict: YELLOW, clean in the operational envelope, with documented graceful degradation beyond it.**

This is sharper than the "bulk-Yellow with Red outliers" framing in the Results Analyst's document. The reframing distinguishes the *operational envelope* — where Phase 3 will actually run — from the *stress-test corners* where the 9 Red excursions live.

The operational envelope is `accumulated_layer_size ≤ 50000` with Round 3's sublayer rotation prescription enforced. Inside that envelope, the benchmark shows:

- **accum=25000 row (closest to operational steady state):** max p95 stall **170.8ms**, no Red excursions. Clean Yellow throughout the row.
- **accum=100000 row (stress corner, not operational):** max p95 stall 369.5ms. All 9 Red excursions live here, at parameter combinations Phase 3's operational constraints exclude by construction.

Every Red config requires at least one of: `accum=100000` (violates rotation policy), `batch_size=1000` (violates operational batch cap), or `shadow_commit=50ms` (violates LanceDB tuning budget). With the Phase 3 constraints in §3 enforced, the steady-state p95 stall is expected to sit in the **50–170ms band** — clean Yellow with meaningful headroom against the 300ms Red threshold.

The previous analyst framing was correct as a strict-reading of the spec; the rulings below sharpen the spec to operational reality. **Phase 3 ships in Yellow tier with the operational envelope defined in §3 below.** Patent claim is unaffected. No Round 4. Phase 3 is authorized to begin — gated on a separate kickoff prompt in a fresh Claude Code session.

---

## 2. Rulings on the six flagged questions

The six questions below are quoted from `docs/phase2-benchmark-results.md §7`. Each ruling is preserved verbatim from the interpretation session; no paraphrasing.

### Q1 — Strict vs charitable Red threshold reading

**RULING: Charitable reading applies.**

The 9 Red configs all sit outside Phase 3's operational envelope. All 9 require accum=100000 (violates rotation policy). 7/9 require batch_size=1000 (violates operational batch cap). 6/9 require shadow_commit=50ms (violates LanceDB tuning budget). A decision gate that triggers Red on configs Phase 3 will not produce is measuring the wrong failure mode. The charitable reading correctly reflects operational reality. Verdict tier: Yellow.

### Q2 — Is `accumulated_layer_size = 100000` realistic or stress corner?

**RULING: Stress corner, explicitly prescribed by Round 3 as a failure mode to avoid.**

Round 3's Yellow-tier specification prescribed "cut rolling sublayer at ~50K prims to cap serialization tax." The benchmark's 100k test row is exactly double that threshold — it exists to characterize what happens if Phase 3 ignores rotation, and confirms that it would indeed fail. The correct operational envelope is accumulated_layer_size ≤ 50000 with rotation enforced at that threshold. The 25k row is the realistic operating point and it is clean Yellow (max p95 stall 170.8ms, no Red excursions).

### Q3 — Is the 3.1× Green-test-point miss a Round 4 trigger?

**RULING: Phase 3 constraint, NOT a Round 4 re-scoping trigger.**

Round 3's numerical Green threshold (p95 < 50ms at accum=100k, shadow=15) was optimistic by 3.1×. The empirical floor at that test point is ~156ms. This is a real finding. It does NOT invalidate Round 3's structural claims.

Per Round 3 Q2, the four substrate novelty claims are STRUCTURAL, not TEMPORAL. Green vs Yellow vs Red is a temporal distinction about consolidation cadence. Structural claims are invariant across tiers:

1. OpenUSD composition arcs as cognitive state substrate (LIVRPS decay priority)
2. USD variant selection as fidelity LOD primitive
3. Pcp-based resolution as implicit multi-fidelity fallback
4. Protected memory as root-pinned strong-position sublayer

The patent claim is unaffected by this finding. What changes is the operational cadence: Phase 3 ships in Yellow tier, not Green tier. Document the numerical refinement in phase2-closure.md and in Phase 3's spec. Round 3's tier framework stands.

### Q4 — Does Phase 3 need sublayer rotation given sublayer_count flatness?

**RULING: Yes. Rotation required. The §5.2 framing in your results doc is slightly inverted and I want to name why.**

The benchmark tested three sublayer counts (1, 5, 20) with accumulated prims ALL IN ONE PRIMARY SUBLAYER. The flatness result says stack depth doesn't affect lock-hold cost when all content lives in one layer. That is a finding about STACK DEPTH, not about per-sublayer size capping.

Round 3's rotation prescription was never about stack depth. It was about per-sublayer size — capping how many prims end up in any single sublayer so Save() cost stays bounded. The benchmark does not measure per-sublayer size distribution because it never distributes. It cannot invalidate a prescription it did not test.

Underlying physics: Save() cost scales with per-layer byte count. Halving the per-layer prim count should roughly halve the Save cost on that layer. Phase 3 rotates at 50k prims per sublayer as Round 3 specified.

Phase 3 verification task (added to investigation tasks below): extend `usd_metabolism_bench_v2.py` with a `(primary_layer_size, secondary_layer_size)` dimension to empirically confirm the rotation hypothesis. Not blocking for Phase 3 kickoff.

### Q5 — Structural_ratio inversion and Phase 3's consolidation cost model

**RULING: Benchmark methodology artifact, acknowledged. No architectural change required.**

Your §5.1 hypothesis is correct: the "attribute write" case creates two Sdf operations (PrimSpec + AttributeSpec) while the "structural write" case creates one (PrimSpec only). The inversion measures spec-creation count, not semantic complexity. The "structural=0.0" (all-attribute) case is the one that matches Moneta's real consolidation pattern — authoring prim + payload attributes per staged entity.

Phase 3 cost model uses the attribute-case numbers, NOT the bare-prim numbers. Plan for ~131ms median p95 stall at steady state (the benchmark's attribute-case global mean), not the optimistic ~107ms bare-prim number. Slightly tightens the operational envelope, does not change the architecture.

Flagged as optional investigation task: future `usd_metabolism_bench_v3.py` (if ever written) should cleanly separate spec-count from semantic-type. Not a Phase 3 blocker.

### Q6 — Can the writer lock release before `Save()` completes?

**RULING: Deferred to Phase 3 as a narrow implementation investigation. NOT a §7 re-open.**

The proposal preserves sequential-write ordering (USD first, vector second). Section 7's correctness guarantees stay intact:

- USD authored first — preserved
- Orphans benign on crash — preserved
- Vector index authoritative — preserved
- No 2PC — preserved

What changes: during the Save() window, readers can observe in-memory prim state before it's durable on disk. If a crash happens during the window, ECS is authoritative via WAL/snapshot, vector index never committed, USD disk state is whatever Save completed before the crash. No dangling vector pointers. No §7 violation.

The open question is CORRECTNESS, not ordering: is concurrent `stage.Traverse()` + `layer.Save()` safe in OpenUSD 0.25.5? The benchmark ran reader+writer under a single shared `threading.Lock`, which is the conservative configuration. It never tested whether releasing the lock across Save() produces latent races, InvalidPrim errors, or internal Pcp cache corruption.

Phase 3 Benchmark Engineer investigation task (required before committing to lock-width choice in the real consolidation translator):

1. **USD thread-safety documentation review.** Does Pixar document concurrent Traverse + Save behavior in USD 0.25.5? If yes, act on it. If no or ambiguous, proceed to step 2.
2. **Targeted thread-safety test.** Extend `usd_metabolism_bench_v2.py` with a narrow-lock variant that releases the reader-blocking mutex during Save(). Run under race detection (ThreadSanitizer if available, or high-contention stress with stage-validity assertions). N ≥ 10000 iterations to expose low-probability races.
3. **Decision gate:**
   - If safe: reduce writer lock scope to ChangeBlock only. ~80% stall collapse per your §5.3 analysis becomes real. Phase 3 ships Green-adjacent at the Green test point.
   - If unsafe: keep full-width lock. Phase 3 ships at Yellow constraints. Acceptable either way.

This is a Phase 3 implementation detail, not a Phase 2 ambiguity. Either outcome produces a working substrate. If the investigation produces ambiguous results (USD docs silent, race detector intermittent without deterministic failures), THAT is the Round 4 trigger — convene Gemini Deep Think with a brief scoped tightly to the USD concurrency question. Not before.

---

## 3. Phase 3 operational envelope

Phase 3 ships in **Yellow tier** with the following constraints. Each is derived from the benchmark data plus the rulings in §2.

### Hard constraints (enforced at Phase 3 build time)

1. **Sublayer rotation at 50k prims per sublayer.** Round 3's prescription, reconfirmed in Q4. When `cortex_YYYY_MM_DD.usda` reaches 50k prims, cut a new sublayer and pin the old one in position. Rotation is the primary lever against accumulated serialization tax.

2. **Consolidation runs only during inference idle windows > 5 seconds.** Round 3's Yellow-tier scheduling. The opportunistic trigger already wired in `consolidation.ConsolidationRunner.should_run` (see `src/moneta/consolidation.py`) activates against real USD writes in Phase 3.

3. **Maximum batch size per consolidation pass: 500 prims.** Half the benchmark's worst-batch test, well inside the operational envelope at accum ≤ 50k. Prevents the single-pass corner case that drove 7/9 Red excursions.

4. **LanceDB shadow commit budget: ≤15ms p99.** The 50ms `shadow_commit` case is where 6/9 Red excursions live. LanceDB tuning is a Phase 3 Persistence Engineer task; if the 15ms budget cannot be met with LanceDB defaults, the Persistence Engineer surfaces it as a **§9 Trigger 2 escalation**, not a silent acceptance.

### Cost model assumptions (for capacity planning)

5. **Steady-state p95 stall: ~131ms median** (benchmark's attribute-case global mean per Q5 ruling). Plan against this number, not the optimistic ~107ms bare-prim number.

6. **Reader throughput under contention: ~41Hz achieved vs 60Hz requested** during worst-case consolidation windows. 68% of target. Readers are starved but not dead. Acceptable degradation for a substrate where query load is not latency-critical at the 25ms level.

7. **Pcp rebuild cost: effectively free** (0.1–2.6ms across the entire sweep). Phase 3 does not need to optimize for Pcp invalidation avoidance, composition graph depth, or variant complexity caps. Bottleneck is disk serialization + shadow commit; optimize those, ignore the rest.

### Investigation tasks (during Phase 3 execution)

8. **Concurrent Traverse + Save safety** (Q6). Determines whether the writer lock can shrink to `ChangeBlock`-only scope. If safe, ~80% stall collapse becomes real and Phase 3 ships Green-adjacent. If unsafe, Phase 3 ships at constraints 1–7 unchanged.

9. **Per-sublayer size distribution benchmark** (Q4 verification). Extend the benchmark harness with a `(primary_layer_size, secondary_layer_size)` dimension to empirically confirm the rotation hypothesis — specifically, that halving per-layer prim count halves Save() cost on that layer.

10. **Benchmark v3 spec-count vs semantic-type separation** (Q5 methodology fix). Optional, low priority. Only if Phase 3 benchmark work surfaces a reason to disambiguate the structural-vs-attribute cost model more cleanly.

---

## 4. What is NOT changing

Explicit non-change list to prevent drift during Phase 3 planning:

- **Four-op agent API** (`deposit`, `query`, `signal_attention`, `get_consolidation_manifest`) — byte-for-byte identical signatures per ARCHITECTURE.md §2. `tests/unit/test_api.py::TestSignatureConformance` enforces this at the AST level.
- **Lazy exponential decay math** — three evaluation points still locked per ARCHITECTURE.md §4. No fourth call site. `tests/unit/test_decay.py` verifies the closed-form curve to 1e-9 relative tolerance.
- **Append-only attention log with sleep-pass reducer** — CPython GIL lock-free discipline still locked. `tests/unit/test_attention_log.py::TestLockFreeDiscipline` structurally enforces no `threading.Lock` / `threading.RLock` imports in `attention_log.py`.
- **Sequential write atomicity discipline** (USD first, vector second) — unchanged. The Q6 lock-width question is separate from the ordering; ordering stays locked per ARCHITECTURE.md §7.
- **Four substrate novelty claims** — unchanged. Patent claim is invariant across Green/Yellow/Red tiers (Q3 ruling).
- **Phase 1 ECS hot tier implementation** — unchanged. 94 tests still green; no regressions permitted during Phase 3.
- **Mock USD target schema in `src/moneta/mock_usd_target.py`** — unchanged. The real USD writer that replaces it in Phase 3 consumes the same JSONL schema as input.
- **Protocol-based dependency inversion in `src/moneta/sequential_writer.py`** — unchanged. The real USD writer drops in via the `AuthoringTarget` Protocol at the single construction site in `api.init()`, without touching `sequential_writer.py`.

---

## 5. §9 and Round 4 status

**§9 escalations outstanding: 0.**

No §9 triggers fired during Phase 2 benchmark execution. No §9 triggers fired during interpretation. All six questions resolved via rulings in §2 without re-opening locked decisions.

**Round 4 Gemini Deep Think status: NOT CONVENED.**

Phase 2 results do not warrant Round 4. Round 3's directional predictions held:

- Accumulated sublayer serialization dominates (Round 3 Q3 #2 ✓)
- Shadow commit is additive (Round 3 Q3 #1 ✓, within 2ms)
- Sequential write ordering is correct atomicity choice (Round 3 Appendix ✓)
- Structural claims survive across integration depths (Round 3 Q2 ✓)

Corrections are numerical (3.1× Green floor miss) and architectural-simplification (Pcp rebuild is free). Empirical refinements within the existing framework, not spec-level surprises.

Round 4 provisionally reserved for one contingency: if Phase 3's Q6 concurrent `Traverse` + `Save` safety investigation produces ambiguous results, that is the Round 4 trigger. Brief scoped tightly to the USD concurrency question. Not before.

---

## 6. Next action

**Phase 2 is closed.** This document and `docs/phase2-benchmark-results.md` together form the Phase 2 record: the results doc is the analyst's data interpretation, this closure doc is the session rulings.

**Phase 3 kickoff is a separate authorization pass in a fresh Claude Code session.** Hard rules shift materially for the first time in the project:

- `pxr` imports become legal inside `src/moneta/` (previously confined to `scripts/`)
- The mock consolidation target is replaced by the real USD authoring layer — `MockUsdTarget` swaps out for a real-USD implementation at the single `AuthoringTarget` construction site in `api.init()`
- Sublayer rotation is implemented against real `cortex_YYYY_MM_DD.usda` files, enforcing the 50k-prim threshold from constraint #1
- Patent claim drafting enters scope alongside build work (Stage 3, per MONETA.md lineage)
- The Q6 thread-safety investigation becomes a Phase 3 Benchmark Engineer task with its own decision gate

**Do NOT begin Phase 3 without the explicit kickoff prompt.** The phased discipline that shipped Phase 1 (5 passes, 94 tests green, zero spec drift) and Phase 2 (1 benchmark pass + this closure, 243 configs, clean verdict) is the reason the project is at this mile with its architecture intact. "Ship over perfect" is a constitutional commitment — it does not override the stop-at-handoff discipline that keeps the substrate coherent. Do not break the discipline at the finish line.

---

## 7. Lineage

- **Round 1** (previous Claude + Joseph session): Initial scoping brief authored for Gemini Deep Think. Adversarial framing stripped; 24–48 hour shipping window specified.
- **Round 2** (Gemini Deep Think): Architectural scoping doc — four-op API, ECS/USD split, lazy decay math, consolidation translator spec, original sizing benchmark, prior art verification, three scoping-phase risks. Reference: `docs/rounds/round-2.md`.
- **Round 2.5** (Claude review): Prior art narrowing (Q1 2026 wave — MemFly, HyMem, VimRAG, CogitoRAG, From Verbatim to Gist, HippoRAG — identified as adjacent work), benchmark gap analysis, four implementation blockers added.
- **Round 3** (Gemini Deep Think): Narrowed novelty claim confirmed as structural-not-temporal. Benchmark gaps identified (shadow index commit, accumulated layer). Atomicity protocol replaced with sequential-write pattern. Reference: `docs/rounds/round-3.md`.
- **Phase 1** (Claude Code MoE team, 5 passes): ECS hot tier, four-op API, lazy decay, append-only attention log, shadow vector index, mock USD target, WAL-lite durability, Protocol-based sequential writer. 94 tests green. v0.1.0 shipped.
- **Phase 2 benchmark** (Claude Code MoE team, 1 pass): Documentarian follow-ups closed, `scripts/usd_metabolism_bench_v2.py` written and run, 243-config sweep in 52.9 minutes on Houdini hython 21.0.512 / OpenUSD 0.25.5, interpretation document authored. AMBIGUOUS verdict flagged for interpretation session. Reference: `docs/phase2-benchmark-results.md`.
- **Phase 2 closure** (this document): Interpretation session rulings, operational envelope defined, Phase 3 authorized on Yellow tier with constraints.
- **Phase 3** (pending): New Claude Code session, new hard rules, real USD integration, patent filing in parallel. Kickoff prompt to be authored separately.

**Pre-Phase-3 Documentarian task (logged, not actioned in this pass):** `docs/rounds/round-2.md` and `docs/rounds/round-3.md` still contain the Pass 1 placeholder stubs I wrote during Phase 1. The actual Gemini Deep Think Round 2 and Round 3 outputs have been placed at the repository root (as `round-2.md` and `round-3.md`) but have not yet been migrated to the `docs/rounds/` canonical paths. Migration is a pre-Phase-3 Documentarian task, not a closure task. Phase 3 kickoff should either complete the migration first, or reference the root-level files explicitly until migrated.

---

*Phase 2 closed 2026-04-11. Phase 3 authorized pending kickoff prompt. No §9 escalations outstanding. Patent claim unaffected. Moneta v0.1.0 operational envelope defined for Yellow-tier steady-state production.*
