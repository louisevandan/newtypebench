"""REFERENCE agent-loop runner — Claude CLI baseline only.

**Position in the benchmark** (PLAN.md §5.5):

This module is *not* the harness contract. PrototypeBench's contract with
the outside world is **task spec + score**; submitters bring their own
agent (their own system prompt, their own tool allowlist, their own
multi-turn / planning / retry strategy). This file is what we run when we
need a quick internal sanity check or when we want a baseline number to
compare against in the leaderboard, and nothing more.

Submitters are free — and encouraged — to wire up their own runner. The
public contract is just:

  1. Read the task instance (problem_statement, base_commit, ...).
  2. Produce a non-test unified diff (or mutate a working tree and let the
     harness `git diff` it).
  3. Pass the diff to `pbench score`.

Adopted in Phase 3 over patch-submission because frontier models reliably
produce semantically-correct fixes but can't reliably serialize byte-exact
unified diffs (2026-05-23 smoke on `IBM/mcp-context-forge#3284` — see
PLAN.md §8.3.0). Agent-loop fixes that by construction: `git diff` is the
canonical serializer of the actual edits.

This reference supports a single backend:

  * `claude` — Anthropic's Claude Code CLI in --print mode with --add-dir
    pointing at the instance's repo. Lets the model use Read/Edit/Write/
    Bash(git diff:*)/Glob/etc. to edit in place. We then git-diff the
    working tree against base_commit, excluding test files (the harness
    re-injects test_patch at score time anyway).

Other backends (Anthropic SDK direct tool-use, Gemini equivalent) plug
into the same `AgentLoopSpec` interface and are stubbed for follow-up.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import git_ops
from .sources import SourceConfig


class AgentLoopError(RuntimeError):
    pass


@dataclass
class AgentLoopSpec:
    instance_id: str
    repo_url: str
    base_commit: str
    problem_statement: str
    source: SourceConfig
    model: str = "claude-opus-4-7"
    max_turns: int | None = None         # backend-specific cap (Claude CLI has its own default)
    timeout_s: float = 1800.0            # 30 min default per instance


@dataclass
class AgentLoopResult:
    instance_id: str
    backend: str
    model: str
    duration_s: float
    diff: str = ""                       # extracted non-test diff (may be empty)
    diff_bytes: int = 0
    n_turns: int | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_AGENT_PROMPT_TEMPLATE = """\
You are an autonomous coding agent solving a PR-mined task.

TASK (from the original PR's problem statement):
{problem_statement}

WORKING REPOSITORY: the cwd is already checked out at the pre-fix `base_commit`. \
You can use the Read / Edit / Write / Glob / Bash tools to explore and modify files.

RULES — read these carefully:
  1. DO NOT modify any test files. Test files include any path matching
     `*test*`, `*.spec.*`, `*.test.*`, paths under `tests/`, `*/tests/`,
     `*/__tests__/`, etc. The harness will re-inject the canonical tests
     at scoring time; your test edits will be discarded.
  2. DO NOT run the tests. Running them takes minutes and reveals nothing
     useful — you don't have access to the canonical test_patch anyway.
  3. DO NOT make commits or stash changes. Just leave your edits in the
     working tree. The harness extracts your diff via `git diff`.
  4. Make the smallest correct change. The reference PR almost always
     touches 1-5 files. If your edit is sprawling, you've misread the spec.
  5. Stop as soon as you believe your edit is correct. The harness scores
     by re-running the canonical tests against your working tree.

Begin.
"""


def _build_prompt(spec: AgentLoopSpec) -> str:
    return _AGENT_PROMPT_TEMPLATE.format(problem_statement=spec.problem_statement.strip())


# ---------------------------------------------------------------------------
# Diff extraction
# ---------------------------------------------------------------------------

# Files the agent's diff should NOT include (the harness injects test_patch
# separately; agent's accidental test edits would conflict).
_TEST_DIFF_EXCLUDE = [
    "*test*",
    "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.spec.jsx",
    "*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx",
]


def _extract_diff(repo_dir: Path, base_commit: str) -> str:
    """git diff of working tree vs base_commit, scoped to non-test files."""
    return git_ops.diff(
        repo_dir,
        base_commit,
        "HEAD",
        paths=["."],
        exclude=_TEST_DIFF_EXCLUDE,
    )


def _extract_working_diff(repo_dir: Path, base_commit: str) -> str:
    """`git diff <base> -- .` over the *working tree* (not committed state).

    Agent edits files in the working tree without committing; HEAD still points
    at base_commit. So `git diff base..HEAD` returns empty. We diff the working
    tree against base directly.
    """
    cmd = [
        "git", "diff", "--no-color", base_commit, "--",
        *(f":(exclude){p}" for p in _TEST_DIFF_EXCLUDE),
    ]
    r = subprocess.run(
        cmd, cwd=repo_dir, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise AgentLoopError(f"git diff failed (rc={r.returncode}): {r.stderr[-500:]}")
    return r.stdout


# ---------------------------------------------------------------------------
# Backend: Claude CLI
# ---------------------------------------------------------------------------

_CLAUDE_ALLOWED_TOOLS = "Read Edit Write Glob Bash(git diff:*) Bash(grep:*) Bash(find:*) Bash(ls:*) Bash(cat:*) Bash(head:*) Bash(tail:*) Bash(wc:*)"


def run_claude_cli(
    spec: AgentLoopSpec,
    *,
    repo_dir: Path,
) -> AgentLoopResult:
    """Drive the agent via `claude --print` with --add-dir pointed at repo_dir."""
    repo_abs = repo_dir if repo_dir.is_absolute() else repo_dir.resolve()
    prompt = _build_prompt(spec)

    cmd = [
        "claude",
        "--print",
        "--model", spec.model,
        "--add-dir", str(repo_abs),
        "--allowedTools", _CLAUDE_ALLOWED_TOOLS,
        "--dangerously-skip-permissions",
        "--output-format", "text",
        "--disable-slash-commands",
        prompt,
    ]

    t0 = time.monotonic()
    try:
        r = subprocess.run(
            cmd,
            cwd=repo_abs,
            capture_output=True,
            text=True,
            timeout=spec.timeout_s,
            stdin=subprocess.DEVNULL,
        )
        timed_out = False
    except subprocess.TimeoutExpired as e:
        r = subprocess.CompletedProcess(
            args=cmd,
            returncode=-1,
            stdout=(e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or ""),
            stderr=(e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or ""),
        )
        timed_out = True

    duration = time.monotonic() - t0

    result = AgentLoopResult(
        instance_id=spec.instance_id,
        backend="claude-cli",
        model=spec.model,
        duration_s=duration,
        stdout=r.stdout,
        stderr=r.stderr,
        returncode=r.returncode,
    )

    if timed_out:
        result.error = f"claude-cli timeout after {spec.timeout_s:.0f}s"
        return result

    # Even on non-zero rc, the agent may have left valid edits in the working
    # tree — extract the diff regardless and let the caller decide.
    try:
        diff = _extract_working_diff(repo_abs, spec.base_commit)
    except AgentLoopError as e:
        result.error = f"diff extraction failed: {e}"
        return result

    result.diff = diff
    result.diff_bytes = len(diff)

    if r.returncode != 0 and not diff:
        result.error = f"claude-cli rc={r.returncode} and empty diff"
    elif r.returncode != 0:
        result.notes.append(f"claude-cli rc={r.returncode} but diff non-empty — recovered")

    return result


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def run_agent_loop(
    spec: AgentLoopSpec,
    *,
    backend: str = "claude",
    repo_dir: Path,
) -> AgentLoopResult:
    """Dispatch by backend name."""
    if backend == "claude":
        return run_claude_cli(spec, repo_dir=repo_dir)
    raise AgentLoopError(
        f"unknown agent-loop backend: {backend!r}. "
        f"Available: 'claude'. (Anthropic SDK / Gemini land in follow-ups.)"
    )
