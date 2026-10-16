"""Gate B: the reference decay loop stays byte-for-byte as shipped.

The nine loop lines of ``ECS._decay_oracle`` must equal ``src/moneta/ecs.py``
lines 264-272 at ``v1.3.0-rc1`` (also ``f9117b7``), compared as LF text so a
CRLF checkout does not matter. Rollback for the native-fallback path lives at
the call site in ``ECS.decay_all``, never inside the loop.

Reference hash: ``git show v1.3.0-rc1:src/moneta/ecs.py | sed -n '264,272p' | sha256sum``.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap

from moneta.ecs import ECS

REFERENCE_LOOP_SHA256 = "ded72d880bb0f2a251e8eceb1d34096d52a646876fbc9ae321308e7d01bce494"
REFERENCE_FIRST = "        for i in range(n):"
REFERENCE_LAST = "            self._last_evaluated[i] = now"


def _loop_lines() -> list[str]:
    src = inspect.getsource(ECS._decay_oracle).replace("\r\n", "\n")
    lines = src.split("\n")
    start = lines.index(REFERENCE_FIRST)
    end = lines.index(REFERENCE_LAST, start)
    return lines[start : end + 1]


def test_decay_oracle_loop_is_byte_identical_to_reference():
    block = _loop_lines()
    assert len(block) == 9, block
    digest = hashlib.sha256(("\n".join(block) + "\n").encode("utf-8")).hexdigest()
    assert digest == REFERENCE_LOOP_SHA256, "\n".join(block)


def test_decay_oracle_contains_only_the_count_and_the_loop():
    """No try/except, rollback or extra statement inside the oracle."""
    fn = ast.parse(textwrap.dedent(inspect.getsource(ECS._decay_oracle))).body[0]
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert [type(s).__name__ for s in body] == ["Assign", "For"]
    assert ast.unparse(body[0]) == "n = len(self._ids)"
    assert not any(isinstance(n, (ast.Try, ast.With)) for n in ast.walk(fn))


def test_decay_all_routes_every_oracle_run_through_decay_oracle():
    fn = ast.parse(textwrap.dedent(inspect.getsource(ECS.decay_all))).body[0]
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    names = [c.func.attr for c in calls]
    assert names.count("_decay_oracle") == 2, names  # pure-oracle path + auto fallback
    assert "decay_value" not in names
    assert not any(isinstance(n, ast.For) for n in ast.walk(fn)), "decay_all must not loop itself"
