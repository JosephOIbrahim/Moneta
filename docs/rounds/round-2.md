# Round 2 — Gemini Deep Think Architectural Scoping

**Source:** Gemini Deep Think, responding to Round 1 scoping brief
**Date:** Round 2 of the Moneta (formerly CLS Hybrid) scoping sequence
**Status:** Closed. Superseded in parts by Round 3. Decisions locked per BUILD_PLAN lineage.
**Do not re-open without §9 escalation.**

---

This is the architectural scoping and benchmark design for the CLS Hybrid system. All adversarial framing and biological metaphor have been stripped where computational precision is required. This document is sized for immediate implementation based on the established premises from Round 1.

## 2. Architectural Specification: The CLS Hybrid

The architecture implements an **Attention-Weighted Temporal Degradation Cache with Implicit LOD Fallback**, formally splitting the high-frequency metabolic loop (ECS) from the cold-path structural target (OpenUSD).

### 2.1 Hot Substrate Schema (Hippocampus / ECS)

The hot substrate must be a flat, highly parallelizable in-memory structure (e.g., an Entity Component System or vectorized DataFrame) to allow lock-free concurrency and vector math.

**Component Schema:**
- `EntityID` (UUID)
- `SemanticVector` (Array[Float]): Crucial for O(1) semantic miss-detection before failing over to USD.
- `Payload` (String / Dict): The uncompressed memory context.
- `Utility` (Float, 0.0 to 1.0): Instantaneous salience. This is the sole target of the decay function.
- `AttendedCount` (Int): Cumulative reinforcement tracker. Separating this from `Utility` is critical to distinguish between a fleeting, highly-salient thought and a foundational concept.
- `ProtectedFloor` (Float, default 0.0): See Section 2.5.
- `LastEvaluated` (Timestamp Float): Wall-clock time.
- `State` (Enum): `VOLATILE`, `STAGED_FOR_SYNC`, `CONSOLIDATED`.
- `UsdLink` (SdfPath, Nullable): If this memory was recalled from USD, this points to its origin prim to prevent duplication upon reconsolidation.

**The Decay Function: Lazy Vectorized Exponential**

Do not use a power-law, and do not use a fixed background tick. A 60Hz loop iterating over 50,000 floats will steal CPU cache from the LLM inference engine. Instead, use a memoryless exponential decay evaluated exactly when an entity is accessed, reinforced, or scanned for consolidation:

```
U_now = max(ProtectedFloor, U_last * exp(-λ * (t_now - t_last)))
```

This is computationally O(1) per access, vectorizable across the entire ECS during the sleep pass, and biologically sufficient.

**Tick Rate: Opportunistic**

Evaluate the decay matrix synchronously at inference boundaries: once immediately before context retrieval, and once immediately after the attention-write phase.

### 2.2 Attention Observation Interface

**Mechanism:** Explicit Agent Signaling.

Do not rely on prompt post-hoc analysis (adds LLM latency tax) or true KV-cache attention extraction (breaks portability across vLLM/Ollama/Commercial APIs). The agent must explicitly declare usage via tool call.

**Interface Contract:**

```python
def signal_attention(weights: Dict[UUID, float]) -> None:
```

The hot substrate accepts this map blindly. For each hit:
1. `Utility = min(1.0, Utility + weights[UUID])`
2. `AttendedCount += 1`
3. `LastEvaluated = now()`

### 2.3 Consolidation Translator (Sleep Pass)

This is the load-bearing subsystem translating flat ECS state into OpenUSD structural arcs.

- **Trigger Conditions:**
  - *Primary (Pressure):* `len(ECS[VOLATILE]) > MAX_ENTITIES`
  - *Secondary (Opportunistic):* LLM inference queue idle for > 5000ms
- **Selection Criteria:**
  - *Prune:* `Utility < 0.1 & AttendedCount < 3` (Transients; delete entirely)
  - *Staged:* `Utility < 0.3 & AttendedCount >= 3` (Fading from active memory, but historically reinforced; flag for USD)
- **Translation Mechanics:** Accumulate into a Rolling Sublayer (`cortex_YYYY_MM_DD.usda`). Do not create a new sublayer per pass — you will exhaust OS file handles and explode the Pcp traversal depth. Sublayer stack order natively dictates decay priority.
- **Gist Emergence (Structural Mutation):** The episodic-to-semantic transition. The script queries a background LLM to summarize the payload, authors an `over` on the rolling sublayer, adds a `gist` Variant, writes the summary there, and switches VariantSelection to `gist`.
- **Failure Modes:** USD writes are not ACID transactional. Run the batch strictly inside `with Sdf.ChangeBlock():`. ECS entities remain `STAGED_FOR_SYNC` until `UsdStage.Save()` successfully returns. If locked, abort and retry next cycle.

### 2.4 Fallback Resolver

- **Query Contract:** `query(semantic_vector: Array[Float], limit: int) -> List[Memory]`
- **Miss Detection:** Query the ECS semantic index first. If similarity is below threshold τ (e.g., 0.85), it is a working-memory miss. Fallback to the USD Shadow Vector Index (see Section 6). `UsdStage` uses LIVRPS to automatically serve the highest surviving fidelity variant.
- **Merge Semantics (Split-Brain):** If a concept hits in both ECS and USD, the ECS version is strictly authoritative. It represents the dirty, un-consolidated, high-fidelity state. *(Note: Superseded by Round 3 — timestamp tiebreaker required.)*
- **Cache Warming (LTP):** Retrieving a memory from USD does not promote it to the ECS (prevents query spam from thrashing working memory). If the agent subsequently calls `signal_attention()` on it, then it hydrates into the ECS as a new VOLATILE entity with its `UsdLink` populated.

### 2.5 Protected Memory Semantics

- **Shape:** A binary floor on the decay math (`ProtectedFloor`). 1.0 ensures permanent context retention (agent identity, core constitutional rules).
- **USD Authoring:** Protected entities bypass rolling daily layers. They consolidate to a dedicated `cortex_protected.usda` layer pinned permanently to the strongest position in the Root stack.
- **Abuse Surface:** Agents will learn to flag everything as protected. Enforce a hard quota (e.g., max 100 pins per agent). If the budget is full, the agent must explicitly call an unpin tool. *(Note: Unpin is a Phase 3 operator-facing tool, not part of the four-op API. Phase 1 raises on quota overflow at deposit time.)*

### 2.6 Agent Integration API

Coupling must be minimized to four operations so the agent requires zero knowledge of USD internals:

1. `deposit(payload: str, embedding: List[float], protected_floor: float = 0.0) -> UUID`
2. `query(embedding: List[float], limit: int = 5) -> List[Memory]`
3. `signal_attention(weights: Dict[UUID, float]) -> None`
4. `get_consolidation_manifest() -> List[Memory]` (Allows agents to optionally reflect on what just became semantic cortex.)

## 3. The Benchmark: Sizing the Lock and Rebuild Tax

OpenUSD `UsdStage` is not thread-safe for concurrent read/write. Structural writes require an application-level mutex that will block your inference threads. The critical sizing metric is **Inference Starvation**: how many milliseconds does the LLM wait for the write to finish plus the time it takes USD's C++ core to rebuild the Pcp graph on the first subsequent read?

Save as `usd_metabolism_bench.py` and run in your plain Python 3.12 `pxr` environment.

```python
import time
import csv
import threading
import itertools
from pxr import Usd, Sdf, Tf

# Mutex simulating application-level thread safety
stage_lock = threading.Lock()
concurrent_latencies = []
is_benchmarking = True

def reader_thread(stage, paths, read_hz):
    """Simulates background inference queries hitting the memory system."""
    global is_benchmarking
    sleep_time = 1.0 / read_hz if read_hz > 0 else 0
    while is_benchmarking:
        start = time.perf_counter()
        with stage_lock:
            # Force LIVRPS evaluation
            prim = stage.GetPrimAtPath(paths[0])
            if prim.IsValid():
                _ = prim.GetAttribute("utility").Get()
        latency = (time.perf_counter() - start) * 1000
        concurrent_latencies.append(latency)
        if sleep_time: time.sleep(sleep_time)

def run_sizing_benchmark():
    global is_benchmarking, concurrent_latencies

    dimensions = {
        "batch_size": [10, 100, 1000, 5000],
        "structural_ratio": [0.0, 0.25, 1.0],
        "sublayer_count": [1, 5, 20],
        "read_load_hz": [10, 100, 1000]
    }

    keys, values = zip(*dimensions.items())
    permutations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    results = []

    print(f"Running {len(permutations)} permutations...")

    for p in permutations:
        stage = Usd.Stage.CreateInMemory()
        root = stage.GetRootLayer()
        sublayers = [Sdf.Layer.CreateAnonymous(f"layer_{i}") for i in range(p["sublayer_count"])]
        root.subLayerPaths = [l.identifier for l in sublayers]

        target_layer = sublayers[0]
        paths = [f"/Memory_{i}" for i in range(max(1000, p["batch_size"]))]

        # Pre-populate
        with Sdf.ChangeBlock():
            for path in paths:
                spec = Sdf.PrimSpec(target_layer, path, Sdf.SpecifierDef, "Scope")
                vset = Sdf.VariantSetSpec(spec, "fidelity")
                Sdf.VariantSpec(vset, "detail")
                Sdf.VariantSpec(vset, "gist")
                spec.variantSelections["fidelity"] = "detail"
                attr = Sdf.AttributeSpec(spec, "utility", Sdf.ValueTypeNames.Float)
                attr.default = 1.0

        # Warm Pcp
        for path in paths:
            stage.GetPrimAtPath(path).GetAttribute("utility").Get()

        concurrent_latencies.clear()
        is_benchmarking = True
        t = threading.Thread(target=reader_thread, args=(stage, paths, p["read_load_hz"]))
        t.start()
        time.sleep(0.1)

        structural_cutoff = int(p["batch_size"] * p["structural_ratio"])

        # 1. The Consolidation Pass (Write Block)
        write_start = time.perf_counter()
        with stage_lock:
            with Sdf.ChangeBlock():
                for i in range(p["batch_size"]):
                    if i < structural_cutoff:
                        target_layer.GetPrimAtPath(paths[i]).variantSelections["fidelity"] = "gist"
                    else:
                        target_layer.GetAttributeAtPath(f"{paths[i]}.utility").default = 0.5
        write_ms = (time.perf_counter() - write_start) * 1000

        # 2. Rebuild Tax (First post-write read on main thread)
        rebuild_start = time.perf_counter()
        with stage_lock:
            _ = stage.GetPrimAtPath(paths[0]).GetAttribute("utility").Get()
        rebuild_ms = (time.perf_counter() - rebuild_start) * 1000

        is_benchmarking = False
        t.join()

        p95_read = sorted(concurrent_latencies)[int(len(concurrent_latencies)*0.95)] if concurrent_latencies else 0.0

        results.append({
            **p,
            "Write_Lock_ms": round(write_ms, 2),
            "Pcp_Rebuild_ms": round(rebuild_ms, 2),
            "P95_Concurrent_Read_Stall_ms": round(p95_read, 2)
        })

    with open("usd_sizing_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print("Complete. Results in usd_sizing_results.csv.")

if __name__ == "__main__":
    run_sizing_benchmark()
```

*(Note: This benchmark has four issues identified in Round 2.5 review and two additional omissions flagged in Round 3. See round-3.md for the Phase 2 benchmark v2 specification.)*

**Interpretation Guide:**
- **Viable ~1Hz Background Tick:** P95 Concurrent Read Stall < 50ms. Consolidation can run seamlessly while the LLM generates tokens.
- **Viable Opportunistic Tick:** Stall between 50-300ms. Must strictly queue until the network/inference pipeline is fully idle.
- **Kill Signal:** If a high structural ratio causes the p95 stall to exceed 500ms, the batch size is entirely too aggressive for your CPU cache, and you must shrink N.

## 4. Prior Art Verification Pass

*(Superseded by Round 3 Q1. The Round 2 verdict of "entirely unrepresented" was overconfident and did not survive review against the Q1 2026 agent memory wave. See BUILD_PLAN.md §3 for the narrowed novelty claim.)*

A targeted, rigorous search mapping to OpenUSD, Information Bottleneck, and Multi-Agent LLM architectures confirms the window is open.

1. **Tiered Systems (Letta/MemGPT, Zep, Mem0):** These systems emulate working vs. archival tiers via functional strings injected into Postgres/PgVector or Neo4j. None of them utilize a hierarchical C++ scene-graph composition engine. They rely on explicit COALESCE-style routing logic.

2. **OpenUSD in AI:** Extremely active, but almost exclusively used for spatial/environmental representation (e.g., Real2USD, arXiv:2510.10778, utilizing LLMs to navigate digital twins). USD is treated as the world, not the mind.

3. **Information Bottleneck (IB) Memory:** MemFly (arXiv Feb 2026) validates your mathematical framing of memory optimization. However, it applies IB strictly to vector clusters and neural gradient optimizers. *(Round 2.5 correction: MemFly uses a gradient-free LLM-driven optimizer, not neural gradients. Round 3 Q1 also surfaced HyMem, VimRAG, CogitoRAG, From Verbatim to Gist, HippoRAG, and two survey papers as adjacent prior art missed in this search.)*

**Verdict:** The synthesis — mapping cognitive state degradation natively onto OpenUSD's LIVRPS composition arcs and variant selection — is entirely unrepresented in published literature or patent space. *(Superseded: the architectural pattern is prior-art-covered. The substrate choice remains defensible. See BUILD_PLAN.md §3.)*

## 6. New Risks Discovered During Scoping

1. **The Vector Search Impedance Mismatch (Distributed State Risk)**
   OpenUSD is a hierarchical graph; it cannot natively perform semantic similarity (K-NN) queries over text. You are strictly forced to maintain a Shadow Vector DB (e.g., FAISS, LanceDB) mapping embeddings to OpenUSD SdfPaths. If the USD stage and the shadow index drift out of sync during a pruning pass, the Fallback Resolver will request an SdfPath that throws a fatal Pcp lookup error. Atomicity across these two stores is your highest implementation risk. *(Mitigation updated in Round 3: sequential write, not 2PC.)*

2. **Gist-Generation Compute Contention**
   The episodic-to-semantic transition requires writing to the `gist` variant. For a memory to become a gist, an LLM must summarize it. If your benchmark dictates a batch size of 500 prims, your "sleep pass" abruptly requires 500 LLM calls. This transforms a fast disk I/O operation into a compute-bound task that will stall the system unless offloaded to a heavily quantized local background model.

3. **The TfToken Registry OOM Trap**
   OpenUSD uses TfToken to make string comparisons O(1) fast. This is a global, immortal C++ string registry. Tokens are never garbage collected. If you construct OpenUSD Prim names dynamically using natural language memory payloads (e.g., `def Prim "User_likes_pizza"`), you will eventually OOM the Python process. **Mitigation:** The schema must be rigidly structured. Prims must be named using standard UUIDs (`def Prim "Memory_1A4B"`). The actual natural language content must remain strictly inside string attribute values, which are not tokenized by the core.

---

*End of Round 2 content. See round-3.md for validation, corrections, and the locked final form.*
