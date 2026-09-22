"""pytest plugin: make `from moneta import Moneta` return the v5 compat facade.

With MONETA_V5_PORT_HELPERS=1 it also re-points two SYNAPSE *test helpers*
that write v1 private ECS columns (`ecs._last_evaluated`, `ecs._ids`) at
their exact v5 equivalents. Production code is never patched.
"""
import os
import time

import moneta
import moneta.v5.compat as _compat
from moneta.v5.model import RECALLABLE

moneta.Moneta = _compat.Moneta


def _v5_backdate(store, seconds_ago=100_000):
    # v1 helper: set every row's LastEvaluated to `past`, utility unchanged.
    # v5 equivalent: move every record's decay anchor time to `past`.
    s = store._handle.v5
    past = time.time() - seconds_ago
    with s._lock:
        for rec in s._fold.records.values():
            rec.anchor_t = past


def _v5_assert_consistent(store):
    s = store._handle.v5
    with s._lock:
        ranked = {r.entity_id for r in s._fold.records.values()
                  if r.status in RECALLABLE and r.unit is not None}
        assert set(s._index._units) == ranked, "index desync from fold"
        assert s._fold.last_seq == s._journal.last_seq, "fold behind journal"


def pytest_collection_finish(session):
    if os.environ.get("MONETA_V5_PORT_HELPERS") != "1":
        return
    seen = set()
    for item in session.items:
        mod = getattr(item, "module", None)
        if mod is None or id(mod) in seen:
            continue
        seen.add(id(mod))
        if hasattr(mod, "_backdate"):
            default = mod._backdate.__defaults__[0]
            mod._backdate = lambda store, seconds_ago=default: _v5_backdate(store, seconds_ago)
        if hasattr(mod, "_assert_ecs_consistent"):
            mod._assert_ecs_consistent = _v5_assert_consistent
