# Pass 6 — Narrow Writer Lock Implementation

**Date:** 2026-04-12
**Phase:** 3, Pass 6
**Commit SHA:** (filled at commit time)
**Implementer role:** Substrate Engineer

---

## What was implemented

The writer lock in `src/moneta/usd_target.py` was shrunk from
full-width (ChangeBlock + Save + shadow-commit) to ChangeBlock-only
scope. `layer.Save()` was moved from `author_stage_batch()` to
`flush()`, which the `SequentialWriter` calls separately after
authoring returns.

### Before (Pass 3–5)

```
author_stage_batch:
  Sdf.ChangeBlock  ←— lock covers here
  layer.Save()     ←— and here
flush:
  safety Save()    (redundant re-save)
```

### After (Pass 6)

```
author_stage_batch:
  Sdf.ChangeBlock  ←— lock covers here only
flush:
  layer.Save()     ←— runs outside lock, concurrent readers safe
```

## Empirical basis

Pass 5 Q6 investigation (commit 500b1dd):
- 2,000 stress-test iterations
- 70,010,000 concurrent prim-attribute read assertions
- Zero exceptions, zero assertion failures
- Save() is `const` on `SdfLayer` — does not edit scene description
  data, does not trigger `LayersDidChange`, does not invalidate Pcp
  composition caches
- OpenUSD 0.25.5, Windows 11, Threadripper PRO 7965WX

Full evidence: `docs/patent-evidence/pass5-openusd-threadsafety-review.md`

## Sequential-write ordering preserved

ARCHITECTURE.md §7 ordering is unchanged:
1. USD authored first (ChangeBlock in `author_stage_batch`)
2. USD saved to disk (`Save()` in `flush()`)
3. Vector index committed second (after `flush()` returns)

The SequentialWriter calls these in sequence. Only the
reader-blocking scope changed — readers can now traverse the
stage during step 2 without stalling.

## Novelty claim linkage

**Primary: Claim #4 — Protected memory as root-pinned strong-position sublayer.**

The narrow lock strengthens claim #4 by demonstrating that the
reader path to `cortex_protected.usda` (pinned at the strongest
Root stack position) is concurrency-safe. An agent querying
protected memory via `stage.Traverse()` receives correct, consistent
data even while a consolidation pass serializes the stage to disk.
The protection semantics (non-decaying state at the strongest
composition position) fall out of the USD composition engine and
remain valid under concurrent access — no application-level locking
is needed on the read path.

**Secondary: Claim #3 — Pcp-based resolution as implicit multi-fidelity fallback.**

Pcp resolution (which serves the highest surviving fidelity variant
without explicit routing logic) is confirmed concurrent-safe with
`Save()`. This means a querying agent receives correct multi-fidelity
resolution results even during active consolidation writes.

## Prior art note

No known LLM memory system documents a narrow-lock writer pattern
against a hierarchical composition-engine substrate. The agent
memory systems surveyed in Round 2 (Letta/MemGPT, Zep, Mem0,
HippoRAG, CogitoRAG, HyMem, VimRAG) use standard database
transactions (Postgres, Neo4j, LanceDB) where concurrent access
safety is a database-engine guarantee, not an application
architecture decision. Moneta's narrow-lock pattern is an
application-level concurrency decision validated against OpenUSD's
undocumented but empirically confirmed const-Save behavior. This
is a novel interaction between the VFX pipeline domain (OpenUSD
threading model) and the AI agent domain (concurrent memory
access during consolidation).
