# SCOUT_MONETA_v0_3

Read-only inventory pass executed against `C:\Users\User\Moneta` on 2026-04-27. No file modifications, no git operations, no installs. Map only what exists. Substrate-over-product flagging on.

Twelve marathon markers below. Each section lists what was found, in plain prose with tables where it helps. Unknowns are first-class output and surface as questions in [12/12].

---

## [1/12] Top-Level Layout

Repository root is a single Python package (`src/moneta`) with `pyproject.toml`, blueprint/spec markdown, a benchmark script directory, and a test tree. No deployment configs, no infra files, no CI/CD descriptors.

| Entry | Type | Description |
|---|---|---|
| `MONETA.md` | doc | The blueprint — narrative, phasing, lineage, risks, role contracts, §9 escalation protocol. 27.9 KB. |
| `ARCHITECTURE.md` | doc | The locked spec. Ported from MONETA.md §1–§2 with §15 Phase 3 envelope and §15.6 narrow lock added. 21.9 KB. |
| `CLAUDE.md` | doc | Repo-level instructions for Claude Code working in this repo. Roles, hard rules, build/test commands. |
| `README.md` | doc | Public-facing project README with Mermaid diagrams (system overview, lifecycle, sleep-pass flow, dual-target, substrate family). |
| `MISSION_scout_moneta_v0_3.md` | doc | This pass's mission brief. |
| `pyproject.toml` | manifest | hatchling backend, name=moneta, version=1.0.0, Python ≥ 3.11, `dependencies = []`, dev extras = pytest/pytest-cov/ruff. ruff line-length 100, pytest pythonpath=src. |
| `.gitignore` | config | Standard Python ignores plus `*.usda`/`*.usdc`/`*.usd` and `*.lance/` for runtime artifacts. |
| `src/moneta/` | package | 13 Python files. Package layout below. |
| `tests/unit/` | tests | 5 test files. 70 collectible cases under plain Python; +1 file (test_usd_target.py) skipped without pxr. |
| `tests/integration/` | tests | 4 test files. 22 collectible cases under plain Python; +1 file (test_real_usd_end_to_end.py) skipped without pxr. |
| `tests/load/` | tests | 1 file (`synthetic_session.py`) — 30-minute synthetic session gate, virtual-clock compressed. |
| `tests/conftest.py` | tests | Two fixtures: `fresh_moneta` (init + reset), `uninitialized_moneta` (assert pre-init errors). |
| `scripts/usd_metabolism_bench_v2.py` | script | Phase 2 benchmark + Pass 5 stress harness (243-config sweep). 33 KB. |
| `scripts/moneta_video_script.md` | script | Untracked — video narration script. |
| `scripts/notebooklm_video.sh` | script | Untracked — Bash script that drives `notebooklm-py` to generate an explainer video from README/MONETA/ARCHITECTURE/phase3-closure docs. |
| `results/` | artifacts | 4 CSV outputs from Phase 2/Pass 5 runs (pass5-narrow.csv, pass5-wide.csv, pass5-threadsafety-stress.csv, usd_sizing_results.csv). |
| `dist/` | artifacts | `moneta-0.2.0` wheel + sdist (note: pyproject.toml is at v1.0.0; dist is from a prior tag). |
| `.benchmarks/` | dir | Empty pytest-benchmark cache directory. |
| `docs/` | docs | api.md, decay-tuning.md, testing.md, substrate-conventions.md, agent-commandments.md, CLAUDE-phase3.md, phase2-benchmark-results.md, phase2-closure.md, phase3-closure.md, pass5-q6-findings.md, plus `rounds/{1,2,3}.md` and `patent-evidence/{README, pass5..., pass6...}.md`. |

`src/moneta/` package contents:

```
__init__.py            api.py             attention_log.py    consolidation.py
decay.py               durability.py      ecs.py              manifest.py
mock_usd_target.py     sequential_writer.py    types.py
usd_target.py          vector_index.py
```

**Language/build/test:** Python ≥ 3.11, hatchling build backend, pytest 8+ test framework. Ruff for lint/format. Zero runtime dependencies declared in `pyproject.toml`. `pxr` (OpenUSD bindings) is required for `src/moneta/usd_target.py` but NOT pip-installable; obtained externally via a bundled OpenUSD distribution (the repo expects Houdini's `hython3.11.exe`). The dual-interpreter testing pattern is documented in CLAUDE.md.

**Substrate-leakage flags at root:**

- The dist/ wheel pinned at 0.2.0 while pyproject.toml is at 1.0.0 — these are out of sync. Not a substrate concern but a release-hygiene flag.
- Two untracked files in `scripts/` (`moneta_video_script.md`, `notebooklm_video.sh`) — present in the working tree but not committed.

---

## [2/12] USD Surface

`pxr` is imported in exactly **three** locations in the repository, and only **one** lives under `src/`. The other two are the test suite and the benchmark script. The README's claim of "Phase 3 USD integration shipped (v1.0.0)" is consistent with the file system: USD authoring is a single concrete module under `src/moneta/usd_target.py`, plus a `mock_usd_target.py` that emits the same JSONL shape without any pxr import.

| File | Imports | USD primitives used | Composition arcs |
|---|---|---|---|
| `src/moneta/usd_target.py` | `from pxr import Sdf, Tf, Usd` (Tf imported for side-effect schema registration per Pass 3 spec, marked `# noqa: F401`) | `Sdf.Path`, `Sdf.Layer.CreateAnonymous`, `Sdf.Layer.CreateNew`, `Sdf.Layer.FindOrOpen`, `Sdf.PrimSpec`, `Sdf.AttributeSpec`, `Sdf.CreatePrimInLayer`, `Sdf.SpecifierDef`, `Sdf.ValueTypeNames.{String,Float,Int,Double}`, `Sdf.ChangeBlock`, `Usd.Stage.Open` | **Sublayers only.** Sublayer paths are mutated via `self._root_layer.subLayerPaths[:]`. No References, Payloads, Inherits, Specializes, or VariantSets are authored anywhere. |
| `tests/unit/test_usd_target.py` | `from pxr import Sdf, Usd` (after `pytest.importorskip("pxr")`) | Sdf/Usd as needed for assertions on the same surface. | Same — sublayer-only. |
| `scripts/usd_metabolism_bench_v2.py` | `from pxr import Sdf, Usd, UsdGeom` (UsdGeom is load-bearing; comment notes it registers the Xform schema so `DefinePrim(path, "Xform")` resolves) | Stage, Layer, Sdf-level authoring, ChangeBlock, Save. | Sublayer-only in the benchmark write path. |

**LIVRPS arcs actually composed: only Local + Sublayer-stack ordering.** Inherits, Variants, References, Payloads, Specializes are never authored. The composition story today is "stronger sublayer position wins"; nothing else is exercised.

**`usdGenSchema` / `plugInfo.json` / schema registry hooks: none present.** A repo-wide search for `usdGenSchema`, `plugInfo`, or `Tf.Type.Define` returns zero hits in `src/`. All prim authoring is generic — `Sdf.SpecifierDef` with no `typeName`, attributes added directly via `Sdf.AttributeSpec` per call. There is no `schema.usda` file anywhere in the repo.

**One `Tf` reference in the substrate** (`from pxr import ... Tf`) — but only for an unused noqa import marked as a "Phase 3 Pass 3 spec" requirement. It does no schema registration work in code.

The codeless-migration foothold (downstream item A) does not exist yet. Every Memory_<hex> prim authored today is a typed-`Def`-with-no-typeName generic prim with six fixed attribute specs. There is no `IsA` schema, no kind, no API schema, no plugin manifest.

---

## [3/12] LIVRPS

LIVRPS is documented as **convention #2** in `docs/substrate-conventions.md`, but only one of its six letters — **L** (sub-Layer stack ordering) — is actively encoded by the implementation. Inherits, VariantSets, References, Payloads, Specializes are documented in the substrate convention but unused.

**Where priority is encoded.** `src/moneta/usd_target.py:183-193` is the entire priority-encoding logic:

```python
paths = list(self._root_layer.subLayerPaths)
if protected:
    paths.insert(0, layer.identifier)            # strongest position
else:
    insert_at = 1 if paths else 0                # right after protected
    paths.insert(insert_at, layer.identifier)
self._root_layer.subLayerPaths[:] = paths
```

`PROTECTED_SUBLAYER_NAME = "cortex_protected.usda"` is the only constant that names a position. The rolling sublayers (`cortex_YYYY_MM_DD.usda`, `cortex_YYYY_MM_DD_NNN.usda` for rotation) take position 1 — newer rolling layers stronger than older ones — purely by the order of insertion. There is no explicit "priority" integer; priority is a side effect of when a sublayer is inserted relative to siblings.

**Safety positioning.** Standard USD ordering is used (lower-index = stronger) — the protected sublayer goes to index 0. There is **no inverted-strongest pattern** (i.e. nothing positions Safety as last-but-strongest). Substrate convention #4 says protected state lives in "the strongest Root position," and the implementation matches that literally with index 0.

**Spine indexing.** There is **no monotonic step counter and no spine prim**. Each rolling daily sublayer is named purely from the UTC date of `authored_at` (`_rolling_sublayer_base()` at `usd_target.py:90`), with rotation-suffix `_001`, `_002` triggered on prim-count cap. Within a sublayer, prims are addressed only by `/Memory_<entity_id_hex>` — no parent xform, no time-index spine, no scope. The sublayer file name is the only temporal index, and it has 1-day granularity.

**How composition resolves in practice (one paragraph).** A read against the live stage walks `cortex_root.usda`, which has `cortex_protected.usda` at index 0, then most-recent rolling sublayer, then older rolling sublayers, in that order. Because every memory has its own UUID-derived prim path, there is no real opinion conflict — most prims appear in exactly one sublayer. Sublayer ordering matters only when a prim is re-authored (which the current code never does, except implicitly via rotation-after-cap creating a new sublayer for new entities) and for global metadata like layer offsets (also unused). The composition engine is being used for **partitioning** and **rotation**, not for **opinion override**. The novelty claim "Pcp-based resolution as implicit multi-fidelity fallback" (README §"Novelty claims" #3) is currently structural — the sublayer stack is in place — but **no fidelity tiers are authored** that would actually exercise it.

---

## [4/12] Discovery Surface

The consumer-visible API is the entire surface of `import moneta`. Eleven names are re-exported. There is no `api/` or `sdk/` submodule, no console scripts, no plugin entry points, no MCP server registration.

| Exported name | Layer | Surface-coupling flag |
|---|---|---|
| `deposit` | runtime / agent four-op | clean — name comes from MONETA.md §2.1, no consumer assumption in docstring. |
| `query` | runtime / agent four-op | clean. |
| `signal_attention` | runtime / agent four-op | clean. |
| `get_consolidation_manifest` | runtime / agent four-op | clean. |
| `init` | harness bootstrap | **Module-level singleton.** `_state: Optional[_ModuleState]` lives at module scope and `init()` replaces it globally. Single-process, single-instance assumption. Doc says "do not call mid-session in production" — this is a substrate-leak flag: the substrate has only one "session" per process. |
| `run_sleep_pass` | harness operator | clean for one process; the runner's `_last_activity_ms` is per-instance, but state is module-global. |
| `smoke_check` | harness self-test | clean. |
| `MonetaConfig` | dataclass (config) | All paths optional; defaults to in-memory. **Single-tenant assumption**: no `tenant_id`, `user_id`, `namespace`, `agent_id` field. The half-life is global, not per-agent. |
| `Memory` | type | clean — frozen dataclass projection of an ECS row. |
| `EntityState` | type | clean — IntEnum {VOLATILE, STAGED_FOR_SYNC, CONSOLIDATED}. |
| `MonetaNotInitializedError` | error | tells you `init()` is required — coherent with the singleton model. |
| `ProtectedQuotaExceededError` | error | clean — quota of 100 per process, not per agent/user. |

Re-exports come from `src/moneta/__init__.py`. There is no `pyproject.toml [project.scripts]` block, no `[project.entry-points]` block, no plugin discovery hook of any kind.

**Substrate-leakage flags on the discovery surface:**

1. **Module-level mutable singleton (`_state` in `api.py:124`).** Every operation calls `_require_state()` which dereferences a module global. This is the canonical single-process, single-tenant, single-agent assumption. To run two Moneta instances in the same process — for example, one per Cozy user, or one per remote-procedure session — you would have to fork the module or refactor `_state` into an injectable container.
2. **`init()` replaces state, with a docstring that says "do not call mid-session in production."** That phrase reads like a product warning, not a substrate one. A substrate would treat init as a constructor on an instance, not a global reset. (`api.py:170-171`)
3. **`PROTECTED_QUOTA: int = 100` is a process-wide constant** at `api.py:49`, applied via `state.ecs.count_protected()`. There is no per-tenant or per-agent quota; if Cozy has 50 users sharing a Moneta process, they share a single 100-slot pool.
4. **No public hook for swapping the embedder, the vector backend, or the authoring target post-init.** `MonetaConfig.use_real_usd` is a one-shot bool selecting between MockUsdTarget and UsdTarget — there's no plugin point, no Protocol-typed parameter on `init()`. The Protocol abstraction (`AuthoringTarget`, `VectorIndexTarget` in `sequential_writer.py:49,68`) exists internally but is not surfaced publicly.

The four-op API itself is clean — its docstrings describe operations in terms of memory state, not consumer surfaces. Cozy is never named in source comments. The leakage is not in *what* the four ops promise; it's in the *one-substrate-per-process* container they live in.

---

## [5/12] State, Retrieval & Provenance

**Session state storage.** State is stored in three layers, all under one module-level `_ModuleState` singleton (`api.py:109-124`):

1. **Hot tier (RAM only).** `ECS` in `src/moneta/ecs.py` is a flat struct-of-arrays of stdlib lists. Nine parallel columns: `_ids, _payloads, _embeddings, _utility, _attended, _protected_floor, _last_evaluated, _state, _usd_link`. An `_id_to_row: dict[UUID, int]` index. Single-writer; mutations are not lock-protected.
2. **Shadow vector index (RAM only in v1.0.0).** `VectorIndex` in `vector_index.py` is a `dict[UUID, tuple[list[float], EntityState]]`. Linear-scan cosine-similarity. The class docstring says LanceDB is the planned production backend (Phase 2 / v1.1) but is not wired today; passing `vector_persist_path` to the config logs a warning and is otherwise ignored (`vector_index.py:75-81`).
3. **Cold tier (disk, optional).** `UsdTarget` writes `.usda` text files (one per rolling-day sublayer + protected sublayer + root) under the directory passed to `MonetaConfig.usd_target_path`. With `usd_target_path=None`, layers are anonymous in-memory only. `MockUsdTarget` writes JSONL to `mock_target_log_path`; with `log_path=None` it buffers in memory.

**Durability.** Optional WAL-lite + periodic snapshot in `src/moneta/durability.py`. Snapshot is a JSON dump of every ECS row written via tmp-file + `os.replace`. WAL is JSONL appended on every `signal_attention`, fsync'd per call. Hydrate replays WAL entries with `timestamp > snapshot_created_at`. **Vector index does not persist independently** — it is rebuilt from the hydrated ECS at `init()` (`api.py:200-203`).

**Model fingerprints, training-data flags, license surface: none of these exist.** No code anywhere in `src/` records *which model produced the embedding*, *which model wrote the payload*, *which training-data tier the source belongs to*, or *what license the payload carries*. The `Memory` dataclass has nine fields and none of them are provenance fields. The `payload` is a `str` with no metadata wrapper.

**Capability registry: none.** A repo-wide grep for "capability", "registry", "plugin", "registrar" returns zero hits in `src/`. The Protocol classes (`AuthoringTarget`, `VectorIndexTarget`) are duck-typed and not registered anywhere; they are just type hints on `SequentialWriter.__init__` parameters.

**Retrieval surface — the embedder seam.** There is **no embedder anywhere in the codebase**. The four-op API takes `embedding: List[float]` as a parameter on `deposit` and `query`, which means the consumer is responsible for producing the embedding. Concretely:

- `deposit(payload, embedding, ...)` at `api.py:255` — embedding flows in pre-computed.
- `query(embedding, limit)` at `api.py:295` — same, no payload is encoded into a vector at query time.
- `vector_index.upsert(entity_id, vector, state)` at `vector_index.py:101` — receives a `List[float]`, stores it, never produces it.
- `MonetaConfig.embedding_dim` is an int that defaults to `None` and is inferred on first deposit. There is no model name, no provider, no max-token budget, no batch interface, no async hook.

**The seam, in concrete terms:** every place that takes `embedding: List[float]` is the seam. There are exactly two — `deposit` and `query`. To plug in EmbeddingGemma (downstream item D), the consumer wraps the four-op API in a layer that calls `embedder(payload) → list[float]` before forwarding to `deposit`. There is no in-substrate hook to register an embedder once and have it apply to both ends; the substrate genuinely does not know what an embedder is. This is **substrate-pure** in one reading (the substrate doesn't care what produced the vector) and **substrate-incomplete** in another (no registry of which model produced which vector means no honest retrieval reranking when models change). EmbeddingGemma drop-in is an afternoon if "drop-in" means "Cozy holds a Gemma-on-4090 instance and calls Moneta with its outputs"; it is a much bigger lift if "drop-in" means "Moneta hosts the embedder and tells Cozy what it produced."

**Identity model: implicitly single-user single-process.** No `tenant_id`, `user_id`, `agent_id`, `org_id`, `namespace`, or `principal` field exists anywhere in `src/moneta/`. The ECS rows have `entity_id` (per-memory UUID) and nothing else identifying *whose* memory it is. The module-level `_state` singleton means one process owns one substrate. To support two users in the same process, every user would need their own `_ModuleState`, which the API does not expose. The `cortex_protected.usda` and `cortex_YYYY_MM_DD.usda` files have no per-tenant prefix — two Cozy users would write into the same sublayer namespace, with prim paths globally collision-free only because UUIDs are 128-bit.

**Identity is the hardest cloud-substrate gap.** Adding `tenant_id` is not an API parameter change; it cascades into ECS schema (a tenant column), vector index (records keyed by `(tenant, entity_id)`), USD authoring (one sublayer stack per tenant or one sublayer per tenant), durability (one snapshot file per tenant or a tenant column in the snapshot), and the protected quota (`PROTECTED_QUOTA: int = 100` becomes per-tenant). The four-op API would need a tenant-binding mechanism (param, context manager, or per-tenant `init()` returning a handle) — and that touches the locked four-op signatures, which are MONETA.md §9-protected.

---

## [6/12] Runtime Architecture

**Existing Anthropic Claude Agent SDK / Claude Code SDK integration: none.** A grep for `anthropic`, `claude`, `claude_agent`, `claude-agent`, `agent_sdk`, `mcp_`, or `MCP` returns **zero hits** anywhere under `src/` or `tests/`. The package has no SDK consumer code, no MCP server registration, no tool definitions, no system-prompt scaffolding. `pyproject.toml` lists no SDK dependency.

**Runtime model: pure synchronous library.** No async functions, no `asyncio` import, no `await`, no coroutines. The only concurrency primitive in the substrate is `threading.Lock` and `threading.Thread` in `src/moneta/durability.py`, used solely for the optional 30-second snapshot daemon. Every agent operation is a synchronous function call that runs to completion on the calling thread.

**Where the agent loop runs today: it doesn't.** Moneta is a library that the consumer imports. The four-op API is called by the consumer's code. Nothing in Moneta drives a conversation, manages a tool call, owns a system prompt, or wraps an SDK client. The "inside-out SDK" posture asked about in the mission has no implementation surface in the repo today — the question of whether the loop should run inside the host (Cozy imports Moneta) or in Moneta (Moneta imports the SDK and embeds Cozy's logic) is not yet decided in code; the code is consistent only with the first reading.

**Mapping the four runtime models against current code:**

| Runtime model | Match against current code |
|---|---|
| Embedded host (Moneta drives the loop) | **No.** Moneta has no agent loop. |
| Sidecar (loop runs alongside) | **No.** No IPC, no socket, no shared-memory channel. |
| MCP server (Moneta is a tool source) | **No.** No `mcp` import, no tool schema, no JSON-RPC handler. |
| Library (loop is consumer's problem) | **Yes.** This is exactly what Moneta is today. |

**Inside-out SDK gap list (against the mission's stated target):**

| Capability | Current state |
|---|---|
| Handler registration (consumer registers callbacks Moneta invokes) | absent — no Protocol, no callback wiring |
| Lifecycle hooks (deposit-began, query-completed, sleep-pass-finished) | absent — only stdlib `logging.getLogger(__name__)` calls inside operations |
| Gate integration (INFORM / REVIEW / APPROVE / CRITICAL) | absent — no concept of gates anywhere in `src/` |
| Tool exposure (Moneta operations as MCP/Anthropic tools) | absent — `pyproject.toml` has no entry point, no schema, no manifest |
| Conversation context handoff (Moneta receives turn-level context) | absent — `payload: str` is the only conversation surface and it has no role/turn metadata |

**How would Cozy attach intelligence to Moneta's state today?** Cozy would (1) instantiate a process-local Moneta via `moneta.init()`, (2) own its own embedder, (3) call `moneta.deposit(payload, embedder(payload))` after each turn it wants remembered, (4) call `moneta.query(embedder(user_query))` before each turn it wants context for, and rerank results into its own prompt, (5) call `moneta.signal_attention({eid: w})` when a memory was used in producing a response, and (6) call `moneta.run_sleep_pass()` from a scheduler or end-of-session hook. None of those steps currently have substrate-side helpers. The "it remembered" demo (downstream item C) is buildable — every seam exists — but the *attachment* is fully on Cozy's side. Moneta does not surface the kinds of hooks that would make the demo a Moneta-side concern (e.g. a streaming attention API, an event bus, a turn-context handoff).

**Should the inside-out runtime live in Moneta or the consumer?** The current code answers *neither*: it's a library, the consumer drives the loop. Choosing "in Moneta" would convert Moneta from a substrate into a framework — Moneta would own the SDK client, the system prompt, the tool router. Choosing "in each consumer" preserves the substrate posture but means every consumer (Cozy, Octavius's eventual coordination agents, future ones) re-implements the loop integration from scratch. A third option — a thin SDK-layer module that ships **alongside** the substrate but isn't *the* substrate — would let Cozy import `moneta.runtime.claude` while leaving `moneta` itself surface-neutral. This is open and surfaces in [12/12].

---

## [7/12] Schema Migration

**Current mechanism: absent for USD, version-tagged-but-unused for the JSON snapshot/WAL formats.**

**Explicit migration code.** Zero. No `migrations/` directory, no `schema/` directory, no version-bump handlers. A grep for `if version <`, `migrate_v`, or `bump_version` against `src/` returns nothing.

**Versioning that does exist:**

| Surface | Constant | Where stored | What handles upgrade |
|---|---|---|---|
| ECS snapshot JSON | `SNAPSHOT_VERSION = 1` (`durability.py:57`) | Top of snapshot file as `"snapshot_version": 1` | `hydrate()` reads version, logs a warning if it isn't `1`, and "attempts best-effort load" — i.e. continues without remapping (`durability.py:193-199`). No actual migration. |
| Attention WAL JSONL | `WAL_VERSION = 1` (`durability.py:58`) | Per-line `"wal_version": 1` | Never inspected on read. `wal_read()` parses and uses the entry regardless of version (`durability.py:151-175`). |
| Mock USD authoring JSONL | `SCHEMA_VERSION = 1` (`mock_usd_target.py:70`) | Top of each batch as `"schema_version": 1` | Test asserts the value at `tests/integration/test_end_to_end_flow.py:239`. No reader code consumes it. |
| Real USD authoring (`*.usda`) | none | not stored | not handled |

**Prim-type inventory.** Moneta authors exactly **one shape** of prim: a generic `Sdf.SpecifierDef` prim with no `typeName`, named `/Memory_<entity_id_hex>`. Its fixed attribute set is six attrs:

| Attribute | USD value type | Source field |
|---|---|---|
| `payload` | `Sdf.ValueTypeNames.String` | `Memory.payload` |
| `utility` | `Sdf.ValueTypeNames.Float` | `Memory.utility` |
| `attended_count` | `Sdf.ValueTypeNames.Int` | `Memory.attended_count` |
| `protected_floor` | `Sdf.ValueTypeNames.Float` | `Memory.protected_floor` |
| `last_evaluated` | `Sdf.ValueTypeNames.Double` | `Memory.last_evaluated` |
| `prior_state` | `Sdf.ValueTypeNames.Int` (cast from `EntityState`) | `int(Memory.state)` |

Typed/generic split: **zero typed (IsA-schema) prims, all generic.** No `UsdGeomXform`, no custom typed schema, no API schema. The prims have no `kind`, no inheritance, no purpose, no payload references. The `semantic_vector` is **not** stored on the prim — the docstring at `usd_target.py:62-67` says embeddings live in the shadow vector index because storing 768+ floats per prim would bloat the stage.

**USD composition as the migration mechanism: not in use today.** The only multi-sublayer pattern in the code is the protected-vs-rolling-vs-rotation split, which is per-day partitioning, not per-version. There is no `cortex_v2` sublayer, no version variant set, no inherits walking version history. Sublayers are stacked across **time** (rolling daily files, plus rotation continuation files), not across **schema versions**.

**Schema version model on the USD side.** None. The USD root layer (`cortex_root.usda`) has no `customLayerData` of any kind; no version key, no schema URL. Reading an old `cortex_protected.usda` with a renamed attribute would silently miss it during traversal — the current readers (mostly in tests) iterate prims and read attributes by name, with no fallback.

**Load paths that lack version handling:**

- `durability.hydrate()` (`durability.py:181`) — reads the snapshot, warns if version mismatches, then proceeds to construct `Memory` objects assuming the field set is fixed. Adding a column to `Memory` (e.g. `tenant_id`) would require a migration step that does not exist.
- `vector_index.restore()` (`vector_index.py:187`) — accepts whatever `embedding_dim` is in the snapshot and rebuilds. No format version field on `VectorIndex.snapshot()`.
- `UsdTarget` itself has no read path — it is a write-only authoring target. Anything that reads back the `.usda` files (today: tests, traversal in benchmark scripts) does so by attribute name with no version awareness.

**Amenability to `usdGenSchema` codeless mode (one paragraph).** The prim type Moneta authors is a fixed, narrow, six-attribute envelope around a single concept — a memory cell. It is genuinely uniform. **That is the easy half.** The work of authoring `schema.usda` for a `MonetaMemory` typed schema and registering it via `usdGenSchema` codeless mode is afternoon-scale on the schema-authoring side: declare the API/typed schema, define six attributes with default value types, generate the codeless `plugInfo.json`, register at process startup. The hard half is **the in-flight authoring code** — `usd_target.author_stage_batch()` currently authors anonymous-typed prims with attributes added by name. To switch to typed authoring, every `Sdf.AttributeSpec(prim_spec, "payload", Sdf.ValueTypeNames.String)` becomes a `prim.GetAttribute("payload").Set(...)` after `Sdf.CreatePrimInLayer(layer, path)` with a `typeName="MonetaMemory"`. The Sdf.ChangeBlock discipline survives the change. Net assessment: **prim types are amenable**; the lift is in writer-side surgery, not in restructuring the data model. The bigger open question is whether codeless mode is the right answer at all — Moneta has only one prim type today, and the value of `usdGenSchema` typically grows with type variety.

---

## [8/12] Deployment Topology

**Where state persists** — a complete inventory of every place a path enters or exits the substrate:

| Resource | How the path is set | Default | Who provides it |
|---|---|---|---|
| ECS snapshot | `MonetaConfig.snapshot_path: Optional[Path]` | `None` (no persistence) | Caller |
| Attention WAL | `MonetaConfig.wal_path: Optional[Path]` | `None` | Caller |
| Mock USD JSONL | `MonetaConfig.mock_target_log_path: Optional[Path]` | `None` (in-memory buffer) | Caller |
| Real USD `.usda` files | `MonetaConfig.usd_target_path: Optional[Path]` | `None` (anonymous in-memory layers) | Caller |
| Vector index persistence | `MonetaConfig.vector_persist_path: Optional[Path]` | Logged-and-ignored | Caller |

**No hardcoded paths.** No `os.environ`, no `os.getenv`, no `XDG_*`, no `~/.moneta`, no `/var/...`, no `tempfile`. All persistence locations come from the config object the caller passes in. The defaults are all `None`, meaning the default Moneta is fully ephemeral.

**Process model: single-process, single-threaded except for one optional daemon.** The substrate is pure synchronous Python. The only thread Moneta itself spawns is `durability.start_background()` — a daemon snapshot thread that fires every 30 seconds (`durability.py:231-251`). It is opt-in (the caller invokes it explicitly) and is the only piece of background work in the entire codebase.

**Concurrency assumptions in code (read directly, not from docs):**

| Module | Concurrency assumption |
|---|---|
| `ecs.py` | **Single-writer.** Module docstring (`ecs.py:14-18`): "Concurrency: single-writer. Agent operations (`deposit`, `query`) and the sleep-pass reducer must not run concurrently on the same instance." The data structures are stdlib lists with no locks. |
| `attention_log.py` | **Lock-free, single-reducer**, predicated on the CPython GIL. Module docstring (`attention_log.py:8-32`): "This analysis holds for CPython 3.11 / 3.12 with the GIL enabled. It does not hold under free-threaded Python (PEP 703) or sub-interpreters with per-interpreter GILs." Multiple `signal_attention` callers can append concurrently; only one reducer may drain at a time. |
| `decay.py` | "not thread-safe for concurrent `set_half_life` calls, but reads of `.lambda_` are atomic (single attribute load under CPython GIL)" (`decay.py:80-82`). |
| `vector_index.py` | No explicit concurrency claim. The internal `_records: dict` is a stdlib dict with the same single-writer assumption inherited from ECS. |
| `usd_target.py` | **Narrow writer lock.** The `Sdf.ChangeBlock` is the writer lock; readers can `Traverse()` during `Save()`. Empirically verified at 775M assertions (Pass 5 ruling). |
| `durability.py` | Holds `threading.Lock` exclusively for the WAL file pointer (open/close/write). Snapshot read+write is implicitly single-process via `os.replace`. |

**Cross-process state sharing: none.** No file locks (`fcntl`, `msvcrt.locking`), no sockets, no shared memory. Two Python processes pointed at the same `snapshot_path` would race on snapshot rewrites with no detection.

**Network surface: zero.** No `http`, `https`, `httpx`, `requests`, `aiohttp`, `grpc`, `websocket`, `asyncio.streams`, or `socket` imports anywhere in `src/`. Moneta has no client library, no server, no port. It cannot be reached from outside the importing process by definition.

**Product-shaped assumptions, explicitly:**

1. **Single user.** No identity in the schema (see [5/12]).
2. **Single process.** Module-level `_state` singleton in `api.py:124`.
3. **Single machine.** No distribution, no replication, no quorum.
4. **Single tenant.** `PROTECTED_QUOTA = 100` is global; sublayer file names (`cortex_protected.usda`) are global.
5. **Single agent.** No agent ID on signals; `signal_attention(weights)` doesn't say *whose* attention.
6. **Single embedding model per session.** `MonetaConfig.embedding_dim` is one int, set at init or inferred on first deposit; the vector index enforces dim-homogeneity (`vector_index.py:108-113`). Mid-session model swaps are not supported.
7. **Local-disk-or-RAM persistence only.** No cloud-storage abstraction, no fsspec, no S3/GCS/blob.

---

## [9/12] Cloud Readiness

**Identity surface: absent.** No tenant, user, session, or agent identity is encoded anywhere — see [5/12] for the file references. Adding identity is a substrate-wide schema change, not a config flag.

**Auth: absent.** No token handling, no key management, no `Authorization` header construction anywhere. The substrate has no concept of "principal."

**Conflict resolution: absent.** No CRDT, no operational transform, no last-write-wins-with-timestamp, no vector clock, no Lamport. The single-writer ECS contract (`ecs.py:14-18`) means there are *no* concurrent writers to resolve between.

**Sync (pull/push, remote-vs-local, reconciliation): absent.** No `pull`, `push`, `remote`, `sync`, `reconcile`, or `replicate` symbol anywhere in `src/`. The substrate has no concept of remote.

**Async-readiness: absent.** No `async def`, no `await`, no `asyncio` import, no `anyio`. Every operation assumes sync execution on a single thread (`signal_attention` is the closest thing to async — it appends to a buffer and returns — but it is itself a synchronous call).

**Cost / quota / budget tracking: absent for cost, present for quota of one specific kind.** `PROTECTED_QUOTA: int = 100` is the only quota in the system, and it bounds *protected memory entries per process*, not requests, tokens, or dollars. There is no rate limiter, no token-budget check, no per-second cap, no LRU eviction by cost.

**Containerization signals: absent.** No `Dockerfile`, no `fly.toml`, no `Procfile`, no `railway.json`, no `modal.toml`, no `compose.yaml`, no `kubernetes/`, no `helm/`, no `.dockerignore`. Zero deployment-thinking files at the repo root or under `docs/`.

**What's in place that helps a thin-deployment cloud path:**

- The substrate is in-memory by default (no required disk path).
- Config is fully parameterized (no magic env vars, no hardcoded paths).
- Zero runtime dependencies (the wheel is small and platform-agnostic).
- Pure stdlib network surface (zero) means there's nothing to misconfigure.
- The module-level singleton means a single Python process per tenant is the natural deployment unit — that's actually a cheap-to-deploy story.

**Every assumption that has to break for thin-deployment to work, in order:**

1. **Module-level singleton `_state`** — needs to become an instance-scoped container, or the deployment needs to be "one Python process per tenant" (which makes thin-deploy expensive at any meaningful scale).
2. **Identity-free four-op API** — every `deposit`/`query`/`signal_attention`/`get_consolidation_manifest` needs a tenant binding. Either parameter, context-manager, or per-tenant init handle.
3. **`PROTECTED_QUOTA` as a process-wide constant** — must become per-tenant.
4. **Zero auth** — a hosted endpoint needs at minimum a tenant-scoped token.
5. **Single-writer ECS** — even with one tenant per process, an HTTP-fronted Moneta will naturally have concurrent inbound requests on different threads. The single-writer contract becomes a serializing queue or a per-tenant lock.
6. **Local-disk-or-RAM persistence** — cloud deployment usually means ephemeral filesystem. The snapshot path needs to point at a durable backing store (volume, blob, or service).
7. **No client library** — consumers will need a thin SDK shim if they aren't going to import Moneta directly.

**Code that would push thin-deployment toward full SaaS scope (warning list):**

- **`durability.start_background(ecs)`** — a 30-second snapshot daemon is fine for a long-lived single-tenant process. In a multi-tenant hosted setup you'd want this controlled centrally, not started by Moneta itself; otherwise every tenant's substrate spawns a thread, and the thread count grows with tenant count.
- **`PROTECTED_QUOTA` enforcement** — once it becomes per-tenant, the caller's quota becomes a billing dimension. Quota → billing is the SaaS gravity well.
- **Vector index "LanceDB Phase 2" plan** — switching to an out-of-process vector store is the moment Moneta stops being a library and starts being an infrastructure component. It's the right move for cloud, but it deserves a deliberate boundary call rather than slipping in as a backend swap.
- **Any "let Moneta host the embedder" follow-on** — the embedder seam ([5/12]) is currently consumer-side. Moving embedding into Moneta means Moneta now owns GPU scheduling, model weights, and model versioning. That is full SaaS scope.

The bottom line on cloud readiness: **the substrate is small enough and pure enough that a thin "one-process-per-user" deployment is plausible without code changes — it just won't scale and won't be hosted-product-shaped.** Anything beyond that requires breaking the singleton, adding identity, and choosing where the embedder lives — none of which the code anticipates today.

---

## [10/12] Measurement Layer

### Benchmarks

| Surface | Where | Status |
|---|---|---|
| `scripts/usd_metabolism_bench_v2.py` | 33 KB Python script | Phase 2 / Pass 5 stress harness. Sweeps 243 configs over `(batch_size, structural_ratio, sublayer_count, read_load_hz, shadow_index_commit_ms, accumulated_layer_size)`. Measures p50/p95/p99 reader stalls, write durations, Pcp rebuild cost. Outputs CSV. Requires pxr — invoked via Houdini `hython3.11.exe` per script docstring. |
| `results/usd_sizing_results.csv` | 50 KB | Phase 2 main sweep output. |
| `results/pass5-narrow.csv`, `pass5-wide.csv`, `pass5-threadsafety-stress.csv` | 6.9 / 6.8 / 62 KB | Pass 5 (Q6 narrow-vs-wide-lock comparison + 2,000-iteration concurrent-Traverse stress). |
| `.benchmarks/` | empty dir | Suggests `pytest-benchmark` was set up at some point. No `pytest-benchmark` declared in `pyproject.toml` `[project.optional-dependencies]`. No pytest fixtures using `benchmark`. |
| In-process timing in tests | Various `time.time()` usages | Used as a clock by the substrate (decay, attention, snapshot timestamps). Not used for benchmarking inside the test suite. |

There is no continuous-benchmark harness that runs in CI or on a schedule. The benchmark script is a one-shot human-driven harness; results accumulate as CSVs in `results/`, interpreted by hand in `docs/phase2-benchmark-results.md` and `docs/phase2-closure.md`.

### Eval sets

**Zero structured eval suites.** No `evals/`, no `eval/`, no fixed-input/expected-output harness, no accuracy/precision/recall pattern, no MTEB-shaped or SWE-bench-shaped suite. The closest thing to an eval is `tests/load/synthetic_session.py` (a 30-minute synthetic session compressed via virtual clock to ~0.3s) which is a **completion-gate test, not a quality eval** — it asserts that a workload runs without errors, not that retrieval returns the right memory.

The "did it remember" question that defines the Cozy demo (downstream item C) has no evaluation surface in the repo today. There is no notion of "this query should have returned this entity," no test that probes retrieval quality, no metric on staleness vs. recall.

### Token economics

**Zero token tracking.** Repo-wide grep for `token`, `tokens`, `prompt_tokens`, `completion_tokens`, `tiktoken`, `tokenize`, `tokenizer`, `usage`, `cost`, `budget` returns hits only for:
- the word "TfToken" (USD's token registry — irrelevant)
- the word "budget" inside `vector_index.py` describing GPU budget for FAISS, and inside `MONETA.md` § risk frame
- the word "cost" used in `O(n) scan cost`, `zero RAM and zero compute cost`, etc.

There is **no code that records LLM token consumption**, no per-call counter, no per-session aggregate, no per-user attribution, no SDK boundary that token counts could be captured at (the SDK isn't there). "Dollars per task" cannot be derived from anything Moneta currently records.

### Performance regression detection

**Zero.** No baseline-comparison logic, no "this run was slower than last run" surface, no `pytest-benchmark` `--compare` integration even though the empty `.benchmarks/` directory hints it was planned. Phase 2 benchmark interpretation in `docs/phase2-benchmark-results.md` is human-authored prose, not code.

### Observability

| Surface | What's emitted |
|---|---|
| `logging.getLogger(__name__)` calls | 9 of 13 substrate modules log at INFO level. Format strings include things like `"consolidation.run_pass attended=%d pruned=%d staged=%d"`, `"sequential_writer.author count=%d target=%s batch=%s"`, `"durability.snapshot path=%s n=%d"`, `"vector_index initialized (in-memory backend)"`, `"decay.config half_life=%.3fs lambda=%.6e"`. |
| Metrics emission | None. No Prometheus, no statsd, no OpenTelemetry, no metric counter anywhere. |
| Tracing | None. |

**Reading observability today: tail the consumer's stdout/stderr for `INFO`-level Python log records.** That is the entire observability surface. There is no structured-log format, no JSON output, no event bus.

### Claims the current code cannot substantiate

- **"Moneta retrieves the right memory"** — no eval set. The benchmark measures stalls under accumulated layer load, not retrieval quality.
- **"Moneta is cheap" (in dollars or tokens)** — no token tracking, no cost attribution.
- **"Decay tuning works in practice"** — `docs/decay-tuning.md` describes a closed-form curve. There is no test or eval that says "agents reinforced their memories at this rate, and these were the survival curves."
- **"It remembered"** (the Cozy demo headline) — no test, no eval, no probe.
- **"Phase 3 is GREEN-adjacent"** — substantiated by stall benchmarks but not by quality benchmarks.
- **"The four-op API is sufficient for an agent"** — substantiated by the 30-min synthetic session running clean, but the synthetic session only exercises the API surface, not the behavior of a real agent against real workloads.
- **"Moneta is a substrate"** — substantiated by interface shape (Protocol-typed authoring target, four-op API, no consumer references in source), but **not** substantiated by a second consumer ever using it. Today's only consumer is the test suite + benchmark harness.

---

## [11/12] Test Coverage

**Counts:** 94 collected and passing under plain Python (pxr-free), 2 file-level skips for pxr-required suites (`tests/unit/test_usd_target.py`, `tests/integration/test_real_usd_end_to_end.py`). Per `CLAUDE.md`, the pxr suites add 17 unit + 6 integration cases when run under hython, totaling **117 tests across the dual interpreters**. Framework: pytest 8.0+. Pass status verified by running `python -m pytest tests/unit tests/integration tests/load --tb=no -q`: `94 passed, 2 skipped, 1 warning in 0.51s`.

**Per-file breakdown (plain-Python view):**

| File | Cases | Subsystem(s) covered |
|---|---|---|
| `tests/unit/test_decay.py` | 20 | Pure decay math + DecayConfig tuning range |
| `tests/unit/test_ecs.py` | 20 | ECS lifecycle, hydrate, attention apply, retrieval |
| `tests/unit/test_api.py` | 19 | Four-op signatures (AST-level), init, deposit/query/signal contract, protected quota |
| `tests/unit/test_attention_log.py` | 11 | Lock-free append/drain + reducer + lock-free discipline assertion |
| `tests/integration/test_end_to_end_flow.py` | 12 | Deposit→query→signal→sleep-pass flow, mock USD JSONL schema |
| `tests/integration/test_durability_roundtrip.py` | 5 | Snapshot+WAL hydrate, WAL filter on snapshot timestamp |
| `tests/integration/test_sequential_writer_ordering.py` | 5 | USD-first/vector-second invariant, orphan benignness |
| `tests/load/synthetic_session.py` | 2 | 30-minute synthetic session (Phase 1 completion gate) |
| `tests/unit/test_usd_target.py` | 17 (hython) | UsdTarget Protocol conformance, prim naming, sublayer routing, rotation, ChangeBlock AST guard, disk round-trip |
| `tests/integration/test_real_usd_end_to_end.py` | 6 (hython) | Real-USD vs MockUsdTarget A/B parity, deposit→query→stage→USD-author flow |

### Subsystem × stability × surface-coupling

| Subsystem | Test count (plain) | Test count (pxr) | Stability signal | Surface-coupling flag |
|---|---|---|---|---|
| Decay math | 20 | — | **Solid.** Pure-function tests + tuning range guards. | Surface-neutral. |
| ECS hot tier | 20 | — | **Solid.** Add/remove/hydrate/iter/decay-all all covered, including swap-and-pop edge cases. | Surface-neutral. |
| Four-op API contract | 19 | — | **Solid.** AST-level signature conformance against MONETA.md §2.1. | Surface-neutral; tests only against direct calls. |
| Attention log | 11 | — | **Solid.** Includes a static guard that the module imports no `threading.Lock`. | Surface-neutral. |
| Mock USD authoring (JSONL schema) | included in end-to-end (12) | — | **Thin but covered.** Schema asserted at one location (`test_end_to_end_flow.py:205-261`). | Surface-neutral. |
| Real USD authoring (Sdf-level) | — | 17 | **Solid under hython, untested under plain Python.** | Surface-neutral. |
| Sequential writer ordering | 5 | — | **Solid.** Verifies USD-first / vector-second invariant. | Surface-neutral. |
| Durability (snapshot+WAL) | 5 | — | **Adequate.** Round-trip + WAL-filter-on-snapshot-timestamp covered. No fuzz on partial-write or crash-mid-WAL scenarios. | Surface-neutral. |
| Vector index | implicit (via end-to-end) | — | **Thin.** No dedicated `test_vector_index.py`; coverage is incidental through end-to-end and api tests. Snapshot/restore path is touched by durability test only. | Surface-neutral. |
| Consolidation runner | implicit (via end-to-end) | — | **Thin.** No dedicated `test_consolidation.py`; trigger logic and 500-prim batch cap are covered only as part of end-to-end. | Surface-neutral. |
| Manifest | implicit | — | **Thin.** Single passthrough function, covered by end-to-end manifest assertions. | Surface-neutral. |
| Synthetic 30-min session | 2 | — | **Completion-gate only.** Asserts the run completes; not a quality eval. | Surface-neutral. |
| End-to-end flow | 12 | 6 | **Solid for happy path, A/B-validated against real USD.** | Surface-neutral. |
| Free-threaded Python (PEP 703) behavior | 0 | 0 | **Untested.** Module docstrings explicitly disclaim this case. | Substrate-leak: GIL-dependent claims are untested under future Python. |

**Surface-coupling assessment:** **No test in the repository couples to a specific consumer surface.** The test fixtures use `moneta.init()` and exercise the four ops directly — there is no Cozy mock, no Octavius mock, no agent-loop simulator. This is **good** for substrate-level testing, and is consistent with the substrate-conventions discipline. The trade-off, surfaced in [10/12]: the substrate has no tests for *agent-shaped* behavior. "Did Moneta serve the right memory to the agent that asked?" is not answerable from the current suite because there is no agent in any test.

**Thin spots that the v0.3 spec should consider:**

- No dedicated `test_vector_index.py` — its surface (upsert/query/delete/update_state/snapshot/restore) is covered only incidentally.
- No dedicated `test_consolidation.py` — `should_run` (pressure + idle trigger), `classify` (prune/stage thresholds), and the 500-prim batch cap are exercised only end-to-end.
- No fuzz/property tests anywhere.
- No tests for the dim-mismatch path on the vector index, beyond the unit-level guard.
- No tests for `_reset_state` cleanup invariants beyond what fixtures rely on.

---

## [12/12] Substrate-over-product synthesis

### A. Open questions for the v0.3 spec

**Contradictions between code and docs.**

- `dist/moneta-0.2.0` wheel exists alongside `pyproject.toml` declaring `version = "1.0.0"`. Which is the shipped artifact?
- `MonetaConfig.vector_persist_path` is documented as "Retained for Phase 2+ LanceDB adoption" but `vector_index.py:75-81` explicitly logs a warning that the parameter is ignored. The README claims "VectorIndex (LanceDB v1.1)" — when does v1.1 land, and is it still LanceDB?
- README says "94 tests green" but the dual-interpreter total is closer to 117 (94 plain + 23 pxr). Does the v0.3 spec keep the dual-interpreter contract, or does it commit to a single `pxr`-included environment?
- `usd_target.py:79` imports `Tf` with `# noqa: F401 — Tf imported per Phase 3 Pass 3 spec`, but `Tf` is never referenced in the file. Is this a vestigial import, or is there a side-effect at module-load that should be made explicit?

**Half-built features / TODO density.**

- `docs/substrate-conventions.md:6` carries a `TODO` to fill in Octavius's equivalent file path "once the Octavius repo layout is known." How is this expected to be resolved before v0.3 commits?
- `MonetaConfig.vector_persist_path` is wired through `init()` but ignored — is it removed in v0.3 or activated?
- Empty `.benchmarks/` directory at the repo root suggests `pytest-benchmark` was planned but never set up. Is benchmark scaffolding (downstream item B) the right place to land it?
- `manifest.py:25` has a forward-looking comment: "Future filters (age, target sublayer, minimum batch size) land here." Are any of those filters in scope for v0.3?

**Architectural gaps a substrate consumer will hit.**

- A second consumer (anything other than the test suite) cannot bind itself to a specific tenant or session — there is no identity. The four-op API is one substrate per process by construction.
- A second consumer cannot register a callback on consolidation events, sleep-pass completion, or attention-window drain — the only observability is `logging`.
- A second consumer cannot own the embedder *and* tell the substrate which model produced which vector — there is no provenance field on `Memory` and no per-record model fingerprint.
- A second consumer has no plugin point for a non-mock, non-real-USD authoring target (e.g. an in-process Postgres writer for testing) — Protocol exists internally but `MonetaConfig.use_real_usd` is a bool, not a `factory: Callable[[], AuthoringTarget]`.

**Inside-out SDK location ambiguity.** Should the runtime layer that connects Moneta to a Claude Code SDK / Claude Agent SDK conversation loop live (a) inside `moneta` as `moneta.runtime.claude`, (b) outside `moneta` as a sibling package owned per-consumer, or (c) inside `moneta` as a thin adapter that the consumer subclasses? Today the answer is (b)-by-default because Moneta has no adapter at all. If v0.3 commits to a substrate posture, (b) preserves it best. If v0.3 commits to a "drop-in inside-out runtime" promise, (a) or (c) is required.

**Codeless schema applicability.** Are the prim types ready for `usdGenSchema`? The data model is uniform enough (one Memory prim type, six attributes), but the writer is currently typeless (`Sdf.SpecifierDef` with no `typeName`). Is the v0.3 commitment to (i) author `schema.usda` and switch to typed authoring against `MonetaMemory` IsA, (ii) add an APISchema for `MonetaMemoryAPI` over still-untyped `Def` prims, or (iii) defer until Moneta authors more than one kind of prim?

**Cloud substrate boundary.** Which primitives in `src/moneta/` are deployment-agnostic, and which assume local? The hot-tier ECS, decay math, attention log, and vector index are deployment-agnostic *if* they are wrapped behind an instance container instead of a module singleton. The durability layer is local-disk-shaped (paths, `os.replace`). The USD authoring target is local-filesystem-shaped (`.usda` files in a directory). Where does v0.3 draw the line — inside the substrate or at the edge?

**Eval and token economics ownership.** Should benchmark scaffolding + token telemetry (downstream item B) live (a) inside `moneta` so every consumer inherits a consistent measurement, (b) inside the consumer because the token economics are SDK-specific, or (c) in a sibling `moneta_eval` package that consumers opt into? The current code has no token-tracking infrastructure to "extend" — the format decision is from-scratch.

**EmbeddingGemma drop-in feasibility.** The seam exists on the consumer side (the `embedding: List[float]` parameter is the seam, period). Does v0.3 introduce a substrate-side embedder registry — and if so, who owns the GPU? The 4090 is on Joseph's workstation; cloud deployment cannot assume it. A substrate-side embedder is a substrate→product migration unless it stays optional.

**Free-threaded Python and sub-interpreters.** The lock-free attention log explicitly disclaims correctness under free-threaded Python (PEP 703) and sub-interpreters. CPython 3.13+ ships free-threading as opt-in; it becomes default at some future version. Does v0.3 commit to staying GIL-bound, or does it open a track to revisit the concurrency primitive?

**Benchmark / measurement format choice.** Does v0.3 standardize on extending `usd_metabolism_bench_v2.py`'s CSV+human-interpretation format, or does it adopt a structured eval format (MTEB-shaped, SWE-bench-shaped, custom JSON-Lines)?

### B. Product vs. Substrate Audit

| File:line | Product-shaped assumption | Substrate-shaped target |
|---|---|---|
| `src/moneta/api.py:124` | `_state: Optional[_ModuleState]` is a module-level mutable singleton. | Instance-scoped container; `Moneta()` returns a substrate handle that the consumer owns. |
| `src/moneta/api.py:170-171` | Docstring says "do not call mid-session in production" — `init()` is a global reset disguised as a constructor. | Constructors don't replace global state; they return new objects. |
| `src/moneta/api.py:49` | `PROTECTED_QUOTA: int = 100` — process-wide constant, applies to one pool of memories. | Per-tenant quota, configurable per substrate handle. |
| `src/moneta/api.py:218-224` | `MonetaConfig.use_real_usd: bool` — single boolean flag selects between two hardcoded authoring targets. | `MonetaConfig.authoring_target_factory: Callable[[], AuthoringTarget]` for arbitrary registered backends. |
| `src/moneta/types.py:64-72` | `Memory` has nine fields, none of which encode tenant, user, agent, model fingerprint, license, or training-data tier. | Provenance and identity fields on the row, or a per-row metadata bag. |
| `src/moneta/usd_target.py:86, 158-159` | `cortex_protected.usda` is a single global protected sublayer name. Two tenants in the same substrate would write into the same sublayer file. | Per-tenant sublayer namespace (tenant prefix or per-tenant directory). |
| `src/moneta/usd_target.py:90-93, 204-216` | Rolling sublayer names are pure UTC date strings — no tenant, no agent, no project key. | Sublayer names parameterized by a logical scope identifier. |
| `src/moneta/durability.py:64-77` | Snapshot and WAL paths are passed at config time and persist for the life of the substrate. There is no per-tenant or per-agent durability separation. | Per-tenant durability paths or a single backing store keyed by tenant+entity. |
| `src/moneta/durability.py:231-251` | `start_background()` spawns a daemon thread per substrate. In a multi-tenant single-process model, every tenant adds a thread. | Centralized snapshot scheduler that fans out across tenant substrates, or a wholly process-external persistence service. |
| `src/moneta/ecs.py:14-18` | Single-writer contract is enforced by docstring, not by code. Concurrent agent writers in the same process are undefined behavior. | Either a serializing queue at the substrate boundary, or a per-instance lock that makes the contract explicit. |
| `src/moneta/attention_log.py:8-32` | Lock-free correctness is predicated on the CPython GIL. Free-threaded / sub-interpreter Python breaks it. | A concurrency primitive whose correctness does not depend on a runtime that future CPython will partially deprecate. |
| `src/moneta/api.py:255-292` | `deposit(payload, embedding, ...)` has no field for "which model produced this embedding." Mid-session model swaps are silently allowed (the vector_index dim guard catches *some* of the breakage, but not all). | Per-record model fingerprint, surfaced as a field and as a re-embed boundary. |
| `src/moneta/api.py:340-355` | `signal_attention(weights)` does not record *whose* attention. There is no agent ID. | Signals carry an agent identity (or arrive on a per-agent log). |
| `src/moneta/vector_index.py:70-83` | `vector_persist_path` is a constructor parameter that is logged-and-ignored. | Either remove or implement; the third option (silently broken) is the worst. |
| `src/moneta/vector_index.py:101-114` | `embedding_dim` is set on first deposit and locked thereafter. | Mid-session model swaps are first-class with a boundary policy, not "first-deposit-wins." |
| `src/moneta/__init__.py:6-17` | The package surface includes `init`, `MonetaConfig`, `_reset_state` (via internal use)— harness verbs and types together. | Cleanly separated surfaces: `moneta` for the substrate, `moneta.harness` for init/reset, `moneta.types` for types. |
| `src/moneta/usd_target.py:62-67` | The docstring asserts "semantic_vector is NOT stored in USD ... USD stores the cognitive state metadata." This is correct for one model and one process, but loses the join key under multi-model or multi-instance composition. | Vector-index records carry tenant + model fingerprint in addition to entity_id. |
| `pyproject.toml:46-48` | `[project.urls]` points at a single GitHub repo; no MCP server URL, no OpenAPI spec, no discovery endpoint. | If thin-deployment is in scope, a discovery URL is part of the contract. |
| Repo root | No `Dockerfile`, `fly.toml`, `Procfile`, `railway.json`, `modal.toml`, `.dockerignore`, `compose.yaml`, `kubernetes/`, `helm/`. | At least one of these is required for downstream item E (thin cloud deployment). |
| Across docs | Cozy is named in `MISSION_scout_moneta_v0_3.md` but not in any source file or any committed document under `docs/`. The substrate has no code-level Cozy dependency, which is the right shape — flagged here for visibility, not as a leak. | (Already substrate-shaped on the source side. The leakage to watch is in v0.3 spec drafting, where Cozy-shaped requirements may quietly land in the substrate.) |

---

## Bottom line

Moneta today is a **small, clean, single-process Python library with one prim type, one user, one tenant, one agent, and one machine baked into its shape** — and a four-op API that is genuinely substrate-clean at the contract level. The internal abstractions (Protocol-typed authoring target, Protocol-typed vector index, dual mock/real USD wiring) are substrate-shaped; the container that holds them is product-shaped. It is **stable** (94 + 23 tests green, v1.0.0 tagged, narrow writer lock empirically hardened), **research-shaped** in measurement (one benchmark harness, zero quality evals, zero token telemetry), **local-shaped** in deployment (no network, no auth, no identity, no containerization), and **surface-neutral** in test posture (no consumer assumptions baked into the suite). The gap to the v0.3 substrate target is not in the algorithms — those are correct and locked. It is in the **container**: removing the module-level singleton, threading identity through the four ops, surfacing the embedder seam, deciding where the inside-out SDK runtime lives, choosing how (and whether) to author a `schema.usda`, and standing up the measurement layer that "Moneta works" and "Moneta is cheap" both currently lack. None of those are blocked by code already in place; all of them require a deliberate boundary call in the v0.3 spec.
