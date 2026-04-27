"""Subprocess body for the schema acceptance gate test.

Invoked by ``tests/test_schema_acceptance_gate.py`` via ``subprocess.run``
with ``PXR_PLUGINPATH_NAME`` pointing at the repo's ``schema/`` directory
and ``PYTHONPATH`` pointing at ``src/``.

This file is not a pytest test (leading underscore + not matching
``test_*.py``); pytest skips it during collection. It runs as a clean
Python invocation per the subprocess-isolation requirement of
``HANDOFF_codeless_schema_moneta.md`` §8.1 / Deep Think brief §7.6.

CLI contract:
    python _schema_gate_subprocess.py <tmp_path>

On success: prints ``OK`` and exits 0.
On any assertion failure: ``AssertionError`` propagates with a
diagnostic message, exit code is non-zero.
"""
from __future__ import annotations

import sys
import time as _time
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: _schema_gate_subprocess.py <tmp_path>"
        )
    tmp_path = Path(sys.argv[1])

    # ------------------------------------------------------------------
    # Step 1 — schema registration assertion (the false-positive defense)
    # ------------------------------------------------------------------
    # Sdf-level authoring is schema-blind. It will write
    # typeName="MonetaMemory" to disk even with no plugin, no
    # plugInfo.json, and no schema. A naive round-trip test passes
    # under that broken state. The defense is to ask the
    # ``Usd.SchemaRegistry`` directly: does the runtime know about
    # MonetaMemory? Per Deep Think brief §7.6, this is the only
    # mathematically sufficient check.
    from pxr import Usd  # noqa: E402 — pxr import ordering must follow env

    prim_def = (
        Usd.SchemaRegistry().FindConcretePrimDefinition("MonetaMemory")
    )
    assert prim_def is not None, (
        "FindConcretePrimDefinition('MonetaMemory') returned None — "
        "the codeless schema is not registered. Check that "
        "PXR_PLUGINPATH_NAME points at the repo's schema/ directory "
        "and that schema/plugInfo.json + schema/generatedSchema.usda "
        "are committed."
    )

    # ------------------------------------------------------------------
    # Step 2 — exercise the four-op API end-to-end through real USD
    # ------------------------------------------------------------------
    # The substrate's only on-disk authoring path runs through
    # consolidation.run_pass -> sequential_writer.commit_staging ->
    # UsdTarget.author_stage_batch. At the moment of the write,
    # entity.state == EntityState.STAGED_FOR_SYNC; that is the only
    # priorState value the substrate produces today. Other
    # allowedTokens values are forward-looking and exercised by
    # tests/test_state_token_roundtrip.py per handoff §8.4.
    import moneta  # noqa: F401 — package-level side effects
    from moneta import Moneta, MonetaConfig

    usd_dir = tmp_path / "usd"
    with Moneta(
        MonetaConfig.ephemeral(
            use_real_usd=True,
            usd_target_path=usd_dir,
            half_life_seconds=60.0,
        )
    ) as m:
        eid = m.deposit("gate test memory", [1.0, 0.0, 0.0])
        # Force the deposited memory to match staging criteria
        # (utility < 0.3 AND attended_count >= 3) so the next sleep
        # pass authors it to USD. Same pattern as
        # tests/integration/test_real_usd_end_to_end.py::_force_staging.
        idx = m.ecs._id_to_row[eid]
        m.ecs._utility[idx] = 0.2
        m.ecs._attended[idx] = 5
        m.ecs._last_evaluated[idx] = _time.time()

        result = m.run_sleep_pass()
        assert result.staged == 1, (
            f"expected exactly 1 staged entity, got {result.staged}"
        )

    # ------------------------------------------------------------------
    # Step 3 — reopen the saved stage in this same subprocess
    # ------------------------------------------------------------------
    root = usd_dir / "cortex_root.usda"
    assert root.exists(), (
        f"cortex_root.usda not found at {root}; the substrate did not "
        "flush to disk"
    )
    stage = Usd.Stage.Open(str(root))
    memory_prims = [
        p
        for p in stage.Traverse()
        if str(p.GetPath()).startswith("/Memory_")
    ]
    assert len(memory_prims) == 1, (
        f"expected 1 memory prim on the reloaded stage, found "
        f"{len(memory_prims)}"
    )
    prim = memory_prims[0]

    # ------------------------------------------------------------------
    # Step 4 — typeName assertion
    # ------------------------------------------------------------------
    # Sdf would write ``typeName='MonetaMemory'`` with or without a
    # registered schema. The Step-1 SchemaRegistry assertion above
    # guarantees this string is more than dead bytes — the
    # OpenUSD runtime recognizes it as a typed schema.
    type_name = prim.GetTypeName()
    assert type_name == "MonetaMemory", (
        f"expected typeName 'MonetaMemory', got {type_name!r}"
    )

    # ------------------------------------------------------------------
    # Step 5 — six-attribute round-trip in USD camelCase per schema
    # ------------------------------------------------------------------
    payload = prim.GetAttribute("payload").Get()
    assert payload == "gate test memory", (
        f"payload round-trip: {payload!r}"
    )

    utility = prim.GetAttribute("utility").Get()
    assert isinstance(utility, float), (
        f"utility not float: {type(utility).__name__}"
    )
    assert abs(utility - 0.2) < 1e-5, (
        f"utility round-trip: {utility}"
    )

    attended = prim.GetAttribute("attendedCount").Get()
    assert attended == 5, f"attendedCount round-trip: {attended}"

    protected_floor = prim.GetAttribute("protectedFloor").Get()
    assert protected_floor == 0.0, (
        f"protectedFloor round-trip: {protected_floor}"
    )

    last_evaluated = prim.GetAttribute("lastEvaluated").Get()
    assert isinstance(last_evaluated, float), (
        f"lastEvaluated not float (USD Double): "
        f"{type(last_evaluated).__name__}"
    )

    # ------------------------------------------------------------------
    # Step 6 — priorState as a token, not an int
    # ------------------------------------------------------------------
    prior_state_attr = prim.GetAttribute("priorState")
    assert prior_state_attr.IsValid(), (
        "priorState attribute missing on a typed MonetaMemory prim"
    )
    prior_state_value = prior_state_attr.Get()
    assert prior_state_value == "staged_for_sync", (
        f"priorState round-trip: {prior_state_value!r} "
        f"(expected 'staged_for_sync' — the only token value the "
        f"substrate produces at staging-pass authoring time)"
    )
    type_token = prior_state_attr.GetTypeName()
    assert str(type_token) == "token", (
        f"priorState SDF type is {type_token!r}, not 'token' — "
        f"this typically means usd_target.py still authors "
        f"prior_state as Sdf.ValueTypeNames.Int"
    )

    print("OK")


if __name__ == "__main__":
    main()
