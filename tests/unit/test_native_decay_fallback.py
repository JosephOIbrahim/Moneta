"""C2: ``ECS.decay_all`` native failure strategy (SPEC section 5) and the
evaluation-point AST check (SPEC section 7).

Fakes from ``native_fakes`` are injected after isolating the loader, so
the file runs in every matrix row (wheel loaded, absent, broken) and under
any ``MONETA_NATIVE``.
"""

from __future__ import annotations

import ast
import logging
import struct
from pathlib import Path
from uuid import uuid4

import native_fakes as nf
import pytest

import moneta
from moneta import NativeSeamError, _native
from moneta.decay import decay_value
from moneta.ecs import ECS, NativeResultError

LAM, NOW = 0.01, 500.0
ROWS = [(0.9, 0.0, 0.0), (0.5, 100.0, 0.2), (1.0, 499.0, 0.0), (0.3, -5.0, 0.4), (0.7, 500.0, 0.0)]


@pytest.fixture
def iso(monkeypatch):
    nf.isolate(monkeypatch)
    yield monkeypatch
    _native._reset_for_tests()


def _bits(xs):
    return [struct.pack("<d", x) for x in xs]


def _ecs(mp, mode="auto", fail=None, rows=ROWS):
    ctl = nf.DecayControl()
    nf.install(mp, nf.make_module(ctl))
    ecs = ECS(native=mode)
    for u, last, floor in rows:
        ecs._ids.append(uuid4())
        ecs._utility.append(u)
        ecs._last_evaluated.append(last)
        ecs._protected_floor.append(floor)
    ctl.fail = fail
    return ecs, ctl


def _oracle(rows=ROWS):
    return [decay_value(u, last, floor, LAM, NOW) for u, last, floor in rows]


def _snap(ecs):
    return _bits(ecs._utility), _bits(ecs._last_evaluated), list(ecs._protected_floor)


# ---------------------------------------------------------------------------
# Success path and counters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["auto", "require"])
def test_native_success_counts_and_matches_oracle(iso, mode):
    ecs, ctl = _ecs(iso, mode)
    ecs.decay_all(LAM, NOW)
    ecs.decay_all(LAM, NOW)
    assert ctl.calls == 2
    st = ecs.decay_seam_status()
    assert st.native_calls == 2 and st.fallbacks == {} and st.all_native
    assert _native.counters()["decay"] == {"native_calls": 2, "fallbacks": {}}


def test_empty_ecs_does_not_call_native(iso):
    ecs, ctl = _ecs(iso, "require", rows=[])
    ecs.decay_all(LAM, NOW)
    assert ctl.calls == 0 and ecs.decay_seam_status().native_calls == 0


# ---------------------------------------------------------------------------
# Step 1: column pre-check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["auto", "require"])
def test_decay_column_mismatch_raises_no_demote(iso, mode):
    ecs, ctl = _ecs(iso, mode)
    ecs._last_evaluated.pop()
    before = _snap(ecs)
    with pytest.raises(RuntimeError, match="ECS column invariant broken") as ei:
        ecs.decay_all(LAM, NOW)
    assert not isinstance(ei.value, NativeSeamError)
    assert ctl.calls == 0
    assert _snap(ecs) == before
    assert ecs.native_decay is True and not ecs.decay_demoted
    assert ecs.decay_seam_status().fallbacks == {}


# ---------------------------------------------------------------------------
# Steps 2-3: known native failures, auto mode
# ---------------------------------------------------------------------------

KNOWN = [
    (TypeError("bad arg"), "decay_error:TypeError", "bad arg"),
    (OverflowError("too big"), "decay_error:OverflowError", "too big"),
    ("short", "decay_error:NativeResultError", "length"),
    ("long", "decay_error:NativeResultError", "length"),
    ("wrong_type", "decay_error:NativeResultError", "int element"),
    ("not_list", "decay_error:NativeResultError", "tuple"),
]


@pytest.mark.parametrize("fail,key,text", KNOWN, ids=[k[1] + ":" + str(k[0]) for k in KNOWN])
@pytest.mark.native_fallback
def test_auto_known_failure_runs_oracle_and_demotes(iso, caplog, fail, key, text):
    ecs, ctl = _ecs(iso, "auto", fail)
    caplog.set_level(logging.WARNING, logger="moneta.ecs")
    ecs.decay_all(LAM, NOW)
    assert len(ecs._utility) == len(ROWS) == len(ecs._last_evaluated)
    assert _bits(ecs._utility) == _bits(_oracle())
    assert ecs._last_evaluated == [NOW] * len(ROWS)
    assert ecs.native_decay is False and ecs.decay_demoted
    st = ecs.decay_seam_status()
    assert st.active == "python" and st.demoted and st.all_native is False
    assert st.fallbacks == {key: 1}
    assert st.native_calls == 0  # a malformed return is not a successful call
    assert st.reason.startswith(key) and text in st.reason
    assert _native.counters()["decay"] == {"native_calls": 0, "fallbacks": {key: 1}}
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1 and text in warns[0].getMessage()
    # Demoted: later passes run the oracle without native and without counting.
    ecs.decay_all(LAM, NOW + 1)
    assert ctl.calls == 1
    assert ecs.decay_seam_status().fallbacks == {key: 1}
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_native_result_error_is_a_typeerror():
    assert issubclass(NativeResultError, TypeError)


def test_auto_oracle_also_raises_reraises_native_chained(iso):
    bad_rows = [(0.9, 0.0, 0.0), ("not a number", 1.0, 0.0)]
    native_exc = TypeError("native refused")
    ecs, _ctl = _ecs(iso, "auto", native_exc, rows=bad_rows)
    u_before, t_before = list(ecs._utility), list(ecs._last_evaluated)
    with pytest.raises(TypeError) as ei:
        ecs.decay_all(LAM, NOW)
    assert ei.value is native_exc
    # Columns unchanged, bit for bit: row 0 decayed by the oracle before
    # row 1 failed must be put back.
    assert len(ecs._utility) == len(u_before) and len(ecs._last_evaluated) == len(t_before)
    assert _bits([ecs._utility[0]]) == _bits([u_before[0]])
    assert ecs._utility[1] is u_before[1]
    assert _bits(ecs._last_evaluated) == _bits(t_before)
    assert isinstance(ei.value.__cause__, TypeError) and ei.value.__cause__ is not native_exc
    # Flags unchanged.
    assert ecs.native_decay is True and not ecs.decay_demoted
    assert ecs.fallback_reason is None
    st = ecs.decay_seam_status()
    assert st.active == "native" and st.fallbacks == {}
    assert _native.counters()["decay"]["fallbacks"] == {}


# ---------------------------------------------------------------------------
# Step 3: require mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fail", [TypeError("t"), OverflowError("o"), "short", "wrong_type", "not_list"])
def test_require_known_failure_raises_seam_error_columns_unchanged(iso, fail):
    ecs, ctl = _ecs(iso, "require", fail)
    before = _snap(ecs)
    with pytest.raises(NativeSeamError) as ei:
        ecs.decay_all(LAM, NOW)
    assert isinstance(ei.value, RuntimeError)
    cause = ei.value.__cause__
    assert isinstance(cause, (TypeError, OverflowError))
    if isinstance(fail, BaseException):
        assert cause is fail
    assert _snap(ecs) == before  # nothing assigned, no oracle run
    assert ctl.calls == 1
    assert ecs.native_decay is True and not ecs.decay_demoted
    st = ecs.decay_seam_status()
    assert st.fallbacks == {} and st.native_calls == 0 and st.active == "native"


# ---------------------------------------------------------------------------
# Step 4: everything else propagates untouched
# ---------------------------------------------------------------------------


class FakePanic(BaseException):
    """Stands in for pyo3's PanicException (a BaseException subclass)."""


@pytest.mark.parametrize("mode", ["auto", "require"])
@pytest.mark.parametrize(
    "exc", [ValueError("after precheck"), ZeroDivisionError("z"), MemoryError(), FakePanic("panic")],
    ids=["ValueError", "ZeroDivisionError", "MemoryError", "PanicException"],
)
def test_other_exceptions_propagate_untouched(iso, mode, exc):
    ecs, _ctl = _ecs(iso, mode, exc)
    before = _snap(ecs)
    with pytest.raises(type(exc)) as ei:
        ecs.decay_all(LAM, NOW)
    assert ei.value is exc
    assert _snap(ecs) == before
    assert ecs.native_decay is True and not ecs.decay_demoted
    assert ecs.decay_seam_status().fallbacks == {}


# ---------------------------------------------------------------------------
# The public flag
# ---------------------------------------------------------------------------


def test_native_decay_flag_on_off_ecs_is_noop(iso):
    nf.install(iso, nf.make_module())
    ecs = ECS(native=False)
    ecs.native_decay = True
    for u, last, floor in ROWS:
        ecs._ids.append(uuid4())
        ecs._utility.append(u)
        ecs._last_evaluated.append(last)
        ecs._protected_floor.append(floor)
    ecs.decay_all(LAM, NOW)
    assert _bits(ecs._utility) == _bits(_oracle())
    st = ecs.decay_seam_status()
    assert st.active == "python" and st.reason == "off" and st.native_calls == 0


def test_lowered_flag_runs_oracle_without_counting(iso):
    ecs, ctl = _ecs(iso, "auto")
    ecs.native_decay = False
    ecs.decay_all(LAM, NOW)
    assert ctl.calls == 0 and _bits(ecs._utility) == _bits(_oracle())
    st = ecs.decay_seam_status()
    assert st.active == "python" and st.fallbacks == {} and not st.demoted
    assert st.reason == "native_decay lowered by caller"


# ---------------------------------------------------------------------------
# Evaluation points (ARCHITECTURE.md §4; SPEC section 7)
# ---------------------------------------------------------------------------

_SRC = Path(moneta.__file__).resolve().parent


def _calls():
    """``[(relpath, enclosing 'Class.func', called name)]`` for decay calls."""
    out = []
    for path in sorted(_SRC.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        if rel.startswith("v5/") or "__pycache__" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def walk(node, scope, rel=rel):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    walk(child, scope + [child.name], rel)
                    continue
                if isinstance(child, ast.Call):
                    f = child.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                    if name in ("decay_all", "decay_one", "decay_value", "decay_batch"):
                        out.append((rel, ".".join(scope), name))
                walk(child, scope, rel)

        walk(tree, [])
    return out


def test_decay_all_has_exactly_three_call_sites():
    sites = sorted((rel, scope) for rel, scope, name in _calls() if name == "decay_all")
    assert sites == [
        ("api.py", "Moneta.query"),
        ("attention_log.py", "reduce_attention_log"),
        ("consolidation.py", "ConsolidationRunner.run_pass"),
    ], sites


def test_decay_kernels_only_inside_ecs_decay_methods():
    for rel, scope, name in _calls():
        if name in ("decay_value", "decay_batch"):
            assert (rel, scope) in {("ecs.py", "ECS._decay_oracle"), ("ecs.py", "ECS.decay_all"), ("ecs.py", "ECS.decay_one")}, (
                rel, scope, name)


def test_decay_one_has_no_callers():
    assert [c for c in _calls() if c[2] == "decay_one"] == []
