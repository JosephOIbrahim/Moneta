"""Unit tests for ``moneta.Moneta`` — the four-op contract.

Covers ARCHITECTURE.md §2. After the singleton surgery
(DEEP_THINK_BRIEF_substrate_handle.md §5.1), the four operations live as
methods on the :class:`Moneta` handle. Signatures are verbatim from
MONETA.md §2.1; only the receiver (``self``) changes — param names,
types, defaults, and return types are untouched.

Verifies:

  - Method signature conformance at the AST level (verbatim vs
    MONETA.md §2.1 modulo the OO receiver)
  - Four-op return-type contracts
  - ``Moneta()`` with no args raises ``TypeError`` (no-arg trap, §5.3)
  - Two handles on the same ``storage_uri`` raise
    :class:`MonetaResourceLockedError` (§5.4)
  - Protected-quota enforcement uses the handle's
    ``config.quota_override`` (ARCHITECTURE.md §10)
  - ``query()`` reranks by cosine x utility
  - ``signal_attention`` does not update ECS synchronously (§5.1)
  - ``run_sleep_pass`` drives the reducer and selector
"""
from __future__ import annotations

import ast
from uuid import UUID

import pytest

from moneta import (
    Memory,
    Moneta,
    MonetaConfig,
    MonetaResourceLockedError,
    ProtectedQuotaExceededError,
)
from moneta import api as moneta_api

# ---------------------------------------------------------------------
# Signature conformance (AST-level vs MONETA.md §2.1)
# ---------------------------------------------------------------------


# Per the surgery, signatures pick up ``self`` as the receiver. Param
# names, types, defaults, and return types are otherwise verbatim from
# MONETA.md §2.1.
EXPECTED_SIGNATURES = {
    "deposit": (
        "def deposit(self, payload: str, embedding: List[float], "
        "protected_floor: float=0.0) -> UUID"
    ),
    "query": (
        "def query(self, embedding: List[float], "
        "limit: int=5) -> List[Memory]"
    ),
    "signal_attention": (
        "def signal_attention(self, weights: Dict[UUID, float]) -> None"
    ),
    "get_consolidation_manifest": (
        "def get_consolidation_manifest(self) -> List[Memory]"
    ),
}


class TestSignatureConformance:
    def test_four_op_signatures_match_spec_verbatim(self) -> None:
        """MONETA.md §2.1 is the source of truth for the four-op signatures.

        Walks the ``Moneta`` class body and asserts each four-op method
        matches the locked signature. ``self`` is added as the receiver
        for the OO migration; everything else is verbatim.
        """
        source = open(moneta_api.__file__, encoding="utf-8").read()
        tree = ast.parse(source)

        moneta_class: ast.ClassDef | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Moneta":
                moneta_class = node
                break
        assert moneta_class is not None, "class Moneta not found in api.py"

        found: dict[str, str] = {}
        for item in moneta_class.body:
            if (
                isinstance(item, ast.FunctionDef)
                and item.name in EXPECTED_SIGNATURES
            ):
                ret = ast.unparse(item.returns) if item.returns else "None"
                sig = (
                    f"def {item.name}({ast.unparse(item.args)}) -> {ret}"
                )
                found[item.name] = sig

        for name, expected in EXPECTED_SIGNATURES.items():
            assert name in found, f"{name} not found on Moneta"
            assert found[name] == expected, (
                f"signature drift in Moneta.{name}:\n"
                f"  expected: {expected}\n"
                f"  actual:   {found[name]}"
            )


# ---------------------------------------------------------------------
# Constructor contract — no-arg trap + URI lock (§5.3, §5.4)
# ---------------------------------------------------------------------


class TestConstructor:
    def test_no_arg_construction_raises_type_error(self) -> None:
        """§5.3 'no-arg trap': ``Moneta()`` must raise ``TypeError``."""
        with pytest.raises(TypeError):
            Moneta()  # type: ignore[call-arg]

    def test_two_handles_same_uri_raise_resource_locked(self) -> None:
        """§5.4 invariant: two live handles on the same storage_uri
        must collide synchronously at the second constructor call."""
        config = MonetaConfig(storage_uri="moneta-test://api/lock-collision")
        with Moneta(config) as _m1:
            with pytest.raises(MonetaResourceLockedError):
                Moneta(config)

    def test_uri_lock_releases_on_close(self) -> None:
        """After close, the URI may be re-acquired by a fresh handle."""
        config = MonetaConfig(storage_uri="moneta-test://api/lock-recycle")
        m1 = Moneta(config)
        m1.close()
        # No leak: a new handle on the same URI succeeds.
        with Moneta(config) as _m2:
            pass

    def test_close_is_idempotent(self) -> None:
        config = MonetaConfig(storage_uri="moneta-test://api/idempotent")
        m = Moneta(config)
        m.close()
        m.close()  # second close is a no-op


# ---------------------------------------------------------------------
# deposit contract
# ---------------------------------------------------------------------


class TestDepositContract:
    def test_deposit_returns_uuid(self, fresh_moneta: Moneta) -> None:
        eid = fresh_moneta.deposit("hello", [1.0, 0.0])
        assert isinstance(eid, UUID)

    def test_deposit_is_retrievable(self, fresh_moneta: Moneta) -> None:
        eid = fresh_moneta.deposit("hello", [1.0, 0.0])
        results = fresh_moneta.query([1.0, 0.0])
        assert len(results) == 1
        assert results[0].entity_id == eid

    def test_deposit_fresh_utility_is_near_one(
        self, fresh_moneta: Moneta
    ) -> None:
        """Fresh memories start at Utility = 1.0. Query applies eval point 1
        decay which shaves a negligible amount — assert >= 0.99, not == 1.0.
        """
        fresh_moneta.deposit("hi", [1.0])
        results = fresh_moneta.query([1.0])
        assert 0.99 <= results[0].utility <= 1.0


# ---------------------------------------------------------------------
# Protected-quota enforcement (ARCHITECTURE.md §10)
# ---------------------------------------------------------------------


class TestProtectedQuota:
    def test_unprotected_deposit_does_not_consume_quota(
        self, fresh_moneta: Moneta
    ) -> None:
        for i in range(150):
            fresh_moneta.deposit(
                f"payload-{i}", [float(i), 1.0], protected_floor=0.0
            )

    def test_protected_quota_exceeded_raises(
        self, fresh_moneta: Moneta
    ) -> None:
        for i in range(fresh_moneta.config.quota_override):
            fresh_moneta.deposit(
                f"p{i}", [float(i), 1.0], protected_floor=0.1
            )
        with pytest.raises(ProtectedQuotaExceededError):
            fresh_moneta.deposit(
                "overflow", [1.0, 1.0], protected_floor=0.1
            )

    def test_unprotected_still_works_at_quota_cap(
        self, fresh_moneta: Moneta
    ) -> None:
        for i in range(fresh_moneta.config.quota_override):
            fresh_moneta.deposit(
                f"p{i}", [float(i), 1.0], protected_floor=0.1
            )
        eid = fresh_moneta.deposit(
            "ephemeral", [1.0, 0.0], protected_floor=0.0
        )
        assert isinstance(eid, UUID)

    def test_concurrent_protected_deposits_respect_quota(
        self, fresh_moneta: Moneta
    ) -> None:
        """Concurrent protected deposits must not exceed §10 hard cap.

        Without the deposit-lock the count_protected → ecs.add window is a
        TOCTOU: two threads at quota-1 can both observe count=quota-1 and
        both call ecs.add, yielding count=quota+1. This test fires N=20
        threads issuing protected deposits when the count is at quota-1
        and asserts exactly one succeeds and N-1 raise. Regression for
        review finding substrate-L2-protected-quota-count-then-add-toctou.
        """
        import threading

        # Fill to one slot below quota.
        for i in range(fresh_moneta.config.quota_override - 1):
            fresh_moneta.deposit(
                f"p{i}", [float(i), 1.0], protected_floor=0.1
            )

        n_threads = 20
        successes: list[UUID] = []
        successes_lock = threading.Lock()
        failures: list[Exception] = []
        failures_lock = threading.Lock()
        ready_barrier = threading.Barrier(n_threads)

        def attempt_deposit(idx: int) -> None:
            ready_barrier.wait()  # release all threads as close together as possible
            try:
                eid = fresh_moneta.deposit(
                    f"contender-{idx}", [float(idx), 9.0], protected_floor=0.1
                )
                with successes_lock:
                    successes.append(eid)
            except ProtectedQuotaExceededError as exc:
                with failures_lock:
                    failures.append(exc)

        threads = [
            threading.Thread(target=attempt_deposit, args=(i,))
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == 1, (
            f"exactly one concurrent deposit must fill the last slot, "
            f"got {len(successes)} successes"
        )
        assert len(failures) == n_threads - 1, (
            f"all other contenders must raise, got {len(failures)} failures"
        )
        assert (
            fresh_moneta.ecs.count_protected()
            == fresh_moneta.config.quota_override
        ), "protected count must settle exactly at quota"


# ---------------------------------------------------------------------
# Round 4 Ruling 5 — quota_override bound
# ---------------------------------------------------------------------


class TestQuotaOverrideBound:
    """ARCHITECTURE.md §10 + MONETA.md §2.10 (Round 4 closure, Ruling 5).

    `quota_override` must satisfy ``1 <= q <= MAX_QUOTA_OVERRIDE`` (1000).
    An unbounded override defeats the §10 backstop entirely; an immutable
    100 ceiling forces consumers into multi-handle workarounds. The
    bounded override is the disambiguation Round 4 ratified.
    """

    def test_default_quota_is_100(self) -> None:
        cfg = MonetaConfig(storage_uri="moneta-test://q/default")
        assert cfg.quota_override == 100

    def test_quota_override_at_ceiling_accepted(self) -> None:
        from moneta.api import MAX_QUOTA_OVERRIDE

        cfg = MonetaConfig(
            storage_uri="moneta-test://q/at-ceiling",
            quota_override=MAX_QUOTA_OVERRIDE,
        )
        assert cfg.quota_override == MAX_QUOTA_OVERRIDE

    def test_quota_override_at_floor_accepted(self) -> None:
        cfg = MonetaConfig(
            storage_uri="moneta-test://q/at-floor", quota_override=1
        )
        assert cfg.quota_override == 1

    def test_quota_override_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="quota_override"):
            MonetaConfig(storage_uri="moneta-test://q/zero", quota_override=0)

    def test_quota_override_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="quota_override"):
            MonetaConfig(
                storage_uri="moneta-test://q/neg", quota_override=-1
            )

    def test_quota_override_above_ceiling_rejected(self) -> None:
        from moneta.api import MAX_QUOTA_OVERRIDE

        with pytest.raises(ValueError, match="quota_override"):
            MonetaConfig(
                storage_uri="moneta-test://q/above",
                quota_override=MAX_QUOTA_OVERRIDE + 1,
            )

    def test_unbounded_override_rejected(self) -> None:
        """The Round 4 finding: caller could previously set 10_000_000."""
        with pytest.raises(ValueError, match="quota_override"):
            MonetaConfig(
                storage_uri="moneta-test://q/unbounded",
                quota_override=10_000_000,
            )

    def test_error_message_cites_round4_ruling(self) -> None:
        with pytest.raises(ValueError, match="Round 4 Ruling 5"):
            MonetaConfig(
                storage_uri="moneta-test://q/cite", quota_override=99999
            )


# ---------------------------------------------------------------------
# query — retrieval and ranking
# ---------------------------------------------------------------------


class TestQuery:
    def test_query_empty(self, fresh_moneta: Moneta) -> None:
        assert fresh_moneta.query([1.0]) == []

    def test_query_returns_list_of_memory(
        self, fresh_moneta: Moneta
    ) -> None:
        fresh_moneta.deposit("a", [1.0, 0.0])
        results = fresh_moneta.query([1.0, 0.0])
        assert isinstance(results, list)
        assert all(isinstance(r, Memory) for r in results)

    def test_query_limit_respected(self, fresh_moneta: Moneta) -> None:
        for i in range(10):
            fresh_moneta.deposit(f"p{i}", [1.0, float(i) * 0.1])
        results = fresh_moneta.query([1.0, 0.0], limit=3)
        assert len(results) == 3


# ---------------------------------------------------------------------
# signal_attention — async reducer contract
# ---------------------------------------------------------------------


class TestSignalAttention:
    def test_signal_attention_returns_none(
        self, fresh_moneta: Moneta
    ) -> None:
        eid = fresh_moneta.deposit("x", [1.0])
        result = fresh_moneta.signal_attention({eid: 0.2})
        assert result is None

    def test_signal_attention_does_not_update_ecs_synchronously(
        self, fresh_moneta: Moneta
    ) -> None:
        """§5.1: signal_attention appends to log; ECS update happens at
        sleep pass. Without a sleep pass, attended_count stays at 0.
        """
        eid = fresh_moneta.deposit("x", [1.0])
        fresh_moneta.signal_attention({eid: 0.5})
        results = fresh_moneta.query([1.0])
        assert results[0].attended_count == 0  # not yet reduced

    def test_signal_attention_applied_by_sleep_pass(
        self, fresh_moneta: Moneta
    ) -> None:
        eid = fresh_moneta.deposit("x", [1.0])
        fresh_moneta.signal_attention({eid: 0.3})
        fresh_moneta.signal_attention({eid: 0.2})  # two signals
        result = fresh_moneta.run_sleep_pass()
        assert result.attention_updated == 1
        results = fresh_moneta.query([1.0])
        assert results[0].attended_count == 2


# ---------------------------------------------------------------------
# get_consolidation_manifest — staging contract
# ---------------------------------------------------------------------


class TestManifest:
    def test_empty_at_startup(self, fresh_moneta: Moneta) -> None:
        assert fresh_moneta.get_consolidation_manifest() == []

    def test_fresh_deposit_not_staged(
        self, fresh_moneta: Moneta
    ) -> None:
        fresh_moneta.deposit("hi", [1.0])
        fresh_moneta.run_sleep_pass()
        # Fresh high-utility memory must not stage
        assert fresh_moneta.get_consolidation_manifest() == []
