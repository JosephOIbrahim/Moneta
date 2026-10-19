# Operator's Card · Moneta native seams and attention durability

**What it is:** an optional Rust wheel, `moneta_native`, that runs Moneta's two hottest loops (the cosine scan and the decay pass) in Rust. It is about 35–70× faster at p95 than pure Python and 4–9× faster than numpy, and it returns the *same bits* as the Python code, which numpy can't.

**Golden rule:** Python is the oracle. If a conformance test goes red, the Rust is wrong, never the test.

**Second rule:** "the wheel is installed" is not "the wheel ran". Read `m.native_status` and the suite's verdict line.

**Also on this card:** attention durability (R1′), further down. It covers what survives a save, the new errors, what the ERROR lines mean, and how to downgrade without losing signals.

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

**Compare three values, never the version.** The version read `1.3.0rc1` on rc1 and on every commit before the `v1.3.0-rc2` release commit, `1.3.0rc2` on rc2, and `1.3.0` from the `v1.3.0` release commit on.

```
python -c "import moneta; b = moneta.build_info(); print(b.commit, b.src_digest)"
python -c "import moneta, moneta._native as n; w = n.wheel_info(); print(w.state, w.sha256, w.record_match)"
```

| Check | Expected (`v1.3.0` and `v1.3.0-rc2`, the same source; computed 2026-10-18, confirmed at the `v1.3.0` release commit 2026-10-19) |
|---|---|
| `src_digest` | `58600b5811c719c9b6aee547509ae97287acededf65b6ab970c5ddc53e1420b0` (`v1.3.0-rc2`, from the merge commit `3c01cf2`; at `14f060f`, before F1 and the USD repair: `11df24bbcf37…`; at the R1′ base `a4f2b0b`: `ac1742722a8d…`; before Gate B (`bec544f`): `f5c721630ac3…`) |
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

**Measured for `v1.3.0-rc2`, re-run for `v1.3.0`** (every row below gave the same result at the `v1.3.0` release commit on 2026-10-19, with the same wheel and a `git archive` mutation check). First run (Python 3.14.2, `pxr` 0.26.5, 2026-10-18, merge commit `3c01cf2`, `src_digest` `58600b5811c7…`, which both release commits keep; wheel `.pyd` sha256 `ec6d7f0c35c5…` installed in site-packages, `src` first on `PYTHONPATH`). The v5 mutation check below ended `missed: []` on the same tree.

| Run | Result | Verdict |
|---|---|---|
| wheel, `=1` | 907 passed | `NATIVE QUALIFIED` (71/71 native tests, qualification 2/2) |
| wheel, `=require` | 907 passed | `NATIVE QUALIFIED` (71/71 native tests, qualification 2/2) |
| wheel, `=0` | 907 passed | `PYTHON-ONLY PASS` |
| no wheel (absent) | 836 passed, 71 skipped | `PYTHON-ONLY PASS` |
| broken wheel (`ImportError` shim) | 836 passed, 71 skipped | `PYTHON-ONLY PASS` |
| no wheel or broken wheel, `=require` | exit 4 | (refused) |
| hython 3.11, all rows | **PLANNED: awaiting owner coordination** | not run *(2026-10-19: run on hython 22.0.400 at `4f7afc7`, same counts and verdicts; see the Houdini gate note below)* |

**No xfails remain.** B and D (see **Attention durability** below) now pass unmarked. The summary no longer prints a "Known unresolved defects" block, because `KNOWN_DEFECTS` in `tests/conftest.py` is empty.

**v5 mutation check** (every mutation must be caught):

```
mkdir <scratch> && git archive HEAD | tar -x -C <scratch>
cd <scratch> && PYTHONPATH=src python scripts/v5/mutation_check.py   # last line: missed: []
```

---

### Attention durability (R1′)

**Status.** In `v1.3.0` (stable; the `v1.3.0-rc2` source, promoted unchanged): B, D and L pass in every matrix row. The Architect conformance review and the Persistence and Substrate cross-review (design gate 3) each returned SOUND-WITH-NITS; the cross-review's fix-severity finding is fixed in `711d7fb`, and both reviews' nits are addressed. The Architect signed off design revision 6 on 2026-10-18 (SIGNED_OFF; its fix, the macOS gap below, and its six nits are applied to the design as a revision 6 erratum), the re-review of `711d7fb` and `3da0053` returned SOUND-WITH-NITS, and the owner accepted the rc2 content (gate 6) the same day. Design: `docs/design/R1-attention-durability.md`, revision 6.

- **B:** `signal_attention`, then `m.durability.snapshot_ecs(m.ecs)` (SYNAPSE's save), then restart. The signal now replays once: a save keeps every WAL line whose signal the reducer has not recorded as applied.
- **D:** a signal that lands between a sleep pass's drain and its save is kept the same way.
- **L (late landing):** an append that lands in a list the reducer has already swapped out is applied by the next pass, or at the next reopen if its appender stalls through that pass too. With one pass at a time, it is never applied twice.
- Native mode has no effect on any of them. Neither seam touches the WAL or the snapshot.
- **Power loss (Round 4 F1):** every WAL append is fsync'd before `signal_attention` returns (about 1.2 ms per signal), and every file a save publishes is fsync'd before its rename; POSIX also fsyncs the directory after each rename. **Windows has no directory fsync:** a power loss shortly after a save can roll back that save's renames. Each file stays whole, but a signal appended after a rolled-back WAL rename is lost (`docs/api.md`, Durability guarantees). **macOS:** `os.fsync` does not flush the drive's write cache, and `F_FULLFSYNC` (named by gate 2) is not called, so these guarantees hold only where fsync reaches stable storage; deferred to a later rc.

**Behaviour changes.** Signatures are unchanged, and every raise below is an existing exception type.

| Change | rc1 | R1′ |
|---|---|---|
| WAL-first `signal_attention` | Buffered, then the WAL. A failed WAL write left the signal applied in memory, and a failed flush could still write the line later. | WAL, then buffer. A failed write leaves the signal in neither place, and the same `OSError` escapes. |
| Shared store files | Only the same `storage_uri` was refused. | A second live handle on the same snapshot, WAL or tmp path raises `MonetaResourceLockedError`, whatever its URI. A config whose own four paths collide raises `ValueError`. |
| Wrong ECS | `snapshot_ecs(any_ecs)` saved it. | `snapshot_ecs(ecs)` or `start_background(ecs)` with anything but the handle's `m.ecs` raises `ValueError` and writes nothing. |
| Closed handle | The WAL reopened lazily, and a stale save still rewrote the files. | After `close()`, `signal_attention`, `wal_append`, `snapshot_ecs` and `start_background` raise `ValueError("durability manager is closed")`. |
| Unreseedable seq allocator | — | `RuntimeError("cannot reseed the WAL sequence allocator")` at construction. Needs a hand-edited `snapshot.json`; no file is changed. |
| Concurrent sleep passes | Unsupported, silent. | Still unsupported. Logs ERROR and carries on; never raises. |

An async exception such as `KeyboardInterrupt`, landing within a few bytecodes of a WAL write, can still leave a *phantom apply*: a signal whose call raised applies once at the next reopen. Design §1.4 describes these windows. That list is not claimed to be complete.

**The clock precondition.** Every signal applied before a snapshot carries a timestamp at or before that snapshot's `snapshot_created_at`. One wall clock running forward satisfies it. A backward clock step between a signal and a save breaks it, and so do two clocks (a virtual signal clock, or v5's `ManualClock`). It matters only where a line is judged by timestamp.

**Rollback and roll-forward** (design §3.5). rc1 and the v5 migration ignore `seq` and judge every line by timestamp. *T* is the `snapshot_created_at` of the snapshot on disk.

| Sequence | Outcome |
|---|---|
| rc1 store → R1′ | **Safe** (rc1-equal). Lines are judged by timestamp until the first R1′ save normalizes the WAL. |
| R1′, clean save → rc1 | **Loses** the pending lines with ts ≤ T: exactly the B and D lines R1′ kept. Never doubles. |
| R1′, crash between snapshot and compaction → rc1 | **Loses** pending ts ≤ T lines. **Could double-apply** if the clock precondition is broken. |
| R1′, compaction failing (K path), then a clean close → rc1 | As the row above, for as long as compaction keeps failing. |
| R1′ degraded save → rc1, or → R1′ | Both judge by timestamp. No double under the precondition; **loses** pending ts ≤ T lines. |
| R1′ → rc1 → R1′, rc1 saved | No double; **loses** the R1′-pending ts ≤ T lines. |
| R1′ → rc1 → R1′, rc1 never saved | **Safe.** |
| R1′ → rc1 → R1′, rc1 saved but its WAL unlink failed | No double (the first R1′ save drops the stale lines); **loses** the R1′-pending ts ≤ T lines. |
| R1′ store → v5 migration | **Loses** pending lines with ts ≤ the snapshot time. Doubles only in the crash or K-path window, with a broken precondition. |
| R1′ → v5 facade → R1′ | **Unsupported.** Loses v5-only state, double-applies when the v5 clock is behind the line timestamps, and then v5 refuses the store. **Cut over both interpreters together.** v5 enforces that by refusing; R1′ cannot detect a v5 export. Its only signal is the hydrate WARNING `snapshot has no usable wal_applied_seqs`. |

No marker can make rc1 refuse an R1′ store. rc1 only warns on a version mismatch, and a version bump would be a §9 Trigger 2.

**Drain, then verify, before a downgrade** (to rc1, or to anything that ignores `seq`). This is the only way to make R1′ → rc1 lossless.

1. Quiesce signals.
2. Under R1′, run `m.run_sleep_pass()`, then `m.close()`.
3. Verify that the WAL is empty: the file is absent, or holds only whitespace.

   ```
   python -c "import pathlib, sys; p = pathlib.Path(sys.argv[1]); print('EMPTY: safe to switch' if not p.exists() or not p.read_bytes().strip() else 'NOT EMPTY: do not switch')" <wal_path>
   ```

4. If it is not empty, do not switch. A signal raced the pass, the save degraded, or compaction failed (the K path keeps applied lines). Fix the cause and repeat from step 2.

**ERROR lines, and what to do.** Grep for these prefixes.

| You see | Means | Do |
|---|---|---|
| `durability.snapshot DEGRADED (step 0 failed: …)` or `(step 1 timed out)` | The save wrote a keyless snapshot with rc1 semantics and left the WAL whole. Deposits are saved, and `degraded_saves` counts it. Until a keyed save, a reopen judges every WAL line by timestamp and loses pending lines up to the time printed in the line. | Do not reopen or downgrade until a later save is keyed (no DEGRADED line). For the cause, read the line logged just before it. |
| `durability.snapshot step 0 (WAL normalization) failed: …` | The first save after a reopen could not rewrite the WAL. Causes: a foreign handle on the WAL (on Windows, `os.replace` raises `PermissionError`), or a WAL that no longer starts with the bytes found at hydrate (the line says so): truncated or rewritten outside the handle, or already normalized by an earlier step 0 of this handle that an interrupt such as `KeyboardInterrupt` cut short. Those repeat at every save until the handle is reopened. | Close the foreign handle (antivirus, indexer, a tail, a v5 migration read). For "no longer starts with": run `m.run_sleep_pass()` (its rows then hold every drained line), then close and reopen. |
| `durability.snapshot consistent read timed out after …s (N reducer(s) in flight, epoch moved=…)` | Sleep passes ran back to back with no quiet gap, or a reducer token is stranded. | Leave a gap between passes. If N stays at 1 or more with no pass running, close and reopen the handle. |
| `durability.snapshot WAL compaction failed: …` (the K path) | The keyed snapshot is written, so deposits are durable, but the WAL keeps its applied lines, and `snapshot_ecs` (or `run_sleep_pass`) raises. The next save retries. R1′ readers stay correct. An rc1 reader of this store could double-apply if the clock precondition is broken, for as long as this repeats. A background save logs it as `background snapshot failed`. | Find the foreign handle on the WAL. Do not downgrade while this repeats. |
| `torn attention apply: …` | A pass stopped after its drain (an exception in `apply_attention`, or an interrupt) with drained seqs recorded as applied; the line counts them. Their effects may be missing, and the next save drops their lines: a stated loss, never a double. Unrecorded seqs keep their lines. The pass raises. | Read the exception that follows it. |
| `concurrent attention reducer at entry (N in flight)` or `concurrent attention reducer detected` | Two sleep passes overlapped, which is unsupported. Nothing raised. No keyed snapshot is written from a torn read. | Run one pass at a time. If the entry line repeats with no other pass running, a token is stranded and every save will degrade: close and reopen. |
| WARNING `durability.hydrate snapshot has no usable wal_applied_seqs but N WAL line(s) carry a seq` | The current snapshot is keyless over R1′ lines: an rc1 save, a degraded save, a rewrite of `snapshot.json` that dropped the key, or a v5 export. Lines are judged by timestamp. | If a v5 facade wrote it, stop, and cut over both interpreters together. |
| `MonetaResourceLockedError` at construction | Another live handle in this process holds that URI, or that snapshot, WAL or tmp path. | Close it first. Two processes on one store are unsupported. |
| `ValueError: durability manager is closed` | A stale reference to a closed handle. Nothing was written. | Use the live handle. |

**Where it lives:** `src/moneta/durability.py` (WAL, snapshot, hydrate), `src/moneta/attention_log.py` (the log and its reducer), `src/moneta/api.py` (`signal_attention`, the store-path registry), and `tests/integration/test_attention_snapshot_regression.py` (B, D and the design §4.2 suite).

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
| ERROR `usd_target: Sdf registry sharing: layer <identifier> is already loaded in this process` | When the target opened, something else in this process (a LOP network, another stage or another `UsdTarget`) already held that store layer. The line names the shared layer and its dirty state. Moneta authors into it; nothing is refused. | Stop editing or reloading that layer from the LOP network while Moneta runs, and drop the network's reference to it before the next session. Detection runs once, when the target is built (in a seat, when the store opens), so a holder that loads a layer later is not detected. |
| `UsdSaveError` raised from `run_sleep_pass` (v1 `moneta.Moneta`), or returned as `SleepPassResult.projection_error` with the ERROR line `moneta.v5 projection failed` (v5 compat `Moneta`) | A layer's `Save()` returned `False` or raised. Every other layer was still saved, and that batch's vector commit did not happen. The failed layer stays dirty, and the next flush retries it. v1 leaves every entity that pass staged in `STAGED_FOR_SYNC` (listed by `get_consolidation_manifest()`), and no later pass commits them again. v5 projects the failed batch, and every later one, again on the next pass, and re-authors their prims in place while routing selects the layer that holds them; a retry at a rotation-cap crossing or after a UTC day change lands in the next layer as a second, stronger copy, and the stale copy stays. | Read `.failures` (layer identifier to cause), or the v5 error string, and fix the file or its permissions. |
| `ValueError: rotation_cap must be positive` | `rotation_cap < 1`. | Pass a positive cap (default 50,000). |

**Reopen keeps the authored stack.** Existing layers open first and are created only when absent; an existing layer that cannot be opened raises instead of being replaced.

**Gate 2 on Houdini, met for `v1.3.0` on 2026-10-19 (H22.0.400, headless hython):** the hython rows are green, and the LOP probe passed (`scripts/houdini/c3_probe.py`, phases `seed`, `lop` and `reopen`, each in its own hython process). Run the probe and the hython suite with `HOUDINI_PACKAGE_DIR` pointed at an empty folder: SYNAPSE's package sets `MONETA_NATIVE=0`. Moving a SYNAPSE seat also means moving its Moneta checkout to `v1.3.0`.

---

### Cut a release

**Prerelease from a feature branch; `main` and "Latest" stay put.** `X.Y.Z-rcN` is the tag; `pyproject.toml` takes `X.Y.ZrcN`. To promote an rc to stable, follow steps 1–5 with these changes, then step 8.

**1 · Green first.** `NATIVE QUALIFIED` with the wheel under `=1` and `=require`, `PYTHON-ONLY PASS` under `=0` and without the wheel, plus the v5 mutation check (`missed: []`). hython rows once the owner has coordinated them.

**2 · Bump the version** in `pyproject.toml` so it matches the tag.

**3 · Public-safety scan.** The repo is public. Scan every commit since the last public tag, patches and messages both, then the tag text and the notes file:

```bash
git log -p --format=fuller <last-public-tag>..HEAD | grep -niE "uspto|claim [0-9]|users[/\]|appdata|onedrive|houdini 21"
```

Every hit is scrubbed at the tip or accepted in writing, with a reason and a precedent; this card's own pattern line matches itself. A secret, a private email or a private path in a commit that was never public is scrubbed by rewriting that commit, never by a tip edit alone.

**`v1.3.0-rc2` record (Route A).** Scan hit 1, local paths that `ea7ee52`, `a5853e7` and `986dae0` added to two docs and `b460e78` removed at the tip, was accepted in writing by the owner on 2026-10-18, so those commits are not rewritten. Reason: history only; no file at the tip has those lines. Precedent: the same prefix is public at `c33bbd96` (`docs/v7/ROUND4_BRIEF.md:367`). The owner's first name in the messages of `0062d4a` and `075eb64` was accepted the same way (precedent: published lines at `c33bbd96`).

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

**8 · Promote an rc to stable** (done for `v1.3.0` on 2026-10-19, from `v1.3.0-rc2`).

- **Branch** `release/vX.Y.Z` from the rc tag, never from `main` unless `main` contains it. Keep every rc tag and release as it is.
- **Change only** the version (`pyproject.toml` takes `X.Y.Z`) and the docs. No `*.py` or `*.rs` change, so the `src_digest` stays the rc's.
- **Re-run step 1 on the release commit**, every row, before the tag. Reuse the rc's reviews only because the code is the same.
- **Tag and publish** without `--prerelease`, and mark it Latest:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z: <one line>"
git push origin release/vX.Y.Z vX.Y.Z
gh release create vX.Y.Z --target release/vX.Y.Z --latest \
    --title "vX.Y.Z — <one line>" --notes-file RELEASE_NOTES.md
```

- **Check** `git ls-remote --tags origin vX.Y.Z` (the peeled `^{}` line is your commit) and `gh release view vX.Y.Z --json isDraft,isPrerelease` (both false). `gh release list` shows it **Latest**.
- **Never** attach an rc's binaries to the stable release. Attach only what was built at the release commit.
