# SYNAPSE against the v5 facade

**Question:** can SYNAPSE's `MonetaBackedStore` run on Moneta v5 with no SYNAPSE change?

**Answer:** 247 of 253 of SYNAPSE's Moneta-facing tests pass unchanged. The 6 that fail each assert that v1 *loses data*; v5 keeps it.

## What was run

| | |
|---|---|
| SYNAPSE | `655766a` (VERSION 5.80.0), unmodified |
| Moneta | branch `v5`, `moneta.v5.compat.Moneta` swapped in for `moneta.Moneta` |
| Runtime | CPython 3.11.15, OpenUSD 26.08 (`usd-core`), Linux |
| Swap | `scripts/v5/synapse_v5_swap.py`, a pytest plugin. It rebinds `moneta.Moneta` and nothing else in production code. |

Test files (17): `test_moneta_store`, `test_moneta_crucible`, `test_moneta_fc4_audit`, `test_moneta_integration`, `test_moneta_runtime`, `test_moneta_search_serialization`, `test_w3_store_contract`, `test_w3_dim_contract`, `test_w3_harden_crash_recovery`, `test_w3_harden_concurrency`, `test_sleep_pass_gate`, `test_memory_lifecycle`, `test_memory_seam_defects`, `test_store_backend_health`, `test_w3_migrate`, `test_ledger_moneta_seam`, `test_moneta_substrate_truth`.

```text
# baseline, v1
python -m pytest -o addopts="" <files>                                        253 passed, 5 xfailed

# v5 facade, SYNAPSE untouched
PYTHONPATH=<moneta>/scripts/v5 python -m pytest -p synapse_v5_swap -o addopts="" <files>
                                                                               237 passed, 16 failed, 5 xfailed

# v5 facade + two SYNAPSE test helpers re-pointed (MONETA_V5_PORT_HELPERS=1)
                                                                               247 passed, 6 failed, 5 xfailed
```

## The first run found two real incompatibilities, both fixed in v5

1. **Zero vectors.** SYNAPSE deposits a zero embedding for empty content, and v1 stored it. v5 first rejected it; it now stores it as *unrankable*. The memory is enumerable, never similarity-ranked, and `explain()` says why.
2. **`snapshot.json` is a de facto public file.** SYNAPSE reads it for dim reconcile, quarantine, export, backfill and cross-process reads, and rewrites it on an embedder swap. Under the facade it is now a derived v1-format export, written by `durability.snapshot_ecs()` with v1's own tmp → fsync → replace primitive. The embedder-swap rewrite is accepted as a journaled `revector`. Any other foreign write is refused (`SnapshotDivergedError`).

## The 10 helper-only failures

`test_moneta_crucible.py` and `test_moneta_fc4_audit.py` fake the passage of time by writing v1's private column `ecs._last_evaluated`, and check consistency via `ecs._ids`. That is test scaffolding, not a production dependency. With the helpers re-pointed at the exact v5 equivalents (`record.anchor_t`, and index-vs-fold consistency), all 10 pass, including SYNAPSE's concurrent add/prune and prune-audit tests. The long-term fix on SYNAPSE's side is to pass a clock rather than edit internals.

## The 6 failures that remain, and why they should

| Test | v1 expectation | v5 result |
|---|---|---|
| `test_corrupt_snapshot_is_quarantined_not_fatal` ×5 | a corrupt `snapshot.json` means a **fresh, empty store** | the store still holds its memory: the snapshot is derived and the journal is intact |
| `test_interrupted_replace_leaves_prior_durable_state_readable` | a crash during the 2nd save **loses the 2nd memory** (`['mem_A']`) | both memories survive (`['mem_A', 'mem_B']`): the deposit was journaled before `add()` returned |

These tests pin v1's failure modes as the contract. Under v5 they should be updated to assert the stronger guarantee.

## What this does not show

- Houdini/hython. These ran under plain CPython. SYNAPSE's `test_loop_integration.py` needs Houdini, Hanish and Octavius runtimes and was not run.
- Mixed interpreters. If hython and the server Python load *different* Moneta versions against one store, v1 would write `snapshot.json` behind v5's back. v5 detects that and refuses to open. It does not merge. Cut over both interpreters together.
- Production data. No real SYNAPSE store (e.g. the 841-record store from the 17 Sep incident) was migrated here.
