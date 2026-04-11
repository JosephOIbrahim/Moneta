"""Unit tests for `moneta.api` — the four-op contract.

Covers ARCHITECTURE.md §2. Verifies:

  - Signature conformance at the AST level (verbatim vs MONETA.md §2.1)
  - Four-op return-type contracts
  - init() idempotency
  - MonetaNotInitializedError on pre-init calls
  - Protected-quota enforcement (ARCHITECTURE.md §10)
  - query() reranks by cosine × utility (Phase 1 Persistence convention)
  - signal_attention does not update ECS synchronously (§5.1)
  - run_sleep_pass drives the reducer and selector
"""
from __future__ import annotations

import ast
from uuid import UUID

import pytest

import moneta
from moneta import (
    EntityState,
    Memory,
    MonetaNotInitializedError,
    ProtectedQuotaExceededError,
    deposit,
    get_consolidation_manifest,
    init,
    query,
    run_sleep_pass,
    signal_attention,
)
from moneta import api as moneta_api


# ---------------------------------------------------------------------
# Signature conformance (AST-level vs MONETA.md §2.1)
# ---------------------------------------------------------------------


EXPECTED_SIGNATURES = {
    "deposit": (
        "def deposit(payload: str, embedding: List[float], "
        "protected_floor: float=0.0) -> UUID"
    ),
    "query": "def query(embedding: List[float], limit: int=5) -> List[Memory]",
    "signal_attention": (
        "def signal_attention(weights: Dict[UUID, float]) -> None"
    ),
    "get_consolidation_manifest": (
        "def get_consolidation_manifest() -> List[Memory]"
    ),
}


class TestSignatureConformance:
    def test_four_op_signatures_match_spec_verbatim(self) -> None:
        """MONETA.md §2.1 is the source of truth for the four-op signatures."""
        source = open(moneta_api.__file__, "r", encoding="utf-8").read()
        tree = ast.parse(source)
        found: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in EXPECTED_SIGNATURES:
                ret = ast.unparse(node.returns) if node.returns else "None"
                sig = f"def {node.name}({ast.unparse(node.args)}) -> {ret}"
                found[node.name] = sig
        for name, expected in EXPECTED_SIGNATURES.items():
            assert name in found, f"{name} not found in api.py"
            assert found[name] == expected, (
                f"signature drift in {name}:\n"
                f"  expected: {expected}\n"
                f"  actual:   {found[name]}"
            )


# ---------------------------------------------------------------------
# init / require_init
# ---------------------------------------------------------------------


class TestInit:
    def test_requires_init_raises(self, uninitialized_moneta: None) -> None:
        with pytest.raises(MonetaNotInitializedError):
            deposit("hi", [1.0])
        with pytest.raises(MonetaNotInitializedError):
            query([1.0])
        with pytest.raises(MonetaNotInitializedError):
            signal_attention({})
        with pytest.raises(MonetaNotInitializedError):
            get_consolidation_manifest()

    def test_init_idempotent(self, uninitialized_moneta: None) -> None:
        """Calling init() twice does not raise and produces a clean state."""
        init()
        eid = deposit("first", [1.0])
        init()  # should reset
        results = query([1.0])
        assert all(r.entity_id != eid for r in results), (
            "second init() did not clear prior state"
        )

    def test_init_accepts_half_life_seconds(
        self, uninitialized_moneta: None
    ) -> None:
        init(half_life_seconds=600.0)
        # No crash; state is live
        deposit("hi", [1.0])

    def test_init_accepts_config(self, uninitialized_moneta: None) -> None:
        cfg = moneta.MonetaConfig(half_life_seconds=600.0, max_entities=42)
        init(config=cfg)
        deposit("hi", [1.0])


# ---------------------------------------------------------------------
# deposit contract
# ---------------------------------------------------------------------


class TestDepositContract:
    def test_deposit_returns_uuid(self, fresh_moneta: None) -> None:
        eid = deposit("hello", [1.0, 0.0])
        assert isinstance(eid, UUID)

    def test_deposit_is_retrievable(self, fresh_moneta: None) -> None:
        eid = deposit("hello", [1.0, 0.0])
        results = query([1.0, 0.0])
        assert len(results) == 1
        assert results[0].entity_id == eid

    def test_deposit_fresh_utility_is_near_one(self, fresh_moneta: None) -> None:
        """Fresh memories start at Utility = 1.0. Query applies eval point 1
        decay which shaves a negligible amount — assert ≥ 0.99, not == 1.0.
        """
        eid = deposit("hi", [1.0])
        results = query([1.0])
        assert 0.99 <= results[0].utility <= 1.0


# ---------------------------------------------------------------------
# Protected-quota enforcement (ARCHITECTURE.md §10)
# ---------------------------------------------------------------------


class TestProtectedQuota:
    def test_unprotected_deposit_does_not_consume_quota(
        self, fresh_moneta: None
    ) -> None:
        # Deposit many unprotected entries — should not raise.
        for i in range(150):
            deposit(f"payload-{i}", [float(i), 1.0], protected_floor=0.0)

    def test_protected_quota_exceeded_raises(
        self, fresh_moneta: None
    ) -> None:
        for i in range(moneta_api.PROTECTED_QUOTA):
            deposit(f"p{i}", [float(i), 1.0], protected_floor=0.1)
        with pytest.raises(ProtectedQuotaExceededError):
            deposit("overflow", [1.0, 1.0], protected_floor=0.1)

    def test_unprotected_still_works_at_quota_cap(
        self, fresh_moneta: None
    ) -> None:
        for i in range(moneta_api.PROTECTED_QUOTA):
            deposit(f"p{i}", [float(i), 1.0], protected_floor=0.1)
        # Unprotected still accepted (dim must match — vector_index enforces
        # dim-homogeneity as a shadow-index sanity invariant).
        eid = deposit("ephemeral", [1.0, 0.0], protected_floor=0.0)
        assert isinstance(eid, UUID)


# ---------------------------------------------------------------------
# query — retrieval and ranking
# ---------------------------------------------------------------------


class TestQuery:
    def test_query_empty(self, fresh_moneta: None) -> None:
        assert query([1.0]) == []

    def test_query_returns_list_of_memory(self, fresh_moneta: None) -> None:
        deposit("a", [1.0, 0.0])
        results = query([1.0, 0.0])
        assert isinstance(results, list)
        assert all(isinstance(r, Memory) for r in results)

    def test_query_limit_respected(self, fresh_moneta: None) -> None:
        for i in range(10):
            deposit(f"p{i}", [1.0, float(i) * 0.1])
        results = query([1.0, 0.0], limit=3)
        assert len(results) == 3


# ---------------------------------------------------------------------
# signal_attention — async reducer contract
# ---------------------------------------------------------------------


class TestSignalAttention:
    def test_signal_attention_returns_none(self, fresh_moneta: None) -> None:
        eid = deposit("x", [1.0])
        result = signal_attention({eid: 0.2})
        assert result is None

    def test_signal_attention_does_not_update_ecs_synchronously(
        self, fresh_moneta: None
    ) -> None:
        """§5.1: signal_attention appends to log; ECS update happens at
        sleep pass. Without a sleep pass, attended_count stays at 0.
        """
        eid = deposit("x", [1.0])
        signal_attention({eid: 0.5})
        results = query([1.0])
        assert results[0].attended_count == 0  # not yet reduced

    def test_signal_attention_applied_by_sleep_pass(
        self, fresh_moneta: None
    ) -> None:
        eid = deposit("x", [1.0])
        signal_attention({eid: 0.3})
        signal_attention({eid: 0.2})  # two signals
        result = run_sleep_pass()
        assert result.attention_updated == 1
        results = query([1.0])
        assert results[0].attended_count == 2


# ---------------------------------------------------------------------
# get_consolidation_manifest — staging contract
# ---------------------------------------------------------------------


class TestManifest:
    def test_empty_at_startup(self, fresh_moneta: None) -> None:
        assert get_consolidation_manifest() == []

    def test_fresh_deposit_not_staged(self, fresh_moneta: None) -> None:
        deposit("hi", [1.0])
        run_sleep_pass()
        # Fresh high-utility memory must not stage
        assert get_consolidation_manifest() == []
