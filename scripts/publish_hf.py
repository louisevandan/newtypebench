"""Publish the combined instances dataset to Hugging Face Hub.

Usage:
    uv run python -m scripts.publish_hf \
        --repo banyaaiofficial/prototypebench-v1 \
        --local dataset

Requires env var HUGGINGFACE_TOKEN with write scope on the target org.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from huggingface_hub import HfApi

app = typer.Typer(no_args_is_help=True)


@app.command()
def main(
    repo: str = typer.Option(
        "banyaaiofficial/prototypebench-v1", "--repo",
        help="HF dataset repo id (<org>/<name>).",
    ),
    local: Path = typer.Option(
        Path("dataset"), "--local",
        help="Local directory to upload (contents become the repo root).",
    ),
    private: bool = typer.Option(
        False, "--private",
        help="Create the repo as private (default public).",
    ),
    commit_msg: str = typer.Option(
        "PrototypeBench v0.1 — 71 task instances", "--message",
    ),
) -> None:
    """Create or update the HF dataset repo and upload the `local` directory."""
    token = (
        os.environ.get("HUGGINGFACE_TOKEN")
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")  # huggingface_hub stdlib name
    )
    if not token:
        raise typer.BadParameter(
            "No HF token in env. Set one of: HUGGINGFACE_TOKEN / HF_TOKEN / "
            "HUGGING_FACE_HUB_TOKEN (write scope). "
            "Get a token at https://huggingface.co/settings/tokens."
        )

    if not local.exists():
        raise typer.BadParameter(f"local dir not found: {local}")
    if not (local / "instances.jsonl").exists():
        raise typer.BadParameter(f"{local}/instances.jsonl missing — run the combine step first.")
    if not (local / "README.md").exists():
        raise typer.BadParameter(f"{local}/README.md missing — dataset card required.")

    api = HfApi(token=token)

    # Idempotent create. exist_ok=True swallows conflicts.
    api.create_repo(
        repo_id=repo,
        repo_type="dataset",
        private=private,
        exist_ok=True,
    )
    typer.echo(f"[green]repo ready[/green]: https://huggingface.co/datasets/{repo}")

    api.upload_folder(
        folder_path=str(local),
        repo_id=repo,
        repo_type="dataset",
        commit_message=commit_msg,
    )
    typer.echo(f"[green]uploaded[/green] {local}/* → {repo}")
    typer.echo(f"view at https://huggingface.co/datasets/{repo}")


if __name__ == "__main__":
    app()
