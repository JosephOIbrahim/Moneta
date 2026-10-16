"""C1: the central native loader (``moneta._native``).

Covers env normalization (SPEC section 2), probe classification and wheel
identity (section 5), the error classes and the process-wide counters
(section 4), and the two v1 import sites (``ECS``, ``VectorIndex``).

Every in-process test isolates loader state: both ``moneta_native`` and
``moneta_native.moneta_native`` are removed from ``sys.modules`` with
``monkeypatch.delitem(..., raising=False)``, ``MONETA_NATIVE`` is set or
cleared with ``monkeypatch``, and ``_reset_for_tests()`` runs in setup and
teardown. No test depends on the process environment, so the file passes
in every matrix row. "Off never imports" runs in a subprocess, because
in-process the answer depends on test order.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.abc
import importlib.machinery
import os
import subprocess
import sys
import types
import warnings
from pathlib import Path

import pytest

import moneta
from moneta import _native
from moneta.decay import decay_value
from moneta.ecs import ECS
from moneta.vector_index import VectorIndex

MOD = "moneta_native"
SUB = "moneta_native.moneta_native"


# ---------------------------------------------------------------------------
# Fixtures and fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated(monkeypatch):
    """No moneta_native in sys.modules, no MONETA_NATIVE, fresh loader."""
    monkeypatch.delitem(sys.modules, MOD, raising=False)
    monkeypatch.delitem(sys.modules, SUB, raising=False)
    monkeypatch.delenv("MONETA_NATIVE", raising=False)
    _native._reset_for_tests()
    yield monkeypatch
    _native._reset_for_tests()


@pytest.fixture
def fresh_loader(monkeypatch):
    """Fresh loader cache only; sys.modules untouched (real-wheel tests).

    A PyO3 extension cannot be initialised twice in one process, so the
    real-wheel tests must not evict it from sys.modules.
    """
    monkeypatch.delenv("MONETA_NATIVE", raising=False)
    _native._reset_for_tests()
    yield monkeypatch
    _native._reset_for_tests()


class _FakeScanIndex:
    def __init__(self, dim):
        self.dim = dim

    def push(self, vec):  # pragma: no cover - shape only
        return 0

    def set(self, slot, vec):  # pragma: no cover
        pass

    def get(self, slot):  # pragma: no cover
        return []

    def kill(self, slot):  # pragma: no cover
        pass

    def compact(self):  # pragma: no cover
        return []

    def scan(self, q, k):  # pragma: no cover
        return []

    def slots(self):  # pragma: no cover
        return 0


def _fake_module(
    *,
    version="0.1.0",
    api=None,
    drop=(),
    drop_scan_methods=(),
    calls=None,
):
    """A module shaped like moneta_native; ``drop`` removes attributes."""
    mod = types.ModuleType(MOD)
    if version is not None:
        mod.__version__ = version
    if api is not None:
        mod.NATIVE_API = api

    def decay_batch(u, last, floor, lam, now):
        if calls is not None:
            calls.append(len(u))
        return [decay_value(u[i], last[i], floor[i], lam, now) for i in range(len(u))]

    mod.decay_batch = decay_batch
    if drop_scan_methods:
        attrs = {k: v for k, v in vars(_FakeScanIndex).items() if k not in drop_scan_methods}
        mod.ScanIndex = type("ScanIndex", (), attrs)
    else:
        mod.ScanIndex = _FakeScanIndex
    for name in drop:
        if hasattr(mod, name):
            delattr(mod, name)
    return mod


def _install(monkeypatch, mod):
    monkeypatch.setitem(sys.modules, MOD, mod)
    return mod


class _RaisingFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Finds ``moneta_native`` and raises ``exc`` from exec_module."""

    def __init__(self, exc):
        self.exc = exc

    def find_spec(self, fullname, path=None, target=None):
        if fullname == MOD:
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        raise self.exc


def _install_finder(monkeypatch, exc):
    monkeypatch.setattr(sys, "meta_path", [_RaisingFinder(exc), *sys.meta_path])


# ---------------------------------------------------------------------------
# Env normalization (SPEC section 2)
# ---------------------------------------------------------------------------

ENV_TABLE = [
    (None, _native.UNSET),
    ("", _native.AUTO),
    ("1", _native.AUTO),
    ("true", _native.AUTO),
    ("on", _native.AUTO),
    ("yes", _native.AUTO),
    ("auto", _native.AUTO),
    ("  TRUE ", _native.AUTO),
    ("Auto", _native.AUTO),
    ("0", _native.OFF),
    ("false", _native.OFF),
    ("off", _native.OFF),
    ("no", _native.OFF),
    (" OFF\n", _native.OFF),
    ("False", _native.OFF),
    ("require", _native.REQUIRE),
    ("  REQUIRE ", _native.REQUIRE),
    ("2", _native.UNKNOWN),
    ("maybe", _native.UNKNOWN),
    ("required", _native.UNKNOWN),
    ("native", _native.UNKNOWN),
]


@pytest.mark.parametrize("raw,expected", ENV_TABLE)
def test_classify_env_table(raw, expected):
    assert _native.classify_env(raw) == expected


@pytest.mark.parametrize(
    "env_class,mode",
    [
        (_native.UNSET, "auto"),
        (_native.AUTO, "auto"),
        (_native.OFF, "off"),
        (_native.REQUIRE, "require"),
        (_native.UNKNOWN, "auto"),
    ],
)
def test_mode_for_class(env_class, mode):
    assert _native.mode_for_class(env_class) == mode


@pytest.mark.parametrize("raw", ["false", "off", "no"])
def test_behaviour_change_false_off_no_now_mean_off(raw, isolated):
    """Approved change: these used to mean ON (only "0" was off)."""
    isolated.setenv("MONETA_NATIVE", raw)
    mode, env_class, got_raw = _native.env_mode()
    assert (mode, env_class, got_raw) == ("off", _native.OFF, raw)


def test_one_stays_auto(isolated):
    isolated.setenv("MONETA_NATIVE", "1")
    assert _native.env_mode() == ("auto", _native.AUTO, "1")


def test_unset_is_default_auto(isolated):
    assert _native.env_mode() == ("auto", _native.UNSET, None)


def test_unknown_value_warns_once_per_process_and_is_auto(isolated):
    isolated.setenv("MONETA_NATIVE", "maybe")
    with pytest.warns(RuntimeWarning, match="maybe"):
        assert _native.env_mode() == ("auto", _native.UNKNOWN, "maybe")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _native.env_mode() == ("auto", _native.UNKNOWN, "maybe")
    _native._reset_for_tests()
    with pytest.warns(RuntimeWarning):
        _native.read_env()


# ---------------------------------------------------------------------------
# Probe classification (SPEC section 5)
# ---------------------------------------------------------------------------


def test_not_probed_until_asked(isolated):
    assert _native.current_wheel().state == _native.NOT_PROBED
    _install(isolated, _fake_module())
    assert _native.current_wheel().state == _native.NOT_PROBED
    assert _native.wheel_info().state == _native.LOADED
    assert _native.current_wheel().state == _native.LOADED


def test_probe_absent(isolated):
    isolated.setitem(sys.modules, MOD, None)
    w = _native.wheel_info()
    assert w.state == _native.ABSENT
    assert "moneta_native" in w.reason
    assert (w.path, w.sha256, w.record_match, w.version, w.api) == (None, None, None, None, None)
    assert _native.native_available() is False


def test_probe_broken_dll(isolated):
    _install_finder(isolated, ImportError("DLL load failed while importing moneta_native: boom"))
    w = _native.wheel_info()
    assert w.state == _native.BROKEN
    assert "DLL load failed" in w.reason and "boom" in w.reason
    assert _native.native_available() is False


def test_probe_broken_partial_wheel(isolated):
    """A ModuleNotFoundError for the inner extension is broken, not absent."""
    _install_finder(
        isolated,
        ModuleNotFoundError("No module named 'moneta_native.moneta_native'", name=SUB),
    )
    w = _native.wheel_info()
    assert w.state == _native.BROKEN
    assert "moneta_native.moneta_native" in w.reason


def test_probe_broken_missing_dependency(isolated):
    _install_finder(isolated, ModuleNotFoundError("No module named 'numpy'", name="numpy"))
    assert _native.wheel_info().state == _native.BROKEN


@pytest.mark.parametrize("exc", [SyntaxError("bad"), ZeroDivisionError("x"), RuntimeError("init")])
def test_non_import_error_propagates(isolated, exc):
    _install_finder(isolated, exc)
    with pytest.raises(type(exc)):
        _native.wheel_info()
    # Not cached as a classification.
    assert _native.current_wheel().state == _native.NOT_PROBED


def test_probe_is_cached(isolated):
    _install(isolated, _fake_module())
    first = _native.wheel_info()
    isolated.setitem(sys.modules, MOD, None)  # would be absent if re-probed
    assert _native.wheel_info() is first
    _native._reset_for_tests()
    assert _native.wheel_info().state == _native.ABSENT


def test_probe_incompatible_missing_symbol(isolated):
    _install(isolated, _fake_module(drop=("decay_batch",)))
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE
    assert "decay_batch" in w.reason
    assert _native.native_available() is False


def test_probe_incompatible_decay_batch_not_callable(isolated):
    mod = _install(isolated, _fake_module())
    mod.decay_batch = 42
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE and "decay_batch" in w.reason


@pytest.mark.parametrize("method", ["push", "set", "get", "kill", "compact", "scan", "slots"])
def test_probe_incompatible_scanindex_method(isolated, method):
    _install(isolated, _fake_module(drop_scan_methods=(method,)))
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE
    assert f"ScanIndex.{method}" in w.reason


def test_probe_incompatible_reason_names_every_missing_attribute(isolated):
    fake = _fake_module(drop=("decay_batch", "__version__"), drop_scan_methods=("compact", "scan"))
    _install(isolated, fake)
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE
    for name in ("decay_batch", "ScanIndex.compact", "ScanIndex.scan", "__version__"):
        assert name in w.reason


def test_probe_incompatible_missing_scanindex(isolated):
    _install(isolated, _fake_module(drop=("ScanIndex",)))
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE and "ScanIndex" in w.reason


def test_probe_incompatible_missing_version(isolated):
    _install(isolated, _fake_module(version=None))
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE and "__version__" in w.reason


def test_probe_incompatible_api(isolated):
    _install(isolated, _fake_module(api=99))
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE
    assert "99" in w.reason and "NATIVE_API" in w.reason
    assert w.api == 99


def test_probe_api_1_accepted(isolated):
    _install(isolated, _fake_module(version="0.2.0", api=1))
    w = _native.wheel_info()
    assert w.state == _native.LOADED and w.reason is None
    assert (w.api, w.version) == (1, "0.2.0")
    assert _native.native_available() is True


def test_probe_legacy_010_accepted(isolated):
    _install(isolated, _fake_module(version="0.1.0", api=None))
    w = _native.wheel_info()
    assert w.state == _native.LOADED
    assert (w.api, w.version) == (None, "0.1.0")
    # A fake has no compiled extension behind it.
    assert (w.path, w.sha256, w.record_match, w.direct_url) == (None, None, None, None)


def test_probe_unknown_legacy_version_incompatible(isolated):
    _install(isolated, _fake_module(version="0.2.0", api=None))
    w = _native.wheel_info()
    assert w.state == _native.INCOMPATIBLE
    assert "unknown legacy version" in w.reason


def test_native_wheel_is_frozen(isolated):
    isolated.setitem(sys.modules, MOD, None)
    w = _native.wheel_info()
    with pytest.raises(AttributeError):
        w.state = "loaded"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Wheel identity on a fake extension layout (sha256, RECORD, direct_url)
# ---------------------------------------------------------------------------


def _fake_ext_layout(tmp_path: Path, record_digest: str | None, direct_url: str | None):
    """site/moneta_native/moneta_native<EXT> + site/moneta_native-0.1.0.dist-info."""
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    pkg = tmp_path / "site" / MOD
    pkg.mkdir(parents=True)
    ext = pkg / f"{MOD}{suffix}"
    ext.write_bytes(b"not really a dll\x00" * 64)
    sha = hashlib.sha256(ext.read_bytes())
    dist = tmp_path / "site" / f"{MOD}-0.1.0.dist-info"
    dist.mkdir()
    if record_digest == "correct":
        digest = base64.urlsafe_b64encode(sha.digest()).rstrip(b"=").decode()
    else:
        digest = record_digest
    lines = [f"{MOD}/__init__.py,sha256=AAAA,1"]
    if digest is not None:
        lines.append(f"{MOD}/{MOD}{suffix},sha256={digest},{ext.stat().st_size}")
    lines.append(f"{MOD}-0.1.0.dist-info/RECORD,,")
    (dist / "RECORD").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if direct_url is not None:
        (dist / "direct_url.json").write_text(direct_url, encoding="utf-8")
    return ext, sha.hexdigest()


def _fake_with_ext(ext: Path):
    mod = _fake_module()
    sub = types.ModuleType(SUB)
    sub.__file__ = str(ext)
    mod.moneta_native = sub
    mod.__file__ = str(ext.parent / "__init__.py")
    return mod


def test_identity_record_match_true_and_direct_url(isolated, tmp_path):
    direct = '{"url": "file:///x/moneta_native.whl", "archive_info": {}}'
    ext, sha = _fake_ext_layout(tmp_path, "correct", direct)
    _install(isolated, _fake_with_ext(ext))
    w = _native.wheel_info()
    assert w.state == _native.LOADED
    assert Path(w.path) == ext
    assert w.sha256 == sha
    assert w.record_match is True
    assert w.direct_url == "file:///x/moneta_native.whl"


def test_identity_record_mismatch(isolated, tmp_path):
    ext, _sha = _fake_ext_layout(tmp_path, "7G1_DDXFs0X5g_SqgM_qCG86ykVOnNdKWLYggiewKDM", None)
    _install(isolated, _fake_with_ext(ext))
    w = _native.wheel_info()
    assert w.record_match is False
    assert w.direct_url is None


def test_identity_no_record_row_is_none(isolated, tmp_path):
    ext, sha = _fake_ext_layout(tmp_path, None, None)
    _install(isolated, _fake_with_ext(ext))
    w = _native.wheel_info()
    assert w.sha256 == sha
    assert w.record_match is None


# ---------------------------------------------------------------------------
# Real wheel (only when the 0.1.0 abi3 wheel is on the path)
# ---------------------------------------------------------------------------

needs_wheel = pytest.mark.skipif(not _native.native_available(), reason="moneta_native not loaded")


@needs_wheel
def test_real_wheel_identity(fresh_loader):
    w = _native.wheel_info()
    assert w.state == _native.LOADED
    assert w.version == "0.1.0" and w.api is None  # legacy API 1
    assert w.path is not None and Path(w.path).is_file()
    assert w.path.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))
    assert w.sha256 == hashlib.sha256(Path(w.path).read_bytes()).hexdigest()
    assert w.record_match in (True, None)  # True when a dist-info RECORD sits beside it


@needs_wheel
def test_native_available_probes_without_handle_even_when_off(fresh_loader):
    fresh_loader.setenv("MONETA_NATIVE", "0")
    assert _native.current_wheel().state == _native.NOT_PROBED
    assert _native.native_available() is True
    assert _native.current_wheel().state == _native.LOADED


# ---------------------------------------------------------------------------
# select() and the error classes
# ---------------------------------------------------------------------------


def test_errors_subclass_the_right_bases():
    assert issubclass(_native.NativeConfigError, ValueError)
    assert issubclass(_native.NativeUnavailableError, RuntimeError)
    assert issubclass(_native.NativeSeamError, RuntimeError)
    for name in ("NativeConfigError", "NativeUnavailableError", "NativeSeamError", "NativeWheel"):
        assert getattr(moneta, name) is getattr(_native, name)
        assert name in moneta.__all__


def test_select_off_never_probes(isolated):
    _install(isolated, _fake_module())
    assert _native.select("off") == (None, "off")
    assert _native.current_wheel().state == _native.NOT_PROBED


def test_select_auto_returns_reason_when_unavailable(isolated):
    isolated.setitem(sys.modules, MOD, None)
    mod, reason = _native.select("auto")
    assert mod is None
    assert reason.startswith("moneta_native absent")


def test_select_require_raises_naming_state_and_reason(isolated):
    _install_finder(isolated, ImportError("DLL load failed: nope"))
    with pytest.raises(_native.NativeUnavailableError, match="broken.*DLL load failed: nope"):
        _native.select("require")


def test_select_rejects_unknown_mode(isolated):
    with pytest.raises(ValueError):
        _native.select("on")


def test_select_loaded_returns_module(isolated):
    mod = _install(isolated, _fake_module())
    assert _native.select("auto") == (mod, None)
    assert _native.select("require") == (mod, None)


# ---------------------------------------------------------------------------
# The two v1 import sites
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state_setup", ["absent", "broken", "incompatible"])
def test_explicit_require_raises_runtimeerror_subclass(isolated, state_setup):
    if state_setup == "absent":
        isolated.setitem(sys.modules, MOD, None)
    elif state_setup == "broken":
        _install_finder(isolated, ImportError("DLL load failed"))
    else:
        _install(isolated, _fake_module(api=99))
    with pytest.raises(_native.NativeUnavailableError, match=state_setup):
        ECS(native=True)
    with pytest.raises(RuntimeError, match=state_setup):
        VectorIndex(backend="native")


@pytest.mark.parametrize("raw", ["0", "false", "off", "no"])
def test_env_off_components_never_probe(isolated, raw):
    _install(isolated, _fake_module())
    isolated.setenv("MONETA_NATIVE", raw)
    ecs = ECS()
    vi = VectorIndex()
    assert ecs.native_decay is False and ecs._native is None
    assert vi.backend == "python" and vi._native is None
    assert _native.current_wheel().state == _native.NOT_PROBED


def test_explicit_off_components_never_probe(isolated):
    _install(isolated, _fake_module())
    isolated.setenv("MONETA_NATIVE", "require")  # explicit args ignore env
    assert ECS(native=False).native_decay is False
    assert VectorIndex(backend="python").backend == "python"
    assert _native.current_wheel().state == _native.NOT_PROBED


@pytest.mark.parametrize("raw", [None, "", "1", "true", "on", "yes", "auto", "require"])
def test_env_auto_components_use_loaded_module(isolated, raw):
    mod = _install(isolated, _fake_module())
    if raw is not None:
        isolated.setenv("MONETA_NATIVE", raw)
    ecs = ECS()
    vi = VectorIndex()
    assert ecs.native_decay is True and ecs._native is mod
    assert vi.backend == "native" and vi._native is mod


def test_env_unknown_components_warn_and_use_auto(isolated):
    mod = _install(isolated, _fake_module())
    isolated.setenv("MONETA_NATIVE", "sometimes")
    with pytest.warns(RuntimeWarning, match="sometimes"):
        ecs = ECS()
    assert ecs._native is mod


@pytest.mark.parametrize("state_setup", ["absent", "broken", "incompatible"])
def test_env_auto_components_fall_back_when_not_loaded(isolated, state_setup):
    if state_setup == "absent":
        isolated.setitem(sys.modules, MOD, None)
    elif state_setup == "broken":
        _install_finder(isolated, ImportError("DLL load failed"))
    else:
        _install(isolated, _fake_module(drop=("decay_batch",)))
    ecs = ECS()
    vi = VectorIndex()
    assert ecs.native_decay is False and ecs._native is None
    assert vi.backend == "python" and vi._native is None
    assert _native.current_wheel().state == state_setup


def test_live_components_keep_their_module_across_reset(isolated):
    calls: list[int] = []
    mod = _install(isolated, _fake_module(calls=calls))
    ecs = ECS()
    vi = VectorIndex()
    ecs._ids.append(object())
    ecs._utility.append(0.5)
    ecs._last_evaluated.append(0.0)
    ecs._protected_floor.append(0.0)
    _native._reset_for_tests()
    isolated.setitem(sys.modules, MOD, None)
    assert _native.wheel_info().state == _native.ABSENT
    assert ecs._native is mod and vi._native is mod
    ecs.decay_all(0.001, 10.0)
    assert calls == [1]  # the captured fake still ran
    assert ECS()._native is None  # new components see the new probe


def test_ecs_decay_uses_captured_module(isolated):
    calls: list[int] = []
    _install(isolated, _fake_module(calls=calls))
    ecs = ECS()
    ecs._ids.append(object())
    ecs._utility.append(0.8)
    ecs._last_evaluated.append(0.0)
    ecs._protected_floor.append(0.1)
    ecs.decay_all(0.01, 100.0)
    assert calls == [1]
    assert ecs._utility == [decay_value(0.8, 0.0, 0.1, 0.01, 100.0)]
    assert ecs._last_evaluated == [100.0]


def test_vector_index_native_available_is_the_loader_shim(isolated):
    from moneta import vector_index

    _install(isolated, _fake_module())
    assert vector_index.native_available() is True
    _native._reset_for_tests()
    isolated.setitem(sys.modules, MOD, None)
    assert vector_index.native_available() is False


# ---------------------------------------------------------------------------
# Process-wide aggregate counters
# ---------------------------------------------------------------------------


def test_counters_shape_increment_copy_and_reset(isolated):
    assert _native.counters() == {
        "scan": {"native_calls": 0, "fallbacks": {}},
        "decay": {"native_calls": 0, "fallbacks": {}},
    }
    _native.count_native_call("scan")
    _native.count_native_call("scan", 3)
    _native.count_native_call("decay")
    _native.count_fallback("scan", "query_nonfinite")
    _native.count_fallback("scan", "query_nonfinite")
    _native.count_fallback("decay", "decay_error:TypeError")
    snap = _native.counters()
    assert snap["scan"] == {"native_calls": 4, "fallbacks": {"query_nonfinite": 2}}
    assert snap["decay"] == {"native_calls": 1, "fallbacks": {"decay_error:TypeError": 1}}
    snap["scan"]["fallbacks"]["x"] = 9  # a copy, not the live dict
    assert "x" not in _native.counters()["scan"]["fallbacks"]
    _native._reset_for_tests()
    assert _native.counters()["scan"] == {"native_calls": 0, "fallbacks": {}}


# ---------------------------------------------------------------------------
# Off never imports (subprocess: in-process the answer is order-dependent)
# ---------------------------------------------------------------------------

_SRC = str(Path(moneta.__file__).resolve().parent.parent)

_OFF_SCRIPT = r"""
import sys
import moneta
from moneta import Moneta, MonetaConfig
with Moneta(MonetaConfig.ephemeral()) as m:
    eid = m.deposit("hello", [1.0, 0.0, 0.0])
    m.query([1.0, 0.0, 0.0], limit=3)
    m.signal_attention({eid: 0.2})
    m.run_sleep_pass()
    m.query([1.0, 0.0, 0.0], limit=3)
    backend = m.vector_index.backend
    decay = m.ecs.native_decay
assert "moneta.v5" not in sys.modules, "moneta.v5 imported"
print("IMPORTED" if "moneta_native" in sys.modules else "NOT_IMPORTED", backend, decay)
"""


def _run_child(env_value: str) -> str:
    env = dict(os.environ)
    env["MONETA_NATIVE"] = env_value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    parent = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _SRC + (os.pathsep + parent if parent else "")
    out = subprocess.run(
        [sys.executable, "-c", _OFF_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("raw", ["0", "false", "off", "no", " OFF "])
def test_off_never_imports(raw):
    assert _run_child(raw) == "NOT_IMPORTED python False"


@needs_wheel
def test_auto_does_import_when_wheel_present():
    """Positive control: the off assertion above is not vacuous."""
    assert _run_child("1") == "IMPORTED native True"
