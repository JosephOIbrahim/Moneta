# Moneta v7: Blueprint

> **Read this first (solo owner, after time away).**
> - **Today:** v1 is still the default handle. Branch `v7-native-seams` (`ba52ca7` plus this paper) carries v1, the committed native seams (`6f4696a`), and the **v5 reference implementation, merged beside v1** (`src/moneta/v5/`, merge `861bed9`); `main` is still `6cf05f5`. An optional Rust wheel (`rust/moneta_native`) speeds up v1's `query` with a scan and a decay kernel, and v5's `recall` with a dot-product seam and the same decay kernel, each bit-identical to its Python oracle on this platform for finite, non-overflowing inputs (anything else is answered by the oracle). It was admitted for exactness, not latency: numpy (arm P) also clears D1's 50 ms gate `[M]`. 405 tests (v1 and v5 together) green in 4 configurations at `ba52ca7` (Python 3.14 and hython 21.0.773, native seams off and on), and v5's mutation check catches every mutation `[M]`; hython without the wheel: 347 pass, 35 native-only skip `[M]`. **Nothing in v7 is built.**
> - **v7 in one sentence:** the governed loop of v6, re-derived as five typed graphs whose invariants are the checks.
> - **Health check:** run the 4-config pytest matrix in `CLAUDE.md` ("Optional native seams"); red on any native conformance suite is a regression. Run `tests/v5` with `PYTHONPATH=src`: a stale `site-packages/moneta` without `v5` otherwise breaks its subprocess tests.
> - **Next actions:** done since pass 4: `rust/` committed (`6f4696a`, with `Cargo.lock`); the v5 bundle found and merged (O35, `861bed9`); the Round 4 brief drafted (`docs/v7/ROUND4_BRIEF.md`) and **ruled** (`RULINGS.md:48-101`). Round 4 implementation pass done (§8 mile 0 status column, `279d903`…`ba52ca7`). Now: (1) the owner accepts or rejects each **met** condition on its number, and rules how E3-2's "stall" is read (writer lock hold, met at 11 ms, or worst single reader delay, missed at ≈ 44 ms on hython); (2) the open conditions, in order: E4-2 (erase reaches every copy, now with two found leak paths), E3-1's prune case (build the re-packed index outside the lock, swap it in), E1-B5, E1-B2, E3-B1–B4, the polish items; (3) two unfixed v5 defects found in reconciliation: a zero-vector slot winner hides its slot (O24), and scores drift in the last bit between hython 3.11 and Python 3.14 (`sum()` changed in 3.12); (4) re-ask the E4 Jev question with corrected option costs (`RULINGS.md`, E4; not yet done); (5) start mile 2, the Python-only experiment; (6) record the rulings in `docs/rounds/round-4.md` and amend `ARCHITECTURE.md` and `CLAUDE.md`'s locks in one PR (neither done). The two stray root files `attention_log.py` and `test_attention_log_gil_guard.py` are still untracked and still excluded.
> - **Your decisions:** the queue at the top of §9. Round 4 is ruled; closing its conditions comes first.
> - **Done this week means:** `rust/` committed ✓; O35 answered ✓; Round 4 brief drafted and ruled ✓; mile 2's harness running; Round 4's blocking conditions implemented and measured ✓ (owner acceptance pending; E3-1 partly, E4-2 open).

**Status:** design only. Nothing in v7 is built. Changes on `main` during this pass (the optional native scan and decay accelerators, §6 "Built so far") are v1-line work under v1 exact-oracle discipline, which this paper calls the seam-admission rule (O27, now RULED). D1's latency gate did not fire. v5 is now merged beside v1 as reference code (`src/moneta/v5/`), and v5's native dot seam sits under the same rule; neither is v7. They were not caused by this document and are not v7 governance; no v7 check goes green because of them.
**Date:** 15 October 2026 · **Owner:** Joseph Ibrahim · **Builds on:** the v6 blueprint (`docs/v7/inputs/BLUEPRINT_v6.md`) + `docs/v7/RULINGS.md`, with evidence from `docs/v7/pass1_rulings_brief.md`; the v5 reconciliation pass adds the merged v5 (`docs/v5/BLUEPRINT.md`, `src/moneta/v5/`, `tests/v5/`, `results/bench_v5_recall_native.jsonl`) and `docs/v7/ROUND4_BRIEF.md`
**Loop position:** Pass 4 of 4 — complete. Pass 2 synthesized three drafts (graph-first as the spine, with grafts from rust-seam-first and mile-0-first) and fixed every judge defect (Review log). Pass 3 applied the eleven-attack red team; findings needing an owner ruling became O16–O30 (Pass 3 attack log). Pass 4 applied four audits (citations, built seams, fold consistency, completeness) and the built facts of 2026-10-15 (tag `[M]`), and added O31–O35 (Pass 4 log, at the end). A final review then found two `[M]` claims false (D1's gate "fired"; the scan's exactness envelope); the `F-` rows of the Pass 4 log record the corrections. A **v5 reconciliation pass** followed: every v5-dependent claim was re-checked against the merged v5 code, tests and results at `57a90bc`, and Round 4's rulings were applied (v5 reconciliation log, at the end).
**Baseline (v5 reconciliation pass):** branch `v7-native-seams` at `57a90bc`. Every v5 citation (`src/moneta/v5/…`, `tests/v5/…`, `scripts/v5/…`, `results/bench_v5_recall_native.jsonl`, `docs/v5/…`) is to that **commit**, not the working tree: `src/moneta/v5/model.py` and `substrate.py` were being modified by a concurrent implementation workflow during this pass. Pass 4's working-tree files are now committed (`6f4696a`, `6cb6966`, `42a0368`); "on `main`" in pass-4 text means that v1-line code, which is on `v7-native-seams`, not on `main`. Since then `rust/moneta_native/src/lib.rs` grew by 67 lines (`88d1f87`, v5 dot seam: anchors after `:36` moved), `src/moneta/api.py` by 2 (`d4f9fd4`, Round 4 F1: the `signal_attention` docstring at `:416-420` grew, so anchors from `:421` on moved by +2) and `CLAUDE.md` changed; pass-4 anchors into those three files are to the pass-4 tree and were not re-anchored.
**Baseline (pass 4):** `main` at `6cf05f5` (`git describe`: `v1.2.0-rc3-1-g6cf05f5`). `pyproject.toml:7` still reads `1.2.0rc1`, so this paper cites the commit, not the version string. **Pass 4 also reads the working tree**, which is uncommitted. **Modified (6):** `src/moneta/api.py`, `ecs.py`, `vector_index.py`, `CLAUDE.md`, `README.md` and `docs/api.md`. **Untracked, part of this work:** `rust/moneta_native/`, `docs/OPERATOR_CARD_native.md`, `docs/v7/`, `scripts/bench_query.py`, `scripts/bench_arm_p.py`, five `results/bench_query_*.jsonl` files (`baseline_python`, `arm_p`, `after_seam1`, `after_seam3`, `fair_matrix`), and `tests/unit/test_native_scan_conformance.py`, `test_native_decay_parity.py`, `test_rank_early_stop.py`. **Excluded from the commit:** two untracked files at the repo root, `attention_log.py` (byte-identical to `src/moneta/attention_log.py`) and `test_attention_log_gil_guard.py`, predate this work and are not part of it. Citations into the four working-tree source files (`api.py`, `ecs.py`, `vector_index.py`, `rust/moneta_native/src/lib.rs`) and into `CLAUDE.md` give **working-tree** lines (they stay valid when that work is committed unchanged); every other `src/` file is identical at `6cf05f5`. The Appendix maps each moved `6cf05f5` line to its working-tree line.

**Tags.**
- `[V]`: verified here. That means one of three things. Either the named v1 source or `ARCHITECTURE.md` was read (at `6cf05f5`, or in the working tree for the working-tree files named in Baseline), with the file:line given and nothing run. Or the v7 ruling files were read. Or (v5 reconciliation pass) the named v5 source, test or doc was read at `57a90bc`, with the file:line given and nothing run.
- `[M]`: measured by running, on a named machine, interpreter and date, with the script and result file named. Magnitudes are machine-dependent; only the stated comparison carries. Default context unless stated: owner workstation (Threadripper PRO 7965WX, Windows), Python 3.14 and hython 3.11, 2026-10-15.
- `[P]`: proposed here.
- `[U]`: unmeasured or unknown.
- `[A]`: assumed and not yet true, **or not checkable on this machine**.
- **`[A; v6: V]`**: v6 reported the claim as verified, but it can't be re-verified here. The RSI-in-USD toy package, SYNAPSE's source, v5's 2-vCPU container measurements and the 8 September decisions are absent from this repo. **v5 itself is now merged** (`src/moneta/v5/`, `861bed9`): every v5 claim in this paper was re-checked against it, rows the code confirms carry `[V]` (or `[M]`), and rows it contradicts are corrected in place (v5 reconciliation log). Decision D1 is **given** by the task and by v6. It is a constraint, not a verified fact.

**Rulings** (`RULINGS.md`):
- **R1** `one_timeline`: RULED.
- **R4** `owner_gate`, amended (a)–(d): RULED.
- **R5** `seals_and_signing`, amended: RULED.
- **R2** `recall_half_life` and **R3** `owner_labels`: carried as `[A]` (Round 4 leaves R2 unflipped, `RULINGS.md:97`).
- **O27** (seam-admission rule): RULED, confirmed (`RULINGS.md:32-33`).
- **Mile 0 / Round 4** (v5's E1–E4 and the half-life call): **RULED 2026-10-15** (`RULINGS.md:48-101`). E1 + E2: for v5, with conditions. E3: for v5, closure gated. E4: semantics only, gated; `compact()` not ratified. Half-life: the journal owns λ; each change is an explicit, journaled choice between reinterpreting and applying forward. Each ruling **closes** only when its blocking conditions are implemented and measured (`RULINGS.md:101`); §8 lists them, with status placeholders. F1 is recorded as factual ground: v1's `signal_attention` flushes the WAL but does not fsync it (`RULINGS.md:52`).

**ID scheme** (so that no identifier means two things):

| ID | Means |
|---|---|
| `G1`–`G5` | graphs |
| `G1-1` and similar | graph invariants |
| `T P C J L X K SM` + number | rules. The v6 IDs are kept; K is keys and SM is seams |
| `Q1`–`Q12` | guarantees the seams need |
| `V-*` | checks |
| `O*` | open decisions |
| `D1` | **only** the 8 September Rust decision, verbatim: "Rust comes in only if a native scan in Python (arm P) misses its latency gate" (`BLUEPRINT_v6.md:41`). The broader seam-admission rule in §6 is **not** D1 (O27) |
| `R1`–`R5` | **only** the owner rulings |
| `E1`–`E4` | the four mile-0 Round 4 items (§8). "Contract E" (§6) is the δ-tolerance fallback, not an E-item |
| `A1`–`A51` | pass-3 attack findings (Pass 3 attack log). "Pass-2 attack n" means the n-th attack in pass 2's §10 list; "attack n" alone means §10 of this paper |
| `JA-n`, `JB-n` | review-log defects from the first and second pass-2 judge. Not rules: `J1`–`J10` are rules |
| arms A–E, arm P | mile-2 experiment arms (v6); arm P is the numpy scan of D1 |
| `δ` / `δ_t` | `δ` is contract E's ulp tolerance (an X1 value). `δ_t` is a time window (host lag) in O14 and V-MISATTR |
| single letters in gate formulas (`N`, `K`, `R`, `A`, `S`) and `[T₁, T₂]` | local variables of that formula, not rule IDs |

---

## On one screen

**What v7 is.** v7 keeps v6's governed loop, which tunes *how* memory recalls and never *what* it remembers. It is re-derived as five explicit typed graphs. Every rule is an invariant of one graph. Every check is that invariant plus the sabotage it must catch.

| Graph | Nodes | Load-bearing invariant |
|---|---|---|
| **G1 Journal** | events (record, `govern`, `seal`, `attest`, `key`, `disclose`) | append-only and hash-linked from a format-7 genesis; every typed edge points strictly backward |
| **G2 Policy derivation** | specs, contexts, layers, resolved policies | resolved policy at seq *n* is a pure function of the prefix; **values** resolve by strength with self weakest; **authorization** resolves by intersection and only narrows |
| **G3 Artifacts** | content-addressed derived leaves | a leaf is used only on a hash match and, for checkpoints, only if sealed outside every rolled-back generation's window; leaves never feed the journal or an open/restore through the substrate |
| **G4 Generation lifecycle** | one state per self generation | only legal transitions; every edge that moves the policy pointer or ends probation is owner-signed; at most one generation in {Promoted, Expired} and at most one Proposed; a promote must rest on evidence scored against the live head |
| **G5 Authority** | keys, pins, referee, held-out window, anchor | every chain of judges ends on something the loop can't write |

**What `main` actually is.** On five points, v1 is the opposite of what v7 assumes. Every row is `[V]` (at `6cf05f5`; `api.py`/`ecs.py` in the working tree):

| v7 assumes | v1 does | Where |
|---|---|---|
| reads never write (E2) | `query()` calls `decay_all`, which writes utility in place (with the wheel installed it runs in native code, `ecs.py:257-263`, and still writes in place) | `src/moneta/api.py:401`, `src/moneta/ecs.py:251-272` |
| the journal is the authority (E1) | "The vector index is authoritative for 'what exists.'" | `ARCHITECTURE.md:146` |
| one ordered journal (E3) | the attention log's correctness depends on the GIL | `src/moneta/attention_log.py:64-68` |
| prune is a tombstone (E4) | prune is `ecs.remove` plus `vector_index.delete` | `src/moneta/consolidation.py:166-169` |
| history is kept | the WAL is unlinked at every snapshot | `src/moneta/durability.py:125` |

**So mile 0 was a MONETA.md §9 Round 4 escalation, not a merge.** E1, E2 and E3 overturn decisions that `CLAUDE.md` lists under "Locked decisions — do not re-open". E4 reverses §6 prune semantics. The brief went out (`docs/v7/ROUND4_BRIEF.md`) and the owner **ruled all five toward v5, with conditions** (`RULINGS.md:48-101`; §8). The table above still describes v1, the default handle; the locks are not yet amended in `ARCHITECTURE.md` or `CLAUDE.md` at `57a90bc`. v5, merged beside v1 (`861bed9`), already does what v7 assumes on four rows `[V]`: its reads write nothing (`src/moneta/v5/substrate.py:663-701, :736-743, :892-954`), its journal is the authority and the index is rebuilt from it (`journal.py:1-6`; `index.py:1-5`), every write is ordered under one lock (`substrate.py:356, :490-502`), and prune appends a `retain` tombstone (`substrate.py:830-841`; `model.py:364-369`). On the fifth it half does: the journal only grows, except that `compact()` rewrites erased bytes in place (`journal.py:349-396`), which E4 did not ratify.

**The line (unchanged from v6).** The loop may only change what moving a pointer can undo. In graph terms, the loop's own action can add at most two `govern` kinds to G1, neither of which moves the policy pointer: the loop's unsigned `govern{tier: self, why: propose}`, which changes no policy, and, when that proposal replaces a pending one, the substrate's unsigned `withdraw` of the old one. Every edge that moves the policy pointer or ends probation needs a signature the loop can't make.

**What the line does not bound.** The stamp and the hold make a pending generation's share of host-echoed attention attributable, deferred and reversible. They do not bound the host echo loop itself (G3-2): outside probation, host echoes reach retention directly, as they do in v1.

**What v7 changes from v6, as the rulings land in the graphs:**
- a per-event hash chain (R5)
- signed promote, adopt, rollback, amend, reload and trust (R4b, R5)
- a generation stamp on every attention event, and a retention fold that drops a rolled-back generation's attention **from both utility and `attended_count`** (R4a)
- one pending generation and a probation ceiling (R4c)
- held-out pass/fail disclosure (R4d)
- record payloads **and vectors** committed by salted digest in per-record files, so erasure doesn't break the chain and leaves no confirmation oracle (new)
- a declared total order for ties, a declared fold step order, and a declared per-event time `t` in every event envelope (new)
- a checkpoint-eligibility predicate over every rolled-back generation, and a reseal that open re-appends after a crash (new)

**Rust.** Four candidate seams, each a pure function of bytes with an exact Python oracle. D1 governs only the scan, and its latency gate did not fire, so all four, the built v1-line scan included, rest on the seam-admission rule (§6), which the owner confirmed as a project constraint (O27, RULED, `RULINGS.md:32-33`):
- the referee (WASM, for the sandbox guarantee), which carries the Rust recall fold with it
- the verifier (speed, if measured; a tripwire, not built by default)
- the `moneta-py` binding of the recall fold for read-path repoints (speed, conditional on R2)
- the scan (exactness first, then speed; D1's latency gate did **not** fire: arm P clears 50 ms `[M]`. A v1-line native scan exists on `main`, admitted on the seam rule's exactness clause (O27); the v7 seam is still `[P]`)

Bit-exactness is the default. Any tolerance is a measured, recorded downgrade. Composition stays Pixar USD, and oxideav-usdz stays parked.

**On `main`, outside v7.** An optional PyO3 crate, `rust/moneta_native`, already provides a scan and a retention-decay kernel as v1-line accelerators, each bit-identical to its Python oracle on this platform for finite, non-overflowing inputs. **D1's latency gate did not fire:** in a fair matrix (N = 200 queries, 2 runs per arm, fresh and aged utilities, every arm on the same exact early-stop rerank), numpy arm P measured 26.6–29.1 ms p95 against 50 ms `[M]`. The scan was admitted instead on exactness (arm P leaves 1496 of 2000 cosines not bit-equal to the oracle) and on the zero-runtime-dependency rule, that is, under the seam-admission rule (O27), not D1. It is also 4–9× tighter than arm P at p95 with 2.7× less store RSS. Neither is a v7 seam (§6, "Built so far"). v5's `recall` gained the same kind of seam: a native dot product behind `ExactIndex.cosines`, bit-identical to v5's own Python loop on the same interpreter, which takes v5 recall p95 from 184–194 ms to 18.8–19.8 ms at 10k × 384 `[M]` (§6 "Built so far"). D1 was not measured on v5: no numpy arm P exists on v5's facade.

**No fifth op.** The agent API stays `deposit`, `query`, `signal_attention` and `get_consolidation_manifest`, and its signatures don't change. Those signatures carry no context, scopes or time (`ARCHITECTURE.md:36-37`; `api.py:328-333, 379-380`), so how a read and a deposit reach them is O16. `reload()`, the tuning pass, `verify()`, `audit()`, `erase` and the signing flow are harness-level operator ops. Precedent: `[V, ARCHITECTURE.md:46-50 (§2.1, Ruling B); src/moneta/api.py:446-451]`.

**The one ask.** Go on mile 2, the Python-only experiment, which now adds a β diagnostic arm (R2).

It needs no Moneta changes (v6 §12, `BLUEPRINT_v6.md:417`). In parallel, Round 4, now ruled (`RULINGS.md:48-101`), is closed condition by condition (§8 mile 0). Mile 2's report did not reach the round; it becomes evidence for R2 and R3.

**Position.** Mile 1 of 6, in v6/RULINGS numbering, which is kept unchanged. Mile 0 is **ruled** (Round 4) but not **closed**: its blocking conditions are open or unconfirmed (§8).

---

## 1. First principles: what v7 changes and why

**v6's five principles stand:**
1. History is append-only, and the present is a pointer.
2. Reads are pure.
3. Records don't compose; policy does.
4. Nothing judges itself.
5. The loop's only power is a typed proposal.

**v6's four facts stand:** (a) a judge sees only what it measures, (b) scores leak the test, (c) you can only react to what you were shown, and (d) replay cost has to be measured where it happens.

**v7 adds three principles.**
- **6. If it isn't an edge, it isn't enforced.** Each dependency the design relies on is a typed edge with a hash: a rollback restoring a spec, attention produced under a generation, a label drawn from a window, a checkpoint standing for a prefix. A check works by walking edges. A dependency that lives only in prose can't be checked, so the design doesn't claim it.
- **7. A seam is a pure function of bytes, and its Python oracle is the spec.** No seam takes a handle, a callback, a clock or a file path. Rust is a cache of the oracle, never its author.
- **8. Derived never feeds back.** Every artifact computed from the journal is a content-addressed leaf. No substrate path reads a leaf's content to decide what to append, or loads it as state on open or restore, except a fold checkpoint, and only after its hash matches an attested seal and it is eligible under G3-3.

| # | v6 | v7 | Why |
|---|---|---|---|
| 1 | `seal` carries a running hash; lines between seals carry only CRC-32 | **every event** carries `prev`, the running hash, from the v7 genesis (R5: "from the v6/v7 genesis"; v5 history is imported, not rewritten, see "Migration into format 7") | v6's V-SEAL clause "an edit after the last seal fails at open" can't be met by seals alone (brief, R5 skeptic #1). R5 amended. |
| 2 | the owner signs constitution changes and seals | the signed set is `govern` with why ∈ {promote, adopt, rollback, amend}, every T3 `reload`, every trust-store change, `key` events, and seal attestations | an unsigned `adopt` lets the substrate approve itself (brief, R4 skeptic). R4b and R5 amended. |
| 3 | probation attention is tagged for the eval builder only | every attention event is **stamped** with the self generation live when `signal_attention` is called, carried through the WAL. The retention fold drops attention stamped with a rolled-back generation **from utility and from `attended_count`** | v1's prune key reads `attended_count` (`src/moneta/consolidation.py:111-112`), which every signal increments regardless of decay (`src/moneta/ecs.py:242`). Without the exclusion, rollback isn't an undo. R4a. |
| 4 | no ceiling, no limit on pending generations | a probation ceiling with a default; one pending generation | R4c |
| 5 | owner evidence shows held-out scores | pass/fail only; each fuller disclosure is a journaled `disclose` that wears the window | R4d |
| 6 | truncation goes undetected | an external anchor holds the latest attested seal; the root key is pinned in code or the genesis | R5 amended |
| 7 | `govern.why` has no "propose" | the loop's proposal is a journaled, unsigned `govern{why: propose}` that changes no policy. `withdraw` and `expire` likewise | makes one-pending, V-SHADOW and V-REPLAY checkable from the journal alone `[P]` |
| 8 | erase destroys bytes in the journal | events commit to a salted digest of the payload and of the vector; both live in one per-record file `payloads/<record_id>`; erase deletes the file and every content-bearing leaf built from it, never the event | otherwise one erase breaks every later hash, two identical payloads share a file, and an unsalted digest confirms guesses `[P]` |
| 9 | ties are "included" in determinism, with no order given | **total order** `(score desc, seq asc, record_id asc)` everywhere | v1's ties fall to dict insertion order through two stable sorts: the scan (`src/moneta/vector_index.py:140,152` in `_oracle_scan`, fed `self._records.items()` at `:344-345`) and the rerank (`src/moneta/ecs.py:380` in `ECS.rank_hits`) `[V]`. A second implementation can match that only by reproducing the implicit row/insertion key: the native scan does exactly that (cosine desc, then row asc, with slots kept in insertion order; `rust/moneta_native/src/lib.rs:76-84`, Rust test `ties_break_by_row` `:284`; `tests/unit/test_native_scan_conformance.py` `:54`, `:94`, `:119`, `:133`) `[M]`. That is fidelity to v1's ties, not P5. The proposal makes the key explicit. |
| 10 | example proposal `recallHalfLife: 1209600.0` (14 days) | recall-half-life bounds are constitution content read from the journal under an X1 ceiling. **Until O28 rules, that X1 ceiling is the locked 1 min – 24 h range**, so the 14-day example stays out of range | the range is a **locked clause**, `ARCHITECTURE.md:82` (MONETA.md §2.3), implemented at `src/moneta/decay.py:33-35` `[V]`. Whether it binds the recall λ is a Round 4 question (O28), not a local call |
| 11 | fold step order is implicit | the recall-fold oracle **declares** its step order and names how it differs from v1's reducer (§2, G3). Every event carries `t` in its envelope | without it, V-ORACLE-FOLD means nothing. v1's reducer never reads the per-entry timestamp (`attention_log.py:127-131`, `ecs.py:243`), so v7's per-event fold adds a journal dependency v1 lacks |
| 12 | format 6 | the genesis declares **format 7**; v5 and v6 readers refuse it | `[P]` |

---

## 2. The typed graphs

**Notation.** Node kinds are in `code`, edge kinds are in **bold**, and `→` points from the newer thing to the older thing it depends on.

### G1. Journal: an append-only, hash-linked DAG

**Nodes.** Each node is one event at one `seq`.

**Envelope `[P]`.** Every event, of every kind, is `{seq, kind, t, prev, body}`. `t` is an f64 bit pattern from the substrate clock at append, and Q2's canonical bytes cover it, so V-CHAIN covers an edit to `t`. The substrate enforces `t` non-decreasing in `seq` at append: it stores `max(t_clock, t_prev)` and records the clamp in the event. The journal is therefore monotone and the fold needs no special case. `t0` of a record is its `deposit` event's `t`. This is a new journal dependency: v1 stamps attention with wall-clock `time.time()` (`api.py:422-424`) but its reducer never reads that timestamp (`attention_log.py:127-131`, `ecs.py:243`). Whether the clamp or a fold-side `max` is used changes anchors, so the choice is recorded with O7.

**Attention time is call time `[P]`.** An `attention` event's body also carries **`t_call`**: the timestamp captured inside the `signal_attention` call with the `gen` stamp, carried through the entry and the WAL (v1 already records it, `api.py:422-429`). The folds use `t_call`, not the envelope `t`, as `t_event` for attention. Under E3-for, attention is journaled at call, so `t_call` equals the envelope `t`. Under E3-against, a whole probation drains at one sleep pass; the envelope `t` is then the drain time and `t_call` keeps per-event time. `t_call` is made non-decreasing at capture, by the same clamp rule, under whatever ordering `signal_attention` has (the single writer under E3-for; under E3-against that ordering is itself O30's question). V-GENTAG's fixtures cover it (signal at t₁, drain at t₂ ≫ t₁: anchors equal call-time folding).

| Kind | Carries (in `body`) | Written by | Signed |
|---|---|---|---|
| `genesis` | format 7, root public key, recovery-key hash, code-ceiling hash, the initial embedder pin (host-declared id and dim) | the substrate, at create | yes (root) |
| `deposit` | record id, payload commitment `C_p`, vector commitment `C_v`, the host-declared embedder id, scope, protected floor | `deposit` | no |
| `attention` | `{record id: weight}`, plus the **`gen`** stamp and **`t_call`**, both captured inside the `signal_attention` call (G4) | `signal_attention` | no |
| `retention` | tombstone and stage decisions from a sleep pass, with the reducer's `now` | the substrate, in a sleep pass | no |
| `erase` | record id, and the erased commitments `C_p`, `C_v` (and every `C_v` a `revector` committed for that record, O25) | an owner operator op | open (O9) |
| `revector` | per record `(old C_v → new C_v)` and the new embedder pin; content otherwise as in v5: one event carrying a new vector for every recallable record, possibly at a new `dim`, with `unembedded` naming any left without one; tombstoned records lose their vector `[V, src/moneta/v5/substrate.py:956-1010; model.py:389-400]` | the owner | open (O9) |
| `consolidate`, `note` | as in v5: one `consolidate{ids, target, batch}` per successfully projected batch; `note` is provenance only, except that a legacy `half_life_change` note replays as a reinterpret change `[V, src/moneta/v5/substrate.py:867-876; model.py:371-372, :402-413]` | the substrate or the owner | no |
| `govern` | `{tier, name, why, spec, of?}`, spec inline (R1) | the substrate only | by `why` (table below) |
| `seal` | running hash at `seq`, checkpoint hash, and **the RolledBack set as of `seq`** (each generation with its `[seq(promote), seq(rollback))` window) plus the G4 state of every generation not yet Retired or Withdrawn (a handful, by G4-3), so eligibility and open can be decided from journal content `[P]` | the substrate | no |
| `attest` | owner signature over a `seal`'s `(seq, hash)` | signed by the owner off-machine, appended by the substrate | yes |
| `key` | rotate (new key) or recover (through the recovery key) | the owner | yes (old key or recovery key) |
| `disclose` | which held-out figure was shown, and for which window | the substrate, when the owner asks | no |

**v5 kinds with no row here `[V]`.** v5 also journals `import` (a v1 row with its anchor, attended count and state, `src/moneta/v5/model.py:318-335`), an operator `tombstone` (`substrate.py:1023-1037`), `retain` (one per sleep pass, even when empty, `substrate.py:830-839`; v7's `retention`) and `half_life` (an explicit λ change naming its mode, `model.py:276-278`; Round 4 half-life ruling). Under format 7, `import` becomes `deposit` events ("Migration into format 7"). Where an operator tombstone and a journaled λ change sit in G1 (their own kinds, or a `govern{const, amend}` that names the mode, G2-10) is `[P]`, not yet drawn.

**`govern.why`.** "Moves" means moves the **policy pointer**: the live self generation (or the live spec of a context or constitution) that resolution uses. A change of G4 state is not a pointer move. G4-2 requires a signature for both.

| `why` | tier | signed | moves the policy pointer? |
|---|---|---|---|
| `genesis` | any | yes | yes |
| `edit` (via `reload`, T3) | context | **yes** | yes |
| `propose` | self | **no** | **no** |
| `withdraw` | self | no | no. It ends a `Proposed` generation that the owner declined, that a newer proposal replaced, or whose base was displaced by a rollback or roll-forward (G4-8) |
| `promote` | self | yes | yes |
| `adopt` | self | yes | no. It changes G4 state (ends probation), not the policy pointer |
| `rollback`, `roll-forward` | self | rollback: yes (R4b). Roll-forward: **signed, pending O9** (treated as rollback-class; not in R4b's text) | yes |
| `expire` | self | no | no. It records that the ceiling was reached and moves nothing |
| `amend` | const, rules | yes | yes |
| `trust` (referee or eval-set pin) | const | yes | no. It changes G5 |

**Where the signature sits `[P]`.** A signed-set `govern` carries its signature **inline**, over its canonical body. The signature covers the body, not `prev`, so the owner can sign off-machine without knowing the head hash. The chain then binds the event's position.

The substrate **refuses to append** a signed-set `govern` without a valid signature. So no "inert until signed" state exists for `govern`, which answers draft-RS O13 (rust-seam-first's numbering, not §9's O13). The signed body of every self `govern` that moves the pointer or ends probation (promote, adopt, rollback, roll-forward) includes:
- the **genesis hash** of the store
- the `seq` of its **of** target (promote → its `propose`; adopt and rollback → the `promote`) or, for roll-forward, of its `restores` target
- the `seq` of the self `govern` that is **live just before it** (a compare-and-swap seq)

A signature therefore binds to one store, one target and one pointer state. Each `propose` can be promoted once, and the live-head seq goes stale as soon as the pointer moves, so a replayed promote, adopt, rollback or roll-forward body is refused even when it targets a spec that recurs (a re-proposed spec, a re-entered generation). A second adopt of the same generation is also an illegal G4 transition. Together these rule out replay within a store and replay into another store (V-STATE).

Seals are different. They are written on the loop machine and attested later by a separate `attest` event. The verifier reports `signed_through_seq`, which is the seq of the latest attested seal. Everything after it is hash-chained but unattested. That window is what K2's anchor and O12 bound.

**Edges.**

| Edge | From → to | Meaning |
|---|---|---|
| **prev** | every event → the event at `seq − 1` | `h_n = SHA-256(h_{n−1} ‖ canonical(event_n))`, where `canonical` is Q2's single encoding with payload and vector bytes replaced by their commitments. This is the backbone and gives a total order. |
| **restores** | `govern{rollback \| roll-forward}` → an earlier `govern{promote \| genesis}` of the same tier and name | the restored spec is byte-identical to the target's |
| **of** | `govern{promote}` → its `govern{propose}`; `govern{adopt \| rollback \| expire \| withdraw}` → the `govern{promote \| propose}` it acts on | which generation the transition concerns. Each `propose` is the target of at most one `promote` |
| **scored_against** `[P]` | `govern{propose \| promote}` → the self `govern` (promote, genesis, rollback or roll-forward) that was the live head when the tuning pass scored | the baseline the margin was measured against (G4-8) |
| **about** | `attention`, `retention`, `erase`, `revector` → `deposit` | which record |
| **produced_under** | `attention` → the self `govern` (promote, genesis, rollback or roll-forward) live **when `signal_attention` was called** | the `gen` stamp, made explicit. The `seq` of a drained attention event can be later than its stamp; the stamp, not the `seq`, decides G4-5 exclusion |
| **checkpoints** | `seal` → a G3 checkpoint leaf, by hash | the leaf stands for the prefix up to the seal **under the exclusion set it names** in `built_from` |
| **attests** | `attest` → `seal` | owner signature over the seal |
| **evidence** | `govern{propose \| promote}` → G3 verdict, eval-set and referee leaves, by hash | what the decision rested on |
| **signed_by** | any signed event → the `key` or `genesis` valid at that `seq` | which key |
| **commits** | `deposit`, `revector` → `payloads/<record_id>` | the payload and vector, by salted commitment. After an erase the edge dangles, and an `erase` **about that record** explains why. A dangle with no such erase is `Fail{kind: payload_missing}` |

**Invariants.**
- **G1-1 Linear backbone.** Every `prev` equals the hash of the predecessor's canonical bytes. There is one genesis and no forks.
- **G1-2 Backward only.** Every **event-to-event** typed edge targets a strictly lower `seq`, so G1 is acyclic by construction. Edges that target a leaf, file or blob (`checkpoints`, `evidence`, `commits`, and G3's `labels`, `labeled_by`, `window`) are bound by hash and constrained by `built_from` (G3-1, G3-3), not by `seq`.
- **G1-3 Edge typing.**
  - `restores` targets a `govern` of the same tier and name, and the restored spec equals the target's spec byte for byte.
  - `about` targets a `deposit`.
  - `produced_under` targets the self generation live when the attention was signalled (G4, "The `gen` stamp").
  - `scored_against` targets a self `govern` of a lower `seq`.
  - `signed_by` targets the key valid at that `seq`.
- **G1-4 Signed set.** Every event whose kind or `why` is in the signed set carries a valid ed25519 signature. That signature chains back to the genesis root key through `key` events.
- **G1-5 One writer.** Only the substrate appends. The tuner never holds a handle (v6 L3). For v5 the single write path is `[V]`: every append goes through `Substrate._append` (`src/moneta/v5/substrate.py:490-502`; the only `_journal.append` call is `:492`), `compact()` rewrites through `_journal.rewrite` (`:1090`), and the facade's migration and snapshot guard call the same `_append` (`compat.py:431, :465, :860, :906, :939`). The tuner half is `[P]`: v5 has no tuner.
- **G1-6 Payload commitment.** Every `commits` target is either present, with its stored nonce, payload and vector hashing to the commitments, or it is absent and an earlier `erase` about that record names those commitments. Anything else is `Fail{kind: payload_missing}` (or `payload_mismatch`). An erased record's content is gone from `payloads/` **and from every derived leaf** (G3-9); its commitments, record id, scope, floor, attention and retention events, and timing stay. Checked by V-ERASE and V-PAYLOAD.
- **G1-7 Format.** The genesis declares format 7. Anything else is refused.
- **G1-8 Finite floats `[P]`.** The canonical codec refuses a non-finite float (NaN, ±inf) in every journaled float field: `t`, weights, floors, bounds, utilities. `-0.0` is canonicalized to `+0.0`. The fold therefore never sees a non-finite input from the journal.

**Why payloads and vectors move out of the journal `[P]`.** With a per-event chain, removing bytes in place invalidates every later `prev`. If each event commits to the content, erase can delete the bytes and the chain still verifies. A vector is a payload: an embedding is approximately invertible to its text, so it must be erasable the same way. Keeping vectors inline in the event would make them unerasable without breaking the chain.

**The commitment `[P]`.** One file per record, `payloads/<record_id>`, holds a 32-byte CSPRNG nonce, the payload bytes, and the vector in Q2's vector encoding (dim, little-endian f64 bit patterns; any non-finite component, NaN or ±inf, refused at deposit as in G1-8; `-0.0` components canonicalized to `+0.0`). The commitments are `C_p = SHA-256("moneta.payload" ‖ nonce ‖ payload)` and `C_v = SHA-256("moneta.vector" ‖ nonce ‖ vector)`. Naming files by record id means two records with identical payloads never share a file, so erasing one leaves the other intact. Salting means a digest left in the permanent, anchored chain doesn't confirm a guessed low-entropy payload, or a guessed payload pushed through a deterministic embedder. Erase deletes the file and with it the nonce.

**Write order `[P]`.** The journal is the authority for existence, order and commitments; `payloads/` is the authority for bytes. Neither alone restores the store, so backup and migration copy `journal/` and `payloads/` together.
- **Deposit:** write the payload file to a temp name, fsync, rename, fsync the directory, then append the `deposit` event. A crash before the append leaves an orphan file, which the audit removes under the single writer (G1-5), and only if no `deposit` in the journal or the unsealed tail names it.
- **Erase:** append and fsync the `erase` event first, then delete the file and the content-bearing leaves (G3-9). A crash in between leaves a present file that an `erase` names, which open finishes deleting.

**Migration into format 7 `[P]`.** R5's chain starts "from the v6/v7 genesis" without rewriting v5 history (`pass1_rulings_brief.md:325`). The format-7 genesis therefore names the SHA-256 of the imported v5 (or v1) store state, and each imported record enters as a `deposit` event with its commitments, written payload-file-first like any deposit. The old store is kept read-only beside the new one, so the imported state stays checkable against the hash the genesis names. V-FORMAT's refusal of formats 5 and 6 applies to opening them as live stores, not to this import. The 841-record cutover at mile 0 uses this path.

The costs:
- one file per record, read lazily: a payload is verified against its commitments on read, and a mismatch is a typed fault, not a crash. Open trusts the **payload manifest** (a Merkle root over `(record id, C_p, C_v, present|erased)`) by seal, as part of the checkpoint (G3), so open stays O(tail). The open-time cost is a gate under O13.
- per-record files rule out deduplication.
- `compact`, which physically rewrites the journal, can't keep the chain at all. It becomes a signed **re-genesis** that names the old final hash (O8).
- E1 does not retire the two-store write. It reduces it to a fixed-order, verifier-checked one (§7).

### G2. Policy derivation graph

**Nodes.**
- `Spec`: a validated canonical spec, content-addressed by fingerprint. Each comes from exactly one `govern` (R1).
- `Context`: a named binding with an optional parent. In USD it is named by fingerprint, never by natural-language name (substrate convention #1, `CLAUDE.md`).
- `Layer`: one tier's opinion in one context.
- `Resolved(c, n)`: the resolved policy for context `c` at prefix `n`.

**Where each tier sits.** The five tiers don't all enter read-time resolution, and leaving that unsaid left the order incomplete.

| Tier | Enters `Resolved(c, n)`? | Role |
|---|---|---|
| X (code ceilings) | no | bound the constitution's bounds (X1) |
| `const` (constitution) | **no read-time values.** It contributes **bounds and pins**, checked at write (G2-6), plus **global write-time retention values** (G2-10) | referee, metric, eval set, holdout, bounds, budget, margin, ceiling, retention policy and its half-life (`BLUEPRINT_v6.md:114, :119`) |
| `rules` | **never** | the tuner's search settings: step sizes, candidates per pass, open names (`BLUEPRINT_v6.md:115`) |
| `owner@c` (context layers via `reload`) | yes | values and authorization |
| `self` | yes, **weakest** | read-time values only (`BLUEPRINT_v6.md:116`) |

**Edges.**
- **parent**: `Context → Context`. These must form a forest.
- **live_at**: `Layer → Spec`. The latest `govern` for that tier and name at or before `n`.
- **stronger_than**: a total order on the value-bearing layers along a chain `c, parent(c), …, root`: `owner@c > owner@parent(c) > … > owner@root > self` `[P]`. The nearer owner wins, and self is weakest everywhere (C1). `const` and `rules` are not in this order because they hold no read-time values. Their place is fixed by the table above.
- **narrows**: `Resolved(c) → Resolved(parent(c))`, for scopes and exclusions.
- **derived_from**: `Resolved(c, n) → {Spec}`.

**Two resolution rules, plus one read-time step.**
- **Values** (`recallHalfLife`, slot **preferences**, other scalars) resolve **by strength**: the first opinion along `stronger_than` wins. This is USD's LIVRPS strength ordering, so USD can compute it. A slot preference is what is stored and resolved; the slot **winner** a caller receives is not a field of `Resolved` (below).
- **Authorization** (scopes, exclusions) resolves **by intersection** along `narrows`. A child can only remove what its parent admits `[P]`. **That is not v5's rule** `[V]`: v5 resolves `include_scopes`, `exclude_scopes` and `exclude_records` by strength, the strongest authored list replacing a weaker one (`src/moneta/v5/policy.py:9-13, :203-207`), so a v5 child context can admit a scope its parent does not. v5's I5 is narrower: the caller's `allowed_scopes` intersect with the resolved policy and can only narrow it (`substrate.py:550-553`; `tests/v5/test_conformance.py:223-243`). **USD's LIVRPS cannot compute an intersection.** So in v7 the intersection is computed only by the plain resolver. The derived USD policy layer carries each context's **already-intersected, flattened** authorization set as an ordinary value `[P]`. USD composes the values and *displays* authorization. It never derives it (O3).
- **Slot winner (read time).** v5 removes records the caller may not see (and tombstoned, erased, scope-excluded and record-excluded ones) before a slot's winner is picked, so the caller's scopes change slot outcomes `[V, src/moneta/v5/substrate.py:545-571]`. v7 makes this an explicit pure step of the read (P1), not of policy resolution: `winner = first entry of Resolved(c, n).slotPref admitted by flatten(scopes(c)) ∩ callerScopes, minus exclusions(c)`, ties under P5. Extending the filter from caller scopes to the context's intersected authorization is `[P]`. What a slot preference is and what a slot resolves to when its preference is not admitted were O24; v5's code answers both (O24): one record id per slot, and otherwise the latest-deposited admitted claim wins. USD displays the preference, never a winner.

**Invariants.**
- **G2-1 Purity.** `Resolved(c, n)` depends only on the journal prefix to `n`. It reads no file, no clock and no draft. How `c` and the caller's scopes reach an agent read under the locked `query(embedding, limit)` is O16; the slot winner is prefix-pure only given the caller's scopes.
- **G2-2 Forest.** `parent` has no cycles, depth is ≤ X1, and every parent exists at `n`. A `reload` that would break this is refused before anything is journaled.
- **G2-3 Self weakest.** `self` comes last in `stronger_than` in every stack.
- **G2-4 Self authors only open read-time scalars.** The self tier may set only the names on the open list (`recallHalfLife` in v7.0, or `utilityExponent` if R2 flips). It can't author records, scopes, exclusions or slot preferences (v6 C2), **whatever the open list contains**. Slot preferences are values, but self can't author them because they choose among records, not because the open list omits them.
- **G2-5 Narrow only.** For every `c`, `scopes(c) ⊆ scopes(parent(c))` and `exclusions(c) ⊇ exclusions(parent(c))`.
- **G2-6 Bounds.** Every self or owner value lies inside the constitution's bounds, and those bounds lie inside X1. **Recall-half-life bounds are constitution content, read from the journal, never hard-coded.** The range they may span is the locked `ARCHITECTURE.md:82` range (1 min – 24 h, implemented at `src/moneta/decay.py:33-35`) until O28 rules whether that lock binds the recall λ.
- **G2-7 The two resolvers agree, on value fields.** The plain and USD resolvers produce byte-identical **value** fields of `Resolved(c, n)`, including slot **preferences**, for every stack, including stacks with a self layer. For authorization fields, the USD layer's flattened set equals the plain resolver's intersection. That is a rendering check, not a second derivation. The slot winner is not checked here; it is a read-time step checked by V-REPLAY. Tags: without self, `[V]` for v5's test (60 random specs; plain and USD `semantic()` and fingerprint equal for every context, `tests/v5/test_review_regressions.py:316-327`) and `[M]` (it passes under Python 3.14 with `pxr`, `tests/v5` at `57a90bc`). v5 resolves every field, scopes included, by strength (above), so that test covers strength-resolved authorization, not v7's flattened intersection. `[P]` with self and for the split.
- **G2-8 Three evaluation points.** In v1, stored retention utility is evaluated at exactly the locked three points (`ARCHITECTURE.md:84-90`; `attention_log.py:129-131`, `api.py:401`, the sleep pass) `[V]`. Under v7's declared per-event retention fold (G3), retention utility is decayed at each attention event's `t`, before the add; whether that is point 2 ("immediately after the attention-write phase") or a fourth point is open `[P]` (O29, with O7). The recall fold is a derived, pure view that writes nothing back to retention state `[P]`. Whether `ARCHITECTURE.md:90`'s "no fourth evaluation point" admits such a view is a question for Round 4 (O2), not a local call. Round 4 replaced the count: "Three evaluation points" becomes "zero mutation points; state changes only through journaled events" (`RULINGS.md:55`). A pure recall view mutates nothing, so O2 is answered in substance; it closes when `ARCHITECTURE.md` is amended to say so.
- **G2-9 Slot winner admitted `[P]`.** A read never returns a slot winner outside `flatten(scopes(c)) ∩ callerScopes`, minus `exclusions(c)`. Shape and empty-slot fallback: O24 (v5's answer: one id; otherwise the latest admitted claim; v7's choice is the owner's).
- **G2-10 Retention values are global `[P]`.** The retention half-life (λ_retention) is one global `const` value: no context layering, never in `Resolved`, consumed only by the retention fold, changed only by an owner-signed `amend`, and inside X1. Changing it is a held change that a pointer move can't undo. Under Round 4's half-life ruling the journal owns λ, and each change is an explicit, journaled, owner-authorised choice between **reinterpreting** history (the new λ applies from each record's last anchor) and applying it **forward** (records are rebased at the change, so earlier decay keeps the old λ) (`RULINGS.md:92-97`). v5 implements both modes and holds the first sleep pass after a change as a dry run `[V, src/moneta/v5/model.py:246-278; substrate.py:504-527, :805-829]`. That the `amend` carries the mode is `[P]`. HL-1: **met** `720b3b0`+`a777287` (verified, owner to accept) `[V]`. HL-2: **met** `720b3b0` (verified, owner to accept) `[V]`. The prune and stage thresholds (0.1, 0.3, 3) are **locked Round 2 constants** (`consolidation.py:53-57`), recorded in the constitution only as pins; changing them needs MONETA.md §9, not `amend`. No `owner@c` or self layer may name a retention field: a `reload` that does is refused before it is journaled.

**This is not the cortex stack.** v1 already composes *records* through sublayers:
- protected memories live in `cortex_protected.usda` at the strongest root position
- rolling sublayers are inserted at position 1 behind it

`[V, src/moneta/usd_target.py:47-48, 101, 225-226, 252-259]`. That is G3's record projection. G2's policy stack is a different graph with a different job. The two share USD and nothing else.

### G3. Artifact graph: content-addressed leaves that never feed back

**Input nodes** (authorities, or inputs from outside the store):
- `Prefix(n, h)`.
- `QueryRecord`, owned by the host (v6 P2). Its **at** edge points to a `Prefix`. It holds:
  - the echo `{seq, time, context, policy fingerprint}`
  - the caller's scopes
  - the exact f64 embedding, and the host-declared embedder id (a QueryRecord whose embedder id differs from the record vectors' leaves the rebuildable eval set, like an erase)
  - the limit
  - the returned ids, and their scores (so a near-tie at rank k is visible from the log)
  - the host request id
- `Label`, with three edges:
  - **labels** → (`QueryRecord`, record id)
  - **labeled_by** → the owner's key, or a model pin plus request hash
  - **window** → its query's window
- `Blob`: a referee module, eval set or label set, named by SHA-256.

**Derived leaves** (those marked † carry record content and are invalidated by erase, G3-9):
- fold checkpoint (retention fold + recall anchors for the live λ + the payload-manifest root + the vector-index leaf hash + the exclusion set it was folded under)
- vector index †, built only from committed vector bytes
- recall anchors
- USD policy layers
- USD record projection (cortex) † (`usd_target.py:320` authors a `payload` attribute per prim `[V]`)
- the v1-format `snapshot.json` export † (`durability.py:90-91` writes `payload` and `semantic_vector` per row `[V]`). **Export-only in v7**: the facade's open and restore replay the journal and never call v1's `hydrate` (`api.py:229`) on it, pending O19. It records the seal seq and hash it was built from, in `derived/INDEX`, not inside the v1 file
- eval set † (pool rows carry `cos`)
- verdict

**Edge.** **built_from**: leaf → its exact inputs by hash, plus the builder version. No edge leaves a leaf. An eval set's and a fold checkpoint's `built_from` names `Prefix(h_build)`, the head prefix it was built from, so the excluded-generation set it honoured is fixed by the journal.

**The fold, with its step order declared.** v1's attention reducer, read at `6cf05f5` `[V]`:
1. Sum a batch's weights per record (`src/moneta/attention_log.py:97-105`).
2. Add the sum to the stored utility, which was last evaluated at an earlier point, and clamp to 1 **once per batch** (`src/moneta/ecs.py:240-241`).
3. `attended_count += count` (`:242`).
4. `_last_evaluated = now` (`:243`).
5. Only then call `decay_all` (`src/moneta/attention_log.py:129-131`). For attended rows, `dt = 0` at that point.

So **decay owed since a record's previous evaluation point is forgiven** whenever attention lands, unless a `query` (eval point 1, `api.py:401`) ran in between. This is observed v1 behavior under locked §4/§5 semantics, not a claim of a bug. v6's "decay with the floor, add the weight, clamp to 1" (`BLUEPRINT_v6.md:224`) is v5's per-event order `[V, src/moneta/v5/model.py:337-348]`: per record in an `attend` event (ids sorted), `u = decay_value(anchor_u, anchor_t, floor, λ, t)`, then `u + w` clamped to 1, then `anchor_t = max(t, anchor_t)` and `attended += 1`. It is **not** v1's. v5's time rule is that fold-side `max`; v5 does not clamp `t` at append (`substrate.py:487-488` takes a host `t` after a finiteness check) (O7).

v7 declares the following `[P]`:
- **Recall-fold oracle order (per event, sorted by `(record, seq)`):** `u ← decay_value(u, t_last, floor, λ_recall, t_event)`, then `u ← min(1, u + w)`, then `t_last ← t_event`, where `t_event` is the event's time: `t_call` for attention (G1, "Attention time is call time"; equal to the envelope `t` under E3-for), the envelope `t` otherwise (non-decreasing by G1) and `t0` is the deposit's `t`. Attention whose `produced_under` generation is in **`excluded_gens`** is skipped. `excluded_gens` is supplied by the caller:
  - for the referee and the eval-set builder, it is the RolledBack set as of the build head `h_build` (G3-7);
  - for live recall anchors and ranking, it is **empty** under O6's default, and becomes the RolledBack set as of `n` (never as of head) only if the owner rules O6 "both".
- **The excluded set has an "as of".** `excluded(k)` = every `g` that is RolledBack in the journal prefix up to `k`, computed from the whole prefix **before** folding, never by a streaming fold that adds `g` when it reaches the rollback. The only source of it at head is the verifier's `Verdict.rolled_back_gens` (§6). Rebuilding a read at `n` uses the set as of `n`.
- **Retention fold:** the same per-event order under the constitution's global retention λ (G2-10), with `attended_count += 1` per non-excluded event. Whether retention keeps v1's per-batch order instead is a Round 4 question that touches lock 2 as well as lock 3 (O7, O29), because it changes which records prune.
- **Fixtures:** V-ORACLE-FOLD's corpus includes a case where per-event and per-batch orders give different anchors, a backward clock step at append (clamped by G1's envelope rule), and NaN, ±inf, -0.0 and subnormal inputs (rejected at the seam boundary, or exactly `decay.py:66-69`'s behaviour on the finite ones). The sabotages "per-batch clamp in one implementation" and "clamp written as `dt.max(0.0)`" (which maps a NaN Δt to `utility`, where `decay.py:66-69` returns the floor) must be caught.

**Invariants.**
- **G3-1 Content address.** A leaf's name is the hash of its bytes, and `built_from` fixes its inputs.
- **G3-2 Never feed back (through the substrate).** No G1 event's content is computed from a leaf's content, and no substrate append, open or restore path loads a leaf's content into substrate state except a checkpoint eligible under G3-3. The journal may *name* a leaf by hash (`checkpoints`, `evidence`), which is a reference, not a dependency. **These host- or owner-mediated paths exist and are named here:**
  1. **Recall anchors → `query` → host echo → `attention` (primary).** SYNAPSE fills a pool of `max(3×limit, 50)` from `query`, which ranks by `max(cos, 0) × utility` (`src/moneta/ecs.py:371`, inside `ECS.rank_hits`, called from `api.py:408`) `[V]`, reranks it with its own scorer, and signals attention on its own top five, weighted by its reranker score (`BLUEPRINT_v6.md:25, :97, :99`) `[A; v6: V]`. In v7, recall anchors are a leaf rebuilt under the promoted generation at probation (§3 step 8), so this is leaf → host → `attention`. v6 named it the loop's indirect route (`BLUEPRINT_v6.md:121`).
  2. **`snapshot.json` → host → `attention` (secondary, `[A]`).** SYNAPSE reads the export (`BLUEPRINT_v6.md:132`); no source shows that its ranking uses the exported utility.
  3. **Verdict → tuner view (J3 train scores) → `propose`.** Creates only an unsigned, non-moving `govern`.
  4. **Verdict → owner → `promote`, `adopt`, `rollback`.** Creates signed `govern` events, not attention (pass-2 attack 2's question).

  **Bounds, stated plainly.** The substrate can't cut paths 1 and 2, because the host is outside.
  - Retention effect of path 1 during probation: held by G4-4, undone on rollback by G4-5.
  - Recall effect of path 1 during probation: **live and not bounded**. The anchors are rebuilt under `g` and the recall fold skips nothing under O6's default, so `g`'s echo inflates `g`'s own recall utility while `g` is being evaluated. The verdict that informs adopt is computed in that self-reinforced state (V-MISATTR measures it; O6, O20).
  - Outside probation (all real-store life through mile 4, per G4-6), host echoes reach retention directly, raise `attended_count` with no decay (`ecs.py:242`), and a record echoed past `PRUNE_ATTENDED_THRESHOLD` (3) can no longer prune (`consolidation.py:55, 111-112`); it can still stage. That is pre-existing v1 behaviour outside G3-2's scope, and v6's "what ranks well may keep ranking well" stays `[U]` (`BLUEPRINT_v6.md:97`), to be sized by V-MISATTR's mile-2 simulation arm.
  - For paths that rank on retention-derived leaves (path 2), every event in probation is stamped `g` but not caused by `g` (O20).
  - A stale export after a rollback is handled by G3-3's export rule and Open step 7.
- **G3-3 Use only on a match, and only an eligible checkpoint.** A leaf is read only if its hash matches one the journal names or one recomputed from its inputs. A mismatch means rebuild, never trust. A fold checkpoint is **eligible** only if it is named by a seal at `seq s` such that, for **every** generation `g` that is RolledBack at head, `s` lies outside `[seq(promote_g), seq(rollback_g))`, a window that includes any Expired span; and the RolledBack set the seal **carries in its body** (G1 table) equals the head's RolledBack set restricted to `seq ≤ s`. Because both sides are journal content, the verifier evaluates the whole predicate from G1 alone; the checkpoint's `built_from` exclusion set must in turn equal the set its seal carries, checked by the harness after the hash match `[P]`. The same predicate, **including attestation**, selects the base for a reseal (G4-5) and the start of open (§3 Open); it also selects the checkpoint behind every periodic seal. The `snapshot.json` export is current only if its recorded seal seq is at or after the latest rollback; otherwise it is deleted at the rollback and rebuilt at open.
- **G3-4 Disposable.** Deleting every derived file changes no answer once leaves are rebuilt. The vector index is rebuilt only from committed vector bytes (G1-6), never from `snapshot.json` or another leaf.
- **G3-5 Byte-identical rebuild.** The eval set rebuilds byte-identically from `Prefix(h_build) + QueryRecords + Labels` (v6 P2). The builder computes `cos` in the deterministic left-to-right oracle order (the semantics of `vector_index.py:145-147`, already ported once as `dot_seq`, `rust/moneta_native/src/lib.rs:28`), never via BLAS. Measured: a numpy/BLAS scan gave 1496 of 2000 cosines not bit-equal to the left-to-right oracle at 384 dims `[M; scripts/bench_arm_p.py → results/bench_query_arm_p.jsonl]`. **Exception:** an eval set whose QueryRecords or pool rows touch a record erased at or before the rebuild, or whose embedder id differs from the record vectors', is not silently rebuilt under the same hash. It is marked unrebuildable by a journaled note naming the `erase` (or `revector`) seq, and the pinned blob stays the record of it. Which side of that line a revector falls on is O25; whether erase may take vectors that replay needs is O18.
- **G3-6 Label window.** A label's inputs lie inside its query's window, and no held-out query reaches train.
- **G3-7 Rollback excludes.** An eval set built at head `h_build` contains no attention stamped with a generation RolledBack in `Prefix(h_build)` (R4a; V-LEAK). Under O6's default the queries in a rolled-back window were served with that attention, so the referee scores them against a history that was never served; that consequence is part of O17.
- **G3-8 Projection envelope.** The record projection keeps §15.2 constraints #1–#3: rotation at 50k prims, consolidation only in idle windows > 5 s, at most 500 staged prims per pass `[V, ARCHITECTURE.md:271-273]`, and `Sdf.ChangeBlock` (convention #5). Checked by V-ENVELOPE. A held backlog released at adopt or rollback drains over several passes, each in its own idle window; carried-over stage candidates (`attended_count ≥ 3`) can't become prune candidates, so draining changes only when content is authored, and V-UNDO compares the whole drain. A held backlog lands in the release day's `cortex_YYYY_MM_DD` layer (`usd_target.py:157-160`), so that layer's date no longer says when content was authored. **Constraint #4** (LanceDB shadow commit ≤ 15 ms p99, `ARCHITECTURE.md:274`) is not carried: v1 has no LanceDB commit (`vector_index.py:35-44`) and in v7 the vector index is a derived leaf off the deposit path. It is superseded with E1 and goes to Round 4; no new budget is invented here.
- **G3-9 Erase reaches leaves `[P]`.** Erase invalidates every leaf whose `built_from` reaches the erased record's `deposit` or commitments, transitively, and every leaf of a content-bearing kind (†). Builders skip erased records, so rebuilt leaves exclude them. Journal references (`checkpoints`, `evidence`) to a deleted leaf become explained dangles; G3-3 then forces a rebuild, never a trust, and an erase that invalidates a sealed checkpoint triggers a reseal. Host-held copies (SYNAPSE's export copy, `host/querylog/`) are the host's obligation; the erase op lists them in its output.

**A lock collision, surfaced here.** Making the vector index a leaf makes the journal the authority for what exists. v1's locked rule says the opposite `[V, ARCHITECTURE.md:146, :152]`. That is E1. As drawn, G3 **depends on E1 being ruled for at mile 0**. **E1 was ruled for** (`RULINGS.md:54`), so G3 stands as drawn and is not redrawn with a second authority. E1's conditions still gate the cutover (§8).

### G4. Generation lifecycle: a typed state machine

There is one machine per self generation `g`, and every transition is one `govern` event in G1.

```
                 propose (unsigned, moves nothing)
   (none) ─────────────────────────────────────▶ Proposed ──withdraw (unsigned)──▶ Withdrawn
                                                    │
                                          promote (owner-signed)
                                                    ▼
                                                 Promoted ──ceiling reached: expire (unsigned, moves nothing)──▶ Expired
                                                  │    │                                                         │    │
                                   adopt (signed) │    │ rollback (signed)                         adopt (signed) │    │ rollback (signed)
                                                  ▼    ▼                                                         ▼    ▼
                                            Adopted    RolledBack                                          Adopted    RolledBack
                                                  │
                     a later promote of g′, or a rollback (signed) ──▶ Retired
```

Expired has exactly two exits, both owner-signed: `adopt` → Adopted and `rollback` → RolledBack. They are the same targets as from Promoted.

**Not yet drawn.** Roll-forward is signed and pointer-moving (G1 table, G4-2, T4), but the diagram gives it no source or target state, and a rollback of an Adopted generation goes to Retired, where G4-5 never fires although R4a's text applies "on rollback". Both are O21; the diagram is not redrawn until the owner rules.

**Invariants.**
- **G4-1 Legal transitions only.** Only the arrows above exist, plus whatever O21 adds for roll-forward. The G4 state table rejects every other transition, checked by V-STATE. If `moneta-verify` is built, its Rust state types also make an illegal transition unrepresentable. This mirrors the amendment channel `Draft → Measured → Signed → Enacted` (v6 §10).
- **G4-2 Signed state changes.** Every self `govern` that moves the policy pointer (promote, rollback, roll-forward) or ends probation (adopt) is owner-signed: promote, adopt and rollback by R4b; roll-forward pending O9. `propose`, `withdraw` and `expire` are unsigned, and each moves neither the pointer nor a generation out of probation. V-STATE checks both: propose, withdraw and expire change neither; adopt changes G4 state only.
- **G4-3 One pending.** At most one generation is in {Promoted, Expired}, and at most one is Proposed (R4c, read as one pending plus one proposal). A new `propose` while one is Proposed is preceded by a substrate `withdraw` of the old one. Consequence for the owner: a loop proposal can withdraw a proposal the owner is reviewing, and the owner's signed `promote` of it is then refused and reported. Refusing a new `propose` while one is Proposed would avoid that but narrows R4c's reading; it is not adopted here.
- **G4-4 Hold.** While any generation is in {Promoted, Expired}, no `retention` event is appended (v6 J7). **What the hold costs:** memory, the attention backlog and the unattested tail grow without retention for as long as the hold lasts (`BLUEPRINT_v6.md:126`), and v1's `MAX_ENTITIES` pressure trigger (`consolidation.py:49, 87-90`; locked through ARCHITECTURE.md §6 and §15.7) can't produce a pass. In v1 `should_run` is defined but never called from `src/moneta/`, so the trigger is advisory and deposits are never refused `[V]`. The hold overrides it visibly: crossing `MAX_ENTITIES` under a hold raises an alarm. What else happens then is O23.
- **G4-5 Rollback undoes retention effects.** Once `g` is RolledBack:
  - the retention fold excludes every `attention` event whose **produced_under** points to `g`, from **utility and `attended_count`** (R4a), on **every** later sleep pass and across reopen, not only the first. The excluded set is `excluded(k)` (G3), taken from `Verdict.rolled_back_gens`.
  - the substrate appends a `seal` over a checkpoint rebuilt from the latest **eligible, attested** seal (G3-3), which is never one sealed inside any rolled-back generation's window; if none qualifies, it folds from genesis. The base must be attested for the same reason as at open: an unattested tail may have been edited, and a reseal built on it would launder the edit into a new seal `[P]`.
  - the substrate deletes the `snapshot.json` export and the recall-anchor leaves before appending the rollback, so a crash leaves no export older than the rollback.
  - the substrate appends an unsigned `withdraw` of any Proposed generation whose `scored_against` base is no longer live (G4-8). Roll-forward does the same; adopt doesn't, because it leaves the policy unchanged.
  - **Crash between the rollback and its reseal.** The rollback and the reseal are two events. Open re-appends a missing reseal (§3 Open step 5) before it serves, and no `retention` event or sleep pass is accepted until the reseal exists. In the journal, the latest seal follows the latest rollback once open completes; the latest **attested** seal may not, which Open step 2 handles.
- **G4-6 Shadow.** Through **mile 4** (RULINGS.md R4, literal), no generation on a real store leaves Proposed. Mile 4 exercises the full cycle on **test stores only**.
- **G4-7 Ceiling.** The constitution sets a probation ceiling. The default is 14 days `[P; value U]`, with a maximum under X1. When the ceiling is reached:
  - `expire` is appended
  - retention stays held
  - an alarm is raised
  - new proposals are refused

  The pointer doesn't move without a signature, so J6 is kept. Auto-rollback is the alternative (O5). **Under the O5 default the ceiling is an alarm, not a bound:** Expired has no time limit, so for an absent owner the hold, its memory growth and the mass that a later rollback drops all scale with the absence (O22).
- **G4-8 Fresh base `[P]`.** A `propose` carries a **scored_against** edge to the self `govern` that was live when the tuning pass scored it, and the verdict leaf records that seq in `built_from`. The signed `promote` body carries the same base seq. The substrate refuses `promote` unless the live self generation at append equals that base. A proposal scored against `g` during `g`'s probation can therefore never be promoted after `g` is rolled back, and the owner's signature covers the comparison the owner reviewed. Comparing seqs, not values, means an adopt never falsely blocks.

**The `gen` stamp is the generation live when `signal_attention` is called.** `signal_attention(weights)` keeps its locked signature `[V, src/moneta/api.py:413; ARCHITECTURE.md §2]`, and v1 attention entries carry only `(entity_id, weight, timestamp)` (`src/moneta/attention_log.py:73`). So the host passes no echo, and the substrate can't know which results an attention event answers. v7 defines the stamp precisely `[P]`; the design is the same under either E3 outcome, but under E3-against its first bullet needs §9 (O30):
- `signal_attention` reads the live self generation under the same single writer that orders `govern` appends, so a promote or rollback can't interleave between the read and the buffer append. **Under E3-against this is not free of §9:** §5.1 stays locked ("the log is lock-free", no per-entity locking, `ARCHITECTURE.md:108-112`), so taking that writer needs a §5.1 amendment, or a lock-free stamp (read an immutable generation snapshot and accept a bounded race, sized by V-MISATTR). Routed to O30.
- The stamp is stored in the in-memory entry **and** in the WAL record (`api.py:425-429` writes both today, without a generation). WAL replay restores the stamp; it never re-stamps at recovery. The WAL record format changes; that is internal, so no §9.
- The journal `attention` event copies the stamp from the entry and never reads the live generation at drain.

Without this, v1's flow (entries buffered until the sleep pass drains them, `consolidation.py:153-155`, while G4-4 holds every pass) would stamp all of a probation's attention with the rollback event, and G4-5 would exclude nothing.

**Misattribution windows, named.**
- **Host latency.** Attention that arrives just after a promote or rollback, for results shown just before it, is stamped with the wrong generation. That cuts in both directions: rolled-back influence survives, or good attention is dropped. Its size on the prune key is measured by V-MISATTR, not argued: per window, at most the number of distinct entity ids attended inside it whose `attended_count` is within 1 of 3 and whose utility is below 0.1 at the first pass. `signal_attention` takes an unbounded dict (`api.py:413`, iterated at `:423`), so the bound is per entity id, not per `limit`. The drop direction deletes a record (`consolidation.py:166-169`), irreversibly under v1 prune and recoverably under E4's tombstone.
- **Retention-ranked host paths.** For a host path that ranks on retention-derived leaves (G3-2 path 2), the window is the whole probation, not just its edges, because nothing it ranks on was produced by `g` (O20).

Requiring a host echo would change a locked signature, which is a §9 escalation, not a design choice here (O14). Stamping by "generation live at call time − δ_t" is **not** adopted: it moves the window rather than closing it, puts a clock lookup into seq-ordered stamping, and contradicts V-GENTAG.

### G5. Authority graph

**Nodes:**
- the genesis root key
- the recovery key
- rotated keys
- the trust pins (the referee hash and eval-set hash, as `govern{const, trust}` content)
- the constitution
- the held-out window `[T₁, T₂]`
- the external anchor

**Edges:**
- **signed_by**
- **rotates**: `key` → the previous key
- **pins**: constitution → referee hash, eval-set hash
- **anchored_by**: latest `attest` → the external anchor

**Invariants.**
- **G5-1 Rooted.** Every `signed_by` path ends at the genesis root key. That key is pinned in code or the genesis, **never in a trust-store file** (R5; brief R5 skeptic #4). There is no trust directory. Pins are journaled, signed `govern{const, trust}` content.
- **G5-2 Rotation chain.** A key is valid from its `key` event to the next one. A rotation is signed by the old key or the pre-registered recovery key.
- **G5-3 Judges end outside the loop.** Every path from a promotion decision ends on a pinned referee hash, the held-out window or the owner's key.
- **G5-4 Anchor.** The anchor's `(seq, hash)` lies on the backbone. A journal shorter than the anchor fails.
- **G5-5 Wear.** Held-out wear is the number of `disclose` events since the window last rolled forward by `amend` (R4d).

---

## 3. Architecture and store layout `[P]`

```
<store>/
  journal/seg-NNNNNN.log   G1. Format 7. The authority for existence, order and commitments. Hash-linked; policy inline;
                           signed-set govern carry sigs.
  payloads/<record_id>     nonce ‖ payload ‖ vector, committed by salted digest (G1-6). The authority for bytes.
                           Written and fsynced before its deposit is appended. Erase deletes the file.
  blobs/<sha256>           G3 inputs: referee .wasm, eval sets, label sets. Verified on use.
  derived/<sha256>/        G3 leaves: fold checkpoints, vector index, recall anchors, USD policy layers,
                           USD cortex projection, v1-format snapshot.json export, verdicts.
  derived/INDEX            leaf kind → expected hash, and for snapshot.json the seal seq/hash it was built from.
                           Advisory only; G3-3 re-checks.
  drafts/                  owner-edited policy layers. Recall never reads them.
host/querylog/             host-owned QueryRecords and Labels (G3 inputs).
off-machine:               owner signing key + recovery key; external anchor (seq, hash) of the latest attested seal.
```

There is no `trust/` directory. Pins live in the journal (G5-1).

**Open** takes seven steps. The verifier walk comes first, because it produces the start seal and the excluded set; open stays O(tail) because each seal carries the RolledBack set and the live G4 states as journal content (G1 table) `[P]`:
1. Read the pinned root key (code or genesis) and the external anchor.
2. **Verify** (the verifier, §6). Walk `prev` and the signatures over the tail from the latest attested seal (G1-1, G1-4), starting from the RolledBack set and G4 states that seal carries and adding every transition in the tail. Report `rolled_back_gens` at head and `signed_through_seq`, and choose `start_seq`: the **latest attested seal that is eligible** under G3-3 (outside every rolled-back generation's window, including Expired spans), walking back at most the pre-promote fallback span that O13's S includes. That covers both a present-but-unattested reseal and an absent one. If no attested seal qualifies, fold from genesis; never fall back to an unattested reseal. The harness doesn't pass `start_seq` in. The anchor still holds the latest attested seal, which may be ineligible as a fold base and then serves only the truncation check.
3. Compare against the anchor (G5-4).
4. Load the checkpoint named by the `start_seq` seal. Check its hash, and that its `built_from` exclusion set equals the set the seal carries (G3-3). A mismatch means rebuild from an earlier eligible base, never trust.
5. **If the latest rollback has no later seal** (a crash between the rollback and its reseal), rebuild from an eligible base and append the reseal, unattested, before any `retention` event or sleep pass is accepted.
6. Fold the tail under `excluded(head)` from `Verdict.rolled_back_gens`, and derive the G4 state of every generation, the pending generation and `signed_through_seq` from the start seal's carried state plus the folded tail, never from a derived file. Finish any erase whose file or content-bearing leaves are still present (G1-6, G3-9).
7. Rebuild the `snapshot.json` export and recall anchors if their recorded seal predates the latest rollback (G3-3), before serving. Open never calls v1's `hydrate` on an export (O19).

**Audit** runs the same walk from genesis, then:
- recomputes every seal's carried RolledBack set and G4 states from the walk and requires them to match (V-SEAL);
- rebuilds every leaf and compares hashes;
- rehashes every present payload file against its commitments, and checks that every missing one has an `erase` (V-PAYLOAD);
- refolds the prefix at each journaled `retention` event under `excluded(k)` as of that event's seq, with the policy and thresholds resolved there and the event's own `now`, and requires the event's tombstone and stage decisions to match exactly (V-RETAIN). Tombstones written before a later rollback are legitimately final; V-RETAIN checks them against the prefix they were written on. Retention events are G1 authority, not leaves, so without this a wrong decision would be replayed as fact.

**Reload (T3).** The owner edits `drafts/` in any tool. `reload()`, a harness-level operator op, then does the following in order:
1. lints the draft
2. validates it into a `Spec`
3. checks G2-2, G2-5 and G2-6
4. obtains the owner's signature over the canonical body
5. appends `govern{tier: context, why: edit}`
6. regenerates the derived USD leaf

A read sees the change only after the append. The live-edit cost in Solaris is accepted (R1).

**Derived USD.** Policy layers are tiny. They are regenerated under `Sdf.ChangeBlock`, with prim names from UUIDs or fingerprints (conventions #1 and #5), outside the 500-prim record batch path `[P; size U]`.

**One tuning pass.** A harness-level operator op; the four agent ops don't change.
1. **Verify G5.** The referee hash is pinned, and the eval-set hash matches the constitution.
2. **Build the tuner's view:** open names, bounds, current values and the tuner's last few train scores. Nothing else (v6 J3).
3. **Parse the proposal.** The tuner returns `{"tier":"self","set":{name:number}}`, which is parsed strictly and size-capped, then checked for types and for bounds against the constitution (G2-6).
4. **Score.** The referee scores the candidate and the head on the train window, debited from the budget. The candidate is scored as the **full resolved spec** it would install, not a sparse delta, and the head's seq is recorded as the base.
5. **Margin.** A paired session bootstrap sets it (resampling unit `[U]`, O34).
6. **Propose.** The winner is appended as an unsigned `govern{why: propose}` with **evidence** edges and a **scored_against** edge to the base (G4-8). This is the **only** kind the tuning pass appends, in every mode, and G4-3 is checked.
7. **Owner review.** The owner sees train scores, the bootstrap interval, tripwires, the base generation, and **held-out pass/fail only**. The owner either signs `promote` (whose body carries the base seq) or the proposal is `withdraw`n.
8. **Probation.** Once Promoted, retention is held and the recall anchors are rebuilt. The owner later signs `adopt` or `rollback`. `adopt` carries no typed evidence: it is the owner's act that moves responsibility for retention effects to the owner's side of the line (`BLUEPRINT_v6.md:124`), and probation is a hold, not a measurement window. Whether adopt should rest on a probation verdict, and whether a minimum probation exists, is O26.

---

## 4. Rules

Every rule maps to a graph invariant. v6 IDs are kept wherever v6 had the rule. "Δ" marks a change from v6.

| ID | Rule | Graph | Tag |
|---|---|---|---|
| **T1** | One linear hash backbone from the format-7 genesis; nothing is edited | G1-1, G1-7 | `[V]` v5 records: append-only, CRC-framed, gap-free `seq` (`src/moneta/v5/journal.py:8-23, :105-135`), not hash-linked, and `compact()` rewrites events in place (`journal.py:349-396`; not ratified, E4) · `[P]` chain |
| **T2** | `govern` carries its spec inline; USD layers are derived | G1, G3 | RULED (R1) · `[P]` |
| **T3** Δ | Owner edits join the timeline through a signed, journaling `reload()` | G1, G2 | RULED (R1, R5) · `[P]` |
| **T4** | Rollback and roll-forward **restore** an earlier spec byte for byte | G1-3 | `[P]`; pattern `[A; v6: V on the toy]` |
| **T5** Δ | Every event carries the running hash; seals name checkpoints; open verifies from the last attested seal; the audit verifies from genesis | G1-1 | RULED (R5) · `[P]` |
| **T6** Δ | Payloads and vectors are committed by salted digest in per-record files, written before their event; erase removes bytes and content-bearing leaves, never events | G1-6, G3-9 | `[P]` |
| **T7** Δ | Typed edges point strictly backward | G1-2 | `[P]` |
| **P1** | A read depends only on (journal prefix, embedding, limit, context, scopes, t). The slot winner is a pure read-time step of these inputs (G2-9). How context and scopes reach an agent `query(embedding, limit)`, which carries neither, is O16 | G2-1 | v5 `recall` `[V]`: writes nothing; takes (embedding, limit, context, allowed scopes, t) and echoes (seq, t, context, policy fingerprint) (`src/moneta/v5/substrate.py:663-701`). Its policy, though, is host-held state that v5 does not journal (`Config.policy`, `use_policy`, `substrate.py:208, :1012-1016`; `policy.py:189-196`), so a v5 read depends on the prefix **plus** that policy; R1 moves it into the journal · **false in v1** `[V, api.py:399-401]`; binding open (O16) |
| **P2** | The host logs every P1 input; the eval set rebuilds byte-identically | G3-5 | `[P]` |
| **P3** | A verdict depends only on the referee's bytes, the eval set's bytes and the candidate's values, and reproduces in a fresh process | G3, G5 | `[P]`; `[A; v6: V on the toy]` |
| **P4** | Model labels carry a pin and request hash before use; replay never calls the model | G3 | `[P]`; moot unless R3 flips |
| **P5** Δ | Every ranking uses the total order `(score desc, seq asc, record_id asc)` | all | `[P]` |
| **P6** Δ | Seams, `Resolved`, the folds and replay take time as an argument. The agent-facing read and deposit sample the substrate clock **exactly once, at entry**, and use only that value. A read journals nothing (principle 2) and **echoes** its sampled `t`; a deposit journals the clamped envelope `t` (G1) and echoes **that same clamped value**. Replay uses the echoed `t`. Checked by V-CLOCK | G2-1 | `[P]`; v1 reads `time.time()` in `deposit` (`api.py:361`), `query` (`:399`) and `signal_attention` (`:422`) `[V]` |
| **C1** | Values resolve by strength; self is weakest; the nearer owner wins | G2-3 | `[P]` |
| **C2** | Self can't author records, scopes, exclusions or slots, whatever the open list holds | G2-4 | `[P]` |
| **C3** Δ | The plain and USD resolvers agree on **value fields** (slot preferences included, slot winners not), with and without self; authorization is rendered flattened | G2-7 | `[V]` without self (v5's 60-spec test, G2-7) / `[P]` |
| **C4** Δ | Authorization resolves by intersection; a child only narrows; a slot winner is filtered by it at read time | G2-5, G2-9 | `[P]`; **not** v5's rule: v5's I5 is caller-scope narrowing only, and v5 resolves context scopes by strength `[V, src/moneta/v5/policy.py:203-207; substrate.py:550-553]` |
| **C5** Δ | `const` contributes no read-time values: bounds, pins, and global write-time retention values (λ_retention) only; the prune/stage thresholds are locked Round 2 pins; `rules` never enters `Resolved` | G2, G2-10 | `[P]` |
| **J1** | The referee is a pinned, zero-import WASM module with fuel and memory caps and a fresh instance per call | G5 | `[P]`; `[A; v6: V on the toy]` |
| **J2** | The constitution holds the objective (referee, metric, eval set, holdout); nDCG@k is the default | G5 | `[P]` |
| **J3** | The tuner's view holds only open names, bounds, values and recent train scores, within a budget | G5-3 | `[P]` |
| **J4** | Promotion needs a margin from a session-level paired bootstrap, measured against the live head (G4-8) | G4, G4-8 | `[P]`; unit `[U]` (O34) |
| **J5** | Tripwires are recorded, never scored, never shown | G4 | `[P]` |
| **J6** Δ | Shadow-only through mile 4; afterwards only signed owner acts move the pointer | G4-2, G4-6 | RULED (R4) · `[P]` |
| **J7** | Sleep passes are held while a generation is Promoted or Expired | G4-4 | `[P]` |
| **J8** Δ | After rollback, the retention fold excludes that generation's attention from utility **and** `attended_count` on every later pass, and the store reseals from an eligible base. Whether this also covers a rollback of an Adopted generation (R4a's text applies "on rollback") is O21; whether R4a has a carrier if E3 is ruled against is O30 | G4-5 | RULED (R4a) · `[P]` |
| **J9** Δ | One pending generation; a probation ceiling with a default; no unsigned pointer move | G4-3, G4-7 | RULED (R4c) · `[P]` |
| **J10** Δ | Held-out is shown as pass/fail; each fuller disclosure is a `disclose` that wears the window | G5-5 | RULED (R4d) · `[P]` |
| **K1** Δ | The root key is pinned in code or the genesis; rotation is signed by the old key or the recovery key | G5-1, G5-2 | RULED (R5) · `[P]` |
| **K2** Δ | An external anchor holds the latest attested seal | G5-4 | RULED (R5) · `[P]` |
| **K3** Δ | The signed set is R5's set; signed `govern` carry their signature inline and can't be appended without it | G1-4 | RULED (R5) · `[P]` placement |
| **L1** | The line: self holds read-time values only | G2-4 | `[P]` |
| **L2** | Proposal grammar `{"tier":"self","set":{name:number}}`, parsed strictly, size-capped, finite and in bounds | G1 | `[P]`; `[A; v6: V on the toy]` |
| **L3** | Only the substrate writes the journal | G1-5 | `[P]`; v5's single write path `[V]` (G1-5) |
| **X1** | Code ceilings no constitution can raise: diff size, op count, fuel, memory, eval-set size, budget, seal interval, context depth, the maximum probation ceiling, the envelope for tunable bounds (the recall λ envelope is `ARCHITECTURE.md:82`'s 1 min – 24 h until O28), the retention λ range, and δ | all | `[P]`; values `[U]` (O33) |
| **X2** | Refuse a genesis format this build doesn't implement | G1-7 | `[P]` |
| **X3** | The four agent ops and their signatures stay unchanged; every new verb is a harness-level operator op | — | `[P]`; precedent `[V, ARCHITECTURE.md:46-50; api.py:446-451]` |
| **SM1** Δ | A seam is a pure function over flat, schema-versioned buffers, with no handles, clocks, I/O or callbacks | — | `[P]` |
| **SM2** Δ | Every seam has a Python oracle that passes its checks before any Rust is written | — | `[P]`; seam rule RULED (O27, `RULINGS.md:32-33`), not D1 |
| **SM3** Δ | A Rust seam ships only with its conformance check green on shared fixtures and its gate measured on defined axes | — | `[P]`; seam rule RULED (O27), not D1 |
| **SM4** Δ | The scan moves to Rust only if arm P misses 50 ms p95 whole-query latency (defined on a 2-vCPU container, `BLUEPRINT_v6.md:353, :361`) | — | D1 (given). **Gate not fired `[M]`:** arm P 26.6–29.1 ms p95 at 10k × 384 on the owner workstation (fair matrix, N = 200, 2 runs, fresh and aged; §6 "Built so far"), so SM4 as written admits no Rust scan. The v1-line native scan on `main` rests on the seam rule's exactness clause (SM2, SM3, O27), not on SM4. The v7 seam (utility, allowed set, P5 order) is still `[P]` |

---

## 5. Checks and sabotages

A check is green only once its sabotage has been caught. v5's invariants I1–I8 still apply. Each is a named test (`docs/v5/BLUEPRINT.md:157-168`; `tests/v5/test_conformance.py`, `test_review_regressions.py`) `[V]`, and `tests/v5` passes at `57a90bc`: 158 under Python 3.14 with the native seam off and on, 151 + 1 skipped (the native-parity module, no wheel) under hython 21.0.773 `[M]`. Two read differently from v7: I5 is caller-scope narrowing only (G2), and I8, "ordering without a GIL", is tested under the GIL, so free-threaded Python stays `[U]` (E3, `RULINGS.md:77`). The **Mile** column is the mile at which the check must first pass, in v6 numbering; `4b` is a v7 sub-mile of mile 4 (§8). A row marked **measurement** is green when it reports its numbers with its sabotage detected; it has no pass/fail threshold. **No check here is green because of the native accelerators on `main`** (§6 "Built so far"): their conformance suites test fidelity to v1, not these invariants.

| Check | Invariant / rule | Pass condition | Sabotage it must catch | Mile |
|---|---|---|---|---|
| **V-CHAIN** | G1-1, G1-8, T5 | flipping any one byte after genesis fails open or audit at that `seq`; an append with `t` below its predecessor's is clamped and recorded; a non-finite float is refused at append | `prev` over the header only; **a hash computed over a re-serialized object instead of the stored bytes**; an edit to `t` alone; a NaN weight accepted | 4 |
| **V-SEAL** | G1-1, G3-3 | an edit before the last seal fails the audit; an edit after it fails at open | a seal written without the running hash; **a seal whose carried RolledBack set omits a generation** | 4 |
| **V-BACKWARD** | G1-2, T7 | every typed edge targets a lower `seq` | an event referencing its own or a later `seq` | 4 |
| **V-RESTORE** | G1-3, T4 | a rollback's spec bytes equal its `restores` target's spec bytes | a rollback rebuilt from the derived USD layer, or from a file, instead of the target event | 4 |
| **V-ERASE** | G1-6, G3-9, T6 | after an erase (with a unique, high-entropy canary payload and vector), the chain verifies; `payloads/<record_id>` is absent; no surviving leaf's `built_from` reaches the erased record; a decoded spot check of `snapshot.json`, the cortex projection and the vector index finds no canary; two records with identical payloads, one erased, leave the other verifying with no unexplained dangle; the erased commitments match neither `H(payload)`, `H(vector)` nor `H(embed(payload))` of the known plaintext | erase implemented as an in-place journal rewrite; **erase that leaves a pre-erase `snapshot.json`, cortex layer or vector index under `derived/`**; payload files named by content digest; an unsalted commitment | 4 |
| **V-PAYLOAD** | G1-6, T6 | the audit rehashes every present payload file against its commitments and finds an `erase` for every missing one; a read verifies lazily and turns a mismatch into a typed fault; crash injection between the payload write and the `deposit` append, between the `erase` append and the file delete, and (under O25 keep) between a `revector` section write and the `revector` append, leaves only an orphan file, or an orphan section the audit truncates, or an erase open finishes | a swapped non-erased file; a file deleted without an erase; verify-on-read turned off; the `deposit` appended before the payload file is durable | 4 |
| **V-FORMAT** | G1-7, X2 | format 5, format 6 or unknown is refused; a v6 reader refuses format 7 | a reader that skips unknown events | 4 |
| **V-SIGSET** | G1-4, K3, G4-2 | an unsigned promote, adopt, rollback, amend, reload or trust event is refused at append; roll-forward likewise once O9 confirms it | signature check turned off for `adopt`; an unsigned `reload` accepted | 4 (test key) / 5 (real key) |
| **V-WRITE** | G1-5, L1, L3 | a tuning pass appends only `govern{why: propose}` (the substrate may add `withdraw`), in every mode | the tuner calling tombstone; the tuning pass appending `promote` | 4 |
| **V-TIMELINE** | G2-1, T1–T3 | after an owner edit, an old query replays under the old policy | `reload()` serving the draft before journaling it | 4 |
| **V-OWNER** | G2-3, C1 | an owner value wins in its context and every child; a nearer owner beats a farther one | self placed strongest; a parent placed stronger than its child | 4 |
| **V-SELF** | G2-4, C2 | a self proposal carrying a scope, exclusion, slot or non-open key is refused | the open-names list extended to a scope, exclusion or slot key | 2 (simulated) / 4 |
| **V-BOUNDS** | G2-6, G2-10 | an out-of-bounds value is refused at write; an `amend` raising a bound past X1 is refused; a `reload` naming a retention field in an `owner@c` or self layer is refused before it is journaled | clamping instead of refusing; **the recall bounds hard-coded in code rather than read from the constitution**; an `owner@c` layer that sets a retention λ read by a sleep pass; **an `amend` that changes a locked threshold (0.1, 0.3, 3)** accepted without §9 | 4 |
| **V-NARROW** | G2-5, C4 | no child resolves to a scope its parent lacks | scopes resolved by strength instead of intersection | 4 |
| **V-FOREST** | G2-2 | cyclic, dangling or too-deep parent chains are refused | the cycle check run after journaling | 4 |
| **V-C3** | G2-7, C3 | value fields agree on random stacks including self; the flattened authorization in USD equals the plain intersection | the USD stack built with self not last; authorization derived by USD strength | 4 |
| **V-EVAL3** | G2-8 | the recall fold writes nothing. Retention arm, conditional on O29/O7: if the per-event order is ruled to be point 2, every retention decay call sits inside the reducer and none outside the three sites; if per-batch is ruled, exactly one retention decay per reduce, at `now`, after the write | a recall fold writing anchors back into retention state; a retention decay call in `signal_attention` or on a timer; (per-batch ruling) the per-event decay | 4 |
| **V-LEAF** | G3-2, G3-4 | deleting every derived file leaves answers identical after rebuild | a resolver reading `derived/` USD layers instead of the journal; the vector index rebuilt from `derived/` or `snapshot.json` instead of committed vectors | 4 |
| **V-NOFEEDBACK** | G3-2 | no substrate append, open or restore path reads `derived/` content into substrate state, except an eligible, hash-matched checkpoint | a sleep pass reading utility from `snapshot.json`; **a v1-style `hydrate` from `snapshot.json` after a rollback, reviving the rolled-back generation's `attended_count` and pruned rows** | 4 |
| **V-HASHGATE** | G3-1, G3-3, G4-5 | every leaf's name is the hash of its bytes; a tampered checkpoint is rebuilt, not loaded; open, a reseal and a periodic seal never use a checkpoint sealed inside any rolled-back generation's `[promote, rollback)` window; with the reseal unattested, open from the pre-promote attested seal gives the same state as open from the attested reseal; after open no export older than the latest rollback exists | a checkpoint loaded without a hash check; a leaf named by kind; **open from a checkpoint sealed during a rolled-back generation's probation or expiry**; **an eligibility check that looks at the latest rollback only** (two rollbacks, both reseals unattested, a seal attested during the first probation, reopen, sleep pass: retention must equal a run where neither was promoted); a fallback that folds the tail without the G4-5 exclusion; rollback, crash before export regeneration, open | 4 |
| **V-REBUILD** | G3-5, P2 | mile 3: the eval set and every verdict leaf rebuild byte-identically from `Prefix(h_build) + QueryRecords + Labels`; mile 4: every leaf, including fold checkpoints and USD policy layers. An eval set touching an erased record is marked, never silently rebuilt | dict or set iteration order leaking into a builder; `cos` computed via BLAS in the builder; a rebuild that drops an erased record under the old hash | 3 (eval set, verdict) / 4 (all leaves) |
| **V-HOLDOUT** | G3-6 | no held-out query in train; no label outside its window | splitting by deposit time instead of query time | 2 (simulated) / 3 |
| **V-LABELPROV** | G3, P4 | every label has provenance; owner batches are signed | an unsigned owner-label batch admitted | 3 |
| **V-LEAK** | G3-7, J8 | an eval set built at `h_build` contains no attention stamped with a generation RolledBack in `Prefix(h_build)` | the `gen` stamp dropped from attention | 4 |
| **V-STATE** | G4-1, G4-2, G4-8 | every illegal transition fails to construct or is refused; `propose`, `withdraw` and `expire` change neither the pointer nor probation; `adopt` changes G4 state only; a `promote` whose base isn't the live head is refused; a signed `promote` of a withdrawn proposal is refused and reported | `adopt` from Proposed; a second `adopt` of the same `g` (signature replay); a signed body from another store (genesis-hash mismatch); `expire` that moves the pointer; **a `promote` body replayed onto a later `propose` of the same spec**; **a roll-forward body replayed after an intervening rollback**; **propose during probation, roll back, then promote the stale proposal**; a sparse `set` applied over a different head | 4 |
| **V-PENDING** | G4-3, J9 | a second promote while one is pending is refused | the pending count read from a derived file that lags the journal | 4 |
| **V-HOLD** | G4-4, J7 | no retention event while a generation is Promoted or Expired; crossing `MAX_ENTITIES` under a hold raises the alarm and then does what O23 rules | a sleep pass during probation; the pressure trigger silently overridden, with no alarm | 4 |
| **V-UNDO** | G4-5, T4, L1, J8 | at a pinned `(seq, t)`, probe answers are identical before promotion and after rollback; **the complete retention-event sequence over at least two post-rollback passes, with a close and reopen between them and a crash between the rollback and its reseal, equals a never-promoted run's from the same attention minus `g`'s**, the post-hold drain included | a tunable that also feeds retention; **a sleep pass after rollback that still counts `g`'s attention in utility or in `attended_count`** (`consolidation.py:112`, `ecs.py:242`); the excluded set reset after the first post-rollback pass | 4 (test store) / 5 (real) |
| **V-RETAIN** | G4-5, J8 | at audit, every journaled `retention` event equals the decisions of a refold of its prefix under `excluded(k)` as of its seq, its own `now`, and the policy and thresholds resolved there | **the excluded set built from the folded tail only, or from rollbacks since the last `retention` event**; **a streaming fold that adds `g` only on reaching the rollback**; the excluded set reset after the first post-rollback pass | 4 |
| **V-GENTAG** | G4-5 | every attention stamp equals the self generation live when `signal_attention` was called, and survives WAL replay unchanged | the stamp taken from the last *proposed* generation; **the stamp taken at drain or journal time** (fixtures: promote g → signal → rollback → sleep pass; signal under g0 → promote g → sleep pass; promote g → signal → crash → recover → rollback → sleep pass); the stamp lost or recomputed on WAL replay; **the fold using the drain-time envelope `t` instead of `t_call`** (fixture: signal at t₁, drain at t₂ ≫ t₁) | 4 |
| **V-MISATTR** | G4-5, O14, O20 | reports, for late signals injected at ±δ_t around promote and rollback, how many records cross `attended_count = 3` at utility < 0.1 in each direction against a test-only ground truth tagged with the served result's generation; reports how far the probation echo inflates `g`'s held-out score (eval on attention stamped before vs after promote). **Measurement** (green = reported, with its sabotage detected); its numbers are O14's and O20's evidence | the count taken per `limit` instead of per entity id; ground truth taken from the stamp | 4 |
| **V-CEILING** | G4-7, J9 | at the ceiling: `expire` appended, alarm raised, hold kept, pointer unmoved, proposals refused | a ceiling that adopts automatically or releases the hold | 4 |
| **V-SHADOW** | G4-6, J6 | mile 3: the shadow flag stops the tuner from changing any policy; mile 4: with shadow on, no generation on a real store leaves Proposed in a full run, checked from the journal | the flag ignored | 3 (flag) / 4 (journal) |
| **V-ENVELOPE** | G3-8 | consolidation runs only in idle windows > 5 s, stages at most 500 prims per pass, rotates at 50k prims, and writes every record-projection batch inside one `Sdf.ChangeBlock`; a synthetic held backlog (about 6k stage candidates) drains over several passes | a policy-layer or cortex regeneration routed through the record batch path; a release pass that stages more than 500 prims; a release pass started by the pressure trigger outside an idle window; rotation skipped past 50k | 4 |
| **V-DISCLOSE** | G5-5, J10 | evidence shows held-out as pass/fail; any numeric figure appends `disclose` | an evidence page showing the held-out score | 4 |
| **V-KEYPIN** | G5-1, K1 | a key swapped into const content or any file is refused | the root key read from mutable state | 4 |
| **V-ROTATE** | G5-2, K1 | a rotation not signed by the old or recovery key is refused | a rotation accepted on the new key's own signature | 5 |
| **V-ANCHOR** | G5-4, K2 | truncation before the anchored seal fails | the anchor compared by `seq` only | 5 |
| **V-PIN** | J1, G5-3 | an unpinned referee is refused | the pin check off | 4 |
| **V-IMPORTS** | J1, SM1 | the referee module's import section is empty | a module importing `env.clock` | 4 |
| **V-VIEW** | J3, G5-3 | the view holds only open names, bounds, values and recent train scores | labels or held-out scores leaked in | 2 (simulated) / 4 |
| **V-MARGIN** | J4 | a noise-only candidate never promotes in 1,000 tries | margin set to zero | 2 (simulated) / 4 |
| **V-DIFF** | L2 | the ported red-team suite lands zero writes | a permissive parser | 4 |
| **V-TRIPWIRE** | J5 | tripwire values are recorded in the verdict leaf and appear in no score and no tuner view | a tripwire folded into the margin; a tripwire value shown in the tuner's view | 4 |
| **V-QUERYSIG** | X3 | the four agent-op signatures are byte-identical to `ARCHITECTURE.md` §2, independent of O16 | a fifth op; an unjournaled module-level context or scope read by `query` | 4 |
| **V-CLOCK** | P6 | each agent read and deposit samples the clock once; a deposit's echoed `t` equals its journaled clamped `t` | `query` reading `time.time()` twice; an echo that differs from the journaled clamped `t` | 4 |
| **V-REPLAY** | P1, P3, P4, G2-9 | mile 3: a fresh process recomputes every shadow-run verdict leaf bit for bit from its `built_from` inputs (a temporary pre-format-7 test fixture under `oracle/`, not substrate state; it does not satisfy review-log JA-7); mile 4: every journaled `govern{propose}` verdict. Only if O16 is ruled (b), or through a harness read that takes scopes: two callers with different scopes sharing one echo fingerprint get different slot winners, each reproducing from its QueryRecord (under O16(a) every agent read has the full scope set, so this arm is vacuous for agent reads) | a referee with unseeded noise; the slot winner computed before the scope filter | 3 (verdict leaves) / 4 (journaled) |
| **V-POOL** | P2 | for random in-bounds values, the referee's top k equals the read path's (the oracle or native scan) **bit for bit by default**; only under a recorded contract-E fallback, pairs whose oracle scores lie within δ are excepted and must be ordered by the total order. From mile 4, both sides are given the same `excluded_gens` and the fixtures include a query inside a rolled-back window | bounds taken at one corner; the negative-Δt clamp removed (`decay.py:66-67`); (mile 4) referee and read path run with different excluded sets | 3 (top-k, empty excluded set) / 4 (excluded-set arm, rolled-back-window fixture) |
| **V-TIES** | P5 | equal-score records are ordered by `(seq, record_id)` in every implementation | the tie key dropped in one implementation | 2 / 4 |
| **V-EXP** | P3, Q5 | the referee (WASM kernel `exp`) and the read path (the Python port) agree on every utility **bit for bit** (default). Under a recorded fallback, they disagree only within δ. Fixtures include exp landing in the subnormal band and underflowing to zero at λ derived from the X1 bounds (at λ = ln2/60: Δt ≈ 61,320 s onset, 61,500 s, 65,000 s), `utility < 1` times a normal exp giving a subnormal, and the floor branch with floor 0.0 against a subnormal (exact bits) and with floor > 0 | a less accurate `exp` swapped in; a process with FTZ/DAZ set | 4 |
| **V-FPENV** | Q11 | each native and oracle entry point probes the FP environment per call or thread (`sys.float_info.min / 2 > 0.0`; `5e-324 * 1.0 == 5e-324`) and fails closed on FTZ/DAZ. **Not implemented anywhere today**, including the native seams on `main`; the probe should land with mile 2's first fixtures | an extension loaded with `-Ofast`/crtfastmath that sets FTZ; a worker thread with flags set | 4 |
| **V-FINITE** | G1-8, Q12 | every float-returning seam maps a non-finite result to one canonical reject tag before return; bit-equality clauses apply to finite outputs plus tag equality | raw NaN bits compared across runtimes; `inf*0.0` and `float('nan')` giving different bits (measured: `0xfff8…` vs `0x7ff8…`) treated as a disagreement; a vector with a ±inf component accepted at deposit | 4 |
| **V-POW** | P3, Q5 | as V-EXP, for `pow(U, β)` | a less accurate `pow` | 4, only if R2 flips |
| **V-ORACLE-REF** | SM2, SM3 | WASM and Python referees return identical `f64` bits on all fixtures | oracle and WASM built from different metric ids | 4 |
| **V-ORACLE-VERIFY** | SM2, SM3 | the Rust and Python verifiers return an identical `Verdict`, including `rolled_back_gens` and `start_seq`, on fixtures plus the mutation corpus: every byte flip, event deletion, truncation point, adjacent swap and signature retarget | a Rust walker that skips signatures on `reload`; a start seal chosen by the latest rollback only | 4b |
| **V-ORACLE-FOLD** | SM2, SM3, G3 | kernel and oracle anchors are bit-identical, **including the per-event vs per-batch fixture**, the backward-clock-step fixture and the non-finite fixtures | a per-batch clamp in one implementation; an "optimization" that reorders a float sum; `dt.max(0.0)` (the v1-line decay kernel on `main` avoids it: `lib.rs:247-249` uses `if dt < 0.0`, so a NaN Δt reaches the floor as in `decay.py:66-69`) | 4, whenever any Rust fold is built (the WASM referee carries one) |
| **V-EXCL** | J8 | a fold with `g` excluded equals a fold of a journal in which `g`'s attention was never written. On the `fold_recall` seam this tests the parameter's mechanics; recall policy uses an empty set unless O6 is ruled "both" | the `produced_under` edge ignored | 4 |
| **V-ORACLE-SCAN** | SM4, Q1, Q4 | **bit-exact by default**: the scan's cosines, top-k and order are bit-identical to the scan oracle, and the rerank `max(cos, 0) × U` is checked separately against its oracle (the v1 pair: `_oracle_scan`, `vector_index.py:120-153`, plus `ECS.rank_hits`, `ecs.py:335-381`); ties under P5 once adopted. δ applies only under a recorded contract-E fallback | the unclamped `ECS.top_k_by_similarity` (`ecs.py:331`) used as the rerank oracle; an early stop that drops a hit the full sort would keep | 4b |

---

## 6. Where Rust fits

**D1, verbatim (given).** "Rust comes in only if a native scan in Python (arm P) misses its latency gate" (`BLUEPRINT_v6.md:41`). D1 governs SM4 and the `moneta-scan` row only. **Its gate did not fire:** with every arm on the same exact early-stop rerank, arm P measured 26.6–29.1 ms p95 against 50 ms on the owner workstation ("Built so far", below) `[M]`. A native scan nonetheless exists on `main` as a v1-line accelerator. It was admitted on the exactness clause of the seam-admission rule below (numpy is not bit-exact, and Rust adds no runtime dependency), not on D1. The repo docs (`README.md`, `CLAUDE.md:138`, `vector_index.py:61-64`) call this "D1's exactness clause"; D1's verbatim text has no such clause, so this paper files it under O27.

**The seam-admission rule, RULED (O27), not D1.** v6 §10 reports v5's rule: "Rust goes behind a pure seam with an exact oracle, where it buys speed or a guarantee" (`BLUEPRINT_v6.md:349`). The merged v5 blueprint does not say this in those words `[V]`: it names two pure, oracled seams and keeps the 8 September order, "Arm P first … Rust only if P misses its gate" (`docs/v5/BLUEPRINT.md:255-262`), which is D1. The owner confirmed the broader rule as a project constraint on 2026-10-15 (`RULINGS.md:32-33`), so its standing no longer rests on that attribution. v7 adds bit-exact conformance on shared fixtures and a measured justification `[P]`. The referee, the kernel, the verifier and the bindings rest on this rule, not on D1. (`pass1_rulings_brief.md:38` carries the same conflation, and so do the working-tree docs `vector_index.py:49-64`, `lib.rs:1-8`, `ecs.py:39`, `CLAUDE.md:136-138` and `README.md`, which file the exactness argument under D1 as "D1's exactness clause". The corrected docs now state the latency facts right but keep that label; routed to the Documentarian.) **O27's "before mile 4" timing was overtaken before it was ruled** (v5's dot seam, below, is a third instance): both native accelerators on `main`, the scan and the decay kernel, were admitted under v1 exact-oracle discipline, which is this rule, not D1, and both sit on the read path of every `query`. A seam may be built in Rust only if all four hold:
1. **Pure:** a function of input bytes only (SM1). The FP environment (FTZ/DAZ, rounding mode = nearest-even) is a declared precondition, not an input, and is probed (Q11).
2. **Oracled:** a Python implementation exists and passes §5 (SM2).
3. **Conformant:** both run the same content-addressed fixtures (`fixtures/<sha>`) from `pytest` and `cargo test`, and **agree bit for bit** on finite outputs and on the reject tag (SM3, Q12).
4. **Justified:** it buys a measured number or a guarantee Python can't give.

Composition stays Pixar's USD, and oxideav-usdz stays parked. **No seam signature carries a `pxr` type.** USD renders G2's output after the seams run.

**Exactness, the default `[P]`.** There is one `exp`, ported as a pure-software implementation (a `libm` port):
- it is compiled into the Rust kernel for both the native and `wasm32` targets
- it is **ported line for line to pure Python as the oracle's `exp`**

Python's `math.exp` is the platform's version and isn't correctly rounded, so the oracle can't use it. Rust doesn't contract to FMA implicitly, and the FP environment is probed (V-FPENV), so the two targets should agree bit for bit `[U]`. V-EXP expects **zero** disagreements. The subnormal band is reachable in normal operation: at the v1 minimum half-life of 60 s, `exp(-λΔt)` is subnormal for Δt between about 17.0 h and 17.9 h, and `decay.py:69` keeps a subnormal when the floor is 0. That is where FTZ/DAZ would change the answer; hython 21.0.773 (Python 3.11.7) and Python 3.14.2 do not flush on the main thread: `sys.float_info.min / 2 > 0.0` and `5e-324 * 1.0 == 5e-324` both hold `[M]`. That is one thread; V-FPENV wants a per-call or per-thread probe. (`CLAUDE.md`'s test command now names Houdini 21.0.773, the installed version, `CLAUDE.md:130`; the stale 21.0.512 path was corrected by the Documentarian.)

**Not to be confused with the v1-line decay kernel.** `moneta_native.decay_batch` on `main` is bit-identical to `decay.py:decay_value` because both call the **same platform `exp`**: Rust `f64::exp` at `lib.rs:250` lowers to the C runtime `exp` that CPython's `math.exp` calls (`lib.rs:240-242`). Parity is verified on Windows under py3.14 and hython 3.11, including clamp, floor, NaN and subnormal edges (`tests/unit/test_native_decay_parity.py`, `test_edges_bit_identical` `:47`, `test_ecs_decay_all_native_equals_oracle` `:81`) `[M]`. That is same-platform parity with v1, not Q5: it says nothing about wasm32 (where `f64::exp` resolves to Rust's libm, not the CRT), other OSes, or the ported `exp`. It has no FP-environment probe (Q11), and its NaN-pattern comparisons are valid same-runtime only (V-FINITE). When the read path switches to the ported `exp`, `decay_batch` must switch with it and be re-verified, or be disabled (O31).

**Fallback.** Only if V-EXP measures a disagreement that can't be closed is contract E adopted for that seam, as a **recorded downgrade**. Under contract E:
- values may differ by up to δ ulps, where δ is a constitution value under X1
- order is compared only for pairs farther apart than δ
- within δ, the total order decides

**Non-finite results `[P]`.** A float-returning seam maps any non-finite result to one canonical reject tag before return; its f64 is meaningful only when the tag says finite. NaN sign and payload depend on how the NaN arose (CPython: `inf*0.0` gives `0xfff8000000000000`, `float('nan')` gives `0x7ff8000000000000`, measured by a finding) and are nondeterministic in wasm unless the runtime canonicalizes, so raw NaN bits are never compared (V-FINITE). Wasmtime's NaN canonicalization is enabled as defence in depth. Non-finite journal inputs can't occur (G1-8).

**Two consequences, named.**
1. When Q5 lands, the read path **must** use the pure-Python port (`src/moneta/oracle/exp.py`, or a non-oracle copy of the same code) in place of the platform `exp`. There are now **two** such call sites: `math.exp` at `decay.py:68` (the oracle and `decay_one` path) and Rust `f64::exp` at `lib.rs:250` (`decay_column`, reached through `decay_batch` `lib.rs:256-269` from `ecs.py:259-261`). The port is bit-identical by construction to the kernel `exp` compiled into the referee. It differs from v1's `math.exp` by up to an ulp, so v1 comparisons are tolerance-based. Which `exp` retention and the read path use, and when, is O31. **In v7 the read path reaches native code only through a gated seam.** On `main` (v1 line, not v7), `api.py` imports no native code, but `query` reaches two optional accelerators when the wheel is installed: the scan through `vector_index.py:329-401` and the decay kernel through `ecs.py:257-263`. `MONETA_NATIVE=0` or an absent wheel restores pure Python `[M]`.
2. **The scan is bit-exact by default too.** Arm P (numpy) sums in BLAS order and measured 1496 of 2000 cosines (≈75%) not bit-equal to the left-to-right oracle at 384 dims, with order unchanged in that sample (`scripts/bench_arm_p.py` → `results/bench_query_arm_p.jsonl`) `[M]`. It clears D1's latency gate (26.6–29.1 ms p95, fair matrix) but fails exactness, and exactness is why a native scan was built at all. The scan built instead is a sequential left fold (`dot_seq`, `lib.rs:28`), bit-identical to `_oracle_scan` (`vector_index.py:120-153`; dot loop `:145-147`) on 32 conformance tests (`tests/unit/test_native_scan_conformance.py`) for finite, non-overflowing inputs; a query whose cosine overflows to NaN is answered by the oracle itself ("Built so far") `[M]`. δ applies to the scan only as a contract-E fallback, as for every other seam. The eval-set builder still computes `cos` in left-to-right oracle order (G3-5), so G3-5 stays byte-identical across machines.

| Crate `[P]` | Seam (pure signature) | Buys | Oracle | Gate | Checks |
|---|---|---|---|---|---|
| `moneta-referee` (`cdylib`, `wasm32-unknown-unknown`, `no_std`) | exports only `alloc(len) -> ptr` and `score(ptr, len) -> f64`; `EvalBuf` = schema-hashed header; per-query pool rows `(record_seq, cos f64, deposit_seq, floor f64, u0 f64, label u8)`; per-record attention runs `(t f64, w f64, gen u32)`; candidate values. A non-finite result returns the reject tag (V-FINITE) | **guarantee**: sandbox, zero imports, fuel and memory caps | `oracle/referee.py`, built at mile 2 as the experiment's scorer; it calls the fold oracle, because features carry raw attention, not anchors | always, at mile 4, **if** fuel and memory on a realistic eval set (about 200 queries × at least 50 pool records) fit under X1 with 2× headroom, and two runtimes on Windows and Linux return the same `f64` bits. Otherwise the referee stays a pinned Python subprocess, recorded as a J1 downgrade, and the Rust fold leaves mile 4 with it. Toy caps: 20 M fuel and 8 MB `[A; v6: V on the toy]` | V-PIN, V-IMPORTS, V-POOL, V-EXP, V-REPLAY, V-ORACLE-REF, V-ORACLE-FOLD, V-FINITE |
| `moneta-journal` (`no_std + alloc`) + `moneta-verify` (std; `sha2`, `ed25519-dalek` pinned): **a tripwire, not built by default** | `verify(journal: &[u8], root: &PinnedKey, anchor: Option<Anchor>) -> Verdict`, where `Verdict = Ok{head_seq, head_hash, signed_through_seq, start_seq, pending_gen, rolled_back_gens} \| Fail{seq, kind}`. At open it walks the tail from the latest attested seal (at audit, G1 from genesis): chain, typed back-references, signed set, key validity, G4 legality, anchor, and **chooses** the start seal by G3-3's predicate (structural: needs only G4 state and the RolledBack sets that seals carry). The seal's checkpoint hash is checked for form and chaining here; comparing it to the checkpoint's bytes happens in the open/harness step, outside the pure seam. It does not resolve policy or fold. The fold's excluded set comes only from `rolled_back_gens` | **speed**, if measured | `oracle/verify.py` (`hashlib`, an ed25519 verify), built at mile 4. Integer- and byte-exact, so equality is bitwise, including `Fail.seq`, `Fail.kind`, `start_seq` and `rolled_back_gens` | **only if** the Python oracle on a synthetic format-7 journal of N = 100k events, K of them signed (K recorded), takes more than 100 ms p95 for tail verify at open over S events, where S = the X1 seal-interval ceiling plus the maximum unattested window (O12) plus the pre-promote fallback span, measured at the X1 maximum so the tester doesn't pick the cadence; or more than 30 s for a full audit of N `[P thresholds; cost U]` | V-CHAIN, V-SEAL, V-SIGSET, V-ROTATE, V-ANCHOR, V-STATE, V-ORACLE-VERIFY |
| `moneta-kernel` `fold_recall` (`no_std`) | `fold_recall(runs, floors, u0, t0, lam, until_t, excluded_gens) -> Vec<Anchor{u, t_last}>`, with runs sorted by `(record, seq)`, the **declared per-event order** (G3), and `excluded_gens` supplied by the caller | **ships in `moneta-kernel` whenever the WASM referee ships, at mile 4**: the referee folds raw attention runs inside WASM. What is conditional is the **`moneta-py` binding** that exposes it to the Python read path for repoints | `oracle/fold.py`: a loop over a ported `decay_value` (semantics of `src/moneta/decay.py:48-69`, clamp at `:66-67`, floor at `:69`) with the clamp to 1 **per event**. Built at mile 2. **Not started.** The v1-line `moneta_native.decay_batch` on `main` (`lib.rs:243-269`; parity `tests/unit/test_native_decay_parity.py`) is a retention-decay column kernel (`decay_value` at one `now`), not this fold: no per-event order, no `excluded_gens`, no clamp to 1, no anchors. It shares only the per-element step, and it uses the platform `exp`, not the port | the kernel fold: with the referee. The `moneta-py` binding: **only if** R2 stays the half-life **and** the Python oracle's repoint rebuild of R records × A attention events per record (both recorded; 100k records at a stated A) takes more than 1 s `[P; cost U]`. If R2 flips to β, the referee's `EvalBuf` switches to pool rows carrying precomputed U `(cos, U, label)`, folded in Python, the attention-runs section and the Rust fold leave the referee, and V-POW is added (`pass1_rulings_brief.md:172`) | V-POOL, V-UNDO, V-EXCL, V-EVAL3, V-ORACLE-FOLD |
| `moneta-scan` (v7 seam `[P]`; a v1-line scan exists on `main`) | `scan(q, vecs n×d row-major, util, seqs, ids, allowed: BitSet, k) -> Vec<(u32, f64)>`, ordered by the total order | speed | `api.query`'s path made explicit. In the working tree that path is `iter_query` (`vector_index.py:366-401`) feeding `ECS.rank_hits` (`ecs.py:335-381`, called at `api.py:406, 408`), which reranks by `max(cos, 0) × U` (`ecs.py:371`) with an **exact early stop** (`:366-367`), so the read path no longer scores the full index. Scan oracle: `_oracle_scan` (`vector_index.py:120-153`). **Not** `ECS.top_k_by_similarity`, which doesn't clamp cosine (`ecs.py:331`) | D1: **only if** arm P misses 50 ms p95 at 10k × 384. **Not fired `[M]`:** arm P 26.6–29.1 ms p95 ("Built so far"). The v1-line native scan was admitted on exactness under the seam rule (O27), not on this gate. The v1-line native scan exists (`moneta_native.ScanIndex`; raw cosine, v1 insertion-order ties; clamp × U reranked in Python). The v7 seam (utility, allowed set, P5 order, pure over flat buffers) is **not built**, and V-TIES and V-ORACLE-SCAN are not green. v5 measured 161 ms **median** on a 2-vCPU container `[A; v6: V]` (stated at `docs/v5/BLUEPRINT.md:242`, not re-run here). On the owner workstation v5's pure-Python `recall` measured 176–187 ms p50 and 184–194 ms p95 at 10k × 384 `[M]` (`results/bench_v5_recall_native.jsonl`). With `backend='python'` or `MONETA_NATIVE=0`, v1's scan is pure-Python O(N·d) `[V]` | V-TIES, V-ORACLE-SCAN |
| G4 state types | a state enum whose transitions consume the old state | **guarantee** against the substrate's own bugs | a Python state table, which is what enforces G4-1 by default | Rust types land only with `moneta-verify`; otherwise the Python table plus V-STATE is the enforcement | V-STATE |

### Built so far (v1 line, 2026-10-15)

Everything in this subsection is on `main` in the working tree (uncommitted; `rust/` is untracked), built under v1 exact-oracle discipline (the seam-admission rule, O27) for both seams; D1's latency gate did not fire. **None of it is a v7 seam, and no §5 check goes green because of it.** Every figure is `[M]` on the owner workstation (Threadripper PRO 7965WX, Windows, Python 3.14; hython 3.11 for the test matrix), 2026-10-15.

**The crate.** `rust/moneta_native/` is a single PyO3 crate (`cdylib` + `rlib`, pyo3 0.30.1 `abi3-py311`, built with maturin; release profile with no fast-math), built locally as an optional wheel (`dist/moneta_native-0.1.0-cp311-abi3-win_amd64.whl`). `dist/` is gitignored, so the wheel is not in git: a fresh clone without rustup and maturin runs 167 passing + 33 skipped, which is green and not a regression. It is imported under `try/except` at `ecs.py:39-42` and `vector_index.py:83-86` and is not a declared dependency (`pyproject.toml:37` still reads `dependencies = []`). With `MONETA_NATIVE=0`, or without the wheel, the Phase 1 oracle path runs unchanged. Build and test commands: `CLAUDE.md:136-157`.

| Seam (v1 line) | Code path | Oracle | Conformance | Status |
|---|---|---|---|---|
| **Scan** (seam rule, O27; D1 not fired) | `VectorIndex(backend='auto'\|'python'\|'native')` (`vector_index.py:105-117`) → `moneta_native.ScanIndex.scan` (`lib.rs:220-227`) over the pure kernel `scan_topk` (`lib.rs:46-91`, sequential `dot_seq` `:28`). Returns raw cosine, ordered cosine desc then row asc; slots kept in insertion order through upsert, delete/reinsert and compaction (`vector_index.py:206`) | `_oracle_scan` (`vector_index.py:120-153`) | `tests/unit/test_native_scan_conformance.py` (32 tests from 20 functions): bit-identical cosines and order, ties included, for finite, non-overflowing inputs; the overflow cases (`test_overflowing_finite_components_match_oracle_without_panic`, `test_overflow_through_the_public_query_op`) match the oracle by falling back to it; Rust tests `ties_break_by_row`, `dead_and_zero_rows_skipped`, `overflow_to_nan_is_reported_not_sorted`, `topk_equals_full_sort_prefix` | built; admitted on exactness, not on D1's latency gate |
| **Rerank with exact early stop** (pure Python) | `VectorIndex.iter_query` (`vector_index.py:366-401`, growing top-k windows) → `ECS.rank_hits` (`ecs.py:335-381`; clamp `:371`, stop `:366-367`, stable sort `:380`) | ranking every hit, as before | `tests/unit/test_rank_early_stop.py` | built. Utility never crosses into Rust, which is the better boundary for Q4 |
| **Retention decay** (not D1) | `ECS.decay_all` native branch (`ecs.py:257-263`) → `decay_batch` (`lib.rs:256-269`) → `decay_column` (`lib.rs:243-253`) | `decay.py:decay_value` (`:48-69`) | `tests/unit/test_native_decay_parity.py`: bit-identical incl. clamp, floor, NaN, subnormal; **same platform `exp` only** (Exactness) | built under the seam rule (O27), not D1; its marginal cost is now bounded by the fair matrix (about 1–1.5 ms p95 at 10k, below) |
| **v5 dot seam** (seam rule, O27; v5 reference code, not the default handle) | `ExactIndex.cosines` (`src/moneta/v5/index.py:104-126`) mirrors v5's unit vectors into `moneta_native.ScanIndex` and calls `ScanIndex.dots` with a sum that reproduces the interpreter's own `sum()` (sequential on ≤ 3.11, Neumaier-compensated on ≥ 3.12, `index.py:15-19, :38-39`). The query is still normalized in Python; `MONETA_NATIVE=0` forces the loop (`index.py:43-48`) | v5's Python loop (`index.py:123-126`) | `tests/v5/test_native_index_parity.py`: sum kernel vs `sum()`, cosines, remove/re-add/compaction, errors, and whole `recall` with and without native | built (`88d1f87`); exact per interpreter, **not across interpreters**: Python 3.11 and 3.14 can differ in the last bit, native or not (`index.py:18-19`) |

**D1 measured (fair matrix).** End-to-end `Moneta.query` at 10k × 384, limit 10, owner workstation, Python 3.14, 2026-10-15 (`scripts/bench_query.py`; arm P `scripts/bench_arm_p.py`; every row from `results/bench_query_fair_matrix.jsonl`). **Every arm uses the same exact early-stop rerank (`ECS.rank_hits`)**, so the arms differ only in the scan and the decay kernel. Each cell is the range over 2 runs of N = 200 queries after warm-up; aged = `--spread` (log-uniform 0.01–1).

| Arm (scan / decay) | p95 | p50 | store RSS (`rss_delta_mb`) | Protocol (inline caveat) | vs 50 ms p95; exactness |
|---|---|---|---|---|---|
| pure-Python oracle / Python | 227–313 ms (fresh + aged) | 211–289 ms | ~185 MB | N = 200 × 2 runs, fresh + aged; **workstation, not the 2-vCPU reference container** (O13) | misses; is the oracle |
| numpy arm P / Python | 26.6–29.1 ms (fresh + aged) | 8.2–9.8 ms | ~184 MB | same; workstation only | **clears**; 1496 of 2000 cosines not bit-equal |
| native scan / Python | 4.3–4.5 ms fresh, 8.1–8.2 ms aged | 4.3 ms fresh, 7.3–7.5 ms aged | ~69 MB | same; workstation only | clears; bit-exact (finite, non-overflowing inputs) |
| native scan / native decay | 3.1–3.3 ms fresh, 6.6–6.7 ms aged | 3.0–3.1 ms fresh, 5.8 ms aged | ~69 MB | same; workstation only | clears; bit-exact (finite, non-overflowing inputs) |

**Reading it.** Arm P clears the gate by about 1.7× on its worst run, so **D1's latency clause did not fire**; the native scan is admitted on exactness and the zero-runtime-dependency rule (seam rule, O27), not on speed. Like for like, native scan + native decay is **4.1–8.8× tighter than arm P at p95** (native scan alone 3.3–6.1×), only 1.6–2.9× at p50, and holds 2.7× less store RSS. The decay kernel's marginal cost is now bounded: native decay moves p95 from 4.3–4.5 to 3.1–3.3 ms fresh and from 8.1–8.2 to 6.6–6.7 ms aged, about 1–1.5 ms. Arm P exactness: 1496 of 2000 cosines not bit-equal to the oracle, order unchanged in that sample (n = 2000, not 10k; `results/bench_query_arm_p.jsonl`). `rss_delta_mb` is the store-build footprint, not query memory.

**v5 measured (dot seam).** `recall(q, 10)` on one v5 journal of 10k × 384, owner workstation, Python 3.14.2, N = 200 after one warm-up query, one process per `MONETA_NATIVE` mode (`scripts/v5/bench_recall_native.py` → `results/bench_v5_recall_native.jsonl`, rows 1–7) `[M]`:

| v5 index | p95 | p50 | open | open RSS (`open_rss_delta_mb`) |
|---|---|---|---|---|
| Python loop (oracle), rows 1, 2, 4, 6 | 184.4–194.4 ms | 176.4–187.2 ms | 0.70–0.85 s | 312 MB with tuple units (rows 2, 4); 193 MB with `array('d')` units (row 6) |
| native dot seam, rows 3, 5, 7 | 18.8–19.8 ms | 14.0–14.8 ms | 0.76–0.79 s | 342 MB with tuple units (rows 3, 5); 224 MB with `array('d')` units (row 7) |

**Reading it.** The dot seam takes v5 recall p95 down about 10×, from 184–194 to 19–20 ms. **The RSS drop is not the seam:** 312 → 194 MB (Python index) and 342 → 224 MB (native) both come from storing unit vectors as packed `array('d')` instead of tuples of floats (`src/moneta/v5/model.py:181-193`; commit `88d1f87`; rows marked `"variant": "unit-array"`). The native index holds about 30 MB **more** than the Python one, because it mirrors the vectors into Rust. Row 1 also built the journal (`build_s` 16.8 s); its open RSS (71 MB) is not comparable. On this machine v5's oracle misses D1's 50 ms gate and the dot seam clears it, but **D1 was not measured on v5** (no numpy arm P on v5's facade; §8 mile 0 Done means #3), so the seam is admitted under O27, not D1. Rows 6–7 are single runs.

**Superseded history, not a gate comparison.** Earlier single runs of 30–50 queries, fresh utilities only, taken before `iter_query` and `rank_hits` existed (every hit materialized and reranked), recorded arm P at **109 ms p95** (`results/bench_query_arm_p.jsonl`) and the native scan alone at 15.4 ms p95 (`results/bench_query_after_seam1.jsonl`); `results/bench_query_baseline_python.jsonl` and `…_after_seam3.jsonl` hold the same era's Python and native runs. The 109 ms figure compared an arm without early stop against a native arm with it, and must not be used as D1 evidence. Read across the two protocols, early stop took arm P from about 109 to about 27 ms and the native scan from 15.4 to about 4.4 ms: **the exact early stop, a pure-Python change, was the dominant latency win**, and the native scan's marginal gain over numpy is the 4–9× at p95 above.

**Machine dependence.** The 50 ms gate was set against single runs on a 2-vCPU container (`BLUEPRINT_v6.md:353, :361`); the figures above come from a much faster workstation. The same pure-Python path ran within about 1.3× across the two machines (345 ms container median vs 267 ms workstation median in the earlier single run) `[A]`, but that factor was measured on pure Python, not on numpy/BLAS limited to 2 vCPUs. So arm P's pass (about 1.7× under the gate here) is likely on the container but less robust than a wide miss would have been, and the native pass (more than 7× headroom with aged utilities) is likely there too; absolute numbers do not carry. A re-run on a 2-vCPU container is `[U]`. The table meets O13's query-gate protocol (N ≥ 200, fresh and aged, run-to-run range) except for the reference machine. A fully vectorized arm P (decay, clamp × U and argpartition all in numpy) was not measured. Native latency depends on the utility distribution, because the early stop does; the worst case is a high-cosine, low-utility head (exercised for exactness by `test_stale_high_cosine_low_utility_forces_deep_scan`, not timed).

**Test matrix.** At `ba52ca7`: 405 passing in each of four configurations (v1 and v5 suites together; hython without the wheel: 347 pass, 35 native-only skip) `[M]`. Before the Round 4 pass: 215 passing in each of four configurations (Python 3.14 and hython 21.0.773 / Python 3.11, each with `MONETA_NATIVE=0` and `=1`); without the wheel, 167 pass and 33 native-only tests skip (`CLAUDE.md:155`, working tree) `[M]`. v5's suite is separate: `tests/v5` at `57a90bc` passes 158 under Python 3.14.2 with `MONETA_NATIVE=0` and `=1`, and 151 + 1 skipped (the native-parity module, no wheel) under hython 21.0.773 `[M]`. Hython with the wheel was not run for v5.

**Gaps against v7's seam rules.** These bind v7 seams, not this crate, but they are what promoting it would have to close:
- **SM1 / principle 7.** `ScanIndex` is a stateful handle (vectors and cached norms held across calls, slots compacted), and `iter_query` carries a single-writer rule (`vector_index.py:375-376`). Only the inner kernel `scan_topk` is a pure function. Whether the v7 seam is `ScanIndex` extended or a pure `scan()` wrapped by it is O32.
- **§6 condition 3.** Conformance is pytest-only against a live oracle; there are no shared content-addressed `fixtures/<sha>`, and the cargo tests are four inline unit tests.
- **Q11.** No FTZ/DAZ probe exists in either seam or oracle (V-FPENV).
- **Q12.** A non-finite, non-numeric or empty vector demotes the native index to the oracle for good (`vector_index.py:269-283`); a non-finite query is answered by the oracle (`:350-354`). Neither returns a reject tag.
- **Overflow `[M]`.** The exactness envelope is finite **and non-overflowing**. Finite components near 1e308 pass `ScanIndex.check` (`lib.rs:116`) but overflow a norm or dot to inf and give a NaN cosine. `scan_topk` now returns `NonExact` on any NaN cosine (`lib.rs:71-73`; Rust test `overflow_to_nan_is_reported_not_sorted` `:302`), `ScanIndex.scan` raises `ArithmeticError` (`:220-227`), and `query` / `iter_query` catch it and answer that query with `_oracle_scan` over the native rows (`vector_index.py:355-362, 389-395`; `test_overflowing_finite_components_match_oracle_without_panic`, `test_overflow_through_the_public_query_op`). Before this fix the comparator mapped NaN to `Equal`, which is not a total order: the order could differ from the oracle's with no demotion, and `sort_unstable_by` could panic through `Moneta.query`. What remains: the fallback is per query, not a demotion, so one stored row near 1e308 sends most later queries (those whose dot also overflows) through the pure-Python oracle (a latency cliff with no log line), and it is still not a reject tag (Q12).
- **P5.** Ties follow v1 insertion order, which is what Q1 says v7 replaces.
- **Packaging.** No `[project.optional-dependencies]` extra names the wheel; the build needs rustup, MSVC build tools and maturin; hython uses the unzipped abi3 wheel on `PYTHONPATH`. Linux and macOS parity (glibc or libSystem `exp`) is `[U]` (O11).
- **Cross-interpreter exactness (v5) `[V]`.** v5's cosine oracle is Python's `sum()`, Neumaier-compensated on 3.12+ and sequential on 3.11 (`src/moneta/v5/index.py:15-19, :38-39`), so one v5 score can differ in the last bit between hython 3.11 and Python 3.14. That is within-interpreter determinism (v5's I6), not G3-5's byte-identical rebuild across machines or V-POOL's bit-for-bit agreement between referee and read path. A v7 read path built on v5's index must first move to one declared summation order.

**Sequencing, as the built facts change it.**
- The scan no longer waits for mile 4b, but not because of D1: D1's gate did not fire, and the v1-line native scan on `main` rests on the seam rule's exactness clause (O27). If the owner confirms that rule, mile 4b **promotes** it to the v7 signature (P5 ties, allowed set, utility, pure over flat buffers) under V-ORACLE-SCAN. Otherwise it stays a v1-line accelerator and the v7 scan is Python: the exact oracle, which misses 50 ms, or numpy arm P, which clears it only as a recorded contract-E downgrade.
- The first **v7** Rust is still `moneta-referee` with the `moneta-kernel` it needs, at mile 4, if the fuel/memory gate fits.
- The decay kernel follows O31: when the ported `exp` lands, it switches and is re-verified, or it is disabled.
- Where the v7 crates live (inside `rust/`, beside or around `moneta_native`) is O32. `moneta_native` is not renamed to fit the plan below.
- Before any of that: commit `rust/` with its `Cargo.lock`.

**Workspace `[P]`** (planned v7 layout; what exists today is the single crate above):

```
rust/  (one cargo workspace, pinned toolchain, Cargo.lock committed)
  moneta_native/   std           exists today (v1 line): ScanIndex + decay_batch, pyo3; its v7 role is O32
  moneta-kernel/   no_std        ported-exp decay (not a move of moneta_native::decay_column), fold_recall, total_order,
                                 the one exp port (needed by the referee unconditionally)
  moneta-referee/  no_std        wasm32; zero imports; deps: kernel
  moneta-journal/  no_std+alloc  canonical codec, event and edge types, hash chain   (tripwire; not built by default)
  moneta-verify/   std           the G1 walker                                         (tripwire; not built by default)
  moneta-py/       std           pyo3 bindings for v7 seams; built only for a gated seam (may be moneta_native itself, O32)
  moneta-scan      no separate crate planned now; the v1-line scan lives in moneta_native (above)
fixtures/<sha256>                shared by pytest and cargo test
src/moneta/oracle/               referee.py, fold.py, verify.py, scan.py, exp.py
```

**What stays out of Rust:** USD composition, labeling, the gating workflow, the tuner, and `reload()` linting.

### The guarantees the seams need (Q1–Q12)

| ID | Guarantee | Seams | v1 today `[V]` |
|---|---|---|---|
| **Q1** | Total order `(score desc, seq asc, record_id asc)` | referee, fold, scan | ties fall to dict insertion order through stable sorts (`vector_index.py:140,152`, insertion order from `:344-345`; `ecs.py:380`). The native scan on main reproduces the same insertion-order ties bit for bit (§1 row 9), so its conformance shows fidelity to v1 ties, not P5. Adopting P5 changes tie order relative to `test_native_scan_conformance.py`; oracle and native must change together |
| **Q2** | Canonical bytes: one encoding per event (the envelope `{seq, kind, t, prev}` plus body; sorted keys, floats as IEEE-754 bit patterns, non-finite refused, `-0.0` as `+0.0`, no optional whitespace, payload and vector replaced by their salted commitments). The chain hashes these bytes. Vectors have one canonical encoding (dim, little-endian f64) | verify | the WAL is plain JSON with "no checksums" (`durability.py:25-26`); v5's framing `[V]`: `<crc32 hex> <canonical JSON>\n` per event, sorted keys, compact separators, `allow_nan=False`, gap-free `seq`; a torn tail is truncated and mid-file corruption refuses to open (`src/moneta/v5/journal.py:8-23, :81-135`). CRC, not a hash chain |
| **Q3** | Complete inputs; time is an argument | referee, fold, scan | `query` reads `time.time()` itself (`api.py:399`) |
| **Q4** | Reads never write (E2) | fold, scan | `query` mutates utility (`api.py:401`; `ecs.py:251-272`, native branch `:257-263`, oracle loop `:264-272`, both in place). E2 is RULED for v5 (`RULINGS.md:54-55`), and v5's `recall`, `explain` and manifest write nothing `[V, src/moneta/v5/substrate.py:663-701, :736-743, :892-954; tests/v5/test_conformance.py:274-283; test_review_regressions.py:196]` |
| **Q5** | One `exp`, bit-exact by default; contract E only as a recorded fallback | referee, fold, scan | platform `exp` at two sites: `math.exp` (`decay.py:68`, oracle and `decay_one`) and, with the wheel, Rust `f64::exp` (`lib.rs:250`, `decay_column`, via `decay_batch` from `ecs.py:259-261`). Both must move to the port together, or the kernel be disabled (O31) |
| **Q6** | Flat, schema-hashed buffers, with the schema named by the constitution | all | `[P]` |
| **Q7** | A generation edge on attention (live when `signal_attention` was called, carried through the WAL) | verify, fold | entries are `(entity_id, weight, timestamp)` (`attention_log.py:73`); the WAL record has no generation (`api.py:427-429`); v5's `attend` event carries only `{t, w}` (`src/moneta/v5/substrate.py:733`) |
| **Q8** | No feedback: seams read `derived/` only for a hash-matched checkpoint | verify, fold | `[P]` |
| **Q9** | Bounds live in the journal under X1 | referee, fold | the locked `ARCHITECTURE.md:82` range, implemented hard-coded as 60 s – 24 h (`decay.py:33-35`) |
| **Q10** | No GIL dependence in seams; ordering comes from the single writer (E3 RULED for v5, closure gated: §8) | all | `attention_log.py:64-68` refuses free-threaded Python. v5 has no GIL sentinel (`tests/v5/test_conformance.py:363-366`) and orders writes under one `RLock` (`src/moneta/v5/substrate.py:356, :490-502`). Free-threaded Python stays `[U]`, with a warning (`RULINGS.md:77`), although v5's docstrings claim support (`substrate.py:23-24`; `compat.py:91`) |
| **Q11** | A declared FP environment: no FTZ/DAZ, round-to-nearest-even, probed per call or thread, fail closed | all float seams, oracles | not checked, including in the native seams on `main`; hython 21.0.773 and Python 3.14 do not flush on the main thread `[M]` |
| **Q12** | Non-finite results canonicalized to one reject tag; non-finite inputs refused by the codec | referee, fold, scan | at 6cf05f5, no finiteness checks anywhere in `src/moneta`. Working tree: the native index demotes for good on a non-finite, non-numeric or empty vector (`vector_index.py:269-283`), answers a non-finite query with the oracle (`:350-354`), and answers a query whose cosine overflows to NaN with the oracle, per query (`:355-362, 389-395`; `lib.rs:71-73`); `rank_hits` disables early stop on non-finite utility (`ecs.py:358-362`); none is a reject tag |

**The cost to name.** v1 declares **no** runtime dependencies `[V, pyproject.toml:37]`. `vector_index.py` explicitly declines `lancedb`/`pyarrow` as runtime dependencies `[V, src/moneta/vector_index.py:35-44]`, and nothing under `src/moneta/` imports `lancedb`. In the working tree, `src/moneta/` also imports the optional `moneta_native` (`rust/moneta_native`, an abi3 wheel) under `try/except` at `ecs.py:39-42` and `vector_index.py:83-86`; it is declared nowhere in the root `pyproject.toml`, and `MONETA_NATIVE=0` or an absent wheel gives the Phase 1 oracle path (`CLAUDE.md:136-157`).

`pxr` is used by `usd_target.py`, but it comes from a bundled OpenUSD, not from pip (`CLAUDE.md`, pxr requirement). Two places disagree with `pyproject.toml`:
- `CLAUDE.md:99` says "Phase 3 adds `pxr` … and LanceDB" (the working-tree `CLAUDE.md` adds the native-seam section at `:136-157` but leaves `:99` unchanged)
- `ARCHITECTURE.md:274` sets a LanceDB commit budget

That is a docs/code drift for the Documentarian, not a v7 decision.

So ed25519 and a WASM runtime (for example `wasmtime`) would be v1's **first** declared runtime dependencies. `moneta_native` is the first **optional** native component: `dependencies = []` still holds because the wheel is undeclared and auto-detected, so a host gets different code paths depending on whether the wheel is installed, with bit-identical results on this platform for finite, non-overflowing inputs, the oracle answering the rest ("Built so far"). Which packages to use, whether they work on Windows, and whether the wheel gets a `native` extra, is O11.

---

## 7. Locks

| Lock (`CLAUDE.md` / `ARCHITECTURE.md`) | In v7 |
|---|---|
| Four-op agent API, no fifth op | **Kept.** New verbs are harness ops `[V, ARCHITECTURE.md:46-50, Ruling B]` |
| Decay `U = max(floor, U·e^(−λΔt))`, lazy, exactly three evaluation points (`ARCHITECTURE.md:84-90`) | **Ruled (E2):** the formula stays verbatim; "three evaluation points" becomes "zero mutation points; state changes only through journaled events" (`RULINGS.md:55`), not yet amended in `ARCHITECTURE.md` at `57a90bc`. **Kept** for retention in v1. Whether v7's per-event retention fold is point 2 or a fourth point was Round 4's (O29); under the new wording it is answered in substance and needs an explicit line in the amendment (`ROUND4_BRIEF.md:338`). The recall fold is a pure view (G2-8, V-EVAL3); whether that reading holds goes to Round 4 (O2) |
| λ tuning range 1 min – 24 h (`ARCHITECTURE.md:82`) | **Kept for retention.** Whether it binds the recall λ goes to Round 4 (O28); until then it is X1's recall envelope |
| Concurrency: append-only attention log (`ARCHITECTURE.md:108-112`) | Replaced by the journal under E3: **RULED for v5, closure gated** (`RULINGS.md:69-79`). E3-1: **partly met** `f379488` (verified, owner to accept): projection-only pass recall p95 1567 → 14.9 ms (hython, real `UsdTarget`, 768-d) meets ≤ 30 ms; a pass that also prunes 1000 records misses at 73.3 ms (lock hold 374 ms) because the E4 re-pack rebuilds the index under the lock; `layer.Save` still holds the GIL (recall max ≈ 490 ms) `[M]`. E3-2: **met on lock hold** `f379488` (verified, owner to accept): export at 10k × 768 holds the lock 11 ms (hython) / 21 ms (Python), was 4951 / 3530 ms; worst single reader delay over baseline ≈ 44 ms on hython, because serialization shares the GIL `[M]`. E3-3: **met** by the checkpoint (see E1-B1) (verified, owner to accept) `[M]`. §5.1 is to be amended so attention is visible immediately (E3-B3). R4a's exclusion has its carrier once E3 closes (O30) |
| Atomicity: sequential write, the vector index authoritative, no 2PC (`ARCHITECTURE.md:146, 152`) | Superseded by E1: **RULED for v5, with conditions** (`RULINGS.md:54-67`). E1-1: **met** `279d903`+`57a90bc` (verified, owner to accept): `os._exit` at 1/2/20/56/57 appends and on an empty journal all reopen with every record; recall equals an uninterrupted migration; post-crash writes refused with working guidance `[M]`. E1 retires the vector-index authority but keeps an ordered two-file write (payload file, then journal append; G1) |
| §6 consolidation triggers (`ARCHITECTURE.md:120-123`, locked through §15.7, `:323`; `consolidation.py:49, 87-90`) | **Suspended for the whole Promoted + Expired hold** under J7/G4-4, which has no time limit under O5's default. Needs Round 4 (§9 Trigger 2) and O23 |
| §15.2 operational envelope | Constraints #1–#3 **kept and checked** for records (G3-8, V-ENVELOPE). Policy layers sit outside the batch path. Constraint #4 (LanceDB commit budget) superseded with E1, Round 4 |
| Composition is Pixar's USD; oxideav-usdz parked | **Kept.** No seam touches USD |
| No free-threaded Python (`attention_log.py:64-68`) | Kept for v1 code. Seams are GIL-independent (Q10). E3's ruling keeps free-threaded Python `[U]`, with a warning (`RULINGS.md:77`). E3-B2: **open**: v5 docstrings still claim free-threaded support; v5 carries no guard (`tests/v5/test_conformance.py:363-366`) |

---

## 8. Mile map

The mile map uses **v6/RULINGS numbering**, unchanged, so that R2's "Mile 2 adds a β sweep" and R4's "shadow-only through mile 4" stay literal. Mile 0 and mile 2 run **in parallel**.

### Mile 0: Round 4 (a MONETA.md §9 escalation): ruled; v5 merged beside v1; closure pending

**Step 0 (owner): done.** The v5 bundle was found and merged beside v1 (O35; `861bed9`, on `v7-native-seams`, not `main`). The brief went out as `docs/v7/ROUND4_BRIEF.md` (not `docs/rounds/round-4-brief.md`), without mile 2's report, and the owner ruled on 2026-10-15 (`RULINGS.md:48-101`). The round **closes** ruling by ruling, as each one's blocking conditions are implemented and measured (`RULINGS.md:101`). Condition IDs below are this paper's, numbered in `RULINGS.md` order. The code column records what was read at `57a90bc`. The status column records the Round 4 implementation pass that followed (one task at a time, each checked by an independent adversarial verifier; 405 tests green under Python 3.14 and hython 3.11, native seams on and off; v5 mutation check `missed: []`). "Met" means implemented, measured and verified; accepting closure is the owner's call.

| ID | Ruling | Condition (`RULINGS.md` line) | Gates | Code at `57a90bc` `[V]` | Status at `ba52ca7` |
|---|---|---|---|---|---|
| E1-1 | E1 + E2 | migration crash window: whether to migrate is decided from a journaled completion marker, not from whether the journal file exists (`:56`) | cutover step 2 | `v1_migration_begin` / `v1_migration` notes; an interrupted migration is set aside and restarted from `snapshot.json.v1-original` (`src/moneta/v5/compat.py:22-29, :267-383, :810-868`; commits `279d903`, `57a90bc`) | **met** `279d903`+`57a90bc` (verified, owner to accept): `os._exit` at 1/2/20/56/57 appends and on an empty journal all reopen with every record; recall equals an uninterrupted migration; post-crash writes refused with working guidance `[M]` |
| E1-B1 | E1 + E2 | a checkpoint, so open replays only the tail (`:58`) | 5.0.0 | open replays the whole journal (`substrate.py:369-370`) | **met with one miss** `9db6aab`+`30ae826` (verified, owner to accept): 1M events reopen 0.063 s from a checkpoint vs 5.56 s full replay (Python 3.14), 0.067 s vs 8.70 s (hython); a deposit-heavy store (99k × 64) reopens in 1.09 s, over the 1 s budget; covered lines are not CRC-checked at open (`Substrate.verify()` is the full check) `[M]` |
| E1-B2 | E1 + E2 | re-projection made idempotent (`:59`) | 5.0.0 | not checked | **open**: not attempted in this pass |
| E1-B3 | E1 + E2 | one source of λ (`:60`) | 5.0.0 | λ from genesis and `half_life` events only (`model.py:8-26, :209-248`) | **met** `720b3b0` (verified, owner to accept): λ from genesis and journaled `half_life` events only `[V]` |
| E1-B4 | E1 + E2 | runtime λ tuning made explicit (`:61`) | 5.0.0 | `set_half_life(mode=…)` (`substrate.py:749-770`) | **met** `720b3b0`+`a777287` (verified, owner to accept): `set_half_life(mode=…)` with `forward` or `reinterpret`; a mismatched open raises `HalfLifeMismatchError` before any write `[V]` |
| E1-B5 | E1 + E2 | a timestamp-skew guard (`:62`) | 5.0.0 | none: host `t` passes after a finiteness check (`substrate.py:487-488`); fold-side `max` only (`model.py:346`) | **open**: not attempted in this pass |
| E1-B6 | E1 + E2 | the native decay seam ported to v5 (`:63`) | 5.0.0 | v5 imports `decay_value` only; no `decay_batch` (`model.py:57`) | **met** `ba52ca7` (verified, owner to accept): recall and the sleep pass decay through `decay_batch`, bit-identical to the oracle; gain is small, p95 15.2–15.4 → 14.4 ms at 10k × 384 (Python 3.14) `[M]` |
| E1-P1 | E1 + E2 | a CRC-bad final line treated as a torn tail (`:65`) | polish | a complete bad line refuses to open (`journal.py:122-127`) | **open** (polish) |
| E1-P2 | E1 + E2 | an attention durability tier (`:66`) | polish | every append fsyncs (`journal.py:326-327`) | **open** (polish) |
| E1-P3 | E1 + E2 | export failure logged, not raised (`:67`) | polish | logged on close (`compat.py:756-763`); not on the sleep-pass export (`compat.py:792-796`) | **open** (polish) |
| E3-1 | E3 | USD projection outside the writer lock; recall p95 stall ≤ 30 ms during a sleep pass (real `UsdTarget`, hython, 500-prim batches) (`:71`) | E3 closure | projection runs inside `with self._lock` (`substrate.py:791-878`) | **partly met** `f379488` (verified, owner to accept): projection-only pass recall p95 1567 → 14.9 ms (hython, real `UsdTarget`, 768-d) meets ≤ 30 ms; a pass that also prunes 1000 records misses at 73.3 ms (lock hold 374 ms) because the E4 re-pack rebuilds the index under the lock; `layer.Save` still holds the GIL (recall max ≈ 490 ms) `[M]` |
| E3-2 | E3 | snapshot export outside the lock; stall ≤ 30 ms per pass at 10k × 768 (`:72`) | E3 closure | export holds the substrate lock (`compat.py:205-242`) | **met on lock hold** `f379488` (verified, owner to accept): export at 10k × 768 holds the lock 11 ms (hython) / 21 ms (Python), was 4951 / 3530 ms; worst single reader delay over baseline ≈ 44 ms on hython, because serialization shares the GIL `[M]` |
| E3-3 | E3 | a journal checkpoint or attend coalescing, with a tested reopen budget (`:73`) | E3 closure | neither present | **met** by the checkpoint (see E1-B1) (verified, owner to accept) `[M]` |
| E3-B1 | E3 | Windows fsync numbers; group commit or the ~700 writes/s ceiling recorded (`:76`) | 5.0.0 | — | **open** |
| E3-B2 | E3 | free-threaded Python stays `[U]`, with a warning (`:77`) | 5.0.0 | docstrings claim support (`substrate.py:23-24`; `compat.py:91`) | **open**: v5 docstrings still claim free-threaded support |
| E3-B3 | E3 | §5.1 amended: attention is visible immediately (`:78`) | 5.0.0 | `ARCHITECTURE.md` unamended | **open**: `ARCHITECTURE.md` unamended |
| E3-B4 | E3 | the SYNAPSE swap re-run on Windows against a copy of the 841-record store (`:79`) | 5.0.0 | — | **open**: needs the owner's 841-record store |
| E4-1 | E4 | recall p95 with 100k dead records within 10% of zero dead (`:85`) | E4 closure | `_classify` walks every record, dead ones included (`substrate.py:545-557`) | **met** `8288a50` (verified, owner to accept): recall walks only recallable records and bulk deaths re-pack survivors; 100k dead was 1.58× zero-dead before the fix, within 10% after, with the native seam on and off `[M]` |
| E4-2 | E4 | `erase()` names or invalidates every derived copy (`:86`) | E4 closure | `erase` returns a seq only (`substrate.py:1039-1058`) | **open**, and two new leak paths found: a record erased while its batch projects still lands in USD (named under `projected_dead`, nothing retracts it); a crash between the journaled erase and the snapshot unlink leaves a pre-erase checkpoint until the next checkpoint or `compact()` |
| E4-3 | E4 | the ruling covers semantics, not mechanism (`:87`) | E4 closure | — | ruled: `compact()` stays unratified |
| E4-4 | E4 | fix the O(n²) dedup at `substrate.py:949` (`:88`) | E4 closure | ordered dict dedup, now `substrate.py:1093-1103` (commit `fae3000`) | **met** `fae3000` (verified, owner to accept): `_known`/`tombstone` on 80k ids 11.1 s → 0.07 / 0.21 s `[M]` |
| HL-1 | half-life | `fold.lam` from genesis and change events, never Config; a mismatched open raises unless the caller names a mode; read-only opens never append (`:94`) | half-life closure | `model.py:209-278`; `substrate.py:339-400` | **met** `720b3b0`+`a777287` (verified, owner to accept) `[V]` |
| HL-2 | half-life | the first sleep pass after a change is a dry run, or needs confirmation above a stated LIVE fraction (`:95`) | half-life closure | dry run until `confirm_half_life_change=True` (`substrate.py:805-829`) | **met** `720b3b0` (verified, owner to accept) `[V]` |

Not conditions, recorded with them: `compact()` is not ratified (`:82`); the E4 Jev question is to be re-asked with corrected option costs (`:90`); R2 does not flip (`:97`).

The table below is the brief's framing, kept for the record. E1–E4 and the half-life call were each ruled **for** (E4 as semantics only). The (question) rows were not ruled one by one: the first two are answered in substance by E2's wording (O2, O29); the λ range (O28), the pressure trigger (O23) and §15.2 #4 stay open.

| Item | Locked clause overturned | v1 line that embodies today's rule | If ruled **for** | If ruled **against** |
|---|---|---|---|---|
| **E1** journal authority | `ARCHITECTURE.md:146, :152` (§7); `CLAUDE.md` lock 4 | `sequential_writer.py:104-105` (authoring first, vector second); `consolidation.py:169` | G3 as drawn; exact replay possible | **rescope**: policy-only journal beside v1 storage; redraw G3 with the index as a second authority; re-plan miles 3–4 |
| **E2** reads never write | `ARCHITECTURE.md:84-90` (eval point 1); `CLAUDE.md` lock 2 | `api.py:401` | replay and the recall split are expressible | **stop the governed loop**: replay dies. v6: "v6 depends on it entirely" (`BLUEPRINT_v6.md:467`) |
| **E3** one ordered journal | `ARCHITECTURE.md:108-112` (§5.1); `CLAUDE.md` lock 3 | `attention_log.py:64-68` | the GIL guard can retire in the same round; retention fold order decided (O7, O29) | **R4a has no carrier**: the §5.1 log is cleared at every sleep pass (`ARCHITECTURE.md:106, :110`) and its entries carry no generation. R4a then needs a §5.1 amendment (a gen-stamped, durable record of attention, or a log that keeps probation-stamped entries across passes), or R4 stays shadow-only (O30). Call-time stamping (G4) is required either way |
| **E4** prune is a tombstone | §6 prune semantics (thresholds "Locked Round 2", `consolidation.py:53-55`) | `consolidation.py:166-169` | the line holds | **stop v7**: "The line depends on it" (`BLUEPRINT_v6.md:469`) |
| **Half-life call** | `ARCHITECTURE.md:82` (λ runtime-configurable, tuning range 1 min – 24 h; silent on history) | `decay.py:91-105` | R2 stays `recall_half_life` `[A]` | R2 flips to `utility_exponent`; the referee's `EvalBuf` carries U, the fold leaves the referee, the read-path binding is struck, and V-POW is added; work continues |
| **(question) recall fold vs "no fourth evaluation point"** | `ARCHITECTURE.md:90` | — | the fold is a view (V-EVAL3) | the recall half-life needs a different mechanism, which favors β |
| **(question) per-event retention fold vs point 2** | `ARCHITECTURE.md:87, :90`; `CLAUDE.md` lock 2 | `attention_log.py:129-131` | the per-event fold is point 2 (O29) | v1's per-batch order is kept for retention |
| **(question) recall λ vs the :82 range** | `ARCHITECTURE.md:82` | `decay.py:33-35` | the fold is a view, so its λ isn't bound by :82 (O28) | recall bounds capped at 1 min – 24 h; v6's 14-day example replaced |
| **(question) hold vs §6 pressure trigger** | `ARCHITECTURE.md:120-123`, §15.7 | `consolidation.py:87-90` | hold as drawn plus a growth policy (O23) | J7 narrows |
| **(question) §15.2 #4** | `ARCHITECTURE.md:274` | none (no LanceDB in v1) | superseded with E1 | a budget re-targeted at the synchronous work v7 adds per deposit |

**Done means:**
1. All rulings are recorded in `docs/rounds/round-4.md`. They are ruled and recorded in `docs/v7/RULINGS.md:48-101`; `docs/rounds/round-4.md` does not exist at `57a90bc`.
2. `ARCHITECTURE.md` and `CLAUDE.md`'s "Locked decisions" are amended in one PR. Not done at `57a90bc`.
3. Then v5 is merged under the round (it was merged beside v1 before the ruling, `861bed9`, as v5's cutover step 1, and is not the default), and its facade runs against a copy of the 841-record store (`journal/` and `payloads/` together). The migration report shows 841 of 841 records, SYNAPSE compatibility is re-measured on this machine (moving it from `[A]` to `[M]`), including SYNAPSE's wrapper restore path at the pinned commit (`docs/synapse-loop.md:13, :38`; O19), and arm P's p95 is recorded **on v5's facade** (the v1-line arm P is already recorded `[M]`, §6 "Built so far"). The import follows "Migration into format 7" (G1). The 841-record run is E3-B4 **open**: needs the owner's 841-record store. SYNAPSE compatibility stays `[A]` until then: v5's own report is 247 of 253 SYNAPSE tests on Linux, CPython 3.11, with no production store migrated (`docs/v5/SYNAPSE_COMPAT.md:5, :13, :50-52`).

**Kill.** None of the first five fired: Round 4 ruled E1–E4 and the half-life call toward v5, and R2 does not flip (`RULINGS.md:48-97`). They are kept for the record; the last stays live.
- E4 rejected: stop.
- E2 rejected: stop.
- E1 rejected: rescope.
- E3 rejected without a §5.1 amendment carrying the gen stamp: R4 is fixed at shadow_only (R4a can't be implemented); V-UNDO, V-LEAK, V-GENTAG, V-EXCL and V-RETAIN leave miles 4–5; miles 5–6 rescope (O30).
- Half-life call rejected: flip R2.
- Any record lost in the cutover: revert.

### Miles 1 to 6

| Mile | What | Done means | Kill or rescope |
|---|---|---|---|
| **1** | **Paper.** This blueprint (pass 4 of 4, complete), its review, and the rulings | R1, R4 and R5 ruled ✓; R2 and R3 carried `[A]` ✓; pass 4 applied and logged (Pass 4 log) ✓; graph schemas reviewed by the owner, recorded as a row in the Review log; go on mile 2; Round 4 brief drafted ✓ and ruled ✓ | a reviewer finds a dependency no graph can express: add the edge or drop the claim |
| **2** | **The experiment.** Python only, no Moneta changes (`BLUEPRINT_v6.md:417`). The v6 world, two hosts, arms A–E, arm D under random and systematic bias, **plus a β sweep as a diagnostic arm** (R2). By-products: `oracle/referee.py`, `oracle/fold.py` (declared step order, total order), `oracle/exp.py`, and the first fixtures. Runs alongside mile 0 | a report that passes or kills; the oracles exist with fixtures; V-HOLDOUT, V-MARGIN, V-VIEW, V-SELF and V-TIES pass in simulation with their sabotages caught | v6 §12's kills hold. **Arm A gains nothing under either knob: stop.** A gains but D and E don't: stop before mile 3, or rescope to larger owner-labeled sets. No leverage on pool recall: nothing to improve for SYNAPSE as it consumes recall today. β gains about as much as the half-life: R2 flips. E fails and D survives bias: R3 flips to `mixed`. **Numeric triggers `[P]`:** "A gains" = the lower bound of the bootstrap CI on held-out nDCG@k is > 0; "β about as much" = β's gain lies inside the half-life arm's bootstrap CI |
| **3** | **Evidence.** SYNAPSE (or a test host) logs full `QueryRecord`s; the G3 eval-set builder exists; about 200 owner labels; tuning runs in shadow on real logs | V-REBUILD (eval set, verdict leaves), V-HOLDOUT, V-REPLAY (verdict leaves), V-POOL, V-SHADOW (flag) and V-LABELPROV green on a real store; leverage measured | no byte-identical rebuild: fix the builder first. Labeling unsustainable: run the R3 flip test. Leverage about zero: stop at shadow reporting. **Numeric triggers `[P]`:** unsustainable = fewer than 50 labels/week over 4 weeks; about zero = \|Δ nDCG@k\| below the J4 margin |
| **4** | **The graphs in the store.** Python first: format 7 with the event envelope, the G1 chain, payload and vector commitment, the signed set (test key), G2 derived USD, the G4 machine, G5 pins, `oracle/verify.py`. **Then** the first Rust, if the referee's fuel/memory gate fits: `moneta-referee` and the `moneta-kernel` it needs (`exp` port and `fold_recall`). Measure the verifier gate (N, K, S as defined in §6), the read-path fold binding gate (R × A), and the open-time gate at 10k and 100k records on Windows against v5's 1.0 s (O13). **Shadow-only on real stores; the full lifecycle on test stores only** (G4-6) | every §5 check marked for mile 4 green, with its sabotage caught; V-ORACLE-REF and V-ORACLE-FOLD green (if the WASM referee ships); gate numbers recorded | a sabotage passes: that check doesn't exist yet and the mile isn't done. Referee fuel over X1: J1 downgraded to a pinned Python referee, recorded. Verifier within its gate: no Rust verifier |
| **4b** | **Conditional Rust** (a v7 sub-mile of mile 4). `moneta-verify` if its gate was missed; the `moneta-py` binding of `fold_recall` for read-path repoints if its gate was missed; the scan: a v1-line native scan exists on `main`, admitted on the seam rule's exactness clause, not on D1, whose gate did not fire (§6 "Built so far"); if the owner confirms that rule (O27), 4b **promotes** it to the v7 signature (P5 ties, allowed set, utility) under V-ORACLE-SCAN, independent of the loop | each built seam's `V-ORACLE-*` green on fixtures and the mutation corpus | a disagreement that can't be closed bit-exactly, and isn't acceptable under a recorded δ fallback: that seam stays Python |
| **5** | **Live, owner-gated.** A real key off-machine, signed transitions, the external anchor, the ceiling, and a key-rotation drill | on a real store: one propose → promote → adopt; one promote → rollback **followed by at least two sleep passes and a reopen** (V-UNDO, V-RETAIN); one rotation; V-ANCHOR and V-ROTATE green | requests pile up faster than the owner reviews them: R4 falls back to shadow_only for good. Key hygiene unsustainable: running hash without signing (the brief's R5 fallback), and J6 reverts to shadow-only. **Numeric trigger `[P]`:** pile-up = more than 2 unreviewed proposals older than 14 days |
| **6** | **Recursion.** The proposer becomes WASM in the rules tier, judged on held-out | one proposer change promoted on held-out evidence | held-out wear outruns label refresh: stop at mile 5. **Numeric trigger `[P]`:** the `disclose` count reaches the O10 cap before the window rolls |

---

## 9. Decisions still open

**Decision queue** (what to decide, in order). Every row below has a default; the owner can accept a default by leaving it.

| When | Items |
|---|---|
| **Now** (mile 0 step 0) | none: O35 answered (FOUND and merged) |
| **In the Round 4 brief** | ruled: O1 (Round 4), O27 (confirmed); answered in substance by E2's wording, pending the amendment: O2, O29. Still open: O7 (time rule, with E1-B5), O23, O28, O30 (moot once E3 closes), O31 |
| **Before mile 4** | O5, O9, O10, O15, O16, O18, O21, O22, O25, O26, O32 |
| **At mile 0, from the v5 code** | O24 answered by the code (the owner rules v7's shape); O19 answered on the substrate side, SYNAPSE side open |
| **On mile 2's report** | O4, O34 |
| **After V-MISATTR reports** | O6, O14, O17, O20 |
| **At mile 4** | O3, O8, O11, O13, O33 |
| **Before mile 5** | O12 |

| # | Decision | Default here | Decided by |
|---|---|---|---|
| **O1** | **RULED 2026-10-15** (`RULINGS.md:48-101`). Mile 0: E1–E4 and the half-life call | all five ruled toward v5: E1 + E2 for, with conditions; E3 for, closure gated; E4 semantics only, gated; half-life: the journal owns λ, each change explicit and journaled. Closure: §8 mile 0 conditions table | the owner, through Round 4 |
| **O2** | Is the recall fold a fourth decay evaluation point under `ARCHITECTURE.md:90`? | no: it is a pure view (V-EVAL3) `[P]`. **Answered in substance by E2's ruling:** "zero mutation points; state changes only through journaled events" (`RULINGS.md:55`); v5 evaluates utility at any read without writing (`src/moneta/v5/model.py:163-164`; `substrate.py:693`) `[V]`. Closes with the `ARCHITECTURE.md` amendment | Round 4 (ruled); the amendment PR |
| **O3** | How USD carries authorization. LIVRPS can't intersect | the plain resolver intersects; USD carries flattened sets; C3 restricted to value fields `[P]` | review; the USD Engineer |
| **O4** | R2 / R3 | `recall_half_life` / `owner_labels` `[A]`; the flip conditions are in RULINGS, with numeric triggers in §8 mile 2 | the owner, on mile 2's report (and Round 4's half-life call) |
| **O5** | At the probation ceiling: hold with an alarm, or auto-rollback (carved out of J6)? | hold + alarm (`expire`), no pointer move `[P]`. Under this default the ceiling is an alarm, not a bound (G4-7, O22) | the owner, before mile 4 (R4c requires a default) |
| **O6** | Does the **recall** fold also drop rolled-back attention, or only the retention fold (as ruled)? | retention only, as ruled; eval sets also exclude it (V-LEAK) `[P]`. Live recall passes an empty `excluded_gens`; if "both", a read at `n` uses the set as of `n`. **Consequences to weigh:** under the default, recall and retention diverge for the whole rolled-back window, and the referee scores the window's queries against a history that was never served (O17); during probation the recall effect of the host echo is live and self-reinforcing (G3-2) | the owner, after pass-2 attack 3 |
| **O7** | Retention fold step order: per event (v5 `[V, src/moneta/v5/model.py:337-348]`) or v1's per batch with decay forgiven (`ecs.py:240-243`); and the time rule (append-time clamp vs fold-side `max`) | per event, declared: the ruled direction (E1–E3 for v5). Append-time clamp (G1 envelope). **v5 does the opposite on the time rule** `[V]`: fold-side `max(t, anchor_t)` (`model.py:346`) and no clamp at append (`substrate.py:487-488`); Round 4 requires a timestamp-skew guard before 5.0.0 **open**: not attempted in this pass. It changes which records prune | Round 4 ruled the order's direction; the time rule stays open with E1-B5 |
| **O8** | `compact` under a hash chain | forbidden, or a signed re-genesis naming the old final hash `[P]` | the owner, at mile 4 |
| **O9** | **Extensions of R5's signed set beyond its literal text:** `erase` and `revector` (irreversible owner ops), and `roll-forward` (treated here as rollback-class; marked "signed, pending O9" in G1, G4-2 and V-SIGSET) | proposed signed, **pending the owner's confirmation**; not adopted silently | the owner, before mile 4 |
| **O10** | Disclosure accounting: what counts as "fuller," and how many wear out a window | any numeric held-out figure; wear cap 3 disclosures per window `[P]` | the owner, in the constitution, before mile 4 |
| **O11** | Runtime dependencies for ed25519 and WASM; Windows; packaging of the native wheel | pyo3 + maturin (already used by `moneta_native`); ed25519 and `wasmtime` candidates evaluated at mile 4; keep the wheel hand-installed until a `native` extra is wanted; Linux/macOS parity run outstanding `[U]` | the Persistence Engineer proposes at mile 4; the owner approves |
| **O12** | The anchor medium, and the maximum unattested window | a signed git tag in a private remote `[P]`; the window is a tripwire with an X1 ceiling `[P]`, value `[U]` (O33) | the owner, before mile 5 |
| **O13** | Gate numbers: verifier 100 ms tail over S events / 30 s full audit of N with K signed; read-path fold binding 1 s at R × A; open at 10k and 100k records on Windows against v5's 1.0 s (`BLUEPRINT_v6.md:367`); δ. **Every gate is stated with the machine, interpreter and dataset it is measured on; a gate re-measured on another machine is a new figure, not a pass** | `[P]`; axes defined in §6. Protocol `[P]`: the gate's script (for the query gate, `scripts/bench_query.py`), N ≥ 200 queries after warm-up, fresh and aged (`--spread`) utilities, p95 with the run-to-run range, on the reference machine (the 2-vCPU container) with the owner workstation as secondary; RSS recorded as a metric, not a gate. **Measured so far** `[M]`: v5 opens a 10k × 384 journal in 0.70–0.85 s on the owner workstation, Python 3.14.2 (`results/bench_v5_recall_native.jsonl`, `open_s`, rows 1–7), under the container's 1.0 s; 100k is not measured here | measured at mile 4; the owner signs the numbers |
| **O14** | Should a host echo on `signal_attention` replace the call-time stamp? Mitigations short of §9: hold the G4-4 hold until a first post-rollback pass has resolved attention arriving within a declared δ_t after any promote or rollback; or keep a record at `attended_count = 2`, utility < 0.1, touched by the exclusion, volatile for one more pass instead of pruning it | no: it would change a locked signature, so it needs §9. No mitigation adopted until V-MISATTR sizes the effect | the owner, with V-MISATTR's and O20's numbers |
| **O15** | Where the root key is pinned: the genesis or code | the genesis `[P]` (R5 allows either) | the owner, before mile 4 |
| **O16** | **How does an agent read or deposit reach a context, scopes and time?** P1 and G2 need them; the locked `query(embedding, limit)` and `deposit(payload, embedding, protected_floor)` carry none (`ARCHITECTURE.md:36-37`; `api.py:328-333, 379-380`), and v1 has no scope concept. Unjournaled ambient state would let a logged QueryRecord{context A} replay wrong with nothing in G1 to detect it | (a) v7.0 has one root context and the full scope set, so both are constants and P1 reduces to (prefix, embedding, limit, t); per-context binding becomes a v7.x item. If per-handle binding is wanted: (b) a harness-level `bind{context fingerprint, scopes, deposit scope}` event at handle construction (Ruling B precedent), checked against G2-5, classified against the signed set (widening scopes is an authorization act), cited by seq from every `deposit` and QueryRecord echo; a rebind is a new event; plus V-BIND (sabotage: serve under context B while the echo claims A) and V-QUERYSIG (the four signatures byte-identical to `ARCHITECTURE.md` §2; sabotage: an unjournaled module-level context). Per-call context or scopes would change a signature: Round 4. **Recommended: (a)** for v7.0. Consequence: G2's context forest, `reload`, V-NARROW and V-FOREST exist and are tested, but no agent read reaches a non-root context until a binding lands, so (a) defers G2's main feature, not just a parameter | the owner; Round 4 only for per-call |
| **O17** | **Which excluded set does each consumer use, and as of when?** An eval set built after a rollback excludes `g`'s attention, while the queries in `g`'s window were served with it (O6 default) | `[P]` as applied: `built_from` names `Prefix(h_build)`; live reads use the set as of `n` (empty under O6's default); V-POOL compares referee and read path under the same set; the referee scores `g`-window queries against a history that was never served, disclosed as a count. The owner should confirm this when ruling O6 | the owner, with O6 |
| **O18** | **Erase vs replay, and embedder identity.** Erasing a record's vector makes every eval set touching it unrebuildable; keeping the vector after erase leaves an invertible embedding. The embedder can't be inferred, because the host supplies the embedding (`api.py:331`) | erase deletes payload and every vector version; G3-5's exception marks affected eval sets unrebuildable and keeps their pinned blobs; the embedder id is host-declared on `deposit` and QueryRecord, pinned in genesis and each `revector`. Tie to O9 (erase is owner-signed) and E1 | the owner, before mile 4 |
| **O19** | **Does SYNAPSE need restore-from-export?** `docs/synapse-loop.md:38` names "SYNAPSE's wrapper-managed snapshot and restore"; v1's `hydrate` loads `snapshot.json` verbatim (`api.py:229`; `durability.py:181-215`; `ecs.py:179-199`), with no generation field (`durability.py:85-100`) | `snapshot.json` is export-only; the facade's open/restore replays the journal from an eligible checkpoint; a host restore request either replays or is refused (as applied in G3, V-NOFEEDBACK). If SYNAPSE needs it, the restore imports as journal events, never sets state. Verify at mile 0 against the pinned commit. **Answered on the substrate side by v5 `[V]`:** the facade never hydrates from `snapshot.json`. On open it accepts an export whose hash it wrote or journaled, ignores an unreadable one with a journal note, turns an embedder-swap rewrite into a journaled `revector`, and refuses anything else with `SnapshotDivergedError` (`src/moneta/v5/compat.py:386-493`; `tests/v5/test_compat.py:556-660`). A restore that writes `snapshot.json` back is therefore a no-op (a known hash) or refused; it never sets state, which matches this default. **Still open:** whether SYNAPSE's wrapper restore path needs more. v5's SYNAPSE report covers embedder-swap rewrites and corrupt snapshots on Linux only (`docs/v5/SYNAPSE_COMPAT.md:33, :43, :50-52`), and the 841-store run re-measures it **open**: needs the owner's 841-record store | the owner, at mile 0 (SYNAPSE side) |
| **O20** | **Host attention on retention-ranked paths during probation.** Nothing such a path ranks on was produced by `g` (G2-4, G2-8, G4-4), yet all its attention in probation is stamped `g`: rollback drops all of it from utility, `attended_count` and eval sets; adopt credits it to `g` | `[P]`: accept and disclose; V-MISATTR measures the mass. Options for the owner: (a) accept; (b) a per-handle declared "gen-neutral" source, configured outside the call (the locked signature can't carry it), which narrows R4a's exclusion and is therefore an owner act; (c) treat it as O14's material-harm evidence | the owner, with O14, after V-MISATTR reports |
| **O21** | **Roll-forward in G4, and rollback of an Adopted generation.** Roll-forward is signed and pointer-moving, but has no state in the diagram and can't itself be rolled back or excluded. Rolling back an Adopted `g` goes to Retired, where G4-5 never fires, although R4a applies "on rollback" (`RULINGS.md:20`) | roll-forward creates a new generation entering Promoted (so hold, ceiling and G4-3 apply) and widens **of** so a later rollback can target it; for an Adopted `g`, either (a) rollback also triggers exclusion and a reseal refolded from the last eligible seal before `g`'s promote, or (b) R4a is read as pre-adopt only and J8 is reworded. Recommended: (a), the literal reading. Depends on O9. Add fixtures: promote, rollback, roll-forward, rollback; adopt then rollback | the owner, before mile 4 |
| **O22** | **The hold has no resource bound.** Under O5's default, Expired has no time limit, so for an absent solo owner the hold, memory and journal growth, the unattested tail, and the attention mass a later rollback drops (14 + T days) all scale with the absence. This is what R4c was ruled to fix (`pass1_rulings_brief.md:272`) | keep hold + alarm, and add an X1 resource ceiling `[value U]` (held wall time, hot-tier count or unattested-tail length) whose action the owner chooses: (a) auto-rollback, carved out of J6 (O5's alternative); (b) a held pass that stages but never prunes and writes no `retention` event, admissible only if shown irreversible-free and reconciled with V-HOLD; (c) refuse `deposit` at the ceiling (a new refusal mode, check against X3). Optionally stamp attention appended while Expired as `(g, expired)`, excluded by default on rollback, so the mass under the plain `g` stamp is bounded by the ceiling; and a rollback-to-promote cooldown in `const` | the owner, before mile 4, with O5 |
| **O23** | **What happens when `MAX_ENTITIES` is crossed under a hold?** The §6 pressure trigger is locked through §15.7; v1's `should_run` is defined but never called, so the trigger is advisory | alarm (as applied); then one of: (i) deposits admitted and the overshoot bounded under X1; (ii) a signed auto-rollback carve-out; (iii) a staging-only pass exempt from the hold, which needs a statement of whether staging carries `g`'s influence. Recommended: (i) until mile 5 measures growth | Round 4 (§9 Trigger 2) and the owner |
| **O24** | **What is a slot preference, and what does an empty slot resolve to?** v5's slot semantics were `[A]` (`BLUEPRINT_v6.md:74, :540`) and are now `[V]` from v5's code (below); pass 1 allowed that selections may list record ids (`pass1_rulings_brief.md:89`) | **Answered by v5's code `[V]`, and it differs from this paper's earlier default.** In v5 a slot preference is **one** record id per slot (`src/moneta/v5/policy.py:30-32, :161-166`), resolved by strength per slot (`:208-210`). The winner is that id if it survives the caller, scope, exclusion and status filters; otherwise the **latest-deposited admitted claim** (max `seq`) wins; a slot is empty only when no claim is admitted (`substrate.py:558-571`; `explain` says which, `:927-936`). The winner is picked before the zero-vector check, so a direction-less winner hides every other claim in its slot (`:572-579`). The earlier default here (an ordered list; empty when none admitted) is **not** v5's. Recommended: adopt v5's shape and fallback for v7.0, so G2-9 and V-REPLAY match the code; an ordered list is a later extension. Answers pass-2 attack 4 once confirmed | the owner, at mile 0: the code has answered the question; the owner rules which shape v7 keeps |
| **O25** | **Revector: keep the old vectors or drop them?** Keeping them preserves replay at earlier prefixes; dropping them makes pre-revector eval sets unrebuildable. Either way an erase must delete every vector version | keep until an explicit erase of that record; erase deletes the closure of every commitment reachable by **about** edges from `deposit` and `revector`. Specify `revector` as one signed event (O9) carrying the new embedder pin and per-record `(old → new)` commitments. Under keep, a `revector` appends a versioned vector section to the record's `payloads/<record_id>` file under the same nonce, so the one-file-per-record layout holds and erase still deletes everything by deleting the file. **Write order `[P]`:** append the section and fsync, then append the `revector` event; on open or audit, a trailing section that no `revector` names is truncated (V-PAYLOAD's crash fixture) | the owner, before mile 4 |
| **O26** | **What does `adopt` rest on, and is there a minimum probation?** Adopt has no **evidence** edge, nothing measures probation, and the 14-day default is derived from nothing | adopt is the owner's untyped judgement, moving responsibility for retention effects to the owner (`BLUEPRINT_v6.md:124`), stated as such (§3 step 8). Optionally an **evidence** edge from adopt to the probation tripwire leaves and the `disclose` events the owner viewed, as a record, not a gate. A minimum probation as an explicit constitution value, default 0. Derive the ceiling from what probation costs, not from a measurement window. A probation verdict on `g`-stamped queries is a new eval channel that wears the window (R4d) and is not recommended | the owner, with O5 |
| **O27** | **RULED 2026-10-15: CONFIRMED** (RULINGS.md). **Is the seam-admission rule a constraint?** D1's text is scan-only (`BLUEPRINT_v6.md:41`); the referee, kernel, verifier and bindings rest on v6 §10's report of v5's rule (`:349`), which pass 2 called "D1, restated" | ruled: a project constraint, not D1 (`RULINGS.md:32-33`). **Live instances (three):** v5's dot seam (`ScanIndex.dots` behind `ExactIndex.cosines`, §6 "Built so far"); and `moneta_native.decay_batch` and `moneta_native.ScanIndex`, which both shipped on `main` 2026-10-15 under this rule, not D1. The scan's justification is exactness plus the zero-runtime-dependency rule, because D1's latency gate did not fire (arm P 26.6–29.1 ms p95). Both sit on the read path of every `query`, which makes this ruling more urgent. Default: keep both behind `MONETA_NATIVE`, with their conformance suites as the contract. Condition 4 now has numbers from the fair matrix: decay about 1–1.5 ms p95, scan 4–9× tighter than arm P at p95 (§6 "Built so far") | the owner, before the Round 4 brief goes out |
| **O28** | **Does `ARCHITECTURE.md:82`'s 1 min – 24 h tuning range bind the recall λ?** It is a locked clause; v6's 14-day example exceeds it | **interim (applied):** the recall λ **is** bound by :82; X1's recall envelope is the :82 range, and V-BOUNDS's sabotage is "bounds hard-coded outside the journal". **Proposal to Round 4 `[P]`:** the fold is a view, so the recall λ is not bound by :82; asked beside O2. Round 4 did not rule it. v5 range-checks its single λ against the :82 range (`DecayConfig`, `src/moneta/v5/substrate.py:344, :767`) `[V]` | Round 4 (not ruled) |
| **O29** | **Is the per-event retention fold eval point 2 or a fourth point?** It decays at each attention `t` before the add; `ARCHITECTURE.md:87` locks point 2 as "immediately after the attention-write phase", and v1 decays once, after the batch write (`attention_log.py:129-131`). Call sites stay three, so the "no fourth call site" test (`:90`) would not fire | route to Round 4 with O7, citing lock 2 (`CLAUDE.md`) as well as E3; fallback is v1's per-batch order for retention. **Answered in substance by E2's wording** ("zero mutation points", `RULINGS.md:55`); the amendment should say explicitly that the per-event fold is the rule (`ROUND4_BRIEF.md:338`) | Round 4 (ruled); the amendment PR |
| **O30** | **E3 was ruled for (`RULINGS.md:69`); this applies only if E3's closure fails.** **If E3 is ruled against, where does R4a live?** The ruled exclusion is realized entirely through `attention` being a seq'd, gen-stamped G1 event; the §5.1 log is cleared every sleep pass | ruling R4a means Round 4 must either accept E3 or amend §5.1's clear-at-sleep-pass rule (a durable gen-stamped attention record, or a log that holds probation-stamped entries across passes); otherwise R4 stays shadow-only. Under E3-against, the call-time stamp's single writer (G4) also puts a lock on §5.1's locked lock-free path, so it needs the same amendment or a lock-free stamp (an immutable generation snapshot with a bounded race, sized by V-MISATTR). The Round 4 brief should say so explicitly | the owner, in the Round 4 brief |
| **O31** | **Which `exp` do retention and the read path use, and when?** v7 wants one ported `exp` (Q5); `main` has two platform-`exp` call sites (`decay.py:68`; `lib.rs:250` via `decay_batch`), and the working-tree `CLAUDE.md:157` makes the decay parity test against `math.exp` a contract | (a) when Q5 lands, move `decay.py:68` and `decay_batch` to the port together and re-point the parity test at the port (`CLAUDE.md:157` changes); until then keep platform `exp` for v1 retention. The alternative (b), keeping the CRT `exp` and recording V-EXP and V-POOL as contract-E comparisons between referee and read path, is not recommended | the owner, in the Round 4 brief |
| **O32** | **Does `rust/` become the v7 workspace?** `rust/moneta_native` is one PyO3 crate holding the scan, the decay kernel and the bindings, a role the plan splits across `moneta-scan`, `moneta-kernel` and `moneta-py`; its `ScanIndex` is a handle (SM1) | `rust/` becomes the v7 workspace with `moneta_native` as its PyO3 member in place of `moneta-py`, wrapping pure kernels that move into `moneta-kernel`; the v7 scan is a pure `scan()` in the kernel that `ScanIndex` wraps; decay switches to the ported `exp` with O31 | the owner, before mile 4 |
| **O33** | **X1 ceiling values** (diff size, op count, fuel, memory, eval-set size, budget, seal interval, context depth, maximum probation ceiling, retention λ range, δ, maximum unattested window) | a proposed table drafted at mile 4 from the referee and verifier gate measurements; the owner signs it | the owner, at mile 4 |
| **O34** | **Bootstrap resampling unit** for the J4 margin | the session `[P]` | the owner, on mile 2's report |
| **O35** | **FOUND 2026-10-15** (`RULINGS.md:44`): the owner supplied `moneta-v5.bundle` (`refs/heads/v5` @ `b1feaaf`, based on `6cf05f5`) and its blueprint; merged beside v1 on `v7-native-seams` (`861bed9`), not on `main`. Earlier the same day it was searched for and not found (`RULINGS.md:35-42`). **Where is the v5 bundle?** | answered: `src/moneta/v5/`, `docs/v5/`, `tests/v5/`, `scripts/v5/`; every v5 claim in this paper was re-checked against it (v5 reconciliation log) | closed |

---

## 10. What to attack

Pass 3 answered or routed every pass-2 question (Pass 3 attack log), and pass 4 applied four audits (Pass 4 log). What remains for the next red team:

1. **Binding (O16).** If the owner picks a `bind` event, attack it: can a read observe a binding that no QueryRecord echoes? Does a rebind race a read in flight? Is a scope-widening `bind` correctly in the signed set?
2. **The eligibility predicate (G3-3).** Find a seal that passes the predicate yet folds a rolled-back generation's attention: roll-forward (O21), Expired spans, an erase that reseals, a periodic seal during a reseal. Does the two-rollback reopen fixture in V-HASHGATE cover every order of attest, crash and promote?
3. **Payload manifest and open cost.** Does trusting the manifest root by seal keep open O(tail) at 10k and 100k on Windows, against v5's 1.0 s? What does lazy verify-on-read miss that only V-PAYLOAD's audit catches, and how long can that gap last?
4. **Mixed embedders (O18, O25).** Construct a pool that mixes vectors from two embedders without any echo or pin disagreeing. Is the host-declared id enough?
5. **The probation echo (G3-2, V-MISATTR, O20).** Is V-MISATTR's ground truth computable without the host echo it replaces? Size the self-reinforcement of `g`'s recall during probation on the mile-2 world.
6. **Fresh base (G4-8).** Find a path where a promote rests on a verdict scored against a head that is no longer live, or where the compare-and-swap seq refuses a legitimate promote.
7. **Hold resources (O22, O23).** Pick each option the owner might rule and find the failure: auto-rollback against J6; a staging-only pass against V-HOLD; deposit refusal against X3.
8. **V-RETAIN's cost.** Refolding every prefix at audit is O(events × records) at worst. Is it affordable at 100k, and what is the incremental form?
9. **Slot winners (G2-9, O24).** Once O24 is ruled, check G2-7's byte-equality claim against the stored preference shape.
10. **Seams after pass 3.** The verifier is now a tripwire and the kernel fold ships with the referee. Argue that the referee itself should wait for a measured gate, or that the read-path binding can never pay for itself. Should the v7 scan be the existing `ScanIndex` extended, or a pure `scan()` in a `no_std` kernel wrapped by it (O32)?
11. **Native accelerators on `main`** (§6 "Built so far"). Does any path let `MONETA_NATIVE` or wheel presence (unjournaled ambient state, P1/O16) change a journaled or replayed answer: snapshot round-trip, permanent demotion on a non-finite vector, the per-query oracle fallback on a NaN cosine, `iter_query` under mutation? Is the overflow fix complete: does any other finite input give a NaN or a disordered cosine, and should a stored near-1e308 row, which now sends every later query through the oracle with no demotion and no log line, demote the index or return a reject tag? Is `rank_hits`' early stop sound with negative, NaN or subnormal utilities (`tests/unit/test_rank_early_stop.py`)? Does `decay_batch`'s platform-`exp` parity survive another OS or a wasm32 target (`test_native_decay_parity.py`, O31)? Arm P already meets 50 ms (26.6–29.1 ms p95): is admission on exactness alone (O27) sound, or should the v7 scan be numpy under a recorded contract-E downgrade? Does the 50 ms gate hold on a 2-vCPU container?
12. **v5 against v7** (v5 reconciliation pass). v5 resolves context scopes by strength, not intersection (G2); its slot preference is one id with a latest-claim fallback (O24); its cosines differ across interpreters (§6 Gaps); its time rule is a fold-side `max` (O7); its policy is host-held, not journaled (P1). Which should v7 adopt, and which must the v7 read path change before V-POOL and G3-5 can hold?

If a lock should go, say which one and why in a separate section, not inside the critique.

---

## Appendix: v1 and v6 references verified for this paper (`6cf05f5`; working tree for `api.py`, `ecs.py`, `vector_index.py`)

- **`src/moneta/decay.py`**
  - `:21` "explicitly provisional"
  - `:31` default of 6 h
  - `:34-35` bounds of 60 s – 24 h
  - `:48-69` `decay_value`
  - `:65` Δt computed
  - `:66-67` negative-Δt clamp
  - `:68` `math.exp`
  - `:69` floor
  - `:91-105` setter, which leaves only a log line
- **`src/moneta/api.py`** (working tree; lines up to `:405` are unchanged from `6cf05f5`)
  - `:328` `deposit`; `:331` the embedding parameter
  - `:379` `query`
  - `:399` `time.time()`
  - `:401` `decay_all` inside `query`
  - `:406` `iter_query` (6cf05f5 `:406-407`, over-fetch of the full index)
  - `:408` `rank_hits` (6cf05f5 `:414` clamp and `:415` stable sort, now in `ecs.py`)
  - `:413` `signal_attention(weights)` (6cf05f5 `:420`)
  - `:422` `time.time()` in `signal_attention`; `:423` iteration over the dict; `:425-429` in-memory and WAL append (6cf05f5 `:429-436`)
  - `:432` `get_consolidation_manifest` (6cf05f5 `:439`)
  - `:446-451` `run_sleep_pass`, "Not part of the agent-facing four-op API" (6cf05f5 `:453-458`)
- **`src/moneta/ecs.py`** (working tree)
  - `:39-42` optional `moneta_native` import
  - `:179-199` `hydrate_row` (6cf05f5 `:150-164`)
  - `:240-241` sum, then clamp once (6cf05f5 `:211-212`)
  - `:242` `attended_count += count` (6cf05f5 `:213`)
  - `:243` `_last_evaluated = now` (6cf05f5 `:214`)
  - `:251-272` `decay_all`, which writes in place; native branch `:257-263`, oracle loop `:264-272` (6cf05f5 `:222-236`)
  - `:331` `cos_sim * utility`, unclamped, in `top_k_by_similarity` `:290-333` (6cf05f5 `:295`)
  - `:335-381` `rank_hits`: early stop `:366-367`, clamp `:371`, stable sort `:380` (new)
- **`src/moneta/attention_log.py`**
  - `:64-68` GIL guard
  - `:73` entry fields
  - `:97-105` `aggregate`
  - `:108` `reduce_attention_log`
  - `:129-131` apply, then `decay_all`
- **`src/moneta/consolidation.py`**
  - `:53-55` thresholds of 0.1 and 3, "Locked Round 2"
  - `:111-112` prune key
  - `:166-169` prune = `ecs.remove` + `vector_index.delete`
- **`src/moneta/durability.py`**
  - `:25-26` "no checksums"
  - `:83` `snapshot_ecs`
  - `:119-125` WAL unlinked
- **`src/moneta/vector_index.py`** (working tree)
  - `:35-44` LanceDB declined as a runtime dependency (unchanged)
  - `:49-69` docstring "Native scan seam (D1)": fair-matrix figures; admission on "D1's other clause" (exactness), which this paper files under O27
  - `:83-86` optional `moneta_native` import; `:105-117` backend resolution (`MONETA_NATIVE`)
  - `:120-153` `_oracle_scan`: loop over items `:140`, left-to-right dot product `:145-147`, stable sort `:152` (6cf05f5 `:155-167`, `:160-162`, inside `query`)
  - `:156-160` `_all_finite`
  - `:206` native slot order equals the oracle's dict insertion order
  - `:269-283` upsert refusal → permanent demotion to the oracle
  - `:329-364` `query` (backend split; insertion order supplied at `:344-345`; non-finite query → oracle `:350-354`; NaN cosine `ArithmeticError` → oracle `:355-362`)
  - `:366-401` `iter_query` (single-writer rule `:375-376`; `ArithmeticError` → oracle `:389-395`)
- **`rust/moneta_native/src/lib.rs`** (untracked)
  - `:1-8` module doc ("admitted under decision D1")
  - `:28` `dot_seq`; `:46-91` `scan_topk` (NaN cosine → `NonExact` `:71-73`, total order `:76-84`); `:116` finiteness check; `:220-227` `ScanIndex.scan` (raises `ArithmeticError`)
  - `:236-253` `decay_column` (platform `exp` at `:250`, `if dt < 0.0` at `:247-249`); `:256-269` `decay_batch`
  - Rust tests `ties_break_by_row` `:284`, `overflow_to_nan_is_reported_not_sorted` `:302`, `topk_equals_full_sort_prefix` `:313`
- **`src/moneta/sequential_writer.py`**
  - `:104-105` `commit_staging`, "Authoring first, vector second"
- **`src/moneta/usd_target.py`**
  - `:47-48` continuations inserted at position 1
  - `:101` `cortex_protected.usda`
  - `:102` rotation cap of 50,000
  - `:225-226` protected sublayer at the strongest root position
  - `:252-259` the insert logic
- **`pyproject.toml`**
  - `:7` `1.2.0rc1`
  - `:37` `dependencies = []`
- **`ARCHITECTURE.md`**
  - `:46-50` §2.1 / Ruling B
  - `:82` λ runtime-configurable
  - `:84-90` exactly three evaluation points
  - `:108-112` §5.1
  - `:146` the vector index is authoritative
  - `:152` no 2PC
  - `:265-281` §15.2
- **`CLAUDE.md`** (working tree)
  - `:99` the Phase 3 dependency prose
  - `:136-157` "Optional native seams" (build, matrix, contract)
  - "Locked decisions — do not re-open" items 2–5
- **`BLUEPRINT_v6.md`**
  - `:111-117` tier table
  - `:41` decision D1
  - `:224` fold step wording
  - `:349` the seam-admission rule
  - `:353`, `:361`, `:366-367` the 50 ms gate, the 2-vCPU container, v5's 161 ms median and 1.0 s open
  - `:263` the 14-day example
  - `:417` no Moneta changes
  - `:467` E2
  - `:469` E4

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

| Term | Meaning here |
|---|---|
| seam | a boundary where Rust may replace Python: a pure function of bytes with a Python oracle (SM1–SM4) |
| oracle | the Python implementation that defines a seam's correct output, bit for bit |
| arm A–E, arm P | the mile-2 experiment arms (v6); arm P is D1's numpy scan |
| β | the `utility_exponent` alternative to the recall half-life (R2) |
| generation | one self-tier policy version, with a G4 state machine |
| probation | the {Promoted, Expired} span, during which retention is held (G4-4) |
| shadow | tuning that may propose but never move the pointer (G4-6) |
| referee | the pinned scorer (WASM, or a pinned Python fallback) that produces verdicts |
| seal / attest / reseal | a journaled running hash plus checkpoint hash / the owner's signature over a seal / a seal re-appended after a rollback |
| eligible checkpoint | a sealed checkpoint outside every rolled-back window, passing G3-3 |
| `signed_through_seq` | the seq of the latest attested seal |
| recall anchors | the recall fold's output `Anchor{u, t_last}` per record. Not the **tamper anchor** |
| tamper anchor | the external `(seq, hash)` of the latest attested seal (K2, G5-4) |
| held-out window, wear | the evaluation window kept from the tuner; wear counts `disclose` events (G5-5) |
| contract E, δ, ulp | the recorded fallback that tolerates δ units in the last place; `δ_t` is a time window |
| FTZ / DAZ, subnormal | flush-to-zero / denormals-are-zero FP modes; subnormals are the tiny floats they flush |
| fuel | WASM execution budget (J1) |
| `cdylib`, `no_std`, abi3, PyO3, maturin | Rust library kinds and the Python-binding toolchain used by `moneta_native` |
| hython | Houdini's Python, used here as the `pxr`-capable interpreter |
| SYNAPSE | the host that consumes Moneta's recall today |
| E1–E4 | the mile-0 Round 4 items (§8) |
| the line | the loop may only change what moving a pointer can undo |
| QueryRecord, Prefix | the host's logged query inputs; a journal prefix by `(seq, hash)` |
| LIVRPS | USD's composition strength order |
| `[M]` | measured by running, with machine, interpreter, date, script and result file |

## Review log

Every judge defect was checked against the sources before it was disposed of. JA is the first judge and JB the second (renamed in pass 4 from J1/J2, which collided with rules J1/J2). Duplicates are cross-referenced. One citation was corrected. No defect was refuted outright.

| # | Defect | Disposition | Where fixed |
|---|---|---|---|
| JA-1 / JB-4 | graph-first: "Open takes five steps" lists four | **fixed**: five steps, adding key/anchor read and the G4/`signed_through_seq` derivation. *Superseded: six steps after A26/A36, seven after pass 4* | §3 Open |
| JA-2 / JB-2 | `stronger_than` omits `const` and `rules` | **fixed; cited evidence corrected.** The order is now complete (C5 and the G2 tier table). JA cited "v6 §4 puts const strongest, then rules, then owner, then self". The v6 tier table (`BLUEPRINT_v6.md:111-117`) has no owner-context row and doesn't order strength. `rules` holds tuner settings (`:115`), so it never enters resolve. `const` contributes bounds, not values | G2 |
| JA-3 | "v1 already carries pxr and LanceDB" is false | **fixed** (`pyproject.toml:37`; `vector_index.py:35-44`; no `lancedb` import). The CLAUDE.md:99 / ARCHITECTURE.md:274 drift is noted | §6 "The cost to name" |
| JA-4 | mile 0 kill omits E4 and credits E2 with killing "the line" | **fixed**: E4 → the line (`BLUEPRINT_v6.md:469`); E2 → replay (`:467`) | §8 mile 0 |
| JA-5 / JB-18 (part) | fold oracle has no declared step order; v1 forgives decay | **fixed**: v1's order verified (`ecs.py:240-243`, `attention_log.py:129-131`); v7's order declared; a distinguishing fixture added | G3 "The fold"; V-ORACLE-FOLD; O7 |
| JA-6 | Withdrawn is not an edge | **fixed**: journaled unsigned `govern{why: withdraw}` with an **of** edge | G1, G4 |
| JA-7 / JB-9 | rust-seam: Proposed and Requested in unjournaled shadow records | **fixed**: `propose` is journaled; there is no Requested state; V-REPLAY reproduces journaled verdicts | G1, G4, V-REPLAY |
| JA-8 | contract E vs "identical top-k" | **fixed**: pass conditions read "identical except pairs within δ, ordered by the total order" wherever δ applies. *Pass 4: V-ORACLE-SCAN and V-POOL are now bit-exact by default; δ only under a recorded fallback* | V-ORACLE-SCAN, V-EXP |
| JA-9 / JB-8 | rust-seam tags `[V, v6 toy]` and `[V, decision D1 per v6]` | **fixed**: all such claims are `[A; v6: V]` or "D1 (given)" | Tags; §4; §6 |
| JA-10 / JB-12 / JB-5 | ID collisions (G-guarantees vs graphs, S-seams vs rules, rule D1 vs decision D1) | **fixed**: ID scheme in the header; Q1–Q10 (now Q1–Q12); SM1–SM4; no rule is named D | header; §4; §6 |
| JA-11 | Expired has no exit; "no govern through mile 4" vs mile 4 checks | **fixed**: Expired → adopt or rollback (signed); mile 4 runs the full cycle on test stores only | G4; §8 mile 4 |
| JA-12 / JB-10 / JB-17 (part) | erase under a per-event chain | **fixed**: payload commitment by digest (G1-6, T6, V-ERASE) | G1 |
| JA-13 | `durability.py:24-26`; `decay.py:65-67` vs `:66-67` | **fixed**: `:25-26` and `:66-67` (`:65` is the subtraction) | Appendix; §5 |
| JA-14 / JB-14 | mile-0-first's `gen` edge "when results were served" can't be computed | **fixed**: live at append; misattribution window named; echo as O14 under §9. *Superseded by A10: the stamp is captured at call time* | G4; Q7; pass-2 attack 3 |
| JA-15 | G1-4 byte equality mapped to V-UNDO | **fixed**: V-RESTORE compares spec bytes | §5 |
| JA-16 / JB-16 | V-WRITE lets the tuning pass append `promote` | **fixed**: only `propose` in every mode; the sabotage includes appending `promote` | §3; V-WRITE |
| JA-17 | `trust/` directory beside journaled pins | **fixed**: no `trust/`; pins are signed `govern{const, trust}` | §3; G5-1 |
| JA-18 / JB-13 | mile renumbering reinterprets R2 and R4 | **fixed**: v6/RULINGS numbering kept; mile 0 and mile 2 run in parallel | §8 |
| JA-19 | mile-0-first's `[V] on the v6 toy` rows; X3's precedent tag | **fixed**: `[A; v6: V on the toy]`; X3 is `[P]` with the precedent cited | §4 |
| JB-1 | G2-7 claims USD reproduces intersection | **fixed**: C3 restricted to value fields; authorization flattened into USD and never derived there; O3 | G2; V-C3 |
| JB-3 / JB-17 (part) | stale checkpoint after rollback | **fixed**: rollback reseals; V-HASHGATE gains "open from a pre-rollback checkpoint". *Superseded by A26/A36: V-HASHGATE now requires open from a pre-promote attested eligible seal to work* | G3-3; G4-5 |
| JB-6 | erase and revector added to R5's signed set silently | **fixed**: raised as O9 pending owner confirmation, with roll-forward | G1 table; O9 |
| JB-7 | contract E weakens D1's exact oracle | **fixed**: bit-exact by default through a ported shared `exp`; δ only as a measured, recorded fallback (scan excepted, for a stated reason). *Pass 4: scan exception retired by built fact; the built scan is bit-exact* | §6 Exactness |
| JB-11 / JB-17 (part) | no authorization-narrowing invariant | **fixed**: G2-5, C4, V-NARROW | G2 |
| JB-15 | mile-0-first G4-2 "every edge signed" vs its unsigned edges | **fixed**: G4-2 covers pointer-moving edges; unsigned edges move nothing (V-STATE) | G4 |
| JB-18 | `attended_count` not named in R4a's exclusion | **fixed**: G4-5, J8 and V-UNDO's sabotage name `attended_count` (`ecs.py:242`, `consolidation.py:112`) | G4-5; V-UNDO |

**Grafts applied** (from both judges' graft lists):
- total order and V-TIES
- canonical bytes and V-CHAIN's re-serialization sabotage
- the fold step-order hazard
- contract E as a fallback, plus V-EVAL3
- draft O14 (reseal) and V-HASHGATE
- recall bounds (draft C8 → G2-6, V-BOUNDS)
- the two score paths (V-ORACLE-SCAN)
- the mile 0 Round 4 table and its done-means
- the parallel experiment
- the "what main actually is" table
- the Expired state with signed exits
- the SYNAPSE `snapshot.json` feedback path (G3-2)
- the per-check mile column
- V-LEAK
- draft O13 (adapted: signatures inline on `govern`, `signed_through_seq` for seals)
- the mutation corpus
- V-IMPORTS
- the locks table

---

## Pass 3 attack log

The pass-2 red team ran eleven attacks (the ten in pass 2's §10 plus a lock audit). Every finding below survived two independent verdicts; none was refuted. **Note (pass 4):** 0 of 102 refuter votes refuted anything, so "survived two verdicts" is weak evidence of correctness; pass 4's fold-consistency audit re-checked the eight criticals (A1, A10, A20, A26, A29, A36, A38, A42) against the sources and found none wrong as applied, but found residue they left (Pass 4 log). Where a verdict corrected a finding's proposed fix, the corrected fix was applied. Dispositions: **applied** (edited in place), **owner** (a new O-item with a recommended default), **refuted** (none). Duplicates share one mechanism and are cross-referenced.

| # | Atk | Finding | Severity | Disposition | Reason |
|---|---|---|---|---|---|
| A1 | 1 | P1/P6 need context, scopes and t, but `query(embedding, limit)` carries none | critical | owner (O16) | binding mechanism is a design choice; P6 reworded to "clock sampled once at entry, echoed" (applied) |
| A2 | 1 | R4a exclusion at build time makes the eval set for prefix n depend on events after n | major | owner (O17) | `built_from` names `Prefix(h_build)`, excluded set has an "as of", V-POOL uses the same set (applied); confirmation goes with O6 |
| A3 | 1 | vector bytes and embedder identity have no home; G3-4 and replay after erase unsatisfiable | major | owner (O18) | vector made payload-class (A20, applied); erase-vs-replay and embedder pin need the owner |
| A4 | 1 | attention and deposit carry no timestamp, yet the fold needs t | minor | applied | event envelope `{seq, kind, t, prev}`; t non-decreasing by append-time clamp; backward-step fixture |
| A5 | 1 | V-POOL demands exact top-k against a δ-exact read path | minor | applied | V-POOL takes the δ clause; builder computes `cos` in left-to-right oracle order |
| A6 | 2 | a proposal scored during probation can be promoted after rollback | major | applied | `scored_against` edge, G4-8 fresh base, base seq in the signed promote body, withdraw on rollback/roll-forward |
| A7 | 2 | G3-2 names the wrong host path; the query → SYNAPSE top-5 echo is unnamed | major | applied | G3-2 lists four paths with bounds; recall effect during probation stated as live and unbounded; snapshot path tagged `[A]` |
| A8 | 2 | `snapshot.json` is SYNAPSE's restore artifact, so it may be written back into the store | major | owner (O19) | export-only default and V-NOFEEDBACK widened to open/restore applied; whether SYNAPSE needs restore is the owner's |
| A9 | 2 | the stamp and hold defer the host loop but don't bound it | minor | applied | "On one screen", G3-2 and the line reworded; steady-state loop named as pre-existing v1 behaviour, `[U]` |
| A10 | 3 | "live at append" isn't pinned to the `signal_attention` call | critical | applied | stamp captured in the call under the single writer, carried in the WAL, copied by the journal; V-GENTAG fixtures |
| A11 | 3 | on retention-ranked host paths, all probation attention is stamped g but not caused by g | major | owner (O20) | the G3-2 bound and the misattribution paragraph now name a whole-probation window (applied); any remedy narrows R4a, so owner |
| A12 | 3 | misattribution flips the prune key and no check sizes it | major | applied | V-MISATTR added and the bound stated per entity id; δ_t stamping rejected; mitigations listed under O14 |
| A13 | 3 | roll-forward isn't in G4; rollback of an Adopted generation excludes nothing | major | owner (O21) | narrowing J8 to RolledBack would reopen R4a; diagram and G4-1 point to O21 |
| A14 | 3 | one pending bounds concurrency, not duration; Expired's excluded mass is unbounded | major | owner (O22) | merged with A29; cost stated in G4-4/G4-7 (applied) |
| A15 | 3 | recall-fold text skips excluded attention, contradicting O6's default | minor | applied | `excluded_gens` is caller-supplied, empty for live recall under O6's default; V-EXCL scoped |
| A16 | 4 | a slot selection is resolved as a value but must obey authorization | major | owner (O24) | filter-then-choose grounded in v6:95 and G2-9 added (applied); slot shape and empty-slot fallback are v5 semantics |
| A17 | 4 | a slot outcome depends on caller scopes, so it can't be a field of `Resolved(c, n)` | major | applied | `Resolved` holds preferences only; winner is a read-time step under P1; G2-7 restricted; V-REPLAY gains the two-caller case |
| A18 | 4 | G2-4 calls slot selections authorization, contradicting the value classification | minor | applied | G2-4 retitled; denylist holds whatever the open list contains; V-SELF sabotage extended |
| A19 | 4 | the retention half-life is a policy field with no category | minor | applied | G2-10: global `const` retention λ, amended only by signed `amend`; thresholds stay locked Round 2 pins; "owner's λ" replaced |
| A20 | 5 | vectors have no authoritative home | critical | applied | vector is payload-class, committed, rebuilt only from committed bytes; V-LEAF sabotage extended |
| A21 | 5 | content-addressed unsalted payload files: erase destroys a twin, the digest confirms guesses | major | applied | per-record files `payloads/<record_id>`, salted commitments with a domain tag; V-ERASE twin and oracle cases |
| A22 | 5 | G1-6 is checked nowhere; the vector leaf forces an O(N) open | major | applied | V-PAYLOAD; payload-manifest root and vector-index hash in the sealed checkpoint; open-time gate in O13 |
| A23 | 5 | payload files bring back the two-store write E1 claims to retire | major | applied | journal = existence/order/commitments, `payloads/` = bytes; write and erase order; `payload_missing`; §7 reworded |
| A24 | 5 | revector and erase break replay and the byte-identical rebuild | major | owner (O25) | G3-5 exception applied; keep-or-drop old vectors is the owner's |
| A25 | 5 | erase leaves the content in retained derived leaves | major | applied | G3-9: erase invalidates content-bearing leaves transitively by `built_from`; V-ERASE by audit plus decoded spot check |
| A26 | 6 | nested rollback: a crash or missing attestation makes a poisoned checkpoint the rebuild base | critical | applied | eligibility predicate over every RolledBack window, used in G3-3, G4-5, Open and periodic seals; two-rollback fixture |
| A27 | 6 | G3-3 and V-HASHGATE forbid the checkpoint G4-5 and Open require; no checkpoint legal after a crash | major | applied | same predicate (A26); Open step 3 re-appends a missing reseal before any retention event |
| A28 | 6 | a stale `snapshot.json` after rollback drives attention the fold never excludes | minor | applied | export records its seal; deleted before rollback and rebuilt at open (Open step 6) |
| A29 | 7 | O5's default ceiling bounds nothing; v6's memory-growth cost was dropped | critical | owner (O22) | cost restored in G4-4/G4-7 (applied); any bound or auto-action is an O5-class owner choice |
| A30 | 7 | releasing the hold drains the backlog in one pass, breaking §15.2 #2/#3 | major | applied | G3-8 multi-pass drain; V-ENVELOPE; V-UNDO compares the whole drain |
| A31 | 7 | `adopt` rests on no evidence; the loop finishes only by signature or timeout | major | owner (O26) | adopt stated as the owner's responsibility-transfer act (applied); evidence edge and minimum probation are owner choices |
| A32 | 7 | a proposal scored against a Promoted head is promoted after that head is rolled back | major | applied | duplicate of A6; same mechanism |
| A33 | 8 | V-POOL demands exact equality against a δ-exact read path | major | applied | duplicate of A5; also the read path "must" call the Python `exp` port |
| A34 | 8 | "identical f64 bits" fails on non-finite results | major | applied | G1-8 codec refuses non-finite; Q12 reject tag; V-FINITE; `dt.max(0.0)` sabotage in V-ORACLE-FOLD |
| A35 | 8 | the subnormal band is reachable and the FP environment is an undeclared input | minor | applied | Q11, V-FPENV probe; subnormal and underflow fixtures in V-EXP (65,000 s for underflow, corrected from the finding's 64,000 s) |
| A36 | 9 | Open's offline fallback picks a checkpoint holding an earlier rolled-back generation's attention; verify takes the start seal as input | critical | applied | duplicate of A26; the verifier now chooses `start_seq` and reports it in `Verdict` |
| A37 | 9 | nothing checks the excluded set or retention events after the first post-rollback pass | major | applied | `Verdict.rolled_back_gens` is the only source; V-RETAIN at audit; V-UNDO over two passes and a reopen |
| A38 | 10 | `fold_recall` is labelled conditional, but the always-built WASM referee needs it | critical | applied | the kernel fold ships with the referee; V-ORACLE-FOLD moved to mile 4; the conditional part is the `moneta-py` binding; the β branch says what replaces the `EvalBuf` |
| A39 | 10 | "read path calls the kernel exp" puts native Rust on `api.query` unconditionally | major | applied | the read path calls the Python port; "shared exp" removed from the fold's Buys; the **v7** read path imports no native code except through a gated seam (pass 4: on `main`, two v1-line accelerators are reachable from `api.query`, §6) |
| A40 | 10 | the verifier is justified by speed, but G4-1 depends on it; its gates measure undefined quantities | major | applied | G4-1 enforced by the state table and V-STATE; verifier kept as a tripwire; gates on N, K, S and R × A; checkpoint-bytes check moved out of the seam |
| A41 | 10 | D1's literal text grants Rust only to the scan | major | owner (O27) | D1 quoted verbatim and confined to SM4/scan; the seam rule relabelled `[A; v6]` (applied); its standing is the owner's |
| A42 | 11 | V-BOUNDS makes conformance to the locked λ range a failing sabotage | critical | owner (O28) | sabotage recast to "hard-coded outside the journal" and X1 envelope = the :82 range until ruled (applied); whether :82 binds the recall λ is Round 4 |
| A43 | 11 | an agent read needs context and scopes, but the locked query carries neither | major | owner (O16) | duplicate of A1; deposit scope added to O16 |
| A44 | 11 | the open fallback loads exactly the checkpoint G3-3 and V-HASHGATE forbid | major | applied | duplicate of A27; the predicate includes the Expired span |
| A45 | 11 | G4 omits roll-forward, and **of** omits promote and roll-forward, so signature replay works | major | applied | `of: promote → propose`; compare-and-swap live-head seq in every signed self body; V-STATE replay sabotages. Roll-forward's diagram placement waits on O21 |
| A46 | 11 | the per-event retention fold decays outside the locked three points, yet G2-8 is `[V]` | major | owner (O29) | G2-8 split into v1 `[V]` and v7 `[P]`; V-EVAL3 retention arm conditional on the ruling (applied); lock 2 is Round 4 |
| A47 | 11 | if E3 is rejected, ruled R4a has no carrier | major | owner (O30) | E3's against-branch and the kill list updated (applied); the Round 4 brief must say R4a depends on E3 or a §5.1 amendment |
| A48 | 11 | J7's indefinite hold suspends the locked §6 `MAX_ENTITIES` trigger | major | owner (O23) | added to the locks table and mile-0 questions, alarm in G4-4/V-HOLD (applied); what else happens is the owner's. `should_run` verified never called from `src/moneta/` |
| A49 | 11 | G3-8 claims §15.2 is kept but has no check and omits #4 | minor | applied | V-ENVELOPE; #4 given an explicit disposition (superseded with E1, Round 4), no invented budget |
| A50 | 11 | adopt is both "pointer-moving" and "moves nothing"; the loop can cause more than one node kind | minor | applied | "moves" defined as the policy pointer; G4-2 renamed; the line restated with the substrate's withdraw; refusal-instead-of-withdraw noted, not adopted |
| A51 | 11 | mile-3 checks depend on artifacts that only exist at mile 4 | minor | applied | V-REBUILD, V-REPLAY and V-SHADOW split 3 / 4; the mile-3 V-REPLAY arm uses verdict leaves, not unjournaled shadow records |

---

## Pass 4 log

Four audits were checked against the sources (the working tree, `rust/moneta_native`, `results/*.jsonl`, `BLUEPRINT_v6.md`, `RULINGS.md`, the brief) before each disposition. Where audits disagreed on a line number, the line read in the working tree wins. Where two audits proposed the same O-number, numbers were allocated once: O31 `exp`, O32 crate role, O33 X1 values, O34 bootstrap unit, O35 v5 bundle. Items outside this file (code docstrings, `CLAUDE.md`) are routed to the Documentarian, not edited.

| Audit | Item | Finding | Disposition | Reason |
|---|---|---|---|---|
| citations | Cit-1 | `api.py:414` clamp → `ecs.py:371` (in `rank_hits`), call site `api.py:408` | applied | G3-2 path 1 and the `moneta-scan` row; checked against the working tree |
| citations | Cit-2 | `api.py:415` stable sort → `ecs.py:380` | applied | §1 row 9, Q1 |
| citations | Cit-3 | `vector_index.py:155,167` → `:132,144`, insertion order `:336-337`, slot order `:198` | applied | §1 row 9, Q1, Built so far; `:328` docstring not cited (adds nothing) |
| citations | Cit-4 | "No second implementation can match" is false; cite `scan_topk`, `ties_break_by_row`, conformance tests | applied | reworded to "matched only by reproducing the implicit row/insertion key" |
| citations | Cit-5 | `moneta-scan` row stale (absent, `:406-407`, `:155-167`) | applied | row rewritten: `iter_query` + `rank_hits` with exact early stop; native seam; evidence; machine caveat |
| citations | Cit-6 | "`api.query` imports no native code"; Q5 `exp` only at `decay.py:68` | applied | §6 consequence 1 names two `exp` sites (`decay.py:68`, `lib.rs:233`); Q5 cell; parity tests cited |
| citations | Cit-7 | `ecs.py:295` → `:331` | applied | V-ORACLE-SCAN, scan row |
| citations | Cit-8 | `ecs.py:222-236` → `:251-272` | applied | E2 row, Q4 (split native `:257-263` / oracle `:264-272`) |
| citations | Cit-9 | `ecs.py:211-212`/`211-214` → `:240-241`/`:240-243` | applied | G3 fold, O7, review log |
| citations | Cit-10 | `ecs.py:213` → `:242` | applied | 4 sites |
| citations | Cit-11 | `ecs.py:214` → `:243` | applied | 2 sites plus the G3 fold list |
| citations | Cit-12 | `ecs.py:150-164` → `:179-199` | applied | O19 |
| citations | Cit-13 | `vector_index.py:160-162` → `:137-139`; `dot_seq` as the existing port; arm-P evidence | applied | G3-5, §6 consequence 2 |
| citations | Cit-14 | `api.py:420` → `:413` | applied | G4 stamp paragraph |
| citations | Cit-15 | `api.py:429-431` → `:422-424`; P6 `:429` → `:422` | applied | envelope, P6 |
| citations | Cit-16 | `api.py:431` → `:413`, `:423` | applied | misattribution paragraph |
| citations | Cit-17 | `api.py:432-436` → `:425-429` | applied | G4 stamp paragraph |
| citations | Cit-18 | `api.py:434-436` → `:427-429` | applied | Q7 |
| citations | Cit-19 | `api.py:453-458` → `:446-451` | applied | On one screen, X3 |
| citations | Cit-20 | `api.py:330` → `:331` (wrong at HEAD too) | applied | O18 |
| citations | Cit-21 | `fold_recall` row lacks the native precedent | applied | oracle cell names `lib.rs:226-252` and the parity test, and says it is not the fold |
| citations | Cit-22 | cost to name omits optional `moneta_native`; cite `CLAUDE.md:136-157` | applied | §6 cost to name |
| built-seams | Blt-1 | no tag for measured facts; baseline ignores the working tree | applied | `[M]` added; Baseline names the working tree. The task's "[V] tags" for the built section are realized as `[M]`, because `[V]` means "nothing run" |
| built-seams | Blt-2 | `api.query` reaches native code; decay kernel under no v7 gate | applied | §6 consequence 1, On one screen, A39 reason |
| built-seams | Blt-3 | scan δ-by-default premise gone (arm P missed, built scan exact) | applied | consequence 2, Q5, V-POOL, V-ORACLE-SCAN; JA-8, JB-7 annotated |
| built-seams | Blt-4 | scan seam described as unbuilt; built seam ≠ v7 seam | applied | SM4, scan row, workspace, mile 4b, §10 item 10 |
| built-seams | Blt-5 | decay kernel uses platform `exp`, opposite of Q5; no FP probe; NaN same-runtime | applied | Exactness paragraph, Q11 cell, O31 |
| built-seams | Blt-6 | decay kernel is not `fold_recall` | applied | fold row, V-ORACLE-FOLD sabotage, workspace, E2 row |
| built-seams | Blt-7 | gate machine never stated; arm P definition; n = 2000; RSS meaning | applied | D1 measured table and machine paragraph; mile 0 #3; O13 |
| built-seams | Blt-8 | crate plan ignores `rust/moneta_native`; proposed O31 | applied | Built so far; numbered **O32** (O31 is the `exp` decision); cost to name |
| built-seams | Blt-9 | G3-5 "never via BLAS" now measured | applied | G3-5 |
| built-seams | Blt-10 | native ties = v1 fidelity, not P5 | applied | §1 row 9, Q1 |
| built-seams | Blt-11 | working-tree drift: keep 6cf05f5 inline, add appendix | applied | variant: inline cites re-anchored to the working tree (valid once committed unchanged), appendix maps every moved 6cf05f5 line |
| built-seams | Blt-12 | Status and loop position; built-fact log | applied | header; the built-fact log is this table |
| built-seams | Blt-13 | red team not pointed at new facts; 0/102 refuter note | applied | §10 item 11; Pass 3 log preamble |
| fold-consistency | Fold-1 | one `exp` for retention/read path; mark Q5 "violated" | applied | O31 added. "Violated" skipped: Q5 is a v7 guarantee not yet in force; the cell names both `exp` sites instead |
| fold-consistency | Fold-2 | header, baseline, stale cites | applied | header; Cit-1–22 |
| fold-consistency | Fold-3 | decay seam on `api.query` passed no defined gate; workspace mismatch | applied | Built so far table and O27 live instance; no separate crate-table row (recorded once, in Built so far) |
| fold-consistency | Fold-4 | D1 tripped; built seam differs; V-ORACLE-SCAN sabotage flags the design | applied | scan row, V-ORACLE-SCAN (rerank checked separately), P5 migration line in Q1; 4b kept as the promotion step |
| fold-consistency | Fold-5 | built scan is a handle (SM1) | applied | recorded as non-conformant in Built so far; SM1 not amended; refactor question is O32 |
| fold-consistency | Fold-6 | code docstrings and CLAUDE.md file decay/exactness under D1 | applied | blueprint states the seam rule (O27); docstring and CLAUDE.md wording routed to the Documentarian (outside this pass's edit scope) |
| fold-consistency | Fold-7 | gate mixes median and p95, machines, whole-query vs scan | applied | SM4 restated; 161 ms labelled median; machine paragraph; worst-case distribution named. Figures tagged `[M]`, not `[V]` |
| fold-consistency | Fold-8 | G3-3's second clause not an edge | applied | the seal body carries the RolledBack set; harness checks `built_from` against it |
| fold-consistency | Fold-9 | open can't be O(tail); steps out of order | applied | seal carries the RolledBack set and live G4 states, recomputed by Audit and checked by V-SEAL; Open reordered to seven steps, verifier first |
| fold-consistency | Fold-10 | drain-time `t` under E3-against | applied | variant: body `t_call` used by the folds (not a call-time envelope `t`, which the monotone clamp would override); V-GENTAG fixture |
| fold-consistency | Fold-11 | single writer vs locked lock-free §5.1 under E3-against | applied | G4 stamp bullet and O30 |
| fold-consistency | Fold-12 | V-REPLAY two-caller clause vacuous under O16(a) | applied | made conditional on O16(b) or a scoped harness read |
| fold-consistency | Fold-13 | P6 echo vs clamped `t`; no check | applied | P6 reworded; V-CLOCK added |
| fold-consistency | Fold-14 | O28 default contradicts applied text | applied | split into interim (applied) and proposal to Round 4 |
| fold-consistency | Fold-15 | roll-forward treated as signed by R4b | applied | "signed, pending O9" in G1 table, G4-2, V-SIGSET |
| fold-consistency | Fold-16 | δ, E, gate letters collide | applied | δ_t for the time window; ID table gains E, A, JA/JB, arms, δ and a local-variable rule. Renaming the gate letters skipped: the ID-table rule disambiguates at lower risk |
| fold-consistency | Fold-17 | historical IDs in normative text | applied | review-log JA-7, draft-RS O13, draft O13/O14/C8, pass-2 attack n |
| fold-consistency | Fold-18 | invariants and rules without checks | applied | V-PIN/V-VIEW → G5-3; V-TRIPWIRE (J5), V-QUERYSIG (X3), V-CLOCK (P6); V-BOUNDS threshold sabotage. Skipped: dedicated J2/T2 checks and V-BACKWARD edge typing (need design, not cheap) |
| fold-consistency | Fold-19 | G1-2 ill-typed for leaf/file edges | applied | restricted to event-to-event edges |
| fold-consistency | Fold-20 | O25 revector orphan section | applied | write order in O25; V-PAYLOAD crash fixture |
| fold-consistency | Fold-21 | reseal base may be unattested | applied | reseal base must be attested, same predicate as open |
| fold-consistency | Fold-22 | "exactly one node kind"; G4 row omits Proposed bound | applied | the line and On one screen |
| fold-consistency | Fold-23 | V-MISATTR green undefined; 4b not v6 | applied | measurement rows defined; 4b noted as v7 sub-mile |
| fold-consistency | Fold-24 | review-log rows superseded; pass-3 intro | applied | JA-1, JA-10, JA-14, JB-3 annotated; 0/102 note |
| fold-consistency | Fold-25 | no migration path into format 7 | applied | "Migration into format 7" `[P]` in G1; R5 restated literally in §1 row 1; mile 0 #3 |
| fold-consistency | Fold-26 | hython 21.0.773 tagged `[A]` though measured | applied | re-measured this pass on 21.0.773 and Python 3.14 (main thread) → `[M]`; CLAUDE.md's 21.0.512 routed to the Documentarian |
| fold-consistency | Fold-27 | vector encoding refuses only NaN | applied | ±inf refused, -0.0 canonicalized; V-FINITE deposit fixture |
| completeness | Comp-1 | D1 fired; crate built; scan out of 4b | applied | SM4, scan row, Built so far; 4b reworded to promotion rather than removed |
| completeness | Comp-2 | two `exp` contracts; owner decision | applied | Exactness paragraph; O31 |
| completeness | Comp-3 | V-ORACLE-SCAN bit-exact | applied | V-ORACLE-SCAN, V-POOL |
| completeness | Comp-4 | seam boundary moved to `rank_hits` | applied | scan row and Built so far; Q4 benefit stated |
| completeness | Comp-5 | O27 live instance; decay-only bench | applied | O27 text; the bench itself is not run (edit-only pass), decay-only cost stays `[U]` |
| completeness | Comp-6 | stale header and §6 claims | applied | header, consequence 1, workspace |
| completeness | Comp-7 | drift appendix; P5 changes the conformance contract | applied | Appendix mapping; Q1 line |
| completeness | Comp-8 | `[M]` tag | applied | Tags |
| completeness | Comp-9 | Built seams subsection | applied | §6 "Built so far (v1 line, 2026-10-15)" |
| completeness | Comp-10 | V-FPENV gap; correct the hython version | applied | gap recorded in V-FPENV, Q11, Built so far. Version "correction" skipped: 21.0.773 is installed and was measured; CLAUDE.md's 21.0.512 is the stale one |
| completeness | Comp-11 | gate protocol | applied | O13 protocol `[P]` |
| completeness | Comp-12 | `[U]` claims with no owner; X1 values and bootstrap unit | applied | O33, O34; `:327` routed to V-MISATTR; `:610` sits beside V-EXP |
| completeness | Comp-13 | O-table defaults and deciders; decision queue | applied | O1, O4, O10, O11, O12, O13, O15 defaults/deciders; deadlines; queue at the top of §9 |
| completeness | Comp-14 | mile 0 hidden v5 prerequisite; brief path | applied | step 0, O35, `docs/rounds/round-4-brief.md`, arm P on v5 facade |
| completeness | Comp-15 | kills without numeric triggers | applied | `[P]` triggers on miles 2, 3, 5, 6; mile 1 adds pass 4 and review record |
| completeness | Comp-16 | glossary; anchor, δ, judge collisions | applied | glossary; JA/JB; δ_t. Renaming "anchor" skipped: the glossary separates recall anchors from the tamper anchor without touching normative lines |
| completeness | Comp-17 | no sea-level summary | applied | "Read this first" (8 lines) under the title |
| completeness | Comp-18 | cost to name: first optional native component | applied | §6 cost to name; Built so far packaging gap; O11 |
| completeness | Comp-19 | attack list misses built seams | applied | §10 item 11 |
| completeness | Comp-20 | move ~40% into appendices | skipped | not cheap; would move every anchor this pass re-cited. Deferred to a later editorial pass |
| final review | F-1 | "D1's gate has fired" is false: the 109 ms arm P predates the early-stop rerank | applied | Read this first, Status, Rust list (incl. "Only the scan rests on D1"), On `main`, SM4, §6 opener, `moneta-scan` row, Built so far preamble and scan row, consequence 2, Sequencing, mile 4b, O27 rewritten to: D1's latency gate did **not** fire (fair matrix: arm P 26.6–29.1 ms p95); the native scan is admitted on the seam rule's exactness clause (O27) plus zero runtime dependencies. Repo docs call it "D1's exactness clause"; this paper keeps D1 verbatim and files it under O27. Supersedes Comp-1, Fold-4 and Blt-4 on this point |
| final review | F-1a | D1 table compared arm P without early stop against native with it | applied | table restated from `results/bench_query_fair_matrix.jsonl` (N = 200, 2 runs, fresh and aged, same `rank_hits` for every arm); 109 ms and 15.4 ms kept only as labelled superseded history; early stop named as the dominant win; native's marginal gain stated as 4–9× at p95 (4.1–8.8× with native decay, 3.3–6.1× scan alone); machine paragraph flipped from "robust miss" to "likely pass, less robust" |
| final review | F-1b | decay-only cost `[U]` | applied | bounded by the fair matrix at about 1–1.5 ms p95; Built so far decay row and O27 updated. Supersedes Comp-5's `[U]` |
| final review | F-2 | exactness envelope hole: finite components near 1e308 give NaN cosines; NaN → `Equal` was not a total order and could panic | applied (code fixed outside this file) | envelope now "finite and non-overflowing": `scan_topk` returns `NonExact`, `ScanIndex.scan` raises `ArithmeticError`, `query`/`iter_query` answer that query with the oracle; Rust test and two conformance tests named `[M]`. Read this first, On `main`, consequence 2, scan row, Q12 row, Gaps list (new Overflow item, residual latency cliff), §10 item 11 |
| final review | F-2a | working-tree anchors moved by the overflow fix (`vector_index.py`, `lib.rs`, 18:08–18:15) | applied | every `vector_index.py` and `lib.rs` anchor re-read and re-cited (§1 row 9, G3-5, V-ORACLE-FOLD, V-ORACLE-SCAN, Exactness, consequences 1–2, crate table, Built so far, Gaps, Q1, Q5, Q12, cost to name, O31, Appendix); conformance count now 32 tests from 20 functions. `ecs.py` and `api.py` unchanged since 17:27 |
| final review | F-3 | citation anchors: `ARCHITECTURE.md:36-37`, `BLUEPRINT_v6.md:114, :118`, `consolidation.py:54-55` | partly applied | verified by `grep -n`: `ARCHITECTURE.md:36` is `deposit` and `:37` is `query`, so `36-37` is correct for "deposit and query" (left unchanged, two places). `BLUEPRINT_v6.md:118` is blank → `:119` ("Retention stays the owner's … retention half-life"). `consolidation.py:55` is `PRUNE_ATTENDED_THRESHOLD = 3` (`:54` is the 0.1 utility threshold) → tightened to `:55` |
| final review | F-4 | Baseline incomplete; "three files" vs four | applied | Baseline lists all 6 modified files and every untracked file of this work; the two stray root files (`attention_log.py`, byte-identical to `src/moneta/attention_log.py`, and `test_attention_log_gil_guard.py`) named as excluded; Tags `[V]` now points to "the working-tree files named in Baseline"; Next action (1) names what to leave out |
| final review | F-5 | gate protocol caveat lived only in O13 | applied | D1 table carries a Protocol column (N, runs, fresh/aged, workstation not reference container) inline; machine paragraph notes O13's protocol is met except the reference machine |
| final review | F-6 | stale counts after the fix | applied | test matrix 211 → 215 in 4 configs; without the wheel 167 + 33 skips (`CLAUDE.md:155`); hython named as 21.0.773; the Exactness paragraph's "CLAUDE.md names 21.0.512" note updated, since `CLAUDE.md:130` now names 21.0.773 |

---

## v5 reconciliation log (after pass 4)

v5 was merged beside v1 (`861bed9`) and Round 4 was ruled (`RULINGS.md:48-101`) after pass 4. This pass re-checked every v5-dependent claim against v5 at `57a90bc` (code and tests read; `tests/v5` run; `results/bench_v5_recall_native.jsonl` and `results/bench_query_fair_matrix.jsonl` read row by row) and applied the rulings. Each change, with old and new text and its evidence, is listed in `CHANGES.md`, delivered beside this revision. The review and pass logs above are unchanged.

- **Upgraded** `[A; v6: V]` / `[A]` → `[V]` or `[M]` where the v5 code, tests or results confirm the claim: event bodies (`revector`, `consolidate`, `note`), the single write path (G1-5, L3), filter-then-choose slots, the 60-spec resolver test (G2-7, C3), the per-event attention order, the journal framing (Q2), I1–I8, v5's recall and open figures.
- **Corrected** where the code contradicts the paper: parent-to-child scope narrowing is not v5's rule (G2, C4); the slot preference is one id with a latest-claim fallback (O24); v5's policy is not journaled (P1); `compact()` edits the journal (T1); λ changes may apply forward, not only reinterpret (G2-10); the seam rule's wording is v6's, not v5's (§6).
- **Answered:** O35 (found), O24 (code), O19 (substrate side), O1 and O27 (ruled), O2 and O29 (in substance, by E2's wording).
- **Round 4 status:** filled from the implementation pass at `ba52ca7` (§8 mile 0 table). Met: E1-1, E1-B1 (one miss), E1-B3, E1-B4, E1-B6, E3-2, E3-3, E4-1, E4-4, HL-1, HL-2. Partly met: E3-1. Open: E1-B2, E1-B5, E1-P1–P3, E3-B1–B4, E4-2. Closure is the owner's call on the measured numbers.
- **Numbers:** v5 recall p95 184–194 ms (oracle) → 18.8–19.8 ms (native dot seam); the open-RSS drop 312 → 194 MB is the `array('d')` change, not the seam; v1's fair matrix re-read unchanged (227–313 ms → 3.1–6.7 ms p95, ~185 → ~69 MB).
