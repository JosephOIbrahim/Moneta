# Deep Think Brief — Moneta Substrate-Handle Design

**Status:** Design source of truth for the singleton surgery.
**Authority:** Sections 1–4 are the original brief. Section 5 is the Deep Think response. Section 6 captures G1 ruling clarifications added during execution.

---

## 1. Mode

Adversarial design pass. Pressure-test the proposed direction, surface alternatives, identify second-order consequences. Not a build sheet. The deliverable is a design recommendation with reasoning that holds up to scrutiny.

---

## 2. Context — Locked Premises

These are findings, not assumptions. Do not re-litigate them.

**1. The system.** Moneta is a USD-native cognitive substrate. Python library, single repo, ~94 tests passing under plain Python plus 17 unit + 6 integration USD tests under hython. Targeted as the persistent memory and state composition layer for multiple consumer surfaces — not a product, a substrate.

**2. The finding.** A read-only scout pass identified the master substrate-leak: a module-level singleton at `api.py:124`, named `_state`, plus a process-wide `PROTECTED_QUOTA = 100`. These mean: one substrate per process, period. The singleton is the single line of code that decides whether Moneta is a substrate or a product.

**3. The constraint chain.** The singleton blocks every meaningful next step:
- Multi-tenancy is impossible — one process, one substrate, one tenant
- Cloud deployment is impossible — would need one process per user, infinitely
- Multi-instance testing is impossible — tests can't construct two substrates in the same process
- Inside-out SDK integration is structurally awkward — agent loops embedded in host applications inherit the host's process, and the host may legitimately need multiple substrate instances

**4. Adjacent findings, for context only — do not solve these.**
- No SDK integration of any kind exists yet (zero `anthropic`/`claude`/`mcp`/`agent_sdk` imports). Clean slate for inside-out SDK design, but not this brief's question.
- One USD prim type, sublayers only, writer currently typeless (`Sdf.SpecifierDef` with no `typeName`). Codeless schema migration via `usdGenSchema` is plausible — not this brief's question either.
- No identity, no auth, no network, no containerization. Cloud-readiness is downstream.
- Embedder seam is consumer-side: `embedding: List[float]` is a parameter Moneta receives, not produces. Confirmed substrate decision.
- 94 tests pass — this is the safety net for any refactor.

**5. The non-goal.** This brief is *only* about replacing the singleton with a structure that makes multi-instance possible. Concurrency correctness, conflict resolution, identity, auth, and cloud deployment are explicitly downstream and out of scope.

---

## 3. The Decision Under Examination

The proposed direction is a **dependency-injected handle**:

```python
substrate = Moneta(config)
substrate.write(...)
substrate.read(...)
```

Three shapes considered, handle favored over alternatives:

| Shape | Characterization | Why considered |
|---|---|---|
| **Context object** | Explicit `MonetaContext` passed into every API call | Zero magic, fully explicit, easy to reason about in async/cloud |
| **Dependency-injected handle** *(proposed)* | `Moneta(config)` returns a handle, methods hang off it | OO familiar shape, multiple substrates per process trivial, cloud-ready convergence point |
| **Contextvar-scoped state** | `contextvars.ContextVar` holds current substrate, API calls read implicitly | Smallest diff from current API, async-safe, but inherits the singleton's worst trait |

**Locked layered decisions, conditional on handle being correct:**

- **Lifecycle:** Context manager from day one
- **Reconstruction policy:** Two handles on the same underlying state explicitly raise
- **Migration path:** Hard cutover, single PR, gated by existing tests passing

---

## 4. Research Questions

**Q1.** Is the dependency-injected handle the right shape?
**Q2.** What is the correct module-level audit method?
**Q3.** What is the correct construction-time signature?
**Q4.** Where is the seam between this surgery and the next?

(Full question text in original brief; Section 5 below is the Deep Think response addressing each.)

---

## 5. Deep Think Response

### 5.1 Q1 Verdict — The Shape

**Verdict:** The **dependency-injected handle** (`substrate = Moneta(config)`) is strictly the correct shape. The proposed direction is sound.

**Reasoning & Alternatives:**

- **Against Contextvars:** `contextvars` are designed for orthogonal, ambient execution metadata (trace IDs, request scopes) where the business logic does not directly mutate the state. A cognitive substrate is a primary domain actor. Hiding it in a contextvar replaces a hardcoded module singleton with a spatially-scoped global singleton. In deep async agent loops, mismanaged task boundaries or thread-pool delegations can cause the contextvar to drop out or silently bleed state across concurrent tasks.
- **Against Context Objects:** Passing an explicit state record into pure functions (`write(ctx, data)`) is canonical in Go because the language is structured around it. In Python, which lacks implicit receivers, it incurs a severe verbosity tax. It breaks IDE discoverability (typing `substrate.` reveals verbs; typing `write(` requires remembering imports) and infects the host application's business logic, forcing them to thread `ctx` through every tool function. An object-oriented handle *is* a context object, natively encapsulated with its operational verbs via `self`.
- **Against Hybrids:** Providing a handle alongside a contextvar convenience accessor (e.g., `Moneta.current()`) is an anti-pattern. It fractures the integration model and provides an escape hatch for developers to write implicitly coupled tool functions, instantly breaking the multi-tenancy goal.

**The Tradeoff:** Adopting the handle breaks the entire test surface. Modifying 94 plain Python tests and 23 USD tests to explicitly construct and inject a handle is a significant, tedious, one-time cost that you must pay upfront.

**When alternatives win:** Context objects win in purely functional data-transformation pipelines. Contextvars win for transparent observability middleware. Neither applies to Moneta.

---

### 5.2 Q2 Method — The Module-Level Audit

**Verdict:** A regex grep for `^[A-Z_]+ =` is dangerously insufficient. It misses Python's implicit evaluation traps and USD's external C++ state.

**The Audit Procedure (three layers):**

1. **The Static Lint (AST Enforcement):** Configure `ruff` to rigorously target `B006` (mutable default arguments), `B008` (function calls in defaults), and `RUF012` (mutable class attributes).
2. **The Memoization Trap (The Grep):** Manually grep for `@functools.lru_cache`, `@cache`, and `@cached_property`. A module-level pure function that reads global config and caches the result implicitly binds to the singleton. When the singleton dies, the cache dictionary itself becomes a hidden global singleton serving Handle A's data to Handle B. These caches must be migrated to instance-level dictionaries on the handle.
3. **The USD C++ Registry Trap (The Dynamic Gate):** USD relies heavily on a C++ global registry (`Sdf.Layer.FindOrOpen`). If two handles point to the same physical path, USD will quietly hand Python the exact same C++ pointer, recreating the singleton beneath Python's awareness. Before the cutover is complete, write the Twin-Substrate permanent regression test:
   - Construct `m1 = Moneta(uri_a)` and `m2 = Moneta(uri_b)` in the same process.
   - Write data to `m1`.
   - Assert `m1` contains the data, and `m2` does not.
   - Assert `m1`'s quota is decremented, and `m2`'s quota is untouched.
   - If this test passes, true multi-instance isolation is achieved.

---

### 5.3 Q3 Signature — Construction-Time API

**Verdict:** The constructor must accept exactly one argument: a strictly typed configuration object. Zero-argument defaults are forbidden.

**Proposed Signature:**

```python
from dataclasses import dataclass

@dataclass(frozen=True, kw_only=True)
class MonetaConfig:
    storage_uri: str
    quota_override: int = 100
    # Anticipated for cloud (do not implement logic yet):
    # tenant_id: str | None = None
    # sync_strategy: str | None = None

class Moneta:
    def __init__(self, config: MonetaConfig): ...
```

**Reasoning:**

- **Dataclass over `**kwargs`:** Strictly typed dataclass cleanly separates validation/parsing from handle instantiation. Host applications can construct, validate, and serialize this config opaquely before spinning up the heavy USD stage.
- **Irreducible Parameters:** `storage_uri` (anticipates `s3://` or `moneta://` routing without requiring rename later) and `quota_override` (the localized replacement for `PROTECTED_QUOTA`).
- **Forward Compatibility:** By enforcing `kw_only=True`, when cloud parameters (tenant, auth) are added, no existing consumer's positional arguments break. The `Moneta(config)` signature remains frozen forever.
- **The No-Arg Trap:** `Moneta()` must throw a `TypeError`. Friendly defaults (like silently writing to `~/.moneta/default.usda`) obscure the physical storage boundary and cause catastrophic, overlapping state bugs in CI/serverless deployments. Force consumers to declare their boundary on line one. For tests, provide an explicit factory: `MonetaConfig.ephemeral()` to keep test boilerplate low without compromising the primary API.

---

### 5.4 Q4 Seam — The Boundary Between Isolation and Concurrency

**Verdict:** The seam is strictly bounded by **In-Memory Exclusivity**. This surgery establishes single-writer exclusivity; the next surgery transforms it into coordination.

**What this surgery MUST establish NOW (The Invariant):**

To satisfy the locked premise ("Two handles pointing at the same underlying state should explicitly raise"), the handle must represent absolute ownership of the URI for the duration of its context manager.

Introduce a module-level or class-level active registry (e.g., `_ACTIVE_URIS = set()`). During `__enter__`, if the URI is already in the set, synchronously raise a `MonetaResourceLockedError`. `__exit__` removes the URI.

*Tradeoff:* You are replacing a state singleton with an ephemeral lock singleton. This is structurally correct. It physically prevents developers from writing agent loops that accidentally rely on undefined concurrent USD write behavior.

**What this surgery MUST NOT establish (The Premature Trap):**

Do not implement OS-level file locking (e.g., `.lock` files), transaction APIs (`.commit()`), or retry-backoff queues.

Implementing a file-lock on disk requires handling stale locks, crash recovery, and PID tracking — these are true concurrency problems. By limiting the current lock to an *in-memory process set*, you perfectly solve the exact constraints in front of you (multi-instance testing and multi-tenant SDK isolation) without writing bespoke local concurrency logic that will be immediately thrown away when the cloud layer dictates a distributed concurrency model.

---

### 5.5 Bottom Line

The **dependency-injected handle**, strictly configured via a `MonetaConfig` dataclass and managed as a context manager, is the unequivocally correct architecture for an embedded cognitive substrate. It avoids the implicit scoping traps of contextvars and perfectly mirrors the structural expectations of modern SDKs. The single most important execution requirement is **ruthlessly enforcing process-level exclusivity at the constructor**: use an in-memory lock to explicitly crash if overlapping handles are instantiated, forcing consumers to serialize access today so you preserve a pristine, predictable foundation for cloud-concurrency tomorrow.

---

## 6. G1 Ruling Clarifications

These rulings were issued during execution at the post-audit human gate. They reconcile design intent with findings the brief did not have visibility into. Authoritative for Forge work.

### 6.1 Existing `MonetaConfig` Field Preservation

**Finding:** Scout's audit identified that the existing `MonetaConfig` dataclass carries nine fields (path/tuning/backend) that six test files depend on. The Deep Think brief did not have visibility into these existing fields when proposing the new signature.

**Ruling:** Field preservation, not field replacement. The signature in Section 5.3 is **additive**, not **exhaustive**.

- `storage_uri` is added as the canonical addressing field. It does **not** subsume the existing `path` / `tuning` / `backend` fields.
- Existing fields stay. Their semantics do not change in this surgery.
- `quota_override` replaces the `PROTECTED_QUOTA = 100` module-level constant — that is the only true field replacement in this surgery.
- The `frozen=True, kw_only=True` constraints and the cloud-anticipated commented fields apply to the **whole** config — meaning if any existing field was already mutable or positional, that's a flag-for-PR-notes situation, not a silent break.

**Scope:** This ruling is for the singleton surgery only. Any consolidation of `path`-style fields into `storage_uri` semantics is a separate, downstream pass — out of scope here.

### 6.2 Twin-Substrate Test Scope

**Finding:** Scout asked whether the Twin-Substrate regression test exercises disk-backed paths (where the `Sdf.Layer.FindOrOpen` C++ registry trap manifests) or anonymous-mode paths.

**Ruling:** Disk-backed paths are primary. The C++ registry trap is the entire reason the test exists — anonymous-mode coverage is complementary, not substitute.

- Forge writes the disk-backed Twin-Substrate test in Step 2.
- Crucible's adversarial pass adds anonymous-mode coverage as additional verification.
- If existing test infrastructure makes disk-backed setup expensive, that's a Forge implementation question, not a scope question. Solve the infrastructure cost; do not retreat to anonymous mode.

### 6.3 Brief-on-Disk Requirement

**Finding:** The brief was referenced by `HANDOFF_singleton_surgery.md` as the design source of truth, but did not exist on disk. The constitution's PR-note mechanism cannot point to a missing document.

**Ruling:** This document is the brief on disk. Saved at `DEEP_THINK_BRIEF_substrate_handle.md` at repo root. Forge may now flag PR notes against it where execution surfaces design ambiguity that this document does not resolve.

---

## 7. End of Brief

Sections 1–5 are frozen. Section 6 is appendable for future gate-level rulings during this surgery. New rulings are dated and identified by gate (e.g., G2.1, G2.2 for Crucible-stage rulings). Anything requiring a Section 1–5 modification is a redesign, not a ruling, and routes back to Architect — not Forge.
