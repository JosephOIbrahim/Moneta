# R1: attention durability across snapshot and restart

**Status:** Architect ruling + design review, revision 4 (review fixes: the reducer/save consistency protocol is replaced, the WAL line grammar is made normative, and the register and baseline impact is stated; see Appendix A, revision 4). DESIGN ONLY. Nothing here is implemented on `harden/native-observability`.
**Destination in the repo:** `docs/design/R1-attention-durability.md` (the path the B/D xfail reason strings name).
**Author role:** Architect (MONETA.md §6; CLAUDE.md role table: Architect owns spec-conformance review and §9 briefs).
**Date:** 2026-10-16.

**Citation base.** Every `path:line` below is at tag `v1.3.0-rc1` (commit `c33bbd9`), read with `git -C C:/Users/User/Moneta-harden show v1.3.0-rc1:<path>`. `durability.py`, `attention_log.py`, `api.py` and `consolidation.py` are byte-unchanged from the tag to clone HEAD `2252ea8` (`git diff --stat v1.3.0-rc1 HEAD -- src tests` touches only `src/moneta/__init__.py`, `_native.py`, `ecs.py`, `vector_index.py` and the new `tests/unit/test_native_loader.py`). The §0 run records were re-taken at `2252ea8`; the earlier records at `ac9662c` gave the same result.

**Scope of the defect.** B and D concern the v1 handle `moneta.Moneta` (`api.py:177`), which `moneta/__init__.py` exports. The v5 facade `moneta.v5.compat.Moneta` (`v5/compat.py:683`) has its own `_DurabilityView` (`v5/compat.py:648-672`), whose `snapshot_ecs(ecs=None)` ignores its argument and refreshes a derived export of the v5 journal. That view neither writes nor unlinks a v1 WAL, so R1′ does not touch it. Its only contact with a v1 WAL is the one-time migration read (`v5/compat.py:1004-1028`), covered in §3.5. Some citations in `harden_plan.md` are stale at rc1. For example, Round 4 F1 cites `api.py:416-418` as claiming an fsync, but rc1 `api.py:418-421` already says "no fsync". This document cites only lines it re-read.

**Scope fence.** SPEC §0 forbids any WAL, snapshot or fsync change on this branch. C6 adds only the regression tests, with B and D marked `xfail(strict=True)`. R1′ (below) lands in a **separate PR**, after the gate in §6.

---

## 0. Evidence: the defect reproduces on this clone

Run records (revision 3, current HEAD):
- `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-Moneta/eb45e56e-ffee-4251-86c6-41782cf26935/scratchpad/harden/runs/R1design-r3-BD-native0.txt`
- `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-Moneta/eb45e56e-ffee-4251-86c6-41782cf26935/scratchpad/harden/runs/R1design-r3-BD-native1.txt`
- `C:/Users/User/AppData/Local/Temp/claude/C--Users-User-Moneta/eb45e56e-ffee-4251-86c6-41782cf26935/scratchpad/harden/runs/R1design-r3-BD-absent.txt`

Earlier records at `ac9662c` (same result): `…/runs/R1design-BD-native0.txt`, `…/runs/R1design-BD-native1.txt`.

| Row | HEAD | Identity | Result |
|---|---|---|---|
| `MONETA_NATIVE=0`, `$S/wheel` | `2252ea864b179c2e9e8902e1e4783ba149680913` | `.pyd` sha256 `ec6d7f0c35c5b345f983f4aa80cfea086f3aca454e9cd74a58b6208227b02833` | **4 passed (A, A2, C, E), 2 failed (B, D)** |
| `MONETA_NATIVE=1`, `$S/wheel` | `2252ea8…` | same `.pyd` | **4 passed (A, A2, C, E), 2 failed (B, D)** |
| env unset, `$S/shim_absent` | `2252ea8…` | shim `shim_absent` | **4 passed (A, A2, C, E), 2 failed (B, D)** |

- Interpreter: Python 3.14.2. Test file: the `$S/durab` copy, run against `$W/src` with `--rootdir=$W -c $W/pyproject.toml`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`. `git status --porcelain` in the clone was empty afterwards.
- The defect is backend-independent, as expected: neither seam touches the WAL or snapshot.

- **B** fails because `attended_count == 0` after the restart and the utility decayed like the control row.
- **D** fails with `assert 0 == 1` (test file `:139`).

### Root cause (verified)

1. **The snapshot holds only ECS rows.** `durability.py:85-107` writes `snapshot_version`, `snapshot_created_at` and `rows`. It holds nothing of the undrained `AttentionLog._buffer` (`attention_log.py:69`).
2. **Every `snapshot_ecs` deletes the whole WAL** (`durability.py:119-125`). The comment at `:119` says "everything before `now` is captured in the snapshot". That is false for undrained entries.
3. **Hydrate replays only lines with `timestamp > snapshot_created_at`** (`durability.py:217-218`). So even a surviving undrained line would be filtered out, because it is older than the snapshot that should have preserved it. Test E pins this.
4. **Path B.** A bare save drops undrained signals. The save is `m.durability.snapshot_ecs(m.ecs)`, the call shape of SYNAPSE's save. The shape is documented by the comment at `tests/v5/test_compat.py:66`; that test runs it against the v5 facade, whereas the regression test runs it against a v1 handle, where it reaches `durability.py:83`.
5. **Path D.** The sleep pass drains at `consolidation.py:154-156` and saves at `api.py:464-467`. A signal that arrives between the two lands in the new buffer (`attention_log.py:82`) and the WAL (`api.py:427-431`). The save then unlinks its WAL line.

---

## 1. Architect ruling

### 1.1 Verdict: implementation defect, not a MONETA.md §9 Trigger 2

The verdict holds **only for the amended design R1′** (§2). The plan's original R1, with `_apply_lock` inside the reducer, would itself be a Trigger 2 (§1.3).

**Grounds**

1. **The code contradicts its own stated design.** It does not contradict a locked clause.
   - `durability.py:15-18`: "every `signal_attention` append is also written to a write-ahead log … at snapshot time the WAL is truncated since its entries are captured."
   - `durability.py:20-23`: hydrate skips pre-snapshot entries because they are "already captured".
   - `docs/api.md:253-256` repeats the premise. The premise is false for undrained entries, so the defect lives in the implementation of a stated design.
2. **The contract being restored is explicit.**
   - `MONETA.md:292`: "Durability layer must survive a kill -9 with no more than the last 30 seconds of volatile state lost."
   - `docs/api.md:226` says `signal_attention` is "WAL-covered".
   - Path B loses a signal of **any age** that is still undrained when any save happens. That is outside the 30-second window. It is a bug against a stated contract.
3. **Trigger 2 is scoped narrowly.**
   - `ARCHITECTURE.md:250` names "the append-only attention log has a failure mode not anticipated in Round 2". The same line says "Python debugging and implementation bugs are not triggers." `MONETA.md:430` says the same.
   - `ARCHITECTURE.md:112` makes it Trigger 2 only "if a failure mode is found that **the append-log pattern cannot absorb**."
   - The log itself is sound: `append` (`attention_log.py:71-73`) and the swap-and-drain (`:75-83`) lose nothing. The loss is in the persistence layer's truncate-and-filter rule.
   - R1′ absorbs the fix inside the pattern. It adds no lock or CAS to the log or the reducer, keeps the single reducer (`attention_log.py:30-36`), and adds no per-entity primitive (`ARCHITECTURE.md:112`).
4. **No version bump.**
   - `durability.py:29-34` makes a *format bump* a Trigger 2. R1′ keeps `SNAPSHOT_VERSION = 1` and `WAL_VERSION = 1` (`durability.py:57-58`) and adds only optional keys, which rc1 parses (§1.2).
   - **Ruling: additive optional keys are not a format bump.** But additive does **not** mean rollback-safe. §3.5 states the rollback semantics concretely, including the sequences that lose data.

### 1.2 Do the optional keys count as a format change?

**The keys:**
- `seq` on each WAL line;
- `wal_applied_seqs` and `wal_next_seq` in `snapshot.json`.

**How rc1 reads them:**
- rc1 `wal_read` reads only the named keys `entity_id`, `weight` and `timestamp` (`durability.py:168-174`), so it ignores `seq`.
- rc1 `hydrate` reads `snapshot_version`, `snapshot_created_at` and `rows` with `.get` (`durability.py:193, 202-203`), so it ignores the new snapshot keys.
- The v5 migration reads named keys too (`v5/compat.py:1009-1012`), so it ignores `seq`.

**Line bytes.** rc1 writes through a text-mode `"a"` handle (`durability.py:147-148`), so on Windows each line ends in `\r\n` (verified: a text-mode write of `"x\n"` produces `b'x\r\n'`). R1′'s binary writer (§2.2) terminates each line with `os.linesep`, so its bytes match what rc1 writes on the same platform. Both readers accept either terminator: rc1 strips each line (`:158`), and v5 uses `read_text` (`v5/compat.py:1005`).

**Ruling:** no version bump, no Trigger 2.

**Hard constraint, binding on any future change.** Every WAL line must remain a JSON **object** with a parseable string UUID `entity_id`, a numeric `weight` and a numeric `timestamp`.
- rc1 catches only `json.JSONDecodeError` (`durability.py:161-167`). Anything else that goes wrong while parsing a line escapes rc1's hydrate, and then rc1 cannot open the store at all:
  - `KeyError`: a line with no `entity_id`, such as a header or marker line;
  - `TypeError`: a JSON line that is not an object (`[1]`, `"x"`), or a `null` weight or timestamp;
  - `ValueError`: a malformed UUID, or a non-numeric string weight.
- So no WAL header and no marker lines are allowed.

**WAL line grammar and parse classes (normative for R1′; one rule, used by hydrate, step 0 and step 3).**
- **Raw line.** The WAL is read in binary mode. A raw line is a maximal run of bytes ending in `b"\n"` (the `\n` included), plus, at the end of the file, a final **non-empty** run with no `\n`. A trailing empty piece after the last `\n` is **not** a raw line. Raw line `i` is the `i`-th such run, counted from 0.
  - Do not use `bytes.split(b"\n")`, which yields a trailing empty piece for every normally terminated file. Do not use `bytes.splitlines()` or text-mode iteration, which also split on a lone `\r`.
  - A `\r` stays part of the raw bytes. It is removed only by the `strip()` applied when parsing.
- **Classes.** Each raw line is classed by `text = raw.decode("utf-8").strip()`, then `json.loads(text)`, then rc1's field parse (`UUID(d["entity_id"])`, `float(d["weight"])`, `float(d["timestamp"])`, as at `durability.py:168-174`):

  | Class | Condition | Hydrate | Step 0 (prefix lines) | Step 3 |
  |---|---|---|---|---|
  | **blank** | `text == ""` | skip (drop) | drop | drop |
  | **undecodable** | `json.loads` raises `JSONDecodeError` | skip with WARNING (drop), as rc1 (`:161-167`) | drop | drop, counted, WARNING |
  | **invalid** | decodes, but the field parse raises `KeyError`, `TypeError` or `ValueError`; or `raw.decode` raises `UnicodeDecodeError` (a `ValueError`) | **raise the original exception unchanged**, as rc1 does | cannot occur (hydrate would have raised) | drop, counted, **ERROR** |
  | **entry** | parses | judged by §2.5 step 3 | per disposition | kept iff `seq ∉ S` |

- **`seq`.** A line carries a seq only if `"seq"` is present, `type(v) is int` (so `True` is not a seq) and `0 ≤ v < 2**53`. Any other value is treated as **no seq**, never as an error.
- **Why invalid lines raise at hydrate but are dropped at step 3.** Raising at hydrate keeps rc1's behaviour, so register test P6 is unchanged (§6 gate 6). At step 3 the line is unreplayable by every reader: rc1 and R1′ both raise on it. Dropping it therefore loses nothing any reader could apply. It is also what rc1's save does to it, by unlinking the WAL. Copying it forward instead would leave a store that no longer opens after a save, where rc1's would.
- **Torn tails fall in blank, undecodable or entry, never in invalid.** A line starts with `{`. A proper prefix of a JSON object is never a complete JSON value, so a torn line either fails to decode or is the whole object (a tear after `}`, or between `\r` and `\n`). Lines are ASCII (`json.dumps` escapes non-ASCII), so a tear cannot split a UTF-8 sequence. A zero-filled tail (NUL bytes after a power loss) decodes as UTF-8 and is undecodable as JSON. Only non-UTF-8 garbage is invalid, and it raises at hydrate, as rc1's text-mode reader also does.

### 1.3 Does a lock in the reducer conform to ARCHITECTURE.md:106-112 and :340?

**No. Ruling: the plan's `_apply_lock` is rejected.**

- `harden_plan.md` §3.3 puts `AttentionLog._apply_lock` around `apply_attention` inside `reduce_attention_log` (`attention_log.py:127-129`).
- `ARCHITECTURE.md:340`, the conformance checklist: "Attention-log reducer is lock-free (no mutex, no CAS)." A mutex taken by the reducer violates it literally.
- `attention_log.py:59` says of the class: "No locks. No CAS."
- `tests/unit/test_attention_log.py:6-12` defines lock-free as "must not use `threading.Lock` or `threading.RLock` in its write path". `:174-193` checks it structurally.
- That AST test only catches `from threading import Lock`. Writing `import threading; threading.Lock()` would pass it by evasion, not by conformance. The test's own docstring says a break "is a §9 Trigger 2 (spec-level surprise), not a local fix" (`test_attention_log.py:178-179`).
- Amending `:340` to admit a reducer mutex would be a Trigger 2. R1′ avoids it.

**Alternative considered and rejected: a guard hoisted into `durability.py` and `api.run_sleep_pass` around the whole `run_pass`.**
- It keeps the module text lock-free, but the reducer still *executes* under a mutex. That conforms to the letter only.
- It also makes a SYNAPSE save block for the whole pass, including USD staging (`consolidation.py:174-186`).

**Adopted: an in-flight set plus an apply epoch on the log, with a bounded optimistic reader.** (Revision 4 replaces the revision 2-3 parity counter `_apply_gen`, which could accept a torn read when two reducers overlapped; Appendix A, revision 4, issue 1.)
- Each reducer registers a unique token in `log._inflight` (a `set`) and stores a fresh `object()` in `log._apply_epoch` when it starts. When it ends, it stores another fresh `object()` and removes its token (§2.3). It never blocks or waits.
- The save, in `durability.py` where a mutex already exists (`durability.py:75`), accepts its read only if `_inflight` was empty before and after the row build, and `_apply_epoch` is still the object it read first. Otherwise it retries, for at most `SEQLOCK_READ_TIMEOUT_S` (§2.4 step 1).
- **Why this is exact even with concurrent reducers.** Every reducer's start writes a value no other reducer can write (a new object), and every live reducer is visible in the set. A reducer whose apply overlaps the save's read window was either in the set at the first check, is still in it at the second, or started and ended inside the window, which changed the epoch. The save holds a reference to the epoch object it read, so that object cannot be freed and its identity cannot be recycled. The parity counter had neither property: two reducers both wrote `g+1`, then `g+2`, so the second one to finish hid the first.
- That is no mutex and no CAS in the reducer. `set.add`, `set.discard` and attribute stores are each a single atomic operation under the GIL; none is a compare-and-swap. `ARCHITECTURE.md:340` holds.
- **What it does not rely on.** The single-reducer rule (`attention_log.py:30-36`) is a docstring, and nothing enforces it. R1′ does not assume it for the consistency of a keyed snapshot:
  - consistency comes from the save-side check above, which covers any number of reducers;
  - the reducer still detects a concurrent reducer on a best-effort basis and raises (§2.3), but that detection is diagnostic and nothing depends on it;
  - the save's spin is bounded, and on timeout it degrades to a keyless snapshot instead of hanging.
- Concurrent reducers stay unsupported, exactly as in rc1: their in-memory row updates can still interleave (`ecs.py:235-245`). What R1′ guarantees is that no **keyed** snapshot is ever written from a torn read.
- The GIL is still required: it makes each set operation and attribute store atomic. It is enforced at `attention_log.py:63-68`.

### 1.4 The behaviour change in `signal_attention` (plan risk 5)

R1′ writes the WAL line **before** the buffer append, reversing `api.py:427` and `:429-431`.

| | Behaviour when `wal_append` raises |
|---|---|
| **rc1** | The signal is buffered, then the `OSError` escapes. It is applied in memory but not durable, so a caller that retries is double-counted in memory. **Also:** if `flush()` raised, the line stays in the text handle's buffer, and a later append, or `close()` (`durability.py:263-266`), can still write it out. A reopen can then replay a signal the caller was told failed. |
| **R1′** | The signal is in neither place, and the same `OSError` escapes. This is guaranteed by construction, as follows. The append is one unbuffered `os.write` of the whole line. On any exception or short write, the file is truncated back to its size before the write, and the descriptor is closed (§2.2). No user-space buffer exists to flush the line later. **Residual:** if the truncation itself fails, the seq is tombstoned (§2.2). The next successful save then lists it as applied, so no reader of that snapshot replays it. A crash *before* that save can still replay it once. |
| **R1′, async exception after `wal_append` returned** (for example a `KeyboardInterrupt` between the WAL write and the buffer append) | The line is durable but not buffered, so without a remedy the caller would see an exception, nothing would apply in process, and the signal would apply at the next reopen: a phantom apply. R1′ wraps the buffer append in `try/except BaseException`, tombstoning the seq before re-raising (§2.2). **Residuals, stated:** (a) an exception that lands after `wal_append` returns but before the `try` is entered, or inside the handler before the tombstone is recorded, leaves the line in place, and it applies once at the next reopen; (b) an exception that lands after the buffer append completed, but still inside the `try`, tombstones a buffered signal. The reducer then applies it in memory although the caller saw an exception, which is the rc1 class of in-memory phantom. The durable state stays self-consistent either way, because a tombstoned seq is in `S` and so is never replayed, and the save that records it also records the rows that hold its effect, or rows without it if it was not yet applied. |

In both, for a multi-entity `weights` dict, the entities before the failing one stay recorded.

**Ruling: not an API change.**
- The signature (`api.py:413`), the return type and the exception type are unchanged.
- It goes in the release notes and in `docs/api.md`.

**Three new raise conditions, ruled the same way.** None changes a signature, and each raises an existing exception type. All three go in the release notes.
- Two live handles whose store paths coincide raise `MonetaResourceLockedError`, even with different `storage_uri`s. The store paths are the resolved `snapshot_path`, `wal_path` and their two derived tmp paths (§2.6). One config whose own four paths are not pairwise distinct raises `ValueError`.
- `snapshot_ecs(ecs)` or `start_background(ecs)` called with an ECS other than the one attached to the handle's log raises `ValueError` (§2.4).
- **A closed `DurabilityManager` refuses to touch the store.** After `close()`, `wal_append`, `snapshot_ecs` and `start_background` raise `ValueError("durability manager is closed")`, which follows the `io` convention for operations on a closed file. rc1 instead reopens the WAL lazily (`durability.py:145-147`), and its `snapshot_ecs` would still rewrite the files. Because `Moneta.close()` releases the store's paths (`api.py:317`), a stale reference or a late thread could otherwise append to, or compact, a store that a new handle now owns. That is two seq allocators on one WAL, the hazard §2.6 closes. Through the public API this means `signal_attention` on a closed durable handle raises `ValueError` and buffers nothing (WAL-first). On a handle without durability it is unchanged.

### 1.5 Why not R2, the shape v5 took

v5 carries attention in its checkpoint (`30ae826`: "checkpoint equality test carries attention since the last pass in the snapshot"). v5 owns its journal format. v1 should not do the same:

1. **It is a format bump.** Embedding the pending buffer in `snapshot.json` is a `snapshot_version` change, and therefore a Trigger 2 (`durability.py:29-34`). This is the deciding reason.
2. **Foreign rewrites of `snapshot.json` do not discriminate between R1′ and R2.** SYNAPSE rewrites `snapshot.json` on an embedder swap (`docs/v5/SYNAPSE_COMPAT.md:33`). Whether that rewrite keeps unknown keys is **unverified**: SYNAPSE's source is outside this clone, and SPEC §0 forbids touching it. That question is an owner-gate item (§6 gate 2).
   - The only modelled consumer rewrites do load-modify-dump: `tests/v5/test_compat.py:629-632` and `:654-656`. They *preserve* unknown keys, and so they would preserve R2's field and R1′'s keys alike. Caveat: both tests run against the v5 facade's derived export, not a v1 store. They model the *shape* of SYNAPSE's rewrite, not its behaviour on a v1 `snapshot.json`.
   - If a rewrite instead *drops* unknown keys, both designs degrade. R2 loses the whole pending buffer. R1′ falls back to the `:218` timestamp rule, and so loses every pending seq line with `ts ≤ T`. That is defect B again, rc1-equal, and H2 pins it as a characterization (§4.2). R1′'s seq lines with `ts > T` still replay.
   - So this point is neutral, or at most slightly favours R1′. It is not an argument against R2 that R1′ escapes.
3. **A window would remain under R2** between the timestamp at `api.py:424` and the buffer append.

---

## 2. R1′ design (amended R1)

### 2.1 State

| Holder | New state | Owner |
|---|---|---|
| `AttentionLog` | `_buffer: list[tuple[AttentionEntry, int \| None]]`; `applied_seqs: set[int]`; `_inflight: set[object]` (one token per running reducer; empty means idle); `_apply_epoch: object` (a fresh `object()` at every reducer start and end, §2.3). **No `threading` import.** `AttentionEntry` stays the public 3-field NamedTuple (`attention_log.py:48-53`). The public `drain()` still returns `list[AttentionEntry]`; the reducer uses a private `_drain_with_seqs()`. `append(entity_id, weight, timestamp, seq=None)`. | Substrate |
| `DurabilityManager` | Existing `_lock` (`durability.py:75`). New `_save_lock`, which serializes `snapshot_ecs` and `close()` against each other. Neither the reducer nor `wal_append` ever takes it. The WAL handle becomes a raw descriptor, `_wal_fd: int \| None` (§2.2). Seq allocator: a plain int `_next_seq`, read and incremented **only under the existing `_lock`**, inside `wal_append` and compaction step 3 (hydrate also allocates, single-threaded, before the handle is published). Nothing depends on seq order matching file order, and it does not always match: hydrate step 6 gives fresh high seqs to no-seq lines that sit earlier in the file, and step 3 renumbers foreign lines in place. Every rule compares seqs only by set membership (test F pins a non-prefix order). The signal path still takes exactly one lock, the one it already takes. `_void_seqs: set[int]`, tombstones from failed appends and from an interrupted buffer append (§2.2), added through a small method `void_seq(seq)` under `_lock`. `_closed: bool`, set by `close()` under `_lock` (§1.4). `_attached: tuple[AttentionLog, ECS] \| None`. `_disposition`: the per-line plan for the WAL as found at hydrate (§2.5). | Persistence |
| `Moneta.__init__` | Attaches `(self.attention, self.ecs)` to the manager after hydrate. `snapshot_ecs(ecs)` keeps its one-argument signature (SYNAPSE calls it, `test_compat.py:66`). Registers the resolved store paths (§2.6). | Substrate |

### 2.2 `signal_attention` and `wal_append`

For each entity in `weights`:

```
seq = durability.wal_append(AttentionEntry(eid, w, now))   # WAL first
try:
    attention.append(eid, w, now, seq=seq)
except BaseException:                  # e.g. KeyboardInterrupt between the write and the append
    durability.void_seq(seq)           # tombstone: never replayed; residuals in §1.4
    raise
```

**`wal_append`, normative.** All of it runs under `_lock`.

```
if _closed:
    raise ValueError("durability manager is closed")     # §1.4; never reopen lazily after close()
if _wal_fd is None:
    fd = os.open(wal_path, O_WRONLY | O_CREAT | O_APPEND | getattr(os, "O_BINARY", 0))
    size = os.fstat(fd).st_size
    if size > 0 and last byte of the file != b"\n":   # torn tail from a crash or power loss
        os.write(fd, os.linesep.encode())               # terminate the fragment first
    _wal_fd = fd
seq = _next_seq; _next_seq = seq + 1                    # allocated before the write; never reused
data = (json.dumps({"wal_version": 1, "entity_id": ..., "weight": ..., "timestamp": ..., "seq": seq})
        + os.linesep).encode("utf-8")
pre = os.fstat(_wal_fd).st_size
try:
    n = os.write(_wal_fd, data)
    if n != len(data): raise OSError("short WAL write")
except BaseException:
    try:
        try: os.ftruncate(_wal_fd, pre)
        except OSError: _void_seqs.add(seq)             # tombstone; logged at ERROR
        try: os.close(_wal_fd)                          # best-effort close
        except OSError: pass
    finally:
        _wal_fd = None                                  # always, even if the close failed
    raise                                               # the original error, never the close's
return seq
```

- **Read the last byte** through a separate `with open(wal_path, "rb")` handle, seeking to `-1` from the end. That handle is closed before the function returns.
- **If the torn-tail repair write fails,** the exception escapes and the signal is not acknowledged. Nothing else changes.
- **Why there is no buffer.** rc1's text handle keeps a line in user space when `flush()` raises. A later flush or close then writes it, which is a phantom apply (§1.4). The unbuffered single write plus truncate-back removes that path.
- **`O_APPEND`.** Each write lands at the end of the file, and `pre` is read under `_lock`, so no in-process writer can move the end between the `fstat` and the write.
- **Tombstones.** `_void_seqs` is merged into `S` at save step 1, so the next snapshot lists the seq as applied, and compaction drops its line. Step 4 then releases those seqs together with `S`. For a failed write, no row ever contains the effect of a tombstoned seq, which matches "the caller was told it failed". For an interrupted buffer append, see §1.4 residual (b).
- **The failure path keeps the original error.** The truncate and the close are each guarded, and `_wal_fd` is cleared in a `finally`. An `OSError` from `os.close` can therefore neither replace the write's error nor leave a stale descriptor that the next append would reuse.
- **A torn tail ending in `\r`** (a tear between `\r` and `\n`) also fails the last-byte check. The repair then appends `os.linesep`, giving `…}\r\r\n`. That is still one raw line (§1.2 grammar), it parses after `strip()`, and its index is unchanged, so a pending hydrate disposition still lines up.

**Why WAL-first is required, not cosmetic.** In rc1's order (buffer first), the reducer could drain, apply and record seq `s` before line `s` reached the file:
1. A save then writes `s` into `wal_applied_seqs`, compacts, and subtracts `s`.
2. Only then does line `s` get appended.
3. The next save writes a set without `s`.
4. The next hydrate replays line `s`: **double apply**.

With WAL-first, every seq in `applied_seqs` has its line in the file before any save can see it.

Without durability (`self.durability is None`), `seq=None` and nothing else changes.

### 2.3 Reducer (replaces `attention_log.py:127-132`; no lock)

```
if log._inflight:
    raise RuntimeError("concurrent attention reducer")    # before draining: nothing lost (best-effort)
tok = object()
clash = False
try:
    log._inflight.add(tok)                   # inside the try: an async exception before it strands nothing
    mine = object(); log._apply_epoch = mine # a value no other reducer can write
    pairs = log._drain_with_seqs()           # the existing single swap, attention_log.py:82
    agg = aggregate([e for e, _ in pairs])
    updated = ecs.apply_attention(agg, now)
    log.applied_seqs.update(s for _, s in pairs if s is not None)
    clash = log._apply_epoch is not mine or len(log._inflight) > 1   # diagnostic only
finally:
    log._apply_epoch = object()              # end-of-apply: changes the epoch again
    log._inflight.discard(tok)               # idempotent; cannot raise
ecs.decay_all(decay.lambda_, now)            # eval point 2, unchanged, outside the window
if clash:
    raise RuntimeError("concurrent attention reducer detected")
return updated                               # unchanged return value (attention_log.py:132)
```

**Rules:**
- `decay_all` keeps exactly three call sites (`api.py:401`, `attention_log.py:131`, `consolidation.py:161`; SPEC §7).
- **What makes a save's read safe** is the save-side check (§2.4 step 1), not anything the reducer detects. A reducer is visible to the save from `_inflight.add(tok)` until `_inflight.discard(tok)`, and its drain, apply and record all happen inside that interval. Its start and its end each store a new object in `_apply_epoch`.
- **Order inside the `try`.** The token is added before the epoch store, and both happen before the drain. So by the time any row or `applied_seqs` changes, the reducer is in the set and the epoch has moved. In the `finally`, the epoch store comes first and the discard second. Either order would be correct, because a reducer that started after the save's first check also moved the epoch at its start, but this order leaves no instant where the reducer has left the set and the epoch still shows its start value.
- **Async exceptions.** `KeyboardInterrupt` under Houdini can land anywhere.
  - If it lands before the `try`, nothing was registered and nothing was drained.
  - If it lands inside the `try`, the `finally` clears the token. If it landed before `add` completed, `discard` of the absent token is a no-op; `discard` cannot raise either way.
  - `AttentionLog.__init__` sets `_inflight = set()` and `_apply_epoch = object()`.
  - If it lands inside the `finally` itself, the token can be stranded. Every later save then sees `_inflight` non-empty, times out, and **degrades** (keyless snapshot, ERROR logged on every save). That is safe, never torn, and it is visible. Reopening the handle clears it. This is a stated residual.
- **Reentrancy detection is best-effort and diagnostic.** The entry check catches a second reducer that starts while one is registered. The `clash` test catches overlap from either side: the first reducer sees the epoch changed by the second, and the second sees the first's token still in the set. A reducer that passes the entry check in the instant before another registers is caught by `clash` only if their applies overlap; if they do not overlap, the two runs were sequential in effect and nothing is wrong. Exactness for the snapshot never depends on this detection.
- A native decay failure at the `decay_all` line happens after the seqs are recorded. That matches SPEC §7 "Exactly-once attention" case 1.

**Residual.** `apply_attention` (`ecs.py:235-245`) mutates rows entity by entity. If it raised midway, the rows would be partly applied with no seqs recorded. A later save would then persist the partial rows, and a replay would double-apply them. For valid input it raises only on `MemoryError`. This is pre-existing in class and is recorded here.

### 2.4 Save: `snapshot_ecs(ecs)`, under `_save_lock`

**Precondition.** If a log is attached and `ecs is not attached_ecs`, raise `ValueError` before writing anything. The consistent read (step 1) pairs `log.applied_seqs` with the rows of the ECS that the reducer writes to. Any other ECS would make `S` describe effects its rows do not contain: a loss or a double on reopen.
- **Closed manager.** If `close()` has run, raise `ValueError("durability manager is closed")` before writing anything (§1.4). `start_background` does the same.
- **In-tree v1 callers at rc1** (`git grep snapshot_ecs\|start_background` over `src tests scripts`, excluding `src/moneta/v5/` and the tests that drive the v5 facade; the `scripts/v5/` directory is **not** excluded, because the bench there drives a v1 handle): `api.py:467`, which passes `self.ecs` (assigned only during `__init__`, `api.py:229, 249`), and `scripts/v5/bench_v5_vs_v1.py:61`, which passes `v1.ecs`. No test under `tests/unit` or `tests/integration` calls `snapshot_ecs` at rc1. The C6 regression file will be the first.
- The `test_compat.py:66, 549, 559, 570, 587, 626` calls pass `m.ecs` too, but to the v5 facade's `_DurabilityView.snapshot_ecs(ecs=None)` (`v5/compat.py:659`), which ignores it. They show SYNAPSE's call shape. They are not evidence about v1 callers. Whether SYNAPSE passes only `m.ecs` to a v1 handle stays owner-gate item 6.
- v5's argument-less `snapshot_ecs()` (`v5/compat.py:852, 886`) is v5's own object, outside this design.
- `start_background(ecs)` applies the same check when it starts.

| Step | Action |
|---|---|
| **0. Normalize** (only if `_disposition` is non-empty) | Under `_lock`: close `_wal_fd`. Read the WAL with `with`, using the §1.2 raw-line grammar (the same reader as hydrate, §2.5 step 2). Write the WAL tmp file `wal_tmp` **in binary mode** (see "tmp paths" and "tmp write mode" below). Lines `i < prefix_len` follow the disposition: drop, or write with their assigned `seq`. Lines `i ≥ prefix_len` (appended since hydrate) are copied unchanged; step 3 of the same save classifies them. Then `os.replace(wal_tmp, wal_path)` and clear `_disposition`. **Semantics-preserving** under the snapshot currently on disk (proof in §3.3).<br>**On step 0 failure, degrade; do not skip the save.** Delete `wal_tmp` best-effort, keep `_disposition` and `applied_seqs`, and log at ERROR. Then go to the **degraded save** below. Do not run steps 1 to 4. |
| **1. Consistent read (optimistic, bounded)** | Set a `time.monotonic()` deadline `SEQLOCK_READ_TIMEOUT_S` (module constant, 5.0 s) ahead. Then loop:<br>1. `e1 = log._apply_epoch`. If `log._inflight` is non-empty, `time.sleep(0)` and retry.<br>2. Build `rows` exactly as `durability.py:85-101`.<br>3. `S = frozenset(log.applied_seqs) \| frozenset(_void_seqs)`, with `_void_seqs` read under `_lock`.<br>4. Accept iff `log._inflight` is empty **and** `log._apply_epoch is e1`; otherwise retry. Both checks are needed: the set catches a reducer still running, and the epoch catches one that started and ended inside the window.<br>**If the deadline passes,** log at ERROR naming the number of in-flight reducers and whether the epoch moved, and go to the **degraded save**. Do not raise and do not hang.<br>No apply overlapped the copy, so `rows` and `S` are mutually consistent. `e1` stays referenced until the check, so its identity cannot be recycled.<br>After the loop, read `nxt = _next_seq` once under `_lock`. Every seq already in the WAL is below `nxt`, and every seq allocated later is above it, which is all `wal_next_seq` needs. |
| **2. Snapshot** | Add `"wal_applied_seqs": sorted(S)` and `"wal_next_seq": nxt` to the dict at `durability.py:103-107`, keeping `snapshot_created_at = time.time()` for older readers. Write with the existing tmp → `fsync` → `os.replace` (`:112-116`). |
| **3. Compact** | Under `_lock`: close `_wal_fd` and set it to `None`. Read the WAL with `with`, using the §1.2 raw-line grammar. Class each line per the §1.2 table: drop blank, undecodable and invalid lines (counting each class, WARNING for undecodable, ERROR for invalid). Of the entry lines, write to `wal_tmp` every one whose `seq ∉ S`. An entry with no seq can only come from a foreign writer here. **Give each one a fresh seq from `_next_seq`** (it is in no row, so replaying it once at the next reopen is correct), count them, and log a WARNING. Write in binary mode, per "tmp write mode" below. Flush, close, `os.replace(wal_tmp, wal_path)`. `_wal_fd` stays `None`, so the next `wal_append` reopens, including its torn-tail check (§2.2). |
| **4. Release** | `log.applied_seqs.difference_update(S)` and `_void_seqs.difference_update(S)` under `_lock`, **only after step 3 succeeded**. This is an in-place C set operation on ints, and it does not race the reducer's `update`. Do not rebind the attribute. Seqs applied after step 1 stay in the set. |

**tmp paths (normative).** The WAL tmp file is `wal_tmp = wal_path.with_name(wal_path.name + ".tmp")`, which is next to the WAL and derived from its full name, exactly as rc1 derives the snapshot tmp (`snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")`, `durability.py:109-111`). It is never a fixed name such as `wal.tmp`: two stores in one directory (`a.wal`, `b.wal`) would then share one tmp file, and one store's `os.replace` could install the other's lines. Both derived tmp paths are registered in `_ACTIVE_STORE_PATHS` (§2.6), so no live handle's store path can be another handle's tmp path.

**tmp write mode (steps 0 and 3, normative).** Open `wal_tmp` with `open(…, "wb")`.
- A line kept unchanged is written as its original raw bytes, terminator included. If it is the final unterminated run (§1.2), `os.linesep` is appended, so the tmp always ends in a terminator.
- A line that is rewritten (a seq assigned) is re-serialized with the same key set as §2.2, then encoded with `os.linesep` as its terminator.
- Never write the tmp in text mode. On Windows, text mode turns a `\r\n` read from a binary reader into `\r\r\n`. That breaks the byte-identity with rc1's lines claimed in §1.2, and it adds a blank-looking `\r` to every line. Both readers would still strip it, but test O's "WAL bytes unchanged" assertions would become meaningless.
- The reader used by steps 0 and 3 must open the WAL in binary mode too and apply the §1.2 raw-line grammar, so the raw-line indices match hydrate's (§2.5 step 2). One shared function implements the grammar for all three.

**Degraded save.** This is the path for a step 0 failure and for a step 1 timeout. It gives rc1 semantics and keeps deposits durable.
1. Build `rows` once, without the consistency check, as rc1 does (`durability.py:85-101`).
2. Write a **keyless** snapshot: rc1's dict, with no `wal_applied_seqs` and no `wal_next_seq`. Use the existing tmp → `fsync` → `os.replace`.
3. **Leave the WAL alone.** No step 0, no compaction, no unlink. Skip step 4. Keep `_disposition` and `applied_seqs` for the next save.
4. Increment `degraded_saves` (a private int on the manager, for tests and the log line; both entries, a step 0 failure and a step 1 timeout, count), log at ERROR naming the entry, then return normally, so the deposit save succeeds.

What a degraded save means:
- **On reopen,** every line is judged by `timestamp > T_new` (§2.5, key absent). Losses equal rc1's: pending lines with `ts ≤ T_new` are lost, which is defect B.
- **No double apply, under the precondition in §3.4:** every signal applied before the snapshot has `ts ≤ T_new`. A signal clock running ahead of the snapshot clock breaks it. Under that condition, lines already applied in memory replay on reopen: a double.
- **Unlike rc1, the WAL is not unlinked,** so it grows for as long as the failure persists. Every degraded save logs at ERROR, so the condition is visible.
- **The next save retries step 0.** `_disposition` is still valid against the keyless `T_new` snapshot now on disk. Its drops are lines with `seq ∈ A`, or with `ts ≤ T_old ≤ T_new`, or duplicates. Under the precondition, the timestamp rule drops all of those too. Its seq assignments are invisible to a keyless reader.

**Compaction failure.** For example, `PermissionError` from `os.replace`; see Windows in §3.1.
- Delete `wal_tmp` on a best-effort basis.
- **Skip step 4**, so `S` stays in `applied_seqs` and the next save writes it again.
- Re-raise the original error. rc1's `unlink` failure also escapes `snapshot_ecs`, and the background thread logs it (`durability.py:240-243`). The snapshot (step 2) is already written, so the deposits are durable. This differs from a step 0 failure, which happens before any snapshot is written and therefore degrades instead.
- **Known bound.** If compaction keeps failing across saves, `S` is never subtracted, so `applied_seqs` and `wal_applied_seqs` grow without bound until one compaction succeeds. Each failure is raised and logged, so the condition is visible.
- The disk is then in the "after step 2, before step 3" state. That is safe for R1′ (§3.3), but it is an **rc1-reader exposure** for as long as the failure persists (§3.5).
- **If step 4 ran after a failed step 3,** the next snapshot would omit `S` while its lines are still in the WAL, and the next hydrate would double-apply them.

**`close()`.** `DurabilityManager.close()` calls `stop_background()` (whose join has a 5 s timeout, `durability.py:257`), then takes `_save_lock`, then `_lock`, then sets `_closed = True` and closes `_wal_fd` (guarded, then set to `None`). From then on `wal_append`, `snapshot_ecs` and `start_background` raise (§1.4). `close()` itself stays idempotent. Because `Moneta.close()` calls it before it releases the URI and the store paths (`api.py:311-317`), no append or save from this manager can reach the files once another handle may own them. A background save still running after the join timeout therefore finishes before the descriptor closes. The order `_save_lock` → `_lock` is the global order (§3.1), so this adds no deadlock. The wait is bounded, because step 1 is bounded and the file steps are finite.

**Without an attached log** (a bare `DurabilityManager`; no src or test constructs one other than `api.py:225`): exact rc1 behaviour. No new keys are written, and the WAL is unlinked.

### 2.5 Hydrate (normative; modifies no file)

1. Load the snapshot as `durability.py:190-215` does.
   - `key_present = "wal_applied_seqs" in snapshot`.
   - `A = set(snapshot.get("wal_applied_seqs", []))`.
   - With no snapshot file (`:183-188`): `key_present = True`, `A = ∅`, `snapshot_ts = 0.0`. That reproduces rc1's replay-everything.
2. Read the WAL **by raw line** `i`, using the §1.2 grammar: maximal runs ending in `\n`, plus a final non-empty unterminated run, and never a trailing empty piece. Blank and undecodable lines are counted too. rc1's `wal_read` skips both (`durability.py:158-167`), so an index over parsed entries would shift every disposition after the first blank line. Class every line per the §1.2 table; an **invalid** line raises its original exception, as rc1 does, so a store that rc1 cannot open, R1′ cannot open either (register test P6 is unchanged). A `seq` counts only under the §1.2 rule. Step 0 and step 3 use this same reader.
   - **Why the trailing empty piece matters.** A WAL that ends in `\n` (the normal case) split naively on `b"\n"` gives a phantom empty last piece. Hydrate would record it as raw line `prefix_len-1` with disposition *drop (blank)*, so `_disposition` would be non-empty on every reopen. The first post-hydrate `wal_append` then lands at exactly that index, and step 0 would drop it: an acknowledged, pending signal gone from the WAL while it sits in the buffer, and lost on a crash after that save. Test AE pins it.
3. **Decide each line:**

   | Line | Rule |
   |---|---|
   | `key_present` and has `seq` | Replay iff `seq ∉ A`. |
   | No `seq`, or key absent | Replay iff `timestamp > snapshot_ts`, the rc1 rule at `:218`. |

4. **Duplicate seq.** Only a collision (§2.6) or a foreign writer can produce one. The first occurrence wins. Later ones are dropped with a WARNING and counted in the `durability.hydrate` log line. A collision must never be dropped silently.
   - First-wins means a cross-lineage collision drops the *newer* signal. That is the intended default: the seed rule makes a collision reachable only through a foreign snapshot replacement, or through two handles sharing a WAL, which §2.6 now refuses. Do not flip it without a new ruling.
5. **Seed the allocator (normative):**
   ```
   sources = [snapshot["wal_next_seq"]] if present
           + [max(A) + 1] if A
           + [max(seqs in WAL) + 1] if any
   next = max(sources) if sources else secrets.randbits(32) << 20   # random lineage base
   ```
   - **All three sources are required.** Without `max(A)+1`, a rewrite that keeps `wal_applied_seqs` but drops `wal_next_seq`, over an empty WAL, would reseed low. New signals would then be filtered as already applied: loss. Test L pins this; it seeds from `A`, so the new seq is ≥ 10.
   - **The random base is normative,** not a recommendation. It is used exactly when no seq information exists: a fresh store, an rc1 store, or a store whose seq information was stripped. It stays below 2^52, under JSON's 2^53. Test Z pins it.
6. **Assign fresh seqs** from the seeded allocator to replayed lines that have none.
7. **Record `_disposition`** for the first save's step 0:
   - `prefix_len` = the raw line count at hydrate;
   - for each raw line: *drop* (filtered, a duplicate, `seq ∈ A`, blank, or undecodable), or *keep with seq s*. "Malformed" in this document means exactly the §1.2 **undecodable** class (`JSONDecodeError`); an **invalid** line never reaches a disposition, because hydrate raised on it. Dropping blank and undecodable lines preserves semantics, because no reader ever replays them. That includes an undecodable torn tail fragment; a torn fragment that parses is an entry and is judged like any other line.
   - The disposition is empty when every line already carries a seq and none is dropped.
8. **Key absent but seq-bearing lines present.** This means an rc1 save, a degraded save, or a foreign rewrite happened. Log a WARNING. This is the only "store-format marker" behaviour available (§3.5).
9. Replay into the log with `seq=s`, via the `api.py:238-241` loop, which passes `seq` through.
10. **Return shape.** The public `hydrate()` keeps its return type (`durability.py:181`: `Tuple[ECS, List[AttentionEntry]]`). HEAD still has `def hydrate(self)`; the `native=` keyword is one this branch **will add** (SPEC §2). A private `_hydrate_with_seqs()` returns `(ECS, List[Tuple[AttentionEntry, int]])`, and `Moneta.__init__` (`api.py:229`) calls it. The public method delegates and strips the seqs.

**Hydrate writes nothing.** SPEC §7 "Failure cleanup" requires that a failed hydrate "modify no file". So normalization, including the torn-tail repair, is deferred: step 0 does the normalization at the first save, and the first `wal_append` does the repair. That is also why the plan's "seed `applied_seqs` with `wal_applied_seqs ∩ WAL`" step is unnecessary: step 0 drops those lines while the old snapshot is still the one on disk.

### 2.6 Sequence allocation and store-path uniqueness

**Scope: per store lineage, held by the single handle that owns the store's files.**
- rc1's registry locks on `storage_uri` only (`api.py:166-169, 198-204`). But `MonetaConfig` takes `snapshot_path` and `wal_path` independently of `storage_uri` (`api.py:125-133`), and `ephemeral()` mints a fresh URI per call (`api.py:154-157`). So two in-process handles can share one WAL today, each with its own `_lock` and `_next_seq`.
- That would break R1′ three ways:
  - duplicate seqs, where first-wins (§2.5 step 4) drops a real signal, with only a WARNING;
  - one handle's step 3 replace racing the other's open append descriptor, which takes the K path forever on Windows;
  - one handle's `S` subtracting lines the other never applied.
- **Ruling: enforce path uniqueness.** Add a sibling registry `_ACTIVE_STORE_PATHS: set[str]` in `api.py`, holding `os.path.normcase(os.path.realpath(p))` for four paths per handle: `snapshot_path`, `wal_path`, the snapshot tmp (`snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")`, `durability.py:109-111`) and the WAL tmp (`wal_path.with_name(wal_path.name + ".tmp")`, §2.4). If a handle's own four paths are not pairwise distinct, raise `ValueError` (§1.4).
  - Check and add the entries next to the URI check at `api.py:198-204`. Discard them in `close()` (`:317`) and in the partial-init handler (`:273-275`).
  - On a clash, raise `MonetaResourceLockedError`, naming the path and the fact that it is held.
  - One set holds every kind of path, so a `snapshot_path` that equals another handle's `wal_path`, or a store path that equals another handle's tmp path, is also refused.
  - Not covered: hard links, and aliasing that `realpath` does not resolve. Those stay a stated precondition.
  - **Suites checked for concurrently live handles that share paths** (`git grep -n "wal_path\|snapshot_path" v1.3.0-rc1 -- tests scripts`, then each hit read):
    - **`tests/v5/test_v1_defects.py:308-320`, `test_v1_p11_two_uris_on_one_snapshot_lose_writes`, breaks.** It opens `a` (URI "A") and `b` (URI "B") on the same `shared.json` and `shared.wal`, both live at once, and asserts that `b`'s sleep pass overwrites `a`'s deposit. Under §2.6, `b = Moneta(...)` raises `MonetaResourceLockedError`. This is the intended outcome: P11 is a v1 defect register entry, and the file's docstring (`:5-7`) says such a test "fails, and the register must be updated" when v1 is fixed. **Planned register update (gate 3):** rewrite it as `test_v1_p11_two_uris_on_one_store_are_refused`. `a` constructs; `Moneta(MonetaConfig(storage_uri="B", **kw))` raises `MonetaResourceLockedError`; `a` deposits, runs a sleep pass and closes; a handle on URI "C" then sees exactly `["from A"]`. `test_v5_p11_one_journal_one_owner` is unchanged. The P11 row of `docs/v5/BLUEPRINT.md:55` is updated in the same PR (gate 5).
    - `tests/v5/test_v1_defects.py:143-165`, P6: one handle at a time; unaffected by §2.6. Its outcome under R1′ hydrate is set by §1.2 (unchanged: still raises `ValueError`).
    - `scripts/v5/bench_v5_vs_v1.py:50-70`: the second handle opens after `v1.close()`. Fine.
    - `tests/integration/test_durability_roundtrip.py`: every reopen follows a `close()` or a `with` exit. Fine.
    - `tests/test_twin_substrate.py:42-49`: distinct directories `a/` and `b/`. Fine.
    - `tests/v5/test_compat.py`, `tests/v5/test_half_life.py`: v5 facade handles. The facade registers only its URI in `_v1api._ACTIVE_URIS` (`v5/compat.py:695-699`), and v5 source is out of scope, so it never registers store paths and these tests are unaffected. `test_compat.py:551` also reopens only after a close.
  - **Residual.** Because the facade registers no paths, a live v5 facade handle and a live R1′ v1 handle on the same files under different URIs are **not** refused by R1′. That is the mixed-interpreter case of §3.5, governed by "cut over both interpreters together".
- Two processes on one store are unsupported, exactly as in rc1. See "Mixed interpreters" (`docs/v5/SYNAPSE_COMPAT.md:51`).

**Seeding on reopen:** see §2.5 step 5.

**Invariant (no collision within a lineage), given path uniqueness.**
- Every seq present in the WAL, or in the current snapshot's `wal_applied_seqs`, is below the seed.
- Seqs are compared only between the current snapshot and the current WAL.

**After an rc1 build wrote the store:**
- An rc1 sleep pass or save writes a keyless snapshot and unlinks the WAL (`durability.py:103-107, 119-125`). R1′ then reopens with no seq information and seeds from the random base. Nothing references old seqs.
- If rc1 saved but its unlink failed, the old seq lines remain. They are judged by timestamp (key absent), and the seed is `max seen + 1`. Step 0 then drops the filtered ones.

**The only cross-lineage collision path** is replacing `snapshot.json` with a copy from another lineage, for example restoring a backup. Lines whose seqs happen to be in the stale `A` would then be skipped: loss.
- Restoring from backup is not a supported operation for rc1 either.
- With the random base, a cross-lineage overlap needs about 2^20 aligned slots to coincide.

---

## 3. Design review: the questions answered explicitly

### 3.1 A concurrent append and a sleep-pass drain during WAL replacement

**Lock map (R1′):**

| Path | Takes | Never takes |
|---|---|---|
| `signal_attention` → `wal_append` | `_lock` | `_save_lock`. No lock on the log. |
| Reducer (sleep pass) | **nothing.** It adds and discards its token in `_inflight` and assigns `_apply_epoch`. | any lock |
| `snapshot_ecs` | `_save_lock`, then `_lock` for step 0, for the `_void_seqs` and `_next_seq` reads in step 1, for step 3 and for step 4's `_void_seqs` release. Rows are built without `_lock`. | — |
| `DurabilityManager.close()` | `_save_lock`, then `_lock` | — |
| `hydrate` | — (single-threaded, inside `__init__`) | — |

**Lock order:** `_save_lock` → `_lock`. Nothing takes them in reverse, and the reducer takes neither, so there is no deadlock. Every wait on `_save_lock` is bounded, because step 1's spin is bounded.

**A line appended between the WAL read and `os.replace`:** impossible in-process.
- Compaction holds `_lock` from the descriptor close, through the read, the tmp write and the `os.replace`. `wal_append` needs `_lock` to write.
- A concurrent signal therefore either finished its write before compaction took `_lock`, so the read sees it, or it **blocks** until compaction finishes. A line the read sees is handled by membership either way. If a reducer drained, applied and recorded it before step 1's read, its seq is in `S` and the rows written at step 2 hold its effect, so dropping it is correct. Otherwise `seq ∉ S` and it is kept. (Revision 3 said such a line "cannot have been applied before it was saved"; that was wrong, though the handling was right.)
- In the blocking case the signal is, by WAL-first ordering, in neither the WAL nor the buffer while it waits. It then opens the *new* file and lands there.
- **A writer in another process** appending in that window would be lost by the replace. rc1's `unlink` loses it too. Cross-process writers are unsupported.
- **Two in-process handles on one WAL** are refused at construction (§2.6).

**A drain during compaction:** harmless. The reducer touches neither file. It can apply and record new seqs while step 3 runs. Those seqs are not in `S`, so their lines are kept, and they stay in `applied_seqs` for the next save (step 4 subtracts only `S`).

**A drain during step 1:** the save detects it (a token in `_inflight`, or a moved `_apply_epoch`) and retries, up to the bound. The reducer never waits. This holds for any number of overlapping reducers (§1.3).

**A save during a pass, path D:** a signal after the drain is WAL-first, so it is in the file with `seq ∉ S`. Compaction keeps it, a restart replays it, and in-process it is applied by the next pass. **D passes.**

**New cost, stated plainly:**
- `signal_attention` can stall for one compaction: O(lines in the WAL since the last save), plus a one-time step 0. SYNAPSE's save-on-add cadence keeps that small. rc1's stall was a single `unlink`.
- Each append is now an unbuffered `os.write` plus an `fstat`. rc1 did a buffered write plus a `flush`, which is also one syscall per line, so the syscall count per append is about the same.
- A save spins for at most one apply window per retry, and for at most `SEQLOCK_READ_TIMEOUT_S` in total.
- **Save starvation under continuous passes.** Step 1 accepts only a read during which no reducer was in flight, so it needs a quiet gap longer than one O(N) row build. If sleep passes run back to back with no such gap for the whole bound, every save degrades to a keyless snapshot (ERROR, `degraded_saves` incremented), and pending `ts ≤ T` lines are then exposed to the rc1-equal loss on reopen. The design makes this visible, not impossible. The envelope runs consolidation "only during inference idle windows > 5 seconds" (`ARCHITECTURE.md:272`, §15.2 constraint 2), which leaves gaps; a caller that drives `run_sleep_pass()` back to back can still starve saves. Stress test T must leave such a gap and assert that no degraded save happened.

**Windows open-handle semantics.**
- Python `open()` and `os.open()` use the CRT, which does not pass `FILE_SHARE_DELETE`. `os.replace` uses `MoveFileExW(MOVEFILE_REPLACE_EXISTING)`. It fails with `PermissionError` (WinError 5 or 32) while *any* handle to the destination lacks share-delete. [I, platform]
- In-process this is handled: `_wal_fd` is closed under `_lock` first, as rc1 does at `durability.py:120-123` for its `unlink`. Compaction's own read handle is closed by `with` before the replace, and the tmp is in the same directory, so this is not a cross-volume move.
- Out-of-process handles (antivirus, the indexer, a SYNAPSE tail, a v5 migration's `read_text` at `v5/compat.py:1005`, which closes promptly) can make the replace fail.
  - At step 3 that takes the "compaction failure" path in §2.4: the snapshot is written, the error is surfaced, and the next save retries.
  - At step 0 it takes the degraded save, so deposits are still persisted.
  - rc1's `unlink` fails the same way today.
  - A *persistent* foreign handle keeps the store on the degraded or K path. Both log at ERROR every save. Neither stops deposits being saved.
- Test W covers it.

### 3.2 Sequence allocation

Covered in §2.5 step 5 and §2.6:
- per store lineage, held by the single handle, with store-path uniqueness enforced;
- seeding = max of three sources, else the random lineage base (normative);
- after an rc1 write, a fresh random base is safe because nothing references old seqs, or old lines are timestamp-judged and then dropped by step 0;
- collisions are impossible within a lineage, and possible only through foreign snapshot replacement across lineages, which the random base mitigates;
- duplicates are logged, never silently dropped.

### 3.3 Crash recovery at every step

`T_old` and `T_new` are the old and new `snapshot_created_at`. `S` is the set written at step 2. "R1′ reopen" means §2.5. "Clock precondition" means §3.4: every signal applied before a snapshot has `ts ≤` that snapshot's `T`.

| Crash point / failure | Disk state | What R1′ replays | Correct? |
|---|---|---|---|
| `signal_attention` before `wal_append` | unchanged | nothing (the caller was not acknowledged) | yes |
| `wal_append` write raised, truncate succeeded (no crash) | unchanged | nothing | yes. The caller saw the error. |
| `wal_append` write raised, truncate failed | the line may be whole or torn; `seq` is in `_void_seqs` | a torn line: nothing. A whole line: nothing after the next save, because the seq is in `A`. **A crash before that save replays it once.** | residual, stated in §1.4 |
| torn tail (power loss or OS crash, §5 exposure 1) | the WAL ends in a fragment of a line that **was** acknowledged: a process kill -9 cannot tear one `os.write` already handed to the OS [I, platform], so a tear comes from the OS losing the tail of written data | if the fragment is undecodable (§1.2): nothing; if it parses (a tear right after `}`, or between `\r` and `\n`): the signal, once. Either way the next append terminates the fragment first (§2.2) | acceptable. An undecodable fragment is an acknowledged signal lost to power loss, the Round 4 F1 class (§5). A parseable fragment is a complete, acknowledged signal, and replaying it once is correct. |
| process crash after `wal_append` returned, before the buffer append | the line is in the WAL | the line (`seq ∉ A`) | yes, once. The caller was never told the call returned or failed. |
| async exception after `wal_append` returned, process alive | the line is in the WAL; the seq is tombstoned (§2.2), unless the exception landed outside the `try` | nothing after the next save (seq in `A`, line compacted). A crash before that save replays it once. | residual, stated in §1.4 (a) and (b) |
| reducer after drain, before apply | old snapshot, full WAL | every drained line | yes |
| reducer after apply-and-record, at or after `decay_all` raised | old snapshot, full WAL | every line: the old rows lack them | yes, once (SPEC §7 case 1) |
| save step 0, before `os.replace` | original WAL, stray `wal_tmp`, old snapshot | as before the save | yes |
| save step 0, after `os.replace` | normalized WAL, old snapshot | see the proof below | yes |
| **save step 0 failed (no crash): degraded save** | **original WAL, new keyless snapshot `T_new`**; `_disposition` kept in memory | lines with `ts > T_new` | no double under the clock precondition. Pending lines with `ts ≤ T_new` are lost, rc1-equal. The next save retries step 0. |
| **step 1 timed out: degraded save** | as the row above | as the row above | as the row above |
| step 1 | none | — | — |
| step 2, before `os.replace` | old snapshot, stray `snapshot.json.tmp`, WAL | as before the save (= test C) | yes |
| **step 2 done, before or during step 3** (including a crash mid-rewrite: `wal_tmp` written partly, not replaced) | **new snapshot (rows include `S`; key = `S`) and the full WAL, including the lines in `S`** | lines `∉ S`, which are pending; the rows lack them, including seqs applied after step 1 | yes. The lines in `S` are filtered, and the next save's step 0 drops them (G, G2). |
| step 3 `os.replace` done, before step 4 | new snapshot, compacted WAL (foreign no-seq lines now carry fresh seqs) | the pending lines, plus each foreign line once | yes. The in-memory `S` is irrelevant after a crash. |
| step 3 failed (no crash) | the same as "step 2 done" | — | yes for R1′, but step 4 is skipped (K). An rc1-reader exposure lasts while the failure persists (§3.5). |

**Proof that step 0 preserves semantics** under the snapshot on disk `(key?, A, T)`:
- **When the old snapshot is on disk** (`T = T_old`):
  - The lines it drops are exactly those the old snapshot already filters out: `seq ∈ A`, timestamp-filtered lines, duplicates, blank and undecodable lines (§1.2). There are no invalid lines in the prefix, because hydrate raised on them.
  - Raw-line indices are stable between hydrate and step 0: appends only add runs after the last one, and the torn-tail repair only terminates the final run (§2.2). Since a trailing empty piece is never a raw line (§1.2), the first append cannot land on an index the disposition covers.
  - The lines it keeps are those it replays. Each gets a seq from an allocator seeded above `A` and above every seq in the WAL, so the new seq is `∉ A`.
  - With the key present, a kept line is therefore still replayed by membership.
  - With the key absent, the timestamp rule still applies to every line, and kept lines have `ts > T_old` by construction.
  - Therefore reopen-after-step-0 equals reopen-before-step-0.
- **When a degraded save put a keyless `T_new` on disk:** a keyless reader ignores seqs, so only the drops matter. Every dropped line has `seq ∈ A`, `ts ≤ T_old`, or is a duplicate, blank or undecodable. Under the clock precondition, each also has `ts ≤ T_new`, so the timestamp rule drops it anyway. If the precondition fails, step 0 can only remove lines that would double-apply; it never adds a replay.

**Why step 0 is needed: a hazard in the plan as written.** The plan's fallback (key absent → timestamp rule for every line) plus its compaction rule ("keep lines whose `seq ∉ S`") resurrects lines. Take an rc1 save whose unlink failed, so old seq lines survive under a keyless snapshot:
1. The timestamp rule filters those lines.
2. Their seqs are not in `S`, so compaction keeps them.
3. The next R1 snapshot has the key with a set that lacks them.
4. The following reopen replays them by membership. That is a double apply for lines rc1 applied, and a resurrection for lines rc1 dropped.

Step 0 deletes them before any keyed snapshot exists. Test H3.

**Legacy no-seq lines need step 0 too.** Without it, an unapplied legacy line kept through a crash between steps 2 and 3 would be judged by the timestamp rule against `T_new` and dropped. Step 0 gives it a seq first. That is also why a failed step 0 must never be followed by a keyed snapshot, and degrades instead.

### 3.4 Wall clock and timestamps

**R1′'s own lines are immune to the clock only once a keyed snapshot is on disk.**
- Under a keyed snapshot, lines R1′ writes are decided by seq membership, and the clock does not matter for them.
- That fixes a pre-existing rc1 loss too: in rc1, after a backward clock step, new signals get `ts < T_last` and are dropped on any reopen (`:218`), even with no save in between.
- **Under a keyless snapshot, R1′'s seq lines are judged by timestamp** (§2.5, table row 2). A backward step then drops them on reopen: a loss. A keyless snapshot is on disk in these cases:
  - an rc1 store before the first R1′ save;
  - a snapshot whose keys a foreign rewrite stripped (H2);
  - after a degraded save (§2.4);
  - after an rc1 save in a roll-back-and-forward sequence (§3.5).

**The timestamp rule survives only in these places:**
- legacy lines without a seq;
- the key-absent fallback, listed above;
- older readers (§3.5).

**The precondition is not "a monotone clock".** Wherever the timestamp rule judges a line that was already applied, the condition for no double apply is:

> **signal clock ≤ snapshot clock:** every signal applied before a snapshot has `ts ≤` that snapshot's `snapshot_created_at`.

- A monotone wall clock shared by both stamps satisfies it.
- It fails on a backward wall-clock step between signal and save.
- It also fails when the two stamps come from different clocks. `signal_attention` stamps `now` from `moneta.api.time` (`api.py:424`). `snapshot_created_at` comes from `durability.py`'s own `time` import (`durability.py:43, 102`). The load harness patches only `moneta.api.time` (`tests/load/synthetic_session.py:58-62`). If that virtual clock runs ahead of the real one, an applied line has `ts > T`, and every timestamp-judging reader double-applies it.
- Q is extended to model that case (§4.2).

**`time.time()` resolution.** Python ≥ 3.13 on Windows uses `GetSystemTimePreciseAsFileTime`; hython's 3.11 uses the coarse ~15.6 ms clock [I, CPython changelog]. An equal timestamp hits rc1's strict `>` and is **dropped**, never doubled.

**Caller-supplied timestamps: none in v1.**
- `signal_attention(weights)` takes only weights (`api.py:413`). It stamps `now = time.time()` (`api.py:424`).
- The only foreign timestamps come from three places:
  - WAL lines written by hand (test E writes them, test file `:153-158`);
  - the load-test virtual clock, above. R1′ membership removes the dependence once a keyed snapshot exists;
  - v5's `signal_attention(..., t=ts)` (`v5/compat.py:1027`), which is the v5 substrate, not the v1 WAL writer.

### 3.5 Older readers, rollback and roll-forward

**Optional keys do not by themselves make rollback safe.** These are the concrete outcomes. "Clock precondition" is §3.4's "signal clock ≤ snapshot clock".

**Older readers:**
- **rc1:** its replay rule is `timestamp > snapshot_created_at` (`durability.py:218`). It ignores `seq` and the new snapshot keys.
- **v5 migration:** the same rule, with `ts <= snap_ts` skipped (`v5/compat.py:1018-1020`). It also ignores `seq`.

| Sequence | Outcome | Class |
|---|---|---|
| **rc1 store → R1′** | The key is absent, so every line follows the `:218` rule, the same as rc1. The seed comes from the WAL, or from the random base. Step 0 normalizes at the first save. | **safe** (rc1-equal) |
| **R1′ (clean save) → rc1** | The WAL holds only pending lines, `seq ∉ S`. rc1 replays those with `ts > T` and **loses** those with `ts ≤ T`: exactly the undrained lines R1′ preserved (the B and D lines). | **loses**, never doubles |
| **R1′ crashed between steps 2 and 3 → rc1** | The WAL also holds the applied lines in `S`. Under the clock precondition their `ts ≤ T_new`, so rc1 filters them. If the precondition fails, rc1 replays them onto rows that already include them. Pending `ts ≤ T` lines are lost. | **loses; could double-apply** (precondition broken + crash window) |
| **R1′ with step 3 failing persistently (K), then a clean close → rc1** | The same disk state as the row above, but it lasts **for as long as compaction keeps failing**, not just for a crash window. Every K-path save leaves the `S` lines in the WAL. | **loses; could double-apply** (precondition broken), for the whole failure period |
| **R1′ degraded save (step 0 failure or step 1 timeout) → rc1, or → R1′** | A keyless snapshot. Both readers apply the timestamp rule to every line. | **no double under the precondition; loses pending `ts ≤ T` lines** (rc1-equal) |
| **R1′ → rc1 → R1′, rc1 saved** | rc1 writes a keyless snapshot and unlinks the WAL. Every line pending under R1′ with `ts ≤ T` that rc1 did not replay is gone, and so is any line rc1 replayed but did not apply before its bare save. R1′ reopens on the timestamp rule, with a fresh random seed base. | **no double; loses R1′-pending `ts ≤ T` lines** |
| **R1′ → rc1 → R1′, rc1 never saved** (it signalled, then crashed) | R1′'s keyed snapshot is still current. Seq lines follow membership. rc1's no-seq lines have `ts > T` and replay; step 0 gives them seqs. | **safe** |
| **R1′ → rc1 → R1′, rc1 saved but its unlink failed** | A keyless snapshot plus old seq lines. The timestamp rule filters the lines rc1 applied, and step 0 drops them. Without step 0 this case resurrects them (H3). R1′-pending lines with `ts ≤ T` that rc1 did not replay are filtered too. | **no double with step 0; loses R1′-pending `ts ≤ T` lines** |
| **R1′ store → v5 migration** | The same as R1′ → rc1: pending lines with `ts ≤ snap_ts` are counted as `wal_before_snapshot` and lost. A double needs the crash window or a K-path failure, plus a broken clock precondition. v5 source is out of scope (SPEC §0); follow-up for the v5 owner: honour `wal_applied_seqs`. | **loses**; could double if the precondition breaks |
| **R1′ → v5 facade → R1′** (mixed interpreters, or a rollback from v5 to an R1′ v1 build) | After migration the facade overwrites `snapshot.json` with a **keyless** v5 export, whose `snapshot_created_at` is v5's own snapshot time (`v5/compat.py:264`), and keeps `wal.log` byte-for-byte as a migration input (`test_compat.py:151`; `SYNAPSE_COMPAT.md:33`). An R1′ handle that reopens this store sees the key absent, so it judges **every** seq line by `timestamp > T_v5`. v5 has already folded those lines into its export rows. (1) Lines with `ts > T_v5` replay onto rows that include them: **double apply**. That happens whenever v5's clock (`ManualClock`, or an explicit `t=`) is behind the line timestamps, which is the clock precondition broken across interpreters. (2) Lines with `ts ≤ T_v5` are filtered. That is correct for the ones v5 replayed at migration. The ones v5 skipped (`ts ≤` the R1′ snapshot's `T`, the row above) stay lost. (3) Everything the facade journaled after migration is invisible to v1, except what its export rows already hold. (4) R1′'s first save then runs step 0 and compaction on `wal.log`, rewriting a file v5 treats as a byte-preserved migration input, and replaces `snapshot.json` behind v5's back. The next v5 open then refuses (`SYNAPSE_COMPAT.md:33`: any other foreign write is refused, `SnapshotDivergedError`; `:51`: "v5 detects that and refuses to open. It does not merge."). | **loses v5-only state; double-applies when the v5 clock is behind the line timestamps; then v5 refuses the store.** Unsupported. The rule "cut over both interpreters together" (`SYNAPSE_COMPAT.md:51`) applies unchanged, and it is **enforced by v5's refusal, not by R1′**: R1′ cannot detect a v5 export. Its only signal is the step 8 WARNING (key absent, seq lines present). The operator card states it. |

**rc1 against itself has the same double-apply exposure.**
- rc1 crashing between `durability.py:116` (snapshot replaced) and `:125` (WAL unlinked), with the clock precondition broken, double-applies too.
- R1′'s exposure is the matching window, between steps 2 and 3, extended for as long as step 3 keeps failing. For R1′ readers it ends at the next save's step 0. For rc1 readers it ends at the next successful compaction.
- So for double application, R1′ is **no worse than rc1-on-rc1** within a crash window. Its persistent K-path exposure toward rc1 readers is new, visible (ERROR every save), and needs a broken clock precondition to bite. R1′ is strictly better on loss.

**The apply-to-save interval is not an exposure.**
- Between a pass's apply and its save, the on-disk snapshot is the old one, whose rows lack those applies.
- Any reader, rc1 included, that replays those lines is correct.

**Mitigations, honestly scoped:**
1. **Compaction removes applied lines** immediately after step 2. Afterwards, an rc1 reader can see applied lines only in the crash window or while compaction keeps failing.
2. **Drain, then verify, before a downgrade.** This is the operational fix, and it goes in the operator card:
   1. Quiesce signals.
   2. Under R1′, run `run_sleep_pass()`, then `close()`.
   3. **Verify that the WAL is empty:** the file is absent, or holds zero non-blank lines.
   4. If it is not empty, do not switch. Either a signal raced the pass, or compaction failed (the K path leaves the `S` lines in place). Fix the cause, then repeat from step 2.

   Only a verified-empty WAL makes the store indistinguishable from an rc1 store. It is the only way to make R1′ → rc1 lossless.
3. **A store-format marker cannot make rc1 refuse anything.** rc1 is fixed code. It only warns on a `snapshot_version` mismatch and loads anyway (`durability.py:193-199`). A bump would also be a Trigger 2 (`:29-34`). **Refusing a downgrade is unavailable.** The marker's only use is R1′ warning on hydrate when the key is absent but seq lines exist (§2.5 step 8).

---

## 4. Regression tests

**File:** `tests/integration/test_attention_snapshot_regression.py`, Test Engineer.

### 4.1 Already written: B and D

B and D are copied verbatim from `$S/durab/tests/integration/test_attention_snapshot_regression.py:72-91` and `:115-139`. Per SPEC §8, C6 marks both:

```python
@pytest.mark.xfail(strict=True, reason="UNRESOLVED DEFECT: undrained attention lost across snapshot/restart (path B); see docs/design/R1-attention-durability.md")
```

D uses the same marker with `(path D)`. The R1′ PR removes both markers, and nothing else in B or D changes.

Verbatim source, shared helpers `_cfg` and `_save` at `:28-40` of the same file; `_save` is `m.durability.snapshot_ecs(m.ecs)`:

```python
def test_B_undrained_attention_survives_snapshot_and_reopen(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path, "B")
    with Moneta(cfg) as m1:
        attended = m1.deposit("attended", [1.0, 0.0])
        control = m1.deposit("control", [0.0, 1.0])
        _save(m1)                                # save-on-add
        m1.signal_attention({attended: 0.5})     # WAL-appended, undrained
        _save(m1)                                # save again, no sleep pass
    time.sleep(0.05)  # let the control row decay measurably
    with Moneta(cfg) as m2:                      # restart
        result = m2.run_sleep_pass()
        a = m2.ecs.get_memory(attended)
        c = m2.ecs.get_memory(control)
        assert a is not None and c is not None
        # utility reflects the attention: min(1, U + 0.5) = 1.0, then Δt=0 decay
        assert a.utility == 1.0 and c.utility < 1.0, (a.utility, c.utility)
        assert a.attended_count == 1
        assert result.attention_updated == 1


def test_D_attention_between_drain_and_pass_snapshot_survives(
    tmp_path: Path,
) -> None:
    """A signal that lands after run_pass drained the log but before
    run_sleep_pass's snapshot_ecs (api.py:455-467). Simulated by wrapping
    the runner; in production this is a concurrent signal_attention."""
    cfg = _cfg(tmp_path, "D")
    with Moneta(cfg) as m1:
        eid = m1.deposit("late", [1.0, 0.0])
        _save(m1)
        orig = m1.consolidation.run_pass

        def run_pass_then_signal(**kw):
            r = orig(**kw)
            m1.signal_attention({eid: 0.5})  # in buffer + WAL, after drain
            return r

        m1.consolidation.run_pass = run_pass_then_signal  # type: ignore[method-assign]
        m1.run_sleep_pass()  # snapshot_ecs then unlinks the WAL
        assert len(m1.attention) == 1  # still undrained in memory
    with Moneta(cfg) as m2:
        m2.run_sleep_pass()
        mem = m2.ecs.get_memory(eid)
        assert mem is not None
        assert mem.attended_count == 1
```

**B:**
1. Deposit `attended` and `control`, then save.
2. `signal_attention({attended: 0.5})`.
3. Save again, with no sleep pass; then close and sleep 0.05 s.
4. Reopen and run the sleep pass. Assert:
   - `a.utility == 1.0` and `c.utility < 1.0`;
   - `a.attended_count == 1`;
   - `result.attention_updated == 1`.

**D:**
1. Deposit, then save.
2. Wrap `consolidation.run_pass` so that it signals after the drain, then run the sleep pass.
3. Assert `len(m1.attention) == 1`.
4. Reopen and run the sleep pass. Assert `attended_count == 1`.

A, A2, C and E stay as characterization tests. **E stays green under R1′:** its hand-written lines carry no `seq`, so the `:218` rule still governs them.

### 4.2 New tests, added in the R1′ PR

All are deterministic unless marked otherwise. Each asserts exact counts or bit-equal utilities, never a bare truthiness (commandment 7, `agent-commandments.md:117-119`).

| ID | Scenario | Assertion |
|---|---|---|
| **F** | Non-prefix drain. Allocate seqs 5 and 6, append 6, drain and apply, then append 5. Save and reopen. | 5 replays and 6 does not; `attended_count` equals 1 per signal. |
| **F2** | Consistent read, one reducer. Monkeypatch `apply_attention` to set a `threading.Event` and then wait on a second event, while a save runs on **another** thread. The test releases the second event after the save has observed a token in `_inflight` at least once. **Never run the save on the reducer's thread mid-apply, and never join the save thread from inside the patched apply.** Both deadlock by design, until the spin bound. | The save retried at least once. The snapshot rows and `wal_applied_seqs` agree: no seq without its row effect, and no effect without its seq. `degraded_saves == 0`. |
| **AB** | Liveness and concurrent reducers. Patch `SEQLOCK_READ_TIMEOUT_S` small. (a) Put a token in `_inflight` with no reducer running. (b) Start a second reducer while a first one is mid-apply (registered). (c) Raise `KeyboardInterrupt` from inside `apply_attention`. (d) **The revision-3 torn-read interleaving, driven deterministically.** Replace `log._inflight` with a `set` subclass whose `add` blocks on an event, on reducer R1's thread only, so that R1 has passed its entry check but is not yet registered. Start R2 on a second thread: it passes the entry check, registers, drains, and blocks inside a patched `apply_attention`. Release R1: it registers, drains and blocks inside `apply_attention`. Release R2 so that it records and finishes while R1 is still mid-apply. Then run a save on a third thread while R1 is still blocked; finally release R1. Same deadlock warning as F2. | (a) The save returns within the bound, writes a **keyless** snapshot that contains a deposit made just before it, logs ERROR, and `degraded_saves == 1`. (b) The second reducer raises `RuntimeError` before draining, and its buffer is intact. (c) Afterwards `_inflight` is empty and the epoch has moved; the next save is keyed. (d) While R1 is in flight, the save never accepts a read. It either times out into a keyless snapshot or, if R1 is released during the spin, writes a keyed snapshot whose rows and `wal_applied_seqs` agree exactly. **No keyed snapshot ever holds an R1 effect without R1's seqs.** Both R1 and R2 raise `RuntimeError("concurrent attention reducer detected")` after `decay_all`. A reopen shows `attended_count` exactly once per signal. |
| **G** | Crash between steps 2 and 3: monkeypatch the compaction to raise `SystemExit`-like after the snapshot `os.replace`. Reopen. | No double apply; pending lines replay once. |
| **G2** | G, then a sleep pass and a save, a reopen, another sleep pass and save, and a final reopen. | `attended_count` incremented exactly once per signal. The WAL holds no lines in `S`. |
| **H** | An rc1-format WAL with no `seq`, under an rc1 snapshot. | It replays by timestamp, identical to rc1. After the first save, every line carries a seq. |
| **H2** | `snapshot.json` stripped of `wal_applied_seqs` (and of `wal_next_seq`), with a seq-bearing WAL holding `k` applied lines and `p` pending lines with `ts ≤ T`, plus one pending line with `ts > T`. **Clock precondition held** (§3.4): every applied line has `ts ≤ T`. | No double apply, **given the precondition**; a WARNING is logged. **Loss characterization:** exactly the `p` pending `ts ≤ T` lines are lost (defect B under a key strip), and the `ts > T` line replays once. The broken-precondition case is covered by Q(d) and N, not by H2. |
| **H3** | Resurrection guard. A keyless snapshot plus seq lines older than `T`. Reopen, save, reopen. | The old lines are never replayed (step 0 dropped them). |
| **I** | Signal, crash, reopen, sleep pass, save, crash, reopen. | `attended_count == 1`, and the WAL is empty after the second save. |
| **J** | Step 0 failure. Open a store whose hydrate leaves `_disposition` non-empty (test E's shape, or an rc1 store). Deposit a new memory, then save with `os.replace` for `wal_tmp` patched to raise `PermissionError`. | The save **returns** and writes a keyless snapshot that contains the new deposit; it logs ERROR, and `degraded_saves == 1`. The WAL bytes are unchanged. A reopen shows no double apply and has the deposit. A second save, unpatched, succeeds: step 0 runs, and a keyed snapshot follows. |
| **K** | Compaction failure: monkeypatch `os.replace` for the WAL to raise `PermissionError` at step 3. | `snapshot_ecs` raises, and the snapshot already holds the deposits. `applied_seqs ⊇ S`. The next save succeeds and writes `S`. A reopen at either point shows no double apply. |
| **L** | Seed from the applied set. Snapshot `wal_applied_seqs=[0..9]`, `wal_next_seq` absent, an empty WAL. Reopen and signal. | The new seq is ≥ 10; after a crash and reopen the signal replays. |
| **M** | Duplicate seq in the WAL. | The first occurrence wins, a WARNING is logged and counted, and it applies exactly once. |
| **N** | Backward clock. Monkeypatch `time.time` in api and durability so the signal timestamps are ahead of the snapshot. | Under a keyed snapshot, seq lines are unaffected. The legacy-line and keyless paths reproduce rc1 semantics, as a characterization. |
| **O** | `wal_append` fails. Three cases: (a) `os.write` raises `OSError` before writing anything; (b) a short write, where the patched write lands half the bytes and returns their count; (c) the write lands all its bytes and then raises. | In each case, `signal_attention` raises `OSError`; `len(m.attention) == 0`; the WAL bytes equal the bytes before the call. A reopen replays nothing from it, and so does a reopen after a further successful append and `close()`. (d) Also patch `os.ftruncate` to fail after (c). The seq is in `_void_seqs`, and after the next save it is in `wal_applied_seqs` and absent from the WAL. (e) Also patch `os.close` to raise `OSError("close failed")` after (a). The exception that escapes is the original write error, not the close's; `_wal_fd is None`; the next append opens a fresh descriptor and succeeds. |
| **P** | Structural. | `attention_log.py` imports no `threading` in any form (`Import` or `ImportFrom`), and `reduce_attention_log` contains no `with` statement and no `.acquire()` call. This extends `test_attention_log.py:174-193`, closing the `import threading` evasion. |
| **Q** | rc1-reader simulation. A frozen helper reproduces rc1's `wal_read` and `hydrate` filter verbatim (`durability.py:151-225`). Run it on an R1′ store: (a) after a clean save; (b) after a crash between steps 2 and 3; (c) after a K-path save then a clean close; (d) as (b), but with `moneta.api.time` patched to run ahead of `durability.py`'s clock. | (a)-(c): no double apply, given the clock precondition. The loss of pending `ts ≤ T` lines is asserted as a characterization. (d): the double apply of the `S` lines is asserted as a characterization of the broken precondition. |
| **R** | Hydrate writes nothing, even when a step-0 disposition is pending and the WAL has a torn tail. | The bytes and mtime of both files are unchanged after construct and close. |
| **U** | Torn tail, **simulating a power-loss tear** of an acknowledged line (§3.3; a kill -9 cannot produce one). Three fragments: (a) a truncated JSON object (undecodable); (b) a complete object cut right after `}`; (c) a complete object cut between `\r` and `\n`. Reopen, signal, then reopen without a save. | (a) The fragment is dropped as undecodable (WARNING). (b) and (c) The fragment parses and replays exactly once. In all three, the new signal replays exactly once, `wal_append` wrote a line terminator before the new line, and the new line is its own raw line. |
| **V** | Stale snapshot tmp and `wal_tmp` (`<wal name>.tmp`) from a prior crash; plus two stores `a.wal` and `b.wal` in one directory, each signalled and saved. | Hydrate ignores the stale files, and the next save overwrites them. The two stores use distinct tmp files (`a.wal.tmp`, `b.wal.tmp`), and each WAL holds only its own lines after both saves. |
| **W** | Windows. A save while a WAL append descriptor is open in-process, plus a second handle opened without share-delete, which makes the replace fail. | The in-process case succeeds. The foreign-handle case at step 3 takes the K path; at step 0 it takes the degraded path (J). |
| **X** | Cold start with no snapshot and a seq WAL. | Every line replays once. |
| **Y** | Path uniqueness. Two `MonetaConfig.ephemeral()` configs with distinct URIs and the same `wal_path`. Separately: the same `snapshot_path`; one's `snapshot_path` equal to the other's `wal_path`; one's `wal_path` equal to the other's WAL tmp path. Also one config whose `snapshot_path` equals its own `wal_path`. | The second `Moneta(...)` raises `MonetaResourceLockedError`. After the first handle closes, the second constructs. A failed construct releases its paths. The self-colliding config raises `ValueError`. |
| **AA** | ECS identity. `m.durability.snapshot_ecs(ECS())` and `start_background(ECS())` on a handle with an attached log. | Each raises `ValueError` and writes nothing: the snapshot and WAL bytes are unchanged. |
| **AC** | Foreign no-seq line at step 3. Append a no-seq line to the WAL between steps 2 and 3. | After step 3 the line carries a fresh seq `∉ S`; a WARNING is counted. A reopen replays it exactly once. |
| **AD** | `close()` versus an in-flight background save. Make a background save block inside step 1 longer than the 5 s join timeout (patched smaller in the test), then call `close()`. | `close()` returns only after that save finishes. The descriptor is closed after the save's last write. No exception escapes. |
| **Z** | Lineage base. A fresh store with no seq information. | The seed is drawn from the random base: it is a multiple of 2^20 and below 2^53. Two fresh stores get different bases (patch `secrets.randbits` for determinism). |
| **T** (stress, marked `slow`) | Threads for a signal loop, a sleep-pass loop and a save loop for N seconds, then close, reopen and drain. The sleep-pass loop pauses between passes for longer than one row build, so step 1 has quiet gaps (§3.1, "Save starvation"). | The total `attended_count` equals the total number of signals, **and `degraded_saves == 0`**. A degraded save reintroduces the rc1 loss and would make the count assertion meaningless, so it fails the test with its own message, not as a count mismatch. |
| **AE** | Trailing newline, pending disposition. A store whose WAL ends in a terminator (`\r\n` on Windows) and whose hydrate leaves `_disposition` non-empty (for example one legacy no-seq line with `ts > T`). Signal once, save, then simulate a crash (no close; reopen from the files). | The post-hydrate line is at raw index `prefix_len`, not `prefix_len-1`, and step 0 copies it unchanged. After the reopen, the new signal and the legacy line each apply exactly once. Also unit-test the reader: `b"a\r\nb\r\n"` gives two raw lines, `b"a\r\nb"` two, and `b"a\rb\n"` one. |
| **AF** | Closed manager. Close a durable handle, then call `signal_attention`, `durability.wal_append`, `durability.snapshot_ecs(m.ecs)` and `durability.start_background(m.ecs)` through the stale reference. Then open a second handle on the same paths, signal and save, and call the stale `signal_attention` again. | Each call raises `ValueError("durability manager is closed")`. The stale handle's buffer stays empty. The stale calls leave the WAL and snapshot bytes unchanged. The second handle's WAL holds only its own seqs, with no duplicates. |
| **AG** | Async exception after the WAL write. Patch `AttentionLog.append` to raise `KeyboardInterrupt` on its first call. | `signal_attention` raises `KeyboardInterrupt`. The line is in the WAL and its seq is in `_void_seqs`. After the next save the seq is in `wal_applied_seqs` and the line is gone, and a reopen replays nothing. A reopen *before* that save replays it once (the stated residual). |
| **AH** | Parse classes (§1.2). (a) Hydrate over a WAL with a blank line, an undecodable line and an entry line. (b) Hydrate over a WAL with one invalid line each: `"not-a-uuid"`, a `null` weight, a non-object `[1]`. (c) A foreign writer appends an undecodable line and an invalid line after hydrate; then save. (d) A line whose `seq` is `true`, `1.5` or `-1`. | (a) Opens; the entry replays once. (b) Construction raises the original `ValueError`, `TypeError` and `TypeError` respectively (P6 unchanged), releases the lock, and changes no file. (c) Step 3 drops both lines (WARNING for undecodable, ERROR for invalid, each counted), and a reopen succeeds. (d) Treated as no seq: judged by timestamp, then given a fresh seq by step 0. |

**Unchanged, still required:**
- SPEC §7 "Exactly-once attention" cases 1 and 2;
- the three-call-site AST check for `decay_all`.

**Matrix:**
- Every test runs with native `=1`, `=0` and absent (SPEC §1).
- The save and reopen tests are already in every row (`harden_plan.md:414`).
- hython rows are PLANNED, awaiting owner coordination.

---

## 5. fsync and rename ordering: explicitly deferred

- **No new fsync.**
  - The snapshot keeps its existing fsync (`durability.py:115`).
  - WAL appends stay unsynced. rc1 flushes to the OS (`durability.py:148-149`); R1′'s `os.write` reaches the OS directly. That is Round 4 F1 (`docs/v7/ROUND4_BRIEF.md:43-44`).
  - The compacted WAL tmp (steps 0 and 3) is flushed, not fsynced.
  - Neither `os.replace` is followed by a directory fsync.
- **Exposure 1, loss, same class as F1.** On an OS crash or power loss after the compaction `os.replace`, NTFS may persist the rename before the data. The new WAL could then be empty or short, losing pending lines. A torn tail from power loss is handled by §2.2's terminator check.
- **Exposure 2, double apply, from rename reordering.**
  - Neither rename is directory-fsynced. On a filesystem without ordered metadata, a power loss could keep save k+1's snapshot rename while reverting save k's compaction rename.
  - The WAL would then still hold the `S_k` lines, under a snapshot keyed `S_{k+1}`. Step 4 of save k removed `S_k` from the set, so `S_{k+1}` excludes them, and the next hydrate replays them: a double apply.
  - **Recorded assumption:** R1′ relies on the filesystem applying metadata operations in order across a power loss. NTFS's metadata journal gives that, so this is unlikely on the target platform. It is not guaranteed on every filesystem.
- **Owner:** the tier is chosen by Round 4 item 5 (`ROUND4_BRIEF.md:101`: "Decide the attention durability tier: per-op fsync, or group commit"). SPEC §0 forbids fsync changes on this branch.
- **Constraints recorded for that decision.**
  - If any fsync tier is adopted, the compaction tmp must be fsynced before `os.replace`. Otherwise compaction becomes the weakest link: it can lose every pending line, where an unsynced append loses only the tail.
  - The tier must state the rename-ordering assumption above. It must either keep it (NTFS-only support) or add a directory fsync after each `os.replace`, where the platform supports one. On Windows, `os.fsync` on a directory is not available through the CRT.

---

## 6. Review path

| # | Gate | Who | Passes when |
|---|---|---|---|
| 1 | **Architect ruling** (this document) | Architect | §1 is recorded: defect, not Trigger 2, conditional on R1′; the keys are not a format bump; `_apply_lock` is rejected under `ARCH:340`. |
| 2 | **Owner gate** (commandment 8, `agent-commandments.md:123-136`: after design, before implementation) | **Joseph Ibrahim** signs | He confirms, or overrides, seven things:<br>1. the ruling;<br>2. the §1.4 behaviour changes: WAL-first ordering, plus the three new raise conditions (shared store paths, including the register update to P11; a mismatched ECS; a closed durability manager);<br>3. the rollback semantics in §3.5, including the loss labels and the "drain, then verify" procedure;<br>4. the deferral of fsync and of directory-fsync to Round 4 item 5, with §5's recorded rename-ordering assumption;<br>5. **what SYNAPSE's embedder-swap rewrite of `snapshot.json` does with unknown keys**: kept (load-modify-dump, as `test_compat.py:629-632` models) or dropped. That is unverifiable from this clone (§1.5). If dropped, H2's loss applies to every swap;<br>6. that SYNAPSE passes only `m.ecs` to `snapshot_ecs` (or `start_background`) and never rebinds it, so §2.4's `ValueError` cannot fire in production;<br>7. that no SYNAPSE deployment points two live handles at one `snapshot_path` or `wal_path` (§2.6).<br>**If he rules Trigger 2 instead:** the Architect drafts the Round 4 brief, Joseph reviews it before it goes to Gemini Deep Think, and the attention and durability subsystem freezes until the round closes (`ARCHITECTURE.md:253`). |
| 3 | **Implementation, separate PR** off a post-C7 base, never on `harden/native-observability` (SPEC §0) | Persistence: `durability.py`. Substrate: `api.py`, `attention_log.py`. | Each reviews the other's hunk. The change crosses roles, so the Architect reviews spec conformance too (commandment 5, `agent-commandments.md:73-89`; `CLAUDE.md` "Do not cross role boundaries without Architect review"). **Production files:** only `durability.py`, `api.py` and `attention_log.py` change. `consolidation.py` and `src/moneta/v5/` are untouched. **Test files that change** (gate 4, Test Engineer): the C6 regression file (B and D xfails removed); the new §4.2 tests; `tests/unit/test_attention_log.py` (P extends the structural check); and **one planned register update**, `tests/v5/test_v1_defects.py` P11, rewritten to assert the new raise (§2.6). That edit is a v1 register test, not v5 source, and the file's own docstring asks for it. P6 is **not** changed: §1.2 keeps rc1's raise on invalid lines. No other existing test changes. |
| 4 | **Tests** | Test Engineer (separate builder and breaker, commandment 7) | Removes the B and D xfails, adds the §4.2 tests, and runs every row of the matrix. Run records include HEAD, the `.pyd` sha256 or shim name, the command and the tail (SPEC §1b). |
| 5 | **Docs, same PR** | Documentarian | Fixes the `durability.py:1-23` docstring and `:119`; replaces `docs/api.md:253-256` (and corrects `:258-259`: with no snapshot, WAL attention still replays per `durability.py:188`). Updates the P11 row of `docs/v5/BLUEPRINT.md:55` to say v1 now refuses a second live handle on the same store paths. Adds to the operator card: the §1.4 behaviour changes, the rollback table (including the R1′ → v5 facade → R1′ row and "cut over both interpreters together"), "drain, then verify, before downgrade", and the meaning of the degraded-save and K-path ERROR lines. Nothing is called fixed until gate 4 is green. |
| 6 | **Acceptance** | Architect, then Joseph | All of the following:<br>- B, D and every §4.2 test pass with native on, off and absent;<br>- an rc1 store reopens (H);<br>- an rc1 reader on an R1′ store never double-applies under the clock precondition (Q a-c);<br>- a step 0 failure still persists a new deposit (J);<br>- baselines hold, restated for the R1′ PR: at its base commit, call the counts `N1` (native 1), `N0` (native 0) and `Na + Sa` (absent: passed + skipped). At `v1.3.0-rc1` these were 405, 405 and 347 + 35, and C5-C7 add their own tests before R1′ branches. The R1′ PR must show `N1 + k`, `N0 + k` and `Na + k_a` passed, where `k` counts the new §4.2 tests plus B and D (moving from xfailed to passed) and `k_a` the subset that runs without the wheel. **P11 counts as passing in its rewritten form,** so it does not change `N`. Any other change in the count of pre-existing tests is a regression;<br>- `test_attention_log.py` structural tests and P are green.<br>Then the owner decides on merge or tag (SPEC §0: no agent merges, pushes or tags). |

---

## Appendix A. Review log

### Revision 2 (historical; HEADs named here are superseded by revision 3)

Each issue was checked against `v1.3.0-rc1` with `git show`, and against clone HEAD `574f5b2`. No issue was rejected outright. Where the fix adopted differs from the one proposed, the reason is given.

| # | Issue | Verified | Disposition |
|---|---|---|---|
| 1 | A failed `wal_append` can leave its line in the WAL (a flush failure keeps it in the text buffer) | **Yes.** rc1 `:147-149` uses a buffered text handle. `close()` at `:263-266` and compaction's close would flush the line later. Also found: the text handle writes `\r\n` on Windows, and `tell()` on a text handle is an opaque cookie, so the "record `tell()`, truncate" fix is fragile in text mode. | **Accepted, unbuffered route.** `os.open` + one `os.write` of an `os.linesep`-terminated line (byte-identical to rc1's lines), `fstat` size before the write, `ftruncate` back on any failure or short write. Added a tombstone backstop for a failed truncate, with its residual stated. §1.2, §1.4, §2.2, §3.3; test O gains the short-write, write-then-raise and truncate-failure cases, and asserts the WAL bytes. |
| 2 | A failed step 0 blocks the snapshot, so deposits stop being saved | **Yes.** `_disposition` is non-empty after any rc1 store, any crash between steps 2 and 3, and any blank, malformed or timestamp-filtered line. rc1 writes the snapshot before its `unlink` can fail (`:112-125`). | **Accepted, degrade option.** Keyless snapshot, WAL untouched, steps 3-4 skipped, `_disposition` and `applied_seqs` kept, ERROR logged, normal return. Stated on top of the proposal: the WAL grows while the failure persists; this path inherits the clock precondition (issue 7b); and the kept disposition stays valid against the keyless `T_new` (proof extended in §3.3). The "persist `T_old` and fingerprints" alternative was rejected: an applied legacy no-seq line can only be matched by a content fingerprint, a much larger format surface. Test J. |
| 3 | The seqlock spin is unbounded | **Yes.** `+= 1` is a read-modify-write; the single-reducer rule is docstring-only (`attention_log.py:30-36`); the first increment sat outside the `try`; `stop_background` joins with a 5 s timeout (`:257`). | **Accepted, all four fixes:** absolute assignment inside the `try` with `finally: g+2`; best-effort reentrancy detection (entry parity check plus token), stated as unable to close the check-to-set gap without a CAS; a bounded save spin; `close()` takes `_save_lock` (lock order preserved, §3.1). **Adjusted:** on timeout the save degrades (as in issue 2) instead of raising, so a stuck reducer cannot stop deposits being saved. F2's note is in §4.2; liveness is test AB; `close()` is test AD. |
| 4 | §1.5's R2 argument applies equally to R1′; H2 does not check loss | **Yes.** `test_compat.py:629-632` and `:654-656` do load-modify-dump, which preserves unknown keys. A key-stripping rewrite sends R1′ to the `:218` rule. | **Accepted.** SYNAPSE's real rewrite cannot be inspected from this clone, and SPEC §0 forbids touching SYNAPSE. It is now owner-gate item 5 (§6). §1.5 point 2 is now marked neutral; the format bump (point 1) is the deciding reason. H2 asserts the exact loss count. |
| 5 | "No collision within a lineage" rests on the URI registry, not the files | **Yes.** `MonetaConfig` (`api.py:125-133`) takes the paths independently of the URI; `ephemeral()` mints a fresh URI (`:154-157`); `_ACTIVE_URIS` holds only URIs (`:169, 198-204`). | **Accepted, enforce.** A sibling `_ACTIVE_STORE_PATHS` holding normcased `realpath`s of both paths, raising `MonetaResourceLockedError`. Hard links are left as a stated precondition. Ruled not an API change (§1.4). Test Y; owner-gate item 7. |
| 6 | `snapshot_ecs(ecs)` assumes the reducer's ECS | **Yes.** The seqlock pairs `log.applied_seqs` with whatever rows are passed. The callers found are `api.py:467` (`self.ecs`, assigned only in `__init__` at `:229, 249`), `test_compat.py:66, 549, 559, 570, 587, 626`, `bench_v5_vs_v1.py:61`. All pass `m.ecs`. v5's `snapshot_ecs()` at `v5/compat.py:852, 886` is v5's own object. | **Accepted, raise.** Attach `(log, ecs)` together; a mismatch raises `ValueError` before any write. The same check applies to `start_background`. The proposal's "or take the rc1 path" was not chosen: rc1's unlink loses the attached log's pending lines silently. Test AA; owner-gate item 6. |
| 7 | The clock claims are too broad | **Yes**, all three parts. (a) Keyless snapshots judge R1′ seq lines by timestamp. (b) `api.py:424` and `durability.py:102` stamp from different module bindings; the load harness patches only `moneta.api.time` (`synthetic_session.py:58-62`). (c) The K path keeps the `S` lines in the WAL for the whole failure period. | **Accepted.** §3.4 narrowed and lists every keyless case. The precondition is now "signal clock ≤ snapshot clock" everywhere: §3.3, §3.5, Q, gate 6. A K-path row and a degraded-save row were added to §3.5. Q gains cases (c) and (d). |
| 8 | The rollback table calls lossy sequences "safe" | **Yes.** Both rows lose R1′-pending `ts ≤ T` lines. | **Accepted.** Both rows are relabelled. "Drain before downgrade" became "drain, then verify": the WAL must be empty after `close()`, or the switch does not happen. |
| 9 | A torn WAL tail swallows the next acknowledged signal | **Yes.** rc1 `:147-148` appends onto whatever is there, and hydrate would classify the merged line as malformed. | **Accepted.** On first open of the append descriptor (and after every step 0 or 3 reopen), under `_lock`, write a line terminator if the last byte is not `\n`. Hydrate still writes nothing (R covers it). Test U. |
| 10 | Step 3 "keeps" foreign no-seq lines that are lost anyway | **Yes.** A kept no-seq line is judged `ts > T_new` at the next hydrate and dropped; step 0 then deletes it. | **Accepted, assign a seq.** Step 3 already holds `_lock`, so it allocates from `_next_seq`. The line is in no row, so replaying it once at the next reopen is correct. Test AC. |
| 11 | §5 lists only loss on power failure; doubles are possible too | **Yes**, by the stated mechanism. Neither `os.replace` is directory-fsynced (`:116`, and the new steps 0 and 3). | **Accepted.** §5 gains exposure 2 and the recorded ordered-metadata assumption, and the Round 4 item 5 constraint now covers it. Also noted: a Windows directory fsync is not available through the CRT. |
| 12 | Claims about current code: nits | **Yes.** HEAD `durability.py:181` is `def hydrate(self)`; `durability.py` is byte-unchanged from the tag. rc1 also raises `TypeError` and `ValueError` while parsing. The seed rule yielded 0 while test Z was required. | **Accepted.** §2.5 step 10 now says the keyword "will add (SPEC §2)"; the old text also cited SPEC §3 wrongly. §1.2 lists all three exception types. The random base is normative in §2.5 step 5, used only when all three seq sources are empty, so L still yields ≥ 10. **Also fixed, not raised by the review:** the citation base named clone HEAD `ac9662c`, but HEAD is now `574f5b2` (C1 fix). `git diff --stat` confirms the four cited source files are still unchanged; §0's run records stay at `ac9662c`, where they ran. |

**Held up under review, unchanged in substance:** WAL-first plus seq membership for paths B and D; the step 3 / step 4 ordering; the "crash between steps 2 and 3" row; H3's resurrection case; the step 0 semantics proof, now extended to the degraded case.

### Revision 3 (freshness pass)

| # | Issue | Verified | Disposition |
|---|---|---|---|
| 13 | The citation base named clone HEAD `574f5b2`; HEAD is now `2252ea8` (a second C1 fix) | **Yes.** `git diff --stat v1.3.0-rc1 HEAD -- src tests` still leaves `durability.py`, `attention_log.py`, `api.py` and `consolidation.py` untouched. | Header updated. Every load-bearing citation was re-read at `v1.3.0-rc1` this revision: `durability.py:1-266`; `attention_log.py:1-132`; `api.py:120-280, 295-320, 395-470`; `consolidation.py:145-190`; `ARCHITECTURE.md:100-115, 245-256, 336-342`; `MONETA.md:288-294, 426-432`; `docs/api.md:222-262`; `test_attention_log.py:1-14, 170-195`; `test_compat.py:1-58, 60-68, 625-634, 650-658`; `v5/compat.py:640-690, 810-825, 1000-1030`; `synthetic_session.py:55-66`; `ROUND4_BRIEF.md:40-46, 99-103`; `agent-commandments.md:70-90, 115-137`; `SYNAPSE_COMPAT.md:30-35, 49-53`; `ecs.py:230-250`. No line moved. |
| 14 | §0's evidence predated the current HEAD and had no absent row | **Yes.** | B and D were re-run at `2252ea8` in three rows (native 0, native 1, absent shim): 4 passed, 2 failed in each. §0 now cites those records. |
| 15 | `test_compat.py:66, 549…` were cited as v1 callers of `snapshot_ecs` | **Yes, a misattribution.** `test_compat.py:21` imports `Moneta` from `moneta.v5.compat`, so `m.durability` is `_DurabilityView` (`v5/compat.py:648-672`), whose `snapshot_ecs(ecs=None)` ignores its argument. | §0 root cause 4, §1.5 point 2 and §2.4's precondition now say so. The in-tree v1 callers are only `api.py:467` and `bench_v5_vs_v1.py:61`. Owner-gate item 6 is unchanged and now carries more weight. A scope note in the header says R1′ does not touch the v5 facade. |
| 16 | §2.4 did not state the write mode of `wal.tmp` | **Yes.** A text-mode write on Windows would turn kept `\r\n` lines into `\r\r\n`. | Added the normative "tmp write mode" paragraph: binary read and write, raw bytes for kept lines, `os.linesep` for re-serialized ones. |

### Revision 4 (review fixes)

Each issue was checked against `v1.3.0-rc1` with `git show`. No issue was rejected. Where the adopted fix differs from the one proposed, the reason is given.

| # | Issue | Verified | Disposition |
|---|---|---|---|
| 1 | **High.** The parity seqlock accepts a torn read when two reducers overlap, though the doc said "a degraded save, never a hang" | **Yes.** Both reducers read `g=0` and both store 1; the one that finishes first stores 2, while the other is still inside `apply_attention`. The save then sees `g=2` before and after, and accepts rows holding part of R1's effects with an `S` that lacks R1's seqs. R1's own `finally` also stores 2, so nothing changes. The token check made only R1 raise, after `decay_all`, by which time the snapshot may be on disk. The window covers the drain and the O(n) `aggregate`, so it is wide. | **Accepted.** `_apply_gen` and `_reducer_token` are replaced by `_inflight: set[object]` and `_apply_epoch: object` (§1.3, §2.1, §2.3, §2.4 step 1, §3.1). **Adjusted from the proposal:** a `set` with `add`/`discard` instead of a list with `append`/`remove`, because `discard` cannot raise in the `finally`; the `add` sits inside the `try`, so an async exception before it strands no token; and the end-of-apply epoch is stored before the discard. The save accepts only with `_inflight` empty before and after the row build and `_apply_epoch is e1`; both checks are needed. The reducer's own detection now catches the overlap from both sides (epoch moved, or another token present), but it is diagnostic only. `ARCHITECTURE.md:340` still holds: no mutex, no CAS. Test AB(d) drives the exact interleaving. A stranded token (an async exception inside the `finally`) is a stated residual whose outcome is degraded saves, never a torn one. |
| 2 | **High.** §2.6 path uniqueness breaks `test_v1_p11_two_uris_on_one_snapshot_lose_writes`, against gate 3 and gate 6 | **Yes.** `test_v1_defects.py:308-320` keeps `a` and `b` live on `shared.json`/`shared.wal`; under §2.6, `b = Moneta(...)` raises. The register docstring (`:5-7`) says such a test "fails, and the register must be updated". | **Accepted.** §2.6 now lists every hit of the grep and names P11 as a planned register rewrite, with the new body. Gate 3 lists the test files that change; gate 6 restates the baselines as base-commit counts plus the new tests, with P11 passing in its rewritten form. Gate 5 adds the `docs/v5/BLUEPRINT.md:55` P11 row. P6 was checked too; see issue 3. |
| 3 | **Medium.** "Malformed" is undefined for hydrate, and one choice flips P6 | **Yes.** rc1 raises on `KeyError`, `TypeError` and `ValueError` lines; P6 (`test_v1_defects.py:143-165`) asserts `pytest.raises(ValueError)` for `"not-a-uuid"`. | **Accepted.** §1.2 now has one normative grammar and parse-class table (blank, undecodable, invalid, entry) used by hydrate, step 0 and step 3. Hydrate raises the original exception on an invalid line, as rc1 does, so **P6 is unchanged**. "Malformed" now means only undecodable (`JSONDecodeError`). Step 3 drops invalid lines (ERROR, counted) instead of copying them: no reader can apply them, and rc1's save also removes them by unlinking. Copying them would leave a store that no longer opens after a save. A non-int, bool or out-of-range `seq` is treated as no seq. Test AH. |
| 4 | **Medium.** Splitting on `\n` and counting blank lines makes a phantom trailing line, so step 0 drops the first post-hydrate append | **Yes,** and it is worse than stated. A WAL ending in a terminator is the normal case, so the phantom blank made `_disposition` non-empty on **every** reopen, and step 0 then dropped the first append every time. | **Accepted.** §1.2 defines a raw line as a maximal run ending in `\n`, plus a final non-empty unterminated run. A trailing empty piece is never a line. `split(b"\n")`, `splitlines()` and text-mode iteration are banned. §2.5 step 2 explains the failure; the §3.3 proof now states index stability. Test AE adds the append, save, crash and reopen sequence, plus reader unit cases. |
| 5 | **Medium.** The fixed name `wal.tmp` can clobber another store in the same directory | **Yes.** rc1 derives the snapshot tmp from the file name (`durability.py:109-111`); a fixed `wal.tmp` would be shared by `a.wal` and `b.wal`. | **Accepted.** `wal_tmp = wal_path.with_name(wal_path.name + ".tmp")` is normative (§2.4 "tmp paths"), and every `wal.tmp` mention now says `wal_tmp`. Both derived tmp paths are added to `_ACTIVE_STORE_PATHS`, and a config whose own four paths collide raises `ValueError` (§1.4, §2.6). Tests V and Y extended. |
| 6 | **Medium.** A closed manager still appends, through the lazy reopen | **Yes.** rc1 `wal_append` reopens when `_wal_fp is None` (`durability.py:145-147`); rc1 `Moneta.close()` sets `_closed` but no op checks it (`api.py:308-310`), and it releases the URI (`:317`). | **Accepted, extended.** `_closed` is set in `DurabilityManager.close()` under `_lock`. `wal_append` **and** `snapshot_ecs` and `start_background` then raise `ValueError("durability manager is closed")`: a stale save could otherwise compact a WAL another handle owns. This is the third §1.4 raise condition and is in owner-gate item 2. `ValueError` follows the `io` convention and is already raised by `signal_attention` for bad weights (P5, `test_v1_defects.py:135`). Test AF. |
| 7 | **Medium.** §3.5 has no row for R1′ → v5 facade → R1′ | **Yes.** The facade overwrites `snapshot.json` with a keyless export (`v5/compat.py:264`; `SYNAPSE_COMPAT.md:33`) and preserves `wal.log` byte-for-byte (`test_compat.py:151`). The facade registers only its URI (`v5/compat.py:695-699`), so R1′'s path registry does not see it. | **Accepted.** New §3.5 row: loses v5-only state, double-applies when the v5 clock is behind the line timestamps, and R1′'s first save rewrites v5's migration input, after which v5 refuses the store (`SYNAPSE_COMPAT.md:33, 51`). "Cut over both interpreters together" is enforced by v5's refusal, not by R1′. §2.6 gains a matching residual. |
| 8 | **Low.** The torn-tail crash row gives the wrong reason | **Yes.** A kill -9 cannot tear one `os.write` already handed to the OS, so a tear is a power-loss artifact of an acknowledged line. A tear after `}` or between `\r` and `\n` parses. | **Accepted.** The row now reads "acceptable": undecodable fragments are an F1-class loss, and parseable ones replay once, correctly. Test U is reframed as a power-loss simulation, with the two parseable cases added. §2.2 notes the `\r\r\n` repair shape. |
| 9 | **Low.** An async exception between `wal_append` and the buffer append is a phantom apply | **Yes.** §1.4 covered only `wal_append` raising, and the crash row "yes, once" hid it. | **Accepted, tombstone route,** with residuals stated. The buffer append is wrapped in `try/except BaseException: durability.void_seq(seq); raise` (§2.2). The residuals are an exception before the `try` or inside the handler, and an exception after the append completed, which tombstones a buffered signal (rc1-class in-memory phantom; the durable state stays consistent). §1.4 table, §3.3 rows split into the process-crash and async-exception cases. Test AG. |
| 10 | **Low.** "Seq order is therefore file order" is false | **Yes.** Hydrate step 6 and step 3 assign fresh high seqs to earlier lines. | **Accepted.** The claim is deleted. §2.1 now says that nothing depends on it: every rule uses set membership, and F pins a non-prefix order. |
| 11 | **Low.** Rows and tests imply unproven safety | **Yes,** all four parts. | **Accepted.** (a) H2 states the clock precondition and points the broken case to Q(d) and N. (b) The §3.1 parenthetical is corrected: a line read by compaction may be in `S`, legitimately, and the handling is by membership either way. (c) §2.4's caller list now says the exclusion is `src/moneta/v5/` and the facade tests; `scripts/v5/bench_v5_vs_v1.py` drives a v1 handle and stays in. (d) §3.1 gains "Save starvation"; the `degraded_saves` counter is added (§2.4, degraded-save step 4, so both entries count; J asserts it too); T leaves quiet gaps and asserts `degraded_saves == 0`, and F2 and AB assert it too. |
| 12 | **Low.** An unguarded `os.close` in the `wal_append` failure path can replace the original error and leave `_wal_fd` set | **Yes,** as written in revision 3. | **Accepted.** The close is guarded with `except OSError: pass`, and `_wal_fd = None` sits in a `finally`; the bare `raise` re-raises the original. Test O(e). |

**Held up under review, unchanged in substance:** WAL-first plus seq membership for paths B and D; step 0 and its semantics proof (now with the grammar and index-stability lemma); the step 3 / step 4 ordering; the degraded-save path; the K path; the §1.3 rejection of `_apply_lock`.

**Process note, revision 4.** Design-only. No test was run for this revision, so it adds no run records; the §0 records from revision 3 still stand, because no file under `src/moneta/{durability,attention_log,api,consolidation}.py` has changed since. Nothing in the clone was edited, staged or committed by this revision. **The clone's working tree was not clean when it was inspected:** `git status --porcelain` at HEAD `2252ea8` showed modified `src/moneta/_native.py`, `src/moneta/ecs.py`, `src/moneta/vector_index.py` and `tests/unit/test_native_scan_conformance.py`, plus untracked `tests/unit/native_fakes.py` and `tests/unit/test_native_selection.py`. That is another workflow step's work in progress, which this revision did not touch. None of the four source files cited above is among them, and every citation here is at `v1.3.0-rc1` anyway. Citations re-read at `v1.3.0-rc1` for this revision: `attention_log.py:60-84, 120-132`; `api.py:296-320, 410-432`; `durability.py:105-175, 176-226, 250-266`; `tests/v5/test_v1_defects.py:1-40, 45-62, 135-170, 300-325`; `tests/v5/test_compat.py:140-160, 268-282`; `tests/v5/test_half_life.py:258-285`; `tests/test_twin_substrate.py:36-60`; `tests/integration/test_durability_roundtrip.py` (every `Moneta(` and `close`); `scripts/v5/bench_v5_vs_v1.py:45-72`; `v5/compat.py:255-272, 695-699, 812, 859`; `docs/v5/SYNAPSE_COMPAT.md:28-55`; `docs/v5/BLUEPRINT.md:50, 55`; `ARCHITECTURE.md:272`.

**Process note.** Revisions 2 and 3 are design-only. Nothing in the clone was edited, and SYNAPSE and the live checkout were not touched. Revision 3 ran only the B/D regression file from `$S/durab` against `$W/src`, in three rows, each recorded under `$S/runs/R1design-r3-BD-*.txt`. `git status --porcelain` in the clone was empty afterwards. Every citation added in this revision was re-read at `v1.3.0-rc1`: `api.py:125-133, 154-157, 169, 198-204, 229, 249, 273-275, 300-317, 424-431, 467`; `durability.py:102, 112-125, 144-149, 181, 257, 261-266`; `test_compat.py:66, 549, 551, 626-632, 651-656`; `synthetic_session.py:58-65`; `bench_v5_vs_v1.py:61`; `v5/compat.py:852, 886`.
