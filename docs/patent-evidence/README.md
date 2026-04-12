# Patent Evidence Directory

This directory contains evidentiary documentation for the four structural
novelty claims defined in MONETA.md §3, organized by Phase 3 pass. Each
entry is a dated record of what was built, which claim it substantiates,
and what prior art it distinguishes from.

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

## Evidence entries

| Pass | File | Claims evidenced | Summary |
|------|------|-----------------|---------|
| Pass 5 | `pass5-usd-threadsafety-review.md` | #4 (protected sublayer concurrency-safe) | Q6 investigation: concurrent Traverse + Save is safe. Reader path to protected sublayer is concurrency-safe. |
