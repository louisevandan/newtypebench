"""Score an agent-submitted patch against a task instance.

Shares the execution core with `harness.extract`. The only difference:
  extract applies `test_patch` on base to *derive* FAIL_TO_PASS/PASS_TO_PASS.
  score  applies `test_patch` + `agent_patch` on base to *verify* them.

Scoring (v1, SWE-bench convention):
  score = 1  iff  FAIL_TO_PASS ⊆ passing(agent_run)
              AND PASS_TO_PASS ⊆ passing(agent_run)
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rich.console import Console

from . import backend_runner, git_ops, junit, postgres
from .sources import SourceConfig, effective_uv_extras


@dataclass
class ScoreSpec:
    instance_id: str
    repo_url: str
    base_commit: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    agent_patch: str
    pytest_args: list[str] | None = None


@dataclass
class ScoreResult:
    instance_id: str
    score: int
    mode: str = "docker"
    source: str = ""
    fail_to_pass_passed: list[str] = field(default_factory=list)
    fail_to_pass_missing: list[str] = field(default_factory=list)
    pass_to_pass_passed: list[str] = field(default_factory=list)
    pass_to_pass_regressed: list[str] = field(default_factory=list)
    phase_returncode: int | None = None
    phase_duration_s: float | None = None
    error: str | None = None


def score_patch(
    spec: ScoreSpec,
    *,
    source: SourceConfig,
    work_root: Path,
    mode: str = "docker",
    console: Console | None = None,
) -> ScoreResult:
    console = console or Console()
    work_root.mkdir(parents=True, exist_ok=True)
    repo_dir = work_root / "repo"
    out_dir = work_root / "out"
    out_dir.mkdir(exist_ok=True)

    result = ScoreResult(instance_id=spec.instance_id, score=0, mode=mode, source=source.name)

    if not repo_dir.exists():
        console.log(f"cloning {spec.repo_url} → {repo_dir}")
        git_ops.clone(spec.repo_url, repo_dir)
    else:
        console.log(f"reusing checkout: {repo_dir}")
        git_ops.clean(repo_dir)

    # 1. base
    console.log(f"checkout base {spec.base_commit[:10]}")
    git_ops.checkout(repo_dir, spec.base_commit)

    # 2. test_patch (harness-injected) — must succeed
    try:
        git_ops.apply_diff(repo_dir, spec.test_patch)
    except git_ops.GitError as e:
        result.error = f"test_patch apply failed: {e}"
        return result

    # 3. agent_patch — empty patch = "no-op" submission (score 0, not error).
    if spec.agent_patch.strip():
        try:
            git_ops.apply_diff(repo_dir, spec.agent_patch)
        except git_ops.GitError as e:
            result.error = f"agent_patch apply failed: {e}"
            return result
    else:
        console.log("agent_patch is empty — skipping apply, scoring as-is")

    # 4. postgres + runner
    pg_name = f"pbench-db-score-{spec.instance_id}"[:60]
    network_name: str | None = None
    pg: postgres.PostgresHandle | None = None
    pg_env: dict[str, str] = {}
    if source.pg_required:
        postgres.stop(pg_name)
        if mode == "docker":
            network_name = f"pbench-net-score-{spec.instance_id}"[:60]
            postgres.create_network(network_name)
        try:
            pg = postgres.start(
                pg_name,
                network=network_name,
                user=source.pg_defaults.get("user", "postgres"),
                password=source.pg_defaults.get("password", "changethis"),
                db=source.pg_defaults.get("db", "app"),
            )
        except postgres.PostgresError as e:
            result.error = f"postgres start failed: {e}"
            return result
        pg_env = pg.env_for(env_map=source.pg_env_map, from_container=(mode == "docker"))

    runner = backend_runner.make(
        mode,
        image=source.backend_image,
        network=network_name,
        out_mount=out_dir,
        container_prefix=f"pbench-s-{spec.instance_id}"[:50],
    )
    backend_dir = repo_dir / source.backend_dir if source.backend_dir else repo_dir

    try:
        # 5. prestart — use extras available at the (base + agent_patch) commit
        eff_extras = effective_uv_extras(source, repo_dir)
        console.log("running prestart")
        rc, so, se = runner.run_prestart(
            workspace_root=repo_dir, backend_dir=backend_dir,
            prestart_steps=source.prestart_steps,
            uv_extras=eff_extras,
            env_overrides=pg_env,
        )
        (out_dir / "agent.prestart.log").write_text(so + "\n---stderr---\n" + se)
        if rc != 0:
            result.error = f"prestart failed (rc={rc}). See agent.prestart.log"
            return result

        # 6. pytest
        console.log("running agent pytest")
        t0 = time.monotonic()
        run = runner.run_pytest(
            workspace_root=repo_dir, backend_dir=backend_dir,
            junit_path=out_dir / "agent.junit.xml",
            pytest_args=spec.pytest_args,
            pytest_extra_args=source.pytest_extra_args,
            uv_extras=eff_extras,
            env_overrides=pg_env,
        )
        result.phase_duration_s = time.monotonic() - t0
        result.phase_returncode = run.returncode
        (out_dir / "agent.stdout.log").write_text(run.stdout)
        (out_dir / "agent.stderr.log").write_text(run.stderr)

        if not run.junit_path.exists():
            result.error = "pytest produced no JUnit xml (likely crashed during collection)"
            return result

        outcomes = junit.parse(run.junit_path)
        passing_tests = junit.passing(outcomes)

        # 7. compare
        f2p_set = set(spec.fail_to_pass)
        p2p_set = set(spec.pass_to_pass)
        result.fail_to_pass_passed = sorted(f2p_set & passing_tests)
        result.fail_to_pass_missing = sorted(f2p_set - passing_tests)
        result.pass_to_pass_passed = sorted(p2p_set & passing_tests)
        result.pass_to_pass_regressed = sorted(p2p_set - passing_tests)

        result.score = int(
            not result.fail_to_pass_missing and not result.pass_to_pass_regressed
        )
    finally:
        if pg:
            postgres.stop(pg_name)
        if network_name:
            postgres.remove_network(network_name)

    (out_dir / "score_summary.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True)
    )
    console.log(
        f"score={result.score}  "
        f"F2P {len(result.fail_to_pass_passed)}/{len(spec.fail_to_pass)}  "
        f"P2P {len(result.pass_to_pass_passed)}/{len(spec.pass_to_pass)}"
    )
    return result


# ---------------------------------------------------------------------------
# Frontend variant — Playwright instead of pytest, same scoring contract.
# ---------------------------------------------------------------------------


def score_patch_frontend(
    spec: ScoreSpec,
    *,
    source: SourceConfig,
    work_root: Path,
    console: Console | None = None,
) -> ScoreResult:
    """Score an agent patch against a frontend (Playwright) PR.

    Mirrors `score_patch` but dispatches to the source-driven frontend runner
    (compose / playwright_direct). FAIL_TO_PASS / PASS_TO_PASS are Playwright
    test titles (see playwright_report.parse).
    """
    from . import frontend_direct_runner, frontend_runner, playwright_report

    console = console or Console()
    work_root.mkdir(parents=True, exist_ok=True)
    repo_dir = work_root / "repo"
    out_dir = work_root / "out_score_frontend"
    out_dir.mkdir(exist_ok=True)

    # Defensive: nuke stale runner output before this run starts. Without
    # this, a failed docker run that doesn't produce a new playwright.json
    # would leave the *previous* run's report on disk, and parse() would
    # silently return the previous run's outcomes — i.e. silently rescue
    # a broken run with stale data and produce an entirely wrong score.
    for f in ("playwright.json", "playwright.exitcode",
              "playwright.stdout", "playwright.stderr"):
        p = out_dir / f
        if p.exists():
            p.unlink()

    result = ScoreResult(
        instance_id=spec.instance_id, score=0,
        mode=source.frontend_runner_kind or "compose",
        source=source.name,
    )

    if not repo_dir.exists():
        console.log(f"cloning {spec.repo_url} → {repo_dir}")
        git_ops.clone(spec.repo_url, repo_dir)
    else:
        console.log(f"reusing checkout: {repo_dir}")
        git_ops.clean(repo_dir)

    console.log(f"checkout base {spec.base_commit[:10]}")
    git_ops.checkout(repo_dir, spec.base_commit)

    if spec.test_patch:
        try:
            git_ops.apply_diff(repo_dir, spec.test_patch)
        except git_ops.GitError as e:
            result.error = f"test_patch apply failed: {e}"
            return result

    if spec.agent_patch.strip():
        try:
            git_ops.apply_diff(repo_dir, spec.agent_patch)
        except git_ops.GitError as e:
            result.error = f"agent_patch apply failed: {e}"
            return result

    runner_kind = source.frontend_runner_kind or "compose"
    project = f"pbench-fe-score-{spec.instance_id}"[:50]

    # Source-driven scoping: extract spec-file paths from test_patch and
    # pass them as Playwright positional args so we run only the specs the
    # PR actually touched (typically a handful) instead of the source's
    # full e2e suite (bruno: ~486 specs, ~38min). This is the same scope
    # the extract phase used to compute F2P/P2P, so the comparison stays
    # consistent.
    import re as _re
    added_specs = _re.findall(r"^\+\+\+ b/(\S+)", spec.test_patch, _re.MULTILINE)
    fe_path_re = (
        _re.compile(source.frontend_test_path_re)
        if source.frontend_test_path_re else None
    )
    strip = source.frontend_test_diff_strip_prefix or ""
    scoped = sorted({
        (p[len(strip):] if strip and p.startswith(strip) else p)
        for p in added_specs
        if fe_path_re and fe_path_re.match(p)
    })
    if scoped:
        console.log(f"scoped to {len(scoped)} spec(s): {scoped[:3]}{'...' if len(scoped)>3 else ''}")

    try:
        if runner_kind == "playwright_direct":
            run, outcomes = frontend_direct_runner.run_phase_direct(
                repo_dir=repo_dir, source=source,
                instance_id=f"score-{spec.instance_id}",
                out_dir=out_dir,
                extra_args=scoped or None,
            )
        elif runner_kind == "compose":
            run, outcomes = frontend_runner.run_phase(
                repo_dir=repo_dir, project=project, out_dir=out_dir,
                extra_args=scoped or None,
            )
        else:
            result.error = f"unsupported frontend_runner_kind: {runner_kind!r}"
            return result
    except frontend_runner.FrontendRunnerError as e:
        result.error = f"frontend runner failed: {e}"
        return result

    result.phase_returncode = run.returncode
    (out_dir / "agent.runner.stdout.log").write_text(run.stdout)
    (out_dir / "agent.runner.stderr.log").write_text(run.stderr)

    if not run.json_present:
        result.error = "Playwright produced no JSON report"
        return result

    passing_tests = playwright_report.passing(outcomes)
    f2p_set = set(spec.fail_to_pass)
    p2p_set = set(spec.pass_to_pass)
    result.fail_to_pass_passed = sorted(f2p_set & passing_tests)
    result.fail_to_pass_missing = sorted(f2p_set - passing_tests)
    result.pass_to_pass_passed = sorted(p2p_set & passing_tests)
    result.pass_to_pass_regressed = sorted(p2p_set - passing_tests)

    result.score = int(
        not result.fail_to_pass_missing and not result.pass_to_pass_regressed
    )

    (out_dir / "score_summary.json").write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True)
    )
    console.log(
        f"score={result.score}  F2P {len(result.fail_to_pass_passed)}/{len(spec.fail_to_pass)}  "
        f"P2P {len(result.pass_to_pass_passed)}/{len(spec.pass_to_pass)}"
    )
    return result
