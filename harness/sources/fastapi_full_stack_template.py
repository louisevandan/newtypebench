"""Source config for fastapi/full-stack-fastapi-template (the original)."""

from __future__ import annotations

from . import SourceConfig, register

CONFIG = register(SourceConfig(
    name="fastapi/full-stack-fastapi-template",
    short_name="fastapi-template",
    repo_url="https://github.com/fastapi/full-stack-fastapi-template.git",
    backend_dir="backend",
    uv_lock_path="uv.lock",                 # workspace root is repo root
    backend_test_path_re=r"^backend/(?:tests|app/tests)/[^\s]+",
    backend_test_path_strip_prefix="backend/",
    backend_image="prototypebench/backend:latest",   # py3.10
    python_version="3.10",
    uv_extras=[],
    uv_dev=False,                            # workspace setup; deps installed via main `uv sync`
    prestart_steps=[
        ["python", "app/backend_pre_start.py"],
        ["alembic", "upgrade", "head"],
        ["python", "app/initial_data.py"],
    ],
    pytest_extra_args=[],                    # tests dir is the default arg
    pg_required=True,
    pg_env_map={
        "server":   "POSTGRES_SERVER",
        "port":     "POSTGRES_PORT",
        "user":     "POSTGRES_USER",
        "password": "POSTGRES_PASSWORD",
        "db":       "POSTGRES_DB",
    },
    pg_defaults={
        "user":     "postgres",
        "password": "changethis",
        "db":       "app",
    },
    extra_services=[],
    uv_era_min_merged_at="2026-01-20",      # PR #2090 introduced uv workspaces

    # Frontend: source repo's own compose stack orchestrates everything.
    frontend_runner_kind="compose",
    frontend_dir="frontend",
    frontend_test_path_re=r"^frontend/.*\.(spec|test)\.[tj]sx?$",
    frontend_test_diff_paths=[
        "frontend/tests/**",
        "frontend/**/*.spec.ts",
        "frontend/**/*.spec.tsx",
        "frontend/**/*.test.ts",
        "frontend/**/*.test.tsx",
    ],
    frontend_test_diff_strip_prefix="frontend/",
))
