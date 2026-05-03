"""Adversarial tests for cross-process flock in Moneta.__init__.

Test Engineer (Commandment #7): structurally separate from the
Substrate Engineer. Tests target the locked flock contract.

Contract:
- flock acquired ONLY when config.snapshot_path is not None.
- Lockfile path: config.snapshot_path.with_suffix('.lock').
- Failure: MonetaResourceLockedError with substring "cross-process".
- POSIX-only; Windows is no-op.
- Released on close().
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from moneta import Moneta, MonetaConfig, MonetaResourceLockedError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _REPO_ROOT / "src"


def _spawn_construct(
    snapshot_path: Path,
    wal_path: Path,
    storage_uri: str,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess:
    """Spawn a subprocess that tries to construct Moneta on the given paths.

    Returns CompletedProcess with stdout containing 'LOCKED:<msg>' if
    MonetaResourceLockedError was raised, 'OK' if construction
    succeeded, or 'OTHER:<repr>' for any other exception.
    """
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_SRC_PATH)!r})
        from pathlib import Path
        from moneta import Moneta, MonetaConfig, MonetaResourceLockedError
        try:
            m = Moneta(MonetaConfig(
                storage_uri={storage_uri!r},
                snapshot_path=Path({str(snapshot_path)!r}),
                wal_path=Path({str(wal_path)!r}),
            ))
            print("OK")
            m.close()
        except MonetaResourceLockedError as e:
            print("LOCKED:" + str(e))
        except Exception as e:
            print("OTHER:" + repr(e))
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(_SRC_PATH) + os.pathsep + env.get("PYTHONPATH", "")
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def test_durability_config_in_same_process_still_raises_in_process_error(
    tmp_path: Path,
) -> None:
    """Same-process collision: _ACTIVE_URIS fires BEFORE flock is even
    attempted. Existing in-process behavior must be preserved."""
    snap = tmp_path / "s.json"
    wal = tmp_path / "w.jsonl"

    m1 = Moneta(MonetaConfig(
        storage_uri="moneta://test-same-process",
        snapshot_path=snap,
        wal_path=wal,
    ))
    try:
        with pytest.raises(MonetaResourceLockedError) as excinfo:
            Moneta(MonetaConfig(
                storage_uri="moneta://test-same-process",
                snapshot_path=snap,
                wal_path=wal,
            ))
        # In-process variant of the error must NOT mention cross-process.
        assert "cross-process" not in str(excinfo.value)
    finally:
        m1.close()


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
def test_cross_process_durability_lock_blocks_second_writer(
    tmp_path: Path,
) -> None:
    """Different process, same snapshot_path -> flock collision -> LOCKED."""
    snap = tmp_path / "s.json"
    wal = tmp_path / "w.jsonl"

    parent = Moneta(MonetaConfig(
        storage_uri="moneta://test-cross-process-parent",
        snapshot_path=snap,
        wal_path=wal,
    ))
    try:
        # Subprocess uses a DIFFERENT storage_uri so the in-process
        # registry can't collide — only the on-disk flock can.
        result = _spawn_construct(
            snap,
            wal,
            storage_uri="moneta://test-cross-process-child",
        )
        assert "LOCKED" in result.stdout, (
            f"expected LOCKED, got stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
        assert "cross-process" in result.stdout, (
            f"expected 'cross-process' substring in error message, "
            f"got: {result.stdout!r}"
        )
    finally:
        parent.close()


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
def test_cross_process_lock_released_on_close(tmp_path: Path) -> None:
    """After parent.close(), a fresh subprocess can acquire the lock."""
    snap = tmp_path / "s.json"
    wal = tmp_path / "w.jsonl"

    parent = Moneta(MonetaConfig(
        storage_uri="moneta://test-release-parent",
        snapshot_path=snap,
        wal_path=wal,
    ))
    parent.close()

    result = _spawn_construct(
        snap,
        wal,
        storage_uri="moneta://test-release-child",
    )
    assert "OK" in result.stdout, (
        f"expected OK after parent close, got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
def test_ephemeral_config_does_not_acquire_flock() -> None:
    """Ephemeral configs (no snapshot_path) -> no flock -> two
    subprocess constructions both succeed."""
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_SRC_PATH)!r})
        from moneta import Moneta, MonetaConfig
        try:
            with Moneta(MonetaConfig.ephemeral()) as m:
                print("OK")
        except Exception as e:
            print("OTHER:" + repr(e))
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(_SRC_PATH) + os.pathsep + env.get("PYTHONPATH", "")
    )

    r1 = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    r2 = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert "OK" in r1.stdout, (
        f"r1 stdout={r1.stdout!r} stderr={r1.stderr!r}"
    )
    assert "OK" in r2.stdout, (
        f"r2 stdout={r2.stdout!r} stderr={r2.stderr!r}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="flock is POSIX-only")
def test_lock_file_lives_at_expected_path(tmp_path: Path) -> None:
    """Lockfile is created at config.snapshot_path.with_suffix('.lock')."""
    snap = tmp_path / "s.json"
    wal = tmp_path / "w.jsonl"
    expected_lockfile = snap.with_suffix(".lock")

    with Moneta(MonetaConfig(
        storage_uri="moneta://test-lockfile-path",
        snapshot_path=snap,
        wal_path=wal,
    )):
        assert expected_lockfile.exists(), (
            f"expected lockfile at {expected_lockfile}, "
            f"contents of tmp_path: {list(tmp_path.iterdir())}"
        )
