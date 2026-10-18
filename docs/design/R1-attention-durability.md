# R1: attention durability across snapshot and restart

**Status:** Architect design, revision 6: implemented. Revision 6 records what shipped: the gate 2 overrides, the gate 3 ruling on the record order, the reducer try window, three wording deltas from the Architect review, and the step 0 fix and doc nits from the Persistence and Substrate cross-review (Appendix A, revision 6). The Architect signed it off on 2026-10-18 (SIGNED_OFF, rows 9 to 12 included), and the owner accepted the rc2 content (gate 6) the same day. The sign-off's one fix and six nits, and one nit from the re-review of `711d7fb` and `3da0053`, are applied after the sign-off as the revision 6 erratum (Appendix A). Implemented by the R1′ PR, branched from `a4f2b0b`: `b7041df` (production), `b122a3a` (tests), `14f060f` (docstrings and docs), `075eb64` (F1 fsync), `6040903` (the reducer try window, test AB(c2)), `6db69c7` (step 0 and step 4 wording), `711d7fb` (step 0 applies the disposition only to the WAL hydrate read, test AL) and `3da0053` (docstrings: the owner by role, the fsync double-fault residual). Revision 6 text: `b460e78` (as implemented, local paths scrubbed) and `1c42f87` (cross-review rows 9 to 12); its erratum is in the rc2 recut. Revision 5 was the design review: the attention log is shown to lose late entries, so the §1.1 ruling is re-argued and goes to the owner as a Trigger 2 question; the reducer takes one snapshot of the swapped list; reducer detection is log-only; snapshot-key type rules; `wal_append` open and failure paths; absent-WAL handling; background-thread shutdown.
**Destination in the repo:** `docs/design/R1-attention-durability.md` (the path the B/D xfail reason strings name).
**Author role:** Architect (MONETA.md §6; CLAUDE.md role table: Architect owns spec-conformance review and §9 briefs).
**Date:** 2026-10-16.

**Citation base (revision 6).** The R1′ PR branched from `a4f2b0b`, not `e7325bb`. The re-check below, `git diff --stat e7325bb a4f2b0b -- src/moneta docs/api.md tests/v5/test_v1_defects.py tests/integration/test_attention_snapshot_regression.py`, lists only `src/moneta/ecs.py`, whose one hunk starts at `:378`, below every cited `ecs.py` line. So `ecs.py:289-322`, `:312-322` and `:328` hold at `a4f2b0b`, as does every other anchor in those paths. Anchors in other files were not re-read for revision 6. The line numbers describe the code R1′ replaced; for the shipped code, read the commits in the status line.

**Citation base (revision 5).** Every `path:line` below is at clone HEAD `e7325bb` (branch `harden/native-observability`, post-C7), read with `git -C <clone> show HEAD:<path>`. That is the base the R1′ implementation PR branches from (§6 gate 3). If the PR branches from a later commit, re-run `git diff --stat e7325bb <base> -- src/moneta docs/api.md tests/v5/test_v1_defects.py tests/integration/test_attention_snapshot_regression.py` and re-read every anchor in a file that moved.
- **Unchanged since `v1.3.0-rc1`** (`c33bbd9`), so rc1 and HEAD anchors coincide: `attention_log.py`, `consolidation.py`, `src/moneta/v5/`, `ARCHITECTURE.md`, `MONETA.md`, `docs/v5/`, `scripts/v5/`, `docs/agent-commandments.md`, `docs/v7/ROUND4_BRIEF.md`, `tests/unit/test_attention_log.py`, `tests/v5/test_compat.py`, `tests/load/synthetic_session.py`, `tests/integration/test_durability_roundtrip.py`, `tests/test_twin_substrate.py`.
- **Changed since rc1:**
  - `durability.py` (+11 lines, C3: `hydrate(self, native=None, *, _source=None)` at `:181-186`). Lines up to `:180` are unchanged; later rc1 lines move by +11.
  - `api.py` (+146, C3).
  - `ecs.py` (C1/C3): `apply_attention` is now `:289-322`, with its row loop at `:312-322`; `decay_all` is at `:328`.
  - `docs/api.md` (+158, C7): the "WAL-covered" row is now `:351`; hydrate steps 3 and 4 (the WAL replay rule) are at `:378-381`; the C7 defect note is `:383-393`; the no-snapshot sentence is `:395-396`.
  - `tests/v5/test_v1_defects.py` (+5 after `:62`, C3): P6 is `:148-170`, P11 is `:313-325`.
  - `tests/integration/test_attention_snapshot_regression.py` is new (C6).
- **Moved `api.py` anchors** (rc1 → HEAD): config path fields `:132-133` → `:143-144`; `ephemeral()` `:144-157` → `:167-180`; `_ACTIVE_URIS` `:169` → `:196`; `class Moneta` `:177` → `:204`; URI check `:198-204` → `:242-248`; `_closed = True` "until construction completes" (new) `:250`; `DurabilityManager(` `:225` → `:277`; the hydrate call `:229` → `:281-283`; the replay loop `:238-241` → `:298-301`; the non-durable `self.ecs = ECS(...)` `:249` → `:309`; the partial-init handler `:273-275` → `:358-367` (it now also calls `self.durability.close()`); `close()` `:300-317` → `:407-428` (`_ACTIVE_URIS.discard` `:317` → `:424`); `decay_all` in `query` `:401` → `:515`; `signal_attention` `:413-431` → `:527-546` (`now` `:424` → `:538`, buffer append `:427` → `:541`, `wal_append` `:429-431` → `:542-545`); `run_sleep_pass` `:455-467` → `:562-582` (`snapshot_ecs` `:467` → `:581`).
- **Moved `durability.py` anchors** (rc1 → HEAD): no-snapshot branch `:183-188` → `:194-199`; snapshot load `:190-215` → `:201-226` (`snapshot_version` check `:193-199` → `:204-210`; `snapshot_created_at`/`rows` reads `:202-203` → `:213-214`); replay filter `:218` → `:229`; `_run` loop `:239-243` → `:250-254`; join `:257` → `:268`; `_stop_event = None` `:259` → `:270`; `close()` `:261-266` → `:272-277`.
- Where the text describes **rc1 behaviour** (the released tag), it says "rc1"; the cited line is still the HEAD line, which carries the same code unless the text says otherwise.

**Scope of the defect.** B and D concern the v1 handle `moneta.Moneta` (`api.py:204`), which `moneta/__init__.py` exports. The v5 facade `moneta.v5.compat.Moneta` (`v5/compat.py:683`) has its own `_DurabilityView` (`v5/compat.py:648-672`), whose `snapshot_ecs(ecs=None)` ignores its argument and refreshes a derived export of the v5 journal. That view neither writes nor unlinks a v1 WAL, so R1′ does not touch it. Its only contact with a v1 WAL is the one-time migration read (`v5/compat.py:1004-1028`), covered in §3.5. Some citations in `harden_plan.md` are stale. For example, Round 4 F1 cites `api.py:416-418` as claiming an fsync, but the `signal_attention` docstring (`api.py:530-535`) already says "no fsync". This document cites only lines it re-read.

**A third loss path, L (late landing), found in review (revision 5).** Independently of the persistence layer, the in-memory attention log can lose an entry that lands in a list the reducer has already swapped out (§1.1 ground 3, with the probe record). It is a v1 defect at rc1 and at HEAD. R1′ must not turn it into a silent durable loss (§2.3).

**Scope fence.** SPEC §0 forbids any WAL, snapshot or fsync change on this branch. C6 adds only the regression tests, with B and D marked `xfail(strict=True)`. R1′ (below) lands in a **separate PR**, after the gate in §6.

---

## 0. Evidence: the defect reproduces on this clone

Run records (revision 5, at HEAD `e7325bb0e253de57c0f12c71b4282499e83dcc15`; in-tree C6 file `tests/integration/test_attention_snapshot_regression.py`, where B and D carry `xfail(strict=True, raises=AssertionError)`):
- `<scratch>/harden/runs/R1design-r5-BD-native0.txt`
- `<scratch>/harden/runs/R1design-r5-BD-native1.txt`
- `<scratch>/harden/runs/R1design-r5-BD-absent.txt`

`<scratch>` stands for the author's local scratch directory (revision 6 replaced the full local path); the run records are not published.

Earlier records, same result: at `2252ea8` against the `$S/durab` copy (`…/runs/R1design-r3-BD-{native0,native1,absent}.txt`: 4 passed, 2 failed), and at `ac9662c` (`…/runs/R1design-BD-native0.txt`, `…/runs/R1design-BD-native1.txt`).

| Row | HEAD | Identity | Result |
|---|---|---|---|
| `MONETA_NATIVE=0`, `$S/wheel` | `e7325bb0e253de57c0f12c71b4282499e83dcc15` | `.pyd` sha256 `ec6d7f0c35c5b345f983f4aa80cfea086f3aca454e9cd74a58b6208227b02833` | **4 passed (A, A2, C, E), 2 xfailed (B, D)** |
| `MONETA_NATIVE=1`, `$S/wheel` | `e7325bb…` | same `.pyd` | **4 passed (A, A2, C, E), 2 xfailed (B, D)** |
| env unset, `$S/shim_absent` | `e7325bb…` | shim `shim_absent` | **4 passed (A, A2, C, E), 2 xfailed (B, D)** |

- Interpreter: Python 3.14.2. Command per record: `PYTHONDONTWRITEBYTECODE=1 [MONETA_NATIVE=<m>] MONETA_QUAL_REPORT=… PYTHONPATH="$W/src;<wheel-or-shim>" python -m pytest tests/integration/test_attention_snapshot_regression.py -q -p no:cacheprovider -rsx`. `git status --porcelain` in the clone was empty afterwards.
- The native1 record's verdict line reads `NATIVE NOT QUALIFIED` (native collected 0 < expected 71, no qualification tests, scan `native_calls=0`). That is the C5 verdict for a single-file run that collects no `native`-marked test. It is not a regression, and it says nothing about B or D.
- The defect is backend-independent, as expected: neither seam touches the WAL or snapshot.
- Strict xfail with `raises=AssertionError` means each of B and D failed on an assertion, not on an error. The `$S/durab` runs at `2252ea8` show which ones:
  - **B** fails because `attended_count == 0` after the restart and the utility decayed like the control row.
  - **D** fails with `assert 0 == 1` (in-tree file `:163`).

**Path L evidence (revision 5).** Probe `<scratch>/harden/probes/r1_append_race.py`, record `<scratch>/harden/runs/R1review-append-race-probe.txt` (HEAD `e7325bb`, shim `shim_absent`, Python 3.14.2, read-only; `attention_log.py` is byte-identical to rc1).
- **Part 1, deterministic.** `AttentionEntry` is patched to block on the appender thread. A `drain()` runs while the appender is blocked, then the appender is released. Result `n_at_drain=0 drained_after=1 buffer_after=0`: the entry landed in the list that `drain()` had already returned, and the live buffer is empty.
- **Part 2, unpatched code, real threads, `sys.setswitchinterval(1e-6)`.** 613 of 200 000 appends landed in a list after it had been drained. That count is a lower bound: the probe counts only landings before its next drain.

### Root cause (verified)

1. **The snapshot holds only ECS rows.** `durability.py:85-107` writes `snapshot_version`, `snapshot_created_at` and `rows`. It holds nothing of the undrained `AttentionLog._buffer` (`attention_log.py:69`).
2. **Every `snapshot_ecs` deletes the whole WAL** (`durability.py:119-125`). The comment at `:119` says "everything before `now` is captured in the snapshot". That is false for undrained entries.
3. **Hydrate replays only lines with `timestamp > snapshot_created_at`** (`durability.py:228-229`). So even a surviving undrained line would be filtered out, because it is older than the snapshot that should have preserved it. Test E pins this.
4. **Path B.** A bare save drops undrained signals. The save is `m.durability.snapshot_ecs(m.ecs)`, the call shape of SYNAPSE's save. The shape is documented by the comment at `tests/v5/test_compat.py:66`; that test runs it against the v5 facade, whereas the regression test runs it against a v1 handle, where it reaches `durability.py:83`.
5. **Path D.** The sleep pass drains at `consolidation.py:154-156` and saves at `api.py:578-581`. A signal that arrives between the two lands in the new buffer (`attention_log.py:82`) and the WAL (`api.py:541-545`). The save then unlinks its WAL line.
6. **Path L (late landing, revision 5).** `attention_log.py:73` is `self._buffer.append(AttentionEntry(entity_id, weight, timestamp))`. Python evaluates `self._buffer.append` (capturing the current list) **before** it builds the argument. Building an `AttentionEntry` runs the named tuple's Python-level `__new__`, where the GIL can switch. If the reducer's swap (`attention_log.py:82`) runs in that gap, the entry lands in the swapped-out list after `reduce_attention_log` has read it (`attention_log.py:127-128`), so no pass ever applies it. In rc1 the WAL line survives only until the next save: `run_sleep_pass` saves right after the pass (`api.py:581`), which unlinks the WAL. So the entry is lost in memory and then on disk too, unless the process crashes before that save. The probe above reproduces the race.

---

## 1. Architect ruling

### 1.1 Verdict (Architect recommendation; the owner decides): implementation defect, absorbed by the pattern, not a MONETA.md §9 Trigger 2

**Gate 2 ruled this absorbed on 2026-10-18 (Appendix A row 3; erratum E5).**

**Revision 5 changes the standing of this verdict.** Revisions 1 to 4 rested partly on the claim that the log itself "loses nothing". That claim is false (path L, §0). The first clause of Trigger 2 names "the append-only attention log has a failure mode not anticipated in Round 2" (`MONETA.md:430`, `ARCHITECTURE.md:250`), almost word for word. So the Architect does not self-certify this ruling. It is argued again below from the corrected facts, and it goes to the owner as owner-gate item 1 (§6), with the probe record. If the owner rules Trigger 2, the protocol in §6 gate 2 applies.

The recommendation holds **only for the amended design R1′** (§2), including the §2.3 single-snapshot reducer. The plan's original R1, with `_apply_lock` inside the reducer, would itself be a Trigger 2 (§1.3).

**Grounds**

1. **The code contradicts its own stated design.** It does not contradict a locked clause.
   - `durability.py:15-18`: "every `signal_attention` append is also written to a write-ahead log … at snapshot time the WAL is truncated since its entries are captured."
   - `durability.py:20-23`: hydrate skips pre-snapshot entries because they are "already captured".
   - `docs/api.md:378-381` (hydrate steps 3 and 4) repeats the premise (C7 added the defect note at `:383-393`). The premise is false for undrained entries, so paths B and D live in the implementation of a stated design.
2. **The contract being restored is explicit.**
   - `MONETA.md:292`: "Durability layer must survive a kill -9 with no more than the last 30 seconds of volatile state lost."
   - `docs/api.md:351` says `signal_attention` is "WAL-covered".
   - Path B loses a signal of **any age** that is still undrained when any save happens. That is outside the 30-second window. It is a bug against a stated contract.
3. **Trigger 2: the facts, corrected in revision 5.**
   - **The log does have a failure mode.** Revisions 1 to 4 said `append` (`attention_log.py:71-73`) and the swap-and-drain (`:75-83`) "lose nothing", and the rc1 module docstring argues the same ("Entries cannot be lost", `attention_log.py:11-19`). Both are false. `list.append` is atomic, but the list it appends to is captured before the `AttentionEntry` is built, and that construction is Python-level code where the GIL can switch. An entry can therefore land in a list the reducer has already swapped out and read (path L, §0 root cause 6; probe part 1 deterministic, part 2 observed 613 times in 200 000 appends). rc1 never applies such an entry, and its next save unlinks the line.
   - **The trigger text matches.** `ARCHITECTURE.md:250` and `MONETA.md:430` name "the append-only attention log has a failure mode not anticipated in Round 2". Round 2 did not anticipate it: `docs/rounds/round-2.md` never analyses the swap, the drain or the GIL. The "cannot be lost" argument is Phase 1 implementation documentation, not a Round 2 or a locked clause. The same lines say "Python debugging and implementation bugs are not triggers." Both readings are available, which is why this goes to the owner.
   - **The deciding test is `ARCHITECTURE.md:112`:** Trigger 2 fires "if a failure mode is found that **the append-log pattern cannot absorb**." The Architect's reading is that the pattern absorbs it:
     - The failure is in two implementation details, not in the pattern: `append` loads the list before it builds the entry, and the reducer works on the swapped-out list object itself instead of one snapshot of it (rc1 iterates it once and drops it; R1′ revision 4 iterated it twice). Neither is required by "append-only log, reduced at sleep pass" (`ARCHITECTURE.md:108-110`).
     - The §2.3 fix stays inside the pattern. It keeps one swap and one reducer, adds no lock, no CAS and no per-entity primitive, and keeps the reducer lock-free (`ARCHITECTURE.md:112, 340`).
     - Under the fix, a late entry is reduced at the next pass, or, in the worst case, replayed on the next reopen (its seq is never recorded as applied, so its WAL line survives every save). Every entry is still applied exactly once by a single reducer (concurrent reducers stay unsupported, §1.3). That is the "eventually consistent" log that `ARCHITECTURE.md:110` commits to. The guarantee does get weaker: "eventually" can now mean "at the next reopen" for a worst-case straggler (§2.3, residual).
   - **The counter-reading**, for the owner: the trigger list names this subsystem and this kind of failure; the in-process guarantee is weakened as just stated; and earlier revisions of this ruling relied on the false claim, which is exactly the surprise Trigger 2 exists to catch.
   - **Without the §2.3 fix, R1′ would make path L worse.** Revision 4's reducer went over the drained pairs twice: once for `aggregate`, once for `applied_seqs.update`. A late entry landing between the two would have its seq recorded as applied with its effect in no row. Save step 2 writes that seq into `wal_applied_seqs` and step 3 deletes its line: an acknowledged signal lost in memory, and lost on disk as soon as that save completes, with nothing left for a reopen to replay. The fix in §2.3 makes the recorded seqs exactly the applied ones.
4. **No version bump.**
   - `durability.py:29-34` makes a *format bump* a Trigger 2. R1′ keeps `SNAPSHOT_VERSION = 1` and `WAL_VERSION = 1` (`durability.py:57-58`) and adds only optional keys, which rc1 parses (§1.2).
   - **Ruling: additive optional keys are not a format bump.** But additive does **not** mean rollback-safe. §3.5 states the rollback semantics concretely, including the sequences that lose data.

### 1.2 Do the optional keys count as a format change?

**The keys:**
- `seq` on each WAL line;
- `wal_applied_seqs` and `wal_next_seq` in `snapshot.json`.

**How rc1 reads them:**
- rc1 `wal_read` reads only the named keys `entity_id`, `weight` and `timestamp` (`durability.py:168-174`), so it ignores `seq`.
- rc1 `hydrate` reads `snapshot_version`, `snapshot_created_at` and `rows` with `.get` (`durability.py:204, 213-214`), so it ignores the new snapshot keys.
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
  | **invalid** | decodes, but the field parse raises `KeyError`, `TypeError` or `ValueError` (revision 6: as shipped, `_classify` treats **any** `Exception` from rc1's field parse as invalid); or `raw.decode` raises `UnicodeDecodeError` (a `ValueError`) | **raise the original exception unchanged**, as rc1 does | cannot occur (hydrate would have raised) | drop, counted, **ERROR** |
  | **entry** | parses | judged by §2.5 step 3 | per disposition | kept iff `seq ∉ S` |

- **Valid seq value (one rule for the WAL `seq`, each element of `wal_applied_seqs`, and `wal_next_seq`).** A value `v` is a valid seq only if `type(v) is int` (so `True` is not a seq) and `0 ≤ v < 2**53`. JSON can carry any of `null`, a bool, a float, a string, a list or an out-of-range int in these places, because SYNAPSE rewrites `snapshot.json` (owner-gate item 5) and because a hand edit can.
- **`seq` on a WAL line.** A line carries a seq only if `"seq"` is present and its value is a valid seq. Any other value is treated as **no seq**, never as an error.
- **`wal_applied_seqs` (normative).** Read with no assumption about its type.
  - The key counts as **present** only if its value is a `list` and **every** element is a valid seq. Then `A` is the set of those elements.
  - Otherwise (not a list, or any element invalid) the key is treated as **absent**, and one WARNING names the reason and the number of invalid elements. Every line is then judged by the timestamp rule (§2.5 step 3, row 2).
  - **Why the whole key, not the valid elements.** Keeping the valid elements of a mangled list would drop the mangled ones from `A`, and their lines, if still in the WAL, would replay by membership onto rows that already hold them: a double apply. Treating the key as absent gives the timestamp rule instead, which never doubles under the clock precondition (§3.4) and loses at most the pending `ts ≤ T` lines (defect B under a mangled key, the same outcome as a key strip, H2). This document prefers a stated loss to a double everywhere else, and does so here.
  - The valid elements still feed the allocator seed (§2.5 step 5), because seeding higher than necessary is always safe.
- **`wal_next_seq` (normative).** Used only if its value is a valid seq. Any other value is ignored with a WARNING. It only seeds the allocator; it never decides a replay.
- Neither key can now raise in hydrate. rc1 opens a store whatever these keys hold, and R1′ must too: `set(None)`, `max()` over mixed types, or an unhashable element would otherwise refuse a store that rc1 opens.
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
- Each reducer registers a unique token in `log._inflight` (a `set`) and stores a fresh `object()` in `log._apply_epoch` when it starts. When it ends, it removes its token and stores another fresh `object()` (§2.3). It never blocks or waits.
- The save, in `durability.py` where a mutex already exists (`durability.py:75`), accepts its read only if `_inflight` was empty before and after the row build, and `_apply_epoch` is still the object it read first. Otherwise it retries, for at most `SEQLOCK_READ_TIMEOUT_S` (§2.4 step 1).
- **Why this is exact even with concurrent reducers.** Every reducer's start writes a value no other reducer can write (a new object), and every live reducer is visible in the set. A reducer whose apply overlaps the save's read window was either in the set at the first check, is still in it at the second, or started and ended inside the window, which changed the epoch. The save holds a reference to the epoch object it read, so that object cannot be freed and its identity cannot be recycled. The parity counter had neither property: two reducers both wrote `g+1`, then `g+2`, so the second one to finish hid the first.
- That is no mutex and no CAS in the reducer. `set.add`, `set.discard` and attribute stores are each a single atomic operation under the GIL; none is a compare-and-swap. `ARCHITECTURE.md:340` holds.
- **What it does not rely on.** The single-reducer rule (`attention_log.py:30-36`) is a docstring, and nothing enforces it. R1′ does not assume it for the consistency of a keyed snapshot:
  - consistency comes from the save-side check above, which covers any number of reducers;
  - the reducer still detects a concurrent reducer on a best-effort basis, but **only logs it** (ERROR, §2.3). It never raises: the detection is diagnostic and nothing depends on it (revision 5; revision 4 raised, which let a stranded token stop every later pass, Appendix A, revision 5, issue 2);
  - the save's spin is bounded, and on timeout it degrades to a keyless snapshot instead of hanging.
- Concurrent reducers stay unsupported, exactly as in rc1. Their in-memory row updates can still interleave (`ecs.py:312-322`): a read-modify-write of one row by two reducers can lose one update. In the rare case that both read the same carried-over stragglers (§2.3), they can also apply one entry twice. A keyed snapshot persists whatever the rows hold. What R1′ guarantees is narrower: no **keyed** snapshot is ever written from a torn read, so `S` and the rows describe the same instant.
- The GIL is still required: it makes each set operation and attribute store atomic. It is enforced at `attention_log.py:63-68`.

### 1.4 The behaviour change in `signal_attention` (plan risk 5)

R1′ writes the WAL line **before** the buffer append, reversing `api.py:541` and `:542-545`.

| | Behaviour when `wal_append` raises |
|---|---|
| **rc1** | The signal is buffered, then the `OSError` escapes. It is applied in memory but not durable, so a caller that retries is double-counted in memory. **Also:** if `flush()` raised, the line stays in the text handle's buffer, and a later append, or `close()` (`durability.py:274-277`), can still write it out. A reopen can then replay a signal the caller was told failed. |
| **R1′** | The signal is in neither place, and the same `OSError` escapes. This is guaranteed by construction, as follows. The append is one unbuffered `os.write` of the whole line. On any exception or short write, the file is truncated back to its size before the write, and the descriptor is closed (§2.2). No user-space buffer exists to flush the line later. **Residual:** if the truncation itself fails, the seq is tombstoned (§2.2). The next successful save then lists it as applied, so no reader of that snapshot replays it. A crash *before* that save can still replay it once. |
| **R1′, async exception after `wal_append` returned** (for example a `KeyboardInterrupt` between the WAL write and the buffer append) | The line is durable but not buffered, so without a remedy the caller would see an exception, nothing would apply in process, and the signal would apply at the next reopen: a phantom apply. R1′ wraps the buffer append in `try/except BaseException`, tombstoning the seq before re-raising (§2.2). **Residuals, stated:** (a) an exception that lands after `wal_append` returns but before the `try` is entered, or inside the handler before the tombstone is recorded, leaves the line in place, and it applies once at the next reopen; (b) an exception that lands after the buffer append completed, but still inside the `try`, tombstones a buffered signal. The reducer then applies it in memory although the caller saw an exception, which is the rc1 class of in-memory phantom. The durable state stays self-consistent either way, because a tombstoned seq is in `S` and so is never replayed, and the save that records it also records the rows that hold its effect, or rows without it if it was not yet applied. |
| **R1′, async exception inside `wal_append`'s own failure path** (revision 5) | The write has already failed and the failure path is running (§2.2). Its first statement clears `_wal_fd`, so any later failure in the path still forces the next append to reopen the file and run the torn-tail check. **Residuals, stated:** (a) an async exception delivered in the one-statement window before `_wal_fd` is cleared leaves the descriptor set and the line (whole, or torn by a short write) in the file. The next append then writes straight after it with no torn-tail check. A torn leftover merges with the next acknowledged line into one undecodable line, which hydrate and step 3 drop: that next signal is lost. A whole leftover replays once at the next reopen with no tombstone: a phantom apply of a signal the caller was told failed. (b) An async exception after `_wal_fd` is cleared but before `os.close(fd)` leaks the descriptor. It was opened without share-delete, so every later `os.replace(wal_tmp, wal_path)` fails on Windows (§3.1) and the store stays on the degraded or K path, logging ERROR on every save, until the process exits. Both need an async exception to land inside a few bytecodes of a write that has already failed. |

In all of these, for a multi-entity `weights` dict, the entities before the failing one stay recorded.

**The reducer adds no raise (revision 5).** `reduce_attention_log`, and so `run_pass` and `run_sleep_pass`, raise nothing that rc1 does not. Concurrent-reducer detection logs at ERROR and the pass continues (§2.3). The one visible change: a reducer that finds another reducer's token at entry still drains and applies, as rc1 would, but logs ERROR. Release notes and `docs/api.md` state it.

**Ruling: not an API change.**
- The signature (`api.py:527`), the return type and the exception type are unchanged.
- It goes in the release notes and in `docs/api.md`.

**Four new raise conditions, ruled the same way.** None changes a signature, and each raises an existing exception type. All four go in the release notes.
- Two live handles whose store paths coincide raise `MonetaResourceLockedError`, even with different `storage_uri`s. The store paths are the resolved `snapshot_path`, `wal_path` and their two derived tmp paths (§2.6). One config whose own four paths are not pairwise distinct raises `ValueError`.
- `snapshot_ecs(ecs)` or `start_background(ecs)` called with an ECS other than the one attached to the handle's log raises `ValueError` (§2.4).
- **A closed `DurabilityManager` refuses to touch the store.** After `close()`, `wal_append`, `snapshot_ecs` and `start_background` raise `ValueError("durability manager is closed")`, which follows the `io` convention for operations on a closed file. rc1 instead reopens the WAL lazily (`durability.py:145-147`), and its `snapshot_ecs` would still rewrite the files. Because `Moneta.close()` releases the store's paths (`api.py:424`), a stale reference or a late thread could otherwise append to, or compact, a store that a new handle now owns. That is two seq allocators on one WAL, the hazard §2.6 closes. Through the public API this means `signal_attention` on a closed durable handle raises `ValueError` and buffers nothing (WAL-first). On a handle without durability it is unchanged.
- **A store whose seq allocator cannot be reseeded** (revision 5; §2.5 step 5) raises `RuntimeError("cannot reseed the WAL sequence allocator")` at construction. It needs a near-limit seed **and** at least 4096 referenced seqs blocking every aligned window below 2^52. No R1′-written store reaches it, so it is practically unreachable. Construction fails cleanly: the lock and store paths are released and no file is modified. Within the reseed's 2^40 headroom, `wal_append` never emits a seq at or above 2^53.

### 1.5 Why not R2, the shape v5 took

v5 carries attention in its checkpoint (`30ae826`: "checkpoint equality test carries attention since the last pass in the snapshot"). v5 owns its journal format. v1 should not do the same:

1. **It is a format bump.** Embedding the pending buffer in `snapshot.json` is a `snapshot_version` change, and therefore a Trigger 2 (`durability.py:29-34`). This is the deciding reason.
2. **Foreign rewrites of `snapshot.json` do not discriminate between R1′ and R2.** SYNAPSE rewrites `snapshot.json` on an embedder swap (`docs/v5/SYNAPSE_COMPAT.md:33`). Whether that rewrite keeps unknown keys is **unverified**: SYNAPSE's source is outside this clone, and SPEC §0 forbids touching it. That question is an owner-gate item (§6 gate 2).
   - The only modelled consumer rewrites do load-modify-dump: `tests/v5/test_compat.py:629-632` and `:654-656`. They *preserve* unknown keys, and so they would preserve R2's field and R1′'s keys alike. Caveat: both tests run against the v5 facade's derived export, not a v1 store. They model the *shape* of SYNAPSE's rewrite, not its behaviour on a v1 `snapshot.json`.
   - If a rewrite instead *drops* unknown keys, both designs degrade. R2 loses the whole pending buffer. R1′ falls back to the `durability.py:229` timestamp rule, and so loses every pending seq line with `ts ≤ T`. That is defect B again, rc1-equal, and H2 pins it as a characterization (§4.2). R1′'s seq lines with `ts > T` still replay.
   - So this point is neutral, or at most slightly favours R1′. It is not an argument against R2 that R1′ escapes.
3. **A window would remain under R2** between the timestamp at `api.py:538` and the buffer append.

---

## 2. R1′ design (amended R1)

### 2.1 State

| Holder | New state | Owner |
|---|---|---|
| `AttentionLog` | `_buffer: list[tuple[AttentionEntry, int \| None]]`; `applied_seqs: set[int]`; `_inflight: set[object]` (one token per running reducer; empty means idle); `_apply_epoch: object` (a fresh `object()` at every reducer start and end, §2.3); `_carry: tuple[list, int] \| None` (the list the last reducer swapped out, and how many items it took from it; one attribute, so it is stored and read in one step, §2.3); `stragglers_carried: int` (a private counter, for tests and the log line). **No `threading` import.** `AttentionEntry` stays the public 3-field NamedTuple (`attention_log.py:48-53`). The public `drain()` still returns `list[AttentionEntry]` (a new list built from one snapshot of the swapped-out list); the reducer uses a private `_drain_with_seqs()`. `append(entity_id, weight, timestamp, seq=None)`. | Substrate |
| `DurabilityManager` | Existing `_lock` (`durability.py:75`). New `_save_lock`, which serializes `snapshot_ecs` and `close()` against each other. Neither the reducer nor `wal_append` ever takes it. The WAL handle becomes a raw descriptor, `_wal_fd: int \| None` (§2.2). Seq allocator: `_next_seq: int \| None`, seeded by hydrate (lazily from the random base only for a never-hydrated bare manager; Appendix A row 13), read and incremented **only under the existing `_lock`**, inside `wal_append` and compaction step 3 (hydrate also allocates, single-threaded, before the handle is published). Nothing depends on seq order matching file order, and it does not always match: hydrate step 6 gives fresh high seqs to no-seq lines that sit earlier in the file, and step 3 renumbers foreign lines in place. Every rule compares seqs only by set membership (test F pins a non-prefix order). The signal path still takes exactly one lock, the one it already takes. `_void_seqs: set[int]`, tombstones from failed appends and from an interrupted buffer append (§2.2), added through a small method `void_seq(seq)` under `_lock`. `_closed: bool`, set by `close()` under `_lock` (§1.4). `_attached: tuple[AttentionLog, ECS] \| None`. `_disposition`: the per-line plan for the WAL as found at hydrate (§2.5). `_disposition_basis: tuple[int, bytes] \| None`: the length and sha256 of the WAL bytes hydrate read; set with `_disposition`, and `None` whenever `_disposition` is empty (§2.4 step 0, revision 6). | Persistence |
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
    wal_path.parent.mkdir(parents=True, exist_ok=True)   # kept from rc1 (durability.py:146)
    fd = os.open(wal_path, O_WRONLY | O_CREAT | O_APPEND | getattr(os, "O_BINARY", 0))
    try:                                                 # nothing may leak fd before it is published
        size = os.fstat(fd).st_size
        if size > 0 and last byte of the file != b"\n":  # torn tail from a crash or power loss
            os.write(fd, os.linesep.encode())            # terminate the fragment first
        _fsync_dir(wal_path.parent)                      # F1 (§5): the open may have created the WAL
    except BaseException:
        try: os.close(fd)
        except OSError: pass
        raise                                            # the original error
    _wal_fd = fd
seq = _next_seq; _next_seq = seq + 1                     # allocated before the write; never reused
data = (json.dumps({"wal_version": 1, "entity_id": ..., "weight": ..., "timestamp": ..., "seq": seq})
        + os.linesep).encode("utf-8")
fd = _wal_fd
pre = os.fstat(fd).st_size
ok = False
try:
    n = os.write(fd, data)
    if n != len(data): raise OSError("short WAL write")
    os.fsync(fd)                                         # F1 (§5): on disk before the signal is acknowledged
    ok = True
finally:
    if not ok:                                           # any exception, including an async one
        _wal_fd = None                                   # FIRST: a failed append always forces a reopen
        try:                                             #   and the torn-tail check on the next append
            try: os.ftruncate(fd, pre)
            except OSError: _void_seqs.add(seq)          # tombstone; logged at ERROR
        finally:
            try: os.close(fd)                            # best-effort close
            except OSError: pass
# the original exception propagates out of the finally unchanged
return seq
```

- **Read the last byte** through a separate `with open(wal_path, "rb")` handle, seeking to `-1` from the end. That handle is closed before the function returns.
- **The open path (revision 5).** rc1 creates the WAL's directory before opening (`durability.py:146`), and R1′ keeps that, so a `wal_path` whose directory does not exist yet still works. Everything between `os.open` and `_wal_fd = fd` (the `fstat`, the last-byte read, the repair write) is wrapped so that any exception, async ones included, closes `fd` before it propagates. A leaked descriptor would otherwise hold the WAL open without share-delete, and every later `os.replace(wal_tmp, wal_path)` would fail on Windows (§3.1). **Residual:** an async exception that lands between `os.open` returning and the `try` being entered still leaks `fd`. That is a window of one bytecode.
- **If the torn-tail repair write fails,** the exception escapes, `fd` is closed and the signal is not acknowledged. Nothing else changes.
- **Why there is no buffer.** rc1's text handle keeps a line in user space when `flush()` raises. A later flush or close then writes it, which is a phantom apply (§1.4). The unbuffered single write plus truncate-back removes that path.
- **`O_APPEND`.** Each write lands at the end of the file, and `pre` is read under `_lock`, so no in-process writer can move the end between the `fstat` and the write.
- **Tombstones.** `_void_seqs` is merged into `S` at save step 1, so the next snapshot lists the seq as applied, and compaction drops its line. Step 4 then releases those seqs together with `S`. For a failed write, no row ever contains the effect of a tombstoned seq, which matches "the caller was told it failed". For an interrupted buffer append, see §1.4 residual (b).
- **The failure path keeps the original error.** The truncate and the close are each guarded, and the close sits in a `finally`. An `OSError` from `os.close` can therefore neither replace the write's error nor leave a stale descriptor that the next append would reuse.
- **`_wal_fd` is cleared first (revision 5).** The failure path is a `finally` keyed on `ok`, and its first statement is `_wal_fd = None`. So an exception anywhere after that statement, including an async one inside the truncate or the close, still leaves no descriptor for the next append to reuse; that append reopens the file and runs the torn-tail check. Revision 4 cleared `_wal_fd` last, in an inner `finally`, so a `KeyboardInterrupt` landing in the handler before that inner `try` left the descriptor set. The residuals that remain (an async exception in the one statement before the clear, and a leaked descriptor between the clear and the close) are stated in §1.4.
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
if log._inflight:                            # best-effort, diagnostic only: log, never raise
    _logger.error("concurrent attention reducer at entry (%d in flight)", len(log._inflight))
tok = object()
clash = False
updated = 0
try:
    log._inflight.add(tok)                   # inside the try: an async exception before it strands nothing
    mine = object(); log._apply_epoch = mine # a value no other reducer can write
    items = log._drain_with_seqs()           # ONE tuple: carried stragglers + one snapshot of this swap
    agg = aggregate([e for e, _ in items])
    seqs = [s for _, s in items if s is not None]   # the same tuple: recorded == drained
    try:                                     # revision 6: opens BEFORE the record
        log.applied_seqs.update(seqs)        # recorded BEFORE the apply (gate 3)
        updated = ecs.apply_attention(agg, now)
    except BaseException:                    # interrupted: a stated loss, never a double
        _logger.error("torn attention apply: ... %d of %d drained WAL seq(s) recorded ...", ...)
        raise
    clash = log._apply_epoch is not mine or len(log._inflight) > 1   # diagnostic only
finally:
    try:
        log._inflight.discard(tok)           # idempotent; cannot raise
    finally:
        log._inflight.discard(tok)           # again: stranding the token now needs two async faults
    log._apply_epoch = object()              # end-of-apply epoch; correctness does not need it (below)
ecs.decay_all(decay.lambda_, now)            # eval point 2, unchanged, outside the window
if clash:
    _logger.error("concurrent attention reducer detected")          # log only; never raise
return updated                               # unchanged return value (attention_log.py:132)
```

**`_drain_with_seqs()` (normative, revision 5).** Reducer only. It returns one immutable tuple, and the reducer uses that tuple for both the aggregate and the seq record.

```
carry = self._carry                          # one read of one attribute: (list, taken) or None
old, self._buffer = self._buffer, []         # the existing single swap, attention_log.py:82
late = tuple(carry[0][carry[1]:]) if carry is not None else ()   # stragglers of the PREVIOUS swap
items = tuple(old)                           # one C-level copy: no thread switch mid-copy
self._carry = (old, len(items))              # one store
if late: self.stragglers_carried += len(late); _logger.warning(...)
return late + items
```

- **Why one snapshot fixes the durable state.** An entry that lands in `old` after `tuple(old)` is in neither `agg` nor the seq record. Its seq stays `∉ applied_seqs`, so it is `∉ S` at every save. Compaction keeps its line, and a reopen replays it once. The keyed durable state is therefore exact under path L: every recorded seq has its effect in the rows, and every unrecorded seq still has its line. Revision 4 read the drained pairs twice (once for `aggregate`, once for `applied_seqs.update`), so a late entry landing between the two reads was recorded as applied with its effect in no row. Save step 2 then wrote it into `wal_applied_seqs` and step 3 deleted its line: a permanent, silent loss on disk.
- **Carry-over (best effort, in memory).** The next reducer takes `old[taken:]` from the previous swap, so a late entry is normally applied one pass later, with its seq recorded then. Each list is carried at most once: `_carry` is replaced by the newer swap in the same call, so no entry can be taken twice by one reducer.
- **Residual, stated.** An entry that lands in a swapped-out list after the **next** reducer has also read it (its appender stalled for a whole pass interval) is not applied in this process at all. Its seq is never recorded, so its line survives every save and it is applied exactly once at the next reopen. A late entry is never lost durably, and never applied twice by one reducer.
- **The public `drain()`** (used only by `tests/unit/test_attention_log.py`) returns `[e for e, _ in tuple(old)]` from one swap. It does not touch `_carry`. Its late-landing exposure is rc1's, and no production path calls it.
- **`len(log)`** still counts only the live buffer (`attention_log.py:85-86`), as in rc1. Carried stragglers are not counted.
- **Optional narrowing, not relied on.** `append` may build its `(AttentionEntry, seq)` item before it loads `self._buffer`. That removes the Python-level constructor from the window between capturing the list and appending to it, which makes late landings rarer. It is not a proof: CPython can still switch threads between the attribute load and the call. Nothing above depends on it, and test AI does not either (§4.2).
- **Docstrings (gate 5).** The module docstring's proof (`attention_log.py:11-19`, "Entries cannot be lost") and the `drain()` docstring (`:76-80`) are rewritten to say: an append can land in a list that was already swapped out; the reducer takes one snapshot of each swapped list, carries late entries to the next pass, and never records a seq it did not apply, so the WAL keeps every unapplied entry.

**Rules:**
- `decay_all` keeps exactly three call sites (`api.py:515`, `attention_log.py:131`, `consolidation.py:161`; SPEC §7).
- **What makes a save's read safe** is the save-side check (§2.4 step 1), not anything the reducer detects. A reducer is visible to the save from `_inflight.add(tok)` until `_inflight.discard(tok)`, and its drain, apply and record all happen inside that interval. Its start stores a new object in `_apply_epoch`, and so does its end.
- **Order inside the `try`.** The token is added before the epoch store, and both happen before the drain. So by the time any row or `applied_seqs` changes, the reducer is in the set and the epoch has moved.
- **Order in the `finally` (revision 5: discard first).** The discards come first and the end-of-apply epoch store last. Correctness needs only the start store: a reducer in flight at the save's first check is in the set, and a reducer that started after it moved the epoch then. The end store can only add a spurious retry (a save that read the epoch between the discard and the end store sees it move). Putting the discard first, in a nested `try/finally` that repeats it, shrinks the stranding window: a single async exception anywhere in the `finally` still leaves one discard to run. Revision 4 stored the epoch first, so one async exception landing before the discard stranded the token.
- **Async exceptions.** `KeyboardInterrupt` under Houdini can land anywhere.
  - If it lands before the `try`, nothing was registered and nothing was drained.
  - If it lands inside the `try`, the `finally` clears the token. If it landed before `add` completed, `discard` of the absent token is a no-op; `discard` cannot raise either way.
  - If it lands inside `_drain_with_seqs` after the swap but before the tuple is returned, the swapped entries are applied by no pass in this process. Their seqs are never recorded, so their lines survive every save and replay once at the next reopen. That is the path L residual above, not a new class.
  - If it lands after the drain and before the end of the apply, the inner `try` is already open (revision 6), so the ERROR `torn attention apply` counts the recorded seqs: recorded seqs are a stated loss, and unrecorded ones replay once at the next reopen.
  - `AttentionLog.__init__` sets `_inflight = set()`, `_apply_epoch = object()`, `_carry = None` and `stragglers_carried = 0`.
- **Stranded token (corrected in revision 5).** Stranding now needs two async exceptions inside the `finally`: one before the first discard and one before the second. If it happens:
  - Later sleep passes still run normally. The entry check only logs ERROR ("concurrent attention reducer at entry"), so every pass still drains, applies and records, and `run_sleep_pass` reaches its save.
  - Every later save sees `_inflight` non-empty for its whole spin, times out, and **degrades**: a keyless snapshot, the WAL left whole, `degraded_saves` incremented, ERROR on every save. Never torn.
  - Under a keyless snapshot a reopen judges every line by timestamp (§2.5), so pending lines with `ts ≤ T_new` are lost at that reopen (defect B), as for any degraded save (§2.4).
  - Reopening the handle clears the token. Closing and reopening right after the first such ERROR limits the exposure.
  - Revision 4's entry check raised instead. A stranded token then made every later sleep pass raise before draining, so attention was never applied again, the buffer grew without bound, and `run_sleep_pass` never reached its save. Test AB(e) pins the new behaviour.
- **Reentrancy detection is best-effort and diagnostic, and it never raises.** The entry check sees a second reducer that starts while one is registered. The `clash` test sees overlap from either side: the first reducer sees the epoch changed by the second, and the second sees the first's token still in the set. Both only log at ERROR. A reducer that passes the entry check in the instant before another registers is seen by `clash` only if their applies overlap; if they do not overlap, the two runs were sequential in effect and nothing is wrong. Exactness for the snapshot never depends on this detection.
- **Why log-only rather than raise (revision 5).** A raise at entry made a stranded token stop every later pass (above), and a raise after `decay_all` escaped `run_pass` after attention was already applied, skipping prune, staging and the pass's save. Neither protects the durable state: the save-side check already refuses a torn read, and concurrent reducers remain unsupported either way (§1.3). With log-only detection, the reducer adds no exception that rc1 does not raise (§1.4).
- A native decay failure at the `decay_all` line happens after the seqs are recorded. That matches SPEC §7 "Exactly-once attention" case 1.

**Residuals.**
- `apply_attention` (`ecs.py:312-322`) mutates rows entity by entity. Under the gate 3 order (revision 6) the drained seqs are already recorded when it runs, so if it raised midway, the rows would be partly applied and every drained seq recorded: the next save drops their lines, so the unapplied part is a stated loss, logged as `torn attention apply`, never a double. For valid input it raises only on `MemoryError`. This is pre-existing in class and is recorded here.
- **Record before apply (gate 3 ruling, revision 6).** Revision 5 kept apply-then-record and flagged the order for gate 3: an async exception after `apply_attention` returned but before `applied_seqs.update` ran would leave effects in the rows with no seqs recorded, and a later keyed save plus a reopen would apply them twice. Gate 3 ruled record-before-apply, which turns both residuals into stated losses, matching this document's preference (§1.2). The inner `try` opens before the record (`6040903`, test AB(c2)), so an async exception between the record and the end of the apply is logged at ERROR with the count of recorded seqs; unrecorded seqs keep their lines and replay once at the next reopen.

### 2.4 Save: `snapshot_ecs(ecs)`, under `_save_lock`

**Precondition.** If a log is attached and `ecs is not attached_ecs`, raise `ValueError` before writing anything. The consistent read (step 1) pairs `log.applied_seqs` with the rows of the ECS that the reducer writes to. Any other ECS would make `S` describe effects its rows do not contain: a loss or a double on reopen.
- **Closed manager.** If `close()` has run, raise `ValueError("durability manager is closed")` before writing anything (§1.4). `start_background` does the same.
- **In-tree v1 callers at HEAD `e7325bb`** (`git grep -n "snapshot_ecs\|start_background" -- tests scripts`, plus `src`, excluding `src/moneta/v5/` and the tests that drive the v5 facade; the `scripts/v5/` directory is **not** excluded, because the bench there drives a v1 handle): `api.py:581`, which passes `self.ecs` (assigned only during `__init__`, `api.py:281, 309`); `scripts/v5/bench_v5_vs_v1.py:61`, which passes `v1.ecs`; and test callers in three files added on this branch, all passing `m.ecs`: `tests/integration/test_attention_snapshot_regression.py:62` (the C6 `_save` helper), `tests/qualification/test_native_executes.py:46` and `tests/unit/test_native_handle.py:374, 612`. At rc1 there was no test caller under `tests/unit` or `tests/integration`.
- The `test_compat.py:66, 549, 559, 570, 587, 626` calls pass `m.ecs` too, but to the v5 facade's `_DurabilityView.snapshot_ecs(ecs=None)` (`v5/compat.py:659`), which ignores it. They show SYNAPSE's call shape. They are not evidence about v1 callers. Whether SYNAPSE passes only `m.ecs` to a v1 handle stays owner-gate item 6.
- v5's argument-less `snapshot_ecs()` (`v5/compat.py:852, 886`) is v5's own object, outside this design.
- `start_background(ecs)` applies the same check when it starts.

| Step | Action |
|---|---|
| **0. Normalize** (only if `_disposition` is non-empty) | Under `_lock`: close `_wal_fd`. Read the WAL with `with`, using the §1.2 raw-line grammar (the same reader as hydrate, §2.5 step 2). Write the WAL tmp file `wal_tmp` **in binary mode** (see "tmp paths" and "tmp write mode" below). Lines `i < prefix_len` follow the disposition: drop, or write with their assigned `seq`. Lines `i ≥ prefix_len` (appended since hydrate) are copied unchanged; step 3 of the same save classifies them. Then `os.replace(wal_tmp, wal_path)` and clear `_disposition`. **Semantics-preserving** under the snapshot currently on disk (proof in §3.3).<br>**Absent or shortened WAL (revision 5).** An absent WAL has zero raw lines (§1.2). If the WAL is absent, step 0 writes nothing, clears `_disposition` and continues to step 1: the lines it would have normalized are gone, so there is nothing to protect. A shortened WAL fails the basis check below (erratum E3).<br>**The basis check (revision 6, cross-review).** Hydrate records the length and sha256 of the WAL bytes it read (`_disposition_basis`). Step 0 applies the disposition only to a WAL that still starts with those bytes; appends, the torn-tail repair included, only add bytes after them. Any WAL that does not start with those bytes, including one shortened or rewritten outside this handle, or one an earlier step 0 of this handle already normalized (below), is a **step 0 failure**.<br>**On step 0 failure, degrade; do not skip the save.** Delete `wal_tmp` best-effort, keep `_disposition` and `applied_seqs`, and log at ERROR. Then go to the **degraded save** below. Do not run steps 1 to 4. (Revision 6: as shipped, step 0 degrades on any `Exception`. A `BaseException` such as `KeyboardInterrupt` inside step 0 escapes `snapshot_ecs` instead; step 0 deletes `wal_tmp` and keeps `_disposition`. If the exception came before the `os.replace`, the WAL is still the one hydrate read, and the next save retries step 0. If it came after the replace and before the clear, the WAL is already normalized: the next save fails the basis check and degrades instead of applying the disposition by index to the normalized WAL, and so does every later save of the handle until it is reopened (test AL). The disposition is kept only until the replace: once the WAL is normalized, `_disposition` is cleared before the directory fsync, so a failed directory fsync degrades that save with nothing left to retry, and a retry over a normalized WAL is never attempted.) |
| **1. Consistent read (optimistic, bounded)** | Set a `time.monotonic()` deadline `SEQLOCK_READ_TIMEOUT_S` (module constant, 5.0 s) ahead. Then loop:<br>1. `e1 = log._apply_epoch`. If `log._inflight` is non-empty, `time.sleep(0)` and retry.<br>2. Build `rows` exactly as `durability.py:85-101`.<br>3. `S = frozenset(log.applied_seqs) \| frozenset(_void_seqs)`, with `_void_seqs` read under `_lock`.<br>4. Accept iff `log._inflight` is empty **and** `log._apply_epoch is e1`; otherwise retry. Both checks are needed: the set catches a reducer still running, and the epoch catches one that started and ended inside the window.<br>**If the deadline passes,** log at ERROR naming the number of in-flight reducers and whether the epoch moved, and go to the **degraded save**. Do not raise and do not hang.<br>No apply overlapped the copy, so `rows` and `S` are mutually consistent. `e1` stays referenced until the check, so its identity cannot be recycled.<br>After the loop, read `nxt = _next_seq` once under `_lock`. Every seq allocated later is at or above `nxt`, and every seq this handle allocated is below it. Seqs inherited from before a hydrate-time reseed (§2.5 step 5) can be above `nxt`; collision freedom for them comes from the reseed's disjointness check, not from `nxt`. |
| **2. Snapshot** | Add `"wal_applied_seqs": sorted(S)` and `"wal_next_seq": nxt` to the dict at `durability.py:103-107`, keeping `snapshot_created_at = time.time()` for older readers. Write with the existing tmp → `fsync` → `os.replace` (`:112-116`). |
| **3. Compact** | Under `_lock`: close `_wal_fd` and set it to `None`. Read the WAL with `with`, using the §1.2 raw-line grammar; an absent WAL has zero raw lines and is not an error (rc1 guards the same way, `durability.py:124, 153`). Class each line per the §1.2 table: drop blank, undecodable and invalid lines (counting each class, WARNING for undecodable, ERROR for invalid). Of the entry lines, write to `wal_tmp` every one whose `seq ∉ S`. An entry with no seq can only come from a foreign writer here. **Give each one a fresh seq from `_next_seq`** (it is in no row, so replaying it once at the next reopen is correct), count them, and log a WARNING. Write in binary mode, per "tmp write mode" below. Flush, close, `os.replace(wal_tmp, wal_path)`. **If no line is kept** (including an absent WAL), write no tmp and create no file: unlink the WAL if it exists, ignoring `FileNotFoundError`, which is rc1's on-disk shape after a save (`durability.py:124-125`). A failed unlink takes the compaction-failure path, as a failed replace does. `_wal_fd` stays `None`, so the next `wal_append` reopens, including its torn-tail check (§2.2). |
| **4. Release** | `log.applied_seqs.difference_update(S)` and, under `_lock`, `_void_seqs.difference_update(S)`, **only after step 3 succeeded** (revision 6: as shipped, the `applied_seqs` release runs outside `_lock`, which is harmless: the reducer never takes `_lock`, and the operation is one in-place C call). This is an in-place C set operation on ints, and it does not race the reducer's `update`. Do not rebind the attribute. Seqs applied after step 1 stay in the set. |

**tmp paths (normative).** The WAL tmp file is `wal_tmp = wal_path.with_name(wal_path.name + ".tmp")`, which is next to the WAL and derived from its full name, exactly as rc1 derives the snapshot tmp (`snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")`, `durability.py:109-111`). It is never a fixed name such as `wal.tmp`: two stores in one directory (`a.wal`, `b.wal`) would then share one tmp file, and one store's `os.replace` could install the other's lines. Both derived tmp paths are registered in `_ACTIVE_STORE_PATHS` (§2.6), so no live handle's store path can be another handle's tmp path.

**tmp write mode (steps 0 and 3, normative).** Open `wal_tmp` with `open(…, "wb")`.
- A line kept unchanged is written as its original raw bytes, terminator included. If it is the final unterminated run (§1.2), `os.linesep` is appended, so the tmp always ends in a terminator.
- A line that is rewritten (a seq assigned) is re-serialized with the same key set as §2.2, then encoded with `os.linesep` as its terminator.
- Never write the tmp in text mode. On Windows, text mode turns a `\r\n` read from a binary reader into `\r\r\n`. That breaks the byte-identity with rc1's lines claimed in §1.2, and it adds a blank-looking `\r` to every line. Both readers would still strip it, but test O's "WAL bytes unchanged" assertions would become meaningless.
- The reader used by steps 0 and 3 must open the WAL in binary mode too and apply the §1.2 raw-line grammar, so the raw-line indices match hydrate's (§2.5 step 2). One shared function implements the grammar for all three.

**Degraded save.** This is the path for a step 0 failure and for a step 1 timeout. It gives rc1 semantics and keeps deposits durable.
1. Build `rows` once, without the consistency check, as rc1 does (`durability.py:85-101`).
2. Write a **keyless** snapshot: rc1's dict, with no `wal_applied_seqs` and no `wal_next_seq`. Use the existing tmp → `fsync` → `os.replace`.
3. **Leave the WAL alone.** No further step 0, no compaction, no unlink. Skip step 4. Keep `applied_seqs`, and keep `_disposition` as it stands. The two entries differ (revision 5):
   - **Step 0 failed:** `_disposition` is still non-empty. If the WAL is still the one hydrate read (the replace failed, for example), the next save retries step 0. If it is not (an interrupt landed after step 0's replace, or something outside the handle changed the WAL), the basis check fails again, and every later save of the handle degrades until it is reopened (revision 6). If only the directory fsync after step 0's replace failed, `_disposition` is already empty: the WAL is the normalized one, and the next save starts at step 1.
   - **Step 1 timed out after step 0 succeeded in this save** (or after `_disposition` was already empty): the WAL is the **normalized** one, and `_disposition` is already empty. The next save has no step 0 to retry and starts at step 1.
4. Increment `degraded_saves` (a private int on the manager, for tests and the log line; both entries, a step 0 failure and a step 1 timeout, count), log at ERROR naming the entry, then return normally, so the deposit save succeeds.

What a degraded save means:
- **On reopen,** every line is judged by `timestamp > T_new` (§2.5, key absent). What is lost is every line whose effect is **not in the degraded rows** and whose `ts ≤ T_new`. That is the lines still pending when the rows were built, **including lines a reducer applied in memory after the row build**: the rows lack them, and their `ts ≤ T_new` (the signal came before `T_new` is stamped), so the timestamp rule filters them. That is defect B, rc1-equal in class. It applies only if a reopen happens while this keyless snapshot is current; a later keyed save puts those lines back under membership, because their seqs are not in that save's `S` unless their effects are in its rows.
- **No double apply, under the precondition in §3.4:** every signal applied before the snapshot has `ts ≤ T_new`. A signal clock running ahead of the snapshot clock breaks it. Under that condition, lines already applied in memory replay on reopen: a double.
- **Unlike rc1, the WAL is not unlinked,** so it grows for as long as the failure persists. Every degraded save logs at ERROR, so the condition is visible.
- **After a step 0 failure, the next save retries step 0** while the WAL still starts with the bytes hydrate read; otherwise it fails the basis check and degrades again (point 3). (After a step 1 timeout that followed a successful step 0, there is nothing to retry; see point 3.) `_disposition` is still valid against the keyless `T_new` snapshot now on disk. Its drops are lines with `seq ∈ A`, or with `ts ≤ T_old ≤ T_new`, or duplicates. Under the precondition, the timestamp rule drops all of those too. Its seq assignments are invisible to a keyless reader.

**Compaction failure.** For example, `PermissionError` from `os.replace`; see Windows in §3.1.
- Delete `wal_tmp` on a best-effort basis.
- **Skip step 4**, so `S` stays in `applied_seqs` and the next save writes it again.
- Re-raise the original error. rc1's `unlink` failure also escapes `snapshot_ecs`, and the background thread logs it (`durability.py:251-254`). The snapshot (step 2) is already written, so the deposits are durable. This differs from a step 0 failure, which happens before any snapshot is written and therefore degrades instead.
- **Known bound.** If compaction keeps failing across saves, `S` is never subtracted, so `applied_seqs` and `wal_applied_seqs` grow without bound until one compaction succeeds. Each failure is raised and logged, so the condition is visible.
- The disk is then in the "after step 2, before step 3" state. That is safe for R1′ (§3.3), but it is an **rc1-reader exposure** for as long as the failure persists (§3.5).
- **If step 4 ran after a failed step 3,** the next snapshot would omit `S` while its lines are still in the WAL, and the next hydrate would double-apply them.

**`close()`.** `DurabilityManager.close()` calls `stop_background()` (whose join has a 5 s timeout, `durability.py:268`), then takes `_save_lock`, then `_lock`, then sets `_closed = True` and closes `_wal_fd` (guarded, then set to `None`). From then on `wal_append`, `snapshot_ecs` and `start_background` raise (§1.4). `close()` itself stays idempotent. Because `Moneta.close()` calls it before it releases the URI and the store paths (`api.py:418-424`), no append or save from this manager can reach the files once another handle may own them. A background save still running after the join timeout therefore finishes before the descriptor closes. The order `_save_lock` → `_lock` is the global order (§3.1), so this adds no deadlock. The wait is bounded, because step 1 is bounded and the file steps are finite.

**Background thread shutdown (normative, revision 5).** rc1's `stop_background` joins with a 5 s timeout and then clears `_stop_event` and `_bg_thread` whether or not the thread has exited (`durability.py:267-270`). `SEQLOCK_READ_TIMEOUT_S` is also 5.0 s, so a background save that spins to its bound outlasts the join. When that save returns, the loop calls `self._stop_event.wait(...)` on `None` (`durability.py:250`): an `AttributeError` that reaches `threading.excepthook`. With `_bg_thread` already cleared, a `start_background` call (`:244`) could also start a second saver beside the first. rc1 has the same bug; R1′'s spin makes it reachable. R1′ therefore changes three things, all in `durability.py`:
1. `_run` captures the event in a local when the thread starts (`stop = self._stop_event`, then `while not stop.wait(interval)`). It never reads `self._stop_event` again.
2. `stop_background` sets the event and joins with the existing timeout. It clears `_bg_thread` and `_stop_event` **only if the thread has exited**. If the join timed out, it logs a WARNING and leaves both set; the thread sees its own event set after its save returns, and exits.
3. `start_background` returns early only while `_bg_thread` is alive (`_bg_thread is not None and _bg_thread.is_alive()`). A dead thread object is cleared and replaced. So a timed-out stop can never lead to two savers, and a finished one never blocks a restart.

`close()` keeps its order: the save still in flight finishes under `_save_lock` before `close()` proceeds, and the thread then exits on its own event without touching the manager again.

**Without an attached log** (a bare `DurabilityManager`; no src or test constructs one other than `api.py:277`): exact rc1 behaviour. No new keys are written, and the WAL is unlinked.

### 2.5 Hydrate (normative; modifies no file)

1. Load the snapshot as `durability.py:201-226` does.
   - Read `wal_applied_seqs` and `wal_next_seq` under the §1.2 type rules (revision 5). Never call `set()` or `max()` on a raw value.
   - `raw = snapshot.get("wal_applied_seqs")`. `A_valid` = the valid seqs in `raw` if `raw` is a list, else `∅`.
   - `key_present` is true only if `raw` is a list and every element is a valid seq. Then `A = A_valid`. Otherwise `key_present` is false, `A = ∅` for replay decisions, and, if the key exists at all, one WARNING names why it was ignored.
   - `next_hint = snapshot.get("wal_next_seq")` if it is a valid seq, else absent (WARNING if the key exists but is invalid).
   - With no snapshot file (`durability.py:194-199`): `key_present = True`, `A = ∅`, `snapshot_ts = 0.0`. That reproduces rc1's replay-everything.
2. Read the WAL **by raw line** `i`, using the §1.2 grammar. **An absent WAL has zero raw lines** (revision 5; rc1 guards the same way, `durability.py:153`): `prefix_len = 0` and the disposition is empty. The grammar in full: maximal runs ending in `\n`, plus a final non-empty unterminated run, and never a trailing empty piece. Blank and undecodable lines are counted too. rc1's `wal_read` skips both (`durability.py:158-167`), so an index over parsed entries would shift every disposition after the first blank line. Class every line per the §1.2 table; an **invalid** line raises its original exception, as rc1 does, so a store that rc1 cannot open, R1′ cannot open either (register test P6 is unchanged). A `seq` counts only under the §1.2 rule. Step 0 and step 3 use this same reader.
   - **Why the trailing empty piece matters.** A WAL that ends in `\n` (the normal case) split naively on `b"\n"` gives a phantom empty last piece. Hydrate would record it as raw line `prefix_len-1` with disposition *drop (blank)*, so `_disposition` would be non-empty on every reopen. The first post-hydrate `wal_append` then lands at exactly that index, and step 0 would drop it: an acknowledged, pending signal gone from the WAL while it sits in the buffer, and lost on a crash after that save. Test AE pins it.
3. **Decide each line:**

   | Line | Rule |
   |---|---|
   | `key_present` and has `seq` | Replay iff `seq ∉ A`. |
   | No `seq`, or key absent | Replay iff `timestamp > snapshot_ts`, the rc1 rule at `durability.py:229`. |

4. **Duplicate seq.** Only a collision (§2.6) or a foreign writer can produce one. The first occurrence wins. Later ones are dropped with a WARNING and counted in the `durability.hydrate` log line. A collision must never be dropped silently.
   - First-wins means a cross-lineage collision drops the *newer* signal. That is the intended default: the seed rule makes a collision reachable only through a foreign snapshot replacement, or through two handles sharing a WAL, which §2.6 now refuses. Do not flip it without a new ruling.
5. **Seed the allocator (normative):**
   ```
   LIMIT  = 2**53                          # every seq is < LIMIT (§1.2)
   MARGIN = 2**40                          # allocations guaranteed per handle lifetime after this seed
   taken  = A_valid ∪ {valid seqs in the WAL}
   sources = [next_hint] if present
           + [max(A_valid) + 1] if A_valid
           + [max(valid seqs in WAL) + 1] if any
   next = max(sources) if sources else random_base()
   if next > LIMIT - MARGIN:               # a foreign or near-limit seed: new seqs would leave the range
       log ERROR (the seed and its source)
       for _ in range(64):
           b = random_base()
           if no element of taken lies in [b, b + MARGIN): next = b; break
       else:                               # deterministic fallback: scan the 2**12 aligned windows
           b = lowest k * 2**40, 0 <= k < 2**12, with no element of taken in [b, b + MARGIN)
           if none exists:                 # taken would need >= 4096 seqs spread over [0, 2**52)
               raise RuntimeError("cannot reseed the WAL sequence allocator")
           next = b
   random_base() = secrets.randbits(32) << 20                               # a multiple of 2**20, below 2**52
   ```
   - **All three sources are required.** Without `max(A)+1`, a rewrite that keeps `wal_applied_seqs` but drops `wal_next_seq`, over an empty WAL, would reseed low. New signals would then be filtered as already applied: loss. Test L pins this; it seeds from `A`, so the new seq is ≥ 10.
   - **The random base is normative,** not a recommendation. It is used when no seq information exists (a fresh store, an rc1 store, or a store whose seq information was stripped) and for a near-limit reseed. It stays below 2^52, under JSON's 2^53. Test Z pins it.
   - **Why the near-limit reseed (revision 5).** A `wal_next_seq` at or above `2**53 - 2**40`, which only a foreign rewrite or a hand edit can produce, would seed every new seq at or past `2**53`. §1.2 treats those as **no seq**, so every new line would be judged by timestamp even under a keyed snapshot: defect B back for good, with no warning. The reseed logs ERROR, picks a random base, and requires the whole window `[base, base + 2**40)` to be disjoint from every seq still referenced (`A_valid` and the WAL's valid seqs). Otherwise a new seq could fall in `A` and a crash-reopen before the next save would filter it as applied: loss. The window gives ≥ 2^40 allocations per handle lifetime (about 35 years at 1000 signals per second). An ordinary seed below the limit gives at least as many. Each random draw fails with probability about 2^-12 for a small `taken` set, so the deterministic scan practically never runs. The scan covers the 2^12 disjoint windows below 2^52, so the `RuntimeError` needs at least 4096 referenced seqs spread across that whole range, which no R1′-written store can hold and only a deliberate hand edit could produce. It is the fourth new raise condition (§1.4): construction fails, the URI and store paths are released and no file is modified, as for any hydrate failure (SPEC §7 "Failure cleanup").
   - **What the reseed does to `nxt`.** After a reseed, seqs inherited from before it can be above the new allocator. Nothing compares seqs by order (§2.1), so that is safe. A later reopen seeds from `max(A_valid) + 1` or the WAL again while those old high seqs are still referenced, and reseeds again (another ERROR) until they are gone: compacted once applied, and dropped from `A` once released.
6. **Assign fresh seqs** from the seeded allocator to replayed lines that have none.
7. **Record `_disposition`** for the first save's step 0:
   - `prefix_len` = the raw line count at hydrate;
   - for each raw line: *drop* (filtered, a duplicate, `seq ∈ A`, blank, or undecodable), or *keep with seq s*. "Malformed" in this document means exactly the §1.2 **undecodable** class (`JSONDecodeError`); an **invalid** line never reaches a disposition, because hydrate raised on it. Dropping blank and undecodable lines preserves semantics, because no reader ever replays them. That includes an undecodable torn tail fragment; a torn fragment that parses is an entry and is judged like any other line.
   - The disposition is empty when every line already carries a seq and none is dropped.
8. **Key absent but seq-bearing lines present.** This means an rc1 save, a degraded save, or a foreign rewrite happened. Log a WARNING. This is the only "store-format marker" behaviour available (§3.5).
9. Replay into the log with `seq=s`, via the `api.py:298-301` loop, which passes `seq` through.
10. **Return shape.** The public `hydrate(self, native=None, *, _source=None)` (`durability.py:181-186`, added by C3) keeps its signature and return type `Tuple[ECS, List[AttentionEntry]]`. A private `_hydrate_with_seqs(native=None, *, _source=None)` takes the same arguments, forwards both to both `ECS(native, _source=_source)` constructions (as `durability.py:199, 212` do now), and returns `(ECS, List[Tuple[AttentionEntry, int]])`. `Moneta.__init__` calls it at `api.py:281-283` with `native=native_mode, _source=native_source`, exactly as it calls `hydrate` now. The public method delegates with both arguments and strips the seqs.

**Hydrate writes nothing.** SPEC §7 "Failure cleanup" requires that a failed hydrate "modify no file". So normalization, including the torn-tail repair, is deferred: step 0 does the normalization at the first save, and the first `wal_append` does the repair. That is also why the plan's "seed `applied_seqs` with `wal_applied_seqs ∩ WAL`" step is unnecessary: step 0 drops those lines while the old snapshot is still the one on disk.

### 2.6 Sequence allocation and store-path uniqueness

**Scope: per store lineage, held by the single handle that owns the store's files.**
- rc1's registry locks on `storage_uri` only (`api.py:192-196, 242-248`). But `MonetaConfig` takes `snapshot_path` and `wal_path` independently of `storage_uri` (`api.py:135-144`), and `ephemeral()` mints a fresh URI per call (`api.py:177-180`). So two in-process handles can share one WAL today, each with its own `_lock` and `_next_seq`.
- That would break R1′ three ways:
  - duplicate seqs, where first-wins (§2.5 step 4) drops a real signal, with only a WARNING;
  - one handle's step 3 replace racing the other's open append descriptor, which takes the K path forever on Windows;
  - one handle's `S` subtracting lines the other never applied.
- **Ruling: enforce path uniqueness.** Add a sibling registry `_ACTIVE_STORE_PATHS: set[str]` in `api.py`, holding `os.path.normcase(os.path.realpath(p))` for four paths per handle: `snapshot_path`, `wal_path`, the snapshot tmp (`snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")`, `durability.py:109-111`) and the WAL tmp (`wal_path.with_name(wal_path.name + ".tmp")`, §2.4). If a handle's own four paths are not pairwise distinct, raise `ValueError` (§1.4).
  - Check and add the entries next to the URI check at `api.py:242-248`, before `self._closed = True` (`:250`) and the `try`. Discard them in `close()`, beside `_ACTIVE_URIS.discard` in its `finally` (`api.py:424`), and in the partial-init handler (`api.py:358-367`), in the same `finally` that discards the URI, after `self.durability.close()`. That handler now closes the durability manager first (C3); the store paths must be released only after it, for the same reason the URI is. Because `Moneta._closed` is `True` until construction completes (`api.py:250`), `close()` on a half-built handle returns early, so the partial-init handler is the only place a failed construct releases its paths.
  - On a clash, raise `MonetaResourceLockedError`, naming the path and the fact that it is held.
  - One set holds every kind of path, so a `snapshot_path` that equals another handle's `wal_path`, or a store path that equals another handle's tmp path, is also refused.
  - Not covered: hard links, and aliasing that `realpath` does not resolve. Those stay a stated precondition.
  - **Suites checked for concurrently live handles that share paths** (`git grep -n "wal_path\|snapshot_path" v1.3.0-rc1 -- tests scripts`, then each hit read):
    - **`tests/v5/test_v1_defects.py:313-325`, `test_v1_p11_two_uris_on_one_snapshot_lose_writes`, breaks.** It opens `a` (URI "A") and `b` (URI "B") on the same `shared.json` and `shared.wal`, both live at once, and asserts that `b`'s sleep pass overwrites `a`'s deposit. Under §2.6, `b = Moneta(...)` raises `MonetaResourceLockedError`. This is the intended outcome: P11 is a v1 defect register entry, and the file's docstring (`:5-7`) says such a test "fails, and the register must be updated" when v1 is fixed. **Planned register update (gate 3):** rewrite it as `test_v1_p11_two_uris_on_one_store_are_refused`. `a` constructs; `Moneta(MonetaConfig(storage_uri="B", **kw))` raises `MonetaResourceLockedError`; `a` deposits, runs a sleep pass and closes; a handle on URI "C" then sees exactly `["from A"]`. `test_v5_p11_one_journal_one_owner` is unchanged. The P11 row of `docs/v5/BLUEPRINT.md:55` is updated in the same PR (gate 5).
    - `tests/v5/test_v1_defects.py:148-170`, P6: one handle at a time; unaffected by §2.6. Its outcome under R1′ hydrate is set by §1.2 (unchanged: still raises `ValueError`).
    - `scripts/v5/bench_v5_vs_v1.py:50-70`: the second handle opens after `v1.close()`. Fine.
    - `tests/integration/test_durability_roundtrip.py`: every reopen follows a `close()` or a `with` exit. Fine.
    - `tests/test_twin_substrate.py:42-49`: distinct directories `a/` and `b/`. Fine.
    - `tests/v5/test_compat.py`, `tests/v5/test_half_life.py`: v5 facade handles. The facade registers only its URI in `_v1api._ACTIVE_URIS` (`v5/compat.py:695-699`), and v5 source is out of scope, so it never registers store paths and these tests are unaffected. `test_compat.py:551` also reopens only after a close.
    - **Test files added on this branch after rc1 (revision 5)**, every file under `tests` that `git diff --name-only v1.3.0-rc1 e7325bb` lists and that names `wal_path` or `snapshot_path`: `tests/unit/test_native_handle.py`, `tests/unit/test_native_attention_once.py`, `tests/qualification/test_native_executes.py`, `tests/qualification/test_native_fallback_intentional.py` and the C6 file. Each opens one handle per store at a time (a `with` block or an explicit close before the reopen). The failure-cleanup tests at `test_native_handle.py:728-766` construct again on the same store after a failed construct ("lock was released"), so they also require §2.6's release of the store paths in the partial-init handler. `test_native_attention_once.py:39-70` (SPEC §7 case 1) stays green under R1′: the failed pass writes no snapshot, the WAL keeps exactly one line (its extra `seq` key does not matter to the test's reader at `:31`), and the reopen replays it once.
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
| late landing (path L, revision 5): an entry lands in a swapped-out list after the reducer's snapshot of it | the line is in the WAL; its seq is not recorded | in process: the next pass applies it (carry-over), or nobody does if the next pass also missed it; on reopen: the line, once, unless a save after it was applied recorded its seq | yes, once. The durable state is exact; only in-process timing changes (§2.3) |
| reducer after apply-and-record, at or after `decay_all` raised | old snapshot, full WAL | every line: the old rows lack them | yes, once (SPEC §7 case 1) |
| save step 0, before `os.replace` | original WAL, stray `wal_tmp`, old snapshot | as before the save | yes |
| save step 0, after `os.replace` | normalized WAL, old snapshot | see the proof below | yes |
| save step 0 interrupted after its `os.replace`, process alive (revision 6) | normalized WAL, old snapshot; `_disposition` kept in memory | on a reopen now: as the row above | yes. Each later save of the handle fails the basis check and takes the degraded save (next row) instead of applying the disposition by index to the normalized WAL, until the handle is reopened. Test AL(a). |
| **save step 0 failed (no crash): degraded save** | **original WAL, new keyless snapshot `T_new`**; `_disposition` kept in memory | lines with `ts > T_new` | no double under the clock precondition. Lost: every line whose effect is not in the degraded rows and whose `ts ≤ T_new`, which includes lines a reducer applied in memory after the row build (rc1-equal in class, §2.4). The next save retries step 0 while the WAL still starts with the bytes hydrate read (the basis check, revision 6). |
| **step 1 timed out, step 0 not needed or failed earlier: degraded save** | as the row above (`_disposition` as it stood: kept if non-empty) | as the row above | as the row above |
| **step 1 timed out after step 0 succeeded in the same save: degraded save** (revision 5) | **normalized WAL** (step 0's `os.replace` done), new keyless snapshot `T_new`; `_disposition` **already cleared** | lines with `ts > T_new` | no double under the clock precondition (the §3.3 proof covers a keyless `T_new` over a normalized WAL). The same loss as the rows above. Nothing to retry: the next save starts at step 1. |
| step 1 | none | — | — |
| step 2, before `os.replace` | old snapshot, stray `snapshot.json.tmp`, WAL | as before the save (= test C) | yes |
| **step 2 done, before or during step 3** (including a crash mid-rewrite: `wal_tmp` written partly, not replaced) | **new snapshot (rows include `S`; key = `S`) and the full WAL, including the lines in `S`** | lines `∉ S`, which are pending; the rows lack them, including seqs applied after step 1 | yes. The lines in `S` are filtered, and the next save's step 0 drops them (G, G2). |
| step 3 `os.replace` done, before step 4 | new snapshot, compacted WAL (foreign no-seq lines now carry fresh seqs) | the pending lines, plus each foreign line once | yes. The in-memory `S` is irrelevant after a crash. |
| step 3 failed (no crash) | the same as "step 2 done" | — | yes for R1′, but step 4 is skipped (K). An rc1-reader exposure lasts while the failure persists (§3.5). |

**Proof that step 0 preserves semantics** under the snapshot on disk `(key?, A, T)`:
- **When the old snapshot is on disk** (`T = T_old`):
  - The lines it drops are exactly those the old snapshot already filters out: `seq ∈ A`, timestamp-filtered lines, duplicates, blank and undecodable lines (§1.2). There are no invalid lines in the prefix, because hydrate raised on them.
  - Raw-line indices are stable between hydrate and step 0: appends only add runs after the last one, and the torn-tail repair only terminates the final run (§2.2). Since a trailing empty piece is never a raw line (§1.2), the first append cannot land on an index the disposition covers. The basis check (§2.4 step 0) verifies this lemma at step 0 instead of assuming it, and a WAL that violates it degrades the save (erratum E7).
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
- That fixes a pre-existing rc1 loss too: in rc1, after a backward clock step, new signals get `ts < T_last` and are dropped on any reopen (`durability.py:229`), even with no save in between.
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
- It also fails when the two stamps come from different clocks. `signal_attention` stamps `now` from `moneta.api.time` (`api.py:538`). `snapshot_created_at` comes from `durability.py`'s own `time` import (`durability.py:43, 102`). The load harness patches only `moneta.api.time` (`tests/load/synthetic_session.py:58-62`). If that virtual clock runs ahead of the real one, an applied line has `ts > T`, and every timestamp-judging reader double-applies it.
- Q is extended to model that case (§4.2).

**`time.time()` resolution.** Python ≥ 3.13 on Windows uses `GetSystemTimePreciseAsFileTime`; hython's 3.11 uses the coarse ~15.6 ms clock [I, CPython changelog]. An equal timestamp hits rc1's strict `>` and is **dropped**, never doubled.

**Caller-supplied timestamps: none in v1.**
- `signal_attention(weights)` takes only weights (`api.py:527`). It stamps `now = time.time()` (`api.py:538`).
- The only foreign timestamps come from three places:
  - WAL lines written by hand (test E writes them, `test_attention_snapshot_regression.py:177-182`);
  - the load-test virtual clock, above. R1′ membership removes the dependence once a keyed snapshot exists;
  - v5's `signal_attention(..., t=ts)` (`v5/compat.py:1027`), which is the v5 substrate, not the v1 WAL writer.

### 3.5 Older readers, rollback and roll-forward

**Optional keys do not by themselves make rollback safe.** These are the concrete outcomes. "Clock precondition" is §3.4's "signal clock ≤ snapshot clock".

**Older readers:**
- **rc1:** its replay rule is `timestamp > snapshot_created_at` (`durability.py:229`). It ignores `seq` and the new snapshot keys.
- **v5 migration:** the same rule, with `ts <= snap_ts` skipped (`v5/compat.py:1018-1020`). It also ignores `seq`.

| Sequence | Outcome | Class |
|---|---|---|
| **rc1 store → R1′** | The key is absent, so every line follows the `durability.py:229` rule, the same as rc1. The seed comes from the WAL, or from the random base. Step 0 normalizes at the first save. | **safe** (rc1-equal) |
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
   3. **Verify that the WAL is empty:** the file is absent, or holds zero non-blank lines. R1′ leaves no file when compaction keeps nothing (§2.4 step 3), as rc1 does; an empty file also passes.
   4. If it is not empty, do not switch. Either a signal raced the pass, or compaction failed (the K path leaves the `S` lines in place). Fix the cause, then repeat from step 2.

   Only a verified-empty WAL makes the store indistinguishable from an rc1 store. It is the only way to make R1′ → rc1 lossless.
3. **A store-format marker cannot make rc1 refuse anything.** rc1 is fixed code. It only warns on a `snapshot_version` mismatch and loads anyway (`durability.py:204-210`). A bump would also be a Trigger 2 (`:29-34`). **Refusing a downgrade is unavailable.** The marker's only use is R1′ warning on hydrate when the key is absent but seq lines exist (§2.5 step 8).

---

## 4. Regression tests

**File:** `tests/integration/test_attention_snapshot_regression.py`, Test Engineer.

### 4.1 Already written: B and D

B and D are in the clone at HEAD `e7325bb`, in `tests/integration/test_attention_snapshot_regression.py`: B at `:94-114` and D at `:138-163`, each including its marker line. C6 copied them from the `$S/durab` file and marks both through a helper, `_unresolved(path)` (`:39-47`):

```python
pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "UNRESOLVED DEFECT: undrained attention lost across snapshot/restart "
        f"(path {path}); see {_DEFECT_DOC}"   # _DEFECT_DOC = "docs/design/R1-attention-durability.md" (:36)
    ),
)
```

B is decorated `@_unresolved("B")` and D `@_unresolved("D")`. The R1′ PR removes both decorators, and nothing else in B or D changes. If `_unresolved` then has no user, it goes too. The B and D entries of `KNOWN_DEFECTS` in `tests/conftest.py:283-294`, which feed the "Known unresolved defects" terminal block (SPEC §8), are removed in the same PR; otherwise the block would keep listing two fixed defects.

Source as in the clone (the decorator lines are omitted below), with the shared helpers `_cfg` (`:50-56`) and `_save` (`:59-62`) of the same file; `_save` is `m.durability.snapshot_ecs(m.ecs)`:

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

A, A2, C and E stay as characterization tests. **E stays green under R1′:** its hand-written lines carry no `seq`, so the `durability.py:229` rule still governs them.

### 4.2 New tests, added in the R1′ PR

All are deterministic unless marked otherwise. Each asserts exact counts or bit-equal utilities, never a bare truthiness (commandment 7, `agent-commandments.md:117-119`).

| ID | Scenario | Assertion |
|---|---|---|
| **F** | Non-prefix drain. Allocate seqs 5 and 6, append 6, drain and apply, then append 5. Save and reopen. | 5 replays and 6 does not; `attended_count` equals 1 per signal. |
| **F2** | Consistent read, one reducer. Monkeypatch `apply_attention` to set a `threading.Event` and then wait on a second event, while a save runs on **another** thread. The test releases the second event after the save has observed a token in `_inflight` at least once. **Never run the save on the reducer's thread mid-apply, and never join the save thread from inside the patched apply.** Both deadlock by design, until the spin bound. | The save retried at least once. The snapshot rows and `wal_applied_seqs` agree: no seq without its row effect, and no effect without its seq. `degraded_saves == 0`. |
| **AB** | Liveness and concurrent reducers. Patch `SEQLOCK_READ_TIMEOUT_S` small. (a) Put a token in `_inflight` with no reducer running. (b) Start a second reducer while a first one is mid-apply (registered). (c) Raise `KeyboardInterrupt` from inside `apply_attention`. (c2) Replace `log.applied_seqs` with a `set` subclass whose `update` records and then raises `KeyboardInterrupt`, with `apply_attention` patched to record calls (erratum E4). (e) **Stranded token (revision 5).** Replace `log._inflight` with a `set` subclass whose `discard` raises `KeyboardInterrupt` on its first call only, run a pass (it raises), then run two more sleep passes with a signal before each, and a bare save. Separately, make `discard` raise on its first **two** calls, to strand the token for real. (d) **The revision-3 torn-read interleaving, driven deterministically.** Replace `log._inflight` with a `set` subclass whose `add` blocks on an event, on reducer R1's thread only, so that R1 has passed its entry check but is not yet registered. Start R2 on a second thread: it passes the entry check, registers, drains, and blocks inside a patched `apply_attention`. Release R1: it registers, drains and blocks inside `apply_attention`. Release R2 so that it records and finishes while R1 is still mid-apply. Then run a save on a third thread while R1 is still blocked; finally release R1. Same deadlock warning as F2. | (a) The save returns within the bound, writes a **keyless** snapshot that contains a deposit made just before it, logs ERROR, and `degraded_saves == 1`. (b) The second reducer logs ERROR ("concurrent attention reducer at entry") and **does not raise**: it drains and applies its own swap, as rc1 would, and `run_pass` completes, including prune, staging and the pass's save (revision 5; revision 4 raised here). (c) Afterwards `_inflight` is empty and the epoch has moved; the next save is keyed. (c2) `run_sleep_pass` raises `KeyboardInterrupt`; the seq is recorded; ERROR "torn attention apply" names 1 of 1 drained seq recorded; the apply never ran; `_inflight` is empty; `attended_count` stays 0. (d) While R1 is in flight, the save never accepts a read. It either times out into a keyless snapshot or, if R1 is released during the spin, writes a keyed snapshot whose rows and `wal_applied_seqs` agree exactly. **No keyed snapshot ever holds an R1 effect without R1's seqs.** R1 and R2 each log ERROR "concurrent attention reducer detected" after `decay_all` and **neither raises**. A reopen shows `attended_count` exactly once per signal. (e) With one injected fault, the nested `finally` still removes the token: `_inflight` is empty, the next pass logs no entry ERROR, and the next save is keyed. With two faults the token is stranded, and then: each later sleep pass logs the entry ERROR, **still applies its signal** (`attended_count` rises by exactly one per pass) and reaches its save; every save degrades (`degraded_saves` rises by one per save; keyless snapshot; WAL bytes kept whole); no exception escapes `run_sleep_pass`. A close and reopen clears the token, and the next save is keyed. |
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
| **O** | `wal_append` fails. Cases (a) to (c), then (d) to (f) layered on them: (a) `os.write` raises `OSError` before writing anything; (b) a short write, where the patched write lands half the bytes and returns their count; (c) the write lands all its bytes and then raises. | In each case, `signal_attention` raises `OSError`; `len(m.attention) == 0`; the WAL bytes equal the bytes before the call. A reopen replays nothing from it, and so does a reopen after a further successful append and `close()`. (d) Also patch `os.ftruncate` to fail after (c). The seq is in `_void_seqs`, and after the next save it is in `wal_applied_seqs` and absent from the WAL. (e) Also patch `os.close` to raise `OSError("close failed")` after (a). The exception that escapes is the original write error, not the close's; `_wal_fd is None`; the next append opens a fresh descriptor and succeeds. (f) **Async exception in the failure path (revision 5).** After (c), patch `os.ftruncate` to raise `KeyboardInterrupt`. `signal_attention` raises `KeyboardInterrupt`; `_wal_fd is None` afterwards; the next append reopens the file, and if the leftover line ends without `\n` (simulate with a short write in (b) plus the failing truncate) it writes a terminator first, so the next acknowledged signal is its own raw line and replays exactly once. |
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
| **AD** | `close()` versus an in-flight background save. Make a background save block inside step 1 longer than the join timeout (both patched smaller in the test), then call `close()`. Install a recording `threading.excepthook` for the test. Separately: let `stop_background()` time out on a blocked save, then call `start_background(m.ecs)` before the save finishes, and again after it finishes. | `close()` returns only after that save finishes, and the descriptor is closed after the save's last write. No exception escapes `close()`, **and the recorded excepthook saw nothing**: the thread exits on its own captured event, with no `AttributeError` (revision 5; rc1 `durability.py:250, 268-270` would raise one). After the timed-out stop, `_bg_thread` is still set while the thread is alive; `start_background` then starts no second thread (exactly one `moneta-snapshot` thread is alive), and once the old thread has exited it starts a new one. |
| **Z** | Lineage base. A fresh store with no seq information. | The seed is drawn from the random base: it is a multiple of 2^20 and below 2^53. Two fresh stores get different bases (patch `secrets.randbits` for determinism). |
| **T** (stress, marked `slow`) | Threads for a signal loop, a sleep-pass loop and a save loop for N seconds, then close, reopen and drain. The sleep-pass loop pauses between passes for longer than one row build, so step 1 has quiet gaps (§3.1, "Save starvation"). | The total `attended_count` equals the total number of signals, **and `degraded_saves == 0`**. Late landings (path L) are expected under this load and still count exactly once, in process through the carry-over or at the reopen; the test reports `stragglers_carried`. A degraded save reintroduces the rc1 loss and would make the count assertion meaningless, so it fails the test with its own message, not as a count mismatch. |
| **AE** | Trailing newline, pending disposition. A store whose WAL ends in a terminator (`\r\n` on Windows) and whose hydrate leaves `_disposition` non-empty (for example one legacy no-seq line with `ts > T`). Signal once, save, then simulate a crash (no close; reopen from the files). | The post-hydrate line is at raw index `prefix_len`, not `prefix_len-1`, and step 0 copies it unchanged. After the reopen, the new signal and the legacy line each apply exactly once. Also unit-test the reader: `b"a\r\nb\r\n"` gives two raw lines, `b"a\r\nb"` two, and `b"a\rb\n"` one. |
| **AF** | Closed manager. Close a durable handle, then call `signal_attention`, `durability.wal_append`, `durability.snapshot_ecs(m.ecs)` and `durability.start_background(m.ecs)` through the stale reference. Then open a second handle on the same paths, signal and save, and call the stale `signal_attention` again. | Each call raises `ValueError("durability manager is closed")`. The stale handle's buffer stays empty. The stale calls leave the WAL and snapshot bytes unchanged. The second handle's WAL holds only its own seqs, with no duplicates. |
| **AG** | Async exception after the WAL write. Patch `AttentionLog.append` to raise `KeyboardInterrupt` on its first call. | `signal_attention` raises `KeyboardInterrupt`. The line is in the WAL and its seq is in `_void_seqs`. After the next save the seq is in `wal_applied_seqs` and the line is gone, and a reopen replays nothing. A reopen *before* that save replays it once (the stated residual). |
| **AH** | Parse classes (§1.2). (a) Hydrate over a WAL with a blank line, an undecodable line and an entry line. (b) Hydrate over a WAL with one invalid line each: `"not-a-uuid"`, a `null` weight, a non-object `[1]`. (c) A foreign writer appends an undecodable line and an invalid line after hydrate; then save. (d) A line whose `seq` is `true`, `1.5` or `-1`. | (a) Opens; the entry replays once. (b) Construction raises the original `ValueError`, `TypeError` and `TypeError` respectively (P6 unchanged), releases the lock, and changes no file. (c) Step 3 drops both lines (WARNING for undecodable, ERROR for invalid, each counted), and a reopen succeeds. (d) Treated as no seq: judged by timestamp, then given a fresh seq by step 0. |
| **AI** | **Late landing, path L (revision 5).** Deterministic, independent of how `append` orders its evaluation. Patch `aggregate` (as the reducer imports it) so that, while it runs, it appends one `(AttentionEntry, seq)` item, whose line the test has already written through `wal_append`, to the list the reducer just swapped out (reached through `log._carry`). This is the shape of probe part 1: the entry lands after the reducer's snapshot. Then save, simulate a crash (no close), and reopen. Second case, the probe's own shape: patch `AttentionEntry` to block on the appender thread, run a sleep pass on the main thread while it is blocked, then release it. Same deadlock warning as F2. Third case: as the first, but run a second pass before the save. | First case: after the pass the late seq is **not** in `applied_seqs`; the save's `wal_applied_seqs` does not contain it; the WAL still holds its line after compaction; the reopen replays it exactly once (`attended_count == 1`). Second case: the same, whichever list the entry landed in. Third case: the second pass applies it from the carry-over (`stragglers_carried == 1`, `attended_count == 1` in process), the save records its seq and compacts its line, and the reopen replays nothing. In every case no `attended_count` ends at 0 or 2. |
| **AJ** | **Snapshot key types (revision 5; §1.2, §2.5 steps 1 and 5).** Each case writes a valid store, then edits `snapshot.json`: `wal_applied_seqs` set to `null`, `"abc"`, `{}`, `[1, true]`, `[1, 1.5]`, `[1, -1]`, `[1, 2**53]`, `[1, "2"]`, `[[1]]`; `wal_next_seq` set to `null`, `"x"`, `true`, `-1`, `2**60`; and `wal_next_seq = 2**53 - 5` with a valid `wal_applied_seqs`. | Every store opens; none raises `TypeError` (rc1 opens each of them). Each malformed `wal_applied_seqs` is treated as absent, with one WARNING, and the lines are judged by timestamp. An invalid `wal_next_seq` alone is ignored with a WARNING, and membership still decides replay. The near-limit case logs ERROR and reseeds: the new seed is a multiple of 2^20 below 2^52, and no seq in `A` or in the WAL lies in `[seed, seed + 2**40)`. A signal after the reseed carries a valid seq, and a crash-reopen after a keyed save decides it by membership, not by timestamp (shown with a backward clock step, as in N). With `secrets.randbits` patched to return a colliding base first, the reseed draws again. |
| **AK** | **Absent WAL and the open path (revision 5; §2.2, §2.4 step 3, §2.5 step 2).** (a) A fresh durable store: deposit, save, close, reopen, save. (b) Signal, sleep pass (everything applied), save. (c) A `wal_path` in a directory that does not exist yet; signal. (d) Patch the last-byte read in `wal_append`'s open path to raise `OSError`, then to raise `KeyboardInterrupt`. (e) Delete the WAL file between hydrate and the first save of a store whose `_disposition` is non-empty. | (a) No `FileNotFoundError` anywhere; each save is keyed; no WAL file is created by a save. (b) After the save the WAL file does not exist (rc1's shape). (c) The directory is created and the signal is durable. (d) `signal_attention` raises the original exception; the descriptor was closed (no fd count increase; on Windows a following save's `os.replace` succeeds); the next append succeeds. (e) The save is keyed, `_disposition` is cleared, and no file is created. |
| **AL** | **The step 0 basis (revision 6, cross-review; §2.4 step 0).** (a) A store whose hydrate leaves `_disposition = [None, (s5, False)]`; two signals (`s6`, `s7`); a save whose `os.replace` of the WAL tmp raises `KeyboardInterrupt` right after it replaced the WAL; then two more saves. (b) The same store, with the WAL truncated to its first line, or rewritten in place with the same line count, between hydrate and the first save. | (a) The interrupted save leaves the normalized WAL `[s5, s6, s7]` and the disposition. Each later save fails the basis check and degrades: the WAL is left whole, the snapshot is keyless, `_disposition` is kept, and the step 0 ERROR says the WAL no longer starts with the bytes found at hydrate. Nothing is applied by index to the normalized WAL. (b) The save degrades, and the WAL is left as found. |

**Unchanged, still required:**
- SPEC §7 "Exactly-once attention" cases 1 and 2;
- the three-call-site AST check for `decay_all`.

**Matrix:**
- Every test runs with native `=1`, `=0` and absent (SPEC §1).
- The save and reopen tests are already in every row (`harden_plan.md:414`).
- hython rows are PLANNED, awaiting owner coordination.

---

## 5. fsync and rename ordering: F1, as shipped (revision 6)

Gate 2 chose the per-append tier for Round 4 item 5 (`ROUND4_BRIEF.md:101`: "Decide the attention durability tier: per-op fsync, or group commit"), and `075eb64` implements it. Revision 5 deferred fsync to that decision; Appendix A, revision 6, records the change.

- **Every WAL append is fsynced.** `wal_append` calls `os.fsync` after `os.write`, inside the same `try` and before `ok = True`. A failed fsync takes the §2.2 failure path: truncate back to the pre-append length, close the descriptor, tombstone the seq if the truncate fails. An `OSError` still means "in neither place".
- **Every tmp is fsynced before its `os.replace`:** the snapshot tmp (as in rc1), the step 0 WAL tmp and the step 3 WAL tmp.
- **Directory fsync where supported.** After each `os.replace`, after step 3's unlink and after the open that may create the WAL, `_fsync_dir` fsyncs the directory. It runs only where the platform supports it (`_DIR_FSYNC_SUPPORTED = os.name != "nt"`).
- **Windows has no directory fsync** through the CRT. R1′ keeps the recorded assumption that NTFS (and ReFS) apply metadata operations in order across a power loss, and the power-loss guarantee is stated for local NTFS and ReFS volumes only.
- **Measured cost** (gate 2; CPython 3.14.2, Windows 11, local NVMe, a 149-byte line): `os.write` plus fsync, median 1.16 ms, mean 1.43 ms, p95 2.12 ms per append; about 7 ms per search at SYNAPSE's at most 5 signalled entities; about 1.2 ms more per save for the compaction tmp fsync.
- **Exposure 1 (loss after the compaction rename): closed where fsync reaches stable storage (not on macOS as shipped; see below).** The compaction tmp is fsynced before its rename, so a power loss can no longer persist the rename before the data.
- **Exposure 2 (double apply from rename reordering): closed on POSIX where fsync reaches stable storage (not on macOS as shipped; see below), an assumption on Windows.** Without a directory fsync, a power loss could keep save k+1's snapshot rename while reverting save k's compaction rename, and the next hydrate would replay the `S_k` lines under a snapshot keyed `S_{k+1}`. POSIX now fsyncs the directory after each rename. On Windows the order rests on NTFS's ordered metadata journal, as revision 5 recorded. A power loss shortly after a save can still roll back that save's renames: each file stays whole, but a signal appended after a rolled-back WAL rename is lost (`docs/api.md`, Durability guarantees).
- **macOS: gate 2's `F_FULLFSYNC` constraint is not carried (erratum E1, after the Architect sign-off).** On macOS `os.fsync` does not flush the drive write cache, and `F_FULLFSYNC` is not used, so the POSIX closure of exposures 1 and 2 is stated for filesystems where fsync reaches stable storage. Gate 2 named `F_FULLFSYNC`; it is deferred to a later rc, with the same clause in the `wal_append` and `_fsync_dir` docstrings and a `darwin` branch with its test.
- **Residual, a double fault (revision 6, cross-review).** An `os.fsync` that fails although its data reached the device, followed by a power loss before the truncate-back is durable, replays the rejected line once at the next reopen, although the caller was told the signal failed. Its seq is not tombstoned, because the truncate itself succeeded. It needs a device-level fsync failure and a power loss together; no code change. The `wal_append` docstring states it.
- **Power loss itself is not testable.** `tests/integration/test_f1_fsync.py` checks the call order with a stand-in for `os` and models a power loss in an NTFS-like and in a strict POSIX model.

---

## 6. Review path

| # | Gate | Who | Passes when |
|---|---|---|---|
| 1 | **Architect ruling** (this document) | Architect | §1 is recorded: a **recommendation** that B, D and L are implementation defects the pattern absorbs, not Trigger 2, conditional on R1′ including the §2.3 single-snapshot reducer; the keys are not a format bump; `_apply_lock` is rejected under `ARCH:340`. Since revision 5 the Trigger 2 question is the owner's (gate 2, item 1), because the trigger text matches path L almost word for word. |
| 2 | **Owner gate** (commandment 8, `agent-commandments.md:123-136`: after design, before implementation) | **Joseph Ibrahim** signs | **Ruled 2026-10-18 under the owner's delegation:** item 1 absorbed, item 4 overridden to per-append fsync, item 8 L not pinned (Appendix A rows 1 to 3; erratum E5).<br>He confirms, or overrides, eight things:<br>1. **the ruling, argued again in revision 5 (§1.1 ground 3).** The attention log loses late entries (path L; probe record `<scratch>/harden/runs/R1review-append-race-probe.txt`). That matches "the append-only attention log has a failure mode not anticipated in Round 2" (`MONETA.md:430`, `ARCHITECTURE.md:250`). The Architect recommends ruling it absorbed (`ARCHITECTURE.md:112`): the fix keeps one swap, one reducer, no lock and no CAS, and every entry is still applied exactly once, at the next pass or, in the worst case, at the next reopen. The owner rules either way;<br>2. the §1.4 behaviour changes: WAL-first ordering; the four new raise conditions (shared store paths, including the register update to P11; a mismatched ECS; a closed durability manager; an unreseedable seq allocator, practically unreachable); and the reducer's log-only concurrency detection, which adds **no** raise to `run_pass` or `run_sleep_pass` (§2.3);<br>3. the rollback semantics in §3.5, including the loss labels and the "drain, then verify" procedure;<br>4. the deferral of fsync and of directory-fsync to Round 4 item 5, with §5's recorded rename-ordering assumption;<br>5. **what SYNAPSE's embedder-swap rewrite of `snapshot.json` does with unknown keys**: kept (load-modify-dump, as `test_compat.py:629-632` models) or dropped. That is unverifiable from this clone (§1.5). If dropped, H2's loss applies to every swap;<br>6. that SYNAPSE passes only `m.ecs` to `snapshot_ecs` (or `start_background`) and never rebinds it, so §2.4's `ValueError` cannot fire in production;<br>7. that no SYNAPSE deployment points two live handles at one `snapshot_path` or `wal_path` (§2.6);<br>8. **whether path L is pinned on this branch now.** SPEC §8 names only B and D as known unresolved defects, and `docs/api.md:383-393` describes only those two. L is a v1 defect at rc1 and at HEAD (§0). Pinning it now (a strict xfail in the C6 file, a `KNOWN_DEFECTS` entry in `tests/conftest.py` and a line in the `docs/api.md` note) is a SPEC §8 scope change, so it is the owner's call. If it is not pinned now, the R1′ PR adds test AI, and the release notes name L as fixed by R1′.<br>**If he rules Trigger 2 instead:** the Architect drafts the Round 4 brief, Joseph reviews it before it goes to Gemini Deep Think, and the attention and durability subsystem freezes until the round closes (`ARCHITECTURE.md:253`). |
| 3 | **Implementation, separate PR** off a post-C7 base, never on `harden/native-observability` (SPEC §0) | Persistence: `durability.py`. Substrate: `api.py`, `attention_log.py`. | Each reviews the other's hunk. The change crosses roles, so the Architect reviews spec conformance too (commandment 5, `agent-commandments.md:73-89`; `CLAUDE.md` "Do not cross role boundaries without Architect review"). **Production files:** only `durability.py`, `api.py` and `attention_log.py` change. `consolidation.py` and `src/moneta/v5/` are untouched. **Test files that change** (gate 4, Test Engineer): the C6 regression file (B and D xfails removed); the new §4.2 tests; `tests/unit/test_attention_log.py` (P extends the structural check); and **one planned register update**, `tests/v5/test_v1_defects.py` P11, rewritten to assert the new raise (§2.6). That edit is a v1 register test, not v5 source, and the file's own docstring asks for it. P6 is **not** changed: §1.2 keeps rc1's raise on invalid lines. Also `tests/conftest.py`: the B and D entries of `KNOWN_DEFECTS` (`:283-294`) are removed (§4.1). No other existing test changes. **Ruled:** seqs are recorded before `apply_attention` (gate 3; Appendix A row 1; erratum E5). |
| 4 | **Tests** | Test Engineer (separate builder and breaker, commandment 7) | Removes the B and D xfails, adds the §4.2 tests, and runs every row of the matrix. Run records include HEAD, the `.pyd` sha256 or shim name, the command and the tail (SPEC §1b). |
| 5 | **Docs, same PR** | Documentarian | Fixes the `durability.py:1-23` docstring and `:119`; rewrites the `attention_log.py:11-19` module docstring and the `drain()` docstring (`:76-80`), whose "Entries cannot be lost" proof is false (§2.3); replaces hydrate steps 3 and 4 at `docs/api.md:378-381` and removes the C7 defect note at `:383-393` (and corrects `:395-396`: with no snapshot, WAL attention still replays per `durability.py:199`). Updates the P11 row of `docs/v5/BLUEPRINT.md:55` to say v1 now refuses a second live handle on the same store paths. Adds to the operator card: the §1.4 behaviour changes, the rollback table (including the R1′ → v5 facade → R1′ row and "cut over both interpreters together"), "drain, then verify, before downgrade", and the meaning of the degraded-save and K-path ERROR lines. Nothing is called fixed until gate 4 is green. |
| 6 | **Acceptance** | Architect, then Joseph | All of the following:<br>- B, D and every §4.2 test pass with native on, off and absent;<br>- an rc1 store reopens (H);<br>- an rc1 reader on an R1′ store never double-applies under the clock precondition (Q a-c);<br>- a step 0 failure still persists a new deposit (J);<br>- baselines hold, restated for the R1′ PR: at its base commit, call the counts `N1` (native 1), `N0` (native 0) and `Na + Sa` (absent: passed + skipped). At `v1.3.0-rc1` these were 405, 405 and 347 + 35, and C5-C7 add their own tests before R1′ branches. The R1′ PR must show `N1 + k`, `N0 + k` and `Na + k_a` passed, where `k` counts the new §4.2 tests plus B and D (moving from xfailed to passed) and `k_a` the subset that runs without the wheel. **P11 counts as passing in its rewritten form,** so it does not change `N`. Any other change in the count of pre-existing tests is a regression;<br>- `test_attention_log.py` structural tests and P are green.<br>Then the owner decides on merge or tag (SPEC §0: no agent merges, pushes or tags). |

---

## Appendix A. Review log

Rows for revisions 2 to 4 are kept as written. Their `path:line` citations are at `v1.3.0-rc1`, where they were checked, and some have moved at HEAD `e7325bb` (see the header's anchor map). Revision 5 is at the end.

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

### Revision 5 (review fixes)

Each issue was checked against clone HEAD `e7325bb` with `git show HEAD:<path>` and `sed -n`, and against `v1.3.0-rc1` where the issue concerns rc1. Issue 1 was also checked against the probe record. **No issue was rejected.** Where the adopted fix differs from the one proposed, the row says so and why.

| # | Issue | Verified | Disposition |
|---|---|---|---|
| 1 | **High.** The attention log loses late entries, and revision 4's reducer turns that into a permanent, silent loss on disk; the §1.1 ruling rested on the false claim | **Yes.** `attention_log.py:73` loads `self._buffer.append` before it builds the `AttentionEntry`, whose named-tuple `__new__` is Python-level code; `:82` swaps; `:127-128` reads the swapped list. Probe record `runs/R1review-append-race-probe.txt` at `e7325bb`: part 1 `n_at_drain=0 drained_after=1 buffer_after=0`; part 2, 613 of 200 000 late landings. `attention_log.py` is byte-identical to rc1. Revision 4 §2.3 iterated `pairs` twice (`aggregate`, then `applied_seqs.update`), so a landing between the passes had its seq recorded with no row effect, and save steps 2 and 3 then wrote it into `wal_applied_seqs` and deleted its line. `docs/rounds/round-2.md` has no analysis of the swap, the drain or the GIL. One refinement of the issue's rc1 comparison: in rc1 the WAL line survives only until the next save, and `run_sleep_pass` saves right after the pass (`api.py:581`), so rc1 also loses the entry on disk unless a crash comes first. | **Accepted.** §0 gains the path L evidence and root cause 6. §1.1 is argued again: ground 3 now states the failure, the matching trigger text, the `ARCHITECTURE.md:112` "cannot absorb" test, the Architect's reading (absorbed) and the counter-reading, and the verdict is a recommendation that goes to the owner as gate 2 item 1 with the probe record. §2.3: `_drain_with_seqs()` returns **one tuple**, used for both the aggregate and the seq record, so recorded == applied and a late entry stays `∉ S`, survives compaction and replays on reopen. **Adjusted from the proposal:** instead of carrying `old[len(items):]` at the end of the same pass, the log keeps `_carry = (old, taken)` and the next reducer takes `old[taken:]`. That gives a stalled appender a whole pass interval instead of a few bytecodes, and the pair lives in one attribute, so it is read and written in one step. The residual (an appender stalled past the next pass too) is applied at the next reopen, never lost durably. The docstring rewrite is in gate 5. Test AI drives the late landing deterministically in three cases, including the probe's own part 1 shape. Also added: owner-gate item 8 (whether to pin L as a known unresolved defect now, a SPEC §8 scope question), a crash-table row for path L, and a note on T. Building the item before loading the buffer is recorded as an optional narrowing that nothing relies on. |
| 2 | **Med-high.** The reducer gained two raises that §1.4 and the owner gate do not list, and the stranded-token residual understated the damage | **Yes.** Revision 4's entry check (`if log._inflight: raise`) and the post-`decay_all` clash raise both escape `run_pass` (`consolidation.py:154-156`) and `run_sleep_pass` (`api.py:570`); the clash raise skips prune, staging and the save (`api.py:578-581`) after attention was applied. rc1 raises neither. A token stranded in the `finally` made the entry check fire on every later pass, before draining. | **Accepted, log-only route.** Both checks log at ERROR and never raise (§2.3); §1.3 and §1.4 now say the reducer adds no raise. The `finally` discards the token first, in a nested `try/finally` that repeats the discard, so stranding needs two async exceptions; the epoch store moved after the discard, which correctness does not need (argued in §2.3). The stranded-token residual is corrected: passes keep applying and reach their saves, and every save degrades, with the defect B exposure on a reopen while a keyless snapshot is current. AB(b) and (d) assert no raise; AB(e) covers a one-fault and a two-fault strand. |
| 3 | **Med.** No type rules for `wal_applied_seqs` and `wal_next_seq`; foreign values can refuse a store rc1 opens, or silently restore defect B | **Yes.** Revision 4 §2.5 steps 1 and 5 used `set(snapshot.get(...))` and `max(sources)` unchecked: `null` gives `TypeError` from `set(None)`; a string beside ints gives `TypeError` in `max`; `true` equals 1; a `wal_next_seq ≥ 2**53` makes every new seq "no seq" under §1.2, so new lines fall to the timestamp rule under a keyed snapshot. rc1 ignores both keys (`durability.py:204, 213-214`). | **Accepted, adjusted.** One "valid seq" rule (`type(v) is int`, `0 ≤ v < 2**53`) now covers the WAL `seq`, each element of `wal_applied_seqs`, and `wal_next_seq` (§1.2). **Adjusted:** a `wal_applied_seqs` that is not a list, or has **any** invalid element, is treated as absent (WARNING), rather than keeping its valid elements. Keeping them could double-apply the lines of the mangled ones, and this document prefers a stated loss to a double (reason in §1.2). Valid elements still feed the seed. An invalid `wal_next_seq` is ignored (WARNING). A seed above `2**53 - 2**40` logs ERROR and reseeds from the random base, with the whole window `[base, base + 2**40)` checked disjoint from `A` and the WAL's seqs, up to 64 draws (§2.5 step 5). Test AJ. |
| 4 | **Med.** The `wal_append` open path drops rc1's `mkdir` and can leak the descriptor | **Yes.** `durability.py:146` (unchanged since rc1) creates the WAL's directory; revision 4's open path did not. An exception from `os.fstat`, the last-byte read or the repair write, or an async one, before `_wal_fd = fd` leaked `fd`, which holds the WAL without share-delete, so every later `os.replace` fails on Windows (§3.1). | **Accepted.** `mkdir(parents=True, exist_ok=True)` restored, and everything after `os.open` wrapped in `try/except BaseException: os.close(fd); raise`, with the close guarded (§2.2). Residual stated: a one-bytecode window between `os.open` returning and the `try`. Test AK (c) and (d). |
| 5 | **Med.** A missing WAL is unspecified for step 3, step 0 and hydrate step 2 | **Yes.** rc1 guards with `.exists()` (`durability.py:124, 153`). Read literally, revision 4's step 3 would raise `FileNotFoundError` on a fresh store's first keyed save, take the K path, and make `snapshot_ecs` and `run_sleep_pass` raise. | **Accepted.** An absent WAL has zero raw lines in all three readers (§2.4 steps 0 and 3, §2.5 step 2). Step 3 with nothing to keep writes no tmp and creates no file; it unlinks the WAL if present, which is rc1's on-disk shape; a failed unlink takes the K path. Step 0 over an absent WAL clears `_disposition`; over a WAL shorter than `prefix_len` (a foreign truncation) it is a step 0 failure. "Drain, then verify" now says both shapes pass. Test AK (a), (b) and (e). |
| 6 | **Med.** Citations to current code were stale at the HEAD this doc ships in | **Yes.** `git diff --stat v1.3.0-rc1 HEAD` shows `api.py` +146 and `durability.py` +21 (C3: `2510d10`, `da7ecb4`, `7fc41c9`), plus `ecs.py`, `docs/api.md` (+158, C7), `tests/v5/test_v1_defects.py` (+5) and the new C6 file. `hydrate(self, native=None, *, _source=None)` exists (`durability.py:181-186`). The partial-init handler at `api.py:358-367` closes the manager. `Moneta._closed` is `True` until construction completes (`api.py:250`). | **Accepted.** The header now sets the citation base at HEAD `e7325bb`, with an anchor map (rc1 → HEAD) and a re-check command for a later base. Every body citation to a moved file was re-read and re-based: the issue's list (`229→281`, `273-275→358-367`, `317→424`, `424-431→538-545`, `467→581`) and others it did not list (`durability.py:218→229`, `:257→268`, `:240-243→251-254`; `ecs.py:235-245→312-322`; `docs/api.md:226→351`, `:253-259→378-396`; `test_v1_defects.py` P6 and P11). §2.5 step 10 now forwards both `native` and `_source`. §2.6 places the store-path discard in the partial-init handler's `finally`, after `self.durability.close()`, and notes that `close()` returns early on a half-built handle. §4.1 now quotes the in-tree marker (`raises=AssertionError`) and line ranges, and gate 3 lists the `tests/conftest.py` `KNOWN_DEFECTS` entries. The rows for revisions 2 to 4 keep their rc1 citations, as noted at the top of this appendix. §0 was re-run at `e7325bb` (three records). |
| 7 | **Low-med.** AD's "no exception escapes" is false: a save that spins to the bound outlasts the 5 s join | **Yes.** `SEQLOCK_READ_TIMEOUT_S` (5.0 s) equals the join timeout (`durability.py:268`). `stop_background` then clears `_stop_event` and `_bg_thread` (`:269-270`), and the loop's next `self._stop_event.wait` (`:250`) raises `AttributeError` into `threading.excepthook`; `start_background` (`:244`) could then start a second saver. Pre-existing in rc1, made reachable by the spin. | **Accepted, local-capture route.** `_run` captures the event; `stop_background` clears both attributes only after the thread has exited; `start_background` returns early only while the thread is alive (§2.4, "Background thread shutdown"). Waiting out the spin bound in the join was not chosen: it would lengthen every `close()`, and it would depend on two constants staying in step. AD asserts no excepthook call and never two saver threads. |
| 8 | **Low.** An async exception inside `wal_append`'s handler is not in the residuals | **Yes.** In revision 4, a `KeyboardInterrupt` landing in the `except BaseException` handler before its inner `try` left the line in place and `_wal_fd` set, so the next append wrote after the fragment with no torn-tail check. | **Accepted.** The failure path is now a `finally` keyed on `ok`, whose first statement clears `_wal_fd` (§2.2). The residual is stated in §1.4: a one-statement window before the clear (a torn leftover merges with the next acknowledged line and loses it; a whole one replays once with no tombstone), and a leaked descriptor between the clear and the close (the store stays on the degraded or K path until the process exits). Test O(f). |
| 9 | **Low.** The degraded-save rows are inaccurate | **Yes.** A step 1 timeout after a successful step 0 leaves a normalized WAL and an empty `_disposition`, so "original WAL, `_disposition` kept" and "the next save retries step 0" are both wrong for it. The loss also includes lines applied in memory after the degraded row build: the rows lack them, and their `ts ≤ T_new`. | **Accepted.** §2.4's degraded save now distinguishes the two entries (point 3) and states the loss as every line whose effect is not in the degraded rows and whose `ts ≤ T_new`; "retries step 0" applies to a step 0 failure only. §3.3 splits the step 1 timeout row in two. |

**Held up under review, unchanged in substance:** WAL-first plus seq membership for paths B and D; the save-side consistent read (in-flight set plus epoch); the step 0 semantics proof; the step 3 / step 4 ordering; the K path; the §1.3 rejection of `_apply_lock`; path uniqueness; the rollback table.

**Process note, revision 5.** Design-only. Nothing in the clone was edited, staged or committed by this revision; `git status --porcelain` was empty before and after. The committed copy at `docs/design/R1-attention-durability.md` (commit `a5853e7`) is revision 4 and is now stale relative to this file. Replacing it is the workflow's commit step, not this revision's. Test runs: only the in-tree C6 file, in three rows at `e7325bb`, recorded at `runs/R1design-r5-BD-{native0,native1,absent}.txt` (§0). The path L probe was run by the reviewer, not by this revision. Citations re-read at HEAD `e7325bb` for this revision: `attention_log.py:1-132`; `durability.py:1-60, 70-277`; `api.py:134-145, 160-200, 236-310, 350-430, 525-582`; `ecs.py:289-328`; `consolidation.py:145-165`; `docs/api.md:370-396`; `tests/integration/test_attention_snapshot_regression.py:36-62, 94-184`; `tests/conftest.py:276-295`; `tests/v5/test_v1_defects.py:140, 148-149, 313-314`; `tests/unit/test_attention_log.py:36-70, 110-125`; `tests/unit/test_native_handle.py:365-380, 600-615`; `ARCHITECTURE.md:96-116, 244-256, 336-342`; `MONETA.md:424-434`; `docs/rounds/round-2.md` (searched for swap, GIL, drain, lost, attention, lock).

### Revision 6 (as implemented)

Revision 6 records what the R1′ PR shipped and the rulings that changed revision 5. Gate 2 was decided on 2026-10-18 under the owner's delegation. The Architect conformance review (gate 6, Architect half) of `b7041df`, `14f060f` and `075eb64` against revision 5 returned SOUND-WITH-NITS. The Persistence and Substrate cross-review that gate 3 names, of the PR at its integration tip, returned SOUND-WITH-NITS with one fix-severity finding (rows 9 to 12).

| # | Change | Source | Where |
|---|---|---|---|
| 1 | Seqs are recorded **before** `apply_attention`. | Gate 2 override; the gate 3 ruling on the open choice revision 5 flagged | §2.3 pseudo-code and residuals |
| 2 | Every WAL append is fsynced; every tmp before its `os.replace`; the directory after each rename where the platform supports it. | Gate 2 override: the F1 tier is per append | §5, rewritten |
| 3 | Path L is absorbed by the append-log pattern, not a MONETA.md §9 Trigger 2. L is not pinned (`KNOWN_DEFECTS` is empty); test AI is its regression test. | Gate 2 items 1 and 8 | §1.1, §6 gate 2, §4.2 AI |
| 4 | The reducer's inner `try` opens before `applied_seqs.update`, so an interrupt between the record and the apply is logged. | Review nit; `6040903`, test AB(c2) | §2.3 |
| 5 | Step 0 degrades only on `Exception`, and a `BaseException` escapes it; what the next save retries is bounded by row 9. Step 4 releases `applied_seqs` outside `_lock`. | Review nits; `6db69c7` (docstring and comment) | §2.4 steps 0 and 4 |
| 6 | `_classify` treats any `Exception` from rc1's field parse as invalid. | Review delta | §1.2 table |
| 7 | Citation base `e7325bb` to `a4f2b0b`; in the header's re-check paths only `ecs.py` moved, below the cited lines. | Header re-check command | Header |
| 8 | Local scratch paths replaced by `<scratch>`. | Publication | §0, §6 gate 2, revision 5 process note |
| 9 | Step 0 applies the disposition only to a WAL that still starts with the bytes hydrate read (length and sha256); any other WAL is a step 0 failure, so the save degrades until the handle is reopened. This replaces the raw-line count check. A retry after an interrupt that landed past step 0's `os.replace` no longer applies the disposition by index to the normalized WAL, which dropped a pending, acknowledged line with no ERROR. | Cross-review, fix; `711d7fb`, test AL | §2.4 step 0 and degraded save, §3.3, §4.2 AL |
| 10 | §2.4 says the disposition is kept only until the replace: after it, a failed directory fsync degrades the save with nothing to retry. | Cross-review nit | §2.4 step 0 and degraded save |
| 11 | The normative `wal_append` shows the F1 lines: the directory fsync in the open path and `os.fsync` before `ok = True`. | Cross-review nit | §2.2 |
| 12 | The double-fault residual on the fsync failure path is stated. | Cross-review nit; `3da0053` (docstring) | §5 |
| 13 | A bare `DurabilityManager` that was never hydrated seeds `_next_seq` lazily from the random base at its first allocation or save (`durability.py:556`, `:764`). Unreachable through Moneta; accepted in writing before rc2 (Architect review nit 8). | Architect sign-off, nit; recorded by the erratum | §2.1 |

**Signed off and accepted (2026-10-18).** The Architect signed off this revision at `292105f`, rows 9 to 12 included: SIGNED_OFF, with one fix (the macOS gap in §5) and six nits, no blocker. The re-review of `711d7fb` and `3da0053` returned SOUND-WITH-NITS, with three nits and no fix. The owner accepted the rc2 content (gate 6) on 2026-10-18. Row 13 and the erratum below were added after the sign-off. The cross-review that gate 3 names is done: its fix is row 9, its doc nits are rows 10 to 12, and test AL(a) also closes its coverage nit (no test had pinned a `BaseException` inside step 0).

**Process note, revision 6.** Written from the gate 2 receipts and the Architect review by the builder of the fix commits, not by the Architect. It edits only this document and the status lines of the Round 4 brief. Rows 9 to 12 were added after the cross-review by the builder of `711d7fb` and `3da0053`, not by the Architect. The revision 6 text itself is `b460e78` (as implemented, local paths scrubbed) and `1c42f87` (rows 9 to 12).

### Revision 6 erratum (rc2 recut, after the sign-off)

The Architect's sign-off recommended that its fix and nits ride an erratum in the final rc2 recut rather than gate anything, and the re-review of `711d7fb` and `3da0053` added one doc nit. This erratum applies their doc halves. It changes no code, so the `src_digest` is unchanged.

| # | Change | Source | Where |
|---|---|---|---|
| E1 | The macOS gap is stated: `os.fsync` does not flush the drive write cache there and `F_FULLFSYNC`, which gate 2 named, is not used, so the POSIX closure of exposures 1 and 2 holds only where fsync reaches stable storage. | Architect sign-off, fix (doc half) | §5 |
| E2 | The state table lists `_disposition_basis`, and `_next_seq` is `int \| None` (row 13). | Architect sign-off, nits | §2.1 |
| E3 | The superseded raw-line count rule is gone from step 0; for a present WAL the basis check is the only rule. | Architect sign-off, nit | §2.4 step 0 |
| E4 | Test AB case (c2) and its assertions are in the test table. | Architect sign-off, nit | §4.2 AB |
| E5 | Gate 2 items 1, 4 and 8 and the gate 3 record order read as ruled. | Architect sign-off, nit | §1.1, §6 gates 2 and 3 |
| E6 | Revision 6's own commits are named. | Architect sign-off, nit | Status line, revision 6 process note |
| E7 | The index-stability lemma names the basis check as what verifies it. | Re-review of `711d7fb`, nit | §3.3 |

**Not applied here (code; a later rc):** the macOS `F_FULLFSYNC` branch, with the same clause in the `wal_append` and `_fsync_dir` docstrings; a second basis over the normalized WAL, so that a retry after an interrupt past step 0's `os.replace` continues keyed instead of degrading until the handle is reopened; an invariant comment at the basis assignment.

**Process note, erratum.** Written by the builder of the rc2 recut from the reviewers' stated fixes, not by the Architect. In this document it changes text only.
