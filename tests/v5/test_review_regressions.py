"""Regressions for the independent review of 22 Sep 2026.

Each test names the finding it pins. Several also close gaps where the
original test passed with the protected property removed (mutation M5-M8,
M2b/c in the review).
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import threading
import uuid

import pytest

from moneta.v5 import (
    Config,
    DimensionMismatchError,
    JournalCorruptError,
    ManualClock,
    PlainPolicyResolver,
    Status,
    Substrate,
    SubstrateClosedError,
    Verdict,
)
from moneta.v5.model import encode_vector

T0 = 1_000_000.0
H = 3600.0


# -- finding 1 (critical): config validated before genesis ----------------


@pytest.mark.parametrize("dim", ["abc", 0, -1, 2.5, True])
def test_bad_embedding_dim_never_reaches_the_journal(tmp_path, dim):
    path = tmp_path / "m"
    with pytest.raises(ValueError):
        Substrate(Config(path=path, embedding_dim=dim))
    assert not path.exists() or path.read_bytes() == b""
    with Substrate(Config(path=path)) as m:  # the path is still usable
        m.deposit("ok", [1.0, 0.0])


@pytest.mark.parametrize("quota", [-1, 1.5, "10", True])
def test_bad_quota_is_rejected_before_opening(tmp_path, quota):
    with pytest.raises(ValueError):
        Substrate(Config(path=tmp_path / "m", protected_quota=quota))


# -- finding 2: compaction removes vectors from revector events too ----------


def test_compact_scrubs_erased_vectors_everywhere(tmp_path):
    m = Substrate(Config(path=tmp_path / "m"))
    a = m.deposit("a", [1.0, 0.0], t=T0)
    b = m.deposit("b", [0.0, 1.0], t=T0)
    new_a = [0.123456789, 0.987654321, 0.5]
    m.revector({a: new_a, b: [0.0, 0.0, 1.0]}, t=T0)
    m.erase([a], t=T0)
    m.compact()
    data = (tmp_path / "m").read_bytes()
    assert encode_vector(new_a).encode() not in data
    assert encode_vector([1.0, 0.0]).encode() not in data
    assert b'"payload":"a"' not in data and b'"payload":"b"' in data
    m.close()
    with Substrate(Config(path=tmp_path / "m")) as again:
        assert again.status_of(a) == Status.ERASED
        assert again.recall([0.0, 0.0, 1.0], 1).items[0].memory.entity_id == b


def test_dimension_survives_erasing_and_compacting_everything(tmp_path):
    m = Substrate(Config(path=tmp_path / "m"))
    a = m.deposit("a", [1.0, 0.0])
    m.erase([a])
    m.compact()
    m.close()
    with Substrate(Config(path=tmp_path / "m")) as again:
        assert again.dim == 2
        with pytest.raises(DimensionMismatchError):
            again.deposit("b", [1.0, 0.0, 0.0])


# -- finding 4: a failed compaction leaves a working handle ---------------


def test_failed_compaction_keeps_the_handle_usable(tmp_path, monkeypatch):
    m = Substrate(Config(path=tmp_path / "m"))
    a = m.deposit("a", [1.0, 0.0])
    m.erase([a])
    real = os.replace

    def eio(src, dst, *args, **kwargs):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "replace", eio)
    with pytest.raises(OSError):
        m.compact()
    monkeypatch.setattr(os, "replace", real)
    assert not (tmp_path / "m.compact.tmp").exists()
    b = m.deposit("b", [0.0, 1.0])  # still writable
    assert m.sync() == m.seq
    m.close()
    with Substrate(Config(path=tmp_path / "m")) as again:
        assert [x.entity_id for x in again.records()] == [b]


def test_sync_on_a_closed_journal_raises_instead_of_pretending(tmp_path):
    from moneta.v5.journal import FileJournal, JournalError

    j = FileJournal(tmp_path / "j")
    j.close()
    with pytest.raises(JournalError):
        j.sync()


# -- finding 5: idempotency keys never resurrect a dead id ------------------


@pytest.mark.parametrize("kill", ["erase", "tombstone"])
def test_key_of_a_dead_memory_deposits_a_new_one(kill):
    with Substrate(Config.ephemeral()) as m:
        old = m.deposit("v1 of the fact", [1.0, 0.0], key="fact")
        getattr(m, kill)([old])
        new = m.deposit("v2 of the fact", [0.0, 1.0], key="fact")
        assert new != old
        assert m.recallable_count() == 1
        assert m.deposit("v2 of the fact", [0.0, 1.0], key="fact") == new  # idempotent again


# -- finding 6: replay equals live ----------------------------------------


def test_reason_must_be_a_string():
    with Substrate(Config.ephemeral()) as m:
        a = m.deposit("a", [1.0, 0.0])
        with pytest.raises(TypeError):
            m.tombstone([a], reason=("gdpr", "t9"))
        with pytest.raises(TypeError):
            m.erase([a], reason=5)


def test_half_life_change_is_recorded_in_the_journal(tmp_path):
    with Substrate(Config(path=tmp_path / "m", half_life_seconds=H)) as m:
        m.deposit("a", [1.0, 0.0], t=T0)
    with Substrate(Config(path=tmp_path / "m", half_life_seconds=2 * H)) as m:
        assert m._fold.half_life_seconds == 2 * H
    notes = [
        json.loads(line[9:])
        for line in (tmp_path / "m").read_bytes().splitlines()
        if b'"half_life_change"' in line
    ]
    assert len(notes) == 1 and notes[0]["from"] == H and notes[0]["half_life_seconds"] == 2 * H
    with Substrate(Config(path=tmp_path / "m", half_life_seconds=2 * H)):
        pass  # same value again: no second note
    assert (tmp_path / "m").read_bytes().count(b'"half_life_change"') == 1


def test_a_fold_failure_after_a_durable_append_stops_the_handle(tmp_path, monkeypatch):
    m = Substrate(Config(path=tmp_path / "m"))
    m.deposit("a", [1.0, 0.0])

    def broken(event):
        raise RuntimeError("simulated fold bug")

    monkeypatch.setattr(m._fold, "apply", broken)
    with pytest.raises(RuntimeError):
        m.deposit("b", [0.0, 1.0])
    with pytest.raises(SubstrateClosedError):
        m.recall([1.0, 0.0])
    m.close()
    with Substrate(Config(path=tmp_path / "m")) as again:  # replay absorbs the event
        assert sorted(x.payload for x in again.records()) == ["a", "b"]


# -- M2b/c: reads leave every field of every record untouched --------------


def _state(s):
    return {
        eid: dataclasses.astuple(rec) for eid, rec in s._fold.records.items()
    }, s._fold.attended_since_pass.copy()


def test_reads_leave_all_record_state_untouched():
    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        a = m.deposit("a", [1.0, 0.0], scope="x", slot="s", t=T0)
        m.deposit("b", [0.0, 1.0], scope="y", slot="s", t=T0)
        m.signal_attention({a: 0.2}, t=T0 + 10)
        m.tombstone([m.deposit("c", [1.0, 1.0], t=T0)], t=T0 + 20)
        before = _state(m)
        for t in (T0, T0 + H, T0 + 30 * H):
            m.recall([1.0, 0.0], 10, t=t)
            m.query([1.0, 0.0], 10, t=t)
            for eid in list(m._fold.records):
                m.explain(eid, t=t)
            m.get_consolidation_manifest(t=t)
            list(m.records(t=t))
            m.describe_context()
        assert _state(m) == before


# -- M5: every fold mutation happens under the substrate lock --------------


def test_every_fold_apply_holds_the_substrate_lock(tmp_path):
    m = Substrate(Config(path=tmp_path / "m", fsync=False))
    eid = m.deposit("hot", [1.0, 0.0])
    real = m._fold.apply
    violations = []

    def checked(event):
        if not m._lock._is_owned():
            violations.append(event["op"])
        return real(event)

    m._fold.apply = checked

    def worker(k):
        for i in range(25):
            m.signal_attention({eid: 0.001 * k}, t=T0 + i)
            m.deposit(f"d{k}-{i}", [float(k), 1.0])

    ts = [threading.Thread(target=worker, args=(k,)) for k in range(1, 7)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    m.run_sleep_pass(t=T0 + 100)
    assert violations == []
    live = _state(m)[0]
    m.close()
    with Substrate(Config(path=tmp_path / "m")) as again:
        assert _state(again)[0] == live  # live execution == journal replay, exactly


# -- M7 / M8: recovery and sequence checks are load-bearing ---------------


def test_recovered_journal_reopens_after_further_writes(tmp_path):
    from moneta.v5.journal import encode_frame

    path = tmp_path / "m"
    with Substrate(Config(path=path)) as m:
        m.deposit("kept", [1.0, 0.0])
    with open(path, "ab") as fp:
        fp.write(encode_frame({"op": "note", "seq": 3, "t": 1.0})[:-5])
    with Substrate(Config(path=path)) as m:
        m.deposit("after", [0.0, 1.0])
    with Substrate(Config(path=path)) as m:
        assert [x.payload for x in m.records()] == ["kept", "after"]


@pytest.mark.parametrize("damage", ["duplicate", "drop"])
def test_sequence_gaps_and_duplicates_are_corruption(tmp_path, damage):
    path = tmp_path / "m"
    with Substrate(Config(path=path)) as m:
        for i in range(3):
            m.deposit(f"r{i}", [1.0, float(i)])
    lines = path.read_bytes().split(b"\n")[:-1]
    if damage == "duplicate":
        lines.insert(2, lines[2])
    else:
        del lines[2]
    path.write_bytes(b"\n".join(lines) + b"\n")
    with pytest.raises(JournalCorruptError, match="seq"):
        Substrate(Config(path=path))


# -- I1 made non-circular: a missing index entry is an error, not a skip ---


def test_index_miss_raises_instead_of_dropping_a_memory():
    with Substrate(Config.ephemeral()) as m:
        a = m.deposit("a", [1.0, 0.0])
        m.deposit("b", [0.0, 1.0])
        m._index.remove(a)  # derived state damaged in memory
        with pytest.raises(KeyError):
            m.recall([1.0, 0.0])


# -- finding 8: resolvers agree on arbitrary validated specs --------------


def _random_spec(rng: random.Random):
    scopes = ["a", "b", "c", "", "a.b"]
    ids = [str(uuid.UUID(int=rng.randrange(1, 50))) for _ in range(4)]
    names = ["default"] + [f"ctx{i}" for i in range(rng.randrange(1, 5))]
    spec = {}
    for i, name in enumerate(names):
        layer = {}
        if i:
            layer["parent"] = rng.choice(names[:i])
        for field in ("include_scopes", "exclude_scopes"):
            if rng.random() < 0.5:
                layer[field] = rng.sample(scopes, rng.randrange(0, len(scopes)))
        if rng.random() < 0.4:
            layer["exclude_records"] = rng.sample(ids, rng.randrange(0, 3))
        if rng.random() < 0.5:
            layer["slots"] = {rng.choice(["s1", "s2", "a slot"]): rng.choice(ids)}
        spec[name] = layer
    return spec


def test_plain_and_usd_resolvers_agree_on_random_specs():
    pytest.importorskip("pxr")
    from moneta.v5.usd import UsdPolicyResolver

    rng = random.Random(20260922)
    for _ in range(60):
        spec = _random_spec(rng)
        plain, usd = PlainPolicyResolver(spec), UsdPolicyResolver.from_spec(spec)
        for ctx in spec:
            assert plain.resolve(ctx).semantic() == usd.resolve(ctx).semantic(), (spec, ctx)
            assert plain.resolve(ctx).fingerprint == usd.resolve(ctx).fingerprint


@pytest.mark.parametrize(
    "layer",
    [
        {"include_scopes": [1, 2]},
        {"include_scopes": ["a", 1]},
        {"exclude_scopes": "a"},
        {"slots": {"s": 5}},
        {"slots": ["s"]},
        {"parent": 3},
    ],
)
def test_invalid_policy_values_are_rejected(layer):
    with pytest.raises((ValueError, TypeError)):
        PlainPolicyResolver({"x": layer})


def test_usd_set_layer_refuses_reparenting():
    pytest.importorskip("pxr")
    from moneta.v5.usd import UsdPolicyResolver

    usd = UsdPolicyResolver.from_spec({"a": {}, "b": {"parent": "a"}})
    usd.set_layer("b", {"parent": "a", "include_scopes": ["x"]})  # same parent: fine
    with pytest.raises(ValueError, match="re-parenting"):
        usd.set_layer("b", {"parent": "default"})
    assert usd.resolve("b").include_scopes == frozenset({"x"})


# -- unrankable after a partial revector is explained ---------------------


def test_partial_revector_leaves_named_records_unrankable():
    with Substrate(Config.ephemeral()) as m:
        a = m.deposit("a", [1.0, 0.0])
        b = m.deposit("b", [0.0, 1.0])
        m.revector({a: [1.0, 0.0, 0.0]}, allow_missing=True)
        assert m.explain(b).verdict == Verdict.UNRANKABLE
        assert [i.memory.entity_id for i in m.recall([1.0, 0.0, 0.0], 5).items] == [a]
        m.revector({a: [1.0, 0.0, 0.0], b: [0.0, 1.0, 0.0]})  # filled in later
        assert m.explain(b).verdict == Verdict.ELIGIBLE


def test_empty_store_can_change_dimension():
    with Substrate(Config.ephemeral(embedding_dim=2)) as m:
        m.revector({}, dim=3)
        assert m.dim == 3
        m.deposit("a", [1.0, 0.0, 0.0])
        with pytest.raises(ValueError):
            m.revector({})  # no dim given and nothing to infer it from


def test_manual_clock_is_deterministic():
    c = ManualClock(5.0)
    assert c.now() == 5.0 and c.advance(2) == 7.0


# -- Round 4 E4 condition 4: id dedup is linear, order-preserving ---------


def test_large_id_list_dedup_is_linear_and_keeps_first_seen_order():
    # 40k distinct ids plus 40k duplicates. The old list-membership dedup
    # took ~11 s on this input (5.58 s for 40k in the Round 4 brief); the
    # dict-based dedup takes well under 0.1 s. The 3 s budget is ~40x the
    # fixed path and ~4x below the quadratic one.
    import time

    n = 40_000
    with Substrate(Config.ephemeral()) as m:
        ids = [m.deposit(f"m{i}", [1.0, float(i % 7)]) for i in range(n)]
        shuffled = ids[:]
        random.Random(4).shuffle(shuffled)
        request = shuffled + ids[::-1] + shuffled[: n // 2]
        expected = [str(e) for e in shuffled]

        start = time.perf_counter()
        keys = m._known(request)
        elapsed = time.perf_counter() - start
        assert keys == expected
        assert elapsed < 3.0, f"dedup of {len(request)} ids took {elapsed:.2f}s"

        start = time.perf_counter()
        m.tombstone(request, t=T0)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"tombstone of {len(request)} ids took {elapsed:.2f}s"
        assert m.recallable_count() == 0
        assert all(m.status_of(e) == Status.TOMBSTONED for e in ids[:100])
