"""Conformance suite: the eight invariants, against the twelve-record fixture.

I1 recoverability · I2 generation purity · I3 append-only claims ·
I4 derived is never authoritative · I5 authorization narrows only ·
I6 determinism at pinned t_eval · I7 four distinct states ·
I8 attention ordering without a GIL assumption.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from moneta.v5 import (
    Config,
    DimensionMismatchError,
    ManualClock,
    Status,
    Substrate,
    UnknownEntityError,
    Verdict,
)
from moneta.v5.model import decode_vector

from .conftest import author_plain
from .fixture import HALF_LIFE, ORACLE, QUERY, SCORES, T0, build


def names(result, ids):
    by_id = {v: k for k, v in ids.items()}
    return [by_id[i.memory.entity_id] for i in result.items]


# ----------------------------------------------------------------------
# Oracle
# ----------------------------------------------------------------------


@pytest.mark.parametrize("context", sorted(ORACLE))
def test_oracle_order_and_scores(world, context):
    s, ids = world
    result = s.recall(QUERY, 20, context=context, t=T0)
    assert names(result, ids) == ORACLE[context]
    for item, name in zip(result.items, ORACLE[context], strict=False):
        assert item.score == pytest.approx(SCORES[name], abs=1e-12)


def test_changing_authored_policy_changes_eligibility(world):
    s, ids = world
    resolver = s.policy
    before = s.recall(QUERY, 20, context="projA", t=T0)
    spec = resolver.spec()["projA"]
    resolver.set_layer("projA", {**spec, "exclude_scopes": []})  # stop excluding scratch
    after = s.recall(QUERY, 20, context="projA", t=T0)
    assert "A3" not in names(before, ids)
    assert names(after, ids) == ["A1", "A3", "C2", "A2", "P", "S1", "D", "S2", "X"]
    assert before.generation.policy_fingerprint != after.generation.policy_fingerprint


# ----------------------------------------------------------------------
# I1 recoverability
# ----------------------------------------------------------------------


def test_i1_reopen_reproduces_results_exactly(tmp_path, clock):
    path = tmp_path / "m.v5.journal"
    s = Substrate(Config(path=path, half_life_seconds=HALF_LIFE, clock=clock))
    ids = build(s)
    policy = author_plain(ids)
    s.use_policy(policy)
    s.signal_attention({ids["D"]: 0.5}, t=T0 - 60)
    before = {c: s.recall(QUERY, 20, context=c, t=T0) for c in ORACLE}
    s.close()  # no sleep pass, no checkpoint: the journal alone must suffice

    s2 = Substrate(Config(path=path, half_life_seconds=HALF_LIFE, clock=clock, policy=policy))
    try:
        for c, r in before.items():
            again = s2.recall(QUERY, 20, context=c, t=T0)
            assert [(i.memory.entity_id, i.score) for i in again.items] == [
                (i.memory.entity_id, i.score) for i in r.items
            ]
            assert again.generation == r.generation
    finally:
        s2.close()


def test_i1_index_is_rebuilt_not_trusted(world):
    s, ids = world
    before = s.recall(QUERY, 20, t=T0)
    s._index = type(s._index)()  # throw the derived index away entirely
    for rec in s._fold.recallable():
        s._index.add(rec.entity_id, rec.unit)
    assert [i.memory.entity_id for i in s.recall(QUERY, 20, t=T0).items] == [
        i.memory.entity_id for i in before.items
    ]


# ----------------------------------------------------------------------
# I2 generation purity
# ----------------------------------------------------------------------


class _PausingResolver:
    """Pauses inside resolve() so another thread can try to interleave."""

    def __init__(self, inner):
        self.inner = inner
        self.entered = threading.Event()
        self.release = threading.Event()

    def contexts(self):
        return self.inner.contexts()

    def resolve(self, context):
        policy = self.inner.resolve(context)
        self.entered.set()
        self.release.wait(5)
        return policy


def test_i2_writes_and_policy_edits_cannot_interleave_a_query(world):
    s, ids = world
    plain = s.policy
    pausing = _PausingResolver(plain)
    s.use_policy(pausing)
    out = {}

    def reader():
        out["result"] = s.recall(QUERY, 20, context="projA", t=T0)

    def writer():
        pausing.entered.wait(5)
        # A policy edit and a new top-scoring deposit, both mid-query.
        plain.set_layer("projA", {"parent": "default", "include_scopes": ["projB"]})
        out["late"] = s.deposit("late arrival", [1.0, 0, 0, 0], scope="projA", t=T0)

    r = threading.Thread(target=reader)
    w = threading.Thread(target=writer)
    r.start()
    w.start()
    pausing.entered.wait(5)
    threading.Event().wait(0.2)  # give the writer every chance to interleave
    pausing.release.set()
    r.join(5)
    w.join(5)

    result = out["result"]
    assert names(result, ids) == ORACLE["projA"]  # old policy, complete
    assert out["late"] not in [i.memory.entity_id for i in result.items]
    assert result.generation.seq < s.seq  # pinned before the write
    assert result.policy.include_scopes == frozenset({"projA", "projA.scratch", "shared"})


def test_i2_every_result_echoes_its_generation(world):
    s, ids = world
    r = s.recall(QUERY, 3, context="projB", t=T0 + 5)
    assert r.generation.seq == s.seq
    assert r.generation.t_eval == T0 + 5
    assert r.generation.context == "projB"
    assert r.generation.policy_fingerprint == s.describe_context("projB").fingerprint


# ----------------------------------------------------------------------
# I3 append-only claims
# ----------------------------------------------------------------------


def test_i3_contradictory_claims_coexist_and_context_picks(world):
    s, ids = world
    for ctx, winner, loser in (("projA", "C2", "C1"), ("projB", "C1", "C2")):
        assert s.explain(ids[winner], context=ctx, t=T0).verdict == Verdict.ELIGIBLE
        e = s.explain(ids[loser], context=ctx, t=T0)
        assert e.verdict == Verdict.SLOT_LOSER
        assert e.slot_winner == ids[winner]
        assert e.payload is not None  # the losing claim is still fully there


def test_i3_journal_bytes_only_ever_grow(world):
    s, ids = world
    path = s.journal_path
    prefix = path.read_bytes()
    s.signal_attention({ids["A1"]: 0.1}, t=T0 + 1)
    s.run_sleep_pass(t=T0 + 2)
    s.tombstone([ids["S2"]], t=T0 + 3)
    assert path.read_bytes().startswith(prefix)


# ----------------------------------------------------------------------
# I4 derived state is never authoritative; no silent empties
# ----------------------------------------------------------------------


def test_i4_wrong_dimension_query_raises(world):
    s, _ = world
    with pytest.raises(DimensionMismatchError):
        s.recall([1.0, 0.0, 0.0], t=T0)


def test_i4_rejected_deposit_leaves_no_trace(world):
    s, _ = world
    seq, count = s.seq, s.recallable_count()
    size = s.journal_path.stat().st_size
    for bad in ([1.0, 0.0], [math.nan, 0, 0, 0], [0.0, 0.0, 0.0, 0.0], "text"):
        with pytest.raises((ValueError, TypeError)):
            s.deposit("bad", bad, t=T0)
    assert (s.seq, s.recallable_count(), s.journal_path.stat().st_size) == (seq, count, size)


def test_i4_attention_is_all_or_nothing(world):
    s, ids = world
    seq = s.seq
    import uuid

    with pytest.raises(UnknownEntityError):
        s.signal_attention({ids["A1"]: 0.1, uuid.uuid4(): 0.1}, t=T0)
    for bad in (-0.1, 1.5, math.nan, math.inf):
        with pytest.raises(ValueError):
            s.signal_attention({ids["A1"]: 0.1, ids["A2"]: bad}, t=T0)
    assert s.seq == seq


# ----------------------------------------------------------------------
# I5 authorization narrows only
# ----------------------------------------------------------------------


def test_i5_caller_scopes_narrow_a_permissive_policy(world):
    s, ids = world
    r = s.recall(QUERY, 20, context="default", allowed_scopes={"projA"}, t=T0)
    assert {i.scope for i in r.items} == {"projA"}


def test_i5_caller_scopes_cannot_widen_a_policy(world):
    s, ids = world
    r = s.recall(
        QUERY, 20, context="projA", allowed_scopes={"projA", "projB", "projA.scratch"}, t=T0
    )
    assert names(r, ids) == [n for n in ORACLE["projA"] if n not in ("C2", "P", "S1", "S2")]
    assert (
        s.explain(ids["A3"], context="projA", allowed_scopes={"projA.scratch"}).verdict
        == Verdict.EXCLUDED_SCOPE
    )
    assert (
        s.explain(ids["B1"], context="projA", allowed_scopes={"projA"}).verdict
        == Verdict.NOT_ALLOWED
    )


def test_i5_allowed_scopes_must_be_a_collection(world):
    s, _ = world
    with pytest.raises(TypeError):
        s.recall(QUERY, allowed_scopes="projA", t=T0)


# ----------------------------------------------------------------------
# I6 determinism
# ----------------------------------------------------------------------


def test_i6_same_journal_same_answers_in_another_process(world, tmp_path):
    s, ids = world
    s.signal_attention({ids["D"]: 0.3, ids["S1"]: 0.2}, t=T0 - 100)
    here = [(str(i.memory.entity_id), repr(i.score)) for i in s.recall(QUERY, 20, t=T0).items]
    copy = tmp_path / "copy.v5.journal"
    shutil.copy(s.journal_path, copy)
    code = f"""
import json
from moneta.v5 import Substrate, Config
with Substrate(Config(path={str(copy)!r}, half_life_seconds={HALF_LIFE})) as m:
    r = m.recall({QUERY!r}, 20, t={T0!r})
    print(json.dumps([(str(i.memory.entity_id), repr(i.score)) for i in r.items]))
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    there = [tuple(x) for x in json.loads(out.stdout.strip().splitlines()[-1])]
    assert there == here


def test_i6_reads_never_write(world):
    s, ids = world
    seq = s.seq
    size = s.journal_path.stat().st_size
    for _ in range(3):
        s.recall(QUERY, 5, t=T0 + 10_000)
        s.explain(ids["A1"], t=T0 + 10_000)
        s.get_consolidation_manifest(t=T0 + 10_000)
    assert (s.seq, s.journal_path.stat().st_size) == (seq, size)
    assert s.recall(QUERY, 1, t=T0).items[0].score == pytest.approx(1.0)


def test_i6_ties_break_by_deposit_order(world):
    s, ids = world
    r = s.recall(QUERY, 20, context="projA", t=T0)
    order = names(r, ids)
    assert order.index("A2") < order.index("P")  # equal scores, A2 deposited first


# ----------------------------------------------------------------------
# I7 four distinct states
# ----------------------------------------------------------------------


def test_i7_resident_excluded_tombstoned_erased_are_distinct(world):
    s, ids = world
    s.tombstone([ids["S1"]], reason="superseded", t=T0)
    s.erase([ids["S2"]], t=T0)
    verdicts = {
        n: s.explain(ids[n], context="projA", t=T0).verdict for n in ("A1", "A3", "S1", "S2")
    }
    assert verdicts == {
        "A1": Verdict.ELIGIBLE,
        "A3": Verdict.EXCLUDED_SCOPE,
        "S1": Verdict.TOMBSTONED,
        "S2": Verdict.ERASED,
    }
    assert s.explain(ids["S1"]).payload == "studio: OCIO is ACEScg"
    assert s.explain(ids["S2"]).payload is None


def test_i7_erase_plus_compact_removes_bytes(world):
    s, ids = world
    secret = "legal hold: never delete"
    assert secret.encode() in s.journal_path.read_bytes()
    s.erase([ids["P"]], t=T0)
    assert secret.encode() in s.journal_path.read_bytes()  # derived state only, until compact
    report = s.compact()
    assert report["events_scrubbed"] == 1
    assert secret.encode() not in s.journal_path.read_bytes()
    path = s.journal_path
    s.close()
    with Substrate(Config(path=path, half_life_seconds=HALF_LIFE)) as again:
        assert again.status_of(ids["P"]) == Status.ERASED
        assert again.recallable_count() == 11


# ----------------------------------------------------------------------
# I8 attention ordering without the GIL
# ----------------------------------------------------------------------


def test_i8_concurrent_signals_reduce_in_journal_order(tmp_path):
    clock = ManualClock(T0)
    path = tmp_path / "a.v5.journal"
    s = Substrate(Config(path=path, half_life_seconds=HALF_LIFE, clock=clock, fsync=False))
    eid = s.deposit("hot", [1.0, 0.0], t=T0 - HALF_LIFE)  # utility 0.5 at T0
    threads, per = 8, 50

    def worker():
        for _ in range(per):
            s.signal_attention({eid: 0.001})

    ts = [threading.Thread(target=worker) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    e = s.explain(eid, t=T0)
    assert e.attended == threads * per
    expected = 0.5
    for _ in range(threads * per):
        expected = min(1.0, expected + 0.001)
    assert e.utility == pytest.approx(expected, abs=1e-12)
    s.close()
    with Substrate(Config(path=path, half_life_seconds=HALF_LIFE, clock=clock)) as again:
        assert again.explain(eid, t=T0).utility == e.utility


def test_i8_no_gil_sentinel_in_v5():
    source = Path(__file__).resolve().parents[2] / "src" / "moneta" / "v5"
    for py in source.rglob("*.py"):
        assert "_is_gil_enabled" not in py.read_text(), py


# ----------------------------------------------------------------------
# Journal encoding is exact
# ----------------------------------------------------------------------


def test_vectors_round_trip_bit_exact(world):
    s, ids = world
    lines = s.journal_path.read_bytes().splitlines()
    event = json.loads(lines[1][9:])
    assert decode_vector(event["emb"]) == (1.0, 0.0, 0.0, 0.0)
    tricky = [0.1, 1e-300, -2.5e17, 3.141592653589793]
    eid = s.deposit("tricky", tricky, t=T0)
    path = s.journal_path
    s.close()
    with Substrate(Config(path=path, half_life_seconds=HALF_LIFE)) as again:
        assert again._fold.records[eid].vector == tuple(tricky)
