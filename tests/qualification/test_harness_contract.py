"""The qualification harness's own contract (SPEC section 6), via subprocess.

Each case runs a small pytest session in a fresh interpreter, with a shim
on ``PYTHONPATH`` that makes ``moneta_native`` absent. These need no wheel
and pass in every matrix row; the child's environment is built here, never
inherited for ``MONETA_NATIVE`` / ``MONETA_QUAL_*``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

ABSENT_SHIM = (
    'raise ModuleNotFoundError("No module named \'moneta_native\'", name="moneta_native")\n'
)


def _run(tmp_path, args, **env_over):
    shim = tmp_path / "shim_absent"
    shim.mkdir(exist_ok=True)
    (shim / "moneta_native.py").write_text(ABSENT_SHIM, encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MONETA_NATIVE", "MONETA_QUAL_REPORT", "MONETA_QUAL_GUARD", "PYTHONPATH")
    }
    # The clone's src and the absent-shim come first, so moneta is the clone's
    # and moneta_native resolves to the shim (it precedes any inherited wheel
    # directory). The parent's own PYTHONPATH follows unchanged, so the nested
    # sys.executable sees the same import roots the parent ran with (e.g. where
    # pytest itself came from). The user site is not enabled.
    inherited = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), str(shim), *inherited])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(env_over)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rs", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_require_without_wheel_is_a_usage_error(tmp_path):
    r = _run(tmp_path, ["tests/qualification/test_native_executes.py"], MONETA_NATIVE="require")
    assert r.returncode == 4, r.stdout + r.stderr
    assert "requires the native wheel" in (r.stdout + r.stderr)
    assert "moneta_native absent" in (r.stdout + r.stderr)


def test_absent_wheel_skips_visibly_and_reports_python_only(tmp_path):
    report = tmp_path / "qual.json"
    r = _run(
        tmp_path,
        ["tests/qualification/test_native_executes.py"],
        MONETA_QUAL_REPORT=str(report),
    )
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "SKIPPED" in out and "moneta_native absent:" in out
    assert "PYTHON-ONLY PASS (not native qualified)" in out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["verdict"] == "PYTHON-ONLY PASS (not native qualified)"
    assert data["wheel"]["state"] == "absent"
    assert data["mode"] == "auto" and data["env_raw"] is None
    c = data["counts"]
    assert c["native_collected"] == c["native_skipped"] == 2
    assert c["native_run"] == c["native_passed"] == 0
    assert c["qualification_collected"] == 2
    for key in ("commit", "src_digest", "path"):
        assert key in data["source"]
    assert data["interpreter"]["version"] == sys.version


def test_off_mode_reports_python_only(tmp_path):
    report = tmp_path / "qual.json"
    r = _run(
        tmp_path,
        ["tests/qualification/test_native_executes.py"],
        MONETA_NATIVE="off",
        MONETA_QUAL_REPORT=str(report),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["mode"] == "off" and data["env_raw"] == "off"
    assert data["verdict"] == "PYTHON-ONLY PASS (not native qualified)"


GUARD_CONFTEST = """\
import sys
sys.path.insert(0, {unit!r})
_src = open({conftest!r}, encoding="utf-8").read()
exec(compile(_src, {conftest!r}, "exec"))
"""

GUARD_TESTS = """\
import native_fakes as nf
import pytest

from moneta import _native
from moneta.ecs import ECS


def _fallback(mp):
    nf.isolate(mp)
    ctl = nf.DecayControl()
    nf.install(mp, nf.make_module(ctl))
    ecs = ECS(native="auto")
    ecs.add(__import__("uuid").uuid4(), "p", [1.0, 0.0], 0.5, 0.0,
            __import__("moneta.types").types.EntityState.VOLATILE, 0.0)
    ctl.fail = TypeError("boom")
    ecs.decay_all(0.01, 10.0)
    _native._reset_for_tests()  # resets must not hide the fallback


def test_unmarked(monkeypatch):
    _fallback(monkeypatch)


@pytest.mark.native_fallback
def test_marked(monkeypatch):
    _fallback(monkeypatch)
"""


def test_unexpected_fallback_fails_unmarked_test_only(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pytest.ini").write_text(
        "[pytest]\naddopts = --strict-markers\nmarkers =\n"
        "    native: needs the wheel\n    native_fallback: intentional fallback\n",
        encoding="utf-8",
    )
    (proj / "conftest.py").write_text(
        GUARD_CONFTEST.format(
            unit=str(ROOT / "tests" / "unit"), conftest=str(ROOT / "tests" / "conftest.py")
        ),
        encoding="utf-8",
    )
    (proj / "test_guard.py").write_text(GUARD_TESTS, encoding="utf-8")
    r = _run(tmp_path, [str(proj), "--rootdir", str(proj), "-c", str(proj / "pytest.ini")])
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "1 failed, 1 passed" in out, out
    assert "unexpected native fallback: decay:decay_error:TypeError" in out
    assert "test_guard.py::test_unmarked" in out


FAILING_TESTS = """\
def test_ok():
    pass


def test_red():
    assert False, "deliberate"
"""

OUTSIDE_TESTS = """\
import uuid

import native_fakes as nf
import pytest

from moneta.ecs import ECS
from moneta.types import EntityState

# A fallback at module import (collection time): no test is running.
_mp = pytest.MonkeyPatch()
nf.isolate(_mp)
_ctl = nf.DecayControl()
nf.install(_mp, nf.make_module(_ctl))
_ecs = ECS(native="auto")
_ecs.add(uuid.uuid4(), "p", [1.0, 0.0], 0.5, 0.0, EntityState.VOLATILE, 0.0)
_ctl.fail = TypeError("boom")
_ecs.decay_all(0.01, 10.0)
_mp.undo()


def test_ok():
    pass
"""


def _guard_proj(tmp_path, tests_src):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pytest.ini").write_text(
        "[pytest]\naddopts = --strict-markers\nmarkers =\n"
        "    native: needs the wheel\n    native_fallback: intentional fallback\n",
        encoding="utf-8",
    )
    (proj / "conftest.py").write_text(
        GUARD_CONFTEST.format(
            unit=str(ROOT / "tests" / "unit"), conftest=str(ROOT / "tests" / "conftest.py")
        ),
        encoding="utf-8",
    )
    (proj / "test_proj.py").write_text(tests_src, encoding="utf-8")
    return proj


def test_red_suite_is_never_reported_as_pass(tmp_path):
    proj = _guard_proj(tmp_path, FAILING_TESTS)
    report = tmp_path / "qual.json"
    r = _run(
        tmp_path,
        [str(proj), "--rootdir", str(proj), "-c", str(proj / "pytest.ini")],
        MONETA_QUAL_REPORT=str(report),
    )
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "1 failed, 1 passed" in out, out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["exitstatus"] == 1
    assert "PASS" not in data["verdict"]
    assert data["verdict"].startswith("PYTHON-ONLY FAIL (not native qualified)")
    assert "suite exit status 1" in data["reasons"]
    assert "PYTHON-ONLY FAIL (not native qualified)" in out
    assert "PYTHON-ONLY PASS" not in out


def test_fallback_outside_any_test_is_reported(tmp_path):
    proj = _guard_proj(tmp_path, OUTSIDE_TESTS)
    report = tmp_path / "qual.json"
    r = _run(
        tmp_path,
        [str(proj), "--rootdir", str(proj), "-c", str(proj / "pytest.ini")],
        MONETA_QUAL_REPORT=str(report),
    )
    out = r.stdout + r.stderr
    # No test owns the fallback, so no test fails; it is reported instead.
    assert r.returncode == 0, out
    assert "native fallbacks outside any test: 1: decay:decay_error:TypeError" in out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["fallbacks_outside_tests"] == ["decay:decay_error:TypeError"]
    assert data["unexpected_fallbacks"] == {}
