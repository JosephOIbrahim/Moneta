"""C3: per-handle native selection, ``Moneta.native_status``, and the
handle-level failure and exactly-once rules (SPEC sections 2, 3, 4, 7).

Fake-module tests isolate the loader (``native_fakes.isolate``) and set
``MONETA_NATIVE`` with ``monkeypatch``, so they pass in every matrix row:
wheel loaded with any ``MONETA_NATIVE``, absent, broken. The few
real-wheel tests never evict the extension from ``sys.modules`` (a PyO3
module cannot initialise twice) and skip when the wheel is not loaded.
"""

from __future__ import annotations

import contextlib
import dataclasses
import importlib.abc
import importlib.machinery
import json
import logging
import math
import os
import struct
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import native_fakes as nf
import pytest

import moneta
from moneta import (
    Moneta,
    MonetaConfig,
    NativeConfigError,
    NativeSeamError,
    NativeUnavailableError,
    _native,
)
from moneta import api as api_mod
from moneta import durability as durability_mod

ENV_UNSET = object()

# One raw spelling per class is enough for the cells; spellings are
# covered separately below.
ENV_CLASSES = {
    "UNSET": ENV_UNSET,
    "AUTO": "1",
    "OFF": "0",
    "REQUIRE": "require",
    "UNKNOWN": "bogus",
}

# SPEC section 2 truth table: (config, env class) -> (mode, source) or error.
TABLE = {
    (None, "UNSET"): ("auto", "default"),
    (None, "AUTO"): ("auto", "env"),
    (None, "OFF"): ("off", "env"),
    (None, "REQUIRE"): ("require", "env"),
    (None, "UNKNOWN"): ("auto", "env"),
    ("auto", "UNSET"): ("auto", "config"),
    ("auto", "AUTO"): ("auto", "config"),
    ("auto", "OFF"): ("off", "env"),
    ("auto", "REQUIRE"): ("require", "env"),
    ("auto", "UNKNOWN"): ("auto", "config"),
    ("off", "UNSET"): ("off", "config"),
    ("off", "AUTO"): ("off", "config"),
    ("off", "OFF"): ("off", "config"),
    ("off", "REQUIRE"): NativeConfigError,
    ("off", "UNKNOWN"): ("off", "config"),
    ("require", "UNSET"): ("require", "config"),
    ("require", "AUTO"): ("require", "config"),
    ("require", "OFF"): NativeConfigError,
    ("require", "REQUIRE"): ("require", "config"),
    ("require", "UNKNOWN"): ("require", "config"),
}
CELLS = sorted(TABLE, key=lambda c: (str(c[0]), c[1]))


@pytest.fixture
def iso(monkeypatch):
    nf.isolate(monkeypatch)
    yield monkeypatch
    _native._reset_for_tests()


@pytest.fixture
def real(monkeypatch):
    """Fresh loader cache only; sys.modules untouched (real-wheel tests)."""
    monkeypatch.delenv("MONETA_NATIVE", raising=False)
    _native._reset_for_tests()
    yield monkeypatch
    _native._reset_for_tests()


# Needs the real wheel; skips visibly through the conftest native harness.
needs_wheel = pytest.mark.native


def _setenv(mp, raw):
    if raw is ENV_UNSET:
        mp.delenv("MONETA_NATIVE", raising=False)
    else:
        mp.setenv("MONETA_NATIVE", raw)


def _env_raw(raw):
    return None if raw is ENV_UNSET else raw


def _broken(mp):
    class Boom(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, name, path=None, target=None):
            return importlib.machinery.ModuleSpec(name, self) if name == nf.MOD else None

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            raise ImportError("DLL load failed: fake")

    mp.setattr(sys, "meta_path", [Boom(), *sys.meta_path])


def _state(mp, state):
    """Put the fake loader into one of the wheel states."""
    if state == "loaded":
        return nf.install(mp, nf.make_module())
    if state == "absent":
        mp.setitem(sys.modules, nf.MOD, None)
    elif state == "incompatible":
        nf.install(mp, nf.make_module(api=99))
    elif state == "broken":
        _broken(mp)
    else:
        raise AssertionError(state)
    return None


def _assert_unlocked(uri, **kw):
    """The URI lock is free: a construct on the same URI succeeds."""
    assert uri not in api_mod._ACTIVE_URIS
    with Moneta(MonetaConfig(storage_uri=uri, native="off", **kw)):
        pass


def _files(*paths):
    return {str(p): (p.read_bytes() if p.exists() else None) for p in paths}


def _wal_lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


# ---------------------------------------------------------------------------
# MonetaConfig.native
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "auto", "off", "require"])
def test_config_native_accepts_the_three_modes_and_none(value):
    assert MonetaConfig.ephemeral(native=value).native == value


@pytest.mark.parametrize("bad", ["on", "Auto", "", "0", "1", True, False, 1, "native", "python"])
def test_config_native_rejects_other_values(bad):
    with pytest.raises(ValueError, match="native"):
        MonetaConfig.ephemeral(native=bad)


def test_config_native_defaults_to_none_and_other_fields_unchanged():
    cfg = MonetaConfig(storage_uri="moneta-test://defaults")
    assert cfg.native is None
    names = [f.name for f in dataclasses.fields(MonetaConfig)]
    assert names[-1] == "native"
    assert names[:-1] == [
        "storage_uri",
        "quota_override",
        "half_life_seconds",
        "embedding_dim",
        "max_entities",
        "snapshot_path",
        "wal_path",
        "vector_persist_path",
        "mock_target_log_path",
        "use_real_usd",
        "usd_target_path",
    ]


# ---------------------------------------------------------------------------
# The truth table: pure resolver, then every cell on a real handle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cell", CELLS, ids=lambda c: f"{c[0]}-{c[1]}")
def test_resolve_handle_every_cell(cell):
    config, cls = cell
    env_class = {"UNSET": _native.UNSET, "AUTO": _native.AUTO, "OFF": _native.OFF,
                 "REQUIRE": _native.REQUIRE, "UNKNOWN": _native.UNKNOWN}[cls]
    raw = _env_raw(ENV_CLASSES[cls])
    expected = TABLE[cell]
    if expected is NativeConfigError:
        with pytest.raises(NativeConfigError) as ei:
            _native.resolve_handle(config, env_class, raw)
        assert isinstance(ei.value, ValueError)
        msg = str(ei.value)
        assert repr(raw) in msg and repr(config) in msg
    else:
        assert _native.resolve_handle(config, env_class, raw) == expected


@pytest.mark.parametrize("cell", CELLS, ids=lambda c: f"{c[0]}-{c[1]}")
def test_handle_every_cell(iso, cell):
    config, cls = cell
    raw = ENV_CLASSES[cls]
    nf.install(iso, nf.make_module())
    _setenv(iso, raw)
    uri = f"moneta-test://cell-{config}-{cls}"
    expected = TABLE[cell]
    if expected is NativeConfigError:
        with pytest.raises(NativeConfigError) as ei:
            Moneta(MonetaConfig(storage_uri=uri, native=config))
        msg = str(ei.value)
        assert repr(raw) in msg and f"native={config!r}" in msg
        # Raised before the lock was taken, and the wheel was never probed.
        assert uri not in api_mod._ACTIVE_URIS
        iso.delenv("MONETA_NATIVE")
        _assert_unlocked(uri)
        return
    mode, source = expected
    ctx = pytest.warns(RuntimeWarning, match="bogus") if cls == "UNKNOWN" else contextlib.nullcontext()
    with ctx:
        m = Moneta(MonetaConfig(storage_uri=uri, native=config))
    with m:
        assert (m.native_mode, m.native_source) == (mode, source)
        st = m.native_status
        for seam in (st.scan, st.decay):
            assert seam.requested == mode
            assert seam.requested_source == source
            assert seam.env_raw == _env_raw(raw)
            assert seam.active == ("python" if mode == "off" else "native")
        assert st.require_satisfied is (True if mode == "require" else None)
        assert st.wheel.state == ("not_probed" if mode == "off" else "loaded")


@pytest.mark.parametrize("raw", ["false", "off", "no", "0", " FALSE ", "Off", "NO"])
def test_off_values_mean_off(iso, raw):
    """Behaviour change: false/off/no used to mean ON; they now mean OFF."""
    nf.install(iso, nf.make_module())
    iso.setenv("MONETA_NATIVE", raw)
    with Moneta(MonetaConfig.ephemeral()) as m:
        st = m.native_status
        assert m.native_mode == "off" and m.native_source == "env"
        assert st.scan.active == st.decay.active == "python"
        assert st.scan.reason == st.decay.reason == "off"
        assert st.wheel.state == "not_probed"  # off never probes


@pytest.mark.parametrize("raw", ["1", "true", "on", "yes", "auto", "", " 1 ", "TRUE"])
def test_auto_values_stay_auto(iso, raw):
    nf.install(iso, nf.make_module())
    iso.setenv("MONETA_NATIVE", raw)
    with Moneta(MonetaConfig.ephemeral()) as m:
        assert (m.native_mode, m.native_source) == ("auto", "env")
        assert m.native_status.scan.active == "native"


def test_unknown_env_warns_once_and_shows_raw(iso):
    nf.install(iso, nf.make_module())
    iso.setenv("MONETA_NATIVE", "reqiure")
    with pytest.warns(RuntimeWarning, match="reqiure"):
        m1 = Moneta(MonetaConfig.ephemeral())
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        m2 = Moneta(MonetaConfig.ephemeral())  # once per process: no second warning
    with m1, m2:
        assert m1.native_status.scan.env_raw == "reqiure"
        assert m1.native_mode == "auto"


# ---------------------------------------------------------------------------
# Five wheel states at handle level
# ---------------------------------------------------------------------------


def test_state_present(iso):
    mod = _state(iso, "loaded")
    with Moneta(MonetaConfig.ephemeral()) as m:
        st = m.native_status
        assert st.scan.active == st.decay.active == "native"
        assert st.scan.reason is None and st.decay.reason is None
        assert st.wheel.state == "loaded"
        assert m.ecs._native is mod and m.vector_index._native is mod


@pytest.mark.parametrize("state", ["absent", "broken", "incompatible"])
def test_state_not_loaded_auto_runs_python_with_reason(iso, state):
    _state(iso, state)
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        st = m.native_status
        assert st.scan.active == st.decay.active == "python"
        assert st.wheel.state == state
        for seam in (st.scan, st.decay):
            assert seam.reason.startswith(f"moneta_native {state}")
            assert not seam.demoted and seam.fallbacks == {}
            assert seam.all_native is False
        assert st.require_satisfied is None
        eid = m.deposit("x", [1.0, 0.0])
        assert m.query([1.0, 0.0])[0].entity_id == eid


@pytest.mark.parametrize("raw", ["0", "false", "off", "no"])
def test_state_disabled(iso, raw):
    _state(iso, "loaded")
    iso.setenv("MONETA_NATIVE", raw)
    with Moneta(MonetaConfig.ephemeral()) as m:
        st = m.native_status
        assert st.scan.active == st.decay.active == "python"
        assert st.wheel.state == "not_probed"


@pytest.mark.parametrize("state", ["absent", "broken", "incompatible"])
@pytest.mark.parametrize("how", ["config", "env"])
def test_state_required_but_missing_raises_before_lock(iso, tmp_path, state, how):
    _state(iso, state)
    snap, wal = tmp_path / "s.json", tmp_path / "w.jsonl"
    uri = f"moneta-test://req-missing-{state}-{how}"
    kw = dict(snapshot_path=snap, wal_path=wal)
    if how == "env":
        iso.setenv("MONETA_NATIVE", "require")
        cfg = MonetaConfig(storage_uri=uri, **kw)
    else:
        cfg = MonetaConfig(storage_uri=uri, native="require", **kw)
    with pytest.raises(NativeUnavailableError) as ei:
        Moneta(cfg)
    assert isinstance(ei.value, RuntimeError)
    assert "require" in str(ei.value) and state in str(ei.value)
    assert not snap.exists() and not wal.exists()
    iso.delenv("MONETA_NATIVE", raising=False)
    _assert_unlocked(uri, **kw)


def test_off_never_imports_in_process(iso):
    """In process: an off handle leaves the probe untouched."""
    iso.setitem(sys.modules, nf.MOD, None)  # a probe would record "absent"
    with Moneta(MonetaConfig.ephemeral(native="off")) as m:
        e = m.deposit("x", [1.0, 0.0])
        m.query([1.0, 0.0])
        m.signal_attention({e: 0.1})
        m.run_sleep_pass()
        assert m.native_status.wheel.state == "not_probed"
    assert _native.current_wheel().state == "not_probed"


_OFF_SCRIPT = textwrap.dedent(
    """
    import sys, tempfile, pathlib
    import moneta
    from moneta import Moneta, MonetaConfig, _native
    d = pathlib.Path(tempfile.mkdtemp())
    cfg = dict(storage_uri="moneta-test://off-sub", snapshot_path=d / "s.json",
               wal_path=d / "w.jsonl")
    native = sys.argv[1] if sys.argv[1] != "none" else None
    for _ in range(2):  # fresh, then reopened
        with Moneta(MonetaConfig(native=native, **cfg)) as m:
            e = m.deposit("x", [1.0, 0.0, 0.5])
            m.query([1.0, 0.0, 0.5])
            m.signal_attention({e: 0.2})
            m.run_sleep_pass()
            m.durability.snapshot_ecs(m.ecs)
            st = m.native_status
            assert st.scan.active == st.decay.active == "python", st
            assert st.wheel.state == "not_probed", st.wheel
    assert "moneta_native" not in sys.modules, "off imported moneta_native"
    assert _native.current_wheel().state == "not_probed"
    print("OFF-NEVER-IMPORTS-OK")
    """
)


@pytest.mark.parametrize("trap", [False, True], ids=["inherited-path", "trap-module"])
@pytest.mark.parametrize("how", ["config", "env"])
def test_off_never_imports_subprocess(tmp_path, how, trap):
    src = Path(moneta.__file__).resolve().parent.parent
    parts = [str(src)]
    if trap:
        # A moneta_native that fails loudly (not an ImportError) if imported.
        trap_dir = tmp_path / "trap"
        trap_dir.mkdir()
        (trap_dir / "moneta_native.py").write_text(
            "raise AssertionError('moneta_native imported by an off handle')\n",
            encoding="utf-8",
        )
        parts.append(str(trap_dir))
    if os.environ.get("PYTHONPATH"):
        parts.append(os.environ["PYTHONPATH"])
    env = {k: v for k, v in os.environ.items() if k != "MONETA_NATIVE"}
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if how == "env":
        env["MONETA_NATIVE"] = "off"
        arg = "none"
    else:
        arg = "off"
    script = tmp_path / "off_script.py"
    script.write_text(_OFF_SCRIPT, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(script), arg],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OFF-NEVER-IMPORTS-OK" in r.stdout


# ---------------------------------------------------------------------------
# native_status: frozen, fresh, require_satisfied, exports, logging
# ---------------------------------------------------------------------------


def test_native_status_is_frozen_and_fresh(iso):
    _state(iso, "loaded")
    with Moneta(MonetaConfig.ephemeral(native="require")) as m:
        a = m.native_status
        b = m.native_status
        assert a is not b and a == b
        assert isinstance(a, moneta.NativeStatus)
        assert isinstance(a.scan, moneta.SeamStatus) and isinstance(a.wheel, moneta.NativeWheel)
        assert isinstance(a.source, moneta.BuildInfo)
        assert a.source is moneta.build_info()
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.require_satisfied = False
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.scan.active = "python"
        a.scan.fallbacks["x"] = 1  # a copy: the handle is unaffected
        assert m.native_status.scan.fallbacks == {}
        m.deposit("x", [1.0, 0.0])
        m.query([1.0, 0.0])
        assert m.native_status.scan.native_calls == a.scan.native_calls + 1
        assert a.scan.native_calls == 0  # the old record did not change


def test_native_status_is_not_an_agent_op():
    assert isinstance(Moneta.__dict__["native_status"], property)


@pytest.mark.native_fallback
def test_require_satisfied_rules(iso):
    _state(iso, "loaded")
    with Moneta(MonetaConfig.ephemeral(native="require")) as m:
        m.deposit("x", [1.0, 0.0])
        m.query([1.0, 0.0])
        assert m.native_status.require_satisfied is True
        m.query([math.nan, 0.0])  # permitted per-query oracle answer, listed
        st = m.native_status
        assert st.scan.fallbacks == {"query_nonfinite": 1}
        assert st.scan.all_native is False
        assert st.require_satisfied is True
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        assert m.native_status.require_satisfied is None


def test_require_satisfied_false_on_decay_fallback():
    def seam(**kw):
        base = dict(seam="decay", requested="require", requested_source="config",
                    env_raw=None, active="native", reason=None, demoted=False,
                    native_calls=1, fallbacks={})
        base.update(kw)
        return _native.seam_status(**base)

    ok = seam()
    assert _native.require_satisfied("require", seam(seam="scan"), ok) is True
    assert _native.require_satisfied("require", seam(seam="scan"),
                                     seam(fallbacks={"decay_error:TypeError": 1})) is False
    assert _native.require_satisfied("require", seam(seam="scan", demoted=True), ok) is False
    assert _native.require_satisfied("require", seam(seam="scan", active="python",
                                                     reason="x"), ok) is False
    assert _native.require_satisfied("auto", ok, ok) is None
    # Scan per-query fallbacks are allowed under require.
    assert _native.require_satisfied(
        "require", seam(seam="scan", fallbacks={"cosine_overflow": 2}), ok) is True


def test_exports():
    for name in ("NativeConfigError", "NativeUnavailableError", "NativeSeamError",
                 "NativeStatus", "SeamStatus", "NativeWheel", "build_info", "BuildInfo"):
        assert name in moneta.__all__
        assert hasattr(moneta, name)
    assert moneta.NativeStatus is _native.NativeStatus
    assert moneta.SeamStatus is _native.SeamStatus
    from moneta import _build

    assert moneta.build_info is _build.build_info
    for name in ("Moneta", "MonetaConfig", "MonetaResourceLockedError",
                 "ProtectedQuotaExceededError", "smoke_check", "Memory", "EntityState"):
        assert name in moneta.__all__


def test_init_logs_one_info_line_with_identity(iso, caplog):
    _state(iso, "loaded")
    caplog.set_level(logging.INFO, logger="moneta.api")
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        st = m.native_status
    lines = [r.getMessage() for r in caplog.records
             if r.name == "moneta.api" and r.getMessage().startswith("Moneta.init")]
    assert len(lines) == 1
    line = lines[0]
    assert "scan=native(None)" in line and "decay=native(None)" in line
    assert f"wheel={st.wheel.state}:" in line
    assert st.source.src_digest[:12] in line
    assert (st.source.commit or "-")[:12] in line


def test_init_log_names_python_reason_and_wheel_sha(iso, caplog):
    _state(iso, "absent")
    caplog.set_level(logging.INFO, logger="moneta.api")
    with Moneta(MonetaConfig.ephemeral()):
        pass
    line = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Moneta.init")][0]
    assert "scan=python(moneta_native absent" in line
    assert "decay=python(moneta_native absent" in line
    assert "wheel=absent:-" in line


@pytest.mark.native_fallback
def test_warning_once_per_handle_per_reason(iso, caplog):
    _state(iso, "loaded")
    caplog.set_level(logging.WARNING)
    for _ in range(2):
        with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
            m.deposit("a", [1.0, 0.0])
            m.deposit("b", [math.inf, 0.0])  # demotes the index
            m.deposit("c", [math.nan, 0.0])  # same reason: no second warning
            st = m.native_status
            assert st.scan.demoted and st.scan.fallbacks == {"demoted:nonfinite_upsert": 1}
    warns = [r for r in caplog.records if "demoted" in r.getMessage()]
    assert len(warns) == 2  # one per handle


# ---------------------------------------------------------------------------
# Deposit envelope pre-check under require
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [[math.nan, 0.0, 0.0], [math.inf, 0.0, 0.0], [], ["a", 0.0, 0.0], [1.0, 0.0], [10**400, 0.0, 0.0]],
    ids=["nan", "inf", "empty", "nonnumeric", "wrong_dim", "hugeint"],
)
def test_require_deposit_rejected_changes_nothing(iso, tmp_path, bad):
    _state(iso, "loaded")
    snap, wal = tmp_path / "s.json", tmp_path / "w.jsonl"
    cfg = MonetaConfig(storage_uri="moneta-test://dep-reject", native="require",
                       snapshot_path=snap, wal_path=wal)
    with Moneta(cfg) as m:
        e = m.deposit("good", [1.0, 0.0, 0.0])
        m.run_sleep_pass()
        m.signal_attention({e: 0.3})
        before_files = _files(snap, wal)
        rows = list(m.ecs.iter_rows())
        n_idx, n_att = len(m.vector_index), len(m.attention)
        activity = m.consolidation._last_activity_ms
        st0 = m.native_status
        with pytest.raises(NativeSeamError):
            m.deposit("bad", bad)
        assert list(m.ecs.iter_rows()) == rows
        assert len(m.vector_index) == n_idx and len(m.attention) == n_att
        assert m.consolidation._last_activity_ms == activity
        assert _files(snap, wal) == before_files
        st = m.native_status
        assert st.scan == st0.scan and not st.scan.demoted
        assert st.require_satisfied is True


@pytest.mark.native_fallback
def test_auto_deposit_nonfinite_demotes_and_counts(iso):
    _state(iso, "loaded")
    with Moneta(MonetaConfig.ephemeral(native="auto")) as m:
        m.deposit("a", [1.0, 0.0])
        m.deposit("b", [math.nan, 0.0])
        st = m.native_status
        assert st.scan.active == "python" and st.scan.demoted
        assert st.scan.fallbacks == {"demoted:nonfinite_upsert": 1}
        assert st.decay.active == "native"


# ---------------------------------------------------------------------------
# Fresh and reopened handles
# ---------------------------------------------------------------------------


def _shape(st):
    keys = ("seam", "requested", "requested_source", "env_raw", "active", "reason", "demoted")
    return tuple(tuple(getattr(s, k) for k in keys) for s in (st.scan, st.decay)), (
        st.wheel, st.require_satisfied)


def _lifecycle(m, n=8):
    ids = [m.deposit(f"p{i}", [1.0, float(i), 0.5 * i]) for i in range(n)]
    m.query([1.0, 0.5, 0.25])
    m.signal_attention({ids[0]: 0.2, ids[3]: 0.1})
    m.run_sleep_pass()
    m.query([1.0, 0.5, 0.25])
    m.signal_attention({ids[1]: 0.05})
    m.durability.snapshot_ecs(m.ecs)
    return ids


@pytest.mark.parametrize("native", [None, "auto", "off", "require"])
def test_fresh_and_reopened_select_identically(iso, tmp_path, native):
    mod = _state(iso, "loaded")
    cfg = MonetaConfig(storage_uri="moneta-test://reopen", native=native,
                       snapshot_path=tmp_path / "s.json", wal_path=tmp_path / "w.jsonl")
    with Moneta(cfg) as m:
        _lifecycle(m)
        fresh = _shape(m.native_status)
        fresh_mod = (m.ecs._native, m.vector_index._native)
    with Moneta(cfg) as m2:
        assert m2.ecs.n == 8
        reopened = _shape(m2.native_status)
        assert (m2.ecs._native, m2.vector_index._native) == fresh_mod
    assert fresh == reopened
    expect = None if native == "off" else mod
    assert fresh_mod == (expect, expect)


@needs_wheel
@pytest.mark.parametrize("native", [None, "require"])
def test_fresh_and_reopened_select_identically_real_wheel(real, tmp_path, native):
    cfg = MonetaConfig(storage_uri="moneta-test://reopen-real", native=native,
                       snapshot_path=tmp_path / "s.json", wal_path=tmp_path / "w.jsonl")
    with Moneta(cfg) as m:
        _lifecycle(m)
        fresh = _shape(m.native_status)
        st = m.native_status
        assert st.scan.native_calls > 0 and st.decay.native_calls > 0
        assert st.scan.fallbacks == {} and st.decay.fallbacks == {}
    with Moneta(cfg) as m2:
        m2.query([1.0, 0.5, 0.25])
        st2 = m2.native_status
        assert _shape(st2) == fresh
        assert st2.scan.active == st2.decay.active == "native"
        assert st2.scan.native_calls > 0 and st2.decay.native_calls > 0
        assert type(m2.vector_index._store).__module__.startswith("moneta_native")


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        self.t += 1.0
        return self.t


def _patch_clock(mp, t0):
    clock = _Clock(t0)
    mp.setattr(api_mod, "time", clock)
    mp.setattr(durability_mod, "time", clock)
    return clock


def _write_store(mp, tmp_path, native):
    _patch_clock(mp, 2_000_000.0)
    cfg = MonetaConfig(storage_uri="moneta-test://xback", native=native,
                       half_life_seconds=60.0, snapshot_path=tmp_path / "s.json",
                       wal_path=tmp_path / "w.jsonl")
    with Moneta(cfg) as m:
        ids = [m.deposit(f"p{i}", [math.sin(i + 1.0), math.cos(i * 0.7), 0.1 * i + 0.3])
               for i in range(24)]
        m.query([0.3, 0.9, 0.1])
        m.signal_attention({ids[2]: 0.3, ids[5]: 0.1, ids[11]: 0.07})
        m.run_sleep_pass()
        m.signal_attention({ids[7]: 0.2})  # after the snapshot: replayed from the WAL
    return cfg


def _reopen_observe(mp, cfg, native):
    _patch_clock(mp, 3_000_000.0)
    with Moneta(dataclasses.replace(cfg, native=native)) as m:
        hits = m.query([0.3, 0.9, 0.1], limit=24)
        hit_bits = [(h.entity_id, struct.pack("<d", h.utility)) for h in hits]
        rows = sorted((r.entity_id, struct.pack("<d", r.utility), r.attended_count,
                       struct.pack("<d", r.last_evaluated)) for r in m.ecs.iter_rows())
        cos = [(eid, struct.pack("<d", c)) for eid, c in m.vector_index.query([0.3, 0.9, 0.1], 24)]
        st = m.native_status
        return hit_bits, rows, cos, len(m.attention), st


@pytest.mark.parametrize("writer,reader", [("require", "off"), ("off", "require")])
def test_cross_backend_reopen_bit_equal_fake(iso, tmp_path, writer, reader):
    _state(iso, "loaded")
    cfg = _write_store(iso, tmp_path, writer)
    a = _reopen_observe(iso, cfg, reader)
    b = _reopen_observe(iso, cfg, writer)
    assert a[:4] == b[:4]
    assert a[4].scan.active == ("native" if reader == "require" else "python")
    assert b[4].scan.active == ("native" if writer == "require" else "python")


@needs_wheel
@pytest.mark.parametrize("writer,reader", [("require", "off"), ("off", "require")])
def test_cross_backend_reopen_bit_equal_real_wheel(real, tmp_path, writer, reader):
    cfg = _write_store(real, tmp_path, writer)
    a = _reopen_observe(real, cfg, reader)
    b = _reopen_observe(real, cfg, writer)
    assert a[:4] == b[:4]
    native_side = a[4] if reader == "require" else b[4]
    assert native_side.scan.active == native_side.decay.active == "native"
    assert native_side.scan.native_calls > 0 and native_side.decay.native_calls > 0
    assert native_side.require_satisfied is True


# ---------------------------------------------------------------------------
# Failure cleanup: lock released, no file modified
# ---------------------------------------------------------------------------


def _seed_store(mp, tmp_path, uri, nan_vector=False):
    snap, wal = tmp_path / "s.json", tmp_path / "w.jsonl"
    cfg = dict(storage_uri=uri, snapshot_path=snap, wal_path=wal)
    with Moneta(MonetaConfig(native="off", **cfg)) as m:
        e = m.deposit("a", [1.0, 0.0, 0.0])
        if nan_vector:
            m.deposit("nan", [math.nan, 1.0, 0.0])
        m.run_sleep_pass()
        snap_ts = json.loads(snap.read_text(encoding="utf-8"))["snapshot_created_at"]
        while time.time() <= snap_ts:
            time.sleep(0.001)
        m.signal_attention({e: 0.25})
    assert snap.exists() and wal.exists()
    return cfg, snap, wal


def _mtimes(*paths):
    return {str(p): p.stat().st_mtime_ns for p in paths}


def test_cleanup_native_unavailable(iso, tmp_path):
    cfg, snap, wal = _seed_store(iso, tmp_path, "moneta-test://cleanup-unavail")
    before, mt = _files(snap, wal), _mtimes(snap, wal)
    _state(iso, "absent")
    with pytest.raises(NativeUnavailableError, match="require.*absent"):
        Moneta(MonetaConfig(native="require", **cfg))
    assert _files(snap, wal) == before and _mtimes(snap, wal) == mt
    with Moneta(MonetaConfig(native="off", **cfg)) as m:  # lock was released
        assert m.ecs.n == 1 and len(m.attention) == 1


def test_cleanup_native_config_error(iso, tmp_path):
    cfg, snap, wal = _seed_store(iso, tmp_path, "moneta-test://cleanup-config")
    before, mt = _files(snap, wal), _mtimes(snap, wal)
    _state(iso, "loaded")
    iso.setenv("MONETA_NATIVE", "off")
    with pytest.raises(NativeConfigError):
        Moneta(MonetaConfig(native="require", **cfg))
    iso.setenv("MONETA_NATIVE", "require")
    with pytest.raises(NativeConfigError):
        Moneta(MonetaConfig(native="off", **cfg))
    assert _files(snap, wal) == before and _mtimes(snap, wal) == mt
    iso.delenv("MONETA_NATIVE")
    with Moneta(MonetaConfig(native="require", **cfg)) as m:
        assert m.ecs.n == 1 and len(m.attention) == 1


@pytest.mark.native_fallback
def test_cleanup_hydrate_native_seam_error(iso, tmp_path):
    cfg, snap, wal = _seed_store(iso, tmp_path, "moneta-test://cleanup-seam", nan_vector=True)
    before, mt = _files(snap, wal), _mtimes(snap, wal)
    assert "NaN" in snap.read_text(encoding="utf-8")
    _state(iso, "loaded")
    with pytest.raises(NativeSeamError):
        Moneta(MonetaConfig(native="require", **cfg))
    assert cfg["storage_uri"] not in api_mod._ACTIVE_URIS
    assert _files(snap, wal) == before and _mtimes(snap, wal) == mt
    # The lock is free, and auto opens the same store (demoting, recorded).
    with Moneta(MonetaConfig(native="auto", **cfg)) as m:
        assert m.ecs.n == 2
        st = m.native_status
        assert st.scan.demoted and st.scan.active == "python"
    assert _files(snap, wal) == before


def test_cleanup_hydrate_mixed_dim_native_seam_error(iso, tmp_path):
    # A stored row whose dim differs from the index dim is outside the
    # envelope (SPEC section 3), so hydrate under require raises
    # NativeSeamError, not upsert's ValueError.
    cfg, snap, wal = _seed_store(iso, tmp_path, "moneta-test://cleanup-mixed-dim")
    with Moneta(MonetaConfig(native="off", **cfg)) as m:
        b = m.deposit("b", [0.0, 1.0, 0.0])
        m.run_sleep_pass()
        snap_ts = json.loads(snap.read_text(encoding="utf-8"))["snapshot_created_at"]
        while time.time() <= snap_ts:
            time.sleep(0.001)
        m.signal_attention({b: 0.25})  # keep a WAL line on disk
    assert wal.exists()
    doc = json.loads(snap.read_text(encoding="utf-8"))
    assert len(doc["rows"]) == 2
    doc["rows"][1]["semantic_vector"] = [1.0, 2.0]
    snap.write_text(json.dumps(doc), encoding="utf-8")
    before, mt = _files(snap, wal), _mtimes(snap, wal)
    _state(iso, "loaded")
    for _ in range(2):  # the second attempt proves the lock was released
        with pytest.raises(NativeSeamError, match="dim 2, index dim 3"):
            Moneta(MonetaConfig(native="require", **cfg))
        assert cfg["storage_uri"] not in api_mod._ACTIVE_URIS
    assert _files(snap, wal) == before and _mtimes(snap, wal) == mt


# ---------------------------------------------------------------------------
# Exactly-once attention (SPEC section 7), with the mode from config
# ---------------------------------------------------------------------------


def test_exactly_once_require_config(iso, tmp_path):
    ctl = nf.DecayControl()
    nf.install(iso, nf.make_module(ctl))
    snap, wal = tmp_path / "s.json", tmp_path / "w.jsonl"
    cfg = dict(storage_uri="moneta-test://once-require-cfg", snapshot_path=snap, wal_path=wal)
    with Moneta(MonetaConfig(native="require", **cfg)) as m:
        eid = m.deposit("remember me", [1.0, 0.0, 0.0])
        m.run_sleep_pass()
        snap_ts = json.loads(snap.read_text(encoding="utf-8"))["snapshot_created_at"]
        while time.time() <= snap_ts:
            time.sleep(0.001)
        m.signal_attention({eid: 0.25})
        ctl.fail = TypeError("injected native decay failure")
        snap_before = snap.read_bytes()
        with pytest.raises(NativeSeamError) as ei:
            m.run_sleep_pass()
        assert isinstance(ei.value.__cause__, TypeError)
        assert len(m.attention) == 0
        assert m.ecs.get_memory(eid).attended_count == 1
        assert snap.read_bytes() == snap_before
        lines = _wal_lines(wal)
        assert len(lines) == 1 and lines[0]["entity_id"] == str(eid)
        st = m.native_status
        assert st.decay.active == "native" and not st.decay.demoted
        assert st.decay.fallbacks == {}
    with Moneta(MonetaConfig(native="off", **cfg)) as m2:
        assert m2.ecs.get_memory(eid).attended_count == 0
        assert len(m2.attention) == 1
        m2.run_sleep_pass()
        assert m2.ecs.get_memory(eid).attended_count == 1


def _run_once_cfg(mp, native, fail):
    nf.isolate(mp)
    ctl = nf.DecayControl()
    nf.install(mp, nf.make_module(ctl))
    mp.setattr(api_mod, "time", _Clock(1_000_000.0))
    with Moneta(MonetaConfig.ephemeral(half_life_seconds=60.0, native=native)) as m:
        ids = [m.deposit(f"p{i}", [1.0, float(i), 0.5]) for i in range(3)]
        m.signal_attention({ids[0]: 0.1, ids[2]: 0.05})
        ctl.fail = fail
        m.run_sleep_pass()
        mems = [m.ecs.get_memory(i) for i in ids]
        return (
            [struct.pack("<d", x.utility) for x in mems],
            [x.attended_count for x in mems],
            len(m.attention),
            m.native_status,
            ctl.calls,
        )


@pytest.mark.native_fallback
def test_exactly_once_auto_config(iso):
    util, attended, log_len, st, calls = _run_once_cfg(iso, "auto", OverflowError("injected"))
    ref_util, ref_attended, ref_log, ref_st, ref_calls = _run_once_cfg(iso, "off", None)
    assert ref_st.decay.active == "python" and ref_calls == 0
    assert attended == ref_attended == [1, 0, 1]
    assert log_len == ref_log == 0
    assert util == ref_util
    assert calls == 1
    assert st.decay.demoted and st.decay.fallbacks == {"decay_error:OverflowError": 1}
    assert st.require_satisfied is None


@pytest.mark.parametrize("durable", [False, True], ids=["ephemeral", "durable"])
def test_cleanup_identity_failure_releases_lock(iso, tmp_path, durable):
    """build_info() does I/O at init (INFO line); its failure must not leak
    the URI lock or the durability manager."""
    _state(iso, "loaded")
    kw = dict(snapshot_path=tmp_path / "s.json", wal_path=tmp_path / "w.jsonl") if durable else {}
    uri = f"moneta-test://identity-fail-{durable}"
    if durable:
        with Moneta(MonetaConfig(storage_uri=uri, native="off", **kw)) as m:
            e = m.deposit("a", [1.0, 0.0])
            m.run_sleep_pass()
            m.signal_attention({e: 0.1})
    before = _files(*(tmp_path / n for n in ("s.json", "w.jsonl")))
    closed = []
    real_close = durability_mod.DurabilityManager.close

    def spy_close(self):
        closed.append(self)
        return real_close(self)

    def boom():
        raise PermissionError("simulated unreadable source file")

    iso.setattr(durability_mod.DurabilityManager, "close", spy_close)
    iso.setattr(api_mod, "build_info", boom)
    with pytest.raises(PermissionError):
        Moneta(MonetaConfig(storage_uri=uri, native="auto", **kw))
    assert uri not in api_mod._ACTIVE_URIS
    assert len(closed) == (1 if durable else 0)
    assert _files(*(tmp_path / n for n in ("s.json", "w.jsonl"))) == before
    iso.setattr(api_mod, "build_info", moneta.build_info)
    _assert_unlocked(uri, **kw)
