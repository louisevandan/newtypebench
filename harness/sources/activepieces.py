"""Source config for activepieces/activepieces — frontend-emphasis source.

activepieces is a TypeScript monorepo (Nx) with a Vite + React + Tailwind v4 +
Radix UI frontend at `packages/web/` and Playwright e2e in `packages/tests-e2e/`.
The backend is Node.js (Express/Fastify), not Python — so this source is
registered as **frontend-only** from the harness's perspective.

License: MIT-Expat for everything outside `packages/ee/` and
`packages/server/api/src/app/ee/`. Those regions are commercial-licensed and
must be excluded — `path_exclude_re` drops any PR that touches them.

Cutoff: 2026-02-01. Tailwind v4 (`@tailwindcss/vite`) landed early-2026; PRs
predating that have a divergent build setup and aren't worth retrofitting.
"""

from __future__ import annotations

from . import SourceConfig, register

CONFIG = register(SourceConfig(
    name="activepieces/activepieces",
    short_name="activepieces",
    repo_url="https://github.com/activepieces/activepieces.git",

    # Backend fields are placeholders — this source has no Python backend.
    # Setting non-empty path_re ensures the filter never accidentally awards
    # `backend_tests` points for a JS-only PR; the regex below matches nothing.
    backend_dir="",
    uv_lock_path="",
    backend_test_path_re=r"(?!x)x",     # never matches — JS repo, no pytest
    backend_test_path_strip_prefix="",
    backend_image="",                    # unused (no backend runner)
    python_version="",

    uv_extras=[],
    uv_dev=False,
    prestart_steps=[],
    pytest_extra_args=[],

    pg_required=False,
    pg_env_map={},
    pg_defaults={},
    extra_services=[],

    uv_era_min_merged_at="2026-02-01",

    # Frontend test path: Playwright specs live under packages/tests-e2e/scenarios.
    frontend_test_path_re=r"^packages/tests-e2e/(?:scenarios|fixtures|pages)/.*\.(spec|test)\.[tj]sx?$",

    # License exclusion: commercial regions.
    path_exclude_re=r"^packages/ee/|^packages/server/api/src/app/ee/",
))
