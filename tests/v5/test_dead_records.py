"""Round 4 E4 blocking condition 1: dead records do not slow recall.

The fold keeps a live map (the recallable records, in deposit order) beside
the full record map. Reads walk the live map only; ``explain`` still answers
for dead ids. These tests pin the invariant that makes that safe, that the
read path never visits a dead record, and that no verdict, ordering or
result changes. The latency gate itself is measured by
``scripts/v5/bench_dead_records.py`` (results/bench_v5_dead_records.jsonl).
"""

from __future__ import annotations

import math
import uuid

from moneta.v5 import Config, Status, Substrate, Verdict
from moneta.v5.model import RECALLABLE, Fold, encode_vector

T0 = 1_000_000.0
H = 3600.0


def _assert_live_matches(fold: Fold) -> None:
    expected = [eid for eid, r in fold.records.items() if r.status in RECALLABLE]
    assert list(fold.live) == expected  # same members, same (deposit) order
    for eid, rec in fold.live.items():
        assert fold.records[eid] is rec


def _churn(m: Substrate) -> dict[str, uuid.UUID]:
    """Every status transition the substrate can make, with checks in between."""
    ids = {
        "keep": m.deposit("keep", [1.0, 0.0], t=T0),
        "keyed": m.deposit("keyed", [0.9, 0.1], key="k", t=T0),
        "slot_old": m.deposit("slot old", [0.7, 0.3], slot="s", t=T0),
        "slot_new": m.deposit("slot new", [0.6, 0.4], slot="s", t=T0 + 1),
        "decays": m.deposit("decays", [0.5, 0.5], t=T0),
        "stages": m.deposit("stages", [0.4, 0.6], t=T0),
        "flat": m.deposit("flat", [0.0, 0.0], t=T0),
        "doomed": m.deposit("doomed", [0.2, 0.8], t=T0),
    }
    _assert_live_matches(m._fold)
    for _ in range(3):
        m.signal_attention({ids["stages"]: 0.1, ids["keep"]: 1.0}, t=T0 + 10)
    _assert_live_matches(m._fold)
    m.signal_attention({ids["keep"]: 1.0, ids["keyed"]: 1.0}, t=T0 + 3 * H)
    m.signal_attention({ids["slot_old"]: 1.0, ids["slot_new"]: 1.0}, t=T0 + 3 * H)
    m.signal_attention({ids["flat"]: 1.0, ids["doomed"]: 1.0}, t=T0 + 3 * H)
    # "decays" is never attended: the pass tombstones it; "stages" is staged
    # and consolidated by the same pass.
    result = m.run_sleep_pass(t=T0 + 4 * H)
    assert ids["decays"] in result.pruned_ids
    assert ids["stages"] in result.consolidated_ids
    _assert_live_matches(m._fold)
    m.tombstone([ids["keyed"]], t=T0 + 4 * H + 1)
    ids["rekeyed"] = m.deposit("keyed again", [0.9, 0.1], key="k", t=T0 + 4 * H + 2)
    m.erase([ids["doomed"], ids["decays"]], t=T0 + 4 * H + 3)
    _assert_live_matches(m._fold)
    live = [eid for eid, r in m._fold.records.items() if r.status in RECALLABLE]
    m.revector({eid: [1.0, 0.0, float(i)] for i, eid in enumerate(live)}, t=T0 + 4 * H + 4)
    _assert_live_matches(m._fold)
    return ids


def test_live_map_tracks_every_transition_and_survives_replay_and_compact(tmp_path):
    path = tmp_path / "m.v5.journal"
    with Substrate(Config(path=path, half_life_seconds=H)) as m:
        ids = _churn(m)
        statuses = {eid: r.status for eid, r in m._fold.records.items()}
        assert statuses[ids["keep"]] == Status.LIVE
        assert statuses[ids["stages"]] == Status.CONSOLIDATED
        assert statuses[ids["decays"]] == Status.ERASED
        assert statuses[ids["keyed"]] == Status.TOMBSTONED
        before = list(m._fold.live)
        m.compact()  # erased deposits replay through the "erased" branch
    with Substrate(Config(path=path, half_life_seconds=H)) as again:
        _assert_live_matches(again._fold)
        assert list(again._fold.live) == before
        assert {eid: r.status for eid, r in again._fold.records.items()} == statuses


def test_live_map_excludes_dead_imports():
    fold = Fold()
    fold.apply({"op": "genesis", "seq": 1, "t": T0, "dim": 2, "half_life_seconds": H})
    base = {"op": "import", "t": T0, "u": 0.5, "anchor_t": T0}
    rows = [
        ("ok", [1.0, 0.0], "live", None),
        ("nan", [math.nan, 1.0], "live", None),  # tombstoned by the fold
        ("dead", [0.0, 1.0], "tombstoned", "v1_pruned"),
        ("staged", [1.0, 1.0], "staged", None),
    ]
    for i, (name, vec, status, reason) in enumerate(rows, start=2):
        e = dict(base, seq=i, id=str(uuid.uuid5(uuid.NAMESPACE_OID, name)))
        e.update(emb=encode_vector(vec), status=status, payload=name)
        if reason:
            e["reason"] = reason
        fold.apply(e)
    fold.apply(
        dict(
            base,
            op="deposit",
            seq=6,
            id=str(uuid.uuid5(uuid.NAMESPACE_OID, "scrubbed")),
            emb=None,
            dim=2,
            erased=True,
        )
    )
    _assert_live_matches(fold)
    assert sorted(r.payload for r in fold.live.values()) == ["ok", "staged"]


def test_read_path_never_visits_dead_records():
    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        live = [
            m.deposit(f"live {i}", [1.0, float(i)], slot="s" if i < 2 else None, t=T0)
            for i in range(4)
        ]
        dead = [m.deposit(f"dead {i}", [1.0, float(i)], slot="s", t=T0 + 1) for i in range(50)]
        m.tombstone(dead[:40], t=T0 + 2)
        m.erase(dead[40:], t=T0 + 3)
        policy = m._resolve(None)
        ruled, winners, eligible = m._classify(policy, None)
        # O(live): no dead record was walked, and each live one exactly once
        assert sorted(r.seq for r, _ in ruled) == sorted(m._fold.records[e].seq for e in live)
        assert set(m._verdicts(policy, None)[0]) == set(live)
        assert winners == {"s": live[1]}  # dead claims never win a slot
        assert [r.entity_id for r in eligible] == live[1:]


def test_dead_records_change_no_result_verdict_or_order():
    """Same live set with and without dead records: identical observable output."""

    def build(n_dead: int) -> tuple[Substrate, list[uuid.UUID], list[uuid.UUID]]:
        m = Substrate(Config.ephemeral(half_life_seconds=H))
        live, dead = [], []
        for i in range(12):
            for j in range(n_dead):
                dead.append(
                    m.deposit(f"dead {i}.{j}", [1.0, 0.1 * j], slot=f"s{i % 3}", scope="x", t=T0)
                )
            # duplicate vectors exercise the deposit-order tie-break
            live.append(
                m.deposit(
                    f"live {i}",
                    [1.0, float(i % 4)],
                    slot=f"s{i % 3}" if i % 2 else None,
                    scope="x" if i % 3 else "y",
                    t=T0 + i,
                )
            )
        if dead:
            m.tombstone(dead[::2], t=T0 + 100)
            m.erase(dead[1::2], t=T0 + 101)
        m.signal_attention({live[3]: 0.5, live[7]: 0.2}, t=T0 + 200)
        return m, live, dead

    clean, clean_live, _ = build(0)
    dirty, dirty_live, dirty_dead = build(5)
    names = {e: f"#{i}" for i, e in enumerate(clean_live)} | {
        e: f"#{i}" for i, e in enumerate(dirty_live)
    }

    def view(m: Substrate, live: list[uuid.UUID], **kw):
        out = []
        for q in ([1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 3.0]):
            r = m.recall(q, 20, t=T0 + 300, **kw)
            out.append([(names[i.memory.entity_id], i.score, i.cosine) for i in r.items])
        for e in live:
            x = m.explain(e, t=T0 + 300, **kw)
            out.append((names[e], x.verdict, names.get(x.slot_winner), x.utility))
        return out

    for kw in ({}, {"allowed_scopes": ["x"]}):
        assert view(clean, clean_live, **kw) == view(dirty, dirty_live, **kw)
    assert clean.recallable_count() == dirty.recallable_count() == 12
    # dead ids still explain, with the same detail as before the live map
    _, winners, _ = dirty._classify(dirty._resolve(None), None)
    for i, e in enumerate(dirty_dead):
        x = dirty.explain(e, t=T0 + 300)
        if i % 2 == 0:
            assert x.verdict == Verdict.TOMBSTONED and x.payload is not None
            assert x.detail.startswith("tombstoned (operator) at seq ")
        else:
            assert x.verdict == Verdict.ERASED and x.payload is None
            assert x.detail.startswith("erased at seq ")
        # slot winner is the live winner, exactly as when dead ids were walked
        assert x.slot is not None and x.slot_winner == winners.get(x.slot)
        assert x.slot_winner in dirty_live
    clean.close()
    dirty.close()


def test_bulk_tombstone_leaves_no_stale_slots_behind():
    """After a batch kills most records, the live map and the index are re-packed.

    A dict keeps its table after deletions, the native store keeps killed
    slots until compacted, and surviving records stay where they were
    allocated, among the dead. So survivors of a bulk tombstone are copied
    into fresh memory and the index is rebuilt. ``sys.getsizeof`` of a dict
    reports its table, so a re-packed map is the size of a fresh copy.
    """
    import sys

    with Substrate(Config.ephemeral(half_life_seconds=H)) as m:
        ids = [m.deposit(f"m {i}", [1.0, float(i)], t=T0) for i in range(3000)]
        dead, live = ids[:2900], ids[2900:]
        survivor, index = m._fold.records[live[0]], m._index
        m.tombstone(dead, t=T0 + 1)
        # survivors were copied into fresh memory and the index rebuilt
        assert m._fold.records[live[0]] is not survivor
        assert m._fold.records[live[0]] == survivor
        assert m._index is not index
        assert sys.getsizeof(m._fold.live) == sys.getsizeof(dict(m._fold.live))
        assert sys.getsizeof(m._index._units) == sys.getsizeof(dict(m._index._units))
        if m._index.native:
            assert m._index._store.slots() == len(live)
        m.erase(live[:90], t=T0 + 2)
        assert sys.getsizeof(m._fold.live) == sys.getsizeof(dict(m._fold.live))
        assert list(m._fold.live) == live[90:]
        assert [i.memory.entity_id for i in m.recall([1.0, 99.0], 3, t=T0 + 3).items]
        _assert_live_matches(m._fold)
