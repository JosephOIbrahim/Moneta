"""End-to-end integration tests for the Moneta substrate.

Exercises the full wiring: deposit -> query -> signal_attention ->
run_sleep_pass -> consolidation -> manifest, against the live
ECS + vector_index + attention_log + consolidation + mock_usd_target
+ sequential_writer stack.

After the singleton surgery (DEEP_THINK_BRIEF_substrate_handle.md),
every substrate access goes through a :class:`Moneta` handle. Tests
that need the harness-level fast-forward (calling
``consolidation.run_pass(..., now=future)`` directly) read the same
substrate fields off the handle that they used to read off
``moneta_api._state``.

Design note — fast-forward via ``now`` parameter
------------------------------------------------
``consolidation.ConsolidationRunner.run_pass`` takes ``now`` as an
explicit parameter so tests can fast-forward time without
``time.sleep``. Several tests here construct a "future" timestamp and
call ``run_pass(..., now=future)`` directly to drive decay past the
selection thresholds in milliseconds of wall-clock time.

Staging requires a two-pass flow: pass 1 applies attention (which sets
``LastEvaluated = now`` on the reinforced entity), then pass 2 decays
from that point. A single pass cannot simultaneously apply attention
and decay-from-before-the-attention because the attention write resets
the decay clock — this is spec-correct per ARCHITECTURE.md §5 and §4.
"""
from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from moneta import Moneta, MonetaConfig
from moneta.types import EntityState


@pytest.fixture
def fast_decay_moneta() -> Iterator[Moneta]:
    """Yield a Moneta handle with a 60-second half-life for prune/stage tests."""
    with Moneta(MonetaConfig.ephemeral(half_life_seconds=60)) as substrate:
        yield substrate


# ---------------------------------------------------------------------
# Deposit / query basics end-to-end
# ---------------------------------------------------------------------


class TestDepositQueryRoundTrip:
    def test_single_deposit_retrievable(
        self, fresh_moneta: Moneta
    ) -> None:
        eid = fresh_moneta.deposit("hello world", [1.0, 0.0, 0.0])
        results = fresh_moneta.query([1.0, 0.0, 0.0])
        assert len(results) == 1
        assert results[0].entity_id == eid
        assert results[0].payload == "hello world"

    def test_deposit_writes_to_vector_index(
        self, fresh_moneta: Moneta
    ) -> None:
        """ARCHITECTURE.md §7: vector index is authoritative for what exists."""
        eid = fresh_moneta.deposit("x", [1.0, 0.0])
        assert fresh_moneta.vector_index.contains(eid)
        assert (
            fresh_moneta.vector_index.get_state(eid)
            == EntityState.VOLATILE
        )

    def test_multiple_deposits_ranked_by_similarity_and_utility(
        self, fresh_moneta: Moneta
    ) -> None:
        best = fresh_moneta.deposit("best", [1.0, 0.0])
        mid = fresh_moneta.deposit("mid", [0.9, 0.1])
        worst = fresh_moneta.deposit("worst", [0.0, 1.0])
        results = fresh_moneta.query([1.0, 0.0], limit=3)
        assert len(results) == 3
        assert [r.entity_id for r in results] == [best, mid, worst]


# ---------------------------------------------------------------------
# Signal attention -> sleep pass -> attended_count
# ---------------------------------------------------------------------


class TestAttentionFlow:
    def test_signal_attention_applied_only_after_sleep_pass(
        self, fresh_moneta: Moneta
    ) -> None:
        eid = fresh_moneta.deposit("x", [1.0, 0.0])
        fresh_moneta.signal_attention({eid: 0.3})
        # Before sleep pass
        assert fresh_moneta.query([1.0, 0.0])[0].attended_count == 0

        fresh_moneta.run_sleep_pass()
        # After sleep pass
        assert fresh_moneta.query([1.0, 0.0])[0].attended_count == 1

    def test_multiple_signals_aggregate_count(
        self, fresh_moneta: Moneta
    ) -> None:
        eid = fresh_moneta.deposit("x", [1.0, 0.0])
        fresh_moneta.signal_attention({eid: 0.1})
        fresh_moneta.signal_attention({eid: 0.1})
        fresh_moneta.signal_attention({eid: 0.1})
        fresh_moneta.run_sleep_pass()
        assert fresh_moneta.query([1.0, 0.0])[0].attended_count == 3


# ---------------------------------------------------------------------
# Prune path: low utility + low attention
# ---------------------------------------------------------------------


class TestPrunePath:
    def test_prune_removes_from_ecs_and_vector_index(
        self, fast_decay_moneta: Moneta
    ) -> None:
        m = fast_decay_moneta
        eid = m.deposit("ephemeral", [1.0, 0.0])

        future = time.time() + 900  # 15 half-lives — utility ~ 0

        result = m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=future,
        )
        assert result.pruned == 1
        assert result.staged == 0
        assert not m.ecs.contains(eid)
        assert not m.vector_index.contains(eid)

    def test_prune_skips_entities_above_threshold(
        self, fast_decay_moneta: Moneta
    ) -> None:
        m = fast_decay_moneta
        eid_fresh = m.deposit("fresh", [1.0, 0.0])

        result = m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=time.time() + 1.0,
        )
        assert result.pruned == 0
        assert m.ecs.contains(eid_fresh)


# ---------------------------------------------------------------------
# Stage path: low utility + >=3 attention signals
# ---------------------------------------------------------------------


class TestStagePath:
    def test_two_pass_staging_commits_to_mock_usd(
        self, fast_decay_moneta: Moneta
    ) -> None:
        """Two-pass flow: apply attention in pass 1, decay-and-stage in pass 2."""
        m = fast_decay_moneta
        eid = m.deposit("reinforced", [1.0, 0.0])
        m.signal_attention({eid: 0.01})
        m.signal_attention({eid: 0.01})
        m.signal_attention({eid: 0.01})

        t0 = time.time()

        # Pass 1 — apply attention. Utility caps at 1.0, attended_count -> 3.
        result1 = m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0,
        )
        assert result1.staged == 0
        assert result1.pruned == 0
        mem_after_pass1 = m.ecs.get_memory(eid)
        assert mem_after_pass1 is not None
        assert mem_after_pass1.attended_count == 3

        # Pass 2 — fast-forward. Utility decays past 0.3, attended_count still 3.
        future = t0 + 900  # 15 half-lives
        result2 = m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=future,
        )
        assert result2.staged == 1
        assert result2.pruned == 0
        assert result2.authored_at is not None

        # ECS state transitioned to CONSOLIDATED
        mem_after_pass2 = m.ecs.get_memory(eid)
        assert mem_after_pass2 is not None
        assert mem_after_pass2.state == EntityState.CONSOLIDATED

        # Vector index state transitioned to CONSOLIDATED
        assert m.vector_index.get_state(eid) == EntityState.CONSOLIDATED

        # Manifest is empty (entities moved to CONSOLIDATED, past STAGED)
        assert m.get_consolidation_manifest() == []

    def test_mock_usd_target_received_schema_compliant_batch(
        self, fast_decay_moneta: Moneta
    ) -> None:
        """Verify the JSONL log schema (mock_usd_target.py docstring)."""
        m = fast_decay_moneta
        eid = m.deposit("schema-check", [1.0, 0.0])
        for _ in range(3):
            m.signal_attention({eid: 0.01})

        t0 = time.time()
        m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0,
        )
        m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0 + 900,
        )

        assert m.mock_target is not None
        buffer = m.mock_target.get_ephemeral_buffer()
        assert len(buffer) == 1
        batch = buffer[0]

        # Top-level schema
        assert batch["schema_version"] == 1
        assert batch["target"] == "mock"
        assert isinstance(batch["authored_at"], float)
        assert isinstance(batch["batch_id"], str)
        assert isinstance(batch["entries"], list)
        assert len(batch["entries"]) == 1

        # Per-entry schema
        entry = batch["entries"][0]
        expected_keys = {
            "entity_id",
            "payload",
            "semantic_vector",
            "utility",
            "attended_count",
            "protected_floor",
            "last_evaluated",
            "prior_state",
            "target_sublayer",
        }
        assert set(entry.keys()) == expected_keys
        assert entry["entity_id"] == str(eid)
        assert entry["payload"] == "schema-check"
        assert entry["attended_count"] == 3
        assert entry["protected_floor"] == 0.0
        assert entry["target_sublayer"].startswith("cortex_")
        assert entry["target_sublayer"].endswith(".usda")
        assert isinstance(entry["prior_state"], int)

    def test_protected_floor_routes_to_protected_sublayer(
        self, fast_decay_moneta: Moneta
    ) -> None:
        """A protected entity stages to cortex_protected.usda per §8."""
        m = fast_decay_moneta
        eid = m.deposit("pinned", [1.0, 0.0], protected_floor=0.2)
        for _ in range(3):
            m.signal_attention({eid: 0.01})

        t0 = time.time()

        # Pass 1: apply attention. Utility caps at 1.0.
        m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0,
        )

        # Pass 2: fast-forward. Decay would drive utility to ~0, but the
        # protected_floor=0.2 clamp holds it at 0.2, which is below stage
        # threshold (0.3) and above prune threshold (0.1). attended_count=3
        # makes it qualify for staging.
        result = m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0 + 900,
        )
        assert result.staged == 1

        assert m.mock_target is not None
        buffer = m.mock_target.get_ephemeral_buffer()
        assert len(buffer) == 1
        entry = buffer[0]["entries"][0]
        assert entry["target_sublayer"] == "cortex_protected.usda"
        assert entry["protected_floor"] == 0.2


# ---------------------------------------------------------------------
# Dry-run (sequential_writer=None) preserves STAGED_FOR_SYNC state
# ---------------------------------------------------------------------


class TestDryRunClassify:
    def test_dry_run_reports_candidates_without_mutating_state(
        self, fast_decay_moneta: Moneta
    ) -> None:
        """``sequential_writer=None``: classify but do NOT mutate state.

        Per ``consolidation.ConsolidationRunner.run_pass`` docstring, a
        None writer means the classifier runs and the result's
        ``staged`` count reflects what WOULD stage, but the ECS state
        is not transitioned (no "stuck STAGED" hazard). Agents that
        want to preview selection without committing should use this
        pattern or call ``classify()`` directly.

        Prune, however, DOES happen in dry-run mode because pruning is
        a local ECS+vector delete with no USD involvement — the
        sequential writer is not on that path.
        """
        m = fast_decay_moneta
        eid = m.deposit("x", [1.0, 0.0])
        for _ in range(3):
            m.signal_attention({eid: 0.01})

        t0 = time.time()

        # Pass 1 via real sequential_writer (attention apply)
        m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0,
        )

        # Pass 2 — DRY-RUN: classify only, no state transition
        result = m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=None,
            now=t0 + 900,
        )
        assert result.staged == 1  # classified as stage candidate
        assert result.authored_at is None  # no commit attempted

        # State NOT mutated — still VOLATILE, not STAGED_FOR_SYNC
        mem = m.ecs.get_memory(eid)
        assert mem is not None
        assert mem.state == EntityState.VOLATILE

        # Manifest reflects actual ECS state — empty
        assert m.get_consolidation_manifest() == []

    def test_classify_finds_prune_and_stage_candidates_directly(
        self, fast_decay_moneta: Moneta
    ) -> None:
        """``classify()`` on its own surfaces both classification paths."""
        m = fast_decay_moneta

        # One entity to prune: low utility, no attention
        eid_prune = m.deposit("prune-me", [1.0, 0.0])

        # One entity to stage: low utility, >=3 attention signals
        eid_stage = m.deposit("stage-me", [0.0, 1.0])
        for _ in range(3):
            m.signal_attention({eid_stage: 0.01})

        t0 = time.time()

        # Pass 1 to apply the attention to eid_stage.
        m.consolidation.run_pass(
            ecs=m.ecs,
            decay=m.decay,
            attention_log=m.attention,
            vector_index=m.vector_index,
            sequential_writer=m.sequential_writer,
            now=t0,
        )

        # Fast-forward decay outside the reducer.
        m.ecs.decay_all(m.decay.lambda_, t0 + 900)

        prune_ids, stage_ids = m.consolidation.classify(m.ecs)
        assert eid_prune in prune_ids
        assert eid_stage in stage_ids
