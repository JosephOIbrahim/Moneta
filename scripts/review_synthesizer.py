"""
Synthesizer (Architect-arbiter) for the multi-agent review harness.

Responsibilities:

1. Validate every finding against the §7 schema in
   `docs/review-constitution.md`.
2. Filter findings that violate role-isolation (Commandment 5) — drop with
   reason `"role-isolation"` unless the emitter is the Adversarial-Reviewer.
3. Deduplicate findings via fuzzy match on (file_path, line_range, claim).
4. Rank by (severity, §9 flag, lead-role bonus, role index).
5. Emit per-loop markdown synthesis and the cross-loop closure ledger.

This module is invoked by `scripts/review_harness.py` after every loop. It
has no Anthropic SDK dependency — all LLM-output parsing happens at the
harness layer; the synthesizer is pure Python over already-extracted JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from review_roles import (
    ALL_ROLES,
    SEVERITY_ORDER,
    VALID_ROLE_PREFIXES,
    VALID_SEVERITIES,
    VALID_THEME_SLUGS,
    Role,
    Theme,
    is_in_touchpoint_scope,
    theme_for_loop,
)

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

_REQUIRED_KEYS: tuple[str, ...] = (
    "id",
    "role",
    "loop",
    "theme",
    "file_path",
    "line_range",
    "severity",
    "claim",
    "evidence_quote",
    "proposed_change",
    "risk",
    "conflicts_with_locked_decision",
    "requires_section9_escalation",
    "references",
    "closes",
)
"""Constitution §7 — these keys must be present on every finding."""

_ID_RE = re.compile(r"^[a-z]+-L\d+-[a-z0-9-]+$")


@dataclass
class ValidationResult:
    """Outcome of validating one finding."""

    ok: bool
    reason: str = ""


def validate_finding(finding: dict[str, Any], expected_loop: int) -> ValidationResult:
    """Validate one finding against the constitution §7 schema.

    Returns `ValidationResult(ok=True)` on success, or
    `ValidationResult(ok=False, reason=...)` describing the first failure.
    """
    if not isinstance(finding, dict):
        return ValidationResult(False, "finding is not an object")

    for key in _REQUIRED_KEYS:
        if key not in finding:
            return ValidationResult(False, f"missing key: {key}")

    if not isinstance(finding["id"], str) or not _ID_RE.match(finding["id"]):
        return ValidationResult(False, f"id malformed: {finding['id']!r}")

    if finding["role"] not in VALID_ROLE_PREFIXES:
        return ValidationResult(False, f"unknown role: {finding['role']!r}")

    if finding["loop"] != expected_loop:
        return ValidationResult(
            False, f"loop mismatch: got {finding['loop']!r}, expected {expected_loop}"
        )

    if finding["theme"] not in VALID_THEME_SLUGS:
        return ValidationResult(False, f"unknown theme: {finding['theme']!r}")

    if not isinstance(finding["file_path"], str) or not finding["file_path"]:
        return ValidationResult(False, "file_path empty or non-string")

    line_range = finding["line_range"]
    if (
        not isinstance(line_range, list)
        or len(line_range) != 2
        or not all(isinstance(n, int) and n >= 0 for n in line_range)
        or line_range[0] > line_range[1]
    ):
        return ValidationResult(False, f"line_range invalid: {line_range!r}")

    if finding["severity"] not in VALID_SEVERITIES:
        return ValidationResult(False, f"unknown severity: {finding['severity']!r}")

    for str_field in ("claim", "evidence_quote", "risk"):
        if not isinstance(finding[str_field], str) or not finding[str_field].strip():
            return ValidationResult(False, f"{str_field} empty or non-string")

    if not isinstance(finding["proposed_change"], str):
        return ValidationResult(False, "proposed_change non-string")

    for bool_field in ("conflicts_with_locked_decision", "requires_section9_escalation"):
        if not isinstance(finding[bool_field], bool):
            return ValidationResult(False, f"{bool_field} non-bool")

    if not isinstance(finding["references"], list) or not all(
        isinstance(r, str) for r in finding["references"]
    ):
        return ValidationResult(False, "references must be a list of strings")

    if finding["closes"] is not None and not isinstance(finding["closes"], str):
        return ValidationResult(False, "closes must be string or null")

    if finding["severity"] == "Critical" and finding["conflicts_with_locked_decision"]:
        if not finding["requires_section9_escalation"]:
            return ValidationResult(
                False,
                "Critical conflicting with locked decision must set requires_section9_escalation=true (§8)",
            )

    return ValidationResult(True)


def role_for_prefix(prefix: str) -> Role:
    """Look up the Role by prefix; raises if unknown."""
    for role in ALL_ROLES:
        if role.prefix == prefix:
            return role
    raise KeyError(f"unknown role prefix: {prefix!r}")


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _normalize_claim(claim: str) -> str:
    """Lowercase + collapse whitespace for fuzzy matching."""
    return " ".join(claim.lower().split())


def _line_ranges_overlap(a: list[int], b: list[int]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


def _dedupe_key(finding: dict[str, Any]) -> tuple[str, str]:
    """Coarse dedupe key: same file + normalized claim."""
    return (finding["file_path"], _normalize_claim(finding["claim"]))


def deduplicate(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop duplicate findings.

    Returns `(kept, dropped)`. A finding is a duplicate of an earlier one
    when their `_dedupe_key`s match AND their line ranges overlap. The
    *higher-severity* finding wins; on ties, the earlier (lower role
    index) finding wins. Dropped findings are returned for audit.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for candidate in findings:
        c_sev = SEVERITY_ORDER.get(candidate["severity"], 99)
        c_key = _dedupe_key(candidate)
        c_lr = candidate["line_range"]
        absorbed = False
        for i, existing in enumerate(kept):
            if _dedupe_key(existing) == c_key and _line_ranges_overlap(
                existing["line_range"], c_lr
            ):
                e_sev = SEVERITY_ORDER.get(existing["severity"], 99)
                if c_sev < e_sev:
                    dropped.append(existing)
                    kept[i] = candidate
                else:
                    dropped.append(candidate)
                absorbed = True
                break
        if not absorbed:
            kept.append(candidate)

    return kept, dropped


# ---------------------------------------------------------------------------
# Role-isolation filtering
# ---------------------------------------------------------------------------


def filter_role_isolation(
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop findings whose `file_path` lies outside the emitter's scope.

    Adversarial-Reviewer is exempt (Constitution §11). Returns
    `(kept, dropped)`.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for finding in findings:
        role = role_for_prefix(finding["role"])
        if role.prefix == "adversarial":
            kept.append(finding)
            continue
        if is_in_touchpoint_scope(role, finding["file_path"]):
            kept.append(finding)
        else:
            dropped.append({**finding, "_drop_reason": "role-isolation"})
    return kept, dropped


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def _rank_key(finding: dict[str, Any], theme: Theme) -> tuple[int, int, int, int]:
    """Sort key: (severity, !§9, !lead-role, role-index).

    Ties broken stably by role declaration order.
    """
    severity_rank = SEVERITY_ORDER.get(finding["severity"], 99)
    section9_rank = 0 if finding["requires_section9_escalation"] else 1
    lead_rank = 0 if finding["role"] in theme.lead_role_prefixes else 1
    role_index = next(
        (i for i, r in enumerate(ALL_ROLES) if r.prefix == finding["role"]), 99
    )
    return (severity_rank, section9_rank, lead_rank, role_index)


def rank(findings: list[dict[str, Any]], loop: int) -> list[dict[str, Any]]:
    """Sort findings highest-priority-first per Constitution §8."""
    theme = theme_for_loop(loop)
    return sorted(findings, key=lambda f: _rank_key(f, theme))


# ---------------------------------------------------------------------------
# Closure ledger
# ---------------------------------------------------------------------------


@dataclass
class ClosureLedger:
    """Tracks which prior-loop findings have been closed by later loops."""

    entries: list[dict[str, str]] = field(default_factory=list)

    def record_closures(self, findings: list[dict[str, Any]]) -> None:
        for f in findings:
            closed = f.get("closes")
            if closed:
                self.entries.append(
                    {
                        "closed_id": closed,
                        "closing_id": f["id"],
                        "closing_loop": str(f["loop"]),
                        "claim_summary": f["claim"][:120],
                    }
                )


# ---------------------------------------------------------------------------
# Per-loop markdown synthesis
# ---------------------------------------------------------------------------


def render_loop_markdown(
    loop: int,
    findings_ranked: list[dict[str, Any]],
    dropped_role: list[dict[str, Any]],
    dropped_dupe: list[dict[str, Any]],
    invalid_count: int,
) -> str:
    """Render one loop's findings as human-skimmable markdown."""
    theme = theme_for_loop(loop)
    lines: list[str] = []
    lines.append(f"# Review round {loop} — {theme.title}")
    lines.append("")
    lines.append(f"**Theme slug:** `{theme.slug}`  ")
    lines.append(f"**Lead role(s):** {', '.join(theme.lead_role_prefixes)}  ")
    lines.append(f"**Findings retained:** {len(findings_ranked)}  ")
    lines.append(f"**Dropped (role-isolation):** {len(dropped_role)}  ")
    lines.append(f"**Dropped (duplicate):** {len(dropped_dupe)}  ")
    lines.append(f"**Schema-invalid:** {invalid_count}")
    lines.append("")
    lines.append("## Lens")
    lines.append("")
    lines.append(theme.lens)
    lines.append("")

    section9 = [f for f in findings_ranked if f["requires_section9_escalation"]]
    others = [f for f in findings_ranked if not f["requires_section9_escalation"]]

    if section9:
        lines.append("## §9 escalation candidates")
        lines.append("")
        for f in section9:
            lines.extend(_render_finding(f))

    if others:
        lines.append("## Findings (ranked)")
        lines.append("")
        for f in others:
            lines.extend(_render_finding(f))

    if not findings_ranked:
        lines.append("_No findings retained this loop._")
        lines.append("")

    return "\n".join(lines) + "\n"


def _render_finding(f: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"### `{f['id']}` — {f['severity']} — {f['claim']}")
    lines.append("")
    lines.append(
        f"**Role:** {f['role']}  "
        f"**File:** `{f['file_path']}:{f['line_range'][0]}-{f['line_range'][1]}`  "
        f"**§9:** {'yes' if f['requires_section9_escalation'] else 'no'}  "
        f"**Conflicts with locked decision:** "
        f"{'yes' if f['conflicts_with_locked_decision'] else 'no'}"
    )
    if f.get("closes"):
        lines.append(f"**Closes:** `{f['closes']}`")
    lines.append("")
    lines.append("**Evidence:**")
    lines.append("")
    lines.append("```")
    lines.append(f["evidence_quote"])
    lines.append("```")
    lines.append("")
    if f["proposed_change"]:
        lines.append(f"**Proposed change:** {f['proposed_change']}")
        lines.append("")
    lines.append(f"**Risk if wrong:** {f['risk']}")
    lines.append("")
    if f["references"]:
        lines.append(
            "**References:** " + ", ".join(f"`{r}`" for r in f["references"])
        )
        lines.append("")
    lines.append("---")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Cross-loop final synthesis
# ---------------------------------------------------------------------------


def render_final_synthesis(
    all_findings: list[dict[str, Any]],
    ledger: ClosureLedger,
    constitution_hash: str,
) -> str:
    """Render the cross-loop synthesis.md.

    Sections:
      1. Headline counts
      2. §9 escalation candidates (consolidated)
      3. Critical findings by file
      4. High findings by file
      5. Closure ledger
      6. Constitution hash
    """
    closed_ids = {entry["closed_id"] for entry in ledger.entries}
    open_findings = [f for f in all_findings if f["id"] not in closed_ids]
    section9 = [f for f in open_findings if f["requires_section9_escalation"]]
    crit = [f for f in open_findings if f["severity"] == "Critical"]
    high = [f for f in open_findings if f["severity"] == "High"]

    lines: list[str] = []
    lines.append("# Multi-agent review synthesis — Moneta v1.0.0")
    lines.append("")
    lines.append(
        f"**Total findings (all loops):** {len(all_findings)}  "
        f"**Open after closures:** {len(open_findings)}  "
        f"**§9 candidates:** {len(section9)}  "
        f"**Critical:** {len(crit)}  "
        f"**High:** {len(high)}"
    )
    lines.append("")
    lines.append(f"**Constitution hash:** `{constitution_hash}`")
    lines.append("")

    if section9:
        lines.append("## §9 escalation candidates")
        lines.append("")
        for f in sorted(section9, key=lambda x: SEVERITY_ORDER.get(x["severity"], 99)):
            lines.extend(_render_finding(f))

    if crit:
        lines.append("## Critical findings (open)")
        lines.append("")
        for f in crit:
            lines.extend(_render_finding(f))

    if high:
        lines.append("## High findings (open)")
        lines.append("")
        for f in high:
            lines.extend(_render_finding(f))

    lines.append("## Closure ledger")
    lines.append("")
    if ledger.entries:
        lines.append("| Closed in loop | Closing id | Original id | Summary |")
        lines.append("| --- | --- | --- | --- |")
        for entry in ledger.entries:
            lines.append(
                f"| {entry['closing_loop']} | `{entry['closing_id']}` | "
                f"`{entry['closed_id']}` | {entry['claim_summary']} |"
            )
    else:
        lines.append("_No prior findings were closed across loops._")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Top-level synthesize() — called once per loop by the harness
# ---------------------------------------------------------------------------


@dataclass
class SynthesisResult:
    loop: int
    kept: list[dict[str, Any]]
    dropped_role: list[dict[str, Any]]
    dropped_dupe: list[dict[str, Any]]
    invalid: list[tuple[dict[str, Any], str]]
    markdown: str


def synthesize_loop(
    raw_findings: list[dict[str, Any]],
    loop: int,
) -> SynthesisResult:
    """Pipeline: validate → role-isolation filter → dedupe → rank → render."""
    invalid: list[tuple[dict[str, Any], str]] = []
    valid: list[dict[str, Any]] = []
    for f in raw_findings:
        result = validate_finding(f, expected_loop=loop)
        if result.ok:
            valid.append(f)
        else:
            invalid.append((f, result.reason))

    kept_after_role, dropped_role = filter_role_isolation(valid)
    kept_after_dedupe, dropped_dupe = deduplicate(kept_after_role)
    ranked = rank(kept_after_dedupe, loop=loop)

    markdown = render_loop_markdown(
        loop=loop,
        findings_ranked=ranked,
        dropped_role=dropped_role,
        dropped_dupe=dropped_dupe,
        invalid_count=len(invalid),
    )

    return SynthesisResult(
        loop=loop,
        kept=ranked,
        dropped_role=dropped_role,
        dropped_dupe=dropped_dupe,
        invalid=invalid,
        markdown=markdown,
    )


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
