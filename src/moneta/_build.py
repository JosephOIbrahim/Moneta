"""Source identity of the running ``moneta`` package (SPEC section 4).

:func:`build_info` answers "which source is this process running?" without
a build step, a generated file or a subprocess, so it works for a raw
``src`` checkout on ``sys.path`` (how SYNAPSE loads Moneta), an editable
install, a VCS install and a wheel.

Verify by ``commit`` + ``src_digest`` (and the ``.pyd`` sha256 in
``NativeWheel``), never by ``version``: the release label is static and can
lag the source (a stale ``moneta 1.2.0rc1`` dist-info on this machine
reports a version that is not what runs).

Fields
------
``path``
    The package directory actually imported (``.../src/moneta``).
``mode``
    ``git-src``  the package sits at ``<root>/src/moneta`` and ``<root>/.git``
                 exists (a directory, or a ``gitdir:`` file for a worktree);
    ``editable`` / ``vcs`` / ``wheel``  an installed ``moneta`` distribution
                 whose location is ``path``, classed by its
                 ``direct_url.json``;
    ``unknown``  neither.
``commit``, ``ref``
    git-src: ``HEAD``, then the loose ref, then ``packed-refs`` (``ref`` is
    None when detached). vcs: ``commit_id`` / ``requested_revision`` from
    ``direct_url.json``. Otherwise None.
``dirty``
    Always ``"unknown"``: refs alone cannot see a dirty tree.
``version``
    git-src: ``[project].version`` of ``<root>/pyproject.toml`` (tomllib).
    Otherwise the installed distribution's version, only when that
    distribution's location is ``path``; else None.
``version_mismatch``
    True when an installed ``moneta`` distribution exists and either its
    location is not ``path`` or its version differs from ``version``.
    False otherwise (including when no distribution is installed).
``src_digest``
    sha256 over every ``*.py`` under the package directory (subpackages
    included, ``__pycache__`` excluded), in sorted order of the relative
    POSIX path *including the package name* (``moneta/api.py``,
    ``moneta/v5/model.py``). For each file the hash is fed
    ``relpath.encode("utf-8") + b"\\0" + content``, with ``content`` CRLF→LF
    normalized and no terminator after it. The same commit therefore gives
    the same digest on any checkout and in any install mode.
``python``
    ``"<implementation> <version>"`` of the running interpreter.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import unquote, urlparse

_PKG = Path(__file__).resolve().parent
DIST_NAME = "moneta"


@dataclass(frozen=True)
class BuildInfo:
    path: str
    mode: str  # git-src | editable | vcs | wheel | unknown
    commit: Optional[str]
    ref: Optional[str]
    dirty: str
    version: Optional[str]
    version_mismatch: bool
    src_digest: str
    python: str


# ---------------------------------------------------------------------------
# src_digest
# ---------------------------------------------------------------------------


def src_digest(pkg: Path) -> str:
    """See the module docstring. ``pkg`` is the package directory."""
    pkg = Path(pkg)
    base = pkg.parent
    files = []
    for p in pkg.rglob("*.py"):
        rel = p.relative_to(base)
        if "__pycache__" in rel.parts or not p.is_file():
            continue
        files.append((rel.as_posix(), p))
    files.sort(key=lambda t: t[0])
    h = hashlib.sha256()
    for rel, p in files:
        content = p.read_bytes().replace(b"\r\n", b"\n")
        h.update(rel.encode("utf-8") + b"\0" + content)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# git (read-only, no subprocess)
# ---------------------------------------------------------------------------


def _git_dirs(root: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """``(gitdir, commondir)`` for a repo or worktree rooted at ``root``."""
    g = root / ".git"
    if g.is_dir():
        return g, g
    if g.is_file():
        text = g.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return None, None
        gd = Path(text[len("gitdir:"):].strip())
        if not gd.is_absolute():
            gd = (root / gd).resolve()
        common = gd
        cd = gd / "commondir"
        if cd.is_file():
            c = Path(cd.read_text(encoding="utf-8").strip())
            common = c if c.is_absolute() else (gd / c).resolve()
        return gd, common
    return None, None


def _read_ref(gitdir: Path, common: Path) -> Tuple[Optional[str], Optional[str]]:
    """``(commit, ref)``: HEAD, then the loose ref, then packed-refs."""
    head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref:"):
        return (head or None), None  # detached
    ref = head[len("ref:"):].strip()
    for base in (gitdir, common):
        p = base / ref
        if p.is_file():
            sha = p.read_text(encoding="utf-8").strip()
            if sha:
                return sha, ref
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1] == ref:
                return parts[0], ref
    return None, ref


def _pyproject_version(root: Path) -> Optional[str]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11
        return None
    try:
        with open(root / "pyproject.toml", "rb") as fp:
            data = tomllib.load(fp)
    except (OSError, ValueError):
        return None
    v = data.get("project", {}).get("version")
    return v if isinstance(v, str) else None


# ---------------------------------------------------------------------------
# installed distribution
# ---------------------------------------------------------------------------


def _lookup_dist():
    try:
        return metadata.distribution(DIST_NAME)
    except metadata.PackageNotFoundError:
        return None
    except Exception:  # damaged metadata is "no usable dist"
        return None


def _direct_url(dist) -> dict:
    try:
        text = dist.read_text("direct_url.json")
    except Exception:
        return {}
    if not text:
        return {}
    try:
        d = json.loads(text)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _same(a: Path, b: Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def _dist_matches(dist, pkg: Path, du: dict) -> bool:
    """True when ``dist`` is the distribution of the package at ``pkg``."""
    try:
        loc = dist.locate_file(f"{DIST_NAME}/__init__.py")
        if _same(Path(str(loc)), pkg / "__init__.py") and (pkg / "__init__.py").exists():
            return True
    except Exception:
        pass
    if du.get("dir_info", {}).get("editable"):
        url = du.get("url", "")
        if isinstance(url, str) and url.startswith("file:"):
            p = unquote(urlparse(url).path)
            if len(p) >= 3 and p[0] == "/" and p[2] == ":":  # file:///C:/...
                p = p[1:]
            root = Path(p)
            for cand in (root / "src" / DIST_NAME, root / DIST_NAME):
                if _same(cand, pkg):
                    return True
    return False


# ---------------------------------------------------------------------------
# build_info
# ---------------------------------------------------------------------------


def _python() -> str:
    return f"{sys.implementation.name} {platform.python_version()}"


def compute_build_info(pkg: Path, lookup_dist: Callable = _lookup_dist) -> BuildInfo:
    """Uncached :func:`build_info` for the package directory ``pkg``."""
    pkg = Path(pkg).resolve()
    mode = "unknown"
    commit: Optional[str] = None
    ref: Optional[str] = None
    version: Optional[str] = None

    root = pkg.parent.parent if pkg.parent.name == "src" else None
    if root is not None and (root / ".git").exists():
        mode = "git-src"
        try:
            gd, common = _git_dirs(root)
            if gd is not None:
                commit, ref = _read_ref(gd, common)
        except (OSError, UnicodeDecodeError):
            commit, ref = None, None
        version = _pyproject_version(root)

    dist = lookup_dist()
    version_mismatch = False
    if dist is not None:
        du = _direct_url(dist)
        matches = _dist_matches(dist, pkg, du)
        dist_version = getattr(dist, "version", None)
        if mode != "git-src" and matches:
            version = dist_version
            dir_info = du.get("dir_info") if isinstance(du.get("dir_info"), dict) else {}
            vcs = du.get("vcs_info") if isinstance(du.get("vcs_info"), dict) else None
            if dir_info.get("editable"):
                mode = "editable"
            elif vcs is not None:
                mode = "vcs"
                commit = vcs.get("commit_id")
                ref = vcs.get("requested_revision")
            else:
                mode = "wheel"
        version_mismatch = (not matches) or (dist_version != version)

    return BuildInfo(
        path=str(pkg),
        mode=mode,
        commit=commit,
        ref=ref,
        dirty="unknown",
        version=version,
        version_mismatch=version_mismatch,
        src_digest=src_digest(pkg),
        python=_python(),
    )


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    """Identity of the running ``moneta`` source. Cached per process."""
    return compute_build_info(_PKG)


__all__ = ["BuildInfo", "build_info", "compute_build_info", "src_digest"]
