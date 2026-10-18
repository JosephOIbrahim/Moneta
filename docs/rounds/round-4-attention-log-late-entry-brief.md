# Round 4 brief: attention-log late-entry loss ("path L")

- **Who rules:** Joseph Ibrahim (owner). This brief recommends; it decides nothing.
- **Status:** DRAFT, never sent. It was written for owner review before going to Gemini Deep Think (MONETA.md §9 escalation protocol). Superseded on 2026-10-18 by the gate 2 ruling (see Freeze); kept as the record of the question.
- **Date:** 2026-10-16. Branch `harden/native-observability` in an isolated clone.
- **How this relates to other rounds:**
  - This is separate from the v7 "Round 4: Mile 0 rulings" (`docs/v7/ROUND4_BRIEF.md`). That round ruled on v5's E1–E4. This one covers v1's locked concurrency primitive.
  - The R1′ durability design that this brief refers to is `docs/design/R1-attention-durability.md` (revision 5 when this brief was drafted; revision 6 records the implementation).
- **Owner framing, approved 2026-10-16:** path L is treated as **both an implementation defect and a possible §9 Trigger 2 case**. The two are not mutually exclusive.
- **Freeze (superseded 2026-10-18):** no implementation on the attention-log subsystem until this round closes. That covers `src/moneta/attention_log.py` and the reducer path in `consolidation.py`. B and D stay unresolved, and fsync stays deferred. **Superseded by the gate 2 ruling** (2026-10-18, under the owner's delegation): path L is an implementation defect that the append-log pattern absorbs, not a §9 Trigger 2, so this round did not open and the freeze never took effect. R1′ is implemented (design revision 6), B, D and L are fixed, and every WAL append is fsynced (F1).

---

## 1. What is at stake

- **Locked decision 3, the concurrency primitive** (`ARCHITECTURE.md` §5.1, `MONETA.md` §2.5): "Append-only attention log, reduced at sleep pass. Not per-entity spinlocks. Not CAS loops. The log is lock-free, eventually consistent, and has the simplest failure mode."
- **The locked invariant** (`ARCHITECTURE.md:112`): "No per-entity locking primitive may be introduced. If a failure mode is found that the append-log pattern cannot absorb, it is a §9 Trigger 2 (spec-level surprise), not a local fix."
- **The conformance item** (`ARCHITECTURE.md:340`): "Attention-log reducer is lock-free (no mutex, no CAS)."
- **The trigger** (`MONETA.md:430`, repeated in `ARCHITECTURE.md:250`): "**Trigger 2 (emergency):** Phase 1 or Phase 3 implementation surfaces an architectural assumption that turns out wrong. Specifically: … **the append-only attention log has a failure mode not anticipated in Round 2**; … Python debugging and implementation bugs are not triggers. **Spec-level surprise** is a trigger."

---

## 2. The failure mode

**Code.** These lines are byte-identical in `v1.3.0-rc1`, `f9117b7` and this branch, so the failure predates the hardening work.

```python
def append(self, entity_id: UUID, weight: float, timestamp: float) -> None:
    self._buffer.append(AttentionEntry(entity_id, weight, timestamp))   # attention_log.py:71-73

def drain(self) -> list[AttentionEntry]:
    drained, self._buffer = self._buffer, []                            # attention_log.py:82
    return drained
```

**Mechanism.**
1. Python evaluates `self._buffer.append` first, which captures the current list object.
2. Only then does it build the `AttentionEntry` argument. That is Python-level namedtuple construction, and the GIL can switch threads during it.
3. If the reducer swaps the buffer, drains it and aggregates it in that window, the entry is appended to the old list after the reducer has read it.
4. rc1 never applies that entry. The sleep pass's own `snapshot_ecs` then deletes the WAL (`durability.py:119-125`), so the loss also becomes permanent on disk.

**The documented guarantee is false.** The module docstring (`attention_log.py:11-19`) says "A concurrent `append` either lands in the old list (and is drained this window) or in the new list … Entries cannot be lost." That argument holds for `list.append` alone, but not for the bound-method capture that happens before the entry is built. `docs/rounds/round-2.md` contains no analysis of the swap, the drain or the GIL. So this failure was not anticipated in Round 2.

---

## 3. Evidence

| # | Evidence | Status | Where |
|---|---|---|---|
| E1 | **Deterministic interleaving.** `AttentionEntry` construction is blocked on the appender thread. `drain()` runs, then the appender is released. Result: `n_at_drain=0 drained_after=1 buffer_after=0`. The entry landed in the list `drain()` had already returned, and the live buffer is empty. | **Saved record** | probe `<scratch>/harden/probes/r1_append_race.py` (sha256 `f062fc70bfd609a29ff00a83c991ad6df23e4ff9ff4adfbdbcd28029a7469514`); record `<scratch>/harden/runs/R1review-append-race-probe.txt` (sha256 `de556934c5227bf4c7c04ec7b87f2becf6de864a6e26270d0b5265f49ebe4da0`); HEAD `e7325bb`; Python 3.14.2 |
| E2 | **Statistical, unpatched code, `sys.setswitchinterval(1e-6)`.** 613 of 200 000 appends landed in an already-drained list. That is a lower bound: the probe counts only landings before its next drain. | **Saved record** | same record as E1, part 2 |
| E3 | **Independent check at the default switch interval (5 ms)**, using the real `aggregate()` and a 1 ms pause per pass: **1 of 200 000 lost.** The same script lost 0 at 1 µs. | **Observed in-session on 2026-10-16. Not saved to a run record.** The script is retained, so it can be rerun when new execution is authorized. | `<scratch>/harden/probes/race2.py` (sha256 `339486266821c5ea0862abff9dcf879cdb4e360240f6ea1e768b3554c3b1d08b`) |

`<scratch>` = the author's local scratch directory; the records are not published.

**How to read it:**
- E1 establishes that the window exists.
- E2 and E3 show it is reachable with real threads.
- How often it happens depends on timing and workload, so neither count is a rate estimate for production.

**Not evidence for path L:**
- Defects B and D (`tests/integration/test_attention_snapshot_regression.py`, strict xfail) are a different mechanism: the snapshot deletes WAL lines for attention not yet applied.
- They interact with path L only in the R1′ design (§5, option E).

---

## 4. Who is exposed

**Path L needs one thread appending while another thread drains, on the same `AttentionLog`.**

**SYNAPSE's store API is not exposed.**
- `MonetaBackedStore.search` takes `self._lock` (an RLock) at `SYNAPSE/python/synapse/memory/moneta_store.py:1194` and signals attention at `:1252`.
- `run_sleep_pass` takes the same lock at `:1287` and drains at `:1300`.
- The auto-consolidate path (`:1010`) re-enters the lock from `add`.
- `server/handlers_memory.py:456` goes through `store.run_sleep_pass()`.

**What is exposed:**
- any caller holding a raw `Moneta` handle that calls `signal_attention` and `run_sleep_pass` from different threads (none found in SYNAPSE's `python/` tree; external tools not audited);
- Moneta's own docs, which present `signal_attention` as safe to call concurrently.

**Not path L, but related:**
- **Unlocked reads.** `loop/ports.py:406, :591` read `_handle.ecs` without the store lock. That is a read-consistency question.
- **Two processes sharing one store's files.** Moneta's URI lock is per process. Two processes on the same files hit the P11 lost-writes class instead (`tests/v5/test_v1_defects.py::test_v1_p11_two_uris_on_one_snapshot_lose_writes`).

---

## 5. Options

| | Option | Stays inside §5.1, `:112` and `:340`? | What it guarantees |
|---|---|---|---|
| **A** | **Reducer takes one snapshot and carries stragglers forward.** The reducer copies the swapped list once (`items = tuple(old)`), keeps `(old, len(items))`, and applies `old[len(items):]` at the next pass. No seq, no WAL change. | **Yes.** One swap, one reducer, no lock, no CAS, no per-entity primitive. | A late entry is applied one pass later in-process, so it is no longer silently dropped by the reducer. **It still dies if a snapshot happens and the process restarts before the next pass**, because rc1 deletes the WAL at snapshot (the B class). |
| **B** | **`append` builds the entry before capturing the buffer.** | Yes | Narrows the window only. CPython can still switch between the attribute load and the call. **Not a proof**, and not relied on. |
| **C** | **A mutex around `append` and `drain`.** | **No.** Breaks `:340` and the lock-free contract, so it would need an amendment to the lock. | Closes the window in-process. Rejected unless this round amends §5.1. |
| **D** | **Accept and document.** | Yes | No fix. The docstring is corrected and a known-loss note is added. |
| **E** | **R1′ (full durability design).** Per-entry seq, an applied-seq set in the snapshot, WAL rewrite instead of deletion, and option A's single snapshot plus carry-over (`R1-attention-durability.md` §2.3). | Yes (rev 5 §1.3) | **Every unapplied entry keeps its WAL line.** A late entry is applied at the next pass, or at worst exactly once at the next reopen. Also closes B and D. |

---

## 6. Recommendation (the owner decides)

1. **Classify path L as both an implementation defect and a §9 Trigger 2 case.**
   - It is a defect because the code fails its own stated design.
   - It meets Trigger 2 because the trigger names this subsystem and this failure, and the design rested on a false guarantee.
   - This round should rule on whether the append-log pattern can absorb it (`ARCHITECTURE.md:112`). This brief argues that it can, through option A or E, without any locking primitive.
2. **Ask the round to approve option A, the reducer snapshot plus carry-over, as conformant with §5.1, `:112` and `:340`.**
   - Option A is the smallest change.
   - It is also a prerequisite of option E: R1′ revision 4, which read the drained list twice, made path L worse.
3. **Ask the round to confirm the weakened meaning of "eventually consistent".**
   - In-process, a straggler is applied at the next pass.
   - Under option E, the worst case is the next reopen.
   - The single-reducer rule stays. Concurrent reducers remain unsupported, and detection is diagnostic only.
4. **Sequencing:** A first, as its own small change after the round closes. Then E, after its own design gate. B and D stay strict xfail until E lands.
5. **Correct the documentation:** the `attention_log.py` docstring and `docs/api.md` must stop claiming "Entries cannot be lost".

---

## 7. Constraints carried into any implementation

These are unchanged from the owner's earlier requirements.
- **No lock, CAS or per-entity primitive in the reducer or in `append`.** The GIL guard in `AttentionLog.__init__` stays.
- **No stored-format change** in option A. Option E adds only optional keys, and **those keys do not by themselves make rollback safe** (R1′ §3.5).
- **fsync changes stay deferred** (R1′ §5).
- **R1′ must still answer the following** (R1′ §3.1–§3.5):
  - concurrent append and drain while the WAL is being replaced;
  - sequence allocation, including after a rollback;
  - crash recovery at every step;
  - whether older (rc1) readers could replay attention that was already applied.
- **Exactly-once attention and failure cleanup stay pinned** by the existing tests:
  - `tests/unit/test_native_attention_once.py`;
  - `test_native_handle.py::test_exactly_once_*` and `test_cleanup_*`.

## 8. Verification plan, once approved (not run)

1. **A deterministic unit test in the shape of E1, test AI in R1′ §4.2.** Block entry construction, drain, then release. Assert the straggler is applied at the next pass and never twice.
2. **A statistical stress run at the default switch interval** that records its counts to a run record, so E3's observation is replaced by saved evidence.
3. **The full qualification matrix,** with B and D still strict xfail.
