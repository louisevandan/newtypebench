"""Source config for usebruno/bruno — frontend-emphasis source.

bruno is an MIT-licensed Electron + React API client (webpack-based, not Vite).
Frontend app lives at `packages/bruno-app/` and Playwright e2e tests are
organized by domain under `tests/` (auth, collection, onboarding, ...) with
the canonical `*.spec.ts` extension.

Why register despite not being Vite: v1+ frontend pool yield from strictly-
Vite OSS is empirically near-zero (see PLAN.md §3.3 + the 2026-05-23
activepieces probe). bruno relaxes the Vite-only invariant in exchange for
a real Playwright test culture (root `playwright.config.ts`, 20+ test
domains, ~1,185 merged PRs/yr, 44k★).

License: MIT (entire repo — no carve-outs).
"""

from __future__ import annotations

from . import SourceConfig, register

CONFIG = register(SourceConfig(
    name="usebruno/bruno",
    short_name="bruno",
    repo_url="https://github.com/usebruno/bruno.git",

    # Placeholder backend fields — bruno has no Python backend.
    backend_dir="",
    uv_lock_path="",
    backend_test_path_re=r"(?!x)x",     # never matches
    backend_test_path_strip_prefix="",
    backend_image="",
    python_version="",

    uv_extras=[],
    uv_dev=False,
    prestart_steps=[],
    pytest_extra_args=[],

    pg_required=False,
    pg_env_map={},
    pg_defaults={},
    extra_services=[],

    # Cutoff: keep generous; bruno's Playwright setup has been stable.
    uv_era_min_merged_at="2024-01-01",

    # Frontend test path: Playwright e2e specs under top-level tests/ tree.
    # `tests/.*\.(spec|test)\.[tj]sx?$` — handles nested domain dirs.
    frontend_test_path_re=r"^tests/.*\.(spec|test)\.[tj]sx?$",

    # No license carve-outs needed.
    path_exclude_re=None,

    # bruno's Playwright config uses webServer to auto-spawn dev:web + bruno-tests
    # mock server; no docker-compose orchestration is required. The harness runs
    # `npm install` + `npx playwright test --project=default` inside a single
    # Playwright base image. (Implementation lands in a follow-up commit.)
    frontend_runner_kind="playwright_direct",
    frontend_dir="packages/bruno-app",
    frontend_docker_image="mcr.microsoft.com/playwright:v1.51.1-jammy",
    frontend_install_cmd=["npm", "ci"],
    # bruno-app depends on these workspaces being built first.
    frontend_pre_test_cmd=[
        ["npm", "run", "build:bruno-common"],
        ["npm", "run", "build:bruno-requests"],
        ["npm", "run", "build:bruno-filestore"],
        ["npm", "run", "build:bruno-converters"],
        ["npm", "run", "build:bruno-query"],
        ["npm", "run", "build:graphql-docs"],
        ["npm", "run", "build:schema-types"],
    ],
    frontend_test_cmd=[
        "npx", "playwright", "test",
        "--project=default",
        "--reporter=json",
    ],
    frontend_json_report_path="playwright-report/results.json",
    frontend_test_diff_paths=[
        "tests/**/*.spec.ts",
        "tests/**/*.spec.tsx",
        "tests/**/*.test.ts",
        "tests/**/*.test.tsx",
    ],
    frontend_test_diff_strip_prefix="",  # testDir == ./tests at repo root
))
