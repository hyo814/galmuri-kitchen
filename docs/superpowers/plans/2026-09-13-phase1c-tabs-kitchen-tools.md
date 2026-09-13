# 1c단계(하단 탭·주방 도구) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면이 늘어날 것에 대비해 하단 탭(해시 라우팅, 폰 뒤로가기 지원)을 도입하고, 조리도구·조리기구를 등록해 코팅 프라이팬 같은 도구의 주기 점검을 알려준다.

**Architecture:** 라우터 라이브러리 없이 `location.hash`(`#/`, `#/more`, `#/tools`)와 `hashchange`로 화면을 바꾼다(브라우저 기본 기능, 뒤로가기 동작). 반복되던 시트의 busy/error 처리 코드를 `useAsyncAction` 훅 하나로 모은다. 백엔드는 `kitchen_tools` 모델·마이그레이션·API를 추가하고, 점검 예정일은 서버가 계산한다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, pytest 9.1.1 / Vite 8, React 19, TypeScript

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 18절(주방 도구). 디자인은 `docs/design/fridge-1b/*.dc.html`의 토큰·컴포넌트를 그대로 따른다(새 시안 없음).

## Global Constraints

- 경로에 공백: `/Users/limhyojin/PycharmProjects/ recipe-ai` — 항상 따옴표.
- 사용자 소유 데이터는 `g.user.id`로 한정, 남의 리소스 404 `{"error": "찾을 수 없어요."}`. 오류 형식 `{"error": "<한국어>"}`.
- 문자열은 `validation.text()`, 정수는 `validation.integer()`(bool 거부). 날짜는 `YYYY-MM-DD`.
- UNIQUE 경합은 `validation`의 IntegrityError→400 헬퍼 패턴을 따른다(기존 `locations.py` 참고).
- 오늘 날짜는 `app.ingredients.seoul_today()`(Asia/Seoul).
- 테스트는 `backend/.venv/bin/pytest -q -W error::DeprecationWarning` — 실패 0, 경고 0.
- 새 마이그레이션은 datetime을 raw로 넣지 않는다(데이터 삽입이 필요하면 `sa.bindparam(type_=sa.DateTime(timezone=True))`).
- 모바일 우선 384px, 터치 타깃 44px 이상, 입력 글자 16px 이상, 이모지 대신 인라인 SVG(`Icon`).
- 삭제 버튼은 `.btn.danger-text`(연빨강 배경+테두리)로, 취소 아래에 둔다(사용자 요청 두 번).
- 개발 서버 포트: Vite 5180, Flask 5181. 다른 프로젝트의 5173은 절대 건드리지 않는다.
- 커밋 메시지 끝(빈 줄 뒤):
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치

| 브랜치 | 태스크 | 병합 시점 |
|---|---|---|
| `feature/bottom-tabs` | 1 | 태스크 1 리뷰 통과 후 컨트롤러가 병합 |
| `feature/kitchen-tools` | 2, 3 | 태스크 3 리뷰 통과 후 |

## 파일 구조

```
frontend/src/
  useHashRoute.ts            (신규) 해시 경로 읽기/이동
  useAsyncAction.ts          (신규) busy/error를 가진 비동기 실행 훅
  components/TabBar.tsx      (신규) 하단 탭
  pages/More.tsx             (신규) 더보기 목록
  pages/Tools.tsx            (신규, Task 3) 주방 도구 목록
  components/ToolForm.tsx    (신규, Task 3) 도구 추가/수정 시트
  App.tsx, pages/Fridge.tsx, components/{LocationsSheet,StaplesSheet,RulesSheet,IngredientForm}.tsx (수정)
  styles.css, api.ts, format.ts (수정)
backend/app/tools.py, models.py, __init__.py
backend/migrations/versions/a4b4c4d4e4f4_kitchen_tools.py
backend/tests/test_tools.py, test_migrations.py
```

---

### Task 1: 하단 탭·해시 라우팅·비동기 실행 훅

**Files:**
- Create: `frontend/src/useHashRoute.ts`, `frontend/src/useAsyncAction.ts`, `frontend/src/components/TabBar.tsx`, `frontend/src/pages/More.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Icon.tsx`, `frontend/src/styles.css`
- Modify (훅으로 정리): `frontend/src/components/IngredientForm.tsx`, `LocationsSheet.tsx`, `StaplesSheet.tsx`, `RulesSheet.tsx`

**Interfaces:**
- Produces:
  - `useHashRoute(): string` — `"#/tools"` → `"/tools"`, 해시 없으면 `"/"`
  - `useAsyncAction(): { busy: boolean; error: string; setError(msg: string): void; run(action: () => Promise<unknown>): Promise<boolean> }` — 실패 시 `error`에 메시지, `false` 반환
  - `TabBar({ route })`, 탭 목록 상수 `TABS`(이후 단계가 레시피·장보기·식단을 추가)
  - `More()` 페이지, 메뉴 상수 `MORE_ITEMS: { path, label, desc }[]`
  - Icon 이름 추가: `fridge`, `menu`, `pan`, `back`
  - CSS: `--tabbar-h`, `.tabbar`, `.tab`, `a.row-btn`, `.back-link`; `.page`와 `.cta-bar`가 탭 높이만큼 위로

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/bottom-tabs
```

- [ ] **Step 1: 훅 두 개**

`frontend/src/useHashRoute.ts`:
```ts
import { useEffect, useState } from "react";

// ponytail: 라우터 라이브러리 대신 브라우저 해시(#/tools). 뒤로가기가 그대로 동작한다. 경로 파라미터가 많아지면 react-router로 교체.
const currentRoute = () => location.hash.replace(/^#/, "") || "/";

export function useHashRoute(): string {
  const [route, setRoute] = useState(currentRoute);
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
```

`frontend/src/useAsyncAction.ts`:
```ts
import { useCallback, useState } from "react";

/** 저장·삭제 같은 비동기 동작의 진행 중 상태와 오류 메시지를 한곳에서 관리한다. */
export function useAsyncAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  return { busy, error, setError, run };
}
```

- [ ] **Step 2: 기존 시트를 훅으로 정리 (동작 변화 없음)**

각 파일에서 로컬 `busy`/`error` state와 `run` 함수를 지우고 `useAsyncAction()`으로 바꾼다. 화면에 보이는 동작·문구는 그대로다.

- `IngredientForm.tsx`: `const { busy, error, run } = useAsyncAction();`. 기존 `run(() => onSubmit({...}))`, `run(onDelete)` 호출은 그대로 둔다.
- `StaplesSheet.tsx`, `RulesSheet.tsx`: `const { busy, error, run } = useAsyncAction();`. 기존 `run`은 액션 뒤에 `await onChanged()`를 했으므로, 호출부를 `run(async () => { await api(...); await onChanged(); })` 형태로 바꾼다. `startEdit`에서 쓰던 `setError("")`는 훅의 `setError`를 꺼내 쓴다.
- `LocationsSheet.tsx`: 오류 칸이 둘(수정용 `editError`, 추가용 `error`)이므로 훅을 두 번 쓴다:
```tsx
  const edit = useAsyncAction();
  const create = useAsyncAction();
```
  수정·삭제는 `edit.run(async () => { await api(...); await onChanged(); })`, 추가는 `create.run(...)`. 버튼 `disabled`는 각각 `edit.busy`/`create.busy`, 오류 표시는 `edit.error`/`create.error`. `startEdit`는 `edit.setError("")`.

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build && grep -n "setBusy" src/components/*.tsx`
Expected: 빌드 성공, `setBusy` 검색 결과 없음

- [ ] **Step 3: 아이콘·탭 바·더보기**

`frontend/src/components/Icon.tsx`의 `PATHS` 객체에 추가:
```tsx
  fridge: (
    <>
      <rect x="5" y="2.5" width="14" height="19" rx="2.5" />
      <path d="M5 10h14M9 5.5v2M9 13v3" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  pan: (
    <>
      <circle cx="10" cy="12" r="6" />
      <path d="M16 12h6" />
    </>
  ),
  back: <path d="M15 6l-6 6 6 6" />,
```

`frontend/src/components/TabBar.tsx`:
```tsx
import Icon, { type IconName } from "./Icon";

interface Tab {
  path: string;
  label: string;
  icon: IconName;
  match: (route: string) => boolean;
}

// 최종 탭 순서(사용자 결정 2026-09-13): 재고 · 레시피 · 장보기 · 식단 · 더보기. 기능이 생기는 단계에서 해당 탭을 이 목록에 끼워 넣는다.
export const TABS: Tab[] = [
  { path: "/", label: "재고", icon: "fridge", match: (r) => r === "/" },
  { path: "/more", label: "더보기", icon: "menu", match: (r) => r === "/more" || r === "/tools" },
];

export default function TabBar({ route }: { route: string }) {
  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => (
        <a
          key={tab.path}
          className="tab"
          href={`#${tab.path}`}
          aria-current={tab.match(route) ? "page" : undefined}
        >
          <Icon name={tab.icon} size={24} />
          <span>{tab.label}</span>
        </a>
      ))}
    </nav>
  );
}
```

`frontend/src/pages/More.tsx`:
```tsx
import Icon from "../components/Icon";

export const MORE_ITEMS = [{ path: "/tools", label: "주방 도구", desc: "프라이팬 코팅 점검 같은 도구 관리" }];

export default function More() {
  return (
    <div className="page">
      <header className="topbar">
        <h1>더보기</h1>
      </header>
      <ul className="list">
        {MORE_ITEMS.map((item) => (
          <li key={item.path}>
            <a className="row-btn" href={`#${item.path}`}>
              <span className="row-main">
                <span className="row-title">{item.label}</span>
                <span className="row-sub">{item.desc}</span>
              </span>
              <Icon name="chevron" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
```
(Task 3이 `/tools` 화면을 연결하기 전까지 목록 항목을 누르면 냉장고 화면이 뜬다 — Task 3에서 해결.)

- [ ] **Step 4: App에 탭 연결**

`frontend/src/App.tsx`:
- import 추가:
```tsx
import TabBar from "./components/TabBar";
import More from "./pages/More";
import { useHashRoute } from "./useHashRoute";
```
- `const [offline, setOffline] = ...` 아래에 `const route = useHashRoute();` 추가
- 마지막 `return <Fridge onLogout={() => setUser(null)} />;`를 교체:
```tsx
  return (
    <>
      {route === "/more" ? <More /> : <Fridge onLogout={() => setUser(null)} />}
      <TabBar route={route} />
    </>
  );
```

- [ ] **Step 4-1: 첫 화면 이름을 '내 재고'로 (사용자 결정)**

`frontend/src/pages/Fridge.tsx`:
- `<h1>내 냉장고</h1>` → `<h1>내 재고</h1>`
- `"냉장고가 비어 있어요."` → `"재고가 비어 있어요."`

`frontend/index.html`의 `<title>`과 `frontend/public/manifest.webmanifest`의 앱 이름("냉장고 레시피")은 앱 이름이므로 바꾸지 않는다.

- [ ] **Step 5: 스타일**

`frontend/src/styles.css`:
- `.page` 규칙의 `padding-bottom`을 `padding-bottom: calc(112px + var(--tabbar-h) + env(safe-area-inset-bottom));`로
- `.cta-bar` 규칙의 `bottom: 0;`을 `bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom));`로, `padding` 줄을 `padding: 32px 20px 16px;`로
- 파일 끝에 추가:
```css
:root {
  --tabbar-h: 64px;
}

.tabbar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 10;
  display: flex;
  justify-content: center;
  height: calc(var(--tabbar-h) + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  border-top: 1px solid var(--line);
  background: var(--surface);
}

.tab {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  max-width: 160px;
  color: var(--text-3);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
}

.tab[aria-current="page"] {
  color: var(--text);
}

a.row-btn {
  color: inherit;
  text-decoration: none;
}

a.row-btn > svg {
  flex-shrink: 0;
  color: var(--text-3);
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-height: 44px;
  margin: 12px 0 -16px 12px;
  padding: 0 8px;
  color: var(--text-2);
  font-size: 15px;
  text-decoration: none;
}
```

- [ ] **Step 6: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류 없음

- [ ] **Step 7: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 하단 탭과 해시 라우팅, 시트 비동기 처리 훅으로 정리"
```

---

### Task 2: 주방 도구 백엔드 (모델·마이그레이션·API·점검 예정일)

**Files:**
- Create: `backend/app/tools.py`, `backend/migrations/versions/a4b4c4d4e4f4_kitchen_tools.py`, `backend/tests/test_tools.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`(auth), `text`, `integer`(validation), `seoul_today`, `SEOUL`(ingredients), 픽스처 `client`, `login`
- Produces:
  - `app.models.KitchenTool(id, user_id, name, category, bought_on, check_every_months, last_checked_on, created_at)`
  - `app.tools.add_months(day: date, months: int) -> date` (말일 보정)
  - API `GET/POST /api/tools`, `PATCH/DELETE /api/tools/<id>`, `POST /api/tools/<id>/checked`, `POST /api/tools/<id>/replaced`
  - 도구 JSON `{id, name, category, bought_on, check_every_months, last_checked_on, due_on, is_due, days_until_due}`
  - 목록 정렬: 점검할 때(is_due) 먼저 → due_on 빠른 순(없으면 뒤) → 분류(조리도구, 조리기구, 칼·도마, 기타) → 이름 → id
  - Alembic revision `a4b4c4d4e4f4` (down `a3b3c3d3e3f3`)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/kitchen-tools
```
(`feature/bottom-tabs`가 main에 병합된 뒤 시작한다.)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_tools.py`:
```python
from datetime import date, timedelta

import pytest

from app.ingredients import seoul_today
from app.tools import add_months


@pytest.mark.parametrize(
    "day, months, expected",
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 11, 15), 3, date(2027, 2, 15)),
        (date(2024, 8, 31), 6, date(2025, 2, 28)),
        (date(2026, 3, 10), 12, date(2027, 3, 10)),
    ],
)
def test_add_months_clamps_month_end(day, months, expected):
    assert add_months(day, months) == expected


def create(client, **fields):
    return client.post("/api/tools", json={"name": "코팅 프라이팬", "category": "조리기구", **fields})


def test_requires_login(client):
    assert client.get("/api/tools").status_code == 401


def test_pan_due_after_cycle_then_checked_and_replaced(client, login):
    login()
    today = seoul_today()
    bought = add_months(today, -7)
    res = create(client, bought_on=bought.isoformat(), check_every_months=6)
    assert res.status_code == 201
    tool = res.get_json()
    assert tool["is_due"] is True
    assert tool["due_on"] == add_months(bought, 6).isoformat()
    assert tool["days_until_due"] < 0

    checked = client.post(f"/api/tools/{tool['id']}/checked").get_json()
    assert checked["last_checked_on"] == today.isoformat()
    assert checked["is_due"] is False
    assert checked["due_on"] == add_months(today, 6).isoformat()

    replaced = client.post(f"/api/tools/{tool['id']}/replaced").get_json()
    assert (replaced["bought_on"], replaced["last_checked_on"]) == (today.isoformat(), today.isoformat())


def test_without_cycle_never_due(client, login):
    login()
    tool = client.post("/api/tools", json={"name": "뒤집개"}).get_json()
    assert (tool["category"], tool["due_on"], tool["is_due"], tool["days_until_due"]) == ("조리도구", None, False, None)


def test_created_date_is_base_when_no_dates(client, login):
    login()
    tool = create(client, check_every_months=1).get_json()
    assert tool["due_on"] == add_months(seoul_today(), 1).isoformat()


def test_list_sorts_due_first(client, login):
    login()
    today = seoul_today()
    create(client, name="뒤집개", category="조리도구")
    create(client, name="국자", category="조리도구", check_every_months=3)
    create(client, name="코팅 프라이팬", bought_on=add_months(today, -8).isoformat(), check_every_months=6)
    names = [t["name"] for t in client.get("/api/tools").get_json()]
    assert names == ["코팅 프라이팬", "국자", "뒤집개"]


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "가" * 31},
        {"category": "냄비"},
        {"check_every_months": 0},
        {"check_every_months": 61},
        {"check_every_months": True},
        {"check_every_months": "6"},
        {"bought_on": "어제"},
    ],
)
def test_create_validation(client, login, fields):
    login()
    res = create(client, **fields)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_patch_clears_cycle_and_dates(client, login):
    login()
    tool = create(client, bought_on="2026-01-01", check_every_months=6).get_json()
    res = client.patch(f"/api/tools/{tool['id']}", json={"check_every_months": None, "bought_on": None, "name": "무쇠 팬"})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["name"], body["check_every_months"], body["bought_on"], body["due_on"]) == ("무쇠 팬", None, None, None)


def test_other_users_tool_is_hidden(client, login):
    login("owner")
    tool = create(client).get_json()
    login("intruder")
    assert client.get("/api/tools").get_json() == []
    for method, path in [
        ("patch", f"/api/tools/{tool['id']}"),
        ("delete", f"/api/tools/{tool['id']}"),
        ("post", f"/api/tools/{tool['id']}/checked"),
        ("post", f"/api/tools/{tool['id']}/replaced"),
    ]:
        kwargs = {"json": {"name": "x"}} if method == "patch" else {}
        assert getattr(client, method)(path, **kwargs).status_code == 404


def test_delete(client, login):
    login()
    tool = create(client).get_json()
    assert client.delete(f"/api/tools/{tool['id']}").status_code == 204
    assert client.get("/api/tools").get_json() == []
```

`backend/tests/test_migrations.py`의 `test_upgrade_to_head_and_back_to_base` 테이블 집합에 `"kitchen_tools"`를 추가한다.

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning tests/test_tools.py tests/test_migrations.py`
Expected: ImportError `app.tools`, `kitchen_tools` 테이블 없음으로 실패

- [ ] **Step 3: 모델**

`backend/app/models.py` 끝에 추가:
```python


class KitchenTool(db.Model):
    __tablename__ = "kitchen_tools"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(30), nullable=False)
    category = db.Column(db.String(10), nullable=False, default="조리도구")
    bought_on = db.Column(db.Date)
    check_every_months = db.Column(db.Integer)
    last_checked_on = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
```

- [ ] **Step 4: API**

`backend/app/tools.py`:
```python
from calendar import monthrange
from datetime import date, timezone

from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .ingredients import SEOUL, seoul_today
from .models import KitchenTool, db
from .validation import integer, text

bp = Blueprint("tools", __name__, url_prefix="/api/tools")

CATEGORIES = ("조리도구", "조리기구", "칼·도마", "기타")
CATEGORY_ORDER = {c: i for i, c in enumerate(CATEGORIES)}


def add_months(day, months):
    """day에서 months개월 뒤(음수면 앞). 없는 날짜(예: 2월 31일)는 그 달 말일로."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def check_base(tool):
    """점검 기준일: 마지막 점검일 → 구매일 → 등록일(서울 날짜)."""
    if tool.last_checked_on or tool.bought_on:
        return tool.last_checked_on or tool.bought_on
    created = tool.created_at
    if created.tzinfo is None:  # SQLite는 timezone 없이 돌려준다(UTC로 저장됨)
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone(SEOUL).date()


def to_json(tool, today):
    due_on = add_months(check_base(tool), tool.check_every_months) if tool.check_every_months else None
    return {
        "id": tool.id,
        "name": tool.name,
        "category": tool.category,
        "bought_on": tool.bought_on.isoformat() if tool.bought_on else None,
        "check_every_months": tool.check_every_months,
        "last_checked_on": tool.last_checked_on.isoformat() if tool.last_checked_on else None,
        "due_on": due_on.isoformat() if due_on else None,
        "is_due": due_on is not None and due_on <= today,
        "days_until_due": (due_on - today).days if due_on else None,
    }


def _optional_date(value, message):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(400, message)


def parse_fields(data, creating):
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    fields = {}
    if creating or "name" in data:
        fields["name"] = text(data.get("name"), "도구 이름은", 30)
    if creating or "category" in data:
        category = data.get("category", "조리도구")
        if category not in CATEGORIES:
            abort(400, "분류를 조리도구·조리기구·칼·도마·기타 중에서 골라 주세요.")
        fields["category"] = category
    if "bought_on" in data:
        fields["bought_on"] = _optional_date(data["bought_on"], "구매일은 YYYY-MM-DD 형식으로 입력해 주세요.")
    if "check_every_months" in data:
        value = data["check_every_months"]
        fields["check_every_months"] = None if value is None else integer(value, "점검 주기는", 1, 60)
    return fields


def _sort_key(row):
    return (
        not row["is_due"],
        row["due_on"] or "9999-12-31",
        CATEGORY_ORDER.get(row["category"], len(CATEGORY_ORDER)),
        row["name"],
        row["id"],
    )


@bp.get("")
@login_required
def list_tools():
    today = seoul_today()
    rows = [to_json(t, today) for t in KitchenTool.query.filter_by(user_id=g.user.id).all()]
    rows.sort(key=_sort_key)
    return jsonify(rows)


@bp.post("")
@login_required
def create_tool():
    tool = KitchenTool(user_id=g.user.id, **parse_fields(request.get_json(silent=True), creating=True))
    db.session.add(tool)
    db.session.commit()
    return jsonify(to_json(tool, seoul_today())), 201


@bp.patch("/<int:tool_id>")
@login_required
def update_tool(tool_id):
    tool = get_owned_or_404(KitchenTool, tool_id)
    for key, value in parse_fields(request.get_json(silent=True), creating=False).items():
        setattr(tool, key, value)
    db.session.commit()
    return jsonify(to_json(tool, seoul_today()))


@bp.post("/<int:tool_id>/checked")
@login_required
def mark_checked(tool_id):
    tool = get_owned_or_404(KitchenTool, tool_id)
    tool.last_checked_on = seoul_today()
    db.session.commit()
    return jsonify(to_json(tool, seoul_today()))


@bp.post("/<int:tool_id>/replaced")
@login_required
def mark_replaced(tool_id):
    tool = get_owned_or_404(KitchenTool, tool_id)
    today = seoul_today()
    tool.bought_on = today
    tool.last_checked_on = today
    db.session.commit()
    return jsonify(to_json(tool, today))


@bp.delete("/<int:tool_id>")
@login_required
def delete_tool(tool_id):
    db.session.delete(get_owned_or_404(KitchenTool, tool_id))
    db.session.commit()
    return "", 204
```

`backend/app/__init__.py`에 `from .tools import bp as tools_bp`와 `app.register_blueprint(tools_bp)` 추가.

- [ ] **Step 5: 마이그레이션**

`backend/migrations/versions/a4b4c4d4e4f4_kitchen_tools.py`:
```python
"""kitchen tools

Revision ID: a4b4c4d4e4f4
Revises: a3b3c3d3e3f3
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a4b4c4d4e4f4"
down_revision = "a3b3c3d3e3f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kitchen_tools",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("bought_on", sa.Date(), nullable=True),
        sa.Column("check_every_months", sa.Integer(), nullable=True),
        sa.Column("last_checked_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_kitchen_tools_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kitchen_tools")),
    )
    op.create_index(op.f("ix_kitchen_tools_user_id"), "kitchen_tools", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_kitchen_tools_user_id"), table_name="kitchen_tools")
    op.drop_table("kitchen_tools")
```

- [ ] **Step 6: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning`
Expected: 실패 0, 경고 0.
Postgres 테스트가 준비돼 있으면(`docs/deploy.md`의 로컬 검증 명령) 같은 명령을 `TEST_DATABASE_URL`/`TEST_MIGRATE_DATABASE_URL`과 함께 한 번 더 실행해 통과를 확인한다.

- [ ] **Step 7: 개발 DB 적용·일치 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app db upgrade && .venv/bin/flask --app app db check`
Expected: `No new upgrade operations detected.`

- [ ] **Step 8: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "feat: 주방 도구 등록과 주기 점검 예정일 계산"
```

---

### Task 3: 주방 도구 화면 (목록·추가/수정 시트·점검/교체)

**Files:**
- Create: `frontend/src/pages/Tools.tsx`, `frontend/src/components/ToolForm.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/format.ts`, `frontend/src/styles.css`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 2 API, Task 1 `useAsyncAction`, `TabBar`의 `/tools` 매칭, `Sheet`, `Icon`(`pan`, `back`, `plus`, `check`)
- Produces:
  - 타입 `ToolCategory`, `KitchenToolInput {name, category, bought_on, check_every_months}`, `KitchenTool`(+ `id, last_checked_on, due_on, is_due, days_until_due`)
  - `cycleLabel(months: number): string` (`format.ts`) — 12의 배수는 "N년", 그 외 "N개월"
  - `Tools()` 페이지(`#/tools`), `ToolForm({ initial, onSubmit, onChecked?, onReplaced?, onDelete?, onClose })`

(브랜치: Task 2와 같은 `feature/kitchen-tools`에서 계속)

- [ ] **Step 1: 타입·포맷·스타일**

`frontend/src/api.ts`의 `ItemRule` 인터페이스 아래에 추가:
```ts
export type ToolCategory = "조리도구" | "조리기구" | "칼·도마" | "기타";

export interface KitchenToolInput {
  name: string;
  category: ToolCategory;
  bought_on: string | null;
  check_every_months: number | null;
}

export interface KitchenTool extends KitchenToolInput {
  id: number;
  last_checked_on: string | null;
  due_on: string | null;
  is_due: boolean;
  days_until_due: number | null;
}
```

`frontend/src/format.ts` 끝에 추가:
```ts
/** 6 → "6개월", 12 → "1년", 24 → "2년" */
export const cycleLabel = (months: number) => (months % 12 === 0 ? `${months / 12}년` : `${months}개월`);
```

`frontend/src/styles.css` 끝에 추가:
```css
.status-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--field);
  font-size: 15px;
  line-height: 22px;
}

.status-box.due {
  background: var(--warn-tint);
  color: var(--warn);
  font-weight: 600;
}
```

- [ ] **Step 2: 도구 입력 시트**

`frontend/src/components/ToolForm.tsx`:
```tsx
import { useState, type FormEvent } from "react";
import type { KitchenTool, KitchenToolInput, ToolCategory } from "../api";
import { cycleLabel, formatDate } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

const CATEGORIES: ToolCategory[] = ["조리도구", "조리기구", "칼·도마", "기타"];
const CYCLES: (number | null)[] = [null, 1, 3, 6, 12];
// 식약처는 기간이 아니라 상태(코팅 30% 이상 벗겨짐) 기준으로 교체를 권고한다 → 6개월마다 '점검'을 제안 (스펙 18절)
const COATED = /프라이팬|코팅/;

interface Props {
  initial: KitchenTool | null;
  onSubmit: (input: KitchenToolInput) => Promise<void>;
  onChecked?: () => Promise<void>;
  onReplaced?: () => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

export default function ToolForm({ initial, onSubmit, onChecked, onReplaced, onDelete, onClose }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState<ToolCategory>(initial?.category ?? "조리도구");
  const [cycle, setCycle] = useState<number | null>(initial?.check_every_months ?? null);
  const [cycleTouched, setCycleTouched] = useState(false);
  const [boughtOn, setBoughtOn] = useState(initial?.bought_on ?? "");
  const { busy, error, run } = useAsyncAction();

  const changeName = (value: string) => {
    setName(value);
    // 새 도구를 입력할 때 코팅 제품이면 6개월 점검을 미리 골라 준다(사용자가 주기를 직접 고르면 건드리지 않음)
    if (!initial && !cycleTouched && COATED.test(value)) setCycle(6);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(() => onSubmit({ name: name.trim(), category, bought_on: boughtOn || null, check_every_months: cycle }));
  };

  return (
    <Sheet title={initial ? "도구 수정" : "도구 추가"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        {initial?.check_every_months && (
          <div className={`status-box${initial.is_due ? " due" : ""}`}>
            <span>
              {initial.is_due
                ? "점검할 때가 됐어요"
                : `다음 점검 ${initial.due_on ? formatDate(initial.due_on) : ""}`}
            </span>
            <div className="grid-2">
              <button type="button" className="btn secondary" disabled={busy} onClick={() => onChecked && run(onChecked)}>
                <Icon name="check" size={18} />
                점검했어요
              </button>
              <button type="button" className="btn secondary" disabled={busy} onClick={() => onReplaced && run(onReplaced)}>
                교체했어요
              </button>
            </div>
          </div>
        )}

        <label className="field">
          <span className="field-label">이름</span>
          <input
            className="input"
            id="tool-name"
            value={name}
            onChange={(e) => changeName(e.target.value)}
            required
            maxLength={30}
            placeholder="예: 코팅 프라이팬"
          />
        </label>

        <div className="field" role="group" aria-label="분류">
          <span className="field-label">분류</span>
          <div className="choices">
            {CATEGORIES.map((c) => (
              <button key={c} type="button" className="choice" aria-pressed={category === c} onClick={() => setCategory(c)}>
                {c}
              </button>
            ))}
          </div>
        </div>

        <div className="field" role="group" aria-label="점검 주기">
          <span className="field-label">점검 주기</span>
          <div className="choices">
            {CYCLES.map((c) => (
              <button
                key={c ?? "none"}
                type="button"
                className="choice"
                aria-pressed={cycle === c}
                onClick={() => {
                  setCycle(c);
                  setCycleTouched(true);
                }}
              >
                {c === null ? "안 함" : cycleLabel(c)}
              </button>
            ))}
          </div>
          {COATED.test(name) && (
            <p className="hint">코팅이 30% 이상 벗겨졌다면 교체를 권장해요(식약처 기준). 6개월마다 상태를 확인해 보세요.</p>
          )}
        </div>

        <label className="field">
          <span className="field-label">
            구매일 <span className="optional">(선택)</span>
          </span>
          <input
            className="input"
            id="tool-bought"
            type="date"
            value={boughtOn}
            onChange={(e) => setBoughtOn(e.target.value)}
          />
        </label>

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
            이 도구 삭제
          </button>
        )}
      </form>
    </Sheet>
  );
}
```

- [ ] **Step 3: 도구 목록 화면**

`frontend/src/pages/Tools.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api, type KitchenTool, type KitchenToolInput } from "../api";
import Icon from "../components/Icon";
import ToolForm from "../components/ToolForm";
import { cycleLabel, formatDate } from "../format";

function subtitle(tool: KitchenTool): string {
  const parts: string[] = [tool.category];
  if (tool.check_every_months) parts.push(`${cycleLabel(tool.check_every_months)}마다 점검`);
  if (tool.last_checked_on) parts.push(`마지막 점검 ${formatDate(tool.last_checked_on)}`);
  else if (tool.bought_on) parts.push(`${formatDate(tool.bought_on)} 구매`);
  return parts.join(" · ");
}

export default function Tools() {
  const [tools, setTools] = useState<KitchenTool[] | null>(null);
  const [editing, setEditing] = useState<KitchenTool | "new" | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    setError("");
    return api<KitchenTool[]>("/api/tools").then(setTools, (e: Error) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  // 오류는 던져서 시트 안에 표시한다.
  const save = async (input: KitchenToolInput) => {
    if (editing === "new") await api("/api/tools", { method: "POST", body: input });
    else if (editing) await api(`/api/tools/${editing.id}`, { method: "PATCH", body: input });
    setEditing(null);
    await load();
  };

  const mark = (action: "checked" | "replaced") => async () => {
    if (!editing || editing === "new") return;
    await api(`/api/tools/${editing.id}/${action}`, { method: "POST" });
    setEditing(null);
    await load();
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${editing.name}을(를) 삭제할까요?`)) return;
    await api(`/api/tools/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const due = tools?.filter((t) => t.is_due).length ?? 0;

  return (
    <div className="page">
      <a className="back-link" href="#/more">
        <Icon name="back" size={18} />
        더보기
      </a>
      <header className="topbar">
        <div>
          <h1>주방 도구</h1>
          {tools && tools.length > 0 && (
            <p className="summary">
              도구 {tools.length}개{due > 0 && ` · 점검할 도구 ${due}개`}
            </p>
          )}
        </div>
      </header>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {tools === null ? (
        !error && <p className="center muted">불러오는 중…</p>
      ) : tools.length === 0 ? (
        <div className="empty">
          <p>등록한 도구가 없어요.</p>
          <p className="muted">프라이팬, 뒤집개처럼 자주 쓰는 도구를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {tools.map((tool) => (
            <li key={tool.id}>
              <button className="row-btn" onClick={() => setEditing(tool)}>
                <span className="row-main">
                  <span className="row-title">{tool.name}</span>
                  <span className="row-sub">{subtitle(tool)}</span>
                </span>
                {tool.is_due ? (
                  <span className="badge old">점검할 때</span>
                ) : (
                  tool.days_until_due !== null &&
                  tool.days_until_due <= 14 && <span className="badge">D-{tool.days_until_due}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="cta-bar">
        <button className="btn primary" onClick={() => setEditing("new")}>
          <Icon name="plus" />
          도구 추가
        </button>
      </div>

      {editing && (
        <ToolForm
          initial={editing === "new" ? null : editing}
          onSubmit={save}
          onChecked={editing === "new" ? undefined : mark("checked")}
          onReplaced={editing === "new" ? undefined : mark("replaced")}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: 경로 연결**

`frontend/src/App.tsx`:
- import 추가: `import Tools from "./pages/Tools";`
- 화면 선택 부분을 교체:
```tsx
      {route === "/more" ? <More /> : route === "/tools" ? <Tools /> : <Fridge onLogout={() => setUser(null)} />}
```

- [ ] **Step 5: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류 없음

- [ ] **Step 6: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 주방 도구 목록과 점검·교체 화면"
```

---

## 1c단계 완료 기준

- 백엔드 테스트 실패 0·경고 0, `flask db check` 차이 없음, `npm run build` 성공
- 두 브랜치가 순서대로 main에 `--no-ff` 병합됨
- 폰(`http://<맥 IP>:5180`)에서: 하단 탭(재고·더보기), 폰 뒤로가기로 이전 화면 복귀, 더보기 → 주방 도구, 코팅 프라이팬 추가 시 6개월 자동 선택과 식약처 안내, 구매 7개월 전 프라이팬의 "점검할 때" 배지, 점검했어요/교체했어요, 삭제 버튼 배경·테두리
