"""Mock USD authoring target — emits structured JSONL of intended writes.

ARCHITECTURE.md §6 (Phase 3 target, mocked in Phase 1). The log schema
below MUST match what Phase 3's real authoring code consumes as input.
Phase 3 is a drop-in replacement at the `AuthoringTarget` Protocol
boundary defined in `sequential_writer.py`.

Log schema (JSONL, one entry per staging batch)
------------------------------------------------

    {
      "schema_version": 1,
      "authored_at": float,           # wall-clock unix seconds
      "batch_id": str,                # UUID of this batch
      "target": "mock",               # becomes "usd" in Phase 3
      "entries": [
        {
          "entity_id": str,                     # UUID; prim-name-compatible per
                                                # docs/substrate-conventions.md §1
          "payload": str,                       # natural language content
          "semantic_vector": list[float],       # the embedding
          "utility": float,
          "attended_count": int,
          "protected_floor": float,
          "last_evaluated": float,
          "prior_state": int,                   # EntityState before this commit
          "target_sublayer": str                # "cortex_YYYY_MM_DD.usda" or
                                                # "cortex_protected.usda"
        },
        ...
      ]
    }

Sublayer routing
----------------
Each entry carries a `target_sublayer` field computed at author time:

- If `protected_floor > 0.0`, the entry is routed to
  `cortex_protected.usda` (strongest Root stack position per
  substrate-conventions §4).
- Otherwise, the entry is routed to the rolling daily sublayer
  `cortex_YYYY_MM_DD.usda` derived from `authored_at` (UTC date).

Phase 3 consumes `target_sublayer` verbatim as the path argument to
`Sdf.Layer.CreateNew` / `UsdStage.GetSubLayerPaths`.

Ephemeral mode
--------------
When `log_path=None`, the mock target buffers log entries in memory
instead of writing to disk. This is used by unit tests and the smoke
check to avoid polluting the filesystem. The buffered entries are
accessible via `get_ephemeral_buffer()` for test assertions.
"""

from __future__ import annotations

import json
import logging
import time
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .sequential_writer import AuthoringResult
from .types import Memory

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
PROTECTED_SUBLAYER = "cortex_protected.usda"


def _rolling_sublayer_name(authored_at: float) -> str:
    """Compute the rolling daily sublayer name for a given timestamp.

    Per ARCHITECTURE.md §6: `cortex_YYYY_MM_DD.usda`, one per day, never
    per pass. UTC date is used so the rollover is stable across time zones.
    """
    dt = datetime.fromtimestamp(authored_at, tz=timezone.utc)
    return f"cortex_{dt.year:04d}_{dt.month:02d}_{dt.day:02d}.usda"


class MockUsdTarget:
    """Phase 1 `AuthoringTarget` — JSONL log file or in-memory buffer.

    Implements the `sequential_writer.AuthoringTarget` Protocol. Phase 3
    replaces this with a pxr-based authoring module. The Protocol + the
    log schema above are the stable edge.
    """

    def __init__(self, log_path: Optional[Path] = None) -> None:
        self._log_path: Optional[Path] = Path(log_path) if log_path is not None else None
        self._fp = None  # opened lazily
        self._ephemeral_buffer: List[dict] = []  # used when log_path is None

    # --- AuthoringTarget Protocol ------------------------------------

    def author_stage_batch(self, entities: List[Memory]) -> AuthoringResult:
        """Emit a JSONL entry for the staging batch and return the result."""
        authored_at = time.time()
        batch_id = str(_uuid.uuid4())
        entries = []
        for m in entities:
            target_sublayer = (
                PROTECTED_SUBLAYER
                if m.protected_floor > 0.0
                else _rolling_sublayer_name(authored_at)
            )
            entries.append(
                {
                    "entity_id": str(m.entity_id),
                    "payload": m.payload,
                    "semantic_vector": list(m.semantic_vector),
                    "utility": m.utility,
                    "attended_count": m.attended_count,
                    "protected_floor": m.protected_floor,
                    "last_evaluated": m.last_evaluated,
                    "prior_state": int(m.state),
                    "target_sublayer": target_sublayer,
                }
            )
        log_entry = {
            "schema_version": SCHEMA_VERSION,
            "authored_at": authored_at,
            "batch_id": batch_id,
            "target": "mock",
            "entries": entries,
        }

        if self._log_path is None:
            self._ephemeral_buffer.append(log_entry)
        else:
            if self._fp is None:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                self._fp = open(self._log_path, "a", encoding="utf-8")
            self._fp.write(json.dumps(log_entry) + "\n")
            self._fp.flush()

        _logger.info(
            "mock_usd_target.author batch=%s count=%d mode=%s",
            batch_id,
            len(entries),
            "ephemeral" if self._log_path is None else "persistent",
        )

        return AuthoringResult(
            entity_ids=[m.entity_id for m in entities],
            authored_at=authored_at,
            target="mock",
            batch_id=batch_id,
        )

    def flush(self) -> None:
        if self._fp is not None:
            self._fp.flush()

    # --- Test / inspection helpers -----------------------------------

    def get_ephemeral_buffer(self) -> List[dict]:
        """Return a copy of the in-memory buffer (ephemeral mode only)."""
        return list(self._ephemeral_buffer)

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None
