"""
Role definitions, loop themes, and touchpoint allowlists for the multi-agent
review harness.

Mirrors `MONETA.md` §6 with one structural addition (Adversarial-Reviewer per
agent-commandments.md §7). The constitution at `docs/review-constitution.md`
is the binding source of truth; this module encodes the operational
parameters the harness needs to dispatch reviewers.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Role:
    """A single MoE reviewer role.

    `prefix` is the short slug used in finding ids and console output.
    `touchpoint_globs` is the set of repo-relative path patterns whose
    findings this role is permitted to emit. Cross-cutting findings are
    allowed only when their `file_path` matches one of these globs.

    `directive` is appended to the constitution-loaded system prompt to
    focus the reviewer on its role. Kept short — the constitution does the
    heavy lifting.
    """

    prefix: str
    name: str
    touchpoint_globs: tuple[str, ...]
    directive: str


ARCHITECT = Role(
    prefix="architect",
    name="Architect-Reviewer",
    touchpoint_globs=(
        "ARCHITECTURE.md",
        "MONETA.md",
        "CLAUDE.md",
        "src/moneta/*.py",
    ),
    directive=(
        "You are the Architect-Reviewer. Your charter is spec-conformance "
        "review. For each ARCHITECTURE.md clause, identify the implementation "
        "site (or its absence) and flag any drift. Cross-cutting findings in "
        "src/moneta/ are in scope when the issue is conformance to a clause. "
        "You are the route for §9 escalation candidates: when a finding "
        "conflicts with a locked decision, you must say so explicitly."
    ),
)

SUBSTRATE = Role(
    prefix="substrate",
    name="Substrate-Reviewer",
    touchpoint_globs=(
        "src/moneta/ecs.py",
        "src/moneta/decay.py",
        "src/moneta/api.py",
        "src/moneta/attention_log.py",
        "src/moneta/types.py",
    ),
    directive=(
        "You are the Substrate-Reviewer. Your charter is the ECS, decay math, "
        "the four-op API, attention log, and core types. Look for "
        "letter-vs-intent gaps in the decay formula, evaluation points, the "
        "lock-free attention log, and the four-op signatures. You may NOT "
        "propose a fifth operation."
    ),
)

PERSISTENCE = Role(
    prefix="persistence",
    name="Persistence-Reviewer",
    touchpoint_globs=(
        "src/moneta/vector_index.py",
        "src/moneta/durability.py",
        "src/moneta/sequential_writer.py",
    ),
    directive=(
        "You are the Persistence-Reviewer. Your charter is the shadow vector "
        "index, WAL-lite durability, and the USD-first/vector-second "
        "sequential write Protocol. Probe kill-9 recovery, the AuthoringTarget "
        "and VectorIndexTarget Protocols, and the LanceDB shadow-commit "
        "budget (≤15ms p99). The vector index is authoritative; no 2PC."
    ),
)

USD = Role(
    prefix="usd",
    name="USD-Reviewer",
    touchpoint_globs=("src/moneta/usd_target.py",),
    directive=(
        "You are the USD-Reviewer. Your charter is the real OpenUSD writer: "
        "narrow lock discipline (Sdf.ChangeBlock only, Save outside lock), "
        "UUID prim naming, strong-position sublayers, and sublayer rotation "
        "at 50k. The Pass 5 Q6 finding (DETERMINISTIC SAFE) is binding; do "
        "not propose restoring a wide writer lock."
    ),
)

CONSOLIDATION = Role(
    prefix="consolidation",
    name="Consolidation-Reviewer",
    touchpoint_globs=(
        "src/moneta/consolidation.py",
        "src/moneta/mock_usd_target.py",
        "src/moneta/manifest.py",
    ),
    directive=(
        "You are the Consolidation-Reviewer. Your charter is the sleep-pass "
        "trigger, selection criteria (prune/stage), the mock USD target "
        "(retained alongside the real target for A/B), and manifest "
        "generation. Idle-window scheduling (>5s, not 1Hz) and 500-prim "
        "batch cap are envelope constraints — verify they are enforced "
        "in code, not just documented."
    ),
)

TEST = Role(
    prefix="test",
    name="Test-Reviewer",
    touchpoint_globs=(
        "tests/**/*.py",
        "tests/conftest.py",
        "scripts/usd_metabolism_bench_v2.py",
    ),
    directive=(
        "You are the Test-Reviewer. Your charter is unit, integration, and "
        "load coverage; fixtures; and the Phase 2 benchmark harness. Per "
        "Commandment 7, tests must be motivated to find failure, not "
        "confirm success. Vague assertions are bugs. Coverage holes that "
        "would let a regression of a locked invariant land silently are "
        "Critical."
    ),
)

DOCUMENTARIAN = Role(
    prefix="documentarian",
    name="Documentarian-Reviewer",
    touchpoint_globs=(
        "README.md",
        "docs/**/*.md",
        "src/moneta/*.py",  # docstring-level findings only
    ),
    directive=(
        "You are the Documentarian-Reviewer. Your charter is doc-vs-code "
        "drift, README accuracy, and docstring discipline. For src/moneta/ "
        "files you may emit findings only against module-level or "
        "public-function docstrings — NOT against implementation. The "
        "Documentarian contract is ≤1 PR lag; flag drift accordingly."
    ),
)

ADVERSARIAL = Role(
    prefix="adversarial",
    name="Adversarial-Reviewer",
    touchpoint_globs=("**/*",),  # adversarial is exempt from role isolation
    directive=(
        "You are the Adversarial-Reviewer. Your charter is to break the "
        "invariants. For each finding the role-reviewers emitted this loop, "
        "ask: is this refutable? For each locked invariant, propose a "
        "concrete mutation (a code change, a config drift, a "
        "third-party-library upgrade) that would silently break the "
        "invariant without breaking any current test. That is a finding. "
        "You are the only reviewer exempt from role isolation."
    ),
)

ROLE_REVIEWERS: tuple[Role, ...] = (
    ARCHITECT,
    SUBSTRATE,
    PERSISTENCE,
    USD,
    CONSOLIDATION,
    TEST,
    DOCUMENTARIAN,
)
"""The seven role reviewers. Adversarial runs separately, after these."""

ALL_ROLES: tuple[Role, ...] = ROLE_REVIEWERS + (ADVERSARIAL,)


# ---------------------------------------------------------------------------
# Loop themes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Theme:
    """One of the five themed loops.

    `slug` is the file-system-safe identifier (used in output filenames and
    finding ids). `lead_role_prefixes` indicates which role(s) are expected
    to produce the highest-signal findings for this theme; the synthesizer
    weights them slightly higher when ranking.
    """

    loop: int
    slug: str
    title: str
    lead_role_prefixes: tuple[str, ...]
    lens: str


THEMES: tuple[Theme, ...] = (
    Theme(
        loop=1,
        slug="spec-conformance",
        title="Spec ↔ code conformance",
        lead_role_prefixes=("architect",),
        lens=(
            "Walk ARCHITECTURE.md clause by clause. For each clause, locate "
            "the implementation site in src/moneta/. Flag any clause without "
            "an implementation site, any implementation site without a "
            "clause, and any byte-level drift in the four-op signatures or "
            "the decay formula. Conformance to MONETA.md §2 (locked "
            "foundations) and the §16 conformance checklist is the spine "
            "of this loop."
        ),
    ),
    Theme(
        loop=2,
        slug="concurrency-atomicity",
        title="Concurrency & atomicity",
        lead_role_prefixes=("usd", "persistence"),
        lens=(
            "Probe the narrow writer-lock scope in usd_target.py "
            "(ChangeBlock-only, Save outside lock); the lock-free attention "
            "log atomic swap in attention_log.py; the sequential-write "
            "ordering in sequential_writer.py (USD first, vector second, "
            "vector authoritative); the URI lock registry in api.py; and "
            "kill-9 recovery via durability.py. The Pass 5 Q6 ruling "
            "(DETERMINISTIC SAFE) and the §15.6 narrow lock are binding."
        ),
    ),
    Theme(
        loop=3,
        slug="correctness-edges",
        title="Correctness & edge cases",
        lead_role_prefixes=("substrate", "adversarial"),
        lens=(
            "Probe correctness edges: decay clock-skew Δt clamp; the "
            "protected-floor never-decays-below trap (a Phase 3 known "
            "limitation); quota race on count_protected; vector-index "
            "state-machine soundness across VOLATILE → STAGED_FOR_SYNC → "
            "CONSOLIDATED; and clamp boundaries (utility floor, half-life "
            "min/max, embedding dimension homogeneity per ARCHITECTURE.md "
            "§7.1). Adversarial-Reviewer leads the failure-mode hunt."
        ),
    ),
    Theme(
        loop=4,
        slug="performance-envelope",
        title="Performance & operational envelope",
        lead_role_prefixes=("architect", "test"),
        lens=(
            "Verify the §15.2 envelope is enforced in code, not just "
            "documented. Sublayer rotation at 50k actually triggered? Batch "
            "≤500 enforced before commit? Idle-window >5s scheduling "
            "respected? Shadow-commit ≤15ms p99 instrumented? Is the Phase 2 "
            "benchmark harness in scripts/ still representative of the "
            "shipped narrow-lock implementation, or has Pass 6 made parts "
            "of it stale?"
        ),
    ),
    Theme(
        loop=5,
        slug="simplicity-doc-tests",
        title="Simplicity, doc drift, dead code, test gaps",
        lead_role_prefixes=("documentarian", "test"),
        lens=(
            "Apply 'don't add abstractions beyond what the task requires' "
            "retroactively. Identify orphaned helpers, dead code, missing "
            "adversarial integration tests, coverage holes that would let a "
            "locked invariant regression land silently, and any drift "
            "between the docs and the code. The Documentarian contract is "
            "≤1 PR lag; flag any drift older than that."
        ),
    ),
)


def theme_for_loop(loop: int) -> Theme:
    """Return the Theme for a 1-indexed loop number, raising on out-of-range."""
    for theme in THEMES:
        if theme.loop == loop:
            return theme
    raise ValueError(f"loop {loop} is out of range; valid 1..{len(THEMES)}")


# ---------------------------------------------------------------------------
# Path-glob matching for role isolation
# ---------------------------------------------------------------------------


def _match_glob(path: str, pattern: str) -> bool:
    """Match a repo-relative path against a glob with `**` and `*` semantics.

    Implements just enough glob to support the touchpoint patterns used in
    role definitions. We do not pull in fnmatch's native `**` because it
    does not by default match across directory separators.
    """
    import re

    regex_parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i : i + 2] == "**":
            regex_parts.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
        elif pattern[i] == "*":
            regex_parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            regex_parts.append("[^/]")
            i += 1
        elif pattern[i] in ".+()|^$[]{}":
            regex_parts.append(re.escape(pattern[i]))
            i += 1
        else:
            regex_parts.append(pattern[i])
            i += 1
    regex = "^" + "".join(regex_parts) + "$"
    return re.match(regex, path) is not None


def is_in_touchpoint_scope(role: Role, file_path: str) -> bool:
    """True if a finding on `file_path` is within `role`'s touchpoint scope."""
    return any(_match_glob(file_path, pat) for pat in role.touchpoint_globs)


# ---------------------------------------------------------------------------
# Severity ordering (highest first) for synthesis ranking
# ---------------------------------------------------------------------------


SEVERITY_ORDER: dict[str, int] = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Low": 3,
    "Note": 4,
}
"""Lower integer = higher priority. Used by the synthesizer to sort."""


VALID_SEVERITIES: frozenset[str] = frozenset(SEVERITY_ORDER.keys())
VALID_ROLE_PREFIXES: frozenset[str] = frozenset(r.prefix for r in ALL_ROLES)
VALID_THEME_SLUGS: frozenset[str] = frozenset(t.slug for t in THEMES)
