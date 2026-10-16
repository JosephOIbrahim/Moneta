"""Central loader for the optional ``moneta_native`` extension (v1 seams).

One place decides whether the Rust seams (scan, decay) may run, and
records why when they don't. It replaces the eager
``try: import moneta_native / except ImportError`` blocks that
``ecs.py`` and ``vector_index.py`` carried, which imported the wheel even
when native was off, reported a broken ``.pyd`` as "absent", and never
checked the API.

Environment (``MONETA_NATIVE``, stripped and lower-cased):

=========  ================================================
UNSET      variable missing
AUTO       ``""``, ``1``, ``true``, ``on``, ``yes``, ``auto``
OFF        ``0``, ``false``, ``off``, ``no``
REQUIRE    ``require``
UNKNOWN    anything else: one ``RuntimeWarning`` per process
=========  ================================================

Behaviour change: ``false``, ``off`` and ``no`` used to mean ON (only the
exact string ``"0"`` disabled native). They now mean OFF. ``1`` still
means auto.

Probe: once per process, cached, under a lock. A component that resolves
to off never triggers it; :func:`wheel_info` and :func:`native_available`
always force it. Classification:

``loaded``        imported and the API shape/version is acceptable.
``absent``        ``ModuleNotFoundError`` whose ``name`` is ``moneta_native``.
``broken``        any other ``ImportError`` (DLL load failure, a partially
                  unzipped wheel, a missing dependency); text kept.
``incompatible``  imported, but missing a symbol v1 calls, or an
                  unsupported ``NATIVE_API``.
``not_probed``    the probe has not run in this process.

Any non-``ImportError`` exception raised while importing propagates.

Each component captures the module reference it was given at
construction, so :func:`_reset_for_tests` never affects live objects.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import importlib.machinery
import json
import os
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Optional, Tuple

ENV_VAR = "MONETA_NATIVE"
MODULE_NAME = "moneta_native"

# ---------------------------------------------------------------------------
# Errors (exported from ``moneta``)
# ---------------------------------------------------------------------------


class NativeConfigError(ValueError):
    """The handle config and ``MONETA_NATIVE`` conflict (require vs off)."""


class NativeUnavailableError(RuntimeError):
    """Native was required, but the wheel is absent, broken or incompatible.

    Subclasses ``RuntimeError`` so callers that caught the old
    ``RuntimeError("... moneta_native is not installed")`` keep working.
    """


class NativeSeamError(RuntimeError):
    """A native seam failed where no fallback is permitted (require mode)."""


# ---------------------------------------------------------------------------
# Environment normalization
# ---------------------------------------------------------------------------

UNSET = "unset"
AUTO = "auto"
OFF = "off"
REQUIRE = "require"
UNKNOWN = "unknown"

_AUTO_VALUES = frozenset({"", "1", "true", "on", "yes", "auto"})
_OFF_VALUES = frozenset({"0", "false", "off", "no"})

# The mode an env class asks for when nothing else decides.
_CLASS_MODE = {UNSET: "auto", AUTO: "auto", OFF: "off", REQUIRE: "require", UNKNOWN: "auto"}


def classify_env(raw: Optional[str]) -> str:
    """Class of a raw ``MONETA_NATIVE`` value (``None`` means unset). Pure."""
    if raw is None:
        return UNSET
    value = raw.strip().lower()
    if value in _AUTO_VALUES:
        return AUTO
    if value in _OFF_VALUES:
        return OFF
    if value == "require":
        return REQUIRE
    return UNKNOWN


def mode_for_class(env_class: str) -> str:
    """``auto``, ``off`` or ``require`` for an env class."""
    return _CLASS_MODE[env_class]


_lock = threading.Lock()
_warned_unknown = False


def read_env() -> Tuple[str, Optional[str]]:
    """``(env_class, raw)`` for the current process environment.

    An UNKNOWN value emits one ``RuntimeWarning`` per process (until
    :func:`_reset_for_tests`); it is otherwise treated as auto.
    """
    global _warned_unknown
    raw = os.environ.get(ENV_VAR)
    env_class = classify_env(raw)
    if env_class == UNKNOWN:
        with _lock:
            first = not _warned_unknown
            _warned_unknown = True
        if first:
            warnings.warn(
                f"{ENV_VAR}={raw!r} is not a recognised value; treating it as auto "
                "(expected one of 1/true/on/yes/auto, 0/false/off/no, require)",
                RuntimeWarning,
                stacklevel=2,
            )
    return env_class, raw


def env_mode() -> Tuple[str, str, Optional[str]]:
    """``(mode, env_class, raw)`` resolved from the environment alone."""
    env_class, raw = read_env()
    return mode_for_class(env_class), env_class, raw


# ---------------------------------------------------------------------------
# Wheel identity
# ---------------------------------------------------------------------------

LOADED = "loaded"
ABSENT = "absent"
BROKEN = "broken"
INCOMPATIBLE = "incompatible"
NOT_PROBED = "not_probed"

SUPPORTED_APIS = frozenset({1})
LEGACY_VERSION = "0.1.0"

# Every attribute v1 calls on the module (ecs.py decay_all; vector_index.py).
_REQUIRED_CALLABLES = ("decay_batch",)
_SCANINDEX_METHODS = ("push", "set", "get", "kill", "compact", "scan", "slots")


@dataclass(frozen=True)
class NativeWheel:
    """What the probe found. Frozen; a new record per probe."""

    state: str
    reason: Optional[str] = None
    version: Optional[str] = None
    api: Optional[int] = None  # NATIVE_API if present; None for legacy 0.1.0
    path: Optional[str] = None  # the extension (.pyd / .so) file
    sha256: Optional[str] = None  # hex digest of ``path``
    record_match: Optional[bool] = None  # vs an adjacent dist-info RECORD
    direct_url: Optional[str] = None  # url from dist-info direct_url.json


_NOT_PROBED = NativeWheel(state=NOT_PROBED, reason="probe has not run in this process")

_probe_lock = threading.Lock()
_wheel: Optional[NativeWheel] = None
_module: Optional[ModuleType] = None


def _extension_path(mod: ModuleType) -> Optional[Path]:
    """Path of the compiled extension behind ``mod``, or None (fakes)."""
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    candidates = [getattr(mod, MODULE_NAME, None), mod]
    for cand in candidates:
        f = getattr(cand, "__file__", None) if isinstance(cand, ModuleType) else None
        if isinstance(f, str) and f.endswith(suffixes):
            return Path(f)
    return None


def _sha256(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _dist_version(dist: Path) -> Optional[str]:
    try:
        with open(dist / "METADATA", encoding="utf-8") as fp:
            for line in fp:
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
                if not line.strip():
                    break  # end of the header block
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return None


def _record_row_match(
    dist: Path, site_dir: Path, ext_resolved: Path, sha_hex: Optional[str]
) -> Tuple[bool, Optional[bool]]:
    """``(has_row, match)`` for the RECORD row naming the extension."""
    try:
        with open(dist / "RECORD", newline="", encoding="utf-8") as fp:
            rows = list(csv.reader(fp))
    except (OSError, UnicodeDecodeError, csv.Error, ValueError):
        # Unreadable or corrupt metadata is "no usable RECORD", never a
        # reason to block classification of an extension that imported.
        return False, None
    for row in rows:
        if not row or len(row) < 2:
            continue
        try:
            entry = (site_dir / row[0]).resolve()
        except OSError:
            continue
        if entry != ext_resolved:
            continue
        algo, _, digest = row[1].partition("=")
        if sha_hex is None or algo != "sha256" or not digest:
            return True, None
        expected = base64.urlsafe_b64encode(bytes.fromhex(sha_hex)).rstrip(b"=")
        return True, digest.encode("ascii", "replace") == expected
    return False, None


def _record_identity(
    ext: Path, sha_hex: Optional[str], version: Optional[str] = None
) -> Tuple[Optional[bool], Optional[str]]:
    """``(record_match, direct_url)`` from the ``moneta_native-*.dist-info``
    beside the package directory. None/None when there is none.

    Unzipping a newer wheel over an older one leaves both dist-info folders,
    so the dist-info whose METADATA ``Version`` equals the loaded module's
    ``__version__`` decides. Without a version match: True if any RECORD row
    for the extension matches, False only if rows exist and none match, None
    if no dist-info names the extension.
    """
    pkg_dir = ext.parent
    site_dir = pkg_dir.parent
    try:
        dist_infos = sorted(site_dir.glob(f"{MODULE_NAME}-*.dist-info"))
    except OSError:
        return None, None
    try:
        ext_resolved = ext.resolve()
    except OSError:
        ext_resolved = ext
    if version is not None:
        for dist in dist_infos:
            if _dist_version(dist) == version:
                has_row, match = _record_row_match(dist, site_dir, ext_resolved, sha_hex)
                if has_row:
                    return match, _direct_url(dist)
    seen_row: Optional[Path] = None
    for dist in dist_infos:
        has_row, match = _record_row_match(dist, site_dir, ext_resolved, sha_hex)
        if not has_row:
            continue
        if match:
            return True, _direct_url(dist)
        if seen_row is None and match is False:
            seen_row = dist
    if seen_row is not None:
        return False, _direct_url(seen_row)
    return None, None


def _direct_url(dist: Path) -> Optional[str]:
    try:
        text = (dist / "direct_url.json").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    try:
        url = json.loads(text).get("url")
    except (ValueError, AttributeError):
        return text.strip() or None
    return url if isinstance(url, str) else text.strip() or None


def _api_problems(mod: ModuleType) -> list[str]:
    missing: list[str] = []
    for name in _REQUIRED_CALLABLES:
        if not callable(getattr(mod, name, None)):
            missing.append(name)
    scan_index = getattr(mod, "ScanIndex", None)
    if scan_index is None:
        missing.append("ScanIndex")
    else:
        for meth in _SCANINDEX_METHODS:
            if not callable(getattr(scan_index, meth, None)):
                missing.append(f"ScanIndex.{meth}")
    if not hasattr(mod, "__version__"):
        missing.append("__version__")
    return missing


def _classify(mod: ModuleType) -> NativeWheel:
    version = getattr(mod, "__version__", None)
    version = None if version is None else str(version)
    api = getattr(mod, "NATIVE_API", None)
    ext = _extension_path(mod)
    sha = _sha256(ext) if ext is not None else None
    record_match: Optional[bool] = None
    direct_url: Optional[str] = None
    if ext is not None:
        try:
            record_match, direct_url = _record_identity(ext, sha, version)
        except Exception:
            # Identity is observability only; damaged dist-info metadata must
            # not turn a successful import into a failed construction.
            record_match, direct_url = None, None
    ident = dict(
        version=version,
        api=api,
        path=None if ext is None else str(ext),
        sha256=sha,
        record_match=record_match,
        direct_url=direct_url,
    )
    missing = _api_problems(mod)
    if missing:
        return NativeWheel(state=INCOMPATIBLE, reason="missing: " + ", ".join(missing), **ident)
    if api is not None:
        # Exact int only: bool/float alias 1 under hashing, and an
        # unhashable value would raise TypeError from the set lookup.
        if not (type(api) is int and api in SUPPORTED_APIS):
            return NativeWheel(
                state=INCOMPATIBLE,
                reason=f"unsupported NATIVE_API {api!r}; v1 supports {sorted(SUPPORTED_APIS)}",
                **ident,
            )
    elif version != LEGACY_VERSION:
        return NativeWheel(
            state=INCOMPATIBLE,
            reason=f"unknown legacy version {version!r} (no NATIVE_API)",
            **ident,
        )
    return NativeWheel(state=LOADED, **ident)


def _probe() -> Tuple[NativeWheel, Optional[ModuleType]]:
    """Import and classify once per process. Non-ImportErrors propagate."""
    global _wheel, _module
    with _probe_lock:
        if _wheel is not None:
            return _wheel, _module
        mod: Optional[ModuleType] = None
        try:
            mod = importlib.import_module(MODULE_NAME)
        except ModuleNotFoundError as e:
            if e.name == MODULE_NAME:
                wheel = NativeWheel(state=ABSENT, reason=f"{type(e).__name__}: {e}")
            else:
                wheel = NativeWheel(state=BROKEN, reason=f"{type(e).__name__}: {e}")
        except ImportError as e:
            wheel = NativeWheel(state=BROKEN, reason=f"{type(e).__name__}: {e}")
        else:
            wheel = _classify(mod)
        _wheel = wheel
        _module = mod if wheel.state == LOADED else None
        return _wheel, _module


def wheel_info() -> NativeWheel:
    """Identity of the wheel; always forces the probe."""
    return _probe()[0]


def current_wheel() -> NativeWheel:
    """The cached probe result, or a ``not_probed`` record. Never probes."""
    with _probe_lock:
        return _wheel if _wheel is not None else _NOT_PROBED


def native_available() -> bool:
    """True when the wheel is loaded and API-compatible; forces the probe."""
    return _probe()[0].state == LOADED


def select(mode: str) -> Tuple[Optional[ModuleType], Optional[str]]:
    """``(module, None)`` when native may run, else ``(None, reason)``.

    ``off`` never probes. ``require`` raises :class:`NativeUnavailableError`
    when the wheel is not loaded. ``auto`` returns ``(None, reason)``.
    """
    if mode == "off":
        return None, "off"
    if mode not in ("auto", "require"):
        raise ValueError(f"unknown native mode {mode!r}; expected 'auto', 'off' or 'require'")
    wheel, mod = _probe()
    if mod is not None:
        return mod, None
    reason = f"moneta_native {wheel.state}: {wheel.reason}"
    if mode == "require":
        raise NativeUnavailableError(f"native required but {reason}")
    return None, reason


# ---------------------------------------------------------------------------
# Process-wide aggregate counters (read by the test harness)
# ---------------------------------------------------------------------------

SEAMS = ("scan", "decay")
_counter_lock = threading.Lock()


def _fresh_counters() -> dict:
    return {seam: {"native_calls": 0, "fallbacks": {}} for seam in SEAMS}


_counters = _fresh_counters()


def count_native_call(seam: str, n: int = 1) -> None:
    """Record ``n`` successful Rust invocations on ``seam``."""
    with _counter_lock:
        _counters[seam]["native_calls"] += n


def count_fallback(seam: str, reason: str) -> None:
    """Record one oracle execution on ``seam`` by a native-active component."""
    with _counter_lock:
        fb = _counters[seam]["fallbacks"]
        fb[reason] = fb.get(reason, 0) + 1


def counters() -> dict:
    """Deep copy: ``{seam: {"native_calls": int, "fallbacks": {reason: int}}}``."""
    with _counter_lock:
        return {
            seam: {"native_calls": c["native_calls"], "fallbacks": dict(c["fallbacks"])}
            for seam, c in _counters.items()
        }


def _reset_for_tests() -> None:
    """Clear the probe cache, the UNKNOWN-warning latch and the counters.

    Live components keep the module reference they captured.
    """
    global _wheel, _module, _warned_unknown, _counters
    with _probe_lock:
        _wheel = None
        _module = None
    with _lock:
        _warned_unknown = False
    with _counter_lock:
        _counters = _fresh_counters()


__all__ = [
    "NativeConfigError",
    "NativeUnavailableError",
    "NativeSeamError",
    "NativeWheel",
    "classify_env",
    "mode_for_class",
    "read_env",
    "env_mode",
    "wheel_info",
    "current_wheel",
    "native_available",
    "select",
    "count_native_call",
    "count_fallback",
    "counters",
]
