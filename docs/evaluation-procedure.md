# PrototypeBench 평가 프로시저 — 기술 문서

> **목적**: 본 문서는 PrototypeBench가 코드 에이전트의 성능과 품질을 어떤 절차로 평가하는지에 대한 기술 사양을 정리한다.
> 본 문서는 `PLAN.md`, `README.md`, `docs/harness-architecture.md`, `docs/task-schema.md`, `docs/seed-curation.md`, `docs/launch-strategy.md`, `dataset/README.md` 의 내용을 종합한 운영 레퍼런스다.
>
> **버전**: v0.1 기준 (corpus 71 instances, schema 0.1)
> **작성일**: 2026-05-22

---

## 0. TL;DR — 한 문장 평가 정의

> PrototypeBench는 실제 머지된 OSS PR을 태스크로 변환한 뒤, 에이전트가 생성한 patch가 **(a)** 해당 PR이 새로 도입한 테스트(`FAIL_TO_PASS`)를 통과시키면서 **(b)** 기존에 통과하던 테스트(`PASS_TO_PASS`)를 깨뜨리지 않는지를 **실제 pytest/Playwright 실행**으로 판정한다. 결과는 태스크당 0/1 이진 점수다.

핵심 특성:

- **LLM-as-judge 사용 안 함**. 채점은 전적으로 테스트 실행 결과에 기반(execution-based).
- **정답** = 실제로 머지된 PR diff. 큐레이터가 임의로 작성한 정답이 아님.
- **하네스와 큐레이션이 동일한 실행 코어를 공유**. 평가 시 적용되는 환경 = 큐레이션 시 사용된 환경.

---

## 1. 평가 파이프라인 전체 구조

평가는 크게 두 단계로 나뉜다.

```
        ┌──────────────────────────────┐         ┌──────────────────────────────┐
        │  Task Curation Pipeline      │         │   Agent Evaluation Pipeline  │
        │  (한 번만 실행, 코퍼스 생성)  │  ──→    │   (에이전트 평가 시 매번)      │
        └──────────────────────────────┘         └──────────────────────────────┘
        crawl → filter → batch-extract             score (patch ↔ instance)
              → build → validate
```

| 단계 | 누가 실행 | 산출물 | 빈도 |
|---|---|---|---|
| 큐레이션 (§2) | 벤치마크 운영자 (curator) | `tasks/instances.<source>.jsonl` (=배포 태스크 코퍼스) | 코퍼스 빌드/리프레시 시점 |
| 에이전트 평가 (§3) | 모델 / 에이전트 평가자 | 인스턴스당 score ∈ {0, 1}, trace 로그 | 모델/에이전트 변경 시점 |

두 단계는 **동일한 실행 코어 (Docker compose 기반 테스트 러너)** 를 공유한다(`docs/harness-architecture.md` D3). 추출기와 채점기는 **같은 머신, 다른 입력 세트**다.

---

## 2. 태스크 큐레이션 프로시저 (코퍼스 생성)

평가의 신뢰는 입력 코퍼스의 품질에 종속된다. 큐레이션은 7단계로 구성되며, 모든 단계가 `harness/sources/<short_name>.py` 의 `SourceConfig`를 기반으로 source-agnostic하게 동작한다.

### 2.1 Step 1 — 크롤(crawl)

```bash
uv run pbench crawl --source <short_name>
```

- GitHub `gh pr list` API로 머지된 PR 메타데이터를 수집해 [raw/<source>/prs.jsonl](../raw/) 에 저장.
- 필드: PR number, base/head SHA, title, body, labels, mergedAt, closing issue, file diffs 등.

### 2.2 Step 2 — 필터 + 휴리스틱 스코어링(filter)

```bash
uv run pbench filter --source <short_name>
```

각 PR을 다음 기준으로 점수화 및 분류한다(`scripts/filter_prs.py`):

| 필터 | 작용 |
|---|---|
| dependabot / docs-only / typo | 제외 |
| 테스트 파일 수정 없음 (no test signal) | `no_signal` 로 분류, 코퍼스 제외 |
| 테스트 파일만 수정 (test-only) | `test_only` 로 분류, 코퍼스 제외 |
| Pre-uv-era PR (`mergedAt < 2026-01-20`) | 제외 (extractor가 `uv.lock`을 가정함) |
| `backend/` 만 수정 | `backend_only` 후보 |
| `frontend/` 만 수정 | `frontend_only` 후보 |
| 둘 다 수정 | `fullstack` 후보 |
| 정답이 자명, 스펙이 제약적 | 가산점 |

산출물: `raw/<source>/candidates.jsonl` (kind 라벨 + 점수 부여됨).

### 2.3 Step 3 — 분포 확인(top)

```bash
uv run pbench top --source <short_name> --kind backend --n 20
```

`--kind ∈ {backend, frontend, fullstack, any}` 로 후보 풀의 분포를 점검한다. seed curation guide(`docs/seed-curation.md`)는 backend_only 3 / frontend_only 2 / fullstack 4 / held_out 1+ 구성을 권장한다.

### 2.4 Step 4 — `FAIL_TO_PASS` / `PASS_TO_PASS` 자동 추출(batch-extract)

여기서부터가 평가 신호의 생성 단계다.

```bash
uv run pbench batch-extract --source <short_name> --top 10
```

각 PR마다 다음을 수행한다(`docs/harness-architecture.md` Extraction pipeline 절):

```
1.  clone base repo → /tmp/pb-<instance_id>/repo
2.  git checkout <base_commit>
3.  git apply <test_patch>                  ← 테스트 파일만
4.  build/reuse 이미지  prototypebench/backend:<uv_lock_sha>
5.  compose up -d db                         ← Postgres (필요시)
6.  docker run backend pytest --junitxml  → base_tests.xml
7.  git reset --hard <base_commit>
8.  git checkout <head_commit>               ← 정답 상태
9.  docker run backend pytest --junitxml  → head_tests.xml
10. 집합 연산:
        FAIL_TO_PASS = { t | t.fails(base) AND t.passes(head) }
        PASS_TO_PASS = { t | t.passes(base) AND t.passes(head) } \ FAIL_TO_PASS
11. (frontend) bun run test:e2e --reporter=json   ← Playwright runner
12. compose down -v
13. raw/extract/<instance_id>/{base.xml, head.xml, frontend.json, summary.json}
```

**핵심 불변식**: `FAIL_TO_PASS`는 “PR이 새로 도입한, 정답 patch가 통과시키는 테스트”이며, `PASS_TO_PASS`는 “PR이 깨뜨리지 않은 회귀 가드 테스트”다.

### 2.5 Step 5 — instance 변환(build-from-extract)

```bash
uv run pbench build-from-extract --source <short_name>
```

추출 결과 + PR 메타 + 환경 해시(`uv_lock_sha`, `bun_lock_sha`, `docker_compose_sha`) 를 합쳐 [task_instance.schema.json](../schemas/task_instance.schema.json) 준수 JSON 객체를 생성, `tasks/instances.<source>.jsonl` 에 append한다.

### 2.6 Step 6 — 스키마 검증(validate)

```bash
uv run pbench validate -p tasks/instances.<source>.jsonl
```

- `required` 필드 누락, 패턴 위반, F2P/P2P 둘 다 empty인 인스턴스 등 거부.
- 현재 코퍼스: 71/71 schema valid.

### 2.7 Step 7 — 오염 티어 지정

PR `created_at` 과 대상 모델의 cutoff 를 비교해 자동 지정(`docs/seed-curation.md` §8):

| `created_at` | tier |
|---|---|
| 모든 대상 모델 cutoff 이전 | `public` |
| 어떤 모델 cutoff 이후 (예: Claude Opus 4.7 cutoff = 2026-01-01) | `held_out` |
| GitHub trending 등 유명 이슈 | `internal_only` (수동) |

v0.1에서는 71 instance 전부 `held_out` (모두 2026-01-01 이후 머지).

---

## 3. 에이전트 평가 프로시저 (스코어링)

태스크 코퍼스가 준비되면, 에이전트는 인스턴스 단위로 평가된다.

### 3.1 에이전트 인터페이스 v1: Patch submission

PrototypeBench v1은 **tool-use agent loop를 직접 구동하지 않는다.** 에이전트가 외부에서 생성한 unified diff를 입력으로 받는다(`docs/harness-architecture.md` D2). 이는 SWE-Bench 호환성을 위함이며, tool-use는 v2 범위다.

에이전트에게 노출되는 입력:

| 필드 | 사용 |
|---|---|
| `problem_statement` | 자연어 task spec (closing issue body 우선, 그 외 PR description) |
| `base_commit` | 시작 상태 |
| `environment` | python_version, node_version, lock SHA 등 |

**에이전트에게 숨겨지는 항목**:

- `patch` (정답 diff)
- `test_patch` (테스트 diff)
- `fail_to_pass` / `pass_to_pass` (테스트 ID 목록)
- `hints_text` (리뷰 코멘트 등 힌트성 텍스트)

### 3.2 Patch 제약 조건 (D5)

에이전트 patch는 **non-test 파일만 수정** 가능하다. 이유:
- 테스트 수정을 허용하면 정답 테스트를 우회 가능 → 채점 무의미.
- `test_patch`는 하네스가 채점 직전에 강제 주입한다.

### 3.3 스코어링 실행 (score)

```bash
uv run pbench score --source <short_name> --pr <N> --patch-file solution.patch
```

내부적으로 §2.4 extraction pipeline의 step 8을 다음으로 치환한 동일 절차다.

```
8'. git checkout <base_commit>
    git apply <test_patch>            ← 하네스가 주입 (에이전트는 보지 못함)
    git apply <agent_patch>           ← 에이전트가 제출한 diff
    docker run backend pytest        → agent_tests.xml
    (frontend) docker run frontend bun run test:e2e --reporter=json → agent_e2e.json
```

### 3.4 점수 산식

`docs/task-schema.md` §스코어링 규약 (v1):

```
score(instance) =
  1   if  ∀ t ∈ FAIL_TO_PASS.backend ∪ FAIL_TO_PASS.frontend  :  t passes(agent_patch)
      AND ∀ t ∈ PASS_TO_PASS.backend ∪ PASS_TO_PASS.frontend  :  t passes(agent_patch)
  0   otherwise
```

- **이진(0/1)**. partial credit (예: 프런트만 통과, 백만 통과)은 v1 공식 점수에서 0이지만, `stack_domain` 라벨을 활용해 분석 단계에서만 도출된다.
- 벤치마크 총점 = `Σ score(i) / |corpus|` (백분율).

### 3.5 다양한 실패 분류와 처리

`summary.json` 에 structured 로 기록된다(`docs/harness-architecture.md` Failure modes):

| 실패 종류 | 발생 시점 | 점수 처리 |
|---|---|---|
| `patch_apply_failed` | `git apply <agent_patch>` 실패 | 0 |
| `image_build_failed` | lock 변경 등으로 이미지 빌드 불가 | 0 (또는 환경 오류 별도 분류) |
| `test_collection_failed` | import error, db 연결 불가 | 0 |
| `timeout` (15분/태스크 상한) | 테스트가 끝나지 않음 | 0 |
| `flaky` (첫 실행만, 재시도 v1 미지원) | 비결정적 | 0 (v1) |

**중요**: 어떤 실패에도 `summary.json` 에 원인이 structured 로 기록된다 — triage 품질이 태스크 품질을 결정한다.

---

## 4. 실행 환경 (재현성 보장)

### 4.1 Docker compose 토폴로지 (태스크 1건 실행 시)

```
┌──────────────────────────────────────────────────────────────┐
│ compose project: pbench-<instance_id>                        │
│                                                              │
│  db              ← postgres:17 (task-scoped ephemeral vol)   │
│  backend-tests   ← prototypebench/backend:<uv_lock_sha>      │
│                    mount: repo-snapshot                      │
│                    cmd:   uv run pytest --junitxml           │
│  backend-serve   ← 같은 이미지, 다른 command                  │
│                    cmd:   uvicorn app.main:app               │
│                    (frontend e2e 단계에서만 기동)             │
│  frontend-tests  ← prototypebench/frontend:<bun_lock_sha>    │
│                    depends_on: backend-serve                 │
│                    cmd: bun run test:e2e --reporter=json     │
└──────────────────────────────────────────────────────────────┘
```

- `db`는 태스크 단위 ephemeral volume → 인스턴스 간 오염 없음.
- `backend-tests` 와 `backend-serve` 는 동일 이미지, 다른 command. frontend e2e 시점에만 `backend-serve` 기동.

### 4.2 이미지 캐시 키 전략

- **Backend image tag = `uv_lock_sha`** (`docs/harness-architecture.md` D4).
- **Frontend image tag = `bun_lock_sha`**.
- lock 파일이 변하지 않으면 deps 레이어가 그대로 재사용 → 태스크당 deps 설치 비용 0.
- 이미지 수 ≈ lock 변동 수 ≪ PR 수.

### 4.3 Source 추상화 (SourceConfig)

새 source 추가는 `harness/sources/<short_name>.py` 한 파일에서 끝난다(`PLAN.md` §3.4):

```python
register(SourceConfig(
    name="OWNER/REPO",
    short_name="repo-alias",
    repo_url="https://github.com/OWNER/REPO.git",
    backend_dir="server",          # or "backend" or ""
    uv_lock_path="server/uv.lock",
    backend_image="prototypebench/backend-py312:latest",
    python_version="3.12",
    uv_extras=["plugins"],         # base commit에 존재하는 것만 필터
    prestart_steps=[...],
    pytest_extra_args=["-n", "auto"],
    pg_required=True | False,
    pg_env_map={"server": "POSTGRES_SERVER", ...},
    extra_services=[...],
))
```

`extract` / `score` / `batch-extract` / `filter` / `crawl` 전 명령이 `SourceConfig` 를 기반으로 동작 → 멀티 소스 native.

### 4.4 Local-only mode (dev fast path)

```bash
pbench <cmd> --mode local
```

- backend: host `uv` 로 `uv run pytest` 직접 실행
- db: 로컬 postgres
- frontend: host `bun` + `bunx playwright`

Docker 모드보다 약 10× 빠르지만 정확 재현성은 Docker 모드만 보장. 큐레이터 iteration용.

---

## 5. 측정되는 “품질” 의 정의

PrototypeBench가 평가하는 것 / 평가하지 않는 것을 명시:

| 측정함 | 측정 안 함 |
|---|---|
| 정답 PR이 새로 도입한 테스트(F2P)를 통과시키는지 | 코드 스타일, 가독성 |
| 기존 기능(P2P)을 깨뜨리지 않는지 | 변수명, 주석 품질 |
| 풀스택 통합 동작 (pytest + Playwright 모두 통과) | API 디자인의 우아함 |
| Modern AI-native stack 환경에서의 동작성 (React+Vite+Tailwind / FastAPI+SQLModel+Postgres) | 일반 코드 LLM 능력 (HumanEval 류) |
| PR-mined 자연스러운 atomic change 한 건 | multi-PR 대형 리팩토링 |

**철학**: SWE-Bench가 “성숙 라이브러리 버그픽스” 를 측정한다면, PrototypeBench는 “모던 풀스택 앱에서의 기능 ship” 을 측정한다(`PLAN.md` §2.3).

---

## 6. 공정성 / 오염(contamination) 방어

평가의 정당성을 지키는 두 축(`PLAN.md` §5, `dataset/README.md`):

### 6.1 공정성 (fairness-first)

- 운영 조직(Banya) 에이전트가 **잘 풀지 못하는 태스크도 필수 포함**. 자사가 잘하는 것만 넣으면 리더보드 신뢰가 즉사한다.
- 벤치마크 이름에 벤더(Banya) 명 배제.
- 자사 모델에 불리한 결과도 공개 약속(`docs/launch-strategy.md` §0).

### 6.2 오염 방어 (contamination)

베이스 repo가 MIT 공개이므로, 프런티어 모델이 PR diff를 학습 데이터로 봤을 가능성이 매우 높다. 대응:

| 메커니즘 | 작용 |
|---|---|
| `contamination_tier` 필드 (`public`/`held_out`/`internal_only`) | 인스턴스 단위 분류 |
| `created_at >= 모델 cutoff` ⇒ `held_out` | 자동 분류 |
| 시즌 단위 held-out 셋 로테이션 (Phase 5) | 시간 경과로 인한 누설 차단 |
| 제출자의 모델 cutoff 공개 요구 | 점수 신뢰성 확보 |
| 버그 주입 / 스펙 변형 파생 태스크 (v2) | 원본 PR이 알려져도 효과 감소 |

v0.1에서는 71/71 인스턴스가 `held_out` (2026-01-01 이후 머지).

---

## 7. 검증된 실패 모드 + 회피 (observed in 2026-04-20 validation)

`docs/harness-architecture.md` 의 검증 결과(PR #1543, #1396, #2104, #1270, #2146 대상):

| 실패 모드 | 근본 원인 | 현재 동작 | 후속 |
|---|---|---|---|
| **Pre-uv-era base_commit** | base commit이 PR #2090 (uv workspace 도입, 2026-01-20) 이전. 하네스가 root `uv.lock` 을 가정. | extractor가 base checkout 후 `uv.lock` 부재를 감지해 actionable error로 중단. `filter_prs.py`가 `mergedAt < 2026-01-20` PR을 후보에서 drop. | Poetry-era runner는 v2+ scope. |
| **Collection-error on base** (예: PR #2104) | `test_patch`가 base에 없는 심볼(e.g. `argon2`)을 import → pytest collection 실패 → file-level error만 emit, test-nodeid emit 안 됨. | F2P = 0, P2P = 0 (base가 nodeid를 안 보고하므로 교집합 empty). | v2: `+def test_*` 를 `test_patch`에서 파싱해 head의 passing set과 교집합. |
| **Flaky on first-cold-cache Docker run** | 아직 미관측 | — | Phase 3에서 모니터링, 필요 시 재시도 추가. |

v1에서 명시적으로 **포함하지 않은 것** (yagni):

- 병렬 실행 스케줄러 (직렬 실행)
- GPU / 모델 inference 컨테이너 (에이전트 patch 생성은 외부, 하네스는 patch만 받음)
- Flaky 재시도 (첫 실행만 사용, 재시도 정책은 Phase 3 튜닝 후)
- 결과 캐싱 (같은 base+patch 재실행 생략은 yagni 보류)

---

## 8. 현 코퍼스 통계 (v0.1, 2026-04-20)

| 지표 | 값 |
|---|---:|
| Task instances | **71** |
| Source 수 | 2 (`fastapi/full-stack-fastapi-template`, `IBM/mcp-context-forge`) |
| `FAIL_TO_PASS` 테스트 (총합) | 689 |
| `PASS_TO_PASS` regression-guard 테스트 (총합) | 31,644 |
| 1회 평가 시 실행되는 개별 테스트 케이스 합 | **32,333** |
| stack_domain 분포 | 71 backend_only (v0.1) |
| contamination_tier 분포 | 71 held_out |
| Schema valid | 71 / 71 |

| Source | Stars | License | Instances | F2P | P2P |
|---|---:|---|---:|---:|---:|
| `fastapi/full-stack-fastapi-template` | 42.7k | MIT | 3 | 7 | 77 |
| `IBM/mcp-context-forge` | 3.6k | Apache-2 | 68 | 682 | 31,567 |

비교용: SWE-Bench Verified 500, SWE-Bench Lite 300, HumanEval 164. v1 공개 베타 목표 200–300.

---

## 9. 평가 1 회차의 end-to-end 시퀀스 (요약)

평가자(외부 모델/에이전트 평가팀) 입장에서 1 회차 평가 전체 흐름:

```
[1] 코퍼스 로드
    from datasets import load_dataset
    ds = load_dataset("banyaaiofficial/prototypebench-v1", split="test")

[2] 인스턴스 i ∈ ds 마다:

    [2-a] 에이전트에게 입력 전달
          - problem_statement
          - base_commit (= repo @ this SHA)
          - environment 정보
          (patch, test_patch, fail_to_pass, pass_to_pass 는 숨김)

    [2-b] 에이전트가 unified diff(`agent_patch_i.diff`) 생성
          - non-test 파일만 수정 가능

    [2-c] 하네스가 채점
          uv run pbench score \
              --source <short_name> \
              --pr <i.pr_number> \
              --patch-file agent_patch_i.diff

          내부적으로:
              git checkout i.base_commit
              git apply i.test_patch          (하네스 주입)
              git apply agent_patch_i.diff    (에이전트 제출)
              docker run backend pytest       → agent_tests.xml
              [frontend 있을 시] bun run test:e2e → agent_e2e.json
              계산:
                  score = 1 iff F2P ⊆ passing(agent) ∧ P2P ⊆ passing(agent)

    [2-d] trace 로그 (에이전트 행동) 저장 — 실패 triage용

[3] 집계
    벤치 점수 = Σ score(i) / |corpus|

[4] 결과 제출
    - 모델 ID + cutoff 일자 공개
    - trace 로그 + score 리포트
    - (Phase 4 이후) 리더보드 제출 양식 따라 PR 또는 API 호출
```

---

## 10. v1 평가 절차의 알려진 한계

평가 절차 자체의 제한 사항(`dataset/README.md` Limitations, `docs/launch-strategy.md` §6):

1. **v0.1은 백엔드 전용**. Playwright runner는 구현되어 있으나 frontend-kind PR이 v1+ 로 미뤄짐.
2. **`mcp-context-forge` 가 corpus 의 96% (68/71)** — 다양한 워크로드 커버리지는 v1+ 우선순위.
3. **테스트 강도 = 벤치마크 품질**. 약한 테스트의 PR은 필터링되지만 완벽하지 않다. 큐레이터 리뷰 권장.
4. **Execution-based 채점은 즉시 결과가 안 나옴** — Docker 빌드 + 테스트 실행 시간 소요. 태스크당 상한 15분.
5. **Partial credit 부재** — “프런트만 통과” 같은 사례는 v1에서 0점.
6. **Tool-use loop 평가 부재 (v1)** — patch submission으로 추상화. tool-use 평가는 v2 범위.
7. **Flaky test 재시도 미지원 (v1)**.

---

## 11. 다음 단계 (Phase 3 — 내부 베타 평가)

`PLAN.md` §8 Phase 3:

- Banya 에이전트 vN / vN−1 비교 평가 (내부 회귀 시그널).
- 3–5 프런티어 모델 평가: Claude Opus 4.7, Sonnet 4.6, GPT-5, Gemini 3 등.
- 비용 추정: 40–60 태스크 × 5 모델 × agent loop ≈ 수백–수천 달러/회차.
- 태스크별 실패 분석 → 태스크 품질 개선 (너무 쉬움/모호함/테스트 부실 제거).

이후 Phase 4에서 공개 리더보드 + Methodology paper 공개 시 본 문서가 methodology 의 운영 레퍼런스가 된다.

---

## 12. 관련 문서

| 문서 | 역할 |
|---|---|
| [PLAN.md](../PLAN.md) | 프로젝트 헌장 · 설계 원칙 · 경쟁 지도 · 로드맵 |
| [docs/harness-architecture.md](harness-architecture.md) | 평가 하네스의 컨테이너/이미지/실행 코어 설계 |
| [docs/task-schema.md](task-schema.md) | 태스크 인스턴스 스키마 필드별 해설 |
| [docs/seed-curation.md](seed-curation.md) | 큐레이션 체크리스트 (수동 단계) |
| [docs/launch-strategy.md](launch-strategy.md) | 공정성 disclosure, methodology 공개 전략 |
| [schemas/task_instance.schema.json](../schemas/task_instance.schema.json) | JSON Schema 원본 |
| [dataset/README.md](../dataset/README.md) | Hugging Face 데이터셋 카드 (외부용) |

---

*이 문서는 2026-05-22 기준 코드/문서 상태를 종합한 운영 레퍼런스다. 코퍼스 통계와 검증된 실패 모드는 `PLAN.md` §7.5와 `docs/harness-architecture.md` 의 갱신과 동기화 유지가 필요하다.*
