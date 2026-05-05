# Patent Evidence Directory

This directory contains evidentiary documentation for the four structural
novelty claims defined in MONETA.md §3, organized by Phase 3 pass and
post-`v1.0.0` surgery. Each entry is a dated record of what was built,
which claim it substantiates (if any), and what prior art it
distinguishes from.

Patent counsel will reference this directory during filing. Content here
is NOT a patent application draft — it is raw evidence that counsel will
translate into claims language.

## The four structural novelty claims (MONETA.md §3)

1. **OpenUSD composition arcs as cognitive state substrate** — LIVRPS
   resolution order implicitly encodes decay priority.
2. **USD variant selection as fidelity LOD primitive** — detail-to-gist
   transitions via VariantSelection.
3. **Pcp-based resolution as implicit multi-fidelity fallback** — highest
   surviving fidelity served without explicit routing logic.
4. **Protected memory as root-pinned strong-position sublayer** —
   non-decaying state falls out of composition resolution, not runtime
   checks.

## Claim-substantiating evidence

These entries map directly to one of the four novelty claims and are
counsel's primary citations.

| Pass | File | Claims evidenced | Summary |
|------|------|-----------------|---------|
| Pass 5 | `pass5-usd-threadsafety-review.md` | #4 (protected sublayer concurrency-safe) | Q6 investigation: concurrent Traverse + Save is safe. Reader path to protected sublayer is concurrency-safe. |
| Pass 6 | `pass6-lock-shrink-implementation.md` | #4 (primary), #3 (secondary) | Narrow-lock implementation confirms concurrency-safe read path in production writer. |

## Implementation maturity evidence

These entries do NOT directly substantiate one of the four novelty
claims, but document the implementation surface around the substrate at
filing time. Counsel may cite them to demonstrate that the claimed
substrate is real, in production, and battle-tested — not theoretical.

| Surgery | Tag | Source | Summary |
|---------|-----|--------|---------|
| Singleton → handle | `v1.1.0` | [`SURGERY_complete.md`](../../SURGERY_complete.md) | In-memory `_ACTIVE_URIS` exclusivity; 480-attempt TOCTOU concurrent-construction stress under CPython GIL with zero double-acquisitions. Demonstrates substrate-handle multi-instance safety. |
| Codeless schema migration | `v1.2.0-rc1` | [`SURGERY_complete_codeless_schema.md`](../../SURGERY_complete_codeless_schema.md) | Runtime-registered `MonetaMemory` typed schema via OpenUSD plugin system (no C++ build). Acceptance gate test in clean subprocess asserts `Usd.SchemaRegistry().FindConcretePrimDefinition("MonetaMemory")` is non-None and round-trips all six attributes including the token-typed `priorState`. |
| Free-threading guard | (commit `76da067`) | `src/moneta/attention_log.py:64-68` | `RuntimeError` at construction time when `sys._is_gil_enabled() is False`. Surfaces the GIL dependency of the lock-free swap-and-drain attention log; converts a silent correctness failure under PEP 703 into a loud one. |

## Claims-evidence gap analysis

Honest accounting of what claims do and don't have dated dedicated
evidence files in this directory at the current commit.

| Claim | Direct evidence in this directory | Implementation surface |
|-------|-----------------------------------|------------------------|
| #1 LIVRPS decay priority | **None — gap** | Implemented via sublayer-stack position ordering in `usd_target.py` (rolling daily sublayers + `cortex_protected.usda` at strongest Root position). |
| #2 Variant LOD for fidelity | **None — gap** | Not yet exercised at runtime. Forward work — `VariantSelection`-based detail-to-gist transitions are Phase 4+ scope per MONETA.md §7. |
| #3 Pcp resolution as fallback | Pass 6 secondary mention | Primary evidence is forward work — needs a fidelity-tier-survivability bench. |
| #4 Protected sublayer | Pass 5 + Pass 6 | `cortex_protected.usda` at strongest Root position; concurrency-safety verified by 775M concurrent-read assertions. |

**Pre-filing forward work** (in priority order): primary evidence file
for claim #3 (multi-fidelity fallback bench); first dedicated evidence
for claim #1 (LIVRPS decay priority demonstration — likely a ranked
retrieval test against varying sublayer-stack positions); claim #2
remains contingent on Phase 4+ variant-selection work landing.

## How to add a new entry

1. **Date the entry** — file name should encode the surgery / pass
   identifier (e.g. `pass7-...`, `v1.3.0-...`).
2. **Claim mapping line** at the top — name which of the four claims
   the entry substantiates, or mark as "implementation maturity" if
   none directly.
3. **Prior-art differentiation** — at least one paragraph distinguishing
   from the closest known prior approach. Counsel needs this to draft
   claim language.
4. **Reproducibility pointer** — exact test file, commit SHA, and
   environment (interpreter, OpenUSD version) that reproduces the
   evidence.
5. **Update this README's tables** — add the row under either
   "Claim-substantiating evidence" or "Implementation maturity evidence"
   as appropriate, and revisit the gap analysis table if a gap closes.
