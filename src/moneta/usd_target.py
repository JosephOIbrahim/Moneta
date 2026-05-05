"""Real USD authoring target — Sdf-level writes via pxr.

ARCHITECTURE.md §15. Phase 3 Pass 3 (created), Pass 6 (lock shrink).

This module implements the AuthoringTarget Protocol from sequential_writer.py
as a drop-in replacement for MockUsdTarget. The MockUsdTarget is kept
alongside for A/B validation through Phase 3 Pass 7.

Writer lock scope (Pass 6, authorized by Pass 5 ruling)
-------------------------------------------------------
``author_stage_batch`` performs Sdf authoring inside ``Sdf.ChangeBlock``
only. ``layer.Save()`` is deferred to ``flush()``, which the
``SequentialWriter`` calls separately after authoring returns. This
narrow-lock pattern allows concurrent ``stage.Traverse()`` during the
Save window without data corruption — empirically verified at 2,000
iterations / 70M concurrent prim-attribute reads on OpenUSD 0.25.5
(see ``docs/patent-evidence/pass5-usd-threadsafety-review.md``,
commit 500b1dd). The sequential-write ordering from ARCHITECTURE.md §7
is preserved: ChangeBlock completes, Save completes, then the shadow
vector index is committed. Only the reader-blocking scope changes.

Authoring pattern
-----------------
All writes use the Sdf-level API (Sdf.CreatePrimInLayer + Sdf.AttributeSpec)
inside Sdf.ChangeBlock, NOT UsdStage.DefinePrim. This matches the benchmark
(scripts/usd_metabolism_bench_v2.py) and avoids the OpenUSD 0.25.5
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

Attributes authored per prim (USD camelCase per MonetaSchema.usda, v1.2.0)
-------------------------------------------------------------------------
payload (String), utility (Float), attendedCount (Int),
protectedFloor (Float), lastEvaluated (Double), priorState (Token).

Each prim is authored with ``typeName="MonetaMemory"``, the codeless
schema registered via ``schema/plugInfo.json``. See
``tests/test_schema_acceptance_gate.py`` for the runtime-registration
validation gate.

``priorState`` is a token, not an int — see ``_state_to_token`` /
``_token_to_state`` below. The schema declares four ``allowedTokens``
values (``volatile``, ``staged_for_sync``, ``consolidated``, ``pruned``);
the substrate produces only ``staged_for_sync`` today, since the only
authoring path runs through ``consolidation.run_pass`` ->
``commit_staging`` at the moment ``EntityState`` is ``STAGED_FOR_SYNC``.
Other tokens are forward-looking. The substrate cannot author
``"pruned"`` because the current ``EntityState`` enum has no ``PRUNED``
member; pruned entities are removed from the ECS rather than
transitioning state.

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
from .types import EntityState, Memory

_logger = logging.getLogger(__name__)

PROTECTED_SUBLAYER_NAME = "cortex_protected.usda"
DEFAULT_ROTATION_CAP = 50_000

# ----------------------------------------------------------------------
# priorState <-> EntityState boundary helpers
# ----------------------------------------------------------------------
#
# MonetaSchema.usda declares ``priorState`` as a token with allowedTokens
# ["volatile", "staged_for_sync", "consolidated", "pruned"]. The current
# EntityState enum (src/moneta/types.py) has only the first three
# members — pruned entities are removed from the ECS rather than
# transitioning to a PRUNED state, so the substrate does not produce
# ``"pruned"`` today. The token is reserved for a future
# PRUNED-as-tombstone surgery; the helper raises on receipt rather than
# silently returning a wrong EntityState (Auditor's interpretation (a)
# at the codeless-schema G1 gate).

_STATE_TO_TOKEN: Dict[EntityState, str] = {
    EntityState.VOLATILE: "volatile",
    EntityState.STAGED_FOR_SYNC: "staged_for_sync",
    EntityState.CONSOLIDATED: "consolidated",
}
_TOKEN_TO_STATE: Dict[str, EntityState] = {
    token: state for state, token in _STATE_TO_TOKEN.items()
}


def _state_to_token(state: EntityState) -> str:
    """Translate an EntityState to its priorState token at the USD write
    boundary. Raises ``KeyError`` if the state has no token mapping
    (the safety net for a future EntityState.PRUNED added before this
    helper is updated)."""
    return _STATE_TO_TOKEN[state]


def _token_to_state(token: str) -> EntityState:
    """Inverse of :func:`_state_to_token`. Resolves a priorState token
    read off a typed MonetaMemory prim into an EntityState member.

    Raises ``ValueError`` on tokens outside the substrate-producible
    set, including the schema-reserved ``"pruned"`` token.

    Imported by test fixtures that read priorState off authored prims.
    Not invoked from substrate code paths — handoff §3 audit verified
    that USD reads do not exist on the substrate side.
    """
    try:
        return _TOKEN_TO_STATE[token]
    except KeyError as exc:
        raise ValueError(
            f"unknown priorState token {token!r}; expected one of "
            f"{sorted(_TOKEN_TO_STATE)} "
            f"(the schema reserves 'pruned' for a future surgery)"
        ) from exc


class FlushPartialFailureError(RuntimeError):
    """Raised when ``UsdTarget.flush()`` saves some layers and not others.

    A partial flush violates the §7 sequential-write invariant: the vector
    index ought to be committed only AFTER the USD side is fully durable.
    If only some layers Saved, the SequentialWriter must NOT proceed to
    update_state, because doing so would advertise CONSOLIDATED for entities
    whose USD prims are not on disk — the inverse of the orphan case (which
    §7 explicitly authorizes) and which §7 does NOT authorize.

    Attributes
    ----------
    saved_layers:
        Layer names whose Save() succeeded before the failure.
    failed_layer:
        The first layer name whose Save() raised.
    pending_layers:
        Layer names that had not yet been attempted when the failure fired.
    cause:
        The underlying exception from the failing Save() call.

    Review finding: ``usd-L2-flush-partial-failure-breaks-sequential-write-atomicity``.
    """

    def __init__(
        self,
        saved_layers: List[str],
        failed_layer: str,
        pending_layers: List[str],
        cause: BaseException,
    ) -> None:
        self.saved_layers = list(saved_layers)
        self.failed_layer = failed_layer
        self.pending_layers = list(pending_layers)
        self.cause = cause
        super().__init__(
            f"UsdTarget.flush partial failure: layer {failed_layer!r} "
            f"raised {type(cause).__name__}({cause}); saved={len(saved_layers)} "
            f"failed=1 pending={len(pending_layers)}"
        )


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
        ``layer.Save()`` is NOT called here — it is deferred to
        ``flush()``, which the ``SequentialWriter`` calls after this
        method returns. This narrow-lock scope allows concurrent readers
        to traverse the stage during the Save window. Empirical basis:
        Pass 5 Q6 investigation (commit 500b1dd, OpenUSD 0.25.5).
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

        # Author per-layer, each inside its own ChangeBlock.
        # Save() is deferred to flush() — narrow lock scope per Pass 5 ruling.
        for name, (layer, batch) in groups.items():
            with Sdf.ChangeBlock():
                for m in batch:
                    path = _prim_path(m.entity_id)
                    prim_spec = Sdf.CreatePrimInLayer(layer, path)
                    prim_spec.specifier = Sdf.SpecifierDef
                    prim_spec.typeName = "MonetaMemory"

                    _set_attr(prim_spec, "payload", Sdf.ValueTypeNames.String, m.payload)
                    _set_attr(prim_spec, "utility", Sdf.ValueTypeNames.Float, m.utility)
                    _set_attr(
                        prim_spec, "attendedCount", Sdf.ValueTypeNames.Int, m.attended_count
                    )
                    _set_attr(
                        prim_spec, "protectedFloor", Sdf.ValueTypeNames.Float, m.protected_floor
                    )
                    _set_attr(
                        prim_spec, "lastEvaluated", Sdf.ValueTypeNames.Double, m.last_evaluated
                    )
                    _set_attr(
                        prim_spec, "priorState", Sdf.ValueTypeNames.Token, _state_to_token(m.state)
                    )

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
        """Save all dirty layers to disk. Primary durability path.

        Called by ``SequentialWriter`` after ``author_stage_batch``
        returns and before the vector index is committed, preserving
        ARCHITECTURE.md §7 sequential-write ordering: ChangeBlock
        (in author_stage_batch) → Save (here) → vector commit (after).

        Since Pass 6, ``author_stage_batch`` no longer calls Save()
        itself — this method is the sole Save call site, enabling the
        narrow-lock pattern verified in Pass 5.

        Failure semantics
        -----------------
        If any individual ``layer.Save()`` raises (disk full, fsync
        timeout, permission, network FS hiccup), this method records
        which layers had already saved and then raises a
        :class:`FlushPartialFailureError` carrying that bookkeeping.
        The structured exception lets the ``SequentialWriter`` refuse
        to proceed to the vector update — the §7 invariant "vector is
        authoritative for what exists" requires that the vector side
        ONLY be advanced once the USD side is fully durable. Without
        this, a partial flush would commit the vector index to
        CONSOLIDATED for entities whose USD prims never reached disk —
        the inverse of the orphan case, and not authorized by §7.

        Review finding: ``usd-L2-flush-partial-failure-breaks-sequential-write-atomicity``.
        """
        if self._in_memory:
            return

        saved: List[str] = []
        # Stable iteration: capture an explicit list so saved_layers and
        # pending_layers refer to the same ordering on retry diagnostics.
        layer_items: List[Tuple[str, Sdf.Layer]] = list(self._layers.items())
        for idx, (name, layer) in enumerate(layer_items):
            try:
                layer.Save()
            except BaseException as exc:  # USD raises diverse exception types
                pending = [n for n, _ in layer_items[idx + 1 :]]
                _logger.error(
                    "UsdTarget.flush partial failure on layer=%s "
                    "saved=%d pending=%d cause=%s",
                    name,
                    len(saved),
                    len(pending),
                    exc,
                )
                raise FlushPartialFailureError(
                    saved_layers=saved,
                    failed_layer=name,
                    pending_layers=pending,
                    cause=exc,
                ) from exc
            saved.append(name)

        # Root layer last: if it raises, every sublayer is durable but the
        # composition handle is not — still a partial-failure event from
        # §7's perspective.
        try:
            self._root_layer.Save()
        except BaseException as exc:
            _logger.error(
                "UsdTarget.flush partial failure on root layer "
                "saved=%d cause=%s",
                len(saved),
                exc,
            )
            raise FlushPartialFailureError(
                saved_layers=saved,
                failed_layer="<root>",
                pending_layers=[],
                cause=exc,
            ) from exc

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
