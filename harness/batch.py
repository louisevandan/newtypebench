"""Batch-extract FAIL_TO_PASS / PASS_TO_PASS over a candidate pool.

Sequential, single-shared-checkout: clone the source repo once into
`<work_root>/_shared_repo/` and reuse it for every PR. extract.py's clean +
checkout cycle resets state between runs.

Output:
  <work_root>/<instance_id>/out/summary.json   (per-PR detail)
  <report_path>                                  (one JSON per PR, batch view)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from . import extract as ex
from . import frontend_extract as fe
from . import git_ops
from .sources import SourceConfig


@dataclass
class BatchRow:
    pr: int
    instance_id: str
    title: str
    f2p: int
    p2p: int
    fallback: str | None
    status: str          # "exact" | "fallback" | "test_only" | "no_signal" | "error"
    error: str | None
    duration_s: float


def _classify_backend(result: ex.ExtractResult) -> str:
    if result.error:
        return "error"
    if result.fallback_used:
        return "fallback"
    if result.fail_to_pass:
        return "exact"
    if result.pass_to_pass:
        return "test_only"
    return "no_signal"


def _classify_frontend(result: fe.FrontendExtractResult) -> str:
    if result.error:
        return "error"
    if result.fail_to_pass:
        return "exact"
    if result.pass_to_pass:
        return "test_only"
    return "no_signal"


def _scope_pytest(test_patch: str, source: SourceConfig) -> list[str]:
    """Source-aware: use the SourceConfig regex + strip-prefix to scope pytest."""
    added_paths = re.findall(r"^\+\+\+ b/(\S+)", test_patch, re.MULTILINE)
    path_re = re.compile(source.backend_test_path_re)
    prefix = source.backend_test_path_strip_prefix
    return sorted({
        (p[len(prefix):] if prefix and p.startswith(prefix) else p)
        for p in added_paths if path_re.match(p)
    })


def _scope_playwright(test_patch: str) -> list[str]:
    """Restrict Playwright to changed spec files (relative to frontend/)."""
    hits = re.findall(
        r"^\+\+\+ b/(frontend/(?:tests/[^\s]+|.+?\.(?:spec|test)\.[tj]sx?))",
        test_patch,
        re.MULTILINE,
    )
    return sorted({p.replace("frontend/", "", 1) for p in hits})


def _signal_for_kind(r: dict, kind: str) -> int:
    s = r.get("signals") or {}
    if kind == "backend":
        return s.get("backend_tests", 0)
    return s.get("frontend_tests", 0)


def _load_existing_summary(work_dir: Path, kind: str) -> dict | None:
    """Return parsed summary.json if a prior extract of this kind finished cleanly.

    backend extract writes <work_dir>/out/summary.json
    frontend extract writes <work_dir>/frontend_out/summary.json

    Without the kind discriminator, a backend summary would be (incorrectly)
    reused as a frontend batch row.
    """
    sub = "out" if kind == "backend" else "frontend_out"
    p = work_dir / sub / "summary.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def batch_extract(
    *,
    candidates_path: Path,
    work_root: Path,
    report_path: Path,
    source: SourceConfig,
    top_n: int | None,
    mode: str,
    kind: str = "backend",
    skip_existing: bool = True,
    console: Console | None = None,
) -> list[BatchRow]:
    console = console or Console()
    repo_url = source.repo_url
    owner, name = source.name.split("/", 1)
    instance_prefix = f"{owner.replace('-','_')}__{name}-"

    rows = []
    with candidates_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # Drop PRs without any test signal of the requested kind — running the
    # extractor on a PR that doesn't touch the relevant tests is guaranteed
    # to produce F2P=0 noise.
    rows = [r for r in rows if _signal_for_kind(r, kind) > 0]
    if top_n:
        rows = rows[:top_n]

    work_root.mkdir(parents=True, exist_ok=True)
    shared_repo = work_root / f"_shared_repo_{source.short_name}"
    if not shared_repo.exists():
        console.log(f"first-time clone of shared repo → {shared_repo}")
        git_ops.clone(repo_url, shared_repo)

    results: list[BatchRow] = []
    quiet_console = Console(quiet=True)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("batch-extract", total=len(rows))
        for r in rows:
            pr = r["pr"]
            number = pr["number"]
            instance_id = f"{instance_prefix}{number}"
            progress.update(task, advance=1, description=f"PR #{number}")
            t0 = time.monotonic()

            head_commit = ((pr.get("mergeCommit") or {}).get("oid")) or ""
            if not head_commit:
                results.append(BatchRow(
                    pr=number, instance_id=instance_id,
                    title=pr.get("title", ""), f2p=0, p2p=0, fallback=None,
                    status="error", error="no mergeCommit.oid",
                    duration_s=time.monotonic() - t0,
                ))
                continue

            try:
                git_ops.clean(shared_repo)
                git_ops.checkout(shared_repo, head_commit)
                base_commit = git_ops.rev_parse(shared_repo, f"{head_commit}^")
                if kind == "backend":
                    # Source-specific test glob.
                    test_paths_glob = (
                        ["backend/tests/**", "backend/app/tests/**"]
                        if source.backend_dir == "backend"
                        else (
                            ["server/tests/**"] if source.backend_dir == "server"
                            else ["tests/**"]
                        )
                    )
                    test_patch = git_ops.diff(
                        shared_repo, base_commit, head_commit, paths=test_paths_glob,
                    )
                else:
                    test_patch = git_ops.diff(
                        shared_repo, base_commit, head_commit,
                        paths=["frontend/tests/**", "frontend/**/*.spec.ts",
                               "frontend/**/*.spec.tsx",
                               "frontend/**/*.test.ts", "frontend/**/*.test.tsx"],
                    )
            except git_ops.GitError as e:
                results.append(BatchRow(
                    pr=number, instance_id=instance_id,
                    title=pr.get("title", ""), f2p=0, p2p=0, fallback=None,
                    status="error", error=f"git: {e}",
                    duration_s=time.monotonic() - t0,
                ))
                continue

            work_dir = work_root / instance_id
            work_dir.mkdir(exist_ok=True)
            patch_filename = "test_patch.diff" if kind == "backend" else "frontend_test_patch.diff"
            (work_dir / patch_filename).write_text(test_patch)

            # Incremental skip: if a prior summary.json exists for this PR
            # AND for this kind (backend vs frontend writes to different dirs),
            # reuse it instead of re-running the (expensive) extract.
            if skip_existing:
                cached = _load_existing_summary(work_dir, kind)
                if cached:
                    f2p = list(cached.get("fail_to_pass") or [])
                    p2p = list(cached.get("pass_to_pass") or [])
                    fb = cached.get("fallback_used")
                    err = cached.get("error")
                    if err:
                        status = "error"
                    elif fb:
                        status = "fallback"
                    elif f2p:
                        status = "exact"
                    elif p2p:
                        status = "test_only"
                    else:
                        status = "no_signal"
                    results.append(BatchRow(
                        pr=number, instance_id=instance_id,
                        title=pr.get("title", ""),
                        f2p=len(f2p), p2p=len(p2p),
                        fallback=fb, status=status, error=err,
                        duration_s=time.monotonic() - t0,
                    ))
                    continue

            try:
                if kind == "backend":
                    scoped = _scope_pytest(test_patch, source) if test_patch else None
                    spec_be = ex.ExtractSpec(
                        instance_id=instance_id,
                        repo_url=repo_url,
                        base_commit=base_commit,
                        head_commit=head_commit,
                        test_patch=test_patch or None,
                        pytest_args=scoped or None,
                    )
                    result_be = ex.extract(
                        spec_be, source=source, work_root=work_dir, mode=mode,
                        console=quiet_console, repo_dir=shared_repo,
                    )
                    results.append(BatchRow(
                        pr=number, instance_id=instance_id,
                        title=pr.get("title", ""),
                        f2p=len(result_be.fail_to_pass),
                        p2p=len(result_be.pass_to_pass),
                        fallback=result_be.fallback_used,
                        status=_classify_backend(result_be),
                        error=result_be.error,
                        duration_s=time.monotonic() - t0,
                    ))
                else:
                    scoped = _scope_playwright(test_patch) if test_patch else None
                    spec_fe = fe.FrontendExtractSpec(
                        instance_id=instance_id,
                        repo_url=repo_url,
                        base_commit=base_commit,
                        head_commit=head_commit,
                        test_patch=test_patch or None,
                        playwright_args=scoped or None,
                        source=source,
                    )
                    result_fe = fe.extract_frontend(
                        spec_fe, work_root=work_dir,
                        console=quiet_console, repo_dir=shared_repo,
                    )
                    results.append(BatchRow(
                        pr=number, instance_id=instance_id,
                        title=pr.get("title", ""),
                        f2p=len(result_fe.fail_to_pass),
                        p2p=len(result_fe.pass_to_pass),
                        fallback=None,
                        status=_classify_frontend(result_fe),
                        error=result_fe.error,
                        duration_s=time.monotonic() - t0,
                    ))
            except Exception as e:  # noqa: BLE001 — never let one PR kill the batch
                results.append(BatchRow(
                    pr=number, instance_id=instance_id,
                    title=pr.get("title", ""), f2p=0, p2p=0, fallback=None,
                    status="error", error=f"crashed: {type(e).__name__}: {e}",
                    duration_s=time.monotonic() - t0,
                ))
                continue

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w") as f:
        for row in results:
            f.write(json.dumps(asdict(row), ensure_ascii=False, sort_keys=True))
            f.write("\n")
    return results


def render_summary(results: list[BatchRow], console: Console) -> None:
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    total = len(results)
    usable = by_status.get("exact", 0) + by_status.get("fallback", 0)

    table = Table(title=f"Batch extract — {total} PRs ({usable} usable, {usable * 100 // max(total, 1)}%)")
    table.add_column("PR", justify="right")
    table.add_column("status")
    table.add_column("F2P", justify="right")
    table.add_column("P2P", justify="right")
    table.add_column("dur(s)", justify="right")
    table.add_column("title", overflow="fold")
    table.add_column("error/note", overflow="fold")

    status_color = {
        "exact": "green", "fallback": "yellow", "test_only": "cyan",
        "no_signal": "white", "error": "red",
    }
    for r in sorted(results, key=lambda x: (x.status != "exact", x.status != "fallback", -x.f2p)):
        col = status_color.get(r.status, "white")
        table.add_row(
            str(r.pr),
            f"[{col}]{r.status}[/{col}]",
            str(r.f2p),
            str(r.p2p),
            f"{r.duration_s:.0f}",
            r.title[:60],
            (r.error or "")[:60],
        )
    console.print(table)

    summary = Table(title="Status breakdown")
    summary.add_column("status")
    summary.add_column("count", justify="right")
    summary.add_column("share", justify="right")
    for status in ("exact", "fallback", "test_only", "no_signal", "error"):
        c = by_status.get(status, 0)
        summary.add_row(status, str(c), f"{c * 100 // max(total, 1)}%")
    console.print(summary)
