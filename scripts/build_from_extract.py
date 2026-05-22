"""Convert batch-extract results into schema-shaped task instances.

Input:  raw/extract_report.jsonl  (batch_extract output)
        raw/prs.jsonl              (PR metadata for problem_statement etc)
        per-PR  <work_root>/<instance_id>/out/summary.json
        per-PR  <work_root>/<instance_id>/test_patch.diff
        shared repo checkout (defaults to <work_root>/_shared_repo)

Output: tasks/instances.jsonl  (one instance per usable PR)

Only PRs with status in {exact, fallback} are converted by default — those are
the ones with a non-empty FAIL_TO_PASS signal, which is the minimum the
schema requires.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from harness import git_ops
from harness.sources import SourceConfig, get as get_source


def _sha256_of_file_at_commit(repo_dir: Path, commit: str, rel_path: str) -> str | None:
    """Return sha256 of `<commit>:<rel_path>` content; None if file absent."""
    try:
        content = git_ops.show_file(repo_dir, commit, rel_path)
    except git_ops.GitError:
        return None
    return "sha256:" + hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def _derive_stack_domain(diff_text: str, source: SourceConfig) -> str:
    """Backend / frontend / fullstack from the non-test patch's `+++ b/` paths.

    Source-aware routing:
      * If `source.frontend_dir` is set, paths under it are frontend.
      * If `source.backend_dir` is non-empty, paths under it are backend;
        otherwise (root-as-backend repos like mcp-context-forge) anything
        not under frontend_dir/`frontend/` is backend.
      * Sources with no backend at all (bruno: frontend-only, backend_dir="")
        report `frontend_only` whenever any frontend path is touched and
        never `backend_only`/`fullstack`.
    """
    paths = re.findall(r"^\+\+\+ b/(.+?)\s*$", diff_text, re.MULTILINE)
    frontend_prefixes: list[str] = []
    if source.frontend_dir:
        frontend_prefixes.append(f"{source.frontend_dir}/")
    # Legacy fastapi-template path also recognized as frontend.
    if "frontend/" not in frontend_prefixes:
        frontend_prefixes.append("frontend/")

    def _is_frontend(p: str) -> bool:
        return any(p.startswith(prefix) for prefix in frontend_prefixes)

    has_fe = any(_is_frontend(p) for p in paths)

    # No Python backend at all (e.g. bruno's backend is Node.js, unsupported
    # by the harness) — surface as frontend-only when frontend changes exist.
    # We detect "no backend" as: backend_dir empty AND the only test_path_re
    # is the never-match sentinel `(?!x)x`.
    backend_unsupported = (
        not source.backend_dir
        and source.backend_test_path_re == r"(?!x)x"
    )
    if backend_unsupported:
        return "frontend_only" if has_fe else "frontend_only"

    if source.backend_dir:
        has_be = any(p.startswith(f"{source.backend_dir}/") for p in paths)
    else:
        # Root-as-backend repos: anything not frontend is backend.
        has_be = any(not _is_frontend(p) for p in paths)

    if has_be and has_fe:
        return "fullstack"
    if has_be:
        return "backend_only"
    if has_fe:
        return "frontend_only"
    return "backend_only"


def _contamination_tier(created_at: str, cutoff: str = "2026-01-01") -> str:
    return "public" if (created_at[:10] < cutoff) else "held_out"


def _problem_statement(pr_meta: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (problem_statement, notes)."""
    notes: list[str] = []
    closing = pr_meta.get("closingIssuesReferences") or []
    if closing and isinstance(closing[0], dict):
        body = (closing[0].get("body") or "").strip()
        if body:
            return body, notes

    body = (pr_meta.get("body") or "").strip()
    if body:
        notes.append("problem_statement sourced from PR description (no linked issue) — review for solution leakage.")
        return body, notes

    notes.append("problem_statement is a placeholder — both PR body and closing issue were empty. Curator must rewrite.")
    return f"<<TODO:problem_statement — PR #{pr_meta.get('number')} has empty body and no closing issue>>", notes


def build_instance_from_extract(
    *,
    pr_meta: dict[str, Any],
    summary: dict[str, Any],
    test_patch: str,
    repo_dir: Path,
    repo: str,
    source: SourceConfig,
    cutoff: str = "2026-01-01",
    kind: str = "backend",
) -> dict[str, Any]:
    base_commit = summary["base_commit"]
    head_commit = summary["head_commit"]
    number = summary.get("instance_id", "").rsplit("-", 1)[-1]

    # Compute the non-test reference patch from base..head.
    patch = git_ops.diff(
        repo_dir, base_commit, head_commit,
        paths=["."],
        exclude=["*test*", "*.spec.ts", "*.spec.tsx", "*.test.ts", "*.test.tsx"],
    )

    # Test paths are source-specific. Backend glob driven by SourceConfig
    # heuristic; frontend glob driven explicitly by source.frontend_test_diff_paths.
    backend_test_globs = (
        ["backend/tests/**", "backend/app/tests/**"] if source.backend_dir == "backend"
        else (["server/tests/**"] if source.backend_dir == "server" else ["tests/**"])
    )
    test_patch_backend = git_ops.diff(
        repo_dir, base_commit, head_commit, paths=backend_test_globs,
    )
    frontend_globs = source.frontend_test_diff_paths or [
        # legacy fastapi-template default
        "frontend/tests/**", "frontend/**/*.spec.ts", "frontend/**/*.spec.tsx",
        "frontend/**/*.test.ts", "frontend/**/*.test.tsx",
    ]
    test_patch_frontend = git_ops.diff(
        repo_dir, base_commit, head_commit, paths=frontend_globs,
    )

    owner, name = repo.split("/", 1)
    instance_id = f"{owner.replace('-','_')}__{name}-{number}"

    notes: list[str] = []
    notes.extend(summary.get("notes") or [])
    if summary.get("fallback_used"):
        notes.append(f"FAIL_TO_PASS recovered via {summary['fallback_used']}")

    problem, problem_notes = _problem_statement(pr_meta)
    notes.extend(problem_notes)

    fail_to_pass_raw = list(summary.get("fail_to_pass") or [])
    pass_to_pass_raw = list(summary.get("pass_to_pass") or [])
    # Place F2P/P2P into the correct bucket based on which runner produced
    # the summary. extract.py produces backend (pytest nodeids); frontend_extract.py
    # produces frontend (Playwright spec titles).
    if kind == "frontend":
        fail_to_pass = {"backend": [], "frontend": fail_to_pass_raw}
        pass_to_pass = {"backend": [], "frontend": pass_to_pass_raw}
    else:
        fail_to_pass = {"backend": fail_to_pass_raw, "frontend": []}
        pass_to_pass = {"backend": pass_to_pass_raw, "frontend": []}

    created_at = pr_meta.get("mergedAt") or pr_meta.get("createdAt") or ""

    instance: dict[str, Any] = {
        "instance_id": instance_id,
        "repo": repo,
        "pr_number": int(number),
        "pr_url": pr_meta.get("url", ""),
        "pr_title": pr_meta.get("title", ""),
        "pr_author": (pr_meta.get("author") or {}).get("login", ""),
        "pr_labels": [l.get("name") for l in (pr_meta.get("labels") or []) if isinstance(l, dict)],
        "base_commit": base_commit,
        "head_commit": head_commit,
        "problem_statement": problem,
        "patch": patch,
        "test_patch": test_patch or (test_patch_backend + test_patch_frontend),
        "test_patch_backend": test_patch_backend,
        "test_patch_frontend": test_patch_frontend,
        "fail_to_pass": fail_to_pass,
        "pass_to_pass": pass_to_pass,
        "stack_domain": _derive_stack_domain(patch, source),
        "environment": {
            "python_version": source.python_version,
            "node_version": "20",
            "uv_lock_sha": _sha256_of_file_at_commit(repo_dir, base_commit, source.uv_lock_path) or "",
            "bun_lock_sha": _sha256_of_file_at_commit(repo_dir, base_commit, "bun.lock") or "",
            "docker_compose_sha": _sha256_of_file_at_commit(repo_dir, base_commit, "compose.yml") or "",
        },
        "created_at": created_at,
        "contamination_tier": _contamination_tier(created_at, cutoff=cutoff) if created_at else "public",
        "notes": "\n".join(notes) if notes else None,
        "schema_version": "0.1",
    }
    # Strip None values that the schema doesn't allow.
    return {k: v for k, v in instance.items() if v is not None}


def build_from_extract(
    *,
    report_path: Path,
    prs_path: Path,
    repo_dir: Path,
    work_root: Path,
    output: Path,
    statuses: set[str],
    source: SourceConfig,
    repo: str = "fastapi/full-stack-fastapi-template",
    cutoff: str = "2026-01-01",
    kind: str = "backend",
) -> tuple[int, int]:
    """Returns (n_built, n_skipped).

    kind controls where extract artifacts live on disk + which F2P/P2P
    bucket the resulting instance's tests are placed in:
      "backend"  → <work_root>/<id>/out/summary.json + test_patch.diff
      "frontend" → <work_root>/<id>/frontend_out/summary.json + frontend_test_patch.diff
    """
    # Index PRs by number.
    prs_by_number: dict[int, dict] = {}
    with prs_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            prs_by_number[row["number"]] = row

    rows = []
    with report_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    output.parent.mkdir(parents=True, exist_ok=True)
    n_built = 0
    n_skipped = 0
    with output.open("w") as out_f:
        for r in rows:
            if r.get("status") not in statuses:
                n_skipped += 1
                continue
            pr_number = r["pr"]
            pr_meta = prs_by_number.get(pr_number)
            if pr_meta is None:
                n_skipped += 1
                continue
            instance_id = r["instance_id"]
            if kind == "frontend":
                summary_path = work_root / instance_id / "frontend_out" / "summary.json"
                test_patch_path = work_root / instance_id / "frontend_test_patch.diff"
            else:
                summary_path = work_root / instance_id / "out" / "summary.json"
                test_patch_path = work_root / instance_id / "test_patch.diff"
            if not summary_path.exists() or not test_patch_path.exists():
                n_skipped += 1
                continue
            summary = json.loads(summary_path.read_text())
            test_patch = test_patch_path.read_text()

            instance = build_instance_from_extract(
                pr_meta=pr_meta,
                summary=summary,
                test_patch=test_patch,
                repo_dir=repo_dir,
                repo=repo,
                source=source,
                cutoff=cutoff,
                kind=kind,
            )
            out_f.write(json.dumps(instance, ensure_ascii=False, sort_keys=True))
            out_f.write("\n")
            n_built += 1
    return n_built, n_skipped
