# CHANGES: BLUEPRINT_v7.md, v5 reconciliation pass

**Input:** `docs/v7/BLUEPRINT_v7.md` as of branch `v7-native-seams` @ `57a90bc` (last touched by `7ab7a36`), copied to `snap/BLUEPRINT_v7.md` before any edit.
**Output:** `BLUEPRINT_v7.md` beside this file. Nothing inside `C:\Users\User\Moneta` was modified, and no writing git command was run.
**Method:** 79 exact string replacements (`edits.py`), each asserted to occur exactly once in the input, applied by `apply.py`; this file is generated from the same list (`render_changes.py`). `diff -u snap/BLUEPRINT_v7.md BLUEPRINT_v7.md` shows the whole change set. The review log, pass 3 attack log and pass 4 log are untouched; a short "v5 reconciliation log" section is appended at the end.
**Evidence baseline:** every v5 citation is to commit `57a90bc` (read via `git show 57a90bc:<path>` into `snap/v5_57a90bc/`), **not** the working tree. During this pass `src/moneta/v5/model.py`, `src/moneta/v5/substrate.py`, `src/moneta/v5/index.py` and `scripts/v5/mutation_check.py` were modified in the working tree, and `tests/v5/test_dead_records.py`, `scripts/v5/bench_dead_records.py` and `results/bench_v5_dead_records.jsonl` were untracked, all from the concurrent implementation workflow. None of those were used as evidence.

---

## Summary

| What | Count |
|---|---|
| Edits applied | 79 (status 35, answer 10, upgrade 11, add 9, numbers 6, correct 4, downgrade 2, placeholder 2) |
| Claims upgraded to `[V]` (code/tests read) or `[M]` (run or results file) | 14 v5 claims: `revector` body; `consolidate` / `note` bodies; G1-5 single write path; L3; slot filter-then-choose (G2); G2-7 60-spec test (`[V]` + `[M]`); C3; per-event attention order (G3 fold); O7's step order; T1's v5 records (with correction); P1's v5 recall (with correction); I1–I8 (`[V]` + `[M]`); Q2 framing; O24's slot semantics |
| New `[M]` figures added | v5 recall p50/p95 and open time/RSS, oracle vs native (§6, On one screen, `moneta-scan` row, O13); `tests/v5` pass counts (Read this first, §5, §6 test matrix) |
| Claims downgraded (`[A; v6: V]` → `[P]`, contradicted by the code) | 2: G2 "a child can only remove what its parent admits (v5 I5)" and C4's tag |
| Claims corrected in place | 5: T1 (`compact()` edits the journal), P1 (v5 policy is not journaled), G2-10 (λ change may apply forward), §6 seam rule (the quoted wording is v6's, not v5's), O24's default (shape and fallback) |
| `[A]` → RULED (ruling, not verification) | 9 sites: E1 (§7 atomicity, G3 lock collision), E2 (Q4, §7 decay, G2-8), E3 (Q10, §7 concurrency), O27 (SM2, SM3, §6 opener) |
| Open questions answered | 6: **O35** (found, `RULINGS.md:44`), **O24** (v5 code), **O19** (substrate side only), **O1** (ruled), **O2** and **O29** (in substance, by E2's wording; close with the `ARCHITECTURE.md` amendment). O27 was already marked RULED; its default text was updated |
| Placeholders inserted | 33 occurrences of 23 distinct condition IDs |

---

## Placeholder IDs → `RULINGS.md` (at `57a90bc`)

The IDs are this revision's, numbered in `RULINGS.md` order, so the implementation workflow can grep `[[R4: <id> status pending]]` and replace each with a status.

| ID | Ruling | Condition | `RULINGS.md` line | Where the placeholder sits |
|---|---|---|---|---|
| E1-1 | E1 + E2 | migration crash window (journaled completion marker) | :56 | §7 atomicity lock; §8 conditions table |
| E1-B1 | E1 + E2 | checkpoint, open replays only the tail | :58 | §8 |
| E1-B2 | E1 + E2 | re-projection idempotent | :59 | §8 |
| E1-B3 | E1 + E2 | one source of λ | :60 | §8 |
| E1-B4 | E1 + E2 | runtime λ tuning explicit | :61 | §8 |
| E1-B5 | E1 + E2 | timestamp-skew guard | :62 | §8; O7 |
| E1-B6 | E1 + E2 | native decay seam ported to v5 | :63 | §8 |
| E1-P1 | E1 + E2 | CRC-bad final line as torn tail (polish) | :65 | §8 |
| E1-P2 | E1 + E2 | attention durability tier (polish) | :66 | §8 |
| E1-P3 | E1 + E2 | export failure logged, not raised (polish) | :67 | §8 |
| E3-1 | E3 | projection outside the writer lock, ≤ 30 ms stall | :71 | §7 concurrency lock; §8 |
| E3-2 | E3 | export outside the lock, ≤ 30 ms at 10k × 768 | :72 | §7 concurrency lock; §8 |
| E3-3 | E3 | checkpoint or attend coalescing, tested reopen budget | :73 | §7 concurrency lock; §8 |
| E3-B1 | E3 | Windows fsync numbers; group commit or ~700 writes/s recorded | :76 | §8 |
| E3-B2 | E3 | free-threaded stays `[U]`, with a warning | :77 | §7 free-threading lock; §8 |
| E3-B3 | E3 | §5.1 amended: attention visible immediately | :78 | §8 |
| E3-B4 | E3 | SYNAPSE swap re-run on Windows, copy of the 841 store | :79 | §8; mile 0 Done means #3; O19 |
| E4-1 | E4 | recall p95 with 100k dead within 10% of zero dead | :85 | §8 |
| E4-2 | E4 | `erase()` names or invalidates every derived copy | :86 | §8 |
| E4-3 | E4 | semantics, not mechanism | :87 | §8 |
| E4-4 | E4 | O(n²) dedup fix | :88 | §8 |
| HL-1 | half-life | `fold.lam` from the journal; mismatched open raises; read-only opens never append | :94 | G2-10; §8 |
| HL-2 | half-life | first sleep pass after a change is a dry run | :95 | G2-10; §8 |

Commits on the branch name some of these (`279d903`, `57a90bc` → E1-1; `a777287`, `720b3b0` → HL-1/HL-2; `fae3000` → E4-4). Closure was **not** judged: the §8 table records only what the code at `57a90bc` contains, in a separate column.

---

## Numbers checked against the result files

**v5 recall, `results/bench_v5_recall_native.jsonl`** (10k × 384, N = 200, Python 3.14.2, owner workstation):

| Row | index | variant | p50 ms | p95 ms | open s | open RSS MB | note |
|---|---|---|---|---|---|---|---|
| 1 | python | tuple units | 184.208 | 190.704 | 0.846 | 71.07 | also built the journal (`build_s` 16.81); RSS not comparable |
| 2 | python | tuple units | 176.425 | 184.363 | 0.699 | 312.28 | |
| 3 | native | tuple units | 14.025 | 18.752 | 0.764 | 342.27 | |
| 4 | python | tuple units | 178.625 | 185.747 | 0.704 | 312.12 | |
| 5 | native | tuple units | 14.792 | 19.762 | 0.763 | 341.73 | |
| 6 | python | `unit-array` | 187.163 | 194.367 | 0.704 | 193.48 | |
| 7 | native | `unit-array` | 14.291 | 19.067 | 0.792 | 223.82 | |

- **Oracle p95 is 184–194 ms, not 185–194.** Row 2 is 184.363. (The commit message of `88d1f87` also says 185–194.)
- **Native p95 is 18.8–19.8 ms**, "19–20 ms" at integer rounding.
- **The open-RSS drop 312 → 194 MB is not the native seam.** It is the Python index going from tuple units (rows 2, 4) to packed `array('d')` units (row 6; `src/moneta/v5/model.py:181-193`). With the native index the same change is 342 → 224 MB (rows 3, 5 → 7), and the native index holds about 30 MB **more** than the Python one, because it mirrors the vectors into Rust. The commit message of `88d1f87` attributes it correctly ("open RSS 312 -> 194 MB (python index) / 342 -> 224 MB (native)"); the task brief's phrasing does not. The paper says so in §6.
- **D1 on v5 is unmeasured.** No numpy arm P exists for v5. The paper keeps v1's "D1 did not fire" as a v1 fact and admits v5's seam under O27.

**v1 query, `results/bench_query_fair_matrix.jsonl`** (rows 1–16): every figure already in the paper's D1 table matches. Oracle p95 226.635–312.924 (paper 227–313), p50 211.032–288.652 (211–289), RSS 184.81–185.91 (~185); arm P p95 26.553–29.106 (26.6–29.1), p50 8.22–9.75 (8.2–9.8); native scan p95 4.336–4.545 fresh, 8.076–8.187 aged; native scan + decay p95 3.091–3.311 fresh, 6.644–6.674 aged (3.1–6.7), RSS 68.2–69.94 (~69). **No change was needed.**

**`tests/v5` at `57a90bc`** (exported with `git archive` to `run57/`, run with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`; log `pytest_v5_57a90bc.txt`):
- Python 3.14.2, `MONETA_NATIVE=0`: 158 passed. `MONETA_NATIVE=1`: 158 passed.
- hython 21.0.773 (Python 3.11), `MONETA_NATIVE=0`, no wheel: 151 passed, 1 skipped (`tests/v5/test_native_index_parity.py:21`, "could not import 'moneta_native'").
- Hython with the wheel was not run.
- Without `PYTHONPATH=src`, two subprocess tests fail with `ModuleNotFoundError: No module named 'moneta.v5'`: a stale `C:\Python314\Lib\site-packages\moneta` shadows the tree (the brief's cutover step 4 names it). The paper's health check now says so.

---

## Contradictions the owner should see

1. **Scope narrowing is not v5's rule (G2, G2-5, C4).** v5 resolves `include_scopes` / `exclude_scopes` / `exclude_records` by strength, the strongest authored list replacing a weaker one (`src/moneta/v5/policy.py:9-13, :203-207`). A v5 child context can admit a scope its parent does not. v5's I5 tests only the caller's `allowed_scopes` against the resolved policy (`tests/v5/test_conformance.py:223-243`; `substrate.py:550-553`). v7's "a child only narrows" is new behaviour relative to v5, not inherited. The 60-spec resolver test therefore verifies strength-resolved authorization, which is why USD can reproduce it.
2. **O24: v7's default slot shape is not v5's.** v5 has one record id per slot (`policy.py:30-32, :161-166`). If the selection is absent or not admitted, the latest-deposited admitted claim wins (`substrate.py:565-570`), not "empty". Also, the winner is chosen before the zero-vector check, so a direction-less winner hides every other claim in its slot (`substrate.py:572-579`). That may be intended (SYNAPSE's empty-content deposits), but it is worth a look.
3. **v5's policy is host-held and unjournaled (P1, R1).** `Config.policy` / `use_policy` / `PlainPolicyResolver.set_layer` (`substrate.py:208, :1012-1016`; `policy.py:189-196`). A v5 read is pure, but it depends on that state as well as the prefix, with only the fingerprint echoed. R1 (`one_timeline`) is a real change from v5, not a restatement.
4. **v5's cosines are interpreter-dependent (G3-5, V-POOL).** The oracle uses Python `sum()`, which is Neumaier-compensated on 3.12+ and sequential on 3.11 (`index.py:15-19, :38-39`). Scores are bit-identical native vs oracle on one interpreter, but can differ in the last bit between hython 3.11 and Python 3.14. A mixed hython/server deployment over one store can rank a near-tie differently, and a v7 read path built on this index cannot meet G3-5 or V-POOL until it uses one declared summation order.
5. **v5's time rule is the opposite of v7's default (O7, E1-B5).** v5 accepts a host `t` on every write (finiteness only, `substrate.py:487-488`) and takes a fold-side `max(t, anchor_t)` (`model.py:346`). Nothing clamps `t` at append, so the journal is not monotone in `t`. Round 4's timestamp-skew guard (E1-B5) is where that lands.
6. **Free-threading (E3-B2).** The ruling keeps free-threaded Python `[U]` with a warning (`RULINGS.md:77`). v5's docstrings say it "is supported" (`substrate.py:23-24`) and `BEHAVIOR_CHANGES["free_threading"]` says "no GIL assumption" (`compat.py:91`).
7. **G2-10 vs the half-life ruling.** The paper said a retention-λ change "reinterprets past utility". The ruling and v5 allow either mode; `forward` rebases anchors so history keeps the old λ (`model.py:253-263`). Corrected.
8. **"v5's seam rule" is v6's paraphrase.** `docs/v5/BLUEPRINT.md:255-262` names two pure, oracled seams and keeps "Arm P first … Rust only if P misses its gate", which is D1. The words "where it buys speed or a guarantee" appear only in `BLUEPRINT_v6.md:349`. This is moot for standing, because O27 is ruled, but the attribution was wrong. Corrected in §6.
9. **Line drift inside `RULINGS.md`.** E4 condition 4 cites `substrate.py:949`. At `57a90bc` `_known` is at `substrate.py:1093-1103`, after the fix commit `fae3000`. The brief also numbers E3's conditions differently from `RULINGS.md` (`ROUND4_BRIEF.md:322` "E3 condition 6", `:336` "E3 condition 5"; `RULINGS.md` lists 3 blocking + 4 before-5.0.0 items). The placeholder IDs follow `RULINGS.md`.
10. **No `retain`, `import`, `tombstone` or `half_life` kind in v7's G1 table.** v5 journals all four. A note under the G1 table now says where they map and leaves the λ-change and operator-tombstone placement `[P]`.
11. **Paper paths that don't exist.** `docs/rounds/round-4-brief.md` (the brief is `docs/v7/ROUND4_BRIEF.md`) and `docs/rounds/round-4.md` (not written). Done means #1 and #2 are not done at `57a90bc`.

---

## Changes, one by one

Each entry gives the section, the kind of change, the evidence, and the old → new text, verbatim.


| ID | Section | Kind | Evidence |
|---|---|---|---|
| C01 | Read this first (Today) | status | git log: 861bed9 (merge v5), 6f4696a (native seams), 88d1f87 (v5 dot seam); `git log main -1` = 6cf05f5 |
| C02 | Read this first (Today) | numbers | ran `tests/v5` at 57a90bc (git archive to scratch, PYTHONPATH=src): `158 passed` with MONETA_NATIVE=0 and =1, Python 3.14.2 ((session scratch) pytest_v5_57a90bc.txt) |
| C03 | Read this first (Health check) | add | first run without PYTHONPATH: 2 failed (`test_i6_same_journal_same_answers_in_another_process`, `test_second_process_is_refused`) with `ModuleNotFoundError: No module named 'moneta.v5'` from C:/Python314/Lib/site-packages/moneta; ROUND4_BRIEF.md:323 (cutover step 4) |
| C04 | Read this first (Next actions) | status | git ls-tree 57a90bc rust/ (Cargo.lock present); RULINGS.md:44, :48-101; docs/v7/ROUND4_BRIEF.md exists, docs/rounds/round-4.md and round-4-brief.md do not (git ls-tree 57a90bc docs); git status (both root files `??`) |
| C05 | Read this first (Your decisions) | status | RULINGS.md:48-101 |
| C06 | Read this first (Done this week) | status | as C04 |
| C07 | Status | status | RULINGS.md:32-33; git log 861bed9, 88d1f87 |
| C08 | Builds on | status | docs/v5/BLUEPRINT.md at 57a90bc is byte-identical to the owner-supplied scratchpad/v5in/Moneta_v5_BLUEPRINT.md (diff -q) |
| C09 | Loop position | status | this pass |
| C10 | Baseline | status | git diff --stat 6f4696a 57a90bc -- (lib.rs +67, api.py +4/-2, CLAUDE.md); git status (model.py, substrate.py modified) |
| C11 | Tags ([V]) | status | legend extension needed because v5 is now in-repo |
| C12 | Tags ([A; v6: V]) | status | RULINGS.md:44; git log 861bed9 |
| C13 | Rulings | status | RULINGS.md:32-33, :48-101 |
| C14 | On one screen (mile 0) | status | RULINGS.md:48-101; v5 files as cited; git show 57a90bc:CLAUDE.md still lists locks 2-4 unamended |
| C15 | On one screen (Rust) | status | RULINGS.md:32-33 |
| C16 | On one screen (On main, outside v7) | numbers | results/bench_v5_recall_native.jsonl rows 1,2,4,6 (python p95 190.704, 184.363, 185.747, 194.367) and rows 3,5,7 (native p95 18.752, 19.762, 19.067) |
| C17 | On one screen (The one ask) | status | RULINGS.md:48-101, :97 |
| C18 | On one screen (Position) | status | RULINGS.md:101 |
| C19 | G1 event table (revector) | upgrade | src/moneta/v5/substrate.py:956-1010 (revector op, event body :996-1003), model.py:389-400 (_op_revector) |
| C20 | G1 event table (consolidate, note) | upgrade | src/moneta/v5/substrate.py:867-876; model.py:371-372 (_op_consolidate), :402-413 (_op_note) |
| C21 | G1 (v5 kinds with no row) | add | src/moneta/v5/model.py:276-278, :318-335; substrate.py:830-839, :1023-1037 |
| C22 | G1-5 | upgrade | grep `_journal.append\|.rewrite(\|_append(` over src/moneta/v5 at 57a90bc |
| C23 | G2 (Authorization) | downgrade | src/moneta/v5/policy.py:9-13 (docstring: strongest authored opinion, lists replace), :203-207 (resolve picks first layer in chain that authors the field); substrate.py:550-553; tests/v5/test_conformance.py:223-243 (I5 tests are caller-scope only) |
| C24 | G2 (Slot winner) | upgrade | src/moneta/v5/substrate.py:545-557 (filters) then :558-571 (winner among candidates) |
| C25 | G2 (Slot winner, O24 pointer) | answer | src/moneta/v5/policy.py:30-32, :161-166; substrate.py:565-570 |
| C26 | G2-7 | upgrade | tests/v5/test_review_regressions.py:316-327 (range(60)); run `-k random_specs` passed under Python 3.14.2 with C:/Python314/Lib/site-packages/pxr |
| C27 | G2-8 | status | RULINGS.md:55 |
| C28 | G2-9 | answer | as C25 |
| C29 | G2-10 | correct | RULINGS.md:92-97; src/moneta/v5/model.py:246-278 (forward rebases anchors :253-263, reinterpret :264), substrate.py:504-527, :805-829 (dry run) |
| C30 | G3 (fold, v5 order) | upgrade | src/moneta/v5/model.py:337-348; substrate.py:487-488 |
| C31 | G3 (lock collision) | status | RULINGS.md:54-67 |
| C32 | §4 T1 | correct | src/moneta/v5/journal.py:8-23, :105-135, :349-396; RULINGS.md:82 |
| C33 | §4 P1 | correct | src/moneta/v5/substrate.py:208, :663-701, :1012-1016; policy.py:189-196 |
| C34 | §4 C3 | upgrade | as C26 |
| C35 | §4 C4 | downgrade | as C23 |
| C36 | §4 L3 | upgrade | as C22 |
| C37 | §4 SM2 | status | RULINGS.md:32-33 |
| C38 | §4 SM3 | status | RULINGS.md:32-33 |
| C39 | §5 preamble (I1–I8) | upgrade | docs/v5/BLUEPRINT.md:157-168; tests/v5 test names (grep 'def test_'); runs recorded in (session scratch) pytest_v5_57a90bc.txt (158 passed x2; hython 151 passed, 1 skipped: test_native_index_parity.py:21 'could not import moneta_native') |
| C40 | §6 seam-admission rule | correct | docs/v5/BLUEPRINT.md:255-262 (grep -i 'guarantee' finds only :230, unrelated); BLUEPRINT_v6.md:349; RULINGS.md:32-33 |
| C41 | §6 seam-admission rule (timing) | status | RULINGS.md:32-33; src/moneta/v5/index.py:11-19 |
| C42 | §6 moneta-scan row | numbers | results/bench_v5_recall_native.jsonl rows 1,2,4,6: p50 184.208, 176.425, 178.625, 187.163; p95 190.704, 184.363, 185.747, 194.367 |
| C43 | §6 Built so far (v5 row) | add | src/moneta/v5/index.py:11-19, :38-48, :104-126; tests/v5/test_native_index_parity.py:40-106; commit 88d1f87 |
| C44 | §6 Built so far (v5 measured) | numbers | results/bench_v5_recall_native.jsonl rows 1-7 (all fields); scripts/v5/bench_recall_native.py:51-78 (one Substrate per mode, warm-up recall at :60, p95 index :73); commit 88d1f87 message ('open RSS 312 -> 194 MB (python index) / 342 -> 224 MB (native)'); src/moneta/v5/model.py:181-193 |
| C45 | §6 Test matrix | numbers | (session scratch) pytest_v5_57a90bc.txt |
| C46 | §6 Gaps (cross-interpreter, v5) | add | src/moneta/v5/index.py:15-19, :38-39, :123-126 |
| C47 | §6 Q2 | upgrade | src/moneta/v5/journal.py:8-23, :81-135 |
| C48 | §6 Q4 | status | RULINGS.md:54-55; src/moneta/v5/substrate.py:663-701 (recall), :736-743 (manifest), :892-954 (explain); tests/v5/test_conformance.py:274-283 |
| C49 | §6 Q7 | add | src/moneta/v5/substrate.py:733 |
| C50 | §6 Q10 | status | RULINGS.md:69, :77; src/moneta/v5/substrate.py:23-24, :356, :490-502; compat.py:91; tests/v5/test_conformance.py:363-366 |
| C51 | §7 decay lock | status | RULINGS.md:55; docs/v7/ROUND4_BRIEF.md:338 |
| C52 | §7 concurrency lock | status | RULINGS.md:69-79 |
| C53 | §7 atomicity lock | status | RULINGS.md:54-67 |
| C54 | §7 free-threading lock | status | RULINGS.md:77 |
| C55 | §8 mile 0 heading | status | RULINGS.md:48-101; 861bed9 |
| C56 | §8 mile 0 step 0 + conditions table | placeholder | RULINGS.md:48-101 (line numbers per condition); code cells read at 57a90bc as cited; commits 279d903, 57a90bc, a777287, 720b3b0, fae3000 name the conditions they target (closure not judged here) |
| C57 | §8 mile 0 Done means #1-2 | status | git ls-tree 57a90bc docs/rounds (round-1..3 only); git show 57a90bc:CLAUDE.md |
| C58 | §8 mile 0 Done means #3 | status | docs/v5/BLUEPRINT.md:228; ROUND4_BRIEF.md:320 |
| C59 | §8 mile 0 Done means #3 (tail) | placeholder | docs/v5/SYNAPSE_COMPAT.md:5, :13, :50-52 (git show 57a90bc:...) |
| C60 | §8 mile 0 Kill | status | RULINGS.md:48-97 |
| C61 | §8 mile 1 row | status | docs/v7/ROUND4_BRIEF.md; RULINGS.md:48-101 |
| C62 | §9 queue (Now) | answer | RULINGS.md:44 |
| C63 | §9 queue (Round 4 brief) | status | RULINGS.md:32-33, :48-101, :55 |
| C64 | §9 queue (v5 code) | answer | see C69, C70 |
| C65 | §9 O1 | status | RULINGS.md:48-101 |
| C66 | §9 O2 | answer | RULINGS.md:55; src/moneta/v5/model.py:163-164; substrate.py:693 |
| C67 | §9 O7 | answer | src/moneta/v5/model.py:337-348, :346; substrate.py:487-488; RULINGS.md:62 |
| C68 | §9 O13 | numbers | results/bench_v5_recall_native.jsonl open_s: 0.846, 0.699, 0.764, 0.704, 0.763, 0.704, 0.792 |
| C69 | §9 O19 | answer | src/moneta/v5/compat.py:174-196 (sidecar keeps the last two export hashes), :245-255, :386-493; tests/v5/test_compat.py:556-660; docs/v5/SYNAPSE_COMPAT.md |
| C70 | §9 O24 (question) | upgrade | src/moneta/v5/policy.py; substrate.py |
| C71 | §9 O24 (default) | answer | src/moneta/v5/policy.py:30-32, :161-166, :208-210; substrate.py:558-579, :927-936 |
| C72 | §9 O27 | status | RULINGS.md:32-33; src/moneta/v5/index.py:11-19 |
| C73 | §9 O28 | add | src/moneta/v5/substrate.py:344, :767; RULINGS.md:48-101 (no O28 ruling) |
| C74 | §9 O29 | answer | RULINGS.md:55; ROUND4_BRIEF.md:338 |
| C75 | §9 O30 | status | RULINGS.md:69 |
| C76 | §9 O35 | answer | RULINGS.md:35-44; git log 861bed9 |
| C77 | §10 What to attack | add | this pass's findings |
| C78 | Appendix (v5 references) | add | files as listed |
| C79 | End: v5 reconciliation log | add | this pass |

### C01: Read this first (Today) (status)

**Evidence:** git log: 861bed9 (merge v5), 6f4696a (native seams), 88d1f87 (v5 dot seam); `git log main -1` = 6cf05f5

**Old:**

```text
> - **Today:** v1 runs on `main` (`6cf05f5` plus uncommitted work). An optional Rust wheel (`rust/moneta_native`) speeds up `query` with a scan and a decay kernel,
```

**New:**

```text
> - **Today:** v1 is still the default handle. Branch `v7-native-seams` (`57a90bc`) carries v1, the committed native seams (`6f4696a`), and the **v5 reference implementation, merged beside v1** (`src/moneta/v5/`, merge `861bed9`); `main` is still `6cf05f5`. An optional Rust wheel (`rust/moneta_native`) speeds up v1's `query` with a scan and a decay kernel, and v5's `recall` with a dot-product seam,
```

### C02: Read this first (Today) (numbers)

**Evidence:** ran `tests/v5` at 57a90bc (git archive to scratch, PYTHONPATH=src): `158 passed` with MONETA_NATIVE=0 and =1, Python 3.14.2 ((session scratch) pytest_v5_57a90bc.txt)

**Old:**

```text
215 tests green in 4 configurations `[M]`. **Nothing in v7 is built.**
```

**New:**

```text
215 tests green in 4 configurations `[M]`; v5's own suite, `tests/v5`, passes 158 under Python 3.14 with the native seam off and on `[M]`. **Nothing in v7 is built.**
```

### C03: Read this first (Health check) (add)

**Evidence:** first run without PYTHONPATH: 2 failed (`test_i6_same_journal_same_answers_in_another_process`, `test_second_process_is_refused`) with `ModuleNotFoundError: No module named 'moneta.v5'` from C:/Python314/Lib/site-packages/moneta; ROUND4_BRIEF.md:323 (cutover step 4)

**Old:**

```text
red on any native conformance suite is a regression.
```

**New:**

```text
red on any native conformance suite is a regression. Run `tests/v5` with `PYTHONPATH=src`: a stale `site-packages/moneta` without `v5` otherwise breaks its subprocess tests.
```

### C04: Read this first (Next actions) (status)

**Evidence:** git ls-tree 57a90bc rust/ (Cargo.lock present); RULINGS.md:44, :48-101; docs/v7/ROUND4_BRIEF.md exists, docs/rounds/round-4.md and round-4-brief.md do not (git ls-tree 57a90bc docs); git status (both root files `??`)

**Old:**

```text
> - **Next actions:** (1) commit `rust/` and the native-seam changes (the files listed in Baseline), leaving out the two stray root files `attention_log.py` and `test_attention_log_gil_guard.py`; (2) locate the v5 bundle (O35); (3) start mile 2, the Python-only experiment; (4) the Architect drafts the Round 4 brief (`docs/rounds/round-4-brief.md`).
```

**New:**

```text
> - **Next actions:** done since pass 4: `rust/` committed (`6f4696a`, with `Cargo.lock`); the v5 bundle found and merged (O35, `861bed9`); the Round 4 brief drafted (`docs/v7/ROUND4_BRIEF.md`) and **ruled** (`RULINGS.md:48-101`). Now: (1) close Round 4's blocking conditions (§8 mile 0; their status is a placeholder in this paper while the implementation workflow runs); (2) start mile 2, the Python-only experiment; (3) record the rulings in `docs/rounds/round-4.md` and amend `ARCHITECTURE.md` and `CLAUDE.md`'s locks in one PR (neither done at `57a90bc`). The two stray root files `attention_log.py` and `test_attention_log_gil_guard.py` are still untracked and still excluded.
```

### C05: Read this first (Your decisions) (status)

**Evidence:** RULINGS.md:48-101

**Old:**

```text
the queue at the top of §9. Round 4 items come first.
```

**New:**

```text
the queue at the top of §9. Round 4 is ruled; closing its conditions comes first.
```

### C06: Read this first (Done this week) (status)

**Evidence:** as C04

**Old:**

```text
> - **Done this week means:** `rust/` committed; O35 answered; mile 2's harness running; brief in draft.
```

**New:**

```text
> - **Done this week means:** `rust/` committed ✓; O35 answered ✓; Round 4 brief drafted and ruled ✓; mile 2's harness running; Round 4's blocking conditions closed, each with its measured number.
```

### C07: Status (status)

**Evidence:** RULINGS.md:32-33; git log 861bed9, 88d1f87

**Old:**

```text
which this paper calls the seam-admission rule (O27). D1's latency gate did not fire. They were not caused
```

**New:**

```text
which this paper calls the seam-admission rule (O27, now RULED). D1's latency gate did not fire. v5 is now merged beside v1 as reference code (`src/moneta/v5/`), and v5's native dot seam sits under the same rule; neither is v7. They were not caused
```

### C08: Builds on (status)

**Evidence:** docs/v5/BLUEPRINT.md at 57a90bc is byte-identical to the owner-supplied scratchpad/v5in/Moneta_v5_BLUEPRINT.md (diff -q)

**Old:**

```text
with evidence from `docs/v7/pass1_rulings_brief.md`
```

**New:**

```text
with evidence from `docs/v7/pass1_rulings_brief.md`; the v5 reconciliation pass adds the merged v5 (`docs/v5/BLUEPRINT.md`, `src/moneta/v5/`, `tests/v5/`, `results/bench_v5_recall_native.jsonl`) and `docs/v7/ROUND4_BRIEF.md`
```

### C09: Loop position (status)

**Evidence:** this pass

**Old:**

```text
the `F-` rows of the Pass 4 log record the corrections.
```

**New:**

```text
the `F-` rows of the Pass 4 log record the corrections. A **v5 reconciliation pass** followed: every v5-dependent claim was re-checked against the merged v5 code, tests and results at `57a90bc`, and Round 4's rulings were applied (v5 reconciliation log, at the end).
```

### C10: Baseline (status)

**Evidence:** git diff --stat 6f4696a 57a90bc -- (lib.rs +67, api.py +4/-2, CLAUDE.md); git status (model.py, substrate.py modified)

**Old:**

```text
**Baseline:** `main` at `6cf05f5` (`git describe`
```

**New:**

```text
**Baseline (v5 reconciliation pass):** branch `v7-native-seams` at `57a90bc`. Every v5 citation (`src/moneta/v5/…`, `tests/v5/…`, `scripts/v5/…`, `results/bench_v5_recall_native.jsonl`, `docs/v5/…`) is to that **commit**, not the working tree: `src/moneta/v5/model.py` and `substrate.py` were being modified by a concurrent implementation workflow during this pass. Pass 4's working-tree files are now committed (`6f4696a`, `6cb6966`, `42a0368`); "on `main`" in pass-4 text means that v1-line code, which is on `v7-native-seams`, not on `main`. Since then `rust/moneta_native/src/lib.rs` grew by 67 lines (`88d1f87`, v5 dot seam: anchors after `:36` moved), `src/moneta/api.py` by 2 (`d4f9fd4`, Round 4 F1: the `signal_attention` docstring at `:416-420` grew, so anchors from `:421` on moved by +2) and `CLAUDE.md` changed; pass-4 anchors into those three files are to the pass-4 tree and were not re-anchored.
**Baseline (pass 4):** `main` at `6cf05f5` (`git describe`
```

### C11: Tags ([V]) (status)

**Evidence:** legend extension needed because v5 is now in-repo

**Old:**

```text
- `[V]`: verified here. That means one of two things. Either the named v1 source or `ARCHITECTURE.md` was read (at `6cf05f5`, or in the working tree for the working-tree files named in Baseline), with the file:line given and nothing run. Or the v7 ruling files were read.
```

**New:**

```text
- `[V]`: verified here. That means one of three things. Either the named v1 source or `ARCHITECTURE.md` was read (at `6cf05f5`, or in the working tree for the working-tree files named in Baseline), with the file:line given and nothing run. Or the v7 ruling files were read. Or (v5 reconciliation pass) the named v5 source, test or doc was read at `57a90bc`, with the file:line given and nothing run.
```

### C12: Tags ([A; v6: V]) (status)

**Evidence:** RULINGS.md:44; git log 861bed9

**Old:**

```text
v5 (an unmerged bundle; no `v5` branch exists locally), the RSI-in-USD toy package, SYNAPSE's source, and the 8 September decisions are all absent from this repo.
```

**New:**

```text
The RSI-in-USD toy package, SYNAPSE's source, v5's 2-vCPU container measurements and the 8 September decisions are absent from this repo. **v5 itself is now merged** (`src/moneta/v5/`, `861bed9`): every v5 claim in this paper was re-checked against it, rows the code confirms carry `[V]` (or `[M]`), and rows it contradicts are corrected in place (v5 reconciliation log).
```

### C13: Rulings (status)

**Evidence:** RULINGS.md:32-33, :48-101

**Old:**

```text
- **R2** `recall_half_life` and **R3** `owner_labels`: carried as `[A]`.
- **Mile 0** (v5's E1–E4 and the half-life call): **unruled**. Every ruling rests on the `[A]` that v5 lands.
```

**New:**

```text
- **R2** `recall_half_life` and **R3** `owner_labels`: carried as `[A]` (Round 4 leaves R2 unflipped, `RULINGS.md:97`).
- **O27** (seam-admission rule): RULED, confirmed (`RULINGS.md:32-33`).
- **Mile 0 / Round 4** (v5's E1–E4 and the half-life call): **RULED 2026-10-15** (`RULINGS.md:48-101`). E1 + E2: for v5, with conditions. E3: for v5, closure gated. E4: semantics only, gated; `compact()` not ratified. Half-life: the journal owns λ; each change is an explicit, journaled choice between reinterpreting and applying forward. Each ruling **closes** only when its blocking conditions are implemented and measured (`RULINGS.md:101`); §8 lists them, with status placeholders. F1 is recorded as factual ground: v1's `signal_attention` flushes the WAL but does not fsync it (`RULINGS.md:52`).
```

### C14: On one screen (mile 0) (status)

**Evidence:** RULINGS.md:48-101; v5 files as cited; git show 57a90bc:CLAUDE.md still lists locks 2-4 unamended

**Old:**

```text
**So mile 0 is a MONETA.md §9 Round 4 escalation, not a merge.** E1, E2 and E3 overturn decisions that `CLAUDE.md` lists under "Locked decisions — do not re-open". E4 reverses §6 prune semantics. The Architect drafts the brief, and the owner reviews it (§8).
```

**New:**

```text
**So mile 0 was a MONETA.md §9 Round 4 escalation, not a merge.** E1, E2 and E3 overturn decisions that `CLAUDE.md` lists under "Locked decisions — do not re-open". E4 reverses §6 prune semantics. The brief went out (`docs/v7/ROUND4_BRIEF.md`) and the owner **ruled all five toward v5, with conditions** (`RULINGS.md:48-101`; §8). The table above still describes v1, the default handle; the locks are not yet amended in `ARCHITECTURE.md` or `CLAUDE.md` at `57a90bc`. v5, merged beside v1 (`861bed9`), already does what v7 assumes on four rows `[V]`: its reads write nothing (`src/moneta/v5/substrate.py:663-701, :736-743, :892-954`), its journal is the authority and the index is rebuilt from it (`journal.py:1-6`; `index.py:1-5`), every write is ordered under one lock (`substrate.py:356, :490-502`), and prune appends a `retain` tombstone (`substrate.py:830-841`; `model.py:364-369`). On the fifth it half does: the journal only grows, except that `compact()` rewrites erased bytes in place (`journal.py:349-396`), which E4 did not ratify.
```

### C15: On one screen (Rust) (status)

**Evidence:** RULINGS.md:32-33

**Old:**

```text
rest on the v5/v6 seam-admission rule (§6), whose standing as a constraint is O27:
```

**New:**

```text
rest on the seam-admission rule (§6), which the owner confirmed as a project constraint (O27, RULED, `RULINGS.md:32-33`):
```

### C16: On one screen (On main, outside v7) (numbers)

**Evidence:** results/bench_v5_recall_native.jsonl rows 1,2,4,6 (python p95 190.704, 184.363, 185.747, 194.367) and rows 3,5,7 (native p95 18.752, 19.762, 19.067)

**Old:**

```text
It is also 4–9× tighter than arm P at p95 with 2.7× less store RSS. Neither is a v7 seam (§6, "Built so far").
```

**New:**

```text
It is also 4–9× tighter than arm P at p95 with 2.7× less store RSS. Neither is a v7 seam (§6, "Built so far"). v5's `recall` gained the same kind of seam: a native dot product behind `ExactIndex.cosines`, bit-identical to v5's own Python loop on the same interpreter, which takes v5 recall p95 from 184–194 ms to 18.8–19.8 ms at 10k × 384 `[M]` (§6 "Built so far"). D1 was not measured on v5: no numpy arm P exists on v5's facade.
```

### C17: On one screen (The one ask) (status)

**Evidence:** RULINGS.md:48-101, :97

**Old:**

```text
In parallel, the Architect drafts the Round 4 brief under the role `CLAUDE.md` already assigns, and the owner reviews it before it goes out. That is not a second approval. Mile 2's report becomes evidence in the round.
```

**New:**

```text
In parallel, Round 4, now ruled (`RULINGS.md:48-101`), is closed condition by condition (§8 mile 0). Mile 2's report did not reach the round; it becomes evidence for R2 and R3.
```

### C18: On one screen (Position) (status)

**Evidence:** RULINGS.md:101

**Old:**

```text
**Position.** Mile 1 of 6, in v6/RULINGS numbering, which is kept unchanged. Mile 0 is not done.
```

**New:**

```text
**Position.** Mile 1 of 6, in v6/RULINGS numbering, which is kept unchanged. Mile 0 is **ruled** (Round 4) but not **closed**: its blocking conditions are open or unconfirmed (§8).
```

### C19: G1 event table (revector) (upgrade)

**Evidence:** src/moneta/v5/substrate.py:956-1010 (revector op, event body :996-1003), model.py:389-400 (_op_revector)

**Old:**

```text
| `revector` | per record `(old C_v → new C_v)` and the new embedder pin; content otherwise as in v5 `[A; v6: V]` |
```

**New:**

```text
| `revector` | per record `(old C_v → new C_v)` and the new embedder pin; content otherwise as in v5: one event carrying a new vector for every recallable record, possibly at a new `dim`, with `unembedded` naming any left without one; tombstoned records lose their vector `[V, src/moneta/v5/substrate.py:956-1010; model.py:389-400]` |
```

### C20: G1 event table (consolidate, note) (upgrade)

**Evidence:** src/moneta/v5/substrate.py:867-876; model.py:371-372 (_op_consolidate), :402-413 (_op_note)

**Old:**

```text
| `consolidate`, `note` | as in v5 `[A; v6: V]` |
```

**New:**

```text
| `consolidate`, `note` | as in v5: one `consolidate{ids, target, batch}` per successfully projected batch; `note` is provenance only, except that a legacy `half_life_change` note replays as a reinterpret change `[V, src/moneta/v5/substrate.py:867-876; model.py:371-372, :402-413]` |
```

### C21: G1 (v5 kinds with no row) (add)

**Evidence:** src/moneta/v5/model.py:276-278, :318-335; substrate.py:830-839, :1023-1037

**Old:**

```text
| `disclose` | which held-out figure was shown, and for which window | the substrate, when the owner asks | no |
```

**New:**

```text
| `disclose` | which held-out figure was shown, and for which window | the substrate, when the owner asks | no |

**v5 kinds with no row here `[V]`.** v5 also journals `import` (a v1 row with its anchor, attended count and state, `src/moneta/v5/model.py:318-335`), an operator `tombstone` (`substrate.py:1023-1037`), `retain` (one per sleep pass, even when empty, `substrate.py:830-839`; v7's `retention`) and `half_life` (an explicit λ change naming its mode, `model.py:276-278`; Round 4 half-life ruling). Under format 7, `import` becomes `deposit` events ("Migration into format 7"). Where an operator tombstone and a journaled λ change sit in G1 (their own kinds, or a `govern{const, amend}` that names the mode, G2-10) is `[P]`, not yet drawn.
```

### C22: G1-5 (upgrade)

**Evidence:** grep `_journal.append|.rewrite(|_append(` over src/moneta/v5 at 57a90bc

**Old:**

```text
- **G1-5 One writer.** Only the substrate appends. The tuner never holds a handle (v6 L3, `[A; v6: V]` for v5).
```

**New:**

```text
- **G1-5 One writer.** Only the substrate appends. The tuner never holds a handle (v6 L3). For v5 the single write path is `[V]`: every append goes through `Substrate._append` (`src/moneta/v5/substrate.py:490-502`; the only `_journal.append` call is `:492`), `compact()` rewrites through `_journal.rewrite` (`:1090`), and the facade's migration and snapshot guard call the same `_append` (`compat.py:431, :465, :860, :906, :939`). The tuner half is `[P]`: v5 has no tuner.
```

### C23: G2 (Authorization) (downgrade)

**Evidence:** src/moneta/v5/policy.py:9-13 (docstring: strongest authored opinion, lists replace), :203-207 (resolve picks first layer in chain that authors the field); substrate.py:550-553; tests/v5/test_conformance.py:223-243 (I5 tests are caller-scope only)

**Old:**

```text
A child can only remove what its parent admits (v5 I5, `[A; v6: V]`).
```

**New:**

```text
A child can only remove what its parent admits `[P]`. **That is not v5's rule** `[V]`: v5 resolves `include_scopes`, `exclude_scopes` and `exclude_records` by strength, the strongest authored list replacing a weaker one (`src/moneta/v5/policy.py:9-13, :203-207`), so a v5 child context can admit a scope its parent does not. v5's I5 is narrower: the caller's `allowed_scopes` intersect with the resolved policy and can only narrow it (`substrate.py:550-553`; `tests/v5/test_conformance.py:223-243`).
```

### C24: G2 (Slot winner) (upgrade)

**Evidence:** src/moneta/v5/substrate.py:545-557 (filters) then :558-571 (winner among candidates)

**Old:**

```text
v5 removes records the caller may not see before a slot's winner is picked, so the caller's scopes change slot outcomes (`BLUEPRINT_v6.md:95`) `[A; v6: V]`.
```

**New:**

```text
v5 removes records the caller may not see (and tombstoned, erased, scope-excluded and record-excluded ones) before a slot's winner is picked, so the caller's scopes change slot outcomes `[V, src/moneta/v5/substrate.py:545-571]`.
```

### C25: G2 (Slot winner, O24 pointer) (answer)

**Evidence:** src/moneta/v5/policy.py:30-32, :161-166; substrate.py:565-570

**Old:**

```text
What a slot preference is (a record id, an ordered list, a rule) and what a slot resolves to when no entry is admitted are O24.
```

**New:**

```text
What a slot preference is and what a slot resolves to when its preference is not admitted were O24; v5's code answers both (O24): one record id per slot, and otherwise the latest-deposited admitted claim wins.
```

### C26: G2-7 (upgrade)

**Evidence:** tests/v5/test_review_regressions.py:316-327 (range(60)); run `-k random_specs` passed under Python 3.14.2 with C:/Python314/Lib/site-packages/pxr

**Old:**

```text
Tags: `[A; v6: V]` without self (v5's 60-spec test); `[P]` with self and for the split.
```

**New:**

```text
Tags: without self, `[V]` for v5's test (60 random specs; plain and USD `semantic()` and fingerprint equal for every context, `tests/v5/test_review_regressions.py:316-327`) and `[M]` (it passes under Python 3.14 with `pxr`, `tests/v5` at `57a90bc`). v5 resolves every field, scopes included, by strength (above), so that test covers strength-resolved authorization, not v7's flattened intersection. `[P]` with self and for the split.
```

### C27: G2-8 (status)

**Evidence:** RULINGS.md:55

**Old:**

```text
Whether `ARCHITECTURE.md:90`'s "no fourth evaluation point" admits such a view is a question for Round 4 (O2), not a local call.
```

**New:**

```text
Whether `ARCHITECTURE.md:90`'s "no fourth evaluation point" admits such a view is a question for Round 4 (O2), not a local call. Round 4 replaced the count: "Three evaluation points" becomes "zero mutation points; state changes only through journaled events" (`RULINGS.md:55`). A pure recall view mutates nothing, so O2 is answered in substance; it closes when `ARCHITECTURE.md` is amended to say so.
```

### C28: G2-9 (answer)

**Evidence:** as C25

**Old:**

```text
minus `exclusions(c)`. Shape and empty-slot fallback: O24.
```

**New:**

```text
minus `exclusions(c)`. Shape and empty-slot fallback: O24 (v5's answer: one id; otherwise the latest admitted claim; v7's choice is the owner's).
```

### C29: G2-10 (correct)

**Evidence:** RULINGS.md:92-97; src/moneta/v5/model.py:246-278 (forward rebases anchors :253-263, reinterpret :264), substrate.py:504-527, :805-829 (dry run)

**Old:**

```text
Changing it reinterprets past utility, so it is a held, history-writing change that a pointer move can't undo.
```

**New:**

```text
Changing it is a held change that a pointer move can't undo. Under Round 4's half-life ruling the journal owns λ, and each change is an explicit, journaled, owner-authorised choice between **reinterpreting** history (the new λ applies from each record's last anchor) and applying it **forward** (records are rebased at the change, so earlier decay keeps the old λ) (`RULINGS.md:92-97`). v5 implements both modes and holds the first sleep pass after a change as a dry run `[V, src/moneta/v5/model.py:246-278; substrate.py:504-527, :805-829]`. That the `amend` carries the mode is `[P]`. [[R4: HL-1 status pending]] [[R4: HL-2 status pending]]
```

### C30: G3 (fold, v5 order) (upgrade)

**Evidence:** src/moneta/v5/model.py:337-348; substrate.py:487-488

**Old:**

```text
v6's "decay with the floor, add the weight, clamp to 1" (`BLUEPRINT_v6.md:224`) is v5's per-event order `[A]`, and it is **not** v1's.
```

**New:**

```text
v6's "decay with the floor, add the weight, clamp to 1" (`BLUEPRINT_v6.md:224`) is v5's per-event order `[V, src/moneta/v5/model.py:337-348]`: per record in an `attend` event (ids sorted), `u = decay_value(anchor_u, anchor_t, floor, λ, t)`, then `u + w` clamped to 1, then `anchor_t = max(t, anchor_t)` and `attended += 1`. It is **not** v1's. v5's time rule is that fold-side `max`; v5 does not clamp `t` at append (`substrate.py:487-488` takes a host `t` after a finiteness check) (O7).
```

### C31: G3 (lock collision) (status)

**Evidence:** RULINGS.md:54-67

**Old:**

```text
As drawn, G3 **depends on E1 being ruled for at mile 0** `[A]`. If E1 is ruled against, G3 is redrawn with the index as a second authority (§8).
```

**New:**

```text
As drawn, G3 **depends on E1 being ruled for at mile 0**. **E1 was ruled for** (`RULINGS.md:54`), so G3 stands as drawn and is not redrawn with a second authority. E1's conditions still gate the cutover (§8).
```

### C32: §4 T1 (correct)

**Evidence:** src/moneta/v5/journal.py:8-23, :105-135, :349-396; RULINGS.md:82

**Old:**

```text
| G1-1, G1-7 | `[A]` records (v5) · `[P]` chain |
```

**New:**

```text
| G1-1, G1-7 | `[V]` v5 records: append-only, CRC-framed, gap-free `seq` (`src/moneta/v5/journal.py:8-23, :105-135`), not hash-linked, and `compact()` rewrites events in place (`journal.py:349-396`; not ratified, E4) · `[P]` chain |
```

### C33: §4 P1 (correct)

**Evidence:** src/moneta/v5/substrate.py:208, :663-701, :1012-1016; policy.py:189-196

**Old:**

```text
| G2-1 | `[A]` (v5 `recall`, `BLUEPRINT_v6.md:95`) · **false in v1** `[V, api.py:399-401]`; binding open (O16) |
```

**New:**

```text
| G2-1 | v5 `recall` `[V]`: writes nothing; takes (embedding, limit, context, allowed scopes, t) and echoes (seq, t, context, policy fingerprint) (`src/moneta/v5/substrate.py:663-701`). Its policy, though, is host-held state that v5 does not journal (`Config.policy`, `use_policy`, `substrate.py:208, :1012-1016`; `policy.py:189-196`), so a v5 read depends on the prefix **plus** that policy; R1 moves it into the journal · **false in v1** `[V, api.py:399-401]`; binding open (O16) |
```

### C34: §4 C3 (upgrade)

**Evidence:** as C26

**Old:**

```text
| G2-7 | `[A; v6: V]` / `[P]` |
```

**New:**

```text
| G2-7 | `[V]` without self (v5's 60-spec test, G2-7) / `[P]` |
```

### C35: §4 C4 (downgrade)

**Evidence:** as C23

**Old:**

```text
| G2-5, G2-9 | `[A; v6: V]` (v5 I5) · `[P]` here |
```

**New:**

```text
| G2-5, G2-9 | `[P]`; **not** v5's rule: v5's I5 is caller-scope narrowing only, and v5 resolves context scopes by strength `[V, src/moneta/v5/policy.py:203-207; substrate.py:550-553]` |
```

### C36: §4 L3 (upgrade)

**Evidence:** as C22

**Old:**

```text
| **L3** | Only the substrate writes the journal | G1-5 | `[P]`; `[A; v6: V]` |
```

**New:**

```text
| **L3** | Only the substrate writes the journal | G1-5 | `[P]`; v5's single write path `[V]` (G1-5) |
```

### C37: §4 SM2 (status)

**Evidence:** RULINGS.md:32-33

**Old:**

```text
| — | `[P]`; v5/v6 seam rule `[A; v6]` (`BLUEPRINT_v6.md:349`), not D1 (O27) |
```

**New:**

```text
| — | `[P]`; seam rule RULED (O27, `RULINGS.md:32-33`), not D1 |
```

### C38: §4 SM3 (status)

**Evidence:** RULINGS.md:32-33

**Old:**

```text
| — | `[P]`; v5/v6 seam rule `[A; v6]`, not D1 (O27) |
```

**New:**

```text
| — | `[P]`; seam rule RULED (O27), not D1 |
```

### C39: §5 preamble (I1–I8) (upgrade)

**Evidence:** docs/v5/BLUEPRINT.md:157-168; tests/v5 test names (grep 'def test_'); runs recorded in (session scratch) pytest_v5_57a90bc.txt (158 passed x2; hython 151 passed, 1 skipped: test_native_index_parity.py:21 'could not import moneta_native')

**Old:**

```text
v5's invariants I1–I8 still apply `[A; v6: V]`.
```

**New:**

```text
v5's invariants I1–I8 still apply. Each is a named test (`docs/v5/BLUEPRINT.md:157-168`; `tests/v5/test_conformance.py`, `test_review_regressions.py`) `[V]`, and `tests/v5` passes at `57a90bc`: 158 under Python 3.14 with the native seam off and on, 151 + 1 skipped (the native-parity module, no wheel) under hython 21.0.773 `[M]`. Two read differently from v7: I5 is caller-scope narrowing only (G2), and I8, "ordering without a GIL", is tested under the GIL, so free-threaded Python stays `[U]` (E3, `RULINGS.md:77`).
```

### C40: §6 seam-admission rule (correct)

**Evidence:** docs/v5/BLUEPRINT.md:255-262 (grep -i 'guarantee' finds only :230, unrelated); BLUEPRINT_v6.md:349; RULINGS.md:32-33

**Old:**

```text
**The seam-admission rule `[A; v6]`, not D1.** v6 §10 reports v5's rule: "Rust goes behind a pure seam with an exact oracle, where it buys speed or a guarantee" (`BLUEPRINT_v6.md:349`). v7 adds bit-exact conformance on shared fixtures and a measured justification `[P]`. The referee, the kernel, the verifier and the bindings rest on this rule, not on D1; whether the owner adopts it as a constraint, given that mile 4 commits to the referee and kernel on its basis, is O27.
```

**New:**

```text
**The seam-admission rule, RULED (O27), not D1.** v6 §10 reports v5's rule: "Rust goes behind a pure seam with an exact oracle, where it buys speed or a guarantee" (`BLUEPRINT_v6.md:349`). The merged v5 blueprint does not say this in those words `[V]`: it names two pure, oracled seams and keeps the 8 September order, "Arm P first … Rust only if P misses its gate" (`docs/v5/BLUEPRINT.md:255-262`), which is D1. The owner confirmed the broader rule as a project constraint on 2026-10-15 (`RULINGS.md:32-33`), so its standing no longer rests on that attribution. v7 adds bit-exact conformance on shared fixtures and a measured justification `[P]`. The referee, the kernel, the verifier and the bindings rest on this rule, not on D1.
```

### C41: §6 seam-admission rule (timing) (status)

**Evidence:** RULINGS.md:32-33; src/moneta/v5/index.py:11-19

**Old:**

```text
**O27's "before mile 4" timing has been overtaken twice:**
```

**New:**

```text
**O27's "before mile 4" timing was overtaken before it was ruled** (v5's dot seam, below, is a third instance):
```

### C42: §6 moneta-scan row (numbers)

**Evidence:** results/bench_v5_recall_native.jsonl rows 1,2,4,6: p50 184.208, 176.425, 178.625, 187.163; p95 190.704, 184.363, 185.747, 194.367

**Old:**

```text
v5 measured 161 ms **median** on a 2-vCPU container `[A; v6: V]`.
```

**New:**

```text
v5 measured 161 ms **median** on a 2-vCPU container `[A; v6: V]` (stated at `docs/v5/BLUEPRINT.md:242`, not re-run here). On the owner workstation v5's pure-Python `recall` measured 176–187 ms p50 and 184–194 ms p95 at 10k × 384 `[M]` (`results/bench_v5_recall_native.jsonl`).
```

### C43: §6 Built so far (v5 row) (add)

**Evidence:** src/moneta/v5/index.py:11-19, :38-48, :104-126; tests/v5/test_native_index_parity.py:40-106; commit 88d1f87

**Old:**

```text
| `tests/unit/test_native_decay_parity.py`: bit-identical incl. clamp, floor, NaN, subnormal; **same platform `exp` only** (Exactness) | built under the seam rule (O27), not D1; its marginal cost is now bounded by the fair matrix (about 1–1.5 ms p95 at 10k, below) |
```

**New:**

```text
| `tests/unit/test_native_decay_parity.py`: bit-identical incl. clamp, floor, NaN, subnormal; **same platform `exp` only** (Exactness) | built under the seam rule (O27), not D1; its marginal cost is now bounded by the fair matrix (about 1–1.5 ms p95 at 10k, below) |
| **v5 dot seam** (seam rule, O27; v5 reference code, not the default handle) | `ExactIndex.cosines` (`src/moneta/v5/index.py:104-126`) mirrors v5's unit vectors into `moneta_native.ScanIndex` and calls `ScanIndex.dots` with a sum that reproduces the interpreter's own `sum()` (sequential on ≤ 3.11, Neumaier-compensated on ≥ 3.12, `index.py:15-19, :38-39`). The query is still normalized in Python; `MONETA_NATIVE=0` forces the loop (`index.py:43-48`) | v5's Python loop (`index.py:123-126`) | `tests/v5/test_native_index_parity.py`: sum kernel vs `sum()`, cosines, remove/re-add/compaction, errors, and whole `recall` with and without native | built (`88d1f87`); exact per interpreter, **not across interpreters**: Python 3.11 and 3.14 can differ in the last bit, native or not (`index.py:18-19`) |
```

### C44: §6 Built so far (v5 measured) (numbers)

**Evidence:** results/bench_v5_recall_native.jsonl rows 1-7 (all fields); scripts/v5/bench_recall_native.py:51-78 (one Substrate per mode, warm-up recall at :60, p95 index :73); commit 88d1f87 message ('open RSS 312 -> 194 MB (python index) / 342 -> 224 MB (native)'); src/moneta/v5/model.py:181-193

**Old:**

```text
**Superseded history, not a gate comparison.**
```

**New:**

```text
**v5 measured (dot seam).** `recall(q, 10)` on one v5 journal of 10k × 384, owner workstation, Python 3.14.2, N = 200 after one warm-up query, one process per `MONETA_NATIVE` mode (`scripts/v5/bench_recall_native.py` → `results/bench_v5_recall_native.jsonl`, rows 1–7) `[M]`:

| v5 index | p95 | p50 | open | open RSS (`open_rss_delta_mb`) |
|---|---|---|---|---|
| Python loop (oracle), rows 1, 2, 4, 6 | 184.4–194.4 ms | 176.4–187.2 ms | 0.70–0.85 s | 312 MB with tuple units (rows 2, 4); 193 MB with `array('d')` units (row 6) |
| native dot seam, rows 3, 5, 7 | 18.8–19.8 ms | 14.0–14.8 ms | 0.76–0.79 s | 342 MB with tuple units (rows 3, 5); 224 MB with `array('d')` units (row 7) |

**Reading it.** The dot seam takes v5 recall p95 down about 10×, from 184–194 to 19–20 ms. **The RSS drop is not the seam:** 312 → 194 MB (Python index) and 342 → 224 MB (native) both come from storing unit vectors as packed `array('d')` instead of tuples of floats (`src/moneta/v5/model.py:181-193`; commit `88d1f87`; rows marked `"variant": "unit-array"`). The native index holds about 30 MB **more** than the Python one, because it mirrors the vectors into Rust. Row 1 also built the journal (`build_s` 16.8 s); its open RSS (71 MB) is not comparable. On this machine v5's oracle misses D1's 50 ms gate and the dot seam clears it, but **D1 was not measured on v5** (no numpy arm P on v5's facade; §8 mile 0 Done means #3), so the seam is admitted under O27, not D1. Rows 6–7 are single runs.

**Superseded history, not a gate comparison.**
```

### C45: §6 Test matrix (numbers)

**Evidence:** (session scratch) pytest_v5_57a90bc.txt

**Old:**

```text
without the wheel, 167 pass and 33 native-only tests skip (`CLAUDE.md:155`, working tree) `[M]`.
```

**New:**

```text
without the wheel, 167 pass and 33 native-only tests skip (`CLAUDE.md:155`, working tree) `[M]`. v5's suite is separate: `tests/v5` at `57a90bc` passes 158 under Python 3.14.2 with `MONETA_NATIVE=0` and `=1`, and 151 + 1 skipped (the native-parity module, no wheel) under hython 21.0.773 `[M]`. Hython with the wheel was not run for v5.
```

### C46: §6 Gaps (cross-interpreter, v5) (add)

**Evidence:** src/moneta/v5/index.py:15-19, :38-39, :123-126

**Old:**

```text
Linux and macOS parity (glibc or libSystem `exp`) is `[U]` (O11).
```

**New:**

```text
Linux and macOS parity (glibc or libSystem `exp`) is `[U]` (O11).
- **Cross-interpreter exactness (v5) `[V]`.** v5's cosine oracle is Python's `sum()`, Neumaier-compensated on 3.12+ and sequential on 3.11 (`src/moneta/v5/index.py:15-19, :38-39`), so one v5 score can differ in the last bit between hython 3.11 and Python 3.14. That is within-interpreter determinism (v5's I6), not G3-5's byte-identical rebuild across machines or V-POOL's bit-for-bit agreement between referee and read path. A v7 read path built on v5's index must first move to one declared summation order.
```

### C47: §6 Q2 (upgrade)

**Evidence:** src/moneta/v5/journal.py:8-23, :81-135

**Old:**

```text
v5's CRC framing is `[A; v6: V]` |
```

**New:**

```text
v5's framing `[V]`: `<crc32 hex> <canonical JSON>\n` per event, sorted keys, compact separators, `allow_nan=False`, gap-free `seq`; a torn tail is truncated and mid-file corruption refuses to open (`src/moneta/v5/journal.py:8-23, :81-135`). CRC, not a hash chain |
```

### C48: §6 Q4 (status)

**Evidence:** RULINGS.md:54-55; src/moneta/v5/substrate.py:663-701 (recall), :736-743 (manifest), :892-954 (explain); tests/v5/test_conformance.py:274-283

**Old:**

```text
native branch `:257-263`, oracle loop `:264-272`, both in place); E2 is `[A]` |
```

**New:**

```text
native branch `:257-263`, oracle loop `:264-272`, both in place). E2 is RULED for v5 (`RULINGS.md:54-55`), and v5's `recall`, `explain` and manifest write nothing `[V, src/moneta/v5/substrate.py:663-701, :736-743, :892-954; tests/v5/test_conformance.py:274-283; test_review_regressions.py:196]` |
```

### C49: §6 Q7 (add)

**Evidence:** src/moneta/v5/substrate.py:733

**Old:**

```text
the WAL record has no generation (`api.py:427-429`) |
```

**New:**

```text
the WAL record has no generation (`api.py:427-429`); v5's `attend` event carries only `{t, w}` (`src/moneta/v5/substrate.py:733`) |
```

### C50: §6 Q10 (status)

**Evidence:** RULINGS.md:69, :77; src/moneta/v5/substrate.py:23-24, :356, :490-502; compat.py:91; tests/v5/test_conformance.py:363-366

**Old:**

```text
| **Q10** | No GIL dependence in seams; ordering comes from the single writer (E3 `[A]`) | all | `attention_log.py:64-68` refuses free-threaded Python |
```

**New:**

```text
| **Q10** | No GIL dependence in seams; ordering comes from the single writer (E3 RULED for v5, closure gated: §8) | all | `attention_log.py:64-68` refuses free-threaded Python. v5 has no GIL sentinel (`tests/v5/test_conformance.py:363-366`) and orders writes under one `RLock` (`src/moneta/v5/substrate.py:356, :490-502`). Free-threaded Python stays `[U]`, with a warning (`RULINGS.md:77`), although v5's docstrings claim support (`substrate.py:23-24`; `compat.py:91`) |
```

### C51: §7 decay lock (status)

**Evidence:** RULINGS.md:55; docs/v7/ROUND4_BRIEF.md:338

**Old:**

```text
| **Kept** for retention in v1. Whether v7's per-event retention fold is point 2 or a fourth point is Round 4 (O29).
```

**New:**

```text
| **Ruled (E2):** the formula stays verbatim; "three evaluation points" becomes "zero mutation points; state changes only through journaled events" (`RULINGS.md:55`), not yet amended in `ARCHITECTURE.md` at `57a90bc`. **Kept** for retention in v1. Whether v7's per-event retention fold is point 2 or a fourth point was Round 4's (O29); under the new wording it is answered in substance and needs an explicit line in the amendment (`ROUND4_BRIEF.md:338`).
```

### C52: §7 concurrency lock (status)

**Evidence:** RULINGS.md:69-79

**Old:**

```text
| Replaced by the journal under E3 `[A]`. Needs Round 4. R4a's exclusion has no carrier unless E3 is ruled for or §5.1 is amended (O30) |
```

**New:**

```text
| Replaced by the journal under E3: **RULED for v5, closure gated** (`RULINGS.md:69-79`) [[R4: E3-1 status pending]] [[R4: E3-2 status pending]] [[R4: E3-3 status pending]]. §5.1 is to be amended so attention is visible immediately (E3-B3). R4a's exclusion has its carrier once E3 closes (O30) |
```

### C53: §7 atomicity lock (status)

**Evidence:** RULINGS.md:54-67

**Old:**

```text
| Superseded by E1 `[A]`. Needs Round 4. E1 retires
```

**New:**

```text
| Superseded by E1: **RULED for v5, with conditions** (`RULINGS.md:54-67`) [[R4: E1-1 status pending]]. E1 retires
```

### C54: §7 free-threading lock (status)

**Evidence:** RULINGS.md:77

**Old:**

```text
| Kept for v1 code. Seams are GIL-independent (Q10). Retiring the guard is part of E3's round |
```

**New:**

```text
| Kept for v1 code. Seams are GIL-independent (Q10). E3's ruling keeps free-threaded Python `[U]`, with a warning (`RULINGS.md:77`) [[R4: E3-B2 status pending]]; v5 carries no guard (`tests/v5/test_conformance.py:363-366`) |
```

### C55: §8 mile 0 heading (status)

**Evidence:** RULINGS.md:48-101; 861bed9

**Old:**

```text
### Mile 0: Round 4 (a MONETA.md §9 escalation), then v5 lands
```

**New:**

```text
### Mile 0: Round 4 (a MONETA.md §9 escalation): ruled; v5 merged beside v1; closure pending
```

### C56: §8 mile 0 step 0 + conditions table (placeholder)

**Evidence:** RULINGS.md:48-101 (line numbers per condition); code cells read at 57a90bc as cited; commits 279d903, 57a90bc, a777287, 720b3b0, fae3000 name the conditions they target (closure not judged here)

**Old:**

```text
**Step 0 (owner):** locate the v5 bundle (a path or remote), or rule that mile 0 proceeds without it (O35); v5 is absent from this repo and no `v5` branch exists. Then the Architect drafts the brief at `docs/rounds/round-4-brief.md`, and the owner reviews it before it goes out. Mile 2's report is attached as evidence if it lands first. No work on an affected subsystem proceeds until the round closes.
```

**New:**

```text
**Step 0 (owner): done.** The v5 bundle was found and merged beside v1 (O35; `861bed9`, on `v7-native-seams`, not `main`). The brief went out as `docs/v7/ROUND4_BRIEF.md` (not `docs/rounds/round-4-brief.md`), without mile 2's report, and the owner ruled on 2026-10-15 (`RULINGS.md:48-101`). The round **closes** ruling by ruling, as each one's blocking conditions are implemented and measured (`RULINGS.md:101`). Condition IDs below are this paper's, numbered in `RULINGS.md` order. The code column records what was read at `57a90bc`; it is not a closure verdict.

| ID | Ruling | Condition (`RULINGS.md` line) | Gates | Code at `57a90bc` `[V]` | Status |
|---|---|---|---|---|---|
| E1-1 | E1 + E2 | migration crash window: whether to migrate is decided from a journaled completion marker, not from whether the journal file exists (`:56`) | cutover step 2 | `v1_migration_begin` / `v1_migration` notes; an interrupted migration is set aside and restarted from `snapshot.json.v1-original` (`src/moneta/v5/compat.py:22-29, :267-383, :810-868`; commits `279d903`, `57a90bc`) | [[R4: E1-1 status pending]] |
| E1-B1 | E1 + E2 | a checkpoint, so open replays only the tail (`:58`) | 5.0.0 | open replays the whole journal (`substrate.py:369-370`) | [[R4: E1-B1 status pending]] |
| E1-B2 | E1 + E2 | re-projection made idempotent (`:59`) | 5.0.0 | not checked | [[R4: E1-B2 status pending]] |
| E1-B3 | E1 + E2 | one source of λ (`:60`) | 5.0.0 | λ from genesis and `half_life` events only (`model.py:8-26, :209-248`) | [[R4: E1-B3 status pending]] |
| E1-B4 | E1 + E2 | runtime λ tuning made explicit (`:61`) | 5.0.0 | `set_half_life(mode=…)` (`substrate.py:749-770`) | [[R4: E1-B4 status pending]] |
| E1-B5 | E1 + E2 | a timestamp-skew guard (`:62`) | 5.0.0 | none: host `t` passes after a finiteness check (`substrate.py:487-488`); fold-side `max` only (`model.py:346`) | [[R4: E1-B5 status pending]] |
| E1-B6 | E1 + E2 | the native decay seam ported to v5 (`:63`) | 5.0.0 | v5 imports `decay_value` only; no `decay_batch` (`model.py:57`) | [[R4: E1-B6 status pending]] |
| E1-P1 | E1 + E2 | a CRC-bad final line treated as a torn tail (`:65`) | polish | a complete bad line refuses to open (`journal.py:122-127`) | [[R4: E1-P1 status pending]] |
| E1-P2 | E1 + E2 | an attention durability tier (`:66`) | polish | every append fsyncs (`journal.py:326-327`) | [[R4: E1-P2 status pending]] |
| E1-P3 | E1 + E2 | export failure logged, not raised (`:67`) | polish | logged on close (`compat.py:756-763`); not on the sleep-pass export (`compat.py:792-796`) | [[R4: E1-P3 status pending]] |
| E3-1 | E3 | USD projection outside the writer lock; recall p95 stall ≤ 30 ms during a sleep pass (real `UsdTarget`, hython, 500-prim batches) (`:71`) | E3 closure | projection runs inside `with self._lock` (`substrate.py:791-878`) | [[R4: E3-1 status pending]] |
| E3-2 | E3 | snapshot export outside the lock; stall ≤ 30 ms per pass at 10k × 768 (`:72`) | E3 closure | export holds the substrate lock (`compat.py:205-242`) | [[R4: E3-2 status pending]] |
| E3-3 | E3 | a journal checkpoint or attend coalescing, with a tested reopen budget (`:73`) | E3 closure | neither present | [[R4: E3-3 status pending]] |
| E3-B1 | E3 | Windows fsync numbers; group commit or the ~700 writes/s ceiling recorded (`:76`) | 5.0.0 | — | [[R4: E3-B1 status pending]] |
| E3-B2 | E3 | free-threaded Python stays `[U]`, with a warning (`:77`) | 5.0.0 | docstrings claim support (`substrate.py:23-24`; `compat.py:91`) | [[R4: E3-B2 status pending]] |
| E3-B3 | E3 | §5.1 amended: attention is visible immediately (`:78`) | 5.0.0 | `ARCHITECTURE.md` unamended | [[R4: E3-B3 status pending]] |
| E3-B4 | E3 | the SYNAPSE swap re-run on Windows against a copy of the 841-record store (`:79`) | 5.0.0 | — | [[R4: E3-B4 status pending]] |
| E4-1 | E4 | recall p95 with 100k dead records within 10% of zero dead (`:85`) | E4 closure | `_classify` walks every record, dead ones included (`substrate.py:545-557`) | [[R4: E4-1 status pending]] |
| E4-2 | E4 | `erase()` names or invalidates every derived copy (`:86`) | E4 closure | `erase` returns a seq only (`substrate.py:1039-1058`) | [[R4: E4-2 status pending]] |
| E4-3 | E4 | the ruling covers semantics, not mechanism (`:87`) | E4 closure | — | [[R4: E4-3 status pending]] |
| E4-4 | E4 | fix the O(n²) dedup at `substrate.py:949` (`:88`) | E4 closure | ordered dict dedup, now `substrate.py:1093-1103` (commit `fae3000`) | [[R4: E4-4 status pending]] |
| HL-1 | half-life | `fold.lam` from genesis and change events, never Config; a mismatched open raises unless the caller names a mode; read-only opens never append (`:94`) | half-life closure | `model.py:209-278`; `substrate.py:339-400` | [[R4: HL-1 status pending]] |
| HL-2 | half-life | the first sleep pass after a change is a dry run, or needs confirmation above a stated LIVE fraction (`:95`) | half-life closure | dry run until `confirm_half_life_change=True` (`substrate.py:805-829`) | [[R4: HL-2 status pending]] |

Not conditions, recorded with them: `compact()` is not ratified (`:82`); the E4 Jev question is to be re-asked with corrected option costs (`:90`); R2 does not flip (`:97`).

The table below is the brief's framing, kept for the record. E1–E4 and the half-life call were each ruled **for** (E4 as semantics only). The (question) rows were not ruled one by one: the first two are answered in substance by E2's wording (O2, O29); the λ range (O28), the pressure trigger (O23) and §15.2 #4 stay open.
```

### C57: §8 mile 0 Done means #1-2 (status)

**Evidence:** git ls-tree 57a90bc docs/rounds (round-1..3 only); git show 57a90bc:CLAUDE.md

**Old:**

```text
1. All rulings are recorded in `docs/rounds/round-4.md`.
2. `ARCHITECTURE.md` and `CLAUDE.md`'s "Locked decisions" are amended in one PR.
```

**New:**

```text
1. All rulings are recorded in `docs/rounds/round-4.md`. They are ruled and recorded in `docs/v7/RULINGS.md:48-101`; `docs/rounds/round-4.md` does not exist at `57a90bc`.
2. `ARCHITECTURE.md` and `CLAUDE.md`'s "Locked decisions" are amended in one PR. Not done at `57a90bc`.
```

### C58: §8 mile 0 Done means #3 (status)

**Evidence:** docs/v5/BLUEPRINT.md:228; ROUND4_BRIEF.md:320

**Old:**

```text
3. Then v5 is merged under the round, and its facade runs against a copy of the 841-record store
```

**New:**

```text
3. Then v5 is merged under the round (it was merged beside v1 before the ruling, `861bed9`, as v5's cutover step 1, and is not the default), and its facade runs against a copy of the 841-record store
```

### C59: §8 mile 0 Done means #3 (tail) (placeholder)

**Evidence:** docs/v5/SYNAPSE_COMPAT.md:5, :13, :50-52 (git show 57a90bc:...)

**Old:**

```text
The import follows "Migration into format 7" (G1).
```

**New:**

```text
The import follows "Migration into format 7" (G1). The 841-record run is E3-B4 [[R4: E3-B4 status pending]]. SYNAPSE compatibility stays `[A]` until then: v5's own report is 247 of 253 SYNAPSE tests on Linux, CPython 3.11, with no production store migrated (`docs/v5/SYNAPSE_COMPAT.md:5, :13, :50-52`).
```

### C60: §8 mile 0 Kill (status)

**Evidence:** RULINGS.md:48-97

**Old:**

```text
**Kill.**
- E4 rejected: stop.
```

**New:**

```text
**Kill.** None of the first five fired: Round 4 ruled E1–E4 and the half-life call toward v5, and R2 does not flip (`RULINGS.md:48-97`). They are kept for the record; the last stays live.
- E4 rejected: stop.
```

### C61: §8 mile 1 row (status)

**Evidence:** docs/v7/ROUND4_BRIEF.md; RULINGS.md:48-101

**Old:**

```text
go on mile 2; Round 4 brief in draft |
```

**New:**

```text
go on mile 2; Round 4 brief drafted ✓ and ruled ✓ |
```

### C62: §9 queue (Now) (answer)

**Evidence:** RULINGS.md:44

**Old:**

```text
| **Now** (mile 0 step 0) | O35 |
```

**New:**

```text
| **Now** (mile 0 step 0) | none: O35 answered (FOUND and merged) |
```

### C63: §9 queue (Round 4 brief) (status)

**Evidence:** RULINGS.md:32-33, :48-101, :55

**Old:**

```text
| **In the Round 4 brief** | O1, O2, O7, O23, O27, O28, O29, O30, O31 |
```

**New:**

```text
| **In the Round 4 brief** | ruled: O1 (Round 4), O27 (confirmed); answered in substance by E2's wording, pending the amendment: O2, O29. Still open: O7 (time rule, with E1-B5), O23, O28, O30 (moot once E3 closes), O31 |
```

### C64: §9 queue (v5 code) (answer)

**Evidence:** see C69, C70

**Old:**

```text
| **At mile 0, from the v5 code** | O19, O24 |
```

**New:**

```text
| **At mile 0, from the v5 code** | O24 answered by the code (the owner rules v7's shape); O19 answered on the substrate side, SYNAPSE side open |
```

### C65: §9 O1 (status)

**Evidence:** RULINGS.md:48-101

**Old:**

```text
| **O1** | Mile 0: E1–E4 and the half-life call | rule all five **for** (v7 as drawn), each `[A]` until ruled `[P]` | the owner, through Round 4; before mile 4 |
```

**New:**

```text
| **O1** | **RULED 2026-10-15** (`RULINGS.md:48-101`). Mile 0: E1–E4 and the half-life call | all five ruled toward v5: E1 + E2 for, with conditions; E3 for, closure gated; E4 semantics only, gated; half-life: the journal owns λ, each change explicit and journaled. Closure: §8 mile 0 conditions table | the owner, through Round 4 |
```

### C66: §9 O2 (answer)

**Evidence:** RULINGS.md:55; src/moneta/v5/model.py:163-164; substrate.py:693

**Old:**

```text
| no: it is a pure view (V-EVAL3) `[P]` | Round 4 |
```

**New:**

```text
| no: it is a pure view (V-EVAL3) `[P]`. **Answered in substance by E2's ruling:** "zero mutation points; state changes only through journaled events" (`RULINGS.md:55`); v5 evaluates utility at any read without writing (`src/moneta/v5/model.py:163-164`; `substrate.py:693`) `[V]`. Closes with the `ARCHITECTURE.md` amendment | Round 4 (ruled); the amendment PR |
```

### C67: §9 O7 (answer)

**Evidence:** src/moneta/v5/model.py:337-348, :346; substrate.py:487-488; RULINGS.md:62

**Old:**

```text
| **O7** | Retention fold step order: per event (v5 `[A]`) or v1's per batch with decay forgiven (`ecs.py:240-243`); and the time rule (append-time clamp vs fold-side `max`) | per event, declared; append-time clamp (G1 envelope); it changes which records prune | Round 4 (E3, and lock 2 via O29) |
```

**New:**

```text
| **O7** | Retention fold step order: per event (v5 `[V, src/moneta/v5/model.py:337-348]`) or v1's per batch with decay forgiven (`ecs.py:240-243`); and the time rule (append-time clamp vs fold-side `max`) | per event, declared: the ruled direction (E1–E3 for v5). Append-time clamp (G1 envelope). **v5 does the opposite on the time rule** `[V]`: fold-side `max(t, anchor_t)` (`model.py:346`) and no clamp at append (`substrate.py:487-488`); Round 4 requires a timestamp-skew guard before 5.0.0 [[R4: E1-B5 status pending]]. It changes which records prune | Round 4 ruled the order's direction; the time rule stays open with E1-B5 |
```

### C68: §9 O13 (numbers)

**Evidence:** results/bench_v5_recall_native.jsonl open_s: 0.846, 0.699, 0.764, 0.704, 0.763, 0.704, 0.792

**Old:**

```text
RSS recorded as a metric, not a gate | measured at mile 4; the owner signs the numbers |
```

**New:**

```text
RSS recorded as a metric, not a gate. **Measured so far** `[M]`: v5 opens a 10k × 384 journal in 0.70–0.85 s on the owner workstation, Python 3.14.2 (`results/bench_v5_recall_native.jsonl`, `open_s`, rows 1–7), under the container's 1.0 s; 100k is not measured here | measured at mile 4; the owner signs the numbers |
```

### C69: §9 O19 (answer)

**Evidence:** src/moneta/v5/compat.py:174-196 (sidecar keeps the last two export hashes), :245-255, :386-493; tests/v5/test_compat.py:556-660; docs/v5/SYNAPSE_COMPAT.md

**Old:**

```text
Verify at mile 0 against the pinned commit | the owner, at mile 0 |
```

**New:**

```text
Verify at mile 0 against the pinned commit. **Answered on the substrate side by v5 `[V]`:** the facade never hydrates from `snapshot.json`. On open it accepts an export whose hash it wrote or journaled, ignores an unreadable one with a journal note, turns an embedder-swap rewrite into a journaled `revector`, and refuses anything else with `SnapshotDivergedError` (`src/moneta/v5/compat.py:386-493`; `tests/v5/test_compat.py:556-660`). A restore that writes `snapshot.json` back is therefore a no-op (a known hash) or refused; it never sets state, which matches this default. **Still open:** whether SYNAPSE's wrapper restore path needs more. v5's SYNAPSE report covers embedder-swap rewrites and corrupt snapshots on Linux only (`docs/v5/SYNAPSE_COMPAT.md:33, :43, :50-52`), and the 841-store run re-measures it [[R4: E3-B4 status pending]] | the owner, at mile 0 (SYNAPSE side) |
```

### C70: §9 O24 (question) (upgrade)

**Evidence:** src/moneta/v5/policy.py; substrate.py

**Old:**

```text
v5's slot semantics are `[A]` (`BLUEPRINT_v6.md:74, :540`);
```

**New:**

```text
v5's slot semantics were `[A]` (`BLUEPRINT_v6.md:74, :540`) and are now `[V]` from v5's code (below);
```

### C71: §9 O24 (default) (answer)

**Evidence:** src/moneta/v5/policy.py:30-32, :161-166, :208-210; substrate.py:558-579, :927-936

**Old:**

```text
| an ordered list of candidate record ids, resolved by strength; the winner is the first admitted entry (G2-9); when none is admitted, the slot is empty unless v5 does otherwise. Answers pass-2 attack 4 once confirmed | the owner, at mile 0 (v5 code) |
```

**New:**

```text
| **Answered by v5's code `[V]`, and it differs from this paper's earlier default.** In v5 a slot preference is **one** record id per slot (`src/moneta/v5/policy.py:30-32, :161-166`), resolved by strength per slot (`:208-210`). The winner is that id if it survives the caller, scope, exclusion and status filters; otherwise the **latest-deposited admitted claim** (max `seq`) wins; a slot is empty only when no claim is admitted (`substrate.py:558-571`; `explain` says which, `:927-936`). The winner is picked before the zero-vector check, so a direction-less winner hides every other claim in its slot (`:572-579`). The earlier default here (an ordered list; empty when none admitted) is **not** v5's. Recommended: adopt v5's shape and fallback for v7.0, so G2-9 and V-REPLAY match the code; an ordered list is a later extension. Answers pass-2 attack 4 once confirmed | the owner, at mile 0: the code has answered the question; the owner rules which shape v7 keeps |
```

### C72: §9 O27 (status)

**Evidence:** RULINGS.md:32-33; src/moneta/v5/index.py:11-19

**Old:**

```text
| label it `[A; v6]` (as applied), not D1; the owner confirms it before mile 4 commits to the referee and kernel. **Live instances (two):** `moneta_native.decay_batch` and `moneta_native.ScanIndex` both shipped
```

**New:**

```text
| ruled: a project constraint, not D1 (`RULINGS.md:32-33`). **Live instances (three):** v5's dot seam (`ScanIndex.dots` behind `ExactIndex.cosines`, §6 "Built so far"); and `moneta_native.decay_batch` and `moneta_native.ScanIndex`, which both shipped
```

### C73: §9 O28 (add)

**Evidence:** src/moneta/v5/substrate.py:344, :767; RULINGS.md:48-101 (no O28 ruling)

**Old:**

```text
asked beside O2 | Round 4 |
```

**New:**

```text
asked beside O2. Round 4 did not rule it. v5 range-checks its single λ against the :82 range (`DecayConfig`, `src/moneta/v5/substrate.py:344, :767`) `[V]` | Round 4 (not ruled) |
```

### C74: §9 O29 (answer)

**Evidence:** RULINGS.md:55; ROUND4_BRIEF.md:338

**Old:**

```text
| route to Round 4 with O7, citing lock 2 (`CLAUDE.md`) as well as E3; fallback is v1's per-batch order for retention | Round 4 |
```

**New:**

```text
| route to Round 4 with O7, citing lock 2 (`CLAUDE.md`) as well as E3; fallback is v1's per-batch order for retention. **Answered in substance by E2's wording** ("zero mutation points", `RULINGS.md:55`); the amendment should say explicitly that the per-event fold is the rule (`ROUND4_BRIEF.md:338`) | Round 4 (ruled); the amendment PR |
```

### C75: §9 O30 (status)

**Evidence:** RULINGS.md:69

**Old:**

```text
| **O30** | **If E3 is ruled against, where does R4a live?**
```

**New:**

```text
| **O30** | **E3 was ruled for (`RULINGS.md:69`); this applies only if E3's closure fails.** **If E3 is ruled against, where does R4a live?**
```

### C76: §9 O35 (answer)

**Evidence:** RULINGS.md:35-44; git log 861bed9

**Old:**

```text
| **O35** | **Searched 2026-10-15, NOT FOUND** locally, on `origin` or in the owner's other GitHub repos; likely in the cloud session that ran v5/v6 (RULINGS.md). **Where is the v5 bundle?** Mile 0 merges v5, but no v5 code or branch is in this repo (Tags) | locate it before the Round 4 brief goes out; if it can't be found, rule whether mile 0 proceeds against v1 alone (then E1–E4 land on v1, and every `[A; v6: V]` row stays `[A]`) | the owner, now (mile 0 step 0) |
```

**New:**

```text
| **O35** | **FOUND 2026-10-15** (`RULINGS.md:44`): the owner supplied `moneta-v5.bundle` (`refs/heads/v5` @ `b1feaaf`, based on `6cf05f5`) and its blueprint; merged beside v1 on `v7-native-seams` (`861bed9`), not on `main`. Earlier the same day it was searched for and not found (`RULINGS.md:35-42`). **Where is the v5 bundle?** | answered: `src/moneta/v5/`, `docs/v5/`, `tests/v5/`, `scripts/v5/`; every v5 claim in this paper was re-checked against it (v5 reconciliation log) | closed |
```

### C77: §10 What to attack (add)

**Evidence:** this pass's findings

**Old:**

```text
If a lock should go, say which one and why in a separate section, not inside the critique.
```

**New:**

```text
12. **v5 against v7** (v5 reconciliation pass). v5 resolves context scopes by strength, not intersection (G2); its slot preference is one id with a latest-claim fallback (O24); its cosines differ across interpreters (§6 Gaps); its time rule is a fold-side `max` (O7); its policy is host-held, not journaled (P1). Which should v7 adopt, and which must the v7 read path change before V-POOL and G3-5 can hold?

If a lock should go, say which one and why in a separate section, not inside the critique.
```

### C78: Appendix (v5 references) (add)

**Evidence:** files as listed

**Old:**

```text
---

## Appendix: glossary
```

**New:**

```text
---

## Appendix: v5 references verified for this paper (`57a90bc`; commit, not working tree)

- **v5 at `57a90bc`** (v5 reconciliation pass)
  - `src/moneta/v5/journal.py`: `:8-23` frame and recovery rules; `:81-102` framing (`allow_nan=False`); `:105-135` scan; `:326-327` fsync per append; `:349-396` `rewrite` (compaction)
  - `src/moneta/v5/model.py`: `:8-26` the journal owns λ; `:181-193` `array('d')` units; `:246-278` half-life modes; `:337-348` `attend` fold; `:364-369` `retain`; `:389-400` `revector`; `:402-413` `note`
  - `src/moneta/v5/policy.py`: `:9-13`, `:203-207` strength resolution, lists replace; `:30-32`, `:161-166` one id per slot
  - `src/moneta/v5/index.py`: `:15-19`, `:38-39` interpreter `sum()`; `:104-126` `cosines` and the native dot seam
  - `src/moneta/v5/substrate.py`: `:487-488` host `t`; `:490-502` `_append`; `:545-579` `_classify`; `:663-701` `recall`; `:703-734` `signal_attention`; `:772-890` `run_sleep_pass`; `:956-1010` `revector`; `:1060-1091` `compact`; `:1093-1103` `_known`
  - `src/moneta/v5/compat.py`: `:22-29`, `:267-383` migration markers; `:386-493` snapshot guard
  - `tests/v5/`: `test_conformance.py:223-243` (I5), `:274-283` (I6 reads never write), `:363-366` (no GIL sentinel); `test_review_regressions.py:316-327` (60 random specs); `test_native_index_parity.py`
  - `results/bench_v5_recall_native.jsonl` rows 1–7; `scripts/v5/bench_recall_native.py`
  - `docs/v5/BLUEPRINT.md`: `:157-168` I1–I8; `:242`, `:244` container figures; `:255-262` where Rust fits. `docs/v5/SYNAPSE_COMPAT.md`: `:5`, `:13`, `:33`, `:43`, `:50-52`

---

## Appendix: glossary
```

### C79: End: v5 reconciliation log (add)

**Evidence:** this pass

**Old:**

```text
| final review | F-6 | stale counts after the fix | applied | test matrix 211 → 215 in 4 configs; without the wheel 167 + 33 skips (`CLAUDE.md:155`); hython named as 21.0.773; the Exactness paragraph's "CLAUDE.md names 21.0.512" note updated, since `CLAUDE.md:130` now names 21.0.773 |
```

**New:**

```text
| final review | F-6 | stale counts after the fix | applied | test matrix 211 → 215 in 4 configs; without the wheel 167 + 33 skips (`CLAUDE.md:155`); hython named as 21.0.773; the Exactness paragraph's "CLAUDE.md names 21.0.512" note updated, since `CLAUDE.md:130` now names 21.0.773 |

---

## v5 reconciliation log (after pass 4)

v5 was merged beside v1 (`861bed9`) and Round 4 was ruled (`RULINGS.md:48-101`) after pass 4. This pass re-checked every v5-dependent claim against v5 at `57a90bc` (code and tests read; `tests/v5` run; `results/bench_v5_recall_native.jsonl` and `results/bench_query_fair_matrix.jsonl` read row by row) and applied the rulings. Each change, with old and new text and its evidence, is listed in `CHANGES.md`, delivered beside this revision. The review and pass logs above are unchanged.

- **Upgraded** `[A; v6: V]` / `[A]` → `[V]` or `[M]` where the v5 code, tests or results confirm the claim: event bodies (`revector`, `consolidate`, `note`), the single write path (G1-5, L3), filter-then-choose slots, the 60-spec resolver test (G2-7, C3), the per-event attention order, the journal framing (Q2), I1–I8, v5's recall and open figures.
- **Corrected** where the code contradicts the paper: parent-to-child scope narrowing is not v5's rule (G2, C4); the slot preference is one id with a latest-claim fallback (O24); v5's policy is not journaled (P1); `compact()` edits the journal (T1); λ changes may apply forward, not only reinterpret (G2-10); the seam rule's wording is v6's, not v5's (§6).
- **Answered:** O35 (found), O24 (code), O19 (substrate side), O1 and O27 (ruled), O2 and O29 (in substance, by E2's wording).
- **Placeholders:** every Round 4 condition's closure status is `[[R4: <id> status pending]]` (§8 mile 0 table): an implementation workflow was running on the branch during this pass, and closure is the owner's call on measured numbers.
- **Numbers:** v5 recall p95 184–194 ms (oracle) → 18.8–19.8 ms (native dot seam); the open-RSS drop 312 → 194 MB is the `array('d')` change, not the seam; v1's fair matrix re-read unchanged (227–313 ms → 3.1–6.7 ms p95, ~185 → ~69 MB).
```


---

## Claims NOT verified, left as they were

- **SYNAPSE's behaviour** (G3-2 path 1: pool of `max(3×limit, 50)`, rerank, top-5 echo; path 2 `[A]`): SYNAPSE's source is not in this repo. Left `[A; v6: V]` / `[A]`.
- **SYNAPSE compatibility** (247 of 253 on Linux, CPython 3.11; `docs/v5/SYNAPSE_COMPAT.md`): read, not re-run. Left `[A]`; E3-B4 re-measures it.
- **v5's container figures** (161 ms median query, 1.0 s open, 0.43 ms durable deposit, 42.6 MB at 10k; `docs/v5/BLUEPRINT.md:236-245`): stated, not re-run. Left `[A; v6: V]`. Workstation figures for recall and open were added beside them as `[M]`.
- **The RSI-in-USD toy claims** (T4, P3, J1, L2, the referee's 20 M fuel / 8 MB caps): the toy package is absent. Left `[A; v6: V on the toy]`.
- **D1 and the 8 September decisions**: given, not verifiable. Left as "given".
- **The 1.3× container/workstation factor** (§6 machine dependence): left `[A]`.
- **v5's free-threaded behaviour, the Windows `msvcrt` lock path, directory fsync on NT**: not tested here. Left `[U]` / unmentioned.
- **E1-B2 (re-projection idempotent)**: not checked in code; the §8 code cell says "not checked".
- **O13 at 100k records**: not measured here (the brief's probe numbers live in scratchpad `e1/`, `e3/`, not in `results/`).
- **The brief's F2/F3 numbers** (100k events 0.81 s open; ~1.4 ms fsync, ~700 writes/s): not re-run, not added to the paper.
- **Pass-4 v1 anchors after drift**: `rust/moneta_native/src/lib.rs` (+67 lines in `88d1f87`, anchors after `:36` moved), `src/moneta/api.py` (+2 lines in `d4f9fd4`: the `signal_attention` docstring at `:416-420` grew, so anchors from `:421` on moved by +2, e.g. `:422` → `:424`, `:425-429` → `:427-431`, `:446-451` → `:448-453`) and `CLAUDE.md` (changed in `42a0368`). The Baseline paragraph now says so; the anchors themselves were **not** re-anchored (out of this pass's scope).
- **"On `main`" wording throughout pass-4 text**: left as written; the Baseline paragraph defines it as the v1-line code now on `v7-native-seams`.
- **R2, R3, O4**: still `[A]`, as ruled (`RULINGS.md:97`).
- **O28** (does `:82` bind the recall λ): not ruled by Round 4. Only the code fact that v5 range-checks its single λ was added.
- **The patent posture**: no claim enumeration or claim-to-evidence mapping was added.

---

## After the Round 4 pass (`ba52ca7`)

- Status column filled for all 23 condition IDs (§8 mile 0). Independent re-run at `ba52ca7`: 405 passed in each of Python 3.14 and hython 21.0.773 with `MONETA_NATIVE=0` and `=1`; hython without the wheel 347 passed, 35 skipped; `scripts/v5/mutation_check.py` on a `git archive HEAD` copy: `missed: []`.
- Known nits, not fixed: `results/bench_v5_lockscope.jsonl` and `results/bench_v5_checkpoint.jsonl` record the parent commit in their "after" rows (measured on the uncommitted tree); pass-4 line citations into `lib.rs`, `api.py` and `CLAUDE.md` are disclosed as stale but not refreshed.
