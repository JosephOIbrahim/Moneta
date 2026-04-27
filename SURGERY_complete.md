# SURGERY complete — Singleton → Handle

**Surgery:** Singleton-to-handle migration in `moneta`.
**Design source of truth:** `DEEP_THINK_BRIEF_substrate_handle.md` (§§5.1–5.4 + §6 G1 rulings).
**Operating contract:** `EXECUTION_constitution_singleton_surgery.md`.
**Status:** All work complete; awaiting **G3** human sign-off.

---

## What changed

- **Module-level singleton replaced with a `Moneta` handle.** `_state` (`api.py:124`), `init()`, `_require_state()`, `_reset_state()`, `MonetaNotInitializedError`, and the free-function four ops are gone. The four-op surface (`deposit`, `query`, `signal_attention`, `get_consolidation_manifest`) plus `run_sleep_pass` now hang off `Moneta` as instance methods. Signatures are MONETA.md §2.1-verbatim modulo the `self` receiver added for OO dispatch.
- **`_ACTIVE_URIS` exclusivity registry.** Module-level `set[str]`. `Moneta.__init__` checks-and-adds; `Moneta.close()` (also `__exit__`) discards. Two live handles on the same `storage_uri` raise `MonetaResourceLockedError` at the second constructor call. In-memory only — no file locks, no transactions, no retry queues per §5.4.
- **`MonetaConfig` is now `frozen=True, kw_only=True` and additive (per G1.1).** `storage_uri: str` (irreducible) and `quota_override: int = 100` (irreducible, replaces the module-level `PROTECTED_QUOTA` constant) were added. All nine pre-existing fields preserved with unchanged semantics. `MonetaConfig.ephemeral(**overrides)` factory generates a unique `moneta-ephemeral://<hex>` URI per call and forwards keyword overrides for test ergonomics.
- **Context-manager lifecycle from day one.** `with Moneta(config) as substrate:` is canonical. `__exit__` order: durability close → authoring-target close → URI discard. `close()` is idempotent; partial init releases the URI lock via `try/except BaseException`.

---

## Audit findings (Scout, three-layer)

| Layer | Tool | Findings |
|---|---|---|
| 1 | `ruff B006/B008/RUF012` | Zero. |
| 2 | `@lru_cache` / `@cache` / `@cached_property` at module level | Zero. |
| 3 | Manual catalog + USD `Sdf.Layer` C++ registry | Singleton `_state`; process-wide `PROTECTED_QUOTA`; six call-site files in tests; six `Sdf.Layer.{CreateNew,FindOrOpen}` sites guarded by `_ACTIVE_URIS` and verified by Twin-Substrate. |

**Lint posture.** Pre-surgery `ruff check src/ tests/` reported **124 errors** (inherited project style debt — `Optional[X]` / `List[X]` / `Dict[X,Y]` from `typing` rather than PEP 604). Post-surgery: **113 errors**. Net **−11**, no new lint failures introduced. Remaining are inherited and explicitly **out of scope** per handoff §"What This Surgery Is Not" — "Not a refactor pass for code quality."

---

## Surprising findings

**Empirical TOCTOU result.** Forge's `_ACTIVE_URIS` is `if x in S: raise; S.add(x)` — theoretically a check-then-add race. Crucible's adversarial pass barrier-aligned **30 iterations × 16 threads = 480 concurrent-construction attempts** on the same URI per iteration. **Zero double-acquisitions observed.** This is **evidence under the documented runtime (CPython 3.11/3.12 with the GIL), not proof under free-threaded Python (PEP 703) or sub-interpreters.** The audit (§F5) had already parked free-threaded correctness as downstream; the empirical signal here is that under the runtime the surgery actually targets, the invariant holds in practice.

---

## Limitations carried forward (next surgery)

| Limitation | Why it's parked |
|---|---|
| Free-threaded Python TOCTOU on `_ACTIVE_URIS` check-then-add | Brief §5.4: "the next surgery transforms exclusivity into coordination." Lock-free correctness under PEP 703 is concurrency, not exclusivity. |
| Same `usd_target_path` / different `storage_uri` → C++ registry layer-pointer collapse | `_ACTIVE_URIS` keys on `storage_uri`. Two handles with distinct URIs but overlapping disk paths bypass the guard; pxr's `Sdf.Layer` registry then collapses them. Brief §5.4 same parking — coordination is the next surgery's scope. |

Both are documented in `AUDIT_pre_surgery.md` (§F5, §3.8) and were observed but deliberately not addressed by Crucible's adversarial cases.

---

## Test count

| Surface | Before | After |
|---|---|---|
| Plain Python passing | 94 | **107** |
| Plain Python skipped (pxr-gated) | 2 | **4** |
| Surgery-added pxr-gated cases verified under hython | — | **2** (`TestTwinSubstrateRealUsdDiskBacked::test_real_usd_handles_are_isolated_on_disk`, `TestUsdLayerCacheAdversarial::test_distinct_uris_with_distinct_usd_paths_have_distinct_layers`) — both **PASS** |

Net **+13 always-run tests** (3 Twin-Substrate disk-backed mock, 10 Crucible adversarial) and **+2 pxr-gated tests** verified green under hython. The pre-existing 23 pxr-gated tests were not re-run (out of scope; G2 was conditioned only on the two surgery-critical cases). **0 regressions** observed at any phase boundary.

---

## Version

**Bumped to `1.1.0`.** Rationale (locked, not a question):

- No external consumers depend on the module-level singleton API at the time of surgery (8 GitHub stars, no inbound integrations).
- The handle API is the v1 contract consummating itself; the singleton was always provisional.
- Future API breaks follow strict semver from this point forward.

`pyproject.toml` updated. Stale `dist/moneta-0.2.0.{whl,tar.gz}` removed. **Wheel regeneration at 1.1.0 is deferred** to a separate pass — outside this surgery's scope.

---

## Gate trail

| Gate | Cleared by | Artifact |
|---|---|---|
| **G0** — design | Human (pre-surgery) | `DEEP_THINK_BRIEF_substrate_handle.md` + `HANDOFF_singleton_surgery.md` |
| **G1** — audit | Human (mid-surgery rulings) | `AUDIT_pre_surgery.md` + `DEEP_THINK_BRIEF_substrate_handle.md` §6 |
| **G2** — verification | Crucible (structural) | 107/107 plain Python; 2/2 surgery-critical pxr-gated under hython |
| **G3** — surgery complete | **Awaiting human sign-off** | this document |

---

## Files touched

**Production:** `src/moneta/api.py` (rewritten), `src/moneta/__init__.py` (rewritten), `pyproject.toml` (version bump), `dist/` (stale 0.2.0 artifacts removed).

**Tests rewritten for handle API:** `tests/conftest.py`, `tests/unit/test_api.py`, `tests/integration/test_durability_roundtrip.py`, `tests/integration/test_end_to_end_flow.py`, `tests/integration/test_real_usd_end_to_end.py`, `tests/load/synthetic_session.py`.

**Tests added:** `tests/test_twin_substrate.py` (Forge — Step 2 truth condition), `tests/test_twin_substrate_adversarial.py` (Crucible — six adversarial cases per Constitution §7).

**Untouched (out of scope per `AUDIT_pre_surgery.md` §F7):** `src/moneta/{ecs,decay,attention_log,consolidation,durability,manifest,mock_usd_target,sequential_writer,types,usd_target,vector_index}.py`; `tests/unit/{test_ecs,test_decay,test_attention_log,test_usd_target}.py`; `tests/integration/test_sequential_writer_ordering.py`.

---

*Steward, awaiting G3.*
