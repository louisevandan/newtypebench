"""Frontend Playwright runner — direct npm + playwright invocation (no compose).

For sources whose Playwright config uses `webServer` to auto-spawn dev
servers (e.g. bruno's `npm run dev:web` + `bruno-tests` mock server on
localhost:3000/8081). No docker-compose orchestration is required; we run
`npm install` + workspace pre-builds + `npx playwright test` inside a single
Playwright base image and capture the JSON report via the
`PLAYWRIGHT_JSON_OUTPUT_NAME` env var.

Per-PR isolation: container name = `pbench-fe-direct-<instance_id>`.

Counterpart of harness.frontend_runner (which drives a compose stack); both
expose `run_phase{,_direct}()` returning the same (PlaywrightRun, outcomes)
tuple shape so harness.frontend_extract can dispatch generically.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from . import playwright_report
from .frontend_runner import FrontendRunnerError, PlaywrightRun
from .sources import SourceConfig


def teardown(container: str) -> None:
    """Idempotent: remove a prior container with this name if it still exists."""
    subprocess.run(
        ["docker", "rm", "-f", container],
        capture_output=True, text=True, timeout=30,
    )


def _build_container_cmd(source: SourceConfig, extra_args: list[str] | None) -> str:
    """Pipeline: install → workspace pre-builds → playwright test → record exit.

    We deliberately don't `set -e` around the playwright invocation itself —
    we want to capture its exitcode regardless and let the diff downstream
    classify the run, rather than aborting on the first failing spec.
    """
    parts: list[str] = ["set -e", "cd /work"]
    parts.append(shlex.join(source.frontend_install_cmd))
    for step in source.frontend_pre_test_cmd:
        parts.append(shlex.join(step))

    test_cmd = list(source.frontend_test_cmd) + list(extra_args or [])
    parts.append("set +e")
    parts.append(
        f"{shlex.join(test_cmd)} "
        f"> /output/playwright.stdout 2> /output/playwright.stderr"
    )
    parts.append("echo $? > /output/playwright.exitcode")
    # Exit 0 so docker run's rc reflects the wrapper, not playwright. The
    # caller reads /output/playwright.exitcode for the real playwright rc.
    parts.append("exit 0")
    return "; ".join(parts)


def run_phase_direct(
    *,
    repo_dir: Path,
    source: SourceConfig,
    instance_id: str,
    out_dir: Path,
    extra_args: list[str] | None = None,
    timeout: float = 3600.0,
) -> tuple[PlaywrightRun, dict[str, playwright_report.Outcome]]:
    """End-to-end one phase: docker run install + pre-build + playwright test."""
    if not source.frontend_docker_image:
        raise FrontendRunnerError(
            f"source {source.short_name!r} missing frontend_docker_image"
        )
    if not source.frontend_install_cmd or not source.frontend_test_cmd:
        raise FrontendRunnerError(
            f"source {source.short_name!r} missing frontend_install_cmd / "
            f"frontend_test_cmd"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    container = f"pbench-fe-direct-{instance_id}"[:60]
    teardown(container)

    container_cmd = _build_container_cmd(source, extra_args)

    # Use the path as-is when absolute (no resolve()) — macOS Docker Desktop
    # treats /tmp differently from /private/tmp under file-sharing policies;
    # frontend_runner.py learned this the hard way.
    repo_abs = repo_dir if repo_dir.is_absolute() else repo_dir.resolve()
    out_abs = out_dir if out_dir.is_absolute() else out_dir.resolve()

    docker_cmd = [
        "docker", "run", "--rm",
        "--name", container,
        "-v", f"{repo_abs}:/work",
        "-v", f"{out_abs}:/output",
        "-w", "/work",
        # PLAYWRIGHT_JSON_OUTPUT_NAME directs the json reporter at this path
        # regardless of the source's playwright.config's own `outputFile`.
        "-e", "PLAYWRIGHT_JSON_OUTPUT_NAME=/output/playwright.json",
        # CI=1 makes bruno-style configs: forbid .only, retry 2x, don't reuse
        # existing servers, drop interactive worker count. We want all of that.
        "-e", "CI=1",
        source.frontend_docker_image,
        "bash", "-c", container_cmd,
    ]

    try:
        r = subprocess.run(
            docker_cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        teardown(container)
        raise FrontendRunnerError(
            f"playwright_direct timed out after {timeout:.0f}s"
        ) from e

    json_path = out_dir / "playwright.json"
    run = PlaywrightRun(
        returncode=r.returncode,
        stdout=r.stdout,
        stderr=r.stderr,
        json_path=json_path,
        json_present=json_path.exists() and json_path.stat().st_size > 0,
    )

    if not run.json_present:
        return run, {}
    outcomes = playwright_report.parse(json_path)
    return run, outcomes
