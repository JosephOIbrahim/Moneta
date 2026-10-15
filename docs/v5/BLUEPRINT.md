# Moneta v5 — Blueprint

**Status:** reference implementation plus the Round 4 (§9) brief. v5 is built and tested on branch `v5`. It changes nothing in v1, and `moneta.Moneta` is still the v1 handle.

**Date:** 22 September 2026 · **Base:** `main` @ `6cf05f5` · **Owner:** Joseph Ibrahim

**Tags used below:**

- `[V]` means verified, either by running code in this repo or by a test in this branch.
- `[P]` means a decision proposed here, waiting on your ruling.
- `[U]` means unmeasured.

---

## 0. You are here

v5 exists as working code: `src/moneta/v5/`, about 3,150 lines, with 124 new tests. The full suite is 273 green under OpenUSD 26.08, and all 149 v1 tests are untouched `[V]`.

SYNAPSE 5.80.0 was run unchanged against the v5 facade. 247 of its 253 Moneta tests pass. The 6 that fail assert v1 data loss, which v5 no longer has `[V]` (see `SYNAPSE_COMPAT.md`).

v5 changes three locked decisions. The repo's own rules say that needs a §9 round before v5 becomes the default. Section 7 is that brief. Nothing flips until you rule on it.

---

## 1. First principles

Strip Moneta to what an agent needs, and three facts fall out.

**The journal is the database.** Every change is one checksummed, fsync'd line appended to one file. Record state, the vector index and the USD layers are all derived by folding that file, and all of them can be deleted and rebuilt.

**Reads are pure.** A read is a function of four things: the journal prefix, the policy, the context and the evaluation time. It never writes. The same inputs always give the same answer, ties included.

**Records don't compose; policy does.** Two contradictory memories are two things with their own provenance, not two opinions about one thing. Policy, meaning which scopes a context admits, which records it excludes and which claim wins a slot, is where opinions genuinely compete. So policy is where USD composition does load-bearing work.

Everything else in v5 follows from those three sentences.

---

## 2. What the code said

At HEAD `6cf05f5`, eleven defects are reproducible. Each one is a pair of tests in `tests/v5/test_v1_defects.py`. The `test_v1_*` half passes *because* the defect exists, and the `test_v5_*` half shows the fix `[V]`.

| # | v1 behavior | Where | v5 |
|---|---|---|---|
| P1 | A deposit is lost on restart unless a sleep pass ran. The snapshot is only written in `run_sleep_pass`, and the 30 s daemon is never started. | `api.py:472` | Durable on return (fsync'd journal) |
| P2 | A wrong-dim deposit raises *after* the ECS row is added, leaving an orphan row with no vector | `api.py:363` then `:372` | Validate first, then journal, then fold |
| P3 | A wrong-dim query returns `[]` as success | `vector_index.py:156` | `DimensionMismatchError` |
| P4 | Attention reduce sets `LastEvaluated = now` before decay runs, which erases decay since the last read | `ecs.py:212-214` | Attention applied at its own timestamp |
| P5 | One weight of −5 or NaN deletes a fresh memory in a single pass | `ecs.py:212` + floor clamp | Weights must be finite and in [0, 1] |
| P6 | Unknown ids go into the WAL, and one malformed WAL line stops the store opening | `durability.py:170` | Unknown ids raise before anything is written |
| P7 | Consolidated rows stay in RAM forever, and USD is never read back | `consolidation.py:108` | Consolidation is a journaled status |
| P8 | A failed USD commit strands records in `STAGED_FOR_SYNC` forever | `consolidation.py:177-183` | Failed projection is retried next pass |
| P9 | `query()` writes state: every read mutates utility and `LastEvaluated` | `api.py:401` | Reads are pure |
| P10 | Prune reports a count; what was deleted is gone | `consolidation.py:190` | `pruned_ids`, and payloads stay readable in `explain()` |
| P11 | Two URIs on one snapshot path both open and silently lose writes | `api.py:204` | OS file lock on the resolved path |

**P4 is a spec defect, not only a code bug.** ARCHITECTURE.md §5 prescribes `LastEvaluated = now()` at attention write. §4 then prescribes decay evaluation point 2 *after* that write. The code does exactly what the locked spec says, and the spec erases decay. That is a §9 Trigger 2, a spec-level surprise.

**The ranking discrepancy is settled.** The May audit (at `2965e5d`) was right that ranking inverted on negative cosine. The clamp landed afterwards, in `c4a6218` on 5 August. Both audits were correct about their own commits `[V]`.

**The real specification was the consumer.** SYNAPSE's `MonetaBackedStore` is 1,300 lines, and much of it compensates for the defects above. It snapshots the whole store on every `add()` (P1), quarantines corrupt snapshots and WALs (P6), and diffs the ECS before and after each sleep pass to find what was pruned (P10). Its own comment says the WAL is "INERT under SYNAPSE… do not read it as 'deposits are journalled today,' because they are not." v5 is the upstream answer to that comment.

---

## 3. Architecture

```
               agent tools / SYNAPSE
                       │
      ┌────────────────┴────────────────┐
      │ compat.Moneta (v1 surface)      │   same MonetaConfig, same four signatures
      │ Substrate (v5 surface)          │   + recall / explain / describe_context
      └────────────────┬────────────────┘
        writer lock ── │ ── every write: validate → journal.append → fold.apply
                       │
   ┌───────────┬───────┴──────┬──────────────┬──────────────────┐
   │ Journal   │ Fold         │ ExactIndex   │ PolicyResolver   │ Projector
   │ TRUTH     │ derived      │ derived      │ port             │ port
   │ .journal  │ records,     │ unit vectors │ Plain │ USD      │ Memory │ USD (v1 UsdTarget)
   │ crc+fsync │ anchors      │ rebuilt open │ same answers     │ derived, retried
   └───────────┴──────────────┴──────────────┴──────────────────┘
```

| Module | Role |
|---|---|
| `journal.py` | Framed `<crc32> <json>\n` lines with gap-free `seq`. A torn tail is truncated; mid-file corruption refuses to open. `repair()` quarantines, never deletes. Exclusive OS lock. Failed appends roll the file back. |
| `model.py` | `Record`, `Status`, the vector codec (exact float64, base64), and `Fold`, the only state machine |
| `index.py` | Exact cosine over precomputed unit vectors. Rebuilt at every open, never persisted. |
| `policy.py` | `ResolvedPolicy`, `PlainPolicyResolver`, context chains |
| `substrate.py` | The handle: four ops, `recall`, `explain`, `describe_context`, and the operator ops |
| `compat.py` | v1-shaped facade, v1 migration, derived `snapshot.json` export, second-writer guard |
| `usd/policy.py` | `UsdPolicyResolver`: one layer per context, parent = sublayer |
| `usd/projection.py` | Writes one generation as typed `MonetaMemory` prims |

The core imports no `pxr`. USD lives only behind the two ports.

---

## 4. Events

Every line in the journal is one of these:

| op | Written by | Effect |
|---|---|---|
| `genesis` | first open | format, version, configured dim and half-life |
| `deposit` | `deposit()` | new record: payload, vector, floor, scope, slot, idempotency key |
| `import` | v1 migration | a v1 row with its utility anchor, attended count and state |
| `attend` | `signal_attention()` | weights, applied at the event's own `t` |
| `retain` | `run_sleep_pass()` | this pass's tombstones and stages; always written, even when empty |
| `consolidate` | `run_sleep_pass()` | a batch that projected successfully |
| `tombstone` / `erase` | operator | retire from recall / remove payload and vector |
| `revector` | `revector()` | embedder swap: a new vector for every recallable record |
| `note` | migration, compat | provenance only |

`compact()` is the one rewrite. It removes erased payloads and vectors from every event that carries them (`deposit`, `import` and `revector`), keeps every `seq` and each erased record's dimension, and uses tmp → fsync → replace → fsync(dir). If the replace fails, the handle keeps working on the old file.

---

## 5. Semantics

**Utility.** Each record carries an anchor `(U, t)`. Utility at time `t` is the locked formula, imported unchanged from `moneta.decay.decay_value`:

```
U(t) = max(floor, U_anchor · e^(−λ(t − t_anchor)))
```

**Attention.** At the signal's time, attention decays the anchor to that moment, adds `w`, clamps to 1, and moves the anchor. This is the P4 fix. Attention is visible to the very next read.

**Changing the half-life** reinterprets history, deterministically. Anchors are recomputed on replay with the current λ `[P]`. That answers the capsule's open question about decay anchors under policy change, and it needs your ruling.

**Ranking.** Records are ranked by `max(cosine, 0) × utility`, which is v1's clamp from `c4a6218`. Ties break by deposit order.

**Retention.** Retention uses the v1 Round 2 thresholds unchanged (prune below 0.1 with fewer than 3 attends; stage below 0.3 with 3 or more). Pruning is a tombstone, not a delete.

**Verdicts.** `explain()` returns exactly one of these, and each has a reason:

- `eligible`
- `not_allowed_for_caller`
- `excluded_scope`
- `excluded_record`
- `slot_loser`
- `unrankable`
- `tombstoned`
- `erased`
- `unknown`

**Policy.** A context is a layer with an optional parent. For each field, the strongest authored opinion wins, and lists replace rather than merge. Slot selections resolve per slot.

**Slot fallback.** If a slot has no selection, or its selection is ineligible in the current context, the most recent eligible claim wins.

**Authorization.** Host-supplied `allowed_scopes` intersect with policy. They can only narrow what a caller sees.

**Zero vectors** are stored as *unrankable*. The record is enumerable and prunable, but never similarity-ranked, and `explain()` says so. SYNAPSE depends on this for empty content.

---

## 6. Invariants → tests

| Invariant | Test (`tests/v5/`) |
|---|---|
| I1 recoverability | `test_i1_reopen_reproduces_results_exactly` (no sleep pass, no checkpoint), `test_a_fold_failure_after_a_durable_append_stops_the_handle` |
| I2 generation purity | `test_i2_writes_and_policy_edits_cannot_interleave_a_query` (a paused resolver while another thread edits policy and deposits a top-scoring record), `test_i2_every_result_echoes_its_generation` |
| I3 append-only claims | `test_i3_contradictory_claims_coexist_and_context_picks`, `test_i3_journal_bytes_only_ever_grow` |
| I4 no silent empties | `test_i4_wrong_dimension_query_raises`, `test_i4_rejected_deposit_leaves_no_trace`, `test_i4_attention_is_all_or_nothing`, `test_i4_direction_less_memory_is_stored_enumerable_and_explained`, `test_index_miss_raises_instead_of_dropping_a_memory` |
| I5 authorization narrows | `test_i5_caller_scopes_narrow_a_permissive_policy`, `test_i5_caller_scopes_cannot_widen_a_policy` |
| I6 determinism | `test_i6_same_journal_same_answers_in_another_process`, `test_i6_reads_never_write`, `test_reads_leave_all_record_state_untouched` (every field of every record), `test_i6_ties_break_by_deposit_order` |
| I7 four states | `test_i7_resident_excluded_tombstoned_erased_are_distinct`, `test_i7_erase_plus_compact_removes_bytes` |
| I8 ordering without a GIL | `test_every_fold_apply_holds_the_substrate_lock` (6 threads mixing deposits and signals; live state must equal replay exactly), `test_i8_concurrent_signals_reduce_in_journal_order`, `test_i8_no_gil_sentinel_in_v5` |

The oracle is the twelve-record, two-project fixture from the capsule. It has a protected record, a contradictory slot pair, a scoped exclusion and a record two half-lives old. Its orderings and scores were written by hand from closed-form cosines, not produced by running the code (`fixture.py`).

---

## 7. Round 4 brief: the locked decisions

| # | Locked decision | v5 | Needs a ruling |
|---|---|---|---|
| 1 | Four-op API, no fifth op | **Kept.** Same names and positional signatures, with keyword-only additions. `recall`, `explain` and `describe_context` are read-only projections. `revector`, `tombstone`, `erase`, `compact` and `sync` are harness-level operators, like `run_sleep_pass` under Ruling B. | no |
| 2 | Decay math, exactly three evaluation points | **Formula kept verbatim.** "Three evaluation points" becomes "zero mutation points", because decay is now a pure function evaluated anywhere. | **E2** |
| 3 | Append-only attention log reduced at the sleep pass, GIL-dependent | **Generalized** to one append-only journal for every write, ordered by a single writer lock. That is not per-entity locking, so §5.1's prohibition holds. Attention becomes visible immediately instead of at the next pass. The PEP 703 sentinel goes. | **E3** |
| 4 | USD first, vector second; the vector index is authoritative for "what exists" | **Replaced.** The journal comes first and is authoritative. The index and USD are both derived. | **E1: the crux** |
| 5 | Handle, not singleton | Kept. Exclusivity moves from a URI string to an OS lock on the path; compat keeps the URI registry too. | no |
| 6 | Codeless typed schema | Kept. The projection writes the same typed prims through v1's own `UsdTarget`. | no |
| — | §15.2 envelope | Kept for projection (500-record batches; rotation inherited) | no |
| — | §8 cache warming, §9 split-brain | **Dissolved.** One truth means there is no second tier to warm and no split brain to resolve. | note only |
| — | Prune deletes | Prune tombstones; physical deletion is `erase` + `compact`. | **E4** |

**E1: authority.** v1's §7 makes the one structure that cannot survive process death the authority for existence. v5 makes the one structure that is fsync'd the authority. Every other v5 change follows from this.

**E2: decay evaluation.** The spec order in §4/§5 erases decay (P4). v5 applies attention at its own timestamp and never mutates on read. The locked formula is untouched.

**E3: concurrency.** The GIL argument is replaced by a total order: one lock, gap-free `seq`. The argument no longer depends on the GIL, and a test asserts that every fold mutation happens under the lock and that live state equals replay. It has not been run on a free-threaded CPython build `[U]`. The trade is that attention is visible immediately, not at the next sleep pass.

**E4: forgetting.** Prune becomes a tombstone, so pruned memories stay explainable. `erase` + `compact` is the only physical delete, which also gives Moneta a real "forget this" for privacy.

---

## 8. USD's role in v5

USD's first job is **policy**, not storage. `UsdPolicyResolver` turns each context into a layer and each parent into its sublayer, so `projA.review → projA → default` is an ordinary sublayer stack. Pcp computes the answer to "which memories may this session see, and which claim wins each slot".

For every context in the fixture, and for 60 randomly generated validated specs, the USD resolver and the plain Python resolver produce identical resolved policies and identical fingerprints. On the fixture they also produce identical recall results `[V]` (`test_usd.py`, `test_review_regressions.py`). That makes the plain resolver a fair control (the capsule's arm C) and the USD one the treatment (arm D), with correctness settled before any benchmark.

Slot prims are named `s_<sha1>`, never from the slot's text, following substrate convention #1. Layers edited on disk by another tool (a Solaris session, say) are picked up by `reload()` `[V]`.

USD's second job is **projection**. `project_generation()` writes one pinned generation as typed `MonetaMemory` prims, and stamps the root layer with the seq and policy fingerprint it came from. Delete the directory, run it again, and you get the same prims `[V]`.

Composition is still used only for policy. Records stay one prim each. Variants and gist LOD remain future work.

---

## 9. Compatibility and cutover

`moneta.v5.compat.Moneta` takes the unchanged `MonetaConfig`. On the first open of a v1 store, it first copies the original snapshot byte-for-byte to `snapshot.json.v1-original`. Then it migrates the snapshot and WAL tail into `snapshot.v5.journal`. Every skipped or repaired item is counted in a journaled note, including WAL lines with non-finite values. The WAL and the preserved original are never modified.

After that, `snapshot.json` is a **derived v1-format export**. It is written by `durability.snapshot_ecs()`, after every sleep pass, and on `close()`, and even v1 itself can read it.

On open, the facade checks `snapshot.json` against the hashes it wrote or journaled:

- **Unreadable** (corrupt, truncated, wrong shape): ignored with a warning and a journal note. The memory is intact, and the next export replaces the file.
- **Embedder-swap rewrite** (same ids, same payloads, every vector at the newly configured dimension): becomes a journaled `revector`. If the rewrite came from a stale export, the journal records it was missing stay recallable but *unrankable*, are named in the event, and are explained until re-embedded.
- **Anything else** (records the journal doesn't have, changed payloads, a non-swap rewrite): `SnapshotDivergedError`, because that is a second writer.

Every intentional behavior change is listed in `compat.BEHAVIOR_CHANGES`.

**Cutover, one step at a time:**

1. **Merge `v5` as-is.** This is zero-risk: v1 stays the default.
2. **Point SYNAPSE at the facade behind a flag.** This is a one-line change in `moneta_runtime`. Test it on a *copy* of a real store, such as the 841-record one from the 17 Sep incident, and read the migration report.
3. **Update SYNAPSE's 6 tests.** They should assert the stronger guarantees. Drop its per-`add()` snapshot, because deposits are already durable.
4. **Move both interpreters (hython and server Python) together.** v5 refuses a store that v1 has written behind its back. It does not merge.
5. **Flip `moneta.Moneta` to the v5 facade and tag `5.0.0`.** Rollback means going back to v1, which reads the v1-format export.

---

## 10. Measured cost

This is one run on a 2-vCPU cloud container, with 10,000 records at 384 dimensions (`scripts/v5/bench_v5_vs_v1.py`). It is **not** your Threadripper and not the Blueprint-B benchmark `[V, this machine only]`.

| | v1 | v5 |
|---|---|---|
| Query, top 10 (median) | 345 ms | 161 ms |
| Make one deposit durable | 3.26 s (full snapshot, which is SYNAPSE's per-`add()` pattern) | 0.43 ms (one fsync'd append) |
| Open (hydrate / replay) | 1.6 s | 1.0 s |
| On-disk size | 81.7 MB (`snapshot.json`) | 42.6 MB (journal) |

Two conclusions follow.

The durability cost, not the scan, was what hurt SYNAPSE. v5 removes it.

The query path, now pure Python over unit vectors, is still about 3× away from the 50 ms p95 gate even at 10k records, let alone 100k `[U at 100k]`. That is the case for arm P (a native scan behind `ExactIndex.cosines`) before any Rust port.

---

## 11. Where Rust fits

It fits behind two seams that now exist: `ExactIndex.cosines()` (the scan) and `Fold.apply()` (the replay). Both are pure, both have exact oracles in this suite, and both can be swapped without touching the journal format or the API.

The order stays as decided on 8 September:

1. **Arm P first:** a numpy or native scan, gated by the conformance suite.
2. **Rust only if P misses its gate.**

oxideav-usdz stays parked. It is an adapter question, and the USD adapters now pass through v1's official-OpenUSD writer.

---

## 12. Not done, and open

- **Checkpoints.** Open time is a full replay. It is linear, estimated at about 10 s at 100k `[U]`. A fold checkpoint would bound it.
- **Compaction beyond erase.** The journal grows forever.
- **Embeddings in blobs.** Each record costs about 4 KB in the journal at 384 dims.
- **Group commit.** Every deposit fsyncs on its own.
- **Windows.** The `msvcrt` lock path and the skipped directory fsync are untested here `[U]`.
- **In-process USD reopen.** v1's `UsdTarget` collides with the Sdf layer registry. This is inherited; v5 now reports it as `projection_error` instead of failing to open.
- **List fields in policy replace rather than merge.** That is a design choice `[P]`. USD list-edit ops are not used.
- **Retention thresholds** are still the untuned Round 2 defaults.
- **Recovering from `SnapshotDivergedError` is manual:** move the snapshot aside, or remove the journal to re-migrate.
- **Octavius** and its shared stage conventions are untouched.

---

## 13. Independent review

A reviewer who had not written the code read it, reproduced defects by running code, and mutation-tested the suite. It found one critical issue plus several major and minor ones. All are fixed, each pinned by a test in `tests/v5/test_review_regressions.py` or `test_compat.py`:

- **Critical: an invalid `embedding_dim` could write a genesis event that never reopens.** Config is now validated before the journal is opened.
- **Compaction left erased vectors inside `revector` events.** They are now scrubbed, and a compacted store keeps its dimension.
- **The snapshot guard refused four legitimate cases:** a corrupt file, a stale export, a missing sidecar after a crash, and an empty store. See §9.
- **A failed compaction left a dead handle,** and `sync()` could silently no-op. Both fixed.
- **An idempotency key could return a tombstoned or erased id** and store nothing. It now deposits a new memory.
- **Replay could differ from live state in three ways:** a non-string `reason`, dim after erasing everything, and an undocumented half-life change. All fixed, and half-life changes are now noted in the journal.
- **A NaN timestamp in the v1 WAL aborted migration.** It is now counted as malformed.
- **The plain and USD resolvers diverged on non-string specs.** Specs are now type-checked, and equivalence is also asserted on 60 random specs.
- **A double fault in rollback or release** could leave the journal writable after a partial frame, or leave a path locked. Fixed.
- **Five tests passed with their property removed** (mutations M5–M8 and M2b/c). The strengthened tests catch all of them. Thirteen mutations now run against the suite, and none survive.

## 14. Run it

```bash
git checkout v5
pip install -e .[dev] usd-core          # usd-core 26.08 gives pxr on CPython 3.11
python -m pytest                        # 273 passed
python -m pytest tests/v5 -q            # the v5 suite alone
python scripts/v5/bench_v5_vs_v1.py --n 10000 --dim 384
# SYNAPSE against v5, SYNAPSE unchanged:
PYTHONPATH=<moneta>/scripts/v5 python -m pytest -p synapse_v5_swap -o addopts="" <synapse tests>
```
