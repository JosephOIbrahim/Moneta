# AUDIT_pre_surgery

**Role:** Scout (read-only, per `EXECUTION_constitution_singleton_surgery.md` §MoE Roles).
**Step:** 1 of `HANDOFF_singleton_surgery.md`.
**Gate:** Surfaces at **G1**. No code written. No tests written. No files modified outside this document.

This audit catalogs everything the singleton surgery has to migrate, plus the things static analysis cannot see and that the Twin-Substrate test will have to catch. Every finding has a migration target. Migration targets reference the locked decisions in the handoff; Scout does not propose alternatives.

---

## Audit Procedure (per Handoff Step 1)

| Layer | Tool | What it catches |
|---|---|---|
| **1** | `ruff check --select B006,B008,RUF012` | Mutable-default args, call-time defaults, mutable class attrs |
| **2** | `grep` for `@functools.lru_cache`, `@cache`, `@cached_property` | Module-level memoization tied to the singleton |
| **3** | Manual catalog of module-level state in `src/moneta/`, plus `Sdf.Layer.FindOrOpen` use | The handoff's master singleton plus the C++-side trap |

The brief's note that **"the USD `Sdf.Layer.FindOrOpen` C++ registry trap is invisible to static analysis"** holds — Layers 1 and 2 cannot detect it. Layer 3's manual catalog locates the call sites; the Twin-Substrate test (Step 2) is the only proof that they are isolated under handle semantics.

---

## Layer 1 — `ruff B006 / B008 / RUF012`

**Command:** `ruff check --select B006,B008,RUF012 src/ tests/ scripts/`
**Result:** `All checks passed!` (zero findings, including under `--no-cache`)

| Rule | Findings | Migration target |
|---|---|---|
| B006 (mutable default arg) | **0** | none required |
| B008 (function call as default) | **0** | none required |
| RUF012 (mutable class attr without `ClassVar`) | **0** | none required |

**Note on ruff config drift.** `pyproject.toml` `[tool.ruff.lint]` selects `E, W, F, I, UP, B`. `B` includes B006/B008. `RUF012` is not selected by the project config but was selected explicitly via `--select` per the handoff — so the result is authoritative regardless of project config. No code change required; documenting this so Forge does not re-litigate the config selection at Step 3.

**Layer 1 verdict:** clean. No B006/B008/RUF012 findings to either resolve or document. The singleton-leak surface is not propagating through the Python defaults idiom.

---

## Layer 2 — Module-level cache decorators

**Command:** `grep -rn "@(functools\\.)?(lru_cache|cache|cached_property)" src/ tests/ scripts/`
**Result:** zero hits in production source, tests, or scripts. (One hit appears in `HANDOFF_singleton_surgery.md` itself referencing the search — not a code finding.)

| Decorator | Hits in `src/moneta/` | Migration target |
|---|---|---|
| `@functools.lru_cache` | **0** | none required |
| `@functools.cache` | **0** | none required |
| `@functools.cached_property` | **0** | none required |

**Layer 2 verdict:** clean. No module-level memoization is bound to the singleton's lifetime. No instance-level dictionaries need to be created on the handle as a result of this layer.

---

## Layer 3 — Module-level state and the USD layer-cache trap

The audit's primary findings live here. Layers 1 and 2 are clean; the singleton survives in plain module-level assignments and in the `Sdf.Layer` C++ registry.

### 3.1 The master singleton

| File:line | Symbol | Role | Migration target |
|---|---|---|---|
| `src/moneta/api.py:124` | `_state: Optional[_ModuleState] = None` | The canonical mutable singleton. Every public function dereferences it via `_require_state()`. | Becomes instance state on `Moneta` (Handoff Step 4: "Owns config. Owns state. Context-manager protocol."). The `_ModuleState` dataclass at `api.py:109-122` is the right shape; it migrates verbatim into the handle as `self.<field>`. |
| `src/moneta/api.py:127-133` | `def _require_state()` | Module-global dereference. Raises `MonetaNotInitializedError`. | Deleted. Methods on `Moneta` access `self.<field>` directly; "not initialized" is unrepresentable when constructor returns a usable handle. |
| `src/moneta/api.py:136-148` | `def _reset_state()` | Closes durability + authoring target, sets `_state = None`. Used by tests. | Becomes `Moneta.__exit__`. Same disposal sequence (durability close → authoring-target close), plus `_ACTIVE_URIS.discard(self.config.storage_uri)` per Handoff Step 5. |
| `src/moneta/api.py:142, 172` | `global _state` declarations | Mutate the singleton (in `_reset_state` and `init`). | Deleted. No module-level rebind in handle world. |
| `src/moneta/api.py:170` | `init()` function | Module-global constructor. Replaces any prior `_state` with a fresh instance. | Replaced by `Moneta(config)` constructor. Per Handoff §"What Was Decided": `Moneta()` with no args raises `TypeError`; `Moneta(config)` returns a handle. The `init()` function itself is removed at cutover (Handoff Step 6 "Hard cutover of all call sites"). |

### 3.2 Process-wide quota

| File:line | Symbol | Role | Migration target |
|---|---|---|---|
| `src/moneta/api.py:49` | `PROTECTED_QUOTA: int = 100` | Module-level integer. Enforced at `api.py:271`. | Becomes `MonetaConfig.quota_override: int = 100` per Handoff Step 3. The constant moves; the value 100 stays the default. The check at `api.py:271` becomes `self.config.quota_override`. |
| `src/moneta/api.py:271` | `state.ecs.count_protected() >= PROTECTED_QUOTA` | Sole enforcement site. | Becomes `self.ecs.count_protected() >= self.config.quota_override`. |
| `src/moneta/api.py:273` | f-string `f"protected quota of {PROTECTED_QUOTA} exceeded"` | Error message. | f-string substitutes `self.config.quota_override`. |
| `tests/unit/test_api.py:157, 165` | `range(moneta_api.PROTECTED_QUOTA)` | Test asserts process-wide constant. | Both call sites read `m.config.quota_override` (where `m` is the handle from the fixture). Forge owns the rewrite. |

### 3.3 Module-level immutable scalars (NOT migration targets)

These are spec-locked constants from MONETA.md / ARCHITECTURE.md. They are not singleton state. They remain at module scope as defaults; the handle does not need to own them.

| File:line | Symbol | Status |
|---|---|---|
| `src/moneta/types.py:27-29` | `EntityState.{VOLATILE, STAGED_FOR_SYNC, CONSOLIDATED}` | IntEnum members. Type definitions. Frozen. |
| `src/moneta/decay.py:31, 34, 35` | `DEFAULT_HALF_LIFE_SECONDS`, `MIN_HALF_LIFE_SECONDS`, `MAX_HALF_LIFE_SECONDS` | Tuning-range constants per MONETA.md §2.3. Frozen. |
| `src/moneta/consolidation.py:49-57` | `DEFAULT_MAX_ENTITIES`, `DEFAULT_IDLE_TRIGGER_MS`, `MAX_BATCH_SIZE`, `PRUNE_*`, `STAGE_*` | Sleep-pass thresholds locked by ARCHITECTURE.md §6 / §15.2. Frozen. |
| `src/moneta/durability.py:55, 57, 58` | `DEFAULT_SNAPSHOT_INTERVAL_SECONDS`, `SNAPSHOT_VERSION`, `WAL_VERSION` | Format constants + cadence default. Frozen. |
| `src/moneta/usd_target.py:86, 87` | `PROTECTED_SUBLAYER_NAME`, `DEFAULT_ROTATION_CAP` | Substrate convention #4 + ARCHITECTURE.md §15.2. Frozen. |
| `src/moneta/mock_usd_target.py:70, 71` | `SCHEMA_VERSION`, `PROTECTED_SUBLAYER` | JSONL schema constant + sublayer name. Frozen. |
| `src/moneta/api.py:49` | (`PROTECTED_QUOTA` — see 3.2 above; this one is a migration target) | Migrates. |
| `src/moneta/{api, consolidation, durability, decay, sequential_writer, mock_usd_target, ecs, usd_target, vector_index}.py` | `_logger = logging.getLogger(__name__)` (9 modules) | Stdlib logger handles. Stateless w.r.t. Moneta. Frozen. |

**No migration required for any row in 3.3.** They are flagged here so Forge does not waste cycles on them at Step 4.

### 3.4 The `Moneta` handle's existing internal shape

`_ModuleState` at `api.py:109-122` is already a dataclass with the exact field set the handle needs:

```
ecs                  # ECS instance
decay                # DecayConfig
attention            # AttentionLog
vector_index         # VectorIndex
consolidation        # ConsolidationRunner
sequential_writer    # SequentialWriter
authoring_target     # MockUsdTarget | UsdTarget
mock_target          # Optional[MockUsdTarget] for test compat
durability           # Optional[DurabilityManager]
```

**Migration target:** these nine fields become attributes of the `Moneta` handle. The `init()` body (`api.py:172-246`) becomes `Moneta.__init__` minus the `global _state` rebind. No restructuring needed; the construction recipe is right.

### 3.5 The four-op + harness API surface

Each `def`-at-module-level becomes an instance method on `Moneta`. The signatures are MONETA.md §9-locked; only the receiver changes (module → `self`).

| `api.py` line | Function | Becomes |
|---|---|---|
| `255` | `deposit(payload, embedding, protected_floor=0.0)` | `Moneta.deposit(...)` |
| `295` | `query(embedding, limit=5)` | `Moneta.query(...)` |
| `340` | `signal_attention(weights)` | `Moneta.signal_attention(...)` |
| `358` | `get_consolidation_manifest()` | `Moneta.get_consolidation_manifest()` |
| `374` | `run_sleep_pass()` | `Moneta.run_sleep_pass()` (harness verb, stays harness) |
| `402` | `smoke_check()` | Either `Moneta.smoke_check()` or a free function that constructs its own handle. Forge call. |

The five `_require_state()` call sites at `api.py:269, 311, 348, 365, 380` migrate to `self` access. There is no "may be uninitialized" branch in the handle world.

### 3.6 Existing `MonetaConfig` — replacement, not extension

`api.py:70-101` already defines `MonetaConfig` — but the existing dataclass diverges from the locked Step 3 specification:

| Concern | Current (api.py:70-101) | Handoff Step 3 specification |
|---|---|---|
| `frozen` | Not frozen | **Frozen** |
| `kw_only` | Not `kw_only=True` | **`kw_only=True`** |
| Primary identity field | none (`storage_uri` does not exist) | **`storage_uri: str` (irreducible, no default)** |
| Quota field | none (`PROTECTED_QUOTA` is module-level) | **`quota_override: int = 100` (irreducible)** |
| Path fields | `snapshot_path`, `wal_path`, `mock_target_log_path`, `usd_target_path`, `vector_persist_path` (5 separate Optional Paths) | brief calls for `storage_uri` to subsume these — exact derivation is a Forge / brief-implementation call |
| Tuning fields | `half_life_seconds`, `embedding_dim`, `max_entities` | not in the Step 3 minimum |
| Backend toggle | `use_real_usd: bool` | not in the Step 3 minimum |
| `ephemeral()` factory | absent | **`MonetaConfig.ephemeral()` classmethod required** |
| Cloud-anticipated commented fields | absent | **`tenant_id`, `sync_strategy` commented but not implemented** |

**Migration target:** `MonetaConfig` is **replaced**, not extended. This is a Forge call per Handoff Step 3. **G1 surfacing:** the existing `MonetaConfig` is consumed by tests in six files and by `init(config=...)` — replacement cascades. See §3.7.

The `field` import at `api.py:26` (`from dataclasses import dataclass, field`) is unused in the current config; flagged here as a noise observation, not a surgery target.

### 3.7 Singleton fan-out — call-site inventory

These are the consumers that depend on the module-global. Each is a migration target for cutover at Step 6.

#### Production code

| File:line | Reference | Migration |
|---|---|---|
| `src/moneta/api.py:124` | `_state` declaration | removed |
| `src/moneta/api.py:127, 142, 172` | `_state` reads/writes inside the module | removed |
| `src/moneta/api.py:269, 311, 348, 365, 380` | `state = _require_state()` inside each public function | replaced with `self` access on `Moneta` |
| `src/moneta/__init__.py:6-17` | re-exports of `init`, `deposit`, `query`, `signal_attention`, `get_consolidation_manifest`, `run_sleep_pass`, `smoke_check`, `MonetaConfig`, `MonetaNotInitializedError`, `ProtectedQuotaExceededError` | replaced by re-export of `Moneta`, `MonetaConfig`, `MonetaResourceLockedError`. Existing module-level functions are removed at cutover. `MonetaNotInitializedError` is deleted (cannot occur in handle world). The exact final `__all__` is a Forge call within the brief's bounds. |

#### Tests touching the singleton

Six files (the substrate-level unit tests `test_ecs.py`, `test_decay.py`, `test_attention_log.py`, `test_usd_target.py`, `test_sequential_writer_ordering.py` test classes directly and do **not** touch the singleton — they are not in scope for cutover):

| File | Singleton-touching uses (counts) | Migration shape |
|---|---|---|
| `tests/conftest.py` | `_reset_state()` (4), `moneta.init()` (1) | Two fixtures — `fresh_moneta`, `uninitialized_moneta` — restructured around `with Moneta(MonetaConfig.ephemeral()) as m: yield m`. The "uninitialized" fixture has no analogue in handle world (per §3.5); test-side adjustment required. |
| `tests/unit/test_api.py` | `init()` (4), `_reset_state()` (0), `PROTECTED_QUOTA` reads (2), unqualified four-op calls (~37) | Each test consumes the handle from the fixture: `def test_X(self, fresh_moneta: Moneta) -> None: fresh_moneta.deposit(...)`. Quota assertions read `fresh_moneta.config.quota_override`. The signature-conformance test (`test_four_op_signatures_match_spec_verbatim` at line 58) currently parses `moneta.api` source for module-level `def`s — needs to walk class methods on `Moneta` instead. |
| `tests/integration/test_durability_roundtrip.py` | `_reset_state()` (~13), `moneta.init(...)` (~7), direct `moneta_api._state` reads (~6), `moneta.deposit/query/...` (many) | Each `kill -9` simulation in the suite is currently `_reset_state(); moneta.init(...)`. In handle world this becomes `m.__exit__(...); m2 = Moneta(same_config)` — and **`MonetaResourceLockedError` will fire if `__exit__` did not release the URI** (Step 5 invariant). This is a Twin-Substrate-adjacent risk: a test that re-inits on the same paths must successfully exit before re-construct. Crucible should confirm. |
| `tests/integration/test_end_to_end_flow.py` | `init(...)`, `_state` reads (4) | Same pattern. Direct `_state` reads become attribute access on the handle. |
| `tests/integration/test_real_usd_end_to_end.py` | Two fixtures (`fresh_moneta_usd`, `fresh_moneta_mock`), each `_reset_state(); init(config=...)`. Plus `_reset_state()` calls at 267 and 303. | Fixture restructure mirrors `conftest.py`. |
| `tests/load/synthetic_session.py` | `_reset_state()` (4) | Synthetic-session harness restructured to use the handle. The 30-min completion gate must keep passing through the cutover. |

**Counts (verified by grep):**
- 23 direct reads of `moneta_api._state` across tests.
- 73 test-side hits on `moneta_api._reset_state`, `moneta_api._state`, or `moneta_api.PROTECTED_QUOTA` total.
- 66 unqualified four-op call sites in tests (after `from moneta import deposit, query, ...`).

These counts size the cutover PR. Exact rewrites are a Forge call.

### 3.8 The USD `Sdf.Layer` C++ registry trap (Layer 3, manual)

This is the brief's flagged trap: pxr's `Sdf.Layer` registry is **process-global C++ state** that no static analyzer can see.

| File:line | Call | Behavior |
|---|---|---|
| `src/moneta/usd_target.py:148` | `Sdf.Layer.CreateAnonymous("cortex_root")` | Creates an anonymous layer. Anonymous layers are not registered by file path — collisions are by anonymous identifier (rare). Low risk. |
| `src/moneta/usd_target.py:152` | `Sdf.Layer.CreateNew(root_path)` | Creates `cortex_root.usda` at the configured path. **Registered by absolute file path** in the C++ layer registry. |
| `src/moneta/usd_target.py:154` | `Sdf.Layer.FindOrOpen(root_path)` | Fallback when `CreateNew` returns `None` (file already exists). Also registers / finds by file path. |
| `src/moneta/usd_target.py:173` | `Sdf.Layer.CreateAnonymous(name)` | Same as line 148, for non-root anonymous layers in in-memory mode. |
| `src/moneta/usd_target.py:176` | `Sdf.Layer.CreateNew(layer_path)` | Per-sublayer file (`cortex_protected.usda`, `cortex_YYYY_MM_DD.usda`). Registered by file path. |
| `src/moneta/usd_target.py:178` | `Sdf.Layer.FindOrOpen(layer_path)` | Fallback when `CreateNew` returns `None`. Registered by file path. |

**The trap.** Two `UsdTarget` instances pointed at the same `log_path` directory will share `Sdf.Layer` objects via the C++ registry. A write through handle A's `UsdTarget` would mutate the same in-memory `Sdf.Layer` that handle B's `UsdTarget` references. Static analysis (Layers 1 and 2) cannot detect this — the Python code holds distinct `UsdTarget` instances; the C++ runtime collapses them at the layer level.

**Migration target.** Per Handoff Step 5: the in-memory `_ACTIVE_URIS` registry refuses construction of two handles on the same `storage_uri`. Combined with the brief's Q4 invariant — "two handles on the same `storage_uri` raise `MonetaResourceLockedError`" — the layer-cache collision is **prevented by construction**. The `_ACTIVE_URIS` set is the Python-side guard for the C++-side trap.

**The Twin-Substrate test (Step 2)** is the only proof this guard works in practice:
- Two handles on **different** `storage_uri` must produce isolated state — distinct ECS, distinct vector index, distinct `Sdf.Layer` instances under the hood. Forge writes the test against this contract.
- Two handles on the **same** `storage_uri` must raise `MonetaResourceLockedError` before either touches USD. Crucible's adversarial test (per constitution §7) verifies this.

**Anonymous-mode caveat to flag at G1.** The protocol distinction between anonymous and disk-backed layers matters here. With `usd_target_path=None`, every layer is anonymous and the C++ identifier is auto-generated — collisions between handles are negligible. With a real disk path, the file path is the registry key and collisions are *guaranteed* if `_ACTIVE_URIS` is bypassed or the cutover misses a release on `__exit__`. The Twin-Substrate test must include the disk-backed path branch, not just anonymous mode, to exercise the trap.

### 3.9 Process resources that `__exit__` must release before URI release

The handoff's `_ACTIVE_URIS.discard()` on `__exit__` is necessary but not sufficient — these handles also own native resources whose disposal must precede URI release, otherwise a re-construct on the same URI races against in-flight workers or open file pointers.

| Resource | Owner | Current cleanup | Migration target |
|---|---|---|---|
| Daemon snapshot thread | `DurabilityManager._bg_thread` (`durability.py:77, 245-251`) | `durability.close()` calls `stop_background()` which sets the stop event and joins (5s timeout). | `Moneta.__exit__` calls `self.durability.close()` if present. Same operation as today's `_reset_state` at `api.py:144-145`. **Order in `__exit__`: close durability → close authoring target → discard from `_ACTIVE_URIS`.** Reverse order risks a re-construct that finds the URI free but the prior background thread still alive. |
| WAL file pointer | `DurabilityManager._wal_fp` (`durability.py:74`) | `durability.close()` → `_wal_fp.close()` under `_lock`. | Same. Subsumed by the `durability.close()` call above. |
| Mock USD log file pointer | `MockUsdTarget._fp` (`mock_usd_target.py:94`) | `_reset_state` calls `authoring_target.close()` if it has the method (`api.py:146-147`). `MockUsdTarget.close()` exists at `mock_usd_target.py:164-167`. | `Moneta.__exit__` calls `self.authoring_target.close()` if it has the method. Same predicate. |
| Real USD layers (`Sdf.Layer` instances) | `UsdTarget._layers` dict (`usd_target.py:142`) | `UsdTarget.close()` at `usd_target.py:320-325` clears the dict and the stage reference. | Same call, but **Python-side dict clearing does not evict from the C++ `Sdf.Layer` registry.** The C++ registry holds layers by identifier as long as any reference survives, including weak references the runtime tracks. This means a quick re-construct on the same path may *find* the prior layers still in the registry. The `_ACTIVE_URIS` guard prevents the consumer from doing this; it does NOT cleanup the registry itself. **G1 note:** Forge should not assume `UsdTarget.close()` evicts from the C++ registry. Twin-Substrate test on disk-backed mode must verify isolation under the `_ACTIVE_URIS` discipline, not under any "registry clears on close" assumption. |
| ECS row data, vector index, attention log | `_ModuleState` fields | Released by garbage collection when `_state = None`. | Released by GC when the handle goes out of scope. No explicit cleanup required. |

---

## Cross-cutting findings (not in any single layer)

### F1. The Deep Think brief is missing on disk

The handoff document references `DEEP_THINK_BRIEF_substrate_handle.md` at the repo root as the design source of truth. **The file does not exist on disk.** The handoff's "What Was Decided" table contains the locked spine; `EXECUTION_constitution_singleton_surgery.md` references the brief implicitly via Q1–Q4 numbering.

**G1 surfacing.** Scout cannot adjudicate whether the handoff table is sufficient or whether the missing brief contains additional constraints (e.g. exact `MonetaConfig` field set, exact `MonetaResourceLockedError` message, tenant_id field comments). Per Constitution §1 ("Forge reads existing test patterns ... Frozen boundaries identified first"), Forge should not start Step 3 without the brief on disk OR the human's confirmation that the handoff's spine table is the operating spec. **This is a Scout flag, not a blocker per the Bounded-Failure protocol — Scout is not authorized to call a blocker on a missing input that the human can produce.** Surfacing for human triage at G1.

### F2. `MonetaConfig` collision between current code and Step 3 specification

`MonetaConfig` already exists in `api.py:70-101` and is consumed by tests. It is **not** the dataclass the handoff requires. The mismatch is structural (`frozen=False`, no `kw_only`, no `storage_uri`, no `quota_override`, no `ephemeral()` factory). Step 3 calls for a replacement, not an extension.

**G1 surfacing.** The handoff's irreducible-vs-cloud-anticipated split (`storage_uri`, `quota_override` mandatory; `tenant_id`, `sync_strategy` commented) **does not preserve** the existing config's path/tuning fields (`snapshot_path`, `wal_path`, `mock_target_log_path`, `usd_target_path`, `vector_persist_path`, `half_life_seconds`, `embedding_dim`, `max_entities`, `use_real_usd`). The handoff says `storage_uri` is "irreducible" but does not specify whether it subsumes the current path fields (one URI parsed into multiple paths) or whether a parallel set of fields survives. **This is the most likely place for a Forge / brief disagreement to surface as a PR note (per Constitution §5).** Scout flags it but does not propose a resolution.

### F3. `MonetaNotInitializedError` becomes unreachable

`MonetaNotInitializedError` (`api.py:52-53`) is raised by `_require_state()` when an op is called before `init()`. In the handle world, "not initialized" is unrepresentable: the constructor either returns a usable handle or raises. The error class becomes dead code at cutover.

**Migration target.** Delete the class at Step 6. Tests that asserted it (`tests/unit/test_api.py:82-91` — `test_requires_init_raises`) are removed or restructured. Scout flags this so Forge does not need to invent a deprecation pathway.

### F4. The `field` dataclass import is unused

`api.py:26`: `from dataclasses import dataclass, field`. `field` is never used in the file. Will likely become unused or used (depending on `MonetaConfig` rewrite) at Step 3.

**Migration target.** Forge cleans up at Step 3. Noise observation.

### F5. PEP 703 / sub-interpreter posture is unchanged

The lock-free attention log (`attention_log.py:8-32`) and decay-config thread-safety claim (`decay.py:80-82`) explicitly disclaim correctness under free-threaded Python and sub-interpreters. The handle migration **does not change this** — `_ACTIVE_URIS` is a plain `set` mutated under no lock. A free-threaded run could see a TOCTOU between `_ACTIVE_URIS.__contains__` and `_ACTIVE_URIS.add` in `__enter__`.

**Migration target.** Out of scope for this surgery per Handoff §"What This Surgery Is Not" ("Not the cloud surgery"). Forge does not lock `_ACTIVE_URIS`; the GIL holds the invariant under CPython 3.11/3.12. Documenting the same posture as today's substrate.

### F6. `dist/` artifact version drift

`dist/moneta-0.2.0-py3-none-any.whl` and `.tar.gz` exist alongside `pyproject.toml v=1.0.0`. Handoff Step 8 resolves this as part of the surgery PR.

**Migration target.** Steward at Step 8. Scout records the existing state so Steward knows what to clean up.

### F7. Test files that do **not** touch the singleton — unchanged at cutover

These files exercise classes directly without going through `moneta.init()` and are out of scope for the cutover edits:

- `tests/unit/test_ecs.py`
- `tests/unit/test_decay.py`
- `tests/unit/test_attention_log.py`
- `tests/unit/test_usd_target.py`
- `tests/integration/test_sequential_writer_ordering.py`

**Migration target.** None. They remain as-is. Scout records this so Forge does not waste cycles re-verifying them.

---

## Summary of migration targets

| Finding | File:line | Layer | Migration target | Owner |
|---|---|---|---|---|
| Master singleton `_state` | `api.py:124` | 3 | Instance state on `Moneta` | Forge Step 4 |
| `_require_state` | `api.py:127-133` | 3 | Deleted | Forge Step 4 |
| `_reset_state` | `api.py:136-148` | 3 | Becomes `Moneta.__exit__` | Forge Steps 4–5 |
| `init()` function | `api.py:170-246` | 3 | Becomes `Moneta.__init__` (no module-level rebind) | Forge Step 4 |
| `PROTECTED_QUOTA = 100` | `api.py:49` | 3 | `MonetaConfig.quota_override: int = 100` | Forge Step 3 |
| Quota check | `api.py:271-273` | 3 | Reads `self.config.quota_override` | Forge Step 4 |
| Quota refs in tests | `test_api.py:157, 165` | 3 | Read from handle's config | Forge Step 6 |
| Existing `MonetaConfig` | `api.py:70-101` | 3 | Replaced (frozen, kw_only, storage_uri, quota_override, ephemeral()) | Forge Step 3 (PR note if brief diverges from handoff spine) |
| `_ModuleState` dataclass | `api.py:109-122` | 3 | Field set migrates to `Moneta` instance attrs | Forge Step 4 |
| Four ops + run_sleep_pass | `api.py:255-394` | 3 | Become methods on `Moneta` (signatures locked, only receiver changes) | Forge Step 4 |
| `_require_state()` call sites | `api.py:269, 311, 348, 365, 380` | 3 | Become `self` access | Forge Step 4 |
| Module re-exports | `__init__.py:6-17` | 3 | Re-export `Moneta`, `MonetaConfig`, `MonetaResourceLockedError` | Forge Step 6 |
| `MonetaNotInitializedError` | `api.py:52-53` | 3 (cross-cutting F3) | Deleted | Forge Step 6 |
| Test fixtures | `conftest.py` | 3 | Yield handle from `with Moneta(...)` block | Forge Step 6 |
| Singleton-consuming tests (6 files) | listed in §3.7 | 3 | Take handle from fixture; access `m.config.quota_override`, etc. | Forge Step 6 |
| Direct `moneta_api._state` reads (23) | listed in §3.7 | 3 | Become attribute access on the handle yielded by the fixture | Forge Step 6 |
| `Sdf.Layer.{CreateNew,FindOrOpen}` calls | `usd_target.py:152, 154, 176, 178` | 3 | Behavior-by-construction guarded by `_ACTIVE_URIS`; verified by Twin-Substrate test (disk-backed branch) | Forge Steps 5, 7; Crucible at G2 |
| `UsdTarget._layers` C++ registry residue | `usd_target.py:142, 320-325` | 3 (cross-cutting) | Out of scope to fix; documented assumption that `_ACTIVE_URIS` is the guard, not registry eviction | Crucible adversarial test (constitution §7 "construct, exit, re-construct on same URI") |
| Daemon thread + file pointers in `__exit__` order | `durability.py`, `mock_usd_target.py`, `usd_target.py` | 3 (cross-cutting) | `__exit__`: close durability → close authoring target → discard from `_ACTIVE_URIS` | Forge Steps 4–5 |
| `field` unused import | `api.py:26` | cross-cutting F4 | Cleaned up at Step 3 | Forge Step 3 |
| `dist/` version drift | repo root | cross-cutting F6 | Resolved at Step 8 | Steward Step 8 |
| Layer 1 (ruff B006/B008/RUF012) | n/a | 1 | None — clean | n/a |
| Layer 2 (`@lru_cache`/`@cache`/`@cached_property`) | n/a | 2 | None — clean | n/a |
| PEP 703 / sub-interpreter posture | `attention_log.py`, `decay.py`, future `_ACTIVE_URIS` | cross-cutting F5 | Out of scope; documented as unchanged | n/a (parked per handoff "What This Surgery Is Not") |
| Untouched test files | listed in §F7 | n/a | None | n/a |

---

## G1 — Items requiring human triage before Step 2

Per Constitution §"Gate Placement": **G1 is the only mid-surgery gate; its purpose is to triage surprises before cutover commits to a direction.** Three items surfaced.

| # | Item | Why it needs human attention |
|---|---|---|
| **G1.1** | `DEEP_THINK_BRIEF_substrate_handle.md` is referenced as the design source of truth but absent on disk (Finding F1). | Constitution §"Gate Placement" frames G1 as "if the audit surfaces something Deep Think didn't anticipate ... the human decides whether to proceed with the planned surgery or reopen design." Scout cannot adjudicate whether the handoff's spine table is the full spec or whether the brief contains tighter constraints. The handoff says "Disagreements with the brief are flagged as notes in the PR" — but Forge cannot flag a disagreement with a document it cannot read. **Decision needed:** is the handoff's "What Was Decided" table the operating spec, or is the brief due back on disk before Step 2 begins? |
| **G1.2** | `MonetaConfig` field-set collision (Finding F2). The handoff's irreducible fields are `storage_uri` and `quota_override`. The current `MonetaConfig` carries seven other fields that downstream tests depend on (`snapshot_path`, `wal_path`, `mock_target_log_path`, `usd_target_path`, `vector_persist_path`, `half_life_seconds`, `embedding_dim`, `max_entities`, `use_real_usd`). | The handoff does not state whether these fields survive Step 3, whether `storage_uri` parses into them, or whether they migrate to a separate config object. Forge cannot infer the answer from the brief because the brief is unavailable (G1.1). **Decision needed:** Forge will need an explicit ruling on `storage_uri` semantics before Step 3 can produce a frozen dataclass that does not break six test files. |
| **G1.3** | Disk-backed Twin-Substrate test scope (§3.8 anonymous-mode caveat). The C++ `Sdf.Layer` registry trap manifests **only** under disk-backed paths. An anonymous-mode-only Twin-Substrate test would not exercise the trap. | The handoff's Step 2 description does not specify anonymous vs disk-backed mode for the test. The brief presumably does. Without the brief, Forge will infer — likely correctly — but the inference is itself a decision the audit cannot validate. **Decision needed (light-touch):** confirm the Twin-Substrate test exercises the disk-backed branch, or accept Forge's inference. |

If the human's response to G1 is "proceed with the handoff's spine table as the operating spec; Twin-Substrate test on disk-backed paths," the Scout audit is complete and Forge takes Step 2.

---

## Items explicitly out of scope (per handoff §"What This Surgery Is Not")

Scout records these for clarity. None are migration targets.

- The codeless schema migration (parked).
- The embedder seam (parked).
- SDK / inside-out runtime integration (parked).
- Benchmark scaffolding + token telemetry (parked).
- Concurrency primitive change for free-threaded Python (parked, Finding F5).
- General code-quality refactor (parked).
- USD writer typeless `Sdf.SpecifierDef` → typed authoring (parked, Constitution §1).

---

## Audit verdict

- **Layer 1: clean.** No B006/B008/RUF012 findings.
- **Layer 2: clean.** No module-level cache decorators in production source.
- **Layer 3: bounded.** One singleton (`_state`), one process-wide quota (`PROTECTED_QUOTA`), six call-site files in tests, and the documented USD `Sdf.Layer` C++ registry trap whose Python-side guard is the `_ACTIVE_URIS` registry from Step 5 and whose only verification path is the Step 2 Twin-Substrate test in its disk-backed branch.
- **Cross-cutting:** seven additional findings (F1–F7), three of which surface at G1 as items requiring human triage.

The surgery is well-scoped. The migration targets are concrete. The trap that static analysis cannot see has a defined catch (Twin-Substrate test) and a defined guard (`_ACTIVE_URIS`). Stopping here per Constitution §"Gate Placement" and §"Role Isolation": Scout has produced the artifact; Forge does not move until the human clears G1.

---

*Scout, Step 1 complete. Awaiting G1 clearance per `EXECUTION_constitution_singleton_surgery.md`.*
