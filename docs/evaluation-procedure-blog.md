# AI 코딩 에이전트를 어떻게 평가할 것인가?

> "당신의 에이전트는 풀스택 기능을 정말로 ship 할 수 있나?"
>
> 이 글은 PrototypeBench 의 평가 프로시저를 — 코드 한 줄 없이 — 풀어쓴 기술 블로그 버전입니다.
> 더 상세한 운영 레퍼런스가 필요하면 [evaluation-procedure.md](https://github.com/prototypebench/prototypebench/blob/main/docs/evaluation-procedure.md) 를 참고하세요.

---

## 1. 왜 새로운 벤치마크가 필요한가

AI 코딩 에이전트의 성능을 측정하는 가장 유명한 벤치마크는 **SWE-Bench** 입니다.
Django, sympy, flask 같은 성숙한 Python 라이브러리에서 "버그를 고쳐라" 라는 과제를 줍니다.

그런데 실제로 AI 제품을 만드는 사람들의 일상은 어떨까요?
대부분 다음 같은 일을 합니다:

- React 컴포넌트를 새로 만들고
- FastAPI 엔드포인트를 추가하고
- Postgres 스키마를 마이그레이션하고
- Playwright 로 E2E 테스트를 통과시키는 일

"성숙 라이브러리의 버그픽스" 와 "모던 풀스택 앱의 기능 ship" 은 **다른 능력** 입니다.
PrototypeBench 는 후자를 측정하기 위해 만들어졌습니다.

타깃 스택은 2024 산업 서베이에서 모두 1위인 조합입니다.

- **프런트**: React (82%) + Vite (78%) + Tailwind (62%) + shadcn/ui
- **백엔드**: FastAPI (38%, ML 엔지니어의 42% 가 사용) + SQLModel + Postgres

"AI 제품을 만드는 사람들의 스택으로 AI 에이전트를 평가한다" — 이게 한 줄 정체성입니다.

---

## 2. 한 문장 평가 정의

> 실제로 머지된 OSS PR 을 태스크로 변환한 뒤, 에이전트가 만든 patch 가
> **PR 이 새로 도입한 테스트는 통과시키면서**
> **기존에 통과하던 테스트는 깨뜨리지 않는지** 를 실제 테스트 실행으로 판정합니다.
> 점수는 태스크당 0 또는 1.

핵심은 세 가지 결단입니다.

1. **LLM-as-judge 안 씁니다.** 판정자는 pytest 와 Playwright 의 실행 결과뿐입니다.
2. **정답은 실제 머지된 PR diff 입니다.** 누군가가 임의로 작성한 reference 가 아닙니다.
3. **이진 점수입니다.** "프런트만 통과" 같은 partial credit 는 v1 에서 인정하지 않습니다 (분석용으로만 보관).

---

## 3. 평가 파이프라인의 큰 그림

PrototypeBench 의 평가는 **두 단계** 로 나뉩니다.

```
┌───────────────────────┐         ┌───────────────────────┐
│  Task Curation        │  ──→    │   Agent Evaluation    │
│  (코퍼스 생성)         │         │   (에이전트 채점)       │
└───────────────────────┘         └───────────────────────┘
   벤치마크 운영자가                   외부 모델/에이전트 팀이
   "한 번" 실행                      "에이전트 바뀔 때마다" 실행
```

흥미로운 점은 두 단계가 **같은 엔진** 을 공유한다는 것입니다.
큐레이션 시 테스트를 돌려서 "정답이 통과시키는 테스트" 를 추출하는 코드와,
채점 시 에이전트의 patch 를 가지고 테스트를 돌리는 코드는 같습니다.
**다른 입력, 같은 머신.**

이게 왜 중요한가요? 평가 환경이 큐레이션 환경과 다르면 "정답" 자체가 깨지기 때문입니다.

---

## 4. 태스크 코퍼스는 어떻게 만들어지나

PrototypeBench 의 모든 태스크는 **실제 OSS repo 에서 머지된 PR** 한 건에서 나옵니다.
무작위 PR 이 아니라, 7 단계 필터를 거친 PR 만 살아남습니다.

### 7 단계 요약

1. **크롤** — GitHub 에서 머지된 PR 메타데이터 수집
2. **필터** — dependabot/docs/typo 제외, 테스트 변경 있는 PR 우선
3. **분포 점검** — backend / frontend / fullstack 종류별 분포 확인
4. **테스트 신호 자동 추출** — 핵심 단계. 아래 자세히
5. **인스턴스 변환** — 스키마 준수 JSON 으로 패키징
6. **스키마 검증** — 누락 필드 / 패턴 위반 거부
7. **오염 티어 지정** — 모델 cutoff 비교로 public / held_out 분류

### 4 단계가 마법의 핵심: `FAIL_TO_PASS` 자동 추출

여기서 "PR 이 새로 도입한 테스트" 와 "기존에도 통과하던 테스트" 를 가른다.
방식은 단순합니다.

- **Base 시점 (PR 시작 직전 상태)**: PR 의 테스트 파일만 미리 갖다 붙여서 테스트를 돌린다.
  → 새 기능을 검증하는 테스트는 **당연히 실패** 한다 (아직 코드가 없으니).
- **Head 시점 (PR 머지된 상태)**: 같은 테스트를 다시 돌린다.
  → 정답 코드가 들어왔으니 통과한다.

두 결과를 비교하면:

- **`FAIL_TO_PASS`** = base 에서 실패했지만 head 에서 통과한 테스트
  → "정답이 새로 통과시켜야 하는 테스트"
- **`PASS_TO_PASS`** = base 에서도 통과했고 head 에서도 통과한 테스트
  → "기존 기능, 깨면 안 되는 회귀 가드"

큐레이터가 손으로 라벨링하는 것이 아니라, **테스트 실행 결과의 집합 연산** 으로 자동 도출됩니다.

> v0.1 코퍼스 71 개 인스턴스의 통계
>
> - `FAIL_TO_PASS` 총합: **689 개**
> - `PASS_TO_PASS` 총합: **31,644 개**
> - 1 회차 풀 평가 시 실행되는 개별 테스트: **32,333 개**

---

## 5. 에이전트는 어떻게 평가되나

코퍼스가 준비되면 에이전트 평가 차례입니다. v1 의 인터페이스는 단순합니다.

### 에이전트에게 주는 것

- **자연어 task spec** (`problem_statement`) — 보통 PR 의 closing issue body 또는 PR description
- **시작 상태** (`base_commit`) — 그 repo 를 이 SHA 로 checkout 한 상태에서 시작
- **환경 정보** — Python 버전, Node 버전, lock 파일 해시 등

### 에이전트에게 절대 주지 않는 것

- 정답 patch
- 테스트 파일 diff (테스트가 검증하는 게 뭔지 미리 보면 안 됨)
- F2P / P2P 테스트 ID 목록
- 리뷰어 코멘트 같은 힌트성 텍스트

### 에이전트가 돌려주는 것

**unified diff 한 덩어리.** 그게 전부입니다.

> v1 은 "tool-use agent loop" 를 직접 굴리지 않습니다.
> 에이전트가 외부에서 어떻게 만들든 상관 없이, 최종 산출물인 patch 만 받습니다.
> 이렇게 한 이유는 (a) SWE-Bench 와 호환성, (b) 스코어링 코어를 먼저 단단히 만들기 위함입니다.
> Tool-use 평가는 v2 의 범위입니다.

### 채점 절차

채점은 큐레이션의 추출 절차와 거의 동일합니다. 한 단계만 다릅니다.

1. Repo 를 base commit 으로 checkout
2. 테스트 diff 를 **하네스가** 강제 주입 (에이전트가 본 적 없는 것)
3. **에이전트의 patch 를 적용**
4. pytest 실행 (백엔드)
5. (해당 시) Playwright 실행 (프런트)
6. 점수 계산:

> `FAIL_TO_PASS` 의 모든 테스트가 통과 **AND** `PASS_TO_PASS` 의 모든 테스트가 통과 → **1점**
> 그 외 → **0점**

벤치마크 총점 = (1점 받은 인스턴스 수) / (전체 인스턴스 수).

### 에이전트가 테스트를 수정하면 안 되는 이유

만약 에이전트가 테스트 파일을 수정할 수 있다면, "정답 테스트를 살짝 바꿔서 통과시키기" 가 가능합니다.
그건 채점을 무의미하게 만들죠.
그래서 PrototypeBench 는 **non-test 파일만 수정** 한 patch 를 받습니다.
테스트는 하네스가 채점 직전에 강제 주입합니다.

### 실제 예시: PR #1396

말로만 설명하면 추상적이니, v0.1 코퍼스에 실제로 들어있는 인스턴스 한 건을 그대로 펼쳐보겠습니다.

**인스턴스 ID**: `fastapi__full-stack-fastapi-template-1396`
**원본 PR**: [fastapi/full-stack-fastapi-template#1396](https://github.com/fastapi/full-stack-fastapi-template/pull/1396) — *🐛 Handle non-existing user IDs in `read_user_by_id`*
**stack_domain**: `backend_only`

#### (1) 에이전트가 받는 것 — `problem_statement`

> Fix an issue where `read_user_by_id` would fail to return if the requested user ID did not exist.
> * Return `404 - Not Found` when ID does not exist.
> * Request without sufficient permission will always result in `403 - Unauthorized`.
> * Add tests to test requesting non-existing user IDs as superuser and normal user.

그리고 `base_commit` SHA — repo 를 그 시점으로 checkout 한 상태에서 시작합니다.
**테스트 코드는 절대 보여주지 않습니다.**

#### (2) 에이전트가 돌려줘야 하는 것 — `patch`

정답 PR 이 머지한 코드 변경은 단 4 줄입니다.

```diff
diff --git a/backend/app/api/routes/users.py b/backend/app/api/routes/users.py
@@ -170,6 +170,8 @@ def read_user_by_id(
             status_code=403,
             detail="The user doesn't have enough privileges",
         )
+    if user is None:
+        raise HTTPException(status_code=404, detail="User not found")
     return user
```

에이전트는 이걸 (혹은 의미상 동등한 patch 를) 자력으로 생성해야 합니다.
"non-existing user ID 면 404" 라는 spec 한 줄로부터 `read_user_by_id` 라는 핸들러를 찾아내고,
권한 검사 이후 / `return` 이전에 None 가드를 넣어야 한다는 위치까지 잡아야 한다는 뜻입니다.

#### (3) 하네스가 채점 직전에 강제 주입하는 것 — `test_patch`

```diff
diff --git a/backend/tests/api/routes/test_users.py b/backend/tests/api/routes/test_users.py
@@ -56,7 +56,7 @@
-def test_get_existing_user(
+def test_get_existing_user_as_superuser(
     client: TestClient, superuser_token_headers: dict[str, str], db: Session
 ) -> None:
@@ -75,6 +76,17 @@
+def test_get_non_existing_user_as_superuser(
+    client: TestClient, superuser_token_headers: dict[str, str]
+) -> None:
+    r = client.get(
+        f"{settings.API_V1_STR}/users/{uuid.uuid4()}",
+        headers=superuser_token_headers,
+    )
+    assert r.status_code == 404
+    assert r.json() == {"detail": "User not found"}
```

(전체 test_patch 에는 권한 에러 회귀 테스트 등 몇 개가 더 있습니다.)

#### (4) 채점 결과

이 인스턴스의 `fail_to_pass` 와 `pass_to_pass` 는 자동 추출 결과 다음과 같이 잡혔습니다.

- `FAIL_TO_PASS` (backend): `tests/api/routes/test_users.py::test_get_non_existing_user_as_superuser` — 새 기능을 검증하는 1 개 테스트
- `PASS_TO_PASS` (backend): 같은 파일의 기존 user 관련 테스트들 — 회귀 가드

에이전트의 patch 가 위 4 줄과 의미상 동등하다면:

- `FAIL_TO_PASS` 의 1 개 → 모두 통과
- `PASS_TO_PASS` 의 모든 테스트 → 깨지지 않음
- ⇒ **1점**

만약 `if user is None` 분기를 누락하거나 권한 검사 *이전* 에 넣어버리면 (그러면 403 회귀 테스트가 깨집니다)
점수는 즉시 **0점** 입니다 — 부분 점수 없음.

> 이 예시는 의도적으로 가장 작은 케이스를 골랐습니다.
> 실제 코퍼스에는 React 컴포넌트 + FastAPI 엔드포인트 + Postgres 마이그레이션이 한 PR 에 얽힌
> fullstack 인스턴스도 다수 포함되며, 그 경우 patch 는 수백 줄, F2P 테스트는 pytest 와 Playwright 양쪽에 걸쳐 분포합니다.

---

## 6. 왜 Docker 인가 — 재현성의 문제

큐레이션 시점에 "이 테스트가 통과했다" 는 것을, 6 개월 뒤 다른 머신에서도 똑같이 재현할 수 있어야 합니다.
그렇지 않으면 채점 결과가 환경에 좌우됩니다.

PrototypeBench 는 태스크 1 건마다 다음 컨테이너를 띄웁니다.

- **db** — Postgres, task 단위 ephemeral volume (인스턴스 간 오염 없음)
- **backend-tests** — pytest 실행용
- **backend-serve** — frontend E2E 시 백엔드 서버 역할
- **frontend-tests** — Playwright (브라우저 바이너리 포함)

### 이미지 캐시의 영리한 트릭

이미지 태그를 commit SHA 가 아니라 **lock 파일 해시** 로 잡습니다.

- Backend 이미지 = `prototypebench/backend:<uv_lock_sha>`
- Frontend 이미지 = `prototypebench/frontend:<bun_lock_sha>`

lock 파일이 바뀌지 않으면 의존성 레이어가 그대로 재사용됩니다.
태스크가 100 개여도 lock 파일 변경이 10 번이면 이미지는 10 개.
"태스크당 deps 설치 비용 0" 을 이렇게 달성합니다.

---

## 7. 무엇을 측정하고, 무엇을 측정하지 않는가

PrototypeBench 는 의도적으로 **좁게** 측정합니다.

| 측정함 | 측정 안 함 |
|---|---|
| 정답 PR 이 새로 도입한 테스트를 통과시키는가 | 코드 스타일 / 가독성 |
| 기존 기능을 깨지 않는가 | 변수명 / 주석 품질 |
| 풀스택 통합 동작 (pytest + Playwright 동시) | API 디자인의 우아함 |
| 모던 AI-native 스택에서의 실제 동작성 | 일반 코드 LLM 능력 (HumanEval 류) |
| PR 단위 atomic change 한 건 | multi-PR 대형 리팩토링 |

좁게 측정하는 이유는, 넓게 측정하려고 하면 **무엇이 좋은 코드인가** 라는 주관에 빠지기 때문입니다.
"테스트가 통과하는가" 는 객관적입니다.

---

## 8. 두 가지 신뢰 — 공정성과 오염 방어

공개 벤치마크의 신뢰는 두 가지에서 무너집니다.

### 8.1 벤더 편향

> 운영 조직의 에이전트만 잘 푸는 태스크로 채워진 벤치마크.

PrototypeBench 의 방어선:

1. 운영 조직 (Banya) 의 에이전트가 **잘 못 푸는 태스크도 필수 포함**
2. 벤치 이름에 벤더명 절대 안 넣음 (그래서 "PrototypeBench")
3. 자사 에이전트에 불리한 점수도 공개 약속

### 8.2 학습 데이터 오염

베이스 repo 가 MIT 라이선스로 공개되어 있다는 뜻은,
**프런티어 모델들이 이미 그 PR diff 들을 학습 데이터로 봤을 가능성이 매우 높다** 는 뜻입니다.

방어:

- **`contamination_tier` 필드**: 각 인스턴스를 `public` / `held_out` / `internal_only` 로 분류
- **자동 분류 규칙**: PR `created_at` 이 모델 cutoff 이후면 `held_out`
- **시즌 단위 로테이션**: 시간이 지나면 held-out 셋도 결국 누설되므로 주기적 교체
- **제출자 의무**: 사용한 모델의 cutoff 일자 공개
- **v2 계획**: 원본 PR 을 변형한 파생 태스크로 누설 효과 무력화

> v0.1 의 71 개 인스턴스는 **전부 held_out** — 모두 2026-01-01 이후 머지된 PR.
> Claude Opus 4.7 의 cutoff (2026-01) 를 안전선으로 잡았습니다.

---

## 9. 평가 1 회차의 흐름 — 평가자의 시점에서

외부 모델 / 에이전트 평가팀의 입장에서 1 회차 평가는 다음 흐름입니다.

```
[1] Hugging Face 에서 코퍼스 로드
    → "banyaaiofficial/prototypebench-v1"

[2] 각 인스턴스마다:

      (a) 에이전트에게 자연어 spec + base SHA 전달
          (정답과 테스트는 숨김)

      (b) 에이전트가 unified diff 한 덩어리 생성

      (c) 하네스가 채점:
          - base 로 checkout
          - 테스트 diff 강제 주입
          - 에이전트 patch 적용
          - pytest / Playwright 실행
          - F2P 모두 통과 ∧ P2P 모두 통과 → 1점, 아니면 0점

      (d) trace 로그 저장 (실패 triage 용)

[3] 집계: 벤치 점수 = Σ score(i) / |corpus|

[4] 결과 제출:
    - 모델 ID + cutoff 일자 공개 (오염 점수 보정용)
    - trace 로그 + score 리포트
```

---

## 10. SWE-Bench 와의 관계

자주 받는 질문: "그냥 SWE-Bench 의 풀스택 버전 아닌가?"

**같은 점**

- "PR mined task + execution-based scoring + binary score" 패턴
- 인스턴스 스키마 호환 (SWE-Bench 툴체인을 거의 그대로 재사용 가능)
- `FAIL_TO_PASS` / `PASS_TO_PASS` 컨벤션

**다른 점**

- **대상**: 성숙 라이브러리 버그픽스 (SWE-Bench) vs 모던 풀스택 앱 기능 ship (PrototypeBench)
- **러너**: pytest 단독 vs pytest + Playwright 이중
- **스택**: Python 만 vs Python + TypeScript + Node toolchain + Docker compose
- **차원**: 한 줄 / 한 함수 수정 위주 vs 백엔드 + 프런트 + DB 마이그레이션이 얽힌 change

요약하면: **상위 카테고리는 같고 (PR-mined coding agent benchmark), 대상 도메인이 다른 보완재** 입니다.

---

## 11. 마치며 — 무엇을 위한 벤치마크인가

PrototypeBench 의 우선순위는 명확합니다.

1. **첫째, 내부 가치**: Banya 에이전트 버전 간 회귀를 측정한다.
2. **둘째, 외부 가치**: 공개 리더보드 — 부산물.

이 우선순위가 역전되면 설계 편향이 들어옵니다.
"리더보드에서 좋아보이는 점수가 나오게" 설계하지 않고, "에이전트 개선이 실제로 반영되게" 설계합니다.
그 결과로 신뢰할 만한 공개 리더보드가 부산물로 따라오기를 기대합니다.

---

## 더 읽을거리

- [PLAN.md](https://github.com/prototypebench/prototypebench/blob/main/PLAN.md) — 프로젝트 헌장과 로드맵
- [evaluation-procedure.md](https://github.com/prototypebench/prototypebench/blob/main/docs/evaluation-procedure.md) — 본 글의 상세 운영 레퍼런스 (코드/명령 포함)
- [harness-architecture.md](https://github.com/prototypebench/prototypebench/blob/main/docs/harness-architecture.md) — 하네스 설계 결정의 근거
- [task-schema.md](https://github.com/prototypebench/prototypebench/blob/main/docs/task-schema.md) — 태스크 인스턴스 스키마
- [Hugging Face dataset](https://huggingface.co/datasets/banyaaiofficial/prototypebench-v1) — 71 개 인스턴스 직접 다운로드

---

*작성: 2026-05-22. PrototypeBench v0.1 기준.*
