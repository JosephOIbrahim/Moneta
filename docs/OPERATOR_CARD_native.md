# Operator's Card · Moneta native seams

**What it is:** an optional Rust wheel, `moneta_native`, that runs Moneta's two hottest loops (the cosine scan and the decay pass) in Rust. It is about 35–70× faster at p95 than pure Python and 4–9× faster than numpy, and it returns the *same bits* as the Python code, which numpy can't.

**Golden rule:** Python is the oracle. If a conformance test goes red, the Rust is wrong, never the test.

**Second rule:** "the wheel is installed" is not "the wheel ran". Read `m.native_status` and the suite's verdict line.

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

### The switch

**`MONETA_NATIVE`** is stripped and lower-cased, then read as one of five classes:

| Class | Values | Means |
|---|---|---|
| UNSET | not set | auto |
| AUTO | `""` `1` `true` `on` `yes` `auto` | native if the wheel loads, else Python |
| OFF | `0` `false` `off` `no` | Python; the wheel is never imported |
| REQUIRE | `require` | native or a loud error |
| UNKNOWN | anything else | auto, plus one `RuntimeWarning` per process |

> **Behaviour change.** `false`, `off` and `no` used to mean ON. They now mean **OFF**. `1` still means auto.

**Per handle:** `MonetaConfig(native=None | "auto" | "off" | "require")`. Resolved once, before the store lock is taken.

| config ↓ / env → | UNSET | AUTO | OFF | REQUIRE | UNKNOWN |
|---|---|---|---|---|---|
| `None` | auto | auto | off | require | auto + warn |
| `"auto"` | auto | auto | **off** (kill switch) | **require** (env tightens) | auto + warn |
| `"off"` | off | off | off | **`NativeConfigError`** | off + warn |
| `"require"` | require | require | **`NativeConfigError`** | require | require + warn |

**Explicit component arguments ignore the env:** `ECS(native=True)` / `VectorIndex(backend="native")` are require, `ECS(native=False)` / `backend="python"` are off. That is why a `MONETA_NATIVE=0` suite run still shows real native calls: the native-marked tests ask for the backend explicitly.

**v5 differs.** `moneta.v5` still reads only `MONETA_NATIVE=0` as off (`v5/index.py`). `MONETA_NATIVE=false` turns v1 off and leaves v5 on.

---

### What `require` guarantees

- **Decay:** every `ECS.decay_all` runs `decay_batch`. No fallback. A native failure raises `NativeSeamError`, columns unchanged.
- **Scan:** the index stays native for life. A deposit outside the envelope (non-finite, non-numeric, empty, wrong dim) raises `NativeSeamError` before any mutation; so does hydrating such a stored vector.
- **Allowed and counted:** a query with a non-finite component (`query_nonfinite`) and a cosine overflow to NaN (`cosine_overflow`) are answered by the oracle. The answer is exact.
- **Not a fallback:** dim-mismatch and zero-norm queries return `[]` on both backends.

---

### Is native running?

```python
st = m.native_status                     # handle property, not an agent op
st.scan.active, st.decay.active          # "native" | "python"
st.scan.reason, st.decay.reason          # why python, or None
st.scan.native_calls, st.scan.fallbacks  # Rust invocations; {reason: count}
st.scan.all_native, st.require_satisfied # True / True (require mode only)
st.wheel.state, st.wheel.sha256, st.wheel.record_match
st.source.commit, st.source.src_digest   # = moneta.build_info()
```

The handle also logs one INFO line at construction with both seams, `wheel.sha256[:12]`, `wheel.state`, `source.commit[:12]` and `source.src_digest[:12]`.

---

### Verify what SYNAPSE loads

**Compare three values, never the version.** The version reads `1.3.0rc1` on both rc1 and this branch.

```
python -c "import moneta; b = moneta.build_info(); print(b.commit, b.src_digest)"
python -c "import moneta, moneta._native as n; w = n.wheel_info(); print(w.state, w.sha256, w.record_match)"
```

| Check | Expected (this branch, run on 2026-10-16) |
|---|---|
| `src_digest` | `f5c721630ac32b9ffcf4bb81b63ce6151040b134dec645cc16236061f0e26de9` |
| `.pyd` sha256 | `ec6d7f0c35c5b345f983f4aa80cfea086f3aca454e9cd74a58b6208227b02833` (0.1.0 abi3, `record_match=True`) |
| `commit` | the commit you checked out. Docs-only commits leave `src_digest` unchanged. |

---

### Test

```
MONETA_NATIVE=1       PYTHONPATH="src;<unzipped-wheel>" python -m pytest tests -q -p no:cacheprovider -rsx
MONETA_NATIVE=require PYTHONPATH="src;<unzipped-wheel>" python -m pytest tests -q -p no:cacheprovider -rsx
MONETA_NATIVE=0       PYTHONPATH="src;<unzipped-wheel>" python -m pytest tests -q -p no:cacheprovider -rsx
```

**Always put `src` first on `PYTHONPATH`.** Otherwise subprocess tests can import a stale installed `moneta`. Add `MONETA_QUAL_REPORT=<file>.json` to save the verdict and identity as JSON.

**Read the last block of the summary:**

| Verdict line | Means |
|---|---|
| `NATIVE QUALIFIED` | Wheel loaded with `record_match=True`, mode auto or require, 0 native tests skipped, qualification tests passed, both seams made real Rust calls, 0 unexpected fallbacks, suite green. |
| `NATIVE NOT QUALIFIED: <reasons>` | Wheel loaded but one of the above failed. The reasons say which. |
| `PYTHON-ONLY PASS (not native qualified)` | Green, but the wheel is not loaded or the mode is off. |
| `PYTHON-ONLY FAIL (not native qualified): …` | Red run without native. |
| exit code 4, `MONETA_NATIVE='require' requires the native wheel` | Require asked, wheel not loaded. |

**Measured on this branch** (Python 3.14.2, commit `98a998f084eb`, `src_digest` `f5c721630ac3`):

| Run | Result | Verdict |
|---|---|---|
| wheel, `=1` | 779 passed, 2 xfailed | `NATIVE QUALIFIED` (71/71 native tests; Rust calls scan 594, decay 512) |
| wheel, `=require` | 779 passed, 2 xfailed | `NATIVE QUALIFIED` |
| wheel, `=0` | 779 passed, 2 xfailed | `PYTHON-ONLY PASS` |
| no wheel / broken wheel | 708 passed, 71 skipped, 2 xfailed | `PYTHON-ONLY PASS` |
| no wheel, `=require` | exit 4 | (refused) |
| hython 3.11, all rows | **PLANNED: awaiting owner coordination** | not run |

**The 2 xfailed are defects B and D below.** They are not passes.

**v5 mutation check** (every mutation must be caught):

```
mkdir <scratch> && git archive HEAD | tar -x -C <scratch>
cd <scratch> && PYTHONPATH=src python scripts/v5/mutation_check.py   # last line: missed: []
```

---

### Known unresolved defects: B and D

**Undrained attention is lost across a bare snapshot and restart. Not fixed.**

- **B:** `signal_attention`, then `m.durability.snapshot_ecs(m.ecs)` (SYNAPSE's save), then restart: the signal is gone.
- **D:** a signal that lands between the sleep pass's drain and its snapshot is gone.
- Pinned as strict xfail in `tests/integration/test_attention_snapshot_regression.py`. The summary prints a "Known unresolved defects" block. Design (not implemented on this branch): `docs/design/R1-attention-durability.md`.
- Native mode has no effect on B or D. Neither seam touches the WAL or the snapshot.

---

### Measure

```
PYTHONPATH=src python scripts/bench_query.py --n 1000 10000
PYTHONPATH=src python scripts/bench_query.py --n 10000 --spread
```

**Expected at 10k on this workstation:** `p95_ms` about 3 (about 6.7 with `--spread`), and `rss_delta_mb` about 69.

**The pure-Python baseline** (`MONETA_NATIVE=0`) is about 230–310 ms and 185 MB.

---

### When it breaks

| You see | Do |
|---|---|
| `wheel.state == "absent"` | Fine in auto. Moneta runs Python. Build the wheel if you want the speed. |
| `wheel.state == "broken"` / `"incompatible"` | Read `wheel.reason`. Rebuild, or unzip the whole wheel (a partial unzip is `broken`). |
| `NativeConfigError` | Config and env contradict: `native="require"` with an OFF env, or `native="off"` with `MONETA_NATIVE=require`. Fix one. |
| `NativeUnavailableError` | Require asked, wheel not loaded. Fix the wheel, or drop to auto. |
| `NativeSeamError` on `deposit` | Require mode, bad embedding (NaN, ∞, empty, wrong dim). Nothing was written. Fix the vector upstream. |
| `NativeSeamError` on construct | Require mode, a stored vector is outside the envelope. Lock released, no file changed. Reopen in auto or off. |
| `NativeSeamError` in a sleep pass | Require mode, `decay_batch` failed. No snapshot is written and the WAL keeps the signal, so a reopen (auto or off) replays it exactly once. |
| `RuntimeWarning: MONETA_NATIVE=... is not a recognised value` | Typo. Treated as auto. |
| `scan.demoted` True, `fallbacks` has `demoted:…` | Auto mode: a bad vector demoted that index to Python. Answers stay exact. Find the bad embedding. |
| `decay.fallbacks` has `decay_error:<Type>` | Auto mode: native decay failed, the oracle ran, decay is demoted for that handle. |
| A conformance test red | Revert the Rust change. Python is the oracle. |
| `NATIVE NOT QUALIFIED` | Read the reasons on the same line. |

---

### Where it lives

- `rust/moneta_native/src/lib.rs`: the scan and decay kernels.
- `src/moneta/_native.py`: loader, env classes, truth table, `NativeStatus`, errors.
- `src/moneta/_build.py`: `build_info()` and `src_digest`.
- `src/moneta/vector_index.py`: `_oracle_scan` and the backends.
- `src/moneta/ecs.py`: `decay_all` and `rank_hits`.
- `tests/conftest.py`: markers, fallback guard, verdict line.
- `tests/qualification/test_native_executes.py`: fresh and reopened lifecycles, native required.
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
| Which seams are on (v5) | `m._index.native`, `m.native_decay`. Only `MONETA_NATIVE=0` turns them off. |
| Which seams are on (v1) | `m.native_status`. |
| v5 latency | `PYTHONPATH=src python scripts/v5/bench_recall_native.py --n 10000` |

---

### USD mirror (cold tier)

**LOP networks must not edit or reload `.moneta/usd` layers in a live session.** Sdf keeps one layer registry per process. A LOP network that loads a store layer holds the same layer object Moneta authors into, and Moneta's `flush()` saves every opinion that layer holds.

| You see | Means | Do |
|---|---|---|
| ERROR `usd_target: Sdf registry sharing: layer <identifier> is already loaded in this process` | When the target opened, something else in this process (a LOP network, another stage or another `UsdTarget`) already held that store layer. The line names the shared layer and its dirty state. Moneta authors into it; nothing is refused. | Stop editing or reloading that layer from the LOP network while Moneta runs, and drop the network's reference to it before the next session. A holder that loads a layer after the target opened it is not detected. |
| `UsdSaveError` from `run_sleep_pass` | A layer's `Save()` returned `False` or raised. Every other layer was still saved, and that batch's vector commit did not happen. The failed layer stays dirty, and the next flush retries it. | Read `.failures` (layer identifier to cause) and fix the file or its permissions. |
| `ValueError: rotation_cap must be positive` | `rotation_cap < 1`. | Pass a positive cap (default 50,000). |

**Reopen keeps the authored stack.** Existing layers open first and are created only when absent; an existing layer that cannot be opened raises instead of being replaced.

**Owed before any Houdini seat moves to this code** (gate 2): a hython row on H22.0.400 with a LOP network sublayering `cortex_root.usda`. Not run.

---

### Cut a release

**Prerelease from a feature branch; `main` and "Latest" stay put.** `X.Y.Z-rcN` is the tag; `pyproject.toml` takes `X.Y.ZrcN`.

**1 · Green first.** `NATIVE QUALIFIED` with the wheel under `=1` and `=require`, `PYTHON-ONLY PASS` under `=0` and without the wheel, plus the v5 mutation check (`missed: []`). hython rows once the owner has coordinated them.

**2 · Bump the version** in `pyproject.toml` so it matches the tag.

**3 · Public-safety scan.** The repo is public. Nothing should print:

```bash
git diff main..HEAD | grep -niE "uspto|claim [0-9]"
grep -niE "users[/\]|houdini 21" README.md RELEASE_NOTES.md
```

**4 · Commit by name.** Never `git add -A`; stray root files exist.

```bash
git add README.md pyproject.toml <changed paths>
git commit
```

**5 · Tag and push** the branch and the tag only. No `main`, no `--force`.

```bash
git tag -a vX.Y.Z-rcN -m "vX.Y.Z-rcN: <one line>"
git push origin <branch> vX.Y.Z-rcN
```

**6 · Publish** as a prerelease from the branch:

```bash
gh release create vX.Y.Z-rcN --target <branch> --prerelease \
    --title "vX.Y.Z-rcN — <one line>" --notes-file RELEASE_NOTES.md
```

**7 · Check** that all mermaid blocks render on the branch's README page on GitHub, then `gh release list` (the rc shows **Pre-release**; "Latest" unchanged).

| You see | Do |
|---|---|
| `A repository cannot have more than 20 topics` | Topics cap at 20. Drop one before `gh repo edit --add-topic`. |
| "Unable to render rich display" on GitHub | A mermaid block GitHub rejects. Quote labels, no `λ` or bare parentheses in nodes, fix, push again. |
| The rc became "Latest" | `gh release edit vX.Y.Z-rcN --prerelease`. |
