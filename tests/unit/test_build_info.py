"""C3: ``moneta.build_info()`` source identity (SPEC section 4).

Git fixtures are built in ``tmp_path`` (no git binary, no subprocess) and
fed to the uncached ``compute_build_info``, with the installed-distribution
lookup injected so the result never depends on what this machine has in
site-packages.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

import moneta
from moneta import _build

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def _no_dist():
    return None


def _tree(root: Path, crlf: bool = False) -> Path:
    """``root/src/moneta`` with a few modules, a subpackage and a cache dir."""
    pkg = root / "src" / "moneta"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__pycache__").mkdir()
    nl = b"\r\n" if crlf else b"\n"
    (pkg / "__init__.py").write_bytes(b'"""pkg."""' + nl + b"X = 1" + nl)
    (pkg / "api.py").write_bytes(b"def f():" + nl + b"    return 2" + nl)
    (pkg / "sub" / "__init__.py").write_bytes(b"")
    (pkg / "sub" / "deep.py").write_bytes(b"Y = 'z'" + nl)
    (pkg / "__pycache__" / "junk.py").write_bytes(b"ignored")
    (pkg / "notes.txt").write_bytes(b"not python")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "moneta"\nversion = "9.9.9rc1"\n', encoding="utf-8"
    )
    return pkg


def _expected_digest(pkg: Path) -> str:
    files = sorted(
        (p.relative_to(pkg.parent).as_posix(), p)
        for p in pkg.rglob("*.py")
        if "__pycache__" not in p.parts
    )
    h = hashlib.sha256()
    for rel, p in files:
        h.update(rel.encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# git layouts
# ---------------------------------------------------------------------------


def test_loose_ref(tmp_path):
    pkg = _tree(tmp_path)
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text(SHA_A + "\n", encoding="utf-8")
    (git / "packed-refs").write_text(f"{SHA_B} refs/heads/main\n", encoding="utf-8")
    bi = _build.compute_build_info(pkg, _no_dist)
    assert bi.mode == "git-src"
    assert (bi.commit, bi.ref) == (SHA_A, "refs/heads/main")  # loose ref wins
    assert bi.dirty == "unknown"
    assert bi.version == "9.9.9rc1" and bi.version_mismatch is False
    assert bi.path == str(pkg.resolve())
    assert bi.src_digest == _expected_digest(pkg)


def test_packed_refs(tmp_path):
    pkg = _tree(tmp_path)
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/harden/x\n", encoding="utf-8")
    (git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{SHA_C} refs/heads/other\n"
        f"{SHA_B} refs/heads/harden/x\n"
        f"^{SHA_C}\n",
        encoding="utf-8",
    )
    bi = _build.compute_build_info(pkg, _no_dist)
    assert bi.mode == "git-src"
    assert (bi.commit, bi.ref) == (SHA_B, "refs/heads/harden/x")


def test_detached_head(tmp_path):
    pkg = _tree(tmp_path)
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text(SHA_C + "\n", encoding="utf-8")
    bi = _build.compute_build_info(pkg, _no_dist)
    assert (bi.mode, bi.commit, bi.ref) == ("git-src", SHA_C, None)


def test_unresolvable_ref(tmp_path):
    pkg = _tree(tmp_path)
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/gone\n", encoding="utf-8")
    bi = _build.compute_build_info(pkg, _no_dist)
    assert (bi.mode, bi.commit, bi.ref) == ("git-src", None, "refs/heads/gone")


@pytest.mark.parametrize("packed", [False, True], ids=["loose-in-common", "packed-in-common"])
@pytest.mark.parametrize("relative", [True, False], ids=["relative-gitdir", "absolute-gitdir"])
def test_gitdir_file_worktree(tmp_path, packed, relative):
    common = tmp_path / "main" / ".git"
    wt_git = common / "worktrees" / "wt"
    wt_git.mkdir(parents=True)
    (wt_git / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
    if packed:
        (common / "packed-refs").write_text(f"{SHA_B} refs/heads/feature\n", encoding="utf-8")
    else:
        (common / "refs" / "heads").mkdir(parents=True)
        (common / "refs" / "heads" / "feature").write_text(SHA_A + "\n", encoding="utf-8")
    wt_root = tmp_path / "wt"
    pkg = _tree(wt_root)
    target = Path("..") / "main" / ".git" / "worktrees" / "wt" if relative else wt_git
    (wt_root / ".git").write_text(f"gitdir: {target.as_posix()}\n", encoding="utf-8")
    bi = _build.compute_build_info(pkg, _no_dist)
    assert bi.mode == "git-src"
    assert (bi.commit, bi.ref) == ((SHA_B if packed else SHA_A), "refs/heads/feature")


def test_no_git(tmp_path):
    pkg = _tree(tmp_path)
    bi = _build.compute_build_info(pkg, _no_dist)
    assert (bi.mode, bi.commit, bi.ref, bi.version, bi.version_mismatch) == (
        "unknown", None, None, None, False)
    assert bi.dirty == "unknown"
    assert bi.src_digest == _expected_digest(pkg)
    assert len(bi.src_digest) == 64


def test_package_not_under_src_is_not_git_src(tmp_path):
    pkg = tmp_path / "site" / "moneta"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "site" / ".git").mkdir()
    assert _build.compute_build_info(pkg, _no_dist).mode == "unknown"


# ---------------------------------------------------------------------------
# src_digest
# ---------------------------------------------------------------------------


def test_src_digest_crlf_equals_lf(tmp_path):
    lf = _tree(tmp_path / "lf")
    crlf = _tree(tmp_path / "crlf", crlf=True)
    assert (crlf / "api.py").read_bytes() != (lf / "api.py").read_bytes()
    assert _build.src_digest(lf) == _build.src_digest(crlf)


def test_src_digest_excludes_pycache_and_non_py(tmp_path):
    pkg = _tree(tmp_path)
    d0 = _build.src_digest(pkg)
    (pkg / "__pycache__" / "junk.py").write_bytes(b"changed")
    (pkg / "notes.txt").write_bytes(b"changed")
    (pkg / "sub" / "__pycache__").mkdir()
    (pkg / "sub" / "__pycache__" / "x.py").write_bytes(b"x")
    assert _build.src_digest(pkg) == d0


def test_src_digest_sees_content_paths_and_new_files(tmp_path):
    pkg = _tree(tmp_path)
    d0 = _build.src_digest(pkg)
    (pkg / "api.py").write_bytes(b"def f():\n    return 3\n")
    d1 = _build.src_digest(pkg)
    assert d1 != d0
    (pkg / "api.py").rename(pkg / "api2.py")
    d2 = _build.src_digest(pkg)
    assert d2 not in (d0, d1)
    (pkg / "sub" / "new.py").write_bytes(b"")
    assert _build.src_digest(pkg) != d2


def test_src_digest_independent_of_location(tmp_path):
    a = _tree(tmp_path / "one")
    b = _tree(tmp_path / "two" / "deeper")
    assert _build.src_digest(a) == _build.src_digest(b)


# ---------------------------------------------------------------------------
# installed distributions
# ---------------------------------------------------------------------------


class FakeDist:
    def __init__(self, version, location, direct_url=None):
        self.version = version
        self._location = Path(location)
        self._direct_url = direct_url

    def locate_file(self, path):
        return self._location / path

    def read_text(self, name):
        return self._direct_url if name == "direct_url.json" else None


def test_stale_dist_elsewhere_flags_mismatch_in_git_src(tmp_path):
    pkg = _tree(tmp_path / "repo")
    (tmp_path / "repo" / ".git").mkdir()
    (tmp_path / "repo" / ".git" / "HEAD").write_text(SHA_A, encoding="utf-8")
    stale = FakeDist("1.2.0rc1", tmp_path / "site-packages",
                     '{"url": "https://x/moneta.git", "vcs_info": {"vcs": "git", '
                     '"commit_id": "76da0673", "requested_revision": "v1.2.0-rc2"}}')
    bi = _build.compute_build_info(pkg, lambda: stale)
    assert bi.mode == "git-src" and bi.commit == SHA_A  # never the stale vcs commit
    assert bi.version == "9.9.9rc1"
    assert bi.version_mismatch is True


def test_stale_dist_elsewhere_without_git(tmp_path):
    pkg = _tree(tmp_path / "loose")
    stale = FakeDist("1.2.0rc1", tmp_path / "site-packages")
    bi = _build.compute_build_info(pkg, lambda: stale)
    assert (bi.mode, bi.version, bi.version_mismatch) == ("unknown", None, True)


def test_matching_wheel_dist(tmp_path):
    site = tmp_path / "site-packages"
    pkg = site / "moneta"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    bi = _build.compute_build_info(pkg, lambda: FakeDist("1.3.0rc1", site, "{}"))
    assert (bi.mode, bi.version, bi.version_mismatch) == ("wheel", "1.3.0rc1", False)


def test_matching_vcs_dist(tmp_path):
    site = tmp_path / "site-packages"
    pkg = site / "moneta"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    du = ('{"url": "https://x/moneta.git", "vcs_info": {"vcs": "git", '
          f'"commit_id": "{SHA_B}", "requested_revision": "v1.3.0-rc1"}}}}')
    bi = _build.compute_build_info(pkg, lambda: FakeDist("1.3.0rc1", site, du))
    assert (bi.mode, bi.commit, bi.ref) == ("vcs", SHA_B, "v1.3.0-rc1")
    assert bi.version_mismatch is False


def test_editable_dist_without_git(tmp_path):
    root = tmp_path / "checkout"
    pkg = _tree(root)  # no .git (an exported tree installed -e)
    url = root.resolve().as_uri()
    du = f'{{"url": "{url}", "dir_info": {{"editable": true}}}}'
    bi = _build.compute_build_info(pkg, lambda: FakeDist("9.9.9rc1", tmp_path / "sp", du))
    assert (bi.mode, bi.version, bi.version_mismatch) == ("editable", "9.9.9rc1", False)


def test_matching_dist_with_other_version_is_mismatch_in_git_src(tmp_path):
    root = tmp_path / "repo"
    pkg = _tree(root)
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text(SHA_A, encoding="utf-8")
    du = f'{{"url": "{root.resolve().as_uri()}", "dir_info": {{"editable": true}}}}'
    bi = _build.compute_build_info(pkg, lambda: FakeDist("1.0.0", tmp_path / "sp", du))
    assert bi.mode == "git-src" and bi.version == "9.9.9rc1"
    assert bi.version_mismatch is True


# ---------------------------------------------------------------------------
# the running package
# ---------------------------------------------------------------------------


def test_build_info_is_cached_frozen_and_describes_this_package():
    a = moneta.build_info()
    assert moneta.build_info() is a
    assert isinstance(a, moneta.BuildInfo)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.commit = "x"
    pkg = Path(moneta.__file__).resolve().parent
    assert a.path == str(pkg)
    assert a.src_digest == _build.src_digest(pkg) == _expected_digest(pkg)
    assert a.dirty == "unknown"
    assert a.mode in ("git-src", "editable", "vcs", "wheel", "unknown")
    if a.mode == "git-src":
        assert a.commit is None or (len(a.commit) == 40 and int(a.commit, 16) >= 0)
    assert a.python.split()[1].count(".") == 2


def test_build_module_uses_no_subprocess():
    tree = ast.parse(Path(_build.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "os"}
    assert imported <= {"__future__", "hashlib", "json", "platform", "sys", "dataclasses",
                        "functools", "importlib", "pathlib", "typing", "urllib", "tomllib"}
