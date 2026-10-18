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
(commit 500b1dd). The sequential-write ordering from ARCHITECTURE.md §7
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

Reopen (ce45, adopted at gate 2)
--------------------------------
An existing store is reopened, never re-created: each existing layer is
opened with ``FindOrOpen``, and a layer is created only when its file is
absent, so a fresh process keeps the authored stack (paths, order,
offsets, metadata and opinions). Each layer's prim count starts from its
top-level prims on disk, and rolling routing resumes the highest existing
continuation. An existing layer or a stage that cannot be opened raises;
nothing falls back to creating a new layer. ``rotation_cap`` must be
positive. Gate 2's two conditions: a layer already loaded in this process
(Sdf's registry is shared with LOP networks) is used as is and logged at
WARNING, and ``flush()`` reports every failed ``Save()`` as
``UsdSaveError``.

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
import os
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


class UsdSaveError(RuntimeError):
    """``UsdTarget.flush()`` could not save one or more layers.

    ``failures`` maps each failed layer's identifier to what its ``Save()``
    did: returned ``False``, or raised (the first raise is chained as
    ``__cause__``). A failed layer stays dirty, so the next ``flush()``
    retries it.
    """

    def __init__(self, failures: dict[str, str]) -> None:
        self.failures: dict[str, str] = dict(failures)
        detail = "; ".join(f"{ident}: {why}" for ident, why in self.failures.items())
        super().__init__(
            f"USD flush failed for {len(self.failures)} layer(s): {detail}"
        )


def _warn_registry_sharing(directory: Path) -> int:
    """Log every layer another holder already loaded from ``directory``.

    Sdf keeps one layer registry per process, and in a Houdini session LOP
    networks share it. A layer from this store that is loaded before this
    target loads anything is held by someone else: a LOP network, another
    stage or another ``UsdTarget``. Moneta will author into that same layer
    object, and its ``flush()`` saves every opinion the layer holds, while
    the other holder sees, edits or reloads it. Gate 2's condition on
    adopting ce45 is that this sharing is detected and logged: one WARNING
    per layer, nothing refused. A holder that loads the layer after this
    target cannot be detected here. Returns the number of layers logged.
    """
    want = os.path.normcase(os.path.realpath(directory))
    n = 0
    for layer in Sdf.Layer.GetLoadedLayers():
        real = layer.realPath
        if not real:  # anonymous layers have no file
            continue
        if os.path.normcase(os.path.dirname(os.path.realpath(real))) != want:
            continue
        n += 1
        _logger.warning(
            "usd_target: Sdf registry sharing: layer %s is already loaded in "
            "this process (a LOP network, another stage or another UsdTarget "
            "holds it; dirty=%s). Moneta authors into that shared layer, and "
            "its flush() saves every opinion the layer holds.",
            layer.identifier,
            layer.dirty,
        )
    return n


def _open_or_create_disk_layer(path: Path) -> Sdf.Layer:
    """Open an existing layer; never replace an unreadable file with a new one.

    Reopen-first (ce45): an existing file is opened, never re-created; a new
    layer is created only after ``lstat`` reports the file absent.

    A layer already in this process's Sdf registry under this identifier is
    used as is: ``CreateNew`` would collide with it ("A layer already
    exists"), and ``FindOrOpen`` would return it anyway. This target's own
    stage puts its sublayers there when it composes the root, so finding
    one here is not sharing by itself; ``_warn_registry_sharing`` detects
    foreign holders before the target loads anything.
    """
    loaded = Sdf.Layer.Find(str(path))
    if loaded is not None:
        return loaded
    try:
        path.lstat()
    except FileNotFoundError:
        layer = Sdf.Layer.CreateNew(str(path))
        action = "create"
    else:
        layer = Sdf.Layer.FindOrOpen(str(path))
        action = "open existing"
    if layer is None:
        raise RuntimeError(f"Unable to {action} USD layer: {path}")
    return layer


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
        if rotation_cap < 1:
            raise ValueError("rotation_cap must be positive")
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
            # Before this target loads anything, so its own stage's layers
            # are never mistaken for another holder's (gate 2).
            _warn_registry_sharing(self._log_path)
            self._root_layer = _open_or_create_disk_layer(self._log_path / "cortex_root.usda")

        self._stage = Usd.Stage.Open(self._root_layer)
        if self._stage is None:
            raise RuntimeError(f"Unable to open USD stage: {self._root_layer.identifier}")

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
            layer = _open_or_create_disk_layer(self._log_path / name)

        self._layers[name] = layer
        self._prim_counts[name] = len(layer.rootPrims)

        # Keep authored paths, ordering and offsets when the layer is already
        # referenced, including relative references to its absolute identifier.
        paths = list(self._root_layer.subLayerPaths)
        if not any(
            path == layer.identifier
            or Sdf.ComputeAssetPathRelativeToLayer(self._root_layer, path) == layer.identifier
            for path in paths
        ):
            insert_at = 0 if protected else (1 if paths else 0)
            self._root_layer.subLayerPaths.insert(insert_at, layer.identifier)

        return layer

    def _resolve_target_layer(
        self, entity: Memory, authored_at: float
    ) -> Tuple[str, Sdf.Layer]:
        """Route entity to protected or rolling sublayer, with rotation."""
        if entity.protected_floor > 0.0:
            return PROTECTED_SUBLAYER_NAME, self._layers[PROTECTED_SUBLAYER_NAME]

        base = _rolling_sublayer_base(authored_at)
        seq = self._rotation_seq.get(base)
        if seq is None:
            seq = 0
            for path in self._root_layer.subLayerPaths:
                stem = Path(path).stem
                suffix = stem[len(base) + 1 :] if stem.startswith(f"{base}_") else ""
                if suffix.isdecimal():
                    seq = max(seq, int(suffix))
            self._rotation_seq[base] = seq

        # Open before checking the cap so persisted counts participate in
        # rotation. Existing full continuations must not receive another write.
        while True:
            name = f"{base}.usda" if seq == 0 else f"{base}_{seq:03d}.usda"
            layer = self._get_or_create_layer(name)
            if self._prim_counts[name] < self._rotation_cap:
                return name, layer
            seq += 1
            self._rotation_seq[base] = seq

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

        Every ``Save()`` is checked (gate 2's condition on adopting ce45):
        a ``False`` result and a raise (usd-core raises
        ``Tf.ErrorException`` for an unwritable file) are both failures.
        The remaining layers are still saved, sublayers first and the root
        last; then ``UsdSaveError`` names every failed layer. The
        ``SequentialWriter`` does not catch it, so the batch's vector
        commit does not happen (ARCHITECTURE.md §7: USD first). A failed
        layer stays dirty, and the next ``flush()`` retries it.
        """
        if self._in_memory:
            return
        failures: dict[str, str] = {}
        first_raise: BaseException | None = None
        for layer in [*self._layers.values(), self._root_layer]:
            try:
                saved = layer.Save()
            except Exception as exc:  # noqa: BLE001 - reported below, never dropped
                failures[layer.identifier] = (
                    f"Save() raised {type(exc).__name__}: {str(exc).strip()}"
                )
                if first_raise is None:
                    first_raise = exc
                continue
            if not saved:
                failures[layer.identifier] = "Save() returned False"
        if failures:
            _logger.error(
                "usd_target.flush failed for %d layer(s): %s",
                len(failures),
                ", ".join(failures),
            )
            raise UsdSaveError(failures) from first_raise

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
