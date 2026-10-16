"""Shared pytest fixtures for Moneta unit and integration tests.

Owned by Test Engineer per MONETA.md §6 Role 5. Per the singleton
surgery (DEEP_THINK_BRIEF_substrate_handle.md), each test that needs a
live substrate takes the ``fresh_moneta`` fixture which yields a fully
constructed :class:`Moneta` handle. The fixture's ``with`` block
guarantees the URI lock is released on teardown so subsequent tests can
re-acquire freely.

Native qualification harness (SPEC section 6)
=============================================

The rest of this file makes the suite show whether the Rust seams ran.

* ``native`` marker: the test needs the real ``moneta_native`` wheel. When
  the wheel is not loaded it skips visibly with the reason
  ``moneta_native <state>: <reason>``, one line per test. Nothing is
  dropped at collection.
* ``native_fallback`` marker: the test intentionally makes a native-active
  component run the Python oracle. Any other test fails with
  ``unexpected native fallback: <reasons>`` if one happens.
* ``MONETA_NATIVE=require`` with the wheel not loaded raises
  ``pytest.UsageError`` in ``pytest_configure`` (exit code 4).
* The report header records the run identity; the terminal summary prints
  the verdict line, and ``MONETA_QUAL_REPORT=<path>`` also writes it as JSON.

Counting. ``moneta._native._reset_for_tests()`` zeroes the process-wide
counters, and many fixtures call it in setup and teardown, so a plain
before/after snapshot of ``_native.counters()`` would miss fallbacks. The
harness therefore tees ``_native.count_native_call`` and
``_native.count_fallback`` (src calls them by attribute on the module, so
the tee survives resets) into its own buckets, attributed to the running
test (setup, call and teardown are each checked). A fallback raised while no
test is running (for example at module import during collection) is kept in
a separate "outside any test" list and fails the native verdict. The verdict
also reads the suite exit status: a red run is never reported as
``NATIVE QUALIFIED`` or ``PYTHON-ONLY PASS`` (it reads ``PYTHON-ONLY FAIL``).
A native call counts as
*real* only when the calling component's captured module is the wheel module
this process probed at configure time; calls into the fakes in
``tests/unit/native_fakes.py`` are counted separately and never satisfy the
verdict.

``MONETA_QUAL_GUARD=record`` logs unexpected fallbacks instead of failing
the test (used once to find the tests that legitimately fall back). They
still count as unexpected in the verdict.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from moneta import Moneta, MonetaConfig, _native, build_info


@pytest.fixture
def fresh_moneta() -> Iterator[Moneta]:
    """Yield a freshly-constructed in-memory Moneta handle, closed on teardown.

    Each call generates a unique ``storage_uri`` via
    :meth:`MonetaConfig.ephemeral`, so tests cannot collide on the
    process-level URI registry.
    """
    with Moneta(MonetaConfig.ephemeral()) as substrate:
        yield substrate


# ---------------------------------------------------------------------------
# Native qualification harness
# ---------------------------------------------------------------------------

# Floor for the number of ``native``-marked tests a full run must collect
# (the "accounted total" of SPEC section 6). It is the count collected by the
# first full post-migration run with the wheel loaded on this branch (run
# record runs/C5-native1.txt). Lower it only together with a deliberate
# removal of native tests; a partial run (-k, a single file) collects fewer
# and is reported NOT QUALIFIED.
NATIVE_TESTS_EXPECTED = 71

# The qualification module proper (SPEC section 6); the intentional-fallback
# module beside it is not qualification evidence.
QUALIFICATION_MODULE = ("qualification", "test_native_executes.py")


class _Harness:
    def __init__(self) -> None:
        self.enabled = False
        self.env_raw: str | None = None
        self.mode: str | None = None
        self.wheel = None
        self.real_mod = None
        self.build = None
        self.pxr: str | None = None
        self.guard_mode = "fail"
        # Tee buckets (never reset).
        self.real_calls = {seam: 0 for seam in _native.SEAMS}
        self.other_calls = {seam: 0 for seam in _native.SEAMS}
        self.fallbacks: dict[str, dict[str, int]] = {seam: {} for seam in _native.SEAMS}
        self.current: str | None = None  # nodeid of the running test
        self.per_item: dict[str, list[str]] = {}
        self.checked: dict[str, int] = {}
        self.unexpected: dict[str, list[str]] = {}
        # Fallbacks raised while no test is running (collection, module
        # import, between items). No test owns them, so the guard cannot
        # fail one; the verdict counts them instead.
        self.outside: list[str] = []
        # Collection and outcomes.
        self.native_ids: set[str] = set()
        self.fallback_ids: set[str] = set()
        self.qual_ids: set[str] = set()
        self.outcomes: dict[str, str] = {}


_H = _Harness()


def _caller_is_real(frame) -> bool:
    """True when the counting component's captured module is the real wheel."""
    if _H.real_mod is None or frame is None:
        return False
    owner = frame.f_locals.get("self")
    return owner is not None and getattr(owner, "_native", None) is _H.real_mod


def _install_tee() -> None:
    orig_call = _native.count_native_call
    orig_fallback = _native.count_fallback
    if getattr(orig_call, "_qual_tee", False):
        return

    def count_native_call(seam: str, n: int = 1) -> None:
        orig_call(seam, n)
        if _caller_is_real(sys._getframe(1)):
            _H.real_calls[seam] += n
        else:
            _H.other_calls[seam] += n

    def count_fallback(seam: str, reason: str) -> None:
        orig_fallback(seam, reason)
        fb = _H.fallbacks[seam]
        fb[reason] = fb.get(reason, 0) + 1
        if _H.current is not None:
            _H.per_item.setdefault(_H.current, []).append(f"{seam}:{reason}")
        else:
            _H.outside.append(f"{seam}:{reason}")

    count_native_call._qual_tee = True  # type: ignore[attr-defined]
    count_fallback._qual_tee = True  # type: ignore[attr-defined]
    _native.count_native_call = count_native_call
    _native.count_fallback = count_fallback


def _pxr_version() -> str:
    try:
        from pxr import Usd  # noqa: PLC0415

        return ".".join(str(x) for x in Usd.GetVersion())
    except Exception:
        return "absent"


def pytest_configure(config: pytest.Config) -> None:
    _H.enabled = True
    _H.env_raw = os.environ.get(_native.ENV_VAR)
    _H.mode = _native.mode_for_class(_native.classify_env(_H.env_raw))
    _H.guard_mode = "record" if os.environ.get("MONETA_QUAL_GUARD") == "record" else "fail"
    # Always probe: the header records what is on the path even in an off
    # run (native-marked tests use explicit native and still execute).
    _H.wheel = _native.wheel_info()
    _H.real_mod = _native._module if _H.wheel.state == _native.LOADED else None
    if _H.mode == "require" and _H.wheel.state != _native.LOADED:
        raise pytest.UsageError(
            f"{_native.ENV_VAR}={_H.env_raw!r} requires the native wheel, but "
            f"moneta_native {_H.wheel.state}: {_H.wheel.reason}"
        )
    _H.build = build_info()
    _H.pxr = _pxr_version()
    _install_tee()


def _header_lines() -> list[str]:
    w, b = _H.wheel, _H.build
    sha = (w.sha256 or "")[:12] or None
    return [
        f"moneta native: mode={_H.mode} env {_native.ENV_VAR}={_H.env_raw!r} "
        f"guard={_H.guard_mode}",
        f"moneta wheel: state={w.state} version={w.version} api={w.api} "
        f"sha256={sha} record_match={w.record_match} path={w.path}"
        + ("" if w.state == _native.LOADED else f" reason={w.reason}"),
        f"moneta source: commit={(b.commit or '')[:12] or None} "
        f"src_digest={b.src_digest[:12]} mode={b.mode} path={b.path}",
        f"moneta interpreter: {sys.executable} python={sys.version.split()[0]} "
        f"pxr={_H.pxr}",
    ]


def pytest_report_header(config: pytest.Config) -> list[str]:
    return _header_lines()


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    if _H.wheel.state == _native.LOADED:
        return
    skip = pytest.mark.skip(reason=f"moneta_native {_H.wheel.state}: {_H.wheel.reason}")
    for item in items:
        if item.get_closest_marker("native") is not None:
            item.add_marker(skip)


def pytest_collection_finish(session: pytest.Session) -> None:
    for item in session.items:
        if item.get_closest_marker("native") is not None:
            _H.native_ids.add(item.nodeid)
            if Path(str(item.path)).parts[-2:] == QUALIFICATION_MODULE:
                _H.qual_ids.add(item.nodeid)
        if item.get_closest_marker("native_fallback") is not None:
            _H.fallback_ids.add(item.nodeid)


def _take_new(item) -> list[str]:
    got = _H.per_item.get(item.nodeid, [])
    new = got[_H.checked.get(item.nodeid, 0):]
    _H.checked[item.nodeid] = len(got)
    if new and item.get_closest_marker("native_fallback") is None:
        _H.unexpected.setdefault(item.nodeid, []).extend(new)
        return new
    return []


def _check_unexpected(item, phase: str) -> None:
    new = _take_new(item)
    if not new:
        return
    reasons = ", ".join(sorted(set(new)))
    if _H.guard_mode == "record":
        sys.stderr.write(f"\n[qual-guard record] {item.nodeid} ({phase}): {reasons}\n")
        return
    pytest.fail(f"unexpected native fallback: {reasons}", pytrace=False)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    _H.current = item.nodeid
    res = yield
    _check_unexpected(item, "setup")
    return res


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    try:
        res = yield
    except BaseException:
        _take_new(item)  # the body already failed; record, don't mask it
        raise
    _check_unexpected(item, "call")
    return res


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    try:
        res = yield
    finally:
        _H.current = None
    _check_unexpected(item, "teardown")
    return res


# ---------------------------------------------------------------------------
# Known unresolved defects (SPEC section 8)
# ---------------------------------------------------------------------------

# Tests that pin a known, UNRESOLVED defect with ``xfail(strict=True)``. The
# terminal summary lists each one that xfailed under "Known unresolved
# defects", so a green run never reads as if the defect were fixed. If one
# starts passing, strict xfail fails the run and the block says so.
KNOWN_DEFECTS = {
    "tests/integration/test_attention_snapshot_regression.py::"
    "test_B_undrained_attention_survives_snapshot_and_reopen": (
        "B",
        "undrained attention lost when a bare snapshot is followed by a restart",
    ),
    "tests/integration/test_attention_snapshot_regression.py::"
    "test_D_attention_between_drain_and_pass_snapshot_survives": (
        "D",
        "attention landing between the sleep-pass drain and its snapshot is lost",
    ),
}
KNOWN_DEFECTS_DOC = "docs/design/R1-attention-durability.md"
_defect_outcomes: dict[str, str] = {}


def _record_defect(report) -> None:
    nid = report.nodeid
    if nid not in KNOWN_DEFECTS:
        return
    if report.when == "call" or (report.when == "setup" and not report.passed):
        if hasattr(report, "wasxfail"):
            _defect_outcomes[nid] = "xfailed" if report.skipped else "XPASS(strict)"
        elif report.skipped:
            _defect_outcomes[nid] = "skipped"
        elif report.failed:
            _defect_outcomes[nid] = "failed"
        else:
            _defect_outcomes[nid] = "passed"


def _write_known_defects(tr) -> None:
    if not _defect_outcomes:
        return
    tr.section("Known unresolved defects")
    for nid, (path, what) in KNOWN_DEFECTS.items():
        outcome = _defect_outcomes.get(nid)
        if outcome is None:
            continue
        line = f"UNRESOLVED DEFECT path {path}: {what} [{outcome}] ({nid})"
        if outcome != "xfailed":
            line += " -- not an xfail; review before changing the mark"
        tr.write_line(line)
    tr.write_line(f"see {KNOWN_DEFECTS_DOC}")


def pytest_runtest_logreport(report) -> None:
    _record_defect(report)
    nid = report.nodeid
    if nid not in _H.native_ids:
        return
    prev = _H.outcomes.get(nid)
    if report.when == "setup":
        if report.skipped:
            _H.outcomes[nid] = "skipped"
        elif report.failed:
            _H.outcomes[nid] = "failed"
    elif report.when == "call":
        if report.skipped:
            _H.outcomes[nid] = "skipped"
        elif report.passed and not hasattr(report, "wasxfail"):
            _H.outcomes[nid] = "passed"
        else:
            _H.outcomes[nid] = "failed"
    elif report.when == "teardown" and report.failed and prev != "skipped":
        _H.outcomes[nid] = "failed"


def _accounting() -> dict:
    out = list(_H.outcomes.values())
    q = [_H.outcomes.get(n) for n in _H.qual_ids]
    return {
        "native_collected": len(_H.native_ids),
        "native_expected": NATIVE_TESTS_EXPECTED,
        "native_run": sum(1 for o in out if o in ("passed", "failed")),
        "native_passed": out.count("passed"),
        "native_failed": out.count("failed"),
        "native_skipped": out.count("skipped"),
        "native_unreported": len(_H.native_ids) - len(_H.outcomes),
        "native_fallback_collected": len(_H.fallback_ids),
        "qualification_collected": len(_H.qual_ids),
        "qualification_passed": q.count("passed"),
    }


def _verdict(acc: dict, exitstatus: int) -> tuple[str, list[str]]:
    w = _H.wheel
    if w.state != _native.LOADED or _H.mode == "off":
        if exitstatus != 0:
            return (
                f"PYTHON-ONLY FAIL (not native qualified): suite exit status {exitstatus}",
                [f"suite exit status {exitstatus}"],
            )
        return "PYTHON-ONLY PASS (not native qualified)", []
    reasons: list[str] = []
    if exitstatus != 0:
        reasons.append(f"suite exit status {exitstatus}")
    if w.record_match is not True:
        reasons.append(f"wheel record_match={w.record_match}")
    if acc["native_skipped"]:
        reasons.append(f"{acc['native_skipped']} native tests skipped")
    if acc["native_collected"] < NATIVE_TESTS_EXPECTED:
        reasons.append(
            f"native collected {acc['native_collected']} < expected {NATIVE_TESTS_EXPECTED}"
        )
    if acc["native_unreported"]:
        reasons.append(f"{acc['native_unreported']} native tests have no outcome")
    if acc["qualification_collected"] == 0:
        reasons.append("no qualification tests collected")
    elif acc["qualification_passed"] != acc["qualification_collected"]:
        reasons.append(
            f"qualification passed {acc['qualification_passed']}"
            f"/{acc['qualification_collected']}"
        )
    for seam in _native.SEAMS:
        if _H.real_calls[seam] <= 0:
            reasons.append(f"{seam} native_calls=0")
    n_unexp = sum(len(v) for v in _H.unexpected.values())
    if n_unexp:
        reasons.append(f"{n_unexp} unexpected fallbacks in {len(_H.unexpected)} tests")
    if _H.outside:
        reasons.append(f"{len(_H.outside)} fallbacks outside any test")
    if reasons:
        return "NATIVE NOT QUALIFIED: " + "; ".join(reasons), reasons
    return "NATIVE QUALIFIED", []


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    _write_known_defects(terminalreporter)
    if not _H.enabled or _H.wheel is None or _H.build is None:
        return
    acc = _accounting()
    verdict, reasons = _verdict(acc, int(exitstatus))
    tr = terminalreporter
    tr.section("moneta native qualification")
    for line in _header_lines():
        tr.write_line(line)
    tr.write_line(
        "native tests: collected={native_collected} (expected>={native_expected}) "
        "run={native_run} passed={native_passed} failed={native_failed} "
        "skipped={native_skipped}; native_fallback tests={native_fallback_collected}; "
        "qualification {qualification_passed}/{qualification_collected}".format(**acc)
    )
    tr.write_line(
        "native calls (real wheel): "
        + " ".join(f"{s}={_H.real_calls[s]}" for s in _native.SEAMS)
        + "; fakes: "
        + " ".join(f"{s}={_H.other_calls[s]}" for s in _native.SEAMS)
    )
    tr.write_line(
        "fallbacks: "
        + "; ".join(f"{s}={dict(sorted(_H.fallbacks[s].items()))}" for s in _native.SEAMS)
    )
    for nid, rs in sorted(_H.unexpected.items()):
        tr.write_line(f"unexpected native fallback: {nid}: {', '.join(sorted(set(rs)))}")
    if _H.outside:
        tr.write_line(
            f"native fallbacks outside any test: {len(_H.outside)}: "
            + ", ".join(sorted(set(_H.outside)))
        )
    tr.write_line(verdict, bold=True)

    path = os.environ.get("MONETA_QUAL_REPORT")
    if not path:
        return
    w, b = _H.wheel, _H.build
    report = {
        "verdict": verdict,
        "reasons": reasons,
        "exitstatus": int(exitstatus),
        "mode": _H.mode,
        "env_raw": _H.env_raw,
        "guard": _H.guard_mode,
        "wheel": {
            "state": w.state,
            "reason": w.reason,
            "version": w.version,
            "api": w.api,
            "path": w.path,
            "sha256": w.sha256,
            "record_match": w.record_match,
            "direct_url": w.direct_url,
        },
        "source": {
            "commit": b.commit,
            "ref": b.ref,
            "src_digest": b.src_digest,
            "path": b.path,
            "mode": b.mode,
            "version": b.version,
            "python": b.python,
        },
        "interpreter": {"executable": sys.executable, "version": sys.version},
        "pxr": _H.pxr,
        "counts": acc,
        "native_calls_real": dict(_H.real_calls),
        "native_calls_fakes": dict(_H.other_calls),
        "fallbacks": {s: dict(_H.fallbacks[s]) for s in _native.SEAMS},
        "unexpected_fallbacks": {k: sorted(set(v)) for k, v in _H.unexpected.items()},
        "fallbacks_outside_tests": list(_H.outside),
    }
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as e:
        tr.write_line(f"MONETA_QUAL_REPORT not written: {e}")
