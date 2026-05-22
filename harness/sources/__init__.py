"""Source-repo configuration registry.

Each `SourceConfig` describes the per-repo facts the harness needs to drive
extract/score against that repo: where the backend lives, which Python image
it needs, how its env vars are named, what its prestart sequence is, and
which extra services (Redis, etc.) must run alongside Postgres.

Adding a new source = creating a `SourceConfig` object and registering it.
The harness modules read these facts instead of hard-coding any one repo's
layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtraService:
    """A side-car container the backend needs at test time (e.g. Redis)."""

    name: str                            # docker compose-style local name (e.g. "redis")
    image: str                           # "redis:alpine"
    healthcheck_cmd: list[str] | None = None
    # When backend container needs to reach this service, these env vars are
    # set on the backend invocation. Use {container_name} as a placeholder
    # for the runtime container name; runner substitutes.
    env_template: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceConfig:
    name: str                            # canonical "owner/name" — matches GitHub
    short_name: str                      # CLI alias, file-name-safe
    repo_url: str                        # https://github.com/owner/name.git

    # Layout
    backend_dir: str                     # repo-relative ("backend", "server", or "" for root)
    uv_lock_path: str                    # repo-relative ("uv.lock" or "server/uv.lock")
    backend_test_path_re: str            # regex: backend test file paths (filter + scope)
    backend_test_path_strip_prefix: str  # stripped before passing to pytest (cwd is backend_dir)

    # Image
    backend_image: str                   # tag the runner expects
    python_version: str                  # for documentation / instance.environment

    # uv invocation
    uv_extras: list[str] = field(default_factory=list)        # `--extra X` for sync + run
    uv_dev: bool = True                                        # `--dev` for sync (default for test deps)

    # Prestart sequence — each step is a uv-run argv list, executed inside backend_dir.
    # Empty = no prestart (e.g. SQLite-default test runners).
    prestart_steps: list[list[str]] = field(default_factory=list)

    # Pytest invocation extras (e.g. ["-n", "auto", "--ignore=tests/fuzz"]).
    pytest_extra_args: list[str] = field(default_factory=list)

    # Postgres usage
    pg_required: bool = True             # False → skip postgres setup entirely (SQLite-only repos)
    pg_env_map: dict[str, str] = field(default_factory=dict)   # canonical → source env var name
    pg_defaults: dict[str, str] = field(default_factory=dict)  # baseline credentials

    # Side-car services beyond Postgres
    extra_services: list[ExtraService] = field(default_factory=list)

    # Filter cutoff: PRs merged before this date are dropped (harness-incompatible base).
    uv_era_min_merged_at: str = "2020-01-01"

    # Frontend (optional — only sources with Playwright / Vitest tasks).
    # If None, filter falls back to the legacy `^frontend/.*\.(spec|test)\.[tj]sx?$`
    # default that fits fastapi-template's layout.
    frontend_test_path_re: str | None = None

    # Path-prefix regex for changed files that disqualify a PR (e.g. dual-license
    # `packages/ee/` regions). Matches against any single changed-file path.
    path_exclude_re: str | None = None

    # ----- Frontend runner (optional) ----------------------------------------
    # Two execution models supported:
    #
    #   "compose"           — source repo's own docker-compose orchestrates
    #                         db + backend + dev-frontend + playwright service.
    #                         fastapi-template uses this. Harness invokes
    #                         `docker compose -f compose.yml -f compose.override.yml
    #                         -f <our overlay> run playwright bunx playwright test`.
    #
    #   "playwright_direct" — Playwright's own `webServer` config spawns dev
    #                         servers in-process; harness runs `npm install`
    #                         + `npx playwright test` inside a single
    #                         Playwright base image. No compose stack required.
    #                         bruno uses this.
    #
    # None ⇒ source doesn't support frontend extraction (most backend-only sources).
    frontend_runner_kind: str | None = None

    # Workspace path of the frontend app — replaces hardcoded "frontend" dir
    # check in frontend_extract.py. "frontend" for fastapi-template,
    # "packages/bruno-app" for bruno, etc.
    frontend_dir: str | None = None

    # ── playwright_direct mode only ─────────────────────────────────────────
    # Base image with browsers preinstalled, e.g.
    # "mcr.microsoft.com/playwright:v1.50.0-jammy".
    frontend_docker_image: str | None = None

    # `npm ci` / `bun install` / `yarn install --frozen-lockfile` etc.
    frontend_install_cmd: list[str] = field(default_factory=list)

    # Per-workspace dependent builds that must run before playwright test
    # (e.g. bruno's `npm run build:bruno-common`). One argv list per step.
    frontend_pre_test_cmd: list[list[str]] = field(default_factory=list)

    # The Playwright invocation itself, e.g.
    # ["npx", "playwright", "test", "--project=default", "--reporter=json"].
    frontend_test_cmd: list[str] = field(default_factory=list)

    # Path (relative to repo root) of the JSON report Playwright writes.
    # bruno's playwright.config.ts hardcodes "playwright-report/results.json";
    # other repos may use `PLAYWRIGHT_JSON_OUTPUT_NAME` env instead.
    frontend_json_report_path: str | None = None

    # Git-diff path filters used to scope `test_patch` to frontend test files
    # only (passed to `git diff -- <paths>`). Glob-style.
    #   fastapi-template: ["frontend/tests/**", "frontend/**/*.spec.ts", ...]
    #   bruno:            ["tests/**/*.spec.ts", "tests/**/*.spec.tsx", ...]
    frontend_test_diff_paths: list[str] = field(default_factory=list)

    # Prefix to strip when converting changed spec paths into Playwright CLI
    # positional args (which expect paths relative to playwright's testDir
    # ancestor). fastapi-template: "frontend/" (testDir inside `frontend/`),
    # bruno: "" (testDir = ./tests at repo root).
    frontend_test_diff_strip_prefix: str = ""


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


_REGISTRY: dict[str, SourceConfig] = {}


def register(cfg: SourceConfig) -> SourceConfig:
    _REGISTRY[cfg.short_name] = cfg
    _REGISTRY[cfg.name] = cfg
    return cfg


def get(short_or_canonical_name: str) -> SourceConfig:
    if short_or_canonical_name not in _REGISTRY:
        raise KeyError(
            f"unknown source: {short_or_canonical_name!r}. "
            f"Known: {sorted(set(c.short_name for c in _REGISTRY.values()))}"
        )
    return _REGISTRY[short_or_canonical_name]


def all_sources() -> list[SourceConfig]:
    seen: set[str] = set()
    out: list[SourceConfig] = []
    for cfg in _REGISTRY.values():
        if cfg.name in seen:
            continue
        seen.add(cfg.name)
        out.append(cfg)
    return out


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def effective_uv_extras(source: SourceConfig, repo_dir) -> list[str]:
    """Return the subset of `source.uv_extras` actually defined in the checked-out
    pyproject.toml. PRs older than the addition of an extra would otherwise fail
    with `Extra X is not defined in the project's optional-dependencies table`.
    """
    from pathlib import Path
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    repo_dir = Path(repo_dir)
    backend = repo_dir / source.backend_dir if source.backend_dir else repo_dir
    pyproject = backend / "pyproject.toml"
    if not pyproject.exists():
        return list(source.uv_extras)
    try:
        data = tomllib.loads(pyproject.read_text())
    except Exception:
        return list(source.uv_extras)
    available = set((data.get("project", {}) or {}).get("optional-dependencies", {}).keys())
    return [e for e in source.uv_extras if e in available]


# Eagerly populate the registry by importing each source module.
from . import fastapi_full_stack_template  # noqa: F401, E402
from . import mcp_context_forge  # noqa: F401, E402
from . import activepieces  # noqa: F401, E402
from . import bruno  # noqa: F401, E402
