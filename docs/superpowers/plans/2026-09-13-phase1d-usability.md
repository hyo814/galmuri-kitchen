# 1d단계(사용성 개선: 빠른 입력·검색·필수품) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주부·1인 가구 사용성 점검에서 사용자가 고른 지금 화면 개선 1~6을 반영한다. 여러 재료 연속 추가, 재고 검색, 필수품 매칭 오탐 차단, 장류·소스 노랑 경고 정리, 필수품 시트 정리, 입력 마찰 줄이기.

**Architecture:** 백엔드는 스키마 변경 없이 이름 매칭 규칙과 상태 판정만 고친다. 짧은 이름은 단어 단위로 매칭하고, 조미료·소스로 분류한 필수품과 이름이 맞는 재료는 위치 기준 "오래됨"을 건너뛴다. 프론트는 `IngredientForm`, `StaplesSheet`, `Fridge`를 고친다.

**Tech Stack:** Flask 3.1 / pytest, React 19 + TypeScript + Vite 8

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 4절 매칭 규칙, 14절 판정·필수품, 23절. 근거 리포트: 사용성 점검 C1~C11, C17, C18, C21, D11.

## Global Constraints

- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다.
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. 실패 0, 경고 0이어야 한다. PostgreSQL 환경에서도 한 번 실행한다(명령은 `docs/deploy.md`).
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정한다.
- 모바일 384px 기준. 터치 영역 44px 이상, 입력 글자 16px 이상. 아이콘은 이모지 대신 `Icon`을 쓴다.
- **삭제 버튼은 `.btn.danger-text`(연빨강 배경과 테두리)로 취소 아래에 둔다. 사용자가 두 번 요청했으므로 위치를 옮기지 않는다.**
- 삭제 확인 문구는 받침에 맞는 조사를 쓴다(`애호박을`, `대파를`).
- 개발 서버는 Vite 5180, Flask 5181이다. 5173은 절대 건드리지 않는다.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음을 붙인다:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치

| 브랜치 | 태스크 |
|---|---|
| `fix/short-name-matching` | 1 (백엔드) |
| `feature/quick-add` | 2 (재료 입력 시트) |
| `feature/inventory-search-staples` | 3 (검색·필수품 시트) |

각 태스크의 리뷰가 통과하면 컨트롤러가 순서대로 main에 `--no-ff`로 병합한다.

---

### Task 1: 짧은 이름 매칭 오탐 차단과 장류·소스 "오래됨" 정리 (백엔드)

**Files:**
- Modify: `backend/app/matching.py`, `backend/app/staples.py`, `backend/app/ingredients.py`
- Modify: `backend/tests/test_matching.py`, `backend/tests/test_staples.py`, `backend/tests/test_ingredients.py`

**Interfaces:**
- Produces:
  - `app.matching.tokens(name) -> list[str]`
  - `names_match(a, b)`: 필수품과 재료를 양방향으로 매칭한다. 짧은 이름 규칙은 아래와 같다.
    - 짧은 쪽이 3글자 이상이면 부분 문자열로 비교한다.
    - 2글자면 긴 쪽의 단어와 같거나, 그 단어가 이 이름으로 끝나야 한다.
    - 1글자면 긴 쪽의 단어와 정확히 같아야 한다.
  - `keyword_in(keyword, name)`: 품목 규칙용이며 한 방향으로만 매칭한다. 키워드가 3글자 이상이면 부분 문자열, 2글자 이하면 단어가 같거나 이 키워드로 끝나야 한다.
  - 필수품 JSON에 `matched_name: str | None`을 추가한다. 재고에서 매칭된 첫 재료 이름이다.
  - 재료 상태 판정: 필수품 중 분류가 `조미료`·`소스`·`양념`·`장류`인 것과 이름이 맞는 **냉장** 재료는 위치 기준 "오래됨"을 건너뛴다(실온처럼 취급). 유통기한 판정과 품목 규칙은 그대로 적용한다.

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b fix/short-name-matching
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_matching.py`:
- import를 `from app.matching import keyword_in, names_match, normalize, tokens`로 바꾼다.
- `test_names_match` parametrize 목록 끝에 추가한다:
```python
        ("파", "양파", False),
        ("대파", "대파 1단", True),
        ("고추", "고추장", False),
        ("고추", "청양고추", True),
        ("무", "단무지", False),
        ("간장", "간장게장", False),
        ("소금", "맛소금", True),
        ("달걀", "유정란 달걀 10구", True),
        ("돼지고기", "돼지고기 앞다리살", True),
```
- 파일 끝에 추가한다:
```python
def test_tokens_split_words_without_parentheses():
    assert tokens("유정란 계란 (특란) 10구") == ["유정란", "계란", "10구"]
    assert tokens("[컬리] 무농약 대파/1단") == ["컬리", "무농약", "대파", "1단"]


@pytest.mark.parametrize(
    "keyword, name, expected",
    [
        ("빵", "식빵", True),
        ("빵", "빵가루", False),
        ("햄", "햄버거", False),
        ("두부", "순두부", True),
        ("주스", "오렌지주스 (1L)", True),
        ("소시지", "비엔나소시지", True),
    ],
)
def test_keyword_in_short_keywords(keyword, name, expected):
    assert keyword_in(keyword, name) is expected
```

`backend/tests/test_staples.py` 끝에 추가한다:
```python
def test_matched_name_and_short_name_false_positive(client, login):
    login()
    client.post("/api/staples", json={"name": "파", "category": "야채"})
    client.post("/api/staples", json={"name": "간장", "category": "조미료"})
    client.post("/api/ingredients", json={"name": "양파", "purchased_on": "2026-09-10"})
    client.post("/api/ingredients", json={"name": "진간장 (500ml)", "purchased_on": "2026-09-10"})
    rows = {s["name"]: s for s in client.get("/api/staples").get_json()}
    assert (rows["파"]["in_stock"], rows["파"]["matched_name"]) == (False, None)
    assert (rows["간장"]["in_stock"], rows["간장"]["matched_name"]) == (True, "진간장 (500ml)")
```

`backend/tests/test_ingredients.py` 끝에 추가한다(파일에 이미 있는 `create` 헬퍼와 `seoul_today`, `timedelta`를 쓴다):
```python
def test_seasoning_staple_skips_fridge_old_badge(client, login):
    login()
    old = (seoul_today() - timedelta(days=30)).isoformat()
    client.post("/api/staples", json={"name": "고추장", "category": "조미료"})
    client.post("/api/staples", json={"name": "굴소스", "category": "소스"})
    client.post("/api/staples", json={"name": "애호박", "category": "야채"})
    statuses = {name: create(client, name=name, purchased_on=old).get_json()["status"] for name in ["고추장", "굴소스", "애호박"]}
    assert statuses == {"고추장": "ok", "굴소스": "ok", "애호박": "old"}
    listed = {i["name"]: i["status"] for i in client.get("/api/ingredients").get_json()}
    assert listed == statuses
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning tests/test_matching.py tests/test_staples.py tests/test_ingredients.py`
Expected: ImportError `tokens`(수집 실패). tokens를 먼저 만들면 새 매칭 케이스, `matched_name`, 조미료 판정이 실패한다.

- [ ] **Step 3: 매칭 구현**

`backend/app/matching.py` 전체를 교체한다:
```python
import re

# ponytail: 이름 매칭은 규칙 기반이다. 오탐·누락이 문제되면 동의어 사전이나 AI 매칭으로 교체 (스펙 4절)
_PARENS = re.compile(r"\([^)]*\)")
_TOKEN_SPLIT = re.compile(r"[\s,/·\[\]*+&]+")


def normalize(name):
    """괄호와 그 안 내용 제거 → 공백 제거 → 소문자."""
    return re.sub(r"\s+", "", _PARENS.sub("", name)).lower()


def tokens(name):
    """괄호 내용을 뺀 뒤 공백·구분 기호로 나눈 소문자 단어들. "유정란 계란 (특란) 10구" → ["유정란", "계란", "10구"]"""
    return [t for t in _TOKEN_SPLIT.split(_PARENS.sub("", name).lower()) if t]


def _short_match(short, name, allow_suffix):
    return any(word == short or (allow_suffix and word.endswith(short)) for word in tokens(name))


def names_match(a, b):
    """필수품↔재료 매칭(양방향). 짧은 이름 오탐을 막는다(사용성 점검 C4).
    - 짧은 쪽이 3글자 이상: 부분 문자열
    - 2글자: 긴 쪽 단어가 같거나 그 이름으로 끝날 때 (대파 1단·청양고추·진간장 O / 고추장·간장게장 X)
    - 1글자: 긴 쪽 단어와 정확히 같을 때 (파→양파 X, 무→단무지 X)
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if len(na) > len(nb):
        a, b, na, nb = b, a, nb, na
    if len(na) >= 3:
        return na in nb
    return _short_match(na, b, allow_suffix=len(na) == 2)


def keyword_in(keyword, name):
    """품목 규칙 키워드가 재료 이름에 들어가는지(한 방향).
    2글자 이하 키워드는 단어가 같거나 그 키워드로 끝날 때만 (식빵·순두부 O / 빵가루·햄버거 X)."""
    keyword = normalize(keyword)
    if not keyword:
        return False
    if len(keyword) >= 3:
        return keyword in normalize(name)
    return _short_match(keyword, name, allow_suffix=True)
```

- [ ] **Step 4: 필수품 JSON에 매칭된 재료 이름 추가**

`backend/app/staples.py`의 `to_json`을 교체한다:
```python
def to_json(staple, names):
    matched = next((n for n in names if names_match(staple.name, n)), None)
    return {
        "id": staple.id,
        "name": staple.name,
        "category": staple.category,
        "in_stock": matched is not None,
        "matched_name": matched,
    }
```

- [ ] **Step 5: 조미료·소스 필수품은 냉장 "오래됨" 건너뛰기**

`backend/app/ingredients.py`:
- import를 수정한다: `from .matching import keyword_in, names_match`, `from .models import Ingredient, ItemRule, Staple, db`
- `SEOUL = ...` 줄 아래에 추가한다:
```python
# 장류·소스는 냉장 보관해도 몇 달씩 쓰므로, 이렇게 분류한 필수품과 이름이 맞으면 위치 기준 '오래됨'을 건너뛴다 (사용성 점검 C3)
SEASONING_CATEGORIES = ["조미료", "소스", "양념", "장류"]
```
- `user_rules` 아래에 추가한다:
```python
def seasoning_names(user_id):
    rows = db.session.query(Staple.name).filter(Staple.user_id == user_id, Staple.category.in_(SEASONING_CATEGORIES))
    return [name for (name,) in rows.all()]
```
- `status_of`와 `to_json`을 교체한다(to_json 본문은 `"status"` 줄만 바뀐다):
```python
def status_of(item, today, rules, seasonings=()):
    kind = item.location.kind
    if kind == "fridge" and any(names_match(s, item.name) for s in seasonings):
        kind = "room"  # 위치 기준 '오래됨'만 건너뛴다. 유통기한·품목 규칙 판정은 그대로
    return ingredient_status(item.purchased_on, item.expires_on, today, kind, matching_rule(item.name, rules))


def to_json(item, today, rules, seasonings=()):
    return {
        "id": item.id,
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "purchased_on": item.purchased_on.isoformat(),
        "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        "status": status_of(item, today, rules, seasonings),
        "location_id": item.location_id,
        "location_name": item.location.name,
        "location_kind": item.location.kind,
        "days_left": (item.expires_on - today).days if item.expires_on else None,
        "days_since_purchase": (today - item.purchased_on).days,
    }
```
- `list_ingredients`, `create_ingredient`, `update_ingredient`가 `seasonings`를 넘기게 한다:
```python
@bp.get("")
@login_required
def list_ingredients():
    today = seoul_today()
    rules = user_rules(g.user.id)
    seasonings = seasoning_names(g.user.id)
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=g.user.id).all()
    items.sort(
        key=lambda i: (
            STATUS_RANK[status_of(i, today, rules, seasonings)],
            i.expires_on or date.max,
            i.purchased_on,
            i.id,
        )
    )
    return jsonify([to_json(i, today, rules, seasonings) for i in items])
```
  `create_ingredient`의 반환은 `jsonify(to_json(item, seoul_today(), user_rules(g.user.id), seasoning_names(g.user.id))), 201`로, `update_ingredient`의 반환은 `jsonify(to_json(item, seoul_today(), user_rules(g.user.id), seasoning_names(g.user.id)))`로 바꾼다.

- [ ] **Step 6: 통과 확인 (SQLite와 PostgreSQL)**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning && TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate .venv/bin/pytest -q -W error::DeprecationWarning
```
Expected: 두 실행 모두 실패 0, 경고 0. 기존 `test_matching_rule_picks_shortest_danger`("소시지빵"은 빵 규칙 (21, 24))도 통과해야 한다.

- [ ] **Step 7: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "fix: 짧은 이름 매칭 오탐 차단, 조미료·소스 필수품은 냉장 오래됨 제외"
```

---

### Task 2: 재료 입력 시트 — 연속 추가·단위 칩·유통기한 빠른 입력·수량 −/+

**Files:**
- Modify: `frontend/src/components/IngredientForm.tsx` (전체 교체), `frontend/src/pages/Fridge.tsx`, `frontend/src/format.ts`, `frontend/src/components/Icon.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Produces:
  - `withJosa(word: string, withBatchim: string, withoutBatchim: string): string` (`format.ts`). 예: `withJosa("애호박", "을", "를")` → `"애호박을"`. 마지막 글자가 한글이 아니면 `"을(를)"`을 붙인다.
  - `IngredientForm` props가 바뀐다.
    - `onSubmit: (input: IngredientInput, keepOpen: boolean) => Promise<void>`
    - `initialName?: string`: 새 재료를 입력할 때 이름을 미리 채운다. Task 3에서 필수품 → 재고 추가에 쓴다.
  - Fridge에 `openNew(name?: string)`를 추가한다. 새 재료 시트를 열고, 열려 있던 설정 시트는 닫는다. Task 3이 사용한다.
  - Icon 이름을 추가한다: `minus`, `search`(search는 Task 3에서 쓴다).

(브랜치: `fix/short-name-matching`이 main에 병합된 뒤 시작한다.)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/quick-add
```

- [ ] **Step 1: 조사 헬퍼·아이콘·스타일**

`frontend/src/format.ts` 끝에 추가한다:
```ts
/** 받침에 맞는 조사를 붙인다. withJosa("애호박", "을", "를") → "애호박을". 한글이 아니면 "을(를)" */
export function withJosa(word: string, withBatchim: string, withoutBatchim: string): string {
  const code = word.trim().charCodeAt(word.trim().length - 1) - 0xac00;
  if (Number.isNaN(code) || code < 0 || code > 11171) return `${word}${withBatchim}(${withoutBatchim})`;
  return word + (code % 28 ? withBatchim : withoutBatchim);
}

/** "2026-09-13" + 3 → "2026-09-16" (기기 로컬 날짜 기준) */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString("sv-SE");
}
```

`frontend/src/components/Icon.tsx`의 `PATHS`에 추가한다:
```tsx
  minus: <path d="M5 12h14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
```

`frontend/src/styles.css` 끝에 추가한다:
```css
.stepper {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 56px;
  gap: 8px;
}

.stepper .icon-btn {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: var(--field);
  color: var(--text);
}

.stepper .input {
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.notice {
  margin: 0;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--accent-tint);
  color: var(--accent-strong);
  font-size: 15px;
  line-height: 22px;
}

.btn.used-up {
  background: var(--danger);
  color: var(--bg);
}
```

- [ ] **Step 2: 재료 입력 시트**

`frontend/src/components/IngredientForm.tsx`를 전체 교체한다:
```tsx
import { useRef, useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput, type StorageLocation } from "../api";
import { addDays, withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

interface Props {
  initial: Ingredient | null;
  initialName?: string;
  locations: StorageLocation[];
  defaultLocationId: number;
  onSubmit: (input: IngredientInput, keepOpen: boolean) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const UNITS = ["개", "g", "ml", "팩", "봉", "병", "모", "단"];
const COUNT_UNITS = new Set(["개", "팩", "봉", "병", "모", "단"]);
const EXPIRY_PRESETS = [1, 3, 7];

/** −/+ 한 번에 바뀌는 양: 개수 단위는 1(1개 이하에서는 0.5), g·ml은 100, 그 외 0.5 */
function stepFor(unit: string, quantity: number) {
  if (COUNT_UNITS.has(unit)) return quantity <= 1 ? 0.5 : 1;
  if (unit === "g" || unit === "ml") return 100;
  return 0.5;
}

export default function IngredientForm({
  initial,
  initialName,
  locations,
  defaultLocationId,
  onSubmit,
  onDelete,
  onClose,
}: Props) {
  const [name, setName] = useState(initial?.name ?? initialName ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? "개");
  const [customUnit, setCustomUnit] = useState(!!initial && !UNITS.includes(initial.unit));
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [locationId, setLocationId] = useState(initial?.location_id ?? defaultLocationId);
  const [lastAdded, setLastAdded] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAsyncAction();

  const qty = Number(quantity) || 0;
  const usedUp = !!initial && !!onDelete && qty === 0;

  const input = (): IngredientInput => ({
    name: name.trim(),
    quantity: qty,
    unit: unit.trim() || "개",
    purchased_on: purchasedOn,
    expires_on: expiresOn || null,
    location_id: locationId,
  });

  const changeQuantity = (direction: 1 | -1) => {
    const next = Math.max(0, Math.round((qty + direction * stepFor(unit, qty)) * 100) / 100);
    setQuantity(String(next));
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (usedUp && onDelete) run(onDelete);
    else run(() => onSubmit(input(), false));
  };

  // 장 본 뒤 여러 개를 이어서 넣는 흐름: 이름·수량·유통기한만 비우고 단위·위치·구입일은 유지 (사용성 점검 C1)
  const saveAndContinue = async () => {
    if (nameRef.current?.form && !nameRef.current.form.reportValidity()) return;
    const added = name.trim();
    if (await run(() => onSubmit(input(), true))) {
      setName("");
      setQuantity("1");
      setExpiresOn("");
      setLastAdded(added);
      nameRef.current?.focus();
    }
  };

  return (
    <Sheet title={initial ? "재료 수정" : "재료 추가"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        {lastAdded && (
          <p className="notice" role="status">
            {withJosa(lastAdded, "을", "를")} 추가했어요. 다음 재료를 입력하세요.
          </p>
        )}

        <label className="field">
          <span className="field-label">이름</span>
          <input
            ref={nameRef}
            className="input"
            id="ingredient-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={50}
            placeholder="예: 대파"
            autoFocus={!initial}
          />
        </label>

        <div className="field">
          <span className="field-label" id="ingredient-quantity-label">
            수량
          </span>
          <div className="stepper">
            <button type="button" className="icon-btn" aria-label="수량 줄이기" onClick={() => changeQuantity(-1)}>
              <Icon name="minus" />
            </button>
            <input
              className="input"
              id="ingredient-quantity"
              aria-labelledby="ingredient-quantity-label"
              type="number"
              inputMode="decimal"
              min={initial ? "0" : "0.01"}
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
            <button type="button" className="icon-btn" aria-label="수량 늘리기" onClick={() => changeQuantity(1)}>
              <Icon name="plus" />
            </button>
          </div>
        </div>

        <div className="field" role="group" aria-label="단위">
          <span className="field-label">단위</span>
          <div className="choices">
            {UNITS.map((u) => (
              <button
                key={u}
                type="button"
                className="choice"
                aria-pressed={!customUnit && unit === u}
                onClick={() => {
                  setCustomUnit(false);
                  setUnit(u);
                }}
              >
                {u}
              </button>
            ))}
            <button
              type="button"
              className="choice"
              aria-pressed={customUnit}
              onClick={() => {
                setCustomUnit(true);
                if (UNITS.includes(unit)) setUnit("");
              }}
            >
              직접 입력
            </button>
          </div>
          {customUnit && (
            <input
              className="input"
              id="ingredient-unit"
              aria-label="단위 직접 입력"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              maxLength={10}
              placeholder="예: 줄, 판, kg"
            />
          )}
        </div>

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
        <div className="choices" role="group" aria-label="유통기한 빠르게 넣기">
          {EXPIRY_PRESETS.map((days) => (
            <button
              key={days}
              type="button"
              className="choice"
              aria-pressed={expiresOn === addDays(purchasedOn, days)}
              onClick={() => setExpiresOn(addDays(purchasedOn, days))}
            >
              구입일 +{days}일
            </button>
          ))}
          {expiresOn && (
            <button type="button" className="choice" onClick={() => setExpiresOn("")}>
              유통기한 지우기
            </button>
          )}
        </div>

        {name.includes("우유") && !expiresOn && (
          <p className="hint">우유는 포장에 적힌 소비기한을 입력하면 가장 정확해요.</p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {!initial && (
          <button type="button" className="btn secondary" disabled={busy} onClick={saveAndContinue}>
            <Icon name="plus" />
            저장하고 계속 추가
          </button>
        )}
        <div className="actions">
          <button type="button" className="btn secondary" onClick={onClose}>
            {lastAdded ? "닫기" : "취소"}
          </button>
          <button className={`btn ${usedUp ? "used-up" : "primary"}`} disabled={busy}>
            {busy ? "저장 중…" : usedUp ? "다 썼어요 (삭제)" : "저장"}
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

- [ ] **Step 3: 냉장고(재고) 화면 연결**

`frontend/src/pages/Fridge.tsx`:
- import에 `withJosa`를 추가한다: `import { formatDate, formatQuantity, withJosa } from "../format";`
- `editing` state 아래에 추가한다: `const [prefillName, setPrefillName] = useState("");`
- `save`와 `remove`를 교체하고 `openNew`를 추가한다:
```tsx
  // 저장·삭제 오류는 던져서 시트 안에 표시한다. keepOpen이면 시트를 닫지 않는다(연속 추가).
  const save = async (input: IngredientInput, keepOpen: boolean) => {
    if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
    else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
    if (!keepOpen) setEditing(null);
    await load();
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${withJosa(editing.name, "을", "를")} 삭제할까요?`)) return;
    await api(`/api/ingredients/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const openNew = (name = "") => {
    setPanel(null);
    setPrefillName(name);
    setEditing("new");
  };
```
- `재료 추가` CTA 버튼의 `onClick={() => setEditing("new")}`를 `onClick={() => openNew()}`로 바꾼다.
- `<IngredientForm ... />`에 `initialName={editing === "new" ? prefillName : undefined}`를 추가한다.

- [ ] **Step 4: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류가 없어야 한다.

- [ ] **Step 5: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 재료 연속 추가, 단위 칩, 유통기한 빠른 입력, 수량 −/+와 다 썼어요"
```

---

### Task 3: 재고 검색과 필수품 시트 정리

**Files:**
- Modify: `frontend/src/pages/Fridge.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/components/LocationsSheet.tsx`(문구 한 줄)
- Replace: `frontend/src/components/StaplesSheet.tsx`

**Interfaces:**
- Consumes: Task 1 필수품 JSON `matched_name`, Task 2 `openNew(name)`, `withJosa`, Icon `search`
- Produces:
  - `Staple.matched_name: string | null`
  - `StaplesSheet({ staples, initialMissingOnly?, onChanged, onAddIngredient, onClose })`

(브랜치: `feature/quick-add`가 main에 병합된 뒤 시작한다.)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/inventory-search-staples
```

- [ ] **Step 1: 타입과 스타일**

`frontend/src/api.ts`의 `Staple`에 `matched_name: string | null;`을 추가한다.

`frontend/src/styles.css` 끝에 다음을 추가한다:
```css
.search {
  position: relative;
  margin: 16px 20px 0;
}

.search > svg {
  position: absolute;
  top: 50%;
  left: 16px;
  color: var(--text-3);
  pointer-events: none;
  transform: translateY(-50%);
}

.search .input {
  padding-left: 46px;
  background: var(--surface);
}

.row-press {
  width: 100%;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.row-end {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}

.add-hint {
  color: var(--accent-strong);
  font-size: 14px;
  font-weight: 600;
}

.stock-ok {
  min-width: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 2: 필수품 시트**

`frontend/src/components/StaplesSheet.tsx`를 통째로 다음 내용으로 바꾼다:
```tsx
import { useRef, useState, type FormEvent } from "react";
import { api, type Staple } from "../api";
import { withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import Icon from "./Icon";
import Sheet from "./Sheet";

const CATEGORIES = ["조미료", "야채", "기타"];

interface Props {
  staples: Staple[];
  initialMissingOnly?: boolean;
  onChanged: () => Promise<unknown>;
  onAddIngredient: (name: string) => void;
  onClose: () => void;
}

export default function StaplesSheet({ staples, initialMissingOnly = false, onChanged, onAddIngredient, onClose }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [missingOnly, setMissingOnly] = useState(initialMissingOnly);
  const [name, setName] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);
  const nameRef = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAsyncAction();

  // 사용자가 직접 만든 분류(소스, 육류 등)도 칩과 그룹으로 보여 준다 (사용성 점검 C18)
  const categories = [...CATEGORIES, ...new Set(staples.map((s) => s.category).filter((c) => !CATEGORIES.includes(c)))];
  const missingCount = staples.filter((s) => !s.in_stock).length;
  const shown = missingOnly ? staples.filter((s) => !s.in_stock) : staples;
  const groups = categories
    .map((c) => ({ category: c, items: shown.filter((s) => s.category === c) }))
    .filter((g) => g.items.length > 0);

  // 추가 폼을 위로 올리고, 추가 후 입력칸에 포커스를 되돌린다 (사용성 점검 C5)
  const add = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(async () => {
      await api("/api/staples", { method: "POST", body: { name, category } });
      await onChanged();
    });
    if (ok) {
      setName("");
      nameRef.current?.focus();
    }
  };

  const remove = (staple: Staple) => {
    if (!confirm(`${withJosa(staple.name, "을", "를")} 필수품에서 뺄까요?`)) return;
    run(async () => {
      await api(`/api/staples/${staple.id}`, { method: "DELETE" });
      await onChanged();
    });
  };

  return (
    <Sheet
      title="필수품"
      description="항상 있어야 하는 재료예요. 떨어지면 재고 화면에서 알려드려요."
      action={
        staples.length > 0 && (
          <button className="text-btn strong" onClick={() => setEditMode(!editMode)}>
            {editMode ? "완료" : "편집"}
          </button>
        )
      }
      onClose={onClose}
    >
      <form className="form compact" onSubmit={add}>
        <div className="add-row">
          <input
            ref={nameRef}
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
          {categories.map((c) => (
            <button key={c} type="button" className="choice" aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c}
            </button>
          ))}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>

      {staples.length > 0 && (
        <div className="choices divider-top" role="group" aria-label="보기">
          <button type="button" className="choice" aria-pressed={!missingOnly} onClick={() => setMissingOnly(false)}>
            전체 {staples.length}
          </button>
          <button type="button" className="choice" aria-pressed={missingOnly} onClick={() => setMissingOnly(true)}>
            떨어진 것만 {missingCount}
          </button>
        </div>
      )}

      {groups.length === 0 ? (
        <p className="hint">{staples.length === 0 ? "아직 등록한 필수품이 없어요. 위에서 추가해 보세요." : "떨어진 필수품이 없어요."}</p>
      ) : (
        <div className="groups">
          {groups.map((group) => (
            <section key={group.category} className="group" aria-label={group.category}>
              <h3 className="section-label">{group.category}</h3>
              <ul className="plain-list">
                {group.items.map((staple) => (
                  <li key={staple.id}>
                    {editMode ? (
                      <div className="plain-row">
                        <span className="staple-name">{staple.name}</span>
                        <button className="btn danger-text inline" disabled={busy} onClick={() => remove(staple)}>
                          삭제
                        </button>
                      </div>
                    ) : staple.in_stock ? (
                      <div className="plain-row">
                        <span className="staple-name">{staple.name}</span>
                        <span className="stock-ok">
                          <Icon name="check" size={16} />
                          있음
                          {staple.matched_name && staple.matched_name !== staple.name && ` · ${staple.matched_name}`}
                        </span>
                      </div>
                    ) : (
                      // 떨어진 필수품을 누르면 이름이 채워진 재료 추가가 열린다 (사용성 점검 C6)
                      <button
                        className="plain-row row-press"
                        aria-label={`${staple.name} 떨어짐, 재고에 추가`}
                        onClick={() => onAddIngredient(staple.name)}
                      >
                        <span className="staple-name">{staple.name}</span>
                        <span className="row-end">
                          <span className="badge danger">떨어짐</span>
                          <span className="add-hint">추가</span>
                        </span>
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Sheet>
  );
}
```

- [ ] **Step 3: 재고 검색과 필수품 시트 연결**

`frontend/src/pages/Fridge.tsx`:
- state 두 개를 추가한다: `const [query, setQuery] = useState("");`, `const [staplesMissingOnly, setStaplesMissingOnly] = useState(false);`
- `visible` 계산을 교체한다:
```tsx
  const q = query.replace(/\s+/g, "").toLowerCase();
  const visible =
    items?.filter(
      (i) =>
        (activeFilter === "all" || i.location_id === activeFilter) &&
        (!q || i.name.replace(/\s+/g, "").toLowerCase().includes(q)),
    ) ?? null;
```
- 배너 버튼 `onClick`을 `onClick={() => { setStaplesMissingOnly(true); setPanel("staples"); }}`로 바꾼다.
- 위치 칩 줄(`{locations.length > 0 && (<div className="chip-row">`) 바로 위에 검색 입력을 추가한다. 재료가 10개 이상이거나 검색어가 있을 때만 보인다:
```tsx
      {items && (items.length >= 10 || query) && (
        <div className="search">
          <Icon name="search" />
          <input
            className="input"
            id="inventory-search"
            type="search"
            aria-label="재고 검색"
            placeholder="재고에서 찾기"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            enterKeyHint="search"
          />
        </div>
      )}
```
- 빈 목록 블록(`visible.length === 0`)을 교체한다. 검색 결과가 없을 때 그 이름으로 바로 추가할 수 있게 한다:
```tsx
        <div className="empty">
          {query ? (
            <>
              <p>‘{query.trim()}’ 재료가 없어요.</p>
              <button className="btn secondary inline" onClick={() => openNew(query.trim())}>
                {withJosa(query.trim(), "을", "를")} 재고에 추가
              </button>
            </>
          ) : (
            <>
              <p>{items && items.length > 0 ? "이 위치에는 재료가 없어요." : "재고가 비어 있어요."}</p>
              <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
            </>
          )}
        </div>
```
- 필수품 시트 렌더를 교체한다:
```tsx
      {panel === "staples" && (
        <StaplesSheet
          staples={staples}
          initialMissingOnly={staplesMissingOnly}
          onChanged={load}
          onAddIngredient={openNew}
          onClose={() => {
            setPanel(null);
            setStaplesMissingOnly(false);
          }}
        />
      )}
```

`frontend/src/components/LocationsSheet.tsx`의 힌트 문구 `냉장은 구입 7일, 냉동은 60일이 지나면 ‘오래됨’으로 표시해요. 실온은 표시하지 않아요.`를 `냉장은 구입 7일, 냉동은 60일이 지나면 노랑 ‘구입 N일째’로 표시해요. 실온은 표시하지 않아요.`로 바꾼다.

- [ ] **Step 4: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: 오류 없이 끝난다.

- [ ] **Step 5: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 재고 검색, 필수품 시트 정리(추가 폼 위로·떨어진 것만·눌러서 재고 추가·매칭 재료 표시)"
```

---

## 1d단계 완료 기준

- 백엔드: SQLite와 PostgreSQL 테스트 모두 실패 0, 경고 0.
- 프론트엔드: `npm run build` 성공.
- 폰에서 확인할 것:
  - 재료 추가: `저장하고 계속 추가`로 연속 입력되고, 입력한 단위·위치·구입일이 유지된다.
  - 입력 편의: 단위 칩, `구입일 +3일`, 수량 −/+가 동작하고, 수정 화면에서 수량을 0으로 두면 버튼이 `다 썼어요 (삭제)`로 바뀐다.
  - 재고 검색이 된다.
  - 필수품 시트:
    - `떨어진 것만` 보기가 된다.
    - 떨어진 항목을 누르면 재고 추가가 열린다.
    - 있는 항목에는 `있음 · 진간장 (500ml)`처럼 연결된 재고 이름이 표시된다.
    - 필수품 `파`는 재고의 양파를 `있음`으로 잡지 않는다.
  - 조미료·소스 필수품은 냉장 보관 30일이 지나도 노랑 배지가 뜨지 않는다.
