# Moneta v1.3.0-rc2

**Prerelease, cut from branch `release/v1.3.0-rc2`, not `main`.** `main` and "Latest" stay where they are. The four-operation v1 API and its signatures are unchanged.

**In one line:** attention you signal now survives a bare save and a restart, the attention log is forced to disk before `signal_attention` returns, and the USD mirror reopens its existing layers instead of resetting them.

Range: `v1.3.0-rc1` (`c33bbd96`) to this commit. Verify a build by `commit` + `src_digest` + the wheel's `.pyd` sha256, never by version.

---

## 1 · Attention durability (R1′): defects B, D and L fixed

In rc1, attention that had been signalled but not yet applied by a sleep pass could be lost:

- **B:** `signal_attention`, then a bare save (`m.durability.snapshot_ecs(m.ecs)`, the shape of SYNAPSE's save), then a restart. rc1's save deleted the WAL, so the signal was gone.
- **D:** a signal that landed after a sleep pass drained the log, but before that pass wrote its snapshot, was lost the same way.
- **L (late landing):** an append could land in a list the reducer had already swapped out and read. No pass applied it, and the next save deleted its line.

What R1′ does (design: `docs/design/R1-attention-durability.md`, revision 6):

- Every WAL line carries a sequence number (`seq`). `signal_attention` writes the WAL first, then buffers.
- A save writes a keyed snapshot (`wal_applied_seqs`, `wal_next_seq`) and keeps every WAL line whose seq the reducer has not recorded as applied. A restart replays those lines once.
- The reducer takes one snapshot of each swapped list, so the seqs it records are exactly the ones it applied. A late entry is carried to the next pass, or applied at the next reopen if its appender stalls through that pass too. With one pass at a time it is never applied twice.
- Seqs are recorded before `apply_attention` runs, inside the same `try`. If the pass stops there, the ERROR `torn attention apply` counts the drained seqs it recorded: a recorded seq whose effect may be missing from the rows is a stated loss, never a silent double, and an unrecorded seq keeps its WAL line and replays at the next reopen.
- The reducer stays lock-free: one swap, one reducer, no lock, no CAS. The snapshot and WAL format versions are unchanged; the new snapshot keys are optional, and rc1 parses them.

**Path L, as ruled.** Gate 2 of the design, decided under the owner's delegation, ruled path L an implementation defect that the append-log pattern absorbs, not a MONETA.md §9 Trigger 2. L was not pinned as a known defect; test AI covers it, and this release names it fixed. `docs/rounds/round-4-attention-log-late-entry-brief.md` remains in the tree as the record of the question; its status and "Freeze" lines are now marked superseded by that ruling.

Commits: `b7041df` (production), `b122a3a` (tests), `14f060f` (docstrings and docs), `6040903` (the reducer try window, from the Architect review), `6db69c7` (step 0 and step 4 wording), `b460e78` (design revision 6), `711d7fb` (step 0 applies the disposition only to the WAL hydrate read, from the cross-review), `3da0053` (docstrings) and `1c42f87` (design revision 6 records the cross-review). Merged as PR 1 of 2 in `0c7f96b`.

## 2 · The attention log is forced to disk (Round 4 F1)

- Every WAL append is fsync'd before `signal_attention` returns. Measured on one Windows workstation: 1.16 ms median, 2.1 ms p95 per signal.
- Every file a save publishes is fsync'd before its `os.replace`. On POSIX the directory is fsync'd after each rename and unlink.
- A failed fsync takes the existing truncate-and-close path: the signal raises `OSError` and leaves no line.
- No signature, file-format or seq change.

Commit: `075eb64`.

## 3 · The USD mirror reopens instead of resetting

rc1 opened the cold-tier layers CreateNew-first, which reset the mirror's sublayer stack whenever a fresh process reopened an existing store. This release adopts the reopen-first candidate `ce45f133` (prepared by Codex outside this repository; it is not in this repository's history), applied unchanged, plus two conditions of its adoption and one fix from its review:

- Existing layers are opened first and created only when absent. An unopenable existing layer raises; there is no creation fallback.
- Authored sublayer paths, order and offsets survive without a duplicate entry. Counts restart from the layers' top-level prims, rolling routing resumes the highest existing continuation, and `rotation_cap < 1` raises `ValueError`.
- **`flush()` checks `Save()`.** Every layer's `Save()` is checked for a False result and for a raise. The other layers are still saved (sublayers first, root last), then `UsdSaveError` (a `RuntimeError`; `.failures` maps each layer identifier to its cause) names every failed layer. `SequentialWriter` does not catch it, so that batch's vector commit does not happen (ARCHITECTURE.md §7). A failed layer stays dirty, and the next flush retries it.
- **Layer-registry sharing is detected and logged at ERROR.** Before the target loads anything, it scans the process's loaded Sdf layers for files in the store directory and logs one ERROR per layer (`Sdf registry sharing`), naming the layer. Sharing is not refused. The operator card carries gate 2's rule: LOP networks must not edit or reload `.moneta/usd` layers in a live session.
- **A batch authored again after a failed save is re-authored in place** (from the USD Engineer review). A prim that already exists gets its attributes updated instead of raising, and each layer's prim count is its real root-prim count. The v5 compat handle projects a failed batch again on its next pass; the v1 handle does not commit it again (see Honest limits).

Commits: `0062d4a` (the port, with condition C1), `5c71511` (condition C2: the ERROR level and the card rule), `2007612` (re-authoring in place, from the USD Engineer review) and `49643c9` (the store's process and thread assumptions, docs). Merged as PR 2 of 2 in `3c01cf2`.

## 4 · Native observability hardening (on the base since rc1)

- **C1** `ac9662c` (fixes `574f5b2`, `2252ea8`): one central native loader, `moneta._native`, behind both v1 import sites. Corrupt dist-info metadata and a non-int `NATIVE_API` are classified instead of raising; `record_match` prefers the dist-info that matches the loaded version.
- **C2** `2afe041` (fix `7aa4f8e`): the loader is wired into `ECS` and `VectorIndex`, with counters, fallback reasons and a decay failure strategy. Decay columns are restored when native and oracle both fail; a huge-int restore raises `NativeSeamError`.
- **C3** `2510d10` (fixes `da7ecb4`, `7fc41c9`): per-handle native selection, `Moneta.native_status` and `moneta.build_info()`. Require-mode hydrate checks the native envelope.
- **C5** `83ec1b6` (fix `023b338`): the native qualification harness. Native-only tests skip visibly, a fallback guard fails any unmarked fallback, and the last lines of every pytest summary print a verdict.
- **C6** `edbac00` (fix `98a998f`): the durability regression tests that pinned B and D as strict xfails. R1′ passes them unmarked.
- **C7** `495c522` (fixes `3ca6447`, `a5853e7`, `b037eb6`, `e7325bb`): docs for native modes, status, build identity and the verdict line.
- **Gate B** `bec544f`: the decay oracle loop extracted verbatim into `ECS._decay_oracle`, with rollback at the call site.
- `a4f2b0b`: nested test processes keep the parent's import roots; the schema gate proves its identity.
- Docs: `f9117b7` (the operator card's release block), `ea7ee52` (R1 design revision 5), `cc7b1db` (README summary), `986dae0` (the Round 4 brief draft for path L).

## Behaviour changes

Signatures are unchanged, and every new raise is an existing exception type.

| Change | rc1 | rc2 |
|---|---|---|
| `signal_attention` | Buffered, then the WAL. A failed WAL write left the signal applied in memory. | WAL (fsync'd), then the buffer. A failed write or fsync leaves the signal in neither place, and the `OSError` escapes. About 1.2 ms per call. |
| Shared store files | Only the same `storage_uri` was refused. | A second live handle in the same process on the same snapshot, WAL or tmp path raises `MonetaResourceLockedError`, whatever its URI. A config whose own four paths collide raises `ValueError`. |
| Wrong ECS | `snapshot_ecs(any_ecs)` saved it. | `snapshot_ecs` or `start_background` with anything but the handle's `m.ecs` raises `ValueError` and writes nothing. |
| Closed handle | The WAL reopened lazily; a stale save still rewrote the files. | After `close()`, `signal_attention`, `wal_append`, `snapshot_ecs` and `start_background` raise `ValueError("durability manager is closed")`. |
| Unreseedable seq allocator | — | `RuntimeError` at construction. Reaching it needs a hand-edited `snapshot.json`. |
| Concurrent sleep passes | Unsupported, silent. | Still unsupported. Logs ERROR and carries on; never raises. |
| USD reopen | A fresh process reset the sublayer stack. | Existing layers open first; the stack, offsets and counts survive. |
| USD save failure | `flush()` ignored `Save()`'s result. | `flush()` raises `UsdSaveError` after saving the other layers; that batch's vector commit does not happen. |
| USD `rotation_cap < 1` | — | `ValueError("rotation_cap must be positive")` at construction. |
| USD batch authored again | Raised `Tf.ErrorException` ("Cannot create spec") at author time. | Re-authored in place: attributes updated, prim count unchanged. |

The v1 defect register follows the refusal: P11 is now `test_v1_p11_two_uris_on_one_store_are_refused`.

**Upgrading from rc1 is safe.** An rc1 store opens under rc2, and its WAL lines are judged by timestamp, as rc1 would, until the first rc2 save normalizes the WAL.

## Tests

Python 3.14.2 on Windows, `pxr` 0.26.5, v1 and v5 suites together, 2026-10-18, at the merge commit `3c01cf2` (`src_digest` `58600b5811c719c9b6aee547509ae97287acededf65b6ab970c5ddc53e1420b0`). This release commit changes no `*.py`, so its `src_digest` is the same. Wheel: `moneta_native` 0.1.0 abi3, `.pyd` sha256 `ec6d7f0c35c5b345f983f4aa80cfea086f3aca454e9cd74a58b6208227b02833`, with `src` first on `PYTHONPATH`.

| Run | Pytest | Verdict |
|---|---|---|
| wheel, `MONETA_NATIVE=1` | 907 passed | `NATIVE QUALIFIED` (71/71 native tests, qualification 2/2) |
| wheel, `MONETA_NATIVE=require` | 907 passed | `NATIVE QUALIFIED` (71/71 native tests, qualification 2/2) |
| wheel, `MONETA_NATIVE=0` | 907 passed | `PYTHON-ONLY PASS (not native qualified)` |
| no wheel (`ModuleNotFoundError`), env unset | 836 passed, 71 skipped visibly | `PYTHON-ONLY PASS (not native qualified)` |
| no wheel, `MONETA_NATIVE=require` | exit 4 | refused: `requires the native wheel` |
| broken wheel (`ImportError`), env unset | 836 passed, 71 skipped visibly | `PYTHON-ONLY PASS (not native qualified)` |
| broken wheel, `MONETA_NATIVE=require` | exit 4 | refused: `requires the native wheel` |
| hython 3.11, every row | **not run** | — |

- **No xfails.** Through the hardening, B and D ran as 2 strict xfails. They now pass unmarked, and `KNOWN_DEFECTS` in `tests/conftest.py` is empty.
- **Where the 123 new tests come from.** The base `a4f2b0b` ran 782 passed + 2 xfailed with the wheel (the Architect's run). 907 = 782 + B and D + 123 new tests: 90 in the R1′ regression suite (86, plus AB(c2) for the reducer try window and the three AL cases for the step 0 basis), 12 for F1, 19 for the USD reopen (18, plus the re-author after a failed save) and 2 attention-log structural checks. Without the wheel: 711 + 2 + 123 = 836, with the same 71 native-only skips.
- **Each PR alone, same seven rows:** PR 1 (R1′ + F1, `1c42f87`) 888 passed with the wheel and 817 + 71 skipped without it; PR 2 (the USD repair on `a4f2b0b`, `49643c9`) 801 passed + 2 xfailed with the wheel and 730 + 71 skipped + 2 xfailed without it, because B and D are fixed only by PR 1.
- **v5 mutation check:** `scripts/v5/mutation_check.py`, run in a `git archive` copy of the merge commit `3c01cf2`, ends `missed: []`.
- The no-wheel and broken-wheel rows put a shim on `PYTHONPATH` that makes `import moneta_native` raise the named error.
- Each run prints 1 warning: a `DeprecationWarning` from the test machine's `pytest_asyncio` plugin, not from Moneta.

## Honest limits

- **hython rows not run.** Every number above is Python 3.14.2 with `pxr` 0.26.5. Houdini's hython 3.11, with its own OpenUSD, has not run this candidate in any configuration.
- **The USD repair: C1 and C2 are met, and C3 is not run.** Gate 2 adopted the reopen-first repair with three conditions. C1 is met in code: `flush()` checks every `Save()` and raises `UsdSaveError`. C2 is met in code and on the card: sharing is logged at ERROR naming the layer, and the operator card carries the LOP live-session rule. C3, a hython row on the target Houdini build (H22.0.400) before any Houdini seat moves to this code, is not run. The repair is its own review unit (PR 2 of 2); its USD Engineer review returned SOUND-WITH-NITS, and its fix-severity finding is fixed in `2007612`. Its 19 tests ran under `pxr` 0.26.5 only.
- **Registry sharing is detected, not refused.** Detection runs once, when the target is built, so a holder that loads one of the store's layers later is not detected.
- **On the v1 handle, a failed USD save strands that pass's staged entities.** `run_sleep_pass` raises `UsdSaveError`, and every entity the pass staged stays `STAGED_FOR_SYNC` (listed by `get_consolidation_manifest()`): no later v1 pass commits it again. The failed layer stays dirty, and the next flush saves it. rc1 stranded them the same way when a `Save()` raised; when one returned `False`, rc1 marked them consolidated although that layer was not saved. The v5 compat handle projects the batch again on its next pass.
- **The store-path check is in-process only.** Two processes on one store are still unsupported, and nothing detects them.
- **Windows has no directory fsync.** A power loss shortly after a save can roll back that save's renames. Each file stays whole, but a signal appended after a rolled-back WAL rename is lost. POSIX fsyncs the directory.
- **Rolling back to rc1 loses pending attention unless you drain first.** An R1′ store opened by rc1 loses the pending lines with timestamps at or before the snapshot time: exactly the B and D lines R1′ kept. Before a downgrade, quiesce signals, run `m.run_sleep_pass()`, then `m.close()`, then check that the WAL is absent or empty. R1′ → v5 facade → R1′ is unsupported: cut over both interpreters together. The full rollback table is on the operator's card (`docs/OPERATOR_CARD_native.md`).
- **The clock precondition.** Every signal applied before a snapshot must carry a timestamp at or before that snapshot's `snapshot_created_at`. One wall clock running forward satisfies it. A backward clock step, or two clocks, breaks it wherever a line is judged by timestamp (keyless snapshots, rc1, the v5 migration).
- **Async-exception windows.** A `KeyboardInterrupt` within a few bytecodes of a WAL write can leave a phantom apply: a signal whose call raised applies once at the next reopen. Design §1.4 lists the known windows; the list is not claimed to be complete. The window between the reducer recording seqs and applying them is logged (`torn attention apply`). An interrupt right after step 0's `os.replace` (the first save after a reopen) leaves every later save of that handle degraded until it is reopened, logged at ERROR; the disposition is never applied by index to the normalized WAL.
- **Path L timing.** A late entry is applied one pass later, or at the next reopen if its appender stalls through that pass too. The durable state is exact; only in-process timing changes.
- **Saves set the loss bound.** The target of at most 30 s of volatile state lost on `kill -9` needs a save at least every 30 s. Moneta saves at the end of every `run_sleep_pass` and never starts the optional saver thread (`start_background`) itself.
- **v5 stays a gated preview.** The rc1 open items (E3-1, E4-2, E1-B1, the zero-vector slot winner, cross-interpreter drift and the other open conditions) are unchanged.

## Review

The Architect's conformance review of `b7041df`, `14f060f` and `075eb64` against design revision 5 returned **SOUND-WITH-NITS**, with its own runs of the wheel `=1`, wheel `=0` and no-wheel rows at the base and the tip. Its nits are addressed in `6040903`, `6db69c7` and `b460e78` (design revision 6), and in this commit (`CLAUDE.md`). The USD repair was outside its scope.

The USD Engineer review of PR 2 returned **SOUND-WITH-NITS**. Its fix-severity finding, a batch authored again after a failed save raising before `flush()` could save it, is fixed in `2007612`. Three of its eight nits are addressed in docs and docstrings (`2007612`, `49643c9`); the rest are listed as open in the README's rc2 verdict.

The Persistence and Substrate cross-review of PR 1 (design gate 3) returned **SOUND-WITH-NITS**. Its fix-severity finding, a step 0 retry that could apply the hydrate-time disposition to an already-normalized WAL, is fixed in `711d7fb` (test AL); its four nits are addressed in `711d7fb`, `3da0053` and `1c42f87`.

**Owed before publication:** the Architect's sign-off of design revision 6, the owner's acceptance (gate 6), and the public-safety scan of the final range. This candidate is not tagged.
