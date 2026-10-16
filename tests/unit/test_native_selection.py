"""C2: component-level native selection and the scan seam (SPEC 2, 3, 4).

Covers the component argument table (``ECS(native=...)``,
``VectorIndex(backend=...)``), env-resolved require, per-component scan
counters and fallback reasons, auto demotion records, and require's
"no demotion, raise before mutation" rule.

Every test isolates the loader (``native_fakes.isolate``) and sets
``MONETA_NATIVE`` with ``monkeypatch``, so the file passes in every matrix
row: wheel loaded with any ``MONETA_NATIVE``, absent, broken.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from uuid import uuid4

import native_fakes as nf
import pytest

from moneta import NativeSeamError, NativeUnavailableError, _native
from moneta.ecs import ECS
from moneta.types import EntityState
from moneta.vector_index import VectorIndex, _oracle_scan

S = EntityState.VOLATILE


@pytest.fixture
def iso(monkeypatch):
    nf.isolate(monkeypatch)
    yield monkeypatch
    _native._reset_for_tests()


def _set_state(mp, state):
    if state == "absent":
        mp.setitem(sys.modules, nf.MOD, None)
    elif state == "incompatible":
        nf.install(mp, nf.make_module(api=99))
    elif state == "loaded":
        return nf.install(mp, nf.make_module())
    else:
        raise AssertionError(state)
    return None


# ---------------------------------------------------------------------------
# C1 carry-over: env REQUIRE resolves env-resolved components to require
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["absent", "incompatible"])
@pytest.mark.parametrize("raw", ["require", "  REQUIRE "])
def test_env_require_raises_for_env_resolved_components(iso, state, raw):
    _set_state(iso, state)
    iso.setenv("MONETA_NATIVE", raw)
    with pytest.raises(NativeUnavailableError, match=state):
        ECS()
    with pytest.raises(NativeUnavailableError, match=state):
        VectorIndex()
    with pytest.raises(NativeUnavailableError, match=state):
        VectorIndex(backend="auto")


def test_env_require_raises_when_broken(iso):
    import importlib.abc
    import importlib.machinery

    class Boom(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, name, path=None, target=None):
            return importlib.machinery.ModuleSpec(name, self) if name == nf.MOD else None

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            raise ImportError("DLL load failed: fake")

    iso.setattr(sys, "meta_path", [Boom(), *sys.meta_path])
    iso.setenv("MONETA_NATIVE", "require")
    with pytest.raises(NativeUnavailableError, match="broken.*DLL load failed"):
        ECS()
    with pytest.raises(NativeUnavailableError, match="broken"):
        VectorIndex()


def test_env_require_loaded_records_require_from_env(iso):
    mod = _set_state(iso, "loaded")
    iso.setenv("MONETA_NATIVE", "require")
    ecs, vi = ECS(), VectorIndex()
    assert ecs._native is mod and vi._native is mod
    for st in (ecs.decay_seam_status(), vi.scan_seam_status()):
        assert (st.requested, st.requested_source, st.env_raw) == ("require", "env", "require")
        assert st.active == "native" and st.reason is None


# ---------------------------------------------------------------------------
# Component argument table (SPEC section 2)
# ---------------------------------------------------------------------------

ENV_CASES = [
    (None, "auto", "default"),
    ("", "auto", "env"),
    ("1", "auto", "env"),
    ("yes", "auto", "env"),
    ("0", "off", "env"),
    ("false", "off", "env"),
    ("off", "off", "env"),
    ("no", "off", "env"),
    ("require", "require", "env"),
]


@pytest.mark.parametrize("raw,mode,source", ENV_CASES)
def test_env_resolved_components(iso, raw, mode, source):
    mod = _set_state(iso, "loaded")
    if raw is not None:
        iso.setenv("MONETA_NATIVE", raw)
    for st, comp in ((ECS().decay_seam_status(), "ecs"), (VectorIndex().scan_seam_status(), "vi")):
        assert (st.requested, st.requested_source, st.env_raw) == (mode, source, raw), comp
        assert st.active == ("python" if mode == "off" else "native")
        assert st.reason == ("off" if mode == "off" else None)
    if mode == "off":
        assert _native.current_wheel().state == _native.NOT_PROBED
    assert mod is not None


def test_env_unknown_warns_and_is_auto_from_env(iso):
    _set_state(iso, "loaded")
    iso.setenv("MONETA_NATIVE", "sometimes")
    with pytest.warns(RuntimeWarning, match="sometimes"):
        st = ECS().decay_seam_status()
    assert (st.requested, st.requested_source, st.env_raw) == ("auto", "env", "sometimes")


@pytest.mark.parametrize("raw", [None, "0", "require", "1"])
def test_explicit_component_args_ignore_env(iso, raw):
    mod = _set_state(iso, "loaded")
    if raw is not None:
        iso.setenv("MONETA_NATIVE", raw)
    cases = [
        (ECS(native=True).decay_seam_status(), "require", "native"),
        (ECS(native=False).decay_seam_status(), "off", "python"),
        (VectorIndex(backend="native").scan_seam_status(), "require", "native"),
        (VectorIndex(backend="python").scan_seam_status(), "off", "python"),
        (ECS(native="auto").decay_seam_status(), "auto", "native"),
        (ECS(native="off").decay_seam_status(), "off", "python"),
        (ECS(native="require").decay_seam_status(), "require", "native"),
        (VectorIndex(backend="auto", _env=False).scan_seam_status(), "auto", "native"),
    ]
    for st, mode, active in cases:
        assert (st.requested, st.requested_source, st.active) == (mode, "explicit", active)
        assert st.env_raw == raw
    assert mod is not None


def test_handle_source_is_recorded(iso):
    _set_state(iso, "loaded")
    assert ECS(native="require", _source="config").native_source == "config"
    vi = VectorIndex(backend="python", _source="default")
    assert vi.requested_source == "default" and vi.requested_mode == "off"
    with pytest.raises(ValueError):
        ECS(native="auto", _source="bogus")


@pytest.mark.parametrize("bad", ["on", "native", "", 1, 0, 2.0])
def test_ecs_rejects_unknown_native_values(iso, bad):
    _set_state(iso, "loaded")
    with pytest.raises(ValueError):
        ECS(native=bad)


def test_explicit_off_never_probes(iso):
    _set_state(iso, "loaded")
    iso.setenv("MONETA_NATIVE", "require")
    ECS(native=False)
    ECS(native="off")
    VectorIndex(backend="python")
    assert _native.current_wheel().state == _native.NOT_PROBED


@pytest.mark.parametrize("state", ["absent", "incompatible"])
def test_auto_not_loaded_records_reason(iso, state):
    _set_state(iso, state)
    for st in (ECS().decay_seam_status(), VectorIndex().scan_seam_status()):
        assert st.requested == "auto" and st.active == "python"
        assert st.reason.startswith(f"moneta_native {state}")
        assert not st.demoted and st.fallbacks == {} and st.native_calls == 0
        assert st.all_native is False


@pytest.mark.parametrize("state", ["absent", "incompatible"])
def test_explicit_require_not_loaded_raises(iso, state):
    _set_state(iso, state)
    with pytest.raises(NativeUnavailableError):
        ECS(native=True)
    with pytest.raises(NativeUnavailableError):
        VectorIndex(backend="native")


def test_seam_status_is_frozen_and_a_copy(iso):
    _set_state(iso, "loaded")
    vi = VectorIndex(backend="native")
    st = vi.scan_seam_status()
    with pytest.raises(AttributeError):
        st.active = "python"  # type: ignore[misc]
    st.fallbacks["x"] = 1
    assert vi.scan_seam_status().fallbacks == {}
    assert st.all_native is True


# ---------------------------------------------------------------------------
# Scan counters (SPEC section 4: Rust invocations, not queries)
# ---------------------------------------------------------------------------


def _filled(backend="native", n=20, dim=4, seed=1, **kw):
    import random

    rng = random.Random(seed)
    vi = VectorIndex(backend=backend, **kw)
    rows = []
    for _ in range(n):
        eid, v = uuid4(), [rng.gauss(0, 1) for _ in range(dim)]
        vi.upsert(eid, v, S)
        rows.append((eid, v))
    return vi, rows


def test_query_counts_one_native_call_each(iso):
    _set_state(iso, "loaded")
    vi, rows = _filled()
    q = rows[0][1]
    for _ in range(3):
        assert vi.query(q, 5) == _oracle_scan(rows, q, 5)
    st = vi.scan_seam_status()
    assert st.native_calls == 3 and st.fallbacks == {} and st.all_native
    assert _native.counters()["scan"] == {"native_calls": 3, "fallbacks": {}}


def test_iter_query_counts_each_window(iso):
    _set_state(iso, "loaded")
    vi, rows = _filled(n=600, dim=3)
    q = rows[0][1]
    got = list(vi.iter_query(q))
    assert got == _oracle_scan(rows, q, 600)
    # windows of 256 then min(600, 2048) = 600
    assert vi.scan_seam_status().native_calls == 2
    assert nf.FakeScanIndex.scans == 2


def test_empty_index_and_k0_do_not_call_rust(iso):
    _set_state(iso, "loaded")
    vi = VectorIndex(backend="native")
    assert vi.query([1.0, 0.0], 3) == []
    vi.upsert(uuid4(), [1.0, 0.0], S)
    assert vi.query([1.0, 0.0], 0) == []
    assert vi.scan_seam_status().native_calls == 0


@pytest.mark.parametrize("mode", ["native", "auto"])
def test_dim_mismatch_and_zero_norm_queries_are_not_fallbacks(iso, mode):
    _set_state(iso, "loaded")
    vi, _rows = _filled(backend=mode)
    assert vi.query([1.0, 2.0], 5) == []  # dim mismatch
    assert vi.query([0.0, 0.0, 0.0, 0.0], 5) == []  # zero norm
    st = vi.scan_seam_status()
    assert st.native_calls == 2 and st.fallbacks == {} and st.all_native


@pytest.mark.parametrize("backend", ["native", "auto"])
def test_nonfinite_query_is_counted_oracle_answer(iso, backend):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend=backend)
    for q in ([math.nan, 1.0, 0.0, 0.0], [math.inf, 0.0, 0.0, 1.0]):
        assert repr(vi.query(q, 7)) == repr(_oracle_scan(rows, q, 7))
    assert repr(list(vi.iter_query([math.nan, 0, 0, 1.0]))) == repr(
        _oracle_scan(rows, [math.nan, 0, 0, 1.0], 20)
    )
    st = vi.scan_seam_status()
    assert st.fallbacks == {"query_nonfinite": 3}
    assert st.native_calls == 0
    assert st.active == "native" and not st.demoted and st.all_native is False
    assert _native.counters()["scan"]["fallbacks"] == {"query_nonfinite": 3}


@pytest.mark.parametrize("backend", ["native", "auto"])
def test_cosine_overflow_is_counted_once_per_query(iso, backend):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend=backend, n=10)
    big = [1e308, -1e308, 1e308, 1e308]
    eid = uuid4()
    vi.upsert(eid, big, S)
    rows.append((eid, big))
    q = [1e308, 1e308, 1.0, 0.0]
    assert repr(vi.query(q, 5)) == repr(_oracle_scan(rows, q, 5))
    assert repr(list(vi.iter_query(q))) == repr(_oracle_scan(rows, q, len(rows)))
    st = vi.scan_seam_status()
    assert st.fallbacks == {"cosine_overflow": 2}
    assert st.native_calls == 0 and st.active == "native" and not st.demoted


def test_python_backend_never_counts(iso):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend="python")
    vi.query(rows[0][1], 3)
    vi.query([math.nan, 0, 0, 1.0], 3)
    st = vi.scan_seam_status()
    assert st.native_calls == 0 and st.fallbacks == {}
    assert _native.counters()["scan"] == {"native_calls": 0, "fallbacks": {}}


# ---------------------------------------------------------------------------
# Auto: demotion is permitted and recorded
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad", [[math.inf, 0.0, 1.0, 0.0], [math.nan, 0.0, 0.0, 0.0], ["x", 0.0, 0.0, 0.0]]
)
def test_auto_demotion_recorded_once(iso, caplog, bad):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend="auto")
    caplog.set_level(logging.WARNING, logger="moneta.vector_index")
    vi.upsert(uuid4(), bad, S)
    vi.upsert(uuid4(), [math.inf] * 4, S)  # already python: no second record
    st = vi.scan_seam_status()
    assert st.active == "python" and st.demoted
    assert st.reason == "demoted:nonfinite_upsert"
    assert st.fallbacks == {"demoted:nonfinite_upsert": 1}
    assert st.all_native is False
    warns = [r for r in caplog.records if "demoted" in r.getMessage()]
    assert len(warns) == 1
    before = st.native_calls
    if all(isinstance(x, float) for x in bad):  # the oracle cannot score a str row
        vi.query(rows[0][1], 3)  # python now: not a native call, not a fallback
    st2 = vi.scan_seam_status()
    assert st2.native_calls == before and st2.fallbacks == st.fallbacks
    assert _native.counters()["scan"]["fallbacks"] == {"demoted:nonfinite_upsert": 1}


def test_auto_restore_outside_envelope_recorded(iso):
    _set_state(iso, "loaded")
    vi = VectorIndex(backend="auto")
    snap = {
        "backend": "in_memory",
        "embedding_dim": 2,
        "records": [{"entity_id": str(uuid4()), "vector": [math.nan, 1.0], "state": 0}],
    }
    vi.restore(snap)
    st = vi.scan_seam_status()
    assert st.active == "python" and st.demoted
    assert st.fallbacks == {"demoted:restore_outside_envelope": 1}
    assert len(vi) == 1


def test_auto_restore_without_dim_recorded(iso):
    _set_state(iso, "loaded")
    vi, _ = _filled(backend="auto", n=2)
    vi.restore(
        {"backend": "in_memory", "embedding_dim": None,
         "records": [{"entity_id": str(uuid4()), "vector": [1.0], "state": 0}]}
    )
    st = vi.scan_seam_status()
    assert st.demoted and "demoted:restore_without_dim" in st.fallbacks


# ---------------------------------------------------------------------------
# Require: demotion forbidden, raise before mutation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [[math.inf, 0.0, 1.0, 0.0], [math.nan] * 4, ["x", 1.0, 1.0, 1.0], [10**400, 0, 0, 1], []],
    ids=["inf", "nan", "str", "hugeint", "empty"],
)
def test_require_upsert_outside_envelope_raises_no_mutation(iso, bad):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend="native")
    snap = json.dumps(vi.snapshot(), sort_keys=True)
    with pytest.raises(NativeSeamError):
        vi.upsert(uuid4(), bad, S)
    with pytest.raises(NativeSeamError):
        vi.upsert(rows[0][0], bad, S)  # replace path too
    assert json.dumps(vi.snapshot(), sort_keys=True) == snap
    st = vi.scan_seam_status()
    assert st.active == "native" and not st.demoted and st.fallbacks == {}


def test_require_first_upsert_bad_does_not_latch_dim(iso):
    _set_state(iso, "loaded")
    vi = VectorIndex(backend="native")
    with pytest.raises(NativeSeamError):
        vi.upsert(uuid4(), [], S)
    assert vi._dim is None and len(vi) == 0 and vi._store is None
    vi.upsert(uuid4(), [1.0, 2.0], S)
    assert vi._dim == 2


def test_require_dim_mismatch_stays_valueerror(iso):
    _set_state(iso, "loaded")
    vi, _ = _filled(backend="native")
    with pytest.raises(ValueError) as ei:
        vi.upsert(uuid4(), [1.0, 2.0], S)
    assert not isinstance(ei.value, NativeSeamError)


def test_require_store_refusal_backstop_raises_seam_error(iso):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend="native")
    snap = json.dumps(vi.snapshot(), sort_keys=True)

    def refuse(vec):
        raise ValueError("refused by store")

    iso.setattr(vi._store, "push", refuse)
    with pytest.raises(NativeSeamError) as ei:
        vi.upsert(uuid4(), [1.0, 2.0, 3.0, 4.0], S)
    assert isinstance(ei.value.__cause__, ValueError)
    assert json.dumps(vi.snapshot(), sort_keys=True) == snap
    assert vi.backend == "native" and not vi.demoted


def test_auto_store_refusal_demotes(iso):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend="auto")

    def refuse(vec):
        raise ValueError("refused by store")

    iso.setattr(vi._store, "push", refuse)
    eid = uuid4()
    vi.upsert(eid, [1.0, 2.0, 3.0, 4.0], S)
    assert vi.backend == "python" and vi.demoted and vi.contains(eid)
    assert len(vi) == len(rows) + 1


@pytest.mark.parametrize(
    "snap,key",
    [
        ({"embedding_dim": None, "records": [{"entity_id": None, "vector": [1.0], "state": 0}]},
         "restore_without_dim"),
        ({"embedding_dim": 4, "records": [{"entity_id": None, "vector": [math.nan, 0, 0, 1], "state": 0}]},
         "restore_outside_envelope"),
        ({"embedding_dim": 4, "records": [{"entity_id": None, "vector": [1.0, 0.0], "state": 0}]},
         "restore_outside_envelope"),
        ({"embedding_dim": 4, "records": [{"entity_id": None, "vector": [10**400, 0, 0, 1], "state": 0}]},
         "restore_outside_envelope"),
    ],
)
def test_require_restore_outside_envelope_raises_no_mutation(iso, snap, key):
    _set_state(iso, "loaded")
    vi, _ = _filled(backend="native")
    for rec in snap["records"]:
        rec["entity_id"] = str(uuid4())
    snap["backend"] = "in_memory"
    before = json.dumps(vi.snapshot(), sort_keys=True)
    with pytest.raises(NativeSeamError, match=key):
        vi.restore(snap)
    assert json.dumps(vi.snapshot(), sort_keys=True) == before
    assert vi.backend == "native" and not vi.demoted


def test_require_restore_hugeint_raises_seam_error_no_mutation(iso):
    # math.isfinite(10**400) raises OverflowError; restore must surface it
    # as NativeSeamError, not a bare OverflowError.
    _set_state(iso, "loaded")
    vi = VectorIndex(backend="native")
    vi.upsert(uuid4(), [1.0, 2.0], S)
    dim, n = vi._dim, len(vi)
    snap = {"backend": "in_memory", "embedding_dim": 2,
            "records": [{"entity_id": str(uuid4()), "vector": [10**400, 1.0], "state": 0}]}
    with pytest.raises(NativeSeamError, match="restore_outside_envelope"):
        vi.restore(snap)
    assert vi._dim == dim and len(vi) == n
    assert vi.backend == "native" and not vi.demoted


def test_auto_restore_hugeint_demotes_instead_of_crashing(iso):
    _set_state(iso, "loaded")
    vi = VectorIndex(backend="auto")
    snap = {"backend": "in_memory", "embedding_dim": 2,
            "records": [{"entity_id": str(uuid4()), "vector": [10**400, 1.0], "state": 0}]}
    vi.restore(snap)
    st = vi.scan_seam_status()
    assert st.active == "python" and st.demoted
    assert st.fallbacks == {"demoted:restore_outside_envelope": 1}
    assert len(vi) == 1


def test_require_restore_valid_snapshot_stays_native(iso):
    _set_state(iso, "loaded")
    src, rows = _filled(backend="python")
    vi = VectorIndex(backend="native")
    vi.restore(src.snapshot())
    assert vi.backend == "native"
    assert vi.query(rows[3][1], 5) == src.query(rows[3][1], 5)


def test_require_permits_counted_per_query_oracle_answers(iso):
    _set_state(iso, "loaded")
    vi, rows = _filled(backend="native")
    vi.query([math.nan, 0, 0, 1.0], 3)
    st = vi.scan_seam_status()
    assert st.requested == "require" and st.active == "native" and not st.demoted
    assert st.fallbacks == {"query_nonfinite": 1} and st.all_native is False


def test_check_native_envelope(iso):
    _set_state(iso, "loaded")
    req, _ = _filled(backend="native")
    auto, _ = _filled(backend="auto")
    for bad in ([math.nan, 0, 0, 1], [], ["x", 1, 1, 1], [1.0, 2.0]):
        with pytest.raises(NativeSeamError):
            req.check_native_envelope(bad)
        auto.check_native_envelope(bad)  # no-op outside require
    req.check_native_envelope([1.0, 2.0, 3.0, 4.0])
    fresh = VectorIndex(backend="native")
    fresh.check_native_envelope([1.0, 2.0])  # dim not yet latched
    assert len(req) == 20 and req._dim == 4
