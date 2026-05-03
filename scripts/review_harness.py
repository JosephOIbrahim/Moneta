"""
Multi-agent review harness — Moneta v1.0.0.

Orchestrates a five-iteration MoE review of the Moneta codebase using
Anthropic's Claude Opus 4.7 (`model="claude-opus-4-7"`). Each iteration
spawns the seven role-scoped reviewers in parallel, then the
Adversarial-Reviewer, then a Synthesizer (Architect-arbiter) call. Five
themed loops run sequentially because each consumes the prior loop's
synthesis as context.

Design choices (locked at plan time):

- **Reviewer context:** full repo snapshot. Role isolation enforced via the
  system-prompt directive plus post-hoc filtering in
  `review_synthesizer.filter_role_isolation`.
- **Output policy:** per-round markdown and `findings.jsonl` go to
  `docs/review/` and are gitignored. The final cross-loop
  `synthesis.md` is the one durable record.
- **Execution scope:** the script is invoked separately by the user. This
  module performs no irreversible action on import. `--dry-run` prints
  prompts without calling the API.
- **Cost control:** prompt caching on the constitution + repo snapshot via
  a single `cache_control: ephemeral` breakpoint. ~45 calls per full run.
- **Robustness:** per-loop JSONL checkpointing makes the harness resumable.
  A constitution hash is stamped into every finding; if the constitution
  changes mid-run the harness aborts.

Usage:

    # Dry-run the assembled prompts for loop 1, no API call:
    python scripts/review_harness.py --dry-run --max-loops 1

    # Live single-loop smoke test (loop 1 only):
    python scripts/review_harness.py --max-loops 1

    # Live full run (5 loops):
    python scripts/review_harness.py

    # Resume after interruption:
    python scripts/review_harness.py --resume

The harness is designed for the Claude Agent SDK environment but uses the
plain `anthropic` SDK so it can run in any Python ≥3.11 process with the
`ANTHROPIC_API_KEY` env var set. The `[review]` extra in `pyproject.toml`
pulls the dependency.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make sibling modules importable when invoked as `python scripts/review_harness.py`.
sys.path.insert(0, str(Path(__file__).parent))

from review_roles import (  # noqa: E402  (sys.path manipulation required first)
    ADVERSARIAL,
    ROLE_REVIEWERS,
    THEMES,
    Role,
    Theme,
    theme_for_loop,
)
from review_synthesizer import (  # noqa: E402
    ClosureLedger,
    append_jsonl,
    read_jsonl,
    render_final_synthesis,
    synthesize_loop,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = REPO_ROOT / "docs" / "review"
CONSTITUTION_PATH = REPO_ROOT / "docs" / "review-constitution.md"
FINDINGS_JSONL = REVIEW_DIR / "findings.jsonl"
INVALID_JSONL = REVIEW_DIR / "findings.invalid.jsonl"
SYNTHESIS_PATH = REVIEW_DIR / "synthesis.md"
CHECKPOINT_PATH = REVIEW_DIR / "checkpoint.json"

MODEL = "claude-opus-4-7"
"""Plan-locked model. The user explicitly requested Opus 4.7."""

REVIEWER_MAX_TOKENS = 8192
SYNTHESIZER_MAX_TOKENS = 16384

PARALLEL_WORKERS = 7
"""One per role-reviewer; Adversarial runs separately."""

# ---------------------------------------------------------------------------
# Snapshot loading
# ---------------------------------------------------------------------------


SNAPSHOT_GLOBS: tuple[tuple[str, str], ...] = (
    ("ARCHITECTURE.md", "**/ARCHITECTURE.md"),
    ("MONETA.md", "**/MONETA.md"),
    ("CLAUDE.md", "**/CLAUDE.md"),
    ("README.md", "**/README.md"),
    ("docs", "docs/**/*.md"),
    ("src/moneta", "src/moneta/**/*.py"),
    ("tests", "tests/**/*.py"),
    ("scripts", "scripts/usd_metabolism_bench_v2.py"),
    ("pyproject.toml", "**/pyproject.toml"),
)
"""Patterns whose union forms the repo snapshot. We deliberately exclude the
review harness itself, the constitution, and any `docs/review/` outputs to
avoid feedback loops where the harness reviews its own output."""

EXCLUDE_PREFIXES: tuple[str, ...] = (
    "docs/review/",
    "scripts/review_harness.py",
    "scripts/review_roles.py",
    "scripts/review_synthesizer.py",
    "docs/review-constitution.md",
)


def _is_excluded(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in EXCLUDE_PREFIXES)


def load_repo_snapshot() -> str:
    """Concatenate every file matched by SNAPSHOT_GLOBS into a single string.

    Files are emitted in deterministic order (alphabetical by path) so the
    resulting prompt prefix has a stable hash for prompt caching.
    """
    paths: set[Path] = set()
    for _label, pattern in SNAPSHOT_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file():
                paths.add(path)

    rendered: list[str] = []
    for path in sorted(paths):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _is_excluded(rel):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            content = f"[unreadable: {exc}]"
        rendered.append(f"===== FILE: {rel} =====\n{content}")
    return "\n\n".join(rendered)


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PromptBundle:
    """Inputs assembled per reviewer, ready for the SDK call."""

    role: Role
    theme: Theme
    system_prompt: str
    user_prompt: str
    cache_breakpoint_index: int  # which content block carries cache_control


def assemble_reviewer_prompt(
    role: Role,
    theme: Theme,
    constitution: str,
    constitution_hash: str,
    snapshot: str,
    prior_synthesis: str,
) -> PromptBundle:
    """Build the system + user prompt for one reviewer."""
    system = textwrap.dedent(
        f"""\
        You are a reviewer agent for the Moneta codebase. The following
        constitution governs your output absolutely. You may not deviate
        from it. Constitution hash: {constitution_hash}.

        ---- BEGIN CONSTITUTION ----
        {constitution}
        ---- END CONSTITUTION ----

        Role-specific directive ({role.name}):
        {role.directive}

        Loop {theme.loop} theme: {theme.title}
        {theme.lens}

        Output format reminder (Constitution §14): emit a single JSON array
        of findings inside one ```json fenced block. Maximum 25 findings.
        No prose after the block. Each finding must conform to Constitution
        §7. Set `loop` to {theme.loop} and `theme` to "{theme.slug}". Set
        `role` to "{role.prefix}". Do NOT populate `constitution_hash` —
        the harness stamps it.
        """
    ).strip()

    prior_section = (
        f"\n\nPrior loop synthesis (read before emitting; do not repeat closed "
        f"findings):\n\n{prior_synthesis}"
        if prior_synthesis
        else "\n\n(This is loop 1 — no prior synthesis exists.)"
    )

    user = textwrap.dedent(
        f"""\
        Repo snapshot follows. Review per your role's touchpoint scope.
        Cross-cutting findings allowed only when the touchpoint lies in
        a file your role owns (Constitution §11). Adversarial-Reviewer is
        exempt.

        ===== REPO SNAPSHOT =====
        {snapshot}
        ===== END REPO SNAPSHOT =====
        {prior_section}

        Emit your findings now. JSON array, one fenced ```json block.
        """
    ).strip()

    return PromptBundle(
        role=role,
        theme=theme,
        system_prompt=system,
        user_prompt=user,
        cache_breakpoint_index=0,  # constitution + role directive cached together
    )


# ---------------------------------------------------------------------------
# JSON extraction from model output
# ---------------------------------------------------------------------------


_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def extract_findings_array(text: str) -> list[dict[str, Any]]:
    """Pull the first ```json fenced block out of `text` and parse it.

    Returns `[]` if no block is present or the block does not parse as a
    list. The synthesizer's validator will then drop any non-conformant
    objects.
    """
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [obj for obj in parsed if isinstance(obj, dict)]


def stamp_constitution_hash(
    findings: list[dict[str, Any]], constitution_hash: str
) -> list[dict[str, Any]]:
    return [{**f, "constitution_hash": constitution_hash} for f in findings]


# ---------------------------------------------------------------------------
# Anthropic SDK invocation (with retry per Commandment 3)
# ---------------------------------------------------------------------------


def _import_anthropic():
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "anthropic SDK not installed. Run: pip install -e .[review]"
        ) from exc
    return anthropic


def _call_via_sdk(bundle: PromptBundle, max_tokens: int) -> str:
    """SDK backend: requires `ANTHROPIC_API_KEY`. Caches the system prompt."""
    anthropic = _import_anthropic()
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": bundle.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": bundle.user_prompt}],
    )
    parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    return "\n".join(parts)


def _call_via_cli(bundle: PromptBundle, max_tokens: int) -> str:
    """CLI backend: dispatches via `claude -p` subprocess.

    Useful in environments without ANTHROPIC_API_KEY where the Claude Code
    CLI is authenticated via keychain/OAuth. The user prompt is piped via
    stdin to avoid argv length limits (the snapshot is ~520KB). The system
    prompt is passed via `--system-prompt` (~25KB, fits in argv).

    Returns the raw text of the model's `result` field. The harness then
    runs `extract_findings_array` on it identically to the SDK path.
    """
    cmd = [
        "claude",
        "-p",
        "--model",
        MODEL,
        "--system-prompt",
        bundle.system_prompt,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--tools",
        "",
        "--permission-mode",
        "default",
    ]
    completed = subprocess.run(  # noqa: S603 — internal harness, prompt is constructed locally
        cmd,
        input=bundle.user_prompt,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"claude CLI exit={completed.returncode}: {completed.stderr[:800]}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude CLI returned non-JSON: {completed.stdout[:400]!r}"
        ) from exc
    if payload.get("is_error") or payload.get("subtype") != "success":
        raise RuntimeError(f"claude CLI returned error payload: {payload}")
    return payload.get("result", "")


def _select_backend() -> str:
    """Return 'sdk' if ANTHROPIC_API_KEY is set, else 'cli'."""
    return "sdk" if os.environ.get("ANTHROPIC_API_KEY") else "cli"


def call_reviewer(
    bundle: PromptBundle,
    max_tokens: int = REVIEWER_MAX_TOKENS,
    *,
    backend: str = "auto",
) -> str:
    """Call Claude Opus 4.7 with one PromptBundle. Returns raw text content.

    Retries up to three times on transient errors (Commandment 3 cap). The
    backend is `sdk` (uses anthropic SDK + ANTHROPIC_API_KEY) or `cli`
    (uses `claude -p` subprocess). `auto` selects sdk if the env var is
    set, else cli.
    """
    if backend == "auto":
        backend = _select_backend()
    if backend not in ("sdk", "cli"):
        raise ValueError(f"unknown backend: {backend!r}")

    impl = _call_via_sdk if backend == "sdk" else _call_via_cli

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            return impl(bundle, max_tokens)
        except Exception as exc:  # noqa: BLE001 — backend errors are heterogeneous
            last_exc = exc
            sleep_s = 2**attempt
            print(
                f"  ! {bundle.role.prefix} ({backend}) attempt {attempt}/3 "
                f"failed: {str(exc)[:200]}; backing off {sleep_s}s",
                file=sys.stderr,
            )
            time.sleep(sleep_s)
    raise RuntimeError(
        f"Three retries exhausted for {bundle.role.prefix}: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Loop orchestration
# ---------------------------------------------------------------------------


@dataclass
class LoopState:
    loop: int
    raw_findings: list[dict[str, Any]]


def run_loop(
    loop: int,
    constitution: str,
    constitution_hash: str,
    snapshot: str,
    prior_synthesis: str,
    *,
    dry_run: bool,
    backend: str,
) -> LoopState:
    """Run one themed loop: parallel role reviewers, then adversarial."""
    theme = theme_for_loop(loop)
    print(f"\n=== Loop {loop}: {theme.title} ({theme.slug}) ===\n")

    role_bundles: list[PromptBundle] = [
        assemble_reviewer_prompt(
            role=role,
            theme=theme,
            constitution=constitution,
            constitution_hash=constitution_hash,
            snapshot=snapshot,
            prior_synthesis=prior_synthesis,
        )
        for role in ROLE_REVIEWERS
    ]

    role_findings: list[dict[str, Any]] = []
    if dry_run:
        for b in role_bundles:
            print(f"  [dry-run] would call {b.role.prefix} "
                  f"(system={len(b.system_prompt)} chars, "
                  f"user={len(b.user_prompt)} chars)")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            futures = {
                pool.submit(call_reviewer, b, backend=backend): b for b in role_bundles
            }
            for future in concurrent.futures.as_completed(futures):
                bundle = futures[future]
                try:
                    text = future.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! {bundle.role.prefix} hard-failed: {exc}", file=sys.stderr)
                    continue
                findings = extract_findings_array(text)
                findings = stamp_constitution_hash(findings, constitution_hash)
                print(f"  ✓ {bundle.role.prefix}: {len(findings)} findings emitted")
                role_findings.extend(findings)

    # Adversarial pass — sees the role findings as additional input.
    adversarial_input = (
        "\n\nFindings emitted this loop by role-reviewers (refute, find "
        "missing failure modes, probe envelope edges):\n\n"
        + json.dumps(role_findings, indent=2, ensure_ascii=False)
    )
    adv_bundle = assemble_reviewer_prompt(
        role=ADVERSARIAL,
        theme=theme,
        constitution=constitution,
        constitution_hash=constitution_hash,
        snapshot=snapshot,
        prior_synthesis=prior_synthesis + adversarial_input,
    )

    if dry_run:
        print(f"  [dry-run] would call adversarial "
              f"(system={len(adv_bundle.system_prompt)} chars, "
              f"user={len(adv_bundle.user_prompt)} chars)")
        adv_findings: list[dict[str, Any]] = []
    else:
        try:
            adv_text = call_reviewer(adv_bundle, backend=backend)
            adv_findings = extract_findings_array(adv_text)
            adv_findings = stamp_constitution_hash(adv_findings, constitution_hash)
            print(f"  ✓ adversarial: {len(adv_findings)} findings emitted")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! adversarial hard-failed: {exc}", file=sys.stderr)
            adv_findings = []

    return LoopState(loop=loop, raw_findings=role_findings + adv_findings)


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------


def save_checkpoint(loop_completed: int, constitution_hash: str) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(
            {"loop_completed": loop_completed, "constitution_hash": constitution_hash},
            indent=2,
        ),
        encoding="utf-8",
    )


def load_checkpoint() -> dict[str, Any] | None:
    if not CHECKPOINT_PATH.exists():
        return None
    return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Moneta multi-agent review harness")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print assembled prompts without calling the API.",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=len(THEMES),
        help=f"Stop after N loops (default {len(THEMES)}).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the last checkpoint instead of starting fresh.",
    )
    parser.add_argument(
        "--print-snapshot-stats",
        action="store_true",
        help="Print the snapshot byte/line count and exit (debugging).",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "sdk", "cli"),
        default="auto",
        help=(
            "Backend for model calls: 'sdk' uses the anthropic SDK with "
            "ANTHROPIC_API_KEY; 'cli' shells out to `claude -p`; 'auto' "
            "(default) picks sdk when ANTHROPIC_API_KEY is set, cli otherwise."
        ),
    )
    args = parser.parse_args(argv)

    if not CONSTITUTION_PATH.exists():
        raise SystemExit(f"Constitution not found at {CONSTITUTION_PATH}")
    constitution = CONSTITUTION_PATH.read_text(encoding="utf-8")
    constitution_hash = _hash(constitution)
    print(f"Constitution hash: {constitution_hash}")

    snapshot = load_repo_snapshot()
    if args.print_snapshot_stats:
        print(f"Snapshot bytes: {len(snapshot):,}")
        print(f"Snapshot lines: {snapshot.count(chr(10)):,}")
        return 0

    backend = args.backend
    if backend == "auto":
        backend = _select_backend()
    print(f"Backend: {backend}")

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    start_loop = 1
    if args.resume:
        ckpt = load_checkpoint()
        if ckpt:
            if ckpt["constitution_hash"] != constitution_hash:
                raise SystemExit(
                    "ConstitutionDriftError: checkpoint was written under a "
                    f"different constitution hash ({ckpt['constitution_hash']} "
                    f"vs current {constitution_hash}). Restart without --resume."
                )
            start_loop = ckpt["loop_completed"] + 1
            print(f"Resuming at loop {start_loop}")
        else:
            print("No checkpoint found; starting at loop 1")

    end_loop = min(start_loop + args.max_loops - 1, len(THEMES))

    ledger = ClosureLedger()
    all_findings: list[dict[str, Any]] = read_jsonl(FINDINGS_JSONL)
    if not args.resume:
        # Fresh run: clear any prior outputs to avoid contamination.
        for path in (FINDINGS_JSONL, INVALID_JSONL, SYNTHESIS_PATH):
            if path.exists():
                path.unlink()
        all_findings = []
        # Also clear per-round files from previous runs.
        for stale in REVIEW_DIR.glob("round-*.md"):
            stale.unlink()

    prior_synthesis = ""

    for loop in range(start_loop, end_loop + 1):
        theme = theme_for_loop(loop)
        loop_state = run_loop(
            loop=loop,
            constitution=constitution,
            constitution_hash=constitution_hash,
            snapshot=snapshot,
            prior_synthesis=prior_synthesis,
            dry_run=args.dry_run,
            backend=backend,
        )

        if args.dry_run:
            # In dry-run there are no findings to synthesize; stop after first loop.
            print("[dry-run] complete; not synthesizing.")
            return 0

        result = synthesize_loop(loop_state.raw_findings, loop=loop)
        round_md_path = REVIEW_DIR / f"round-{loop}-{theme.slug}.md"
        round_md_path.write_text(result.markdown, encoding="utf-8")

        append_jsonl(FINDINGS_JSONL, result.kept)
        if result.invalid:
            append_jsonl(
                INVALID_JSONL,
                [{"finding": f, "reason": reason} for f, reason in result.invalid],
            )

        ledger.record_closures(result.kept)
        all_findings.extend(result.kept)
        prior_synthesis = result.markdown

        save_checkpoint(loop_completed=loop, constitution_hash=constitution_hash)

        print(
            f"  → round-{loop}-{theme.slug}.md written "
            f"({len(result.kept)} kept, "
            f"{len(result.dropped_role)} role-isolation, "
            f"{len(result.dropped_dupe)} duplicate, "
            f"{len(result.invalid)} invalid)"
        )

    if not args.dry_run and end_loop == len(THEMES):
        SYNTHESIS_PATH.write_text(
            render_final_synthesis(all_findings, ledger, constitution_hash),
            encoding="utf-8",
        )
        print(f"\nFinal synthesis written to {SYNTHESIS_PATH.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
