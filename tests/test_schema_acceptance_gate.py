"""Acceptance gate for the codeless schema migration.

``HANDOFF_codeless_schema_moneta.md`` §8.1 / ``DEEP_THINK_BRIEF`` §7.6.

This is the truth condition for the schema migration. Sdf-level
authoring is intentionally schema-blind: ``Sdf.CreatePrimInLayer`` plus
``prim_spec.typeName = "MonetaMemory"`` writes the literal string to
disk regardless of whether any schema is registered. A naive round-trip
test (write a typed prim, reload it, assert ``GetTypeName() ==
"MonetaMemory"``) **passes under a broken plugin** — that is the
false-positive hazard the gate must defend against.

The defense, per Deep Think §7.6:

  1. **Subprocess isolation.** The gate test logic runs in a freshly
     spawned Python interpreter with ``PXR_PLUGINPATH_NAME`` pointing
     at the repo's ``schema/`` directory. The parent pytest process's
     ``pxr`` plugin state is not inherited; every gate run gets a
     clean USD runtime.

  2. **Explicit registry assertion.** Before any round-trip, the
     subprocess asserts
     ``Usd.SchemaRegistry().FindConcretePrimDefinition("MonetaMemory")
     is not None``. This is the only check that mathematically proves
     the OpenUSD runtime recognizes the schema (vs. Sdf having
     happened to serialize a string).

  3. **Six-attribute round-trip after the registry assertion.**
     Establishes value fidelity for all six attributes including the
     token-encoded ``priorState``.

The subprocess body lives in ``tests/_schema_gate_subprocess.py`` so
that the test file does not embed Python source as an f-string (an
escaping nightmare). The subprocess receives ``tmp_path`` as
``argv[1]``.

Why this test fails today (pre-implementation)
-----------------------------------------------

At step 2 of the surgery sequence, this test is written **first** and
**watched fail** before any schema is authored. The expected first
failure mode is exactly:

    AssertionError: FindConcretePrimDefinition('MonetaMemory') returned
    None — the codeless schema is not registered.

That failure proves the test is real (not a rubber stamp passing on
Sdf string serialization). After steps 3–5 land schema artifacts and
the typed-prim authoring change, the test passes.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "pxr",
    reason=(
        "schema acceptance gate requires pxr (OpenUSD bindings); "
        "run under a pxr-capable interpreter such as hython"
    ),
)

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
_SCHEMA_DIR = _REPO_ROOT / "schema"
_SUBPROCESS_BODY = _THIS_DIR / "_schema_gate_subprocess.py"


def test_schema_acceptance_gate(tmp_path: Path) -> None:
    """Subprocess-isolated SchemaRegistry validation + round-trip.

    See module docstring for the false-positive hazard this defends
    against. The first assertion inside the subprocess is the
    registry check; all other assertions follow only after that
    passes.
    """
    env = os.environ.copy()
    env["PXR_PLUGINPATH_NAME"] = str(_SCHEMA_DIR)
    # PYTHONPATH so the subprocess can import moneta (the repo is not
    # pip-installed in the gate's clean USD process).
    env["PYTHONPATH"] = str(_REPO_ROOT / "src")

    result = subprocess.run(
        [sys.executable, str(_SUBPROCESS_BODY), str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        pytest.fail(
            "schema acceptance gate subprocess failed "
            f"(returncode={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    assert "OK" in result.stdout, (
        "subprocess returned 0 but did not print 'OK' — the gate "
        "body terminated early without raising:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
