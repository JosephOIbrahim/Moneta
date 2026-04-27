# MISSION: Scout Moneta v0.3

**Role:** `[SCAFFOLD × SCOUT]`
**Type:** Read-only inventory pass — no FORGE actions
**Repo:** `C:\Users\User\Moneta`
**Output:** `SCOUT_MONETA_v0_3.md` at the repo root

---

## Why This Exists

Moneta is the USD-native cognitive substrate. The v0.1 plan mapped what existed inside one set of assumptions: local execution, embedded SDK, in-tree state, surface-coupled tests. Five additions reshape the question:

1. **Inside-out SDK** — Claude Code SDK + Claude Agent SDK runtime, with the agent loop running *inside* the host application, not above it.
2. **Codeless schema migration** — version transitions handled by USD composition and `usdGenSchema` codeless mode, not by hand-written migrators.
3. **Cloud substrate** — net-new deployment dimension. Local-first, cloud-native, or tiered are open questions.
4. **Benchmarks, eval sets, token economics** — measurement layer. Without it, "Moneta works" is unfalsifiable and "Moneta is cheap" is unprovable.
5. **Substrate over product** — the lens. Both the local world and the cloud world need it.

This pass produces the substrate map that v0.3 spec drafting and the next four to six weeks of implementation will commit against.

The scout is organized around two first-principles questions:

- **Deployment** — where does Moneta run, where does state live, where does the agent loop execute, what assumptions are baked into "where"?
- **Discovery** — how do consumer surfaces find Moneta, how do migrations get found and applied, how does eval surface what works, how is anything in the substrate addressable from outside it?

Read source, not summaries. Map only what exists. Flag everything that quietly assumes "product" when "substrate" was the goal.

---

## Downstream Work This Scout Is Sized Against

This scout exists to make five concrete pieces of forward work executable without speculation. Each step below is sized against at least one of these. The scout itself proposes nothing — it produces the map these depend on.

| # | Forward work | Scout dependency |
|---|---|---|
| **A** | Codeless schema migration applied to Moneta's prim types via `usdGenSchema` | Step [7] |
| **B** | Benchmark scaffolding + token telemetry standardized across the substrate, instrumented on real Cozy workloads | Step [10] |
| **C** | Cozy × Moneta working demo — same query, better answer after context accumulates ("it remembered" moment) | Steps [4], [5], [6] |
| **D** | EmbeddingGemma drop-in spike — 308M-param local embedder on the 4090 to tighten the local-first retrieval story | Steps [5], [6] |
| **E** | Thin cloud deployment path — Fly.io / Modal / Railway level, "try-without-installing" link, not a hosted product | Steps [8], [9] |

**Cozy is the first reference consumer.** The scout treats Cozy-coupled assumptions as substrate leakage to flag, not as Cozy-specific work to defend. The substrate has to be addressable from a second consumer to be a substrate at all.

---

## To Start

Open Claude Code at `C:\Users\User\Moneta` and paste:

```
Execute MISSION_scout_moneta_v0_3.md. Read-only scout pass.
Output to SCOUT_MONETA_v0_3.md at the repo root.
Marathon markers every step. Stop and report on any block.
```

That's the kickoff. Full mission below.

---

## Hard Constraints

1. **Read-only.** Zero file modifications. Zero git operations. Zero installs. Zero refactors. Zero "while I'm here" cleanups.

2. **No speculative extraction.** Map only what exists. If a primitive isn't there, that's the finding — don't sketch where it would go.

3. **Read actual source.** Do not rely on README summaries alone. If a README claim conflicts with code, flag it.

4. **Note unknowns.** If anything is unclear, write the question down — do not guess. Unknowns are first-class scout output.

5. **Moneta only.** Do not touch any sibling repo. Do not touch Cozy code in this pass — Cozy appears in this scout only as the named first reference consumer, used to test whether Moneta's surface is addressable from outside. Cozy code lives in its own scout.

6. **Stop on blocks.** If anything blocks the pass (missing dependency, broken import, test infrastructure failure), STOP at that step, write what you found up to that point, note the block, do not fix.

7. **Substrate-over-product flagging.** When you find code that quietly assumes a single application, single user, single process, single filesystem, or single deployment — flag it. These are the inflection points where substrate ambitions meet product implementation. They don't need to be fixed in this pass. They need to be visible.

---

## Output Format

Write one file: `SCOUT_MONETA_v0_3.md` at the repo root.

Each section header is a marathon marker: `## [N/12] {section name}`
Plain prose + tables. No diagrams.

Progress indicator format before each section:
`[N/12] {section name}...` — one line of status.

---

## Steps

### [1/12] Top-level inventory

- List every directory and file at the repo root.
- Read `README.md`, `CHANGELOG.md`, and any `*.md` at root.
- Identify: package layout, language, build system, test framework, dependency manifest.

**Output:** `Top-Level Layout` — list with one-line description per entry.

---

### [2/12] USD substrate surface

- Find every file that imports `usd-core` or `pxr`.
- For each: filename, USD primitives used (Stage, Layer, Prim, Sdf, UsdGeom, etc.), and which composition arcs are composed (sublayer, reference, payload, variant, inherit, specialize).
- Note any use of `usdGenSchema`, schema registry hooks, or `plugInfo.json` — these are the codeless-migration footholds.

**Output:** `USD Surface` — table of file × primitives × arcs, plus a short note on whether `usdGenSchema` is wired up anywhere today.

---

### [3/12] LIVRPS implementation

- Find code that implements LIVRPS ordering or opinion resolution.
- Identify: how priority is encoded, how Safety is positioned (standard USD ordering vs. inverted-strongest), how the spine is indexed (monotonic step counter? other?).

**Output:** `LIVRPS` — file references, priority constants, and one paragraph on how composition resolves in practice.

---

### [4/12] Discovery surface — public API

The discovery question: what does a consumer import to use Moneta, and what makes that surface addressable?

- Map: `__init__.py` exports, any explicit `api/` or `sdk/` modules, named entry points in `pyproject.toml` or `setup.py`, console scripts, plugin registrations.
- For each exported name: one-line description and the layer it lives at (USD primitive, runtime, state, agent, utility).
- Flag any public symbol whose docstring assumes a specific consumer surface — that's substrate leakage into product territory. Cozy-shaped assumptions count as leakage even though Cozy is the first reference consumer.

**Output:** `Discovery Surface` — table of exported names × layer × surface-coupling flag.

---

### [5/12] State, memory, retrieval, and provenance

- How is session state stored? USD prims, JSONL, both, neither?
- How are model fingerprints, training-data flags, and license surfaces represented?
- Where is the capability registry, if one exists?
- **Retrieval surface:** is there an embedding-backed retrieval path today? If yes, where does the embedder plug in (config, dependency-injection, hardcoded)? If no, where would it plug in — what's the seam? This sizes the EmbeddingGemma drop-in spike (downstream item D).
- **Identity model:** is there any concept of *who* the state belongs to (user, session, tenant), or is it implicitly single-user single-process? Identity ambiguity here is what the cloud substrate path (downstream item E) will hit first.

**Output:** `State, Retrieval & Provenance` — concrete file/prim references, one paragraph on identity assumptions, and a specific note on the embedder seam (or its absence).

---

### [6/12] Runtime model — inside-out SDK posture

The deployment question: where does the agent loop run, and who owns it?

- Is there existing Anthropic Claude Agent SDK or Claude Code SDK integration? If yes, where, and what does it import?
- Is the runtime model: embedded host (Moneta drives the loop), sidecar (loop runs alongside), MCP server (loop runs in the host, Moneta is a tool source), or library (loop is the consumer's problem)?
- For an inside-out architecture — agent runs *inside* the host application, host imports Moneta — what's already in place vs. what's missing? Specifically: handler registration, lifecycle hooks, gate integration (INFORM/REVIEW/APPROVE/CRITICAL), tool exposure, conversation context handoff.
- How would Cozy attach intelligence to Moneta's state today, with what's actually in the repo? This sizes the Cozy × Moneta demo (downstream item C).

**Output:** `Runtime Architecture` — concrete description of current runtime model, gap list against inside-out SDK target, and an explicit note on whether the inside-out runtime should live in Moneta or in each consumer.

---

### [7/12] Schema migration surface — codeless applicability

The discovery question for state: when the schema changes, how does old state become new state?

The downstream target (item A) is **codeless schema migration via `usdGenSchema`** — Pydantic becomes wrapper, USD becomes truth. The scout's job is to determine whether Moneta's prim types are amenable to that pattern, not to invent it.

- Search for explicit migration code: any `migrations/`, `schema/`, version-bump handlers, `if version <` branches in load paths.
- Inventory the prim types Moneta currently composes — count them, list them, note which ones are typed (formal USD types) vs. generic (untyped prims with custom attributes).
- Check whether USD composition is being used as the migration mechanism — sublayers stacked across versions, variants per schema, inherits walking version history. If so, document the pattern.
- Identify the current schema versioning model: is there one? Where is the version stored (USD metadata, JSON header, file naming)?
- Flag any state-loading code that silently assumes the schema it was written against is the schema on disk — that's a migration bug waiting to fire.

**Output:** `Schema Migration` — current mechanism (coded, codeless via composition, or absent), prim-type inventory with typed/generic split, version-tracking location, every load path that lacks version handling, and a one-paragraph assessment of how amenable the prim types are to a `schema.usda` + `usdGenSchema` codeless approach.

---

### [8/12] Deployment topology — what does "where Moneta runs" mean today?

The deployment question, asked of the existing code rather than future plans.

- Where does state persist? Local filesystem paths, environment variables, config files — list every place a path is hardcoded or constructed.
- Process model: single-process, multi-process, async, threaded, none-of-the-above-it's-just-functions?
- Concurrency assumptions: does any code assume single-writer, single-reader, single-tenant?
- Cross-process state sharing: file locks, sockets, shared memory, none?
- Network surface: any HTTP, gRPC, websocket, or socket code at all? Any client libraries (`httpx`, `requests`, `aiohttp`, `grpc`)?

**Output:** `Deployment Topology` — table of resource × persistence location × concurrency assumption, plus an explicit list of every product-shaped assumption (single-user, single-process, single-machine).

---

### [9/12] Cloud substrate readiness — thin-deployment path

The cloud question, scoped to existing code rather than design. The downstream target (item E) is a **thin cloud deployment path** at the Fly.io / Modal / Railway level — a try-without-installing link, not a hosted product. Scope discipline matters: anything that drifts toward SaaS scope is a different business with a different surface area, and the scout should flag it.

- Identity: is there any user/tenant/session identity surface, or is everything implicitly local-user?
- Auth: any auth code, token handling, key management?
- Conflict resolution: any code that handles "two writers, one state" — CRDTs, OT, last-write-wins with timestamps, vector clocks, none?
- Sync: any pull/push semantics, any reconciliation logic, any concept of "remote vs. local"?
- Async-readiness: are state operations async-safe, or do they assume sync execution on a single thread?
- Cost/quota: any rate limiting, budget tracking, request counting?
- **Containerization signals:** any `Dockerfile`, `fly.toml`, `modal` imports, Procfile, `railway.json` — anything that suggests deployment thinking has started, or its absence?

**Output:** `Cloud Readiness` — what's in place, what's absent, a list of every assumption that would have to break for a thin-deployment cloud path to work, and an explicit warning list of any code that would push a thin-deployment toward full SaaS scope.

---

### [10/12] Benchmarks, eval sets, and token economics

The discovery question for "does it work" and "does it pay for itself." The downstream target (item B) is **standardized benchmark scaffolding and token telemetry across the substrate, instrumented on real Cozy workloads** — dollars per task on a workload that actually runs. The format decision is the hard part; populating numbers is grindable. The scout's job is to find what exists and what the format would have to subsume.

- Benchmarks: any timing harnesses, latency measurements, throughput tracking? Where? Run them if they exist (read-only — don't modify the harness).
- Eval sets: any structured eval suites — fixed inputs with expected outputs, accuracy/precision/recall harnesses, regression eval? List the files, count the cases. Note any pattern that resembles MTEB or SWE-bench structure (these are the reference precedents the format will need to interoperate with).
- Token economics: any code that tracks token consumption per operation, per session, per user? Any cost attribution, any budget enforcement? Note specifically whether per-call token counts are captured at the SDK boundary or only inferred.
- Performance regression detection: any baseline-comparison logic, any "this run was slower than the last run" surfacing?
- Observability: logging, metrics, tracing — what's emitted, where does it go, can you read it without instrumenting anything new?

**Output:** `Measurement Layer` — three sub-tables (benchmarks, eval, token economics) listing what exists, plus an explicit list of every claim about Moneta's quality, speed, or cost that the current code cannot substantiate.

---

### [11/12] Tests and stability signal

- Test count, framework, pass status. Run existing test scripts only — do not author new tests, do not modify test config.
- Identify which subsystems are well-tested vs. thin.
- Flag any test that exercises Moneta against a specific consumer surface — substrate-level testing should be surface-independent.

**Output:** `Test Coverage` — table of subsystem × test count × stability signal (solid / thin / untested) × surface-coupling flag.

---

### [12/12] Substrate-over-product synthesis

Synthesize across the previous eleven steps. Two outputs:

**A. Open questions for the v0.3 spec** — bulleted questions only. No proposed resolutions. The point is to surface, not solve. Cover at minimum:

- Contradictions between code and docs.
- Half-built features (TODO/FIXME density, empty modules, stubbed-out classes).
- Architectural gaps a substrate consumer will hit.
- Inside-out SDK location ambiguity (Moneta or consumer?).
- Codeless schema applicability (are the prim types ready for `usdGenSchema`, or do they need restructuring first?).
- Cloud substrate boundary (which primitives are deployment-agnostic, which assume local?).
- Eval and token economics ownership (substrate-level harness, or per-consumer?).
- EmbeddingGemma drop-in feasibility (is there a clean seam, or does retrieval need to be carved out first?).

**B. Product-shaped vs. substrate-shaped audit** — a table listing every place the current code assumes "product" semantics (one user, one process, one machine, one consumer surface, one deployment) when "substrate" semantics (many of each, deployment-agnostic, surface-neutral) is the stated goal. Include file references and one-line descriptions.

**Output:** `v0.3 Spec Open Questions` and `Product vs. Substrate Audit`.

---

## Closing

End `SCOUT_MONETA_v0_3.md` with a one-paragraph **Bottom line**:

In plain language, what does Moneta currently look like as a substrate? Stable or in flux? Production-shaped or research-shaped? Local-shaped or deployment-agnostic? Surface-coupled or surface-neutral? Where on the substrate-product spectrum does the code actually sit today, and how far is the gap to the v0.3 target?

---

## What This Map Unlocks

When `SCOUT_MONETA_v0_3.md` comes back, each downstream item gets concrete:

- **Item A — Codeless schema migration for Moneta** gets sized against step [7]. Either the prim types are amenable and the work is `schema.usda` authoring + `usdGenSchema` registration, or the prim types need restructuring first and the work doubles. The scout decides which.

- **Item B — Benchmark scaffolding + token telemetry** gets sourced from step [10]. The format decision becomes "extend what exists" or "design from scratch." Either way, the scope is known.

- **Item C — Cozy × Moneta demo** gets concrete against steps [4], [5], and [6]. The "it remembered" moment requires a known seam where Cozy attaches to Moneta's state and a known retrieval path that returns better answers as context accumulates. The scout finds the seams or finds the gaps.

- **Item D — EmbeddingGemma spike** gets sized against step [5]'s embedder-seam finding. If the seam exists, the spike is an afternoon. If it doesn't, the spike is preceded by carving one out — different scope, same intent.

- **Item E — Thin cloud deployment path** gets sourced from steps [8] and [9]. Every product-shaped assumption that would have to break is on a list, in order. The scope of "thin" is defined by what's already deployment-ready vs. what isn't.

- **Moneta v0.3 spec drafting** gets sourced from steps [4], [5], [12A], and [12B].

No building until this map is in hand.
