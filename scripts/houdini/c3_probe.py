"""Gate 2 condition C3 probe: a LOP network sublayering cortex_root.usda.

Run each phase in its own hython process, against a disposable store:
    hython c3_probe.py seed   <work_dir>
    hython c3_probe.py lop    <work_dir>
    hython c3_probe.py reopen <work_dir>
Each phase prints one JSON line prefixed with "C3RESULT ".
"""
import json
import logging
import sys
import time
from pathlib import Path

import hou  # noqa: F401  (hython: proves we are inside Houdini)
from pxr import Sdf, Usd

import moneta
from moneta.usd_target import UsdSaveError

PHASE, WORK = sys.argv[1], Path(sys.argv[2])
STORE = WORK / "usd"
ROOT = STORE / "cortex_root.usda"
HALF_LIFE = 60.0  # seconds, the configured minimum; a pass stages after ~2.5 half-lives
SHARING = "Sdf registry sharing"


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append((record.levelname, record.getMessage()))


cap = Capture()
logging.getLogger("moneta").addHandler(cap)
logging.getLogger("moneta").setLevel(logging.INFO)


def config():
    return moneta.MonetaConfig(
        storage_uri=f"c3-probe://{WORK.name}",
        half_life_seconds=HALF_LIFE,
        snapshot_path=WORK / "snapshot.json",
        wal_path=WORK / "attention.wal",
        use_real_usd=True,
        usd_target_path=STORE,
        native="off",
    )


def stage_and_consolidate(m, n, tag):
    """Deposit n memories, attend each 3 times, let them decay, consolidate."""
    ids = [m.deposit(f"{tag}-{i}", [1.0, float(i), 0.5]) for i in range(n)]
    # one protected memory (floor 0.2 < the 0.3 stage line) exercises cortex_protected.usda
    ids.append(m.deposit(f"{tag}-protected", [0.5, 1.0, 1.0], protected_floor=0.2))
    for _ in range(3):
        m.signal_attention({eid: 0.05 for eid in ids})
    first = m.run_sleep_pass()  # applies attention: attended_count = 3
    time.sleep(HALF_LIFE * 2.5)  # utility decays below the 0.3 stage line
    second = m.run_sleep_pass()  # stages and commits through USD
    return ids, {"pass1_staged": first.staged, "pass2_staged": second.staged,
                 "pass2_pruned": second.pruned}


def memory_prims(stage):
    return sorted(p.GetName() for p in stage.GetPseudoRoot().GetChildren()
                  if p.GetName().startswith("Memory_"))


def layer_report():
    root = Sdf.Layer.FindOrOpen(str(ROOT))
    paths = list(root.subLayerPaths)
    offsets = [(o.offset, o.scale) for o in root.subLayerOffsets]
    counts = {}
    for p in paths:
        lyr = Sdf.Layer.FindOrOpen(str(STORE / Path(p).name)) if not Path(p).is_absolute() else Sdf.Layer.FindOrOpen(p)
        counts[Path(p).name] = len([c for c in lyr.rootPrims if c.name.startswith("Memory_")]) if lyr else None
    return {"sublayers": [Path(p).name for p in paths], "offsets": offsets,
            "duplicate_sublayers": len(paths) != len(set(paths)), "prims_per_layer": counts}


def lop_network():
    lop = hou.node("/stage").createNode("sublayer", "c3_sublayer")
    lop.parm("filepath1").set(str(ROOT).replace("\\", "/"))
    return lop


def lop_prims(lop, force=False):
    if force:
        lop.cook(force=True)
    return memory_prims(lop.stage())


out = {"phase": PHASE, "houdini": hou.applicationVersionString(),
       "moneta_path": str(Path(moneta.__file__).parent),
       "build": [moneta.build_info().version, moneta.build_info().commit, moneta.build_info().src_digest]}
try:
    if PHASE == "seed":
        WORK.mkdir(parents=True, exist_ok=True)
        with moneta.Moneta(config()) as m:
            _, out["consolidation"] = stage_and_consolidate(m, 3, "seed")
        out["layers"] = layer_report()
        out["composed_prims"] = len(memory_prims(Usd.Stage.Open(str(ROOT))))

    elif PHASE == "lop":
        lop = lop_network()
        out["lop_prims_before"] = len(lop_prims(lop))
        loaded = [lyr.identifier for lyr in Sdf.Layer.GetLoadedLayers()
                  if lyr.realPath and Path(lyr.realPath).parent == STORE]
        out["store_layers_loaded_by_lop"] = [Path(x).name for x in loaded]
        cap.records.clear()
        try:
            with moneta.Moneta(config()) as m:
                out["sharing_errors_at_open"] = sum(1 for lvl, msg in cap.records
                                                    if lvl == "ERROR" and SHARING in msg)
                _, out["consolidation"] = stage_and_consolidate(m, 3, "lop")
                out["usd_save_error"] = None
        except UsdSaveError as exc:
            out["usd_save_error"] = {k: str(v) for k, v in exc.failures.items()}
        out["lop_prims_after_recook"] = len(lop_prims(lop, force=True))
        out["layers"] = layer_report()
        out["warnings_and_errors"] = [f"{lvl}: {msg[:160]}" for lvl, msg in cap.records]

    elif PHASE == "reopen":
        out["composed_prims_fresh_open"] = len(memory_prims(Usd.Stage.Open(str(ROOT))))
        out["layers"] = layer_report()
        cap.records.clear()
        with moneta.Moneta(config()) as m:
            out["manifest_len"] = len(m.get_consolidation_manifest())
            out["sharing_errors_at_open"] = sum(1 for lvl, msg in cap.records
                                                if lvl == "ERROR" and SHARING in msg)
        lop = lop_network()
        out["lop_prims_fresh_process"] = len(lop_prims(lop))
    out["ok"] = True
except Exception as exc:  # report, never hide
    out["ok"] = False
    out["exception"] = f"{type(exc).__name__}: {exc}"
print("C3RESULT " + json.dumps(out))
