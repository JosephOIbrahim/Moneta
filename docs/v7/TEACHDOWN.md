# Sea level: what this session built, and how to run it

*Two things came out of this session: **code you can run today**, and **a paper that decides what v7 is**. They're separate, and this page covers both.*

---

## Part 1 · The native seams (code, on `main`'s working tree)

### What we built

Every Moneta query used to do two slow things in pure Python:

- **The scan:** compare the query against every stored memory, a cosine similarity per memory.
- **The decay pass:** fade every memory's utility with time.

Both now have an **optional Rust version**, packaged as a *wheel* (a pre-built Python package) called `moneta_native`. A Rust version is only allowed in if it returns *the exact same bits* as the Python code. The Python code is the **oracle**, the reference the Rust is checked against.

One more change is plain Python. The query used to build a full `Memory` object for *every* stored memory just to return the top 5. Now it ranks first, builds only the winners, and stops early once nothing further down the list could still win. Nothing about the result changes.

**The numbers** (10k memories × 384 dimensions, this workstation):

| | p95 latency | memory |
|---|---|---|
| before | ~300 ms | 185 MB |
| numpy (the cheap alternative) | ~28 ms, and **not** bit-exact | 184 MB |
| **now** | **3–7 ms**, bit-exact | **69 MB** |

### How to run it

1. **Build the wheel:** `cd rust/moneta_native && maturin build --release -o dist`. This compiles the Rust into one file that works for Python 3.11 and up, so it covers Houdini 21's hython too.
2. **Install it:** `pip install --force-reinstall dist/moneta_native-0.1.0-cp311-abi3-win_amd64.whl`. From then on, Moneta uses it automatically.
3. **Test:** `MONETA_NATIVE=1 python -m pytest tests -q`, then the same with `=0`. The second run forces the Python path. Both must say `215 passed`.
4. **Measure:** `PYTHONPATH=src python scripts/bench_query.py --n 10000`. It prints latency and memory as JSON.

### What you'll see

- `215 passed` in each test run.
- A bench line with `"backend": "native"` and `p95_ms` around 3.

### When it breaks

- **`moneta_native` is not installed:** nothing breaks. Moneta runs the Python path, just slower.
- **A conformance test goes red:** the Rust is wrong. Revert the Rust change; never loosen the test.
- **The log says `demoted to python backend`:** a NaN, ∞ or non-numeric vector came in. Answers stay exact, but that index stays on the slow path, so fix the embedding upstream.

### Where it lives

| What | Where |
|---|---|
| Rust kernels | `rust/moneta_native/src/lib.rs` |
| Python oracles and switch | `src/moneta/vector_index.py` (`_oracle_scan`), `src/moneta/ecs.py` (`decay_all`, `rank_hits`) |
| The contract | `tests/unit/test_native_scan_conformance.py`, `test_native_decay_parity.py`, `test_rank_early_stop.py` |
| Numbers | `results/bench_query_fair_matrix.jsonl` |
| One-page commands | `docs/OPERATOR_CARD_native.md` |

**Safe to touch:** the bench scripts and the docs. **Touch with care:** `lib.rs`, and only with the conformance suite green afterwards. **Don't touch:** `_oracle_scan` and `decay_value`. They are the reference everything else is checked against.

---

## Part 2 · The v7 paper

### What we built

`docs/v7/BLUEPRINT_v7.md` is a **design**, not code. Nothing in v7 is built yet; the native seams above are v1-line work.

v6 proposed a *governed loop*: a tuner that improves **how** Moneta recalls, never **what** it remembers. Every change it makes has to be reversible, judged by something it can't touch, and re-derivable from the journal. v7 rebuilds that loop as **five typed graphs**. A *typed graph* has named kinds of nodes and edges, and rules (*invariants*) that must always hold. Every invariant has a check, and every check has a deliberate *sabotage* it must catch, which proves the check isn't asleep.

| Graph | What it holds |
|---|---|
| **Journal** | Every event, chained by hash. History is append-only, and the present is a pointer into it. |
| **Policy derivation** | How a context's policy resolves. Owner values beat the loop's, and scopes only ever narrow. |
| **Artifacts** | USD layers, eval sets and checkpoints. All are derived from the journal and never feed back into it. |
| **Generation lifecycle** | `Proposed → Promoted → Adopted / RolledBack`. Each move is a signed event. |
| **Authority** | Your key, what it signs, and the external anchor that catches truncation. |

### How to run it (as the owner)

1. **Read the top of the paper**, "Read this first": seven lines covering where things stand.
2. **Open the decision queue at the top of §9.** It's ordered by when each decision is needed, and every row has a default. Leaving a row alone accepts its default.
3. **Decide the "Now" row.** That's O35, the missing v5 code: recover it from the cloud session where v5 was built, or rule that mile 0 proceeds on v1 alone.
4. **Next actions:** the Architect drafts the Round 4 brief (`docs/rounds/round-4-brief.md`), and mile 2 starts. Mile 2 is the Python-only experiment that can kill or confirm R2 and R3.

### What you'll see

The paper uses status tags on every claim:

- `[V]` verified in code
- `[M]` measured
- `[P]` proposed
- `[A]` assumed
- `[U]` unknown

A healthy paper keeps `[A]` and `[U]` visible instead of hiding them.

### When it breaks

- **Round 4 rejects E2 (reads never write) or E4 (prune is a tombstone).** v7 stops; the paper names this as its top risk.
- **Mile 2 shows owner labels can't move the needle.** R3 flips to `mixed`, or v7 rescopes, using the flip conditions written in `RULINGS.md`.
- **The paper drifts from the code.** Pass 4 re-anchored every citation; re-run that audit after any `src/` change.

### Where it lives

| File | What it is |
|---|---|
| `docs/v7/BLUEPRINT_v7.md` | the paper |
| `docs/v7/RULINGS.md` | your rulings: R1–R5, O27, and the O35 search |
| `docs/v7/pass1_rulings_brief.md` | the evidence behind them |
| `docs/v7/jev/` | the Jev runs: every request and response, plus the scripts |
| `docs/v7/pass*_*.json` | the loop's records: advocates, judges, 51 attack findings, audits, Fable's verdicts |
