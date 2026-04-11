# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Moneta is

A memory substrate for LLM agents. Hot/cold tiered: ECS hot tier (Phase 1), OpenUSD cold tier composed via `Pcp`/`Sdf` (Phase 3). Exposes a four-operation agent API that hides every internal mechanism.

Sibling project: **Octavius** (coordination substrate on the same OpenUSD thesis). Moneta is memory, Octavius is coordination. They share substrate conventions but not Python code. See `docs/substrate-conventions.md`.

## Source of truth

1. **`MONETA.md`** — the blueprint. Narrative, phasing, lineage, risks, role contracts, escalation protocol. Read §1, §2, §6, §7, §9 before touching code.
2. **`ARCHITECTURE.md`** — the locked spec. Ported from MONETA.md §1–§2. When implementing, cite clause numbers from ARCHITECTURE.md, not MONETA.md.
3. **`docs/substrate-conventions.md`** — the five conventions shared with Octavius (MONETA.md §8).
4. **`docs/rounds/round-{1,2,3}.md`** — Gemini Deep Think outputs from scoping. Round 4+ land here as escalations fire.

If the blueprint and the spec disagree on a clause, that is a §9 trigger, not a silent edit.

## Current phase

**Phase 1** — ECS + four-op API, zero USD dependency.

Phase 1 is gated on:

- All four ops working end-to-end
- Decay math verified against reference implementation
- Shadow index consistent under simulated load
- Mock consolidation selection stable under test load
- Full unit test suite green
- A 30-minute synthetic session runs clean

Phases 2 (USD benchmark) and 3 (USD integration at measured depth) are gated on their predecessors. See MONETA.md §4.

## Locked decisions — do not re-open

The following cannot be patched without MONETA.md §9 escalation. Rounds 2 and 3 are closed:

1. **The four-operation API.** `deposit`, `query`, `signal_attention`, `get_consolidation_manifest`. No fifth op. Signatures in `ARCHITECTURE.md` §2 are verbatim from MONETA.md §2.1.
2. **Decay math.** `U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))`. Lazy, memoryless, exponential. Never on a background tick. Exactly three evaluation points.
3. **Concurrency primitive.** Append-only attention log, reduced at sleep pass. Not spinlocks. Not CAS.
4. **Atomicity.** Sequential write — USD first, vector second. Vector index is authoritative. No 2PC.

If implementation surfaces a reason one of these looks wrong, that is §9 Trigger 2 (spec-level surprise), not a local fix.

## Phase 1 non-goals (MONETA.md §7)

Do **not** build any of these in Phase 1. They will be reverted:

- Any `pxr`, `Usd`, `Sdf`, or `Pcp` imports
- Real USD authoring, variant creation, or sublayer management
- Gist generation via LLM calls
- Multi-agent shared stage coordination (Octavius territory)
- Cross-session USD hydration at cold start
- Cognitive Twin integration
- Cognitive Bridge MCP server implementation
- Benchmark work (Phase 2)
- Patent filing (Stage 3)
- Renaming, rebranding, or re-scoping
- Framework edits to `MONETA.md` without §9 escalation
- A fifth agent API operation

The `UsdLink` field on ECS entities exists as an opaque tag in Phase 1 — the mock USD target populates it, and it carries no `pxr` type.

## Role system

Phase 1 runs in Mixture-of-Experts mode. Six roles, defined in MONETA.md §6. **One agent per role at a time.** Roles coordinate through artifacts, not through direct messaging.

| Role | Owns |
|---|---|
| Architect | `ARCHITECTURE.md`, `CLAUDE.md`, spec-conformance review, §9 escalation briefs |
| Substrate Engineer | `ecs.py`, `decay.py`, `api.py`, `types.py`, `attention_log.py` |
| Persistence Engineer | `vector_index.py`, `durability.py`, `sequential_writer.py` |
| Consolidation Engineer | `consolidation.py`, `mock_usd_target.py`, `manifest.py` |
| Test Engineer | `tests/unit/`, `tests/integration/`, `tests/load/`, `tests/conftest.py` |
| Documentarian | `README.md`, `docs/api.md`, `docs/decay-tuning.md`, inline docstrings; maintains `docs/substrate-conventions.md` after Architect seeds it |

Identify your role before writing. If a task crosses a role boundary, say so and check before proceeding.

## Shared substrate conventions (MONETA.md §8)

Both Moneta and Octavius write USD stages following the same discipline. Full text in `docs/substrate-conventions.md`. The five invariants:

1. **Prim naming is UUID-based.** Never construct prim names from natural language — `TfToken` registry OOM trap. Content lives in string attributes.
2. **LIVRPS is the priority primitive.** Stronger arcs override weaker arcs. Sublayer stack position encodes priority. Use it intentionally, not incidentally.
3. **The stage is the interface.** Cross-project composition happens at the USD stage layer, not at the Python code layer. Never `from octavius import ...` from Moneta, or vice versa.
4. **Strong-position sublayers for invariants.** Protected memory (Moneta) and critical coordination state (Octavius) live in dedicated sublayers at the strongest Root stack position.
5. **`Sdf.ChangeBlock` for batch writes.** Always. Python-side notification fan-out dominates otherwise.

These apply to Phase 3. They are recorded here so Phase 1 code does not accidentally violate them with forward-looking design decisions.

## Escalation triggers (MONETA.md §9)

1. **Primary** — Ambiguous Phase 2 benchmark numbers.
2. **Emergency** — Spec-level surprise. Debugging and implementation bugs do **not** count.
3. **Distant** — Phase 3 USD atomicity edge case.

Architect drafts the Round 4 brief. Joseph Ibrahim reviews before it goes to Gemini Deep Think. No implementation proceeds on the affected subsystem until the round closes.

## Build and test commands

Phase 1 uses Python ≥ 3.11, `pytest`, `ruff`. No runtime dependencies — Substrate Engineer elected stdlib-only list-backed SoA for the ECS; Persistence Engineer elected an in-memory shadow vector index (LanceDB deferred to Phase 2 profiling).

Standard commands:

```bash
pip install -e .[dev]
pytest tests/unit              # unit tests (70 passing as of Phase 1 Pass 3)
pytest tests/integration       # end-to-end flow — not yet landed
pytest tests/load              # 30-minute synthetic session — Phase 1 gate, not yet landed
python -c "import moneta; moneta.smoke_check()"   # end-to-end smoke (requires PYTHONPATH=src if not editable-installed)
ruff check src tests
ruff format src tests
```

Tests are discoverable from the repo root via `pytest` because `pyproject.toml` sets `pythonpath = ["src"]` under `[tool.pytest.ini_options]`. For direct `python -c` runs without an editable install, prefix with `PYTHONPATH=src`.

`moneta.smoke_check()` exercises deposit → query → signal_attention → `run_sleep_pass` → manifest end-to-end and is the lowest-friction way to sanity-check after a change. It is NOT a substitute for the Test Engineer suite.

## Repository structure

```
MONETA.md                      # blueprint (source of narrative + phasing)
ARCHITECTURE.md                # locked spec (Architect)
CLAUDE.md                      # this file
pyproject.toml                 # project metadata, dev deps, tool config
src/moneta/                    # Phase 1 implementation surface
tests/unit/                    # Test Engineer
tests/integration/
tests/load/
docs/
├── substrate-conventions.md   # shared with Octavius
└── rounds/
    ├── round-1.md             # scoping brief placeholder
    ├── round-2.md             # Gemini R2 + Claude R2.5 placeholder
    └── round-3.md             # Gemini R3 + closure placeholder
```

## Hard rules for any Claude Code session working in this repo

- Do not re-open Round 2 or Round 3 decisions. Escalate per MONETA.md §9.
- Do not import `pxr`, `Usd`, `Sdf`, or `Pcp` in Phase 1 code under any circumstances.
- Do not add a fifth operation to the agent API.
- Do not expand Phase 1 scope beyond MONETA.md §7.
- Do not let documentation lag implementation by more than one PR (Documentarian contract).
- Do not cross role boundaries without Architect review.

Ship Moneta.
