# 3c단계(양념 비율 계산기) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 레시피 탭 `양념 비율` 칸에서 불고기·제육볶음·간장조림·초고추장·쌈장·갈비 양념 같은 기본 비율을 고르고, 고기 무게·인분·완성량을 넣으면 각 양념의 양을 실제로 뜰 수 있는 숟가락 단위(`3½큰술`, `⅓작은술`)와 밥숟가락 환산(`밥숟가락 약 4개`)으로 보여준다. 자주 쓰는 비율은 `내 비율`로 저장·수정·삭제하고, 계산 결과를 레시피 재료로 가져간다.

**Architecture:** 계산은 전부 화면에서 한다. 단위 환산·배율·분수 반올림은 순수 함수 모듈 `frontend/src/seasoning.ts` 하나에 두고(기존 `format.ts`의 `SNAPS`·`formatAmountNumber` 재사용), 기본 비율은 서버 테이블이 아니라 **화면 번들의 데이터 파일**(`frontend/src/data/seasoningPresets.ts`)로 둔다 — 운영자가 바꾸는 값이라 시드 CLI·마이그레이션 데이터가 필요 없고, 출처 메모와 함께 코드 리뷰로 바뀐다. 사용자 "내 비율"만 스펙 22절대로 서버에 저장한다(`seasonings` 테이블 하나, 양념 줄은 3a `recipes.ingredients`처럼 JSON 칸). 결과를 레시피로 가져가는 것은 3b의 `openDraft`를 쓴다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, pytest 9.1.1 / React 19 + TypeScript + Vite 8, Node 24(`.ts` 직접 실행 한 줄 검사)

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 2절(3단계), 22절(양념 비율 계산기), 26절(수십 개 목록은 페이지 없음), 23절 D1(인분 배율). 스펙과 다르게 정한 것(Task 1 Step 6·Task 2 Step 3에서 스펙에 기록): 기본 비율은 DB가 아니라 화면 데이터 파일, `seasoning_items` 테이블 대신 `seasonings.items` JSON. 선행: 3b Task 4(`openDraft`). 3b보다 먼저 하게 되면 Task 3에서 `openDraft`만 3b 계획 모양 그대로 먼저 넣는다. 디자인: `docs/design/seasoning-3c/*.dc.html`(아직 없음 — Task 3 전에 시안 승인).

## Global Constraints

- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다.
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. SQLite와 PostgreSQL(`TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate`, 이미 설정됨) 둘 다 실패 0, 경고 0.
- 프론트 태스크는 `cd frontend && npm run build`(`tsc --noEmit` + `vite build`)가 오류 없이 끝나야 한다. 순수 함수는 `node --input-type=module -e` + `node:assert/strict` 한 줄 검사(테스트 러너를 새로 들이지 않는다).
- 테스트는 절대 실제 외부 API를 부르지 않는다(이번 단계는 외부 호출 자체가 없다). 키는 `backend/.env`에만 두고 읽거나 커밋하지 않는다. `DEV_MODE` 예시 결과가 필요한 기능은 없다(기본 비율이 곧 예시).
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정하고 남의 것은 404.
- 모바일 384px 기준. 터치 영역 44px 이상, 입력 글자 16px 이상(숫자 입력은 `inputMode="decimal"`). 아이콘은 이모지 대신 `Icon`. 라이트·다크 모두 확인.
- **삭제 버튼은 `.btn.danger-text`(연빨강 배경 + 테두리)로 다른 버튼 아래에 둔다(`이 비율 삭제`는 `수정` 아래).**
- 화면 문구는 보조 용언을 붙여 쓴다(`보여줘요`, `입력해주세요`, `조절해주세요`). 개발 용어(프리셋, 배율 계수, ml 환산 로직)는 화면에 쓰지 않는다.
- 개발 서버는 Vite 5180, Flask 5181. 5173은 건드리지 않는다. 개발 DB는 지우지 않는다.
- 브랜치는 태스크마다 하나, 리뷰 통과 후 main에 `--no-ff` 병합.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음 한 줄만 붙인다:
  ```
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치

| 브랜치 | 태스크 | 시작 시점 | 시안 |
|---|---|---|---|
| `feature/seasoning-calc` | 1 (숟가락 환산·배율 순수 모듈, 기본 비율 데이터) | main에서 바로 | **UI 시안 승인 전 진행 가능** |
| `feature/seasonings-backend` | 2 (내 비율 테이블·마이그레이션·API) | main에서 바로(태스크 1과 병렬 가능, 겹치는 파일 없음) | **UI 시안 승인 전 진행 가능** |
| `feature/seasoning-ui` | 3 (양념 비율 칸, 계산 화면, 내 비율 폼, 레시피로 가져오기) | 태스크 1·2 병합 + 3b Task 4 병합 + 시안 승인 뒤 | **시안 승인 후** |

## 파일 구조

```
frontend/src/
  format.ts                                         (수정, T1) SNAPS export
  seasoning.ts                                      (신규, T1) 단위·배율·숟가락 표시 순수 함수, 타입
  data/seasoningPresets.ts                          (신규, T1) 기본 비율 6개 + 출처 메모
  api.ts                                            (수정, T3) Seasoning 타입 재수출
  pages/Seasonings.tsx                              (신규, T3) 양념 비율 칸 목록(Recipes.tsx에서 사용)
  pages/SeasoningCalc.tsx                           (신규, T3) #/recipes/seasonings/preset/:id, #/recipes/seasonings/:id
  pages/SeasoningForm.tsx                           (신규, T3) #/recipes/seasonings/new, #/recipes/seasonings/:id/edit
  pages/Recipes.tsx, useHashRoute.ts, App.tsx, styles.css (수정, T3)
backend/
  app/models.py                                     (수정, T2) Seasoning
  migrations/versions/b1b1c1d1e1f1_seasonings.py    (신규, T2)
  app/seasonings.py                                 (신규, T2) /api/seasonings CRUD
  app/__init__.py                                   (수정, T2) 블루프린트
  tests/test_seasonings.py                          (신규, T2), tests/test_migrations.py (수정, T2)
docs/superpowers/specs/2026-09-13-recipe-ai-design.md (수정, T1·T2)
```

---

### Task 1: 숟가락 환산·배율 순수 모듈과 기본 비율 데이터 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `frontend/src/seasoning.ts`, `frontend/src/data/seasoningPresets.ts`
- Modify: `frontend/src/format.ts`(`SNAPS`를 export만), 스펙 문서 22절(밥숟가락 기준·표시 규칙·출처)

**Interfaces:**
- Consumes: `SNAPS`, `formatAmountNumber`(format.ts)
- Produces:
  ```ts
  export type SeasoningUnit = "큰술" | "작은술" | "컵" | "ml" | "g" | "개" | "꼬집";
  export type Basis = "main_weight" | "servings" | "yield";
  export type BasisUnit = "g" | "인분" | "컵" | "ml";
  export interface SeasoningItem { name: string; amount: number; unit: SeasoningUnit }
  export interface Seasoning {
    id: number; name: string; basis: Basis; basis_amount: number; basis_unit: BasisUnit;
    main_ingredient: string | null; items: SeasoningItem[];
    source: "default" | "user"; source_note: string | null;
  }
  export const SPOON_ML = { 큰술: 15, 작은술: 5, 컵: 200, ml: 1 } as const;   // 스펙 22절 계량 기준
  export const RICE_SPOON_ML: number;  // 밥숟가락 1개 용량. 출처 확인 전 후보 12 (아래 Step 2)
  export const BASIS_UNITS: Record<Basis, BasisUnit[]>;  // main_weight: ["g"], servings: ["인분"], yield: ["컵", "ml"]

  /** 입력량 ÷ 기준량. 같은 기준 단위일 때만(yield의 컵↔ml는 SPOON_ML로 맞춘다). 0 이하·NaN이면 null */
  export function scaleFactor(s: Pick<Seasoning, "basis_amount" | "basis_unit">, input: number, inputUnit: BasisUnit): number | null;

  /** 0.33 → "⅓", 3.5 → "3½", 0.9 → "1", 12.4 → "12". 가장 가까운 ¼·⅓·½·⅔·¾ 또는 정수(10 이상은 정수) */
  export function snapSpoon(value: number): string;

  /** 한 양념 줄 × 배율 → 화면 표시 */
  export function scaleItem(item: SeasoningItem, factor: number): { text: string; riceSpoon: string | null };
  ```
- **표시 규칙(스펙 22절 구체화, 열린 질문의 기본값):**
  1. 부피 단위(`큰술`·`작은술`·`컵`)는 `ml = amount × SPOON_ML[unit] × factor`로 바꾼 뒤 **ml만 보고** 단위를 다시 고른다:
     - `ml ≥ 100`(½컵 이상) → `snapSpoon(ml / 200) + "컵"`
     - `ml ≥ 15`(1큰술 이상) → `snapSpoon(ml / 15) + "큰술"` (14ml는 작은술 쪽 `2¾작은술`)
     - `ml ≥ 1.25`(¼작은술 이상) → `snapSpoon(ml / 5) + "작은술"`
     - 그보다 적으면 `"약간"`
  2. 원래 단위가 `ml`이면 ml 그대로(`formatAmountNumber` 대신 10 이상 정수, 그 아래 소수 한 자리) — 사용자가 ml로 적은 건 계량컵을 쓴다는 뜻.
  3. `g`·`개`는 `formatAmountNumber(amount × factor) + unit`. `꼬집`은 `Math.max(1, Math.round(...))꼬집`.
  4. 밥숟가락: 결과가 `큰술`·`작은술`일 때만 `n = ml / RICE_SPOON_ML`을 ½ 단위로 반올림, `n ≥ ½`이면 `riceSpoon = "밥숟가락 약 N개"`(½은 `½개`, 1½은 `1½개`), 아니면 null.
  - `ponytail:` 반올림 오차(예 110ml → ½컵, 10ml 손실)는 "취향에 따라 조절" 안내로 둔다. 불만이 나오면 `½컵 + ⅔큰술`처럼 나머지 표시를 추가.
- `data/seasoningPresets.ts`: `export const SEASONING_PRESETS: Seasoning[]` — `id` 1~6(경로용, 바꾸지 않음), `source: "default"`, `source_note`에 비교한 출처 이름(2곳 이상)과 확인 날짜. 기준 예: 불고기·제육볶음·갈비 → `main_weight` 고기 `600g`, 간장조림 → `main_weight`, 초고추장·쌈장 → `yield` `1컵` 또는 `servings`. 이름은 스펙 22절 목록 그대로.

- [ ] **Step 0: 브랜치** — `cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/seasoning-calc`

- [ ] **Step 1: 한 줄 검사를 먼저 쓰고 실패 확인**
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && node --input-type=module -e '
import assert from "node:assert/strict";
import { snapSpoon, scaleItem, scaleFactor, RICE_SPOON_ML } from "./src/seasoning.ts";
import { SEASONING_PRESETS } from "./src/data/seasoningPresets.ts";
assert.equal(snapSpoon(0.33), "⅓"); assert.equal(snapSpoon(3.5), "3½"); assert.equal(snapSpoon(0.9), "1"); assert.equal(snapSpoon(12.4), "12");
const tbsp = (amount, factor) => scaleItem({ name: "간장", amount, unit: "큰술" }, factor);
assert.equal(tbsp(3, 1).text, "3큰술");
assert.equal(tbsp(3.5, 1).text, "3½큰술");
assert.equal(tbsp(3, 1 / 3).text, "1큰술");
assert.equal(tbsp(1, 0.5).text, "1½작은술");                 // 큰술이 작으면 작은술
assert.equal(scaleItem({ name: "소금", amount: 1, unit: "작은술" }, 1 / 3).text, "⅓작은술");
assert.equal(scaleItem({ name: "소금", amount: 1, unit: "작은술" }, 0.1).text, "약간");
assert.equal(scaleItem({ name: "물", amount: 1, unit: "컵" }, 2).text, "2컵");
assert.equal(tbsp(10, 1).text, "¾컵");                         // 150ml → ¾컵(½컵 이상은 컵)
assert.equal(scaleItem({ name: "물", amount: 150, unit: "ml" }, 1.5).text, "225ml");
assert.equal(scaleItem({ name: "고춧가루", amount: 20, unit: "g" }, 1.5).text, "30g");
assert.equal(scaleItem({ name: "후추", amount: 1, unit: "꼬집" }, 0.3).text, "1꼬집");
if (RICE_SPOON_ML === 12) assert.equal(tbsp(3, 1).riceSpoon, "밥숟가락 약 4개");   // 스펙 예시 3큰술 ≈ 4개
assert.equal(scaleItem({ name: "고춧가루", amount: 20, unit: "g" }, 1).riceSpoon, null);
assert.equal(scaleFactor({ basis_amount: 600, basis_unit: "g" }, 900, "g"), 1.5);
assert.equal(scaleFactor({ basis_amount: 1, basis_unit: "컵" }, 100, "ml"), 0.5);
assert.equal(scaleFactor({ basis_amount: 2, basis_unit: "인분" }, 0, "인분"), null);
assert.equal(new Set(SEASONING_PRESETS.map((p) => p.id)).size, SEASONING_PRESETS.length);
for (const p of SEASONING_PRESETS) {
  assert.ok(p.items.length > 0 && p.basis_amount > 0 && p.source_note, p.name);
  for (const i of p.items) assert.ok(i.amount > 0 && i.name, `${p.name} ${i.name}`);
}
console.log("seasoning ok");
'
```
Expected(구현 전): 모듈 없음 오류. 구현 후: `seasoning ok`.

- [ ] **Step 2: 밥숟가락 기준 확인** — 공신력 있는 출처(농촌진흥청·식약처·한국영양학회 등 계량 안내)에서 밥숟가락(가정용 숟가락) 1개 용량을 찾아 `RICE_SPOON_ML`과 주석 출처를 정한다. 출처가 없거나 서로 다르면 **12ml(스펙 예시 `3큰술 (밥숟가락 약 4개)`와 맞음)** 로 두고 주석에 "출처 미확인, 스펙 예시 기준"과 열린 질문 번호를 남긴다.

- [ ] **Step 3: 구현** — `seasoning.ts`(Interfaces·표시 규칙대로), `format.ts`에서 `SNAPS` export.

- [ ] **Step 4: 기본 비율 데이터** — 여섯 양념마다 신뢰할 수 있는 출처 2곳 이상(식약처·농진청 메뉴젠·만개의레시피 인기 레시피·요리 전문 서적 등)을 비교해 중간값에 가깝게 정하고 `source_note`에 출처 이름·날짜를 남긴다. 값은 PR 설명에 표로 붙여 **사용자 확인**을 받는다(열린 질문). 인터넷을 쓸 수 없는 환경이면 값을 지어내지 말고 이 스텝을 보류로 표시하고 멈춘다.

- [ ] **Step 5: 확인** — Step 1 검사 `seasoning ok`, `cd frontend && npm run build` 성공(아직 어디서도 import하지 않아도 `tsc`가 검사한다).

- [ ] **Step 6: 스펙 갱신** — 22절: 표시 규칙(½컵 이상 컵, 1큰술 미만 작은술, ¼작은술 미만 약간, ml 입력은 ml 유지), 밥숟가락 기준과 출처, 기본 비율은 화면 데이터 파일이라는 결정.

- [ ] **Step 7: 커밋** — `git add frontend docs && git commit -m "feat: 양념 비율 계산(숟가락 분수·작은술 자동 환산·밥숟가락 환산), 기본 양념 비율 데이터" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

### Task 2: 내 비율 저장 백엔드 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `backend/app/seasonings.py`, `backend/migrations/versions/b1b1c1d1e1f1_seasonings.py`, `backend/tests/test_seasonings.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`, `backend/tests/test_migrations.py`, 스펙 문서

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`(auth), `text`, `commit_or_duplicate`(validation), `utcnow`
- Produces:
  - `app.models.Seasoning`(`seasonings`): id, user_id FK users CASCADE NOT NULL index, name String(30), basis String(20)(`main_weight|servings|yield`), basis_amount Float, basis_unit String(10)(`g|인분|컵|ml`), main_ingredient String(50) NULL, items JSON(`[{name, amount, unit}]`), created_at, updated_at(onupdate). UNIQUE(user_id, name).
  - Alembic revision `b1b1c1d1e1f1`. **down_revision은 구현 시점의 실제 head**(3b를 먼저 병합했으면 `a9b9c9d9e9f9`, 아니면 `a8b8c8d8e8f8`). `ls backend/migrations/versions`로 확인하고, 다른 세션이 추가한 마이그레이션이 있으면 그 뒤로 붙이고 id를 겹치지 않게 바꾼다. 병렬 브랜치끼리 head가 둘로 갈라지면 나중에 병합하는 쪽이 down_revision을 고친다(`flask db heads`가 하나여야 한다).
  - `MAX_SEASONINGS_PER_USER = 100`, `MAX_ITEMS = 30`, `UNITS = ("큰술", "작은술", "컵", "ml", "g", "개", "꼬집")`, `BASIS_UNITS = {"main_weight": ("g",), "servings": ("인분",), "yield": ("컵", "ml")}`.
  - `parse_seasoning(data) -> dict`(생성·PUT 공통, 전체 교체):
    - name: `text(..., "이름은", 30)`
    - basis/basis_unit: 표에 없는 조합 → 400 `기준을 다시 확인해주세요.`
    - basis_amount: bool 아닌 숫자, `servings`면 정수 1~20, 그 외 0 초과 10,000 이하 → 아니면 400 `기준 양을 다시 확인해주세요.`
    - main_ingredient: 없음/빈 문자열 → None, 문자열 1~50자 아니면 400 `주재료는 50자까지 입력해주세요.`
    - items: 리스트 1~30 → 아니면 400 `양념을 1~30개 입력해주세요.` / 각 줄 dict 아님 400 `잘못된 요청이에요.` / 이름 1~30자 400 `N번째 양념 이름은 1~30자로 입력해주세요.` / 양 bool 아닌 유한 숫자 0 초과 10,000 이하 400 `N번째 양념 양을 다시 확인해주세요.` / 단위 목록 밖 400 `N번째 양념 단위를 다시 골라주세요.`
  - `seasoning_json(s)` → `{id, name, basis, basis_amount, basis_unit, main_ingredient, items, source: "user", source_note: null, updated_at}`(화면 `Seasoning` 타입과 같은 모양).
  - API(로그인):
    - `GET /api/seasonings` → `{items:[...]}` `updated_at`·id 내림차순, 페이지 없음(26절 수십 개).
    - `POST /api/seasonings` → 201. 100개 → 400 `양념 비율은 100개까지 저장할 수 있어요.` 이름 중복 → 400 `같은 이름의 비율이 있어요.`(`commit_or_duplicate`)
    - `GET/PUT/DELETE /api/seasonings/<id>` → 상세 / 상세 / 204. 남의 것 404.
  - `ponytail:` 기본 비율을 "고쳐 쓰기"는 화면에서 기본 비율 내용을 폼에 채워 `POST`(복사)로 한다. 서버에 기본 비율 행·숨기기가 없다.

- [ ] **Step 0: 브랜치** — main에서 `feature/seasonings-backend`. 마이그레이션 head 확인.

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_seasonings_migration_adds_and_removes_table`.
  - `test_seasonings.py`
    - `test_requires_login`(목록 401, POST CSRF 헤더 없음 400).
    - `test_create_list_get_update_delete` — 201 모양, 목록 최신 순, PUT 전체 교체 후 `updated_at` 바뀜, DELETE 204 후 404.
    - `test_validation` parametrize — 이름 없음/31자, basis `yield` + unit `g`, servings 1.5·0·21, basis_amount `True`·`"600"`·0·10001·`float("nan")`(JSON으로는 못 보내므로 `1e999` 문자열 대신 `10001` 경계만), items 0개·31개·줄이 문자열·이름 31자·양 0·양 `True`·단위 `숟가락` → 각 문구 확인.
    - `test_duplicate_name_400_and_cap_100`(100개는 루프 대신 `db.session.add_all`로 넣고 API로 101번째).
    - `test_other_users_seasoning_is_404`(GET·PUT·DELETE).
    - `test_user_delete_cascades`(사용자 삭제 시 함께 삭제 — 기존 CASCADE 테스트 모양).

- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 개발 DB `flask db upgrade` 후 `flask db check` 차이 없음.

- [ ] **Step 3: 스펙 갱신** — 22절: `seasonings`에서 user_id NULL(기본 제공)·`source`·`source_note` 칸을 빼고 기본 비율은 화면 데이터 파일로, `seasoning_items` 테이블 대신 `items` JSON(순서 = 표시 순서), 검증 한도, API 표.

- [ ] **Step 4: 커밋** — `git add backend docs && git commit -m "feat: 내 양념 비율 저장 API(추가·수정·삭제, 사용자당 100개)" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

### Task 3: 양념 비율 화면 (시안 승인 후)

**Files:**
- Create: `frontend/src/pages/Seasonings.tsx`, `frontend/src/pages/SeasoningCalc.tsx`, `frontend/src/pages/SeasoningForm.tsx`
- Modify: `frontend/src/pages/Recipes.tsx`(`SeasoningSoon` 제거), `frontend/src/useHashRoute.ts`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/components/Icon.tsx`(시안에 필요한 것만)

**Interfaces:**
- Consumes: T1 `seasoning.ts`·`SEASONING_PRESETS`, T2 API, `useResource`/`forgetResources`, `navigate`/`goBack`, `openDraft`(3b T4 `RecipeForm.tsx`), `useAsyncAction`, 3a 폼의 행 추가·빼기·나가기 확인 패턴(`RecipeForm.tsx`)
- Produces:
  - 경로: `/recipes/seasonings/preset/:id`, `/recipes/seasonings/new`, `/recipes/seasonings/:id`, `/recipes/seasonings/:id/edit`(모두 숫자 id, 기존 `matchRoute` 규칙 그대로).
  - `Seasonings.tsx`(칸 본문): `기본 비율` 묶음(프리셋 6개 행: 이름 · `고기 600g 기준`/`2인분 기준`/`1컵 기준`), `내 비율` 묶음(`GET /api/seasonings`, 빈 상태 `자주 쓰는 비율을 저장해두면 바로 계산해줘요.`) + `비율 추가`.
  - `SeasoningCalc.tsx`: 기준 입력 — `servings`는 `−/+`(1~20), `main_weight`는 숫자 입력(g) + 빠른 칩(`300g`·`600g`·`1kg`), `yield`는 숫자 + `컵/ml` 고르기. 입력이 바뀌면 바로 결과 목록: 양념 이름 · 큰 글씨 `3½큰술` · 보조 `밥숟가락 약 5개`. 입력이 비었거나 0이면 `기준 양을 입력해주세요.` 아래 안내 `계량스푼 기준이에요(1큰술 15ml). 취향에 따라 조절해주세요.`와 기본 비율이면 `출처: …`.
    - 버튼: `레시피 재료로 가져오기` → `openDraft({ title: 이름, servings: basis가 servings면 입력값 아니면 2, ingredients: 결과 [{name, amount: text}], steps: [], source: "mine", source_url: null })`. 기본 비율이면 `내 비율로 고쳐 쓰기`(폼에 복사), 내 비율이면 `수정`과 그 아래 `.btn.danger-text` `이 비율 삭제`(확인창 `이 비율을 삭제할까요?` → `DELETE` → `forgetResources("/api/seasonings")` → `goBack("/recipes")`).
    - `ponytail:` 입력값은 저장하지 않는다(화면을 나가면 기준량으로 돌아감). 자주 바꾸면 localStorage.
  - `SeasoningForm.tsx`: 이름, 기준 3개 라디오(`고기 무게`·`인분`·`완성량`), 기준 양·단위, 주재료(`고기 무게`일 때만), 양념 행(이름 · 양 `inputMode="decimal"` · 단위 select) 추가·빼기(최대 30), 저장 → `POST`/`PUT` → 계산 화면으로 `replace`. 서버 400 문구는 해당 칸 아래에 보여준다(`N번째 양념` 문구면 그 행 빨간 테두리). 작성 중 `< 레시피`는 기존 확인창.
  - `Recipes.tsx`: `seasoning` 칸이 `Seasonings`를 그린다.

- [ ] **Step 0: 브랜치** — main(T1·T2·3b T4 병합, 시안 승인)에서 `feature/seasoning-ui`.
- [ ] **Step 1: 경로** — `node` 한 줄 검사: `matchRoute("/recipes/seasonings/preset/3").params.id === "3"`, `/recipes/seasonings/7/edit` 패턴, `/recipes/seasonings/new`가 `:id`에 먹히지 않음, 기존 경로 그대로 → `matchRoute ok`.
- [ ] **Step 2: 칸 목록** — `npm run build`.
- [ ] **Step 3: 계산 화면** — `npm run build`, Task 1 `seasoning ok` 다시 확인.
- [ ] **Step 4: 내 비율 폼·삭제** — `npm run build`.
- [ ] **Step 5: 폰 확인**(갤럭시 S22 Ultra, 개발용 로그인):
  - `양념 비율` 칸 → `불고기` → 고기 `900g` → 간장이 `4½큰술 (밥숟가락 약 …개)`처럼 분수로, 소량 재료는 작은술·`약간`으로 보인다. `+/−`·칩 누르면 바로 바뀐다.
  - `레시피 재료로 가져오기` → 레시피 폼에 양념 줄이 채워져 있다 → 저장 → 내 레시피 상세.
  - `내 비율로 고쳐 쓰기` → 폼에 복사됨 → 이름 바꿔 저장 → 계산 화면 → 뒤로가기 → `내 비율`에 보인다. `수정`, 그 아래 연빨강 배경·테두리 `이 비율 삭제`.
  - 폼에서 양 `0`으로 저장 → 그 행 빨간 테두리와 문구. 숫자 칸을 눌러도 화면이 확대되지 않는다(16px).
  - 라이트·다크, 384px에서 결과 글자·밥숟가락 보조 문구가 한 줄 안에 읽힌다.
- [ ] **Step 6: 커밋** — `git add frontend && git commit -m "feat: 양념 비율 칸(기본·내 비율), 계산 화면(숟가락·밥숟가락 환산), 내 비율 폼, 레시피 재료로 가져오기" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

## 3c단계 완료 기준

- 백엔드: SQLite·PostgreSQL 테스트 실패 0, 경고 0. `flask db heads`가 하나, 개발 DB `flask db check` 차이 없음.
- 프론트엔드: `npm run build` 성공, `seasoning ok`, `matchRoute ok`.
- 세 브랜치가 순서대로 main에 `--no-ff` 병합됨.
- 기본 비율 6개 값과 출처를 사용자가 확인함. 밥숟가락 기준 출처가 스펙 22절에 적혀 있음(없으면 "스펙 예시 기준" 표시).
- 장보기 담기(22절 "없는 양념 재료는 장보기 목록에 담기")는 4단계에서 한다.

## 시안에서 사용자가 정할 것 (추천 기본값)

- 컵으로 바꾸는 경계 — **추천: ½컵(100ml) 이상이면 컵.** 대안: 1컵 이상만 컵(그 아래는 `10큰술`처럼 큰술).
- 작은술로 바꾸는 경계 — **추천: 1큰술 미만이면 작은술, ¼작은술 미만은 `약간`.**
- 밥숟가락 1개 용량 — **추천: 출처 확인 후 결정, 확인 전 12ml(스펙 예시 3큰술 ≈ 4개).** 표시는 ½개 단위.
- 밥숟가락 표시 모양 — **추천: 결과 아래 작은 회색 줄 `밥숟가락 약 4개`.** 대안: 스펙 예시처럼 한 줄 괄호 `3큰술 (밥숟가락 약 4개)` — 384px에서 긴 이름과 겹치면 줄바꿈이 생긴다.
- 기준 입력 방식 — **추천: 인분은 −/+, 고기 무게는 숫자 + `300g·600g·1kg` 칩, 완성량은 숫자 + 컵/ml.**
- 기본 비율 6개의 수치 — **사용자 확인 필요.** 추천: 출처 2곳 이상 중간값, 계산 화면에 출처 표시.
- 계산 화면 진입 — **추천: 목록 행을 누르면 바로 계산 화면(상세·계산을 한 화면).**
- 기본 비율 고치기 — **추천: `내 비율로 고쳐 쓰기`(복사). 기본 비율 자체 수정·숨기기는 없음.**
