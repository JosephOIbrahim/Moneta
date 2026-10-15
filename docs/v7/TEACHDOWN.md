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

*(Written after Fable's final verdict on the paper. See below.)*
