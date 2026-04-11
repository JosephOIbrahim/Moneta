"""USD Metabolism Benchmark v2 — Phase 2 decision-gate harness.

MONETA.md §4 Phase 2. Measures the USD lock-and-rebuild tax under
accumulated load to produce decision-gate numbers that determine Phase 3
integration depth.

Source lineage note
-------------------
The Phase 2 authorization prompt referenced `docs/rounds/round-2.md` as
the original benchmark script source and `docs/rounds/round-3.md` as the
amendments document. At the time of this script's authoring, both round
files on disk are still the Pass 1 placeholders I wrote — the Gemini
Deep Think content was never migrated to the repo (Joseph's action item
logged in Pass 1 never completed). This script is therefore implemented
from the amendment spec in the Phase 2 authorization prompt directly,
not from the literal Round 2 source code. Rationale for each fix is
documented inline below so the result can be compared against the
original when it becomes available.

Round 2.5 review fixes + Round 3 amendments applied
----------------------------------------------------

(a) Reader and writer thread lock scopes separated.
    The original Round 2 benchmark (per the Pass 2.5 review) took
    `stage_lock` across the full reader tick cycle including inter-tick
    sleep. That measures pure lock contention rather than realistic
    concurrent read/write behavior. This v2 holds the lock only for
    the actual `Traverse()` call on the reader side; the inter-tick
    sleep happens lock-free.

(b) Pcp rebuild tax measured as a distribution.
    The original reported a single sample of the first read after a
    write. This v2 runs N_WRITES_PER_CONFIG writes per config (default
    20) and aggregates reader latencies from the post-write window
    into p50/p95/p99 percentiles. This captures the tail that a single
    sample hides.

(c) Real disk path via `primary_layer.Save()`.
    The original used `Sdf.Layer.CreateAnonymous()` which bypasses the
    filesystem. This v2 creates real `.usda` files in a temp directory
    and measures `Save()` as part of the write lock hold, so the
    serialization-to-disk cost is captured in the measured stall.

(d) Small batches use small stages.
    The original inflated the stage to max(1000, batch_size) prims
    even for `batch_size=10`, which inflated the baseline. This v2
    sizes its pre-populated stage purely from `accumulated_layer_size`,
    and `batch_size` controls only how many prims/attributes are
    authored per batch.

(e) `shadow_index_commit_ms ∈ [5, 15, 50]` — Round 3 Q3 finding #1.
    A blocking `time.sleep(ms/1000)` inside the writer's lock scope
    alongside `Save()`, simulating a concurrent LanceDB/FAISS disk
    append. Captures the shadow-index contribution to writer lock hold.

(f) `accumulated_layer_size ∈ [0, 25000, 100000]` — Round 3 Q3 finding #2.
    Pre-populated dummy prims before the benchmark loop begins.
    Measures end-of-day serialization stall against an accumulated
    sublayer, not just a morning baseline against an empty stage.

Runtime requirement
-------------------
This script requires `pxr` (OpenUSD Python bindings). On this
development environment, `pip install usd-core` is not available for
Python 3.14. The benchmark is invoked via Houdini's bundled `hython`,
which ships OpenUSD 0.25.5 under Python 3.11.7:

    "C:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython.exe" \\
        scripts/usd_metabolism_bench_v2.py [flags]

Flags
-----
  --warmup-only      Run a single minimal config for timing calibration.
  --prune LEVEL      Pruned sweep. LEVEL in {none, small, medium}.
                     `none` = full sweep (default).
                     `small` = 16-config debug sweep.
                     `medium` = ~50-config intermediate sweep.
  --output PATH      CSV output path (default: results/usd_sizing_results.csv)
  --n-writes N       Writes per config (default: 20)
  --progress         Print per-config progress to stdout.

Sweep dimensions (full)
-----------------------
    batch_size              [10, 100, 1000]
    structural_ratio        [0.0, 0.5, 1.0]
    sublayer_count          [1, 5, 20]
    read_load_hz            [60]
    shadow_index_commit_ms  [5, 15, 50]
    accumulated_layer_size  [0, 25000, 100000]

Full sweep = 3 * 3 * 3 * 1 * 3 * 3 = 243 configs.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import statistics
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from itertools import product
from pathlib import Path
from typing import List, Optional, Tuple

# ----------------------------------------------------------------------
# pxr imports — Phase 2 is the first phase where these are legal.
# Strictly contained to this script and any scripts/bench_helpers.py.
# Do NOT add these imports anywhere under src/moneta/ — Phase 3 is when
# pxr enters the runtime substrate.
# ----------------------------------------------------------------------
try:
    from pxr import Sdf, Usd, UsdGeom  # noqa: F401
    # UsdGeom import is load-bearing: it registers the Xform schema so
    # `DefinePrim(path, "Xform")` resolves the type name. Without this
    # import, DefinePrim fails with `_DefinePrim` at stage.cpp:3889 —
    # surfaced during the first warmup run of this script.
except ImportError as exc:
    sys.stderr.write(
        "ERROR: pxr not available. This benchmark requires OpenUSD Python\n"
        "bindings. On Python 3.14 Windows, usd-core is not on PyPI; use\n"
        "Houdini's bundled hython instead:\n\n"
        "    \"C:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython.exe\" "
        "scripts/usd_metabolism_bench_v2.py [flags]\n\n"
        f"Original import error: {exc}\n"
    )
    sys.exit(2)


# ----------------------------------------------------------------------
# Sweep definitions
# ----------------------------------------------------------------------

SWEEP_BATCH_SIZES = [10, 100, 1000]
SWEEP_STRUCTURAL_RATIOS = [0.0, 0.5, 1.0]
SWEEP_SUBLAYER_COUNTS = [1, 5, 20]
SWEEP_READ_LOAD_HZ = [60]
SWEEP_SHADOW_INDEX_COMMIT_MS = [5, 15, 50]
SWEEP_ACCUMULATED_LAYER_SIZES = [0, 25000, 100000]

DEFAULT_N_WRITES_PER_CONFIG = 20
POST_WRITE_WINDOW_SEC = 0.5
WARMUP_SEC = 0.4
READER_TRAVERSE_CAP = 20  # prims visited per reader tick (bounded work)
DEFAULT_OUTPUT = "results/usd_sizing_results.csv"


# ----------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class BenchConfig:
    batch_size: int
    structural_ratio: float
    sublayer_count: int
    read_load_hz: int
    shadow_index_commit_ms: int
    accumulated_layer_size: int


@dataclass
class MetricsRow:
    # Sweep parameters
    batch_size: int
    structural_ratio: float
    sublayer_count: int
    read_load_hz: int
    shadow_index_commit_ms: int
    accumulated_layer_size: int
    # Measured metrics
    n_writes: int
    write_lock_ms_median: float
    write_lock_ms_max: float
    pcp_rebuild_p50_ms: float
    pcp_rebuild_p95_ms: float
    pcp_rebuild_p99_ms: float
    p95_concurrent_read_stall_ms: float
    achieved_reader_hz: float
    n_concurrent_samples: int
    n_post_write_samples: int
    n_total_samples: int
    setup_sec: float
    run_sec: float


# ----------------------------------------------------------------------
# Percentile helper (stdlib-only, no numpy)
# ----------------------------------------------------------------------


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


# ----------------------------------------------------------------------
# Stage construction — real disk path, Round 3 Q3 fix (c)
# ----------------------------------------------------------------------


def build_stage_for_config(
    work_dir: Path, config: BenchConfig
) -> Tuple["Usd.Stage", "Sdf.Layer"]:
    """Build a stage with `accumulated_layer_size` prims and `sublayer_count`
    empty sublayers, written to disk under `work_dir`.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    primary_path = work_dir / "primary.usda"
    primary_layer = Sdf.Layer.CreateNew(str(primary_path))

    # Create empty sublayers. `sublayer_count=1` means one sublayer (minimal stack);
    # higher counts stack more empty layers below the primary.
    sublayer_paths: List[str] = []
    for i in range(config.sublayer_count):
        sp = work_dir / f"sublayer_{i}.usda"
        Sdf.Layer.CreateNew(str(sp))
        sublayer_paths.append(sp.name)
    primary_layer.subLayerPaths[:] = sublayer_paths

    stage = Usd.Stage.Open(primary_layer)

    # Round 3 Q3 fix (f): pre-populate the stage with accumulated_layer_size
    # dummy prims before the benchmark loop begins.
    #
    # Authoring uses `Sdf.CreatePrimInLayer` rather than
    # `UsdStage.DefinePrim`. During development of this benchmark we
    # discovered that `UsdStage.DefinePrim` fails inside `Sdf.ChangeBlock`
    # when the stage has sublayers attached — a USD 0.25.5 behavior that
    # surfaces as `_DefinePrim` at stage.cpp:3889. The lower-level Sdf API
    # bypasses this and is in fact more faithful to Moneta's substrate
    # convention #5 ("Sdf.ChangeBlock for batch writes — always"), since
    # Phase 3's real authoring code will operate at the Sdf.Layer level
    # directly.
    if config.accumulated_layer_size > 0:
        with Sdf.ChangeBlock():
            for i in range(config.accumulated_layer_size):
                Sdf.CreatePrimInLayer(
                    primary_layer, Sdf.Path(f"/accum_{i}")
                )
        primary_layer.Save()

    return stage, primary_layer


# ----------------------------------------------------------------------
# Write batch — structural_ratio controls prim-create vs attr-write mix
# ----------------------------------------------------------------------


def author_batch(
    target_layer: "Sdf.Layer",
    batch_id: int,
    batch_size: int,
    structural_ratio: float,
) -> None:
    """Author a batch of changes directly to `target_layer` via the Sdf API.

    structural_ratio = 0.0  → pure property changes (create attribute)
    structural_ratio = 1.0  → pure structural changes (create new prims)
    structural_ratio = 0.5  → half and half

    The split is intentional: Pcp rebuild is triggered by structural
    changes more aggressively than by pure attribute edits, so the
    ratio exposes how sensitive the tax is to structural pressure.

    Note: authoring uses `Sdf.CreatePrimInLayer` + `Sdf.AttributeSpec`
    rather than `UsdStage.DefinePrim` + `UsdPrim.CreateAttribute` —
    see `build_stage_for_config` for the rationale (USD 0.25.5
    DefinePrim-inside-ChangeBlock-with-sublayers incompatibility).
    """
    n_structural = int(batch_size * structural_ratio)
    n_property = batch_size - n_structural

    with Sdf.ChangeBlock():
        for i in range(n_structural):
            Sdf.CreatePrimInLayer(
                target_layer, Sdf.Path(f"/struct_b{batch_id}_{i}")
            )
        for i in range(n_property):
            prim_spec = Sdf.CreatePrimInLayer(
                target_layer, Sdf.Path(f"/prop_b{batch_id}_{i}")
            )
            attr_spec = Sdf.AttributeSpec(
                prim_spec, "test_attr", Sdf.ValueTypeNames.Float
            )
            attr_spec.default = float(batch_id)


# ----------------------------------------------------------------------
# Reader thread — separated lock scope (Round 2.5 fix a)
# ----------------------------------------------------------------------


class ReaderStats:
    """Thread-safe collector for (wall_time, latency_ms) samples."""

    def __init__(self) -> None:
        self.samples: List[Tuple[float, float]] = []
        self._lock = threading.Lock()

    def append(self, wall_time: float, latency_ms: float) -> None:
        with self._lock:
            self.samples.append((wall_time, latency_ms))

    def snapshot(self) -> List[Tuple[float, float]]:
        with self._lock:
            return list(self.samples)

    def clear(self) -> None:
        with self._lock:
            self.samples.clear()


def reader_loop(
    stage: "Usd.Stage",
    hz: int,
    stats: ReaderStats,
    stop_event: threading.Event,
    stage_lock: threading.Lock,
) -> None:
    """Read tick loop. Lock scope is bounded to the `Traverse()` call only
    — the inter-tick sleep happens lock-free (Round 2.5 fix a).
    """
    period = 1.0 / hz
    next_tick = time.perf_counter()
    while not stop_event.is_set():
        tick_start = time.perf_counter()
        with stage_lock:
            n_visited = 0
            for _ in stage.Traverse():
                n_visited += 1
                if n_visited >= READER_TRAVERSE_CAP:
                    break
        latency_ms = (time.perf_counter() - tick_start) * 1000.0
        stats.append(tick_start, latency_ms)

        next_tick += period
        sleep_for = next_tick - time.perf_counter()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            # Running behind — skip ahead to avoid drift amplification.
            next_tick = time.perf_counter() + period


# ----------------------------------------------------------------------
# Config runner
# ----------------------------------------------------------------------


def run_config(
    config: BenchConfig,
    tmp_root: Path,
    n_writes: int,
) -> MetricsRow:
    """Execute one benchmark config end-to-end."""
    setup_start = time.perf_counter()
    work_dir = tmp_root / f"cfg_{id(config):x}"

    stage, primary_layer = build_stage_for_config(work_dir, config)
    setup_sec = time.perf_counter() - setup_start

    stats = ReaderStats()
    stop_event = threading.Event()
    stage_lock = threading.Lock()

    reader = threading.Thread(
        target=reader_loop,
        args=(stage, config.read_load_hz, stats, stop_event, stage_lock),
        daemon=True,
        name="reader",
    )
    reader.start()

    run_start = time.perf_counter()

    # Warmup so the first measurements aren't cold-cache.
    time.sleep(WARMUP_SEC)
    stats.clear()

    # Writer loop — N batches with per-batch lock windows.
    write_windows: List[Tuple[float, float]] = []
    for i in range(n_writes):
        with stage_lock:
            write_start = time.perf_counter()
            author_batch(
                primary_layer,
                batch_id=i,
                batch_size=config.batch_size,
                structural_ratio=config.structural_ratio,
            )
            primary_layer.Save()
            # Round 3 Q3 fix (e): shadow index commit inside the writer lock.
            time.sleep(config.shadow_index_commit_ms / 1000.0)
            write_end = time.perf_counter()
        write_windows.append((write_start, write_end))

        # Let the reader observe post-write Pcp rebuild tax.
        time.sleep(POST_WRITE_WINDOW_SEC)

    stop_event.set()
    reader.join(timeout=5.0)

    run_sec = time.perf_counter() - run_start
    samples = stats.snapshot()

    # Partition samples into (concurrent with write, post-write, neither).
    concurrent_latencies: List[float] = []
    post_write_latencies: List[float] = []
    for tick_wall, latency_ms in samples:
        for ws, we in write_windows:
            if ws <= tick_wall <= we:
                concurrent_latencies.append(latency_ms)
                break
            if we < tick_wall <= we + POST_WRITE_WINDOW_SEC:
                post_write_latencies.append(latency_ms)
                break

    write_lock_times_ms = [
        (we - ws) * 1000.0 for ws, we in write_windows
    ]

    # Achieved reader hz from post-warmup sample count.
    measured_duration_sec = max(run_sec - WARMUP_SEC, 1e-6)
    achieved_hz = len(samples) / measured_duration_sec

    # Cleanup working files to keep temp small.
    try:
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass

    return MetricsRow(
        batch_size=config.batch_size,
        structural_ratio=config.structural_ratio,
        sublayer_count=config.sublayer_count,
        read_load_hz=config.read_load_hz,
        shadow_index_commit_ms=config.shadow_index_commit_ms,
        accumulated_layer_size=config.accumulated_layer_size,
        n_writes=n_writes,
        write_lock_ms_median=(
            statistics.median(write_lock_times_ms)
            if write_lock_times_ms
            else 0.0
        ),
        write_lock_ms_max=(
            max(write_lock_times_ms) if write_lock_times_ms else 0.0
        ),
        pcp_rebuild_p50_ms=percentile(post_write_latencies, 50),
        pcp_rebuild_p95_ms=percentile(post_write_latencies, 95),
        pcp_rebuild_p99_ms=percentile(post_write_latencies, 99),
        p95_concurrent_read_stall_ms=percentile(concurrent_latencies, 95),
        achieved_reader_hz=achieved_hz,
        n_concurrent_samples=len(concurrent_latencies),
        n_post_write_samples=len(post_write_latencies),
        n_total_samples=len(samples),
        setup_sec=setup_sec,
        run_sec=run_sec,
    )


# ----------------------------------------------------------------------
# Sweep construction
# ----------------------------------------------------------------------


def full_sweep() -> List[BenchConfig]:
    return [
        BenchConfig(b, r, s, h, c, a)
        for b, r, s, h, c, a in product(
            SWEEP_BATCH_SIZES,
            SWEEP_STRUCTURAL_RATIOS,
            SWEEP_SUBLAYER_COUNTS,
            SWEEP_READ_LOAD_HZ,
            SWEEP_SHADOW_INDEX_COMMIT_MS,
            SWEEP_ACCUMULATED_LAYER_SIZES,
        )
    ]


def small_sweep() -> List[BenchConfig]:
    """16-config debug sweep covering extremes of each dimension."""
    return [
        BenchConfig(b, r, s, 60, c, a)
        for b, r, s, c, a in product(
            [10, 1000], [0.0, 1.0], [1, 20], [5, 50], [0, 100000]
        )
    ]


def medium_sweep() -> List[BenchConfig]:
    """~54-config intermediate sweep — coarser batch_size, full accumulated,
    coarser sublayer_count.
    """
    return [
        BenchConfig(b, r, s, 60, c, a)
        for b, r, s, c, a in product(
            [10, 100, 1000], [0.0, 1.0], [1, 20],
            [5, 15, 50], [0, 25000, 100000],
        )
    ]


def warmup_sweep() -> List[BenchConfig]:
    return [BenchConfig(10, 0.5, 1, 60, 5, 0)]


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="USD Metabolism Benchmark v2 — Phase 2 decision gate"
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT, help="CSV output path"
    )
    parser.add_argument(
        "--warmup-only",
        action="store_true",
        help="Run a single minimal config for timing calibration.",
    )
    parser.add_argument(
        "--prune",
        choices=["none", "small", "medium"],
        default="none",
        help="Pruned sweep variant.",
    )
    parser.add_argument(
        "--n-writes",
        type=int,
        default=DEFAULT_N_WRITES_PER_CONFIG,
        help="Writes per config.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print per-config progress.",
    )
    args = parser.parse_args()

    if args.warmup_only:
        configs = warmup_sweep()
    elif args.prune == "small":
        configs = small_sweep()
    elif args.prune == "medium":
        configs = medium_sweep()
    else:
        configs = full_sweep()

    print(f"USD Metabolism Benchmark v2", flush=True)
    print(f"  sweep       = {args.prune if not args.warmup_only else 'warmup'}", flush=True)
    print(f"  configs     = {len(configs)}", flush=True)
    print(f"  n_writes    = {args.n_writes}", flush=True)
    print(f"  output      = {args.output}", flush=True)
    print(f"  pxr.Usd ver = {Usd.GetVersion() if hasattr(Usd, 'GetVersion') else '?'}", flush=True)
    print(f"  python      = {sys.version.split()[0]}", flush=True)
    print(flush=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start_all = time.perf_counter()
    rows: List[MetricsRow] = []

    with tempfile.TemporaryDirectory(prefix="moneta_bench_") as tmp:
        tmp_root = Path(tmp)
        for i, cfg in enumerate(configs, 1):
            cfg_start = time.perf_counter()
            if args.progress or args.warmup_only:
                print(
                    f"[{i:3d}/{len(configs)}] "
                    f"b={cfg.batch_size:4d} r={cfg.structural_ratio:.1f} "
                    f"sl={cfg.sublayer_count:2d} hz={cfg.read_load_hz} "
                    f"shc={cfg.shadow_index_commit_ms:2d}ms "
                    f"acc={cfg.accumulated_layer_size:6d} ...",
                    end="",
                    flush=True,
                )
            try:
                row = run_config(cfg, tmp_root, args.n_writes)
                rows.append(row)
                if args.progress or args.warmup_only:
                    dt = time.perf_counter() - cfg_start
                    print(
                        f" {dt:6.2f}s "
                        f"write_lock_med={row.write_lock_ms_median:6.1f}ms "
                        f"p95_stall={row.p95_concurrent_read_stall_ms:6.1f}ms "
                        f"pcp_p95={row.pcp_rebuild_p95_ms:6.1f}ms "
                        f"hz={row.achieved_reader_hz:5.1f}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                if args.progress or args.warmup_only:
                    print(f" FAILED: {exc}", flush=True)
                import traceback
                traceback.print_exc()

    total_duration = time.perf_counter() - start_all
    print(flush=True)
    print(f"Total sweep duration: {total_duration:.1f}s ({total_duration/60:.1f} min)", flush=True)
    print(f"Mean per-config:      {total_duration/max(len(rows), 1):.2f}s", flush=True)

    # Write CSV
    if rows:
        with open(output_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(asdict(rows[0]).keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        print(f"Wrote {len(rows)} rows to {output_path}", flush=True)
    else:
        print("No rows collected — CSV not written.", flush=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
