"""Frontend (Playwright) FAIL_TO_PASS / PASS_TO_PASS extraction for one PR.

Mirrors `harness.extract` but uses the source repo's compose stack instead of
the host pytest path. The compose stack provides db + backend + prestart +
mailcatcher + frontend (dev) + playwright — all wired by the base repo.

Flow:
  1. clone/reuse repo checkout
  2. checkout base + apply test_patch (frontend test files only)
  3. compose build + run playwright → base.json
  4. checkout head
  5. compose build + run playwright → head.json
  6. diff → FAIL_TO_PASS / PASS_TO_PASS
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rich.console import Console

from . import frontend_direct_runner, frontend_runner, git_ops, playwright_report
from .sources import SourceConfig


@dataclass
class FrontendExtractSpec:
    instance_id: str
    repo_url: str
    base_commit: str
    head_commit: str
    test_patch: str | None = None     # frontend test diff (optional)
    playwright_args: list[str] | None = None  # e.g. ["tests/sign-up.spec.ts"]
    source: SourceConfig | None = None  # required for source-driven dispatch


@dataclass
class FrontendPhase:
    returncode: int
    json_present: bool
    n_passed: int
    n_failed: int
    n_skipped: int
    duration_s: float


@dataclass
class FrontendExtractResult:
    instance_id: str
    base_commit: str
    head_commit: str
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    base: FrontendPhase | None = None
    head: FrontendPhase | None = None
    notes: list[str] = field(default_factory=list)
    error: str | None = None


def _phase_summary(
    outcomes: dict[str, playwright_report.Outcome], rc: int, json_present: bool, dur: float
) -> FrontendPhase:
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for o in outcomes.values():
        counts[o] = counts.get(o, 0) + 1
    return FrontendPhase(
        returncode=rc,
        json_present=json_present,
        n_passed=counts["passed"],
        n_failed=counts["failed"],
        n_skipped=counts["skipped"],
        duration_s=dur,
    )


def extract_frontend(
    spec: FrontendExtractSpec,
    *,
    work_root: Path,
    console: Console | None = None,
    repo_dir: Path | None = None,
) -> FrontendExtractResult:
    console = console or Console()
    work_root.mkdir(parents=True, exist_ok=True)
    if repo_dir is None:
        repo_dir = work_root / "repo"
    out_dir = work_root / "frontend_out"
    out_dir.mkdir(exist_ok=True)

    result = FrontendExtractResult(
        instance_id=spec.instance_id,
        base_commit=spec.base_commit,
        head_commit=spec.head_commit,
    )

    def _write_summary() -> None:
        (out_dir / "summary.json").write_text(
            json.dumps(asdict(result), indent=2, sort_keys=True)
        )

    if not repo_dir.exists():
        console.log(f"cloning {spec.repo_url} → {repo_dir}")
        git_ops.clone(spec.repo_url, repo_dir)
    else:
        console.log(f"reusing checkout: {repo_dir}")
        git_ops.clean(repo_dir)

    project = f"pbench-fe-{spec.instance_id}"[:50]

    # Each compose project is its own docker network + volumes; teardown both
    # base and head explicitly to avoid stale db state.
    base_out = out_dir / "base"
    head_out = out_dir / "head"

    # Resolve dispatch + frontend dir from source config (with fastapi-template
    # legacy defaults so callers that don't pass `source` still work).
    runner_kind = (spec.source.frontend_runner_kind if spec.source else None) or "compose"
    fe_dir = (spec.source.frontend_dir if spec.source else None) or "frontend"

    if runner_kind not in ("compose", "playwright_direct"):
        result.error = f"unknown frontend_runner_kind: {runner_kind!r}"
        _write_summary()
        return result

    def _run_phase(phase_out: Path):
        """Dispatch to the right runner module; both return the same shape."""
        if runner_kind == "compose":
            return frontend_runner.run_phase(
                repo_dir=repo_dir, project=project, out_dir=phase_out,
                extra_args=spec.playwright_args,
            )
        # playwright_direct
        return frontend_direct_runner.run_phase_direct(
            repo_dir=repo_dir, source=spec.source,  # type: ignore[arg-type]
            instance_id=spec.instance_id, out_dir=phase_out,
            extra_args=spec.playwright_args,
        )

    # --- BASE ---
    console.log(f"checkout base {spec.base_commit[:10]}")
    git_ops.checkout(repo_dir, spec.base_commit)

    if not (repo_dir / fe_dir).exists():
        result.error = (
            f"base_commit has no {fe_dir}/ dir — likely pre-monorepo or wrong "
            f"source. Unsupported."
        )
        _write_summary()
        return result

    if spec.test_patch:
        try:
            git_ops.apply_diff(repo_dir, spec.test_patch)
        except git_ops.GitError as e:
            result.error = f"test_patch apply failed on base: {e}"
            _write_summary()
            return result

    console.log(f"running playwright (base, {runner_kind})")
    t0 = time.monotonic()
    try:
        run_b, base_outcomes = _run_phase(base_out)
    except frontend_runner.FrontendRunnerError as e:
        result.error = f"playwright base phase failed: {e}"
        _write_summary()
        return result
    base_out.mkdir(parents=True, exist_ok=True)
    (base_out / "runner.stdout.log").write_text(run_b.stdout)
    (base_out / "runner.stderr.log").write_text(run_b.stderr)
    result.base = _phase_summary(
        base_outcomes, run_b.returncode, run_b.json_present, time.monotonic() - t0
    )

    # --- HEAD ---
    console.log(f"checkout head {spec.head_commit[:10]}")
    git_ops.reset_hard(repo_dir, spec.base_commit)
    git_ops.checkout(repo_dir, spec.head_commit)

    console.log(f"running playwright (head, {runner_kind})")
    t0 = time.monotonic()
    try:
        run_h, head_outcomes = _run_phase(head_out)
    except frontend_runner.FrontendRunnerError as e:
        result.error = f"playwright head phase failed: {e}"
        _write_summary()
        return result
    head_out.mkdir(parents=True, exist_ok=True)
    (head_out / "runner.stdout.log").write_text(run_h.stdout)
    (head_out / "runner.stderr.log").write_text(run_h.stderr)
    result.head = _phase_summary(
        head_outcomes, run_h.returncode, run_h.json_present, time.monotonic() - t0
    )

    # --- diff ---
    base_pass = playwright_report.passing(base_outcomes)
    base_fail = playwright_report.failing(base_outcomes)
    head_pass = playwright_report.passing(head_outcomes)
    head_all = set(head_outcomes)

    # Specs that exist only on head (newly added in test_patch) are absent
    # from base_outcomes entirely. Treat them as base-failed for F2P purposes:
    # if the test didn't exist on base, agent must produce code to make it
    # pass on head — semantically identical to a failing test.
    new_in_head = head_all - set(base_outcomes)

    base_failed_or_missing = base_fail | new_in_head

    # Source-driven advisory filter, P2P-only: tests matching
    # source.advisory_test_path_re (e.g. Playwright snapshot tests) are kept
    # OUT of P2P (where they cause spurious binary failures via base/score-time
    # rendering drift) but stay IN F2P (where they're often the actual feature
    # being tested by a snapshot-style spec — excluding them would erase
    # legitimate regression signal and leave the instance with F2P=0).
    import re
    src_cfg = spec.source
    adv_re = (
        re.compile(src_cfg.advisory_test_path_re)
        if (src_cfg and src_cfg.advisory_test_path_re)
        else None
    )
    def _is_advisory(t: str) -> bool:
        return bool(adv_re and adv_re.search(t))

    f2p_raw = base_failed_or_missing & head_pass
    p2p_raw = (base_pass & head_pass) - f2p_raw
    p2p_advisory = {t for t in p2p_raw if _is_advisory(t)}

    result.fail_to_pass = sorted(f2p_raw)
    result.pass_to_pass = sorted(p2p_raw - p2p_advisory)

    if new_in_head:
        result.notes.append(
            f"{len(new_in_head)} spec(s) absent from base run — counted as F2P "
            f"candidates (typical for PRs that add new e2e tests)."
        )
    if p2p_advisory:
        result.notes.append(
            f"{len(p2p_advisory)} advisory P2P test(s) excluded "
            f"(matched source.advisory_test_path_re; F2P kept intact)."
        )

    _write_summary()
    console.log(
        f"FAIL_TO_PASS={len(result.fail_to_pass)} PASS_TO_PASS={len(result.pass_to_pass)}"
    )
    return result
