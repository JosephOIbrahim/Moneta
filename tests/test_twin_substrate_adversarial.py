"""Crucible adversarial verification — Singleton Surgery, G2.

Per ``EXECUTION_constitution_singleton_surgery.md`` §7 (Adversarial
Verification), Crucible's job is to find what's broken — not confirm
success. These cases pressure the handle invariants from
DEEP_THINK_BRIEF_substrate_handle.md §5.4 (the in-memory
``_ACTIVE_URIS`` exclusivity registry) and §6.2 (anonymous-mode
coverage as Crucible's responsibility) along three axes the
truth-condition test in ``tests/test_twin_substrate.py`` does not
exercise:

  - **Anonymous mode** — handles with no disk paths still must isolate.
  - **Lock pressure** — three handles, thread boundaries, and a
    barrier-aligned check-then-add race window on ``_ACTIVE_URIS``.
  - **Lifecycle** — ``__exit__`` releases on exception, and
    re-construction on a closed URI yields a fresh substrate (not a
    silently rehydrated one).
  - **USD C++ registry** — pxr-gated probe that two handles on
    distinct ``usd_target_path`` values hold distinct
    ``Sdf.Layer`` C++ pointers at every sublayer level.

These cases run in the default pytest discovery path. Per Constitution
§5 ("Crucible does not fix"), if any case fails, this file does not
patch the implementation — it surfaces specific reproduction steps
back to Forge.
"""
from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import List

import pytest

from moneta import Moneta, MonetaConfig, MonetaResourceLockedError


# ---------------------------------------------------------------------
# pxr availability — per-class skip pattern, not module-level.
# ---------------------------------------------------------------------

try:
    import pxr  # noqa: F401

    _HAS_PXR = True
except ImportError:
    _HAS_PXR = False


def _fresh_uri(label: str) -> str:
    """Generate a per-test-unique storage_uri.

    Crucible-test URIs are namespaced under ``moneta-crucible://`` and
    suffixed with a uuid4 hex so leaked state from a failed test
    cannot poison a subsequent test that happens to reuse the same
    label.
    """
    return f"moneta-crucible://{label}/{uuid.uuid4().hex}"


# ---------------------------------------------------------------------
# 1. Anonymous-mode Twin-Substrate isolation
# ---------------------------------------------------------------------


class TestAnonymousModeIsolation:
    """No disk paths anywhere — purely in-memory handles must isolate.

    ``test_twin_substrate.py``'s primary cases all carry ``snapshot_path``
    or ``mock_target_log_path`` writing to disk. This complementary
    case (per brief §6.2) verifies isolation when every persistence
    surface is in-memory: an ECS row in ``m_a`` must be invisible to
    ``m_b``, and the underlying ``ECS`` / ``AttentionLog`` /
    ``VectorIndex`` / ``MockUsdTarget`` instances must be physically
    distinct objects.
    """

    def test_two_anonymous_handles_are_isolated(self) -> None:
        cfg_a = MonetaConfig(storage_uri=_fresh_uri("anon-a"))
        cfg_b = MonetaConfig(storage_uri=_fresh_uri("anon-b"))

        with Moneta(cfg_a) as m_a, Moneta(cfg_b) as m_b:
            eid = m_a.deposit("anon-only-in-a", [1.0, 0.0])

            results_a = m_a.query([1.0, 0.0])
            results_b = m_b.query([1.0, 0.0])

            assert len(results_a) == 1
            assert results_a[0].entity_id == eid
            assert results_a[0].payload == "anon-only-in-a"
            assert results_b == []

            # Defense in depth — physically distinct objects
            assert m_a.ecs is not m_b.ecs
            assert m_a.attention is not m_b.attention
            assert m_a.vector_index is not m_b.vector_index
            assert m_a.authoring_target is not m_b.authoring_target


# ---------------------------------------------------------------------
# 2. Three-handle collision: A, B, then duplicate-A
# ---------------------------------------------------------------------


class TestThreeHandleCollision:
    """A and B are simultaneously alive on distinct URIs. Constructing
    a third handle on A's URI must raise even though B occupies a
    different slot in ``_ACTIVE_URIS``."""

    def test_third_handle_on_first_uri_raises(self) -> None:
        uri_a = _fresh_uri("three-A")
        uri_b = _fresh_uri("three-B")

        with Moneta(MonetaConfig(storage_uri=uri_a)) as _m_a:
            with Moneta(MonetaConfig(storage_uri=uri_b)) as _m_b:
                with pytest.raises(MonetaResourceLockedError):
                    Moneta(MonetaConfig(storage_uri=uri_a))
                # And B is symmetrically unaffected by A's presence
                with pytest.raises(MonetaResourceLockedError):
                    Moneta(MonetaConfig(storage_uri=uri_b))

    def test_third_handle_after_first_close_succeeds(self) -> None:
        """Once A closes, its URI is free even while B remains alive."""
        uri_a = _fresh_uri("three-recycle-A")
        uri_b = _fresh_uri("three-recycle-B")

        m_a = Moneta(MonetaConfig(storage_uri=uri_a))
        with Moneta(MonetaConfig(storage_uri=uri_b)) as _m_b:
            m_a.close()
            # Re-acquiring A is now legal — B is irrelevant
            with Moneta(MonetaConfig(storage_uri=uri_a)) as m_a2:
                assert m_a2.ecs.n == 0


# ---------------------------------------------------------------------
# 3. Thread-boundary + TOCTOU pressure on _ACTIVE_URIS
# ---------------------------------------------------------------------


class TestThreadBoundaryAndToctou:
    """Concurrency invariants on the ``_ACTIVE_URIS`` registry.

    The audit (``AUDIT_pre_surgery.md`` §F5) flagged that
    ``_ACTIVE_URIS`` is a plain ``set`` mutated under no lock; the
    Forge implementation is ``if x in _ACTIVE_URIS: raise; add(x)`` —
    a check-then-add pair that is theoretically TOCTOU-vulnerable.
    Under CPython 3.11/3.12 with the GIL, the bytecode sequence
    typically runs without a thread switch, but the switch interval
    can split the sequence at scale. These two cases exercise:

      - **Thread boundary** (Constitution §7): construct in a worker,
        close from the main thread; the lock survives the join.
      - **Concurrent construction**: many threads barrier-sync on the
        same URI; exactly one constructor must succeed per attempt.
        If more than one succeeds in any iteration, the surgery has a
        real concurrent-construction regression — flake or not.
    """

    def test_construct_in_thread_exit_in_main_thread(self) -> None:
        uri = _fresh_uri("thread-boundary")
        container: List[Moneta] = []
        worker_errors: List[BaseException] = []

        def worker() -> None:
            try:
                container.append(
                    Moneta(MonetaConfig(storage_uri=uri))
                )
            except BaseException as e:  # noqa: BLE001
                worker_errors.append(e)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)

        assert not worker_errors, (
            f"worker raised: {worker_errors!r}"
        )
        assert len(container) == 1, (
            "worker thread did not produce a handle"
        )

        m = container[0]
        try:
            # Main thread sees the lock the worker acquired
            with pytest.raises(MonetaResourceLockedError):
                Moneta(MonetaConfig(storage_uri=uri))
        finally:
            m.close()

        # After main-thread close, URI is reusable
        with Moneta(MonetaConfig(storage_uri=uri)) as m2:
            assert m2.ecs.n == 0

    def test_concurrent_construction_yields_at_most_one_handle(
        self,
    ) -> None:
        """Barrier-aligned race: N threads attempt to construct on the
        same URI simultaneously. Exactly one must succeed per
        iteration. Run multiple iterations to give the GIL switch
        interval many chances to land between the
        ``_ACTIVE_URIS.__contains__`` and ``_ACTIVE_URIS.add`` calls.
        """
        iterations = 30
        n_threads = 16

        for it in range(iterations):
            uri = _fresh_uri(f"toctou/{it}")
            barrier = threading.Barrier(n_threads)
            successes: List[Moneta] = []
            failures: List[BaseException] = []
            mu = threading.Lock()

            def worker() -> None:
                try:
                    barrier.wait(timeout=5.0)
                except threading.BrokenBarrierError as e:
                    with mu:
                        failures.append(e)
                    return
                try:
                    m = Moneta(MonetaConfig(storage_uri=uri))
                except MonetaResourceLockedError as e:
                    with mu:
                        failures.append(e)
                except BaseException as e:  # noqa: BLE001
                    with mu:
                        failures.append(e)
                else:
                    with mu:
                        successes.append(m)

            threads = [
                threading.Thread(target=worker)
                for _ in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10.0)

            try:
                total = len(successes) + len(failures)
                assert total == n_threads, (
                    f"iter {it}: only {total} of {n_threads} workers "
                    f"reported an outcome (deadlock or barrier break)"
                )
                assert len(successes) == 1, (
                    f"iter {it}: {len(successes)} concurrent "
                    f"constructors succeeded on URI {uri!r}; "
                    f"_ACTIVE_URIS check-then-add race fired"
                )
                # Every losing thread must have raised the right type
                for f in failures:
                    assert isinstance(f, MonetaResourceLockedError), (
                        f"iter {it}: unexpected exception "
                        f"{type(f).__name__}: {f!r}"
                    )
            finally:
                for m in successes:
                    m.close()


# ---------------------------------------------------------------------
# 4. Mid-context exception with __exit__ lock release verification
# ---------------------------------------------------------------------


class TestExceptionInContext:
    """An exception raised inside the ``with`` block must still let
    ``__exit__`` run, which must release the URI lock so a subsequent
    handle can re-acquire."""

    def test_exception_in_with_block_releases_uri_lock(self) -> None:
        uri = _fresh_uri("exc-mid-context")

        class _Boom(Exception):
            pass

        with pytest.raises(_Boom):
            with Moneta(MonetaConfig(storage_uri=uri)):
                raise _Boom("kaboom")

        # If __exit__ did not release the lock, this would raise
        # MonetaResourceLockedError instead of constructing.
        with Moneta(MonetaConfig(storage_uri=uri)) as m:
            assert m.ecs.n == 0

    def test_exception_does_not_suppress_propagation(self) -> None:
        """Sanity: __exit__ returns False so the original exception
        propagates. A False return is what we want — never True."""
        uri = _fresh_uri("exc-no-suppress")

        class _Boom(Exception):
            pass

        with pytest.raises(_Boom):
            with Moneta(MonetaConfig(storage_uri=uri)):
                raise _Boom("propagate me")


# ---------------------------------------------------------------------
# 5. Construct -> exit -> re-construct on same URI
# ---------------------------------------------------------------------


class TestReconstructAfterExit:
    """After close, the URI is reusable AND the resulting handle
    reflects a fresh substrate, not silent rehydration.

    The Forge test in test_api.py verifies that re-construction
    succeeds. Crucible verifies that the new handle's state is
    actually fresh — no leaked rows from the prior life.
    """

    def test_close_then_reconstruct_yields_fresh_substrate(self) -> None:
        uri = _fresh_uri("recycle")

        m1 = Moneta(MonetaConfig(storage_uri=uri))
        eid = m1.deposit("ghost", [1.0, 0.0])
        assert m1.ecs.n == 1
        m1.close()

        m2 = Moneta(MonetaConfig(storage_uri=uri))
        try:
            assert m2.ecs.n == 0, (
                "reconstructed handle leaked rows from prior life"
            )
            assert m2.ecs.contains(eid) is False
            assert m2.query([1.0, 0.0]) == []
        finally:
            m2.close()

    def test_with_block_recycle_yields_fresh_substrate(self) -> None:
        uri = _fresh_uri("recycle-with")

        with Moneta(MonetaConfig(storage_uri=uri)) as m1:
            m1.deposit("ghost", [1.0, 0.0])
            assert m1.ecs.n == 1

        with Moneta(MonetaConfig(storage_uri=uri)) as m2:
            assert m2.ecs.n == 0
            assert m2.query([1.0, 0.0]) == []

    def test_repeated_recycle_remains_clean(self) -> None:
        """Many recycle iterations on the same URI never leak state."""
        uri = _fresh_uri("recycle-many")
        for _ in range(10):
            with Moneta(MonetaConfig(storage_uri=uri)) as m:
                assert m.ecs.n == 0
                m.deposit("transient", [1.0, 0.0])
                assert m.ecs.n == 1


# ---------------------------------------------------------------------
# 6. USD layer-cache adversarial probe — pxr-gated
# ---------------------------------------------------------------------


@pytest.mark.skipif(
    not _HAS_PXR, reason="pxr (OpenUSD bindings) not available"
)
class TestUsdLayerCacheAdversarial:
    """Probe the C++ ``Sdf.Layer`` registry for cross-handle pointer
    collapse.

    DEEP_THINK_BRIEF_substrate_handle.md §5.2 frames the registry as
    the trap that no static analyzer can see: two handles pointing at
    the same physical USD path would silently share C++ pointers. The
    surgery's guard against that is ``_ACTIVE_URIS`` plus the
    convention that distinct ``usd_target_path`` values produce
    distinct file paths and therefore distinct registry entries.

    Crucible verifies the second half of that compound condition
    holds at every layer level (root + every sublayer the handle
    creates, including the protected sublayer). If any sublayer
    pointer is shared between two handles, the registry collapsed
    them — a real surgery regression.
    """

    def test_distinct_uris_with_distinct_usd_paths_have_distinct_layers(
        self, tmp_path: Path
    ) -> None:
        cfg_a = MonetaConfig(
            storage_uri=_fresh_uri("usd-distinct-a"),
            use_real_usd=True,
            usd_target_path=tmp_path / "ua",
        )
        cfg_b = MonetaConfig(
            storage_uri=_fresh_uri("usd-distinct-b"),
            use_real_usd=True,
            usd_target_path=tmp_path / "ub",
        )

        with Moneta(cfg_a) as m_a, Moneta(cfg_b) as m_b:
            target_a = m_a.authoring_target
            target_b = m_b.authoring_target

            # Top-level pointers
            assert target_a.stage is not target_b.stage
            assert target_a._root_layer is not target_b._root_layer
            assert (
                target_a._root_layer.identifier
                != target_b._root_layer.identifier
            )

            # Force creation of a rolling-day sublayer on each side by
            # depositing + staging — this exercises sublayers beyond
            # cortex_protected.usda which is created at construction.
            for m in (m_a, m_b):
                eid = m.deposit("probe", [1.0, 0.0])
                idx = m.ecs._id_to_row.get(eid)
                assert idx is not None
                m.ecs._utility[idx] = 0.2
                m.ecs._attended[idx] = 5
                import time as _time
                m.ecs._last_evaluated[idx] = _time.time()
                result = m.run_sleep_pass()
                assert result.staged == 1

            # Every sublayer name on both sides must map to physically
            # distinct Sdf.Layer pointers.
            for name in target_a.sublayer_names:
                layer_a = target_a.get_layer(name)
                layer_b = target_b.get_layer(name)
                if layer_a is not None and layer_b is not None:
                    assert layer_a is not layer_b, (
                        f"sublayer {name!r} shares Sdf.Layer pointer "
                        f"between handles A and B — C++ registry "
                        f"collapsed entries that should be distinct"
                    )
                    assert (
                        layer_a.identifier != layer_b.identifier
                    ), (
                        f"sublayer {name!r} has identical layer "
                        f"identifier on both handles: "
                        f"{layer_a.identifier!r}"
                    )
