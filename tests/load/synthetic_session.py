"""Phase 1 synthetic session harness — completion gate.

MONETA.md §4: "Phase 1 is complete when an agent can run a 30-minute
synthetic session producing realistic deposit/query/attention patterns
and the system survives it."

This harness drives Moneta through a simulated 30-minute session using a
patched `moneta.api.time` namespace — real wall-clock runtime is ~1
second. At the end it emits a metrics report and asserts the
completion-gate thresholds approved in Pass 4.

STATUS: Pass 5 FINAL — Phase 1 completion gate
-----------------------------------------------
Pass 4 closed with Joseph's rulings on Tier 1 + Tier 2 thresholds.
This file carries two tests:

- `test_phase1_synthetic_session_completion_gate` runs Tier 1 —
  architectural invariants + hard deterministic facts. Primary
  completion gate; runs on the default pytest discovery path.
- `test_phase1_synthetic_session_completion_gate_load` runs Tier 1
  plus Tier 2 canonical-range assertions. Marked `@pytest.mark.load`
  for target runs via `pytest -m load`.

Seeding discipline (critical — surfaced during Pass 4)
------------------------------------------------------
`_embed` seeds its Random instance from `hashlib.md5`, NOT Python's
built-in `hash()`. Python's `hash()` for strings is randomized per
process by default (PYTHONHASHSEED), and using it to seed randomness
would make the session non-reproducible across process starts. Pass 4
surfaced this gotcha during threshold proposal — initial runs showed
pruned/staged counts of 13/10, 14/13, 15/13, 15/11, 8/9 across five
back-to-back invocations. Switching to hashlib collapsed the variance
to zero.

RULE: any test that seeds randomness from a string must use `hashlib`
(or a literal int), never `hash()`. See `docs/testing.md` (Documentarian
follow-up from Pass 4) for the externalized version of this rule.

Session pattern (per the Pass 4 authorization)
----------------------------------------------
1. **Research burst** (0 → 30s): ~50 deposits, no queries, no attention.
   Simulates an agent consuming a document.
2. **Conversation** (30s → ~14m30s): ~5 deposits/min, ~10 queries/min,
   attention on top-2 results per query. Simulates an agent in dialogue.
3. **Idle jump** (+5m virtual): simulates the agent walking away.
4. **Context switch** (30s): query burst against stale memories.
5. **Recall** (60s): repeated queries for a single concept, reinforcing
   its matches.
6. **Consolidation cycles**: 3 sleep passes at natural phase boundaries.

Virtual clock
-------------
`moneta.api.time` is replaced with a `SimpleNamespace(time=clock.time)`
for the duration of `run_session_internal`. All internal `time.time()`
calls in the api layer see the virtual clock. Consolidation's run_pass
accepts `now` as an explicit parameter, so the reducer + decay points
also see virtual time via api.run_sleep_pass's `now = time.time()`.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import List
from uuid import UUID

import pytest

import moneta
import moneta.api as moneta_api
from moneta import MonetaConfig


# ---------------------------------------------------------------------
# Virtual clock
# ---------------------------------------------------------------------


class VirtualClock:
    """Monotonic virtual clock for session pacing."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------


@dataclass
class PassSnapshot:
    pass_index: int
    wall_clock_offset: float
    attention_updated: int
    pruned: int
    staged: int
    ecs_n_before: int
    ecs_n_after: int
    manifest_size: int


@dataclass
class SessionMetrics:
    total_deposits: int = 0
    total_queries: int = 0
    total_attention_signals: int = 0
    max_ecs_size: int = 0
    pass_snapshots: List[PassSnapshot] = field(default_factory=list)
    final_ecs_n: int = 0
    final_attended_count_distribution: dict = field(default_factory=dict)
    final_utility_distribution: dict = field(default_factory=dict)
    total_pruned: int = 0
    total_staged: int = 0


# ---------------------------------------------------------------------
# Deterministic pseudo-embedder
# ---------------------------------------------------------------------


DIM = 16
TOPICS = [
    "compilers",
    "gpu",
    "usd",
    "decay",
    "vector-db",
    "consolidation",
    "protocol",
    "memory",
    "agents",
    "openusd",
]


def _embed(topic: str, variant: int = 0) -> List[float]:
    """Deterministic normalized pseudo-embedding keyed on (topic, variant).

    Uses hashlib.md5 instead of Python's built-in `hash()` because `hash()`
    is randomized per-process by default (PYTHONHASHSEED) — any use of
    `hash()` for seeding would make the session non-reproducible across
    runs. This subtle bug surfaced during Pass 4 harness development and
    is worth noting: ANY test that seeds randomness from string hashes
    must use hashlib (or a fixed-seed substitute), never `hash()`.
    """
    key = f"{topic}:{variant}".encode("utf-8")
    seed = int.from_bytes(hashlib.md5(key).digest()[:4], "little")
    rng = random.Random(seed)
    raw = [rng.gauss(0.0, 1.0) for _ in range(DIM)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


# ---------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------


def _phase_research_burst(
    clock: VirtualClock, metrics: SessionMetrics
) -> List[UUID]:
    """~50 deposits in ~30 seconds, no queries, no attention."""
    deposited: List[UUID] = []
    for i in range(50):
        eid = moneta.deposit(
            payload=f"research note {i} about {TOPICS[i % len(TOPICS)]}",
            embedding=_embed(TOPICS[i % len(TOPICS)], variant=i),
        )
        deposited.append(eid)
        metrics.total_deposits += 1
        clock.advance(0.6)  # 50 deposits / 30 seconds
    return deposited


def _phase_conversation(
    clock: VirtualClock,
    metrics: SessionMetrics,
    known: List[UUID],
    duration_seconds: float,
) -> None:
    """~5 deposits/min, ~10 queries/min, attention on top-2 results."""
    rng = random.Random(42)
    elapsed = 0.0
    while elapsed < duration_seconds:
        # Deposit rate ~5/min = P(1 per second) = 1/12
        if rng.random() < (1.0 / 12.0):
            topic = rng.choice(TOPICS)
            eid = moneta.deposit(
                payload=f"conversation about {topic}",
                embedding=_embed(topic, variant=rng.randrange(1000)),
            )
            known.append(eid)
            metrics.total_deposits += 1

        # Query rate ~10/min = P(1 per second) = 1/6
        if rng.random() < (1.0 / 6.0):
            topic = rng.choice(TOPICS)
            results = moneta.query(
                _embed(topic, variant=rng.randrange(1000)), limit=3
            )
            metrics.total_queries += 1
            if results:
                weights = {r.entity_id: 0.15 for r in results[:2]}
                moneta.signal_attention(weights)
                metrics.total_attention_signals += len(weights)

        clock.advance(1.0)
        elapsed += 1.0
        state = moneta_api._state
        if state is not None:
            metrics.max_ecs_size = max(metrics.max_ecs_size, state.ecs.n)


def _phase_context_switch(
    clock: VirtualClock, metrics: SessionMetrics
) -> None:
    """15 queries at 2s intervals — surface decayed memories."""
    rng = random.Random(7)
    for _ in range(15):
        topic = rng.choice(TOPICS)
        moneta.query(_embed(topic, variant=rng.randrange(1000)), limit=5)
        metrics.total_queries += 1
        clock.advance(2.0)


def _phase_recall(
    clock: VirtualClock, metrics: SessionMetrics, target_topic: str
) -> None:
    """20 queries for the same concept at 3s intervals, reinforcing top hit."""
    for _ in range(20):
        results = moneta.query(_embed(target_topic, variant=0), limit=3)
        metrics.total_queries += 1
        if results:
            moneta.signal_attention({results[0].entity_id: 0.1})
            metrics.total_attention_signals += 1
        clock.advance(3.0)


def _take_pass_snapshot(
    clock: VirtualClock,
    metrics: SessionMetrics,
    session_start: float,
) -> PassSnapshot:
    state = moneta_api._state
    assert state is not None
    n_before = state.ecs.n
    result = moneta.run_sleep_pass()
    n_after = state.ecs.n
    manifest = moneta.get_consolidation_manifest()
    snapshot = PassSnapshot(
        pass_index=len(metrics.pass_snapshots) + 1,
        wall_clock_offset=clock.time() - session_start,
        attention_updated=result.attention_updated,
        pruned=result.pruned,
        staged=result.staged,
        ecs_n_before=n_before,
        ecs_n_after=n_after,
        manifest_size=len(manifest),
    )
    metrics.pass_snapshots.append(snapshot)
    metrics.total_pruned += result.pruned
    metrics.total_staged += result.staged
    return snapshot


# ---------------------------------------------------------------------
# Session driver
# ---------------------------------------------------------------------


def run_session_internal(clock: VirtualClock) -> SessionMetrics:
    """Run the synthetic session against a preinstalled virtual clock.

    Caller is responsible for installing `moneta.api.time` (via
    `monkeypatch.setattr` in pytest, or direct assignment with manual
    restoration in a CLI entry point).
    """
    random.seed(1337)
    metrics = SessionMetrics()
    session_start = clock.time()

    moneta_api._reset_state()
    # 5-minute half-life — short enough to exercise decay through a
    # 30-minute virtual session, long enough that fresh deposits aren't
    # aggressively pruned by the first sleep pass.
    moneta.init(
        config=MonetaConfig(half_life_seconds=300.0, max_entities=10_000)
    )

    known: List[UUID] = []

    # Phase 1 — research burst (0 → 30s)
    research_ids = _phase_research_burst(clock, metrics)
    known.extend(research_ids)

    # Sleep pass 1 — immediately after burst
    _take_pass_snapshot(clock, metrics, session_start)

    # Phase 2 — conversation (30s → ~14m30s)
    _phase_conversation(
        clock, metrics, known, duration_seconds=14 * 60
    )

    # Sleep pass 2 — mid session
    _take_pass_snapshot(clock, metrics, session_start)

    # Phase 3 — idle jump + context switch (+5m virtual)
    clock.advance(5 * 60)
    _phase_context_switch(clock, metrics)

    # Phase 4 — recall (reinforce one topic)
    _phase_recall(clock, metrics, target_topic=TOPICS[0])

    # Sleep pass 3 — late session
    _take_pass_snapshot(clock, metrics, session_start)

    # Final distribution capture
    state = moneta_api._state
    assert state is not None
    metrics.final_ecs_n = state.ecs.n
    attended_hist: dict[int, int] = {}
    util_hist: dict[float, int] = {}
    for memory in state.ecs.iter_rows():
        attended_hist[memory.attended_count] = (
            attended_hist.get(memory.attended_count, 0) + 1
        )
        u_bucket = round(memory.utility, 2)
        util_hist[u_bucket] = util_hist.get(u_bucket, 0) + 1
    metrics.final_attended_count_distribution = attended_hist
    metrics.final_utility_distribution = util_hist

    return metrics


def run_synthetic_session() -> SessionMetrics:
    """CLI entry point — installs the clock, runs, restores on cleanup."""
    clock = VirtualClock()
    original_time = moneta_api.time
    moneta_api.time = SimpleNamespace(time=clock.time)
    try:
        return run_session_internal(clock)
    finally:
        moneta_api.time = original_time
        moneta_api._reset_state()


# ---------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------


def format_report(metrics: SessionMetrics) -> str:
    lines = [
        "=" * 64,
        "Phase 1 Synthetic Session — Metrics Report",
        "=" * 64,
        f"Total deposits        : {metrics.total_deposits}",
        f"Total queries         : {metrics.total_queries}",
        f"Total attention sigs  : {metrics.total_attention_signals}",
        f"Max ECS size          : {metrics.max_ecs_size}",
        f"Final ECS size        : {metrics.final_ecs_n}",
        f"Total pruned          : {metrics.total_pruned}",
        f"Total staged          : {metrics.total_staged}",
        "",
        "Sleep pass snapshots:",
    ]
    for snap in metrics.pass_snapshots:
        lines.append(
            f"  pass {snap.pass_index} @ {snap.wall_clock_offset:8.1f}s: "
            f"attended={snap.attention_updated:4d} "
            f"pruned={snap.pruned:4d} staged={snap.staged:3d} "
            f"n_before={snap.ecs_n_before:5d} n_after={snap.ecs_n_after:5d} "
            f"manifest={snap.manifest_size:3d}"
        )
    lines.append("")
    lines.append("Final attended_count distribution:")
    for k in sorted(metrics.final_attended_count_distribution.keys()):
        lines.append(
            f"  attended={k}: {metrics.final_attended_count_distribution[k]} entities"
        )
    lines.append("")
    lines.append("Final utility distribution (rounded to 0.01):")
    for k in sorted(metrics.final_utility_distribution.keys()):
        lines.append(
            f"  u={k:4.2f}: {metrics.final_utility_distribution[k]} entities"
        )
    lines.append("=" * 64)
    return "\n".join(lines)


# ---------------------------------------------------------------------
# Completion-gate assertions — Pass 4 approved thresholds
# ---------------------------------------------------------------------


def _assert_tier1(metrics: SessionMetrics) -> None:
    """Tier 1 — architectural invariants + hard deterministic facts.

    Approved in Pass 4 rulings as-is (all 14 assertions). Runs on the
    default pytest discovery path as the primary Phase 1 completion
    gate.
    """
    # Sleep pass count — exactly 3 per the session pattern.
    assert len(metrics.pass_snapshots) == 3, (
        f"expected 3 sleep passes, got {len(metrics.pass_snapshots)}"
    )

    # Non-empty session smoke.
    assert metrics.total_deposits > 0
    assert metrics.total_queries > 0

    # Max-size invariant: no pre-pruning before the session maximum.
    assert metrics.max_ecs_size == metrics.total_deposits, (
        f"max_ecs_size={metrics.max_ecs_size} "
        f"!= total_deposits={metrics.total_deposits}"
    )

    # Final-size invariant: staged entities stay in ECS as CONSOLIDATED,
    # only prunes remove from ECS.
    assert metrics.final_ecs_n == metrics.total_deposits - metrics.total_pruned, (
        f"final_ecs_n={metrics.final_ecs_n} "
        f"!= deposits ({metrics.total_deposits}) - pruned ({metrics.total_pruned})"
    )

    # Pass 1: fresh burst, no effects.
    p1 = metrics.pass_snapshots[0]
    assert p1.attention_updated == 0, (
        f"pass 1 attention updates: expected 0, got {p1.attention_updated}"
    )
    assert p1.pruned == 0
    assert p1.staged == 0
    assert p1.ecs_n_before == 50, (
        f"burst size: expected 50, got {p1.ecs_n_before}"
    )

    # Pass 2: conversation phase keeps entities fresh via query-path decay
    # + attention boosts; no prunes, no stages.
    p2 = metrics.pass_snapshots[1]
    assert p2.pruned == 0, f"unexpected prunes at pass 2: {p2.pruned}"
    assert p2.staged == 0, f"unexpected stages at pass 2: {p2.staged}"

    # All pass manifests empty — commit transitions STAGED→CONSOLIDATED
    # in-pass, so manifest drains at every boundary.
    manifest_sizes = [s.manifest_size for s in metrics.pass_snapshots]
    assert all(size == 0 for size in manifest_sizes), (
        f"manifest should drain after commit at every pass, got {manifest_sizes}"
    )

    # Both consolidation paths fire at least once across the session.
    assert metrics.total_pruned >= 1, "session should exercise prune path"
    assert metrics.total_staged >= 1, "session should exercise stage path"


def _assert_tier2(metrics: SessionMetrics) -> None:
    """Tier 2 — canonical deterministic values + approved ranges.

    Approved in Pass 4 rulings with three modifications from the
    original proposal:
      - DROPPED: the "u=0.12 bucket count in [20,35]" assertion
        (too brittle; kept as qualitative note in the harness docstring
        and this module's metrics histogram only).
      - LOOSENED: total_attention_signals from [290,294] to [280,304].
      - LOOSENED: pass_snapshots[1].attention_updated from [88,100] to
        [85,105].
    """
    # Exact canonical totals — deterministic under fixed seed + hashlib embedder.
    assert metrics.total_deposits == 107, (
        f"canonical deposit count 107, got {metrics.total_deposits}"
    )
    assert metrics.total_queries == 171, (
        f"canonical query count 171, got {metrics.total_queries}"
    )
    assert 280 <= metrics.total_attention_signals <= 304, (
        f"attention signals outside [280,304]: "
        f"{metrics.total_attention_signals}"
    )

    # Pass 2 — load-test-sensitive range for distinct-entity reach.
    p2 = metrics.pass_snapshots[1]
    assert p2.ecs_n_before == 107, (
        f"pass 2 n_before: expected 107, got {p2.ecs_n_before}"
    )
    assert 85 <= p2.attention_updated <= 105, (
        f"pass 2 attention_updated outside [85,105]: {p2.attention_updated}"
    )

    # Pass 3 — consolidation fires here.
    p3 = metrics.pass_snapshots[2]
    assert p3.ecs_n_before == 107, (
        f"pass 3 n_before: expected 107, got {p3.ecs_n_before}"
    )
    assert p3.attention_updated == 1, (
        f"recall phase should reinforce exactly 1 distinct entity; "
        f"got {p3.attention_updated}"
    )
    assert 8 <= p3.pruned <= 16, (
        f"pass 3 pruned outside [8,16]: {p3.pruned}"
    )
    assert 5 <= p3.staged <= 13, (
        f"pass 3 staged outside [5,13]: {p3.staged}"
    )

    # Pass 1 and pass 2 both zero; pass 3 accounts for all totals.
    assert metrics.total_pruned == p3.pruned
    assert metrics.total_staged == p3.staged

    # Recall phase reinforces a single entity up to utility = 1.0 exactly.
    assert max(metrics.final_attended_count_distribution.keys()) >= 10, (
        "recall phase should produce at least one heavily attended entity"
    )
    at_u1 = metrics.final_utility_distribution.get(1.00, 0)
    assert at_u1 == 1, (
        f"recall should cap exactly 1 entity at u=1.0; found {at_u1}"
    )


# ---------------------------------------------------------------------
# Pytest entry points
# ---------------------------------------------------------------------


def test_phase1_synthetic_session_completion_gate(monkeypatch) -> None:
    """Phase 1 completion gate — Tier 1 architectural invariants.

    MONETA.md §4: "Phase 1 is complete when an agent can run a
    30-minute synthetic session producing realistic deposit/query/
    attention patterns and the system survives it."

    This test is the primary completion gate. It runs on the default
    pytest discovery path. The @pytest.mark.load sibling test
    `test_phase1_synthetic_session_completion_gate_load` adds Tier 2
    canonical-range assertions.
    """
    clock = VirtualClock()
    monkeypatch.setattr(
        moneta_api, "time", SimpleNamespace(time=clock.time)
    )
    try:
        metrics = run_session_internal(clock)
        print()
        print(format_report(metrics))
        _assert_tier1(metrics)
    finally:
        moneta_api._reset_state()


@pytest.mark.load
def test_phase1_synthetic_session_completion_gate_load(monkeypatch) -> None:
    """Phase 1 completion gate — Tier 1 + Tier 2 canonical ranges.

    Marked `@pytest.mark.load`. Runs on default pytest discovery AND
    is selectable via `pytest -m load`. Contains all Tier 1 assertions
    plus the Tier 2 deterministic-value and range assertions approved
    in Pass 4.
    """
    clock = VirtualClock()
    monkeypatch.setattr(
        moneta_api, "time", SimpleNamespace(time=clock.time)
    )
    try:
        metrics = run_session_internal(clock)
        print()
        print(format_report(metrics))
        _assert_tier1(metrics)
        _assert_tier2(metrics)
    finally:
        moneta_api._reset_state()


# ---------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------


if __name__ == "__main__":
    metrics = run_synthetic_session()
    print(format_report(metrics))
