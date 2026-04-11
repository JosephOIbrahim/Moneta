# Testing conventions

This file collects testing rules that span multiple test modules. Each rule cites its origin (pass, ruling, or incident) so future test authors understand the history.

## Seed randomness from `hashlib`, never from `hash()`

**Rule:** Any test that seeds a random number generator from a string input must use `hashlib` (or a literal int), never Python's built-in `hash()`.

**Why:** Python's `hash()` for strings is randomized per-process by default (via the `PYTHONHASHSEED` environment variable, which defaults to `random` in CPython 3.3+). A test that does `random.Random(hash(("topic", variant)))` will produce a DIFFERENT seed on each process start, making the test non-reproducible across invocations. This is especially dangerous because the determinism *does* survive within a single process (so the test appears stable in a single pytest run) and only breaks when you run pytest twice in a row, or when CI runs the same test on two workers with different hash seeds.

**Incident:** Phase 1 Pass 4 — synthetic session harness threshold proposal.

The synthetic session harness used `hash((topic, variant))` to seed `_embed`'s local `Random`. Initial runs of `tests/load/synthetic_session.py` showed pruned/staged counts of `13/10`, `14/13`, `15/13`, `15/11`, `8/9` across five back-to-back invocations. The totals (`total_deposits=107`, `total_queries=171`, `total_attention_signals=292`) were exactly deterministic, but the fine-grained classification outcomes varied. Setting `PYTHONHASHSEED=0` collapsed the variance to zero, which isolated the source. Fix: replace `hash(...)` with `hashlib.md5(key.encode()).digest()[:4]` converted to int.

**How to apply:**

```python
# WRONG — non-reproducible across process starts.
# Python's hash() for strings is randomized per-process by default.
rng = random.Random(hash((topic, variant)) & 0xFFFFFFFF)

# RIGHT — deterministic across runs.
import hashlib
key = f"{topic}:{variant}".encode("utf-8")
seed = int.from_bytes(hashlib.md5(key).digest()[:4], "little")
rng = random.Random(seed)

# ALSO RIGHT — literal int when you don't need string-keyed seeding.
rng = random.Random(42)
```

**Scope:** This rule applies to:
- All tests under `tests/`
- Any benchmark scripts under `scripts/` that need reproducible seeding
- Any future test harnesses that synthesize inputs from string keys

Production code in `src/moneta/` that needs randomness (there currently isn't any — UUIDs come from `uuid4()` which uses OS randomness by design) should document its determinism expectations explicitly.

## How to verify reproducibility in CI

A quick reproducibility check for any stochastic test harness:

```bash
PYTHONPATH=src python my_harness.py > run1.txt
PYTHONPATH=src python my_harness.py > run2.txt
diff run1.txt run2.txt  # must be empty
```

If `diff` shows differences, trace back to any use of `hash()`, `id()`, dict-iteration-over-non-insertion-order structures, or uninitialized `random` module state. The most common culprit is `hash()`-seeded randomness, per the incident above.

## Related

- Inline version of the `hash()` rule lives in `tests/load/synthetic_session.py` module docstring, so anyone reading the harness in isolation sees the warning without needing this file.
- The fix landed in Phase 1 Pass 4 after Joseph authorized the hashlib transition during threshold review.
- Phase 2 benchmark work (`scripts/usd_metabolism_bench_v2.py`) follows the same rule for any test fixture generation.
