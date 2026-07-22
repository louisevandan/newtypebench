<p align="right">
  <b>English</b> · <a href="README.ko.md">한국어</a>
</p>

# NewtypeBench

> **Can your agent ship a full-stack AI-native prototype?**

![phase](https://img.shields.io/badge/phase-3%20active-green)
![corpus](https://img.shields.io/badge/corpus-123%20tasks-blue)
![dataset](https://img.shields.io/badge/HF-v0.2.2-yellow)
![license](https://img.shields.io/badge/license-MIT-blue)
![stack](https://img.shields.io/badge/stack-React%20%2B%20Vite%20%2B%20Tailwind%20%7C%20FastAPI%20%2B%20SQLModel-black)

NewtypeBench is an open benchmark for evaluating the **full-stack product-shipping ability** of AI coding agents. Where SWE-Bench measures bug-fixing in mature Python libraries, NewtypeBench measures **"can the agent ship a full-stack feature on a modern AI-native stack?"**

- **📦 Dataset on Hugging Face**: [`banyaaiofficial/newtypebench-v1`](https://huggingface.co/datasets/banyaaiofficial/newtypebench-v1) — **123 instances** (v0.2.2, 71 backend + 52 frontend), MIT, `datasets.load_dataset(...)` ready.
- **Task sources** (multi-source via `harness/sources/`):
  - [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) — MIT, 42.7k★ — full-stack template (React+Vite+Tailwind+shadcn / FastAPI+SQLModel+Postgres). 3 backend instances.
  - [`IBM/mcp-context-forge`](https://github.com/IBM/mcp-context-forge) — Apache-2, 3.6k★ — FastAPI MCP gateway, 1,645 PRs/yr, hermetic SQLite tests. 68 backend instances.
  - [`usebruno/bruno`](https://github.com/usebruno/bruno) — MIT, 44k★ — Electron + React + Tailwind + Playwright API client, 1,185 PRs/yr. **52 frontend instances** via `playwright_direct` runner (custom Playwright + Xvfb + Electron deps image).
- **Scoring**: all `FAIL_TO_PASS` pass + all `PASS_TO_PASS` don't regress = 1 point (binary). Dual runner (pytest + Playwright). Snapshot tests are P2P-advisory (kept out of the regression-guard set; see [`docs/phase3-fe-smoke-analysis.md`](docs/phase3-fe-smoke-analysis.md)).
- **Judge**: execution-based (no LLM-as-judge) — pytest/Playwright is the arbiter, ground-truth = the actual merged PR diff.
- **Format**: extends the SWE-Bench `instances.jsonl` schema — existing tooling is re-usable with minimal glue.
- **Phase 3 evaluation interface** (since 2026-05-23): **agent-loop** is the primary path — the harness mounts the repo, the submitter's agent edits files via tools, and the harness `git diff`s the result for scoring (sidesteps the byte-exact-diff serialization problem that broke patch-submission for frontier models). See [`PLAN.md` §5.5](PLAN.md) — harness defines task spec + score; submitters own the agent design.

## Why this stack?

Each component is #1 in its category per 2024 industry surveys.

| | Share | Source |
|---|---|---|
| **React** | 82% (undisputed #1) | State of JS 2024 |
| **Vite** | 78.1% (overtook Webpack) | State of JS 2024 |
| **Tailwind CSS** | 62% (first time over Bootstrap) | State of CSS 2024 |
| **FastAPI** | 38% (first time over Django/Flask), 42% of ML engineers | JetBrains Python Survey 2024 |

16,209 open "fastapi react" jobs on Indeed (2025). We evaluate AI agents on the stack that actual AI product teams ship on.

## What's in a task

Each task is a JSON object derived from one real merged PR. It extends the SWE-Bench format with **dual-test (backend + frontend)** fields.

```jsonc
{
  "instance_id": "fastapi__full-stack-fastapi-template-1234",
  "repo": "fastapi/full-stack-fastapi-template",
  "base_commit": "0123...",
  "head_commit": "abcd...",
  "problem_statement": "Users should be able to archive an item without deleting it ...",
  "patch": "diff --git a/backend/app/api/routes/items.py ...",
  "test_patch": "diff --git a/... test files only ...",
  "fail_to_pass": {
    "backend":  ["backend/app/tests/.../test_archive_item_success"],
    "frontend": ["frontend/tests/items.spec.ts:42:3 › archive button toggles"]
  },
  "pass_to_pass": { "backend": [...], "frontend": [...] },
  "stack_domain": "fullstack",
  "environment": { "python_version": "3.11", "node_version": "20", "uv_lock_sha": "...", "bun_lock_sha": "..." },
  "contamination_tier": "held_out"
}
```

Full schema: [`schemas/task_instance.schema.json`](schemas/task_instance.schema.json) · [`docs/task-schema.md`](docs/task-schema.md).

## Status

| Phase | Status |
|---|---|
| 1 · Task curation pipeline | ✅ **123 task instances** — pool target (40-60) 2× exceeded |
| 2 · Evaluation harness (pytest + Playwright + Docker, multi-source) | ✅ Backend (Docker pytest) + Frontend (compose / playwright_direct) + score scoping (85% wall-time cut) |
| 3 · Internal beta (model shootout) | 🟢 **Active** — reference agent-loop runner + agent-score CLI shipped; first 20-instance smoke complete |
| 4 · Public leaderboard | ⏳ |
| 5 · Continuous task refresh | ⏳ |

**Current corpus** (2026-05-24, dataset v0.2.2):

| Stat | Value |
|---|---:|
| Task instances | **123** |
| Sources | 3 (`fastapi/full-stack-fastapi-template`, `IBM/mcp-context-forge`, `usebruno/bruno`) |
| `stack_domain` distribution | 71 backend_only + 52 frontend_only |
| `FAIL_TO_PASS` tests (combined) | **940** |
| `PASS_TO_PASS` regression-guard tests | **31,945** (snapshot tests P2P-advisory) |
| Total individual test cases per full evaluation | **32,885** |
| Schema valid | 123 / 123 |

For comparison: SWE-Bench Verified ships 500, SWE-Bench Lite 300, HumanEval 164. v1 public-beta target: 200-300 instances split across `public` / `held_out` / `internal_only` tiers.

**First multi-instance smoke** (Claude Opus 4.7, reference Claude-CLI agent-loop runner, 2026-05-23~24): backend 5/10 = 50%, frontend 1/10 = 10%, **6/20 = 30%** binary; ~46% partial-weighted. See [`docs/phase3-fe-smoke-analysis.md`](docs/phase3-fe-smoke-analysis.md) for the failure analysis and [`PLAN.md` §8.3](PLAN.md) for the running Phase 3 log.

Leaderboard submissions open in Phase 4. Design principles, observed-failure-modes, and the full roadmap live in [`PLAN.md`](PLAN.md).

## Fairness & contamination

Two invariants carry the benchmark's credibility:

1. **Fairness** — tasks on which the operating organization's agent performs *poorly* are required. The benchmark name carries no vendor branding.
2. **Contamination defense** — the source repo is MIT-public, so frontier models likely saw its PR diffs during training.
   Tasks are partitioned into `public` / `held_out` / `internal_only` tiers by merge date vs. model cutoff. Held-out tiers rotate per leaderboard season.
   Submitters must disclose model cutoff dates.

## Quick start

### Prerequisites

- Python 3.11+, [`uv`](https://docs.astral.sh/uv/)
- [`gh` CLI](https://cli.github.com/) (authenticated, only needed for crawl/filter)
- Docker (for hermetic backend pytest + Playwright/Electron runners)
- (optional, for the reference agent-loop runner) Claude Code CLI (`claude`)

### Install

```bash
git clone https://github.com/louisevandan/newtypebench.git
cd newtypebench
uv sync
```

### Evaluating an agent (submitter path)

The harness's public contract is **task spec + score**. You bring your own agent
(system prompt, tool allowlist, multi-turn / planning / retry strategy are all
yours; see [PLAN.md §5.5](PLAN.md)). Two contract surfaces are supported:

**A. Patch submission** (SWE-Bench style — back-compat)
```bash
# Prereq: download instances, run extract once to seed work_dir,
# then call score with your unified diff:
uv run pbench score --source mcp-context-forge --pr 3284 \
    --patch-file solution.patch
```

**B. Agent loop** (Phase 3 primary — sidesteps byte-exact-diff serialization)
The reference runner uses Claude CLI; submitters typically replace it.
```bash
uv run pbench agent-score --source mcp-context-forge --pr 3284 \
    --model claude-opus-4-7 --timeout 600
# → mounts the instance's repo, runs the agent, harness `git diff`s
#   the result, then scores it.
```

### Curating tasks (maintainer path)

```bash
# 1. Crawl merged PRs → raw/<source>/prs.jsonl
uv run pbench crawl   --source fastapi-template
uv run pbench crawl   --source mcp-context-forge
uv run pbench crawl   --source bruno

# 2. Filter + score → raw/<source>/candidates.jsonl
uv run pbench filter  --source bruno

# 3. Inspect (filter by signal kind: backend | frontend | fullstack | any)
uv run pbench top     --source bruno --kind frontend --n 20

# 4. Auto-derive FAIL_TO_PASS / PASS_TO_PASS by running the source's tests
#    on base vs head (Docker; --kind backend pytest, --kind frontend Playwright)
uv run pbench batch-extract --source bruno --kind frontend --top 10

# 5. Convert usable extract results into schema-shaped task instances
uv run pbench build-from-extract --source bruno --kind frontend

# 6. Validate against the schema
uv run pbench validate -p tasks/instances.bruno.jsonl
```

Full CLI help: `uv run pbench --help`.

### Adding a new task source

Drop a `SourceConfig` registration in `harness/sources/<short_name>.py` —
backend dir, uv-lock path, prestart steps, env-var aliasing for postgres,
extras, image tag, etc. The harness reads the registry; no other module
needs to change. See [`harness/sources/mcp_context_forge.py`](harness/sources/mcp_context_forge.py)
for a minimal SQLite-only example.

## Repo layout

```
newtypebench/
├── PLAN.md                      # Project charter (principles · competitive map · roadmap)
├── schemas/
│   └── task_instance.schema.json
├── docs/
│   ├── task-schema.md           # Field-by-field schema explainer
│   └── seed-curation.md         # Manual curation checklist
├── scripts/                     # `pbench` CLI
│   ├── cli.py
│   ├── crawl_prs.py
│   ├── filter_prs.py
│   ├── build_instance.py
│   └── validate.py
├── tasks/
│   └── instances.jsonl          # Final task bundle (curation output)
└── raw/                         # Crawler scratch (gitignored)
```

## Contributing

In Phase 1, **task quality is benchmark credibility**. Welcome contributions:

- Improvements to the [`docs/seed-curation.md`](docs/seed-curation.md) checklist
- Schema v0.2 proposals (see last section of [`docs/task-schema.md`](docs/task-schema.md))
- Filter-heuristic tuning (`scripts/filter_prs.py`)
- New seed-task proposals (link to a specific base-repo PR + a `notes` draft)

Please open an Issue before a PR while the process is still hardening.

## References

- [SWE-Bench](https://www.swebench.com/) · [Terminal-Bench](https://www.tbench.ai/) · [FullStackBench (arxiv 2412.00535)](https://arxiv.org/abs/2412.00535) · [LiveBench](https://livebench.ai/)
- [State of JS 2024](https://2024.stateofjs.com/) · [State of CSS 2024](https://2024.stateofcss.com/) · [JetBrains Python Survey 2024](https://lp.jetbrains.com/python-developers-survey-2024/)

## License

MIT. The base repo `fastapi/full-stack-fastapi-template` is also MIT.

## Cite

Citation format will be fixed at the Phase 4 public launch.
