# Multi-agent review synthesis — Moneta v1.0.0

**Total findings (all loops):** 494  **Open after closures:** 466  **§9 candidates:** 8  **Critical:** 17  **High:** 100

**Constitution hash:** `3b56e3ffae083c9b`

## §9 escalation candidates

### `architect-L1-four-op-signatures-drift` — Critical — ARCHITECTURE.md §2 specifies the four-op API as module-level callables with self-less signatures, but src/moneta/api.py implements them as bound methods on a `Moneta` class; the §16 conformance check ('api.py must export exactly these four callables with exactly these signatures') cannot pass against the current code.

**Role:** architect  **File:** `ARCHITECTURE.md:27-42`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
```python
def deposit(payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID
def query(embedding: List[float], limit: int = 5) -> List[Memory]
def signal_attention(weights: Dict[UUID, float]) -> None
def get_consolidation_manifest() -> List[Memory]
```

Agents have zero knowledge of ECS, USD, vector indices, decay, or consolidation. All internals are implementation concerns.

**Conformance:** `src/moneta/api.py` must export exactly these four callables with exactly these signatures.
```

**Proposed change:** Update ARCHITECTURE.md §2 to express the four-op API as instance methods on `Moneta` (signatures `def deposit(self, payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID`, etc.), and update §16 conformance to check class-method signatures. Cite the v1.1.0 surgery decision (DEEP_THINK_BRIEF_substrate_handle.md / SURGERY_complete.md referenced in README) as the lineage. Without this update, the locked spec's literal conformance check is impossible to satisfy.

**Risk if wrong:** If the spec is correct as written and the implementation is wrong, then v1.1.0 silently violated a locked decision (Constitution §1 round closure). If the implementation is correct (per the cited Deep Think round), the spec is stale and any future engineer reading ARCHITECTURE.md alone will rebuild the wrong surface.

**References:** `ARCHITECTURE.md §2`, `ARCHITECTURE.md §16`, `MONETA.md §2.1`, `CLAUDE.md 'Locked decisions'`

---

### `architect-L3-protected-consolidation-contradiction` — Critical — MONETA.md §2.5 declares protected entities consolidate to `cortex_protected.usda` (a routing destination, not an exemption), but ARCHITECTURE.md §6 selection criteria require `Utility < 0.3` to stage — and the protected-floor clamp pins utility at the floor for any entity with `protected_floor ≥ 0.3`, mathematically guaranteeing those entities NEVER stage; phase3-closure.md §4 acknowledges this as a 'known limitation' but the contradiction between MONETA.md §2.5 and ARCHITECTURE.md §6 is unresolved at the spec layer.

**Role:** architect  **File:** `ARCHITECTURE.md:114-142`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
**Trigger conditions:**

- ECS volatile count exceeds `MAX_ENTITIES`, **or**
- Inference queue idle > 5000 ms.

**Selection criteria:**

- `Utility < 0.1 AND AttendedCount < 3` → **prune** (delete entirely).
- `Utility < 0.3 AND AttendedCount >= 3` → **stage for USD authoring**.
```

**Proposed change:** Architect drafts a §9 Trigger 2 brief reconciling MONETA.md §2.5 ('Protected entities... consolidate to a dedicated cortex_protected.usda layer pinned permanently to the strongest position') against ARCHITECTURE.md §6 selection criteria. Two viable resolutions: (a) extend §6 with a parallel selection rule for protected entities (e.g., `protected_floor > 0 AND AttendedCount >= 3 AND time_since_deposit > T` triggers protected-sublayer authoring without requiring utility decay), or (b) amend MONETA.md §2.5 to acknowledge protected entities are exempt from periodic consolidation by spec design and that `cortex_protected.usda` is hydrated only via explicit operator action (the unpin tool inverse). Either resolution is fine; the current state — three locked artifacts that mutually contradict — is not.

**Risk if wrong:** If the contradiction is somehow benign (e.g., MONETA.md §2.5's 'consolidate to' is read as 'WHEN they consolidate, they go to'), then the current behavior matches an alternative interpretation and the finding is documentation-only. But docs/phase3-closure.md §4 explicitly names the gap as a 'limitation' and a 'v1.1 task', which is incompatible with the benign reading. The locked spec layer needs to settle which reading governs.

**References:** `MONETA.md §2.5`, `ARCHITECTURE.md §6`, `docs/phase3-closure.md §4`, `MONETA.md §9 Trigger 2`

---

### `consolidation-L3-protected-floor-stage-trap` — Critical — Protected memories with protected_floor >= 0.3 NEVER stage and NEVER prune — they remain VOLATILE for the lifetime of the substrate, directly contradicting MONETA.md §2.5's promise that 'protected entities consolidate to a dedicated cortex_protected.usda layer'; the locked Round 2 selection criteria (utility < 0.3 AND attended_count >= 3) cannot fire because decay clamps utility at floor, so utility < 0.3 is unreachable when floor >= 0.3.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:114-135`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
if (
                memory.utility < PRUNE_UTILITY_THRESHOLD
                and memory.attended_count < PRUNE_ATTENDED_THRESHOLD
            ):
                prune_ids.append(memory.entity_id)
            elif (
                memory.utility < STAGE_UTILITY_THRESHOLD
                and memory.attended_count >= STAGE_ATTENDED_THRESHOLD
            ):
                stage_ids.append(memory.entity_id)
```

**Proposed change:** This is a §9 Trigger 2 candidate: MONETA.md §2.5 mandates protected-memory consolidation but ARCHITECTURE.md §6's locked selection criteria preclude it for any floor >= 0.3. The integration test test_protected_floor_routes_to_protected_sublayer only passes because it specifically uses floor=0.2 (below stage threshold). Architect must rule whether (a) selection adds a protected-aware clause that stages protected entities on a different trigger (e.g., age, or AttendedCount alone), or (b) §2.5's consolidation promise is amended to 'protected entities are pinned in the hot tier and never consolidate'. Path (a) extends Round 2's locked criteria; path (b) admits the spec gap. Today neither is true and the substrate silently violates §2.5.

**Risk if wrong:** If wrong, tests would have caught it. They don't because protected_floor is exercised only at floor=0.2 (a value carefully chosen to land between thresholds). Production callers using floor=1.0 (the canonical 'pin forever' value documented in README) get exactly zero consolidation activity for those entities — they never reach cortex_protected.usda, never appear in any patent-evidence demonstration of claim #4 ('Protected memory as root-pinned strong-position sublayer'), and the four substrate novelty claims silently rest on a USD authoring path the substrate cannot reach.

**References:** `MONETA.md §2.5`, `MONETA.md §2.10`, `ARCHITECTURE.md §6`, `ARCHITECTURE.md §10`, `docs/phase3-closure.md §4.1 (known limitations)`, `MONETA.md §3 claim #4`

---

### `adversarial-L1-multi-handle-protected-quota-aggregation` — High — ARCHITECTURE.md §10 declares 'Hard cap: 100 protected entries per agent', but the v1.1.0 multi-instance handle pattern lets a single agent process construct N Moneta handles on N storage_uris and pin 100×N protected entries. The §10 backstop ('agents will try to flag everything as protected') is a per-process safety property the spec authorizes, but the implementation enforces only per-handle caps.

**Role:** adversarial  **File:** `src/moneta/api.py:264-274`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
if (
            protected_floor > 0.0
            and self.ecs.count_protected() >= self.config.quota_override
        ):
            raise ProtectedQuotaExceededError(
                f"protected quota of {self.config.quota_override} "
```

**Proposed change:** Decide explicitly: (a) §10 is reinterpreted as 'per substrate handle' to match the v1.1.0 multi-tenant model — update ARCHITECTURE.md §10 + MONETA.md §2.10 accordingly, citing DEEP_THINK_BRIEF_substrate_handle.md as lineage; or (b) add a process-level protected counter alongside `_ACTIVE_URIS` that aggregates across handles and enforces 100 globally. Path (a) is consistent with multi-tenant cloud deployment and matches what the code does; path (b) preserves the literal spec but is incompatible with multi-tenant operation. Either way, the silent semantic shift from 'per agent' to 'per handle' is itself a §9 candidate.

**Risk if wrong:** If §10 'per agent' was intended as a per-process safety invariant against agent abuse, multi-instance handles silently subvert it. If §10 was always meant per-substrate, the v1.1.0 surgery should have updated the spec. Today neither is documented.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `DEEP_THINK_BRIEF_substrate_handle.md`

---

### `architect-L2-vector-authoritative-vs-hydrate-inversion` — High — ARCHITECTURE.md §7 declares the vector index authoritative for 'what exists' as the runtime invariant that justifies sequential-write atomicity, but Moneta's hydrate path rebuilds the vector index from the ECS snapshot — silently inverting the authoritative store on every restart and breaking the very assumption that orphan-tolerance depends on.

**Role:** architect  **File:** `src/moneta/api.py:186-211`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
self.ecs, wal_replay = self.durability.hydrate()
                # Rebuild vector index from hydrated ECS (shadow rebuild).
                for memory in self.ecs.iter_rows():
                    self.vector_index.upsert(
                        memory.entity_id,
                        memory.semantic_vector,
                        memory.state,
                    )
```

**Proposed change:** Either (a) persist the vector index to disk alongside the ECS snapshot so the restart preserves the runtime authoritative-store ordering — VectorIndex.snapshot()/restore() already exist in vector_index.py but are orphaned (Loop 1 persistence-L1-vector-snapshot-orphan), wire them through DurabilityManager; or (b) amend ARCHITECTURE.md §7 with an explicit clause: 'On hydrate, the ECS snapshot is authoritative; the vector index is rebuilt as a shadow of the hydrated ECS rows. Runtime authoritativeness flips back to the vector index on the first deposit.' Path (a) honors the locked invariant; path (b) documents the inversion. Today neither is in force.

**Risk if wrong:** A kill-9 between deposit's ecs.add and vector_index.upsert leaves a partial deposit; the runtime invariant says 'doesn't exist' (vector wins), but on hydrate the row IS in ECS and is replayed into the vector. The deposit silently 'recovers' across a crash even though it was incomplete at the moment of the crash. Spec-level surprise candidate (§9 Trigger 2): the atomicity reasoning in §7 — 'orphans benign because Pcp never traverses' — assumes the vector remains authoritative across restart. It does not.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §11`, `src/moneta/durability.py:hydrate`, `src/moneta/vector_index.py:snapshot`

---

### `architect-L2-handle-exclusivity-concurrency-model-unspecified` — High — The v1.1.0 handle exclusivity model — `_ACTIVE_URIS` as a process-level lock, check-then-add inside the constructor, release on close — is treated as a locked decision in README but absent from ARCHITECTURE.md, including its concurrency model: TOCTOU under CPython GIL, behavior under fork(), behavior under PEP 703 free-threading, and the cleanup ordering requirement when SIGTERM arrives mid-with-block.

**Role:** architect  **File:** `ARCHITECTURE.md:25-60`  **§9:** yes  **Conflicts with locked decision:** no
**Closes:** `architect-L1-handle-pattern-undocumented`

**Evidence:**

```
### 2.1 Harness-level bootstrap (not part of the agent API)

The module also exposes `init()`, `run_sleep_pass()`, `smoke_check()`, and `MonetaConfig`. **These are not part of the agent-facing four-op surface.** They are harness-level entry points used by test fixtures, operator scripts, and Consolidation Engineer's sleep-pass scheduler. Agents never call them; fifth-op rules do not apply.
```

**Proposed change:** Add ARCHITECTURE.md §2.2 'Substrate handle and process-level exclusivity' covering: (1) `Moneta(config)` is the sole constructor; no-arg construction is a TypeError by contract; (2) two live handles on the same `storage_uri` raise MonetaResourceLockedError synchronously at the second constructor call; (3) the exclusivity primitive is an in-memory Python set, NOT a file lock, NOT a distributed lock — single process only; (4) check-then-add atomicity relies on CPython GIL bytecode semantics and is undefined under PEP 703 free-threaded Python or under sub-interpreters with per-interpreter GILs; (5) fork() inheritance is undefined — the child process inherits a copy of `_ACTIVE_URIS` whose contents reference handles that no longer exist in its address space, and a child constructor on a previously-held URI will spuriously raise; (6) close ordering is durability-thread-stop → authoring-target-close → URI release. Cite DEEP_THINK_BRIEF_substrate_handle.md §5.4 as lineage and Loop 1's Crucible adversarial test (test_concurrent_construction_yields_at_most_one_handle) as empirical evidence for the GIL-only guarantee. Without §2.2 the rule that locks Moneta to single-process operation is invisible to a reader of the spec, and a Phase 4 cloud-deployment surgery (the brief explicitly anticipates s3:// or moneta:// URIs) has no foundation to extend.

**Risk if wrong:** Concurrency-shaped extensions to the codebase compound on this gap: free-threaded TOCTOU (Loop 1 adversarial-L1-active-uris-no-lock-toctou), fork-and-forget child processes, atexit/SIGTERM handlers that need to discover live handles, multi-interpreter embedding. Each of these reaches the locked-spec layer; today none of them have a spec to anchor against.

**References:** `README.md 'Locked decisions' #5`, `src/moneta/api.py:_ACTIVE_URIS`, `DEEP_THINK_BRIEF_substrate_handle.md`, `tests/test_twin_substrate_adversarial.py`

---

### `adversarial-L2-hydrate-inversion-spec-surprise-confirmed` — High — PRIOR FINDING architect-L2-vector-authoritative-vs-hydrate-inversion is correctly classified as §9 candidate. Reinforce: ARCHITECTURE.md §7's 'vector index is authoritative for what exists' is the keystone of the no-2PC atomicity argument — if vector is authoritative, an interrupted deposit (ecs.add succeeded, vector.upsert raised) leaves a benign 'doesn't exist' state. The hydrate path silently inverts this: ECS snapshot becomes the source of truth, vector is reconstructed from it. A deposit that raised mid-construction in the prior session re-emerges in the new session via ECS hydrate, vector then receives it via the rebuild loop. The atomicity argument's load-bearing assumption — vector wins — is broken across restart.

**Role:** adversarial  **File:** `src/moneta/api.py:186-211`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
self.ecs, wal_replay = self.durability.hydrate()
                # Rebuild vector index from hydrated ECS (shadow rebuild).
                for memory in self.ecs.iter_rows():
                    self.vector_index.upsert(
                        memory.entity_id,
                        memory.semantic_vector,
                        memory.state,
                    )
```

**Proposed change:** This is genuinely §9 Trigger 2 (spec-level surprise). The §7 atomicity argument depends on vector authoritativeness; hydrate violates it; the violation is invisible. Architect should draft a §9 brief covering: (a) is vector-side persistence (vector_index.snapshot/restore wired through DurabilityManager) the correct fix? (b) Or should §7 be amended to acknowledge a 'restart inversion' clause stating ECS snapshot is authoritative on hydrate and authoritativeness flips back to vector on first deposit? Path (a) honors the locked invariant; path (b) documents the inversion as accepted. Both are spec-level decisions, not local fixes.

**Risk if wrong:** If the hydrate inversion is ACTUALLY benign (no real data scenario produces an ECS row whose vector record was never committed), the §9 escalation is over-aggressive. Today the only path that creates this divergence is a kill-9 between ecs.add and vector.upsert in deposit (Phase 1 deposit ordering is ECS-first per substrate-L2-deposit-no-rollback-on-vector-failure). Probability is low; consequence is silent inconsistency that survives restart.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §11`, `MONETA.md §9 Trigger 2`, `architect-L2-vector-authoritative-vs-hydrate-inversion`

---

### `architect-L3-quota-override-bypasses-section10-cap` — High — ARCHITECTURE.md §10 declares 'Hard cap: 100 protected entries per agent' as a locked invariant, but `MonetaConfig.quota_override: int = 100` is unbounded — any caller can construct `MonetaConfig(quota_override=10_000_000)` and the §10 cap is silently bypassed; the v1.1.0 surgery converted the singleton-era `PROTECTED_QUOTA = 100` constant into a per-handle override without an accompanying §9 escalation to amend §10's 'hard cap' language.

**Role:** architect  **File:** `src/moneta/api.py:104-120`  **§9:** yes  **Conflicts with locked decision:** yes

**Evidence:**

```
    storage_uri: str
    quota_override: int = 100

    # Preserved from singleton-era config (semantics unchanged).
    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS
```

**Proposed change:** Architect drafts a §9 Trigger 2 brief: either (a) clamp quota_override at construction time (`if quota_override > 100: raise ValueError`), preserving §10's locked text; or (b) amend ARCHITECTURE.md §10 to read 'Default cap: 100 protected entries per agent; per-handle override is permitted via MonetaConfig.quota_override but values exceeding 100 are an explicit operator override of the §10 backstop — log at WARNING level and document on the config field that the spec's intent is a backstop against agent abuse, not a hard ceiling on operator-side capacity planning.' Path (a) preserves the locked spec; path (b) honors the v1.1.0 design while documenting the loosening. Today the spec says one thing and the code does another.

**Risk if wrong:** If the v1.1.0 DEEP_THINK_BRIEF authorized the loosening explicitly (the brief is referenced from README but the relevant section is not in this snapshot), then the spec amendment was already approved and the only gap is that ARCHITECTURE.md §10 was never updated. That is still a real architect finding (Documentarian + Architect responsibility per Constitution §16). If the brief did not authorize unbounded override, the implementation broke the locked cap silently.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `DEEP_THINK_BRIEF_substrate_handle.md §5.3`, `MONETA.md §9 Trigger 2`

---

## Critical findings (open)

### `architect-L1-four-op-signatures-drift` — Critical — ARCHITECTURE.md §2 specifies the four-op API as module-level callables with self-less signatures, but src/moneta/api.py implements them as bound methods on a `Moneta` class; the §16 conformance check ('api.py must export exactly these four callables with exactly these signatures') cannot pass against the current code.

**Role:** architect  **File:** `ARCHITECTURE.md:27-42`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
```python
def deposit(payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID
def query(embedding: List[float], limit: int = 5) -> List[Memory]
def signal_attention(weights: Dict[UUID, float]) -> None
def get_consolidation_manifest() -> List[Memory]
```

Agents have zero knowledge of ECS, USD, vector indices, decay, or consolidation. All internals are implementation concerns.

**Conformance:** `src/moneta/api.py` must export exactly these four callables with exactly these signatures.
```

**Proposed change:** Update ARCHITECTURE.md §2 to express the four-op API as instance methods on `Moneta` (signatures `def deposit(self, payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID`, etc.), and update §16 conformance to check class-method signatures. Cite the v1.1.0 surgery decision (DEEP_THINK_BRIEF_substrate_handle.md / SURGERY_complete.md referenced in README) as the lineage. Without this update, the locked spec's literal conformance check is impossible to satisfy.

**Risk if wrong:** If the spec is correct as written and the implementation is wrong, then v1.1.0 silently violated a locked decision (Constitution §1 round closure). If the implementation is correct (per the cited Deep Think round), the spec is stale and any future engineer reading ARCHITECTURE.md alone will rebuild the wrong surface.

**References:** `ARCHITECTURE.md §2`, `ARCHITECTURE.md §16`, `MONETA.md §2.1`, `CLAUDE.md 'Locked decisions'`

---

### `test-L1-vector-index-dim-homogeneity-untested` — Critical — ARCHITECTURE.md §7.1 locks the shadow vector index dim-homogeneity invariant ('the vector index rejects dim-mismatched upserts') but no unit test file exists for vector_index.py; the test directory has test_ecs.py, test_decay.py, test_attention_log.py, test_api.py, test_usd_target.py but no test_vector_index.py, leaving the ValueError-on-mismatch contract unverified.

**Role:** test  **File:** `tests/integration/test_durability_roundtrip.py:1-30`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
from moneta import Moneta, MonetaConfig
from moneta.types import EntityState
```

**Proposed change:** Create tests/unit/test_vector_index.py with at minimum: (a) test that first upsert sets the dim, (b) test that second upsert with mismatched dim raises ValueError (NOT a silent skip), (c) test that delete and update_state on missing entity_id are idempotent no-ops per docstring, (d) test that fresh VectorIndex with embedding_dim=None defers dim-locking until first upsert.

**Risk if wrong:** If wrong: vector_index.py:upsert already raises ValueError on dim mismatch, and tests at the integration layer (e.g., deposit + query) may incidentally cover the contract — but no test exercises the failure path explicitly, so a refactor that downgrades the error to a warning or skip would land green.

**References:** `ARCHITECTURE.md §7.1`

---

### `documentarian-L1-api-md-singleton-references` — Critical — docs/api.md 'Setup' section instructs callers to invoke moneta.init(), which does not exist after the v1.1.0 singleton surgery; the actual API is the Moneta(config) handle.

**Role:** documentarian  **File:** `docs/api.md:21-36`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
Every Moneta process must call `init()` once before any agent operation:

```python
import moneta
moneta.init()                         # defaults (in-memory, 6h half-life)
moneta.init(half_life_seconds=60)     # minutes-scale half-life
```

**Proposed change:** Rewrite the Setup section around `with Moneta(MonetaConfig.ephemeral()) as m:` and explicit MonetaConfig(storage_uri=...) construction. Reference the README v1.1.0 section as the surgery record. Remove every reference to moneta.init().

**Risk if wrong:** If docs/api.md is in fact out of role for Documentarian (e.g., implicitly transferred to architect when ARCHITECTURE.md was locked), the finding is misclassified — but Constitution §11 explicitly assigns docs/** to documentarian.

**References:** `CLAUDE.md 'Do not let documentation lag implementation by more than one PR'`, `README.md v1.1.0 surgery section`, `src/moneta/api.py Moneta class`

---

### `usd-L2-flush-partial-failure-breaks-sequential-write-atomicity` — Critical — UsdTarget.flush() saves N layers in a bare for-loop with no error handling; if any layer.Save() raises (disk full, fsync timeout, permission, network FS hiccup), prior layers are durable, later layers are not, and the SequentialWriter — which calls flush() and then proceeds to update_state on every entity — commits the vector index to CONSOLIDATED for entities whose USD prims never reached disk, breaking ARCHITECTURE.md §7's invariant that 'the vector index is authoritative for what exists.'

**Role:** usd  **File:** `src/moneta/usd_target.py:297-310`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def flush(self) -> None:
        """Save all dirty layers to disk. Primary durability path.

        Called by ``SequentialWriter`` after ``author_stage_batch``
        returns and before the vector index is committed, preserving
        ARCHITECTURE.md §7 sequential-write ordering: ChangeBlock
        (in author_stage_batch) → Save (here) → vector commit (after).

        Since Pass 6, ``author_stage_batch`` no longer calls Save()
        itself — this method is the sole Save call site, enabling the
        narrow-lock pattern verified in Pass 5.
        """
        if not self._in_memory:
            for layer in self._layers.values():
                layer.Save()
            self._root_layer.Save()
```

**Proposed change:** Wrap the loop in a try/except that, on partial failure, (a) records which layers succeeded and which did not, (b) re-raises a structured exception carrying the per-layer status so the SequentialWriter can refuse to proceed to the vector update for entities whose target layer failed to save, OR (c) at minimum logs the partial-flush state at ERROR level so the §7 invariant violation is observable. The §7 'orphan' case (USD durable, vector not) is benign by spec; the reverse case (vector says exists, USD did not save) is what flush() partial failure produces, and §7 does not authorize it.

**Risk if wrong:** If layer.Save() never partial-fails in practice on the target deployment hardware, the bug is latent. Modern fsync semantics on local disk make this rare. But network-mounted FS, full-disk conditions during a long consolidation batch, or any future S3/`moneta://` storage_uri scheme makes partial Save failure realistic — and the §7 atomicity protocol is then silently violated with no detection path.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §15.6`

---

### `substrate-L2-protected-quota-count-then-add-toctou` — Critical — Moneta.deposit performs a check-then-act on the protected quota: `count_protected() >= quota_override` is computed, then `ecs.add` runs unconditionally if the check passes; under concurrent protected deposits two callers can both observe count=99 and both succeed, ending at count=101. The §10 backstop ('hard cap of 100 protected entries per agent') is bypassed without raising — the constitution explicitly flags this as 'quota race on count_protected.'

**Role:** substrate  **File:** `src/moneta/api.py:263-282`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if (
            protected_floor > 0.0
            and self.ecs.count_protected() >= self.config.quota_override
        ):
            raise ProtectedQuotaExceededError(
                f"protected quota of {self.config.quota_override} "
                f"exceeded; Phase 3 unpin tool required "
                f"(ARCHITECTURE.md §10)"
            )

        entity_id = uuid4()
        now = time.time()

        self.ecs.add(
            entity_id=entity_id,
            payload=payload,
            embedding=embedding,
            utility=1.0,
            protected_floor=protected_floor,
            state=EntityState.VOLATILE,
            now=now,
        )
```

**Proposed change:** Either (a) document explicitly that Moneta.deposit is single-writer and add a deposit-side runtime guard (e.g., a per-handle `threading.Lock` acquired around the count-then-add critical section, mirroring the eventual approach for `_ACTIVE_URIS`); or (b) push quota enforcement into ECS.add itself as an atomic 'add-if-quota-ok' operation that consults count_protected under a shared lock with the row mutation. Path (a) preserves the §3 single-writer comment but enforces it locally; path (b) makes the §10 invariant inviolable regardless of the consumer's threading model. Either way, document the choice and add a stress test analogous to tests/test_twin_substrate_adversarial.py::test_concurrent_construction_yields_at_most_one_handle that fires N concurrent protected deposits at quota-1 and asserts exactly one succeeds.

**Risk if wrong:** Existing tests (TestProtectedQuota in tests/unit/test_api.py) verify the cap serially and would not detect this race. The race is reachable any time an agent issues protected deposits from multiple threads (a likely pattern for a multi-tool agent issuing parallel tool calls). The §10 wording is 'hard cap' — the implementation provides a soft cap under concurrency.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `Constitution §10 Loop 3 theme bullet 'quota race on count_protected'`

---

### `consolidation-L2-stage-partial-batch-atomicity-break` — Critical — ConsolidationRunner.run_pass commits staged entities in batches via sequential_writer.commit_staging but defers the ECS state transition to CONSOLIDATED to a separate post-batch loop; if any batch raises, all stage_ids — including those whose USD+vector commits already succeeded — remain in STAGED_FOR_SYNC permanently because classify() only re-considers VOLATILE entities, breaking the §7 atomicity protocol's recoverability invariant.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:156-170`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
if stage_ids and sequential_writer is not None:
            staged_memories: List[Memory] = []
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.STAGED_FOR_SYNC)
                memory = ecs.get_memory(eid)
                if memory is not None:
                    staged_memories.append(memory)
            for batch_start in range(0, len(staged_memories), MAX_BATCH_SIZE):
                batch = staged_memories[batch_start : batch_start + MAX_BATCH_SIZE]
                result = sequential_writer.commit_staging(batch)
                authoring_at = result.authored_at
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.CONSOLIDATED)
```

**Proposed change:** Hoist the CONSOLIDATED transition INSIDE the batch loop, immediately after each successful commit_staging: `for memory in batch: ecs.set_state(memory.entity_id, EntityState.CONSOLIDATED)`. This way, a failure on batch N+1 leaves batches 0..N in CONSOLIDATED state (matching reality on disk and in vector index) and only batch N+1's entities remain in STAGED_FOR_SYNC. Add an integration test that injects a commit_staging failure mid-multi-batch and asserts: (a) successful batches are CONSOLIDATED in ECS, (b) failed batch entities are STAGED_FOR_SYNC, (c) get_consolidation_manifest reflects only the truly-pending set.

**Risk if wrong:** If commit_staging is in fact transactionally all-or-nothing (which it is not — each batch is an independent USD save + vector update per §7), the proposed change would be a no-op. But the multi-batch loop creates N independent §7 sequential-write events, each of which can succeed or fail independently. The current code treats them as a single atomic unit, which they are not.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §15.2 #3`, `src/moneta/sequential_writer.py:commit_staging`

---

### `test-L2-attention-log-no-thread-stress` — Critical — ARCHITECTURE.md §5.1 locks 'append-only attention log, reduced at sleep pass' as the concurrency primitive, but the test suite verifies the lock-free property only structurally (an AST scan for `threading.Lock` imports) — no test exercises concurrent appends against a `drain()` to confirm the invariant 'a concurrent append either lands in the old list (and is drained this window) or in the new list (and is drained next window)' and that no entries are lost across the swap.

**Role:** test  **File:** `tests/unit/test_attention_log.py:123-158`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
class TestLockFreeDiscipline:
    def test_no_threading_lock_imports_in_attention_log(self) -> None:
        """The concurrency primitive is an append-only log (ARCHITECTURE §5.1).

        The module must not import `threading.Lock` or `threading.RLock`.
        This is a structural invariant — if it breaks, it is a §9 Trigger 2
        (spec-level surprise), not a local fix.
        """
```

**Proposed change:** Add a multithread stress test in tests/unit/test_attention_log.py: spawn N=8 producer threads each appending K=10000 entries with deterministic entity_ids, plus one consumer thread that drains repeatedly; after producers join, drain remaining entries and assert (a) total observed entries equals N*K (no entries lost across drain boundaries), (b) per-entity weight sums match the expected aggregation, (c) every drained entry is unique. Run for ~1 second under `sys.setswitchinterval(0.0001)` to maximize GIL switch pressure between the `STORE_ATTR` of the swap and concurrent `list.append` on the old buffer reference.

**Risk if wrong:** If the test is too lenient or the swap+append pattern is not in fact lock-free under CPython 3.11/3.12, it will surface as flaky failures rather than a deterministic bug — but flakes signal a real race. The current AST scan proves the source code does not lock; it does not prove the algorithm is correct. The locked §5.1 invariant has zero empirical coverage.

**References:** `ARCHITECTURE.md §5.1`, `MONETA.md §2.5`, `src/moneta/attention_log.py module docstring`

---

### `test-L2-consolidation-partial-batch-commit-untested` — Critical — ConsolidationRunner.run_pass commits staged memories in a per-batch loop (consolidation.py:163-168) and only transitions ECS state to CONSOLIDATED *after* the loop exits; if `commit_staging` raises mid-loop (e.g., on batch 2 of 3 due to USD disk full or vector-index failure), the first successfully-authored batch is durable on disk but the ECS still believes those entities are STAGED_FOR_SYNC. No integration test exercises a mid-batch commit failure, so this atomicity break against ARCHITECTURE.md §7 is silently uncovered.

**Role:** test  **File:** `tests/integration/test_sequential_writer_ordering.py:108-130`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_vector_failure_does_not_rollback_authoring(self) -> None:
        """§7: 'USD orphans from interrupted writes are benign.'

        The sequential writer must NOT attempt to undo the authoring
        write when the vector index fails. The orphan is the protocol.
        """
        target = MockUsdTarget(log_path=None)
        vec = _FailingVector()
        writer = SequentialWriter(target, vec)

        mem = _make_memory()

        with pytest.raises(RuntimeError, match="simulated"):
            writer.commit_staging([mem])
```

**Proposed change:** Add a test in tests/integration/test_end_to_end_flow.py that (a) deposits >MAX_BATCH_SIZE staged candidates, (b) injects an authoring-target wrapper that raises on the second `author_stage_batch` call only, (c) calls run_sleep_pass and asserts it propagates the failure, (d) inspects ECS state and asserts no stuck-STAGED entities remain inconsistently — i.e., decide and lock down whether ECS rolls back to VOLATILE on partial failure or whether successfully-committed batches advance to CONSOLIDATED while failed batches stay STAGED. Either contract is defensible; today the contract is undefined and untested.

**Risk if wrong:** The current TestVectorFailure proves single-batch commit_staging behavior at the unit level. It does not prove the consolidation-loop-around-commit_staging behavior. A real partial-batch failure in production would leave the substrate in a state where get_consolidation_manifest reports stale STAGED entries that USD already holds — confusing the operator and risking double-authoring on the next sleep pass.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §15.2 #3`, `src/moneta/consolidation.py:155-170`

---

### `adversarial-L2-attention-log-loss-not-section9` — Critical — PRIOR FINDING substrate-L2-attention-log-drain-stale-buffer-race IS REAL but its §9 escalation framing is NOT VALID: ARCHITECTURE.md §5.1's locked text says 'lock-free, eventually consistent, and has the simplest failure mode' — eventual-consistency explicitly permits the loss window the race exposes. The 'Entries cannot be lost' wording is the IMPLEMENTATION'S module docstring overpromise, not a spec contract. The fix is a Critical implementation correction (and docstring softening) on the substrate side; raising it to §9 misroutes a real bug into a spec-level escalation queue and risks reopening Round 2's locked concurrency primitive.

**Role:** adversarial  **File:** `src/moneta/attention_log.py:22-58`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `substrate-L2-attention-log-drain-stale-buffer-race`

**Evidence:**

```
**Append-only attention log, reduced at sleep pass.** Not per-entity spinlocks. Not CAS loops. The log is lock-free, eventually consistent, and has the simplest failure mode. The sleep pass reads the log, applies reductions to the ECS, then clears the log.
```

**Proposed change:** Treat as Critical implementation finding owned by Substrate. Two acceptable resolutions inside the locked spec: (a) replace the swap-and-drain pattern with a `collections.deque` plus a single bounded-scope `Lock` whose only critical section is `popleft`/`append` — this is NOT a per-entity spinlock and NOT a CAS loop, so it does not violate §5.1's locked invariants; or (b) keep the list+swap and update the module docstring to read 'best-effort delivery; signals racing the swap window may land in the drained buffer and be lost on the order of the GIL switch interval — the at-least-once delivery is upgraded to at-most-once-loss-per-swap, consistent with §5.1 eventual consistency.' Path (a) is the correctness fix; path (b) honestly documents the race. Neither requires §9.

**Risk if wrong:** If §5.1 is read maximally — 'eventually consistent' meaning 'lossless after sleep-pass' rather than 'lossless modulo eventual delivery' — then the loss window IS a spec-level surprise and §9 is correct. The phrase is ambiguous in the locked text. Routing it as a Critical implementation finding rather than §9 trades 'maybe overreact' for 'definitely fix it'; if Architect later determines §9 escalation was correct, the Critical fix landing meanwhile does no harm.

**References:** `ARCHITECTURE.md §5.1`, `MONETA.md §2.5`, `src/moneta/attention_log.py module docstring`

---

### `architect-L3-protected-consolidation-contradiction` — Critical — MONETA.md §2.5 declares protected entities consolidate to `cortex_protected.usda` (a routing destination, not an exemption), but ARCHITECTURE.md §6 selection criteria require `Utility < 0.3` to stage — and the protected-floor clamp pins utility at the floor for any entity with `protected_floor ≥ 0.3`, mathematically guaranteeing those entities NEVER stage; phase3-closure.md §4 acknowledges this as a 'known limitation' but the contradiction between MONETA.md §2.5 and ARCHITECTURE.md §6 is unresolved at the spec layer.

**Role:** architect  **File:** `ARCHITECTURE.md:114-142`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
**Trigger conditions:**

- ECS volatile count exceeds `MAX_ENTITIES`, **or**
- Inference queue idle > 5000 ms.

**Selection criteria:**

- `Utility < 0.1 AND AttendedCount < 3` → **prune** (delete entirely).
- `Utility < 0.3 AND AttendedCount >= 3` → **stage for USD authoring**.
```

**Proposed change:** Architect drafts a §9 Trigger 2 brief reconciling MONETA.md §2.5 ('Protected entities... consolidate to a dedicated cortex_protected.usda layer pinned permanently to the strongest position') against ARCHITECTURE.md §6 selection criteria. Two viable resolutions: (a) extend §6 with a parallel selection rule for protected entities (e.g., `protected_floor > 0 AND AttendedCount >= 3 AND time_since_deposit > T` triggers protected-sublayer authoring without requiring utility decay), or (b) amend MONETA.md §2.5 to acknowledge protected entities are exempt from periodic consolidation by spec design and that `cortex_protected.usda` is hydrated only via explicit operator action (the unpin tool inverse). Either resolution is fine; the current state — three locked artifacts that mutually contradict — is not.

**Risk if wrong:** If the contradiction is somehow benign (e.g., MONETA.md §2.5's 'consolidate to' is read as 'WHEN they consolidate, they go to'), then the current behavior matches an alternative interpretation and the finding is documentation-only. But docs/phase3-closure.md §4 explicitly names the gap as a 'limitation' and a 'v1.1 task', which is incompatible with the benign reading. The locked spec layer needs to settle which reading governs.

**References:** `MONETA.md §2.5`, `ARCHITECTURE.md §6`, `docs/phase3-closure.md §4`, `MONETA.md §9 Trigger 2`

---

### `consolidation-L3-protected-floor-stage-trap` — Critical — Protected memories with protected_floor >= 0.3 NEVER stage and NEVER prune — they remain VOLATILE for the lifetime of the substrate, directly contradicting MONETA.md §2.5's promise that 'protected entities consolidate to a dedicated cortex_protected.usda layer'; the locked Round 2 selection criteria (utility < 0.3 AND attended_count >= 3) cannot fire because decay clamps utility at floor, so utility < 0.3 is unreachable when floor >= 0.3.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:114-135`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
if (
                memory.utility < PRUNE_UTILITY_THRESHOLD
                and memory.attended_count < PRUNE_ATTENDED_THRESHOLD
            ):
                prune_ids.append(memory.entity_id)
            elif (
                memory.utility < STAGE_UTILITY_THRESHOLD
                and memory.attended_count >= STAGE_ATTENDED_THRESHOLD
            ):
                stage_ids.append(memory.entity_id)
```

**Proposed change:** This is a §9 Trigger 2 candidate: MONETA.md §2.5 mandates protected-memory consolidation but ARCHITECTURE.md §6's locked selection criteria preclude it for any floor >= 0.3. The integration test test_protected_floor_routes_to_protected_sublayer only passes because it specifically uses floor=0.2 (below stage threshold). Architect must rule whether (a) selection adds a protected-aware clause that stages protected entities on a different trigger (e.g., age, or AttendedCount alone), or (b) §2.5's consolidation promise is amended to 'protected entities are pinned in the hot tier and never consolidate'. Path (a) extends Round 2's locked criteria; path (b) admits the spec gap. Today neither is true and the substrate silently violates §2.5.

**Risk if wrong:** If wrong, tests would have caught it. They don't because protected_floor is exercised only at floor=0.2 (a value carefully chosen to land between thresholds). Production callers using floor=1.0 (the canonical 'pin forever' value documented in README) get exactly zero consolidation activity for those entities — they never reach cortex_protected.usda, never appear in any patent-evidence demonstration of claim #4 ('Protected memory as root-pinned strong-position sublayer'), and the four substrate novelty claims silently rest on a USD authoring path the substrate cannot reach.

**References:** `MONETA.md §2.5`, `MONETA.md §2.10`, `ARCHITECTURE.md §6`, `ARCHITECTURE.md §10`, `docs/phase3-closure.md §4.1 (known limitations)`, `MONETA.md §3 claim #4`

---

### `substrate-L3-signal-attention-bypasses-protected-floor` — Critical — ECS.apply_attention computes new_u = utility + sum_weight and clamps only the upper bound (min(1.0, ...)), never the lower bound against protected_floor; a signal_attention call with a negative weight (or a batch whose summed weights are negative) drives a protected entity's utility below its floor, defeating §10 'protected memory' semantics — the entity then ranks lowest in query() until the next decay eval point restores the floor via decay_value's clamp.

**Role:** substrate  **File:** `src/moneta/ecs.py:177-188`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        for entity_id, (sum_weight, count) in agg.items():
            row = self._id_to_row.get(entity_id)
            if row is None:
                continue
            new_u = self._utility[row] + sum_weight
            self._utility[row] = 1.0 if new_u > 1.0 else new_u
            self._attended[row] += count
            self._last_evaluated[row] = now
```

**Proposed change:** Add the protected_floor clamp symmetric to the upper clamp: `clamped = max(self._protected_floor[row], min(1.0, new_u))`. The ARCHITECTURE.md §5 formula 'Utility = min(1.0, Utility + weights[UUID])' is silent on the lower bound, but §4's protected-floor invariant ('Utility never drops below ProtectedFloor') is the operational contract for §10 protected memory and must hold across BOTH decay eval points and attention writes — the current implementation makes attention the sole back door around the floor. Either clamp here or, alternatively, validate at the api.signal_attention layer that weights are non-negative and raise ValueError on negative weight (more restrictive but matches the spec wording 'reinforcement counter' from MONETA.md §2.4).

**Risk if wrong:** If the spec authors intended attention writes to be one-way reinforcement only (positive weights), then the implementation already accepts under-specified inputs and the fix is at the api.signal_attention boundary. If the spec authors intended attention to be bidirectional (negative weights as 'this was misleading, demote it'), then the floor-bypass is a real gap. Either way the current implementation's silent acceptance of negative weights without floor enforcement is wrong; the question is which of the two fixes lands.

**References:** `ARCHITECTURE.md §4`, `ARCHITECTURE.md §5`, `ARCHITECTURE.md §10`, `MONETA.md §2.4`

---

### `test-L3-vector-index-no-unit-tests` — Critical — No `tests/unit/test_vector_index.py` exists; the §7.1 locked dim-homogeneity invariant ('the vector index rejects dim-mismatched upserts ... a hard ValueError — not a silent skip'), the constructor `embedding_dim` parameter behavior, the `update_state` silent no-op on missing entity (§5.1 eventually-consistent), and the entire VectorIndex state-machine surface are exercised only transitively via deposit/query integration tests — the unit-level contract that ARCHITECTURE.md §7 calls 'authoritative for what exists' has zero direct coverage.

**Role:** test  **File:** `tests/unit/test_api.py:1-30`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
from moneta import (
    EntityState,
    Memory,
    Moneta,
    MonetaConfig,
    MonetaResourceLockedError,
    ProtectedQuotaExceededError,
)
```

**Proposed change:** Create `tests/unit/test_vector_index.py` with at minimum: (a) `test_upsert_first_vector_sets_dim_when_constructor_dim_none` — verify auto-set behavior; (b) `test_upsert_dim_mismatch_raises_value_error` — verify §7.1 hard raise (not silent skip), with both constructor-set and auto-set first dim; (c) `test_update_state_on_missing_entity_is_silent_noop` — verify §5.1 discipline, no exception, no length change; (d) `test_delete_idempotent_on_missing_entity` — verify silent no-op; (e) `test_query_with_zero_norm_query_returns_empty` — verify the q_norm==0 guard; (f) `test_query_skips_zero_norm_stored_vectors` — verify the v_norm==0 guard; (g) `test_query_k_zero_returns_empty` and `test_query_k_greater_than_n_returns_all`. Each test cites its locked-clause anchor in the docstring.

**Risk if wrong:** If the spec is read maximally — §7.1 is locked and any future change to silently-skip dim mismatches or change update_state semantics would constitute spec-level surprise — and there is no unit-level test, the next maintainer can land a 'cleanup' that converts the hard raise to a logged warning without breaking any current test. The integration tests (test_api.py::TestDepositContract) never trigger dim mismatch and would not catch the regression.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §7.1`, `src/moneta/vector_index.py`, `Constitution §10 Loop 3 theme bullet 'vector-index state machine soundness'`

---

### `test-L3-quota-count-protected-toctou-no-stress` — Critical — Constitution §10 Loop 3 theme explicitly names 'quota race on count_protected' as a probe target, but `TestProtectedQuota` only tests sequentially — no concurrent test fires N threads issuing protected deposits at quota-1 to verify exactly one (1) succeeds and N-1 raise `ProtectedQuotaExceededError`. The §10 'hard cap' invariant is therefore preserved by single-writer convention only, with no test that would catch the race that Loop 2's `substrate-L2-protected-quota-count-then-add-toctou` identifies in code.

**Role:** test  **File:** `tests/unit/test_api.py:129-160`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_protected_quota_exceeded_raises(
        self, fresh_moneta: Moneta
    ) -> None:
        for i in range(fresh_moneta.config.quota_override):
            fresh_moneta.deposit(
                f"p{i}", [float(i), 1.0], protected_floor=0.1
            )
        with pytest.raises(ProtectedQuotaExceededError):
            fresh_moneta.deposit(
                "overflow", [1.0, 1.0], protected_floor=0.1
            )
```

**Proposed change:** Add `TestProtectedQuotaConcurrent` mirroring the structure of `tests/test_twin_substrate_adversarial.py::test_concurrent_construction_yields_at_most_one_handle`: pre-fill the handle to `quota_override - 1` protected deposits, then barrier-sync N=16 threads each attempting one protected deposit, repeated for ~30 iterations under `sys.setswitchinterval(1e-6)` plus a CPU-bound noise thread. Assert (a) exactly one (1) thread's deposit returns a UUID, (b) the remaining N-1 raise `ProtectedQuotaExceededError`, (c) `count_protected()` returns `quota_override` after each iteration. Mark `@pytest.mark.load` if the iteration count makes it slow.

**Risk if wrong:** Loop 2 identified the implementation race at Critical severity but no test covers it. Without the stress test, fixing the implementation race is unverifiable — a 'fix' that reduces the window without closing it would land green. The race fires any time a multi-tool agent issues parallel protected deposits (a likely real workload). Single-writer convention is documented in `ecs.py` only, not in `api.py`, and the v1.1.0 README's multi-instance language invites consumers to assume per-handle thread safety.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `Constitution §10 Loop 3 theme bullet 'quota race on count_protected'`, `substrate-L2-protected-quota-count-then-add-toctou`

---

### `test-L5-docs-api-md-references-deleted-init-function` — Critical — docs/api.md is the user-facing four-op API reference and prominently documents `moneta.init()` and `moneta.run_sleep_pass()` as module-level free functions: 'Every Moneta process must call init() once before any agent operation' with three explicit code examples. The v1.1.0 singleton surgery (per CLAUDE.md and README) removed module-level singletons entirely — `moneta.init()` does not exist; the API is `Moneta(config)` handle. docs/api.md is hopelessly stale and would actively misdirect any new consumer reading it as the canonical API reference.

**Role:** documentarian  **File:** `docs/api.md:10-36`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
## Setup

Every Moneta process must call `init()` once before any agent operation:

```python
import moneta
moneta.init()                         # defaults (in-memory, 6h half-life)
moneta.init(half_life_seconds=60)     # minutes-scale half-life
moneta.init(config=moneta.MonetaConfig(
    half_life_seconds=3600,
    snapshot_path="/var/moneta/ecs.json",
```

**Proposed change:** Rewrite docs/api.md against the v1.1.0+ handle API: replace the entire 'Setup' section with `Moneta(config)` construction examples, replace every `moneta.deposit(...)` / `moneta.query(...)` / `moneta.signal_attention(...)` / `moneta.get_consolidation_manifest(...)` call with `m.deposit(...)` etc. against a `with Moneta(MonetaConfig.ephemeral()) as m:` pattern. Update the 'Memory type' section's `signal_attention(weights)` to a method call. Add a v1.2.0-rc1 section documenting that consolidated memories now ship as typed `MonetaMemory` prims with USD camelCase attribute names. The README has the correct examples; docs/api.md must be brought into alignment. CLAUDE.md hard rule: doc lag ≤1 PR; this lag is two surgeries (v1.1.0 + v1.2.0-rc1).

**Risk if wrong:** A new consumer following docs/api.md verbatim hits `AttributeError: module 'moneta' has no attribute 'init'` on the very first line — the doc is operationally broken. The 'Errors' section even references `MonetaNotInitializedError`, which does not exist post-singleton-surgery. This is the canonical API reference cited in CLAUDE.md ('Documentarian owns docs/api.md'); its correctness is structural, not stylistic. CLAUDE.md hard rule explicitly forbids this lag; the doc is a Critical correctness defect against the locked four-op surface.

**References:** `docs/api.md`, `src/moneta/__init__.py`, `src/moneta/api.py:Moneta`, `CLAUDE.md hard rules`, `README.md`

---

### `documentarian-L5-api-md-pre-v110-singleton-everywhere` — Critical — docs/api.md is the canonical four-op API reference and describes the pre-v1.1.0 module-singleton API verbatim — every example uses `moneta.init()`, module-level `moneta.deposit(...)`/`moneta.query(...)`/`moneta.signal_attention(...)`, and the 'Setup' section opens with `moneta.init()` followed by 'Calling init() a second time resets all substrate state'; the v1.1.0 singleton surgery deleted `init()`, deleted the module-level functions, and converted them into methods on the `Moneta(config)` handle, but docs/api.md has not been touched. The doc is now structurally wrong end-to-end and will mis-teach every consumer following it.

**Role:** documentarian  **File:** `docs/api.md:10-270`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
## Setup

Every Moneta process must call `init()` once before any agent operation:

```python
import moneta
moneta.init()                         # defaults (in-memory, 6h half-life)
moneta.init(half_life_seconds=60)     # minutes-scale half-life
moneta.init(config=moneta.MonetaConfig(
    half_life_seconds=3600,
    snapshot_path="/var/moneta/ecs.json",
    wal_path="/var/moneta/wal.jsonl",
    mock_target_log_path="/var/moneta/usd_authorings.jsonl",
))
```

Calling `init()` a second time resets all substrate state.
```

**Proposed change:** Full rewrite of docs/api.md to match the v1.1.0+ handle pattern: replace the 'Setup' section with construction via `with Moneta(MonetaConfig.ephemeral()) as m:` (the README pattern), convert each of the four op subsections so the example reads `m.deposit(...)` instead of `moneta.deposit(...)`, drop the 'Calling init() a second time resets state' wording entirely (the handle's __init__ + close() lifecycle is the new contract — replace with two-handle-same-URI raises MonetaResourceLockedError per §5.4 of DEEP_THINK_BRIEF_substrate_handle.md), drop MonetaNotInitializedError from the 'Errors' section (the type no longer exists; the 'no-arg trap' (Moneta() raises TypeError per §5.3) is the new error surface), and update the durability-config example to pass paths through MonetaConfig rather than init(). Anchor the doc with a 'Status: as of v1.2.0-rc1' header so future drift is visible. The README already carries the correct shape; api.md is the longer-form companion that needs to mirror it.

**Risk if wrong:** If wrong (the doc is intentionally retained as Phase 1 historical reference), then the 'Source of truth' framing in CLAUDE.md '#3 docs/api.md' is misleading because it points readers at a stale snapshot. But CLAUDE.md role table puts api.md squarely under Documentarian's ownership for keeping in sync with implementation; this is the load-bearing example reference for the four-op surface, and it has been stale across two surgeries (v1.1.0 + v1.2.0-rc1). The Documentarian contract per CLAUDE.md hard rules is '≤1 PR doc lag'; this drift is at least two PRs deep, structurally violating the contract.

**References:** `CLAUDE.md 'Source of truth' #3`, `CLAUDE.md 'Hard rules' (≤1 PR doc lag)`, `DEEP_THINK_BRIEF_substrate_handle.md §5.1 §5.3 §5.4`, `README.md 'Quick start' + 'The four-op API'`

---

### `adversarial-L5-api-md-three-findings-collapse` — Critical — Three Loop 5 findings target docs/api.md as Critical/High drift: test-L5-docs-api-md-references-deleted-init-function (Critical), documentarian-L5-api-md-pre-v110-singleton-everywhere (Critical), test-L5-docs-api-md-singleton-error-references (High), plus documentarian-L5-api-md-monetanotinitializederror-dead-class (Medium) and documentarian-L5-api-md-no-version-stamp (Low). Five findings, one file. Synthesis must collapse into a single api.md rewrite pass — piecemeal patches risk landing partially (e.g., updating Setup section but leaving Errors section stale, then a sixth finding fires next loop on the residual gap).

**Role:** adversarial  **File:** `docs/api.md:1-270`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
Every Moneta process must call `init()` once before any agent operation:

```python
import moneta
moneta.init()                         # defaults (in-memory, 6h half-life)
```

**Proposed change:** Single Documentarian surgery: rewrite docs/api.md end-to-end against the v1.1.0+ handle pattern. (a) Replace 'Setup' section with `with Moneta(MonetaConfig.ephemeral()) as m:` examples; (b) every operation example uses `m.deposit(...)` / `m.query(...)` / `m.signal_attention(...)` / `m.get_consolidation_manifest(...)` instead of module-level dispatch; (c) replace MonetaNotInitializedError in Errors section with TypeError (no-arg trap) + MonetaResourceLockedError (URI collision); (d) update durability section to acknowledge that start_background is opt-in (handle's __init__ does not auto-start); (e) add a top-of-doc 'Status: as of v1.2.0-rc1' anchor; (f) add v1.2.0-rc1 schema note for typed MonetaMemory prims as the on-disk shape consumed memories take. The five findings collapse into one ~150-line rewrite. Do not split into five PRs — partial patches multiply the inconsistency surface.

**Risk if wrong:** If wrong (a piecemeal patch order is preferred for review surface), the rewrite is too large for a single PR. Mitigation: stage the rewrite as one file, one PR, with each section's diff individually reviewable. The current state is operationally Critical because every code example in the doc is broken — a consumer following docs/api.md verbatim hits AttributeError on the first line.

**References:** `test-L5-docs-api-md-references-deleted-init-function`, `documentarian-L5-api-md-pre-v110-singleton-everywhere`, `test-L5-docs-api-md-singleton-error-references`, `documentarian-L5-api-md-monetanotinitializederror-dead-class`, `documentarian-L5-api-md-no-version-stamp`

---

## High findings (open)

### `adversarial-L1-multi-handle-protected-quota-aggregation` — High — ARCHITECTURE.md §10 declares 'Hard cap: 100 protected entries per agent', but the v1.1.0 multi-instance handle pattern lets a single agent process construct N Moneta handles on N storage_uris and pin 100×N protected entries. The §10 backstop ('agents will try to flag everything as protected') is a per-process safety property the spec authorizes, but the implementation enforces only per-handle caps.

**Role:** adversarial  **File:** `src/moneta/api.py:264-274`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
if (
            protected_floor > 0.0
            and self.ecs.count_protected() >= self.config.quota_override
        ):
            raise ProtectedQuotaExceededError(
                f"protected quota of {self.config.quota_override} "
```

**Proposed change:** Decide explicitly: (a) §10 is reinterpreted as 'per substrate handle' to match the v1.1.0 multi-tenant model — update ARCHITECTURE.md §10 + MONETA.md §2.10 accordingly, citing DEEP_THINK_BRIEF_substrate_handle.md as lineage; or (b) add a process-level protected counter alongside `_ACTIVE_URIS` that aggregates across handles and enforces 100 globally. Path (a) is consistent with multi-tenant cloud deployment and matches what the code does; path (b) preserves the literal spec but is incompatible with multi-tenant operation. Either way, the silent semantic shift from 'per agent' to 'per handle' is itself a §9 candidate.

**Risk if wrong:** If §10 'per agent' was intended as a per-process safety invariant against agent abuse, multi-instance handles silently subvert it. If §10 was always meant per-substrate, the v1.1.0 surgery should have updated the spec. Today neither is documented.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `DEEP_THINK_BRIEF_substrate_handle.md`

---

### `architect-L1-init-helper-stale` — High — ARCHITECTURE.md §2.1 names `init()`, `run_sleep_pass()`, `smoke_check()`, and `MonetaConfig` as harness-level module exports; the implementation has removed `init()` (replaced by the `Moneta(config)` constructor) and moved `run_sleep_pass` to a method on the handle, so the spec lists exports that do not exist.

**Role:** architect  **File:** `ARCHITECTURE.md:44-56`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
### 2.1 Harness-level bootstrap (not part of the agent API)

The module also exposes `init()`, `run_sleep_pass()`, `smoke_check()`, and `MonetaConfig`. **These are not part of the agent-facing four-op surface.**
```

**Proposed change:** Rewrite §2.1 to describe the actual exported surface: `Moneta` class (constructor with `MonetaConfig`, context-manager protocol, `close()`), `MonetaConfig`, `MonetaResourceLockedError`, `ProtectedQuotaExceededError`, and free-function `smoke_check`. Move `run_sleep_pass` documentation to be a method on `Moneta`. Reference Pass-2 closure 'Ruling B' as the precedent for the harness/agent split, but update the example.

**Risk if wrong:** A reader following the spec will write `moneta.init()` and get an AttributeError. docs/api.md still carries the old `moneta.init()` examples (separate Documentarian finding), but the architectural source-of-truth is wrong here too.

**References:** `ARCHITECTURE.md §2.1`, `src/moneta/__init__.py __all__`, `src/moneta/api.py`

---

### `consolidation-L1-idle-trigger-not-enforced` — High — ConsolidationRunner.should_run encodes the §15.2 #2 idle-window envelope constraint but is never invoked from any production code path — Moneta.run_sleep_pass calls run_pass unconditionally — so the 'enforced at build time' envelope constraint is documented in code but not actually enforced.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:78-89`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def should_run(self, ecs: ECS, now_ms: float) -> bool:
        """Pressure (MAX_ENTITIES) or opportunistic (idle) trigger."""
        if ecs.n >= self._max_entities:
            return True
        if self._last_activity_ms == 0.0:
            return False
        if now_ms - self._last_activity_ms >= self._idle_trigger_ms:
            return True
        return False
```

**Proposed change:** Either (a) gate Moneta.run_sleep_pass on self.consolidation.should_run(...) returning True, with an explicit 'force=True' override for harness/test fast-forward, OR (b) delete should_run entirely and document in consolidation.py that envelope enforcement (§15.2 #2 idle window) is the operator/scheduler's responsibility outside the substrate. The current middle ground — defined-but-uncalled — creates the appearance of enforcement without the substance, which is exactly the trap §8 'enforced fragilely' identifies.

**Risk if wrong:** If a future operator wires Moneta.run_sleep_pass to a fixed-cadence scheduler (cron, 1Hz tick) instead of an idle-watcher, the §15.2 #2 envelope is violated silently and the substrate offers no resistance. Phase 2 closure §3 §9 Trigger 2 escalation path is bypassed because there is no detection.

**References:** `ARCHITECTURE.md §15.2 #2`, `ARCHITECTURE.md §6`, `docs/phase2-closure.md §3`

---

### `test-L1-conformance-checklist-cache-warming-untested` — High — ARCHITECTURE.md §16 conformance checklist requires a test for §8 cache-warming ('querying a USD-sourced entity does not mutate the ECS until signal_attention fires on it'), but no such test exists in the integration suite; the cache-warming invariant from §8 has no tripwire even though Phase 3 has shipped a real USD target.

**Role:** test  **File:** `tests/integration/test_end_to_end_flow.py:1-50`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
class TestDepositQueryRoundTrip:
    def test_single_deposit_retrievable(
        self, fresh_moneta: Moneta
    ) -> None:
        eid = fresh_moneta.deposit("hello world", [1.0, 0.0, 0.0])
```

**Proposed change:** Add tests/integration/test_cache_warming.py exercising §8: (1) deposit + consolidate to USD; (2) query an embedding that hits the USD-sourced entity; (3) assert the ECS row count is unchanged and no new VOLATILE entity has been created; (4) signal_attention on the USD-sourced entity_id; (5) assert that NOW the ECS hydrates a new VOLATILE row with usd_link populated.

**Risk if wrong:** If wrong: §8 hydration may not be wired in Phase 3 yet (the spec says 'Phase 3 will narrow this to SdfPath' on usd_link); the test might need to be split into a Phase-1-stub assertion (no hydration possible) and a Phase 3 hydration assertion. But the conformance checklist is locked and unchecked items are explicit gaps.

**References:** `ARCHITECTURE.md §8`, `ARCHITECTURE.md §16 conformance checklist`

---

### `test-L1-conformance-checklist-split-brain-untested` — High — ARCHITECTURE.md §16 conformance checklist requires 'Split-brain (§9): timestamp tiebreaker is exercised in both directions' but no test verifies §9's resolution rules (ECS wins if newer than last USD consolidation, USD wins otherwise); both directions of the tiebreaker are unguarded.

**Role:** test  **File:** `tests/integration/test_end_to_end_flow.py:1-50`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
from moneta import Moneta, MonetaConfig
from moneta.types import EntityState
```

**Proposed change:** Add tests/integration/test_split_brain.py with two cases: (a) deposit -> consolidate -> deposit-newer-version-with-same-concept -> assert ECS wins; (b) deposit -> consolidate -> let the ECS row decay/prune -> reload from USD -> assert USD's CONSOLIDATED state is served. Both cases must compare timestamps explicitly to verify the tiebreaker code path runs.

**Risk if wrong:** If wrong: §9's split-brain semantics may not yet be fully implemented in Phase 3 — the spec says 'When a concept hits in both ECS and USD' which presumes USD readback; if readback is deferred to v1.1, the test should be marked xfail with a closure note rather than added to green CI.

**References:** `ARCHITECTURE.md §9`, `ARCHITECTURE.md §16 conformance checklist`

---

### `documentarian-L1-api-md-monetanotinitializederror` — High — docs/api.md 'Errors' section documents MonetaNotInitializedError, which has been removed; src/moneta/api.py explicitly states this class no longer exists.

**Role:** documentarian  **File:** `docs/api.md:180-188`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
## Errors

- `MonetaNotInitializedError` — raised when an operation is called
  before `init()`.
- `ProtectedQuotaExceededError` — raised when a protected deposit would
  exceed the 100-entry quota (ARCHITECTURE.md §10).
```

**Proposed change:** Replace MonetaNotInitializedError with MonetaResourceLockedError (raised when two handles claim the same storage_uri). Cross-reference DEEP_THINK_BRIEF_substrate_handle.md §5.4. Note that 'not initialized' is unrepresentable in handle world.

**Risk if wrong:** Low — the class genuinely does not exist; api.py module docstring states 'There is no MonetaNotInitializedError — in handle world, "not initialized" is unrepresentable.'

**References:** `src/moneta/api.py module docstring`, `src/moneta/api.py:MonetaResourceLockedError`

---

### `documentarian-L1-api-md-handle-not-documented` — High — docs/api.md presents the four operations as module-level functions (moneta.deposit(...), moneta.query(...)) but the surgery moved them onto the Moneta handle; the worked examples will raise AttributeError under the v1.2.0-rc1 module surface.

**Role:** documentarian  **File:** `docs/api.md:38-96`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
### `deposit(payload, embedding, protected_floor=0.0) -> UUID`

Deposit a new memory. Returns a newly minted `EntityID` (UUID).

```python
eid = moneta.deposit(
    payload="The user prefers concise explanations.",
    embedding=[0.12, -0.45, 0.78, ...],  # from your embedder
    protected_floor=0.0,                 # 0.0 = ephemeral, >0 = pinned
)
```

**Proposed change:** Rewrite each per-operation example to call the method on a constructed handle (e.g., `eid = m.deposit(...)` inside a `with Moneta(MonetaConfig.ephemeral()) as m:` block). Replicate the README's Quick Start pattern for consistency.

**Risk if wrong:** If users still rely on docs/api.md as the canonical reference, every code snippet they copy will fail — making this finding a usability blocker, not just a doc nit.

**References:** `src/moneta/__init__.py exports`, `README.md Quick Start`, `src/moneta/api.py:Moneta`

---

### `documentarian-L1-api-md-durability-stale` — High — docs/api.md 'Recommended durability cadence' invokes durability.start_background(ecs) at module level after init(), but durability is now per-handle (m.durability) and there is no module-level ecs in handle world.

**Role:** documentarian  **File:** `docs/api.md:156-165`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
For production usage that wants the full ~30-second guarantee, call `durability.start_background(ecs)` after `init()`. For test harnesses and unit work, explicit `run_sleep_pass()` calls drive snapshotting on demand and avoid a background thread.
```

**Proposed change:** Replace with handle-scoped guidance: 'Pass snapshot_path and wal_path on MonetaConfig; call m.durability.start_background(m.ecs) inside the with-block if a daemon snapshotter is required.' Note that close() (or context-manager exit) stops the daemon thread.

**Risk if wrong:** The `ecs` symbol referenced in the docstring is a module-level value that no longer exists; users following this guidance will hit NameError or worse if they invent a workaround.

**References:** `src/moneta/durability.py:DurabilityManager.start_background`, `src/moneta/api.py:Moneta.__init__`

---

### `documentarian-L1-api-md-monetaconfig-broken` — High — docs/api.md MonetaConfig example omits the now-required storage_uri field; the dataclass is frozen kw_only with no default for storage_uri, so the example would raise TypeError at construction.

**Role:** documentarian  **File:** `docs/api.md:27-34`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
moneta.init(config=moneta.MonetaConfig(
    half_life_seconds=3600,
    snapshot_path="/var/moneta/ecs.json",
    wal_path="/var/moneta/wal.jsonl",
    mock_target_log_path="/var/moneta/usd_authorings.jsonl",
))
```

**Proposed change:** Update the example to include storage_uri (e.g., 'moneta-prod://main') and document the in-process URI exclusivity invariant. Cross-reference MonetaConfig.ephemeral() for tests.

**Risk if wrong:** Low — verification is trivial (read MonetaConfig source). The risk is to readers, not to me.

**References:** `src/moneta/api.py:MonetaConfig (frozen, kw_only=True, storage_uri required)`

---

### `adversarial-L1-active-uris-no-lock-toctou` — High — The `_ACTIVE_URIS` exclusivity registry is a plain `set` mutated under no synchronization; the constructor's `if uri in _ACTIVE_URIS: raise; add(uri)` is a check-then-act pair that depends on CPython GIL bytecode-level atomicity to be safe against concurrent constructors. Free-threaded Python or any future C-extension that releases the GIL between the membership test and `set.add` (e.g., a customized `__hash__` on a future URI type) would let two handles enter simultaneously.

**Role:** adversarial  **File:** `src/moneta/api.py:156-170`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
if config.storage_uri in _ACTIVE_URIS:
            raise MonetaResourceLockedError(
                f"storage_uri {config.storage_uri!r} is already held by "
                f"another live Moneta handle in this process; release it "
                f"via close() or context-manager exit before reconstructing"
            )
        _ACTIVE_URIS.add(config.storage_uri)
```

**Proposed change:** Wrap the check-then-add in a module-level `threading.Lock`. The cost is one Python-level lock per construction (rare). The current `tests/test_twin_substrate_adversarial.py::test_concurrent_construction_yields_at_most_one_handle` happens to pass under CPython 3.11 GIL but does not prove the invariant holds against (a) sys.setswitchinterval(0.0001) pressure, (b) free-threaded Python, (c) future Python versions whose bytecode for `in` and `add` may differ.

**Risk if wrong:** If wrong, the existing Crucible adversarial test would have failed during the v1.1.0 surgery — but that test is run under CPython 3.11 GIL, the very platform whose atomicity it is meant to verify. The §5.4 invariant is preserved by accident of platform, not by construction.

**References:** `src/moneta/api.py:_ACTIVE_URIS`, `DEEP_THINK_BRIEF_substrate_handle.md §5.4`, `tests/test_twin_substrate_adversarial.py`

---

### `adversarial-L1-close-partial-failure-leaks-authoring-target` — High — `Moneta.close` sets `self._closed = True` BEFORE the try-block; if `self.durability.close()` raises, the URI lock is released (good) but `self.authoring_target.close()` is never reached, leaving the real-USD `Sdf.Layer` cache holding native references. A subsequent call to `close()` returns early via the `_closed` guard, so the authoring target is never reclaimed for the lifetime of the process.

**Role:** adversarial  **File:** `src/moneta/api.py:222-244`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
def close(self) -> None:
        """Release native resources and the URI lock. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            if self.durability is not None:
                self.durability.close()
            if hasattr(self.authoring_target, "close"):
                self.authoring_target.close()
        finally:
            _ACTIVE_URIS.discard(self.config.storage_uri)
```

**Proposed change:** Wrap each subordinate close in its own try/except (suppress and log), so a single subordinate failure does not orphan the others. Set `self._closed = True` only after every subordinate close has been attempted. Or alternatively use `contextlib.ExitStack` to guarantee LIFO close ordering with exception aggregation. This matters under v1.2.0+ because the real `UsdTarget` holds `Sdf.Layer` native pointers; an orphaned layer survives in the C++ Sdf registry, recreating the very registry-collapse hazard the v1.1.0 surgery exists to prevent — but on the *next* construction with a path that happens to match.

**Risk if wrong:** If durability.close() never fails in practice (current implementation just stops a thread), the bug is latent. But a future durability backend (e.g., LanceDB commit-on-close per §15.2 #4) that raises on commit failure would silently leak USD layers into the global Sdf registry, exposing the very C++ trap that DEEP_THINK_BRIEF_substrate_handle.md §5.2 documents.

**References:** `src/moneta/api.py:Moneta.close`, `DEEP_THINK_BRIEF_substrate_handle.md §5.2`

---

### `adversarial-L1-schema-attribute-names-stringly-typed` — High — The six MonetaMemory schema attribute names ('payload', 'utility', 'attendedCount', 'protectedFloor', 'lastEvaluated', 'priorState') are hard-coded string literals in usd_target.py and re-typed as string literals in tests/_schema_gate_subprocess.py and tests/unit/test_schema_read_branching.py. A typo in a refactor — say 'attended_count' on the writer side, 'attendedCount' on the reader — would compile, satisfy the schema-gate (which only round-trips what was written), and silently produce on-disk prims unreadable by usdview's MonetaMemory schema layout. There is no single source of truth pinning the writer to the schema's allowedTokens / attribute list.

**Role:** adversarial  **File:** `src/moneta/usd_target.py:255-270`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
_set_attr(prim_spec, "payload", Sdf.ValueTypeNames.String, m.payload)
                    _set_attr(prim_spec, "utility", Sdf.ValueTypeNames.Float, m.utility)
                    _set_attr(
                        prim_spec, "attendedCount", Sdf.ValueTypeNames.Int, m.attended_count
                    )
```

**Proposed change:** Add a unit test that loads schema/MonetaSchema.usda via Sdf.Layer.OpenAsAnonymous, extracts the 'class MonetaMemory' attribute spec list, and asserts the six attribute names + types match the writer's authored set. This makes a one-sided rename impossible to land — the test reads the schema file, not a Python constant. Companion: pin the four allowedTokens against `_STATE_TO_TOKEN.values()` ∪ {'pruned'}.

**Risk if wrong:** The existing `tests/test_schema_acceptance_gate.py` round-trips what was written and asserts type-by-type, so a coordinated rename in writer + gate would land green even though the schema/MonetaSchema.usda file is unchanged. The schema file becomes a comment, not a contract.

**References:** `schema/MonetaSchema.usda`, `src/moneta/usd_target.py`, `tests/_schema_gate_subprocess.py`

---

### `adversarial-L1-idle-trigger-off-by-one-strict-vs-inclusive` — High — ARCHITECTURE.md §15.2 #2 mandates 'consolidation runs only during inference idle windows > 5 seconds' (strict greater-than) and MONETA.md §2.6 says 'inference queue idle > 5000ms', but consolidation.py uses `>=` to decide trigger eligibility — a 5000ms idle window fires consolidation under the implementation but not under the spec.

**Role:** adversarial  **File:** `src/moneta/consolidation.py:85-90`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if self._last_activity_ms == 0.0:
            return False
        if now_ms - self._last_activity_ms >= self._idle_trigger_ms:
            return True
        return False
```

**Proposed change:** Change to `>` to match the spec literally. The Phase 2 envelope was sized against the spec wording; a 5000ms-exactly trigger is technically out-of-envelope. Companion: extend test reviewer's proposed test_idle_trigger_ms_boundary with both 4999/5000/5001ms cases to pin the strict-greater semantics.

**Risk if wrong:** Practical impact is microscopic at production timing scales — but the spec wording is precise and the implementation contradicts it. This is the kind of letter-vs-implementation drift Constitution §9 calls out: the constraint exists to prevent inference starvation; a sub-millisecond off-by-one does not violate the intent. Severity High because it is a numeric envelope discrepancy with the locked spec.

**References:** `ARCHITECTURE.md §15.2 #2`, `MONETA.md §2.6`

---

### `adversarial-L1-mock-vs-real-prior-state-divergence-sharpened` — High — Sharpens consolidation-L1-mock-prior-state-int-vs-token-drift: the divergence is not just a JSONL-vs-USD mismatch, it actively defeats the §15.7 'mock target retained for A/B validation' contract. The test test_mock_usd_target_received_schema_compliant_batch in test_end_to_end_flow.py asserts `isinstance(entry['prior_state'], int)`, locking in the wrong shape. A future engineer reading that test believes the mock is correct.

**Role:** adversarial  **File:** `src/moneta/mock_usd_target.py:99-110`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `consolidation-L1-mock-prior-state-int-vs-token-drift`

**Evidence:**

```
        # Per-entry schema
        entry = batch["entries"][0]
        expected_keys = {
            "entity_id",
            "payload",
            "semantic_vector",
            "utility",
            "attended_count",
            "protected_floor",
            "last_evaluated",
            "prior_state",
            "target_sublayer",
        }
        assert set(entry.keys()) == expected_keys
        assert entry["entity_id"] == str(eid)
        assert entry["payload"] == "schema-check"
        assert entry["attended_count"] == 3
        assert entry["protected_floor"] == 0.0
        assert entry["target_sublayer"].startswith("cortex_")
        assert entry["target_sublayer"].endswith(".usda")
        assert isinstance(entry["prior_state"], int)
```

**Proposed change:** Bump severity to High (it was Medium in consolidation-L1). The integration test cited above is an active anchor for the wrong shape — fixing the mock without fixing the test fails CI. Coordinated fix: (a) update mock_usd_target.py to emit `_state_to_token(m.state)` token strings; (b) bump SCHEMA_VERSION to 2; (c) update the integration test's prior_state assertion to expect a string in the allowedTokens set. This is a test-locked-in-bad-shape pattern, not just a doc lag.

**Risk if wrong:** If A/B differential debugging is ever needed in production (Phase 4 idle-window scheduler, Octavius integration), the mock cannot stand in for the real target on the prior_state field. The test fortifies the divergence.

**References:** `src/moneta/usd_target.py:_STATE_TO_TOKEN`, `ARCHITECTURE.md §15.7`

---

### `architect-L2-vector-authoritative-vs-hydrate-inversion` — High — ARCHITECTURE.md §7 declares the vector index authoritative for 'what exists' as the runtime invariant that justifies sequential-write atomicity, but Moneta's hydrate path rebuilds the vector index from the ECS snapshot — silently inverting the authoritative store on every restart and breaking the very assumption that orphan-tolerance depends on.

**Role:** architect  **File:** `src/moneta/api.py:186-211`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
self.ecs, wal_replay = self.durability.hydrate()
                # Rebuild vector index from hydrated ECS (shadow rebuild).
                for memory in self.ecs.iter_rows():
                    self.vector_index.upsert(
                        memory.entity_id,
                        memory.semantic_vector,
                        memory.state,
                    )
```

**Proposed change:** Either (a) persist the vector index to disk alongside the ECS snapshot so the restart preserves the runtime authoritative-store ordering — VectorIndex.snapshot()/restore() already exist in vector_index.py but are orphaned (Loop 1 persistence-L1-vector-snapshot-orphan), wire them through DurabilityManager; or (b) amend ARCHITECTURE.md §7 with an explicit clause: 'On hydrate, the ECS snapshot is authoritative; the vector index is rebuilt as a shadow of the hydrated ECS rows. Runtime authoritativeness flips back to the vector index on the first deposit.' Path (a) honors the locked invariant; path (b) documents the inversion. Today neither is in force.

**Risk if wrong:** A kill-9 between deposit's ecs.add and vector_index.upsert leaves a partial deposit; the runtime invariant says 'doesn't exist' (vector wins), but on hydrate the row IS in ECS and is replayed into the vector. The deposit silently 'recovers' across a crash even though it was incomplete at the moment of the crash. Spec-level surprise candidate (§9 Trigger 2): the atomicity reasoning in §7 — 'orphans benign because Pcp never traverses' — assumes the vector remains authoritative across restart. It does not.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §11`, `src/moneta/durability.py:hydrate`, `src/moneta/vector_index.py:snapshot`

---

### `architect-L2-handle-exclusivity-concurrency-model-unspecified` — High — The v1.1.0 handle exclusivity model — `_ACTIVE_URIS` as a process-level lock, check-then-add inside the constructor, release on close — is treated as a locked decision in README but absent from ARCHITECTURE.md, including its concurrency model: TOCTOU under CPython GIL, behavior under fork(), behavior under PEP 703 free-threading, and the cleanup ordering requirement when SIGTERM arrives mid-with-block.

**Role:** architect  **File:** `ARCHITECTURE.md:25-60`  **§9:** yes  **Conflicts with locked decision:** no
**Closes:** `architect-L1-handle-pattern-undocumented`

**Evidence:**

```
### 2.1 Harness-level bootstrap (not part of the agent API)

The module also exposes `init()`, `run_sleep_pass()`, `smoke_check()`, and `MonetaConfig`. **These are not part of the agent-facing four-op surface.** They are harness-level entry points used by test fixtures, operator scripts, and Consolidation Engineer's sleep-pass scheduler. Agents never call them; fifth-op rules do not apply.
```

**Proposed change:** Add ARCHITECTURE.md §2.2 'Substrate handle and process-level exclusivity' covering: (1) `Moneta(config)` is the sole constructor; no-arg construction is a TypeError by contract; (2) two live handles on the same `storage_uri` raise MonetaResourceLockedError synchronously at the second constructor call; (3) the exclusivity primitive is an in-memory Python set, NOT a file lock, NOT a distributed lock — single process only; (4) check-then-add atomicity relies on CPython GIL bytecode semantics and is undefined under PEP 703 free-threaded Python or under sub-interpreters with per-interpreter GILs; (5) fork() inheritance is undefined — the child process inherits a copy of `_ACTIVE_URIS` whose contents reference handles that no longer exist in its address space, and a child constructor on a previously-held URI will spuriously raise; (6) close ordering is durability-thread-stop → authoring-target-close → URI release. Cite DEEP_THINK_BRIEF_substrate_handle.md §5.4 as lineage and Loop 1's Crucible adversarial test (test_concurrent_construction_yields_at_most_one_handle) as empirical evidence for the GIL-only guarantee. Without §2.2 the rule that locks Moneta to single-process operation is invisible to a reader of the spec, and a Phase 4 cloud-deployment surgery (the brief explicitly anticipates s3:// or moneta:// URIs) has no foundation to extend.

**Risk if wrong:** Concurrency-shaped extensions to the codebase compound on this gap: free-threaded TOCTOU (Loop 1 adversarial-L1-active-uris-no-lock-toctou), fork-and-forget child processes, atexit/SIGTERM handlers that need to discover live handles, multi-interpreter embedding. Each of these reaches the locked-spec layer; today none of them have a spec to anchor against.

**References:** `README.md 'Locked decisions' #5`, `src/moneta/api.py:_ACTIVE_URIS`, `DEEP_THINK_BRIEF_substrate_handle.md`, `tests/test_twin_substrate_adversarial.py`

---

### `adversarial-L2-hydrate-inversion-spec-surprise-confirmed` — High — PRIOR FINDING architect-L2-vector-authoritative-vs-hydrate-inversion is correctly classified as §9 candidate. Reinforce: ARCHITECTURE.md §7's 'vector index is authoritative for what exists' is the keystone of the no-2PC atomicity argument — if vector is authoritative, an interrupted deposit (ecs.add succeeded, vector.upsert raised) leaves a benign 'doesn't exist' state. The hydrate path silently inverts this: ECS snapshot becomes the source of truth, vector is reconstructed from it. A deposit that raised mid-construction in the prior session re-emerges in the new session via ECS hydrate, vector then receives it via the rebuild loop. The atomicity argument's load-bearing assumption — vector wins — is broken across restart.

**Role:** adversarial  **File:** `src/moneta/api.py:186-211`  **§9:** yes  **Conflicts with locked decision:** no

**Evidence:**

```
self.ecs, wal_replay = self.durability.hydrate()
                # Rebuild vector index from hydrated ECS (shadow rebuild).
                for memory in self.ecs.iter_rows():
                    self.vector_index.upsert(
                        memory.entity_id,
                        memory.semantic_vector,
                        memory.state,
                    )
```

**Proposed change:** This is genuinely §9 Trigger 2 (spec-level surprise). The §7 atomicity argument depends on vector authoritativeness; hydrate violates it; the violation is invisible. Architect should draft a §9 brief covering: (a) is vector-side persistence (vector_index.snapshot/restore wired through DurabilityManager) the correct fix? (b) Or should §7 be amended to acknowledge a 'restart inversion' clause stating ECS snapshot is authoritative on hydrate and authoritativeness flips back to vector on first deposit? Path (a) honors the locked invariant; path (b) documents the inversion as accepted. Both are spec-level decisions, not local fixes.

**Risk if wrong:** If the hydrate inversion is ACTUALLY benign (no real data scenario produces an ECS row whose vector record was never committed), the §9 escalation is over-aggressive. Today the only path that creates this divergence is a kill-9 between ecs.add and vector.upsert in deposit (Phase 1 deposit ordering is ECS-first per substrate-L2-deposit-no-rollback-on-vector-failure). Probability is low; consequence is silent inconsistency that survives restart.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §11`, `MONETA.md §9 Trigger 2`, `architect-L2-vector-authoritative-vs-hydrate-inversion`

---

### `persistence-L2-wal-clock-skew-filters-signals` — High — WAL hydrate filters replay entries by `e.timestamp > snapshot_ts`, so any post-snapshot signal_attention whose wall-clock timestamp is less than the snapshot's `snapshot_created_at` is silently dropped on restart — which fires on every NTP-backward step, virtualized clock rewind, or test-harness time injection that lands between a snapshot and a kill -9.

**Role:** persistence  **File:** `src/moneta/durability.py:195-205`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
all_wal = self.wal_read()
        replay = [e for e in all_wal if e.timestamp > snapshot_ts]
```

**Proposed change:** Replace the timestamp-based filter with a structural marker: capture the WAL byte offset at snapshot_ecs entry, persist it inside the snapshot blob (e.g. `wal_offset_at_snapshot`), and on hydrate replay every WAL entry past that offset regardless of its embedded timestamp. Or write a per-entry monotonic sequence counter and replay by counter rather than wall clock. Either preserves the kill -9 contract under non-monotonic time.

**Risk if wrong:** If wrong, the existing wal-replay test (test_wal_replay_after_post_snapshot_signal in tests/integration/test_durability_roundtrip.py) only exercises a forward-time path and would still pass. The bug fires only when an operator combines durability.start_background with NTP synchronization on long-running processes — i.e. the documented production configuration in docs/api.md.

**References:** `MONETA.md §5 risk #4`, `ARCHITECTURE.md §11`, `docs/api.md 'Durability guarantees'`

---

### `persistence-L2-vector-index-query-iteration-race` — High — VectorIndex.query iterates `self._records.items()` directly without snapshotting the keys; a concurrent upsert/delete from another thread (deposit on agent thread + sleep-pass prune on consolidation thread is the canonical multi-call pattern) raises `RuntimeError: dictionary changed size during iteration` mid-query, so the §7 'vector index is authoritative' invariant has no safe concurrent read path.

**Role:** persistence  **File:** `src/moneta/vector_index.py:115-145`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        for eid, (vec, _state) in self._records.items():
            if len(vec) != dim:
                continue
```

**Proposed change:** Snapshot the iterable before the scoring loop: `records_snapshot = list(self._records.items())` then iterate the snapshot. The cost is one O(n) shallow copy per query (n = live entity count, bounded by §15.2 envelope at ~50k×rotation, so a single allocation of references). Alternatively document a hard single-writer/single-reader contract on the module docstring and add an integration test that asserts query is never called concurrently with upsert.

**Risk if wrong:** If wrong, the issue is masked by the de-facto convention that Phase 1 callers run single-threaded — but durability.start_background runs a daemon thread that triggers snapshot_ecs (which iterates ECS, not vector_index) without any guard against concurrent agent-thread queries on the same handle. Once a future caller wires a concurrent reader (Octavius, MCP server, async agent loop), the RuntimeError is unavoidable.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §7.1`, `src/moneta/ecs.py module docstring 'Concurrency: single-writer'`

---

### `usd-L2-sublayerpaths-mutation-outside-changeblock` — High — _get_or_create_layer mutates self._root_layer.subLayerPaths outside any Sdf.ChangeBlock; this violates substrate convention #5 ('Sdf.ChangeBlock for batch writes — always') and, more dangerously, drives a Pcp recomposition on the live UsdStage outside the empirical scope of Pass 5's narrow-lock ruling, which only verified concurrent Traverse during ChangeBlock-internal authoring + layer.Save on a static sublayer stack.

**Role:** usd  **File:** `src/moneta/usd_target.py:195-210`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        # Insert into root sublayer stack
        paths = list(self._root_layer.subLayerPaths)
        if protected:
            # Strongest position (index 0)
            paths.insert(0, layer.identifier)
        else:
            # Right after protected sublayer: newer rolling sublayers are
            # stronger than older ones at composition time.
            insert_at = 1 if paths else 0
            paths.insert(insert_at, layer.identifier)
        self._root_layer.subLayerPaths[:] = paths
```

**Proposed change:** Wrap the get/insert/assign-back triple in `with Sdf.ChangeBlock():` so the subLayerPaths edit batches into a single LayersDidChange notification per substrate convention #5. Separately, the §15.6 narrow-lock claim only covers Save+Traverse concurrency; if a future component performs concurrent stage.Traverse() on the live stage during sublayer-stack mutation, that scenario must be re-evaluated (it was outside Pass 5's 775M-assertion stress test, which used a fixed sublayer stack).

**Risk if wrong:** The current code path runs only at first-deposit-of-day or at rotation, both rare events, and is single-writer in practice. If a future Phase 4 idle-window scheduler interleaves a reader against day rollover or rotation, the unbatched subLayerPaths mutation fires per-element notifications and triggers a Pcp recomposition that was never empirically validated as concurrent-safe.

**References:** `docs/substrate-conventions.md §5`, `ARCHITECTURE.md §15.6`, `docs/pass5-q6-findings.md`

---

### `usd-L2-flush-dict-iteration-race` — High — flush() iterates self._layers.values() while a concurrent author_stage_batch can mutate self._layers via _get_or_create_layer (rotation creates new entries). Under any pattern that calls flush() and author_stage_batch from different threads — e.g., an operator scheduler that flushes on a timer while consolidation runs, a test harness that exercises both APIs, or a Phase 4 idle-window scheduler with parallel batches — Python raises `RuntimeError: dictionary changed size during iteration`.

**Role:** usd  **File:** `src/moneta/usd_target.py:305-310`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if not self._in_memory:
            for layer in self._layers.values():
                layer.Save()
            self._root_layer.Save()
```

**Proposed change:** Snapshot the layers before iterating: `for layer in list(self._layers.values()): layer.Save()`. The cost is one list materialization per flush call (cheap relative to Save). Alternatively, document explicitly in the module docstring that UsdTarget is single-threaded with respect to author_stage_batch + flush + close, and add an AST-level assertion that no consumer of the AuthoringTarget Protocol calls these from multiple threads. ARCHITECTURE.md §15.6 narrow-lock semantics already imply 'one writer thread' but the implementation does not protect against trivial accidental violation.

**Risk if wrong:** Today the SequentialWriter calls author_stage_batch then flush sequentially from the same thread, so the race is unreachable. A two-line change — adding a background flush daemon, or moving flush behind a Phase 4 commit-batching layer — exposes the bug. Single-writer convention is preserved by accident, not by construction.

**References:** `ARCHITECTURE.md §15.6`

---

### `usd-L2-multilayer-save-exceeds-pass5-empirical-scope` — High — ARCHITECTURE.md §15.6 cites Pass 5's 775M-assertion safety verification (`docs/pass5-q6-findings.md`) as the empirical basis for the narrow-lock ruling, but that test exercised concurrent Traverse during a single layer.Save on a single-layer stage. UsdTarget.flush() saves N layers in sequence (rolling sublayer + protected + root + any rotated continuations), each a discrete Save call. The cumulative wall-clock contention window is N× the single-layer case, and the Pass 5 ruling does not establish DETERMINISTIC SAFE for the multi-layer Save shape.

**Role:** usd  **File:** `src/moneta/usd_target.py:305-310`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if not self._in_memory:
            for layer in self._layers.values():
                layer.Save()
            self._root_layer.Save()
```

**Proposed change:** Either (a) rerun the Pass 5 stress harness against a multi-layer stage (rolling + protected + root, all dirty) to extend the DETERMINISTIC SAFE ruling to UsdTarget's actual Save shape, and update `docs/pass5-q6-findings.md` with the multi-layer addendum; or (b) update ARCHITECTURE.md §15.6 to scope the narrow-lock ruling to single-layer Save and add a hard constraint that flush() saves at most one dirty layer per call (with overflow surfaced as §9 Trigger 2). Path (a) is cheaper than path (b); both close the letter-vs-intent gap.

**Risk if wrong:** If multi-layer concurrent Save+Traverse has a different failure profile than single-layer (e.g., interleaving notifications across layers race the Pcp cache differently), Phase 3's Green-adjacent verdict rests on incomplete empirical evidence. A future patent challenge or operational incident at the multi-layer shape would have no evidence trail.

**References:** `ARCHITECTURE.md §15.6`, `docs/pass5-q6-findings.md`, `docs/patent-evidence/pass5-usd-threadsafety-review.md`

---

### `architect-L2-multibatch-staging-ecs-state-stranding` — High — Multi-batch consolidation strands ECS rows at STAGED_FOR_SYNC permanently if any sub-batch raises, because the STAGED→CONSOLIDATED transition runs only after the entire batch loop completes and a subsequent classify() skips non-VOLATILE rows; ARCHITECTURE.md §7's atomicity guarantee covers USD orphans but is silent on this ECS-side stranding mode that the §15.2 #3 batch cap creates.

**Role:** architect  **File:** `src/moneta/consolidation.py:148-173`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
if stage_ids and sequential_writer is not None:
            staged_memories: List[Memory] = []
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.STAGED_FOR_SYNC)
                memory = ecs.get_memory(eid)
                if memory is not None:
                    staged_memories.append(memory)
            for batch_start in range(0, len(staged_memories), MAX_BATCH_SIZE):
                batch = staged_memories[batch_start : batch_start + MAX_BATCH_SIZE]
                result = sequential_writer.commit_staging(batch)
                authoring_at = result.authored_at
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.CONSOLIDATED)
```

**Proposed change:** Restructure run_pass so the STAGED→CONSOLIDATED transition is per-batch and inside a try/except that converts mid-pass exceptions to (a) a partial-success ConsolidationResult plus (b) reverting the un-committed sub-batch's ECS rows back to VOLATILE so classify() can re-pick them on the next pass. Update ARCHITECTURE.md §7 to add: 'ECS state transitions for staged entities are per-batch atomic; a failed sub-batch leaves untouched entities in VOLATILE for re-classification — never permanently STAGED_FOR_SYNC.' Without one of these, the spec letter (orphans benign) hides a real ECS-side wedge that §15.2 #3's mandatory batching makes routinely reachable.

**Risk if wrong:** If commit_staging never raises in production (single-handle, in-memory shadow index, real USD with idempotent Sdf.CreatePrimInLayer), the bug is latent. But every documented future addition — LanceDB shadow with disk-full, OpenUSD Save() failure modes, network-mounted cortex sublayers — opens the failure path, and the wedged entity is invisible (classify skips it, manifest count grows but never drains).

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §15.2 #3`, `src/moneta/consolidation.py:run_pass`, `src/moneta/consolidation.py:classify`

---

### `architect-L2-section-11-snapshot-wal-coordination-silent` — High — ARCHITECTURE.md §11 lists 'Shadow vector index + WAL-lite durability' as a Phase 1 deliverable but specifies neither the snapshot/WAL coordination invariant nor the per-mutation durability scope; the spec gap is what enables Loop 1's persistence-L1-wal-truncation-race to exist as code (snapshot timestamp captured before write, WAL truncated unconditionally after) without any spec-level tripwire.

**Role:** architect  **File:** `ARCHITECTURE.md:253-271`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `persistence-L1-wal-truncation-race`

**Evidence:**

```
Phase 1 ships:

- Flat ECS hot tier (§3)
- Lazy decay (§4)
- Four-op API (§2)
- Append-only attention log and sleep-pass reducer (§5.1)
- Shadow vector index + WAL-lite durability
- Sequential-writer wrapper around a mock USD target (§7 discipline without `pxr`)
- Mock consolidation target producing a manifest log in Phase 3 shape (§6)
- Synthetic 30-minute session harness as the completion gate
```

**Proposed change:** Add ARCHITECTURE.md §11.1 'Durability invariants' covering: (i) the snapshot is taken under the same lock that gates WAL truncation, OR equivalently the WAL truncation is bounded by the byte offset captured at snapshot start (not by timestamp); (ii) the deposit path is snapshot-covered (intentional volatility window per MONETA.md §5 risk #4) and signal_attention is WAL-covered; (iii) on hydrate, WAL entries with timestamp > snapshot_created_at replay into the attention log (not the ECS). Without §11.1 the architect-spec angle of Loop 1's Critical implementation race is open: the spec authorizes neither the right answer (lock-coordinated truncation) nor the wrong answer (timestamp-coordinated truncation, which is what ships).

**Risk if wrong:** If Loop 1's persistence-L1-wal-truncation-race is fixed locally (set timestamp under lock, or truncate-by-offset), the spec is still silent and a future Persistence Engineer can re-introduce the race 'for performance' without violating any locked clause. The constraint exists to prevent attention loss across snapshot boundaries; it must live in the spec, not just in the implementation.

**References:** `ARCHITECTURE.md §11`, `MONETA.md §5 risk #4`, `src/moneta/durability.py:snapshot_ecs`

---

### `substrate-L2-single-writer-rule-not-enforced-in-handle` — High — ecs.py documents 'Concurrency: single-writer. Agent operations (deposit, query) and the sleep-pass reducer must not run concurrently on the same instance' but Moneta exposes `deposit`, `query`, and `run_sleep_pass` as plain methods with no synchronization; concurrent calls drive `ecs.decay_all` (which mutates `_utility` and `_last_evaluated` in place) against ongoing `add`/`remove` (which use swap-and-pop list mutations) — the §5.1 lock-free guarantee covers ONLY the attention log path; every other path silently relies on a single-writer convention the substrate does not enforce.

**Role:** substrate  **File:** `src/moneta/api.py:246-320`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def query(
        self, embedding: List[float], limit: int = 5
    ) -> List[Memory]:
        """Retrieve the top-k memories by relevance to ``embedding``.

        ARCHITECTURE.md §4 evaluation point 1: lazy decay is applied
        to every live entity before scoring.
```

**Proposed change:** Two viable paths: (a) add an internal `threading.RLock` to Moneta covering deposit, query, run_sleep_pass, and get_consolidation_manifest — signal_attention remains lock-free per §5.1. This is the simplest enforcement and matches the implicit substrate intent; (b) document loudly in api.py and ARCHITECTURE.md §3 that the four-op handle is not thread-safe except for signal_attention, and require consumers to externally serialize. Path (b) preserves the implementation but inverts the apparent contract — the README's multi-instance support invites consumers to assume per-handle thread safety. Either way, pair the change with a stress test that fires concurrent deposit/query/run_sleep_pass against one handle and asserts no list-changed-during-iteration exceptions and no orphaned vector_index entries.

**Risk if wrong:** The single-writer comment is in ecs.py only; ARCHITECTURE.md §3 does not state the invariant. A consumer reading the README and v1.1.0 surgery brief reasonably concludes a handle is thread-safe (the surgery emphasized multi-instance, not single-writer-per-instance). The first concurrent crash will be in production. If wrong, existing tests would have already failed under a multi-threaded test runner — they don't because pytest-default is serial.

**References:** `ARCHITECTURE.md §3`, `ARCHITECTURE.md §5.1`, `src/moneta/ecs.py module docstring`, `README.md v1.1.0 surgery section`

---

### `substrate-L2-signal-attention-batch-not-atomic` — High — Moneta.signal_attention iterates the weights dict and performs `attention.append` followed by an optional `durability.wal_append` per entity; a sleep pass that drains the attention log between two iterations splits the logical batch into two states — the first half is reduced into the ECS and captured by the post-reduce snapshot; the second half is durable in the WAL with timestamps strictly less than `snapshot_created_at` and is therefore filtered OUT of the WAL replay on hydrate, silently lost on crash. The dict argument intent (one logical signal applied atomically) is not honored.

**Role:** substrate  **File:** `src/moneta/api.py:296-314`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def signal_attention(self, weights: Dict[UUID, float]) -> None:
        """Record agent attention for the given entities.

        Writes go to the append-only attention log (ARCHITECTURE.md
        §5.1). If durability is enabled, each signal is also fsync'd to
        the WAL so that a kill -9 after the return does not lose the
        signal. The ECS update happens when the sleep-pass reducer
        drains the log.
        """
        now = time.time()
        for entity_id, weight in weights.items():
            w = float(weight)
            self.attention.append(entity_id, w, now)
            if self.durability is not None:
                self.durability.wal_append(
                    AttentionEntry(entity_id, w, now)
                )
```

**Proposed change:** Two options: (a) buffer all (eid, w, now) tuples into a local list, then perform one `attention.extend(...)` call (extend is also bytecode-atomic on lists under CPython) followed by a single batched WAL write covering all entries — the sleep pass either sees all or none of the batch; (b) document explicitly in the docstring that signal_attention is not transactional across multiple entity_ids and that callers wanting batch atomicity should serialize signal_attention calls under their own lock. Option (a) requires AttentionLog.extend (one-line addition) and DurabilityManager.wal_append_batch. The 'fsync'd to the WAL' docstring claim already over-promises (see persistence-L1-wal-fsync-drift); fixing both gives one coherent durability semantic.

**Risk if wrong:** The concrete loss path requires (1) durability enabled, (2) multiple entity_ids in one signal_attention call, (3) sleep pass timer elapses between two iterations, (4) crash before the WAL entry's timestamp would be > the next snapshot_created_at. All four are reachable in production. If wrong, dict iteration is fast enough that the sleep pass never preempts mid-loop — but Python's GIL switch interval (default 5ms) is comparable to dict iteration cost for medium-large weights dicts.

**References:** `ARCHITECTURE.md §5.1`, `ARCHITECTURE.md §11 Phase 1 deliverables`, `docs/api.md 'Coverage by operation' table`

---

### `substrate-L2-close-uncoordinated-with-inflight-ops` — High — Moneta.close sets `_closed = True`, calls `durability.close()` and `authoring_target.close()`, then `_ACTIVE_URIS.discard(...)` — all without coordinating with method calls in flight on other threads. A concurrent `query()` or `run_sleep_pass()` continues to use the half-torn-down ECS, vector_index, and authoring_target while another thread can already construct a fresh handle on the same `storage_uri`. This is the §5.4 in-memory exclusivity invariant being preserved by URI but violated by physical state.

**Role:** substrate  **File:** `src/moneta/api.py:222-244`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def close(self) -> None:
        """Release native resources and the URI lock. Idempotent.

        Order matters: shut the snapshot daemon thread before closing
        the authoring target, then discard the URI from
        ``_ACTIVE_URIS``. Reverse order would let a re-construct on the
        same URI race against an in-flight snapshot or open file handle.
        """
        if self._closed:
            return
        self._closed = True
        try:
            if self.durability is not None:
                self.durability.close()
            if hasattr(self.authoring_target, "close"):
                self.authoring_target.close()
        finally:
            _ACTIVE_URIS.discard(self.config.storage_uri)
```

**Proposed change:** Either (a) make close() block until all in-flight method calls return — wraps every public method (deposit, query, signal_attention, get_consolidation_manifest, run_sleep_pass) in an entry/exit refcount, and close() waits until refcount==0 before tearing down; or (b) document explicitly that close() is the consumer's responsibility to call only after no other thread is using the handle, and have every public method check `if self._closed: raise MonetaClosedError` at the top to fail fast on use-after-close. Path (b) is consistent with Python file-object semantics and cheap to implement; path (a) is more defensive. The current implementation does neither: there is no `_closed` check in deposit/query/signal_attention.

**Risk if wrong:** Real-world exposure is bounded by typical use (a single-thread context manager). But docstring says 'Order matters: shut the snapshot daemon thread before closing the authoring target' — the careful ordering implies thread-safety intent that the implementation does not deliver. A consumer following the v1.1.0 README's multi-instance pattern who closes a handle from a signal handler while a worker thread is mid-query will hit AttributeError or worse.

**References:** `ARCHITECTURE.md §3`, `DEEP_THINK_BRIEF_substrate_handle.md §5.4`, `src/moneta/api.py:Moneta.close`

---

### `consolidation-L2-cross-store-state-divergence-mid-batch` — High — During the multi-batch staging loop, sequential_writer.commit_staging transitions the vector index to CONSOLIDATED inside each call (via vector_index.update_state) while the ECS state transition to CONSOLIDATED happens only AFTER all batches complete; this creates a cross-store divergence window where vector says CONSOLIDATED but ECS still says STAGED_FOR_SYNC for batches 0..N-1 while batch N is still running.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:162-170`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
for batch_start in range(0, len(staged_memories), MAX_BATCH_SIZE):
                batch = staged_memories[batch_start : batch_start + MAX_BATCH_SIZE]
                result = sequential_writer.commit_staging(batch)
                authoring_at = result.authored_at
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.CONSOLIDATED)
```

**Proposed change:** Same fix as consolidation-L2-stage-partial-batch-atomicity-break: transition each entity's ECS state to CONSOLIDATED immediately after its batch's commit_staging returns, so vector and ECS state advance together per-batch. The single-writer convention rules out concurrent reads observing the divergence window today, but the divergence becomes permanent on partial failure (sister finding) and is observable by any future code path that reads memory.state during run_pass (e.g., a manifest read from another thread, a status endpoint, a debugger).

**Risk if wrong:** Single-writer convention means no live consumer observes the divergence window; the practical impact is conditional on the partial-failure case becoming permanent. If the sister Critical finding is fixed correctly, this finding is automatically resolved.

**References:** `ARCHITECTURE.md §7`, `src/moneta/sequential_writer.py:commit_staging`, `src/moneta/vector_index.py:update_state`

---

### `consolidation-L2-commit-staging-not-idempotent-on-retry` — High — If a sleep pass fails mid-multi-batch (sister finding) and a future operator manually unpicks STAGED_FOR_SYNC entities back to VOLATILE for retry, the next run_pass will re-invoke commit_staging on entities whose USD prims already exist on disk; UsdTarget.author_stage_batch silently overwrites typeName + 6 attributes via Sdf.CreatePrimInLayer with no entity-already-authored guard, producing potentially corrupted attribute values when the retry is at a different decay/attention point than the original commit.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:156-170`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
for batch_start in range(0, len(staged_memories), MAX_BATCH_SIZE):
                batch = staged_memories[batch_start : batch_start + MAX_BATCH_SIZE]
                result = sequential_writer.commit_staging(batch)
                authoring_at = result.authored_at
```

**Proposed change:** Either (a) make commit_staging idempotent at the consolidation layer by checking ECS state before authoring (skip entities already in CONSOLIDATED), making retry-safe by construction; or (b) document explicitly in the consolidation.py docstring that commit_staging is NOT idempotent and that any recovery path MUST guarantee no entity is re-authored (the §7 spec's 'orphans benign' rule applies to UNREFERENCED prims, but CreatePrimInLayer with the same path produces a REFERENCED overwrite, not an orphan). Path (a) is preferred because the partial-failure case is real and recovery is otherwise impossible.

**Risk if wrong:** If §7's 'sequential write, vector authoritative' is interpreted to mean 'vector index is the only thing that decides what was committed', then a retry that finds a vector index entry in CONSOLIDATED would skip — but that decision logic does not exist in run_pass; classify() only looks at ECS state. The hazard is real and only the symptoms are covered by spec.

**References:** `ARCHITECTURE.md §7`, `src/moneta/usd_target.py:author_stage_batch`

---

### `consolidation-L2-manifest-stale-after-partial-failure` — High — build_manifest returns ecs.staged_entities() unconditionally; after a partial-batch failure (sister finding), entities whose USD+vector commits already succeeded but whose ECS state never advanced to CONSOLIDATED appear in get_consolidation_manifest() as 'pending USD commit' even though they are durably authored on disk — the four-op API returns inaccurate state with no way for the agent to distinguish 'truly pending' from 'stuck-due-to-partial-failure'.

**Role:** consolidation  **File:** `src/moneta/manifest.py:12-25`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
def build_manifest(ecs: ECS) -> List[Memory]:
    """Return every entity currently in `STAGED_FOR_SYNC` state.

    Phase 1: direct passthrough to `ecs.staged_entities()`. Future
    filters (age, target sublayer grouping, minimum batch size) land
    here without touching the api.py layer.
    """
    return ecs.staged_entities()
```

**Proposed change:** Fixing the sister Critical finding (consolidation-L2-stage-partial-batch-atomicity-break) closes this one — once ECS state transitions are interleaved with batch commits, the manifest reflects truth. As an independent defense-in-depth measure, build_manifest could cross-check vector_index.get_state(eid) for each STAGED_FOR_SYNC entity and surface a divergence (vector says CONSOLIDATED, ECS says STAGED_FOR_SYNC) as a structured warning, but this is downstream — the primary fix is the run_pass loop ordering.

**Risk if wrong:** If the partial-failure case is fixed at the source, this manifest staleness is impossible. The finding here reinforces that the manifest is a thin projection of ECS state and inherits whatever inconsistency the runner produces.

**References:** `ARCHITECTURE.md §2 fourth op`, `src/moneta/ecs.py:staged_entities`

---

### `test-L2-pass5-stress-not-in-pytest-loop` — High — The Pass 5 thread-safety stress test (`--stress N`) is the sole empirical evidence for the §15.6 narrow-lock DETERMINISTIC SAFE ruling — 775M concurrent prim-attribute reads at the time of v1.0.0 ship — but it is invoked manually as a script flag, never by pytest. Nothing in the test suite would catch a Pass 6 regression that re-introduces wide-lock semantics or a future OpenUSD upgrade that breaks concurrent Traverse + Save safety; the locked §15.6 invariant is anchored only by a one-off CSV in `results/`.

**Role:** test  **File:** `scripts/usd_metabolism_bench_v2.py:627-650`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    parser.add_argument(
        "--stress",
        type=int,
        default=0,
        metavar="N",
        help="Run Q6 thread-safety stress test with N iterations instead of sweep.",
    )
```

**Proposed change:** Add a `@pytest.mark.load` test in tests/load/ (e.g., `test_pass5_threadsafety_smoke.py`) that imports `run_stress_test` from `scripts/usd_metabolism_bench_v2.py` and runs N=200 iterations (sub-second wall-clock under hython, sufficient to hit the concurrent Save/Traverse window many times) with `assertions_ok` and zero exceptions. Marked load so it doesn't slow the default suite, but selectable via `pytest -m load` so a Pass 6 regression CI job can catch reversals. Also add a strict structural assertion in the same file: AST scan that `UsdTarget.author_stage_batch` does NOT call `.Save()` on any layer.

**Risk if wrong:** Without CI coverage, a future maintainer who notices that `flush()` is called once per pass and 'optimizes' by inlining `layer.Save()` into `author_stage_batch` (the wide-lock pattern) would land green tests and silently regress the operational envelope from ~10–30ms p95 stall back to ~131ms — Phase 2 Yellow steady state.

**References:** `ARCHITECTURE.md §15.6`, `docs/pass5-q6-findings.md`, `docs/patent-evidence/pass6-lock-shrink-implementation.md`

---

### `test-L2-wal-truncation-race-no-regression-test` — High — The WAL truncation race in `DurabilityManager.snapshot_ecs` (Loop 1 finding `persistence-L1-wal-truncation-race`) — where post-`now` `wal_append` calls land in the file between fsync and `unlink`, then are silently deleted — has no regression test in the durability suite; even after the bug is fixed, no test would prevent a re-regression because the suite only exercises sequential snapshot→signal→hydrate flows.

**Role:** test  **File:** `tests/integration/test_durability_roundtrip.py:110-165`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_pre_snapshot_deposit_is_lost_on_crash(
        self, tmp_path: Path
    ) -> None:
        """Documented volatility window: deposits before the first snapshot
        are lost on crash. This is MONETA.md §5 risk #4 acceptance.
        """
```

**Proposed change:** Add a concurrency test in tests/integration/test_durability_roundtrip.py: launch two threads, one calling `snapshot_ecs` and another calling `signal_attention` (which fans out to `wal_append`) at high frequency; use a `threading.Event` to signal that the snapshot's `json.dump` has just completed but `unlink` has not yet run, and inject a barrier before the unlink (test-only hook); assert that any signal whose timestamp post-dates the snapshot's `now` survives the truncation. The test exposes the race and locks the future fix shape (preserve-by-offset or hold lock across the whole snapshot).

**Risk if wrong:** Critical bug already present (per Loop 1) is invisible to test suite. If the fix lands in a future surgery without a paired test, the same code path will re-regress under future maintenance. Constitution §15 'whether the test is adversarial' applies: tests must be motivated to find this failure, not confirm the happy path.

**References:** `ARCHITECTURE.md §11`, `MONETA.md §5 risk #4`, `src/moneta/durability.py:98-130`

---

### `test-L2-snapshot-atomicity-functionally-untested` — High — `test_snapshot_file_is_atomic` only verifies that no leftover `.tmp` file exists after a successful snapshot — it does NOT verify the actual atomicity claim, which is that a kill -9 mid-snapshot leaves either the old snapshot intact or the new snapshot fully present, never a half-written file. The os.replace + tmp-file pattern is the documented atomicity primitive, but the test exercises only the success path.

**Role:** test  **File:** `tests/integration/test_durability_roundtrip.py:142-165`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_snapshot_file_is_atomic(self, tmp_path: Path) -> None:
        """Snapshot writes go through a tmp file + os.replace.

        Verify the tmp file is cleaned up after a successful snapshot (no
        leftover .tmp file).
        """
        uri = "moneta-test://dura/atomic"
        cfg = _config(tmp_path, storage_uri=uri)

        with Moneta(cfg) as m:
            m.deposit("x", [1.0])
            m.run_sleep_pass()

            assert cfg.snapshot_path.exists()  # type: ignore[union-attr]
            # No leftover tmp file
            assert not (tmp_path / "s.json.tmp").exists()
```

**Proposed change:** Strengthen the test to actually exercise mid-write crash: (a) write a known snapshot, (b) start a second snapshot using a monkey-patched `json.dump` that raises a `KeyboardInterrupt` after writing partial bytes to the tmp file, (c) verify the original snapshot file is unchanged, (d) verify the .tmp file may exist but the canonical path was not corrupted. Bonus: assert that hydrating after the simulated crash returns the pre-crash snapshot, not a corrupted state.

**Risk if wrong:** If `os.replace` is in fact non-atomic on some filesystem (network mounts, certain Windows configurations, or future durability backends with different rename semantics), the substrate will silently lose data on crash and the test rename suggests it's verified. The test name claims atomicity; the assertion checks tmp-file housekeeping.

**References:** `ARCHITECTURE.md §11`, `src/moneta/durability.py:108-118`

---

### `test-L2-kill9-between-usd-save-and-vector-commit-untested` — High — ARCHITECTURE.md §7 sequential-write atomicity says USD authoring completes first, then the vector index commits — and that a crash between the two leaves a benign USD orphan because the vector index is authoritative for 'what exists'. No integration test simulates kill -9 in this exact window (after `flush()` returns, before `vector_index.update_state` runs). The test suite covers ECS↔WAL durability but not the cross-tier atomicity invariant of §7.

**Role:** test  **File:** `tests/integration/test_durability_roundtrip.py:55-90`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
class TestDurabilityRoundTrip:
    def test_no_snapshot_fresh_start(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path, storage_uri="moneta-test://dura/no-snap")
        with Moneta(cfg) as m:
            assert m.ecs.n == 0
            assert m.durability is not None
            # No snapshot file exists yet — hydrate found nothing
            assert not cfg.snapshot_path.exists()  # type: ignore[union-attr]
```

**Proposed change:** Add tests/integration/test_atomicity_orphan.py with a SequentialWriter test double whose `commit_staging` calls `target.author_stage_batch(...)`, calls `target.flush()`, then raises before invoking `vector_index.update_state`. Verify on a fresh handle reconstruct: (a) USD authored prims exist on disk for the staged batch (orphans), (b) vector_index has those entities still in their pre-commit state (VOLATILE/STAGED_FOR_SYNC), (c) `query()` returns results consistent with the vector index, not the USD orphans — i.e., the vector index is authoritative as §7 mandates, (d) the orphan USD prim is reachable via `target.stage.Traverse()` but does not appear in any agent-visible result.

**Risk if wrong:** §7's 'orphans benign, vector authoritative' contract is the keystone of Moneta's no-2PC atomicity story. If a future change makes the vector index check the USD stage on query (e.g., 'fall through to USD on miss'), §7 silently becomes 'USD authoritative', the inverse of the spec. Without a test exercising the exact crash window the spec describes, the contract is preserved by accident.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §16 conformance checklist (sequential-writer item)`, `src/moneta/sequential_writer.py:commit_staging`

---

### `adversarial-L2-fork-orphans-active-uris` — High — `_ACTIVE_URIS` is module-global Python state; on `os.fork()` the child process inherits a copy populated with the parent's URIs but with no live `Moneta` instances backing them. The child cannot construct a `Moneta` on any URI the parent held — `MonetaResourceLockedError` fires spuriously — and cannot release them because no `close()`-able handle exists. multiprocessing.Process with the default 'fork' start method (POSIX) is the trip mutation: zero source changes, locked spec invariant subverted.

**Role:** adversarial  **File:** `src/moneta/api.py:82-90`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
# In-memory only. Per §5.4: "an ephemeral lock singleton" — structurally
# correct for single-process exclusivity. Replaced by distributed
# coordination in the next surgery.
_ACTIVE_URIS: set[str] = set()
```

**Proposed change:** Either (a) register an `os.register_at_fork(after_in_child=lambda: _ACTIVE_URIS.clear())` callback at module import so the child starts clean — the parent's handles remain valid in the parent process, the child gets a fresh exclusivity scope; or (b) document explicitly in the §5.4 spec text and the api.py module docstring that handle lifecycle is not fork-safe and that consumers using multiprocessing must use the 'spawn' start method or construct Moneta only after fork. Path (a) is a one-line POSIX fix that closes the failure mode silently; path (b) ships the limitation honestly. Either way, the v1.1.0 surgery's 'in-memory exclusivity' contract has a fork hole that nothing in the test suite, the brief, or the Crucible adversarial pass exercises.

**Risk if wrong:** If Moneta is never deployed under `multiprocessing.Process(start_method='fork')` or under any forking server (gunicorn pre-fork, uWSGI, celery prefork), the bug is unreachable. Those are common Python production patterns — and the brief explicitly anticipates cloud routing via `s3://` and `moneta://` URIs, where pre-fork worker pools are standard.

**References:** `DEEP_THINK_BRIEF_substrate_handle.md §5.4`, `src/moneta/api.py:_ACTIVE_URIS`

---

### `adversarial-L2-fork-shares-wal-fd` — High — DurabilityManager opens the WAL via `open(self._wal_path, 'a', ...)` and retains the file pointer. After `os.fork()`, the file descriptor is shared between parent and child; both processes can call `wal_append` and the OS append-mode atomic-write guarantee holds at the per-write level but the WAL's logical contract — 'every entry in this file came from this Moneta handle' — collapses. Hydrate then replays the union of parent + child signals as if they belonged to one substrate, silently corrupting the ECS state on restart.

**Role:** adversarial  **File:** `src/moneta/durability.py:137-156`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        with self._lock:
            if self._wal_fp is None:
                self._wal_path.parent.mkdir(parents=True, exist_ok=True)
                self._wal_fp = open(self._wal_path, "a", encoding="utf-8")
            self._wal_fp.write(line + "\n")
            self._wal_fp.flush()
```

**Proposed change:** Compounds with adversarial-L2-fork-orphans-active-uris. The `os.register_at_fork(after_in_child=...)` hook should also close `self._wal_fp` on the child side and clear `_ACTIVE_URIS`, so the child cannot inherit either the URI lock or the open WAL fd. Alternatively, set `O_CLOEXEC` flag on the WAL fp at open time so subprocess.* calls don't share it (does not solve fork without exec). The locked §5.4 'in-memory exclusivity' invariant relies on a guarantee — 'one URI ↔ one process ↔ one set of file handles' — that fork breaks at the fd level even before it breaks at the URI level.

**Risk if wrong:** Reachable via the same fork patterns as the sibling finding. If the WAL path is on a tmpfs or /dev/null in tests (common pattern), the corruption is silent. In production with real filesystem WAL paths, restart hydrate replays a chronologically-interleaved mix of parent and child signals; some signals reference entity_ids only the parent ever deposited, get filtered as orphans by ECS.apply_attention, and disappear silently — exactly the §5.1 'eventually consistent missing entity' silent-skip path covered earlier.

**References:** `MONETA.md §5 risk #4`, `ARCHITECTURE.md §11`, `src/moneta/durability.py:wal_append`

---

### `adversarial-L2-pass5-stress-shape-mismatch` — High — The §15.6 narrow-lock DETERMINISTIC SAFE ruling rests on the Pass 5 stress test, which authored prims with `SdfSpecifierDef` and a single `Int` attribute named `val` to a single `primary_layer`. Production `UsdTarget.author_stage_batch` writes typed prims (`typeName='MonetaMemory'`) with SIX attributes — including a `Token` with `allowedTokens` validation — distributed across multiple sublayers (rolling + protected + rotated) that each get their own `layer.Save()` in `flush()`. The empirical safety claim does not cover the production write shape: more attributes per prim mean more notification fan-out per ChangeBlock exit; Token attribute creation may invoke schema validation paths Int does not; and per-layer Save sequencing changes the contention window structure.

**Role:** adversarial  **File:** `scripts/usd_metabolism_bench_v2.py:495-545`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        def writer_fn(iteration: int = i) -> None:
            try:
                with stage_lock:
                    with Sdf.ChangeBlock():
                        for j in range(10):
                            path = Sdf.Path(f"/stress_{iteration}_{j}")
                            ps = Sdf.CreatePrimInLayer(primary_layer, path)
                            ps.specifier = Sdf.SpecifierDef
                            Sdf.AttributeSpec(
                                ps, "val", Sdf.ValueTypeNames.Int
                            ).default = iteration
```

**Proposed change:** Extend `run_stress_test` with a `--shape monetamemory` mode that authors typed `MonetaMemory` prims with the actual six-attribute layout (payload String, utility Float, attendedCount Int, protectedFloor Float, lastEvaluated Double, priorState Token) across two layers (rolling + protected) and re-runs the 10,000-iteration concurrent-Traverse harness. If results match the 2026-04-12 evidence, append the addendum to `docs/patent-evidence/pass6-lock-shrink-implementation.md`. If results diverge (any failure), file §9 Trigger 2 — the empirical basis for the narrow-lock ruling did not cover the production code path it certifies.

**Risk if wrong:** If the Token attribute path or the multi-layer Save path has a different concurrency profile than the single-Int single-layer harness, the §15.6 ruling is overclaimed and Phase 3's Green-adjacent verdict rests on incomplete evidence. The patent-evidence chain (claim #4) inherits this gap. The fix is a one-day stress-test extension; the cost of NOT closing the gap is silent operational fragility plus a weakened patent posture.

**References:** `ARCHITECTURE.md §15.6`, `docs/pass5-q6-findings.md`, `docs/patent-evidence/pass6-lock-shrink-implementation.md`, `src/moneta/usd_target.py:author_stage_batch`

---

### `adversarial-L2-multi-entity-vector-failure-untested` — High — TestVectorFailure::test_vector_failure_does_not_rollback_authoring uses a `_FailingVector` whose `update_state` raises on the FIRST call. SequentialWriter.commit_staging loops `vector_index.update_state` per-memory in the batch — the first failure short-circuits the loop, leaving entries 1..N-1 in CONSOLIDATED but entries N..end never advanced. The §7 'orphan benign' contract is single-entity-shaped; the partial-batch case (M of N updated) is silently uncovered, and a future LanceDB backend whose update_state can transiently fail (network blip on entity K) leaves the substrate in a half-committed state.

**Role:** adversarial  **File:** `tests/integration/test_sequential_writer_ordering.py:108-135`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_vector_failure_does_not_rollback_authoring(self) -> None:
        """§7: 'USD orphans from interrupted writes are benign.'

        The sequential writer must NOT attempt to undo the authoring
        write when the vector index fails. The orphan is the protocol.
        """
        target = MockUsdTarget(log_path=None)
        vec = _FailingVector()
        writer = SequentialWriter(target, vec)

        mem = _make_memory()

        with pytest.raises(RuntimeError, match="simulated"):
            writer.commit_staging([mem])
```

**Proposed change:** Add `test_vector_failure_mid_batch_leaves_partial_consolidation`: construct a vector double whose `update_state` succeeds on the first 2 calls and raises on the 3rd; pass a 5-entity batch to commit_staging; assert (a) the exception propagates, (b) entities 0,1 are CONSOLIDATED in the vector double, (c) entities 2,3,4 remain in their pre-call state. This pins the §7 contract under partial failure: either the spec authorizes M-of-N partial commit (in which case the substrate must surface the divergence in a structured exception that consolidation.run_pass can use to advance ECS state for the M, leave STAGED for the N-M), or the spec mandates all-or-nothing (in which case commit_staging must be wrapped in a compensation path).

**Risk if wrong:** The current single-entity test is correct for what it tests — it just doesn't test the partial-batch case that ARCHITECTURE.md §15.2 #3 (500-prim batch cap) explicitly creates. With MockUsdTarget the partial state never persists; with real UsdTarget + a future LanceDB backend whose update_state can fail per-entry, the partial state IS persisted on the USD side and HALF-persisted on the vector side. The substrate has no documented recovery path because the failure mode has never been tested.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §15.2 #3`, `src/moneta/sequential_writer.py:commit_staging`

---

### `adversarial-L2-snapshot-iter-rows-generator-race` — High — DurabilityManager.snapshot_ecs calls `for memory in ecs.iter_rows(): rows.append(...)` — iter_rows is a generator that yields `_row_to_memory(i)` for `i in range(len(self._ids))`. ECS.remove uses swap-and-pop which OVERWRITES `_ids[row]` with `_ids[last]` at the removed index. If a sleep pass runs concurrently with the daemon snapshot and prunes entity at row K while the snapshot generator is at index J<K, when the generator advances to K it yields a row whose `_ids[K]` is now the swapped-from-end entity AND whose `_payloads[K]/_utility[K]/_embeddings[K]` are also the swapped-from-end values — but it could yield index L<original-last whose contents have already been read at their original index. Net: snapshot contains duplicated rows and missing rows, hydrate restores a corrupted ECS.

**Role:** adversarial  **File:** `src/moneta/durability.py:80-100`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        rows = []
        for memory in ecs.iter_rows():
            rows.append(
                {
                    "entity_id": str(memory.entity_id),
```

**Proposed change:** This deepens persistence-L2-snapshot-ecs-iteration-unguarded with a concrete corruption mode. The fix MUST be acquire `self._lock` (or a substrate-level lock) BEFORE the iteration begins and hold it across the entire row-collection loop, releasing only after `rows` is fully built (the json.dump can run lock-free against the immutable list). Alternatively, snapshot_ecs could call a new ECS.snapshot_rows() method that returns an atomic copy of all column lists under a lock — clearer interface boundary. The current implementation iterates a live generator against a mutable struct-of-arrays; the swap-and-pop pattern in ECS.remove is the single most concurrency-hostile data structure choice in the substrate.

**Risk if wrong:** Reachable any time durability.start_background runs alongside a concurrent sleep pass that prunes — i.e., the documented production durability cadence. The corruption is silent: hydrate restores a wrong ECS, query returns wrong results, the operator sees no error. The persistence-L2 finding correctly identified the iteration-not-locked gap; this finding identifies the SPECIFIC corruption mode (swap-and-pop interaction) that makes it Critical-class behavior, not just 'torn snapshot'.

**References:** `ARCHITECTURE.md §11`, `src/moneta/ecs.py:remove`, `src/moneta/ecs.py:iter_rows`, `persistence-L2-snapshot-ecs-iteration-unguarded`

---

### `architect-L3-quota-override-bypasses-section10-cap` — High — ARCHITECTURE.md §10 declares 'Hard cap: 100 protected entries per agent' as a locked invariant, but `MonetaConfig.quota_override: int = 100` is unbounded — any caller can construct `MonetaConfig(quota_override=10_000_000)` and the §10 cap is silently bypassed; the v1.1.0 surgery converted the singleton-era `PROTECTED_QUOTA = 100` constant into a per-handle override without an accompanying §9 escalation to amend §10's 'hard cap' language.

**Role:** architect  **File:** `src/moneta/api.py:104-120`  **§9:** yes  **Conflicts with locked decision:** yes

**Evidence:**

```
    storage_uri: str
    quota_override: int = 100

    # Preserved from singleton-era config (semantics unchanged).
    half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS
```

**Proposed change:** Architect drafts a §9 Trigger 2 brief: either (a) clamp quota_override at construction time (`if quota_override > 100: raise ValueError`), preserving §10's locked text; or (b) amend ARCHITECTURE.md §10 to read 'Default cap: 100 protected entries per agent; per-handle override is permitted via MonetaConfig.quota_override but values exceeding 100 are an explicit operator override of the §10 backstop — log at WARNING level and document on the config field that the spec's intent is a backstop against agent abuse, not a hard ceiling on operator-side capacity planning.' Path (a) preserves the locked spec; path (b) honors the v1.1.0 design while documenting the loosening. Today the spec says one thing and the code does another.

**Risk if wrong:** If the v1.1.0 DEEP_THINK_BRIEF authorized the loosening explicitly (the brief is referenced from README but the relevant section is not in this snapshot), then the spec amendment was already approved and the only gap is that ARCHITECTURE.md §10 was never updated. That is still a real architect finding (Documentarian + Architect responsibility per Constitution §16). If the brief did not authorize unbounded override, the implementation broke the locked cap silently.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `DEEP_THINK_BRIEF_substrate_handle.md §5.3`, `MONETA.md §9 Trigger 2`

---

### `substrate-L3-protected-floor-not-validated-against-utility-domain` — High — Moneta.deposit and ECS.add accept protected_floor as any float without validating it against [0.0, 1.0]; a deposit with protected_floor=2.0 stores the row, and the very next decay eval point pushes utility UP to 2.0 (decay_value returns max(2.0, decayed) = 2.0) — directly violating the ARCHITECTURE.md §3 'Utility ∈ [0.0, 1.0]' invariant. Worse: subsequent apply_attention computes 1.0 if new_u > 1.0 else new_u, so an attention write resets utility to 1.0, which the next decay restores to 2.0 — an oscillating value that breaks ranking.

**Role:** substrate  **File:** `src/moneta/api.py:263-282`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if (
            protected_floor > 0.0
            and self.ecs.count_protected() >= self.config.quota_override
        ):
            raise ProtectedQuotaExceededError(
                f"protected quota of {self.config.quota_override} "
                f"exceeded; Phase 3 unpin tool required "
                f"(ARCHITECTURE.md §10)"
            )

        entity_id = uuid4()
        now = time.time()

        self.ecs.add(
```

**Proposed change:** Validate protected_floor at the api.deposit boundary: `if not (0.0 <= protected_floor <= 1.0): raise ValueError(f'protected_floor must be in [0.0, 1.0], got {protected_floor}')`. The §3 invariant 'Utility ∈ [0.0, 1.0]' depends on this clamp because decay_value uses protected_floor as a lower bound on utility; the implementation's silent acceptance of out-of-domain floors makes the §3 invariant defensible only by convention. Add a unit test in tests/unit/test_api.py exercising protected_floor=1.5 and asserting ValueError, plus a test with protected_floor=-0.1.

**Risk if wrong:** If callers in the wild are passing fractional floors > 1.0 'just in case' (treating it as a 'super-protected' marker), strict validation breaks them. But no current call site does this, and the constitution §15 first-principles directive prefers letter-aligned domain enforcement over silent acceptance.

**References:** `ARCHITECTURE.md §3`, `ARCHITECTURE.md §4`, `ARCHITECTURE.md §10`, `src/moneta/decay.py:decay_value`

---

### `substrate-L3-nan-inf-weight-poisons-utility` — High — Moneta.signal_attention casts weights via float(weight) which silently accepts NaN and inf; the WAL-appended entry persists the poisoned value to disk, and on reduce ECS.apply_attention computes new_u = utility + NaN = NaN, then `1.0 if NaN > 1.0 else NaN` evaluates to NaN (NaN comparisons are always False), storing NaN-utility into the live ECS. Until the next decay_all corrects via the protected_floor lower bound (which only fires because NaN > floor is False), every query returns NaN-ranked results and the consolidation classifier's `utility < 0.3` comparison evaluates to False, silently skipping the entity from staging.

**Role:** substrate  **File:** `src/moneta/api.py:296-314`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        now = time.time()
        for entity_id, weight in weights.items():
            w = float(weight)
            self.attention.append(entity_id, w, now)
            if self.durability is not None:
                self.durability.wal_append(
                    AttentionEntry(entity_id, w, now)
                )
```

**Proposed change:** Add NaN/inf guard at the api boundary: `import math; if not math.isfinite(w): raise ValueError(f'weight for {entity_id} must be finite, got {weight}')`. Accept positive zero and ordinary floats; reject NaN, +inf, -inf. The decay layer's eventual self-correction does not protect WAL integrity — a corrupt WAL entry persists across hydrate and a NaN-poisoned snapshot rehydrates a NaN-utility ECS. The single-line guard at signal_attention is the cheapest defense.

**Risk if wrong:** If a caller intentionally sends inf as a 'maximum reinforcement' marker, strict rejection breaks them. But the spec formula `Utility = min(1.0, Utility + weights[UUID])` already implies finite arithmetic; inf is undefined behavior in the spec. The risk of silent NaN propagation through hydrate is greater than the risk of breaking a hypothetical inf-using caller.

**References:** `ARCHITECTURE.md §5`, `ARCHITECTURE.md §11`, `src/moneta/ecs.py:apply_attention`, `src/moneta/decay.py:decay_value`

---

### `substrate-L3-protected-floor-traps-staging-substrate-side` — High — decay_value clamps utility from below at protected_floor; in combination with the §6 staging criterion (utility < 0.3 AND attended_count >= 3), any protected memory with floor >= 0.3 mathematically cannot match staging — utility never drops below 0.3, classify() never selects it, and the protected memory never reaches CONSOLIDATED. ARCHITECTURE.md §6 states 'protected memory is consolidated to cortex_protected.usda' but the substrate's decay+selection interaction makes this unreachable for any meaningfully-protected entity (floor >= 0.3). docs/phase3-closure.md §4 #1 acknowledges this for floor=1.0 specifically; the substrate-side mechanism applies for any floor >= 0.3.

**Role:** substrate  **File:** `src/moneta/decay.py:44-62`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    dt = now - last_evaluated
    if dt < 0.0:
        dt = 0.0
    decayed = utility * math.exp(-lam * dt)
    return decayed if decayed > protected_floor else protected_floor
```

**Proposed change:** Two viable resolutions, both Architect-bound: (a) carve out a separate 'protected staging' criterion in consolidation.classify() that selects protected entities by an alternative trigger (e.g., age since last attention, or accumulated count threshold) — this matches docs/phase3-closure.md §4 #1's planned 'dedicated protected-memory consolidation trigger'; (b) document explicitly in ARCHITECTURE.md §4 that protected_floor >= 0.3 is a 'pin forever in hot tier' marker and the consolidation path is unreachable by construction, so operators MUST size the quota and pin selectively. Path (a) closes the §6/§10 letter-vs-intent gap; path (b) makes the limitation a contract. The substrate has zero observability into which path is intended today.

**Risk if wrong:** If protected memories accumulate past the 100-entry quota during a long-running session, the substrate's deposit path raises ProtectedQuotaExceededError with no recovery (the unpin tool is Phase 3 spec'd but not implemented). The quota saturates monotonically because no protected entity ever transitions to CONSOLIDATED to free a slot semantically, and pruning never fires (utility never drops below 0.1).

**References:** `ARCHITECTURE.md §4`, `ARCHITECTURE.md §6`, `ARCHITECTURE.md §10`, `docs/phase3-closure.md §4 #1`

---

### `adversarial-L3-empty-embedding-bricks-vector-dim` — High — A single deposit with embedding=[] permanently bricks the vector index for the lifetime of the handle: VectorIndex.upsert sets `self._dim = len(vector) = 0` on the first call (the `if self._dim is None: self._dim = len(vector)` branch); every subsequent deposit with a non-empty embedding raises §7.1 ValueError because `len(vector) != 0`. The §7.1 'dim-homogeneity' invariant is preserved (correctly) but with a degenerate dim that no real embedder produces. Recovery requires constructing a fresh handle on a different storage_uri (per the spec's 'Callers that need to switch embedders must construct a fresh VectorIndex'). No test exercises this; no input validation rejects it; one bad call from a faulty embedder permanently disables the substrate.

**Role:** adversarial  **File:** `src/moneta/vector_index.py:82-96`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def upsert(
        self,
        entity_id: UUID,
        vector: List[float],
        state: EntityState,
    ) -> None:
        """Insert or replace an entity's vector and state."""
        if self._dim is None:
            self._dim = len(vector)
        elif len(vector) != self._dim:
            raise ValueError(
                f"embedding dim mismatch: expected {self._dim}, got {len(vector)}"
            )
```

**Proposed change:** Reject empty embeddings at the api.deposit boundary: `if not embedding: raise ValueError('embedding must be non-empty')`. Reject at vector_index.upsert as a defense-in-depth: `if len(vector) == 0: raise ValueError('embedding length must be > 0')`. Add a unit test: deposit with embedding=[], assert ValueError raised; assert subsequent deposit with [1.0] succeeds (no dim was ever locked). Closes the constitution §10 'embedding dimension homogeneity' clamp boundary that today admits a degenerate value.

**Risk if wrong:** Real-world embedders can produce empty vectors on degenerate input (empty string fed to a tokenizer-then-pool pipeline that returns no tokens). Silent acceptance + permanent dim-0 lock is the worst-case interaction with the §7.1 hard-raise discipline — the hard raise is meant to catch caller mistakes loudly, but the dim=0 case turns the hard raise into a permanent denial-of-service. A test fixture or production input that triggers this once disables the substrate until restart on a fresh URI.

**References:** `ARCHITECTURE.md §7.1`, `Constitution §10 Loop 3 theme bullet 'embedding dimension homogeneity'`, `src/moneta/api.py:Moneta.deposit`

---

### `adversarial-L3-negative-protected-floor-evades-quota` — High — Moneta.deposit gates the §10 protected-quota check on `protected_floor > 0.0`, but ecs.add accepts protected_floor=-0.5 without validation, and ecs.count_protected counts only `pf > 0.0`. A deposit with protected_floor=-0.5 stores an ECS row with a negative floor (which decay_value's `max(floor, decayed)` treats as no-floor since decayed is always non-negative), AND does not consume a quota slot, AND is invisible to the quota cap. An agent (or buggy caller) that always passes protected_floor=-0.001 gets unlimited 'protected'-flagged entries that aren't really protected and aren't quota-counted — the §10 backstop's intent ('agents will try to flag everything as protected; the quota is the backstop') is bypassed by negative inputs.

**Role:** adversarial  **File:** `src/moneta/api.py:263-282`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if (
            protected_floor > 0.0
            and self.ecs.count_protected() >= self.config.quota_override
        ):
            raise ProtectedQuotaExceededError(
                f"protected quota of {self.config.quota_override} "
                f"exceeded; Phase 3 unpin tool required "
                f"(ARCHITECTURE.md §10)"
            )
```

**Proposed change:** Validate protected_floor at api.deposit boundary: `if not (0.0 <= protected_floor <= 1.0): raise ValueError(f'protected_floor must be in [0.0, 1.0], got {protected_floor}')`. This closes both the negative-floor evasion AND the >1.0 utility-domain violation (covered by substrate-L3-protected-floor-not-validated-against-utility-domain). The two findings share a single one-line fix at the api boundary. Add unit tests: deposit with -0.5 and 1.5 both raise ValueError; ECS state unchanged after each.

**Risk if wrong:** If callers in the wild pass negative floors deliberately (treating it as a 'no floor' sentinel distinct from 0.0 — which would be unreasonable but conceivable), strict validation breaks them. But there are no current callers doing this and the §10 spec wording 'protected memory quota' implies the value should produce protection semantics; negative values produce the inverse.

**References:** `ARCHITECTURE.md §3`, `ARCHITECTURE.md §10`, `src/moneta/api.py:Moneta.deposit`, `substrate-L3-protected-floor-not-validated-against-utility-domain`

---

### `architect-L3-vector-index-skips-staged-state` — High — ARCHITECTURE.md §3 defines a three-state lifecycle (VOLATILE → STAGED_FOR_SYNC → CONSOLIDATED) that both ECS and vector index nominally implement (both use `EntityState`), but `SequentialWriter.commit_staging` transitions the vector index directly from VOLATILE to CONSOLIDATED, never observing STAGED_FOR_SYNC; the two stores' state machines are structurally divergent and the spec doesn't acknowledge that the vector-index state column has a dead branch.

**Role:** architect  **File:** `src/moneta/sequential_writer.py:97-115`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        for memory in staged:
            self._vector.update_state(memory.entity_id, EntityState.CONSOLIDATED)
        _logger.info("sequential_writer.vector_update count=%d", len(staged))

        return result
```

**Proposed change:** Either (a) emit `vector_index.update_state(eid, STAGED_FOR_SYNC)` in `consolidation.run_pass` immediately after `ecs.set_state(eid, STAGED_FOR_SYNC)` so the two stores' state columns advance in lockstep — closes the gap by construction and lets a future operator query 'which entities are mid-flight' from either store; or (b) amend ARCHITECTURE.md §3 to clarify that `EntityState` on the vector index is a coarse {VOLATILE, CONSOLIDATED} subset and that STAGED_FOR_SYNC is an ECS-only intermediate. Path (a) costs one line per pass and removes a class of cross-store divergence findings (Loop 2 consolidation-L2-cross-store-state-divergence-mid-batch). Path (b) accepts the divergence but documents it. Today the divergence is silent and `vector_index.update_state(eid, STAGED_FOR_SYNC)` is callable but never called.

**Risk if wrong:** If a future read path consults `vector_index.get_state` to answer 'is this entity pending?' the answer is wrong — the vector index never advertises STAGED_FOR_SYNC, so a real pending entity reads as VOLATILE there. Today no such reader exists, but build_manifest's spec-stated job is exactly that question; if the manifest implementation ever switches to consulting the vector index (e.g., for performance), it silently returns the wrong set.

**References:** `ARCHITECTURE.md §3`, `ARCHITECTURE.md §7`, `src/moneta/consolidation.py:run_pass`, `src/moneta/vector_index.py:update_state`

---

### `architect-L3-protected-floor-staging-trap-not-in-spec` — High — The staging condition `Utility < 0.3 AND AttendedCount >= 3` (§6) and the decay clamp `U_now = max(ProtectedFloor, ...)` (§4) interact such that any entity with `protected_floor >= 0.3` is mathematically prevented from ever staging, regardless of attention or time elapsed; this is acknowledged in `docs/phase3-closure.md §4` as a known limitation but ARCHITECTURE.md §6 nowhere states the implication, leaving spec readers to deduce a load-bearing pathology from the multiplication of two clauses.

**Role:** architect  **File:** `ARCHITECTURE.md:114-145`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
- `Utility < 0.3 AND AttendedCount >= 3` → **stage for USD authoring**.

**Authoring targets (Phase 3 reference; Phase 1 mock shape must match):**

- **Rolling sublayer:** `cortex_YYYY_MM_DD.usda`, one per day, never per pass.
```

**Proposed change:** Add an explicit clause to ARCHITECTURE.md §6: 'Staging-floor interaction: an entity with `protected_floor >= 0.3` (the staging utility threshold) cannot satisfy the staging condition because the decay clamp (§4) holds its utility at or above the floor. Consequence: protected entities with strong floors do not consolidate via the periodic sleep pass and persist in ECS-VOLATILE indefinitely. This is by-construction behavior; protected memories' consolidation path is governed by §2.5 / future-surgery (see docs/phase3-closure.md §4 for known-limitation status).' Without this clause, the load-bearing trap is invisible at the spec level and a future contributor reading §6 in isolation cannot reason about why integration tests use `protected_floor=0.1` rather than `1.0`.

**Risk if wrong:** Letter-but-not-intent (Constitution §9): the spec's §6 selection criteria are correctly implemented in `consolidation.classify`, but the criteria interact with §4's clamp to produce behavior the spec never names. A maintainer reading §6 alone cannot derive the trap; a maintainer changing the staging threshold (e.g., raising it to 0.5 for tuning) doesn't realize they're changing the implicit boundary at which protected memories become ineligible. The pathology is preserved by accident of current threshold values.

**References:** `ARCHITECTURE.md §4`, `ARCHITECTURE.md §6`, `docs/phase3-closure.md §4 'Known limitations'`, `tests/integration/test_real_usd_end_to_end.py 'protected_floor=0.1'`

---

### `persistence-L3-update-state-no-transition-guard` — High — VectorIndex.update_state accepts any EntityState value and silently overwrites the prior state with no validation of forward-only progression — a CONSOLIDATED entity can be transitioned back to STAGED_FOR_SYNC or VOLATILE without raising, undermining the implicit lifecycle ARCHITECTURE.md §3 declares (VOLATILE → STAGED_FOR_SYNC → CONSOLIDATED) on the very store §7.1 names authoritative.

**Role:** persistence  **File:** `src/moneta/vector_index.py:97-108`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def update_state(self, entity_id: UUID, state: EntityState) -> None:
        """Change the state on an existing entity without touching its vector.

        Silently no-ops if the entity is absent (matches §5.1's
        "eventually consistent" discipline for missing entities).
        """
        rec = self._records.get(entity_id)
        if rec is None:
            return
        vec, _ = rec
        self._records[entity_id] = (vec, state)
```

**Proposed change:** Either (a) validate the requested transition against an explicit progression table — VOLATILE→{STAGED_FOR_SYNC, CONSOLIDATED}, STAGED_FOR_SYNC→{CONSOLIDATED, VOLATILE} (the latter for retry/rollback), CONSOLIDATED→{} — and raise on any backward move, or (b) at minimum log at WARNING level when the new state is numerically less than the prior state. Pair with a unit test in tests/unit/test_vector_index.py (currently absent — Loop 1 finding test-L1-no-vector-index-tests) that asserts each illegal transition is rejected. The 'no per-entity locking' §5.1 lock-free invariant is satisfied because the guard is a same-thread arithmetic check, not a synchronization primitive.

**Risk if wrong:** If a future code path needs to reset a CONSOLIDATED entity (e.g., rehydration with stale data, sleep-pass retry after partial failure), the guard would block a legitimate operation. Mitigation: provide an explicit reset_state() method with louder semantics for the rollback case. Today no caller does backward transitions, so the guard would be a no-op in practice — but the absence of the guard means the next refactor that 'simplifies' run_pass to retry STAGED entities (per Round 2 §2.3 retry intent) silently corrupts the state machine.

**References:** `ARCHITECTURE.md §3`, `ARCHITECTURE.md §7.1`, `src/moneta/types.py:EntityState`, `docs/rounds/round-2.md §2.3`

---

### `persistence-L3-query-dim-mismatch-silent-empty` — High — ARCHITECTURE.md §7.1 locks dim-homogeneity as a hard ValueError 'enforced at upsert time, not at query time, and the error is a hard ValueError — not a silent skip', but query() does silently skip dim-mismatched entries via the per-entry `if len(vec) != dim: continue` guard — so a query whose VECTOR has the wrong dim hits the skip on every stored entry and returns an empty list with no diagnostic, exactly the silent-skip failure mode §7.1 was written to forbid.

**Role:** persistence  **File:** `src/moneta/vector_index.py:113-145`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        q_norm = math.sqrt(q_norm_sq)
        dim = len(vector)
        scored: list[tuple[UUID, float]] = []
        for eid, (vec, _state) in self._records.items():
            if len(vec) != dim:
                continue
```

**Proposed change:** Validate query vector dim against self._dim at the top of query(), symmetric with upsert(): if `self._dim is not None and len(vector) != self._dim` raise ValueError with the same wording as upsert. Then the per-entry `if len(vec) != dim: continue` becomes dead code (defensive but unreachable under the upsert dim guard) and can be removed. Add a unit test that constructs a vector index, upserts a 3-dim vector, queries with a 4-dim vector, and asserts ValueError. The §7.1 letter is enforced at the only entry point that today violates its intent.

**Risk if wrong:** If a caller intentionally uses VectorIndex with heterogeneous dims (no current path does this — embedding_dim is per-MonetaConfig), the proposed enforcement breaks them. Mitigation: the §7.1 locked clause already forbids mixed-dim usage, so any such caller is already outside spec. The §7.1 hazard is exactly 'switch embedders without constructing a fresh VectorIndex' — query-side enforcement makes that mistake observable instead of returning ranking-corrupted-or-empty results silently.

**References:** `ARCHITECTURE.md §7.1`

---

### `persistence-L3-mid-batch-vector-state-divergence` — High — commit_staging's per-memory update_state loop has no transactional boundary; if update_state raises on entity K of N (transient backend error, an enforced state-transition guard from sister finding persistence-L3-update-state-no-transition-guard, or a future LanceDB I/O blip), entries 0..K-1 are CONSOLIDATED in the vector index while K..N-1 retain prior state — within a single commit_staging call, the §7.1-authoritative store splits mid-batch into CONSOLIDATED + STAGED_FOR_SYNC for entities whose USD prims were all authored in the same prior author_stage_batch.

**Role:** persistence  **File:** `src/moneta/sequential_writer.py:106-115`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        for memory in staged:
            self._vector.update_state(memory.entity_id, EntityState.CONSOLIDATED)
        _logger.info("sequential_writer.vector_update count=%d", len(staged))

        return result
```

**Proposed change:** Either (a) wrap the loop in a try/except that on first failure (i) records which entity_ids succeeded, (ii) raises a structured PartialCommitError carrying both the AuthoringResult and the partition (committed_ids, uncommitted_ids), so consolidation.run_pass can advance only the committed set's ECS state to CONSOLIDATED and leave the uncommitted set in STAGED_FOR_SYNC for the next pass to retry; or (b) batch the vector updates into a single transactional call (vector_index.bulk_update_state(ids, state)) that is atomic at the dict-mutation level under CPython GIL. Path (a) is the spec-honest fix: it admits partial failure and exposes recovery state. Path (b) hides partial failure inside an atomic primitive but doesn't help if the underlying store can fail mid-bulk-update (a real concern for any future disk-backed backend).

**Risk if wrong:** Today VectorIndex.update_state is in-memory dict mutation that cannot raise — so the loop is atomic by accident of backend choice. The §7 'orphans benign' clause covers USD-side orphans (USD durable, vector not committed) but is silent on partial vector-side commits. A future LanceDB backend, or the persistence-L3 state-machine guard above, makes the partial-failure path reachable with no documented recovery contract. Compounds with consolidation-L2-stage-partial-batch-atomicity-break and adversarial-L2-multi-entity-vector-failure-untested from prior loops.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §7.1`, `ARCHITECTURE.md §15.2 #3`

---

### `persistence-L3-restore-violates-section-71-dim-immutability` — High — ARCHITECTURE.md §7.1 locks 'Once the first embedding is upserted into the shadow vector index, its dimension is locked for the lifetime of the instance' as the hard invariant, but VectorIndex.restore() unconditionally reassigns self._dim from the snapshot dict — directly mutating the dim mid-instance-lifetime. Today restore() is orphaned (the durability layer rebuilds via upsert calls instead — see persistence-L1-vector-snapshot-orphan) so the violation is unreachable; the moment that orphan is fixed (the architect-L2-vector-authoritative-vs-hydrate-inversion repair path), the §7.1 hard invariant is silently broken on every hydrate.

**Role:** persistence  **File:** `src/moneta/vector_index.py:165-175`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def restore(self, snapshot: dict) -> None:
        """Replace current state with a snapshot produced by `snapshot()`."""
        self._dim = snapshot.get("embedding_dim")
        self._records.clear()
        for rec in snapshot.get("records", []):
```

**Proposed change:** Either (a) raise ValueError if `self._dim is not None and snapshot['embedding_dim'] != self._dim` — preserves §7.1's intent ('callers that need to switch embedders must construct a fresh VectorIndex'); or (b) amend ARCHITECTURE.md §7.1 with a restore-exception clause: 'restore() resets the instance lifetime as if freshly constructed; subsequent upserts must match the restored dim.' Path (a) is correct under the locked clause as written; path (b) is a §9 candidate (spec amendment to a locked invariant). Without one of the two, the snapshot/restore wiring path is a §7.1 letter violation waiting to be enabled.

**Risk if wrong:** If wrong, restore() is never called by production code (the orphan finding documents this), and the violation is theoretical. But persistence-L1-vector-snapshot-orphan is exactly the gap the architect Loop 2 finding wants closed; the moment a future surgery wires DurabilityManager → VectorIndex.restore, the dim-immutability hard invariant collapses on every restart. The fix must land BEFORE the wiring, not after.

**References:** `ARCHITECTURE.md §7.1`, `src/moneta/vector_index.py:upsert`

---

### `consolidation-L3-protected-floor-prune-paradox` — High — A memory with 0 < protected_floor < 0.1 is counted toward the 100-entry protected quota (ARCHITECTURE.md §10's count_protected uses pf > 0.0) but is still prune-eligible because the floor clamps utility at a value below PRUNE_UTILITY_THRESHOLD; the substrate has 'protected' entities that quota-block other deposits AND get destroyed by ordinary pruning — the dual semantics of protected_floor (decay-floor vs prune-immunity) are silently inconsistent.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:120-130`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
PRUNE_UTILITY_THRESHOLD = 0.1
PRUNE_ATTENDED_THRESHOLD = 3
STAGE_UTILITY_THRESHOLD = 0.3
STAGE_ATTENDED_THRESHOLD = 3
```

**Proposed change:** Either (a) make ECS.count_protected only count entities whose floor would actually prevent pruning (floor >= PRUNE_UTILITY_THRESHOLD), aligning quota semantics with the prune-immunity intent of §10's 'backstop against agents flagging everything as protected'; or (b) extend classify() to skip prune for any entity with protected_floor > 0.0, regardless of utility — making 'protected' uniformly mean 'never deleted'. Path (a) is the smaller change; path (b) honors §2.10's English-language semantic of 'protection' more directly. Today the quota mechanism is tuned for path (b) but the prune mechanism implements neither path consistently.

**Risk if wrong:** Reachable when an agent deposits with a small protected_floor (e.g., 0.05) believing it pins the memory. Decay clamps utility at 0.05; selection sees utility=0.05 < 0.1 AND attended_count < 3 and prunes the entity despite its 'protected' status. The agent observes the memory disappearing while still seeing it counted in any future protected-quota check via count_protected at the moment of the pf>0 check (between deposit and prune). The §10 quota cap then prevents NEW protected deposits because old already-pruned protected entities still count.

**References:** `ARCHITECTURE.md §10`, `MONETA.md §2.10`, `src/moneta/ecs.py:count_protected`

---

### `consolidation-L3-vector-state-machine-skips-staged` — High — ARCHITECTURE.md §3 declares the State enum has three values (VOLATILE, STAGED_FOR_SYNC, CONSOLIDATED) and the vector index carries State as a column, but the consolidation flow transitions the vector directly from VOLATILE to CONSOLIDATED — the vector index never observes STAGED_FOR_SYNC because SequentialWriter.commit_staging only calls update_state(CONSOLIDATED). The vector's state machine is a strict subset of ECS's, an asymmetry not documented and not enforced by the Protocol.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:148-173`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
if stage_ids and sequential_writer is not None:
            staged_memories: List[Memory] = []
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.STAGED_FOR_SYNC)
                memory = ecs.get_memory(eid)
                if memory is not None:
                    staged_memories.append(memory)
            for batch_start in range(0, len(staged_memories), MAX_BATCH_SIZE):
                batch = staged_memories[batch_start : batch_start + MAX_BATCH_SIZE]
                result = sequential_writer.commit_staging(batch)
                authoring_at = result.authored_at
            for eid in stage_ids:
                ecs.set_state(eid, EntityState.CONSOLIDATED)
```

**Proposed change:** Either (a) call sequential_writer/vector_index.update_state(STAGED_FOR_SYNC) immediately after ecs.set_state(STAGED_FOR_SYNC) and before commit_staging, so vector and ECS state evolve in lockstep; or (b) document explicitly in ARCHITECTURE.md §3 that the vector index implements only {VOLATILE, CONSOLIDATED} and STAGED_FOR_SYNC is an ECS-only intermediate state — and remove the state parameter from VectorIndexTarget.update_state if it cannot meaningfully observe STAGED. Today the API surface promises three states and delivers two, and the cross-store divergence window (from set_state(STAGED) to vector update_state(CONSOLIDATED)) is the exact window where Loop 2's hydrate-inversion bug operates.

**Risk if wrong:** Loop 3 theme bullet calls out 'vector-index state machine soundness across VOLATILE → STAGED_FOR_SYNC → CONSOLIDATED' as an explicit probe target. Today no consumer reads vector state during the staging window, so the asymmetry is invisible — but the API surface invites consumers to do so (vector_index.get_state is a public method, returning the state column). A future reader path that uses vector.get_state to ask 'is this entity pending consolidation?' will never see STAGED_FOR_SYNC and will silently produce wrong answers.

**References:** `ARCHITECTURE.md §3`, `src/moneta/sequential_writer.py:commit_staging`, `src/moneta/vector_index.py:update_state`

---

### `consolidation-L3-stuck-staged-no-recovery` — High — classify() iterates only entities in EntityState.VOLATILE — entities stuck in STAGED_FOR_SYNC from a prior failed pass (mid-batch raise, kill -9 between commit_staging and the post-loop set_state(CONSOLIDATED), or any future operator-driven recovery) are invisible to subsequent passes; the §6 selection criteria's 'state != VOLATILE: continue' filter is the structural gap that makes Round 2's 'remain STAGED_FOR_SYNC until UsdStage.Save() successfully returns. If locked, abort and retry next cycle' retry promise unimplementable.

**Role:** consolidation  **File:** `src/moneta/consolidation.py:114-135`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `adversarial-L2-staged-retry-not-implemented`

**Evidence:**

```
        prune_ids: List[UUID] = []
        stage_ids: List[UUID] = []
        for memory in ecs.iter_rows():
            if memory.state != EntityState.VOLATILE:
                continue
```

**Proposed change:** Extend classify (or add a new run_pass step before classify) to detect STAGED_FOR_SYNC entities whose corresponding vector_index state is still VOLATILE (i.e., commit_staging never reached vector.update_state) and demote them back to VOLATILE for re-classification — implementing Round 2's retry semantics. Alternatively, add a 'stale STAGED' watchdog that flags entities in STAGED_FOR_SYNC for >N seconds and surfaces them via a new harness-level operator (NOT a fifth agent op). The current implementation has no recovery path; once an entity gets stuck in STAGED, it is invisible to every future pass and only an operator manually mutating ecs._state can recover it.

**Risk if wrong:** Compounds Loop 2's consolidation-L2-stage-partial-batch-atomicity-break (which identified the partial-failure CAUSE). Without a recovery mechanism, a single transient flush failure mid-pass produces permanently invisible entities. The Phase 2/3 envelope assumes consolidation is durable forward-progress; this gap means partial failures accumulate unboundedly.

**References:** `docs/rounds/round-2.md §2.3`, `ARCHITECTURE.md §6`, `consolidation-L2-stage-partial-batch-atomicity-break (Loop 2)`

---

### `test-L3-protected-floor-consolidation-trap-untested` — High — The Phase 3 known limitation #1 from `docs/phase3-closure.md` ('Memories with `protected_floor=1.0` never match staging criteria because the decay floor keeps utility at 1.0 after every eval point') is a prose-only claim with no asserting test; the only protected-routing test (`test_protected_floor_routes_to_protected_sublayer`) deliberately uses `protected_floor=0.2` (below stage threshold 0.3) so the entity *can* stage, leaving the inverse — high floors *prevent* automatic staging — completely untested. A future surgery that fixes the limitation (or accidentally regresses by changing decay clamp semantics) would land green.

**Role:** test  **File:** `tests/integration/test_end_to_end_flow.py:212-260`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_protected_floor_routes_to_protected_sublayer(
        self, fast_decay_moneta: Moneta
    ) -> None:
        """A protected entity stages to cortex_protected.usda per §8."""
        m = fast_decay_moneta
        eid = m.deposit("pinned", [1.0, 0.0], protected_floor=0.2)
```

**Proposed change:** Add `TestProtectedFloorConsolidationTrap` to `tests/integration/test_end_to_end_flow.py` with: (a) `test_floor_one_never_stages_after_decay` — deposit with `protected_floor=1.0`, signal 5 times, fast-forward to t+24h, run sleep pass, assert `staged==0` and the entity remains VOLATILE; (b) `test_floor_above_stage_threshold_never_stages` — same but `protected_floor=0.5` (above STAGE_UTILITY_THRESHOLD=0.3); (c) `test_floor_below_stage_threshold_can_stage` — `protected_floor=0.2` matches the existing test, retained as the boundary case. Each docstring cites `docs/phase3-closure.md` §4 #1 explicitly so the test fires as a tripwire if the limitation is later 'fixed' without a paired test update.

**Risk if wrong:** Locking a known limitation by test is the discipline that separates 'documented behavior' from 'accidental behavior'. Without it, a v1.1 surgery aimed at adding protected-memory consolidation trigger (listed in `docs/phase3-closure.md` §6 'Next actions') has no regression anchor; a partial implementation that reduces but doesn't eliminate the trap would silently land. If wrong (the limitation is not actually invariant), the test surfaces the inconsistency between code and closure record.

**References:** `docs/phase3-closure.md §4 known limitation #1`, `ARCHITECTURE.md §6`, `ARCHITECTURE.md §10`, `src/moneta/consolidation.py STAGE_UTILITY_THRESHOLD`

---

### `test-L3-decay-all-backward-clock-untested` — High — `TestDecayValue::test_negative_dt_guarded_to_zero` proves the function-level Δt clamp prevents utility amplification on a single backward-time call, but no test covers `ECS.decay_all`'s timestamp-pollution behavior identified at Loop 2 (`adversarial-L2-decay-backward-clock-propagates`): the unconditional `self._last_evaluated[i] = now` write propagates a backward-clock value into every entity's last_evaluated, biasing every subsequent forward decay. The locked §4 formula is preserved per-call but the multi-call timestamp invariant is not.

**Role:** test  **File:** `tests/unit/test_decay.py:85-95`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_negative_dt_guarded_to_zero(self) -> None:
        """Clock skew: last_evaluated in the future → no amplification."""
        lam = lambda_from_half_life(60.0)
        # "now" is 100s earlier than last_evaluated
        result = decay_value(0.8, 100.0, 0.0, lam, 0.0)
        # Δt clamps to 0 → utility unchanged, not amplified
        assert result == pytest.approx(0.8)
```

**Proposed change:** Add `TestEcsDecayAllClockSkew` to `tests/unit/test_ecs.py` (or a new `test_decay_integration.py`) with: (a) `test_decay_all_backward_then_forward_decays_correct_delta` — seed an entity at t=100 with utility=1.0, call `ecs.decay_all(lam, now=50)` (backward), then `ecs.decay_all(lam, now=160)` (forward 60s = one half-life from t=100); assert utility decayed by exactly the 60s delta from the original last_evaluated, not from the polluted t=50. (b) `test_decay_all_backward_does_not_pollute_last_evaluated` — assert `_last_evaluated[i]` is monotonically non-decreasing across decay_all calls. The current behavior fails (b).

**Risk if wrong:** NTP backward steps under `ntpd -g` are uncommon but not rare on long-running processes; virtual-clock test injection (Phase 1's `synthetic_session.py` uses VirtualClock with monotonic-forward semantics, which is exactly why the bug is invisible). Once a test fixture or a real production NTP step injects a backward time, every subsequent decay biases against the polluted timestamp. The constitution's Loop 3 'decay clock-skew Δt clamp' bullet calls for exactly this kind of multi-call probe.

**References:** `ARCHITECTURE.md §4`, `src/moneta/ecs.py:decay_all`, `Constitution §10 Loop 3 theme bullet 'decay clock-skew Δt clamp'`, `adversarial-L2-decay-backward-clock-propagates`

---

### `test-L3-deposit-dim-mismatch-orphan-untested` — High — `Moneta.deposit` calls `ecs.add` then `vector_index.upsert`; if the upsert raises (the locked §7.1 dim-mismatch ValueError is the documented trip path), the ECS row is orphaned — invisible to query but counted by `count_protected` and `iter_rows`. Loop 2 `substrate-L2-deposit-no-rollback-on-vector-failure` identifies the bug; no test in `TestDepositContract` exercises a second deposit with a dim-mismatched embedding to confirm the §7.1 invariant fires AND that the substrate state remains consistent on the failure.

**Role:** test  **File:** `tests/unit/test_api.py:149-175`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
class TestDepositContract:
    def test_deposit_returns_uuid(self, fresh_moneta: Moneta) -> None:
        eid = fresh_moneta.deposit("hello", [1.0, 0.0])
        assert isinstance(eid, UUID)

    def test_deposit_is_retrievable(self, fresh_moneta: Moneta) -> None:
        eid = fresh_moneta.deposit("hello", [1.0, 0.0])
        results = fresh_moneta.query([1.0, 0.0])
        assert len(results) == 1
        assert results[0].entity_id == eid
```

**Proposed change:** Add `TestDepositDimMismatch` to `tests/unit/test_api.py`: (a) `test_dim_mismatched_second_deposit_raises_value_error` — first deposit with `[1.0, 0.0]`, second with `[1.0, 0.0, 0.0]`; assert `pytest.raises(ValueError)` referencing §7.1; (b) `test_dim_mismatch_leaves_no_orphan_ecs_row` — after the raise, assert `m.ecs.n == 1` (only the first deposit), `len(m.vector_index) == 1`, `m.query([1.0, 0.0]) == [first_eid]`. Today (b) FAILS because the ECS row from the failed deposit persists. The test pins the §7.1 contract AND the cross-store consistency requirement that Loop 2 identifies as missing.

**Risk if wrong:** The §7.1 invariant is locked spec; the cross-store consistency on failure is implicit but follows from §7's 'vector index is authoritative for what exists'. Without the test, a future Persistence Engineer 'fix' for the orphan that reorders to vector-first creates a SYMMETRIC orphan (Loop 2 `adversarial-L2-deposit-reorder-creates-new-orphan` identifies this). Either ordering needs the test to lock the contract explicitly.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §7.1`, `src/moneta/api.py:Moneta.deposit`, `substrate-L2-deposit-no-rollback-on-vector-failure`

---

### `test-L3-vector-state-machine-never-staged` — High — The vector index state machine has only TWO states in practice (VOLATILE on deposit, CONSOLIDATED on commit_staging via `vector_index.update_state(eid, EntityState.CONSOLIDATED)`); STAGED_FOR_SYNC is an ECS-only intermediate state never written to the vector index. This invariant is enforced by code path (sequential_writer skips the STAGED transition on the vector side) but no test asserts it — a future change that adds `vector_index.update_state(eid, STAGED_FOR_SYNC)` for 'consistency' would silently land.

**Role:** test  **File:** `tests/integration/test_end_to_end_flow.py:60-75`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_deposit_writes_to_vector_index(
        self, fresh_moneta: Moneta
    ) -> None:
        """ARCHITECTURE.md §7: vector index is authoritative for what exists."""
        eid = fresh_moneta.deposit("x", [1.0, 0.0])
        assert fresh_moneta.vector_index.contains(eid)
        assert (
            fresh_moneta.vector_index.get_state(eid)
            == EntityState.VOLATILE
        )
```

**Proposed change:** Add `test_vector_index_state_machine_never_holds_staged_for_sync` to `tests/integration/test_end_to_end_flow.py`: deposit, signal 3 times, force staging via `_force_staging`, run sleep pass; AT EACH transition observe `m.vector_index.get_state(eid)` and assert it is exclusively `VOLATILE` (before pass) or `CONSOLIDATED` (after pass) — never `STAGED_FOR_SYNC`. The mid-pass observation requires hooking SequentialWriter or instrumenting commit_staging; if invasive, add a structural AST guard in a separate unit test that scans `consolidation.py` for `vector_index.update_state(.*STAGED_FOR_SYNC)` and fails if found.

**Risk if wrong:** The asymmetric state machine (ECS has 3 states, vector has 2) is correct per §7 — 'vector index is authoritative for what exists', and STAGED is an in-flight ECS-side notion — but is preserved by accident, not by construction or test. If a maintainer reads the EntityState enum and adds vector-side STAGED transitions for 'symmetry', the §7 atomicity reasoning shifts subtly because vector-side state would no longer be a simple existence flag.

**References:** `ARCHITECTURE.md §3`, `ARCHITECTURE.md §7`, `src/moneta/sequential_writer.py:commit_staging`, `Constitution §10 Loop 3 theme bullet 'vector-index state machine soundness'`

---

### `documentarian-L3-api-md-pre-handle-api-throughout` — High — docs/api.md still documents the pre-v1.1.0 module-level singleton API throughout — `moneta.init()`, free-function `moneta.deposit(...)` / `moneta.query(...)` / `moneta.signal_attention(...)` / `moneta.run_sleep_pass()` — but the singleton was excised by the v1.1.0 surgery and the only constructor today is `Moneta(config)` per api.py; the canonical user-facing API reference is wrong end-to-end and violates the CLAUDE.md hard-rule Documentarian contract (≤1 PR lag).

**Role:** documentarian  **File:** `docs/api.md:22-45`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
Every Moneta process must call `init()` once before any agent operation:

```python
import moneta
moneta.init()                         # defaults (in-memory, 6h half-life)
moneta.init(half_life_seconds=60)     # minutes-scale half-life
moneta.init(config=moneta.MonetaConfig(
    half_life_seconds=3600,
    snapshot_path="/var/moneta/ecs.json",
    wal_path="/var/moneta/wal.jsonl",
    mock_target_log_path="/var/moneta/usd_authorings.jsonl",
))
```

Calling `init()` a second time resets all substrate state.
```

**Proposed change:** Rewrite docs/api.md from the top to the handle API matching README's quickstart: replace the Setup section's `moneta.init(...)` examples with `with Moneta(MonetaConfig.ephemeral()) as m:` and `with Moneta(MonetaConfig(storage_uri=..., snapshot_path=..., wal_path=..., ...))`. Replace every free-function call (moneta.deposit, moneta.query, moneta.signal_attention, moneta.run_sleep_pass, moneta.get_consolidation_manifest) with the corresponding `m.<method>` form. Document the no-arg trap (`Moneta()` raises TypeError), the storage_uri exclusivity rule, and the `MonetaResourceLockedError` raised by a duplicate-URI construction. Cross-link DEEP_THINK_BRIEF_substrate_handle.md as the surgery rationale.

**Risk if wrong:** If wrong, docs/api.md is the source of truth most consumers and reviewers reach first; a stale reference teaches the wrong shape and any new consumer copy-pasting the Setup snippet hits AttributeError on `moneta.init`. The lag is two surgeries deep (v1.1.0 + v1.2.0-rc1) — well past the ≤1-PR contract.

**References:** `CLAUDE.md 'Hard rules'`, `DEEP_THINK_BRIEF_substrate_handle.md §5.3`, `src/moneta/api.py:Moneta`, `README.md 'Hello world'`

---

### `documentarian-L3-api-md-monetanotinitialized-stale` — High — docs/api.md's Errors section lists `MonetaNotInitializedError` as a documented exception, but that error type was removed when the singleton was replaced — api.py exports only `ProtectedQuotaExceededError` and `MonetaResourceLockedError`; consumers wiring exception handlers from this doc against `MonetaNotInitializedError` get an ImportError, and the doc fails to mention `MonetaResourceLockedError` (the one new exception the v1.1.0 surgery introduced).

**Role:** documentarian  **File:** `docs/api.md:156-162`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
## Errors

- `MonetaNotInitializedError` — raised when an operation is called
  before `init()`.
- `ProtectedQuotaExceededError` — raised when a protected deposit would
  exceed the 100-entry quota (ARCHITECTURE.md §10). Phase 1: `deposit`
  raises. Phase 3: operator-facing unpin tool.
```

**Proposed change:** Remove the `MonetaNotInitializedError` bullet (the symbol no longer exists). Add `MonetaResourceLockedError — raised when `Moneta(config)` is constructed against a `storage_uri` already held by another live handle in this process; release via `close()` or context-manager exit before reconstructing.` Update the `ProtectedQuotaExceededError` bullet to read 'exceed `config.quota_override` (default 100)' since the quota is now per-handle, not a module-level constant.

**Risk if wrong:** Consumers writing `except moneta.MonetaNotInitializedError` against this doc get an `AttributeError` at import time. The omission of `MonetaResourceLockedError` leaves the v1.1.0 marquee invariant undocumented at the user-API level — the only consumer-visible failure mode of the URI exclusivity contract has no entry in the Errors section.

**References:** `src/moneta/api.py exports list`, `src/moneta/__init__.py`, `DEEP_THINK_BRIEF_substrate_handle.md §5.4`

---

### `architect-L4-rotation-cap-bypassed-on-reopen` — High — ARCHITECTURE.md §15.2 constraint #1 (50k prims per sublayer rotation) is enforced only against an in-process `_prim_counts` counter that resets to 0 on every UsdTarget construction; when `Sdf.Layer.CreateNew` returns None and the FindOrOpen fallback reopens an existing on-disk sublayer (the cross-session and same-day-restart case), the counter starts at 0 regardless of how many prims the file already contains, so the next session can author up to 50k MORE prims to a sublayer that may already hold 49k — net file size 99k, silently breaching the locked envelope cap.

**Role:** architect  **File:** `src/moneta/usd_target.py:180-215`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `usd-L3-prim-counts-coldstart-bypass-rotation-cap`

**Evidence:**

```
        if self._in_memory:
            layer = Sdf.Layer.CreateAnonymous(name)
        else:
            layer_path = str(self._log_path / name)
            layer = Sdf.Layer.CreateNew(layer_path)
            if layer is None:
                layer = Sdf.Layer.FindOrOpen(layer_path)

        self._layers[name] = layer
        self._prim_counts[name] = 0
```

**Proposed change:** When the FindOrOpen fallback fires, count the prim specs already present in the layer (`sum(1 for p in layer.rootPrims)` or a recursive Sdf walk) and seed `self._prim_counts[name]` with the actual count, NOT zero. Alternatively, if cross-session hydration is genuinely deferred per phase3-closure.md §4, make `CreateNew` returning None a hard error rather than a silent FindOrOpen fallback — operators get a loud signal instead of a silently-over-cap sublayer. Pair with a regression test: pre-create a `cortex_X.usda` file with N>cap prims, instantiate UsdTarget against the parent dir, author one entity, assert rotation triggered (or count seeded to N). Closes the architect-side framing of usd-L3-prim-counts-coldstart-bypass-rotation-cap from Loop 3.

**Risk if wrong:** Cross-session USD hydration is documented as deferred (phase3-closure.md §4 limitation), so the FindOrOpen path is rarely exercised today. But the path EXISTS — same-day process restart, partial-cleanup-after-test, two UsdTargets pointing at the same `usd_target_path` (the substrate-L2-storage-uri-no-normalization gap), or any v1.1+ surgery that lights up cross-session hydration without auditing this code path silently breaches §15.2 #1. The Phase 2 cost model is sized against the cap; breaching it pushes back into Yellow tier latencies the §15.6 narrow-lock projection no longer covers.

**References:** `ARCHITECTURE.md §15.2 #1`, `docs/phase3-closure.md §4 (cross-session hydration deferred)`, `usd-L3-prim-counts-coldstart-bypass-rotation-cap`

---

### `test-L4-batch-cap-test-doesnt-verify-batching-actually-happens` — High — test_large_staging_respects_500_prim_batch_cap deposits MAX_BATCH_SIZE+50 entities and asserts the final prim count, but never verifies that author_stage_batch was actually called multiple times — a regression that deletes the `for batch_start in range(0, len(staged_memories), MAX_BATCH_SIZE)` loop in consolidation.run_pass and authors the entire 550-entity batch in a single call would still pass this test, silently violating ARCHITECTURE.md §15.2 #3.

**Role:** test  **File:** `tests/integration/test_real_usd_end_to_end.py:222-264`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def test_large_staging_respects_500_prim_batch_cap(
        self, fresh_moneta_usd: Moneta
    ) -> None:
        """ARCHITECTURE.md §15.2 #3: max 500 prims per consolidation batch.

        Deposits more than ``MAX_BATCH_SIZE`` entities, forces them all
        to staging criteria, and verifies the sleep pass succeeds
        (meaning batching worked — without batching, a single
        ``commit_staging`` call with >500 entities would still work,
        but the batching is visible in the authored prim count spread
        across batches)."""
```

**Proposed change:** Wrap the authoring target with a counting spy that records every author_stage_batch invocation (call count + entity count per call). After run_sleep_pass, assert the spy was called exactly ceil(550/500) = 2 times, that the first call carried <=500 entities and the second carried the remainder, and that the sum equals 550. Without this, the test only proves the substrate authors entities — not that it batches them. The docstring's stated intent ('the batching is visible in the authored prim count spread across batches') is unverified because the test doesn't actually inspect the batch boundaries.

**Risk if wrong:** If the substrate ever loses the batch loop (e.g., during a refactor that 'simplifies' run_pass after deciding the batch cap is enforced elsewhere), this test passes green and the §15.2 #3 hard constraint is silently violated. The Phase 2 cost model is sized against batch ≤500; super-batches would push the substrate back into Yellow stall territory.

**References:** `ARCHITECTURE.md §15.2 #3`, `src/moneta/consolidation.py:run_pass batch loop`, `src/moneta/consolidation.py:MAX_BATCH_SIZE`

---

### `test-L4-max-batch-size-constant-not-pinned` — High — ARCHITECTURE.md §15.2 #3 locks MAX_BATCH_SIZE at 500 prims as a hard constraint, but no test asserts the literal constant value — `from moneta.consolidation import MAX_BATCH_SIZE` is used in test arithmetic (`n = MAX_BATCH_SIZE + 50`) without an explicit `assert MAX_BATCH_SIZE == 500`. A change in consolidation.py from 500 to 5000 (silently relaxing the cap by 10x) would land green because every test that uses MAX_BATCH_SIZE references the symbol, not the value.

**Role:** test  **File:** `tests/integration/test_real_usd_end_to_end.py:10-25`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
from moneta.consolidation import MAX_BATCH_SIZE  # noqa: E402
```

**Proposed change:** Add `tests/unit/test_consolidation.py::TestEnvelopeConstants::test_max_batch_size_locked_at_500` asserting `consolidation.MAX_BATCH_SIZE == 500` with a docstring citing ARCHITECTURE.md §15.2 #3 as the authority and naming the change as a §9-escalation candidate. Same pattern for DEFAULT_MAX_ENTITIES==10000, DEFAULT_IDLE_TRIGGER_MS==5000, and PRUNE/STAGE thresholds (0.1 / 0.3 / 3 — locked Round 2 defaults per ARCHITECTURE.md §6).

**Risk if wrong:** The §15.2 envelope was sized empirically against batch ≤500. A silent change to the constant — perhaps as part of a 'tuning experiment' or a misread of the spec — has no structural defense. The integration test test_large_staging_respects_500_prim_batch_cap uses MAX_BATCH_SIZE+50 = 550 as its threshold; if MAX_BATCH_SIZE became 5000, the test would deposit 5050 entities and still pass (one super-batch), with no assertion that the cap was honored.

**References:** `ARCHITECTURE.md §15.2 #3`, `src/moneta/consolidation.py:MAX_BATCH_SIZE`, `Constitution §10 Loop 4 'Batch ≤500 enforced before commit'`

---

### `test-L4-default-rotation-cap-not-pinned-and-default-not-exercised` — High — ARCHITECTURE.md §15.2 #1 locks rotation at 50,000 prims per sublayer; usd_target.py defines `DEFAULT_ROTATION_CAP = 50_000`. Every test exercising rotation overrides it to 5 or 10 for test speed, and no test asserts the literal default value. A regression that lowered the default to 500 (causing 100x more rotations and breaking the §15.2 cost model) or raised it to 5_000_000 (effectively disabling rotation) would land green.

**Role:** test  **File:** `tests/unit/test_usd_target.py:185-220`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        cap = 10
        target = UsdTarget(log_path=None, rotation_cap=cap)

        # Author exactly `cap` memories — should fill the first sublayer
        first_batch = [_make_memory() for _ in range(cap)]
        target.author_stage_batch(first_batch)
```

**Proposed change:** Add `tests/unit/test_usd_target.py::TestEnvelopeDefaults::test_default_rotation_cap_locked_at_50000` asserting `from moneta.usd_target import DEFAULT_ROTATION_CAP; assert DEFAULT_ROTATION_CAP == 50_000` with docstring citing ARCHITECTURE.md §15.2 #1. Additionally, add `test_default_construction_uses_50k_cap` that constructs `UsdTarget(log_path=None)` (no rotation_cap override) and inspects `target._rotation_cap == 50_000` — exercises the default path without forcing 50k authoring.

**Risk if wrong:** The 50k cap is the primary lever against accumulated serialization tax (per Phase 2 closure §3 constraint #1). A silent change here propagates through every operational deployment without surfacing in any test. Constitution §10 Loop 4 explicitly authorizes 'Sublayer rotation at 50k actually triggered?' as a probe target; today the answer is 'rotation triggered at 5 or 10 in tests, never at 50k'.

**References:** `ARCHITECTURE.md §15.2 #1`, `src/moneta/usd_target.py:DEFAULT_ROTATION_CAP`, `Constitution §10 Loop 4 theme bullet`

---

### `test-L4-idle-trigger-boundary-untested` — High — ARCHITECTURE.md §15.2 #2 locks 'Consolidation runs only during inference idle windows > 5 seconds' as the Yellow-tier scheduling discipline. ConsolidationRunner.should_run implements `now_ms - self._last_activity_ms >= self._idle_trigger_ms` with default 5000ms — but no test exercises this boundary in either direction. Integration tests bypass should_run entirely by calling run_pass directly with explicit `now=` parameters; the should_run trigger logic is exercised by no test at all.

**Role:** test  **File:** `tests/integration/test_end_to_end_flow.py:1-50`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
Design note — fast-forward via ``now`` parameter
------------------------------------------------
``consolidation.ConsolidationRunner.run_pass`` takes ``now`` as an
explicit parameter so tests can fast-forward time without
``time.sleep``. Several tests here construct a "future" timestamp and
call ``run_pass(..., now=future)`` directly to drive decay past the
selection thresholds in milliseconds of wall-clock time.
```

**Proposed change:** Add to the proposed tests/unit/test_consolidation.py: (a) test_idle_trigger_below_5s_does_not_fire — runner.mark_activity(now_ms=0), assert should_run(ecs, now_ms=4999) returns False; (b) test_idle_trigger_at_exactly_5s_fires — same setup, should_run(ecs, now_ms=5000) returns True; (c) test_pressure_trigger_overrides_idle — fill ecs to max_entities, mark_activity(now=t), assert should_run(ecs, t+1ms) returns True (pressure dominates); (d) test_no_activity_marker_disables_idle_trigger — fresh runner with _last_activity_ms=0, should_run returns False forever until mark_activity fires (current behavior; pin it as contract).

**Risk if wrong:** Integration tests bypass should_run by calling run_pass directly, so a refactor that breaks should_run's idle math (e.g., uses a wrong attribute, returns True unconditionally, or never fires after the first activity) would not surface anywhere. The §15.2 #2 'Yellow-tier scheduling per Round 3' discipline is the load-bearing mechanism that keeps consolidation out of the inference latency path; an untested trigger is an invisible Yellow-to-Red regression.

**References:** `ARCHITECTURE.md §15.2 #2`, `src/moneta/consolidation.py:should_run`, `src/moneta/consolidation.py:DEFAULT_IDLE_TRIGGER_MS`

---

### `test-L4-synthetic-session-only-mock-target` — High — The 30-min synthetic session — Phase 1 completion gate AND the only documented load-tier regression test — uses MonetaConfig.ephemeral() which defaults to use_real_usd=False, exercising MockUsdTarget exclusively. The §15.2 envelope is locked against real USD performance characteristics (sublayer rotation at 50k, narrow writer lock per §15.6, real Sdf authoring); the synthetic session never touches the real USD writer that ships in v1.0.0+, so the load gate measures the wrong substrate.

**Role:** test  **File:** `tests/load/synthetic_session.py:255-285`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    # 5-minute half-life — short enough to exercise decay through a
    # 30-minute virtual session, long enough that fresh deposits aren't
    # aggressively pruned by the first sleep pass.
    config = MonetaConfig.ephemeral(
        half_life_seconds=300.0, max_entities=10_000
    )
    with Moneta(config) as m:
```

**Proposed change:** Add a sibling test `tests/load/synthetic_session_real_usd.py` (or a parametrized variant of the existing test) that runs the same 30-min session with `use_real_usd=True` and `usd_target_path=tmp_path`. Mark `@pytest.mark.load` and pxr-gate via importorskip. Assert (a) Tier 1 architectural invariants identical to the mock run, (b) all 1500+ deposits actually reach disk via flush(), (c) sublayer rotation never fires at default cap=50000 (current scale shouldn't trigger it; pin that as contract), (d) the run completes within wall-clock budget that catches gross regressions (e.g., 60s ceiling for the 30-min virtual session under in-memory pxr layers). Without this, real USD has zero load-test regression coverage.

**Risk if wrong:** The Phase 3 closure record §4 lists 'usd-core pip path support, CI pipeline for dual-interpreter testing' as a known gap. Today the synthetic session ships green under plain Python with the mock target, and the real USD writer is exercised only by ~6 small-scale integration tests. A pxr upgrade or a usd_target.py refactor that subtly breaks under sustained load (Sdf.ChangeBlock memory growth, layer reference leaks, _layers dict bloat) has no detection mechanism. The marquee 'synthetic 30-minute session' load gate from MONETA.md §4 is mock-only.

**References:** `MONETA.md §4 Phase 1 completion gate`, `ARCHITECTURE.md §15.2`, `ARCHITECTURE.md §15.6`, `docs/phase3-closure.md §4`

---

### `test-L4-no-substrate-side-envelope-instrumentation` — High — The §15.2 #4 'LanceDB shadow commit budget: ≤15ms p99' and the §15.6 'p95 reader stall projected at ~10–30ms at operational batch sizes' are envelope constraints stated as hard build-time invariants — but no test measures any latency property of the running substrate, and the substrate emits no histogram, p99 counter, or warning log when commit_staging exceeds budget. Adherence relies entirely on one-off benchmark runs that never enter CI; envelope violation is undetectable from inside the substrate.

**Role:** test  **File:** `tests/integration/test_sequential_writer_ordering.py:1-50`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
4. **LanceDB shadow commit budget: ≤ 15ms p99.** The 50ms shadow_commit case is where 6/9 Red excursions live. If the 15ms budget cannot be met with LanceDB defaults, the Persistence Engineer surfaces it as a §9 Trigger 2 escalation, not a silent acceptance.
```

**Proposed change:** Add `tests/integration/test_envelope_instrumentation.py` with: (a) test_commit_staging_logs_warning_when_authoring_exceeds_budget — wrap authoring_target with a target that sleeps 25ms in author_stage_batch, run a sleep pass, assert that a WARNING-level log was emitted citing the §15.2 #4 budget; (b) test_sequential_writer_records_per_phase_timing — extend SequentialWriter to record per-phase elapsed time on AuthoringResult (or a sibling EnvelopeMetrics record), assert the metrics surface the authoring/save/vector phases distinctly. The substrate-side instrumentation is out of role for Test, but the test gap that would force its existence is in scope. Filing here surfaces the missing tripwire.

**Risk if wrong:** Phase 1's in-memory VectorIndex has zero shadow commit cost, so the §15.2 #4 budget is automatically satisfied today by accident of backend choice. When LanceDB lands (deferred per docs/phase3-closure.md §4 #5), no test will detect a 30ms commit time silently breaking the budget. The §15.2 closure explicitly demands '§9 Trigger 2 escalation, not silent acceptance' — but with no instrumentation, the escalation cannot fire because the violation is invisible. Letter satisfied at the spec level; intent (operator-detectable budget violation) has no implementation site.

**References:** `ARCHITECTURE.md §15.2 #4`, `ARCHITECTURE.md §15.6`, `Constitution §10 Loop 4 'Shadow-commit ≤15ms p99 instrumented?'`

---

### `substrate-L4-ecs-n-counts-all-states-mask-volatile` — High — ECS exposes only `n` / `__len__` returning total row count across all EntityState values; the consolidation runner consumes this as `ecs.n >= self._max_entities` but ARCHITECTURE.md §6 specifies the trigger as 'ECS volatile count exceeds MAX_ENTITIES' — substrate's missing `volatile_count` primitive forces consolidation into a spec-incorrect read, and combined with adversarial-L3-staged-classify-uses-state-volatile-only (CONSOLIDATED never evicts) the trigger fires permanently once total crosses MAX_ENTITIES, breaking the §15.2 #2 idle-window scheduling discipline by promoting MAX_ENTITIES to a continuous (not pressure) trigger.

**Role:** substrate  **File:** `src/moneta/ecs.py:38-48`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def __len__(self) -> int:
        return len(self._ids)

    @property
    def n(self) -> int:
        """Number of live entities."""
        return len(self._ids)
```

**Proposed change:** Add `volatile_count(self) -> int` to ECS that returns `sum(1 for s in self._state if s == EntityState.VOLATILE)` (or maintain a running counter incremented in add/hydrate_row and decremented in remove/set_state when transitioning out of VOLATILE — symmetric with the count_protected optimization in substrate-L3-count-protected-on-every-deposit). Update consolidation.should_run to use `ecs.volatile_count() >= self._max_entities`. The §6 trigger then fires on operational hot-tier pressure, not on lifetime cumulative count, and §15.2 #2 idle scheduling remains the dominant trigger.

**Risk if wrong:** If wrong (the spec INTENT is total ECS size, not volatile-only), then the implementation is correct and the finding is doc-only. But the §6 text is unambiguous ('volatile count') and the implementation drifted. Without the fix, a long-running session that has accumulated >MAX_ENTITIES CONSOLIDATED entities triggers MAX_ENTITIES on EVERY mark_activity call regardless of idle state, defeating §15.2 #2's 'consolidation runs only during inference idle windows > 5 seconds' contract.

**References:** `ARCHITECTURE.md §6`, `ARCHITECTURE.md §15.2 #2`, `src/moneta/consolidation.py:should_run`, `adversarial-L3-staged-classify-uses-state-volatile-only`

---

### `substrate-L4-decay-all-on-query-path-no-envelope-guard` — High — ecs.decay_all is O(n) Python-level math.exp loop fired at every decay evaluation point — including api.Moneta.query (eval point 1, on the agent-blocking critical path) — with no envelope guard, no batch cap, no instrumentation; at MAX_ENTITIES=10000 each query pays 10k math.exp + 10k list-index-write calls before any vector search, which can dominate the §15.2 #6 reader throughput envelope (~41Hz achieved vs 60Hz requested ~ 24ms median budget per query) entirely on substrate side, before USD authoring contention even enters.

**Role:** substrate  **File:** `src/moneta/ecs.py:193-210`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def decay_all(self, lam: float, now: float) -> None:
        """Lazy exponential decay across all live entities.

        Called at evaluation points 1 (before retrieval) and 2 (after
        attention reduce). Decayed values are clamped to `protected_floor`.
        """
        for i in range(len(self._ids)):
            self._utility[i] = decay_value(
                self._utility[i],
                self._last_evaluated[i],
                self._protected_floor[i],
                lam,
                now,
            )
            self._last_evaluated[i] = now
```

**Proposed change:** Three-step defense: (a) add per-call latency capture via time.perf_counter() with a logger.warning at INFO if duration exceeds a configurable budget (default 10ms, well below the §15.2 #6 derived ~24ms query budget); (b) document in the docstring that decay_all is O(n) Python-level and that callers operating in the §15.2 envelope (MAX_ENTITIES=10000) should expect ~5-15ms per call on commodity hardware — anchor the cost so future regressions are visible; (c) consider lazy per-entity decay in query() (decay only the entities returned by vector_index.query, not all 10k) — preserves §4 'evaluation point 1 before retrieval' literal but at O(limit) instead of O(n). Path (c) is a substantive optimization requiring Architect ruling on whether §4 'before retrieval' is satisfied by post-vector-hit decay (the entities not in the result don't need fresh utility values for that specific query).

**Risk if wrong:** If wrong (decay_all cost is negligible at envelope sizes), the finding is over-cautious — but the substrate currently has zero observability into actual cost, so the answer is empirically unknown today. The Phase 2 benchmark sized the §15.2 envelope against USD lock-and-rebuild tax and shadow commit budget; substrate-side decay tax was implicitly assumed negligible without measurement. A regression that adds a math.log call to decay_value or switches to numpy-without-vectorization could silently double query latency before any test catches it.

**References:** `ARCHITECTURE.md §4`, `ARCHITECTURE.md §15.2 #5`, `ARCHITECTURE.md §15.2 #6`, `src/moneta/api.py:Moneta.query`

---

### `substrate-L4-shadow-commit-budget-no-substrate-instrumentation` — High — ARCHITECTURE.md §15.2 #4 locks 'LanceDB shadow commit budget: ≤ 15ms p99' as a build-time constraint and mandates §9 Trigger 2 escalation if unmet, but Moneta.deposit (and run_sleep_pass which drives commit_staging) calls vector_index.upsert / update_state with zero timing capture — the substrate has no observability path to detect, log, or escalate when the 15ms budget is violated; the constraint exists in spec but is unverifiable from substrate code, defeating the §9 Trigger 2 escalation discipline by construction.

**Role:** substrate  **File:** `src/moneta/api.py:275-285`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        self.ecs.add(
            entity_id=entity_id,
            payload=payload,
            embedding=embedding,
            utility=1.0,
            protected_floor=protected_floor,
            state=EntityState.VOLATILE,
            now=now,
        )
        self.vector_index.upsert(
            entity_id, embedding, EntityState.VOLATILE
        )
```

**Proposed change:** Wrap vector_index.upsert and vector_index.update_state calls in api.py with time.perf_counter() guards: `t0 = time.perf_counter(); self.vector_index.upsert(...); commit_ms = (time.perf_counter() - t0) * 1000; if commit_ms > 15.0: _logger.warning('shadow commit %.1fms exceeded §15.2 #4 budget', commit_ms)`. Aggregate p99 over a rolling window (deque of last N samples) and emit ERROR-level log when the rolling p99 crosses 15ms — the §9 Trigger 2 surface §15.2 #4 demands. Today the budget is a paper claim; the instrumentation is the load-bearing observability the spec assumes exists.

**Risk if wrong:** If wrong (the budget is intended as a tuning target enforced at the LanceDB level, not at the substrate boundary), the finding misreads §15.2 #4. But §15.2 #4 explicitly says 'If the 15ms budget cannot be met with defaults, surface as a §9 Trigger 2 escalation' — the surfacing requires measurement, and measurement requires instrumentation, and the substrate is the only place that owns the call site spanning all backends.

**References:** `ARCHITECTURE.md §15.2 #4`, `MONETA.md §9 Trigger 2`, `src/moneta/vector_index.py:upsert`

---

### `substrate-L4-query-path-decay-precedes-vector-no-budget` — High — Moneta.query runs ecs.decay_all (O(n) over every live entity) BEFORE the vector_index.query — meaning the substrate's per-query critical path is decay-tax + vector-search + ECS-row-projection + sort, and the implicit latency budget §15.2 #6 (~41Hz under contention ⇒ ~24ms/query) is consumed by all four phases sequentially with no allocation between them; at envelope size (MAX_ENTITIES=10000 + N consolidated growing unboundedly per adversarial-L3-vector-index-unbounded-consolidated-growth) the decay tax can monotonically grow to dominate the budget while the substrate has no signal that it has done so.

**Role:** substrate  **File:** `src/moneta/api.py:284-320`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        now = time.time()

        self.ecs.decay_all(self.decay.lambda_, now)

        if self.ecs.n == 0:
            return []

        over_fetch_k = max(len(self.vector_index), 1)
        hits = self.vector_index.query(embedding, over_fetch_k)
```

**Proposed change:** Two paired changes: (a) instrument query() phases — capture `t_decay`, `t_vector`, `t_project`, `t_sort` separately via time.perf_counter() and emit a single DEBUG-level structured log per query; aggregate to a rolling p95 attribute on the handle (`m.query_phase_p95`) for operator inspection. (b) Architect-routed evaluation of lazy per-hit decay (decay only the entities the vector index returned, not all 10k) — would collapse the substrate-side tax from O(n) to O(limit) while preserving §4 'evaluation point 1 before retrieval' under a defensible reading (the hits' utility values must reflect current decay before reranking; entities NOT returned don't influence the answer). The Architect must rule whether §4's 'before retrieval' applies to all entities or just the retrieved subset; today it's interpreted maximally without measurement justifying the choice.

**Risk if wrong:** Compounds with substrate-L4-decay-all-on-query-path-no-envelope-guard — together they capture both the cost (decay_all is O(n)) and the structural ordering (decay precedes vector search, so the cost cannot be amortized). Without instrumentation, there's no path from 'query latency increased' back to 'decay_all is the cause' in production. The §15.2 #6 envelope was sized against USD contention; the substrate's own contribution to query latency is unmeasured.

**References:** `ARCHITECTURE.md §4`, `ARCHITECTURE.md §15.2 #6`, `src/moneta/ecs.py:decay_all`, `adversarial-L3-vector-index-unbounded-consolidated-growth`

---

### `persistence-L4-shadow-commit-budget-uninstrumented` — High — ARCHITECTURE.md §15.2 #4 declares a hard ≤15ms p99 LanceDB shadow-commit budget, but VectorIndex.upsert/update_state/delete emit no per-call timing — there is no path in code that observes whether the budget is met, breached, or off by an order of magnitude.

**Role:** persistence  **File:** `src/moneta/vector_index.py:82-112`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def upsert(
        self,
        entity_id: UUID,
        vector: List[float],
        state: EntityState,
    ) -> None:
        """Insert or replace an entity's vector and state."""
        if self._dim is None:
            self._dim = len(vector)
        elif len(vector) != self._dim:
            raise ValueError(
                f"embedding dim mismatch: expected {self._dim}, got {len(vector)}"
            )
        self._records[entity_id] = (list(vector), state)
```

**Proposed change:** Add per-call latency emission at INFO/DEBUG level for each shadow-commit-class operation (upsert, update_state, delete), capturing the elapsed time. Aggregate p50/p95/p99 across a configurable rolling window and surface the rolling p99 via a `last_p99_ms` attribute or structured log so operators can verify §15.2 #4 conformance in production. The current Phase 1 in-memory backend trivially meets 15ms; the instrumentation matters because the §9 Trigger 2 escalation contract for breaching the budget (per phase2-closure.md §3) requires a measurement to fire on. With no measurement, breach detection falls to bench-time sleep simulation, which §15.6's narrow-lock revision has invalidated as the only signal.

**Risk if wrong:** If the budget is later met automatically by whatever backend lands (LanceDB defaults under light load), the missing instrumentation is theoretical. But the locked spec at §15.2 #4 is *budget*, not *aspiration* — the §9 escalation path is contingent on detecting a breach. A LanceDB swap that runs at 25ms p99 under contention would produce no diagnostic, no §9 escalation, no operator signal. The substrate would silently exit the operational envelope.

**References:** `ARCHITECTURE.md §15.2 #4`, `docs/phase2-closure.md §3`, `ARCHITECTURE.md §7`, `MONETA.md §9 Trigger 2`

---

### `persistence-L4-sequential-writer-no-phase-timing` — High — SequentialWriter.commit_staging is the single coordination site where the §7 sequential-write protocol's two phases (USD authored first, vector second) become observable, yet it emits zero per-phase timing — the §15.2 #4 shadow-commit budget targets exactly the second phase, and the natural measurement seam is exposed neither to logs nor to the AuthoringResult return value.

**Role:** persistence  **File:** `src/moneta/sequential_writer.py:89-115`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def commit_staging(self, staged: List[Memory]) -> AuthoringResult:
        """Commit a staging batch. Authoring first, vector second.

        Returns the `AuthoringResult` from the authoring target. If the
        vector-index update raises, the authoring-target state is left
        intact (benign orphan per §7), and the exception propagates.
        """
        result = self._target.author_stage_batch(staged)
        self._target.flush()
        _logger.info(
            "sequential_writer.author count=%d target=%s batch=%s",
            len(staged),
            result.target,
            result.batch_id,
        )

        for memory in staged:
            self._vector.update_state(memory.entity_id, EntityState.CONSOLIDATED)
        _logger.info("sequential_writer.vector_update count=%d", len(staged))
```

**Proposed change:** Wrap each phase (author_stage_batch+flush, then the vector update_state loop) in time.perf_counter() blocks; extend the existing INFO logs to include `author_ms` and `vector_commit_ms`. Emit the same fields on a structured event so monitoring can compute p99 over windows. Optionally add `author_ms` and `vector_commit_ms` fields to AuthoringResult so consolidation.run_pass can surface them in ConsolidationResult and the harness can assert against §15.2 #4 in load tests. Cost: ~6 lines, near-zero overhead.

**Risk if wrong:** Without phase timing at the coordination seam, the substrate has two independent unmeasured paths (the AuthoringTarget side and the VectorIndexTarget side), and §15.2 #4 cannot be enforced from outside either side. A future load test or production tracing harness has no entry point to extract the partition.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §15.2 #4`, `ARCHITECTURE.md §15.6`

---

### `persistence-L4-vector-index-query-on-monotonic-growth` — High — VectorIndex.query is an O(n) linear scan over self._records; combined with the absence of any eviction path on update_state(CONSOLIDATED) or anywhere else, the index size grows monotonically with all-time consolidated count, making p95 query latency scale with session age rather than with the §15.2 operational envelope's accumulated ≤50k assumption — silently breaching the envelope on the read side as the USD side rotates within it.

**Role:** persistence  **File:** `src/moneta/vector_index.py:113-146`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `adversarial-L3-vector-index-unbounded-consolidated-growth`

**Evidence:**

```
        q_norm = math.sqrt(q_norm_sq)
        dim = len(vector)
        scored: list[tuple[UUID, float]] = []
        for eid, (vec, _state) in self._records.items():
            if len(vec) != dim:
                continue
            dot = 0.0
            v_norm_sq = 0.0
            for a, b in zip(vec, vector):
                dot += a * b
                v_norm_sq += a * a
            if v_norm_sq == 0.0:
                continue
            cos_sim = dot / (math.sqrt(v_norm_sq) * q_norm)
            scored.append((eid, cos_sim))
        scored.sort(key=lambda t: t[1], reverse=True)
```

**Proposed change:** Two paired changes: (a) on commit_staging's vector phase, evict CONSOLIDATED entities from the index entirely (their authoritative storage is on disk in USD per §7; cache-warming per §8 will repopulate on access). This caps the index at the operational hot-tier size, which §15.2 #1 already bounds. (b) Document the eviction policy in vector_index.py module docstring so the §7.1 'authoritative for what exists' clause is interpreted as 'authoritative for what is currently hot'. Without (a), production sessions running for days accumulate vector_index records bounded only by lifetime deposit count, and the query hot path scales with that history.

**Risk if wrong:** Today's tests use ephemeral handles and short sessions, so the unbounded growth is invisible. A 30-day production session at 100 deposits/hour with 50% staging produces ~36k consolidated records the index iterates on every query — within Phase 1's in-memory dict that's microseconds, but a future LanceDB backend with the same retention policy compounds the §15.2 #4 budget against an unbounded data volume. Closes adversarial-L3-vector-index-unbounded-consolidated-growth from Loop 3 with the §15.2 envelope framing it lacked.

**References:** `ARCHITECTURE.md §7`, `ARCHITECTURE.md §7.1`, `ARCHITECTURE.md §15.2`, `ARCHITECTURE.md §8`

---

### `persistence-L4-commit-staging-per-memory-loop` — High — SequentialWriter.commit_staging issues N independent vector_index.update_state calls in a Python for-loop with no bulk primitive on the VectorIndexTarget Protocol; at the §15.2 #3 batch cap of 500 prims, the vector phase pays Python attribute-lookup and dict-mutation overhead 500 times per pass, and there is no path for a future backend (LanceDB) to amortize the per-batch cost into a single transactional write within the §15.2 #4 budget.

**Role:** persistence  **File:** `src/moneta/sequential_writer.py:106-115`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        for memory in staged:
            self._vector.update_state(memory.entity_id, EntityState.CONSOLIDATED)
        _logger.info("sequential_writer.vector_update count=%d", len(staged))

        return result
```

**Proposed change:** Extend the VectorIndexTarget Protocol with `bulk_update_state(entity_ids: list[UUID], state: EntityState) -> None`; the in-memory backend implements it as a single dict comprehension with one logger.info, the future LanceDB backend implements it as a single transaction. SequentialWriter.commit_staging calls bulk_update_state once per batch instead of update_state N times. This also resolves Loop 3 persistence-L3-mid-batch-vector-state-divergence at the protocol level — a bulk transactional update either succeeds or fails atomically, eliminating the partial-commit window. Cost: one new Protocol method, one default implementation in vector_index.py, one call-site change in sequential_writer.py.

**Risk if wrong:** At Phase 1's in-memory backend the loop is microseconds and operationally invisible. The risk fires when a real backend lands: 500 individual LanceDB upserts vs one batched transaction is a 100x latency delta in typical columnar stores. Today's Protocol surface gives the future backend no path to that optimization, locking the substrate into per-record cost on the very phase §15.2 #4 budgets at 15ms p99.

**References:** `ARCHITECTURE.md §15.2 #3`, `ARCHITECTURE.md §15.2 #4`, `ARCHITECTURE.md §7`

---

### `usd-L4-batch-rotation-overshoot` — High — _resolve_target_layer reads self._prim_counts.get(name, 0) once per entity but the count is only incremented AFTER the per-layer ChangeBlock loop completes; for a single batch of N entities arriving when pre-batch count is in [rotation_cap - N + 1, rotation_cap - 1], every entity in the batch routes to the same existing sublayer and the post-batch count silently exceeds rotation_cap by up to N-1 prims, violating the locked ARCHITECTURE.md §15.2 #1 50k cap by up to MAX_BATCH_SIZE - 1 = 499 prims per overshoot event.

**Role:** usd  **File:** `src/moneta/usd_target.py:218-235`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        base = _rolling_sublayer_base(authored_at)
        seq = self._rotation_seq.get(base, 0)
        name = f"{base}.usda" if seq == 0 else f"{base}_{seq:03d}.usda"

        # Check rotation cap
        count = self._prim_counts.get(name, 0)
        if count >= self._rotation_cap:
            seq += 1
            self._rotation_seq[base] = seq
            name = f"{base}_{seq:03d}.usda"
```

**Proposed change:** Track an in-flight count alongside the persistent self._prim_counts during the resolve loop. In author_stage_batch, after a tentative groups assignment, recompute target layer for each entity considering both stored count and the running count of entities already grouped to that layer; rotate when stored_count + in_flight_count >= rotation_cap. Add tests/unit/test_usd_target.py::TestSublayerRotation::test_single_batch_exceeding_cap_rotates_within_batch — cap=10, single batch of 12 entities, assert two rolling sublayers with counts 10 and 2. The current implementation silently produces one sublayer with count 12.

**Risk if wrong:** If wrong, the rotation cap is preserved by accident of the per-batch resolve-then-author flow because _resolve_target_layer DOES update self._rotation_seq mid-loop. Re-tracing: when stored count crosses cap mid-batch (e.g., a prior batch left count=50000), the FIRST entity of the new batch sees count >= cap and triggers rotation; entities 2..N see updated rotation_seq and route to the new layer. But this only fires when stored count >= cap before the batch begins. The bug fires specifically when stored count is in (cap - N, cap), which is a ~1% probability band per batch but produces a permanently-over-cap sublayer when it fires. Verified by tracing with stored count 49,800 + batch of 500.

**References:** `ARCHITECTURE.md §15.2 #1`, `ARCHITECTURE.md §15.2 #3`, `src/moneta/usd_target.py:_resolve_target_layer`, `src/moneta/consolidation.py:MAX_BATCH_SIZE`

---

### `usd-L4-coldstart-rotation-cap-violation` — High — _get_or_create_layer's FindOrOpen fallback path (when CreateNew returns None because the file already exists on disk) unconditionally seeds self._prim_counts[name] = 0, ignoring any prims already authored to that layer in a prior session — a reopened sublayer carrying its full 50k complement allows the substrate to author another 50k prims on top before rotation triggers, doubling the §15.2 #1 envelope to 100k accumulated prims per sublayer and breaking the Phase 2 cost model assumption that p95 stall is bounded by the 50k cap.

**Role:** usd  **File:** `src/moneta/usd_target.py:195-215`  **§9:** no  **Conflicts with locked decision:** no
**Closes:** `usd-L3-prim-counts-coldstart-bypass-rotation-cap`

**Evidence:**

```
        if self._in_memory:
            layer = Sdf.Layer.CreateAnonymous(name)
        else:
            layer_path = str(self._log_path / name)
            layer = Sdf.Layer.CreateNew(layer_path)
            if layer is None:
                layer = Sdf.Layer.FindOrOpen(layer_path)

        self._layers[name] = layer
        self._prim_counts[name] = 0
```

**Proposed change:** When the FindOrOpen fallback fires, count the existing root prims on the reopened layer (e.g., len(list(layer.rootPrims)) or a recursive Sdf prim spec count) and seed self._prim_counts[name] with that value. Alternatively, if cross-session hydration is genuinely out of scope (per docs/phase3-closure.md §4), make CreateNew==None a hard error rather than a silent fallback so the operator gets a loud signal. Pair with tests/unit/test_usd_target.py::TestColdStartReopen that pre-populates a usda file with N>cap prims, instantiates UsdTarget against that path, authors one entity, and asserts the sublayer count reflects N+1 (or rotation triggered).

**Risk if wrong:** Cross-session USD hydration is documented as not-yet-shipped, so the FindOrOpen fallback path is rarely exercised today. The hazard fires whenever the root layer's child sublayer file pre-exists (manual file restore, partial-cleanup-after-test, two UsdTargets pointing at the same usd_target_path because storage_uri normalization is missing per Loop 2 substrate-L2-storage-uri-no-normalization), or any v1.1+ surgery that lights up cross-session hydration without auditing this code path. Phase 2 cost model is sized against the 50k cap; breaching it pushes the operational point back into Yellow tier latencies the narrow-lock claim no longer covers.

**References:** `ARCHITECTURE.md §15.2 #1`, `ARCHITECTURE.md §15.6`, `docs/phase3-closure.md §4`, `docs/phase2-closure.md §3`

---

### `adversarial-L4-typed-schema-cost-model-collision` — High — Three findings — architect-L4-typed-schema-overhead-not-in-cost-model, architect-L4-narrow-lock-projection-unvalidated-at-cap, and architect-L4-benchmark-bare-prim-not-representative — converge on the same root: Pass 5/6 narrow-lock claim ('~10-30ms p95 stall at batch ≤500') was measured against bare-prim authoring, while v1.2.0-rc1 production authors 6 typed attrs/prim. With Pass 5 data showing batch=10 at 99.5% reduction but batch=1000 at ~0% reduction (recomposition dominates), the 6× spec-creation count multiplier at batch=500 likely pushes actual production stall well above 30ms — the §15.6 cost model is empirically unanchored at the operational point under the production write shape.

**Role:** adversarial  **File:** `ARCHITECTURE.md:365-380`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
**Revised cost model:** The steady-state p95 reader stall drops from ~131ms (Phase 2 attribute-case mean, §15.2 constraint #5) to a projected ~10–30ms at Moneta's operational batch sizes (≤500 prims, ≤50k accumulated). At batch=10 (typical), the stall drops to sub-1ms. These are projections from the Pass 5 narrow-lock benchmark comparison, not re-measured production numbers.
```

**Proposed change:** Architect-routed v1.0.1 task: re-run scripts/usd_metabolism_bench_v2.py --lock-scope narrow with author_batch modified to write the v1.2.0-rc1 production shape (typeName='MonetaMemory' + 6 attrs: String, Float, Int, Float, Double, Token), at batch_size in {10, 100, 250, 500} × accumulated in {0, 25k, 50k}. Update §15.6 with the measured numbers. If the projected 10-30ms band at batch=500 holds under typed-schema authoring, the Phase 3 closure's 'Green-adjacent' framing is empirically substantiated; if it does not hold, §15.6 must be revised and the patent-evidence chain (claims #2 #3) must reflect the actual cost basis. The benchmark re-run is the critical-path empirical task before any further capacity claim.

**Risk if wrong:** The patent-evidence chain (docs/patent-evidence/pass6-lock-shrink-implementation.md) cites Pass 5 numbers as the basis for claim #4's substantiation. If the typed-schema overhead pushes production stall to the 50-100ms range (between the Pass 5 batch=500 wide-lock 130-200ms and narrow-lock <30ms projection), the 'Green-adjacent' tier framing in docs/phase3-closure.md §1 is overstated; v1.0.0+ may operationally ship Yellow with §15.6 advertising Green-adjacent. The empirical gap is not academic — it shifts the operational tier classification.

**References:** `ARCHITECTURE.md §15.6`, `docs/pass5-q6-findings.md narrow-lock benchmark table`, `docs/phase3-closure.md §1`, `schema/MonetaSchema.usda`

---

### `adversarial-L4-pcp-rebuild-cost-typed-schema-untested` — High — ARCHITECTURE.md §15.2 #7 locks 'Pcp rebuild cost: effectively free (0.1–2.6ms across the entire sweep)' as a Phase 3 cost-model assumption — but this number was measured against bare-prim authoring per scripts/usd_metabolism_bench_v2.py::author_batch. v1.2.0-rc1 introduces typed schema (typeName='MonetaMemory') which engages OpenUSD's SchemaRegistry-aware composition path; Pcp rebuild on typed prims may exercise schema attribute fallback resolution, allowedTokens validation, and typeName inheritance walks that bare prims bypass. The 'effectively free' claim is empirically un-validated against the typed-schema path that ships in production.

**Role:** adversarial  **File:** `ARCHITECTURE.md:298-304`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
7. **Pcp rebuild cost: effectively free** (0.1–2.6ms across the entire
   sweep). No optimization needed for invalidation avoidance, composition
   graph depth, or variant complexity caps.
```

**Proposed change:** Same benchmark re-run path as adversarial-L4-typed-schema-cost-model-collision: extend scripts/usd_metabolism_bench_v2.py to author typed MonetaMemory prims and capture the pcp_rebuild_p50_ms / pcp_rebuild_p95_ms columns; verify the §15.2 #7 'effectively free' number holds under typed-schema authoring, OR update §15.2 #7 with the measured typed-schema cost. If Pcp rebuild grows from 0.1-2.6ms to, say, 5-15ms on typed prims, the 'no optimization needed' guidance in §15.2 #7 is stale and Phase 4+ surgeries planning typed-schema hot paths inherit a wrong assumption. The cost-model gap compounds with the narrow-lock projection gap: both are downstream of the bare-prim benchmark shape.

**Risk if wrong:** If typed-schema Pcp rebuild is genuinely still in the 0.1-2.6ms band, the finding is over-cautious. But OpenUSD's SchemaRegistry lookup (engaged when typeName='MonetaMemory' resolves through the codeless plugin) is a known cost path that bare prims explicitly bypass. The Phase 2 closure's confidence that Pcp is 'effectively free' was empirically grounded in the bare-prim case; the typed-schema migration changed the authoring shape AFTER the closure ruled. Compounds with architect-L4-investigation-task-9-never-executed: two §15.3 investigation tasks (per-sublayer size + spec-count vs semantic-type) both unexecuted, the typed-schema migration ships against an unmeasured cost basis.

**References:** `ARCHITECTURE.md §15.2 #7`, `ARCHITECTURE.md §15.3 #10`, `schema/MonetaSchema.usda`, `scripts/usd_metabolism_bench_v2.py`

---

### `adversarial-L4-volatile-count-ecs-n-confusion-deepens` — High — substrate-L4-ecs-n-counts-all-states-mask-volatile correctly identifies that ConsolidationRunner.should_run uses ecs.n (total count across all states) where ARCHITECTURE.md §6 specifies 'volatile count exceeds MAX_ENTITIES'. The Adversarial framing deepens this: combined with adversarial-L3-staged-classify-uses-state-volatile-only (CONSOLIDATED entities never evict), once total count grows past max_entities through CONSOLIDATED accumulation, should_run.pressure-trigger fires CONTINUOUSLY on every check — but should_run is unwired (architect-L4-should-run-dead-code), so the bug is dormant. The moment should_run gets wired (per the synthesis of architect-L4-should-run-dead-code-idle-window-not-enforced), this cascading failure activates: the substrate goes from never-consolidating to always-consolidating, breaking §15.2 #2 idle-window discipline from the opposite direction.

**Role:** adversarial  **File:** `src/moneta/consolidation.py:62-76`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    def should_run(self, ecs: ECS, now_ms: float) -> bool:
        """Pressure (MAX_ENTITIES) or opportunistic (idle) trigger."""
        if ecs.n >= self._max_entities:
            return True
```

**Proposed change:** The substrate-L4 finding's proposed fix (add ecs.volatile_count(), use it in should_run) is necessary AND insufficient — must land paired with a fix for the CONSOLIDATED-never-evicts gap (Loop 3 adversarial-L3-staged-classify-uses-state-volatile-only). If only volatile_count() lands without CONSOLIDATED eviction, volatile entities consolidate normally but the §10 protected quota and ECS memory footprint grow unbounded with CONSOLIDATED rows. If only CONSOLIDATED eviction lands without volatile_count(), pressure trigger uses total count which is now bounded by eviction, but the spec wording 'volatile count' is still violated. Architect must synthesize: (a) CONSOLIDATED entities are evicted from ECS at some point (the cache-warming §8 path explicitly REQUIRES this — 'retrieving from USD does not promote to ECS' implies CONSOLIDATED entities aren't in ECS); AND (b) should_run uses volatile_count() for spec letter-correctness. Both fixes together close the cascade; either alone leaves a gap.

**Risk if wrong:** When should_run gets wired (a near-term planned change per the multi-finding consolidation-L4-idle-window-not-enforced-in-runpass cluster), the substrate transitions from one envelope violation (no idle-window enforcement) to another (continuous pressure-triggered consolidation against accumulated CONSOLIDATED count). Without paired fixes, wiring should_run is operationally worse than leaving it dead.

**References:** `ARCHITECTURE.md §6`, `ARCHITECTURE.md §8`, `ARCHITECTURE.md §15.2 #2`, `substrate-L4-ecs-n-counts-all-states-mask-volatile`, `adversarial-L3-staged-classify-uses-state-volatile-only`, `architect-L4-should-run-dead-code-idle-window-not-enforced`

---

### `adversarial-L4-stress-test-not-in-ci-evidence-aging` — High — test-L4-pass5-stress-test-not-in-regression-suite identifies that the 10k-iteration / 775M-assertion stress test (the empirical foundation for §15.6 narrow-lock + patent claim #4) is invoked manually with no CI gate; combined with adversarial-L4-pcp-rebuild-cost-typed-schema-untested and adversarial-L4-typed-schema-cost-model-collision, the v1.2.0-rc1 codeless schema migration changed the authoring shape AFTER the empirical evidence was collected. Patent counsel-facing evidence cites OpenUSD 0.25.5 + bare-prim shapes; production v1.2.0-rc1 ships typed prims on the same OpenUSD; the stress evidence's structural claim (Save() const-ness is shape-independent) is plausibly preserved but unverified.

**Role:** adversarial  **File:** `scripts/usd_metabolism_bench_v2.py:351-405`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    parser.add_argument(
        "--stress",
        type=int,
        default=0,
        metavar="N",
        help="Run Q6 thread-safety stress test with N iterations instead of sweep.",
    )
```

**Proposed change:** Critical-path v1.0.1 task: re-run the Pass 5 stress test with the v1.2.0-rc1 production authoring shape (typeName='MonetaMemory' + 6 typed attrs including Token-typed priorState). Update docs/patent-evidence/pass5-usd-threadsafety-review.md with a Pass 6 supplemental section reporting (a) iteration count, (b) per-iteration Save+Traverse latency distribution, (c) zero-failure validation, (d) commit hash. The Save() const-ness argument plausibly extends to typed prims (the schema is registered via plugin path, doesn't mutate Save semantics) but PLAUSIBLY-EXTENDS is not the same as EMPIRICALLY-VERIFIED. Patent counsel deserves the latter. Pair with adding a smoke-scale variant (100-200 iterations, ~1M assertions) marked @pytest.mark.load to CI per test-L4-pass5-stress-test-not-in-regression-suite — catches gross regressions in narrow-lock semantics without requiring full-scale runs.

**Risk if wrong:** Patent claim #4 ('Protected memory as root-pinned strong-position sublayer, concurrent-read-safe') rests on the 775M-assertion run on OpenUSD 0.25.5 + bare prims. If a counsel review or adversarial filing examination notices that production now writes typed prims and the empirical evidence is bare-prim, the structural argument requires a separate justification. A re-run under typed-prim authoring is a single weekend of compute and closes the patent-evidence gap before filing.

**References:** `ARCHITECTURE.md §15.6`, `docs/patent-evidence/pass5-usd-threadsafety-review.md`, `MONETA.md §3 claim #4`, `schema/MonetaSchema.usda`, `test-L4-pass5-stress-test-not-in-regression-suite`

---

### `adversarial-L4-bench-default-lock-scope-supersedence` — High — test-L4-bench-v2-default-lock-scope-stale-vs-pass6-shipped correctly identifies that --lock-scope defaults to 'wide' (Phase 2 baseline) while production ships narrow lock per §15.6. Adversarial framing: the implications cascade further than test-L4 documented — anyone running the benchmark to PRODUCE numbers for envelope justification (e.g., a v1.0.1 cost-model re-run, a Phase 4 capacity planning exercise, a patent-evidence supplemental) gets wide-lock numbers by default and must explicitly opt into narrow to match production. The script's default contradicts the shipped substrate's default behavior, and every report generated from default flags is structurally wrong about the production envelope.

**Role:** adversarial  **File:** `scripts/usd_metabolism_bench_v2.py:557-565`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    parser.add_argument(
        "--lock-scope",
        choices=["wide", "narrow"],
        default="wide",
        help="Writer lock scope. 'wide' = Phase 2 baseline. 'narrow' = Q6 variant.",
    )
```

**Proposed change:** Flip the default to narrow with explicit docstring + help-text changes: '--lock-scope narrow' becomes the default reflecting shipped UsdTarget; '--lock-scope wide' is retained for historical comparison and explicitly named as 'Phase 2 baseline, superseded by §15.6'. The script's docstring's existing 'Round 2.5 review fixes' section gains a new 'Pass 5/6 update' subsection citing docs/pass5-q6-findings.md and ARCHITECTURE.md §15.6 supersedence. ANY future operator running the benchmark with default flags then matches production behavior; the wide-lock comparison requires explicit opt-in. Pairs with documentarian-L4-bench-v2-docstring-no-pass6-supersedence at the same code site.

**Risk if wrong:** The script is the canonical tool referenced by docs/phase2-benchmark-results.md and docs/patent-evidence/pass6-lock-shrink-implementation.md. A capacity planner running default flags TODAY and reporting '~131ms p95 stall at batch=1000, accumulated=100k' as 'current Moneta cost model' commits a regression-by-mismatch. The default-scope mismatch is a cross-cutting Documentarian + Architect concern that the test-L4 finding flagged at Medium; the Adversarial reframing argues High because the false-confidence path is reachable in a single command-line invocation.

**References:** `ARCHITECTURE.md §15.6`, `docs/pass5-q6-findings.md`, `docs/patent-evidence/pass6-lock-shrink-implementation.md`, `test-L4-bench-v2-default-lock-scope-stale-vs-pass6-shipped`

---

### `adversarial-L4-half-life-vs-idle-window-interaction-genuine` — High — substrate-L4-half-life-min-vs-idle-window-min-conflict identifies a genuine envelope-design conflict that the architect-side review should treat as load-bearing: at MIN_HALF_LIFE_SECONDS=60, an entity loses ~5.7% of utility per 5-second idle window, and the §6 staging condition Utility<0.3 is reachable from Utility=1.0 in ~30s of unattended decay. Combined with §15.2 #2 5s idle trigger and §15.2 #1 50k rotation cap, an operator tuning to 1-minute half-life produces a substrate where every memory stages within 30s × MAX_BATCH_SIZE ≈ 25 minutes regardless of attention reinforcement, saturating cortex_today.usda within a single short session.

**Role:** adversarial  **File:** `src/moneta/decay.py:22-30`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
DEFAULT_HALF_LIFE_SECONDS: float = 6 * 60 * 60  # 6 hours

# Tuning range per MONETA.md §2.3 ("1 minute to 24 hours").
MIN_HALF_LIFE_SECONDS: float = 60.0
MAX_HALF_LIFE_SECONDS: float = 24 * 60 * 60.0
```

**Proposed change:** Architect-routed: the §15.2 envelope was sized assuming a 6-hour-default half-life cadence; tuning to 1-minute breaks the cost-model assumption and exits the envelope by construction. Either (a) raise MIN_HALF_LIFE_SECONDS to a value where the full §15.2 envelope still holds (e.g., 600s = 10 minutes yields ~0.6% utility loss per idle window, well under STAGE threshold), OR (b) document the tuning-vs-envelope interaction in docs/decay-tuning.md and ARCHITECTURE.md §4 explicitly: 'half_life < 600s exits the §15.2 operational envelope; sublayer rotation cadence and consolidation frequency become workload-driven rather than envelope-bounded; operators tuning below this threshold accept that the §15.2 cost model no longer applies'. Path (b) is the smaller change and honors MONETA.md §2.3's tuning-range commitment; path (a) preserves envelope-by-construction at the cost of shrinking the documented tuning range.

**Risk if wrong:** Substrate-L4 finding marked Medium; Adversarial reframing argues for High because the interaction is load-bearing for capacity planning. A research-burst phase against a 1-minute-half-life substrate produces consolidation saturation that breaches the §15.2 #1 50k cap on the very first session — the envelope's sublayer rotation guarantees collapse. Operators following docs/decay-tuning.md's documented tuning range without reading the §15.2 envelope sizing assumptions land in this trap.

**References:** `MONETA.md §2.3`, `ARCHITECTURE.md §4`, `ARCHITECTURE.md §15.2 #1`, `ARCHITECTURE.md §15.2 #2`, `substrate-L4-half-life-min-vs-idle-window-min-conflict`

---

### `adversarial-L4-vector-index-monotonic-growth-cumulative-impact` — High — PRIOR FINDING persistence-L4-vector-index-query-on-monotonic-growth (closes adversarial-L3-vector-index-unbounded-consolidated-growth) identifies that VectorIndex._records grows monotonically with all-time CONSOLIDATED count. The Adversarial cumulative-impact framing: combined with substrate-L4-decay-all-on-query-path-no-envelope-guard (decay_all is O(n) on every query) and substrate-L4-ecs-n-counts-all-states-mask-volatile (ecs.n includes CONSOLIDATED rows), every query() call in a long-running session pays O(all-time consolidated count) on THREE separate paths: ECS decay, vector index linear scan, and (when wired) pressure-trigger arithmetic. A 30-day production session with steady ~100 stagings/day accumulates ~3000 records that every query iterates against.

**Role:** adversarial  **File:** `src/moneta/vector_index.py:113-146`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        scored: list[tuple[UUID, float]] = []
        for eid, (vec, _state) in self._records.items():
            if len(vec) != dim:
                continue
            dot = 0.0
            v_norm_sq = 0.0
            for a, b in zip(vec, vector):
                dot += a * b
                v_norm_sq += a * a
```

**Proposed change:** The persistence-L4 finding's proposed fix (evict CONSOLIDATED entities from vector_index on commit_staging) is correct but architecturally load-bearing — it changes the §7.1 'authoritative for what exists' invariant to 'authoritative for what is currently hot', with cache-warming per §8 as the rehydration path. This requires (a) §8 cache-warming implementation (currently deferred per docs/phase3-closure.md §4 limitation #4), (b) updating §7.1's authoritative-for-what-exists wording to reflect hot-tier-only scope, (c) a cross-store consistency mechanism so that 'is this entity in vector index' is no longer a canonical 'does it exist' answer. Architect must rule whether this is a v1.1+ task gated on §8 cache-warming, or whether the eviction-without-cache-warming pattern is acceptable as an interim (entities in cortex_YYYY_MM_DD.usda but not in vector index are unqueryable until §8 ships, which may be acceptable since cross-session hydration is also deferred).

**Risk if wrong:** Today's tests use ephemeral handles so monotonic growth is invisible. A production agent running for 30 days at 100 deposits/hour with 50% staging accumulates ~36k consolidated records every query iterates. Within Phase 1's in-memory dict that's microseconds, but compound with a future LanceDB backend (§15.2 #4 budget 15ms p99) and the per-query commit cost grows with session age. The §15.2 envelope was sized assuming bounded vector_index size; current behavior preserves the envelope by accident of ephemeral test sessions.

**References:** `ARCHITECTURE.md §7.1`, `ARCHITECTURE.md §8`, `ARCHITECTURE.md §15.2 #4`, `persistence-L4-vector-index-query-on-monotonic-growth`, `substrate-L4-decay-all-on-query-path-no-envelope-guard`, `substrate-L4-ecs-n-counts-all-states-mask-volatile`

---

### `adversarial-L4-default-rotation-cap-50k-test-gap` — High — test-L4-default-rotation-cap-not-pinned-and-default-not-exercised + test-L4-rotation-default-cap-50k-never-exercised together identify that the §15.2 #1 50k cap has no test coverage at the actual cap value — every rotation test uses cap=5 or cap=10. The Adversarial deepening: combined with usd-L4-batch-rotation-overshoot (within-batch overshoot up to 499 prims) and usd-L4-coldstart-rotation-cap-violation (FindOrOpen resets counter to 0), the 50k cap is preserved by THREE compounding accidents — small-cap test scaling, in-process counter fidelity, and same-session continuity. Any one of the three failing in production produces a >50k sublayer the substrate cannot detect.

**Role:** adversarial  **File:** `tests/unit/test_usd_target.py:185-220`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        cap = 10
        target = UsdTarget(log_path=None, rotation_cap=cap)

        # Author exactly `cap` memories — should fill the first sublayer
        first_batch = [_make_memory() for _ in range(cap)]
        target.author_stage_batch(first_batch)
```

**Proposed change:** Three-pronged paired fix: (1) add a `@pytest.mark.load`-marked test that authors 50,001 entities to a single rotation_cap=DEFAULT_ROTATION_CAP UsdTarget instance, asserts rotation fired exactly once at the boundary, asserts both sublayers exist with combined prim count == 50,001 — exercises the actual cap value once; (2) add a unit test for the within-batch overshoot scenario with cap=10, pre-stored count=8, batch=5, asserts rotation fires mid-batch with 10 in old + 3 in new — pins usd-L4-batch-rotation-overshoot's fix; (3) add a unit test for the FindOrOpen seeding fix with a pre-existing usda file containing N>cap prims, asserts the reopened UsdTarget seeds _prim_counts to N — pins usd-L4-coldstart-rotation-cap-violation's fix. The three tests jointly close the §15.2 #1 cap's verification gap.

**Risk if wrong:** The 50k cap is the Phase 2 closure §3 #1 hard constraint and the primary lever against accumulated serialization tax. Without test coverage at any of three failure dimensions, each becomes a regression vector that could land green. The patent-evidence chain (claims #1, #2, #3, #4 all rely on bounded sublayer growth) inherits the same gap.

**References:** `ARCHITECTURE.md §15.2 #1`, `test-L4-default-rotation-cap-not-pinned-and-default-not-exercised`, `test-L4-rotation-default-cap-50k-never-exercised`, `usd-L4-batch-rotation-overshoot`, `usd-L4-coldstart-rotation-cap-violation`

---

### `adversarial-L4-synthetic-session-mock-only-load-gate-stale` — High — test-L4-synthetic-session-only-mock-target identifies that the 30-min synthetic session — MONETA.md §4 Phase 1 completion gate AND the only load-tier regression test — uses MockUsdTarget exclusively. The Adversarial framing: this is THE marquee load gate cited in MONETA.md, and after v1.0.0 ship + v1.2.0-rc1 ship its coverage is structurally non-representative. Production v1.x ships with use_real_usd capability (defaulting to False per MonetaConfig.use_real_usd), which means EVERY downstream load-test inherits the mock's faster behavior and zero-cost shadow commit; production envelope characteristics are unsmoke-tested at scale by any test in the suite.

**Role:** adversarial  **File:** `tests/load/synthetic_session.py:255-285`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
    # 5-minute half-life — short enough to exercise decay through a
    # 30-minute virtual session, long enough that fresh deposits aren't
    # aggressively pruned by the first sleep pass.
    config = MonetaConfig.ephemeral(
        half_life_seconds=300.0, max_entities=10_000
    )
    with Moneta(config) as m:
```

**Proposed change:** Add a sibling test `tests/load/synthetic_session_real_usd.py` (or parametrize the existing test) running the same 30-min session with use_real_usd=True against a tmp_path. Mark @pytest.mark.load and pxr-gate via importorskip. Assert: (a) Tier 1 architectural invariants identical to the mock run (proves A/B parity), (b) all deposits actually reach disk via flush() (proves end-to-end durability), (c) sublayer rotation never fires at default cap=50000 (current scale doesn't trigger it; pin as contract), (d) wall-clock budget catches gross regressions (e.g., 60s ceiling for the 30-min virtual session — calibrated against actual current run). This converts the marquee load gate from mock-only to dual-target, closing the largest regression-coverage gap in the v1.x release line.

**Risk if wrong:** The MONETA.md §4 'Phase 1 completion gate' was authored when mock was the ONLY target. v1.0.0+ shipped with real USD as the production default behavior pattern — but tests that load-validate run only against mock. A pxr upgrade or usd_target.py refactor that subtly breaks under sustained load (Sdf.ChangeBlock memory growth, layer reference leaks, _layers dict bloat per usd-L3-typename-overwrite-on-reopen, _prim_counts drift per usd-L4-prim-counts-drift-on-partial-batch-failure) has zero detection mechanism. The synthetic-session harness is the highest-trust regression artifact in the suite, and it's mock-blind.

**References:** `MONETA.md §4 Phase 1 completion gate`, `ARCHITECTURE.md §15.2`, `ARCHITECTURE.md §15.6`, `docs/phase3-closure.md §4`, `test-L4-synthetic-session-only-mock-target`

---

### `adversarial-L4-locked-constants-pinning-test-gap` — High — test-L4-no-consolidation-runner-unit-tests + test-L4-default-max-entities-not-pinned + test-L4-max-batch-size-constant-not-pinned + test-L4-default-rotation-cap-not-pinned-and-default-not-exercised together identify that NONE of the locked envelope constants (MAX_BATCH_SIZE=500, DEFAULT_MAX_ENTITIES=10000, DEFAULT_IDLE_TRIGGER_MS=5000, DEFAULT_ROTATION_CAP=50_000, PRUNE_UTILITY_THRESHOLD=0.1, STAGE_UTILITY_THRESHOLD=0.3, attended thresholds=3) have a pinning test asserting their literal value. Every test that uses these constants references the SYMBOL, not the VALUE, so a silent change to any constant lands green.

**Role:** adversarial  **File:** `tests/unit/test_consolidation.py:1-1`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
tests/integration/test_real_usd_end_to_end.py             # 28 tests (22 Phase 1 + 6 Phase 3 USD)
tests/load/                                              # 2 tests (synthetic session gate)
```

**Proposed change:** Single coordinated fix: create tests/unit/test_locked_envelope_constants.py with one test per locked constant: test_max_batch_size_locked_at_500, test_default_max_entities_locked_at_10000, test_default_idle_trigger_ms_locked_at_5000, test_default_rotation_cap_locked_at_50000, test_prune_utility_threshold_locked_at_0_1, test_stage_utility_threshold_locked_at_0_3, test_prune_attended_threshold_locked_at_3, test_stage_attended_threshold_locked_at_3. Each test docstring cites the spec authority (ARCHITECTURE.md §15.2 #N or §6 ruling) and names a change as a §9-escalation candidate. A single-file test asserting these eight invariants closes four Loop 4 findings and provides structural defense against silent constant drift across the entire envelope.

**Risk if wrong:** Without pinning tests, ANY refactor that 'tunes' a locked constant (perhaps as part of a benchmark experiment that gets accidentally committed, perhaps under the influence of a misread spec, perhaps as a 'fix' for a perceived issue) silently shifts the entire §15.2 envelope. The locked-decisions list in CLAUDE.md is paper; the constant values are the implementation; without test pinning, the gap between paper and implementation is unobservable. This is the most cost-effective single fix in Loop 4 (one new file, eight assertions) for the most cost-effective outcome (structural defense of every locked envelope value).

**References:** `ARCHITECTURE.md §15.2`, `ARCHITECTURE.md §6`, `MONETA.md §2.6 ruling #5`, `test-L4-no-consolidation-runner-unit-tests`, `test-L4-default-max-entities-not-pinned`, `test-L4-max-batch-size-constant-not-pinned`, `test-L4-default-rotation-cap-not-pinned-and-default-not-exercised`

---

### `test-L5-no-test-asserts-no-fourth-decay-call-site` — High — ARCHITECTURE.md §4 names a locked invariant: 'Exactly three evaluation points... A test asserts the absence of a fourth call site.' The §16 conformance checklist repeats: 'Decay evaluation points: exactly three (§4). A test asserts no fourth call site.' No such test exists. The decay test suite covers math correctness extensively (closed-form curves, clamp boundaries, clock skew) but does NOT structurally enforce the call-site count. A future refactor adding a fourth ecs.decay_all call site (e.g., in a hot-tier maintenance method, in a new harness operator, in a query-path optimization) would land green.

**Role:** test  **File:** `tests/unit/test_decay.py:1-50`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
**Locked invariant:** No fourth evaluation point. No scheduled decay task. A test asserts the absence of a fourth call site.
```

**Proposed change:** Add `tests/unit/test_decay_call_sites.py::test_exactly_three_decay_call_sites` performing AST-level scan over `src/moneta/`: parse every .py file, walk for ast.Call nodes with attribute name in {'decay_all', 'decay_one'}, assert the union count is exactly 3 and that the call sites are in {api.py:Moneta.query (eval point 1), attention_log.py:reduce_attention_log (eval point 2), consolidation.py:run_pass (eval point 3)}. Cite ARCHITECTURE.md §4 'A test asserts the absence of a fourth call site' and §16 conformance checklist as authority. Pattern is identical to the existing test_lock_free_discipline AST scan in test_attention_log.py.

**Risk if wrong:** The §4 invariant has been carried since architecture lock; the test that enforces it is named in the spec but missing in code. A regression that adds a fourth decay site is not just a performance issue (substrate-L4-decay-all-on-query-path-no-envelope-guard family) — it is a §9 Trigger 2 spec-level surprise per the locked invariant. Without the test, the invariant is preserved by accident of code review attention rather than by structural defense.

**References:** `ARCHITECTURE.md §4`, `ARCHITECTURE.md §16`, `tests/unit/test_attention_log.py::TestLockFreeDiscipline (pattern reference)`

---

### `test-L5-docs-api-md-singleton-error-references` — High — docs/api.md 'Errors' section documents `MonetaNotInitializedError` ('raised when an operation is called before init()') as part of the canonical error surface. v1.1.0 deleted both `init()` and `MonetaNotInitializedError` (DEEP_THINK_BRIEF_substrate_handle.md §5.3 'no-arg trap' replaced the not-initialized concept entirely with TypeError); v1.1.0 introduced `MonetaResourceLockedError` for URI collisions. The docs name a non-existent error and omit the actual one shipped.

**Role:** documentarian  **File:** `docs/api.md:171-180`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
## Errors

- `MonetaNotInitializedError` — raised when an operation is called
  before `init()`.
- `ProtectedQuotaExceededError` — raised when a protected deposit would
  exceed the 100-entry quota (ARCHITECTURE.md §10). Phase 1: `deposit`
  raises. Phase 3: operator-facing unpin tool.
```

**Proposed change:** Rewrite the 'Errors' section: '- `TypeError` — `Moneta()` raised at construction time when no config is passed (per DEEP_THINK_BRIEF §5.3 no-arg trap; pass `MonetaConfig.ephemeral()` for tests). - `MonetaResourceLockedError` — raised when a second `Moneta(config)` is constructed against a `storage_uri` already held by a live handle in this process (per DEEP_THINK_BRIEF §5.4). Release via the holding handle's `close()` or context-manager exit. - `ProtectedQuotaExceededError` — raised when a protected deposit would exceed the per-handle `config.quota_override` (default 100 per ARCHITECTURE.md §10).' Cross-link to README's locked-decisions item #5 and #6 for context.

**Risk if wrong:** A consumer wrapping `try / except MonetaNotInitializedError` per the docs hits `NameError` because the symbol does not exist. A consumer constructing two handles on the same URI and not knowing about MonetaResourceLockedError gets a Python traceback they cannot match against any documented error type. The docs name a fictional error and hide a real one — this is precisely the doc-vs-code drift that erodes trust in the API reference.

**References:** `docs/api.md`, `src/moneta/api.py:MonetaResourceLockedError`, `src/moneta/api.py:ProtectedQuotaExceededError`, `README.md 'Locked decisions' #5`

---

### `documentarian-L5-claude-phase3-orphan-duplicate` — High — docs/CLAUDE-phase3.md is an orphan near-duplicate of the top-level CLAUDE.md, dated to the Phase 3 era ('Current phase: **Phase 3** — USD integration at measured depth. Yellow tier'); the top-level CLAUDE.md was updated post-v1.0.0 ('Current phase: **v1.0.0 shipped.** All three phases complete'). The orphan is reachable via filesystem traversal, contains a contradictory phase status, and serves no role — there is no documented reason to retain a Phase-3-frozen snapshot in docs/. Two CLAUDE files in the same repo invite split brain.

**Role:** documentarian  **File:** `docs/CLAUDE-phase3.md:1-50`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
## Current phase

**Phase 3** — USD integration at measured depth. Yellow tier.

Phase 1 shipped as v0.1.0 (94 tests green, ECS + four-op API + mock USD target + Protocol-based sequential writer). Phase 2 closed as tag `moneta-v0.2.0-phase2-closed` with verdict YELLOW — clean in the operational envelope, with documented graceful degradation beyond it.

Phase 3 hard rules are locked in `ARCHITECTURE.md` §15. Agent discipline is governed by `docs/agent-commandments.md` from Pass 3 onward.
```

**Proposed change:** Delete docs/CLAUDE-phase3.md outright. CLAUDE.md is the live source-of-truth; phase-frozen snapshots belong in git history, not in the working tree. If the Phase 3 era guidance is genuinely needed for some retrospective purpose (Architect spec-conformance audits, patent-evidence review), preserve it via git tag `moneta-v1.0.0` rather than as a tracked file that drifts. Per CLAUDE.md 'Don't use feature flags or backwards-compatibility shims when you can just change the code' — the same principle applies to documentation: shipping two CLAUDE files for the same repo is a documentation shim against deletion.

**Risk if wrong:** If wrong (the orphan is intentionally retained as patent-evidence anchor for the Phase 3 era), it should be moved to docs/patent-evidence/ with a clear 'archived' header rather than left at docs/CLAUDE-phase3.md where it appears live. Today its mere existence at that path implies it is the Phase 3 working version — but no reader can tell at a glance that it is superseded by the top-level CLAUDE.md. The risk of an Architect or test-engineer agent loading the wrong file is real and silent.

**References:** `CLAUDE.md 'Current phase'`, `CLAUDE.md 'Hard rules' (no backwards-compat shims)`, `Constitution §12`

---

### `documentarian-L5-rounds-round1-still-placeholder-since-phase1` — High — docs/rounds/round-1.md has been a placeholder since pre-Phase-1 ('**Status:** Placeholder. Content not yet migrated to repo.') with an action note 'Paste the full Round 1 brief here when it is recovered'; the project has shipped through Phase 3 + two surgeries with the placeholder unresolved. CLAUDE.md 'Source of truth' #4 names rounds 1-3 as authoritative outputs from scoping, but #1 is empty — a missing link in the lineage chain that downstream docs (MONETA.md §10, docs/phase2-closure.md §7) cite as if present.

**Role:** documentarian  **File:** `docs/rounds/round-1.md:1-11`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
# Round 1 — Initial scoping brief

**Status:** Placeholder. Content not yet migrated to repo.

**Source:** Round 1 was a scoping brief authored by Claude + Joseph Ibrahim in a previous session. Adversarial framing was stripped; a 24–48 hour shipping window was specified; §2.3 (consolidation translator) and §4 (prior art) were flagged as load-bearing.

**Action:** Paste the full Round 1 brief here when it is recovered from the scoping session artifacts. Do not paraphrase from MONETA.md §10 — the lineage summary there is not a substitute for the original text.
```

**Proposed change:** Either (a) recover and paste the Round 1 brief content as the file directs, completing the lineage chain that CLAUDE.md cites; or (b) explicitly mark the file as '**Status:** Permanently lost. Round 1 content is not available. The lineage summary in MONETA.md §10 is the authoritative remnant.' and update CLAUDE.md 'Source of truth' #4 to read 'docs/rounds/round-{2,3}.md' (omitting round-1) so the placeholder's perpetual existence is not part of the doc-of-truth chain. Today the file is in a status-purgatory worse than either option: it claims content is forthcoming, no content arrives, and no doc updates the lineage to acknowledge the gap.

**Risk if wrong:** Documentation-only. Risk if wrong (the brief is being actively recovered by Joseph): the placeholder is correctly held open. But the placeholder has been in this state since at least Phase 1 Pass 1 and the file has not been touched across multiple opportunities to update it. The right Documentarian action is to convert the open-but-unresolved placeholder into either a resolution or an explicit acknowledgement of unresolvability.

**References:** `CLAUDE.md 'Source of truth' #4`, `MONETA.md §10 Lineage`, `docs/phase2-closure.md §7`

---

### `documentarian-L5-substrate-conventions-octavius-cross-link-todo-perpetual` — High — docs/substrate-conventions.md carries a `> **Cross-link (TODO):** Octavius's equivalent file path — to be filled in once the Octavius repo layout is known.` placeholder that has not been filled in across Phase 1, 2, 3 ship plus v1.1.0 + v1.2.0-rc1 surgeries; the doc itself states 'Both must stay in sync. Cross-reference the Octavius copy when its path is available' and 'A unilateral edit in one repo is always wrong' — but with no cross-link, every edit IS unilateral by construction, and the locked invariant that Moneta and Octavius share substrate conventions has no enforcement path.

**Role:** documentarian  **File:** `docs/substrate-conventions.md:4-12`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
**Sibling document:** This file is the Moneta mirror of Octavius's equivalent substrate-conventions document. Both must stay in sync. Cross-reference the Octavius copy when its path is available; if the two drift, that is a §9 escalation on the cross-project thesis, not a local fix.

> **Cross-link (TODO):** Octavius's equivalent file path — to be filled in once the Octavius repo layout is known. Until then, treat this document as the authoritative Moneta-side mirror.
```

**Proposed change:** Either (a) populate the cross-link with the actual Octavius path (the README mentions Octavius as a sibling project at github.com/JosephOIbrahim — if the Octavius repo exists, link it; if it has a substrate-conventions.md, anchor the link to it); or (b) downgrade the 'must stay in sync' contract to acknowledge Moneta-side authoritative status pending Octavius availability, and remove the §9-escalation framing for cross-project drift since one side of the cross-project pair does not yet have a public document. Today the doc claims a sync contract that is structurally unenforceable; a reader concluding 'this is binding cross-project doctrine' is mis-oriented.

**Risk if wrong:** If wrong (Octavius is in private development and the cross-link is intentionally deferred), the placeholder is correctly held open. But the placeholder has spanned the entire shipped Moneta lifecycle; the convention file's framing as 'sibling document' implies an actual sibling exists today. Convention #6 (UTC sublayer date routing) was added post-Phase-1 explicitly as 'A sixth was added in docs/substrate-conventions.md after Phase 1' — that addition was NOT cross-checked with Octavius because Octavius has no public mirror, demonstrating the contract is currently inactive.

**References:** `MONETA.md §8`, `CLAUDE.md 'Shared substrate conventions'`, `README.md 'Sibling project'`

---

### `documentarian-L5-agent-commandments-locked-through-v100-but-v110-v120-shipped` — High — docs/agent-commandments.md closes with `These commandments are locked through Phase 3 completion (v1.0.0). Revisions after v1.0.0 require a new scoping round.` — but v1.1.0 (singleton surgery) and v1.2.0-rc1 (codeless schema migration) have shipped post-v1.0.0 with no documented scoping round, and the README v1.1.0/v1.2.0-rc1 sections describe new MoE roles (Scout, Forge, Crucible, Steward, Auditor, Schema Author) and a new constitution pattern (EXECUTION_constitution_singleton_surgery.md) that the eight commandments don't acknowledge. Either the commandments are stale (silently revised by surgery practice) or the surgeries violated the locked revision protocol.

**Role:** documentarian  **File:** `docs/agent-commandments.md:165-175`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
These commandments are locked through Phase 3 completion (v1.0.0). Revisions after v1.0.0 require a new scoping round.
```

**Proposed change:** Architect-routed: either (a) confirm the eight commandments still apply verbatim to v1.1+ surgery work and amend the closing paragraph to read 'These commandments are locked through v1.2.0-rc1. Surgery-era role variants (Scout, Forge, Crucible, Steward, Auditor, Schema Author) inherit the same eight commandments under their constitution-specific role mappings (see EXECUTION_constitution_*.md). Revisions require a new scoping round.'; or (b) acknowledge that the surgery practice has produced a de facto revision and document the new commandments alongside the originals. Today the file's authority is silently expired but its status text is unchanged — readers cite 'agent commandments' from CLAUDE.md hard-rules as if active, and no doc surface tells them the v1.0.0 lock has been crossed.

**Risk if wrong:** If wrong (the eight commandments are unconditionally binding and the v1.1+ surgeries were governed by the same eight without new scoping — no contradiction), the closing paragraph just needs the version number bumped. But the README v1.1.0 / v1.2.0-rc1 sections describe surgery-specific constitutions and role names that the commandments file doesn't contemplate. The lock claim is paper unless someone routes the question to the Architect.

**References:** `CLAUDE.md 'Hard rules' (Follow agent-commandments.md from Phase 3 Pass 3 onward)`, `README.md 'v1.1.0 — singleton surgery verdict'`, `README.md 'v1.2.0-rc1 — codeless schema migration verdict'`, `MONETA.md §6 role system`

---

### `architect-L5-architecture-md-locked-date-vs-shipped-surgeries` — High — ARCHITECTURE.md is the locked spec and source of truth, yet its closing line says 'Locked 2026-04-11. §15 added 2026-04-12 (Phase 3 Pass 2). Source: MONETA.md. Changes require MONETA.md §9 escalation' — and v1.1.0 (singleton-to-handle surgery) plus v1.2.0-rc1 (codeless typed schema) shipped post-lock without §15.7+ entries, without a §9 escalation note, and without a revision-tracking tail; the README enumerates these as locked decisions #5 and #6, but the spec the README cites as the canonical ARCHITECTURE.md surface has admitted neither.

**Role:** architect  **File:** `ARCHITECTURE.md:419-421`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
*Locked 2026-04-11. §15 added 2026-04-12 (Phase 3 Pass 2). Source: MONETA.md. Changes require MONETA.md §9 escalation.*
```

**Proposed change:** Add ARCHITECTURE.md §17 'Post-Phase-3 surgeries' (or §15.8 / §15.9 sub-sections) documenting (a) the v1.1.0 singleton-to-handle migration: the four-op API now lives as instance methods on a `Moneta(config)` handle, with `_ACTIVE_URIS` registry as the in-process exclusivity primitive; (b) the v1.2.0-rc1 codeless typed schema migration: on-disk prims have `typeName='MonetaMemory'`, `priorState` is a token with four `allowedTokens`, the schema is registered via `schema/plugInfo.json`. Update the closing locked-on line to track each surgery date. Per CLAUDE.md hard rules, 'documentation lag implementation by more than one PR' is forbidden; the spec is two surgeries behind shipped code.

**Risk if wrong:** If wrong (the surgeries are intentionally invisible to ARCHITECTURE.md and only the README admits them), then locked-decision discipline has fragmented: future agents reading ARCHITECTURE.md as the source-of-truth surface (per CLAUDE.md §'Source of truth' #2) will not see #5/#6 and may operate as if they are not locked. Either the spec admits the surgeries or the README's locked-decisions list is making non-binding claims.

**References:** `ARCHITECTURE.md closing line`, `README.md 'Locked decisions' #5 and #6`, `CLAUDE.md 'Source of truth' #2`, `CLAUDE.md 'Hard rules' (≤1 PR doc lag)`

---

### `architect-L5-architecture-md-init-references-stale` — High — ARCHITECTURE.md §2.1 'Harness-level bootstrap (not part of the agent API)' explicitly enumerates `init()` as one of the four harness-level entry points, but the v1.1.0 singleton-to-handle surgery deleted `init()` from `src/moneta/api.py` entirely; the locked spec lists a function that does not exist, and a Test Engineer auditing §2.1 conformance against the codebase finds a missing public callable that the spec affirms must be exposed.

**Role:** architect  **File:** `ARCHITECTURE.md:40-46`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
The module also exposes `init()`, `run_sleep_pass()`, `smoke_check()`, and `MonetaConfig`. **These are not part of the agent-facing four-op surface.** They are harness-level entry points used by test fixtures, operator scripts, and Consolidation Engineer's sleep-pass scheduler.
```

**Proposed change:** Replace the §2.1 enumeration to reflect the post-v1.1.0 handle surface: 'The module also exposes `Moneta` (the handle class), `MonetaConfig`, `MonetaResourceLockedError`, and `smoke_check()`. The `Moneta` handle owns `run_sleep_pass()` as an instance method. **These are not part of the agent-facing four-op surface.** They are harness-level entry points used by test fixtures, operator scripts, and Consolidation Engineer's sleep-pass scheduler. Agents never call them; fifth-op rules do not apply.' Add a Ruling C (post-v1.1.0 closure) note: 'The v1.1.0 surgery replaced module-level `init()`/`_state` with a per-handle constructor; the agent-facing surface is unchanged in shape, only the receiver changed from module-level dispatch to instance methods.'

**Risk if wrong:** If wrong (the spec is intentionally aspirational and `init()` should exist), then the v1.1.0 surgery violated a locked clause without §9 escalation. The ruling either way is required; the current state — spec lists a function that the implementation deleted — is unrepresentable in the locked-decision discipline.

**References:** `ARCHITECTURE.md §2.1`, `src/moneta/api.py (no init() defined)`, `README.md v1.1.0 singleton surgery section`

---

### `substrate-L5-smoke-check-no-test-coverage` — High — moneta.smoke_check() is documented in README ('lowest-friction sanity check'), CLAUDE.md ('lowest-friction way to sanity-check after a change'), and api.md as the canonical end-to-end smoke for deposit -> query -> attention -> sleep_pass -> manifest — but no test in tests/unit, tests/integration, or tests/load actually invokes it. A regression that breaks smoke_check (e.g., changes the assertion thresholds, adds a parameter, or makes it fail under default config) lands green and is detected only by humans running 'python -c "import moneta; moneta.smoke_check()"' manually. The function's promised contract is verifiable only by hand.

**Role:** substrate  **File:** `src/moneta/api.py:400-445`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
def smoke_check() -> None:
    """End-to-end exercise of the four-op API + a consolidation pass.

    Pass 3 coverage: deposit -> query -> attention -> sleep pass ->
    manifest. Constructs its own ephemeral handle so callers do not
    need to manage lifecycle. Raises on any deviation.
    """
```

**Proposed change:** Add tests/unit/test_api.py::TestSmokeCheck::test_smoke_check_runs_clean that calls moneta.smoke_check() and asserts no exception. Also add ::test_smoke_check_releases_uri_lock that calls smoke_check() and then asserts the in-process registry _ACTIVE_URIS does not contain any moneta-ephemeral:// URI (smoke_check's `with Moneta(...)` block must clean up). Two-line test, ~50 ms runtime, closes the canonical-sanity-surface coverage hole.

**Risk if wrong:** If wrong (smoke_check is meant as a developer-only convenience and not part of the contract surface), there's no harm in testing it anyway. If right, the README/CLAUDE.md promise that smoke_check is the canonical sanity check becomes verifiable by CI rather than by trust. A regression in smoke_check today produces silent doc drift: README says 'If you see OK, the four ops, decay math, attention reducer, sleep pass, and consolidation are all wired correctly' but if smoke_check itself broke, OK could be wrong without anyone noticing.

**References:** `README.md 'Smoke check' section`, `CLAUDE.md 'Build and test commands'`, `docs/api.md 'Example: minimal end-to-end'`

---

### `persistence-L5-no-unit-test-vector-index` — High — tests/unit/test_vector_index.py does not exist. ARCHITECTURE.md §7.1 declares an explicit locked invariant — 'the vector index rejects dim-mismatched upserts. Dim-homogeneity is enforced at upsert time, not at query time, and the error is a hard ValueError — not a silent skip' — but no unit test directly invokes VectorIndex.upsert with a mismatched dimension and asserts ValueError. The §7.1 invariant has only transitive coverage via api.py paths; a regression that softens upsert's `raise ValueError` to a silent skip or a logger.warn would land green.

**Role:** persistence  **File:** `src/moneta/vector_index.py:82-112`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        if self._dim is None:
            self._dim = len(vector)
        elif len(vector) != self._dim:
            raise ValueError(
                f"embedding dim mismatch: expected {self._dim}, got {len(vector)}"
            )
        self._records[entity_id] = (list(vector), state)
```

**Proposed change:** Create tests/unit/test_vector_index.py with at minimum: (a) test_first_upsert_locks_dim — first upsert fixes _dim; (b) test_dim_mismatch_raises_value_error — second upsert with wrong-length vector raises ValueError per §7.1; (c) test_dim_mismatch_at_construction_with_explicit_dim — VectorIndex(embedding_dim=N) plus upsert with len != N raises; (d) test_query_dim_mismatch_returns_empty — query with wrong-length vector returns []  (silent skip is acceptable on the read side per §7.1 'enforced at upsert time, not at query time'); (e) test_zero_norm_vector_skipped_in_query — defensive scoring path; (f) test_update_state_missing_entity_no_raise — eventually-consistent semantic from §5.1; (g) test_delete_idempotent — repeat delete does not raise. ~40 lines of test, locks every invariant the §7/§7.1 surface promises.

**Risk if wrong:** The §7.1 invariant is the only Persistence-Engineer-judgment-call that escalated to ARCHITECTURE-spec status (added during Phase 1 Pass 3, approved Pass 4). A regression here silently produces subtly-wrong query rankings — exactly the failure mode the invariant was added to prevent. Without a unit test, the only defense is the implementation's `raise ValueError` line itself; one careless change to `_logger.warning` and the spec letter is satisfied (the error is reported) but the spec intent (hard rejection at upsert time) is gone. Constitution §9 letter-vs-intent applies precisely.

**References:** `ARCHITECTURE.md §7.1`, `ARCHITECTURE.md §5.1`, `src/moneta/vector_index.py:upsert`, `Constitution §9 first-principles`

---

### `adversarial-L5-fifth-op-no-structural-defense` — High — CLAUDE.md hard rule 'Do not add a fifth operation to the agent API' is the most-cited Phase 1+ invariant, structurally locked by MONETA.md §7 and ARCHITECTURE.md §2. TestSignatureConformance walks Moneta's class body and asserts each of the four named methods matches its locked signature — but the AST walk is keyed on EXPECTED_SIGNATURES.items(), so it never asserts the inverse: that NO additional public methods (beyond the four ops + harness-level run_sleep_pass + dunder methods + close) live on Moneta. A future contributor adding `def remember(self, payload: str) -> UUID:` as a fifth op silently passes — the test confirms the four are correct without enforcing they are the only four.

**Role:** adversarial  **File:** `tests/unit/test_api.py:31-65`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
        for name, expected in EXPECTED_SIGNATURES.items():
            assert name in found, f"{name} not found on Moneta"
            assert found[name] == expected, (
                f"signature drift in Moneta.{name}:\n"
                f"  expected: {expected}\n"
                f"  actual:   {found[name]}"
            )
```

**Proposed change:** Extend TestSignatureConformance with `test_no_fifth_agent_op_on_moneta_class`: walk Moneta's body, collect every public-named (non-underscore) method, subtract the locked four-op set + the harness-level allowlist {'__init__', '__enter__', '__exit__', 'close', 'run_sleep_pass'}; assert the residue is empty. Cite MONETA.md §7 and CLAUDE.md hard rule as the authority. Without this, the entire fifth-op prohibition is preserved by code review attention only — a Critical-class hard rule with paper enforcement.

**Risk if wrong:** If wrong (the four-op rule is intentionally enforced at the import surface in __init__.py rather than at the class boundary), then __init__.py's __all__ list is the structural defense. Re-reading: __init__.py exports Moneta, MonetaConfig, errors, and smoke_check — but adding a fifth op to Moneta does not change __all__. The AST class-walk is the only place a fifth op would surface as a test failure. The gap is real.

**References:** `ARCHITECTURE.md §2`, `MONETA.md §7`, `CLAUDE.md 'Hard rules' (no fifth op)`, `Constitution §10 Loop 5`

---

### `adversarial-L5-entity-state-int-reorder-silent-corruption` — High — EntityState is an IntEnum with VOLATILE=0, STAGED_FOR_SYNC=1, CONSOLIDATED=2; durability.py snapshot_ecs persists `int(state)` and hydrate calls `EntityState(int(...))`. test-L5-no-test-for-types-memory-immutability surfaced this gap. Adversarial concrete mutation: a future surgery adding `EntityState.PRUNED` per the schema's reserved 'pruned' allowedToken would naturally land it at the next free position — VOLATILE=0, STAGED_FOR_SYNC=1, CONSOLIDATED=2, PRUNED=3 — but a careless reorder for 'logical lifecycle ordering' (PRUNED=0, VOLATILE=1, STAGED=2, CONSOLIDATED=3) silently corrupts every snapshot on disk: hydrated VOLATILE rows arrive as PRUNED, breaking selection invariants. Zero test catches this; mypy doesn't help because IntEnum values are nominally interchangeable.

**Role:** adversarial  **File:** `src/moneta/types.py:22-35`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
class EntityState(IntEnum):
    """ECS entity lifecycle (ARCHITECTURE.md §3)."""

    VOLATILE = 0
    STAGED_FOR_SYNC = 1
    CONSOLIDATED = 2
```

**Proposed change:** Pin the integer values structurally: add `tests/unit/test_types.py::TestEntityStateValuesAreFrozen` asserting `EntityState.VOLATILE == 0`, `EntityState.STAGED_FOR_SYNC == 1`, `EntityState.CONSOLIDATED == 2` with docstring 'These integer values are persisted in durability.py snapshots. A reorder silently corrupts cross-version restore — treat as on-disk schema, not internal enum. Future EntityState additions (e.g., PRUNED) MUST take the next free integer; reorders are §9 escalation candidates.' Pair with closing test-L5-no-test-for-types-memory-immutability and aligning the snapshot format with the §9-trigger format-stability claim in durability.py.

**Risk if wrong:** If wrong (the integer values are an internal representation and a reorder would be paired with a snapshot migration), no current snapshot migration path exists in the substrate — there is no version-bump mechanism for the integer encoding. The risk fires on the v1.x to v2.x transition: someone reorders the enum, ships the change, deployments restart, every snapshot's STAGED becomes VOLATILE, every CONSOLIDATED becomes STAGED, and the substrate silently rebuilds with corrupt state. The fix is one test, three lines.

**References:** `src/moneta/types.py:EntityState`, `src/moneta/durability.py snapshot_ecs`, `src/moneta/durability.py hydrate`, `test-L5-no-test-for-types-memory-immutability`

---

### `adversarial-L5-frozen-dataclass-no-test` — High — Memory carries `@dataclass(frozen=True)` with the docstring promise 'Frozen: mutations flow back through signal_attention, never through this object.' MonetaConfig in api.py is also `@dataclass(frozen=True, kw_only=True)` with similar load-bearing immutability semantics for the URI-lock contract. Adversarial concrete mutation: a refactor 'removing the frozen=True for performance' (a real-world pattern when serializing dataclasses to JSON) silently turns either object mutable. For Memory, returned snapshots become aliases that callers can mutate, breaking the agent-vs-substrate contract. For MonetaConfig, the URI-lock invariant collapses because storage_uri can be mutated post-acquisition. test-L5-no-test-for-types-memory-immutability surfaced Memory; MonetaConfig is also uncovered.

**Role:** adversarial  **File:** `src/moneta/types.py:37-75`  **§9:** no  **Conflicts with locked decision:** no

**Evidence:**

```
@dataclass(frozen=True)
class Memory:
    """Agent-facing projection of an ECS row (ARCHITECTURE.md §3).

    Returned from `query()` and `get_consolidation_manifest()`. Frozen:
    mutations flow back through `signal_attention()`, never through this
    object.
```

**Proposed change:** Add tests/unit/test_types.py::TestMemoryFrozen asserting `with pytest.raises(FrozenInstanceError): mem.utility = 0.5` AND tests/unit/test_api.py::TestMonetaConfigFrozen asserting `with pytest.raises(FrozenInstanceError): cfg.storage_uri = 'other'`. Cite ARCHITECTURE.md §3 (Memory contract) and DEEP_THINK_BRIEF_substrate_handle.md §5.4 (URI-lock contract depends on storage_uri immutability) as the load-bearing reasons. Without these tests, `frozen=True` removal lands as a one-character diff (drop `True`) and breaks two invariants the spec treats as locked.

**Risk if wrong:** If wrong (frozenness is enforced by code review and the dataclass decorator is self-documenting), the structural test is over-cautious. But the URI-lock surgery's safety hinges on storage_uri being unchangeable post-acquisition — a mutable MonetaConfig admits the operator-side pattern `cfg.storage_uri = other_uri; some_op(cfg)` after a handle has acquired the original URI, and the registry collapse becomes reachable. The test cost is six lines; the invariant cost of breakage is the entire singleton-surgery contract.

**References:** `ARCHITECTURE.md §3`, `DEEP_THINK_BRIEF_substrate_handle.md §5.4`, `test-L5-no-test-for-types-memory-immutability`

---

## Closure ledger

| Closed in loop | Closing id | Original id | Summary |
| --- | --- | --- | --- |
| 1 | `adversarial-L1-mock-vs-real-prior-state-divergence-sharpened` | `consolidation-L1-mock-prior-state-int-vs-token-drift` | Sharpens consolidation-L1-mock-prior-state-int-vs-token-drift: the divergence is not just a JSONL-vs-USD mismatch, it ac |
| 1 | `adversarial-L1-protected-quota-severity-bump` | `architect-L1-protected-quota-now-configurable` | Sharpens architect-L1-protected-quota-now-configurable. The architect set this Low; the actual severity is Medium becaus |
| 2 | `adversarial-L2-attention-log-loss-not-section9` | `substrate-L2-attention-log-drain-stale-buffer-race` | PRIOR FINDING substrate-L2-attention-log-drain-stale-buffer-race IS REAL but its §9 escalation framing is NOT VALID: ARC |
| 2 | `architect-L2-handle-exclusivity-concurrency-model-unspecified` | `architect-L1-handle-pattern-undocumented` | The v1.1.0 handle exclusivity model — `_ACTIVE_URIS` as a process-level lock, check-then-add inside the constructor, rel |
| 2 | `architect-L2-section-11-snapshot-wal-coordination-silent` | `persistence-L1-wal-truncation-race` | ARCHITECTURE.md §11 lists 'Shadow vector index + WAL-lite durability' as a Phase 1 deliverable but specifies neither the |
| 2 | `persistence-L2-vector-commit-uninstrumented` | `architect-L1-lancedb-constraint-no-implementation` | ARCHITECTURE.md §15.2 hard constraint #4 mandates 'LanceDB shadow commit budget: ≤ 15ms p99' enforced at build time, wit |
| 2 | `usd-L2-rotation-toctou-under-concurrent-writers` | `usd-L1-rotation-count-update-lag` | Closes Loop 1 finding usd-L1-rotation-count-update-lag with a Loop 2 lens. _resolve_target_layer reads self._prim_counts |
| 2 | `architect-L2-narrow-lock-projections-no-reader` | `usd-L1-narrow-lock-letter-vs-implementation` | ARCHITECTURE.md §15.6's stall-reduction projections are predicated on 'concurrent readers' traversing the UsdStage durin |
| 2 | `test-L2-narrow-lock-no-concurrent-reader-load-test` | `adversarial-L1-narrow-lock-untested-on-disk` | Deepens Loop 1 finding `adversarial-L1-narrow-lock-untested-on-disk` and `test-L1-narrow-lock-structural-guard-missing`. |
| 2 | `documentarian-L2-attention-log-phase1-stale-framing` | `documentarian-L1-attention-log-phase1-role4` | The attention_log.py module docstring frames the lock-free GIL contract as 'Phase 1 targets CPython GIL'; Phase 3 has sh |
| 2 | `substrate-L2-free-threaded-python-deepens-drain-race` | `adversarial-L1-free-threaded-python-attention-log` | PRIOR FINDING adversarial-L1-free-threaded-python-attention-log IS UNDER-SCOPED: the loss mode under PEP 703 free-thread |
| 2 | `adversarial-L2-mock-flush-fsync-out-of-scope` | `consolidation-L2-mock-flush-no-fsync` | PRIOR FINDING consolidation-L2-mock-flush-no-fsync IS NOT VALID at Medium severity: MockUsdTarget is a TEST-ONLY authori |
| 3 | `consolidation-L3-stuck-staged-no-recovery` | `adversarial-L2-staged-retry-not-implemented` | classify() iterates only entities in EntityState.VOLATILE — entities stuck in STAGED_FOR_SYNC from a prior failed pass ( |
| 3 | `architect-L3-section16-conformance-test-no-fourth-callsite-missing` | `test-L1-decay-fourth-callsite-test-missing` | ARCHITECTURE.md §16 conformance checklist promises 'Decay evaluation points: exactly three (§4). A test asserts no fourt |
| 3 | `documentarian-L3-attention-log-reducer-phase1-role-stale` | `documentarian-L2-attention-log-phase1-stale-framing` | attention_log.reduce_attention_log docstring attributes the call site to 'Consolidation Engineer's sleep-pass trigger (P |
| 3 | `substrate-L3-decay-eval-point-3-redundant-substrate-noted` | `substrate-L2-decay-eval-point-3-spurious-recompute` | PRIOR FINDING substrate-L2-decay-eval-point-3-spurious-recompute IS VALID and the correctness-edges lens reinforces it:  |
| 3 | `adversarial-L3-section6-prune-stage-bands-handled-correctly` | `architect-L3-section6-prune-vs-stage-disjoint-incomplete` | PRIOR FINDING architect-L3-section6-prune-vs-stage-disjoint-incomplete IS PARTIALLY VALID but the Medium severity is ove |
| 3 | `adversarial-L3-cache-warming-correctly-deferred` | `architect-L3-cache-warming-no-implementation-site` | PRIOR FINDING architect-L3-cache-warming-no-implementation-site at High severity is OVERSTATED: ARCHITECTURE.md §8's cac |
| 3 | `adversarial-L3-split-brain-correctly-deferred` | `architect-L3-split-brain-no-implementation-site` | PRIOR FINDING architect-L3-split-brain-no-implementation-site at High severity inherits the same overstatement as the ca |
| 3 | `adversarial-L3-decay-clamp-boundary-floor-equals-decayed` | `substrate-L2-decay-clamp-strict-greater-than-not-greater-equal` | decay_value uses `decayed if decayed > protected_floor else protected_floor` — strict greater-than. At the exact equalit |
| 4 | `architect-L4-rotation-cap-bypassed-on-reopen` | `usd-L3-prim-counts-coldstart-bypass-rotation-cap` | ARCHITECTURE.md §15.2 constraint #1 (50k prims per sublayer rotation) is enforced only against an in-process `_prim_coun |
| 4 | `persistence-L4-vector-index-query-on-monotonic-growth` | `adversarial-L3-vector-index-unbounded-consolidated-growth` | VectorIndex.query is an O(n) linear scan over self._records; combined with the absence of any eviction path on update_st |
| 4 | `usd-L4-coldstart-rotation-cap-violation` | `usd-L3-prim-counts-coldstart-bypass-rotation-cap` | _get_or_create_layer's FindOrOpen fallback path (when CreateNew returns None because the file already exists on disk) un |
| 4 | `substrate-L4-decay-all-doubles-memory-writes-at-envelope` | `substrate-L3-decay-all-timestamp-update-when-no-change` | ecs.decay_all writes BOTH `self._utility[i] = decay_value(...)` AND `self._last_evaluated[i] = now` for every entity unc |
| 4 | `usd-L4-prim-counts-drift-on-partial-batch-failure` | `usd-L3-state-to-token-keyerror-mid-changeblock` | self._prim_counts[name] is incremented by len(batch) AFTER the per-layer with Sdf.ChangeBlock() block exits; if any help |
| 4 | `adversarial-L4-redundant-decay-call-fast-path-correct-fix` | `substrate-L3-decay-eval-point-3-redundant-substrate-noted` | consolidation-L4-redundant-eval-point-3-cpu-cost correctly identifies the per-pass O(N) redundant decay_all cost. PRIOR  |
| 4 | `substrate-L4-mark-activity-fires-on-empty-signal-suppresses-idle` | `substrate-L3-aggregate-empty-batch-mark-activity-still-fires` | Moneta.signal_attention calls consolidation.mark_activity unconditionally even when weights={} is empty — closing Loop 3 |
| 5 | `persistence-L5-wal-flush-vs-fsync-doc-drift` | `persistence-L4-wal-flush-not-fsync` | docs/api.md tells consumers signal_attention is 'fsync'd to the JSONL WAL when durability is enabled' (durability table  |
| 5 | `consolidation-L5-classify-boundary-tests-missing-locked-thresholds` | `test-L4-no-consolidation-runner-unit-tests` | ConsolidationRunner.classify implements the four locked Round 2 thresholds (PRUNE_UTILITY_THRESHOLD=0.1, PRUNE_ATTENDED_ |
| 5 | `consolidation-L5-trigger-conditions-docstring-misframed-as-governance` | `documentarian-L4-consolidation-trigger-claim-vs-run-pass-unconditional` | consolidation.py module docstring presents 'Trigger conditions (MONETA.md §2.6)' immediately after 'Phase 3 target ... a |

