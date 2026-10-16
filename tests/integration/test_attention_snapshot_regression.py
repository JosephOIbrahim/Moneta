"""Regression: undrained attention vs. snapshot + restart (v1.3.0-rc1).

Deposits and attention are tested separately on purpose. Deposits are
snapshot-covered (docs/api.md volatility table); attention is WAL-covered.

SYNAPSE's save() is ``m.durability.snapshot_ecs(m.ecs)``
(tests/v5/test_compat.py:66). ``Moneta.close()`` does NOT snapshot
(api.py:300-320), so close() + Moneta(cfg) models a restart / kill -9.

Expected at v1.3.0-rc1 (and on this branch):
  A  deposit -> snapshot -> reopen: memory present             PASS
  A2 deposit after the last snapshot -> reopen: memory absent  PASS (documented window)
  B  attention -> snapshot (no sleep pass) -> reopen -> sleep  XFAIL (unresolved defect)
  C  attention -> reopen (no intervening snapshot) -> sleep    PASS (WAL replay works)
  D  attention landing between drain and snapshot in a pass    XFAIL (second loss path)
  E  hydrate's ts filter drops pre-snapshot WAL entries        PASS (pins current filter)

B and D are UNRESOLVED DEFECTS, not fixed. They are marked
``xfail(strict=True)``: the assertions state the correct behaviour, the
suite stays green while the defect exists, and the day either one starts
passing the strict mark turns it into a failure so the change is reviewed
deliberately (see docs/design/R1-attention-durability.md). The terminal
summary lists them under "Known unresolved defects" whenever they xfail.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from moneta import Moneta, MonetaConfig

_DEFECT_DOC = "docs/design/R1-attention-durability.md"


def _unresolved(path: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "UNRESOLVED DEFECT: undrained attention lost across snapshot/restart "
            f"(path {path}); see {_DEFECT_DOC}"
        ),
    )


def _cfg(tmp_path: Path, name: str) -> MonetaConfig:
    return MonetaConfig(
        storage_uri=f"moneta-test://attn-snap/{name}",
        snapshot_path=tmp_path / "snapshot.json",
        wal_path=tmp_path / "attention.wal.jsonl",
        half_life_seconds=60.0,  # MIN_HALF_LIFE_SECONDS; makes decay visible
    )


def _save(m: Moneta) -> None:
    """SYNAPSE's save(): the bare snapshot call, no sleep pass."""
    assert m.durability is not None
    m.durability.snapshot_ecs(m.ecs)


# ---------------------------------------------------------------- deposits


def test_A_deposit_survives_snapshot_and_reopen(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "A")
    with Moneta(cfg) as m1:
        eid = m1.deposit("mem_A", [1.0, 0.0])
        _save(m1)
    with Moneta(cfg) as m2:
        mem = m2.ecs.get_memory(eid)
        assert mem is not None and mem.payload == "mem_A"
        assert m2.vector_index.contains(eid)


def test_A2_deposit_after_last_snapshot_is_lost(tmp_path: Path) -> None:
    """Characterization of the documented deposit volatility window."""
    cfg = _cfg(tmp_path, "A2")
    with Moneta(cfg) as m1:
        a = m1.deposit("saved", [1.0, 0.0])
        _save(m1)
        b = m1.deposit("unsaved", [0.0, 1.0])
    with Moneta(cfg) as m2:
        assert m2.ecs.contains(a)
        assert not m2.ecs.contains(b)  # no deposit journal in v1


# --------------------------------------------------------------- attention


@_unresolved("B")
def test_B_undrained_attention_survives_snapshot_and_reopen(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path, "B")
    with Moneta(cfg) as m1:
        attended = m1.deposit("attended", [1.0, 0.0])
        control = m1.deposit("control", [0.0, 1.0])
        _save(m1)                                # save-on-add
        m1.signal_attention({attended: 0.5})     # WAL-appended, undrained
        _save(m1)                                # save again, no sleep pass
    time.sleep(0.05)  # let the control row decay measurably
    with Moneta(cfg) as m2:                      # restart
        result = m2.run_sleep_pass()
        a = m2.ecs.get_memory(attended)
        c = m2.ecs.get_memory(control)
        assert a is not None and c is not None
        # utility reflects the attention: min(1, U + 0.5) = 1.0, then Δt=0 decay
        assert a.utility == 1.0 and c.utility < 1.0, (a.utility, c.utility)
        assert a.attended_count == 1
        assert result.attention_updated == 1


def test_C_attention_wal_replay_without_intervening_snapshot(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path, "C")
    with Moneta(cfg) as m1:
        attended = m1.deposit("attended", [1.0, 0.0])
        control = m1.deposit("control", [0.0, 1.0])
        _save(m1)
        m1.signal_attention({attended: 0.5})
        # no second snapshot
    time.sleep(0.05)
    with Moneta(cfg) as m2:
        result = m2.run_sleep_pass()
        a = m2.ecs.get_memory(attended)
        c = m2.ecs.get_memory(control)
        assert a is not None and c is not None
        assert a.utility == 1.0 and c.utility < 1.0, (a.utility, c.utility)
        assert a.attended_count == 1
        assert result.attention_updated == 1


@_unresolved("D")
def test_D_attention_between_drain_and_pass_snapshot_survives(
    tmp_path: Path,
) -> None:
    """A signal that lands after run_pass drained the log but before
    run_sleep_pass's snapshot_ecs (api.py:455-467). Simulated by wrapping
    the runner; in production this is a concurrent signal_attention."""
    cfg = _cfg(tmp_path, "D")
    with Moneta(cfg) as m1:
        eid = m1.deposit("late", [1.0, 0.0])
        _save(m1)
        orig = m1.consolidation.run_pass

        def run_pass_then_signal(**kw):
            r = orig(**kw)
            m1.signal_attention({eid: 0.5})  # in buffer + WAL, after drain
            return r

        m1.consolidation.run_pass = run_pass_then_signal  # type: ignore[method-assign]
        m1.run_sleep_pass()  # snapshot_ecs then unlinks the WAL
        assert len(m1.attention) == 1  # still undrained in memory
    with Moneta(cfg) as m2:
        m2.run_sleep_pass()
        mem = m2.ecs.get_memory(eid)
        assert mem is not None
        assert mem.attended_count == 1


def test_E_hydrate_filters_wal_entries_older_than_snapshot(
    tmp_path: Path,
) -> None:
    """Pins durability.py:218. Matters for repair option (a): rewriting
    undrained entries into the WAL with their original timestamps would
    be silently filtered out on hydrate."""
    cfg = _cfg(tmp_path, "E")
    with Moneta(cfg) as m1:
        eid = m1.deposit("x", [1.0, 0.0])
        _save(m1)
    snap_ts = json.loads(cfg.snapshot_path.read_text())["snapshot_created_at"]  # type: ignore[union-attr]
    line = {"wal_version": 1, "entity_id": str(eid), "weight": 0.5}
    cfg.wal_path.write_text(  # type: ignore[union-attr]
        json.dumps({**line, "timestamp": snap_ts - 1.0}) + "\n"
        + json.dumps({**line, "entity_id": str(uuid4()), "timestamp": snap_ts + 1.0})
        + "\n"
    )
    with Moneta(cfg) as m2:
        assert len(m2.attention) == 1  # only the post-snapshot entry replays
