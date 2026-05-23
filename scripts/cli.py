"""`pbench` — PrototypeBench pipeline CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .build_instance import build_from_candidates
from .crawl_prs import crawl
from .filter_prs import filter_prs, load_jsonl
from .validate import validate_file

# Harness (Phase 2) — imported lazily inside commands to keep `pbench --help`
# fast even when docker-dependent paths aren't ready.

app = typer.Typer(
    name="pbench",
    help="PrototypeBench task curation pipeline.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

DEFAULT_REPO = "fastapi/full-stack-fastapi-template"
DEFAULT_RAW_DIR = Path("raw")


def _raw_path(source: str | None, fname: str) -> Path:
    """Per-source raw artifact path: raw/<source>/<fname> if source given, else raw/<fname>."""
    if source:
        return DEFAULT_RAW_DIR / source / fname
    return DEFAULT_RAW_DIR / fname


@app.command(name="crawl")
def crawl_cmd(
    source: str = typer.Option(
        "fastapi-template", "--source", help="Source short name (registered config)."
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output JSONL. Default: raw/<source>/prs.jsonl",
    ),
    limit: int = typer.Option(1000, "--limit", help="Max merged PRs to pull."),
    no_resume: bool = typer.Option(False, "--no-resume", help="Re-enrich from scratch."),
) -> None:
    """Phase 1 step 1 — crawl merged PRs from a source repo into raw/<source>/prs.jsonl."""
    from harness.sources import get as get_source
    src = get_source(source)
    out = output or _raw_path(src.short_name, "prs.jsonl")
    count = crawl(src.name, out, limit=limit, resume=not no_resume, console=console)
    console.print(f"[bold green]done[/bold green]: {count} PRs in {out}")


@app.command(name="filter")
def filter_cmd(
    source: str = typer.Option(
        "fastapi-template", "--source", help="Source short name."
    ),
    input: Path = typer.Option(None, "--input", "-i", help="Crawled PRs JSONL (default: raw/<source>/prs.jsonl)."),
    candidates: Path = typer.Option(None, "--candidates", help="Default: raw/<source>/candidates.jsonl."),
    rejected: Path = typer.Option(None, "--rejected", help="Default: raw/<source>/rejected.jsonl."),
) -> None:
    """Phase 1 step 2 — score and filter crawled PRs into a candidate pool."""
    from harness.sources import get as get_source
    src = get_source(source)
    inp = input or _raw_path(src.short_name, "prs.jsonl")
    cand = candidates or _raw_path(src.short_name, "candidates.jsonl")
    rej = rejected or _raw_path(src.short_name, "rejected.jsonl")
    n_ok, n_drop = filter_prs(inp, cand, rej, source=src)
    console.print(f"[green]accepted[/green] {n_ok} → {cand}")
    console.print(f"[yellow]rejected[/yellow] {n_drop} → {rej}")


@app.command(name="top")
def top_cmd(
    source: str = typer.Option(
        "fastapi-template", "--source", help="Source short name."
    ),
    candidates: Path = typer.Option(None, "--candidates", help="Default: raw/<source>/candidates.jsonl."),
    n: int = typer.Option(20, "--n", help="Number of candidates to show."),
    kind: str = typer.Option(
        "any", "--kind",
        help="Filter by test signal: 'backend' | 'frontend' | 'fullstack' | 'any'.",
    ),
) -> None:
    """Quick look: print top-N candidates by score, optionally filtered by kind."""
    from harness.sources import get as get_source
    src = get_source(source)
    cand = candidates or _raw_path(src.short_name, "candidates.jsonl")
    rows = load_jsonl(cand)

    def _matches(r: dict) -> bool:
        s = r.get("signals") or {}
        be, fe = s.get("backend_tests", 0), s.get("frontend_tests", 0)
        if kind == "backend":
            return be > 0
        if kind == "frontend":
            return fe > 0
        if kind == "fullstack":
            return be > 0 and fe > 0
        return True

    rows = [r for r in rows if _matches(r)][:n]
    table = Table(title=f"Top {len(rows)} candidates (kind={kind})")
    table.add_column("#", justify="right")
    table.add_column("score", justify="right")
    table.add_column("BE", justify="right")
    table.add_column("FE", justify="right")
    table.add_column("title", overflow="fold")
    table.add_column("reasons", overflow="fold")
    for r in rows:
        pr = r["pr"]
        s = r.get("signals") or {}
        table.add_row(
            str(pr["number"]),
            str(r["score"]),
            str(s.get("backend_tests", 0)),
            str(s.get("frontend_tests", 0)),
            (pr.get("title") or "")[:80],
            ", ".join(r["reasons"]),
        )
    console.print(table)


@app.command(name="stats")
def stats_cmd(
    input: Path = typer.Option(
        DEFAULT_RAW_DIR / "prs.jsonl", "--input", "-i", help="Crawled PRs JSONL."
    ),
) -> None:
    """Quick summary over crawled PRs — label distribution, size histogram."""
    prs = load_jsonl(input)
    if not prs:
        console.print("[yellow]no PRs loaded[/yellow]")
        return
    label_counts: dict[str, int] = {}
    for pr in prs:
        for l in pr.get("labels") or []:
            if isinstance(l, dict):
                name = l.get("name", "")
                label_counts[name] = label_counts.get(name, 0) + 1
    by_label = sorted(label_counts.items(), key=lambda kv: -kv[1])
    table = Table(title=f"Labels across {len(prs)} PRs")
    table.add_column("label")
    table.add_column("count", justify="right")
    for name, c in by_label[:25]:
        table.add_row(name, str(c))
    console.print(table)


@app.command(name="draft")
def draft_cmd(
    candidates: Path = typer.Option(
        DEFAULT_RAW_DIR / "candidates.jsonl", "--candidates", help="Candidate pool JSONL."
    ),
    output: Path = typer.Option(
        Path("tasks/drafts.jsonl"), "--output", "-o", help="Draft instances JSONL."
    ),
    top: int = typer.Option(10, "--top", help="How many top candidates to draft."),
) -> None:
    """Phase 1 step 3 — generate schema-shaped drafts from top-N candidates.

    Drafts contain <<TODO:...>> placeholders for fields that need test execution
    or curator judgment. Fill them in, then run `pbench validate`.
    """
    n = build_from_candidates(candidates, output, top_n=top)
    console.print(f"[green]wrote {n} draft(s)[/green] → {output}")
    console.print("Fill in <<TODO:...>> markers, then run `pbench validate`.")


@app.command(name="build-from-extract")
def build_from_extract_cmd(
    source: str = typer.Option("fastapi-template", "--source", help="Source short name."),
    report: Path = typer.Option(None, "--report", help="Default: raw/<source>/extract_report.jsonl."),
    prs: Path = typer.Option(None, "--prs", help="Default: raw/<source>/prs.jsonl."),
    work_root: Path = typer.Option(
        Path("/tmp/pbench"), "--work-root", help="Same scratch dir used by batch-extract."
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Default: tasks/instances.<source>.jsonl."
    ),
    statuses: str = typer.Option(
        "exact,fallback", "--statuses",
        help="Comma-separated extract statuses to convert.",
    ),
    cutoff: str = typer.Option(
        "2026-01-01", "--cutoff", help="ISO date for contamination_tier split."
    ),
    kind: str = typer.Option(
        "backend", "--kind",
        help="'backend' or 'frontend' — selects extract artifact paths + F2P bucket.",
    ),
) -> None:
    """Phase 1 step 4 — convert usable batch-extract results into tasks/instances.jsonl.

    Per-PR build pulls fields from three sources:
      - PR metadata    (raw/prs.jsonl)            → title, author, labels, body
      - Extract summary (work_root/.../summary.json) → F2P, P2P, base/head commits
      - Shared repo    (work_root/_shared_repo)    → patch, test_patch_*, lock SHAs
    """
    from harness.sources import get as get_source
    from scripts.build_from_extract import build_from_extract as bfe

    src = get_source(source)
    # Default report path is kind-aware so callers can omit --report when they
    # ran `batch-extract --kind frontend` (which writes to *.frontend.jsonl).
    default_report_name = (
        "extract_report.frontend.jsonl" if kind == "frontend" else "extract_report.jsonl"
    )
    rep = report or _raw_path(src.short_name, default_report_name)
    pr_path = prs or _raw_path(src.short_name, "prs.jsonl")
    out = output or Path(f"tasks/instances.{src.short_name}.jsonl")

    repo_dir = work_root / f"_shared_repo_{src.short_name}"
    if not repo_dir.exists():
        # fall back to the legacy per-source location used previously
        legacy = work_root / "_shared_repo"
        if legacy.exists() and src.short_name == "fastapi-template":
            repo_dir = legacy
        else:
            raise typer.BadParameter(
                f"shared repo not found at {repo_dir} — run "
                f"`pbench batch-extract --source {source}` first."
            )
    status_set = {s.strip() for s in statuses.split(",") if s.strip()}
    n_built, n_skipped = bfe(
        report_path=rep, prs_path=pr_path, repo_dir=repo_dir,
        work_root=work_root, output=out,
        statuses=status_set, cutoff=cutoff, repo=src.name, source=src,
        kind=kind,
    )
    console.print(f"[green]built[/green] {n_built} instance(s) → {out}")
    console.print(f"[yellow]skipped[/yellow] {n_skipped} (status not in {sorted(status_set)} or missing artifacts)")
    console.print(f"\nNext: [bold]pbench validate -p {out}[/bold]")


@app.command(name="validate")
def validate_cmd(
    path: Path = typer.Option(
        Path("tasks/instances.jsonl"), "--path", "-p", help="Instances JSONL to validate."
    ),
) -> None:
    """Phase 1 step 5 — validate instances.jsonl against the task schema."""
    if not path.exists():
        console.print(f"[red]not found:[/red] {path}")
        raise typer.Exit(code=2)
    n, errors = validate_file(path)
    if not errors:
        console.print(f"[green]OK[/green] — {n} instance(s) valid")
        return
    for line_no, iid, msg in errors[:50]:
        console.print(f"[red]L{line_no}[/red] {iid}: {msg}")
    if len(errors) > 50:
        console.print(f"... and {len(errors) - 50} more")
    console.print(f"[red]{len(errors)} error(s) across {n} instance(s)[/red]")
    raise typer.Exit(code=1)


def _find_pr(prs_path: Path, pr_number: int) -> dict:
    for line in prs_path.open():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("number") == pr_number:
            return row
    raise typer.BadParameter(f"PR #{pr_number} not found in {prs_path}")


def _fetch_pr_head_commit(repo: str, pr: int) -> str:
    """Fall back to gh API if the PR isn't in our crawled list."""
    import subprocess
    r = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo, "--json", "mergeCommit"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise typer.BadParameter(f"gh pr view {pr}: {r.stderr.strip()}")
    data = json.loads(r.stdout)
    head = (data.get("mergeCommit") or {}).get("oid") or ""
    if not head:
        raise typer.BadParameter(f"PR #{pr} has no mergeCommit.oid")
    return head


@app.command(name="extract")
def extract_cmd(
    pr: int = typer.Option(..., "--pr", help="Merged PR number from the source repo."),
    source: str = typer.Option(
        "fastapi-template", "--source",
        help="Source short name (see `harness/sources/`).",
    ),
    prs: Path = typer.Option(
        DEFAULT_RAW_DIR / "prs.jsonl", "--prs", help="Crawled PRs JSONL (optional)."
    ),
    work_root: Path = typer.Option(
        Path("/tmp/pbench"), "--work-root", help="Scratch dir for checkouts/outputs."
    ),
    pytest_args: str = typer.Option(
        "", "--pytest-args",
        help="Extra pytest args, space-separated. If empty, auto-scoped from test_patch.",
    ),
    mode: str = typer.Option(
        "docker", "--mode", help="Execution mode: 'docker' (reproducible) or 'local' (host uv)."
    ),
) -> None:
    """Phase 2 — extract FAIL_TO_PASS / PASS_TO_PASS for a single PR (backend)."""
    from harness import extract as ex
    from harness import git_ops
    from harness.sources import get as get_source

    src = get_source(source)
    repo_url = src.repo_url

    # PR head_commit lookup: prefer crawled jsonl, fall back to gh.
    head_commit: str | None = None
    if prs.exists():
        try:
            row = _find_pr(prs, pr)
            head_commit = ((row.get("mergeCommit") or {}).get("oid")) or None
        except typer.BadParameter:
            head_commit = None
    if not head_commit:
        console.log(f"PR #{pr} not in {prs}; querying gh")
        head_commit = _fetch_pr_head_commit(src.name, pr)

    owner, name = src.name.split("/", 1)
    instance_id = f"{owner.replace('-','_')}__{name}-{pr}"
    work_dir = work_root / instance_id
    work_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = work_dir / "repo"

    if not repo_dir.exists():
        console.log(f"cloning {repo_url} → {repo_dir}")
        git_ops.clone(repo_url, repo_dir)
    else:
        console.log(f"reusing checkout: {repo_dir}")

    base_commit = git_ops.rev_parse(repo_dir, f"{head_commit}^")
    console.log(f"source={src.short_name} base={base_commit[:10]} head={head_commit[:10]}")

    # Derive the test-only patch from the PR range.
    test_patch = git_ops.diff(
        repo_dir, base_commit, head_commit,
        paths=["*test*", "*.spec.ts", "*.spec.tsx", "*.test.ts", "*.test.tsx"],
    )
    (work_dir / "test_patch.diff").write_text(test_patch)
    console.log(f"test_patch: {len(test_patch)} bytes")

    # Auto-scope pytest using the source's path regex.
    scoped = [a for a in pytest_args.split() if a]
    if not scoped and test_patch:
        # Extract +++ b/ paths from test_patch and match against source's test path regex.
        added_paths = re.findall(r"^\+\+\+ b/(\S+)", test_patch, re.MULTILINE)
        path_re = re.compile(src.backend_test_path_re)
        prefix = src.backend_test_path_strip_prefix
        rel = sorted({
            (p[len(prefix):] if prefix and p.startswith(prefix) else p)
            for p in added_paths if path_re.match(p)
        })
        if rel:
            scoped = rel
            console.log(f"auto-scoped pytest: {' '.join(rel)}")

    spec = ex.ExtractSpec(
        instance_id=instance_id,
        repo_url=repo_url,
        base_commit=base_commit,
        head_commit=head_commit,
        test_patch=test_patch or None,
        pytest_args=scoped or None,
    )
    result = ex.extract(spec, source=src, work_root=work_dir, mode=mode, console=console)

    console.print("")
    if result.error:
        console.print(f"[red]error:[/red] {result.error}")
    console.print(f"[bold]FAIL_TO_PASS[/bold]: {len(result.fail_to_pass)}")
    for t in result.fail_to_pass[:10]:
        console.print(f"  + {t}")
    if len(result.fail_to_pass) > 10:
        console.print(f"  ... and {len(result.fail_to_pass) - 10} more")
    console.print(f"[bold]PASS_TO_PASS[/bold]: {len(result.pass_to_pass)}")
    console.print(f"summary → {work_dir / 'out' / 'summary.json'}")


@app.command(name="extract-frontend")
def extract_frontend_cmd(
    pr: int = typer.Option(..., "--pr", help="Merged PR number from the source repo."),
    repo_url: str = typer.Option(
        "https://github.com/fastapi/full-stack-fastapi-template.git",
        "--repo-url",
    ),
    prs: Path = typer.Option(
        DEFAULT_RAW_DIR / "prs.jsonl", "--prs", help="Crawled PRs JSONL."
    ),
    work_root: Path = typer.Option(
        Path("/tmp/pbench"), "--work-root", help="Scratch dir; reuses _shared_repo if present."
    ),
    playwright_args: str = typer.Option(
        "", "--playwright-args",
        help="Extra args, e.g. 'tests/sign-up.spec.ts' to scope to one file.",
    ),
) -> None:
    """Phase 2 — extract FAIL_TO_PASS / PASS_TO_PASS for a PR via Playwright.

    Uses the source repo's compose stack (db + backend + prestart + mailcatcher
    + frontend + playwright). First run will build the playwright image
    (5-15 min); subsequent runs reuse the cached image.
    """
    from harness import frontend_extract as fe
    from harness import git_ops as g

    row = _find_pr(prs, pr)
    head_commit = ((row.get("mergeCommit") or {}).get("oid")) or ""
    if not head_commit:
        raise typer.BadParameter(f"PR #{pr} has no mergeCommit.oid")

    instance_id = f"fastapi__full-stack-fastapi-template-{pr}"
    work_dir = work_root / instance_id
    work_dir.mkdir(parents=True, exist_ok=True)

    shared = work_root / "_shared_repo"
    if shared.exists():
        repo_dir = shared
    else:
        repo_dir = work_dir / "repo"
        if not repo_dir.exists():
            console.log(f"cloning {repo_url} → {repo_dir}")
            g.clone(repo_url, repo_dir)

    base_commit = g.rev_parse(repo_dir, f"{head_commit}^")
    console.log(f"base={base_commit[:10]} head={head_commit[:10]}")

    # extract-frontend is currently single-source (fastapi-template). When a
    # multi-source CLI lands, route via `--source <short_name>` and look up
    # the SourceConfig here. For now, hard-code the only compose-mode source.
    from harness.sources import get as _get_source
    src = _get_source("fastapi-template")

    # Auto-scope test_patch to frontend test files only — source-driven globs
    # so this command stays compatible when extended to other sources.
    test_patch = g.diff(
        repo_dir, base_commit, head_commit,
        paths=src.frontend_test_diff_paths or [
            "frontend/tests/**", "frontend/**/*.spec.ts", "frontend/**/*.spec.tsx",
            "frontend/**/*.test.ts", "frontend/**/*.test.tsx",
        ],
    )
    (work_dir / "frontend_test_patch.diff").write_text(test_patch)
    console.log(f"frontend test_patch: {len(test_patch)} bytes")

    spec = fe.FrontendExtractSpec(
        instance_id=instance_id,
        repo_url=repo_url,
        base_commit=base_commit,
        head_commit=head_commit,
        test_patch=test_patch or None,
        playwright_args=[a for a in playwright_args.split() if a] or None,
        source=src,
    )
    result = fe.extract_frontend(spec, work_root=work_dir, console=console, repo_dir=repo_dir)

    console.print("")
    if result.error:
        console.print(f"[red]error:[/red] {result.error}")
    console.print(f"[bold]FAIL_TO_PASS[/bold]: {len(result.fail_to_pass)}")
    for t in result.fail_to_pass[:10]:
        console.print(f"  + {t}")
    if len(result.fail_to_pass) > 10:
        console.print(f"  ... and {len(result.fail_to_pass) - 10} more")
    console.print(f"[bold]PASS_TO_PASS[/bold]: {len(result.pass_to_pass)}")
    for n in result.notes:
        console.print(f"[yellow]note:[/yellow] {n}")


@app.command(name="batch-extract")
def batch_extract_cmd(
    source: str = typer.Option("fastapi-template", "--source", help="Source short name."),
    candidates: Path = typer.Option(None, "--candidates", help="Default: raw/<source>/candidates.jsonl."),
    top: int = typer.Option(0, "--top", help="Process only the top-N candidates (0 = all)."),
    report: Path = typer.Option(None, "--report", help="Default: raw/<source>/extract_report.jsonl."),
    work_root: Path = typer.Option(
        Path("/tmp/pbench"), "--work-root", help="Scratch dir; shares one repo checkout."
    ),
    mode: str = typer.Option(
        "docker", "--mode", help="Execution mode: 'docker' or 'local' (backend kind only)."
    ),
    kind: str = typer.Option(
        "backend", "--kind",
        help="'backend' (pytest) or 'frontend' (Playwright). Default: backend.",
    ),
) -> None:
    """Phase 2 — batch-run the extractor over the candidate pool.

    Produces a per-PR JSONL report and prints a status-breakdown table:
      exact     — F2P derived from base/head test diff
      fallback  — F2P recovered from test_patch parse (base collection-error)
      test_only — no F2P signal but P2P present (test-refactor PR)
      no_signal — no F2P, no P2P (likely needs manual triage)
      error     — pipeline failed; see `error` field in the report
    """
    from harness import batch
    from harness.sources import get as get_source
    src = get_source(source)
    cand = candidates or _raw_path(src.short_name, "candidates.jsonl")
    rep = report or _raw_path(src.short_name, "extract_report.jsonl")

    results = batch.batch_extract(
        candidates_path=cand,
        work_root=work_root,
        report_path=rep,
        source=src,
        top_n=top or None,
        mode=mode,
        kind=kind,
        console=console,
    )
    console.print("")
    batch.render_summary(results, console)
    console.print(f"\nreport → {rep}")


@app.command(name="score")
def score_cmd(
    pr: int = typer.Option(..., "--pr", help="Merged PR number (must have been extracted first)."),
    patch_file: Path = typer.Option(..., "--patch-file", help="Path to the agent's unified-diff patch."),
    source: str = typer.Option(
        "fastapi-template", "--source", help="Source short name."
    ),
    work_root: Path = typer.Option(
        Path("/tmp/pbench"), "--work-root", help="Must match the extract run's --work-root."
    ),
    pytest_args: str = typer.Option(
        "", "--pytest-args", help="Extra pytest args (same scope used during extract)."
    ),
    mode: str = typer.Option(
        "docker", "--mode", help="Execution mode: 'docker' or 'local'."
    ),
) -> None:
    """Phase 2 — score an agent patch against a PR's FAIL_TO_PASS/PASS_TO_PASS.

    Prereq: `pbench extract --pr <N> --source <s>` has already run.
    """
    from harness import score as sc
    from harness.sources import get as get_source

    src = get_source(source)
    owner, name = src.name.split("/", 1)
    instance_id = f"{owner.replace('-','_')}__{name}-{pr}"
    work_dir = work_root / instance_id

    summary_path = work_dir / "out" / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(
            f"No extract summary at {summary_path}. Run `pbench extract --pr {pr} --source {source}` first."
        )
    summary = json.loads(summary_path.read_text())

    test_patch_path = work_dir / "test_patch.diff"
    test_patch = test_patch_path.read_text() if test_patch_path.exists() else ""

    if not patch_file.exists():
        raise typer.BadParameter(f"patch file not found: {patch_file}")
    agent_patch = patch_file.read_text()

    spec = sc.ScoreSpec(
        instance_id=instance_id,
        repo_url=src.repo_url,
        base_commit=summary["base_commit"],
        test_patch=test_patch,
        fail_to_pass=list(summary.get("fail_to_pass") or []),
        pass_to_pass=list(summary.get("pass_to_pass") or []),
        agent_patch=agent_patch,
        pytest_args=[a for a in pytest_args.split() if a] or None,
    )
    result = sc.score_patch(spec, source=src, work_root=work_dir, mode=mode, console=console)

    console.print("")
    color = "green" if result.score == 1 else "red"
    console.print(f"[bold {color}]score = {result.score}[/bold {color}]")
    console.print(
        f"FAIL_TO_PASS: {len(result.fail_to_pass_passed)}/{len(spec.fail_to_pass)} passing"
    )
    if result.fail_to_pass_missing:
        console.print(f"  [red]missing[/red]:")
        for t in result.fail_to_pass_missing[:8]:
            console.print(f"    - {t}")
    console.print(
        f"PASS_TO_PASS: {len(result.pass_to_pass_passed)}/{len(spec.pass_to_pass)} passing"
    )
    if result.pass_to_pass_regressed:
        console.print(f"  [red]regressed[/red]:")
        for t in result.pass_to_pass_regressed[:8]:
            console.print(f"    - {t}")
    if result.error:
        console.print(f"[red]error:[/red] {result.error}")
    raise typer.Exit(code=0 if result.score == 1 else 1)


@app.command(name="agent-score")
def agent_score_cmd(
    pr: int = typer.Option(..., "--pr", help="Merged PR number (must have been extracted first)."),
    source: str = typer.Option("fastapi-template", "--source", help="Source short name."),
    backend: str = typer.Option(
        "claude", "--backend", help="Agent backend (currently: 'claude').",
    ),
    model: str = typer.Option(
        "claude-opus-4-7", "--model", help="Model identifier passed to the backend.",
    ),
    work_root: Path = typer.Option(
        Path("/tmp/pbench"), "--work-root", help="Must match the extract run's --work-root.",
    ),
    timeout: float = typer.Option(
        1800.0, "--timeout", help="Per-instance agent timeout (seconds).",
    ),
    keep_diff: Path = typer.Option(
        None, "--keep-diff",
        help="If set, write the extracted agent diff to this file before scoring.",
    ),
    mode: str = typer.Option(
        "docker", "--mode", help="Score execution mode: 'docker' or 'local'.",
    ),
) -> None:
    """Phase 3 — agent-loop scoring (mount repo → model edits → git diff → score).

    Replaces patch-submission for frontier-model evaluation. The agent gets
    a working repo + the natural-language problem_statement; the harness
    extracts the resulting non-test diff with `git diff` and feeds it to the
    existing scorer.

    Prereq: `pbench extract --pr <N> --source <s>` has already run.
    """
    from harness import agent_loop_runner as al
    from harness import score as sc
    from harness.sources import get as get_source

    src = get_source(source)
    owner, name = src.name.split("/", 1)
    instance_id = f"{owner.replace('-','_')}__{name}-{pr}"
    work_dir = work_root / instance_id

    summary_path = work_dir / "out" / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(
            f"No extract summary at {summary_path}. "
            f"Run `pbench extract --pr {pr} --source {source}` first."
        )
    summary = json.loads(summary_path.read_text())

    # The agent's working repo: prefer the batch-extract shared checkout
    # (single-source, reused across many PRs), else fall back to the
    # per-instance repo that single `extract` creates.
    from harness import git_ops as g
    candidate_repos = [
        work_root / f"_shared_repo_{src.short_name}",
        work_dir / "repo",
        work_root / "_shared_repo",   # legacy
    ]
    repo_dir = next((p for p in candidate_repos if p.exists()), None)
    if repo_dir is None:
        raise typer.BadParameter(
            f"no extract repo found. Tried: {[str(p) for p in candidate_repos]}. "
            f"Run `pbench extract --pr {pr} --source {source}` first."
        )
    console.log(f"resetting {repo_dir} to base {summary['base_commit'][:10]}")
    g.clean(repo_dir)
    g.reset_hard(repo_dir, summary["base_commit"])
    shared_repo = repo_dir

    # Find PR meta for the problem_statement (could also read from instances.jsonl).
    prs_path = _raw_path(src.short_name, "prs.jsonl")
    pr_meta = _find_pr(prs_path, pr)
    # Prefer the problem_statement we curated into instances.jsonl (it strips
    # solution-leaking sections); fall back to PR body if no instance file.
    inst_path = Path(f"tasks/instances.{src.short_name}.jsonl")
    if not inst_path.exists() and src.short_name == "fastapi-template":
        inst_path = Path("tasks/instances.jsonl")
    problem_statement = ""
    if inst_path.exists():
        for line in inst_path.read_text().splitlines():
            if not line.strip(): continue
            row = json.loads(line)
            if row.get("pr_number") == pr:
                problem_statement = row.get("problem_statement", "")
                break
    if not problem_statement:
        problem_statement = pr_meta.get("body") or pr_meta.get("title") or ""

    spec = al.AgentLoopSpec(
        instance_id=instance_id,
        repo_url=src.repo_url,
        base_commit=summary["base_commit"],
        problem_statement=problem_statement,
        source=src,
        model=model,
        timeout_s=timeout,
    )

    console.log(f"agent-loop start: backend={backend} model={model} pr={pr}")
    al_result = al.run_agent_loop(spec, backend=backend, repo_dir=shared_repo)
    console.log(
        f"agent-loop done: rc={al_result.returncode} dur={al_result.duration_s:.0f}s "
        f"diff={al_result.diff_bytes}B"
    )
    if al_result.error:
        console.print(f"[red]agent-loop error:[/red] {al_result.error}")
    for n in al_result.notes:
        console.print(f"[yellow]note:[/yellow] {n}")

    if not al_result.diff:
        console.print("[red]agent produced an empty diff — score=0[/red]")
        raise typer.Exit(code=1)

    # Optionally archive the diff for inspection / re-runs.
    diff_path = keep_diff or (work_dir / "agent_loop_diff.patch")
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(al_result.diff)
    console.log(f"agent diff → {diff_path}")

    # Now reuse the existing scorer (it re-resets, re-applies test_patch, etc.)
    test_patch_path = work_dir / "test_patch.diff"
    test_patch = test_patch_path.read_text() if test_patch_path.exists() else ""
    score_spec = sc.ScoreSpec(
        instance_id=instance_id,
        repo_url=src.repo_url,
        base_commit=summary["base_commit"],
        test_patch=test_patch,
        agent_patch=al_result.diff,
        fail_to_pass=list(summary.get("fail_to_pass") or []),
        pass_to_pass=list(summary.get("pass_to_pass") or []),
    )
    score_result = sc.score_patch(
        score_spec, source=src, work_root=work_dir, mode=mode, console=console,
    )
    console.print("")
    console.print(f"[bold]score = {score_result.score}[/bold]")
    console.print(
        f"FAIL_TO_PASS: {len(score_result.fail_to_pass_passed)}/{len(score_spec.fail_to_pass)} passing"
    )
    if score_result.fail_to_pass_failed:
        for t in score_result.fail_to_pass_failed[:8]:
            console.print(f"    - {t}")
    console.print(
        f"PASS_TO_PASS: {len(score_result.pass_to_pass_passed)}/{len(score_spec.pass_to_pass)} passing"
    )
    if score_result.error:
        console.print(f"[red]error:[/red] {score_result.error}")
    raise typer.Exit(code=0 if score_result.score == 1 else 1)


if __name__ == "__main__":
    app()
