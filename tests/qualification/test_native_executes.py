"""Native qualification: the Rust seams execute on a real handle (SPEC section 6).

Two lifecycles on the current runtime, each under config ``auto`` and
``require``: a fresh durable handle, then the same store reopened from its
snapshot and WAL. Each lifecycle deposits >= 50 vectors, queries, signals
attention, runs a sleep pass, queries again, snapshots (as SYNAPSE does, with
``durability.snapshot_ecs``) and closes.

For each handle it asserts that both seams are active native and executed
(``native_calls > 0``), with no fallback and no demotion, and that the
objects doing the work come from the extension module whose file and sha256
are the ones ``native_status.wheel`` reports. Under ``require`` it asserts
``require_satisfied is True``.

``MONETA_NATIVE`` is removed for these tests so the config alone decides;
they pass in every matrix row where the wheel is loaded. The run's verdict
still reflects the row's own mode.
"""
from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path

import pytest

from moneta import Moneta, MonetaConfig, _native

pytestmark = pytest.mark.native

N_DEPOSITS = 60
DIM = 16


def _vec(rng):
    return [rng.gauss(0.0, 1.0) for _ in range(DIM)]


def _lifecycle(m, rng):
    ids = [m.deposit(f"q{i}-{rng.random():.6f}", _vec(rng)) for i in range(N_DEPOSITS)]
    assert m.query(_vec(rng), limit=10)
    m.signal_attention({ids[0]: 0.3, ids[7]: 0.2, ids[19]: 0.1})
    m.run_sleep_pass()
    assert m.query(_vec(rng), limit=10)
    m.durability.snapshot_ecs(m.ecs)


def _module_identity(mod):
    path = _native._extension_path(mod)
    assert path is not None, f"{mod!r} has no compiled extension file"
    return str(path), hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _assert_native_executed(m, mode):
    st = m.native_status
    w = st.wheel
    assert w.state == _native.LOADED
    for seam in (st.scan, st.decay):
        assert seam.active == "native", seam
        assert seam.reason is None, seam
        assert seam.native_calls > 0, seam
        assert seam.fallbacks == {}, seam
        assert seam.demoted is False, seam
        assert seam.all_native is True, seam
    assert st.require_satisfied is (True if mode == "require" else None)

    # The objects doing the work come from the extension the status names.
    store = m.vector_index._store
    assert store is not None
    store_mod = sys.modules[type(store).__module__]
    assert store_mod.__name__.split(".")[0] == "moneta_native"
    assert _module_identity(store_mod) == (w.path, w.sha256)
    assert m.ecs._native is m.vector_index._native
    assert _module_identity(m.ecs._native) == (w.path, w.sha256)
    return st


@pytest.mark.parametrize("mode", ["auto", "require"])
def test_fresh_and_reopened_handles_execute_native(real, tmp_path, mode):
    rng = random.Random(1729)
    cfg = MonetaConfig(
        storage_uri=f"moneta-test://qual-{mode}",
        native=mode,
        snapshot_path=tmp_path / "snap.json",
        wal_path=tmp_path / "wal.jsonl",
    )

    with Moneta(cfg) as m:
        assert m.native_mode == mode
        _lifecycle(m, rng)
        fresh = _assert_native_executed(m, mode)
        n_fresh = m.ecs.n
    assert n_fresh >= 50

    with Moneta(cfg) as m2:  # reopened from snapshot + WAL
        assert m2.native_mode == mode
        assert m2.ecs.n == n_fresh
        _lifecycle(m2, rng)
        reopened = _assert_native_executed(m2, mode)

    assert reopened.wheel == fresh.wheel
    for a, b in ((fresh.scan, reopened.scan), (fresh.decay, reopened.decay)):
        assert (a.requested, a.requested_source, a.active) == (
            b.requested,
            b.requested_source,
            b.active,
        )
