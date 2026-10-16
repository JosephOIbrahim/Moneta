# Operator's Card · Moneta native seams

**What it is:** an optional Rust wheel, `moneta_native`, that runs Moneta's two hottest loops (the cosine scan and the decay pass) in Rust. It is about 35–70× faster at p95 than pure Python and 4–9× faster than numpy, and it returns the *same bits* as the Python code, which numpy can't.

**Golden rule:** Python is the oracle. If a conformance test goes red, the Rust is wrong, never the test.

---

### Build

```
cd rust/moneta_native
cargo test --release
maturin build --release -o dist
pip install --force-reinstall dist/moneta_native-0.1.0-cp311-abi3-win_amd64.whl
```

*If `cargo` isn't found, prefix the commands with `PATH="$HOME/.cargo/bin:$PATH"`, because the winget install doesn't update an open shell.*

---

### Test: four configurations, all must be green

```
MONETA_NATIVE=0 python -m pytest tests -q
MONETA_NATIVE=1 python -m pytest tests -q
```

```
# hython: unzip the wheel somewhere, never install it into Houdini
PYTHONPATH="src;<unzipped-wheel>" "C:/Program Files/Side Effects Software/Houdini 21.0.773/bin/hython3.11.exe" -m pytest tests -q -p no:faulthandler -p no:cacheprovider
```

Run the hython command twice, once with `MONETA_NATIVE=0` and once with `MONETA_NATIVE=1`.

**Expected:** `405 passed` in every configuration (v1 and v5 together). Without the wheel: `347 passed, 35 skipped`. Always run from the repo root with `PYTHONPATH=src`: a stale `site-packages/moneta` otherwise hides `moneta.v5` from the subprocess tests.

**v5 mutation check** (every mutation must be caught):

```
mkdir <scratch> && git archive HEAD | tar -x -C <scratch>
cd <scratch> && PYTHONPATH=src python scripts/v5/mutation_check.py   # last line: missed: []
```

---

### Measure

```
PYTHONPATH=src python scripts/bench_query.py --n 1000 10000
PYTHONPATH=src python scripts/bench_query.py --n 10000 --spread
```

**Expected at 10k on this workstation:** `p95_ms` about 3 (about 6.7 with `--spread`), and `rss_delta_mb` about 69.

**The pure-Python baseline** (`MONETA_NATIVE=0`) is about 230–310 ms and 185 MB.

---

### Off switch

**`MONETA_NATIVE=0`.** Moneta then runs the pure-Python oracle path. The answers are bit-identical, just slower.

---

### When it breaks

| You see | Do |
|---|---|
| `ModuleNotFoundError: moneta_native` | Fine. Moneta runs the Python path. Rebuild with **Build** above if you want the speed. |
| A conformance test red | Revert the Rust change. Python is the oracle. |
| A log line saying `vector_index demoted to python backend` | A NaN, ∞ or non-numeric vector came in. Answers stay exact, but that index is now on the slow path. Find the bad embedding upstream. |

---

### Where it lives

- `rust/moneta_native/src/lib.rs`: the scan and decay kernels.
- `src/moneta/vector_index.py`: `_oracle_scan` and the backends.
- `src/moneta/ecs.py`: `decay_all` and `rank_hits`.
- `tests/unit/test_native_*`, `test_rank_early_stop.py`: the contract.
- `results/bench_query_*.jsonl`: measured numbers.

- `src/moneta/v5/index.py`, `model.py` (`utilities_at`): v5's dot and decay seams. `tests/v5/test_native_index_parity.py` and `test_native_decay_parity.py` are their contract.

---

### v5 operations

| Want | Do |
|---|---|
| Change the half-life | `Substrate(config, half_life_change="forward")` (old decay keeps the old rate) or `"reinterpret"` (history recomputed). A plain open with a different half-life refuses. The next sleep pass is a dry run until you confirm it. |
| Fast reopen of a big journal | `Config(checkpoint_every=N)`, or call `checkpoint()`. Open then replays only the tail. |
| Full integrity check | `verify()`. Open no longer CRC-checks the lines a checkpoint covers. |
| Which seams are on | `m._index.native`, `m.native_decay`. |
| v5 latency | `PYTHONPATH=src python scripts/v5/bench_recall_native.py --n 10000` |
