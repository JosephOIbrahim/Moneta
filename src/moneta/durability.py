"""WAL-lite durability for Moneta ECS and attention log.

ARCHITECTURE.md §11 deliverable list (Phase 1). MONETA.md §5 risk #4
("ECS durability on crash") mitigation.

Target: survive `kill -9` with at most 30 seconds of volatile state lost.

Design
------

1. **Snapshot** — the ECS is serialized to a JSON file atomically
   (tmp-file + `os.replace`). Default cadence: every 30 seconds via a
   background daemon thread. Snapshot replaces the previous file.

2. **WAL** — every `signal_attention` append is also written to a
   write-ahead log (JSONL, one line per entry). The WAL is `flush()`ed
   on each append for durability. Between snapshots, the WAL grows; at
   snapshot time the WAL is truncated since its entries are captured.

3. **Hydrate** — on restart, load the latest snapshot, then replay any
   WAL entries whose timestamp is strictly after the snapshot's
   `snapshot_created_at`. Entries from before the snapshot are skipped
   (already captured).

The "lite" in WAL-lite: no transaction framing, no checksums, no page
boundaries. A Python dict gets JSON-dumped. Correct for Phase 1 scale;
Phase 2 profiling decides whether to upgrade.

Format stability
----------------
Snapshot and WAL files are versioned via `snapshot_version` and
`wal_version` keys. Phase 3 may re-use these formats when real USD
hydration joins the loop; in that case, a format bump is a §9 Trigger 2
(spec-level surprise), not a silent change.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from .attention_log import AttentionEntry, AttentionLog
from .ecs import ECS
from .types import EntityState, Memory

_logger = logging.getLogger(__name__)

# MONETA.md §5 risk #4 target: ≤30 seconds of volatile state lost.
DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 30.0

SNAPSHOT_VERSION = 1
WAL_VERSION = 1


class DurabilityManager:
    """Coordinates ECS snapshots and attention-log WAL for crash recovery."""

    def __init__(
        self,
        snapshot_path: Path,
        wal_path: Path,
        snapshot_interval: float = DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        self._wal_path = Path(wal_path)
        self._snapshot_interval = snapshot_interval
        self._last_snapshot_ts: float = 0.0
        self._wal_fp = None  # opened lazily on first append
        self._lock = threading.Lock()  # guards _wal_fp open/close/truncate
        self._stop_event: Optional[threading.Event] = None
        self._bg_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot_ecs(self, ecs: ECS) -> None:
        """Atomically write ECS state to `snapshot_path`."""
        rows = []
        for memory in ecs.iter_rows():
            rows.append(
                {
                    "entity_id": str(memory.entity_id),
                    "payload": memory.payload,
                    "semantic_vector": list(memory.semantic_vector),
                    "utility": memory.utility,
                    "attended_count": memory.attended_count,
                    "protected_floor": memory.protected_floor,
                    "last_evaluated": memory.last_evaluated,
                    "state": int(memory.state),
                    "usd_link": None
                    if memory.usd_link is None
                    else str(memory.usd_link),
                }
            )
        now = time.time()
        snapshot = {
            "snapshot_version": SNAPSHOT_VERSION,
            "snapshot_created_at": now,
            "rows": rows,
        }
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._snapshot_path.with_suffix(
            self._snapshot_path.suffix + ".tmp"
        )
        with open(tmp_path, "w", encoding="utf-8") as fp:
            json.dump(snapshot, fp)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, self._snapshot_path)
        self._last_snapshot_ts = now

        # Truncate the WAL — everything before `now` is captured in the snapshot.
        with self._lock:
            if self._wal_fp is not None:
                self._wal_fp.close()
                self._wal_fp = None
            if self._wal_path.exists():
                self._wal_path.unlink()
        _logger.info(
            "durability.snapshot path=%s n=%d", self._snapshot_path, ecs.n
        )

    # ------------------------------------------------------------------
    # WAL
    # ------------------------------------------------------------------

    def wal_append(self, entry: AttentionEntry) -> None:
        """Append a single attention entry to the WAL (flush on each append)."""
        line = json.dumps(
            {
                "wal_version": WAL_VERSION,
                "entity_id": str(entry.entity_id),
                "weight": entry.weight,
                "timestamp": entry.timestamp,
            }
        )
        with self._lock:
            if self._wal_fp is None:
                self._wal_path.parent.mkdir(parents=True, exist_ok=True)
                self._wal_fp = open(self._wal_path, "a", encoding="utf-8")
            self._wal_fp.write(line + "\n")
            self._wal_fp.flush()

    def wal_read(self) -> List[AttentionEntry]:
        """Read all entries from the current WAL file. Used by `hydrate()`."""
        if not self._wal_path.exists():
            return []
        entries: List[AttentionEntry] = []
        with open(self._wal_path, "r", encoding="utf-8") as fp:
            for raw in fp:
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    _logger.warning(
                        "skipping malformed WAL line: %s", line[:80]
                    )
                    continue
                entries.append(
                    AttentionEntry(
                        UUID(d["entity_id"]),
                        float(d["weight"]),
                        float(d["timestamp"]),
                    )
                )
        return entries

    # ------------------------------------------------------------------
    # Hydrate
    # ------------------------------------------------------------------

    def hydrate(self) -> Tuple[ECS, List[AttentionEntry]]:
        """Load snapshot + replay WAL. Returns `(ECS, entries_to_replay)`."""
        if not self._snapshot_path.exists():
            _logger.info(
                "durability.hydrate no snapshot at %s; starting fresh",
                self._snapshot_path,
            )
            return ECS(), self.wal_read()

        with open(self._snapshot_path, "r", encoding="utf-8") as fp:
            snapshot = json.load(fp)

        ver = snapshot.get("snapshot_version")
        if ver != SNAPSHOT_VERSION:
            _logger.warning(
                "snapshot_version=%s (expected %d); attempting best-effort load",
                ver,
                SNAPSHOT_VERSION,
            )

        ecs = ECS()
        snapshot_ts: float = float(snapshot.get("snapshot_created_at", 0.0))
        for row_data in snapshot.get("rows", []):
            memory = Memory(
                entity_id=UUID(row_data["entity_id"]),
                payload=row_data["payload"],
                semantic_vector=list(row_data["semantic_vector"]),
                utility=float(row_data["utility"]),
                attended_count=int(row_data["attended_count"]),
                protected_floor=float(row_data["protected_floor"]),
                last_evaluated=float(row_data["last_evaluated"]),
                state=EntityState(int(row_data["state"])),
                usd_link=row_data.get("usd_link"),
            )
            ecs.hydrate_row(memory)

        all_wal = self.wal_read()
        replay = [e for e in all_wal if e.timestamp > snapshot_ts]
        _logger.info(
            "durability.hydrate n=%d wal_total=%d wal_replay=%d",
            ecs.n,
            len(all_wal),
            len(replay),
        )
        return ecs, replay

    # ------------------------------------------------------------------
    # Background thread (optional)
    # ------------------------------------------------------------------

    def start_background(self, ecs: ECS) -> None:
        """Start a daemon thread that snapshots every `snapshot_interval` seconds."""
        if self._bg_thread is not None:
            return
        self._stop_event = threading.Event()

        def _run() -> None:
            assert self._stop_event is not None
            while not self._stop_event.wait(self._snapshot_interval):
                try:
                    self.snapshot_ecs(ecs)
                except Exception:  # noqa: BLE001
                    _logger.exception("background snapshot failed")

        self._bg_thread = threading.Thread(
            target=_run, daemon=True, name="moneta-snapshot"
        )
        self._bg_thread.start()
        _logger.info(
            "durability.start_background interval=%.1fs", self._snapshot_interval
        )

    def stop_background(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._bg_thread is not None:
            self._bg_thread.join(timeout=5)
            self._bg_thread = None
            self._stop_event = None

    def close(self) -> None:
        self.stop_background()
        with self._lock:
            if self._wal_fp is not None:
                self._wal_fp.close()
                self._wal_fp = None
