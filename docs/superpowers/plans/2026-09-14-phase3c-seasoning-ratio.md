# 3c단계(양념 비율 계산기) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 레시피 탭 `양념 비율` 칸에서 제육볶음·불고기·간장조림·초고추장·쌈장·갈비 양념 같은 기본 양념을 고르고, 주재료 무게·인분·완성량을 넣으면 각 양념의 양을 실제로 뜰 수 있는 숟가락 단위(`3큰술`, `1½작은술`)와 그 아래 회색 줄의 밥숟가락 어림(`밥숟가락 약 4개`)으로 보여준다. 자주 쓰는 비율은 `내 비율`로 저장·수정·삭제한다.

**Architecture:** 계산은 전부 화면에서 한다. 단위 환산·배율·분수 반올림·기준 문구는 순수 함수 모듈 `frontend/src/seasoning.ts` 하나에 두고(기존 `format.ts`의 `SNAPS`·`formatAmountNumber` 재사용), 기본 양념은 서버 테이블이 아니라 **화면 번들의 데이터 파일**(`frontend/src/data/seasoningPresets.ts`)로 둔다 — 운영자가 바꾸는 값이라 시드 CLI·마이그레이션 데이터가 필요 없고, 출처 메모와 함께 코드 리뷰로 바뀐다. 사용자 "내 비율"만 서버에 저장한다(`seasonings` 테이블 하나, 양념 줄은 3a `recipes.ingredients`처럼 JSON 칸). 화면은 승인된 시안 `docs/design/recipes-3b3c/Seasoning*.dc.html`을 그대로 따른다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, pytest 9.1.1 / React 19 + TypeScript + Vite 8, Node 24(`.ts` 직접 실행 한 줄 검사)

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 2절(3단계), 22절(양념 비율 계산기 — 2026-09-14 시안 승인 결정 포함: 기본 양념은 화면 데이터 파일, `items` JSON, 밥숟가락 표시), 26절(수십 개 목록은 페이지 없음). **디자인: `docs/design/recipes-3b3c/SeasoningList.dc.html`, `SeasoningCalc.dc.html`, `SeasoningCalcDark.dc.html`, `SeasoningForm.dc.html`(사용자 승인 2026-09-14).** 3b와 파일·API가 겹치지 않아 순서와 무관하게 진행할 수 있다.

## Global Constraints

- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다.
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. SQLite와 PostgreSQL(`TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate`, 이미 설정됨) 둘 다 실패 0, 경고 0.
- 프론트 태스크는 `cd frontend && npm run build`(`tsc --noEmit` + `vite build`)가 오류 없이 끝나야 한다. 순수 함수는 `node --input-type=module -e` + `node:assert/strict` 한 줄 검사(테스트 러너를 새로 들이지 않는다).
- 테스트는 절대 실제 외부 API를 부르지 않는다(이번 단계는 외부 호출 자체가 없다). 키는 `backend/.env`에만 두고 읽거나 커밋하지 않는다. `DEV_MODE` 예시 결과가 필요한 기능은 없다(기본 양념이 곧 예시).
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정하고 남의 것은 404.
- 모바일 384px 기준. 터치 영역 44px 이상, 입력 글자 16px 이상(숫자 입력은 `inputMode="decimal"`). 아이콘은 이모지 대신 `Icon`. 라이트·다크 모두 확인(`SeasoningCalcDark` 프레임).
- **삭제 버튼은 `.btn.danger-text`(연빨강 배경 + 테두리)로 다른 버튼 아래에 둔다(`이 비율 삭제`는 `수정` 아래).**
- 화면 문구는 시안 그대로, 새 문구는 보조 용언을 붙여 쓴다(`보여줘요`, `입력해주세요`, `조절해주세요`). 개발 용어(프리셋, 배율 계수, ml 환산)는 화면에 쓰지 않는다.
- 시안의 `r3-*` 클래스 스타일은 `docs/design/recipes-3b3c/Seasoning*.dc.html`의 `<style>`에서 `frontend/src/styles.css`로 옮기되, 3b에서 이미 옮긴 것·기존 클래스(`stepper`, `icon-btn`)는 다시 만들지 않는다.
- 개발 서버는 Vite 5180, Flask 5181. 5173은 건드리지 않는다. 개발 DB는 지우지 않는다.
- 브랜치는 태스크마다 하나, 리뷰 통과 후 main에 `--no-ff` 병합.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음 한 줄만 붙인다:
  ```
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치

| 브랜치 | 태스크 | 시작 시점 | 시안 |
|---|---|---|---|
| `feature/seasoning-calc` | 1 (숟가락 환산·배율·기준 문구 순수 모듈, 기본 양념 데이터) | main에서 바로 | **UI 시안 승인 전 진행 가능** |
| `feature/seasonings-backend` | 2 (내 비율 테이블·마이그레이션·API) | main에서 바로(태스크 1과 병렬 가능, 겹치는 파일 없음) | **UI 시안 승인 전 진행 가능** |
| `feature/seasoning-ui` | 3 (양념 비율 칸, 계산 화면, 내 비율 폼) | 태스크 1·2 병합 뒤 | **시안 승인 후**(승인됨 2026-09-14) |

## 파일 구조

```
frontend/src/
  format.ts                                         (수정, T1) SNAPS export
  seasoning.ts                                      (신규, T1) 단위·배율·숟가락 표시·기준 문구·양 입력 해석 순수 함수, 타입
  data/seasoningPresets.ts                          (신규, T1) 기본 양념 6개 + 출처 메모
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
docs/superpowers/specs/2026-09-13-recipe-ai-design.md (수정, T1) 밥숟가락 출처·기본 양념 수치 출처
```

---

### Task 1: 숟가락 환산·배율 순수 모듈과 기본 양념 데이터 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `frontend/src/seasoning.ts`, `frontend/src/data/seasoningPresets.ts`
- Modify: `frontend/src/format.ts`(`SNAPS`를 export만), 스펙 문서 22절(밥숟가락 출처·기본 양념 출처)

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
  export const RICE_SPOON_ML: number;  // 밥숟가락 1개 용량. 출처 확인 전 12 (Step 2)
  export const BASIS_UNITS: Record<Basis, BasisUnit[]>;  // main_weight: ["g"], servings: ["인분"], yield: ["컵", "ml"]

  /** 입력량 ÷ 기준량. yield의 컵↔ml는 SPOON_ML로 맞춘다. 0 이하·NaN이면 null */
  export function scaleFactor(s: Pick<Seasoning, "basis_amount" | "basis_unit">, input: number, inputUnit: BasisUnit): number | null;

  /** 0.33 → "⅓", 3.5 → "3½", 0.9 → "1", 12.4 → "12". 가장 가까운 ¼·⅓·½·⅔·¾ 또는 정수(10 이상은 정수) */
  export function snapSpoon(value: number): string;

  /** 한 양념 줄 × 배율 → 시안 SeasoningCalc의 굵은 양(text)과 회색 보조 줄(sub) */
  export function scaleItem(item: SeasoningItem, factor: number): { text: string; sub: string | null };

  /** 시안 SeasoningList·SeasoningCalc 보조 줄: "돼지고기 600g 기준", "2인분 기준", "완성 ½컵 기준", "완성 300ml 기준" */
  export function basisLabel(s: Pick<Seasoning, "basis" | "basis_amount" | "basis_unit" | "main_ingredient">): string;

  /** 계산 화면 배지: 1.5 → "×1.5", 1 → "×1", 1/3 → "×0.33" */
  export function ratioLabel(factor: number): string;

  /** 폼 양 입력: "½"·"1½"·"1/2"·"1 1/2"·"0.5"·"3" → 숫자, 비었거나 0 이하·틀린 모양·"1/0" → null */
  export function parseAmountInput(text: string): number | null;
  ```
- **표시 규칙(스펙 22절, 시안 `SeasoningCalc`와 맞춤):**
  1. 부피 단위(`큰술`·`작은술`·`컵`)는 `ml = amount × SPOON_ML[unit] × factor`로 바꾼 뒤 **ml만 보고** 단위를 다시 고른다:
     - `ml ≥ 100`(½컵 이상) → `snapSpoon(ml / 200) + "컵"`, sub null
     - `ml ≥ 15`(1큰술 이상) → `snapSpoon(ml / 15) + "큰술"`, sub `밥숟가락 약 N개`(N = `Math.round(ml / RICE_SPOON_ML)`, 최소 1)
     - `ml ≥ 1.25`(¼작은술 이상) → `snapSpoon(ml / 5) + "작은술"`, sub는 `ml ≥ 3.75`(¼큰술 이상)면 `snapSpoon(ml / 15) + "큰술"`(시안 `참기름 1½작은술 / ½큰술`), 아니면 null
     - 그보다 적으면 `"약간"`, sub null
  2. 원래 단위가 `ml`이면 ml 그대로(10 이상 정수, 그 아래 소수 한 자리), sub null — ml로 적은 건 계량컵을 쓴다는 뜻.
  3. `g`·`개`는 `formatAmountNumber(amount × factor) + unit`. `꼬집`은 `Math.max(1, Math.round(...))꼬집`. sub null.
  - `ponytail:` 반올림 오차(예 110ml → ½컵)는 시안 안내 `입맛에 맞게 조절해주세요`로 둔다. 불만이 나오면 `½컵 + ⅔큰술`처럼 나머지 표시를 추가.
- `data/seasoningPresets.ts`: `export const SEASONING_PRESETS: Seasoning[]` — `id` 1~6(경로용, 바꾸지 않음), `source: "default"`, `source_note`에 비교한 출처 이름(2곳 이상)과 확인 날짜. 기준은 시안 `SeasoningList` 그대로: 제육볶음 양념(`main_weight` 돼지고기 600g), 불고기 양념(`main_weight` 소고기 600g), 간장조림 양념(`servings` 2인분), 초고추장(`yield` 0.5컵), 쌈장(`yield` 0.5컵), 갈비 양념(`main_weight` 소갈비, 무게는 출처 확인 후). 목록 순서도 이 순서.

- [ ] **Step 0: 브랜치** — `cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/seasoning-calc`

- [ ] **Step 1: 한 줄 검사를 먼저 쓰고 실패 확인**
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && node --input-type=module -e '
import assert from "node:assert/strict";
import { snapSpoon, scaleItem, scaleFactor, basisLabel, ratioLabel, parseAmountInput, RICE_SPOON_ML } from "./src/seasoning.ts";
import { SEASONING_PRESETS } from "./src/data/seasoningPresets.ts";
assert.equal(snapSpoon(0.33), "⅓"); assert.equal(snapSpoon(3.5), "3½"); assert.equal(snapSpoon(0.9), "1"); assert.equal(snapSpoon(12.4), "12");
const item = (name, amount, unit, factor) => scaleItem({ name, amount, unit }, factor);
// 시안 SeasoningCalc: 돼지고기 600g 기준 → 900g(×1.5)
assert.equal(item("고추장", 2, "큰술", 1.5).text, "3큰술");
assert.equal(item("고춧가루", 1, "큰술", 1.5).text, "1½큰술");
assert.equal(item("설탕", 2 / 3, "큰술", 1.5).text, "1큰술");
assert.deepEqual(item("참기름", 1, "작은술", 1.5), { text: "1½작은술", sub: "½큰술" });
if (RICE_SPOON_ML === 12) {
  assert.equal(item("고추장", 2, "큰술", 1.5).sub, "밥숟가락 약 4개");
  assert.equal(item("고춧가루", 1, "큰술", 1.5).sub, "밥숟가락 약 2개");
  assert.equal(item("설탕", 2 / 3, "큰술", 1.5).sub, "밥숟가락 약 1개");
}
assert.equal(item("간장", 1, "큰술", 0.5).text, "1½작은술");      // 큰술이 작으면 작은술
assert.deepEqual(item("소금", 1, "작은술", 1 / 3), { text: "⅓작은술", sub: null });
assert.equal(item("소금", 1, "작은술", 0.1).text, "약간");
assert.deepEqual(item("물", 1, "컵", 2), { text: "2컵", sub: null });
assert.equal(item("간장", 10, "큰술", 1).text, "¾컵");             // 150ml → ½컵 이상은 컵
assert.equal(item("물", 150, "ml", 1.5).text, "225ml");
assert.deepEqual(item("고춧가루", 20, "g", 1.5), { text: "30g", sub: null });
assert.equal(item("후추", 1, "꼬집", 0.3).text, "1꼬집");
assert.equal(scaleFactor({ basis_amount: 600, basis_unit: "g" }, 900, "g"), 1.5);
assert.equal(scaleFactor({ basis_amount: 0.5, basis_unit: "컵" }, 100, "ml"), 1);
assert.equal(scaleFactor({ basis_amount: 2, basis_unit: "인분" }, 0, "인분"), null);
assert.equal(basisLabel({ basis: "main_weight", basis_amount: 600, basis_unit: "g", main_ingredient: "돼지고기" }), "돼지고기 600g 기준");
assert.equal(basisLabel({ basis: "servings", basis_amount: 2, basis_unit: "인분", main_ingredient: null }), "2인분 기준");
assert.equal(basisLabel({ basis: "yield", basis_amount: 0.5, basis_unit: "컵", main_ingredient: null }), "완성 ½컵 기준");
assert.equal(basisLabel({ basis: "yield", basis_amount: 300, basis_unit: "ml", main_ingredient: null }), "완성 300ml 기준");
assert.equal(ratioLabel(1.5), "×1.5"); assert.equal(ratioLabel(1), "×1"); assert.equal(ratioLabel(1 / 3), "×0.33");
for (const [text, value] of [["½", 0.5], ["1½", 1.5], ["1/2", 0.5], ["1 1/2", 1.5], ["0.5", 0.5], ["3", 3]]) assert.equal(parseAmountInput(text), value, text);
for (const text of ["", "abc", "0", "-1", "1/0", "½½"]) assert.equal(parseAmountInput(text), null, text);
assert.equal(new Set(SEASONING_PRESETS.map((p) => p.id)).size, SEASONING_PRESETS.length);
for (const p of SEASONING_PRESETS) {
  assert.ok(p.items.length > 0 && p.basis_amount > 0 && p.source_note, p.name);
  for (const i of p.items) assert.ok(i.amount > 0 && i.name, `${p.name} ${i.name}`);
}
console.log("seasoning ok");
'
```
Expected(구현 전): 모듈 없음 오류. 구현 후: `seasoning ok`.

- [ ] **Step 2: 밥숟가락 기준 확인** — 공신력 있는 출처(농촌진흥청·식약처·한국영양학회 등 계량 안내)에서 밥숟가락(가정용 숟가락) 1개 용량을 찾아 `RICE_SPOON_ML`과 주석 출처를 정한다. 출처가 없거나 서로 다르면 **12ml**(시안 `3큰술 → 밥숟가락 약 4개`, `1큰술 → 약 1개`와 맞음)로 두고 주석에 "출처 미확인, 시안 기준"을 남긴다. 화면 안내가 이미 `밥숟가락은 집마다 달라서 대략으로 보여줘요`라 어림값이다.

- [ ] **Step 3: 구현** — `seasoning.ts`(Interfaces·표시 규칙대로), `format.ts`에서 `SNAPS` export.

- [ ] **Step 4: 기본 양념 데이터** — 여섯 양념마다 신뢰할 수 있는 출처 2곳 이상(식약처·농진청 메뉴젠·요리 전문 서적 등)을 비교해 중간값에 가깝게 정하고 `source_note`에 출처 이름·날짜를 남긴다. 값은 PR 설명에 표로 붙여 **사용자 확인**을 받는다. 인터넷을 쓸 수 없는 환경이면 값을 지어내지 말고 이 스텝을 보류로 표시하고 멈춘다.

- [ ] **Step 5: 확인** — Step 1 검사 `seasoning ok`, `cd frontend && npm run build` 성공.

- [ ] **Step 6: 스펙 갱신** — 22절에 밥숟가락 기준 출처(또는 "시안 기준 12ml, 출처 미확인")와 기본 양념 출처 요약.

- [ ] **Step 7: 커밋** — `git add frontend docs && git commit -m "feat: 양념 비율 계산(숟가락 분수·작은술 자동 환산·밥숟가락 어림·기준 문구), 기본 양념 데이터" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

### Task 2: 내 비율 저장 백엔드 (UI 시안 승인 전 진행 가능)

**Files:**
- Create: `backend/app/seasonings.py`, `backend/migrations/versions/b1b1c1d1e1f1_seasonings.py`, `backend/tests/test_seasonings.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`(auth), `text`, `commit_or_duplicate`(validation), `utcnow`
- Produces:
  - `app.models.Seasoning`(`seasonings`, 스펙 22절): id, user_id FK users CASCADE NOT NULL index, name String(30), basis String(20)(`main_weight|servings|yield`), basis_amount Float, basis_unit String(10)(`g|인분|컵|ml`), main_ingredient String(50) NULL, items JSON(`[{name, amount, unit}]`, 순서 = 표시 순서), created_at, updated_at(onupdate). UNIQUE(user_id, name).
  - Alembic revision `b1b1c1d1e1f1`. **down_revision은 구현 시점의 실제 head**(3b를 먼저 병합했으면 `a9b9c9d9e9f9`, 아니면 `a8b8c8d8e8f8`). `ls backend/migrations/versions`로 확인하고, 다른 세션이 추가한 마이그레이션이 있으면 그 뒤로 붙이고 id를 겹치지 않게 바꾼다. 병렬 브랜치끼리 head가 둘로 갈라지면 나중에 병합하는 쪽이 down_revision을 고친다(`flask db heads`가 하나여야 한다).
  - `MAX_SEASONINGS_PER_USER = 100`, `MAX_ITEMS = 30`, `UNITS = ("큰술", "작은술", "컵", "ml", "g", "개", "꼬집")`, `BASIS_UNITS = {"main_weight": ("g",), "servings": ("인분",), "yield": ("컵", "ml")}`.
  - `parse_seasoning(data) -> dict`(생성·PUT 공통, 전체 교체):
    - name: `text(..., "이름은", 30)`
    - basis/basis_unit: 표에 없는 조합 → 400 `기준을 다시 확인해주세요.`
    - basis_amount: bool 아닌 숫자, `servings`면 정수 1~20, 그 외 0 초과 10,000 이하 → 아니면 400 `기준 양을 다시 확인해주세요.`
    - main_ingredient: 없음/빈 문자열 → None, 문자열 1~50자 아니면 400 `주재료는 50자까지 입력해주세요.` `main_weight`가 아니면 저장하지 않는다(None).
    - items: 리스트 1~30 → 아니면 400 `양념을 1~30개 입력해주세요.` / 각 줄 dict 아님 400 `잘못된 요청이에요.` / 이름 1~30자 400 `N번째 양념 이름은 1~30자로 입력해주세요.` / 양 bool 아닌 유한 숫자 0 초과 10,000 이하 400 `N번째 양념 양을 다시 확인해주세요.` / 단위 목록 밖 400 `N번째 양념 단위를 다시 골라주세요.`
  - `seasoning_json(s)` → `{id, name, basis, basis_amount, basis_unit, main_ingredient, items, source: "user", source_note: null, updated_at}`(화면 `Seasoning` 타입과 같은 모양).
  - API(로그인):
    - `GET /api/seasonings` → `{items:[...]}` `updated_at`·id 내림차순, 페이지 없음(26절 수십 개).
    - `POST /api/seasonings` → 201. 100개 → 400 `양념 비율은 100개까지 저장할 수 있어요.` 이름 중복 → 400 `같은 이름의 비율이 있어요.`(`commit_or_duplicate`)
    - `GET/PUT/DELETE /api/seasonings/<id>` → 상세 / 상세 / 204. 남의 것 404.
  - `ponytail:` 기본 양념을 고치는 것은 화면에서 기본 양념 내용을 폼에 채워 `POST`(복사)로 한다(`이 비율 고쳐서 내 비율로`). 서버에 기본 양념 행·숨기기가 없다.

- [ ] **Step 0: 브랜치** — main에서 `feature/seasonings-backend`. 마이그레이션 head 확인.

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_migrations.py`: `test_seasonings_migration_adds_and_removes_table`.
  - `test_seasonings.py`
    - `test_requires_login`(목록 401, POST CSRF 헤더 없음 400).
    - `test_create_list_get_update_delete` — 201 모양, 목록 최신 순, PUT 전체 교체 후 `updated_at` 바뀜, DELETE 204 후 404.
    - `test_validation` parametrize — 이름 없음/31자, basis `yield` + unit `g`, servings 1.5·0·21, basis_amount `True`·`"600"`·0·10001, items 0개·31개·줄이 문자열·이름 31자·양 0·양 `True`·단위 `숟가락` → 각 문구 확인.
    - `test_main_ingredient_only_for_main_weight` — `servings`에 주재료를 보내도 None.
    - `test_duplicate_name_400_and_cap_100`(100개는 `db.session.add_all`로 넣고 API로 101번째).
    - `test_other_users_seasoning_is_404`(GET·PUT·DELETE).
    - `test_user_delete_cascades`(사용자 삭제 시 함께 삭제 — 기존 CASCADE 테스트 모양).

- [ ] **Step 2: 실패 확인 → 구현 → 전체 테스트(SQLite·PostgreSQL)** — 개발 DB `flask db upgrade` 후 `flask db check` 차이 없음.

- [ ] **Step 3: 커밋** — `git add backend && git commit -m "feat: 내 양념 비율 저장 API(추가·수정·삭제, 사용자당 100개)" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

### Task 3: 양념 비율 화면 (시안 승인 후)

**시안(그대로 따른다):** `docs/design/recipes-3b3c/SeasoningList.dc.html`, `SeasoningCalc.dc.html`, `SeasoningCalcDark.dc.html`, `SeasoningForm.dc.html`

**Files:**
- Create: `frontend/src/pages/Seasonings.tsx`, `frontend/src/pages/SeasoningCalc.tsx`, `frontend/src/pages/SeasoningForm.tsx`
- Modify: `frontend/src/pages/Recipes.tsx`(`SeasoningSoon` 제거), `frontend/src/useHashRoute.ts`, `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/components/Icon.tsx`(시안에 필요한 것만)

**Interfaces:**
- Consumes: T1 `seasoning.ts`·`SEASONING_PRESETS`, T2 API, `useResource`/`forgetResources`, `navigate`/`goBack`, `useAsyncAction`, 3a 폼의 행 추가·빼기·나가기 확인 패턴(`RecipeForm.tsx`), 기존 `stepper`·`icon-btn` 클래스
- Produces:
  - 경로: `/recipes/seasonings/preset/:id`, `/recipes/seasonings/new`, `/recipes/seasonings/:id`, `/recipes/seasonings/:id/edit`(모두 숫자 id, 기존 `matchRoute` 규칙 그대로).
  - **`SeasoningList` — `Seasonings.tsx`(칸 본문):** 묶음 `내 비율`(`GET /api/seasonings`, 0개면 묶음 자체를 숨김)이 **위**, 묶음 `기본 양념`(프리셋 6개)이 아래. 행: 제목(`우리집 제육 (덜 달게)`) · 보조 `basisLabel(s) + " · 재료 N개"`(`돼지고기 600g 기준 · 재료 6개`) · 오른쪽 화살표, 44px 이상. 목록 아래 `내 비율 만들기`(secondary) → `/recipes/seasonings/new`.
  - **`SeasoningCalc` — `SeasoningCalc.tsx`:** 뒤로 `레시피`, 제목 = 이름(`제육볶음 양념`), 보조 `기본 비율 · 돼지고기 600g 기준`(내 비율이면 `내 비율 · …`).
    - 기준 섹션 머리: `main_weight`면 `돼지고기 얼마나 써요?`(`main_ingredient` 없으면 `주재료 얼마나 써요?`), `servings`면 `몇 인분 만들어요?`, `yield`면 `얼마나 만들어요?` + 오른쪽 배지 `ratioLabel(factor)`(`×1.5`).
    - `stepper`(− · 값+단위 `900 g` · +): 한 번에 g 100 / 인분 1 / 컵 ¼ / ml 50, 최소 한 칸 이상, 최대 g 10,000·인분 20·컵 20·ml 4,000. 값을 눌러 직접 입력(`inputMode="decimal"`)도 된다. 처음 값은 기준량.
    - 빠른 칩 줄(선택 칩 `on`): `main_weight` `300g · 600g · 900g · 1kg · 1.2kg`(시안 그대로), `servings` `1 · 2 · 3 · 4인분`, `yield` `½컵 · 1컵 · 2컵`(시안 프레임은 주재료 무게만 있어 같은 모양으로 만든다). `yield`이고 기준 단위가 ml이면 칩은 `100ml · 200ml · 400ml`.
    - 양념 섹션 머리 `양념` + 오른쪽 힌트 `계량스푼 기준`. 줄마다 왼쪽 이름, 오른쪽 굵은 `text`와 그 아래 회색 `sub`(없으면 한 줄). 입력이 비었거나 0이면 결과 대신 `기준 양을 입력해주세요.`
    - 안내 `1큰술은 15ml예요. 밥숟가락은 집마다 달라서 대략으로 보여줘요. 입맛에 맞게 조절해주세요.` 기본 양념이면 아래 작은 글씨 `출처: {source_note}`.
    - 버튼: 기본 양념이면 `이 비율 고쳐서 내 비율로`(secondary, 전체 폭) → 모듈 변수에 프리셋을 담아 `/recipes/seasonings/new`. 내 비율이면 `수정`과 그 아래 `.btn.danger-text` `이 비율 삭제`(확인창 `이 비율을 삭제할까요?` → `DELETE` → `forgetResources("/api/seasonings")` → `goBack("/recipes")`).
    - `ponytail:` 입력값은 저장하지 않는다(화면을 나가면 기준량으로 돌아감). 자주 바꾸면 localStorage.
    - 다크는 `SeasoningCalcDark`와 대조.
  - **`SeasoningForm` — `SeasoningForm.tsx`:** 뒤로 `양념 비율`, 제목 `내 비율 만들기`(수정이면 `내 비율 고치기`), 필드 `이름`, 질문 `무엇을 기준으로 할까요?` + 세그먼트 `주재료 무게 · 인분 · 완성량`, `기준` 줄: 주재료 무게면 주재료 이름 입력(`돼지고기`) + 양 입력 + 단위 `g`, 인분이면 양 입력 + `인분`, 완성량이면 양 입력 + `컵/ml` 고르기. `양념 재료` 행: 이름 · 양(글자 입력, `½`·`1½`·`1/2` 허용 → `parseAmountInput`, 틀리면 그 칸 빨간 테두리 `양을 숫자나 ½처럼 입력해주세요`) · 단위 select(`큰술·작은술·컵·ml·g·개·꼬집`) · 빼기 아이콘 버튼(`aria-label="고추장 빼기"`, 44px). 아래 `재료 추가`(최대 30). 하단 `취소` · `저장` → `POST`/`PUT` → 계산 화면으로 `replace`, `forgetResources("/api/seasonings")`. 서버 400 문구는 해당 칸 아래(`N번째 양념` 문구면 그 행 빨간 테두리, 이름 중복은 이름 칸). 폼의 양 표시는 `formatAmountNumber`로(0.5 → `½`). 작성 중 뒤로·`취소`는 기존 확인창 `작성 중인 내용이 사라져요. 나갈까요?`. 기본 양념에서 왔으면 값이 채워진 채로 열린다(이름은 그대로, 저장할 때 중복이면 서버 문구).
  - `Recipes.tsx`: `seasoning` 칸이 `Seasonings`를 그린다.

- [ ] **Step 0: 브랜치** — main(T1·T2 병합)에서 `feature/seasoning-ui`. 시안 4개 프레임을 열어 둔다.
- [ ] **Step 1: 경로·스타일** — 시안 `<style>`의 필요한 `r3-*`(`r3-quick`, `r3-ratio`, `r3-basis`, `r3-sitems`, `r3-samt` 등)을 `styles.css`로. `node` 한 줄 검사: `matchRoute("/recipes/seasonings/preset/3").params.id === "3"`, `/recipes/seasonings/7/edit` 패턴, `/recipes/seasonings/new`가 `:id`에 먹히지 않음, 기존 경로 그대로 → `matchRoute ok`.
- [ ] **Step 2: 칸 목록** — `npm run build`.
- [ ] **Step 3: 계산 화면** — `npm run build`, Task 1 `seasoning ok` 다시 확인.
- [ ] **Step 4: 내 비율 폼·삭제** — `npm run build`.
- [ ] **Step 5: 폰 확인**(갤럭시 S22 Ultra, 개발용 로그인). 시안 프레임과 대조:
  - `양념 비율` 칸 → `기본 양념` 6개(보조 줄 `돼지고기 600g 기준 · 재료 6개` 등), 내 비율이 없으면 그 묶음이 안 보인다.
  - `제육볶음 양념` → `900g` 칩 → 배지 `×1.5`, `고추장 3큰술 / 밥숟가락 약 4개`, `참기름 1½작은술 / ½큰술`. −/+·칩 누르면 바로 바뀐다. 안내 문구 시안 그대로.
  - `이 비율 고쳐서 내 비율로` → 폼에 복사됨 → 이름 `우리집 제육 (덜 달게)`, 설탕 양 `½` → 저장 → 계산 화면(`내 비율 · …`) → 뒤로가기 → `내 비율` 묶음이 `기본 양념` 위에 보인다. `수정`, 그 아래 연빨강 배경·테두리 `이 비율 삭제`.
  - 폼에서 양 `abc` → 그 칸 빨간 테두리와 문구. 숫자 칸을 눌러도 화면이 확대되지 않는다(16px).
  - 라이트·다크(`SeasoningCalcDark`), 384px에서 결과 글자·회색 보조 줄이 겹치지 않는다.
- [ ] **Step 6: 커밋** — `git add frontend && git commit -m "feat: 양념 비율 칸(내 비율·기본 양념), 계산 화면(숟가락·밥숟가락 어림, 빠른 칩), 내 비율 폼" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"`

---

## 3c단계 완료 기준

- 백엔드: SQLite·PostgreSQL 테스트 실패 0, 경고 0. `flask db heads`가 하나, 개발 DB `flask db check` 차이 없음.
- 프론트엔드: `npm run build` 성공, `seasoning ok`, `matchRoute ok`.
- 세 브랜치가 순서대로 main에 `--no-ff` 병합됨.
- 화면이 시안 4개 프레임과 문구·배치가 같다.
- 기본 양념 6개 값과 출처를 사용자가 확인함. 밥숟가락 기준 출처가 스펙 22절에 적혀 있음(없으면 "시안 기준 12ml, 출처 미확인").

## 남은 결정 (시안 승인 뒤에도 열려 있는 것)

- 기본 양념 6개의 수치 — **사용자 확인 필요.** 추천: 출처 2곳 이상 중간값, 계산 화면에 출처 표시.
- 밥숟가락 1개 용량 — 추천: 출처를 찾으면 그 값, 못 찾으면 12ml(시안 수치와 맞음).
- 갈비 양념 기준 무게 — 시안 목록에 보이지 않는 여섯째 항목. 추천: 소갈비 1kg 기준(출처 확인 후).
- `레시피 재료로 가져오기`·`장보기에 담기`(스펙 22절 연결) — 시안 계산 화면에 버튼이 없어 3c에서는 만들지 않는다. 추천: 3b `openDraft`가 들어간 뒤 계산 화면 보조 버튼으로 추가(장보기는 4단계).
- 컵으로 바꾸는 경계(½컵 이상) — 시안에 사례가 없어 제안값을 유지한다(사용자 수락). 초고추장·쌈장 계산에서 어색하면 1컵 이상으로 바꾼다.
