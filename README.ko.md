<p align="right">
  <a href="README.md">English</a> · <b>한국어</b>
</p>

# PrototypeBench

> **Can your agent ship a full-stack AI-native prototype?**

![phase](https://img.shields.io/badge/phase-3%20active-green)
![corpus](https://img.shields.io/badge/corpus-123%20tasks-blue)
![dataset](https://img.shields.io/badge/HF-v0.2.2-yellow)
![license](https://img.shields.io/badge/license-MIT-blue)
![stack](https://img.shields.io/badge/stack-React%20%2B%20Vite%20%2B%20Tailwind%20%7C%20FastAPI%20%2B%20SQLModel-black)

PrototypeBench는 AI 코딩 에이전트의 **풀스택 제품 개발 능력**을 평가하는 공개 벤치마크입니다. SWE-Bench가 "성숙한 Python 라이브러리에서의 버그픽스"를 측정한다면, PrototypeBench는 **"현대적 AI-native 스택에서 풀스택 기능을 ship 할 수 있는가"** 를 측정합니다.

- **📦 Hugging Face 데이터셋**: [`banyaaiofficial/prototypebench-v1`](https://huggingface.co/datasets/banyaaiofficial/prototypebench-v1) — **123 instances** (v0.2.2, 71 backend + 52 frontend), MIT, `datasets.load_dataset(...)` 바로 사용 가능.
- **태스크 소스** (multi-source via `harness/sources/`):
  - [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) — MIT, 42.7k★ — 풀스택 템플릿 (React+Vite+Tailwind+shadcn / FastAPI+SQLModel+Postgres). backend 3건.
  - [`IBM/mcp-context-forge`](https://github.com/IBM/mcp-context-forge) — Apache-2, 3.6k★ — FastAPI MCP gateway, **연 1,645 PR**, hermetic SQLite 테스트. backend 68건.
  - [`usebruno/bruno`](https://github.com/usebruno/bruno) — MIT, 44k★ — Electron + React + Tailwind + Playwright API client, 연 1,185 PR. **frontend 52건** — `playwright_direct` runner (자체 Playwright + Xvfb + Electron 의존성 image).
- **스코어링**: `FAIL_TO_PASS` 전체 통과 + `PASS_TO_PASS` 미회귀 = 1점 (이진). pytest + Playwright 이중 러너. snapshot test 는 P2P-advisory 분류 ([`docs/phase3-fe-smoke-analysis.md`](docs/phase3-fe-smoke-analysis.md) 참조).
- **Judge**: execution-based (LLM-as-judge 안 씀) — 정답 = 실제 머지된 PR diff, 채점은 테스트 실행.
- **포맷**: SWE-Bench `instances.jsonl` 과 호환되는 확장 스키마 — 기존 툴체인 재사용 가능.
- **Phase 3 평가 인터페이스** (2026-05-23 채택): **agent-loop** 우선 — 하네스가 repo 를 마운트하고 응시자의 에이전트가 tool 로 file 을 편집한 뒤 하네스가 `git diff` 로 결과 추출해 채점 (프런티어 모델의 byte-exact diff serialization 문제 우회). [`PLAN.md` §5.5](PLAN.md) — 하네스는 task spec + score 만, agent 설계는 응시자 자유.

## Why this stack?

각 컴포넌트는 2024 업계 서베이 기준 자기 카테고리 1위입니다.

| | Share | Source |
|---|---|---|
| **React** | 82% (독보적 1위) | State of JS 2024 |
| **Vite** | 78.1% (Webpack 추월) | State of JS 2024 |
| **Tailwind CSS** | 62% (Bootstrap 첫 추월) | State of CSS 2024 |
| **FastAPI** | 38% (Django/Flask 첫 추월), ML 엔지니어 42% | JetBrains Python Survey 2024 |

Indeed "fastapi react" 직무 공고 16,209건 (2025). AI 제품을 만드는 사람들의 스택에서 AI 에이전트를 평가한다는 서사.

## What's in a task

각 태스크는 하나의 실제 merged PR에서 도출된 JSON 객체입니다. SWE-Bench 포맷에 **풀스택 이중 테스트** 확장이 더해졌습니다.

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

전체 스키마: [`schemas/task_instance.schema.json`](schemas/task_instance.schema.json) · [`docs/task-schema.md`](docs/task-schema.md).

## Status

| Phase | 상태 |
|---|---|
| 1 · 태스크 큐레이션 파이프라인 | ✅ **123 task instances** — 풀 목표 (40-60) 2배 초과 |
| 2 · 평가 하네스 (pytest + Playwright + Docker, multi-source) | ✅ Backend (Docker pytest) + Frontend (compose / playwright_direct) + score scoping (85% 단축) |
| 3 · 내부 베타 (모델 비교) | 🟢 **진행 중** — reference agent-loop runner + `agent-score` CLI 완료; 첫 20-instance smoke 완료 |
| 4 · 공개 리더보드 | ⏳ |
| 5 · 지속 운영 | ⏳ |

**현재 corpus** (2026-05-24, dataset v0.2.2):

| 지표 | 값 |
|---|---:|
| Task instances | **123** |
| Source 수 | 3 (`fastapi/full-stack-fastapi-template`, `IBM/mcp-context-forge`, `usebruno/bruno`) |
| `stack_domain` 분포 | 71 backend_only + 52 frontend_only |
| `FAIL_TO_PASS` 테스트 합 | **940** |
| `PASS_TO_PASS` regression-guard 테스트 합 | **31,945** (snapshot test 는 P2P-advisory) |
| 1회 평가 시 실행되는 개별 테스트 수 | **32,885** |
| 스키마 검증 통과 | 123 / 123 |

비교: SWE-Bench Verified 500, SWE-Bench Lite 300, HumanEval 164. v1 공개 베타 목표는 200-300 instance (`public` / `held_out` / `internal_only` 분리).

**첫 multi-instance smoke** (Claude Opus 4.7, reference Claude-CLI agent-loop runner, 2026-05-23~24): backend 5/10 = 50%, frontend 1/10 = 10%, **6/20 = 30%** binary; ~46% partial-weighted. 실패 분석은 [`docs/phase3-fe-smoke-analysis.md`](docs/phase3-fe-smoke-analysis.md), 진행 로그는 [`PLAN.md` §8.3](PLAN.md).

Phase 4 공개 론칭 전까지 리더보드 제출은 열리지 않습니다. 설계 원칙과 전체 로드맵은 [`PLAN.md`](PLAN.md).

## Fairness & contamination

공개 벤치마크의 신뢰는 두 축에 달려있습니다:

1. **공정성** — 운영 조직의 에이전트에게 불리한 태스크도 필수 포함. 벤치 이름에 벤더 이름 배제.
2. **오염 방어** — 베이스 repo가 MIT 공개라 프런티어 모델이 학습 데이터로 접했을 가능성이 높습니다.
   태스크를 cutoff 기준으로 `public` / `held_out` / `internal_only` 티어로 분리 운영. held-out 셋은 시즌 단위 로테이션.
   리더보드 제출 시 모델 cutoff 공개가 요구됩니다.

## Quick start

### Prerequisites

- Python 3.11+, [`uv`](https://docs.astral.sh/uv/)
- [`gh` CLI](https://cli.github.com/) (GitHub 인증 — crawl/filter 시에만 필요)
- Docker (backend pytest + Playwright/Electron 러너 격리)
- (선택, reference agent-loop runner 용) Claude Code CLI (`claude`)

### Install

```bash
git clone https://github.com/prototypebench/prototypebench.git
cd prototypebench
uv sync
```

### 에이전트 평가 (응시자 path)

하네스의 public contract 은 **task spec + score**. agent (system prompt / tool / multi-turn / planning) 는 응시자 영역 ([PLAN.md §5.5](PLAN.md)). 두 contract 인터페이스 지원:

**A. Patch submission** (SWE-Bench 호환 — back-compat)
```bash
# Prereq: instance 다운로드, extract 한 번 (work_dir seed), 그 다음 score:
uv run pbench score --source mcp-context-forge --pr 3284 \
    --patch-file solution.patch
```

**B. Agent loop** (Phase 3 primary — byte-exact diff serialization 우회)
Reference runner 는 Claude CLI 사용; 응시자는 보통 자기 runner 로 교체.
```bash
uv run pbench agent-score --source mcp-context-forge --pr 3284 \
    --model claude-opus-4-7 --timeout 600
# → instance 의 repo 마운트 → agent 실행 → 하네스가 `git diff` 추출 → 채점
```

### 태스크 큐레이션 (maintainer path)

```bash
# 1. merged PR 크롤 → raw/<source>/prs.jsonl
uv run pbench crawl   --source fastapi-template
uv run pbench crawl   --source mcp-context-forge
uv run pbench crawl   --source bruno

# 2. 필터 + 스코어 → raw/<source>/candidates.jsonl
uv run pbench filter  --source bruno

# 3. 후보 분포 확인 (--kind backend | frontend | fullstack | any)
uv run pbench top     --source bruno --kind frontend --n 20

# 4. base/head 에서 테스트 실행해 FAIL_TO_PASS / PASS_TO_PASS 자동 추출
#    (Docker; --kind backend = pytest, --kind frontend = Playwright)
uv run pbench batch-extract --source bruno --kind frontend --top 10

# 5. usable 결과를 스키마 준수 instance 로 변환
uv run pbench build-from-extract --source bruno --kind frontend

# 6. 스키마 검증
uv run pbench validate -p tasks/instances.bruno.jsonl
```

CLI 도움말: `uv run pbench --help`.

### 새 task source 추가

`harness/sources/<short_name>.py` 에 `SourceConfig` 등록 한 줄. backend dir,
uv-lock 위치, prestart 명령, postgres env-var 매핑, extras, image tag 등을
정의하면 다른 모듈 변경 없이 동작합니다. SQLite-only 최소 예시는
[`harness/sources/mcp_context_forge.py`](harness/sources/mcp_context_forge.py).

## Repo layout

```
prototypebench/
├── PLAN.md                      # 프로젝트 헌장 (원칙 · 경쟁 지도 · 로드맵)
├── schemas/
│   └── task_instance.schema.json
├── docs/
│   ├── task-schema.md           # 스키마 필드별 해설
│   └── seed-curation.md         # 수동 큐레이션 체크리스트
├── scripts/                     # `pbench` CLI 구현
│   ├── cli.py
│   ├── crawl_prs.py
│   ├── filter_prs.py
│   ├── build_instance.py
│   └── validate.py
├── tasks/
│   └── instances.jsonl          # 최종 태스크 번들 (큐레이션 산출물)
└── raw/                         # 크롤러 중간 산출물 (gitignored)
```

## Contributing

Phase 1에서는 **태스크 품질**이 곧 벤치마크 신뢰도입니다. 환영하는 기여:

- `docs/seed-curation.md` 체크리스트 개선 제안
- 태스크 스키마 v0.2 의견 ([`docs/task-schema.md`](docs/task-schema.md) 마지막 섹션)
- 필터 휴리스틱 튜닝 (`scripts/filter_prs.py`)
- 새로운 seed 태스크 제안 (베이스 repo의 특정 PR 링크 + `notes` 초안)

프로세스 성숙 전까지는 Issue로 논의를 시작해주세요.

## References

- [SWE-Bench](https://www.swebench.com/) · [Terminal-Bench](https://www.tbench.ai/) · [FullStackBench (arxiv 2412.00535)](https://arxiv.org/abs/2412.00535) · [LiveBench](https://livebench.ai/)
- [State of JS 2024](https://2024.stateofjs.com/) · [State of CSS 2024](https://2024.stateofcss.com/) · [JetBrains Python Survey 2024](https://lp.jetbrains.com/python-developers-survey-2024/)

## License

MIT. 베이스 repo인 `fastapi/full-stack-fastapi-template` 또한 MIT.

## Cite

Phase 4 공개 론칭 시 인용 형식이 확정됩니다.
