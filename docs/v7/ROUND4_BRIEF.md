# Round 4 brief: the five Mile 0 rulings

**Who rules:** Joe (owner). This brief recommends a ruling for each item and does not make any of them.
**Where we are:** branch `v7-native-seams`. v5 sits beside v1 (`src/moneta/v5/`, merge commit `861bed9`). Mile 0 has not been ruled (`docs/v7/RULINGS.md:46`, `docs/v7/BLUEPRINT_v7.md:29`).
**What is at stake:** v1's locks 2, 3 and 4 (`CLAUDE.md` "Locked decisions"), plus prune semantics and the half-life rule. This is a MONETA.md §9 escalation.

---

## The table (read this first)

| Ruling | Jev (jev-1.13.0) | Does the skeptic's case for v1 hold? | Recommended ruling | Blocking conditions |
|---|---|---|---|---|
| **E1** journal is authority | journal_authoritative **1.0**, swing 0.0 | **No** | For v5, conditional | 1 (migration crash window) |
| **E2** reads never write | pure_evaluation **0.9925**, swing 0.015 | **No** (it holds on the math only) | For v5, as a consequence of E1 | 1 (one source of λ) |
| **E3** one ordered journal | single_ordered_journal **1.0**, swing 0.0 | **Partially** (on reader latency) | For v5, closure gated | 3 (lock scope ×2, checkpoint) |
| **E4** tombstone, then erase | tombstone_then_erase **0.9275**, swing 0.045 | **Partially** (on footprint) | For v5's *semantics*, not its mechanism | 4 |
| **Half-life** rewrites history | reinterpret_history **0.84**, swing 0.08 | **Partially** | For v5's journal, *against* reinterpretation as implemented | 2 |

**The headline:** every ruling points toward v5, but they do not all close the same way.
- **E1 and E2** close cleanly once their blocking conditions are attached.
- **E3** closes only after the lock-scope fixes land. Otherwise it silently reopens the §15.6 reader-stall envelope.
- **E4** rules a *meaning* (prune = tombstone, erase = real delete). It does not rule `compact()`, which v7 already rejects.
- **The half-life ruling** accepts v5's journal and rejects "a config value read at open silently rewrites history".

---

## The Jev caveat (applies to all five)

**The question state came from v5's own blueprint** (`docs/v5/BLUEPRINT.md` §7), and that blueprint argues for v5. All five came back "settled" under the rotation protocol, which tests stability under option reordering. That is not independence.

**E4 has a specific, verified framing error.** Two option costs in `docs/v7/inputs/round4.jev.json` are wrong, and both errors favour v5:
- `:89`: the tombstone cost says *"journal keeps growing until compacted"*. But `compact()` only scrubs ERASED records (`src/moneta/v5/substrate.py:914-916`), so tombstones never shrink.
- `:94`: the physical-delete cost says *"cannot be explained or recovered"*. But v5 tombstones can't be recovered either (`src/moneta/v5/model.py:300-301`, no restore API).

**For the half-life ruling:** 0.84 is the weakest score and has the largest swing. Read it as **"v5 direction, conditions unresolved"**, not as settled.

**Rest every ruling on the code findings below, not on the scores.**

---

## Shared findings (cited by several rulings)

**F1. v1's durability claim is false (verified).**
`src/moneta/api.py:416-418` says each signal *"is also fsync'd to the WAL so that a kill -9 after the return does not lose the signal"*. But `src/moneta/durability.py:144-149` takes a lock, writes, and calls `flush()` with no fsync. The only fsync in `durability.py` is the snapshot's (`:115`). **Acknowledged attention can be lost on crash today.** E1, E2 and E3 all lean on this.

**F2. The journal grows without bound and has no checkpoint.**
Open replays everything (`src/moneta/v5/journal.py:262`, `substrate.py:312`). `compact()` keeps every event (`substrate.py:910-941`). Measured: 100k events = 29.4 MB and a 0.81 s open (E1 probe), or 11 MB and 0.44 s with 200 records (E3 probe). Both grow linearly. For contrast, v1 truncates its WAL at snapshot (`durability.py:117-125`). E1, E3 and E4 all measure this.

**F3. fsync on every write.**
`journal.py:326-327`: about **1.4 ms per deposit or attend** on Windows NVMe, against 0.012–0.043 ms without fsync. All writes serialize under one RLock (`substrate.py:297-298`), so the ceiling is **about 700 writes/s**. This is the real price of durability, not a bug. Cited by E1 and E3.

**F4. On Windows, `os.replace` fails while another handle has the file open.**
`PermissionError [WinError 5]` whenever a reader, AV scanner, indexer or backup agent holds the file. It hits the snapshot export (`src/moneta/v5/compat.py:99-107`) and compact (`journal.py:375-378`). Cited by E1 and E4.

---

## E1: who decides what exists

**What changes**
- v1: USD first, then the vector index, and **the index is the authority** (`ARCHITECTURE.md:146, :152`; lock 4; `sequential_writer.py:104-105`).
- v5: **the journal is first and is the authority.** The index and USD are both derived from it.

**Jev:** 1.0, settled. Subject to the framing caveat.

**Skeptic's strongest case for v1**
- Two structures and two rules, locked through Rounds 2 and 3, measured in Phases 2 and 3.
- The crash story is closed-form: a USD orphan is never traversed, so healing is implicit.
- v5 adds a third persistent structure plus a pile of recovery code (torn-tail truncation, CRC refusal, `repair()`, quarantine, sha sidecars, reconciliation, a failed-migration rename). Each piece can fail at the worst moment.
- v5 puts fsync on the attention path and ties open time to history.
- SYNAPSE pins v1's failure semantics in 6 tests.

**Did it hold? No.** v1's authority for existence is an in-memory structure that cannot survive process death, and its WAL doesn't fsync (F1). Every v5 risk the skeptic found is an implementation risk, not a design risk.

**Risks found in v5 code**
- **A hard kill mid-migration leaves a store that won't open, and the error message's suggested fix loses data (probed).**
  - Whether to migrate is decided only by whether the journal exists (`compat.py:416`).
  - The completion note and sidecar hash are written only at the end (`compat.py:656-659`).
  - The `.failed-migration` rename runs only on an in-process exception (`compat.py:446`), and that is the only path tested (`tests/v5/test_compat.py:191`).
  - After `os._exit` at 1, 20 or 52 of 52 appends, the store reopens with `SnapshotDivergedError` (`compat.py:217-223, :250`).
  - Following the message's first fix ("move the snapshot aside") on the 20-append case opened 19 of 50 records. `close()` then exported those 19 over `snapshot.json`.
  - Recoverable only from `snapshot.json.v1-original` (`compat.py:560-562`), and only by someone who knows to look there.
- **A damaged final line refuses the whole store (probed).** A torn tail without a newline is truncated (`journal.py:119-121`). A CRC-failing final line *with* its newline raises `JournalCorruptError` at open (`journal.py:124-127`), even though that record was never fsync-acknowledged.
- **Unbounded replay (F2).** `events()` re-reads the whole file (`journal.py:292-301`), and `_journal_known_shas` runs it on facade opens (`compat.py:181-191, :214`).
- **Write ceiling (F3).** SYNAPSE gets `fsync=True` by default (`compat.py:401`).
- **On Windows, `run_sleep_pass` raises after the pass has already committed (probed).** When the export fails (F4), the facade raises (`compat.py:531-535`) even though the retain and consolidate events are already journaled. `close()` swallows the same failure (`compat.py:499-510`). v1 has the same `os.replace` (`durability.py:109-116`), so this is not a regression. What changes is that a failure in a derived file gets reported as a failure of the operation.
- **A crash between USD projection and the consolidate event re-projects the same records.** Projection runs at `substrate.py:708` and is journaled at `:719-727`, and records stay STAGED (`:694`). Prims go to `/Memory_{hex}` (`src/moneta/usd_target.py:163-165`) in a sublayer chosen by UTC date (`usd_target.py:271-280`). A retry on a later day creates a **duplicate prim** in a second sublayer and inflates `_prim_counts`, which drives rotation. **This is §9 Trigger 3 territory.**
- **Lock edge cases.** The lock is `msvcrt.locking` on byte 0 of `<journal>.lock` (`journal.py:143-150`). Two `storage_uri` values sharing one snapshot now raise `JournalLockedError`, which is a new exception type for SYNAPSE (`compat.py:405-409`). SMB is untested.
- **Calibration, in v5's favour:** per-add export is *cheaper* on v5. At 841 records: dim 64 is 46.7 ms → 30.4 ms, and dim 768 is 422.8 ms → 231.2 ms.

**Conditions**

*Blocking (before cutover step 2):*
1. **Make migration crash-safe.** Journal `migration_begin` (snapshot sha256 and expected row count) right after genesis. On open, treat "begin without completion" as half-migrated: either re-migrate from `.v1-original` or rename to `.failed-migration`. Don't offer "move the snapshot aside" first in that state. Add an `os._exit` hard-kill test next to `test_compat.py:191`.

*Before 5.0.0:*
2. **Add a checkpoint or fold-snapshot event** so open replays only the tail. Stop the full scan in `_journal_known_shas`. Set a stated open budget.
3. **Make re-projection idempotent across sublayer days.** Either route a retried id back to its original layer or journal a project-intent event first. Brief it as Trigger 3 if it touches §15.2.

*Polish:*
4. Treat a CRC-failing *final* line as a torn tail: quarantine it and log it. Keep the hard error for damage mid-file.
5. Decide the attention durability tier: per-op fsync, or group commit. Record about 1.4 ms per op in `BEHAVIOR_CHANGES`.
6. In the facade's `run_sleep_pass`, log a derived-export failure the way `close()` does instead of raising.
7. Record F1 in the ruling text as a factual ground.

**Recommended ruling:** **For v5, with condition 1 blocking cutover step 2.**
Owner decision: ☐ for ☐ against ☐ hold

---

## E2: decay is a pure read

**What changes**
- v1: decay is written back at three evaluation points, and `query` mutates (`ARCHITECTURE.md:84-90`; lock 2; `api.py:401`; `ecs.py:251-272`).
- v5: **zero mutation points.** Utility is a pure function of (anchor, λ, t). The formula is kept verbatim.

**Jev:** 0.9925, settled. Subject to the framing caveat.

**Skeptic's strongest case for v1**
- The decay is memoryless, so mutating at three points and evaluating purely give **the same numbers**. Measured drift: 3.7e-13 over 10k mutations.
- The real defect is P4: attention reduce stamps `LastEvaluated=now`, which erases owed decay (`ecs.py:212-247`). It can be fixed inside v1 by running `decay_all` before `apply_attention`.
- v1 keeps a native batched decay kernel on the read path (`ecs.py:258-262`) and a public runtime λ (`api.py:210`, `decay.py:91`).

**Did it hold? No. It holds on the math, not on the decision.** Once the journal is the authority and live state must equal replay (`substrate.py:425-437`; `tests/v5/test_conformance.py:274` `test_i6_reads_never_write`), a read cannot write. The only alternatives are journaling every query (an fsync on reads) or letting live state drift from replay. **E2 follows from E1 and is not a separate choice.** On clock faults v5 is also safer: a forward spike under v1 over-decays every row, while under v5 it touches only the ids attended during the spike.

**Risks found in v5 code**
- **λ has two copies.** Fold copies it at construction (`substrate.py:311`) and `_op_attend` uses that copy (`model.py:286`), while reads use `Substrate.lam` (`substrate.py:388-389`). Probe: a live `set_half_life(60)` left live state at 4.3e-19 against replay at 7.5e-37. Today this needs private access to trigger. It becomes a real bug the moment a runtime setter exists.
- **Runtime decay tuning is gone.** `compat.Moneta` has no `.decay`, and `_EcsView` (`compat.py:324-355`) has no `decay_all` (v1 caller: `tests/integration/test_end_to_end_flow.py:407`). Callers get a hard `AttributeError`.
- **A forward clock spike freezes decay.** `anchor_t = max(t, anchor_t)` (`model.py:289`) and negative dt is clamped to 0 (`decay.py:66-68`). Probe: an attend at T0+30d froze utility for reads at T0, T0+1d and T0+7d. Realistic triggers: w32time, sleep/resume, VM clock jumps (`substrate.py:103-105`). `_t()` (`substrate.py:422-423`) doesn't bound or flag event times.
- **Time-travel reads mislead.** `recall`/`explain` accept any finite `t` (`substrate.py:573-583`). Probe: 0.75 returned where the true historical value was 0.5. The facade doesn't forward `t` (`compat.py:514`), so SYNAPSE can't reach this.
- **No native decay on v5's read path.** `decay_value` runs once per record in Python (`substrate.py:603`; `model.py:144-145`). At 50k×64, recall takes about 111 ms against v1's 4.7 ms. **Only about 10 ms of that gap is E2**; the rest is classification.
- **SYNAPSE semantic change.** `Memory.last_evaluated` now means evaluation time (`model.py:147-157`). Crucible/fc4 helpers that fake time by writing to it break (`docs/v5/SYNAPSE_COMPAT.md:37`).
- **Migration freezes P4 damage in place.** v1's `(utility, last_evaluated)` is imported as the anchor unchanged (`compat.py:598-619`). Expected and unavoidable. State it so nobody expects corrected utilities.

**Conditions**

*Blocking:*
1. **One source of λ.** Fold and Substrate read the same value (`substrate.py:311` vs `:388-389`). Add a test that a λ change journals a note and that live equals replay afterwards.

*Before 5.0.0:*
2. **Decide runtime λ tuning:** either a journaled `set_half_life` plus a `.decay` shim on the facade, or a documented "reopen-only" break. Never an unexplained `AttributeError`.
3. **Timestamp skew guard.** Warn and note, or reject, when an event's `t` is far beyond the journal's high-water `t`. Test a spike followed by a return to normal time.
4. **Port the bit-exact native `decay_batch` seam** to v5's recall, sleep pass and records, with a parity test.

*Polish:*
5. Rule E2 together with E1, and amend `ARCHITECTURE.md` §4: the formula stays verbatim, and "three evaluation points" becomes "zero mutation points; state changes only via journaled events".
6. Document read-side `t` as evaluation time, not an as-of query, or reject `t` below the anchor.
7. Publish the `last_evaluated` change in `SYNAPSE_COMPAT.md`. Ask SYNAPSE to pass a clock.
8. Keep two existing safeguards as invariants: retain events journal concrete id lists (`substrate.py:681-689`), and `test_i6_reads_never_write` stays mandatory.

**Recommended ruling:** **For v5, explicitly as a consequence of E1.** If E1 is ruled against, keep lock 2 and fix P4 with a reorder in v1's reducer.
Owner decision: ☐ for ☐ against ☐ hold

---

## E3: one ordered journal

**What changes**
- v1: a lock-free, GIL-dependent attention log, reduced at the sleep pass (`ARCHITECTURE.md:108-112`; lock 3; `attention_log.py:64-68`).
- v5: **every write goes into one journal under one writer lock, with a gap-free seq.** Attention is visible immediately. The GIL sentinel is removed.

**Jev:** 1.0, settled. Subject to the framing caveat.

**Skeptic's strongest case for v1**
- Attention costs about 0.23 µs: one `list.append` with no lock (`attention_log.py:73`).
- `query` takes no lock at all (`api.py:379-410`), so **readers never wait**.
- §15.6 narrowed the writer lock to the `Sdf.ChangeBlock` alone so that `layer.Save()` runs alongside readers (`ARCHITECTURE.md:312`). That was a hard-won envelope ruling.
- Deferred attention gives stable rankings within a session.
- The GIL limit fails loudly. v5 deletes the guard and a test forbids bringing it back (`tests/v5/test_conformance.py:363-366`), yet v5 has never run free-threaded (`docs/v5/BLUEPRINT.md:192` marks this `[U]`).

**Did it hold? Partially.**
- **Correctness: no.** v1's durable attention is lock-taking and flush-only (F1), so it loses acknowledged signals on crash, and it can't run without the GIL. Its single-reducer rule is a convention the code doesn't enforce (`attention_log.py:30-36`). v5 gives a total order and live == replay, and tests check it (`tests/v5/test_review_regressions.py:207-236`, `test_conformance.py:336-360`). All 131 v5 tests pass on Windows with `PYTHONPATH=src`.
- **Reader latency: yes.** v5 as written gives up "readers never wait".

**Risks found in v5 code**
- **The sleep pass holds the global RLock through USD Save.** `substrate.py:668, :708` calls `projector.project()`, which in the compat path is `author_stage_batch` plus `flush` = `layer.Save()` (`compat.py:312-316`). `src/moneta/v5/usd/projection.py:31-57` does the same. Probe: recall's worst latency during the pass was **232 ms**. **This walks back §15.6 (`ARCHITECTURE.md:312`).**
- **The compat export holds the lock while serializing everything.** `compat.py:141` runs after every sleep pass (`:531-534`), which is the SYNAPSE path. Probe at 10k × 768: **2,892 ms** of lock hold, so every SYNAPSE reader stalls about 3 s per pass.
- **Attention cost (F3).** Each call is one fsync'd append under both locks (`journal.py:315-343`; `substrate.py:425-427, :643`). Measured 1,383 µs against v1's 0.23 µs, about 6,000×. Recall p99 went from 0.30 ms to 2.5 ms with one concurrent attention writer.
- **No checkpoint (F2).** v1 drains its log (`attention_log.py:82`) and truncates its WAL.
- **Free-threaded safety is asserted, not tested.** The only check is `_lock._is_owned()` under the GIL (`test_review_regressions.py:215`). Lock-free readers remain (`Substrate.seq`, `substrate.py:392-393`; `closed`). The Rust seam has never run without the GIL. There is no 3.14t interpreter on this machine.
- **The Windows paths are not covered by tests.** `# pragma: no cover` at `journal.py:144, :161, :176, :375-381`. Directory fsync is a no-op on NT. The SYNAPSE evidence is Linux-only (`SYNAPSE_COMPAT.md:13`).
- **A stale install breaks v5 tests.** `C:/Python314/Lib/site-packages/moneta` is a non-editable install without v5. Without `PYTHONPATH`, two cross-process tests fail with `ModuleNotFoundError: moneta.v5`.
- **Behaviour change: attention is visible immediately** (`substrate.py:643`). No test pins this either way.
- **Minor: re-entrancy.** The lock is an RLock, and the projector is called while it is held. A projector that calls back into the substrate could mutate the fold mid-iteration. No current projector does this.

**Conditions**

*Blocking (E3 doesn't close without these):*
1. **Project outside the lock.** Take the batch under the lock, project with no lock held, then append `consolidate` under the lock. **Acceptance:** recall p95 stall ≤ 30 ms during a sleep pass, with the real `UsdTarget` under hython at 500-prim batches, *measured*.
2. **Export outside the lock.** Copy rows under the lock, then serialize, write and fsync outside it. **Acceptance:** SYNAPSE-path stall ≤ 30 ms per pass at 10k × 768.
3. **Journal checkpoint or attend coalescing,** with a tested reopen budget (for example, under 1 s at 1M events).

*Before 5.0.0:*
4. Benchmark Windows fsync p50/p99 for deposit and attend. Either add group commit or write the ~700 writes/s ceiling into the envelope.
5. Keep free-threaded support marked `[U]` until tests/v5, including the M5 lock test and the native parity tests, pass on 3.13t or 3.14t. Until then, log a warning under `sys._is_gil_enabled() == False`.
6. Amend §5.1 explicitly: attention is visible immediately, and "lock-free" becomes "one writer lock, total order". Add a test that pins the visibility.
7. Re-run the SYNAPSE swap on Windows under plain CPython *and* hython against a copy of the 841 store. Remove the stale site-packages install.

*Regardless of the ruling:*
8. Fix v1's docstring at `api.py:416-418` (F1).

**Recommended ruling:** **For v5, with closure conditional on blocking items 1–3, each with a measured Windows/hython number.** Ruling for v5 without them silently reopens §15.6, which would be its own §9 trigger.
Owner decision: ☐ for ☐ against ☐ hold

---

## E4: prune means tombstone

**What changes**
- v1: prune physically removes the record from the ECS and the index (`consolidation.py:166-169`; thresholds locked in Round 2, `:53-55`).
- v5: **prune tombstones** the record, so it is never recalled but stays explainable. `erase` + `compact` is the only physical delete.

**Jev:** 0.9275, settled. **The option text is wrong in v5's favour** (see the caveat). Re-run it before this score counts as evidence.

**Skeptic's strongest case for v1**
- Prune is v1's **only** mechanism that keeps memory bounded, and the §15 envelope (rotation at 50k, batch caps) assumes the hot tier tracks the live set.
- In v5, no operation ever removes a record from the fold. Measured with 2k live records: recall goes from **2.4 ms to 48.9 ms** with 100k tombstones, and the sleep pass from 1 ms to 27 ms. RAM after pruning 20k: 321.9 MB → 320.7 MB, effectively unchanged.
- "Recoverable" is false: there is no un-tombstone, and revector drops tombstoned vectors.

**Did it hold? Partially.**
- **On footprint and read cost: yes.**
- **On forgetting and audit: no.** v1 has no targeted delete, and v1's prune doesn't reach USD, the snapshot or the WAL either. It is not a stronger privacy story.

**Risks found in v5 code**
- **The fold is unbounded.** `_op_erase` (`model.py:319-329`) and `_set_status` (`:293-305`) never delete. `_classify` (`substrate.py:455-459`) and `run_sleep_pass` (`:674`) walk every record ever deposited. After erase + compact, the record still counts (`{'erased': 1}`).
- **Tombstoned payloads stay resident and on disk.** The 85.7 MB journal still contains the content. `compact()` scrubs ERASED records only (`substrate.py:914-916`). The blueprint admits "The journal grows forever" (`docs/v5/BLUEPRINT.md:271`).
- **Tombstones are irreversible.** `model.py:300-301` allows only TOMBSTONED → ERASED, and revector drops tombstoned vectors (`model.py:331-342`). Yet `docs/v7/BLUEPRINT_v7.md:413` says "recoverably under E4's tombstone" (verified), which the code does not support.
- **Erase doesn't reach projections.** The Projector protocol has no retract hook (`substrate.py:127-136`). `TargetProjector` (`compat.py:312-317`) writes the payload as a prim attribute (`usd_target.py:320`), and nothing scrubs `cortex_*.usda`.
- **Other copies survive erase + compact:** the last `snapshot.json` export (`compat.py:133-178`), SYNAPSE's host-held copy, `.failed-migration` (`compat.py:446`), `.quarantine-N` (`journal.py:441-445`), and the v1 source snapshot and WAL (`compat.py:549+`). "A real forget this for privacy" (`BLUEPRINT.md:194`) overstates what the code does.
- **Quadratic id dedup under the lock.** `substrate.py:949` checks membership against a list. Measured: 40k ids takes **5.58 s**, stalling everything (`:879-881`, `:900-902`).
- **Compact on Windows (F4).** It fails whenever any other handle is open (`journal.py:375-378`). Recovery is clean (`:380-382`) but there is no retry, and `erase()` has already reported success.
- **Weaker crash durability on Windows.** `_fsync_dir` is a no-op on NT (`journal.py:175-177`), yet the docstring at `:353` promises a directory fsync. A power loss right after the replace could bring back the pre-compact file, erased payload included. Plausible, not reproduced.
- **The window between erase and compact is unbounded by design** (`substrate.py:894-896, :905`). Nothing schedules compact.
- **Compact is O(whole journal), runs under the lock, and peaks at about 6× the file size in RAM** (`journal.py:358-364`; `substrate.py:940`). Measured on 86 MB: 2.9 s stop-the-world, 510 MB peak.
- **A stale `.compact.tmp` is never cleaned up** (`journal.py:235-284`).
- **SYNAPSE semantics change.** `compat.py:74`: *"pruned payloads stay readable via .v5.explain()"* (verified). Rollback exports only RECALLABLE records (`compat.py:146-147`), so tombstone history is lost on rollback.

**Conditions**

*Blocking (before E4 closes):*
1. **Bound the read path.** Add a horizon GC that leaves only an explain stub (id, status, reason, seq), or split the fold into live and dead maps. **Gate:** recall p95 with 100k dead records within 10% of zero dead. Today it is 20×.
2. **`erase()` names or invalidates every derived copy:** USD prims, the last export, `.failed-migration`, `.quarantine-N`, and the v1 sources. Projector gains a retract hook. This pulls v7's G3-9 / V-ERASE forward.
3. **Rule the semantics only:** "prune = tombstone; operator erase removes content from every store". **Do not ratify `compact()`.** v7 already replaces it with per-record payload files and re-genesis (`BLUEPRINT_v7.md:135, :240, :563`).
4. **Fix the O(n²) dedup** at `substrate.py:949` with a set or `dict.fromkeys`.

*Before any long-lived deployment:*
5. Drop `vector`/`unit` after tombstoning, and lazy-load the payload for `explain`.
6. Either add an un-tombstone operator, or strike "recoverable" from the v5 blueprint, `BLUEPRINT_v7.md:413` and the Jev option text.
7. Harden compact on Windows: retry with backoff, report "erase pending compaction", fix the `:353` docstring or use `MOVEFILE_WRITE_THROUGH`, and delete a stale `.compact.tmp` at open.
8. Make compact streaming, or label it a maintenance-window operation.
9. **Re-run the Jev E4 question with corrected option costs** before the 0.93 counts as evidence.
10. Update `SYNAPSE_COMPAT.md`: pruned payloads are retained, and the exported `snapshot.json` is a copy erase cannot reach. Move SYNAPSE's tests from private-field edits to a clock.

**Recommended ruling:** **For v5's semantics (prune = tombstone, plus a real operator erase), with blocking conditions 1–4.** Do not lock in the mechanism.
Owner decision: ☐ for ☐ against ☐ hold

---

## Half-life call: does a changed λ rewrite history?

**What changes**
- v1: λ is runtime-configurable within 1 min – 24 h, and the spec says nothing about history (`ARCHITECTURE.md:82`; `decay.py:91-105`).
- v5: **opening with a different half-life reinterprets all history on replay**, logs a warning and appends a note (`substrate.py:328-346`).

**Jev:** 0.84, swing 0.08. The weakest of the five: **direction only.**

**Skeptic's strongest case for forward-only**
- Under forward-only, a mistake (wrong units, a test fixture value, a library default bump) does damage in proportion to how long it stays live, not to the store's age.
- Under v5, one config value becomes a **hidden retroactive input to an irreversible operation**.
- Inconsistent ownership: the journal owns the dimension (`compat.py:422-423`) but config silently overrides λ.
- "Reinterpretation is needed for determinism" is false. A journaled rebase event is just as deterministic.

**Did it hold? Partially.** v5 is deterministic and can be undone right up until a sleep pass. **After one pass, it can't be undone.**

**Probe** (24h → 1h, which is inside the allowed range at `decay.py:34-35`; 30 deposits over 45 h; one pass):
- **30 of 30 tombstoned.**
- Forward-only at the same instant would have pruned **0 of 30**.
- Reverting to 24h leaves **0 recallable**.

**This is not really v1 versus v5.** Both semantics can be expressed on v5's journal.

**Risks found in v5 code**
- `substrate.py:328-346`: any open with a different `half_life_seconds` rewrites history behind a log warning. **Opening is itself a write.**
- `substrate.py:170` + `decay.py:31`: Config falls back to the library default. An inspection script or REPL that omits λ reinterprets the store, and a future default change rewrites every store on upgrade.
- `model.py:293-302` + `substrate.py:674-680`: the first pass prunes on the rewritten utilities, and tombstones are one-way.
- `model.py:189-194, 220-221, 280-290, 344-348`; `substrate.py:311`: the fold's λ comes from config, never from the journal. **Replaying the journal under a different config gives a different state.**
- `model.py:307-317`: the rewrite is partial. Retain, stage and consolidate decisions stay frozen while utilities are recomputed, so `explain()` can show a record "tombstoned for decay" whose current utility is well above 0.1.
- `compat.py:600-619`: imported v1 anchors already contain decay under v1's λ.
- `usd_target.py:321`: USD-authored utility values diverge from the journal after a change, and nothing flags it.
- `substrate.py:338-346`: the note's `t` is unchecked. Alternating configs append a note on every open.
- `tests/v5/test_review_regressions.py:147-160`: the only test checks that the note exists. **Nothing tests change → pass → revert.**
- **SYNAPSE today:** `moneta_store.py:318-337` never sets λ, so it runs at the 6h default with **no current exposure**. The APPROVE gate (`:844-1010`) wouldn't show a half-life change as the cause of a prune list.

**Conditions**

*Blocking:*
1. **The journal owns λ, as it owns dim.** `fold.lam` comes from genesis and change events, never from Config. A mismatched open **raises** unless the caller explicitly passes `half_life_change='reinterpret'` (or a forward mode). Read-only opens never append.
2. **Gate the first pass after a change.** Run it as a dry run that returns the would-prune set, or require confirmation above a stated LIVE fraction. SYNAPSE's audit names the half-life change as the cause.

*Before 5.0.0:*
3. A change is an explicit, owner-authorised journaled operation (v7 G2-10 "owner-signed amend", `BLUEPRINT_v7.md:283`). Its implementation must **replace** `substrate.py:328-346`, not sit on top of it.
4. Every retain event records the λ it was decided under, so `explain()` can say "tombstoned under λ_old".
5. Either a journaled restore for decay tombstones until erase, or a plain statement that change + one pass is irreversible.
6. Regression tests: the 30/30 probe; a default-config open on a non-default store refuses; replay is identical without the original Config.
7. Keep a **forward-only rebase** mode available per change. It costs one O(N) pass.
8. Document how far the rewrite reaches (frozen decisions, imported anchors, USD values). Release notes state that a default change never rewrites existing stores.

**Recommended ruling:** **For v5's journal-and-fold design. Against "reinterpret history" as implemented.** Make the semantics a journaled, owner-authorised, per-change choice (reinterpret or forward) behind conditions 1–2.
Owner decision: ☐ for ☐ against ☐ hold

**Note for v7:** the v7 table (`BLUEPRINT_v7.md:781`) says "ruled for → R2 stays `recall_half_life` `[A]`" and "ruled against → R2 flips to `utility_exponent`". Under this recommendation R2 **does not flip**, because v5's journal is kept, but R2 remains `[A]` until mile 2's report (O4, `:835`).

---

## What ruling all five toward v5 unlocks

### Cutover: `docs/v5/BLUEPRINT.md` §9, step by step

| Step | What it is | Status, and what gates it |
|---|---|---|
| **1** | Merge v5 as-is; v1 stays the default | **Done.** Commit `861bed9` on this branch. This also makes **O35 stale** (`BLUEPRINT_v7.md:866` still says "NOT FOUND… searched 2026-10-15"). Close it. |
| **2** | Point SYNAPSE at the facade behind a flag (one line in `moneta_runtime`); test on a **copy** of the 841-record store | **Gated by E1 condition 1**, the migration crash window (`compat.py:416, :446, :656-659`). This is the one path where following v5's own error message loses data. |
| **3** | Update SYNAPSE's 6 tests; drop the per-`add()` snapshot | Gated by E3 condition 6 (pin visibility semantics), E4's `prune_audit` change (`compat.py:74`) and E2's `last_evaluated` change (`SYNAPSE_COMPAT.md:37`). |
| **4** | Move hython and server Python together | Remove the stale `C:/Python314/Lib/site-packages/moneta`. The Windows lock path and hython-under-v5 are unmeasured (next section). |
| **5** | Flip `moneta.Moneta` to the facade and tag **5.0.0**. Rollback = v1 reads the v1-format export | **Gated by E3's three blocking items.** Without them, §15.6 (`ARCHITECTURE.md:312`) is silently reopened. Also needs E1's checkpoint, E4 conditions 1–4 and half-life conditions 1–2. Keep the v1 export as the rollback path for an agreed production period. |

### Paperwork Mile 0 requires ("Done means", `BLUEPRINT_v7.md:784-791`)
1. All rulings, *with their conditions*, recorded in `docs/rounds/round-4.md`.
2. `ARCHITECTURE.md` (§4, §5.1, §7, §6 prune semantics, :82) and `CLAUDE.md` locks 2, 3 and 4 amended in **one PR**.
3. The facade is run against a copy of the 841 store and the migration report shows **841 of 841**. SYNAPSE compatibility is re-measured on this machine, including the wrapper restore path (O19). Arm P's p95 is recorded on v5's facade.

### v7 `[A]` rows that become *ruled* (not *measured*)

**Flip on the Mile 0 ruling alone:**
- **O1** (`BLUEPRINT_v7.md:832`): Mile 0 itself.
- **Locked-decision rows** `:758` (attention log → journal, E3) and `:759` (vector-index authority superseded, E1).
- **Q4** (`:729`, reads never write, E2) and **Q10** (`:735`, no GIL dependence, E3). Q10's *free-threaded* half stays `[U]` until a 3.13t/3.14t run (E3 condition 5).
- **G3's dependency on E1** (`:359`): G3 holds as drawn and is not redrawn with a second authority.
- **O7 / O29 / O30** (`:838`, `:860`, `:861`) via E3: per-event retention fold, R4a gets its carrier, and the call-time stamp has its single writer. O29 still needs an explicit line in the ruling stating that the per-event fold *is* evaluation point 2.
- **`RULINGS.md:46`**: "Still unruled: mile 0" can be closed.
- **The Kill list** (`:793-799`) is cleared for E1, E2, E3 and E4. For the half-life call, R2 does not flip.

**Do NOT flip on the ruling:**
- **R2 / R3** (`RULINGS.md:12, :15`; O4 `:835`): these wait on mile 2's report.
- **T1 / P1** (`:509`, `:516`): these rest on v5 records actually landing in format 7 and on O16's context binding. They are implementation facts, not rulings.
- **O24** (`:855`, slot semantics): owner, at mile 0, from v5 code. This is a separate decision.
- **SYNAPSE compatibility** (`:791`): moves `[A]` → `[M]` only by **measurement** on this machine.

**Ruled is not the same as measured.** The ruling makes the design assumption legitimate. It does not make any v5 number true on Windows or hython.

---

## Still unmeasured

- **The 841-record store from the 17 Sep incident.** No real SYNAPSE store has been migrated (`SYNAPSE_COMPAT.md`, "What this does not show"). Needed: the migration report showing 841/841, per-add export at that size on *this* machine, the wrapper restore path, and arm P's p95 on the facade.
- **The Windows lock path.**
  - `msvcrt` byte-range lock behaviour on SMB/network shares is untested (`journal.py:143-150`).
  - The Windows branches are `# pragma: no cover` (`journal.py:144, :161, :176, :375-381`).
  - No directory fsync on NT (`journal.py:175-177`). The power-loss resurrection of an erased payload is plausible and not reproduced.
  - `os.replace` fails against Defender, the indexer or a SYNAPSE reader (F4), with no retry.
  - The SYNAPSE compat evidence is **Linux-only** (`SYNAPSE_COMPAT.md:13`).
- **hython under v5.** E3's acceptance numbers (≤ 30 ms recall stall with the real `UsdTarget` at 500-prim batches; ≤ 30 ms export stall at 10k × 768) don't exist yet. Today's figures (232 ms, 2.9 s) came from a stand-in projector and plain CPython.
- **Free-threaded CPython.** There is no 3.13t/3.14t on this machine, and the Rust seam has never run without the GIL.
- **Long-horizon journal behaviour.** Open time on a year of SYNAPSE history, and the reopen budget at 1M events. Only linear extrapolation from 100k exists.
- **Jev with corrected inputs.** E4 needs a re-run with fixed option costs. All five would benefit from question state that wasn't drawn from v5's own blueprint.

**Probe scripts** (all read-only, no repo files edited):
`C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Moneta\eb45e56e-ffee-4251-86c6-41782cf26935\scratchpad\e1\`, `...\scratchpad\e2\`, `...\scratchpad\e3\`, `...\scratchpad\e4\`, `...\scratchpad\hl\probe.py`