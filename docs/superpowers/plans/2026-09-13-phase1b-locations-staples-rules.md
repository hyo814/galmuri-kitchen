# 1b단계(보관 위치·필수품·품목별 경고 + 새 디자인) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 재료를 사용자 정의 보관 위치별로 관리하고, 떨어진 필수품과 품목별(식약처 참고값·달걀) 경고를 보여주며, 승인된 토스풍 시안으로 화면을 새로 입힌다.

**Architecture:** 기존 Flask 단일 앱에 블루프린트 3개(`locations`, `staples`, `item_rules`)와 모델 3개를 추가하고, 기능마다 Alembic 마이그레이션 1개(기존 사용자 데이터 이관 포함). 재료 상태 판정은 `ingredient_status`에 위치 종류·품목 규칙을 더해 "가장 심각한 상태"를 고른다. 프론트는 공통 `Sheet`(네이티브 `<dialog>`) 위에 시트들을 올리고, 디자인 토큰을 시안 값으로 교체한다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, pytest 9.1.1 / Vite 8, React 19, TypeScript

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` (14절이 이 단계의 상세, 4~8절 규칙 유지)
**Design:** `docs/design/fridge-1b/*.dc.html` (승인된 시안. 색·크기·간격 값은 이 파일들에서 그대로 가져온다)

## Global Constraints

- 경로에 공백이 있다: 저장소 루트 `/Users/limhyojin/PycharmProjects/ recipe-ai` — 항상 따옴표.
- 모든 사용자 소유 데이터는 `g.user.id`로 한정, 남의 리소스 404 `{"error": "찾을 수 없어요."}`.
- API 오류 형식 `{"error": "<한국어 메시지>"}` + 상태 코드. 상태 변경 `/api/*` 요청은 `X-Requested-With: fetch` 필수(이미 전역 처리).
- 입력 검증: 문자열 필드는 `str` 타입이어야 함(아니면 400), 정수 필드는 `bool`이 아닌 `int`.
- 기본 보관 위치(사용자 생성 시): `냉장실`(fridge), `냉동실`(freezer), `실온`(room), sort_order 0,1,2.
- 오래됨 기준(유통기한·품목 규칙 없을 때): fridge 7일, freezer 60일, room 없음.
- 상태 심각도: `danger` > `urgent` > `old` > `ok`. 정렬도 이 순서.
- 기본 품목 규칙(warn/danger, 구입일 기준): 달걀 25/30, 계란 25/30 (source `user`),
  두부 15/18, 요거트 22/25, 요구르트 22/25, 주스 25/28, 빵 21/24, 어묵 30/33, 소시지 41/44, 햄 42/45 (source `mfds`;
  식약처 소비기한 참고값 두부23·발효유32·과채주스35·빵류31·어묵42·소시지56·햄57일의 80% 내림 = danger, warn = danger−3).
- 이름 매칭 정규화: 괄호와 그 안 내용 제거 → 공백 제거 → 소문자. 필수품은 양방향 포함, 품목 규칙은 "키워드가 재료 이름에 포함"만.
- 모바일 우선(뷰포트 384px), 터치 타깃 44px 이상, 입력 글자 16px 이상. 이모지 아이콘 금지(인라인 SVG).
- 커밋 메시지 끝(빈 줄 뒤):
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치 (사용자 요청: 기능별 브랜치 → main에 `--no-ff` 병합)

| 브랜치 | 태스크 | 병합 시점 |
|---|---|---|
| `chore/test-fixture-cleanup` | 1 | 태스크 1 리뷰 통과 후 컨트롤러가 병합 |
| `design/ui-refresh` | 2 | 태스크 2 리뷰 통과 후 |
| `feature/storage-locations` | 3, 4 | 태스크 4 리뷰 통과 후 |
| `feature/staples` | 5, 6 | 태스크 6 리뷰 통과 후 |
| `feature/item-warning-rules` | 7, 8 | 태스크 8 리뷰 통과 후 |

각 브랜치의 첫 태스크 Step 0에서 `main`으로부터 브랜치를 만든다. 구현자는 병합하지 않는다.

## 파일 구조

```
backend/app/
  models.py          (수정) StorageLocation, Staple, ItemRule, Ingredient.location_id
  defaults.py        (신규) 기본 위치·기본 품목 규칙 시드
  validation.py      (신규) text(), integer() 입력 검증 헬퍼
  matching.py        (신규) normalize(), names_match(), keyword_in()
  locations.py       (신규) /api/locations
  staples.py         (신규) /api/staples
  item_rules.py      (신규) /api/item-rules
  ingredients.py     (수정) 위치 필드, 상태 판정 확장
  auth.py            (수정) upsert_user가 새 사용자에 기본값 시드
  __init__.py        (수정) 블루프린트 등록
backend/migrations/versions/
  a1b1c1d1e1f1_storage_locations.py, a2b2c2d2e2f2_staples.py, a3b3c3d3e3f3_item_rules.py
backend/tests/
  conftest.py (login이 기본값 시드), test_oauth.py, test_locations.py, test_staples.py, test_item_rules.py,
  test_matching.py, test_migrations.py, test_ingredients.py(수정)
frontend/
  index.html (폰트), src/styles.css (전면 교체), src/api.ts (타입)
  src/components/Sheet.tsx (신규), Icon.tsx (신규), IngredientForm.tsx (수정)
  src/components/LocationsSheet.tsx, StaplesSheet.tsx, RulesSheet.tsx, SettingsSheet.tsx (신규)
  src/pages/Fridge.tsx, Login.tsx, App.tsx (수정)
```

---

### Task 1: OAuth 테스트 픽스처의 공유 세션 제거

1단계 최종 리뷰에서 넘어온 항목. `oauth_app` 픽스처가 테스트 전체에 app context를 열어 두어 요청 간 DB 세션이 공유된다.

**Files:**
- Modify: `backend/tests/test_oauth.py:15-24`, `:58`

**Interfaces:**
- Consumes: `make_app` 픽스처 (conftest)
- Produces: 없음 (테스트만)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b chore/test-fixture-cleanup
```

- [ ] **Step 1: 픽스처 수정**

`backend/tests/test_oauth.py`의 `oauth_app` 픽스처를 교체:
```python
@pytest.fixture
def oauth_app(make_app):
    # app context를 붙잡지 않는다: 요청마다 새 세션을 써야 commit 누락이 테스트에서 드러난다 (conftest의 app 픽스처와 같은 이유)
    return make_app(
        KAKAO_CLIENT_ID="kid",
        KAKAO_CLIENT_SECRET="ksecret",
        GOOGLE_CLIENT_ID="gid",
        GOOGLE_CLIENT_SECRET="gsecret",
    )
```

`test_kakao_callback_logs_in`의 마지막 줄을 교체:
```python
    with oauth_app.app_context():
        assert User.query.filter_by(provider="kakao", provider_id="42").count() == 1
```

- [ ] **Step 2: 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: `39 passed`, 경고 없음

- [ ] **Step 3: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend/tests/test_oauth.py && git commit -m "test: OAuth 테스트도 요청마다 새 DB 세션 사용"
```

---

### Task 2: 새 디자인 적용 (기능 변화 없음)

승인된 시안(`docs/design/fridge-1b/Main.dc.html`, `HomeDark.dc.html`, `AddSheet.dc.html`)의 토큰과 컴포넌트를 기존 화면에 입힌다. 뒤 태스크가 쓸 칩·세그먼트·배너 스타일과 `Sheet`, `Icon`도 여기서 만든다.
함께 정리하는 1단계 이월 항목: 저장 오류가 시트 뒤에 가려짐 → 시트 안 오류 표시, App의 401 이중 처리와 인라인 style, `toFixed(1)` 수량 표시.

**Files:**
- Modify: `frontend/index.html`, `frontend/src/App.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/pages/Fridge.tsx`, `frontend/src/components/IngredientForm.tsx`
- Replace: `frontend/src/styles.css`
- Create: `frontend/src/format.ts`, `frontend/src/components/Icon.tsx`, `frontend/src/components/Sheet.tsx`

**Interfaces:**
- Consumes: `api`, `ApiError`, `onUnauthorized`, `localToday`, 타입 `Ingredient`, `IngredientInput`, `User`, `AuthOptions` (`src/api.ts`, 변경 없음)
- Produces:
  - `Sheet({ title, description?, action?, onClose, children })` — 네이티브 `<dialog>` 바텀시트, 배경 탭·Esc·뒤로가기로 닫힘
  - `Icon({ name: "plus" | "chevron" | "alert" | "sliders" | "more" | "check" | "settings", size?: number })`
  - `formatQuantity(q: number): string`, `formatDate(iso: string): string` (`src/format.ts`)
  - `IngredientForm`의 `onSubmit`/`onDelete`가 reject하면 시트 안에 오류 메시지를 보여준다 (호출 측은 에러를 삼키지 말고 던질 것)
  - CSS 클래스: `.page .topbar .summary .text-btn .list .row-btn .row-main .row-title .row-sub .badge(.urgent|.danger|.old) .empty .btn(.primary|.secondary|.danger-text|.inline|.kakao|.google) .cta-bar .sheet* .form .field .field-label .input .grid-2 .actions .hint .chips .chip .choices .choice .segmented .icon-btn .section-label .divider-top .banner* .chip-row .chip-row-end .plain-list .plain-row .error .center .muted`

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b design/ui-refresh
```

- [ ] **Step 1: 폰트와 테마 색**

`frontend/index.html`의 `<meta name="theme-color" ...>` 줄을 다음으로 교체하고, 그 아래에 폰트 링크를 추가:
```html
    <meta name="theme-color" content="#f3f4f6" media="(prefers-color-scheme: light)" />
    <meta name="theme-color" content="#0e0f11" media="(prefers-color-scheme: dark)" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap" />
```

- [ ] **Step 2: 스타일 전면 교체**

`frontend/src/styles.css` 전체를 다음으로 교체 (값은 시안 파일에서 가져온 것):
```css
:root {
  --bg: #f3f4f6;
  --surface: #ffffff;
  --field: #f3f4f6;
  --text: #17191c;
  --text-2: #5b616b;
  --text-3: #8b919a;
  --placeholder: #9097a1;
  --line: #eef0f2;
  --chip-text: #3a3f46;
  --handle: #e1e4e8;
  --accent: #0f9d63;
  --accent-strong: #0b7a4c;
  --accent-tint: #e7f6ef;
  --on-accent: #ffffff;
  --inverse-bg: #17191c;
  --inverse-text: #ffffff;
  --danger: #e5484d;
  --danger-tint: #fdeded;
  --warn: #b86e00;
  --warn-tint: #fff3dc;
  --neutral-tint: #eef0f2;
  --scrim: rgb(15 17 20 / 0.48);
  color-scheme: light dark;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e0f11;
    --surface: #1a1c20;
    --field: #24272c;
    --text: #f1f2f4;
    --text-2: #a6acb5;
    --text-3: #7c838c;
    --placeholder: #6e747d;
    --line: #2a2d32;
    --chip-text: #d3d7dc;
    --handle: #3a3d43;
    --accent: #2fc07f;
    --accent-strong: #5bd39c;
    --accent-tint: #173a2a;
    --on-accent: #07140d;
    --inverse-bg: #f1f2f4;
    --inverse-text: #0e0f11;
    --danger: #ff6b6f;
    --danger-tint: #3b1c1f;
    --warn: #f2b04a;
    --warn-tint: #3a2c12;
    --neutral-tint: #2a2d32;
    --scrim: rgb(0 0 0 / 0.6);
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 "IBM Plex Sans KR", "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif;
  -webkit-tap-highlight-color: transparent;
}

button,
input,
select {
  font: inherit;
  color: inherit;
}

button {
  cursor: pointer;
}

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.muted {
  color: var(--text-2);
}

.page {
  max-width: 520px;
  margin: 0 auto;
  padding-bottom: calc(112px + env(safe-area-inset-bottom));
}

.topbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  padding: 28px 20px 0;
}

.topbar h1 {
  margin: 0;
  font-size: 26px;
  line-height: 34px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.summary {
  margin: 4px 0 0;
  font-size: 15px;
  line-height: 22px;
  color: var(--text-2);
}

.text-btn {
  min-height: 44px;
  padding: 0 4px;
  border: 0;
  background: none;
  color: var(--text-3);
  font-size: 15px;
}

.center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 64px 20px;
  text-align: center;
}

.error {
  margin: 0;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--danger-tint);
  color: var(--danger);
  font-size: 15px;
  line-height: 22px;
}

.page > .error {
  margin: 16px 20px 0;
}

.list {
  margin: 16px 20px 0;
  padding: 6px 0;
  list-style: none;
  background: var(--surface);
  border-radius: 20px;
}

.row-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 72px;
  padding: 12px 20px;
  border: 0;
  background: none;
  text-align: left;
}

.row-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.row-title {
  font-size: 17px;
  line-height: 25px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.row-sub {
  font-size: 14px;
  line-height: 20px;
  color: var(--text-3);
}

.badge {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  background: var(--neutral-tint);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.badge.urgent,
.badge.danger {
  background: var(--danger-tint);
  color: var(--danger);
  font-weight: 700;
}

.badge.old {
  background: var(--warn-tint);
  color: var(--warn);
  font-weight: 700;
}

.empty {
  margin: 16px 20px 0;
  padding: 48px 20px;
  background: var(--surface);
  border-radius: 20px;
  text-align: center;
}

.empty p {
  margin: 4px 0;
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 56px;
  padding: 0 20px;
  border: 0;
  border-radius: 16px;
  font-size: 17px;
  font-weight: 600;
  text-decoration: none;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.btn.primary {
  background: var(--accent);
  color: var(--on-accent);
}

.btn.secondary {
  background: var(--neutral-tint);
  color: var(--chip-text);
}

.btn.danger-text {
  min-height: 48px;
  background: none;
  color: var(--danger);
  font-size: 16px;
}

.btn.inline {
  width: auto;
}

.btn.kakao {
  background: #fee500;
  color: #191600;
}

.btn.google {
  background: #ffffff;
  color: #1f1f1f;
  box-shadow: inset 0 0 0 1px #dadce0;
}

.cta-bar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  padding: 32px 20px calc(24px + env(safe-area-inset-bottom));
  background: linear-gradient(to bottom, transparent, var(--bg) 36%);
  pointer-events: none;
}

.cta-bar .btn {
  max-width: 480px;
  margin: 0 auto;
  pointer-events: auto;
}

.login {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 440px;
  min-height: 100dvh;
  margin: 0 auto;
  padding: 24px 20px calc(32px + env(safe-area-inset-bottom));
}

.login-hero {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.login-hero h1 {
  margin: 0;
  font-size: 32px;
  line-height: 42px;
  font-weight: 700;
  letter-spacing: -0.8px;
}

.login-hero p {
  margin: 0;
  font-size: 17px;
  line-height: 26px;
  color: var(--text-2);
}

.sheet {
  width: 100%;
  max-width: 520px;
  max-height: calc(100dvh - 40px);
  margin: auto auto 0;
  padding: 0;
  border: 0;
  border-radius: 24px 24px 0 0;
  background: var(--surface);
  color: var(--text);
}

.sheet::backdrop {
  background: var(--scrim);
}

.sheet-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 12px 20px calc(24px + env(safe-area-inset-bottom));
}

.sheet-handle {
  align-self: center;
  width: 40px;
  height: 4px;
  border-radius: 2px;
  background: var(--handle);
}

.sheet-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.sheet-header h2 {
  margin: 0;
  font-size: 22px;
  line-height: 30px;
  font-weight: 700;
  letter-spacing: -0.4px;
}

.sheet-desc {
  margin: 4px 0 0;
  font-size: 15px;
  line-height: 22px;
  color: var(--text-2);
  text-wrap: pretty;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.field-label {
  padding: 0;
  font-size: 14px;
  line-height: 20px;
  font-weight: 500;
  color: var(--text-2);
}

.field-label .optional {
  color: var(--placeholder);
  font-weight: 400;
}

.input {
  width: 100%;
  height: 56px;
  padding: 0 16px;
  border: 0;
  border-radius: 14px;
  background: var(--field);
  color: var(--text);
  font-size: 17px;
}

.input::placeholder {
  color: var(--placeholder);
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.actions {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 8px;
  margin-top: 4px;
}

.hint {
  margin: 0;
  font-size: 13px;
  line-height: 19px;
  color: var(--text-3);
  text-wrap: pretty;
}

.chips {
  display: flex;
  gap: 8px;
  padding: 0 20px;
  overflow-x: auto;
  scrollbar-width: none;
}

.chips::-webkit-scrollbar {
  display: none;
}

.chip {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  height: 44px;
  padding: 0 16px;
  border: 0;
  border-radius: 22px;
  background: var(--surface);
  color: var(--chip-text);
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
}

.chip[aria-pressed="true"] {
  background: var(--inverse-bg);
  color: var(--inverse-text);
  font-weight: 600;
}

.chip-row {
  position: relative;
  margin-top: 16px;
}

.chip-row .chips {
  padding-right: 92px;
}

.chip-row-end {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  align-items: center;
  height: 44px;
  padding: 0 20px 0 28px;
  background: linear-gradient(to right, transparent, var(--bg) 30%);
}

.chip-row-end .icon-btn {
  background: var(--surface);
  color: var(--chip-text);
}

.choices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.choice {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 44px;
  padding: 0 14px;
  border: 1.5px solid transparent;
  border-radius: 12px;
  background: var(--field);
  color: var(--chip-text);
  font-size: 15px;
  font-weight: 500;
}

.choice[aria-pressed="true"] {
  border-color: var(--accent);
  background: var(--accent-tint);
  color: var(--accent-strong);
  font-weight: 600;
}

.segmented {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  padding: 4px;
  border-radius: 14px;
  background: var(--field);
}

.segmented button {
  height: 40px;
  border: 0;
  border-radius: 10px;
  background: none;
  color: var(--text-2);
  font-size: 15px;
  font-weight: 500;
}

.segmented button[aria-pressed="true"] {
  background: var(--surface);
  color: var(--text);
  font-weight: 600;
  box-shadow: 0 1px 3px rgb(15 17 20 / 0.12);
}

.icon-btn {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 22px;
  background: none;
  color: var(--text-3);
}

.section-label {
  margin: 0;
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  color: var(--text-3);
}

.divider-top {
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.banner {
  display: flex;
  align-items: center;
  gap: 12px;
  width: calc(100% - 40px);
  min-height: 72px;
  margin: 20px 20px 0;
  padding: 16px;
  border: 0;
  border-radius: 18px;
  background: var(--surface);
  text-align: left;
}

.banner-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 20px;
  background: var(--danger-tint);
  color: var(--danger);
}

.banner-title {
  font-size: 16px;
  line-height: 23px;
  font-weight: 600;
}

.banner-sub {
  font-size: 14px;
  line-height: 20px;
  color: var(--text-2);
}

.plain-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.plain-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 48px;
}

@media (prefers-reduced-motion: reduce) {
  * {
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 3: 포맷 헬퍼·아이콘·시트**

`frontend/src/format.ts`:
```ts
/** 1 → "1", 0.25 → "0.25", 1.5 → "1.5" (소수 둘째 자리까지) */
export const formatQuantity = (q: number) => String(Number(q.toFixed(2)));

/** "2026-09-10" → "9월 10일" (올해가 아니면 "2025년 9월 10일") */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const md = `${m}월 ${d}일`;
  return y === new Date().getFullYear() ? md : `${y}년 ${md}`;
}
```

`frontend/src/components/Icon.tsx`:
```tsx
const PATHS = {
  plus: <path d="M12 5v14M5 12h14" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  alert: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5M12 16.5h.01" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7h9M19 7h1M4 17h2M11 17h9" />
      <circle cx="16" cy="7" r="2.5" />
      <circle cx="8.5" cy="17" r="2.5" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </>
  ),
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3 : 2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
```

`frontend/src/components/Sheet.tsx`:
```tsx
import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  action?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

/** 네이티브 <dialog> 바텀시트. Esc·안드로이드 뒤로가기·배경 탭으로 닫힌다. */
export default function Sheet({ title, description, action, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal(); // StrictMode 이중 실행 대비
  }, []);

  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // 배경(::backdrop) 탭
      }}
    >
      <div className="sheet-body">
        <div className="sheet-handle" aria-hidden="true" />
        <div className="sheet-header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p className="sheet-desc">{description}</p>}
          </div>
          {action}
        </div>
        {children}
      </div>
    </dialog>
  );
}
```

- [ ] **Step 4: 재료 입력 시트**

`frontend/src/components/IngredientForm.tsx` 전체 교체:
```tsx
import { useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput } from "../api";
import Sheet from "./Sheet";

interface Props {
  initial: Ingredient | null;
  onSubmit: (input: IngredientInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const UNITS = ["개", "g", "kg", "ml", "L", "팩", "봉", "병", "모", "단"];

export default function IngredientForm({ initial, onSubmit, onDelete, onClose }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? "개");
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(() =>
      onSubmit({
        name: name.trim(),
        quantity: Number(quantity),
        unit: unit.trim() || "개",
        purchased_on: purchasedOn,
        expires_on: expiresOn || null,
      }),
    );
  };

  return (
    <Sheet title={initial ? "재료 수정" : "재료 추가"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">이름</span>
          <input
            className="input"
            id="ingredient-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={50}
            placeholder="예: 대파"
          />
        </label>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">수량</span>
            <input
              className="input"
              id="ingredient-quantity"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">단위</span>
            <input
              className="input"
              id="ingredient-unit"
              list="units"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              maxLength={10}
            />
            <datalist id="units">
              {UNITS.map((u) => (
                <option key={u} value={u} />
              ))}
            </datalist>
          </label>
        </div>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">구입일</span>
            <input
              className="input"
              id="ingredient-purchased"
              type="date"
              value={purchasedOn}
              onChange={(e) => setPurchasedOn(e.target.value)}
              required
            />
          </label>
          <label className="field">
            <span className="field-label">
              유통기한 <span className="optional">(선택)</span>
            </span>
            <input
              className="input"
              id="ingredient-expires"
              type="date"
              value={expiresOn}
              onChange={(e) => setExpiresOn(e.target.value)}
            />
          </label>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="btn secondary" onClick={onClose}>
            취소
          </button>
          <button className="btn primary" disabled={busy}>
            {busy ? "저장 중…" : "저장"}
          </button>
        </div>
        {onDelete && (
          <button type="button" className="btn danger-text" disabled={busy} onClick={() => run(onDelete)}>
            이 재료 삭제
          </button>
        )}
      </form>
    </Sheet>
  );
}
```

- [ ] **Step 5: 냉장고 화면**

`frontend/src/pages/Fridge.tsx` 전체 교체:
```tsx
import { useEffect, useState } from "react";
import { api, type Ingredient, type IngredientInput } from "../api";
import IngredientForm from "../components/IngredientForm";
import Icon from "../components/Icon";
import { formatDate, formatQuantity } from "../format";

function badge(item: Ingredient): string | null {
  const d = item.days_left;
  if (item.status === "old") return `구입 ${item.days_since_purchase}일째`;
  if (d !== null) return d > 0 ? `D-${d}` : d === 0 ? "D-day" : `${-d}일 지남`;
  return null;
}

export default function Fridge({ onLogout }: { onLogout: () => void }) {
  const [items, setItems] = useState<Ingredient[] | null>(null);
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [error, setError] = useState("");

  // 401은 api()의 전역 핸들러(App.tsx)가 처리한다.
  const load = () => api<Ingredient[]>("/api/ingredients").then(setItems, (e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  // 저장·삭제 오류는 던져서 시트 안에 표시한다.
  const save = async (input: IngredientInput) => {
    if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
    else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
    setEditing(null);
    await load();
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${editing.name}을(를) 삭제할까요?`)) return;
    await api(`/api/ingredients/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const logout = async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    onLogout();
  };

  const soon = items?.filter((i) => i.status === "urgent").length ?? 0;

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>내 냉장고</h1>
          {items && items.length > 0 && (
            <p className="summary">
              재료 {items.length}개{soon > 0 && ` · 곧 먹어야 할 재료 ${soon}개`}
            </p>
          )}
        </div>
        <button className="text-btn" onClick={logout}>
          로그아웃
        </button>
      </header>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {items === null ? (
        !error && <p className="center muted">불러오는 중…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          <p>냉장고가 비어 있어요.</p>
          <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {items.map((item) => {
            const label = badge(item);
            return (
              <li key={item.id}>
                <button className="row-btn" onClick={() => setEditing(item)}>
                  <span className="row-main">
                    <span className="row-title">{item.name}</span>
                    <span className="row-sub">
                      {formatQuantity(item.quantity)}
                      {item.unit} · {formatDate(item.purchased_on)} 구입
                    </span>
                  </span>
                  {label && <span className={`badge ${item.status}`}>{label}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="cta-bar">
        <button className="btn primary" onClick={() => setEditing("new")}>
          <Icon name="plus" />
          재료 추가
        </button>
      </div>

      {editing && (
        <IngredientForm
          initial={editing === "new" ? null : editing}
          onSubmit={save}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 6: 로그인과 App**

`frontend/src/pages/Login.tsx`의 `return (...)` 블록 전체를 교체:
```tsx
  return (
    <main className="login">
      <div className="login-hero">
        <h1>냉장고 레시피</h1>
        <p>냉장고 속 재료로 오늘 뭐 해 먹을지 정해요.</p>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {options?.providers.includes("kakao") && (
        <a className="btn kakao" href="/auth/login/kakao">
          카카오 로그인
        </a>
      )}
      {options?.providers.includes("google") && (
        <a className="btn google" href="/auth/login/google">
          Google로 계속하기
        </a>
      )}
      {options?.dev_login && (
        <button className="btn secondary" onClick={devLogin}>
          개발용 로그인
        </button>
      )}
      {options && options.providers.length === 0 && !options.dev_login && (
        <p className="center muted">아직 로그인 방법이 설정되지 않았어요.</p>
      )}
    </main>
  );
```

`frontend/src/App.tsx`의 `checkMe`와 offline 분기를 교체:
```tsx
  const checkMe = () => {
    setOffline(false);
    setUser(undefined);
    api<User>("/api/me").then(setUser, (e: unknown) => {
      if (e instanceof ApiError && e.status === 0) setOffline(true);
      else if (!(e instanceof ApiError && e.status === 401)) setUser(null); // 401은 전역 핸들러가 처리
    });
  };
```
```tsx
  if (offline)
    return (
      <div className="center">
        <p>서버에 연결할 수 없어요.</p>
        <button className="btn primary inline" onClick={checkMe}>
          다시 시도
        </button>
      </div>
    );
```

- [ ] **Step 7: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: `tsc` 오류 없음, vite 빌드 성공.

- [ ] **Step 8: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "design: 토스풍 새 디자인 토큰·시트·목록 적용"
```

---

### Task 3: 보관 위치 백엔드 (모델·마이그레이션·API·재료 연동)

**Files:**
- Create: `backend/app/validation.py`, `backend/app/defaults.py`, `backend/app/locations.py`
- Create: `backend/migrations/versions/a1b1c1d1e1f1_storage_locations.py`
- Modify: `backend/app/models.py`, `backend/app/ingredients.py`, `backend/app/auth.py:72-79`, `backend/app/__init__.py:58-64`
- Create: `backend/tests/test_locations.py`, `backend/tests/test_migrations.py`
- Modify: `backend/tests/conftest.py:47-59`, `backend/tests/test_ingredients.py`

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`, `db`, `utcnow`, 픽스처 `client`, `login`, `app`
- Produces:
  - `app.validation.text(value, label: str, max_len: int) -> str` — label은 조사 포함(예: `"이름은"`), 위반 시 400 `"{label} 1~{max_len}자로 입력해 주세요."`
  - `app.validation.integer(value, label: str, lo: int, hi: int) -> int` — bool 거부, 위반 시 400 `"{label} {lo}~{hi} 사이 정수로 입력해 주세요."`
  - `app.models.StorageLocation(id, user_id, name, kind, sort_order, created_at)`, `Ingredient.location_id`, `Ingredient.location`
  - `app.defaults.seed_user_defaults(user_id: int) -> None` (commit 안 함)
  - `app.locations.user_locations(user_id) -> list[StorageLocation]`, `default_location(user_id) -> StorageLocation`, `owned_location(value) -> StorageLocation`
  - `app.ingredients.ingredient_status(purchased_on, expires_on, today, kind="fridge") -> "urgent"|"old"|"ok"`
  - API `GET/POST /api/locations`, `PATCH/DELETE /api/locations/<id>`. 위치 JSON `{id, name, kind, item_count}`
  - 재료 JSON에 `location_id`, `location_name`, `location_kind` 추가. `POST /api/ingredients`의 `location_id`는 선택(없으면 첫 fridge 위치)
  - Alembic revision `a1b1c1d1e1f1` (down `69204259dd5d`)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/storage-locations
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_locations.py`:
```python
import pytest


def test_new_user_gets_default_locations(client, login):
    login()
    body = client.get("/api/locations").get_json()
    assert [(l["name"], l["kind"], l["item_count"]) for l in body] == [
        ("냉장실", "fridge", 0),
        ("냉동실", "freezer", 0),
        ("실온", "room", 0),
    ]


def test_dev_login_seeds_defaults_once(client):
    client.post("/api/dev-login")
    assert len(client.get("/api/locations").get_json()) == 3
    client.post("/api/dev-login")
    assert len(client.get("/api/locations").get_json()) == 3


def test_create_rename_and_order(client, login):
    login()
    res = client.post("/api/locations", json={"name": " 김치냉장고 ", "kind": "fridge"})
    assert res.status_code == 201
    location = res.get_json()
    assert (location["name"], location["item_count"]) == ("김치냉장고", 0)
    assert client.get("/api/locations").get_json()[-1]["name"] == "김치냉장고"

    res = client.patch(f"/api/locations/{location['id']}", json={"name": "찬장", "kind": "room"})
    assert res.status_code == 200
    assert (res.get_json()["name"], res.get_json()["kind"]) == ("찬장", "room")


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "kind": "fridge"},
        {"name": "가" * 21, "kind": "fridge"},
        {"name": 3, "kind": "fridge"},
        {"name": "베란다", "kind": "garage"},
        {"name": "냉장실", "kind": "fridge"},
    ],
)
def test_create_validation(client, login, body):
    login()
    res = client.post("/api/locations", json=body)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_delete_rules_and_item_count(client, login):
    login()
    fridge, freezer, room = (l["id"] for l in client.get("/api/locations").get_json())
    client.post("/api/ingredients", json={"name": "우유", "purchased_on": "2026-09-10", "location_id": fridge})
    assert client.get("/api/locations").get_json()[0]["item_count"] == 1

    res = client.delete(f"/api/locations/{fridge}")
    assert res.status_code == 400
    assert res.get_json()["error"] == "이 위치에 있는 재료를 먼저 옮겨 주세요."

    assert client.delete(f"/api/locations/{freezer}").status_code == 204
    assert client.delete(f"/api/locations/{room}").status_code == 204

    item = client.get("/api/ingredients").get_json()[0]
    client.delete(f"/api/ingredients/{item['id']}")
    res = client.delete(f"/api/locations/{fridge}")
    assert res.status_code == 400
    assert res.get_json()["error"] == "위치는 하나 이상 있어야 해요."


def test_other_users_location_is_hidden(client, login):
    login("owner")
    location_id = client.get("/api/locations").get_json()[0]["id"]
    login("intruder")
    assert client.patch(f"/api/locations/{location_id}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/locations/{location_id}").status_code == 404
    res = client.post("/api/ingredients", json={"name": "우유", "purchased_on": "2026-09-10", "location_id": location_id})
    assert res.status_code == 400
    assert res.get_json()["error"] == "보관 위치를 다시 선택해 주세요."
```

`backend/tests/test_ingredients.py` 수정:

1) import 줄 `from app.models import Ingredient, User, db`를 `from app.models import Ingredient, StorageLocation, User, db`로 교체.

2) `test_ingredient_status` 아래에 추가:
```python
@pytest.mark.parametrize(
    "kind, days, expected",
    [
        ("fridge", 6, "ok"),
        ("fridge", 7, "old"),
        ("freezer", 59, "ok"),
        ("freezer", 60, "old"),
        ("room", 400, "ok"),
    ],
)
def test_old_threshold_depends_on_location_kind(kind, days, expected):
    assert ingredient_status(TODAY - timedelta(days=days), None, TODAY, kind) == expected


def test_location_defaults_and_fields(client, login):
    login()
    freezer = client.get("/api/locations").get_json()[1]
    res = create(client, name="만두", purchased_on=(seoul_today() - timedelta(days=30)).isoformat(), location_id=freezer["id"])
    body = res.get_json()
    assert (body["location_name"], body["location_kind"], body["status"]) == ("냉동실", "freezer", "ok")

    body = create(client, name="우유").get_json()
    assert (body["location_name"], body["location_kind"]) == ("냉장실", "fridge")

    moved = client.patch(f"/api/ingredients/{body['id']}", json={"location_id": freezer["id"]}).get_json()
    assert moved["location_id"] == freezer["id"]
```

3) `test_create_validation`의 parametrize 목록 끝에 세 항목 추가:
```python
        {"name": 123},
        {"quantity": True},
        {"location_id": "1"},
```

4) `test_deleting_user_cascades_ingredients` 전체 교체:
```python
def test_deleting_user_cascades_ingredients(app):
    with app.app_context():
        user = User(provider="test", provider_id="cascade", nickname="x")
        db.session.add(user)
        db.session.commit()
        location = StorageLocation(user_id=user.id, name="냉장실", kind="fridge")
        db.session.add(location)
        db.session.commit()
        db.session.add(Ingredient(user_id=user.id, location_id=location.id, name="계란", purchased_on=date(2026, 1, 1)))
        db.session.commit()

        db.session.delete(user)
        db.session.commit()

        assert Ingredient.query.filter_by(user_id=user.id).count() == 0
        assert StorageLocation.query.filter_by(user_id=user.id).count() == 0
```

`backend/tests/test_migrations.py`:
```python
from pathlib import Path

import sqlalchemy as sa
from flask_migrate import downgrade, upgrade

from app import create_app
from app.models import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


def migration_app(tmp_path, monkeypatch):
    # Alembic env.py의 fileConfig가 기존 로거(app 등)를 꺼 버려 다른 테스트의 caplog를 망가뜨리지 않도록 막는다
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    return create_app(
        {"TESTING": True, "SECRET_KEY": "t", "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'migrate.sqlite3'}"}
    )


def test_location_migration_moves_existing_ingredients_to_fridge(tmp_path, monkeypatch):
    app = migration_app(tmp_path, monkeypatch)
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="69204259dd5d")
        with db.engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, provider, provider_id, nickname, created_at) "
                    "VALUES (1, 'test', '1', 'u', '2026-09-01 00:00:00')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO ingredients (user_id, name, quantity, unit, purchased_on, created_at) "
                    "VALUES (1, '우유', 1, '개', '2026-09-10', '2026-09-10 00:00:00')"
                )
            )

        upgrade(directory=MIGRATIONS, revision="a1b1c1d1e1f1")

        with db.engine.connect() as conn:
            locations = conn.execute(
                sa.text("SELECT name, kind FROM storage_locations WHERE user_id = 1 ORDER BY sort_order")
            ).all()
            moved_to = conn.execute(
                sa.text("SELECT l.name FROM ingredients i JOIN storage_locations l ON l.id = i.location_id")
            ).scalar_one()
        assert [tuple(r) for r in locations] == [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]
        assert moved_to == "냉장실"

        downgrade(directory=MIGRATIONS, revision="69204259dd5d")
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: `test_locations.py`, `test_migrations.py`, 새 `test_ingredients.py` 테스트들이 실패(404, ImportError `StorageLocation`, 마이그레이션 revision 없음 등)

- [ ] **Step 3: 검증 헬퍼·모델·기본값**

`backend/app/validation.py`:
```python
from flask import abort


def text(value, label, max_len):
    """앞뒤 공백을 뺀 1~max_len자 문자열. label은 조사를 포함한다(예: "이름은")."""
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_len:
        abort(400, f"{label} 1~{max_len}자로 입력해 주세요.")
    return value.strip()


def integer(value, label, lo, hi):
    """bool이 아닌 lo~hi 정수."""
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        abort(400, f"{label} {lo}~{hi} 사이 정수로 입력해 주세요.")
    return value
```

`backend/app/models.py`에서 `class Ingredient` 바로 위에 추가:
```python
class StorageLocation(db.Model):
    __tablename__ = "storage_locations"
    __table_args__ = (db.UniqueConstraint("user_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # fridge | freezer | room
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


```
`class Ingredient`의 `user_id` 줄 바로 아래에 추가:
```python
    location_id = db.Column(db.Integer, db.ForeignKey("storage_locations.id"), nullable=False, index=True)
    location = db.relationship("StorageLocation")
```

`backend/app/defaults.py`:
```python
from .models import StorageLocation, db

DEFAULT_LOCATIONS = [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]


def seed_user_defaults(user_id):
    """새 사용자에게 기본 보관 위치를 만든다. commit은 호출 측에서."""
    for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
        db.session.add(StorageLocation(user_id=user_id, name=name, kind=kind, sort_order=order))
```

`backend/app/auth.py`:
- import에 추가: `from .defaults import seed_user_defaults`
- `upsert_user`의 `if user is None:` 블록을 교체:
```python
    if user is None:
        user = User(provider=provider, provider_id=provider_id)
        db.session.add(user)
        db.session.flush()
        seed_user_defaults(user.id)
```

`backend/tests/conftest.py`:
- import에 추가: `from app.defaults import seed_user_defaults`
- `login` 픽스처 안 `db.session.commit()` 다음 줄에 추가:
```python
            seed_user_defaults(user.id)
            db.session.commit()
```

- [ ] **Step 4: 위치 API**

`backend/app/locations.py`:
```python
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func

from .auth import get_owned_or_404, login_required
from .models import Ingredient, StorageLocation, db
from .validation import text

bp = Blueprint("locations", __name__, url_prefix="/api/locations")

KINDS = ("fridge", "freezer", "room")
INVALID_LOCATION = "보관 위치를 다시 선택해 주세요."


def user_locations(user_id):
    return (
        StorageLocation.query.filter_by(user_id=user_id)
        .order_by(StorageLocation.sort_order, StorageLocation.id)
        .all()
    )


def default_location(user_id):
    locations = user_locations(user_id)
    if not locations:
        abort(400, "보관 위치를 먼저 만들어 주세요.")
    return next((l for l in locations if l.kind == "fridge"), locations[0])


def owned_location(value):
    if isinstance(value, bool) or not isinstance(value, int):
        abort(400, INVALID_LOCATION)
    location = db.session.get(StorageLocation, value)
    if location is None or location.user_id != g.user.id:
        abort(400, INVALID_LOCATION)
    return location


def item_counts(user_id):
    rows = (
        db.session.query(Ingredient.location_id, func.count(Ingredient.id))
        .filter(Ingredient.user_id == user_id)
        .group_by(Ingredient.location_id)
        .all()
    )
    return dict(rows)


def to_json(location, count):
    return {"id": location.id, "name": location.name, "kind": location.kind, "item_count": count}


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    return data


def _kind(value):
    if value not in KINDS:
        abort(400, "보관 종류를 냉장·냉동·실온 중에서 골라 주세요.")
    return value


def _unique_name(value, exclude_id=None):
    name = text(value, "위치 이름은", 20)
    query = StorageLocation.query.filter_by(user_id=g.user.id, name=name)
    if exclude_id is not None:
        query = query.filter(StorageLocation.id != exclude_id)
    if query.first():
        abort(400, "이미 있는 위치 이름이에요.")
    return name


@bp.get("")
@login_required
def list_locations():
    counts = item_counts(g.user.id)
    return jsonify([to_json(l, counts.get(l.id, 0)) for l in user_locations(g.user.id)])


@bp.post("")
@login_required
def create_location():
    data = _json_body()
    name = _unique_name(data.get("name"))
    kind = _kind(data.get("kind"))
    last = db.session.query(func.max(StorageLocation.sort_order)).filter(StorageLocation.user_id == g.user.id).scalar()
    location = StorageLocation(
        user_id=g.user.id, name=name, kind=kind, sort_order=0 if last is None else last + 1
    )
    db.session.add(location)
    db.session.commit()
    return jsonify(to_json(location, 0)), 201


@bp.patch("/<int:location_id>")
@login_required
def update_location(location_id):
    location = get_owned_or_404(StorageLocation, location_id)
    data = _json_body()
    if "name" in data:
        location.name = _unique_name(data["name"], exclude_id=location.id)
    if "kind" in data:
        location.kind = _kind(data["kind"])
    db.session.commit()
    return jsonify(to_json(location, item_counts(g.user.id).get(location.id, 0)))


@bp.delete("/<int:location_id>")
@login_required
def delete_location(location_id):
    location = get_owned_or_404(StorageLocation, location_id)
    if Ingredient.query.filter_by(location_id=location.id).first():
        abort(400, "이 위치에 있는 재료를 먼저 옮겨 주세요.")
    if StorageLocation.query.filter_by(user_id=g.user.id).count() <= 1:
        abort(400, "위치는 하나 이상 있어야 해요.")
    db.session.delete(location)
    db.session.commit()
    return "", 204
```

`backend/app/__init__.py` 블루프린트 import·등록에 추가:
```python
    from .locations import bp as locations_bp
```
```python
    app.register_blueprint(locations_bp)
```

- [ ] **Step 5: 재료에 위치 연결**

`backend/app/ingredients.py`:

- import 교체/추가:
```python
from sqlalchemy.orm import joinedload

from .auth import get_owned_or_404, login_required
from .locations import default_location, owned_location
from .models import Ingredient, db
from .validation import text
```
- `OLD_DAYS = 7 ...` 줄과 `STATUS_RANK` 줄을 교체:
```python
OLD_DAYS_BY_KIND = {"fridge": 7, "freezer": 60, "room": None}  # 유통기한이 없을 때 오래됨 기준(일), room은 표시 안 함
STATUS_RANK = {"urgent": 0, "old": 1, "ok": 2}
```
- `ingredient_status` 교체:
```python
def ingredient_status(purchased_on, expires_on, today, kind="fridge"):
    if expires_on is not None:
        return "urgent" if (expires_on - today).days <= URGENT_DAYS else "ok"
    old_days = OLD_DAYS_BY_KIND[kind]
    return "old" if old_days is not None and (today - purchased_on).days >= old_days else "ok"
```
- `to_json`의 `"status"` 줄 교체, 위치 필드 추가:
```python
        "status": ingredient_status(item.purchased_on, item.expires_on, today, item.location.kind),
        "location_id": item.location_id,
        "location_name": item.location.name,
        "location_kind": item.location.kind,
```
- `parse_fields`:
  - name 처리 블록을 교체:
```python
    if creating or "name" in data:
        fields["name"] = text(data.get("name"), "이름은", 50)
```
  - quantity 블록의 `try:` 바로 위에 추가:
```python
        if isinstance(data.get("quantity"), bool):
            abort(400, "수량은 숫자로 입력해 주세요.")
```
  - `return fields` 바로 위에 추가:
```python
    if creating or "location_id" in data:
        value = data.get("location_id")
        location = default_location(g.user.id) if creating and value is None else owned_location(value)
        fields["location_id"] = location.id
```
- `list_ingredients`의 조회와 정렬 키를 교체:
```python
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=g.user.id).all()
    items.sort(
        key=lambda i: (
            STATUS_RANK[ingredient_status(i.purchased_on, i.expires_on, today, i.location.kind)],
            i.expires_on or date.max,
            i.purchased_on,
            i.id,
        )
    )
```

- [ ] **Step 6: 마이그레이션**

`backend/migrations/versions/a1b1c1d1e1f1_storage_locations.py`:
```python
"""storage locations

Revision ID: a1b1c1d1e1f1
Revises: 69204259dd5d
Create Date: 2026-09-13

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "a1b1c1d1e1f1"
down_revision = "69204259dd5d"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본값을 고정한다(앱 코드가 바뀌어도 이 마이그레이션의 결과는 같아야 함)
DEFAULT_LOCATIONS = [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]


def upgrade():
    op.create_table(
        "storage_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_storage_locations_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_locations")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_storage_locations_user_id")),
    )
    with op.batch_alter_table("storage_locations") as batch_op:
        batch_op.create_index(batch_op.f("ix_storage_locations_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.add_column(sa.Column("location_id", sa.Integer(), nullable=True))

    # 기존 사용자에게 기본 위치를 만들고, 기존 재료는 모두 냉장실로 옮긴다
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all():
        for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
            conn.execute(
                sa.text(
                    "INSERT INTO storage_locations (user_id, name, kind, sort_order, created_at) "
                    "VALUES (:user_id, :name, :kind, :sort_order, :created_at)"
                ),
                {"user_id": user_id, "name": name, "kind": kind, "sort_order": order, "created_at": now},
            )
        fridge_id = conn.execute(
            sa.text(
                "SELECT id FROM storage_locations WHERE user_id = :user_id AND kind = 'fridge' "
                "ORDER BY sort_order LIMIT 1"
            ),
            {"user_id": user_id},
        ).scalar()
        conn.execute(
            sa.text("UPDATE ingredients SET location_id = :location_id WHERE user_id = :user_id"),
            {"location_id": fridge_id, "user_id": user_id},
        )

    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.alter_column("location_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f("ix_ingredients_location_id"), ["location_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_ingredients_location_id_storage_locations"), "storage_locations", ["location_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_ingredients_location_id_storage_locations"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_ingredients_location_id"))
        batch_op.drop_column("location_id")
    with op.batch_alter_table("storage_locations") as batch_op:
        batch_op.drop_index(batch_op.f("ix_storage_locations_user_id"))
    op.drop_table("storage_locations")
```

- [ ] **Step 7: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: 실패 0, 경고 0

- [ ] **Step 8: 개발 DB에 적용하고 모델-마이그레이션 일치 확인**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && cp instance/dev.sqlite3 instance/dev.sqlite3.before-locations && .venv/bin/flask --app app db upgrade && .venv/bin/flask --app app db check
```
Expected: 업그레이드 성공, `No new upgrade operations detected.` (차이가 보고되면 모델과 마이그레이션의 컬럼·제약 이름을 맞춘다). 개발 DB 백업 파일은 지우지 않는다.

- [ ] **Step 9: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "feat: 사용자 정의 보관 위치와 위치 종류별 오래됨 기준"
```

---

### Task 4: 보관 위치 화면 (탭·위치 선택·위치 관리·설정)

시안: `Main.dc.html`(위치 칩 + 조절 아이콘), `AddSheet.dc.html`(보관 위치 선택), `LocationsSheet.dc.html`(위치 관리).
시안 대비 추가: 헤더 오른쪽 `로그아웃` 글자 대신 설정 아이콘(설정 시트에 보관 위치·로그아웃, 이후 태스크에서 필수품·품목별 경고 추가).

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/format.ts`, `frontend/src/styles.css`, `frontend/src/components/IngredientForm.tsx`, `frontend/src/pages/Fridge.tsx`
- Create: `frontend/src/components/LocationsSheet.tsx`, `frontend/src/components/SettingsSheet.tsx`

**Interfaces:**
- Consumes: Task 3 API (`/api/locations`, 재료 JSON의 `location_id/location_name/location_kind`), Task 2 `Sheet`, `Icon`, CSS 클래스
- Produces:
  - 타입 `LocationKind`, `StorageLocation {id, name, kind, item_count}`; `IngredientInput.location_id: number`; `Ingredient.location_name`, `Ingredient.location_kind`
  - `KIND_LABEL: Record<LocationKind, string>` (`format.ts`)
  - `LocationsSheet({ locations, onChanged, onClose })`
  - `SettingsSheet({ onOpen, onLogout, onClose })`, `type SettingsTarget = "locations"` — 태스크 6·8이 `"staples"`, `"rules"`를 추가
  - `IngredientForm`에 props `locations: StorageLocation[]`, `defaultLocationId: number` 추가

(브랜치: Task 3과 같은 `feature/storage-locations`에서 계속)

- [ ] **Step 1: 타입과 라벨**

`frontend/src/api.ts`:
- `export type Status = ...` 줄 아래에 추가:
```ts
export type LocationKind = "fridge" | "freezer" | "room";

export interface StorageLocation {
  id: number;
  name: string;
  kind: LocationKind;
  item_count: number;
}
```
- `IngredientInput`에 `location_id: number;` 추가
- `Ingredient`에 `location_name: string;`, `location_kind: LocationKind;` 추가

`frontend/src/format.ts` 끝에 추가:
```ts
import type { LocationKind } from "./api";

export const KIND_LABEL: Record<LocationKind, string> = { fridge: "냉장", freezer: "냉동", room: "실온" };
```
(import 문은 파일 맨 위로 옮긴다)

`frontend/src/styles.css` 끝에 추가:
```css
.location-row {
  min-height: 64px;
}

.edit-block {
  gap: 12px;
  padding: 12px 0;
}

.form.compact {
  gap: 12px;
}

.menu-row {
  width: 100%;
  min-height: 56px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--text);
  text-align: left;
}

.menu-row svg {
  color: var(--text-3);
}

.menu-row.logout {
  color: var(--text-3);
  font-size: 16px;
}
```

- [ ] **Step 2: 설정 시트와 위치 관리 시트**

`frontend/src/components/SettingsSheet.tsx`:
```tsx
import Icon from "./Icon";
import Sheet from "./Sheet";

export type SettingsTarget = "locations";

const MENU: { target: SettingsTarget; label: string }[] = [{ target: "locations", label: "보관 위치" }];

interface Props {
  onOpen: (target: SettingsTarget) => void;
  onLogout: () => void;
  onClose: () => void;
}

export default function SettingsSheet({ onOpen, onLogout, onClose }: Props) {
  return (
    <Sheet title="설정" onClose={onClose}>
      <ul className="plain-list">
        {MENU.map((item) => (
          <li key={item.target}>
            <button className="plain-row menu-row" onClick={() => onOpen(item.target)}>
              <span className="row-title">{item.label}</span>
              <Icon name="chevron" />
            </button>
          </li>
        ))}
        <li>
          <button className="plain-row menu-row logout" onClick={onLogout}>
            로그아웃
          </button>
        </li>
      </ul>
    </Sheet>
  );
}
```

`frontend/src/components/LocationsSheet.tsx`:
```tsx
import { useState, type FormEvent } from "react";
import { api, type LocationKind, type StorageLocation } from "../api";
import { KIND_LABEL } from "../format";
import Icon from "./Icon";
import Sheet from "./Sheet";

const KINDS: LocationKind[] = ["fridge", "freezer", "room"];

function KindPicker({ value, onChange }: { value: LocationKind; onChange: (kind: LocationKind) => void }) {
  return (
    <div className="segmented" role="group" aria-label="보관 종류">
      {KINDS.map((kind) => (
        <button key={kind} type="button" aria-pressed={value === kind} onClick={() => onChange(kind)}>
          {KIND_LABEL[kind]}
        </button>
      ))}
    </div>
  );
}

interface Props {
  locations: StorageLocation[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function LocationsSheet({ locations, onChanged, onClose }: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editKind, setEditKind] = useState<LocationKind>("fridge");
  const [newName, setNewName] = useState("");
  const [newKind, setNewKind] = useState<LocationKind>("fridge");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (location: StorageLocation) => {
    setEditingId(location.id);
    setEditName(location.name);
    setEditKind(location.kind);
    setError("");
  };

  const saveEdit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { name: editName, kind: editKind };
    if (await run(() => api(`/api/locations/${editingId}`, { method: "PATCH", body }))) setEditingId(null);
  };

  const remove = async (location: StorageLocation) => {
    if (!confirm(`${location.name}을(를) 삭제할까요?`)) return;
    if (await run(() => api(`/api/locations/${location.id}`, { method: "DELETE" }))) setEditingId(null);
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const body = { name: newName, kind: newKind };
    if (await run(() => api("/api/locations", { method: "POST", body }))) setNewName("");
  };

  return (
    <Sheet title="위치 관리" onClose={onClose}>
      <ul className="plain-list">
        {locations.map((location) => (
          <li key={location.id}>
            {editingId === location.id ? (
              <form className="form edit-block" onSubmit={saveEdit}>
                <input
                  className="input"
                  id={`location-name-${location.id}`}
                  aria-label="위치 이름"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  maxLength={20}
                  required
                />
                <KindPicker value={editKind} onChange={setEditKind} />
                <div className="actions">
                  <button type="button" className="btn secondary" onClick={() => setEditingId(null)}>
                    취소
                  </button>
                  <button className="btn primary" disabled={busy}>
                    저장
                  </button>
                </div>
                <button type="button" className="btn danger-text" disabled={busy} onClick={() => remove(location)}>
                  이 위치 삭제
                </button>
              </form>
            ) : (
              <div className="plain-row location-row">
                <div className="row-main">
                  <span className="row-title">{location.name}</span>
                  <span className="row-sub">
                    {KIND_LABEL[location.kind]} · {location.item_count > 0 ? `재료 ${location.item_count}개` : "비어 있음"}
                  </span>
                </div>
                <button className="icon-btn" aria-label={`${location.name} 수정`} onClick={() => startEdit(location)}>
                  <Icon name="more" />
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="hint">재료가 들어 있는 위치는 비운 뒤에 삭제할 수 있어요.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <form className="form compact divider-top" onSubmit={add}>
        <label className="field">
          <span className="field-label">새 위치</span>
          <input
            className="input"
            id="new-location-name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={20}
            placeholder="예: 베란다"
            required
          />
        </label>
        <KindPicker value={newKind} onChange={setNewKind} />
        <p className="hint">냉장은 구입 7일, 냉동은 60일이 지나면 ‘오래됨’으로 표시해요. 실온은 표시하지 않아요.</p>
        <button className="btn primary" disabled={busy}>
          위치 추가
        </button>
      </form>
    </Sheet>
  );
}
```

- [ ] **Step 3: 재료 시트에 보관 위치 선택**

`frontend/src/components/IngredientForm.tsx`:
- import 교체:
```tsx
import { useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import Icon from "./Icon";
import Sheet from "./Sheet";
```
- `Props`에 추가:
```tsx
  locations: StorageLocation[];
  defaultLocationId: number;
```
- 함수 시그니처를 `({ initial, locations, defaultLocationId, onSubmit, onDelete, onClose }: Props)`로, `expiresOn` state 아래에 추가:
```tsx
  const [locationId, setLocationId] = useState(initial?.location_id ?? defaultLocationId);
```
- `onSubmit({...})` 객체에 `location_id: locationId,` 추가
- 수량/단위 `grid-2` 블록과 구입일/유통기한 `grid-2` 블록 사이에 추가:
```tsx
        <div className="field" role="group" aria-label="보관 위치">
          <span className="field-label">보관 위치</span>
          <div className="choices">
            {locations.map((location) => (
              <button
                key={location.id}
                type="button"
                className="choice"
                aria-pressed={locationId === location.id}
                onClick={() => setLocationId(location.id)}
              >
                {locationId === location.id && <Icon name="check" size={16} />}
                {location.name}
              </button>
            ))}
          </div>
        </div>
```

- [ ] **Step 4: 냉장고 화면**

`frontend/src/pages/Fridge.tsx` 전체 교체:
```tsx
import { useEffect, useState } from "react";
import { api, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import Icon from "../components/Icon";
import IngredientForm from "../components/IngredientForm";
import LocationsSheet from "../components/LocationsSheet";
import SettingsSheet, { type SettingsTarget } from "../components/SettingsSheet";
import { formatDate, formatQuantity } from "../format";

function badge(item: Ingredient): string | null {
  const d = item.days_left;
  if (item.status === "old") return `구입 ${item.days_since_purchase}일째`;
  if (d !== null) return d > 0 ? `D-${d}` : d === 0 ? "D-day" : `${-d}일 지남`;
  return null;
}

export default function Fridge({ onLogout }: { onLogout: () => void }) {
  const [items, setItems] = useState<Ingredient[] | null>(null);
  const [locations, setLocations] = useState<StorageLocation[]>([]);
  const [filter, setFilter] = useState<number | "all">("all");
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [panel, setPanel] = useState<"settings" | SettingsTarget | null>(null);
  const [error, setError] = useState("");

  // 401은 api()의 전역 핸들러(App.tsx)가 처리한다.
  const load = () =>
    Promise.all([
      api<Ingredient[]>("/api/ingredients").then(setItems),
      api<StorageLocation[]>("/api/locations").then(setLocations),
    ]).catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  // 저장·삭제 오류는 던져서 시트 안에 표시한다.
  const save = async (input: IngredientInput) => {
    if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
    else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
    setEditing(null);
    await load();
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${editing.name}을(를) 삭제할까요?`)) return;
    await api(`/api/ingredients/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const logout = async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    onLogout();
  };

  const activeFilter = filter !== "all" && locations.some((l) => l.id === filter) ? filter : "all";
  const visible = items?.filter((i) => activeFilter === "all" || i.location_id === activeFilter) ?? null;
  const defaultLocationId =
    activeFilter !== "all" ? activeFilter : (locations.find((l) => l.kind === "fridge") ?? locations[0])?.id;
  const soon = items?.filter((i) => i.status === "urgent").length ?? 0;

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>내 냉장고</h1>
          {items && items.length > 0 && (
            <p className="summary">
              재료 {items.length}개{soon > 0 && ` · 곧 먹어야 할 재료 ${soon}개`}
            </p>
          )}
        </div>
        <button className="icon-btn" aria-label="설정" onClick={() => setPanel("settings")}>
          <Icon name="settings" size={22} />
        </button>
      </header>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {locations.length > 0 && (
        <div className="chip-row">
          <div className="chips" role="group" aria-label="보관 위치">
            <button className="chip" aria-pressed={activeFilter === "all"} onClick={() => setFilter("all")}>
              전체
            </button>
            {locations.map((location) => (
              <button
                key={location.id}
                className="chip"
                aria-pressed={activeFilter === location.id}
                onClick={() => setFilter(location.id)}
              >
                {location.name}
              </button>
            ))}
          </div>
          <div className="chip-row-end">
            <button className="icon-btn" aria-label="위치 관리" onClick={() => setPanel("locations")}>
              <Icon name="sliders" />
            </button>
          </div>
        </div>
      )}

      {visible === null ? (
        !error && <p className="center muted">불러오는 중…</p>
      ) : visible.length === 0 ? (
        <div className="empty">
          <p>{items && items.length > 0 ? "이 위치에는 재료가 없어요." : "냉장고가 비어 있어요."}</p>
          <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {visible.map((item) => {
            const label = badge(item);
            return (
              <li key={item.id}>
                <button className="row-btn" onClick={() => setEditing(item)}>
                  <span className="row-main">
                    <span className="row-title">{item.name}</span>
                    <span className="row-sub">
                      {formatQuantity(item.quantity)}
                      {item.unit} · {item.location_name} · {formatDate(item.purchased_on)} 구입
                    </span>
                  </span>
                  {label && <span className={`badge ${item.status}`}>{label}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="cta-bar">
        <button className="btn primary" disabled={defaultLocationId === undefined} onClick={() => setEditing("new")}>
          <Icon name="plus" />
          재료 추가
        </button>
      </div>

      {editing && defaultLocationId !== undefined && (
        <IngredientForm
          initial={editing === "new" ? null : editing}
          locations={locations}
          defaultLocationId={defaultLocationId}
          onSubmit={save}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}

      {panel === "settings" && <SettingsSheet onOpen={setPanel} onLogout={logout} onClose={() => setPanel(null)} />}
      {panel === "locations" && (
        <LocationsSheet locations={locations} onChanged={load} onClose={() => setPanel(null)} />
      )}
    </div>
  );
}
```

- [ ] **Step 5: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류 없음

- [ ] **Step 6: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 보관 위치 탭·선택·위치 관리 화면"
```

---

### Task 5: 필수품 백엔드 (이름 매칭·모델·마이그레이션·API)

**Files:**
- Create: `backend/app/matching.py`, `backend/app/staples.py`, `backend/migrations/versions/a2b2c2d2e2f2_staples.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`
- Create: `backend/tests/test_matching.py`, `backend/tests/test_staples.py`
- Modify: `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: Task 3 `text()`, `login_required`, `get_owned_or_404`, `Ingredient`, 픽스처
- Produces:
  - `app.matching.normalize(name) -> str`, `names_match(a, b) -> bool`(양방향 포함), `keyword_in(keyword, name) -> bool`(한 방향)
  - `app.models.Staple(id, user_id, name, category, created_at)`
  - API `GET/POST /api/staples`, `DELETE /api/staples/<id>`. JSON `{id, name, category, in_stock}`. 목록 정렬: 떨어진 것 먼저 → 분류(조미료, 야채, 기타, 그 외) → 이름
  - Alembic revision `a2b2c2d2e2f2` (down `a1b1c1d1e1f1`)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/staples
```
(`feature/storage-locations`가 main에 병합된 뒤 시작한다.)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_matching.py`:
```python
import pytest

from app.matching import keyword_in, names_match, normalize


def test_normalize_drops_parentheses_spaces_and_case():
    assert normalize(" 진 간장 (500ml) ") == "진간장"
    assert normalize("Egg 10구") == "egg10구"


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("대파", "대파", True),
        ("간장", "진간장 (500ml)", True),
        ("진간장", "간장", True),
        ("Egg", "egg 10구", True),
        ("대파", "양파", False),
        ("", "양파", False),
        ("(국산)", "양파", False),
    ],
)
def test_names_match(a, b, expected):
    assert names_match(a, b) is expected


def test_keyword_in_is_one_way():
    assert keyword_in("계란", "유정란 계란 10구")
    assert not keyword_in("유정란 계란", "계란")
    assert not keyword_in("", "계란")
```

`backend/tests/test_staples.py`:
```python
import pytest


def test_in_stock_and_order(client, login):
    login()
    for body in [
        {"name": "간장", "category": "조미료"},
        {"name": "참기름", "category": "조미료"},
        {"name": "대파", "category": "야채"},
        {"name": "계란"},
    ]:
        assert client.post("/api/staples", json=body).status_code == 201
    client.post("/api/ingredients", json={"name": "진간장 (500ml)", "purchased_on": "2026-09-10"})
    client.post("/api/ingredients", json={"name": "계란", "purchased_on": "2026-09-10"})

    body = client.get("/api/staples").get_json()
    assert [(s["name"], s["category"], s["in_stock"]) for s in body] == [
        ("참기름", "조미료", False),
        ("대파", "야채", False),
        ("간장", "조미료", True),
        ("계란", "기타", True),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "가" * 51},
        {"name": 1},
        {"name": "소금", "category": "가" * 11},
        {"name": "소금", "category": 3},
    ],
)
def test_create_validation(client, login, body):
    login()
    res = client.post("/api/staples", json=body)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_duplicate_name_rejected(client, login):
    login()
    client.post("/api/staples", json={"name": "소금"})
    res = client.post("/api/staples", json={"name": " 소금 "})
    assert res.status_code == 400
    assert res.get_json()["error"] == "이미 등록된 필수품이에요."


def test_delete_and_ownership(client, login):
    login("owner")
    staple = client.post("/api/staples", json={"name": "소금"}).get_json()
    login("intruder")
    assert client.delete(f"/api/staples/{staple['id']}").status_code == 404
    assert client.get("/api/staples").get_json() == []
    login("owner2")
    mine = client.post("/api/staples", json={"name": "후추"}).get_json()
    assert client.delete(f"/api/staples/{mine['id']}").status_code == 204
    assert client.get("/api/staples").get_json() == []
```

`backend/tests/test_migrations.py` 끝에 추가:
```python
def test_upgrade_to_head_and_back_to_base(tmp_path, monkeypatch):
    app = migration_app(tmp_path, monkeypatch)
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert {"users", "ingredients", "storage_locations", "staples"} <= tables
        downgrade(directory=MIGRATIONS, revision="base")
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q tests/test_matching.py tests/test_staples.py tests/test_migrations.py`
Expected: ImportError(`app.matching`), 404, `staples` 테이블 없음으로 실패

- [ ] **Step 3: 구현**

`backend/app/matching.py`:
```python
import re

# ponytail: 부분 문자열 매칭 — "파"가 "파프리카"에 걸리는 오류 가능. 문제되면 동의어 사전이나 AI 매칭으로 교체 (스펙 4절)


def normalize(name):
    """괄호와 그 안 내용 제거 → 공백 제거 → 소문자."""
    return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", name)).lower()


def names_match(a, b):
    a, b = normalize(a), normalize(b)
    return bool(a) and bool(b) and (a in b or b in a)


def keyword_in(keyword, name):
    keyword = normalize(keyword)
    return bool(keyword) and keyword in normalize(name)
```

`backend/app/models.py` 끝에 추가:
```python


class Staple(db.Model):
    __tablename__ = "staples"
    __table_args__ = (db.UniqueConstraint("user_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(10), nullable=False, default="기타")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
```

`backend/app/staples.py`:
```python
from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .matching import names_match
from .models import Ingredient, Staple, db
from .validation import text

bp = Blueprint("staples", __name__, url_prefix="/api/staples")

CATEGORY_ORDER = {"조미료": 0, "야채": 1, "기타": 2}


def ingredient_names(user_id):
    return [name for (name,) in db.session.query(Ingredient.name).filter(Ingredient.user_id == user_id).all()]


def to_json(staple, names):
    return {
        "id": staple.id,
        "name": staple.name,
        "category": staple.category,
        "in_stock": any(names_match(staple.name, n) for n in names),
    }


@bp.get("")
@login_required
def list_staples():
    names = ingredient_names(g.user.id)
    rows = [to_json(s, names) for s in Staple.query.filter_by(user_id=g.user.id).all()]
    rows.sort(
        key=lambda r: (r["in_stock"], CATEGORY_ORDER.get(r["category"], len(CATEGORY_ORDER)), r["category"], r["name"])
    )
    return jsonify(rows)


@bp.post("")
@login_required
def create_staple():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    name = text(data.get("name"), "필수품 이름은", 50)
    category = text(data.get("category", "기타"), "분류는", 10)
    if Staple.query.filter_by(user_id=g.user.id, name=name).first():
        abort(400, "이미 등록된 필수품이에요.")
    staple = Staple(user_id=g.user.id, name=name, category=category)
    db.session.add(staple)
    db.session.commit()
    return jsonify(to_json(staple, ingredient_names(g.user.id))), 201


@bp.delete("/<int:staple_id>")
@login_required
def delete_staple(staple_id):
    db.session.delete(get_owned_or_404(Staple, staple_id))
    db.session.commit()
    return "", 204
```

`backend/app/__init__.py`에 `from .staples import bp as staples_bp`와 `app.register_blueprint(staples_bp)` 추가.

`backend/migrations/versions/a2b2c2d2e2f2_staples.py`:
```python
"""staples

Revision ID: a2b2c2d2e2f2
Revises: a1b1c1d1e1f1
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a2b2c2d2e2f2"
down_revision = "a1b1c1d1e1f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "staples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_staples_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staples")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_staples_user_id")),
    )
    with op.batch_alter_table("staples") as batch_op:
        batch_op.create_index(batch_op.f("ix_staples_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("staples") as batch_op:
        batch_op.drop_index(batch_op.f("ix_staples_user_id"))
    op.drop_table("staples")
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: 실패 0, 경고 0

- [ ] **Step 5: 개발 DB 적용·일치 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app db upgrade && .venv/bin/flask --app app db check`
Expected: `No new upgrade operations detected.`

- [ ] **Step 6: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "feat: 필수품 목록과 재고 이름 매칭"
```

---

### Task 6: 필수품 화면 (떨어진 필수품 배너·필수품 시트)

시안: `Main.dc.html`(배너), `StaplesSheet.dc.html`.

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/components/SettingsSheet.tsx`, `frontend/src/pages/Fridge.tsx`
- Create: `frontend/src/components/StaplesSheet.tsx`

**Interfaces:**
- Consumes: Task 5 API (`/api/staples`), Task 4 `SettingsSheet`/`Fridge` 구조, Task 2 `Sheet`/`Icon`/CSS
- Produces: 타입 `Staple {id, name, category, in_stock}`; `StaplesSheet({ staples, onChanged, onClose })`; `SettingsTarget`에 `"staples"` 추가

(브랜치: Task 5와 같은 `feature/staples`에서 계속)

- [ ] **Step 1: 타입·스타일**

`frontend/src/api.ts`의 `StorageLocation` 인터페이스 아래에 추가:
```ts
export interface Staple {
  id: number;
  name: string;
  category: string;
  in_stock: boolean;
}
```

`frontend/src/styles.css` 끝에 추가:
```css
.banner > svg {
  flex-shrink: 0;
  color: var(--placeholder);
}

.stock-ok {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-3);
  font-size: 14px;
}

.text-btn.strong {
  color: var(--text-2);
  font-weight: 600;
}

.add-row {
  display: flex;
  gap: 8px;
}

.add-row .input {
  flex: 1;
  min-width: 0;
  height: 52px;
}

.add-row .btn {
  width: 72px;
  min-height: 52px;
  padding: 0;
  border-radius: 14px;
  font-size: 16px;
}

.staple-name {
  font-size: 17px;
  font-weight: 500;
}

.group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
```

- [ ] **Step 2: 필수품 시트**

`frontend/src/components/StaplesSheet.tsx`:
```tsx
import { useState, type FormEvent } from "react";
import { api, type Staple } from "../api";
import Icon from "./Icon";
import Sheet from "./Sheet";

const CATEGORIES = ["조미료", "야채", "기타"];

interface Props {
  staples: Staple[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function StaplesSheet({ staples, onChanged, onClose }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => api("/api/staples", { method: "POST", body: { name, category } }))) setName("");
  };

  const groups = [...CATEGORIES, ...new Set(staples.map((s) => s.category).filter((c) => !CATEGORIES.includes(c)))]
    .map((c) => ({ category: c, items: staples.filter((s) => s.category === c) }))
    .filter((g) => g.items.length > 0);

  return (
    <Sheet
      title="필수품"
      description="항상 있어야 하는 재료예요. 떨어지면 냉장고 화면에서 알려드려요."
      action={
        staples.length > 0 && (
          <button className="text-btn strong" onClick={() => setEditMode(!editMode)}>
            {editMode ? "완료" : "편집"}
          </button>
        )
      }
      onClose={onClose}
    >
      {groups.length === 0 ? (
        <p className="hint">아직 등록한 필수품이 없어요. 아래에서 추가해 보세요.</p>
      ) : (
        <div className="groups">
          {groups.map((group) => (
            <section key={group.category} className="group" aria-label={group.category}>
              <h3 className="section-label">{group.category}</h3>
              <ul className="plain-list">
                {group.items.map((staple) => (
                  <li key={staple.id} className="plain-row">
                    <span className="staple-name">{staple.name}</span>
                    {editMode ? (
                      <button
                        className="btn danger-text inline"
                        disabled={busy}
                        onClick={() => run(() => api(`/api/staples/${staple.id}`, { method: "DELETE" }))}
                      >
                        삭제
                      </button>
                    ) : staple.in_stock ? (
                      <span className="stock-ok">
                        <Icon name="check" size={16} />
                        있음
                      </span>
                    ) : (
                      <span className="badge danger">떨어짐</span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form className="form compact divider-top" onSubmit={add}>
        <div className="add-row">
          <input
            className="input"
            id="new-staple-name"
            aria-label="필수품 이름"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={50}
            placeholder="예: 고춧가루"
            required
          />
          <button className="btn primary" disabled={busy}>
            추가
          </button>
        </div>
        <div className="choices" role="group" aria-label="분류">
          {CATEGORIES.map((c) => (
            <button key={c} type="button" className="choice" aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c}
            </button>
          ))}
        </div>
      </form>
    </Sheet>
  );
}
```
`.section-label`이 `<h3>`에 쓰이므로 styles.css의 `.section-label` 규칙은 이미 `margin: 0`을 갖고 있다(Task 2).

- [ ] **Step 3: 설정 메뉴에 필수품**

`frontend/src/components/SettingsSheet.tsx`:
```tsx
export type SettingsTarget = "locations" | "staples";

const MENU: { target: SettingsTarget; label: string }[] = [
  { target: "locations", label: "보관 위치" },
  { target: "staples", label: "필수품" },
];
```

- [ ] **Step 4: 냉장고 화면에 배너와 시트 연결**

`frontend/src/pages/Fridge.tsx`:
- import에 `type Staple` 추가, `import StaplesSheet from "../components/StaplesSheet";` 추가
- `locations` state 아래에 추가: `const [staples, setStaples] = useState<Staple[]>([]);`
- `load`의 `Promise.all([...])` 배열에 추가: `api<Staple[]>("/api/staples").then(setStaples),`
- `const soon = ...` 줄 아래에 추가: `const missing = staples.filter((s) => !s.in_stock);`
- 오류 `<p className="error">` 블록 바로 아래에 추가:
```tsx
      {missing.length > 0 && (
        <button className="banner" onClick={() => setPanel("staples")}>
          <span className="banner-icon">
            <Icon name="alert" size={22} />
          </span>
          <span className="row-main">
            <span className="banner-title">필수품 {missing.length}개가 떨어졌어요</span>
            <span className="banner-sub">{missing.map((s) => s.name).join(", ")}</span>
          </span>
          <Icon name="chevron" />
        </button>
      )}
```
- `LocationsSheet` 렌더 블록 아래에 추가:
```tsx
      {panel === "staples" && <StaplesSheet staples={staples} onChanged={load} onClose={() => setPanel(null)} />}
```

- [ ] **Step 5: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류 없음

- [ ] **Step 6: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 떨어진 필수품 배너와 필수품 관리 화면"
```

---

### Task 7: 품목별 경고 규칙 백엔드 (식약처 참고값 기본값·위험 상태)

**Files:**
- Create: `backend/app/item_rules.py`, `backend/migrations/versions/a3b3c3d3e3f3_item_rules.py`, `backend/tests/test_item_rules.py`
- Modify: `backend/app/models.py`, `backend/app/defaults.py`, `backend/app/ingredients.py`, `backend/app/__init__.py`
- Modify: `backend/tests/test_ingredients.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: Task 3 `text()`, `integer()`, `seed_user_defaults`, `ingredient_status(..., kind)`; Task 5 `keyword_in`
- Produces:
  - `app.models.ItemRule(id, user_id, keyword, warn_days, danger_days, source, created_at)`
  - `app.defaults.DEFAULT_RULES: list[tuple[str, int, int, str]]`; `seed_user_defaults`가 규칙도 만든다
  - `app.ingredients.ingredient_status(purchased_on, expires_on, today, kind="fridge", rule=None) -> "danger"|"urgent"|"old"|"ok"` (`rule`은 `(warn_days, danger_days)`)
  - `app.ingredients.matching_rule(name, rules) -> tuple[int, int] | None`
  - API `GET/POST /api/item-rules`, `PATCH/DELETE /api/item-rules/<id>`. JSON `{id, keyword, warn_days, danger_days, source}`, 목록은 keyword 순
  - Alembic revision `a3b3c3d3e3f3` (down `a2b2c2d2e2f2`)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/item-warning-rules
```
(`feature/staples`가 main에 병합된 뒤 시작한다.)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_item_rules.py`:
```python
import pytest

DEFAULTS = {
    "달걀": (25, 30, "user"),
    "계란": (25, 30, "user"),
    "두부": (15, 18, "mfds"),
    "요거트": (22, 25, "mfds"),
    "요구르트": (22, 25, "mfds"),
    "주스": (25, 28, "mfds"),
    "빵": (21, 24, "mfds"),
    "어묵": (30, 33, "mfds"),
    "소시지": (41, 44, "mfds"),
    "햄": (42, 45, "mfds"),
}


def rules_by_keyword(client):
    return {r["keyword"]: r for r in client.get("/api/item-rules").get_json()}


def test_new_user_gets_default_rules(client, login):
    login()
    rules = rules_by_keyword(client)
    assert {k: (r["warn_days"], r["danger_days"], r["source"]) for k, r in rules.items()} == DEFAULTS
    assert "우유" not in rules


def test_dev_login_seeds_rules_once(client):
    client.post("/api/dev-login")
    client.post("/api/dev-login")
    assert len(client.get("/api/item-rules").get_json()) == len(DEFAULTS)


def test_create_update_delete(client, login):
    login()
    res = client.post("/api/item-rules", json={"keyword": "닭가슴살", "warn_days": 2, "danger_days": 4})
    assert res.status_code == 201
    assert res.get_json()["source"] == "user"

    tofu = rules_by_keyword(client)["두부"]
    res = client.patch(f"/api/item-rules/{tofu['id']}", json={"danger_days": 20})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["warn_days"], body["danger_days"], body["source"]) == (15, 20, "user")

    assert client.delete(f"/api/item-rules/{tofu['id']}").status_code == 204
    assert "두부" not in rules_by_keyword(client)


@pytest.mark.parametrize(
    "body",
    [
        {"keyword": "", "warn_days": 1, "danger_days": 2},
        {"keyword": "닭", "warn_days": 0, "danger_days": 2},
        {"keyword": "닭", "warn_days": 3, "danger_days": 3},
        {"keyword": "닭", "warn_days": True, "danger_days": 3},
        {"keyword": "닭", "warn_days": "2", "danger_days": 3},
        {"keyword": "두부", "warn_days": 1, "danger_days": 2},
    ],
)
def test_create_validation(client, login, body):
    login()
    res = client.post("/api/item-rules", json=body)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_patch_must_keep_red_after_yellow(client, login):
    login()
    egg = rules_by_keyword(client)["계란"]
    res = client.patch(f"/api/item-rules/{egg['id']}", json={"warn_days": 30})
    assert res.status_code == 400
    assert res.get_json()["error"] == "빨강 경고 일수는 노랑보다 커야 해요."


def test_other_users_rule_is_hidden(client, login):
    login("owner")
    rule_id = rules_by_keyword(client)["햄"]["id"]
    login("intruder")
    assert client.patch(f"/api/item-rules/{rule_id}", json={"warn_days": 1}).status_code == 404
    assert client.delete(f"/api/item-rules/{rule_id}").status_code == 404
```

`backend/tests/test_ingredients.py` 수정:

1) import 줄 `from app.ingredients import ingredient_status, seoul_today`를 교체:
```python
from types import SimpleNamespace

from app.ingredients import ingredient_status, matching_rule, seoul_today
```

2) `test_old_threshold_depends_on_location_kind` 아래에 추가:
```python
@pytest.mark.parametrize(
    "days, expires_in, expected",
    [
        (24, None, "ok"),
        (25, None, "old"),
        (30, None, "danger"),
        (30, 10, "danger"),  # 유통기한이 넉넉해도 품목 규칙이 더 심각하면 위험
        (5, 1, "urgent"),  # 유통기한 임박이 품목 규칙보다 심각
    ],
)
def test_item_rule_status(days, expires_in, expected):
    expires = None if expires_in is None else TODAY + timedelta(days=expires_in)
    assert ingredient_status(TODAY - timedelta(days=days), expires, TODAY, "fridge", (25, 30)) == expected


def test_item_rule_replaces_location_kind_rule():
    assert ingredient_status(TODAY - timedelta(days=10), None, TODAY, "fridge", (25, 30)) == "ok"
    assert ingredient_status(TODAY - timedelta(days=31), None, TODAY, "room", (25, 30)) == "danger"


def test_matching_rule_picks_shortest_danger():
    rules = [
        SimpleNamespace(keyword="빵", warn_days=21, danger_days=24),
        SimpleNamespace(keyword="소시지", warn_days=41, danger_days=44),
    ]
    assert matching_rule("소시지빵", rules) == (21, 24)
    assert matching_rule("우유", rules) is None


def test_egg_rule_applied_and_sorted_first(client, login):
    login()
    today = seoul_today()
    create(client, name="우유", expires_on=today.isoformat())
    res = create(client, name="유정란 계란 10구", purchased_on=(today - timedelta(days=31)).isoformat())
    assert res.get_json()["status"] == "danger"
    assert client.get("/api/ingredients").get_json()[0]["name"] == "유정란 계란 10구"
```

3) `test_create_and_list_sorted_by_urgency`에서 두부에 기본 규칙(18일 위험)이 걸리므로 이름만 바꾼다: `create(client, name="두부", ...)` → `create(client, name="애호박", ...)`, 기대값 `("두부", "old")` → `("애호박", "old")`.

`backend/tests/test_migrations.py` 끝에 추가:
```python
def test_item_rules_migration_seeds_existing_users(tmp_path, monkeypatch):
    app = migration_app(tmp_path, monkeypatch)
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a2b2c2d2e2f2")
        with db.engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, provider, provider_id, nickname, created_at) "
                    "VALUES (1, 'test', '1', 'u', '2026-09-01 00:00:00')"
                )
            )

        upgrade(directory=MIGRATIONS, revision="a3b3c3d3e3f3")

        with db.engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT keyword, warn_days, danger_days FROM item_rules WHERE user_id = 1")
            ).all()
        assert len(rows) == 10
        assert ("계란", 25, 30) in [tuple(r) for r in rows]
```
그리고 `test_upgrade_to_head_and_back_to_base`의 테이블 집합에 `"item_rules"`를 추가한다.

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: 새 테스트 실패(404, ImportError `matching_rule`, `item_rules` 테이블 없음)

- [ ] **Step 3: 모델·기본값**

`backend/app/models.py` 끝에 추가:
```python


class ItemRule(db.Model):
    __tablename__ = "item_rules"
    __table_args__ = (db.UniqueConstraint("user_id", "keyword"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword = db.Column(db.String(20), nullable=False)
    warn_days = db.Column(db.Integer, nullable=False)
    danger_days = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(10), nullable=False, default="user")  # mfds | user
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
```

`backend/app/defaults.py` 전체 교체:
```python
from .models import ItemRule, StorageLocation, db

DEFAULT_LOCATIONS = [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]


def _mfds(reference_days):
    """식약처 소비기한 참고값은 제조일 기준이라, 구입일 기준으로는 80%(내림)에서 빨강, 그 3일 전부터 노랑."""
    danger = reference_days * 8 // 10
    return danger - 3, danger


# 기본 품목 규칙 (키워드, 노랑 일수, 빨강 일수, 출처). 기준일은 구입일. 스펙 14절.
# 식약처 「식품유형별 소비기한 설정 보고서」 참고값: 두부 23, 발효유 32, 과채주스 35, 빵류 31, 어묵 42, 소시지 56, 햄 57일
#   https://www.foodnews.co.kr/news/articleView.html?idxno=99913
#   https://www.lecturernews.com/news/articleView.html?idxno=113115
# 달걀·계란: 식약처 권장 산란일 기준 45일, 가정 냉장 3~5주 → 구입일 기준 30일 (사용자 결정 2026-09-13)
# 우유: 참고값 없음(우유류 소비기한 표시제 2031년 적용) → 규칙 없이 포장 소비기한 입력을 안내
DEFAULT_RULES = [
    ("달걀", 25, 30, "user"),
    ("계란", 25, 30, "user"),
    ("두부", *_mfds(23), "mfds"),
    ("요거트", *_mfds(32), "mfds"),
    ("요구르트", *_mfds(32), "mfds"),
    ("주스", *_mfds(35), "mfds"),
    ("빵", *_mfds(31), "mfds"),
    ("어묵", *_mfds(42), "mfds"),
    ("소시지", *_mfds(56), "mfds"),
    ("햄", *_mfds(57), "mfds"),
]


def seed_user_defaults(user_id):
    """새 사용자에게 기본 보관 위치와 품목 규칙을 만든다. commit은 호출 측에서."""
    for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
        db.session.add(StorageLocation(user_id=user_id, name=name, kind=kind, sort_order=order))
    for keyword, warn_days, danger_days, source in DEFAULT_RULES:
        db.session.add(
            ItemRule(user_id=user_id, keyword=keyword, warn_days=warn_days, danger_days=danger_days, source=source)
        )
```

- [ ] **Step 4: 상태 판정 확장**

`backend/app/ingredients.py`:
- import에 추가: `from .matching import keyword_in`, 그리고 `from .models import Ingredient, db`를 `from .models import Ingredient, ItemRule, db`로
- `STATUS_RANK` 줄을 교체:
```python
SEVERITY = {"ok": 0, "old": 1, "urgent": 2, "danger": 3}
STATUS_RANK = {"danger": 0, "urgent": 1, "old": 2, "ok": 3}
```
- `ingredient_status` 교체하고 헬퍼 추가:
```python
def ingredient_status(purchased_on, expires_on, today, kind="fridge", rule=None):
    """rule은 (warn_days, danger_days) 또는 None. 가장 심각한 상태를 고른다 (스펙 14절)."""
    statuses = []
    if expires_on is not None:
        statuses.append("urgent" if (expires_on - today).days <= URGENT_DAYS else "ok")
    age = (today - purchased_on).days
    if rule is not None:
        warn_days, danger_days = rule
        statuses.append("danger" if age >= danger_days else "old" if age >= warn_days else "ok")
    if not statuses:
        old_days = OLD_DAYS_BY_KIND[kind]
        statuses.append("old" if old_days is not None and age >= old_days else "ok")
    return max(statuses, key=SEVERITY.__getitem__)


def matching_rule(name, rules):
    """이름에 키워드가 들어가는 규칙 중 빨강 일수가 가장 짧은 규칙의 (warn_days, danger_days)."""
    matched = [r for r in rules if keyword_in(r.keyword, name)]
    if not matched:
        return None
    best = min(matched, key=lambda r: r.danger_days)
    return best.warn_days, best.danger_days


def user_rules(user_id):
    return ItemRule.query.filter_by(user_id=user_id).all()


def status_of(item, today, rules):
    return ingredient_status(
        item.purchased_on, item.expires_on, today, item.location.kind, matching_rule(item.name, rules)
    )
```
- `to_json(item, today)` 시그니처를 `to_json(item, today, rules)`로 바꾸고 `"status"` 값을 `status_of(item, today, rules)`로
- `list_ingredients`:
```python
@bp.get("")
@login_required
def list_ingredients():
    today = seoul_today()
    rules = user_rules(g.user.id)
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=g.user.id).all()
    items.sort(
        key=lambda i: (STATUS_RANK[status_of(i, today, rules)], i.expires_on or date.max, i.purchased_on, i.id)
    )
    return jsonify([to_json(i, today, rules) for i in items])
```
- `create_ingredient`와 `update_ingredient`의 반환을 각각 교체:
```python
    return jsonify(to_json(item, seoul_today(), user_rules(g.user.id))), 201
```
```python
    return jsonify(to_json(item, seoul_today(), user_rules(g.user.id)))
```

- [ ] **Step 5: 규칙 API**

`backend/app/item_rules.py`:
```python
from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .models import ItemRule, db
from .validation import integer, text

bp = Blueprint("item_rules", __name__, url_prefix="/api/item-rules")

MAX_DAYS = 3650


def to_json(rule):
    return {
        "id": rule.id,
        "keyword": rule.keyword,
        "warn_days": rule.warn_days,
        "danger_days": rule.danger_days,
        "source": rule.source,
    }


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    return data


def _keyword(value, exclude_id=None):
    keyword = text(value, "품목 이름은", 20)
    query = ItemRule.query.filter_by(user_id=g.user.id, keyword=keyword)
    if exclude_id is not None:
        query = query.filter(ItemRule.id != exclude_id)
    if query.first():
        abort(400, "이미 있는 품목이에요.")
    return keyword


def _check_order(warn_days, danger_days):
    if danger_days <= warn_days:
        abort(400, "빨강 경고 일수는 노랑보다 커야 해요.")


@bp.get("")
@login_required
def list_rules():
    rules = ItemRule.query.filter_by(user_id=g.user.id).order_by(ItemRule.keyword).all()
    return jsonify([to_json(r) for r in rules])


@bp.post("")
@login_required
def create_rule():
    data = _json_body()
    keyword = _keyword(data.get("keyword"))
    warn_days = integer(data.get("warn_days"), "노랑 경고 일수는", 1, MAX_DAYS)
    danger_days = integer(data.get("danger_days"), "빨강 경고 일수는", 1, MAX_DAYS)
    _check_order(warn_days, danger_days)
    rule = ItemRule(user_id=g.user.id, keyword=keyword, warn_days=warn_days, danger_days=danger_days, source="user")
    db.session.add(rule)
    db.session.commit()
    return jsonify(to_json(rule)), 201


@bp.patch("/<int:rule_id>")
@login_required
def update_rule(rule_id):
    rule = get_owned_or_404(ItemRule, rule_id)
    data = _json_body()
    keyword = _keyword(data["keyword"], exclude_id=rule.id) if "keyword" in data else rule.keyword
    warn_days = integer(data["warn_days"], "노랑 경고 일수는", 1, MAX_DAYS) if "warn_days" in data else rule.warn_days
    danger_days = (
        integer(data["danger_days"], "빨강 경고 일수는", 1, MAX_DAYS) if "danger_days" in data else rule.danger_days
    )
    _check_order(warn_days, danger_days)
    rule.keyword, rule.warn_days, rule.danger_days, rule.source = keyword, warn_days, danger_days, "user"
    db.session.commit()
    return jsonify(to_json(rule))


@bp.delete("/<int:rule_id>")
@login_required
def delete_rule(rule_id):
    db.session.delete(get_owned_or_404(ItemRule, rule_id))
    db.session.commit()
    return "", 204
```

`backend/app/__init__.py`에 `from .item_rules import bp as item_rules_bp`와 `app.register_blueprint(item_rules_bp)` 추가.

- [ ] **Step 6: 마이그레이션**

`backend/migrations/versions/a3b3c3d3e3f3_item_rules.py`:
```python
"""item rules

Revision ID: a3b3c3d3e3f3
Revises: a2b2c2d2e2f2
Create Date: 2026-09-13

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "a3b3c3d3e3f3"
down_revision = "a2b2c2d2e2f2"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본 규칙을 숫자로 고정한다 (app/defaults.py DEFAULT_RULES와 같은 값)
DEFAULT_RULES = [
    ("달걀", 25, 30, "user"),
    ("계란", 25, 30, "user"),
    ("두부", 15, 18, "mfds"),
    ("요거트", 22, 25, "mfds"),
    ("요구르트", 22, 25, "mfds"),
    ("주스", 25, 28, "mfds"),
    ("빵", 21, 24, "mfds"),
    ("어묵", 30, 33, "mfds"),
    ("소시지", 41, 44, "mfds"),
    ("햄", 42, 45, "mfds"),
]


def upgrade():
    op.create_table(
        "item_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=20), nullable=False),
        sa.Column("warn_days", sa.Integer(), nullable=False),
        sa.Column("danger_days", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_item_rules_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_rules")),
        sa.UniqueConstraint("user_id", "keyword", name=op.f("uq_item_rules_user_id")),
    )
    with op.batch_alter_table("item_rules") as batch_op:
        batch_op.create_index(batch_op.f("ix_item_rules_user_id"), ["user_id"], unique=False)

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all():
        for keyword, warn_days, danger_days, source in DEFAULT_RULES:
            conn.execute(
                sa.text(
                    "INSERT INTO item_rules (user_id, keyword, warn_days, danger_days, source, created_at) "
                    "VALUES (:user_id, :keyword, :warn_days, :danger_days, :source, :created_at)"
                ),
                {
                    "user_id": user_id,
                    "keyword": keyword,
                    "warn_days": warn_days,
                    "danger_days": danger_days,
                    "source": source,
                    "created_at": now,
                },
            )


def downgrade():
    with op.batch_alter_table("item_rules") as batch_op:
        batch_op.drop_index(batch_op.f("ix_item_rules_user_id"))
    op.drop_table("item_rules")
```

`backend/tests/test_item_rules.py` 끝에 기본값 이중 관리 방지 테스트 추가:
```python
def test_migration_defaults_match_app_defaults():
    import importlib.util
    from pathlib import Path

    from app.defaults import DEFAULT_RULES

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "a3b3c3d3e3f3_item_rules.py"
    spec = importlib.util.spec_from_file_location("item_rules_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.DEFAULT_RULES == DEFAULT_RULES
```

- [ ] **Step 7: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: 실패 0, 경고 0

- [ ] **Step 8: 개발 DB 적용·일치 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app db upgrade && .venv/bin/flask --app app db check`
Expected: `No new upgrade operations detected.`

- [ ] **Step 9: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "feat: 품목별 경고 규칙(식약처 참고값·달걀)과 섭취 주의 상태"
```

---

### Task 8: 품목별 경고 화면 (섭취 주의 배지·규칙 관리·우유 안내)

**Files:**
- Modify: `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/components/SettingsSheet.tsx`, `frontend/src/components/IngredientForm.tsx`, `frontend/src/pages/Fridge.tsx`
- Create: `frontend/src/components/RulesSheet.tsx`

**Interfaces:**
- Consumes: Task 7 API (`/api/item-rules`, 재료 `status: "danger"`), Task 6까지의 `Fridge`/`SettingsSheet`
- Produces: `Status`에 `"danger"`; 타입 `ItemRule {id, keyword, warn_days, danger_days, source}`; `RulesSheet({ rules, onChanged, onClose })`; `SettingsTarget`에 `"rules"`

(브랜치: Task 7과 같은 `feature/item-warning-rules`에서 계속)

- [ ] **Step 1: 타입·스타일**

`frontend/src/api.ts`:
- `export type Status = "urgent" | "old" | "ok";` → `export type Status = "danger" | "urgent" | "old" | "ok";`
- `Staple` 인터페이스 아래에 추가:
```ts
export interface ItemRule {
  id: number;
  keyword: string;
  warn_days: number;
  danger_days: number;
  source: "mfds" | "user";
}
```

`frontend/src/styles.css` 끝에 추가:
```css
.source-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--accent-tint);
  color: var(--accent-strong);
  font-size: 12px;
  font-weight: 600;
  vertical-align: 2px;
}
```

- [ ] **Step 2: 규칙 관리 시트**

`frontend/src/components/RulesSheet.tsx`:
```tsx
import { useState, type FormEvent } from "react";
import { api, type ItemRule } from "../api";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Draft {
  keyword: string;
  warn: string;
  danger: string;
}

const EMPTY: Draft = { keyword: "", warn: "", danger: "" };

const toBody = (d: Draft) => ({ keyword: d.keyword, warn_days: Number(d.warn), danger_days: Number(d.danger) });

function RuleFields({ draft, onChange, idPrefix }: { draft: Draft; onChange: (d: Draft) => void; idPrefix: string }) {
  return (
    <>
      <input
        className="input"
        id={`${idPrefix}-keyword`}
        aria-label="품목 이름"
        placeholder="예: 닭가슴살"
        maxLength={20}
        required
        value={draft.keyword}
        onChange={(e) => onChange({ ...draft, keyword: e.target.value })}
      />
      <div className="grid-2">
        <label className="field">
          <span className="field-label">노랑 (구입 후 일)</span>
          <input
            className="input"
            id={`${idPrefix}-warn`}
            type="number"
            inputMode="numeric"
            min="1"
            max="3650"
            step="1"
            required
            value={draft.warn}
            onChange={(e) => onChange({ ...draft, warn: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field-label">빨강 (구입 후 일)</span>
          <input
            className="input"
            id={`${idPrefix}-danger`}
            type="number"
            inputMode="numeric"
            min="1"
            max="3650"
            step="1"
            required
            value={draft.danger}
            onChange={(e) => onChange({ ...draft, danger: e.target.value })}
          />
        </label>
      </div>
    </>
  );
}

interface Props {
  rules: ItemRule[];
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

export default function RulesSheet({ rules, onChanged, onClose }: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<Draft>(EMPTY);
  const [newDraft, setNewDraft] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (rule: ItemRule) => {
    setEditingId(rule.id);
    setEditDraft({ keyword: rule.keyword, warn: String(rule.warn_days), danger: String(rule.danger_days) });
    setError("");
  };

  const saveEdit = async (e: FormEvent) => {
    e.preventDefault();
    const body = toBody(editDraft);
    if (await run(() => api(`/api/item-rules/${editingId}`, { method: "PATCH", body }))) setEditingId(null);
  };

  const remove = async (rule: ItemRule) => {
    if (!confirm(`${rule.keyword} 경고를 삭제할까요?`)) return;
    if (await run(() => api(`/api/item-rules/${rule.id}`, { method: "DELETE" }))) setEditingId(null);
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const body = toBody(newDraft);
    if (await run(() => api("/api/item-rules", { method: "POST", body }))) setNewDraft(EMPTY);
  };

  return (
    <Sheet
      title="품목별 경고"
      description="구입일부터 센 날짜예요. 포장에 소비기한이 적혀 있으면 재료에 직접 입력하는 게 가장 정확해요."
      onClose={onClose}
    >
      <ul className="plain-list">
        {rules.map((rule) => (
          <li key={rule.id}>
            {editingId === rule.id ? (
              <form className="form edit-block" onSubmit={saveEdit}>
                <RuleFields draft={editDraft} onChange={setEditDraft} idPrefix={`rule-${rule.id}`} />
                <div className="actions">
                  <button type="button" className="btn secondary" onClick={() => setEditingId(null)}>
                    취소
                  </button>
                  <button className="btn primary" disabled={busy}>
                    저장
                  </button>
                </div>
                <button type="button" className="btn danger-text" disabled={busy} onClick={() => remove(rule)}>
                  이 경고 삭제
                </button>
              </form>
            ) : (
              <div className="plain-row location-row">
                <div className="row-main">
                  <span className="row-title">
                    {rule.keyword}
                    {rule.source === "mfds" && <span className="source-tag">식약처 참고값</span>}
                  </span>
                  <span className="row-sub">
                    노랑 {rule.warn_days}일 · 빨강 {rule.danger_days}일
                  </span>
                </div>
                <button className="icon-btn" aria-label={`${rule.keyword} 수정`} onClick={() => startEdit(rule)}>
                  <Icon name="more" />
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form className="form compact divider-top" onSubmit={add}>
        <span className="field-label">새 경고</span>
        <RuleFields draft={newDraft} onChange={setNewDraft} idPrefix="new-rule" />
        <button className="btn primary" disabled={busy}>
          경고 추가
        </button>
      </form>
    </Sheet>
  );
}
```

- [ ] **Step 3: 설정 메뉴**

`frontend/src/components/SettingsSheet.tsx`:
```tsx
export type SettingsTarget = "locations" | "staples" | "rules";

const MENU: { target: SettingsTarget; label: string }[] = [
  { target: "locations", label: "보관 위치" },
  { target: "staples", label: "필수품" },
  { target: "rules", label: "품목별 경고" },
];
```

- [ ] **Step 4: 재료 시트의 우유 안내**

`frontend/src/components/IngredientForm.tsx`에서 구입일/유통기한 `grid-2` 블록 바로 아래에 추가:
```tsx
        {name.includes("우유") && !expiresOn && (
          <p className="hint">우유는 포장에 적힌 소비기한을 입력하면 가장 정확해요.</p>
        )}
```

- [ ] **Step 5: 냉장고 화면**

`frontend/src/pages/Fridge.tsx`:
- import에 `type ItemRule` 추가, `import RulesSheet from "../components/RulesSheet";` 추가
- `badge` 함수 첫 줄에 추가: `if (item.status === "danger") return "섭취 주의";`
- `staples` state 아래에 추가: `const [rules, setRules] = useState<ItemRule[]>([]);`
- `load`의 배열에 추가: `api<ItemRule[]>("/api/item-rules").then(setRules),`
- `const soon = ...` 줄을 교체: `const soon = items?.filter((i) => i.status === "urgent" || i.status === "danger").length ?? 0;`
- 목록 `row-sub`의 `{formatDate(item.purchased_on)} 구입` 뒤에 추가: `{item.status === "danger" && ` · 구입 ${item.days_since_purchase}일째`}`
- `StaplesSheet` 렌더 블록 아래에 추가:
```tsx
      {panel === "rules" && <RulesSheet rules={rules} onChanged={load} onClose={() => setPanel(null)} />}
```

- [ ] **Step 6: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류 없음

- [ ] **Step 7: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 섭취 주의 배지와 품목별 경고 관리 화면"
```

---

## 1b단계 완료 기준

- `backend/.venv/bin/pytest -q` 실패 0·경고 0, `flask db check` 차이 없음
- `frontend`에서 `npm run build` 성공
- 5개 브랜치가 순서대로 main에 `--no-ff` 병합됨
- 폰(`./dev.sh`)에서: 위치 탭 필터, 재료 추가 시 위치 선택, 위치 추가·이름 변경·삭제 규칙, 떨어진 필수품 배너, 구입 31일 지난 계란의 `섭취 주의` 배지, 규칙 수정, 라이트/다크 모두 시안과 같은 느낌
