"""Score and filter crawled PRs into a candidate pool for task conversion.

Reads:  raw/prs.jsonl
Writes: raw/candidates.jsonl   (filtered + scored, sorted desc by score)
        raw/rejected.jsonl     (dropped PRs with reason — audit trail)

Scoring signals (v0.1 — tune after seed curation):
  + has test file changes              (+3)  — highest signal for task viability
  + label contains bug/feature/fix     (+2)
  + closing issue linked               (+2)  — richer problem_statement
  + 2 ≤ changed_files ≤ 20             (+1)  — not trivial, not sprawling
  - author is dependabot / renovate    drop
  - title starts with chore/docs/ci    drop
  - only docs/workflows/lock files     drop
  - PR body too short (<120 chars) and no closing issue  (−2)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harness.sources import SourceConfig, get as get_source

DROP_TITLE_PREFIXES = (
    "chore:",
    "docs:",
    "doc:",
    "ci:",
    "release:",
    "bump ",
    "⬆",
    "⬆️",
    "revert ",
    "🔒",
)

TEST_PATH_PATTERNS = (
    re.compile(r"^backend/.*tests?/.*\.py$"),
    re.compile(r"^backend/.*test_.*\.py$"),
    re.compile(r"^frontend/tests/.*\.(spec|test)\.[tj]sx?$"),
    re.compile(r"^frontend/.*\.(spec|test)\.[tj]sx?$"),
)

IGNORE_PATH_PATTERNS = (
    re.compile(r"^\.github/"),
    re.compile(r"^docs?/"),
    re.compile(r"/README\.md$"),
    re.compile(r"^README\.md$"),
    re.compile(r"(^|/)(uv\.lock|bun\.lockb|package-lock\.json|yarn\.lock|poetry\.lock)$"),
)

SIGNAL_LABELS = {"bug", "feature", "enhancement", "fix"}

_DEFAULT_FRONTEND_TEST_RE = re.compile(r"^frontend/.*\.(spec|test)\.[tj]sx?$")


def _author_login(pr: dict[str, Any]) -> str:
    a = pr.get("author") or {}
    return (a.get("login") or "").lower() if isinstance(a, dict) else str(a).lower()


def _author_is_bot(pr: dict[str, Any]) -> bool:
    a = pr.get("author") or {}
    if isinstance(a, dict) and a.get("is_bot"):
        return True
    login = _author_login(pr)
    return login.startswith("app/") or login.endswith("[bot]")


def _file_paths(pr: dict[str, Any]) -> list[str]:
    files = pr.get("files") or []
    return [f.get("path", "") for f in files if isinstance(f, dict)]


def _is_test_path(path: str) -> bool:
    return any(p.match(path) for p in TEST_PATH_PATTERNS)


def _is_ignorable_path(path: str) -> bool:
    return any(p.search(path) for p in IGNORE_PATH_PATTERNS)


def _label_names(pr: dict[str, Any]) -> set[str]:
    labels = pr.get("labels") or []
    return {l.get("name", "").lower() for l in labels if isinstance(l, dict)}


def score(
    pr: dict[str, Any],
    source: SourceConfig,
) -> tuple[int, list[str], str | None, dict[str, int]]:
    """Return (score, reasons, drop_reason, signals).

    signals = {"backend_tests": N, "frontend_tests": N} — used downstream by
    `top --kind` and `batch-extract --kind` to route PRs to the right runner.
    """
    reasons: list[str] = []
    signals = {"backend_tests": 0, "frontend_tests": 0}
    if _author_is_bot(pr):
        return 0, reasons, f"bot author: {_author_login(pr)}", signals

    title = (pr.get("title") or "").lower()
    if any(title.startswith(p) for p in DROP_TITLE_PREFIXES):
        return 0, reasons, f"non-task title prefix: {title[:40]}", signals

    merged_at = pr.get("mergedAt") or ""
    if merged_at and merged_at[:10] < source.uv_era_min_merged_at:
        return 0, reasons, f"pre-uv-era merge ({merged_at[:10]}) — harness unsupported for {source.short_name}", signals

    paths = _file_paths(pr)
    if not paths:
        return 0, reasons, "no files", signals

    if source.path_exclude_re:
        excl = re.compile(source.path_exclude_re)
        hit = next((p for p in paths if excl.search(p)), None)
        if hit:
            return 0, reasons, f"excluded path region: {hit}", signals

    meaningful_paths = [p for p in paths if not _is_ignorable_path(p)]
    if not meaningful_paths:
        return 0, reasons, "only docs/ci/lock files", signals

    s = 0
    backend_test_re = re.compile(source.backend_test_path_re)
    frontend_test_re = (
        re.compile(source.frontend_test_path_re)
        if source.frontend_test_path_re
        else _DEFAULT_FRONTEND_TEST_RE
    )
    backend_tests = [p for p in meaningful_paths if backend_test_re.match(p)]
    frontend_tests = [p for p in meaningful_paths if frontend_test_re.match(p)]
    signals["backend_tests"] = len(backend_tests)
    signals["frontend_tests"] = len(frontend_tests)

    if backend_tests:
        s += 3
        reasons.append(f"backend tests: {len(backend_tests)}")
    if frontend_tests:
        s += 3
        reasons.append(f"frontend tests: {len(frontend_tests)}")
    if not backend_tests and not frontend_tests:
        return 0, reasons, "no test file changes (neither backend nor frontend)", signals

    labels = _label_names(pr)
    hit_labels = labels & SIGNAL_LABELS
    if hit_labels:
        s += 2
        reasons.append(f"labels: {sorted(hit_labels)}")

    closing = pr.get("closingIssuesReferences") or []
    if closing:
        s += 2
        reasons.append(f"closes {len(closing)} issue(s)")

    n_changed = len(meaningful_paths)
    if 2 <= n_changed <= 20:
        s += 1
        reasons.append(f"{n_changed} files (in band)")

    body = pr.get("body") or ""
    if len(body) < 120 and not closing:
        s -= 2
        reasons.append("short body, no issue link")

    return s, reasons, None, signals


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write("\n")


def filter_prs(
    input_path: Path,
    candidates_path: Path,
    rejected_path: Path,
    source: SourceConfig,
) -> tuple[int, int]:
    prs = load_jsonl(input_path)
    accepted: list[dict] = []
    rejected: list[dict] = []
    for pr in prs:
        s, reasons, drop, signals = score(pr, source)
        if drop:
            rejected.append({"number": pr.get("number"), "title": pr.get("title"), "reason": drop})
            continue
        accepted.append({
            "number": pr["number"],
            "score": s,
            "reasons": reasons,
            "signals": signals,
            "pr": pr,
        })

    accepted.sort(key=lambda r: (-r["score"], -r["number"]))
    write_jsonl(candidates_path, accepted)
    write_jsonl(rejected_path, rejected)
    return len(accepted), len(rejected)
