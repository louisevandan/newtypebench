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
    # Playwright base + Electron GUI deps (GTK/NSS/ATK/cups/asound/xvfb).
    # See harness/docker/Dockerfile.playwright-electron.
    frontend_docker_image="prototypebench/playwright-electron:v1.51.1",
    # bruno's own setup.js does install (npm i --legacy-peer-deps +
    # force-install platform deps) AND the 7 workspace builds in the right
    # dependency order AND the JS sandbox library bundle. Then we SUID
    # chrome-sandbox (required by Electron unless --no-sandbox is passed,
    # which we can't pass without patching bruno's own playwright/index.ts).
    frontend_install_cmd=[
        "bash", "-c",
        "npm run setup && "
        "chown root:root node_modules/electron/dist/chrome-sandbox && "
        "chmod 4755 node_modules/electron/dist/chrome-sandbox",
    ],
    frontend_pre_test_cmd=[],
    # No `--project=` here: bruno's config has three projects (default, auth,
    # ssl) where `default` testIgnores `auth/**` & `ssl/**`. Hard-coding any
    # single project would silently skip specs that live in the others
    # (verified: #7911's `tests/auth/...spec.ts` was 0-matched under
    # `--project=default`). Without --project, Playwright routes each spec
    # path arg to the project whose testDir+testIgnore matches.
    frontend_test_cmd=[
        "npx", "playwright", "test",
        "--reporter=json",
    ],
    frontend_json_report_path="playwright-report/results.json",
    # NB: includes the whole tests/ tree, not just *.spec.ts. bruno's e2e
    # specs require co-located fixtures (.bru collections, preferences.json,
    # auth helpers, etc.) — leaving them out of test_patch means
    # `base + test_patch + agent_patch` doesn't reproduce `head_commit`'s
    # tree, which makes Playwright fail to load fixtures and score=0 even
    # when the agent submits a byte-identical copy of the reference patch
    # (see docs/phase3-fe-smoke-analysis.md, #7947 root-cause).
    frontend_test_diff_paths=["tests/**"],
    frontend_test_diff_strip_prefix="",  # testDir == ./tests at repo root
))
