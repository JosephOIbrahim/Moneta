"""`get_consolidation_manifest` implementation.

ARCHITECTURE.md §2 (the fourth op). `api.get_consolidation_manifest`
delegates here. Consolidation Engineer replaces Substrate Engineer's
Pass 2 stub return value.

Contract: return every entity currently in `STAGED_FOR_SYNC`. The
`get_consolidation_manifest` API surface lives in `api.py`; this module
holds the selection logic so that future filters (age, target sublayer,
minimum batch size) can be added without touching api.py.
"""

from __future__ import annotations

from typing import List

from .ecs import ECS
from .types import Memory


def build_manifest(ecs: ECS) -> List[Memory]:
    """Return every entity currently in `STAGED_FOR_SYNC` state.

    Phase 1: direct passthrough to `ecs.staged_entities()`. Future
    filters (age, target sublayer grouping, minimum batch size) land
    here without touching the api.py layer.
    """
    return ecs.staged_entities()
