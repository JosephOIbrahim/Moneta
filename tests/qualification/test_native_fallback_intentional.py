"""Intentional native fallbacks, kept apart from qualification (SPEC section 6).

Every test here makes a native-active component run the Python oracle (or,
under require, refuse to) on purpose, so the module is ``native_fallback``
and the unexpected-fallback guard expects the counters to move.

* auto, fake failing ``decay_batch``: decay demotes and the fallback is counted
  (runs in every matrix row; the fake is injected);
* real wheel, non-finite query: the oracle answers and it is counted;
* real wheel, non-finite deposit in auto: the scan index demotes, counted;
* real wheel, non-finite deposit in require: rejected, nothing changes.
"""
from __future__ import annotations

import math

import native_fakes as nf
import pytest

from moneta import Moneta, MonetaConfig, NativeSeamError, _native

pytestmark = pytest.mark.native_fallback


@pytest.fixture
def iso(monkeypatch):
    nf.isolate(monkeypatch)
    yield monkeypatch
    _native._reset_for_tests()


def test_auto_failing_fake_decay_demotes_and_counts(iso):
    ctl = nf.DecayControl()
    nf.install(iso, nf.make_module(ctl))
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        m.deposit("a", [1.0, 0.0, 0.0])
        m.deposit("b", [0.0, 1.0, 0.0])
        assert m.native_status.decay.active == "native"
        ctl.fail = TypeError("fake decay failure")
        m.run_sleep_pass()
        st = m.native_status
    assert st.decay.active == "python" and st.decay.demoted
    assert st.decay.fallbacks == {"decay_error:TypeError": 1}
    assert _native.counters()["decay"]["fallbacks"] == {"decay_error:TypeError": 1}


@pytest.mark.native
def test_real_nonfinite_query_answered_by_oracle_and_counted(real):
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        m.deposit("a", [1.0, 0.0, 0.0])
        m.deposit("b", [0.0, 1.0, 0.0])
        calls0 = m.native_status.scan.native_calls
        m.query([math.nan, 1.0, 0.0])
        st = m.native_status
    assert st.scan.active == "native" and not st.scan.demoted
    assert st.scan.fallbacks == {"query_nonfinite": 1}
    assert st.scan.native_calls == calls0
    assert st.scan.all_native is False


@pytest.mark.native
def test_real_nonfinite_deposit_auto_demotes_and_counts(real):
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        m.deposit("a", [1.0, 0.0])
        m.deposit("b", [math.nan, 0.0])
        st = m.native_status
    assert st.scan.active == "python" and st.scan.demoted
    assert st.scan.fallbacks == {"demoted:nonfinite_upsert": 1}
    assert st.decay.active == "native"


@pytest.mark.native
def test_real_nonfinite_deposit_require_rejected_without_change(real, tmp_path):
    snap, wal = tmp_path / "s.json", tmp_path / "w.jsonl"
    cfg = MonetaConfig(
        storage_uri="moneta-test://qual-require-reject",
        native="require",
        snapshot_path=snap,
        wal_path=wal,
    )

    def files():
        return tuple(p.read_bytes() if p.exists() else None for p in (snap, wal))

    with Moneta(cfg) as m:
        e = m.deposit("good", [1.0, 0.0, 0.0])
        m.signal_attention({e: 0.3})
        rows = list(m.ecs.iter_rows())
        n_idx, n_att = len(m.vector_index), len(m.attention)
        before = files()
        st0 = m.native_status
        with pytest.raises(NativeSeamError):
            m.deposit("bad", [math.inf, 0.0, 0.0])
        assert list(m.ecs.iter_rows()) == rows
        assert len(m.vector_index) == n_idx and len(m.attention) == n_att
        assert files() == before
        st = m.native_status
        assert st.scan == st0.scan and not st.scan.demoted
        assert st.require_satisfied is True
