# PrototypeBench — 프로젝트 인수인계 문서

> 이 문서는 신규 프로젝트 디렉토리로 옮겨 cold start 로 이어받을 수 있도록 작성됨.
> 생성 일자: 2026-04-20

---

## 0. TL;DR

**PrototypeBench** 는 AI 에이전트의 **full-stack 제품 개발 능력** 을 평가하는 공개 벤치마크다.
타깃 스택은 **React + Vite + Tailwind + shadcn/ui (프런트)** + **FastAPI + SQLModel + Postgres (백엔드)**.
주 목적은 **Banya 에이전트의 내부 품질 개선 루프**, 공개 리더보드는 부산물.
베이스 태스크 소스는 [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) (MIT, 42.7k stars).

**현재 상태**: 네이밍 확정, GitHub org 확보, `.org` 도메인 확보. 엔지니어링 미착수.
**다음 작업**: 태스크 큐레이션 파이프라인 (§8 Phase 1).

---

## 1. 프로젝트 정체성

| 항목 | 내용 |
|---|---|
| 이름 | **PrototypeBench** |
| 태그라인 | *"Can your agent ship a full-stack AI-native prototype?"* |
| 포지션 | AI-native full-stack agent benchmark |
| 벤치마크 이름 컨벤션 | SWE-Bench / Terminal-Bench 계열 (`-Bench` 접미사) |
| 브랜드 중립성 | Banya 이름은 의도적으로 배제 (공정성 확보) |

---

## 2. 배경 / 존재 이유

### 2.1 왜 이 스택인가

4개 컴포넌트 **모두 각 카테고리 1위** (2024 업계 서베이 기준):

| 컴포넌트 | 지표 | 출처 |
|---|---|---|
| Vite | 사용률 **78.1%**, Webpack 추월 | State of JS 2024 |
| React | 사용률 **82%** (독보적 1위) | State of JS 2024 |
| Tailwind | 사용률 **62%**, 만족도 **81%**, Bootstrap 첫 추월 | State of CSS 2024 |
| FastAPI | 사용률 **38%** (Django 35%/Flask 34% 첫 추월) | JetBrains Python Survey 2024 |
| FastAPI (ML) | **ML 엔지니어 42% 사용** | JetBrains 2024 |

Indeed "fastapi react" 직무 공고 **16,209건** (2025).

### 2.2 왜 이 포지션("AI-native full-stack")인가

- FastAPI 가 ML/AI 엔지니어 사실상 기본값 → "AI-native" 내러티브가 **데이터로 자동 정당화**.
- Next.js+tRPC 진영 (JS 단일언어 풀스택) 과 세그먼트 분리. 경쟁 아님.
- "AI 프로덕트를 만드는 사람들의 스택으로 AI 에이전트를 평가한다" — 서사적 일관성.

### 2.3 차별화 축 (기존 벤치와의 경계)

| 기존 벤치 | 측정 대상 | 한계 (PrototypeBench 가 채움) |
|---|---|---|
| SWE-Bench / SWE-Bench Lite | Django/sympy/flask 등 **성숙 라이브러리 버그픽스** | 모던 스택(FastAPI/Vite/Tailwind) 미커버, 기능 추가/풀스택 통합 평가 부재 |
| FullStackBench (ByteDance, arxiv 2412.00535) | 11개 도메인 일반 코드 품질 | 특정 모던 스택 최적화 X, 프로덕트-레벨 "ship" 평가 X |
| Terminal-Bench | 터미널 CLI 태스크 | 풀스택 제품 빌드 X |
| Web-Bench / WebArena | 브라우저 에이전트 | 코드-생성 에이전트 X |

**PrototypeBench 의 고유 축**: "모던 AI-native 스택" × "프런트↔백 통합 기능 shipping".

---

## 3. 기술 기반

### 3.1 타깃 스택 (v1)

**Frontend**:
- React + TypeScript
- **Vite** (빌드)
- **Tailwind CSS + shadcn/ui**
- TanStack Router / TanStack Query
- Axios (auto-generated OpenAPI client)
- Biome (lint/format) · Bun (pkg mgr)
- **Playwright** (E2E)

**Backend**:
- **FastAPI** + Pydantic v2
- SQLModel · SQLAlchemy
- PostgreSQL + Alembic
- **pytest**
- uv (pkg mgr)

### 3.2 태스크 베이스 repo (multi-source, 2026-05-23 갱신)

PrototypeBench 의 task source 는 **확장 가능한 registry** (`harness/sources/`).
v1 에 등록된 source 는 **세 개** (backend 2 + frontend 1):

#### A. fastapi/full-stack-fastapi-template — primary (full-stack)

| 속성 | 값 |
|---|---|
| Stars | 42,731 (2026-04 기준) |
| License | MIT |
| 스택 일치도 | **완벽** (§3.1 과 동일) |
| Backend | `backend/` · uv workspace · pytest · Postgres |
| Frontend | `frontend/` · React+Vite+Tailwind+shadcn · Playwright |
| CI 테스트 | `test-backend.yml` (pytest) + `playwright.yml` (Playwright) |
| Filter pool (uv-era 이후) | 8 candidates (32 → 8 backend-test 강화 필터) |
| 첫 batch usable rate | 9% (3/32) — 풀스택 차별화 핵심 source |

#### B. IBM/mcp-context-forge — backend-only secondary (2026-04 추가)

| 속성 | 값 |
|---|---|
| Stars | 3,593 |
| License | Apache-2.0 |
| 스택 부분 일치 | Backend 만 — FastAPI + SQLAlchemy 2.x async + Alembic + pytest, **uv extras=[plugins]** |
| Backend dir | repo root (`mcpgateway/` + `tests/`) |
| Postgres 의존 | **없음** (SQLite-by-default conftest, opt-in Postgres) |
| Python | **3.14** (별도 image: `prototypebench/backend-py312:latest`) |
| 머지 PR | **1,645 / yr** (vs fastapi-template 의 ~수십) |
| 첫 batch usable rate | **60%** (3/5 pilot) — 인기 + 활동성이 풀 품질을 지배 |

**B 채택 사유**: §3.3 의 정확-스택-일치 search 가 비었기 때문. backend-only 확장이 풀스택 차별화를 약화시키지 않으면서 pool 을 ×100 수준으로 키움. PLAN §5 fairness 기조 유지 (벤더 중립).

#### C. usebruno/bruno — frontend-emphasis (2026-05-23 추가)

| 속성 | 값 |
|---|---|
| Stars | 44,341 |
| License | MIT |
| 스택 부분 일치 | **Frontend 만** — Electron + React + Tailwind + Playwright + **rsbuild (webpack-compatible, not Vite)** |
| Frontend dir | `packages/bruno-app` (workspace) |
| Backend | Node.js (Express/Fastify) — PrototypeBench 가 평가하지 않음 |
| Test 인프라 | root `playwright.config.ts` + `tests/<domain>/...spec.ts` (auth/onboarding/collection 등 20+ domain) |
| `webServer` | in-process — `npm run dev:web` (rsbuild) + `bruno-tests` mock server (외부 backend 의존성 0) |
| Runner | `frontend_runner_kind="playwright_direct"` — Playwright base + Electron deps + Xvfb (`Dockerfile.playwright-electron`) |
| 머지 PR | **1,185 / yr** |
| top-100 batch usable rate | **83%** (52 exact / 62 frontend signal candidates) |

**C 채택 사유**: OSS landscape 에서 "frontend-only standalone OSS + Playwright + 활성 + clean license + external backend 의존성 없음" 의 교집합이 사실상 부재 (§3.3.2 함정 패턴). bruno 의 Electron + in-process webServer 가 unusual sweet spot. Vite 정체성을 한 칸 양보 (Vite | Webpack | rsbuild) 한 교환으로 frontend pool 0 → 52 instance 확보.

### 3.3 대안 태스크 소스 — 리서치 결과 (2026-04-20)

정확 스택 일치(React+Vite+Tailwind+shadcn / FastAPI+SQLModel+Postgres) OSS 풀스택 앱은 stars>500 기준 **사실상 유일** (`fastapi/full-stack-fastapi-template`).

주요 honorable mentions (§3.2 B 의 채택 근거가 된 후보들):

| Repo | Stars | License | 탈락 사유 |
|---|---|---|---|
| polarsource/polar | 9.7k | Apache-2 | Next.js 프런트, backend test infra가 매우 무거움 (Postgres + Redis + MinIO + Tinybird + email render) |
| evroon/bracket | 1.6k | **AGPL ✗** | redistribution 불가 |
| 0010aor/FlashNotes | 105 | MIT | 17 PR/yr — mineable material 부족 |
| smithyhq/sqladmin | 2.7k | BSD-3 | library (admin templating), 50 PR/yr — 후보 |

차후 Phase 3 이후 **backend 확장 source 1-2 개 추가** (smithyhq/sqladmin 등) + **frontend-only standalone source** (예: shadcn 기반 Vite 앱) 검토.

#### 3.3.1 Frontend source 후속 리서치 (2026-05-23)

정확 일치 OSS 가 거의 부재한 사실이 200-PR 실측으로 확인됨. 정체성을 **"Vite + React + Tailwind + Playwright"** 에서 **"React + Tailwind + Playwright (Vite | Webpack | rsbuild)"** 로 한 칸 양보. AGPL/proprietary 라이선스는 dataset publish 차단 정책 유지.

| Repo | Stars | License | Stack | Frontend test | 평가 |
|---|---:|---|---|---|---|
| usebruno/bruno | 44k | MIT | Electron + rsbuild + Tailwind | Playwright (root) | **채택 ✅** (frontend_runner_kind=playwright_direct, 첫 instance 산출됨) |
| triggerdotdev/trigger.dev | 15k | Apache-2 | Remix + Vite + Tailwind | Playwright (root) | **2순위 ★** — Phase 1+ 등록 후보 |
| appsmithorg/appsmith | 39k | Apache-2 | webpack + Tailwind + Cypress (Playwright 신규) | Playwright 일부 | Cypress 메인이라 task pool 작음. **Java backend 보유 → §3.5 sister 후보** |
| activepieces/activepieces | 22k | MIT (ee/ 제외) | Vite + Tailwind v4 + Radix | Playwright 있으나 PR 비율 0.5% | 채택했으나 yield 0 (probe-only registered) |
| Mintplex-Labs/anything-llm | 60k | MIT | Vite + Tailwind | ❌ Playwright 부재 | 탈락 |
| coollabsio/coolify | 55k | Apache-2 | Vite + Tailwind | ❌ Playwright 부재 | 탈락 |
| documenso/documenso | 12k | AGPL-3.0 | — | — | **라이선스 차단** |
| plane / twenty / AppFlowy / ToolJet / formbricks | — | AGPL/MPL/NOASSERTION | — | — | **라이선스 차단** |
| tldraw/tldraw | 47k | 자체 (production-restricted) | Vite + Playwright | ✅ | dataset publish 불가 |

#### 3.3.2 Mid-tier 후속 검색 — 구조적 함정 패턴 (2026-05-23)

stars 기준을 1k+ → 200~ mid-tier 로 완화 + Vue 까지 명시적 허용한 추가 리서치. 결론: **bruno 가 사실상 유일한 sweet spot**. 4 후보 모두 **production-app 의 external backend 의존성** 또는 **활성도 부족** 함정.

| 후보 | 함정 |
|---|---|
| triggerdotdev/trigger.dev (Apache-2, 15k★, Remix+Vite+Tailwind+Playwright) | `tests/e2e/` 안 spec **1 개뿐** + Postgres + 2 webServer + 3 브라우저 — environment 비용 vs yield 0% |
| saleor/saleor-dashboard (BSD-3, 996★, Vite+React+Radix+Playwright, 777 PR/yr) | `webServer` 부재 → external Saleor backend (Django + Postgres + Redis + Celery + ES + Mailpit) 필요 |
| marktext/marktext (MIT, 56k★, Vue+Electron+Playwright) | **70 PR/yr** — mining 절대량 부족 |
| danny-avila/LibreChat (MIT, 37k★, Next.js+Tailwind+Playwright, 1557 PR/yr) | `start-server.js` 가 **MongoDB** 의존 + e2e PR 1.7%(27/1557) — environment 확장 + yield 모두 비효율 |
| Vue 활성 OSS 전반 (nuxt, element-plus, vue-vben-admin, vueuse, ag-grid, primevue 등) | Vue 생태계가 **Vitest/Cypress 위주** — Playwright 도입 OSS 가 거의 부재 |

**구조적 진단**:

> OSS landscape 에서 **"frontend-only standalone OSS + Playwright + 활성 PR + clean license + external backend 의존성 없음"** 의 교집합이 bruno 외 사실상 부재. mid-tier 검색을 거듭해도 같은 함정 패턴 (Postgres/MongoDB/Redis/Celery/external server 의존성, 또는 PR rate 부족) 이 반복됨. bruno 의 **Electron + in-process webServer + 외부 의존성 0** 조합이 OSS landscape 의 unusual sweet spot.

**v1 frontend pool 전략 확정**: **bruno 단일 source scale up** (1년 전수 crawl 시 ~190-220 instance 도달 가능). marktext/LibreChat 는 **honorable mention** — 환경 인프라 확장 (MongoDB / mongodb-memory-server) 후 v1+ 에서 재검토.

### 3.4 SourceConfig 추상화

새 source 추가는 `harness/sources/<short_name>.py` 한 파일. v0.2 (2026-05-23) 부터 SourceConfig 가 **backend + frontend dispatch** 모두 표현:

```python
register(SourceConfig(
    # --- identity ---
    name="OWNER/REPO",
    short_name="repo-alias",
    repo_url="https://github.com/OWNER/REPO.git",

    # --- backend (Python) — backend_only sources 에 의미, 그 외엔 sentinel ---
    backend_dir="server",                          # or "backend" or "" or sentinel for non-Python
    uv_lock_path="server/uv.lock",
    backend_test_path_re=r"^server/tests/.*\.py$", # or never-match sentinel r"(?!x)x"
    backend_test_path_strip_prefix="server/",
    backend_image="prototypebench/backend-py312:latest",
    python_version="3.12",
    uv_extras=["plugins"],                          # extras filtered to those existing at base commit
    uv_dev=True,
    prestart_steps=[...],
    pytest_extra_args=["-n", "auto"],
    pg_required=True | False,
    pg_env_map={"server": "POSTGRES_SERVER", ...},
    extra_services=[...],
    uv_era_min_merged_at="2026-01-20",              # PR-cutoff for harness compat

    # --- frontend (optional — for sources with Playwright tasks) ---
    frontend_test_path_re=r"^tests/.*\.(spec|test)\.[tj]sx?$",  # filter signal regex
    path_exclude_re=r"^packages/ee/",                # commercial-license carveout drop
    frontend_runner_kind="playwright_direct",        # or "compose" or None
    frontend_dir="packages/bruno-app",
    frontend_docker_image="prototypebench/playwright-electron:v1.51.1",
    frontend_install_cmd=["bash", "-c", "npm run setup && chown root:root ..."],
    frontend_pre_test_cmd=[...],                    # workspace dependent builds (often empty)
    frontend_test_cmd=["npx", "playwright", "test", "--reporter=json"],
    frontend_json_report_path="playwright-report/results.json",
    frontend_test_diff_paths=["tests/**/*.spec.ts", ...],
    frontend_test_diff_strip_prefix="",              # path prefix not visible to Playwright CLI
))
```

`extract` / `score` / `batch-extract` / `filter` / `crawl` / `build-from-extract` 모두 SourceConfig 기반 — multi-source + dual-runner (backend pytest / frontend Playwright {compose | playwright_direct}) 가 native.

**v0.2 등록 source**: [fastapi_full_stack_template.py](harness/sources/fastapi_full_stack_template.py) (compose), [mcp_context_forge.py](harness/sources/mcp_context_forge.py) (backend-only), [bruno.py](harness/sources/bruno.py) (playwright_direct), [activepieces.py](harness/sources/activepieces.py) (probe-only, yield 0).

### 3.5 Sister benchmark — PrototypeBench-Spring (미착수 / 보류)

PrototypeBench 의 v1 정체성 (Python FastAPI 중심) 을 양보하지 않으면서 **Java/Spring Boot 백엔드 평가** 를 별도 trail 로 확장. 결정: **별도 sister repo + 하네스 일부 공유**.

| 항목 | 결정 / 후보 |
|---|---|
| 이름 | `PrototypeBench-Spring` (TBD) |
| Repo | 별도 (`github.com/prototypebench/prototypebench-spring` 예상) |
| 하네스 공유 | 1순위: 현 repo `harness/` 를 git submodule. 2순위 (안정화 후): PyPI `prototypebench-harness` 분리 |
| Test runner | JUnit 5 (Surefire XML) — 기존 `harness/junit.py` 가 호환 |
| Build tool | Maven (`mvn`) 또는 Gradle (`./gradlew`) — `SourceConfig` 에 `language` 분기 필드 추가 필요 |
| Image base | `eclipse-temurin:21-jdk` 추정 |
| 첫 task source 후보 | `appsmithorg/appsmith` (Apache-2, 39k★, app/server = Java 백엔드, 411 PR/yr). v1 launch 이후 정밀 검증 |
| 활성화 조건 | PrototypeBench v1 (Phase 4) launch 완료 + frontend pool 안정화 후 |

PrototypeBench v1 은 정체성 ("AI-native Python+JS stack") 유지. Spring sister 는 별도 narrative ("Enterprise Java agent benchmark") 로 분리 평가.

---

## 4. 확보된 자산 / 확보 필요

| 자산 | 상태 |
|---|---|
| `github.com/prototypebench` | ✅ 확보 |
| `github.com/prototypebench/prototypebench` repo | ✅ public |
| `prototypebench.org` | ✅ 확보 |
| HF dataset `banyaaiofficial/prototypebench-v1` | ✅ **v0.2 publish (2026-05-23, 123 instances, 12.6 MB)** |
| `prototypebench.ai` | ⏳ 방어 확보 권장 (~$80/년) |
| `prototypebench.com` | ⏳ 방어 확보 권장 (~$12/년) |
| `prototypebench.dev` | 옵션 |
| `prototypebench.io` | 옵션 |
| Hugging Face leaderboard 호스팅 (HF Spaces) | 미정 |
| X `@prototypebench` | 미정 (론칭 전 확보) |

---

## 5. 설계 원칙 (타협 불가)

### 5.1 공정성 (Fairness-first)
- Banya 에이전트에 **불리한 태스크도 필수 포함**. 자사 에이전트가 잘 푸는 것만 넣으면 리더보드 신뢰 즉사.
- 브랜드(Banya) 이름이 벤치에 들어가지 않음 (§1).

### 5.2 오염 대응 (Contamination mitigation)
- 베이스 repo 가 MIT 공개라 **프런티어 모델이 PR diff 를 훈련 데이터로 봤을 가능성 매우 높음**.
- 완화책:
  - (a) **cutoff 이후 PR 만** 공개 held-out 셋으로 사용
  - (b) 전체셋은 **내부 dev loop** 전용
  - (c) 버그 주입 / 스펙 변형으로 파생 태스크 생성 (v2)
- 리더보드 제출자의 모델 cutoff 날짜 공개 요구.

### 5.3 투명성
- SWE-Bench / Terminal-Bench 수준의 methodology 문서 v1 론칭 시 필수.
- 오염 대응 · 재현성 · 스코어링 로직 전부 공개.

### 5.4 주 목적 우선순위
1. **내부**: Banya 에이전트 버전 간 상대 시그널 측정
2. **외부**: 공개 리더보드 (부산물)

우선순위가 역전되면 설계 편향 발생. 내부 가치 먼저.

---

## 6. 기각된 네이밍 (재조사 방지)

모두 2026-04-20 조사, **AI eval 도메인 직접 충돌** 확인:

| 이름 | 충돌 원인 |
|---|---|
| `AINative-Bench` | arxiv 2601.09393 (CUHK, Jan 2026) + `AINativeOps/AINativeBench` GitHub + "AI-native" 최상위 버즈워드로 SEO 절망 |
| `StackBench` | [NapthaAI/openstackbench](https://github.com/NapthaAI/openstackbench) (stackbench.ai 활성) + ByteDance FullStackBench |
| `ForgeBench` | arxiv 2504.15185 (Georgia Tech) + ForgeCode (forgecode.dev, Terminal-Bench 2.0 상위) |
| `CraftBench` | craftbench.ai 활성 SaaS (2023-10~), `.com/.ai/.dev/.io` 전부 선점 |
| `FeatureBench` | arxiv 2602.10975 "FeatureBench: Benchmarking Agentic Coding" (ICLR 2026) — **완벽 동명이인** |
| `BlueprintBench` | arxiv 2509.25229 "Blueprint-Bench" (VLM 공간지능 벤치) |
| `DeliveryBench` | arxiv 2512.19234 "DeliveryBench" (VLM 에이전트 벤치, 2025-12) |
| `MissionBench` | arxiv 2504.02623 "Multi-Mission Tool Bench" 인접 + 가구 SEO 노이즈 |
| `ShipBench` | (충돌 미조사, 비영어권 어감 문제로 기각 — "ship=배" 오해) |
| `Banya-Bench` / `Banya-Stack` | 공정성 원칙 위배 (벤더명 포함) |

---

## 7. 경쟁 환경 지도

| 프로젝트 | 도메인 | 우리와의 관계 |
|---|---|---|
| SWE-Bench / SWE-Bench Lite | Python 라이브러리 버그픽스 | 상위 카테고리 내 **보완재** (다른 축) |
| Terminal-Bench | 터미널 CLI | 카테고리 다름, 네이밍 컨벤션만 참고 |
| LiveBench | LLM 멀티태스크 | 모델 평가 vs 에이전트 평가 — 층위 다름 |
| FullStackBench (ByteDance) | 일반 풀스택 코드 품질 | **가장 가까운 경쟁**, 차별점은 "모던 특정 스택 + 프로덕트 ship" |
| AINativeBench | 에이전틱 시스템 + MCP/A2A | 추상화 레벨 다름 (인프라 vs 제품) |
| NapthaAI StackBench | AI 에이전트의 라이브러리/문서 사용 능력 | 과업 유형 다름 |
| WebArena / WebBench | 브라우저 에이전트 | 카테고리 다름 |

---

## 7.5 진행 상황 (2026-05-23 갱신)

| Phase | 항목 | 상태 |
|---|---|---|
| **1** | **태스크 큐레이션 파이프라인** | **✅ 완료** |
| 1 | repo 생성, 스키마 v0.1, validator | ✅ |
| 1 | PR 크롤러 (multi-source) | ✅ |
| 1 | filter (kind 라우팅 + uv-era cutoff + path_exclude_re) | ✅ |
| 1 | seed 큐레이션 → instance 자동 빌드 | ✅ **123 / 40-60** (목표 3배 초과) — fastapi-template 3 + mcp-context-forge 68 + bruno 52 (frontend) |
| **2** | **평가 하네스 (Phase 2 코어 + frontend extension)** | **✅ 완료** |
| 2 | 하네스 architecture doc | ✅ |
| 2 | Backend FAIL_TO_PASS extractor (Docker) | ✅ |
| 2 | Agent runner v1 (patch submission, 3-scenario validated) | ✅ |
| 2 | Collection-error fallback | ✅ (#2104 검증) |
| 2 | Frontend Playwright runner — compose stack (fastapi-template) | ✅ (#2146 검증) |
| 2 | SourceConfig 추상화 (multi-source) | ✅ (mcp-context-forge 검증) |
| 2 | effective_uv_extras (extras lifecycle 대응) | ✅ |
| 2 | batch validator + per-source artifact dir | ✅ |
| 2 | build-from-extract → instances JSONL | ✅ |
| 2 | **SourceConfig frontend dispatch** (compose / playwright_direct / None) | ✅ (2026-05-23, bruno end-to-end) |
| 2 | **frontend_direct_runner.py** (single-image npm + playwright) | ✅ (2026-05-23) |
| 2 | **Dockerfile.playwright-electron** (Xvfb + GTK/NSS/ATK for Electron e2e) | ✅ (2026-05-23) |
| 2 | **build_from_extract kind-aware** (frontend bucket + source-driven globs) | ✅ (2026-05-23) |
| 3 | 모델 평가 자동화 | ⏳ |
| 4 | 공개 리더보드 (HF dataset 만 선행 완료) | ⏳ (`banyaaiofficial/prototypebench-v1` published) |
| 5 | 지속 운영 (held-out rotation, contribution guide) | ⏳ |

**현재 instance pool**: **123 task** (Phase 1 목표 40-60 의 ~2-3 배 초과)

| Source | License | Instances | F2P 합 | P2P 합 | Stack |
|---|---|---:|---:|---:|---|
| fastapi-template | MIT | 3 | 7 | 77 | backend_only |
| mcp-context-forge | Apache-2 | 68 | 682 | 31,567 | backend_only |
| **bruno** | MIT | **52** | **251** | **327** | **frontend_only** (NEW 2026-05-23) |
| activepieces (probe-only) | MIT/ee 제외 | 0 | — | — | yield 0 확인 |

**bruno top-100 batch 결과** (2026-05-23): 처리 62 PR (frontend signal 있는 candidate). exact 52 / test_only 6 / error 2 (timeout) / no_signal 2 = **83% usable rate**. F2P 분포 풍부 (단일 PR F2P 1~12). 가장 큰 PR: #7947 "fix: persist scroll for assertions" F2P=12.

**Stack domain 분포**: backend_only 71 / frontend_only 52 (frontend ratio **42%** — §10.1 한계가 완전히 해소되어 backend ↔ frontend 비율 안정)

테스트 자산 (full eval):
- F2P 940 · P2P 31,971 · 총 **32,911** individual test cases

**Source 등록 상태**:
- ✅ fastapi-template (compose-mode frontend runner)
- ✅ mcp-context-forge (backend-only)
- ✅ bruno (playwright_direct runner, electron base image)
- ✅ activepieces (probe-registered, frontend mining yield ≈ 0)
- 🔜 trigger.dev (2순위 후보, §3.3.1)

→ Phase 1·2 모두 **완료**. SWE-Bench Lite (300) 의 ~24% 수준. 다음 → Phase 3 (모델 평가).

---

## 8. 다음 작업 (Phase 별)

### Phase 1 — 태스크 큐레이션 파이프라인 ✅ 완료

**목표**: PR 40~60개를 재현 가능한 태스크 번들로 변환 → **72 instances 달성**.

- [x] `github.com/prototypebench/prototypebench` 메인 repo 생성
- [x] 태스크 스키마 설계 (`schemas/task_instance.schema.json`, v0.1):
  - `instance_id`, `repo`, `base_commit` / `head_commit`
  - `problem_statement`, `patch`, `test_patch` (+ `test_patch_backend` / `test_patch_frontend`)
  - `fail_to_pass` / `pass_to_pass` (`{backend, frontend}` 이중 bucket)
  - `environment` (python/node version, uv/bun lock SHA, docker compose SHA)
  - `stack_domain`, `contamination_tier`, `schema_version`
- [x] PR 크롤러 스크립트 (`scripts/crawl_prs.py`) — multi-source registry 기반
  - dependabot / chore / docs PR 필터링
  - 테스트 파일 수정 포함 PR 우선 (kind 라우팅)
  - closing issue 자동 링크
- [x] 10개 seed 태스크 수동 큐레이션 (`tasks/drafts.jsonl`)
- [x] 자동화 확장 → 72 instance (3 fastapi-template + 68 mcp-context-forge + 1 bruno)

**산출물**: `tasks/instances.*.jsonl` (3 sources) + `dataset/instances.jsonl` (HF publish ready)

### Phase 2 — 하네스 (runner) ✅ 완료

**목표**: 태스크를 실제로 에이전트에게 주고 채점하는 자동화.

- [x] PrototypeBench 전용 runner 작성 (`harness/`):
  - backend: pytest junitxml extractor (Docker compose-based)
  - frontend (compose mode): fastapi-template 의 compose stack
  - frontend (playwright_direct mode): single-image npm + playwright (bruno)
- [x] 차이점 대응:
  - 이중 테스트 (pytest + Playwright) 실행
  - docker-compose 기반 DB/백/프런트 동시 기동
  - 프런트 빌드 타임 이슈 (Playwright webServer 대기 / Xvfb / Electron deps)
- [x] 스코어링 (`harness/score.py`): F2P 전체 통과 + P2P 미회귀 → 1, 그 외 0
- [x] 태스크당 trace (logs/, summary.json) 저장 — 실패 triage 표준화

### Phase 3 — 내부 베타 ⏳ 진행 예정 (next)

#### 3.0 평가 인터페이스 결정 (2026-05-23, 채택)

**결정**: Phase 3 부터 **agent-loop interface 우선** 채택. v1 spec 의 patch-submission 은 backward-compat 으로만 유지.

**근거** — 2026-05-23 smoke test (`IBM/mcp-context-forge#3284`, F2P=1):
- (A) 하네스 sanity (정답 patch → score): ✅ score=1, F2P 1/1, P2P 6/6 (3 분)
- (B) Claude CLI `--print` nested (problem + 코드 excerpt → diff): ⚠ 의미적 정답 100% 일치, but **`git apply` "corrupt patch at line 12"** — context line whitespace / hunk header line-count 의 byte-exact mismatch 로 score=0

→ patch-submission 은 모델의 *의미 능력* 외에 *unified-diff format reproduction* 까지 요구하는 strict interface. frontier model 도 한 줄 변경에서 byte-exact diff 못 만듦. **모델의 "코드 작성" 능력과 "텍스트 diff serialize" 능력을 섞어서 측정** → noise.

**Agent-loop interface 의 모양** (Phase 3 구현):
- 에이전트에게 작업용 repo 디렉토리를 마운트 (e.g. `claude --add-dir /tmp/pbench/<instance>/repo` 같은 형태)
- 에이전트가 `Read`/`Edit`/`Bash(git *)` 등 tool 사용하며 file 을 직접 수정
- 종료 후 하네스가 `git diff` 를 자동 추출 → 그 diff 로 score 채점
- 결과: format byte-exact 자동 보장 + agent 의 실제 코드 편집 능력만 측정

**v1 patch-submission 은 유지**: SWE-Bench 호환 외부 제출자가 그 길로도 채점 가능하게. dual interface.

#### 3.1 모델 평가 작업

- [ ] Agent-loop runner 작성 (`harness/agent_loop_runner.py`) — `claude --add-dir` / Anthropic SDK with tool-use / Gemini equivalent 의 3 backend
- [ ] Banya 에이전트 v N / v N-1 비교 평가
- [ ] 3~5개 프런티어 모델 평가 (Claude Opus 4.7, Sonnet 4.6, GPT-5, Gemini 3 등)
- [ ] 비용 추정 필요 (123 태스크 × 5 모델 × 에이전트 루프 ≈ 수천 달러/회차)
- [ ] 태스크별 실패 분석 → 태스크 품질 개선 (너무 쉬움/모호함/테스트 부실 제거)

### Phase 4 — 공개 베타 ⏳

론칭 채널 · 메시지 · KPI 등 종합 전략은 [`docs/launch-strategy.md`](docs/launch-strategy.md).

- [ ] `.ai` / `.com` 도메인 방어 확보
- [ ] 리더보드 사이트 (`prototypebench.org`) — 기술 선택 필요 (단순 static 이면 Astro + GitHub Pages 무난)
- [ ] Methodology 문서 공개 (`docs/evaluation-procedure.md` 초안 ✅)
- [ ] 제출 양식 / 재현성 요구사항 정의
- [ ] Social preview image (1280×640 PNG)
- [ ] CONTRIBUTING.md / CODE_OF_CONDUCT.md / issue templates (GitHub Community Standards)
- [ ] GitHub Releases v1.0.0 — 첫 공식 corpus + harness snapshot
- [x] Hugging Face dataset publish (`banyaaiofficial/prototypebench-v1`) — commit 32e72d7
- [ ] HF Spaces leaderboard mirror
- [ ] Hacker News 론칭 포스트 (Show HN, 화요일 PT 오전)
- [ ] Newsletter pitch (Latent Space, AlphaSignal, TLDR AI, Import AI)
- [ ] Twitter launch thread (8-12 tweets)
- [ ] awesome-list PR 침투 (`awesome-llm-eval`, `awesome-coding-llm`, `awesome-fastapi` 등)

### Phase 5 — 지속 운영 ⏳

- [ ] 분기별 태스크 셋 업데이트 (오염 방지 + 신규 PR 반영)
- [ ] held-out 셋 로테이션
- [ ] 기여 가이드 (외부 태스크 제안 수용)
- [ ] (§3.5 참조) PrototypeBench-Spring sister benchmark 부트스트랩

---

## 9. 열린 결정 사항 (다음 세션에서 판단)

- **태스크 스키마 최종형**: SWE-bench 포맷 그대로 vs full-stack 전용 확장 (테스트 이중화 필드 등).
- **스코어링 모델**: pass/fail 이진 vs partial credit (프런트만 맞고 백엔드 실패 같은 케이스).
- **cutoff 날짜**: 어느 모델 cutoff 기준으로 held-out 셋 나눌지. Claude Opus 4.7 cutoff (2026-01) 기준 제안.
- **리더보드 제출 방식**: fork + PR (SWE-bench 방식) vs 중앙 API (편의성).
- **에이전트 평가 비용 budget**: 회차당 예산 상한.
- **Hugging Face 리더보드 호스팅 여부**: 노출 크지만 자체 사이트 통제성 희생.
- **공개 홍보 타이밍**: 20개 태스크 beta 시 공개 vs 전체 완성 후.

---

## 10. 레퍼런스

### 주 소스
- [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)
- [State of JS 2024 — Build Tools](https://2024.stateofjs.com/en-US/libraries/build_tools/)
- [State of JS 2024 — Front-end Frameworks](https://2024.stateofjs.com/en-US/libraries/front-end-frameworks/)
- [State of CSS 2024 — Usage](https://2024.stateofcss.com/en-US/usage/)
- [JetBrains Python Developers Survey 2024](https://lp.jetbrains.com/python-developers-survey-2024/)

### 경쟁 벤치마크
- [SWE-bench](https://www.swebench.com/) / [SWE-bench Lite](https://www.swebench.com/lite.html)
- [Terminal-Bench](https://www.tbench.ai/)
- [FullStackBench (ByteDance, arxiv 2412.00535)](https://arxiv.org/abs/2412.00535)
- [LiveBench](https://livebench.ai/)

### 기존 Banya 하네스 (참고용, 독립 프로젝트로 분리 예정)
- `banya-framework/agent-evaluation/` — SWE-bench adapter, LCB adapter

---

## 11. 인수인계 체크리스트 (다음 세션 시작 시)

### 2026-05-23 마무리 시점 — 현 상태

- [x] PrototypeBench repo, schema, 큐레이션 파이프라인, 평가 하네스 모두 완료 (Phase 1·2 ✅)
- [x] 코퍼스 **123 instances** (71 backend + 52 frontend), HF dataset v0.2 publish 완료
- [x] SourceConfig 의 backend + frontend dual-runner 추상화 완료 (4 sources 등록)
- [x] Phase 3 의 평가 인터페이스 결정: **agent-loop 우선** (smoke test §8 Phase 3.0 근거)

### 다음 세션 진입점

- [ ] **Phase 3.1 첫 작업** — `harness/agent_loop_runner.py` 작성 (3-backend: Claude CLI `--add-dir` / Anthropic SDK tool-use / Gemini equivalent)
- [ ] 비용 추정: 123 × 5 모델 × agent loop = 수천 USD/회차 — budget 결정 필요 (§9 의 "에이전트 평가 비용 budget")
- [ ] 첫 model shootout 시도 (single instance + Claude Opus 4.7 agent-loop) — sanity 통과 후 batch
- [ ] (선택) bruno scale up 더 (top-300 또는 1년 전수, +50~150 frontend instance)
- [ ] (선택) trigger.dev / saleor / marktext / LibreChat 의 honorable mention 환경 인프라 추가 검토 (§3.3.2)

### 보류 트랙

- [ ] (§3.5) PrototypeBench-Spring sister benchmark 부트스트랩 — v1 launch 후
- [ ] (§9) cutoff 날짜, partial credit, 리더보드 제출 방식 등 잔여 결정사항

### 즉시 회수 가능한 단편 산출물

- 평가 procedure 운영 reference: [docs/evaluation-procedure.md](docs/evaluation-procedure.md)
- 평가 procedure plain-language 블로그: [docs/evaluation-procedure-blog.md](docs/evaluation-procedure-blog.md)
- Slack 보고 스크립트 (단발 + 2h loop): [scripts/notify_slack.py](scripts/notify_slack.py)
- HF publish 스크립트: [scripts/publish_hf.py](scripts/publish_hf.py)

---

*Generated from Banya-framework planning session, 2026-04-20. Updated 2026-05-23 after frontend pool / agent-loop interface adoption.*
