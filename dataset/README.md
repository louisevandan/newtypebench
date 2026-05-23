---
license: mit
language:
  - en
task_categories:
  - text-generation
pretty_name: PrototypeBench v0.1
tags:
  - benchmark
  - llm-evaluation
  - llm-benchmark
  - coding-agent
  - agent-evaluation
  - swe-bench
  - fastapi
  - python
  - software-engineering
  - execution-based-evaluation
  - rlvr
size_categories:
  - n<1K
source_datasets:
  - original
configs:
  - config_name: default
    data_files:
      - split: test
        path: "instances.jsonl"
dataset_info:
  features:
    - name: instance_id
      dtype: string
    - name: repo
      dtype: string
    - name: pr_number
      dtype: int32
    - name: pr_url
      dtype: string
    - name: pr_title
      dtype: string
    - name: base_commit
      dtype: string
    - name: head_commit
      dtype: string
    - name: problem_statement
      dtype: string
    - name: patch
      dtype: string
    - name: test_patch
      dtype: string
    - name: stack_domain
      dtype: string
    - name: contamination_tier
      dtype: string
    - name: created_at
      dtype: string
    - name: schema_version
      dtype: string
---

# PrototypeBench v0.1

> **Can your agent ship a full-stack AI-native prototype?**

PrototypeBench is an open benchmark for evaluating AI coding agents on **full-stack feature shipping**. Where SWE-Bench measures bug-fixing in mature Python libraries, PrototypeBench measures *"can the agent ship a full-stack feature on a modern AI-native stack?"*

- **Project home**: https://github.com/prototypebench/prototypebench
- **Website**: https://prototypebench.org
- **License**: MIT
- **Version**: v0.1 (initial corpus)
- **Language**: English (problem statements), Python (backend code), TypeScript/JavaScript (frontend code, future)

## Dataset Summary

123 **PR-mined task instances** from active open-source repositories, each shaped for SWE-Bench-compatible execution-based scoring:

| Stat | Value |
|---|---:|
| Total instances | **123** |
| Sources | 3 (`fastapi/full-stack-fastapi-template`, `IBM/mcp-context-forge`, `usebruno/bruno`) |
| `FAIL_TO_PASS` tests | 940 |
| `PASS_TO_PASS` regression-guard tests | 31,971 |
| Total test cases per full eval | **32,911** |
| stack_domain | 71 backend_only + 52 frontend_only (fullstack instances in later versions) |
| contamination_tier | 123 held_out (all post-2026-01-01) |
| Schema version | 0.1 |

**Comparison**: SWE-Bench Verified has 500 instances, SWE-Bench Lite 300, HumanEval 164. v1 public-beta targets 200–300.

## Scoring

Execution-based binary scoring (no LLM-as-judge):

```
score(instance) = 1  iff  FAIL_TO_PASS ⊆ passing_tests
                     AND  PASS_TO_PASS ⊆ passing_tests    (no regression)
                  0  otherwise
```

**Judge**: `pytest` (backend) and `Playwright` (frontend, future). **Ground truth** = the actual merged PR diff (hidden from the agent). See the [methodology notes](https://github.com/prototypebench/prototypebench/blob/main/PLAN.md#52-오염-대응-contamination-mitigation).

## Usage

```python
from datasets import load_dataset

ds = load_dataset("banyaaiofficial/prototypebench-v1", split="test")

for item in ds:
    print(item["instance_id"])           # e.g. "IBM__mcp-context-forge-4270"
    print(item["problem_statement"])     # NL task spec (PR body or closing issue)
    base_sha = item["base_commit"]        # pre-PR commit — agent starts here
    # Agent produces a non-test unified diff against base_sha.
    # Score it with the companion harness:
    #   pbench score --source <short> --pr <N> --patch-file agent_patch.diff
```

Each instance extends the SWE-Bench `instances.jsonl` schema with dual-test fields (`fail_to_pass.backend` / `.frontend`, `test_patch_backend` / `.frontend`) for future Playwright integration.

Full schema: https://github.com/prototypebench/prototypebench/blob/main/schemas/task_instance.schema.json

## Source Composition

| Source | Stars | License | Instances | F2P | P2P | Stack |
|---|---:|---|---:|---:|---:|---|
| [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) | 42.7k | MIT | 3 | 7 | 77 | backend_only |
| [`IBM/mcp-context-forge`](https://github.com/IBM/mcp-context-forge) | 3.6k | Apache-2 | 68 | 682 | 31,567 | backend_only |
| [`usebruno/bruno`](https://github.com/usebruno/bruno) | 44k | MIT | **52** | **251** | **327** | **frontend_only** (NEW v0.2) |

All PRs are **merged PRs with maintainer-reviewed tests**. Task instances mine the natural atomic unit of change (one feature or fix at a time).

`bruno` frontend instances are validated end-to-end via a Playwright + Electron runner (`harness/frontend_direct_runner.py`) — `docker run` of a custom `prototypebench/playwright-electron` image (Playwright base + GTK/NSS/ATK/Xvfb + chrome-sandbox SUID) that hosts bruno's own `webServer` config in-process. No external backend dependency.

## Data Fields

See the task-schema doc for full field-by-field semantics. Highlights:

- `instance_id` — stable unique ID (`owner__repo-<pr_number>`)
- `base_commit` / `head_commit` — SHAs bounding the reference change
- `problem_statement` — natural-language task spec (from closing issue body, else PR description)
- `patch` — reference solution (non-test diff). **Hidden from the agent at evaluation time.**
- `test_patch` — test-only diff that the harness applies before running the agent's patch
- `fail_to_pass` — `{backend: [...], frontend: [...]}` — tests the agent must make pass
- `pass_to_pass` — `{backend: [...], frontend: [...]}` — regression-guard tests (must not break)
- `stack_domain` — `backend_only` | `frontend_only` | `fullstack`
- `environment` — python_version, node_version, uv_lock_sha, etc. for reproducible builds
- `contamination_tier` — `public` | `held_out` | `internal_only`

## Contamination & Fairness

- **Held-out by construction**: all v0.2 instances are merged after 2026-01-01 (Claude Opus 4.7 cutoff). Submitters must disclose their model cutoff for point-count adjustment.
- **Rotation**: held-out tier is rotated per leaderboard season (Phase 5).
- **No vendor branding**: benchmark carries no vendor name. Hosted on `banyaaiofficial` for convenience only; the benchmark is project-neutral.

## Limitations

- v0.2 adds frontend coverage but no `fullstack` instances yet (single PR touching both backend and frontend in a coordinated way — pending source diversification).
- Two backend sources cover 71 instances; `bruno` covers 52 frontend instances — single-source frontend pool is the current trade-off (see [`PLAN.md` §3.3.1-3.3.2](https://github.com/prototypebench/prototypebench/blob/main/PLAN.md) for the OSS-landscape diagnosis behind it).
- "test strength = benchmark quality": PRs with weak tests are filtered but not perfectly. Curator review recommended.
- Execution-based scoring requires running tests (not instantaneous) — see the harness for Docker-based reproducible runs.
- bruno frontend instances run inside an Electron-capable Playwright image with Xvfb; cold-start (`npm run setup` + workspace builds) adds ~3-5 min per phase. Caching across `base` and `head` phases via Docker named volumes is a v0.3 target.

## Related Benchmarks

- [SWE-Bench](https://www.swebench.com/) — Python library bug-fixes (2,294 instances). PrototypeBench extends the pattern to modern AI-native full-stack apps.
- [SWE-Bench Lite / Verified](https://www.swebench.com/lite.html) — curated subsets.
- [Terminal-Bench](https://www.tbench.ai/) — CLI tasks.
- [BigCodeBench](https://bigcode-bench.github.io/) — library-usage function-level tasks.

## Citation

Citation format will be fixed at Phase 4 public launch. For now:

```
@misc{prototypebench_v02,
  title        = {PrototypeBench v0.2: An AI-native Full-Stack Coding Agent Benchmark},
  year         = {2026},
  url          = {https://github.com/prototypebench/prototypebench},
  note         = {123 instances across 3 source repos (71 backend + 52 frontend);
                  execution-based scoring (pytest + Playwright)}
}
```

## Changelog

- **v0.2** (2026-05-23): +52 frontend_only instances from `usebruno/bruno` via the new `playwright_direct` runner (custom Playwright+Electron image with Xvfb). Corpus 71 → 123. F2P 689 → 940, P2P 31,644 → 31,971. Frontend ratio 0% → 42%. Schema v0.1 unchanged.
- **v0.1** (2026-04-20): initial corpus. 71 backend_only instances, all held_out. Schema v0.1.
