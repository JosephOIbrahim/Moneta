"""Moneta type definitions.

ARCHITECTURE.md §3 defines the hot-tier schema. `Memory` is the agent-facing
projection of an ECS row; `EntityState` is the lifecycle enum.

These types are the stable handoff surface between Substrate, Persistence,
Consolidation, and Test Engineer. Changes here ripple downstream — avoid
breaking field names or types without an Architect review.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
from uuid import UUID


class EntityState(IntEnum):
    """ECS entity lifecycle (ARCHITECTURE.md §3).

    VOLATILE         — fresh deposit, fully in hot tier.
    STAGED_FOR_SYNC  — Consolidation Engineer has flagged it for USD authoring
                       (Phase 3); still in hot tier until the sleep pass commits.
    CONSOLIDATED     — successfully authored to USD (Phase 3 only).
    """

    VOLATILE = 0
    STAGED_FOR_SYNC = 1
    CONSOLIDATED = 2


@dataclass(frozen=True)
class Memory:
    """Agent-facing projection of an ECS row (ARCHITECTURE.md §3).

    Returned from `query()` and `get_consolidation_manifest()`. Frozen:
    mutations flow back through `signal_attention()`, never through this
    object. A `Memory` is a snapshot at the moment of the call.

    Field names are the snake_case projection of MONETA.md §2.2 / ARCHITECTURE.md
    §3's PascalCase schema columns:

        EntityID       → entity_id
        SemanticVector → semantic_vector
        Payload        → payload
        Utility        → utility
        AttendedCount  → attended_count
        ProtectedFloor → protected_floor
        LastEvaluated  → last_evaluated
        State          → state
        UsdLink        → usd_link

    Note: the deposit API parameter is `embedding` (verbatim from MONETA.md
    §2.1), which is the same data as the stored `semantic_vector`. The two
    names reflect different conceptual roles — the agent's embedder produces
    an `embedding`; the ECS stores it as a `semantic_vector` used for miss
    detection.

    The `usd_link` field is typed as `object` in Phase 1 because Phase 1 has
    zero USD dependency — no `pxr` import is permitted. Phase 3 will narrow
    this to `SdfPath`.
    """

    entity_id: UUID
    payload: str
    semantic_vector: list[float]
    utility: float
    attended_count: int
    protected_floor: float
    last_evaluated: float  # wall-clock unix seconds
    state: EntityState
    usd_link: Optional[object] = None
