"""C2: exactly-once attention when native decay fails inside a sleep pass
(SPEC sections 5 and 7).

A real ``Moneta`` handle runs on the functional fake (``native_fakes``).
The handle has no ``native`` config field yet (C3), so its mode comes from
``MONETA_NATIVE``, set per test with ``monkeypatch``. The fake is injected
after isolating the loader, so these run in every matrix row.
"""

from __future__ import annotations

import json
import struct
import time

import native_fakes as nf
import pytest

from moneta import Moneta, MonetaConfig, NativeSeamError, _native
from moneta import api as api_mod


@pytest.fixture
def iso(monkeypatch):
    nf.isolate(monkeypatch)
    yield monkeypatch
    _native._reset_for_tests()


def _wal_lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_sleep_pass_require_failure_attention_once(iso, tmp_path):
    ctl = nf.DecayControl()
    nf.install(iso, nf.make_module(ctl))
    iso.setenv("MONETA_NATIVE", "require")
    snap, wal = tmp_path / "s.json", tmp_path / "w.jsonl"
    cfg = dict(storage_uri="moneta-test://once-require", snapshot_path=snap, wal_path=wal)

    with Moneta(MonetaConfig(**cfg)) as m:
        assert m.ecs.native_mode == "require" and m.vector_index.requested_mode == "require"
        eid = m.deposit("remember me", [1.0, 0.0, 0.0])
        m.run_sleep_pass()  # native OK: snapshot written with attended_count 0
        assert snap.exists()
        snap_ts = json.loads(snap.read_text(encoding="utf-8"))["snapshot_created_at"]
        while time.time() <= snap_ts:  # keep the WAL entry strictly newer
            time.sleep(0.001)
        m.signal_attention({eid: 0.25})
        ctl.fail = TypeError("injected native decay failure")
        snap_before = snap.read_bytes()
        with pytest.raises(NativeSeamError) as ei:
            m.run_sleep_pass()
        assert isinstance(ei.value.__cause__, TypeError)
        assert len(m.attention) == 0
        assert m.ecs.get_memory(eid).attended_count == 1
        assert snap.read_bytes() == snap_before  # no snapshot after the failure
        lines = _wal_lines(wal)
        assert len(lines) == 1 and lines[0]["entity_id"] == str(eid)
        st = m.ecs.decay_seam_status()
        assert st.active == "native" and not st.demoted and st.fallbacks == {}

    # Reopen with native off: the WAL replays the signal exactly once.
    iso.setenv("MONETA_NATIVE", "0")
    with Moneta(MonetaConfig(**cfg)) as m2:
        assert m2.ecs.native_mode == "off"
        assert m2.ecs.get_memory(eid).attended_count == 0
        assert len(m2.attention) == 1
        m2.run_sleep_pass()
        assert m2.ecs.get_memory(eid).attended_count == 1


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        self.t += 1.0
        return self.t


def _run_once(mp, env, fail):
    """deposit x3 -> signal -> sleep pass on a fixed clock; returns state."""
    nf.isolate(mp)
    ctl = nf.DecayControl()
    nf.install(mp, nf.make_module(ctl))
    mp.setenv("MONETA_NATIVE", env)
    mp.setattr(api_mod, "time", _Clock(1_000_000.0))
    with Moneta(MonetaConfig.ephemeral(half_life_seconds=60.0)) as m:
        ids = [m.deposit(f"p{i}", [1.0, float(i), 0.5]) for i in range(3)]
        m.signal_attention({ids[0]: 0.1, ids[2]: 0.05})
        ctl.fail = fail
        m.run_sleep_pass()
        mems = [m.ecs.get_memory(i) for i in ids]
        return (
            [struct.pack("<d", x.utility) for x in mems],
            [x.attended_count for x in mems],
            len(m.attention),
            m.ecs.decay_seam_status(),
            ctl.calls,
        )


@pytest.mark.native_fallback
def test_sleep_pass_auto_failure_attention_once(iso):
    util, attended, log_len, st, calls = _run_once(iso, "auto", OverflowError("injected"))
    ref_util, ref_attended, ref_log, ref_st, ref_calls = _run_once(iso, "0", None)
    assert ref_st.active == "python" and ref_calls == 0
    assert attended == ref_attended == [1, 0, 1]
    assert log_len == ref_log == 0
    assert util == ref_util  # bit-equal to the oracle-only run
    assert calls == 1  # native tried once at point 2; point 3 ran the oracle
    assert st.demoted and st.fallbacks == {"decay_error:OverflowError": 1}
