from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from moneta.v5 import Config, ManualClock, PlainPolicyResolver, Substrate

from .fixture import HALF_LIFE, T0, build, policy_spec


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(T0)


@pytest.fixture
def open_substrate(tmp_path: Path, clock: ManualClock) -> Iterator[Callable[..., Substrate]]:
    """Factory for file-backed substrates; everything opened is closed on teardown."""
    opened: list[Substrate] = []

    def _open(path: Path | None = None, **kwargs) -> Substrate:
        kwargs.setdefault("half_life_seconds", HALF_LIFE)
        kwargs.setdefault("clock", clock)
        s = Substrate(
            Config(path=path if path is not None else tmp_path / "m.v5.journal", **kwargs)
        )
        opened.append(s)
        return s

    yield _open
    for s in opened:
        s.close()


def author_plain(ids) -> PlainPolicyResolver:
    spec = policy_spec(ids)
    resolver = PlainPolicyResolver()
    for name in ("default", "projA", "projB", "projA.review"):
        resolver.set_layer(name, spec[name])
    return resolver


@pytest.fixture
def world(open_substrate):
    """The fixture store with plain policy. Returns (substrate, ids)."""
    s = open_substrate()
    ids = build(s)
    s.use_policy(author_plain(ids))
    return s, ids
