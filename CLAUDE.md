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

**v1.0.0 shipped.** All three phases complete.

- **Phase 1** shipped as v0.1.0 (94 tests green, ECS + four-op API + mock USD target + Protocol-based sequential writer).
- **Phase 2** closed as tag `moneta-v0.2.0-phase2-closed` with verdict YELLOW — clean in the operational envelope.
- **Phase 3** shipped as v1.0.0 in Green-adjacent tier. Real USD writer with narrow writer lock (ChangeBlock-only scope per Pass 5 DETERMINISTIC SAFE ruling). Steady-state p95 reader stall projected at ~10–30ms at operational batch sizes.

Phase 3 operational envelope locked in `ARCHITECTURE.md` §15. Agent discipline governed by `docs/agent-commandments.md`. Phase 3 closure record at `docs/phase3-closure.md`.

## Locked decisions — do not re-open

The following cannot be patched without MONETA.md §9 escalation. Rounds 2 and 3 are closed:

1. **The four-operation API.** `deposit`, `query`, `signal_attention`, `get_consolidation_manifest`. No fifth op. Signatures in `ARCHITECTURE.md` §2 are verbatim from MONETA.md §2.1.
2. **Decay math.** `U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))`. Lazy, memoryless, exponential. Never on a background tick. Exactly three evaluation points.
3. **Concurrency primitive.** Append-only attention log, reduced at sleep pass. Not spinlocks. Not CAS.
4. **Atomicity.** Sequential write — USD first, vector second. Vector index is authoritative. No 2PC.
5. **Phase 3 operational envelope.** Seven hard constraints in ARCHITECTURE.md §15.2, derived from Phase 2 benchmark + closure rulings. Sublayer rotation at 50k, idle-window scheduling, 500-prim batch cap, 15ms shadow commit budget.

If implementation surfaces a reason one of these looks wrong, that is §9 Trigger 2 (spec-level surprise), not a local fix.

## Phase 1 non-goals (MONETA.md §7) — scope changes for Phase 3

The following were non-goals in Phase 1. Phase 3 lifts specific restrictions as noted:

- ~~Any `pxr`, `Usd`, `Sdf`, or `Pcp` imports~~ **Legal in `src/moneta/` starting Phase 3 Pass 3** (ARCHITECTURE.md §15.1)
- ~~Real USD authoring, variant creation, or sublayer management~~ **Phase 3 scope** (ARCHITECTURE.md §15)
- Gist generation via LLM calls
- Multi-agent shared stage coordination (Octavius territory)
- Cross-session USD hydration at cold start
- Cognitive Twin integration
- Cognitive Bridge MCP server implementation
- ~~Benchmark work (Phase 2)~~ **Phase 2 complete** — see `docs/phase2-benchmark-results.md` and `docs/phase2-closure.md`
- ~~Patent filing (Stage 3)~~ **Enters scope in Phase 3** — gated on MVP existence per Round 3 Q2
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
| USD Engineer | `usd_target.py` (Phase 3 real USD authoring target) |
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

Phase 1 and Phase 3 use Python ≥ 3.11, `pytest`, `ruff`. Phase 1 has zero runtime dependencies (stdlib-only ECS, in-memory vector index). Phase 3 adds `pxr` (OpenUSD Python bindings) and LanceDB.

**pxr requirement (Phase 3 Pass 3+):** OpenUSD's Python bindings (`pxr`) are not pip-installable as `usd-core` on all platforms. Obtain `pxr` from a bundled OpenUSD distribution (tested: OpenUSD 0.25.5, Python 3.11.7) or build from source. If using a pxr-capable interpreter other than your system Python, invoke tests as `<pxr-interpreter> -m pytest` instead of `pytest`.

Standard commands:

```bash
pip install -e .[dev]
pytest tests/unit              # unit tests (94 passing as of Phase 1 completion)
pytest tests/integration       # end-to-end flow
pytest tests/load              # 30-minute synthetic session gate
python -c "import moneta; moneta.smoke_check()"   # end-to-end smoke (requires PYTHONPATH=src if not editable-installed)
ruff check src tests
ruff format src tests
```

Tests are discoverable from the repo root via `pytest` because `pyproject.toml` sets `pythonpath = ["src"]` under `[tool.pytest.ini_options]`. For direct `python -c` runs without an editable install, prefix with `PYTHONPATH=src`.

`moneta.smoke_check()` exercises deposit → query → signal_attention → `run_sleep_pass` → manifest end-to-end and is the lowest-friction way to sanity-check after a change. It is NOT a substitute for the Test Engineer suite.

### Dual-interpreter testing (Phase 3 Pass 3+)

The test suite is dual-interpreter. Phase 1 tests (pxr-free) run under plain Python. Phase 3 USD tests require a pxr-capable interpreter (OpenUSD 0.25.5+).

```bash
# Phase 1 pxr-free suite — plain Python (70 unit + 22 integration + 2 load)
pytest tests/unit
pytest tests/integration
pytest tests/load

# Phase 3 USD target tests — pxr-capable interpreter required (local: hython)
PYTHONPATH="src" "C:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython3.11.exe" \
    -m pytest tests/unit/test_usd_target.py -v -p no:faulthandler -p no:cacheprovider
```

Both suites must be green at every pass boundary from Pass 3 onward. The `-p no:faulthandler` flag suppresses harmless `os.environ` access violation warnings from hython's patched environment. USD tests use `pytest.importorskip("pxr")` so they are skipped (not failed) under plain Python.

### Multi-agent review harness (Opus 4.7, MoE roles, 5-loop)

`scripts/review_harness.py` orchestrates a 5-iteration MoE review against `claude-opus-4-7`. The bespoke constitution at `docs/review-constitution.md` regulates every reviewer; per-loop markdown lands in `docs/review/round-*.md` (gitignored), the durable record is `docs/review/synthesis.md`. Install the optional extra and dry-run before any live call:

```bash
pip install -e .[review]
python scripts/review_harness.py --dry-run --max-loops 1
python scripts/review_harness.py --max-loops 1   # live single-loop smoke
python scripts/review_harness.py                 # full 5-loop run
```

## Repository structure

```
MONETA.md                      # blueprint (source of narrative + phasing)
ARCHITECTURE.md                # locked spec — §15 Phase 3, §15.6 narrow lock
CLAUDE.md                      # this file
pyproject.toml                 # project metadata, dev deps, tool config
README.md                      # project README with Mermaid architecture diagrams
src/moneta/                    # implementation surface (Phase 1 + Phase 3)
├── usd_target.py              # Phase 3 real USD writer (narrow lock, OpenUSD 0.25.5)
└── ...                        # Phase 1 substrate modules
tests/unit/                    # 17 unit tests (11 Phase 1 USD + 6 adversarial)
tests/integration/             # 28 tests (22 Phase 1 + 6 Phase 3 USD)
tests/load/                    # 2 tests (synthetic session gate)
scripts/
└── usd_metabolism_bench_v2.py # Phase 2 benchmark + Pass 5 stress test harness
results/                       # benchmark and stress test CSVs
docs/
├── agent-commandments.md      # eight commandments governing MoE agent discipline
├── substrate-conventions.md   # shared with Octavius
├── phase2-benchmark-results.md # Phase 2 analyst data interpretation
├── phase2-closure.md          # Phase 2 rulings + operational envelope
├── phase3-closure.md          # Phase 3 closure record
├── pass5-q6-findings.md       # Q6 thread-safety ruling
├── patent-evidence/           # dated evidence entries for counsel
│   ├── pass5-usd-threadsafety-review.md
│   └── pass6-lock-shrink-implementation.md
└── rounds/
    ├── round-1.md             # scoping brief placeholder
    ├── round-2.md             # Gemini Deep Think Round 2
    └── round-3.md             # Gemini Deep Think Round 3
```

## Hard rules for any Claude Code session working in this repo

- Do not re-open Round 2 or Round 3 decisions. Escalate per MONETA.md §9.
- Do not import `pxr`, `Usd`, `Sdf`, or `Pcp` outside `src/moneta/`, or before Phase 3 Pass 3.
- Do not add a fifth operation to the agent API.
- Do not violate the Phase 3 operational envelope (ARCHITECTURE.md §15.2).
- Do not let documentation lag implementation by more than one PR (Documentarian contract).
- Do not cross role boundaries without Architect review.
- Do not break the 94 existing Phase 1 tests. Regression is higher priority than new work.
- Follow `docs/agent-commandments.md` from Phase 3 Pass 3 onward.

Ship Moneta.
