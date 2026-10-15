"""Project one generation of the journal into USD.

The projection is derived: delete the directory and run this again for
the same generation, and you get the same prims. It reuses v1's
``UsdTarget`` writer, so the layout is v1's (``cortex_root.usda``,
``cortex_protected.usda``, rolling ``cortex_YYYY_MM_DD.usda``; typed
``MonetaMemory`` prims named ``/Memory_<uuid hex>``). The root layer's
``customLayerData`` records which generation and policy it came from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...usd_target import UsdTarget
from ..substrate import Substrate, Verdict


def project_generation(
    substrate: Substrate,
    directory: Path,
    *,
    context: str | None = None,
    t: float | None = None,
) -> dict[str, Any]:
    """Write every record eligible in ``context`` at ``t`` to a fresh directory."""
    directory = Path(directory)
    if (directory / "cortex_root.usda").exists():
        raise FileExistsError(f"{directory} already holds a projection; use a fresh directory")
    with substrate._lock:
        substrate._check_open()
        when = substrate._t(t)
        policy = substrate._resolve(context)
        verdicts, _ = substrate._verdicts(policy, None)
        records = sorted(
            (substrate._fold.records[eid] for eid, v in verdicts.items() if v == Verdict.ELIGIBLE),
            key=lambda r: r.seq,
        )
        memories = [r.to_memory(substrate.lam, when) for r in records]
        seq = substrate.seq
    target = UsdTarget(log_path=directory)
    try:
        if memories:
            target.author_stage_batch(memories)
        root = target._root_layer
        data = dict(root.customLayerData)
        data.update(
            {
                "monetaGenerationSeq": seq,
                "monetaContext": policy.context,
                "monetaPolicyFingerprint": policy.fingerprint,
                "monetaEvaluatedAt": when,
            }
        )
        root.customLayerData = data
        target.flush()
    finally:
        target.close()
    return {
        "directory": str(directory),
        "records": len(memories),
        "seq": seq,
        "context": policy.context,
        "policy_fingerprint": policy.fingerprint,
        "t_eval": when,
    }
