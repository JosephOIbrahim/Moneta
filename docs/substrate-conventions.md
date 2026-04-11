# Substrate conventions (shared with Octavius)

**Status:** Locked for both Moneta and Octavius. Sourced from MONETA.md §8.
**Sibling document:** This file is the Moneta mirror of Octavius's equivalent substrate-conventions document. Both must stay in sync. Cross-reference the Octavius copy when its path is available; if the two drift, that is a §9 escalation on the cross-project thesis, not a local fix.

> **Cross-link (TODO):** Octavius's equivalent file path — to be filled in once the Octavius repo layout is known. Until then, treat this document as the authoritative Moneta-side mirror.

---

## Why these conventions exist

Moneta and Octavius are siblings, not cousins. Both inherit the same parent thesis:

> OpenUSD's composition engine, designed for scene description, is a general-purpose prioritization-and-visibility substrate for agent state that is not geometry.

- **Moneta** applies the thesis to **memory state** — memory decays through sublayer stack position, consolidates through variant transitions, and resolves through Pcp fallback.
- **Octavius** applies the same thesis to **coordination state** — agents coordinate through compositional awareness on a shared stage, with LIVRPS shadowing determining visibility.

Both projects must eventually compose on a shared USD stage **without importing each other's Python modules**. For that to work, the following five conventions cannot drift between the projects. Every one of them trades runtime cleverness for composition-engine behavior that is already correct by construction.

---

## The five conventions

### 1. Prim naming is UUID-based

Never construct prim names from natural language content. Natural language belongs inside string attribute values, not in prim paths.

**Why:** `TfToken` interns every prim name for the process lifetime. Natural-language token streams blow the `TfToken` registry. This was identified as a Round 2 risk (MONETA.md §5 risk #3) and is mitigated by writer-enforced UUID-only naming.

**How to apply:** Writers generate a UUID per prim at authoring time. The concept-to-UUID mapping is maintained in string attributes on the prim (e.g. `concept_label`, `source_text`) and/or in a sidecar vector index. No code path produces an `Sdf.Path` from user-provided natural-language text.

### 2. LIVRPS is the priority primitive

LIVRPS (Local, Inherits, VariantSets, References, Payloads, Specializes) is USD's composition arc strength ordering. Stronger arcs override weaker arcs. Sublayer stack position encodes priority.

**Why:** Both Moneta and Octavius route prioritization decisions through composition, not runtime `if` checks. Moneta's decay, protected memory, and consolidation all fall out of sublayer position. Octavius's visibility shadowing works the same way. Using LIVRPS *incidentally* breaks the substrate claim — it has to be used *intentionally*.

**How to apply:** When authoring any new sublayer, decide its stack position deliberately and document why in a comment referencing this convention. Protected state goes to the strongest Root position. Decaying state goes further down the stack. Never reorder the stack to fix a bug — that is almost always a sign the schema is wrong.

### 3. The stage is the interface

Cross-project composition happens at the USD stage layer, not at the Python code layer. Moneta and Octavius must be able to compose on a shared stage without importing each other's Python modules.

**Why:** If the two projects reach into each other's internals, the stage stops being the interface and the substrate claim collapses. The whole point is that the composition engine is the coordination mechanism — not a Python API.

**How to apply:** Never `from octavius import ...` from Moneta, or `from moneta import ...` from Octavius. If a behavior needs to be shared, it is shared by authoring prims, attributes, sublayers, or variants onto the stage. The stage is the contract.

### 4. Strong-position sublayers for invariants

Non-decaying or invariant state lives in a dedicated sublayer pinned to the strongest Root stack position.

**Why:** "Protection" semantics should fall out of composition resolution, not runtime checks. A protected memory in Moneta is protected because its sublayer wins at resolution time — not because of an `if entity.protected` branch. The same logic applies to Octavius's critical coordination state. This is one of the four structural novelty claims in MONETA.md §3.

**How to apply:**

- **Moneta:** `cortex_protected.usda` pinned to the strongest Root position.
- **Octavius:** its equivalent critical-coordination sublayer at the same stack position.
- Neither project adds runtime `if` checks to enforce protection. Composition does the enforcement.

### 5. `Sdf.ChangeBlock` for batch writes — always

All batch authoring must happen inside an `Sdf.ChangeBlock`. No exceptions.

**Why:** Without a change block, every Python-side notification fires per-attribute. Fan-out cost dominates real work and will blow the lock-and-rebuild tax past the Phase 2 benchmark targets. Identified in Round 2 as a required discipline, not an optimization.

**How to apply:** Any function that authors more than one attribute in a single logical operation wraps those authorings in `with Sdf.ChangeBlock():`. Test Engineer adds a guard test that fails if any authoring path violates this.

### 6. Sublayer date routing uses UTC

Rolling daily sublayers (`cortex_YYYY_MM_DD.usda`) derive their date component from UTC, not local time.

**Why:** UTC is monotonic across time zones and does not observe daylight saving. Cross-project composition between Moneta and Octavius, or between geographically distributed authoring processes, must agree on the sublayer name for any given `authored_at` timestamp — and that agreement only holds if the rollover is independent of the authoring host's local clock. Using local time would produce split sublayers (one host writes `cortex_2026_04_11.usda`, another writes `cortex_2026_04_12.usda` for the same logical moment), breaking composition order at the sublayer stack level.

**How to apply:** Any code that computes a rolling-sublayer name from a timestamp uses `datetime.fromtimestamp(authored_at, tz=timezone.utc)`. Never construct the date from `datetime.now()` or from a naive `datetime.fromtimestamp(ts)`. Phase 1's `mock_usd_target._rolling_sublayer_name` is the reference implementation; Phase 3's real USD writer inherits the same discipline. `authored_at` itself is a wall-clock unix seconds float — the *storage* format is UTC-agnostic, only the *derived date component* uses UTC.

---

## Phase 1 applicability

Phase 1 has **zero** USD dependency. None of the above conventions are directly exercised yet. They are recorded here so that:

1. No Phase 1 design accidentally precludes them. In particular, the mock USD target's log shape must be compatible with UUID-based prim naming (convention #1) and strong-position sublayer authoring (convention #4).
2. Phase 3 implementation work has an authoritative reference instead of re-deriving the conventions from the blueprint narrative.
3. Octavius and Moneta stay coordinated without a direct communication channel.

**Phase 1 tripwire:** If Consolidation Engineer's `mock_usd_target.py` emits a log shape that would require natural-language prim paths, or a flat sublayer model without stack-position discipline, the Architect role treats that as a §9 Trigger 2 (spec-level surprise) and blocks the PR.

---

## Change protocol

These conventions are shared across two repositories. Changing any of them is a cross-project decision and fires MONETA.md §9 on Moneta's side (and the equivalent trigger on Octavius's side). **A unilateral edit in one repo is always wrong.**

The Architect role in whichever repo observed the need drafts the escalation brief; both projects review before the change lands.

---

*Sourced from MONETA.md §8. Mirror document for Octavius to be cross-linked when path is available.*
