"""Real USD authoring target — Sdf-level writes via pxr.

ARCHITECTURE.md §15. Phase 3 Pass 3. First pxr import in src/moneta/.

This module implements the AuthoringTarget Protocol from sequential_writer.py
as a drop-in replacement for MockUsdTarget. The MockUsdTarget is kept
alongside for A/B validation through Phase 3 Pass 6.

Authoring pattern
-----------------
All writes use the Sdf-level API (Sdf.CreatePrimInLayer + Sdf.AttributeSpec)
inside Sdf.ChangeBlock, NOT UsdStage.DefinePrim. This matches the benchmark
(scripts/usd_metabolism_bench_v2.py) and avoids the USD 0.25.5
DefinePrim-inside-ChangeBlock-with-sublayers incompatibility (stage.cpp:3889).

Prim naming discipline
----------------------
Prim names are strictly UUID-hex: ``/Memory_<hex>``. Never derived from
payload content. Natural language goes in string attributes on the prim,
not in the prim path. This is substrate convention #1 and guards against
the TfToken registry OOM trap (Round 2 §6.3).

Sublayer routing
----------------
- Protected memories (protected_floor > 0.0): ``cortex_protected.usda``
  at strongest Root stack position (substrate convention #4).
- Unprotected memories: ``cortex_YYYY_MM_DD.usda`` using UTC date
  (substrate convention #6).

Sublayer rotation (ARCHITECTURE.md §15.2 constraint #1)
-------------------------------------------------------
When a rolling daily sublayer reaches ``rotation_cap`` prims (default
50,000), a continuation sublayer is created:
``cortex_YYYY_MM_DD_001.usda``, ``cortex_YYYY_MM_DD_002.usda``, etc.
New continuation sublayers are inserted at position 1 in the root
sublayer stack (right after ``cortex_protected.usda``) so newer data has
stronger opinion at composition time.

In-memory mode
--------------
When ``log_path=None``, all layers are anonymous in-memory layers. No
disk I/O occurs. The stage is still composable for traversal and query
validation. ``Save()`` calls are skipped in this mode.

Attributes authored per prim
----------------------------
payload (String), utility (Float), attended_count (Int),
protected_floor (Float), last_evaluated (Double), prior_state (Int).

semantic_vector is NOT stored in USD — the shadow vector index
(LanceDB in Phase 3) is authoritative for embeddings. Storing
768+ floats per prim would bloat the stage and is redundant with the
vector index. The entity_id-to-vector mapping lives in the vector index;
USD stores the cognitive state metadata.
"""

from __future__ import annotations

import logging
import time
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pxr import Sdf, Tf, Usd  # noqa: F401 — Tf imported per Phase 3 Pass 3 spec

from .sequential_writer import AuthoringResult
from .types import Memory

_logger = logging.getLogger(__name__)

PROTECTED_SUBLAYER_NAME = "cortex_protected.usda"
DEFAULT_ROTATION_CAP = 50_000


def _rolling_sublayer_base(authored_at: float) -> str:
    """Date prefix for rolling sublayer. UTC per substrate convention #6."""
    dt = datetime.fromtimestamp(authored_at, tz=timezone.utc)
    return f"cortex_{dt.year:04d}_{dt.month:02d}_{dt.day:02d}"


def _prim_path(entity_id: _uuid.UUID) -> Sdf.Path:
    """UUID-hex prim path. Substrate convention #1. TfToken-safe."""
    return Sdf.Path(f"/Memory_{entity_id.hex}")


def _set_attr(
    prim_spec: Sdf.PrimSpec,
    name: str,
    type_name: Sdf.ValueTypeName,
    value: object,
) -> None:
    """Author an attribute with default value on a prim spec."""
    attr = Sdf.AttributeSpec(prim_spec, name, type_name)
    attr.default = value


class UsdTarget:
    """Phase 3 AuthoringTarget — real USD authoring via pxr/Sdf.

    Conforms to ``sequential_writer.AuthoringTarget`` Protocol via duck
    typing. Drop-in replacement for ``MockUsdTarget`` at the
    ``SequentialWriter`` construction site.

    Parameters
    ----------
    log_path
        Root directory for sublayer ``.usda`` files. ``None`` for in-memory
        mode (anonymous layers, no disk I/O).
    rotation_cap
        Maximum prims per rolling sublayer before rotation triggers.
        Defaults to 50,000 per ARCHITECTURE.md §15.2 constraint #1.
        Exposed as a parameter so tests can exercise rotation logic
        without authoring 50k prims.
    """

    def __init__(
        self,
        log_path: Optional[Path] = None,
        *,
        rotation_cap: int = DEFAULT_ROTATION_CAP,
    ) -> None:
        self._log_path = Path(log_path) if log_path is not None else None
        self._in_memory = log_path is None
        self._rotation_cap = rotation_cap

        # Layer registry
        self._layers: Dict[str, Sdf.Layer] = {}
        self._prim_counts: Dict[str, int] = {}
        self._rotation_seq: Dict[str, int] = {}  # date_base -> current seq#

        # Root layer
        if self._in_memory:
            self._root_layer = Sdf.Layer.CreateAnonymous("cortex_root")
        else:
            self._log_path.mkdir(parents=True, exist_ok=True)
            root_path = str(self._log_path / "cortex_root.usda")
            self._root_layer = Sdf.Layer.CreateNew(root_path)
            if self._root_layer is None:
                self._root_layer = Sdf.Layer.FindOrOpen(root_path)

        self._stage = Usd.Stage.Open(self._root_layer)

        # Protected sublayer at strongest Root position
        self._get_or_create_layer(PROTECTED_SUBLAYER_NAME, protected=True)

    # ------------------------------------------------------------------
    # Layer management
    # ------------------------------------------------------------------

    def _get_or_create_layer(
        self, name: str, *, protected: bool = False
    ) -> Sdf.Layer:
        """Get an existing sublayer or create and register a new one."""
        if name in self._layers:
            return self._layers[name]

        if self._in_memory:
            layer = Sdf.Layer.CreateAnonymous(name)
        else:
            layer_path = str(self._log_path / name)
            layer = Sdf.Layer.CreateNew(layer_path)
            if layer is None:
                layer = Sdf.Layer.FindOrOpen(layer_path)

        self._layers[name] = layer
        self._prim_counts[name] = 0

        # Insert into root sublayer stack
        paths = list(self._root_layer.subLayerPaths)
        if protected:
            # Strongest position (index 0)
            paths.insert(0, layer.identifier)
        else:
            # Right after protected sublayer: newer rolling sublayers are
            # stronger than older ones at composition time.
            insert_at = 1 if paths else 0
            paths.insert(insert_at, layer.identifier)
        self._root_layer.subLayerPaths[:] = paths

        return layer

    def _resolve_target_layer(
        self, entity: Memory, authored_at: float
    ) -> Tuple[str, Sdf.Layer]:
        """Route entity to protected or rolling sublayer, with rotation."""
        if entity.protected_floor > 0.0:
            return PROTECTED_SUBLAYER_NAME, self._layers[PROTECTED_SUBLAYER_NAME]

        base = _rolling_sublayer_base(authored_at)
        seq = self._rotation_seq.get(base, 0)
        name = f"{base}.usda" if seq == 0 else f"{base}_{seq:03d}.usda"

        # Check rotation cap
        count = self._prim_counts.get(name, 0)
        if count >= self._rotation_cap:
            seq += 1
            self._rotation_seq[base] = seq
            name = f"{base}_{seq:03d}.usda"

        layer = self._get_or_create_layer(name)
        return name, layer

    # ------------------------------------------------------------------
    # AuthoringTarget Protocol
    # ------------------------------------------------------------------

    def author_stage_batch(self, entities: List[Memory]) -> AuthoringResult:
        """Author staged entities to USD via Sdf-level API.

        All writes inside ``Sdf.ChangeBlock`` (substrate convention #5).
        ``layer.Save()`` called per dirty layer after the ChangeBlock
        exits, matching the pattern measured by the Phase 2 benchmark.
        """
        authored_at = time.time()
        batch_id = str(_uuid.uuid4())

        # Group entities by target layer
        groups: Dict[str, Tuple[Sdf.Layer, List[Memory]]] = {}
        for m in entities:
            name, layer = self._resolve_target_layer(m, authored_at)
            if name not in groups:
                groups[name] = (layer, [])
            groups[name][1].append(m)

        # Author per-layer, each inside its own ChangeBlock
        for name, (layer, batch) in groups.items():
            with Sdf.ChangeBlock():
                for m in batch:
                    path = _prim_path(m.entity_id)
                    prim_spec = Sdf.CreatePrimInLayer(layer, path)
                    prim_spec.specifier = Sdf.SpecifierDef

                    _set_attr(prim_spec, "payload", Sdf.ValueTypeNames.String, m.payload)
                    _set_attr(prim_spec, "utility", Sdf.ValueTypeNames.Float, m.utility)
                    _set_attr(
                        prim_spec, "attended_count", Sdf.ValueTypeNames.Int, m.attended_count
                    )
                    _set_attr(
                        prim_spec, "protected_floor", Sdf.ValueTypeNames.Float, m.protected_floor
                    )
                    _set_attr(
                        prim_spec, "last_evaluated", Sdf.ValueTypeNames.Double, m.last_evaluated
                    )
                    _set_attr(prim_spec, "prior_state", Sdf.ValueTypeNames.Int, int(m.state))

            # Save after ChangeBlock exits — matches benchmark lock scope
            if not self._in_memory:
                layer.Save()

            self._prim_counts[name] = self._prim_counts.get(name, 0) + len(batch)

        _logger.info(
            "usd_target.author batch=%s count=%d mode=%s",
            batch_id,
            len(entities),
            "in-memory" if self._in_memory else "disk",
        )

        return AuthoringResult(
            entity_ids=[m.entity_id for m in entities],
            authored_at=authored_at,
            target="usd",
            batch_id=batch_id,
        )

    def flush(self) -> None:
        """Ensure all layers are durable on disk.

        In normal flow, ``Save()`` already fires per-layer inside
        ``author_stage_batch``. This is the safety net called by
        ``SequentialWriter`` between authoring and vector update per
        ARCHITECTURE.md §7.
        """
        if not self._in_memory:
            for layer in self._layers.values():
                layer.Save()
            self._root_layer.Save()

    # ------------------------------------------------------------------
    # Inspection / lifecycle helpers
    # ------------------------------------------------------------------

    @property
    def stage(self) -> Usd.Stage:
        """Underlying UsdStage for test assertions and traversal."""
        return self._stage

    def get_layer(self, name: str) -> Optional[Sdf.Layer]:
        """Get a managed sublayer by name. Returns None if not created."""
        return self._layers.get(name)

    def get_prim_count(self, name: str) -> int:
        """Current authored prim count for a sublayer."""
        return self._prim_counts.get(name, 0)

    @property
    def sublayer_names(self) -> List[str]:
        """Names of all managed sublayers (for test inspection)."""
        return list(self._layers.keys())

    def close(self) -> None:
        """Release stage and layer references."""
        self._stage = None
        self._layers.clear()
        self._prim_counts.clear()
        self._rotation_seq.clear()
