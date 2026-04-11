# Phase 2 Benchmark — USD Metabolism, Results & Interpretation

**Status:** Phase 2 benchmark complete. Verdict: **AMBIGUOUS (bulk-Yellow with Red outliers at extreme corners).** Flagged for a Joseph + Claude interpretation session per the Phase 2 authorization (*"If the result is Yellow or ambiguous, STOP and flag it for Joseph + Claude to interpret in a separate conversation. Do not force a verdict on ambiguous data."*).

**Data source:** `results/usd_sizing_results.csv` — 243 rows from `scripts/usd_metabolism_bench_v2.py` executed via Houdini 21.0.512's bundled hython (OpenUSD 0.25.5, Python 3.11.7). Full sweep runtime: 52.9 minutes. Seed-stable within the virtual-write window.

**Decision-gate framework:** MONETA.md §4.

---

## 1. Executive summary

| Tier | Criterion | Status |
|---|---|---|
| Green | p95 < 50ms across all batch sizes with (accum=100k, shadow=15) | **FAIL** — 0/27 configs pass; range 156.8–290.8ms |
| Yellow | p95 ∈ [50, 300]ms under accumulated load | **146/162** (90.1%) of accumulated-load configs |
| Red | p95 > 300ms under any realistic accumulated load | **9/162** (5.6%) triggered, max 369.5ms |
| Kill | p95 > 500ms at minimum viable batch (batch=10) | **PASS** — 0 configs; max at batch=10 is 309.7ms |

**Verdict interpretation (my read — not authorization to act):**

This is **not** a clean tier. The bulk of the distribution is Yellow, but:

- Zero configs pass the Green test point. Round 3's expectation that the writer lock hold could stay sub-50ms under 100k accumulated prims with a 15ms shadow commit is **broken by the data** — the minimum observed at that test point is 156.8ms, 3.1× over the Green threshold.
- The Yellow band holds most of the mass, including 27/27 configs at the Green test point.
- 9 configs (5.6% of accumulated-load cases) cross 300ms and formally trigger Red under the strict reading of "p95 > 300ms under any realistic accumulated load." The Red excursions are confined to `accumulated_layer_size = 100000` — 25k accumulated load never crosses 200ms in this sweep.
- Kill is comfortably untriggered.

**Why this is AMBIGUOUS and not a forced verdict:**

Reading the Red tier strictly ("any realistic accumulated load") says Red. Reading it charitably (the Red band is 5.6% of the accumulated-load universe and clusters at the extreme-batch / long-shadow-commit corner) says Yellow with caveats. The two readings imply meaningfully different Phase 3 scoping:

- **Strict Red** → Phase 3 rescopes to once-per-session archival consolidation, abandoning the runtime-partner model.
- **Dominant Yellow** → Phase 3 ships an idle-window consolidation scheduler (bounded to idle windows > 5s), possibly with sublayer rotation, and avoids writing at peak batches during accumulated-load windows.

The 3.1× Green-test-point miss argues against the idle-window Yellow reading too — it says the substrate cannot meet Round 3's scoping expectation even at the mid-case, let alone the tail. A third possibility exists: **Round 3's numeric thresholds were set too optimistically**, and the Yellow tier should be re-scoped with wider bands that acknowledge the observed cost floor (~150ms at accum=100k).

**I do not have authorization to make this call.** This document exists to give Joseph + Claude the data they need to make it in a separate pass.

---

## 2. Summary table — p95 concurrent read stall

**p95_concurrent_read_stall_ms grouped by (accumulated_layer_size × shadow_index_commit_ms), averaged over `batch_size` × `structural_ratio` × `sublayer_count` (27 samples per cell):**

| accum | shadow | n | min (ms) | p50 (ms) | mean (ms) | max (ms) |
|---|---|---|---|---|---|---|
| 0 | 5 | 27 | 5.2 | 8.2 | 25.5 | 95.6 |
| 0 | 15 | 27 | 14.8 | 20.8 | 35.6 | 95.1 |
| 0 | 50 | 27 | 51.9 | 56.4 | 69.9 | 118.5 |
| 25000 | 5 | 27 | 43.2 | 58.1 | 69.5 | 128.3 |
| 25000 | 15 | 27 | 50.6 | 77.9 | 84.4 | 168.2 |
| 25000 | 50 | 27 | 85.9 | 103.1 | 115.5 | 170.8 |
| **100000** | **5** | 27 | **151.8** | **189.7** | **210.5** | **337.9** |
| **100000** | **15** | 27 | **156.8** | **212.8** | **220.9** | **290.8** |
| **100000** | **50** | 27 | **195.3** | **250.9** | **257.8** | **369.5** |

Read the 100000 rows as the accumulated-load verdict zone. The 25000 band straddles Yellow, the 0 band mostly stays in Green/low-Yellow.

### 2.1 Writer lock hold as a shadow of p95 stall

p95_stall is close to, and slightly exceeds, the writer's median lock hold. This confirms the stall is caused by readers waiting on the writer's lock, not by post-write Pcp cost:

| accum | shadow | write_lock_median (ms) | p95_stall (ms) |
|---|---|---|---|
| 0 | 5 | 11.9 | 8.2 |
| 0 | 50 | 56.0 | 56.4 |
| 25000 | 15 | 56.0 | 77.9 |
| 100000 | 5 | 163.5 | 189.7 |
| 100000 | 15 | 179.3 | 212.8 |
| 100000 | 50 | 226.5 | 250.9 |

The lock hold is dominated by `primary_layer.Save()` serialization against the accumulated sublayer. Round 3 Q3 finding #1 (shadow_index_commit_ms contributes additively inside the writer lock) is **confirmed**: every +10ms of shadow commit adds ~+10ms to the lock hold and ~+10ms to the stall.

### 2.2 Pcp rebuild tax is not the bottleneck

| accum | shadow | pcp_rebuild_p95 (ms) |
|---|---|---|
| 0 | any | 0.1–0.9 |
| 25000 | any | 1.4–2.6 |
| 100000 | any | 0.8–1.1 |

**pcp_rebuild_p95 is essentially noise compared to write_lock_median.** This is load-bearing: Round 2's concern about Pcp rebuild cost was the wrong concern. The real cost center is `Save()`, not Pcp invalidation.

This result partially contradicts the Round 2/3 framing. Round 2 scoped the benchmark around "lock and rebuild tax" as a single compound metric; Round 3 amended it with shadow commit and accumulated load. **Neither round predicted that post-write Pcp rebuild would be effectively free.** The bottleneck is disk serialization plus the shadow-index simulated commit.

---

## 3. Red-trigger configs (p95 > 300ms)

All 9 Red-triggering configs are at `accumulated_layer_size = 100000`. Sorted by descending p95:

| batch | struct | sublayers | shadow | accum | p95_stall (ms) | write_lock_med (ms) |
|---|---|---|---|---|---|---|
| 1000 | 0.0 | 20 | 50 | 100000 | **369.5** | 297.4 |
| 1000 | 0.5 | 1 | 50 | 100000 | 354.6 | 301.5 |
| 1000 | 0.0 | 1 | 5 | 100000 | 337.9 | 244.0 |
| 1000 | 0.5 | 5 | 50 | 100000 | 321.0 | 269.7 |
| 100 | 0.0 | 5 | 50 | 100000 | 318.7 | 226.5 |
| 1000 | 0.0 | 1 | 50 | 100000 | 312.3 | 276.4 |
| 10 | 0.0 | 20 | 50 | 100000 | 309.7 | 279.0 |
| 1000 | 1.0 | 5 | 5 | 100000 | 308.2 | 218.5 |
| 1000 | 0.5 | 20 | 5 | 100000 | 305.3 | 250.6 |

**Patterns in the Red set:**
- 7/9 have `batch_size = 1000` (the heaviest).
- 6/9 have `shadow_index_commit_ms = 50ms`. All three shadow values are represented.
- Structural_ratio 0.0 is overrepresented (5/9).
- **0/9 have `shadow_index_commit_ms = 15`** — the Green test point sits in a narrow band between the 5ms and 50ms shadow-commit cases, and happens to not trigger Red in any of its 27 configs.

The last point is important: **strict-Red reading of the spec would call Red, but the Green test point specifically does not.** A Yellow verdict with specific Red-avoidance rules at the shadow-commit-50ms corner is defensible.

---

## 4. Sensitivity analysis

### 4.1 Global (all other dims averaged)

**p95_concurrent_read_stall_ms by each single dimension (243 configs, 81 per bucket):**

| dim | value | min | p50 | mean | max |
|---|---|---|---|---|---|
| **accum** | 0 | 5.2 | 47.6 | 43.7 | 118.5 |
| **accum** | 25000 | 43.2 | 87.5 | 89.8 | 170.8 |
| **accum** | 100000 | 151.8 | 221.0 | 229.7 | 369.5 |
| batch_size | 10 | 5.2 | 60.6 | 98.5 | 309.7 |
| batch_size | 100 | 5.4 | 78.1 | 107.1 | 318.7 |
| batch_size | 1000 | 35.9 | 121.5 | 157.6 | 369.5 |
| structural_ratio | 0.0 | 5.5 | 112.5 | 131.3 | 369.5 |
| structural_ratio | 0.5 | 5.2 | 95.2 | 124.9 | 354.6 |
| structural_ratio | 1.0 | 5.3 | 83.0 | 106.9 | 308.2 |
| sublayer_count | 1 | 5.2 | 93.9 | 122.2 | 354.6 |
| sublayer_count | 5 | 5.3 | 95.6 | 118.7 | 321.0 |
| sublayer_count | 20 | 5.3 | 95.1 | 122.3 | 369.5 |
| shadow_index_commit_ms | 5 | 5.2 | 73.6 | 101.8 | 337.9 |
| shadow_index_commit_ms | 15 | 14.8 | 78.8 | 113.6 | 290.8 |
| shadow_index_commit_ms | 50 | 51.9 | 112.9 | 147.8 | 369.5 |

**Dimension ranking by effect magnitude:**

1. **accumulated_layer_size** — dominant. 5.3× mean increase from 0 to 100k. This is the primary cost driver, as Round 3 Q3 finding #2 predicted.
2. **batch_size** — secondary. 1.6× mean increase from 10 to 1000. Roughly linear.
3. **shadow_index_commit_ms** — additive. +11.8ms mean from shc=5 to shc=15, +34.2ms from shc=15 to shc=50. The delta closely tracks the injected sleep duration, confirming the shadow commit is serialized inside the writer lock.
4. **structural_ratio** — inverse. Higher structural ratio → lower stall. See surprise #1 below.
5. **sublayer_count** — near-flat. See surprise #2 below.

### 4.2 At the Green test point (accum=100k, shadow=15)

Holding accum=100k and shadow=15 fixed, 27 configs remaining, varied over batch/struct/sublayers:

**batch_size effect at Green test point:**
| batch_size | n | min | p50 | max |
|---|---|---|---|---|
| 10 | 9 | 156.8 | 183.0 | 246.4 |
| 100 | 9 | 157.1 | 196.1 | 284.1 |
| 1000 | 9 | 207.5 | 256.9 | 290.8 |

**structural_ratio effect at Green test point:**
| structural_ratio | n | min | p50 | max |
|---|---|---|---|---|
| 0.0 | 9 | 156.8 | 244.7 | 286.1 |
| 0.5 | 9 | 164.2 | 240.3 | 290.8 |
| 1.0 | 9 | 157.1 | 193.3 | 248.4 |

**sublayer_count effect at Green test point:**
| sublayer_count | n | min | p50 | max |
|---|---|---|---|---|
| 1 | 9 | 181.7 | 240.3 | 279.7 |
| 5 | 9 | 156.8 | 212.8 | 286.1 |
| 20 | 9 | 164.2 | 207.5 | 290.8 |

At the Green test point specifically, the dynamic range is ~157–291ms. batch_size is the primary knob (40% span). sublayer_count is 7-12% effect, arguably noise.

---

## 5. Surprises

Five findings that Round 2/3 scoping did not anticipate or predicted differently:

### 5.1 structural_ratio is INVERSELY correlated with p95_stall

Global means: struct=0.0 → 131.3ms; struct=0.5 → 124.9ms; struct=1.0 → 106.9ms. Pure structural writes are **19% faster** than pure attribute writes.

**This contradicts the intuitive reading that structural changes trigger Pcp rebuild more aggressively.** Hypothesis: my benchmark authors attribute writes by creating a new prim AND an attribute spec on it (two Sdf operations per property write), while structural writes create only a prim spec (one operation). Under this reading, the cost is dominated by the per-spec Sdf work, not by Pcp rebuild type. This would mean the test is really measuring "spec creation count" rather than "structural vs property semantics."

**Implication for Phase 3:** this is a benchmark artifact, not a substrate property. A realistic Moneta consolidation pass would author 1:1 prim + attribute for STAGED entities (matching my "property" case), not bare prims, so the *attribute* cost number is the Phase 3-relevant one — and it's higher than the structural cost, which contradicts the scoping intuition. **Flag for the interpretation session.**

### 5.2 sublayer_count is nearly flat at depths 1/5/20

Global means: sl=1 → 122.2ms; sl=5 → 118.7ms; sl=20 → 122.3ms. No meaningful trend.

**Round 3 Yellow-tier mitigation** ("sublayer rotation policy required — cut rolling sublayer at ~50K prims to cap serialization tax") **was motivated by the assumption that sublayer count scales the lock-hold cost.** The data says otherwise. Rotation may still help by keeping individual sublayer sizes small, but the number of sublayers in the stack is not a load-bearing knob at these depths.

**Implication:** Phase 3's sublayer rotation policy should be re-motivated from "cap serialization tax" to "cap per-sublayer prim count" — the two are related but not identical. A stage with 20 empty sublayers performs the same as a stage with 1 sublayer when all 100k prims are in the primary layer. Flag for interpretation.

### 5.3 Pcp rebuild post-write is negligible

`pcp_rebuild_p95_ms` stays in the 0.1–2.6ms range across the entire sweep, regardless of accumulated_layer_size, shadow, or batch. **Round 2's original framing of "lock and rebuild tax" as a single compound metric conflated two costs that are not actually compound.** The rebuild part is free; the lock part is everything.

**Implication:** if Phase 3 can release the writer's lock before the next read hits — i.e. if the writer lock scope is reduced to only the `Sdf.ChangeBlock` portion, not the `Save()` portion — the stall collapses. But `Save()` must be in the lock per ARCHITECTURE.md §7 sequential-write protocol (USD first, then vector second). So this is a re-scoping question for the atomicity protocol, not a Phase 2 tuning knob.

### 5.4 shadow_index_commit_ms behaves as pure additive cost

The delta between shc=5, shc=15, shc=50 tracks the sleep duration almost exactly:
- shc=5 → 15: +11.8ms mean (expected +10ms, observed +11.8ms)
- shc=15 → 50: +34.2ms mean (expected +35ms, observed +34.2ms)

**This is a confirming signal, not a surprise** — but it's worth noting because it means shadow index commit cost is fully predictable from the sleep duration. No amplification, no second-order effects. Phase 3's vector-index commit budget maps 1:1 to writer lock hold.

### 5.5 achieved_reader_hz degrades smoothly to ~41Hz at worst

At accum=100k and shadow=50, achieved_reader_hz averages 41.1Hz against a requested 60Hz (68% of target). **Readers are starved but not dead.** If the agent query path can tolerate a 32% reduction in query frequency during write windows, the substrate survives accumulated-load consolidation cycles even at the worst parameter corner.

This is **better than I expected before running the benchmark.** Round 3 scoping focused on stall magnitude, not on reader throughput degradation, so there's no predicted number to compare against. Flag as a positive signal for interpretation.

---

## 6. Phase 3 recommendation space

**I am explicitly not making a Phase 3 recommendation.** Per the Phase 2 authorization, ambiguous verdicts are flagged for a separate Joseph + Claude interpretation session, and the authorization is explicit: *"Your job is to read the numbers and describe what they mean, not to decide what to build next."*

Reasonable Phase 3 paths, ordered by optimism:

### A. Dominant-Yellow, per-schedule scoping (my prior probability ~0.45)

Read the 90% Yellow mass as the dominant signal. Phase 3 implements idle-window consolidation only (`inference queue idle > 5000ms`), bounded to batches below 1000 prims, with sublayer rotation triggered by per-sublayer prim count not sublayer-stack depth. The 9 Red configs are flagged as "out-of-band operating conditions" that Phase 3 avoids rather than optimizes.

**Risk:** the 3.1× Green test point miss says the substrate cost floor at 100k accum is meaningfully higher than Round 3 scoping anticipated. A Yellow that's really 156ms+ at its best is not the Yellow Round 3 imagined.

### B. Strict-Red, session-archival scoping (my prior probability ~0.30)

Read the spec literally: 9/162 configs at p95 > 300ms under realistic accumulated load triggers Red. Phase 3 rescopes to once-per-session archival consolidation, abandoning the runtime-partner model. The runtime agent path stays entirely in the hot tier; consolidation happens at session boundaries or on idle-hour background jobs.

**Risk:** this is a large scope reduction. It may overreact to 9 outliers that are at the extreme corners and not realistic operating points.

### C. Re-scope Yellow bands per observed floor (my prior probability ~0.20)

Round 3 scoping set Yellow at 50–300ms based on an optimistic cost estimate. The data says the Yellow floor at 100k accum is ~156ms. A third interpretation is that **the thresholds were miscalibrated**, and the verdict should be evaluated against re-drawn bands. This would be a Round 4 escalation, not a Phase 3 kickoff.

**Risk:** it re-opens Round 2/3 decisions that were locked. Per §9, threshold re-calibration should only happen if the data is genuinely outside the model, not just uncomfortable.

### D. Other (my prior probability ~0.05)

Something Joseph + Claude see in the data that I'm missing.

---

## 7. Flags for the interpretation session

Items the interpretation session should explicitly address:

1. **Which reading of "Red: > 300ms under any realistic accumulated load" applies?** Strict (any single config > 300ms) or charitable (distribution median > 300ms)? The spec is ambiguous on this, and it changes the verdict.
2. **Is `accumulated_layer_size = 100000` a realistic operating point?** MONETA.md §5 risk #11 says "Accumulated sublayer serialization tax." Is 100k prims in a single sublayer the end-of-day condition the spec anticipated, or a stress-test corner?
3. **Is the 3.1× Green test point miss a show-stopper?** If Round 3 set "Green at 50ms, accum=100k, shadow=15" as a realistic target and the observed floor is 156ms, the Green tier is effectively unreachable on this hardware under this access pattern. That may or may not require re-scoping.
4. **Does Phase 3 need sublayer rotation?** My sublayer_count sensitivity says no (flat effect). Round 3's Yellow tier says yes. The two disagree.
5. **Does the structural_ratio inversion affect Phase 3's consolidation cost model?** Attribute writes are more expensive than structural ones — the opposite of the scoping assumption. A consolidation that authors prim + attribute per staged memory will pay a higher per-entity cost than a consolidation that authors bare prims with payload data in sidecar string attributes.
6. **Re-scoping the atomicity protocol.** Could the writer lock release after `Sdf.ChangeBlock` exits but before `Save()` returns? That would collapse the p95_stall to sub-50ms at all tested configs, but violates ARCHITECTURE.md §7 sequential-write ordering. Worth evaluating whether the ordering can be weakened.

---

## 8. Methodology notes (for reproducibility)

- **Platform:** Windows 11 Pro for Workstations, Threadripper PRO 7965WX, 128GB DDR5, NVMe SSD.
- **Runtime:** Houdini 21.0.512 hython, Python 3.11.7, OpenUSD 0.25.5.
- **Benchmark script:** `scripts/usd_metabolism_bench_v2.py` (see module docstring for Round 3 amendment rationale).
- **Seed stability:** the benchmark does not use randomness in its sweep execution. Reader latencies are real wall-clock measurements, so there is some natural variance between runs, but the structural results (tier boundaries, sensitivity rankings, surprise directions) are stable.
- **Authoring API:** writes use `Sdf.CreatePrimInLayer` and `Sdf.AttributeSpec` directly on the `Sdf.Layer`, inside `Sdf.ChangeBlock`. The initial attempt used `UsdStage.DefinePrim` which fails inside `ChangeBlock` when the stage has sublayers (USD 0.25.5 behavior at stage.cpp:3889) — documented in the script. The Sdf-level authoring is also more faithful to Moneta's substrate convention #5 and to Phase 3's real authoring pattern.
- **Lock discipline:** reader and writer take the same `threading.Lock`. The reader holds the lock only for the `stage.Traverse()` call (Round 2.5 fix a), not across the inter-tick sleep. The writer holds the lock for `ChangeBlock → Save → shadow_commit_sleep`.
- **Sample counts per config:** 20 writes per config × ~3 reader samples per writer window (during lock hold, 60Hz reader) = ~60 concurrent samples per config (enough for stable p95). Post-write window is 500ms → ~30 samples per config for Pcp rebuild measurement.
- **Warmup:** 0.4s before the first measured write. The first warmup config runs a minimum-load pre-pass to ensure USD caches are hot.

---

## 9. Source lineage

- **Round 2:** Gemini Deep Think architectural scoping, contained the original benchmark script. The on-disk `docs/rounds/round-2.md` is still a Pass 1 placeholder; the literal Round 2 script was never migrated into the repo. This benchmark was implemented from the Phase 2 authorization prompt's amendment spec directly. Rationale for each fix is inline in the benchmark script docstring.
- **Round 3:** the two load-bearing amendments (shadow_index_commit_ms, accumulated_layer_size) are implemented per the authorization prompt; I have not seen the Round 3 document itself (same placeholder status). Interpretation by Joseph + Claude should compare this data to the Round 3 predictions to verify the amendments had their intended effect. The confirming signal on shadow additivity and the surprise on sublayer flatness are the two places I'd want Round 3 context the most.
- **Phase 2 scope lock:** no re-opening of Round 2/3 decisions was necessary. No §9 escalations fired during benchmark execution.

---

*Benchmark executed 2026-04-11. CSV at `results/usd_sizing_results.csv`. Full sweep: 243 configs, 52.9 min. Phase 1 test suite verified green (94/94) after benchmark.*
