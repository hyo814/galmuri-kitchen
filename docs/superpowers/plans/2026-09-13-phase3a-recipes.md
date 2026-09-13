# 3a단계(레시피 기본: 내 레시피 · 공공 레시피 · 추천) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 내 레시피를 쓰고 고치고 지울 수 있고, 식약처 공공 레시피(키가 없으면 직접 쓴 예시 레시피 12개)를 받아 둔다. 레시피 탭의 `추천`은 지금 재고와 겹치는 재료가 많은 요리를 일치율 순으로 보여 주고, 빨리 먹어야 할 재료를 쓰는 요리를 앞으로 올린다. 상세 화면은 재료마다 재고에 있는지 보여 주고 인분을 바꾸면 양을 화면에서만 다시 계산한다.

**Architecture:** 백엔드는 `recipe_parse.py`(식약처 원문 → 재료·단계, 순수 함수), `recipes.py`(내 레시피 CRUD, 공공 레시피 상세·저장, 추천 API), `public_recipes.py`(동기화·예시 레시피 CLI)로 나눈다. 매칭은 기존 `names_match` 한 곳을 그대로 쓰고, 공공 레시피는 동기화할 때 `ingredient_keys`(매칭용 이름)를 미리 만들어 둔다. 추천은 요청마다 재고를 한 번 읽고 서로 다른 재료 키마다 한 번만 비교한다. 동기화 테스트는 `requests.get`을 가짜로 바꿔 네트워크를 쓰지 않는다. 프론트는 해시 경로를 작은 경로표(`/recipes/mine/:id` 같은 파라미터)로 바꾸고, 화면 데이터는 `useResource`(모듈 Map 캐시 + 다시 받기)로 불러와 상세에서 돌아왔을 때 목록과 스크롤 위치가 그대로 남게 한다.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, requests 2.34.2, pytest 9.1.1 / React 19 + TypeScript + Vite 8

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md` 2절(3단계), 4절(`recipes`, `public_recipes`, 매칭·일치율 규칙), 5절(API, CLI), 6절-3~5(추천·상세·레시피 탭), 10절(식약처 HTTP는 가짜), 23절 D1(인분, 이 절이 우선). 17절(링크 가져오기)·22절(양념 비율)은 3b·3c에서 한다. 결정 사항: 컨트롤러 결정 파일(2026-09-13, 3a). 디자인: `docs/design/recipes-3a/*.dc.html`(사용자 승인 2026-09-13, 작은 카드안).

## Global Constraints

- 경로에 공백이 있다: `/Users/limhyojin/PycharmProjects/ recipe-ai`. 항상 따옴표로 감싼다.
- 테스트 명령: `backend/.venv/bin/pytest -q -W error::DeprecationWarning`. SQLite와 PostgreSQL(`TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate`) 둘 다 실패 0, 경고 0이어야 한다.
- 프론트 태스크는 `cd frontend && npm run build`(`tsc --noEmit` + `vite build`)가 오류 없이 끝나야 한다.
- 오류 형식은 `{"error": "<한국어>"}`. 사용자 소유 데이터는 `g.user.id`로 한정하고 남의 것은 404.
- 테스트는 절대 네트워크(식약처 API)를 부르지 않는다. `requests.get`을 `monkeypatch`로 바꾼다. 그래서 `public_recipes.py`는 `requests.get(...)`처럼 모듈 속성으로 부른다.
- `backend/.env`는 읽거나 커밋하지 않는다(키는 거기에만 있다). `FOODSAFETY_API_KEY`는 로그·오류 문구에 찍지 않는다(요청 URL에 들어간다).
- 개발 서버는 Vite 5180, Flask 5181이다. 5173은 절대 건드리지 않는다. 개발 DB(`backend/instance/dev.sqlite3`)는 지우거나 초기화하지 않는다(마이그레이션·예시 레시피 넣기만).
- 모바일 384px 기준. 터치 영역 44px 이상, 입력 글자 16px 이상. 아이콘은 이모지 대신 `Icon`을 쓴다. 라이트·다크 모두 확인한다.
- **삭제 버튼은 `.btn.danger-text`(연빨강 배경 + 테두리)로 다른 버튼 아래에 둔다(사용자 요청). 레시피 상세의 `이 레시피 삭제`도 `수정` 아래에 같은 모양으로 둔다.**
- 화면 문구는 보조 용언을 붙여 쓴다(`보여줘요`, `입력해주세요`, `추가해보세요`). 개발 용어(API, DB, 동기화)는 화면에 쓰지 않는다.
- 커밋 메시지 끝에 빈 줄 하나를 두고 다음 한 줄만 붙인다(`Co-Authored-By` 줄은 넣지 않는다):
  ```
  Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH
  ```

## 브랜치

| 브랜치 | 태스크 | 시작 시점 |
|---|---|---|
| `feature/recipes-backend` | 1 (모델·마이그레이션, 원문 파서, 내 레시피 CRUD, 공공 레시피 상세·저장, 미래 구입일 거부) | main에서 바로 |
| `feature/public-recipes-sync` | 2 (식약처 동기화 CLI, 예시 레시피, 추천 API) | 태스크 1이 main에 병합된 뒤 |
| `feature/recipes-routing` | 3 (경로표·파라미터, 탭 표시, `useResource`, 구입일 max, 재고 요약 문구) | 태스크 2가 main에 병합된 뒤 |
| `feature/recipes-ui` | 4 (레시피 탭·상세·폼 화면) | 태스크 3이 main에 병합된 뒤 |

각 태스크의 리뷰(백엔드: 코드·보안·테스트, 화면: 코드·UX/접근성)가 통과하면 컨트롤러가 순서대로 main에 `--no-ff`로 병합한다.

## 파일 구조

```
backend/
  app/models.py                                     (수정, T1) PublicRecipe, Recipe
  migrations/versions/a6b6c6d6e6f6_recipes.py       (신규, T1)
  app/recipe_parse.py                               (신규, T1) parse_ingredients, split_steps, parse_servings, ingredient_key
  app/recipes.py                                    (신규, T1 / 수정, T2) 내 레시피 CRUD, 공공 상세·저장 / 추천
  app/validation.py                                 (수정, T1) iso_date (20260101 같은 모양 거부)
  app/ingredients.py, app/tools.py, app/scan.py     (수정, T1) iso_date 사용, 미래 구입일 거부(ingredients)
  app/__init__.py                                   (수정, T1·T2) 블루프린트, FOODSAFETY_API_KEY
  app/public_recipes.py                             (신규, T2) sync-public-recipes, seed-sample-recipes
  app/data/sample_recipes.json                      (신규, T2) 직접 쓴 예시 레시피 12개
  tests/test_recipe_parse.py, tests/test_recipes.py (신규, T1)
  tests/test_ingredients.py, test_tools.py, test_migrations.py (수정, T1)
  tests/test_public_recipes.py, tests/test_recommendations.py (신규, T2)
  tests/conftest.py                                 (수정, T2)
docs/superpowers/specs/2026-09-13-recipe-ai-design.md (수정, T1·T2), docs/deploy.md (수정, T2)
frontend/src/
  useHashRoute.ts                                   (수정, T3) ROUTES, matchRoute, navigate, goBack
  useResource.ts                                    (신규, T3) useResource, forgetResources
  App.tsx                                           (수정, T3·T4) 경로 → 화면 표, 스크롤 복원
  components/TabBar.tsx, pages/Tools.tsx            (수정, T3) path prop·레시피 하위 경로 / useResource·goBack
  pages/More.tsx, components/IngredientForm.tsx, pages/Fridge.tsx (수정, T3)
  api.ts, format.ts, components/Icon.tsx            (수정, T4) 레시피 타입, scaleAmount·imageSrc, 아이콘 3개
  pages/Recipes.tsx, pages/RecipeDetail.tsx, pages/RecipeForm.tsx (신규, T4)
  pages/ComingSoon.tsx, styles.css                  (수정, T4)
docs/site/product.html, docs/site/portfolio.html    (수정, T3) 재고 요약 문구
```

---

### Task 1: 레시피 백엔드 (모델·마이그레이션, 원문 파서, 내 레시피 CRUD, 공공 레시피 상세·저장, 미래 구입일 거부)

**Files:**
- Create: `backend/app/recipe_parse.py`, `backend/app/recipes.py`, `backend/migrations/versions/a6b6c6d6e6f6_recipes.py`, `backend/tests/test_recipe_parse.py`, `backend/tests/test_recipes.py`
- Modify: `backend/app/models.py`, `backend/app/__init__.py`, `backend/app/validation.py`, `backend/app/ingredients.py`, `backend/app/tools.py`, `backend/app/scan.py`, `backend/tests/test_ingredients.py`, `backend/tests/test_tools.py`, `backend/tests/test_migrations.py`
- Modify (문서): `docs/superpowers/specs/2026-09-13-recipe-ai-design.md`

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`(auth), `seoul_today`, `status_of`, `user_rules`, `seasoning_names`(ingredients), `names_match`, `normalize`, `tokens`(matching), `text`, `integer`, `commit_or_duplicate`(validation), 픽스처 `client`, `raw_client`, `login`, `app`
- Produces:
  - `app.models.PublicRecipe(id, rcp_seq UNIQUE, title≤120, category≤30, method≤30, kcal, servings=2, ingredients_text, ingredients JSON, ingredient_keys JSON, steps JSON, image_url≤500, is_sample=False, updated_at)`
  - `app.models.Recipe(id, user_id CASCADE, title≤60, servings=2, ingredients JSON, steps JSON, source≤20="mine", source_url≤500, public_recipe_id SET NULL, image_url≤500, created_at, updated_at)`, UNIQUE(user_id, public_recipe_id)
  - Alembic revision `a6b6c6d6e6f6`(down `a5b5c5d5e5f5`)
  - `app.recipe_parse`: `MAX_INGREDIENTS`(50), `parse_ingredients(text, title="") -> [{name, amount}]`, `split_steps(row) -> [str]`, `parse_servings(text) -> int`, `ingredient_key(name) -> str`
  - `app.validation.iso_date(value) -> date | None` (YYYY-MM-DD 모양만)
  - `app.recipes`: `MAX_RECIPES_PER_USER`(1000), `ALWAYS_HAVE`(`{"물"}`), `inventory(user_id) -> [(name, is_urgent)]`(빨리 먹어야 할 재료가 앞), `match_key(key, stock) -> (matched_name | None, have)`, `annotate(ingredients, keys, stock)`, `recipe_json`, `public_json`, `list_json`, `parse_recipe(data)`
  - API (모두 로그인 필요)
    - `GET /api/recipes` → `[{id, title, servings, source, image_url, ingredient_count, updated_at}]` 최신 순
    - `POST /api/recipes` `{title, servings?, ingredients:[{name, amount?}], steps?, source_url?}` → 201 상세. `source`는 받지 않고 `mine`
    - `GET/PUT/DELETE /api/recipes/<id>` → 상세 / 상세(PUT은 전체 교체, `source_url`은 보냈을 때만 바꿈) / 204. 남의 것 404
    - 상세 모양 `{kind:"mine", id, title, servings, category:null, ingredients:[{name, amount, have, matched_name}], steps, source, source_url, public_recipe_id, image_url}`
    - `GET /api/public-recipes/<id>` → `{kind:"public", id, title, servings, category, method, kcal, ingredients:[{name, amount, have, matched_name}], steps, image_url, is_sample}`
    - `POST /api/public-recipes/<id>/save` → 201 내 레시피 상세(source `public`), 이미 저장했으면 200 같은 레시피
    - 검증 문구: `제목은 1~60자로 입력해주세요.` / `인분은 1~20 사이 정수로 입력해주세요.` / `재료를 1~50개 입력해주세요.` / `N번째 재료 이름은 1~50자로 입력해주세요.` / `N번째 재료 양은 30자까지 입력해주세요.` / `만드는 법을 다시 확인해주세요.` / `만드는 법은 30단계까지 입력할 수 있어요.` / `N번째 단계는 500자까지 입력해주세요.` / `링크는 http:// 또는 https://로 시작하는 주소로 입력해주세요.` / `레시피는 1000개까지 저장할 수 있어요.`
  - 재료 API: `purchased_on`이 서울 오늘보다 뒤면 400 `구입일은 오늘보다 뒤일 수 없어요.`(단건·일괄·수정 모두 `parse_fields` 한 곳). 날짜는 `YYYY-MM-DD` 모양만 받는다(`20260101` 거부, 재료·도구·스캔 공통).

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/recipes-backend
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_recipe_parse.py`(새 파일). 입력은 식약처 COOKRCP01 `RCP_PARTS_DTLS`·`MANUAL01..20`의 실제 모양(첫 줄 요리 이름, `●주재료 :`, `[1인분]`, `·양념장 :`, 단계 끝 `a`)을 흉내 냈다:
```python
import pytest

from app.recipe_parse import MAX_INGREDIENTS, ingredient_key, parse_ingredients, parse_servings, split_steps


def pairs(text, title=""):
    return [(i["name"], i["amount"]) for i in parse_ingredients(text, title)]


def test_parses_dish_title_line_and_section_header():
    # 식약처 COOKRCP01 RCP_PARTS_DTLS 모양: 첫 줄은 요리 이름, 중간에 "고명" 같은 제목 줄
    text = "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개)\n고명\n시금치 10g(3줄기)"
    assert pairs(text, "새우 두부 계란찜") == [
        ("연두부", "75g(3/4모)"),
        ("칵테일새우", "20g(5마리)"),
        ("달걀", "30g(1/2개)"),
        ("시금치", "10g(3줄기)"),
    ]


def test_strips_bullets_labels_and_serving_brackets():
    text = (
        "[1인분]조선부추 50g, 날콩가루 7g(1⅓작은술)\n"
        "·양념장 : 저염간장 3g(2/3작은술), 다진 마늘 2g(1/2쪽), 참깨 약간\n"
        "●주재료 :\n두부 1/2모(150g)\n[양념장]\n고춧가루 1작은술(5g)"
    )
    assert pairs(text) == [
        ("조선부추", "50g"),
        ("날콩가루", "7g(1⅓작은술)"),
        ("저염간장", "3g(2/3작은술)"),
        ("다진 마늘", "2g(1/2쪽)"),
        ("참깨", "약간"),
        ("두부", "1/2모(150g)"),
        ("고춧가루", "1작은술(5g)"),
    ]


def test_dish_name_suffix_line_is_dropped():
    assert pairs("북엇국\n북어채 25g(15개), 물 300ml(1½컵)", "사과 새우 북엇국") == [
        ("북어채", "25g(15개)"),
        ("물", "300ml(1½컵)"),
    ]


@pytest.mark.parametrize(
    "item, expected",
    [
        ("돼지고기 200g", ("돼지고기", "200g")),
        ("소금 약간", ("소금", "약간")),
        ("다진 마늘 1작은술(5g)", ("다진 마늘", "1작은술(5g)")),
        ("두부 1/2모(150g)", ("두부", "1/2모(150g)")),
        ("7분도쌀 100g", ("7분도쌀", "100g")),
        ("오메가3 달걀 2개", ("오메가3 달걀", "2개")),
        ("대파1대", ("대파", "1대")),
        ("½큰술 참기름", ("½큰술 참기름", "")),  # 이름이 없으면 확신이 없으니 통째로 이름
        ("후추", ("후추", "")),
        ("소금(1g, 약간)", ("소금(1g, 약간)", "")),  # 괄호 안 쉼표로 나누지 않는다
    ],
)
def test_splits_trailing_amount(item, expected):
    assert pairs(item) == [expected]


def test_drops_empty_dedupes_and_caps():
    assert pairs("대파 1대,, 대파 2대,\n 양파 1개 ,") == [("대파", "1대"), ("양파", "1개")]
    many = ", ".join(f"재료{i} 1개" for i in range(80))
    assert len(parse_ingredients(many)) == MAX_INGREDIENTS
    long = parse_ingredients("가" * 70 + " " + "1" * 40 + "g")[0]
    assert (len(long["name"]), len(long["amount"])) == (50, 30)
    assert parse_ingredients(None) == [] and parse_ingredients("") == []


def test_split_steps_strips_numbers_and_trailing_marks():
    row = {
        "MANUAL01": "1. 손질된 새우를 끓는 물에 데쳐 건진다.a",
        "MANUAL02": "2. 연두부와 달걀을 믹서에 간다.b\n",
        "MANUAL03": "",
        "MANUAL04": "  ",
        "MANUAL05": "5. 1.5컵의 물을 붓고 끓인다.",
        "MANUAL20": "10분 정도 찐다.",
        "MANUAL21": "21번째는 없는 칸이다.",
    }
    assert split_steps(row) == ["손질된 새우를 끓는 물에 데쳐 건진다.", "연두부와 달걀을 믹서에 간다.", "1.5컵의 물을 붓고 끓인다.", "10분 정도 찐다."]


@pytest.mark.parametrize(
    "text, expected",
    [("[1인분]조선부추 50g", 1), ("재료(4인분) 감자 2개", 4), ("감자 2개", 2), ("[40인분] 쌀", 2), (None, 2)],
)
def test_parse_servings(text, expected):
    assert parse_servings(text) == expected


def test_ingredient_key_is_lowercase_words_without_parentheses():
    assert ingredient_key("유정란 계란 (특란)") == "유정란 계란"
    assert ingredient_key("Egg/Milk") == "egg milk"
    assert ingredient_key("대파1대") == "대파 1대"
```

`backend/tests/test_recipes.py`(새 파일):
```python
import pytest

import app.recipes as recipes_module
from app.ingredients import seoul_today
from app.models import PublicRecipe, Recipe, User, db
from app.recipe_parse import ingredient_key

BODY = {
    "title": "대파 계란볶음밥",
    "servings": 1,
    "ingredients": [{"name": "대파", "amount": "1대"}, {"name": "계란", "amount": "2개"}, {"name": "밥", "amount": ""}],
    "steps": ["대파를 썰어요.", "  ", "계란과 밥을 볶아요."],
}


def create(client, **fields):
    return client.post("/api/recipes", json={**BODY, **fields})


def add_ingredient(client, name, **fields):
    body = {"name": name, "purchased_on": seoul_today().isoformat(), **fields}
    assert client.post("/api/ingredients", json=body).status_code == 201


def add_public(app, **fields):
    ingredients = fields.pop("ingredients", [{"name": "두부", "amount": "1모"}, {"name": "간장", "amount": "2큰술"}])
    values = {
        "rcp_seq": "100",
        "title": "두부조림",
        "category": "반찬",
        "method": "기타",
        "kcal": 180.0,
        "servings": 2,
        "ingredients_text": "두부 1모, 간장 2큰술",
        "ingredients": ingredients,
        "ingredient_keys": [ingredient_key(i["name"]) for i in ingredients],
        "steps": ["두부를 썰어요.", "간장에 졸여요."],
        "image_url": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.png",
        **fields,
    }
    with app.app_context():
        recipe = PublicRecipe(**values)
        db.session.add(recipe)
        db.session.commit()
        return recipe.id


def test_requires_login(client):
    assert client.get("/api/recipes").status_code == 401
    assert client.get("/api/public-recipes/1").status_code == 401


def test_create_list_get_update_delete(client, login):
    login()
    add_ingredient(client, "대파(국산) 1단")
    res = create(client, source="ai")
    assert res.status_code == 201
    recipe = res.get_json()
    assert recipe == {
        "kind": "mine",
        "id": recipe["id"],
        "title": "대파 계란볶음밥",
        "servings": 1,
        "category": None,
        "ingredients": [
            {"name": "대파", "amount": "1대", "have": True, "matched_name": "대파(국산) 1단"},
            {"name": "계란", "amount": "2개", "have": False, "matched_name": None},
            {"name": "밥", "amount": "", "have": False, "matched_name": None},
        ],
        "steps": ["대파를 썰어요.", "계란과 밥을 볶아요."],
        "source": "mine",  # 클라이언트가 보낸 source는 무시하고 서버가 정한다
        "source_url": None,
        "public_recipe_id": None,
        "image_url": None,
    }
    second = create(client, title="계란국").get_json()

    listed = client.get("/api/recipes").get_json()
    assert [(r["title"], r["servings"], r["source"], r["ingredient_count"]) for r in listed] == [
        ("계란국", 1, "mine", 3),
        ("대파 계란볶음밥", 1, "mine", 3),
    ]
    assert set(listed[0]) == {"id", "title", "servings", "source", "image_url", "ingredient_count", "updated_at"}
    assert client.get(f"/api/recipes/{recipe['id']}").get_json() == recipe

    res = client.put(
        f"/api/recipes/{recipe['id']}",
        json={"title": " 볶음밥 ", "servings": 3, "ingredients": [{"name": " 밥 ", "amount": " 1공기 "}], "steps": []},
    )
    assert res.status_code == 200
    updated = res.get_json()
    assert (updated["title"], updated["servings"], updated["ingredients"], updated["steps"]) == (
        "볶음밥",
        3,
        [{"name": "밥", "amount": "1공기", "have": False, "matched_name": None}],
        [],
    )

    assert client.delete(f"/api/recipes/{second['id']}").status_code == 204
    assert [r["title"] for r in client.get("/api/recipes").get_json()] == ["볶음밥"]


@pytest.mark.parametrize(
    "fields, error",
    [
        ({"title": ""}, "제목은 1~60자로 입력해주세요."),
        ({"title": "가" * 61}, "제목은 1~60자로 입력해주세요."),
        ({"servings": 0}, "인분은 1~20 사이 정수로 입력해주세요."),
        ({"servings": 21}, "인분은 1~20 사이 정수로 입력해주세요."),
        ({"servings": "2"}, "인분은 1~20 사이 정수로 입력해주세요."),
        ({"servings": True}, "인분은 1~20 사이 정수로 입력해주세요."),
        ({"ingredients": []}, "재료를 1~50개 입력해주세요."),
        ({"ingredients": [{"name": "대파"}] * 51}, "재료를 1~50개 입력해주세요."),
        ({"ingredients": "대파"}, "재료를 1~50개 입력해주세요."),
        ({"ingredients": [{"name": "대파"}, {"name": " "}]}, "2번째 재료 이름은 1~50자로 입력해주세요."),
        ({"ingredients": [{"name": "가" * 51}]}, "1번째 재료 이름은 1~50자로 입력해주세요."),
        ({"ingredients": [{"name": "대파", "amount": "1" * 31}]}, "1번째 재료 양은 30자까지 입력해주세요."),
        ({"ingredients": [{"name": "대파", "amount": 1}]}, "1번째 재료 양은 30자까지 입력해주세요."),
        ({"ingredients": ["대파"]}, "잘못된 요청이에요."),
        ({"steps": "볶아요"}, "만드는 법을 다시 확인해주세요."),
        ({"steps": [1]}, "만드는 법을 다시 확인해주세요."),
        ({"steps": ["볶아요"] * 31}, "만드는 법은 30단계까지 입력할 수 있어요."),
        ({"steps": ["", "가" * 501]}, "1번째 단계는 500자까지 입력해주세요."),
        ({"source_url": "javascript:alert(1)"}, "링크는 http:// 또는 https://로 시작하는 주소로 입력해주세요."),
        ({"source_url": "https://" + "a" * 500}, "링크는 http:// 또는 https://로 시작하는 주소로 입력해주세요."),
    ],
)
def test_validation(client, login, fields, error):
    login()
    res = create(client, **fields)
    assert (res.status_code, res.get_json()) == (400, {"error": error})
    assert client.get("/api/recipes").get_json() == []


def test_optional_fields_and_non_object_body(client, login):
    login()
    body = create(client, servings=None, steps=None, source_url=None)
    assert body.status_code == 400  # servings·steps를 보내면 형식이 맞아야 한다
    minimal = client.post("/api/recipes", json={"title": "밥", "ingredients": [{"name": "쌀", "amount": None}]})
    assert minimal.status_code == 201
    assert (minimal.get_json()["servings"], minimal.get_json()["steps"]) == (2, [])
    link = create(client, source_url="https://www.youtube.com/watch?v=abc").get_json()
    assert link["source_url"] == "https://www.youtube.com/watch?v=abc"
    assert client.post("/api/recipes", json=["title"]).status_code == 400


def test_put_keeps_source_url_when_not_sent(client, login):
    login()
    recipe = create(client, source_url="https://example.com/r/1").get_json()
    res = client.put(f"/api/recipes/{recipe['id']}", json={**BODY, "title": "새 제목"})
    assert res.get_json()["source_url"] == "https://example.com/r/1"


def test_other_users_recipe_is_404(client, login):
    login("owner")
    recipe = create(client).get_json()
    login("intruder")
    assert client.get("/api/recipes").get_json() == []
    assert client.get(f"/api/recipes/{recipe['id']}").status_code == 404
    assert client.put(f"/api/recipes/{recipe['id']}", json=BODY).status_code == 404
    assert client.delete(f"/api/recipes/{recipe['id']}").status_code == 404
    assert client.get(f"/api/recipes/{2**40}").status_code == 404


def test_recipe_cap(client, login, monkeypatch):
    monkeypatch.setattr(recipes_module, "MAX_RECIPES_PER_USER", 1)
    login()
    assert create(client).status_code == 201
    res = create(client)
    assert (res.status_code, res.get_json()) == (400, {"error": "레시피는 1개까지 저장할 수 있어요."})


def test_public_detail_marks_have_with_current_inventory(client, login, app):
    login()
    recipe_id = add_public(app, ingredients=[{"name": "두부", "amount": "1모"}, {"name": "진간장", "amount": "2큰술"}, {"name": "물", "amount": "100ml"}])
    add_ingredient(client, "간장 (500ml)")
    res = client.get(f"/api/public-recipes/{recipe_id}")
    assert res.status_code == 200
    assert res.get_json() == {
        "kind": "public",
        "id": recipe_id,
        "title": "두부조림",
        "servings": 2,
        "category": "반찬",
        "method": "기타",
        "kcal": 180.0,
        "ingredients": [
            {"name": "두부", "amount": "1모", "have": False, "matched_name": None},
            {"name": "진간장", "amount": "2큰술", "have": True, "matched_name": "간장 (500ml)"},
            {"name": "물", "amount": "100ml", "have": True, "matched_name": None},  # 물은 늘 있는 것으로 본다
        ],
        "steps": ["두부를 썰어요.", "간장에 졸여요."],
        "image_url": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.png",
        "is_sample": False,
    }
    assert client.get("/api/public-recipes/999999").status_code == 404
    assert client.get(f"/api/public-recipes/{2**40}").status_code == 404


def test_urgent_inventory_is_preferred_as_matched_name(client, login, app):
    login()
    recipe_id = add_public(app)
    add_ingredient(client, "두부 (국산)")
    add_ingredient(client, "두부", expires_on=seoul_today().isoformat())
    ingredients = client.get(f"/api/public-recipes/{recipe_id}").get_json()["ingredients"]
    assert ingredients[0]["matched_name"] == "두부"


def test_save_public_recipe_copies_once(client, login, app):
    user = login()
    recipe_id = add_public(app, title="가" * 70, servings=4)
    res = client.post(f"/api/public-recipes/{recipe_id}/save")
    assert res.status_code == 201
    saved = res.get_json()
    assert (saved["kind"], saved["title"], saved["servings"], saved["source"], saved["public_recipe_id"]) == (
        "mine",
        "가" * 60,
        4,
        "public",
        recipe_id,
    )
    assert saved["image_url"] == "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.png"
    assert [i["name"] for i in saved["ingredients"]] == ["두부", "간장"]
    assert saved["steps"] == ["두부를 썰어요.", "간장에 졸여요."]

    again = client.post(f"/api/public-recipes/{recipe_id}/save")
    assert (again.status_code, again.get_json()["id"]) == (200, saved["id"])
    with app.app_context():
        assert Recipe.query.filter_by(user_id=user.id).count() == 1

    login("other")  # 다른 사용자는 따로 저장한다
    assert client.post(f"/api/public-recipes/{recipe_id}/save").status_code == 201
    assert client.post("/api/public-recipes/999999/save").status_code == 404


def test_deleting_public_recipe_keeps_saved_copy_and_user_cascades(client, login, app):
    user = login()
    recipe_id = add_public(app)
    saved_id = client.post(f"/api/public-recipes/{recipe_id}/save").get_json()["id"]
    with app.app_context():
        db.session.delete(db.session.get(PublicRecipe, recipe_id))
        db.session.commit()
    assert client.get(f"/api/recipes/{saved_id}").get_json()["public_recipe_id"] is None
    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert db.session.get(Recipe, saved_id) is None


def test_mutations_require_fetch_header(raw_client):
    for method, path in [("post", "/api/recipes"), ("put", "/api/recipes/1"), ("delete", "/api/recipes/1"), ("post", "/api/public-recipes/1/save")]:
        res = getattr(raw_client, method)(path, json=BODY)
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
```

`backend/tests/test_ingredients.py` 끝에 추가한다(파일에 이미 있는 `create`, `bulk`, `seoul_today`, `timedelta`, `pytest`를 쓴다):
```python
# --- 3단계 T1: 미래 구입일 거부, 날짜 형식 ---

FUTURE_PURCHASE = "구입일은 오늘보다 뒤일 수 없어요."


def test_future_purchased_on_rejected_on_create_bulk_and_patch(client, login):
    login()
    today = seoul_today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    res = create(client, purchased_on=tomorrow)
    assert (res.status_code, res.get_json()) == (400, {"error": FUTURE_PURCHASE})
    res = bulk(client, {"name": "대파", "purchased_on": today.isoformat()}, {"name": "우유", "purchased_on": tomorrow})
    assert res.get_json() == {"error": f"2번째 재료: {FUTURE_PURCHASE}", "errors": [{"index": 1, "error": FUTURE_PURCHASE}]}
    item = create(client, purchased_on=today.isoformat()).get_json()
    res = client.patch(f"/api/ingredients/{item['id']}", json={"purchased_on": tomorrow})
    assert (res.status_code, res.get_json()) == (400, {"error": FUTURE_PURCHASE})
    assert [i["purchased_on"] for i in client.get("/api/ingredients").get_json()] == [today.isoformat()]


@pytest.mark.parametrize("value", ["20260101", "2026-9-1", "2026-09-01T00:00", " 2026-09-01"])
def test_dates_must_be_yyyy_mm_dd(client, login, value):
    login()
    res = create(client, purchased_on=value)
    assert (res.status_code, res.get_json()) == (400, {"error": "구입일은 YYYY-MM-DD 형식으로 입력해주세요."})
    res = create(client, expires_on=value)
    assert (res.status_code, res.get_json()) == (400, {"error": "유통기한은 YYYY-MM-DD 형식으로 입력해주세요."})
```

`backend/tests/test_tools.py` 끝에 추가한다(파일에 이미 있는 `create`를 쓴다):
```python
def test_bought_on_rejects_compact_date(client, login):
    login()
    res = create(client, bought_on="20260101")
    assert (res.status_code, res.get_json()) == (400, {"error": "구매일은 YYYY-MM-DD 형식으로 입력해주세요."})
```

`backend/tests/test_migrations.py`:
- `def test_upgrade_to_head_and_back_to_base(app):` 바로 위에 추가한다:
```python
def test_recipes_migration_adds_and_removes_tables(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a5b5c5d5e5f5")
        upgrade(directory=MIGRATIONS, revision="a6b6c6d6e6f6")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            tables = set(inspector.get_table_names())
            recipe_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("recipes")}
            public_uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("public_recipes")}
        assert {"recipes", "public_recipes"} <= tables
        assert recipe_fks == {"users": "CASCADE", "public_recipes": "SET NULL"}
        assert ("rcp_seq",) in public_uniques

        downgrade(directory=MIGRATIONS, revision="a5b5c5d5e5f5")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert not {"recipes", "public_recipes"} & tables
```
- `test_upgrade_to_head_and_back_to_base`의 테이블 집합 줄
  `        assert {"users", "ingredients", "storage_locations", "staples", "item_rules", "kitchen_tools", "ai_calls"} <= tables`
  를 교체한다:
```python
        assert {
            "users",
            "ingredients",
            "storage_locations",
            "staples",
            "item_rules",
            "kitchen_tools",
            "ai_calls",
            "public_recipes",
            "recipes",
        } <= tables
```

- [ ] **Step 2: 실패 확인**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning tests/test_recipe_parse.py tests/test_recipes.py; .venv/bin/pytest -q -W error::DeprecationWarning tests/test_ingredients.py tests/test_tools.py tests/test_migrations.py
```
Expected:
- 첫 실행: `Interrupted: 2 errors during collection` (`app.recipe_parse`, `app.recipes`가 없어 ImportError).
- 둘째 실행: `5 failed, 101 passed`. 실패는 `test_future_purchased_on_rejected_on_create_bulk_and_patch`(201이 나옴), `test_dates_must_be_yyyy_mm_dd[20260101]`(Python 3.11+의 `date.fromisoformat`이 받아 줌), `test_bought_on_rejects_compact_date`, `test_recipes_migration_adds_and_removes_tables`(revision 없음), `test_upgrade_to_head_and_back_to_base`(테이블 없음). 나머지 날짜 모양 3개는 지금도 통과한다.

- [ ] **Step 3: 모델과 마이그레이션**

`backend/app/models.py` 끝에 추가한다:
```python
class PublicRecipe(db.Model):
    """식약처 COOKRCP01 레시피(또는 키가 없을 때 넣는 예시 레시피). 사용자 소유가 아니다."""

    __tablename__ = "public_recipes"

    id = db.Column(db.Integer, primary_key=True)
    rcp_seq = db.Column(db.String(20), nullable=False, unique=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30))  # RCP_PAT2 (반찬, 국&찌개 …)
    method = db.Column(db.String(30))  # RCP_WAY2 (끓이기, 볶기 …)
    kcal = db.Column(db.Float)  # INFO_ENG
    servings = db.Column(db.Integer, nullable=False, default=2)
    ingredients_text = db.Column(db.Text, nullable=False, default="")  # RCP_PARTS_DTLS 원문
    ingredients = db.Column(db.JSON, nullable=False, default=list)  # [{name, amount}]
    ingredient_keys = db.Column(db.JSON, nullable=False, default=list)  # ingredients와 같은 순서의 매칭용 이름
    steps = db.Column(db.JSON, nullable=False, default=list)  # [str]
    image_url = db.Column(db.String(500))
    is_sample = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Recipe(db.Model):
    __tablename__ = "recipes"
    # 같은 공공 레시피를 두 번 저장하지 않는다(동시에 눌러도). public_recipe_id가 NULL인 행끼리는 겹쳐도 된다.
    __table_args__ = (db.UniqueConstraint("user_id", "public_recipe_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(60), nullable=False)
    servings = db.Column(db.Integer, nullable=False, default=2)
    ingredients = db.Column(db.JSON, nullable=False, default=list)  # [{name, amount}]
    steps = db.Column(db.JSON, nullable=False, default=list)  # [str]
    source = db.Column(db.String(20), nullable=False, default="mine")  # mine | public | ai | youtube | instagram | text
    source_url = db.Column(db.String(500))
    public_recipe_id = db.Column(db.Integer, db.ForeignKey("public_recipes.id", ondelete="SET NULL"))
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
```

`backend/migrations/versions/a6b6c6d6e6f6_recipes.py`(새 파일):
```python
"""recipes

Revision ID: a6b6c6d6e6f6
Revises: a5b5c5d5e5f5
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a6b6c6d6e6f6"
down_revision = "a5b5c5d5e5f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "public_recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rcp_seq", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=True),
        sa.Column("method", sa.String(length=30), nullable=True),
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("ingredients_text", sa.Text(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("ingredient_keys", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_sample", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_public_recipes")),
        sa.UniqueConstraint("rcp_seq", name=op.f("uq_public_recipes_rcp_seq")),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("public_recipe_id", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["public_recipe_id"],
            ["public_recipes.id"],
            name=op.f("fk_recipes_public_recipe_id_public_recipes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_recipes_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.UniqueConstraint("user_id", "public_recipe_id", name=op.f("uq_recipes_user_id")),
    )
    op.create_index(op.f("ix_recipes_user_id"), "recipes", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_recipes_user_id"), table_name="recipes")
    op.drop_table("recipes")
    op.drop_table("public_recipes")
```

- [ ] **Step 4: 날짜 모양 검사와 미래 구입일 거부**

`backend/app/validation.py`:
- 맨 위 import를 교체한다:
```python
import re
from datetime import date

from flask import abort
from sqlalchemy.exc import IntegrityError

from .models import db

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
```
- 파일 끝에 추가한다:
```python
def iso_date(value):
    """YYYY-MM-DD 문자열만 날짜로 바꾸고, 아니면 None. date.fromisoformat은 3.11부터 20260101도 받아서 모양을 먼저 거른다."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
```

`backend/app/ingredients.py`:
- `from .validation import text` → `from .validation import iso_date, text`
- `_date`를 교체한다:
```python
def _date(value, label):
    day = iso_date(value)
    if day is None:
        abort(400, f"{label}은 YYYY-MM-DD 형식으로 입력해주세요.")
    return day
```
- `parse_fields`의 구입일 줄 아래에 두 줄을 추가한다:
```python
    if creating or "purchased_on" in data:
        fields["purchased_on"] = _date(data.get("purchased_on"), "구입일")
        if fields["purchased_on"] > seoul_today():  # 단건·일괄·수정이 모두 여기를 지난다
            abort(400, "구입일은 오늘보다 뒤일 수 없어요.")
```

`backend/app/tools.py`:
- `from .validation import integer, text` → `from .validation import integer, iso_date, text`
- `_optional_date`의 `try:` 블록 세 줄을 교체한다:
```python
    parsed = iso_date(value)
    if parsed is None:
        abort(400, message)
```

`backend/app/scan.py`:
- `from datetime import date, datetime, time, timedelta, timezone` → `from datetime import datetime, time, timedelta, timezone`
- `from .models import AiCall, db, utcnow` 아래에 `from .validation import iso_date`
- `_purchased_on`의 본문을 교체한다:
```python
def _purchased_on(value, today):
    day = iso_date(value)
    return day.isoformat() if day and day <= today else None
```

- [ ] **Step 5: 식약처 원문 파서**

`backend/app/recipe_parse.py`(새 파일). 2026-09-13 식약처 샘플 5건(`/api/sample/COOKRCP01/json/1/5`)에 돌려 제목 줄·`고명`·`[1인분]`·`·양념장 :`이 모두 걸러지는 것을 확인했다:
```python
"""식약처 COOKRCP01 레시피 원문 정리. 순수 함수만 두어 네트워크 없이 테스트한다.

ponytail: 규칙 기반 파서다. 확신이 없으면 문자열 전체를 이름으로 두고 양은 ""로 둔다(버리지 않는다).
원문 모양이 더 다양하면 규칙을 늘리기보다 AI 정리(3b)로 교체한다.
"""

import re

from .matching import normalize, tokens

MAX_INGREDIENTS = 50
MAX_NAME = 50
MAX_AMOUNT = 30
MAX_STEP = 500
DEFAULT_SERVINGS = 2

_BULLET = re.compile(r"^[\s●○•·▶▷■□◆◇※*-]+")
_BRACKET = re.compile(r"^[\[【<]([^\]】>]*)[\]】>]\s*")  # "[1인분]", "[양념장]"
_LABEL = re.compile(r"^[^,:：()]{1,20}[:：]\s*")  # "양념장 : ", "주재료:"
_LEAD_WORD = re.compile(r"^(?:주재료|부재료|재료)\s+")
_HEADER_WORDS = {"재료", "주재료", "부재료", "양념", "양념장", "소스", "고명", "육수", "드레싱", "반죽", "토핑", "곁들임"}
_AMOUNT_START = r"(?:\d|[½⅓⅔¼¾⅛]|약간|적당량|적당히|조금|소량|취향껏)"
_SPACED = re.compile(rf"^(.+?)\s+({_AMOUNT_START}.*)$")  # "다진 마늘 1작은술(5g)"
_ATTACHED = re.compile(r"^(.*[가-힣])(\d[\d./]*[^\s\d(]*(?:\([^)]*\))?)$")  # "대파1대" (양 안에 공백 없음)
_STEP_NO = re.compile(r"^\d+[.)](?!\d)\s*")  # "1. " (1.5컵은 그대로)
_STEP_MARK = re.compile(r"(?<=[.!?])\s*[a-zA-Z]$")  # 원문 단계 끝의 "a", "b"
_SERVINGS = re.compile(r"(\d+)\s*인분")


def _split_items(line):
    """괄호 밖 쉼표로 나눈다. "소금(1g, 약간), 후추" → ["소금(1g, 약간)", " 후추"]"""
    items, depth, start = [], 0, 0
    for index, char in enumerate(line):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char in ",，" and depth == 0:
            items.append(line[start:index])
            start = index + 1
    items.append(line[start:])
    return items


def _clean_item(item):
    item = _BULLET.sub("", item).strip()
    while match := _BRACKET.match(item):
        item = item[match.end() :].strip()
    item = _LABEL.sub("", item, count=1)
    return _LEAD_WORD.sub("", item, count=1).strip()


def _name_amount(item):
    match = _SPACED.match(item) or _ATTACHED.match(item)
    if not match or match.group(1).count("(") != match.group(1).count(")"):  # 괄호 안에서 자르지 않는다
        return item, ""
    return match.group(1).strip(), match.group(2).strip()


def parse_ingredients(text, title=""):
    """RCP_PARTS_DTLS → [{name, amount}]. 제목 줄·구역 제목을 빼고, 이름이 같으면 처음 것만, 최대 50개."""
    title_key = normalize(title or "")
    result, seen = [], set()
    for line in (text or "").splitlines():
        for raw in _split_items(line):
            item = _clean_item(raw)
            if not item:
                continue
            name, amount = _name_amount(item)
            key = normalize(name)
            is_header = key in _HEADER_WORDS or (title_key and (key == title_key or (len(key) >= 3 and title_key.endswith(key))))
            if not key or key in seen or (not amount and is_header):
                continue
            seen.add(key)
            result.append({"name": name[:MAX_NAME].strip(), "amount": amount[:MAX_AMOUNT].strip()})
            if len(result) == MAX_INGREDIENTS:
                return result
    return result


def split_steps(row):
    """MANUAL01~MANUAL20 중 내용이 있는 칸. 앞 번호("1. ")와 끝 표시 글자("a")는 뗀다(화면이 번호를 붙인다)."""
    steps = []
    for number in range(1, 21):
        value = row.get(f"MANUAL{number:02d}")
        if not isinstance(value, str):
            continue
        step = _STEP_MARK.sub("", _STEP_NO.sub("", " ".join(value.split())))
        if step:
            steps.append(step[:MAX_STEP])
    return steps


def parse_servings(text):
    """원문에 "N인분"이 있으면 그 값(1~20), 없으면 2 (스펙 23절 D1)."""
    match = _SERVINGS.search(text or "")
    servings = int(match.group(1)) if match else DEFAULT_SERVINGS
    return servings if 1 <= servings <= 20 else DEFAULT_SERVINGS


def ingredient_key(name):
    """매칭용 이름: 괄호 내용을 빼고 소문자 단어를 공백 하나로 잇는다. names_match와 같은 단어 경계를 유지한다."""
    return " ".join(tokens(name))
```

- [ ] **Step 6: 레시피 API**

`backend/app/recipes.py`(새 파일):
```python
from datetime import timezone
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.orm import joinedload

from .auth import get_owned_or_404, login_required
from .ingredients import seasoning_names, seoul_today, status_of, user_rules
from .matching import names_match, normalize
from .models import Ingredient, PublicRecipe, Recipe, db
from .recipe_parse import ingredient_key
from .validation import commit_or_duplicate, integer, text

bp = Blueprint("recipes", __name__, url_prefix="/api")

MAX_RECIPES_PER_USER = 1000
MAX_INGREDIENTS = 50
MAX_STEPS = 30
ALWAYS_HAVE = {"물"}  # 물은 재고에 넣지 않으니 늘 있는 것으로 본다
URL_ERROR = "링크는 http:// 또는 https://로 시작하는 주소로 입력해주세요."


def inventory(user_id):
    """[(재고 이름, 빨리 먹어야 하는지)] — 빨리 먹어야 할 재료(urgent·danger)가 앞. 요청마다 한 번 만든다."""
    today, rules, seasonings = seoul_today(), user_rules(user_id), seasoning_names(user_id)
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=user_id).order_by(Ingredient.id).all()
    stock = [(i.name, status_of(i, today, rules, seasonings) in ("urgent", "danger")) for i in items]
    return sorted(stock, key=lambda row: not row[1])


def match_key(key, stock):
    """재료 키에 매칭되는 첫 재고 이름(없으면 None)과 있음 여부."""
    matched = next((name for name, _ in stock if names_match(name, key)), None)
    return matched, matched is not None or normalize(key) in ALWAYS_HAVE


def annotate(ingredients, keys, stock):
    rows = []
    for item, key in zip(ingredients, keys):
        matched, have = match_key(key, stock)
        rows.append({"name": item["name"], "amount": item["amount"], "have": have, "matched_name": matched})
    return rows


def _iso(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()  # SQLite는 tz 없이 돌려준다


def recipe_json(recipe, stock):
    return {
        "kind": "mine",
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "category": None,
        "ingredients": annotate(recipe.ingredients, [ingredient_key(i["name"]) for i in recipe.ingredients], stock),
        "steps": recipe.steps,
        "source": recipe.source,
        "source_url": recipe.source_url,
        "public_recipe_id": recipe.public_recipe_id,
        "image_url": recipe.image_url,
    }


def public_json(recipe, stock):
    return {
        "kind": "public",
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "category": recipe.category,
        "method": recipe.method,
        "kcal": recipe.kcal,
        "ingredients": annotate(recipe.ingredients, recipe.ingredient_keys, stock),
        "steps": recipe.steps,
        "image_url": recipe.image_url,
        "is_sample": recipe.is_sample,
    }


def list_json(recipe):
    return {
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "source": recipe.source,
        "image_url": recipe.image_url,
        "ingredient_count": len(recipe.ingredients),
        "updated_at": _iso(recipe.updated_at),
    }


def _ingredients(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_INGREDIENTS:
        abort(400, f"재료를 1~{MAX_INGREDIENTS}개 입력해주세요.")
    rows = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            abort(400, "잘못된 요청이에요.")
        name, amount = item.get("name"), item.get("amount")
        amount = "" if amount is None else amount
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
            abort(400, f"{index}번째 재료 이름은 1~50자로 입력해주세요.")
        if not isinstance(amount, str) or len(amount.strip()) > 30:
            abort(400, f"{index}번째 재료 양은 30자까지 입력해주세요.")
        rows.append({"name": name.strip(), "amount": amount.strip()})
    return rows


def _steps(value):
    if not isinstance(value, list) or not all(isinstance(step, str) for step in value):
        abort(400, "만드는 법을 다시 확인해주세요.")
    steps = [step.strip() for step in value if step.strip()]
    if len(steps) > MAX_STEPS:
        abort(400, f"만드는 법은 {MAX_STEPS}단계까지 입력할 수 있어요.")
    for index, step in enumerate(steps, 1):
        if len(step) > 500:
            abort(400, f"{index}번째 단계는 500자까지 입력해주세요.")
    return steps


def _source_url(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value.strip()) > 500:
        abort(400, URL_ERROR)
    parsed = urlparse(value.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        abort(400, URL_ERROR)
    return value.strip()


def parse_recipe(data):
    """생성·수정(PUT) 공통. source는 서버가 정하므로 받지 않는다. source_url은 보냈을 때만 바꾼다."""
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    fields = {
        "title": text(data.get("title"), "제목은", 60),
        "servings": integer(data.get("servings", 2), "인분은", 1, 20),
        "ingredients": _ingredients(data.get("ingredients")),
        "steps": _steps(data.get("steps", [])),
    }
    if "source_url" in data:
        fields["source_url"] = _source_url(data["source_url"])
    return fields


def _check_recipe_cap():
    if Recipe.query.filter_by(user_id=g.user.id).count() >= MAX_RECIPES_PER_USER:
        abort(400, f"레시피는 {MAX_RECIPES_PER_USER}개까지 저장할 수 있어요.")


def _public_or_404(recipe_id):
    recipe = db.session.get(PublicRecipe, recipe_id) if recipe_id <= 2**31 - 1 else None
    if recipe is None:
        abort(404, "찾을 수 없어요.")
    return recipe


@bp.get("/recipes")
@login_required
def list_recipes():
    recipes = Recipe.query.filter_by(user_id=g.user.id).order_by(Recipe.id.desc()).all()
    return jsonify([list_json(r) for r in recipes])


@bp.post("/recipes")
@login_required
def create_recipe():
    fields = parse_recipe(request.get_json(silent=True))
    _check_recipe_cap()
    recipe = Recipe(user_id=g.user.id, source="mine", **fields)
    db.session.add(recipe)
    db.session.commit()
    return jsonify(recipe_json(recipe, inventory(g.user.id))), 201


@bp.get("/recipes/<int:recipe_id>")
@login_required
def get_recipe(recipe_id):
    return jsonify(recipe_json(get_owned_or_404(Recipe, recipe_id), inventory(g.user.id)))


@bp.put("/recipes/<int:recipe_id>")
@login_required
def update_recipe(recipe_id):
    recipe = get_owned_or_404(Recipe, recipe_id)
    for key, value in parse_recipe(request.get_json(silent=True)).items():
        setattr(recipe, key, value)
    db.session.commit()
    return jsonify(recipe_json(recipe, inventory(g.user.id)))


@bp.delete("/recipes/<int:recipe_id>")
@login_required
def delete_recipe(recipe_id):
    db.session.delete(get_owned_or_404(Recipe, recipe_id))
    db.session.commit()
    return "", 204


@bp.get("/public-recipes/<int:recipe_id>")
@login_required
def get_public_recipe(recipe_id):
    return jsonify(public_json(_public_or_404(recipe_id), inventory(g.user.id)))


@bp.post("/public-recipes/<int:recipe_id>/save")
@login_required
def save_public_recipe(recipe_id):
    """공공 레시피를 내 레시피로 복사한다. 이미 저장했으면 그 레시피를 200으로 돌려준다."""
    public = _public_or_404(recipe_id)
    existing = Recipe.query.filter_by(user_id=g.user.id, public_recipe_id=public.id).first()
    if existing:
        return jsonify(recipe_json(existing, inventory(g.user.id)))
    _check_recipe_cap()
    recipe = Recipe(
        user_id=g.user.id,
        title=public.title[:60].strip(),
        servings=public.servings,
        ingredients=public.ingredients,  # 파서가 이미 50개·이름 50자·양 30자로 잘랐다
        steps=public.steps[:MAX_STEPS],
        source="public",
        public_recipe_id=public.id,
        image_url=public.image_url,
    )
    db.session.add(recipe)
    commit_or_duplicate("이미 저장한 레시피예요.")  # 동시에 두 번 누른 경우 UNIQUE(user_id, public_recipe_id)
    return jsonify(recipe_json(recipe, inventory(g.user.id))), 201
```

`backend/app/__init__.py`의 블루프린트 import·등록에 recipes를 추가한다(알파벳 순서 유지):
```python
    from .locations import bp as locations_bp
    from .recipes import bp as recipes_bp
    from .scan import bp as scan_bp
```
```python
    app.register_blueprint(locations_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(scan_bp)
```

- [ ] **Step 7: 스펙 갱신**

`docs/superpowers/specs/2026-09-13-recipe-ai-design.md`에서 아래 줄을 각각 통째로 바꾼다. 찾을 줄은 파일에 한 번씩만 있다.

4절 recipes:
```text
- `recipes`: id, user_id, title, ingredients(JSON `[{name, amount}]`), steps(JSON `[str]`), source(`mine`|`public`|`ai`), image_url(선택), created_at
```
→
```text
- `recipes`: id, user_id, title(1~60자), servings(1~20, 기본 2), ingredients(JSON `[{name, amount}]` 1~50개), steps(JSON `[str]` 0~30개), source(`mine`|`public`|`ai`|`youtube`|`instagram`|`text`), source_url(선택), public_recipe_id(선택, SET NULL), image_url(선택), created_at, updated_at. UNIQUE(user_id, public_recipe_id)
```

4절 public_recipes:
```text
- `public_recipes`: id, rcp_seq(UNIQUE), title, ingredients_text(원문), ingredient_names(JSON, 파싱된 이름 목록), steps(JSON), image_url. 사용자 소유 아님.
```
→
```text
- `public_recipes`: id, rcp_seq(UNIQUE), title, category(RCP_PAT2), method(RCP_WAY2), kcal(INFO_ENG), servings(원문 `N인분`, 없으면 2), ingredients_text(원문), ingredients(JSON `[{name, amount}]`, 파싱), ingredient_keys(JSON, ingredients와 같은 순서의 매칭용 이름), steps(JSON), image_url, is_sample(키 없을 때 넣는 예시 레시피), updated_at. 사용자 소유 아님.
```

5절 표 두 줄:
```text
| GET/PUT/DELETE | `/api/recipes/<id>` | 상세 / 수정 / 삭제 |
| GET | `/api/public-recipes/<id>` | 공공 레시피 상세 |
```
→
```text
| GET/PUT/DELETE | `/api/recipes/<id>` | 상세 / 수정 / 삭제. 상세의 `ingredients`는 `[{name, amount, have, matched_name}]`(현재 재고 기준) |
| GET | `/api/public-recipes/<id>` | 공공 레시피 상세(같은 `ingredients` 모양) |
| POST | `/api/public-recipes/<id>/save` | 내 레시피로 복사(source `public`) 201. 이미 저장했으면 그 레시피 200 |
```

- [ ] **Step 8: 통과 확인 (SQLite와 PostgreSQL)**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning && TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate .venv/bin/pytest -q -W error::DeprecationWarning
```
Expected: 두 실행 모두 실패 0, 경고 0 (main 223개 + 새 테스트 59개 = `282 passed`). `test_urgent_inventory_is_preferred_as_matched_name`은 재고를 빨리 먹어야 할 순서로 정렬하지 않으면, `test_save_public_recipe_copies_once`는 저장 전에 기존 복사본을 찾지 않으면 실패한다.

- [ ] **Step 9: 개발 DB 적용·일치 확인**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app db upgrade && .venv/bin/flask --app app db check
```
Expected: `Running upgrade a5b5c5d5e5f5 -> a6b6c6d6e6f6, recipes` 뒤에 `No new upgrade operations detected.` (dev.sh의 Flask 5181은 `--debug` 리로더라 새 코드로 다시 뜬다. 끄지 않는다.)

- [ ] **Step 10: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend docs/superpowers/specs/2026-09-13-recipe-ai-design.md && git status --short && git commit -m "feat: 레시피 모델·마이그레이션, 내 레시피 API, 공공 레시피 상세·저장, 식약처 원문 파서, 미래 구입일 거부" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"
```
`git status --short`에 `backend/.env`가 없어야 한다(gitignore).

---

### Task 2: 식약처 레시피 동기화·예시 레시피·추천 API

**Files:**
- Create: `backend/app/public_recipes.py`, `backend/app/data/sample_recipes.json`, `backend/tests/test_public_recipes.py`, `backend/tests/test_recommendations.py`
- Modify: `backend/app/recipes.py`, `backend/app/__init__.py`, `backend/tests/conftest.py`
- Modify (문서): `docs/superpowers/specs/2026-09-13-recipe-ai-design.md`, `docs/deploy.md`

**Interfaces:**
- Consumes: T1 `PublicRecipe`, `Recipe`, `parse_ingredients`, `parse_servings`, `split_steps`, `ingredient_key`, `inventory`, `match_key`, 픽스처 `app`, `client`, `login`
- Produces:
  - 설정값 `FOODSAFETY_API_KEY`(env, 비었으면 None)
  - `app.public_recipes`: `bp`(`cli_group=None`), `API_URL`(https), `PAGE_SIZE`(1000), `SAMPLE_FILE`, `row_fields(row)`, `sample_fields(item)`, `upsert(items) -> (created, updated)`, `fetch_rows(key)`
  - CLI `flask sync-public-recipes`: 키 없으면 종료 코드 1 + `FOODSAFETY_API_KEY가 없어요. 키 없이 화면을 확인하려면 flask seed-sample-recipes로 예시 레시피를 넣어주세요.` / 성공 `식약처 레시피 N건을 받았어요. 새로 A건, 바뀐 것 B건, 예시 레시피 C건은 지웠어요.` / 실패 `식약처 레시피를 받지 못했어요(1~1000번, ConnectionError).`, `식약처 API가 오류를 돌려줬어요(INFO-100).` — 실패하면 아무것도 쓰지 않는다
  - CLI `flask seed-sample-recipes`: `예시 레시피 12개를 넣었어요. 새로 A개, 바뀐 것 B개.` (`SAMPLE-01`~`SAMPLE-12`, `is_sample` True, 여러 번 실행해도 같다)
  - API `GET /api/recommendations?limit=20`(1~50으로 자름) → `{mine:[카드], public:[카드], sample, inventory_count}`
    - 카드 `{kind, id, title, image_url, servings, match_rate(소수 둘째 자리), have_count, total_count, missing(최대 5), urgent_used, urgent_names, score}`
    - `urgent_names`: 이 레시피가 쓰는 재고 이름 중 상태가 urgent·danger인 것(매칭된 재고 이름, 레시피 재료 순서, 중복 제거). `urgent_used = len(urgent_names)`, `score = match_rate + 0.1 × urgent_used`
    - 재고와 겹치는 재료가 없는 레시피는 뺀다(물만 겹치는 것 포함). `물`은 늘 있는 것으로 센다. 정렬은 score 내림차순 → 제목 → id
    - `sample`: 공공 레시피가 있고 전부 `is_sample`일 때 true. `inventory_count`: 내 재고 수(0이면 화면이 "재고가 비어 있어요")

(브랜치: `feature/recipes-backend`가 main에 병합된 뒤 시작한다.)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/public-recipes-sync
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/conftest.py`의 `TEST_CONFIG`에 한 줄을 추가한다(셸에 키가 있어도 테스트가 흔들리지 않게):
```python
TEST_CONFIG = {
    "TESTING": True,
    "SECRET_KEY": "test",
    "SQLALCHEMY_DATABASE_URI": database_url(TEST_DATABASE_URL),
    "DEV_MODE": True,
    "SESSION_COOKIE_SECURE": False,
    "ANTHROPIC_API_KEY": None,  # 셸에 키가 있어도 테스트는 예시 모드로 시작한다
    "FOODSAFETY_API_KEY": None,  # 셸에 키가 있어도 동기화 테스트는 키 없음으로 시작한다
}
```

`backend/tests/test_public_recipes.py`(새 파일). 두 행은 식약처 샘플 응답 모양을 줄인 것이다:
```python
import json
from types import SimpleNamespace

import pytest
import requests

import app.public_recipes as public_module
from app.matching import normalize
from app.models import PublicRecipe
from app.public_recipes import SAMPLE_FILE, row_fields

ROWS = [
    {
        "RCP_SEQ": "28",
        "RCP_NM": "새우 두부 계란찜",
        "RCP_PAT2": "반찬",
        "RCP_WAY2": "찌기",
        "INFO_ENG": "220",
        "RCP_PARTS_DTLS": "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개)\n고명\n시금치 10g(3줄기)",
        "MANUAL01": "1. 손질된 새우를 끓는 물에 데쳐 건진다.a",
        "MANUAL02": "2. 연두부와 달걀을 믹서에 갈아 새우와 섞는다.b",
        "MANUAL03": "",
        "ATT_FILE_NO_MAIN": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png",
    },
    {
        "RCP_SEQ": "29",
        "RCP_NM": "부추 콩가루 찜",
        "RCP_PAT2": "반찬",
        "RCP_WAY2": "찌기",
        "INFO_ENG": "",
        "RCP_PARTS_DTLS": "[1인분]조선부추 50g, 날콩가루 7g(1⅓작은술)\n·양념장 : 저염간장 3g(2/3작은술), 참깨 약간",
        "MANUAL01": "1. 부추를 씻어 5cm 길이로 썬다.",
        "ATT_FILE_NO_MAIN": "",
    },
]


def page(rows, total=None, code="INFO-000"):
    body = {"COOKRCP01": {"total_count": str(len(rows) if total is None else total), "row": rows, "RESULT": {"MSG": "", "CODE": code}}}
    return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)


def fake_get(monkeypatch, *responses):
    calls = []

    def get(url, timeout):
        calls.append((url, timeout))
        response = responses[len(calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(requests, "get", get)
    return calls


def run(app, command):
    return app.test_cli_runner().invoke(args=[command])


def public_rows(app):
    with app.app_context():
        return [(r.rcp_seq, r.title, r.is_sample) for r in PublicRecipe.query.order_by(PublicRecipe.rcp_seq)]


def test_row_fields_maps_cookrcp01_row():
    fields = row_fields(ROWS[0])
    assert fields == {
        "rcp_seq": "28",
        "title": "새우 두부 계란찜",
        "category": "반찬",
        "method": "찌기",
        "kcal": 220.0,
        "servings": 2,
        "ingredients_text": ROWS[0]["RCP_PARTS_DTLS"],
        "ingredients": [
            {"name": "연두부", "amount": "75g(3/4모)"},
            {"name": "칵테일새우", "amount": "20g(5마리)"},
            {"name": "달걀", "amount": "30g(1/2개)"},
            {"name": "시금치", "amount": "10g(3줄기)"},
        ],
        "ingredient_keys": ["연두부", "칵테일새우", "달걀", "시금치"],
        "steps": ["손질된 새우를 끓는 물에 데쳐 건진다.", "연두부와 달걀을 믹서에 갈아 새우와 섞는다."],
        "image_url": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png",
        "is_sample": False,
    }
    second = row_fields(ROWS[1])
    assert (second["servings"], second["kcal"], second["image_url"]) == (1, None, None)


def test_sync_without_key_points_to_sample_seed(app, monkeypatch):
    calls = fake_get(monkeypatch)
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 1
    assert "FOODSAFETY_API_KEY가 없어요" in result.output
    assert "flask seed-sample-recipes" in result.output
    assert calls == []


def test_sync_fetches_pages_and_upserts(app, monkeypatch):
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    monkeypatch.setattr(public_module, "PAGE_SIZE", 1)
    calls = fake_get(monkeypatch, page(ROWS[:1], total=2), page(ROWS[1:], total=2))
    assert run(app, "seed-sample-recipes").exit_code == 0

    result = run(app, "sync-public-recipes")
    assert result.exit_code == 0, result.output
    assert calls == [
        ("https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/1/1", 30),
        ("https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/2/2", 30),
    ]
    assert "식약처 레시피 2건을 받았어요. 새로 2건, 바뀐 것 0건, 예시 레시피 12건은 지웠어요." in result.output
    assert public_rows(app) == [("28", "새우 두부 계란찜", False), ("29", "부추 콩가루 찜", False)]

    changed = {**ROWS[0], "RCP_NM": "새우 두부 계란찜(개정)"}
    fake_get(monkeypatch, page([changed], total=2), page(ROWS[1:], total=2))
    result = run(app, "sync-public-recipes")
    assert "새로 0건, 바뀐 것 2건, 예시 레시피 0건은 지웠어요." in result.output
    assert public_rows(app)[0] == ("28", "새우 두부 계란찜(개정)", False)


@pytest.mark.parametrize(
    "response, message",
    [
        (requests.ConnectionError("https://openapi.foodsafetykorea.go.kr/api/test-key/..."), "식약처 레시피를 받지 못했어요(1~1000번, ConnectionError)."),
        (SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"oops": 1}), "식약처 레시피를 받지 못했어요(1~1000번, KeyError)."),
        (page([], code="INFO-100"), "식약처 API가 오류를 돌려줬어요(INFO-100)."),
    ],
)
def test_sync_failure_writes_nothing_and_hides_key(app, monkeypatch, response, message):
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    fake_get(monkeypatch, response)
    run(app, "seed-sample-recipes")
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 1
    assert message in result.output
    assert "test-key" not in result.output
    assert len(public_rows(app)) == 12  # 예시 레시피도 그대로


def test_seed_sample_recipes_is_idempotent(app):
    first = run(app, "seed-sample-recipes")
    assert "예시 레시피 12개를 넣었어요. 새로 12개, 바뀐 것 0개." in first.output
    second = run(app, "seed-sample-recipes")
    assert "새로 0개, 바뀐 것 12개." in second.output
    with app.app_context():
        recipes = PublicRecipe.query.order_by(PublicRecipe.rcp_seq).all()
        assert [r.rcp_seq for r in recipes] == [f"SAMPLE-{n:02d}" for n in range(1, 13)]
        assert {r.title for r in recipes} == {
            "된장찌개", "김치찌개", "계란말이", "두부조림", "애호박볶음", "제육볶음",
            "감자조림", "콩나물무침", "계란국", "대파 계란볶음밥", "어묵볶음", "시금치나물",
        }
        for r in recipes:
            assert r.is_sample and r.image_url is None and r.category
            assert 1 <= r.servings <= 20 and 4 <= len(r.steps) <= 7
            assert all(i["name"] and i["amount"] for i in r.ingredients)
            assert [normalize(k) for k in r.ingredient_keys] == [normalize(i["name"]) for i in r.ingredients]


def test_sample_file_names_are_unique_per_recipe():
    for item in json.loads(SAMPLE_FILE.read_text(encoding="utf-8")):
        names = [normalize(i["name"]) for i in item["ingredients"]]
        assert len(names) == len(set(names)), item["title"]
```

`backend/tests/test_recommendations.py`(새 파일). 마지막 테스트는 식약처 전체(약 1,100건) × 재고 60개 스모크다. 재료 12개 중 6개는 레시피마다 다른 없는 이름이라 캐시가 거의 먹지 않는 쪽으로 만들었다:
```python
import time
from datetime import timedelta

from app.ingredients import seoul_today
from app.models import Ingredient, PublicRecipe, StorageLocation, db
from app.recipe_parse import ingredient_key


def add_ingredient(client, name, **fields):
    body = {"name": name, "purchased_on": seoul_today().isoformat(), **fields}
    assert client.post("/api/ingredients", json=body).status_code == 201


def public(rcp_seq, title, names, is_sample=False):
    ingredients = [{"name": n, "amount": "1개"} for n in names]
    return PublicRecipe(
        rcp_seq=rcp_seq,
        title=title,
        servings=2,
        ingredients_text=", ".join(names),
        ingredients=ingredients,
        ingredient_keys=[ingredient_key(n) for n in names],
        steps=["만들어요."],
        is_sample=is_sample,
    )


def add_public(app, *recipes):
    with app.app_context():
        db.session.add_all(recipes)
        db.session.commit()


def recommend(client, query=""):
    res = client.get(f"/api/recommendations{query}")
    assert res.status_code == 200
    return res.get_json()


def test_requires_login(client):
    assert client.get("/api/recommendations").status_code == 401


def test_empty_inventory_recommends_nothing(client, login, app):
    login()
    add_public(app, public("1", "두부조림", ["두부", "간장"]))
    assert recommend(client) == {"mine": [], "public": [], "sample": False, "inventory_count": 0}


def test_public_cards_are_ranked_by_match_rate_with_missing_names(client, login, app):
    login()
    add_public(
        app,
        public("1", "두부조림", ["두부", "간장", "대파", "고춧가루", "설탕", "참기름", "마늘"]),
        public("2", "계란국", ["계란", "대파", "물"]),
        public("3", "잡채", ["당면", "시금치"]),  # 가진 재료가 하나도 없으면 빠진다
        public("4", "가지볶음", ["가지", "대파"]),
    )
    add_ingredient(client, "대파 1단")
    add_ingredient(client, "유정란 계란 10구")
    add_ingredient(client, "두부 (국산)")
    body = recommend(client)
    assert (body["mine"], body["sample"], body["inventory_count"]) == ([], False, 3)
    assert body["public"] == [
        {
            "kind": "public",
            "id": body["public"][0]["id"],
            "title": "계란국",
            "image_url": None,
            "servings": 2,
            "match_rate": 1.0,
            "have_count": 3,  # 물은 늘 있는 것으로 센다
            "total_count": 3,
            "missing": [],
            "urgent_used": 0,
            "urgent_names": [],
            "score": 1.0,
        },
        {**body["public"][1], "title": "가지볶음", "match_rate": 0.5, "have_count": 1, "total_count": 2, "missing": ["가지"], "score": 0.5},
        {
            **body["public"][2],
            "title": "두부조림",
            "match_rate": 0.29,
            "have_count": 2,
            "total_count": 7,
            "missing": ["간장", "고춧가루", "설탕", "참기름", "마늘"],  # 최대 5개
            "score": 0.29,
        },
    ]


def test_urgent_ingredients_add_score_and_are_named(client, login, app):
    login()
    today = seoul_today()
    add_public(
        app,
        public("1", "가나다 비빔밥", ["밥", "두부", "대파", "애호박"]),
        public("2", "라마바 볶음밥", ["밥", "계란", "대파", "당근"]),
    )
    add_ingredient(client, "밥")
    add_ingredient(client, "계란")
    add_ingredient(client, "애호박", expires_on=today.isoformat())  # urgent
    add_ingredient(client, "두부", purchased_on=(today - timedelta(days=30)).isoformat())  # 품목 규칙 danger
    add_ingredient(client, "대파", expires_on=(today + timedelta(days=1)).isoformat())  # urgent
    cards = {c["title"]: c for c in recommend(client)["public"]}
    bibim, fried = cards["가나다 비빔밥"], cards["라마바 볶음밥"]
    assert (bibim["match_rate"], bibim["urgent_names"], bibim["urgent_used"], bibim["score"]) == (1.0, ["두부", "대파", "애호박"], 3, 1.3)
    assert (fried["match_rate"], fried["urgent_names"], fried["urgent_used"], fried["score"]) == (0.75, ["대파"], 1, 0.85)
    assert [c["title"] for c in recommend(client)["public"]] == ["가나다 비빔밥", "라마바 볶음밥"]


def test_mine_section_limit_and_sample_flag(client, login, app):
    login()
    add_ingredient(client, "계란")
    for title in ["가 계란찜", "나 계란말이", "다 계란국"]:
        assert client.post("/api/recipes", json={"title": title, "ingredients": [{"name": "계란", "amount": "2개"}, {"name": "Milk"}]}).status_code == 201
    add_public(app, public("SAMPLE-01", "계란말이", ["계란"], is_sample=True), public("SAMPLE-02", "계란국", ["계란", "물"], is_sample=True))

    body = recommend(client, "?limit=2")
    assert [(c["kind"], c["title"], c["missing"]) for c in body["mine"]] == [("mine", "가 계란찜", ["Milk"]), ("mine", "나 계란말이", ["Milk"])]
    assert [c["title"] for c in body["public"]] == ["계란국", "계란말이"]
    assert body["sample"] is True
    assert len(recommend(client, "?limit=0")["mine"]) == 1
    assert len(recommend(client, "?limit=abc")["mine"]) == 3

    add_public(app, public("100", "계란밥", ["계란", "밥"]))
    assert recommend(client)["sample"] is False


def test_other_users_recipes_and_inventory_are_not_used(client, login, app):
    login("owner")
    add_ingredient(client, "계란")
    client.post("/api/recipes", json={"title": "주인 계란찜", "ingredients": [{"name": "계란"}]})
    login("other")
    assert recommend(client) == {"mine": [], "public": [], "sample": False, "inventory_count": 0}


def test_recommendations_are_fast_enough_for_full_public_db(client, login, app):
    # 식약처 전체(약 1,100건) × 재고 60개 스모크: 1.5초 안 (스펙 4절 매칭 규칙 그대로)
    user = login()
    words = ["대파", "양파", "두부", "계란", "감자", "당근", "애호박", "돼지고기", "소고기", "닭가슴살",
             "김치", "콩나물", "시금치", "표고버섯", "고추", "마늘", "간장", "고추장", "된장", "설탕"]
    with app.app_context():
        location = StorageLocation.query.filter_by(user_id=user.id).first()
        db.session.add_all(
            Ingredient(user_id=user.id, location_id=location.id, name=f"{words[i % 20]} {i}" if i >= 20 else words[i], purchased_on=seoul_today())
            for i in range(60)
        )
        db.session.add_all(
            # 재료 12개 중 6개는 재고에 있는 이름, 6개는 레시피마다 다른 없는 이름(캐시가 거의 안 먹는 쪽)
            public(str(n), f"레시피 {n}", [words[(n + j) % 20] if j % 2 == 0 else f"양념{n}-{j}" for j in range(12)])
            for n in range(1100)
        )
        db.session.commit()

    started = time.perf_counter()
    body = recommend(client)
    elapsed = time.perf_counter() - started
    assert len(body["public"]) == 20
    assert body["public"][0]["total_count"] == 12
    assert elapsed < 1.5, f"{elapsed:.2f}s"
```

- [ ] **Step 2: 실패 확인**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning tests/test_public_recipes.py; .venv/bin/pytest -q -W error::DeprecationWarning tests/test_recommendations.py
```
Expected:
- 첫 실행: `Interrupted: 1 error during collection` (`app.public_recipes`가 없어 ImportError).
- 둘째 실행: `7 failed`. 라우트가 없어 `/api/<path>` 404로 떨어진다(`test_requires_login`도 401이 아니라 404).

- [ ] **Step 3: 예시 레시피 데이터**

`backend/app/data/sample_recipes.json`(새 파일). 어느 출처에서도 옮기지 않고 가정식 기준으로 직접 썼다. 사진은 없다(`image_url` null):
```json
[
  {
    "rcp_seq": "SAMPLE-01",
    "title": "된장찌개",
    "category": "국&찌개",
    "method": "끓이기",
    "servings": 2,
    "ingredients": [
      {"name": "된장", "amount": "2큰술"},
      {"name": "두부", "amount": "1/2모"},
      {"name": "애호박", "amount": "1/3개"},
      {"name": "감자", "amount": "1개"},
      {"name": "양파", "amount": "1/4개"},
      {"name": "대파", "amount": "1/2대"},
      {"name": "청양고추", "amount": "1개"},
      {"name": "다진 마늘", "amount": "1작은술"},
      {"name": "물", "amount": "500ml"}
    ],
    "steps": [
      "감자와 애호박, 양파는 한입 크기로 썰고 두부는 깍둑썰기해요.",
      "냄비에 물을 붓고 된장을 풀어 끓여요.",
      "끓어오르면 감자를 먼저 넣고 5분 정도 익혀요.",
      "애호박, 양파, 다진 마늘을 넣고 3분 더 끓여요.",
      "두부와 대파, 청양고추를 넣고 한소끔 끓이면 완성이에요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-02",
    "title": "김치찌개",
    "category": "국&찌개",
    "method": "끓이기",
    "servings": 2,
    "ingredients": [
      {"name": "김치", "amount": "300g"},
      {"name": "돼지고기", "amount": "150g"},
      {"name": "두부", "amount": "1/2모"},
      {"name": "대파", "amount": "1/2대"},
      {"name": "고춧가루", "amount": "1큰술"},
      {"name": "다진 마늘", "amount": "1작은술"},
      {"name": "식용유", "amount": "1큰술"},
      {"name": "물", "amount": "400ml"}
    ],
    "steps": [
      "김치와 돼지고기는 한입 크기로 썰어요.",
      "냄비에 식용유를 두르고 돼지고기를 볶다가 김치를 넣어 함께 볶아요.",
      "물과 고춧가루, 다진 마늘을 넣고 중불에서 10분 정도 끓여요.",
      "두부와 대파를 넣고 5분 더 끓이면 완성이에요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-03",
    "title": "계란말이",
    "category": "반찬",
    "method": "굽기",
    "servings": 2,
    "ingredients": [
      {"name": "계란", "amount": "4개"},
      {"name": "대파", "amount": "1/4대"},
      {"name": "당근", "amount": "20g"},
      {"name": "소금", "amount": "약간"},
      {"name": "식용유", "amount": "1큰술"}
    ],
    "steps": [
      "대파와 당근은 잘게 다져요.",
      "계란을 풀고 다진 채소와 소금을 넣어 섞어요.",
      "약불로 달군 팬에 식용유를 얇게 두르고 계란물을 1/3만 부어요.",
      "반쯤 익으면 한쪽으로 돌돌 말고, 남은 계란물을 나눠 부으며 이어서 말아요.",
      "한 김 식힌 뒤 먹기 좋게 썰어요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-04",
    "title": "두부조림",
    "category": "반찬",
    "method": "끓이기",
    "servings": 2,
    "ingredients": [
      {"name": "두부", "amount": "1모"},
      {"name": "간장", "amount": "3큰술"},
      {"name": "고춧가루", "amount": "1큰술"},
      {"name": "설탕", "amount": "1작은술"},
      {"name": "다진 마늘", "amount": "1작은술"},
      {"name": "대파", "amount": "1/2대"},
      {"name": "참기름", "amount": "1작은술"},
      {"name": "물", "amount": "100ml"}
    ],
    "steps": [
      "두부는 1cm 두께로 썰어 키친타월로 물기를 닦아요.",
      "팬에 두부를 올려 앞뒤로 노릇하게 부쳐요.",
      "간장, 고춧가루, 설탕, 다진 마늘, 물을 섞어 양념장을 만들어요.",
      "두부 위에 양념장을 끼얹고 약불에서 국물이 자작해질 때까지 졸여요.",
      "송송 썬 대파와 참기름을 올려 마무리해요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-05",
    "title": "애호박볶음",
    "category": "반찬",
    "method": "볶기",
    "servings": 2,
    "ingredients": [
      {"name": "애호박", "amount": "1개"},
      {"name": "양파", "amount": "1/4개"},
      {"name": "새우젓", "amount": "1작은술"},
      {"name": "다진 마늘", "amount": "1/2작은술"},
      {"name": "식용유", "amount": "1큰술"},
      {"name": "참깨", "amount": "약간"}
    ],
    "steps": [
      "애호박은 반달 모양으로, 양파는 채 썰어요.",
      "팬에 식용유를 두르고 다진 마늘을 볶아 향을 내요.",
      "애호박과 양파를 넣고 중불에서 2분 정도 볶아요.",
      "새우젓으로 간을 맞추고 참깨를 뿌려요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-06",
    "title": "제육볶음",
    "category": "일품",
    "method": "볶기",
    "servings": 2,
    "ingredients": [
      {"name": "돼지고기 앞다리살", "amount": "300g"},
      {"name": "양파", "amount": "1/2개"},
      {"name": "대파", "amount": "1대"},
      {"name": "고추장", "amount": "2큰술"},
      {"name": "고춧가루", "amount": "1큰술"},
      {"name": "간장", "amount": "1큰술"},
      {"name": "설탕", "amount": "1큰술"},
      {"name": "다진 마늘", "amount": "1큰술"},
      {"name": "참기름", "amount": "1작은술"}
    ],
    "steps": [
      "고추장, 고춧가루, 간장, 설탕, 다진 마늘을 섞어 양념장을 만들어요.",
      "돼지고기에 양념장을 넣고 버무려 10분 정도 재워요.",
      "양파는 채 썰고 대파는 어슷하게 썰어요.",
      "달군 팬에 고기를 넣고 센불에서 볶아요.",
      "고기가 거의 익으면 양파와 대파를 넣고 2분 더 볶아요.",
      "불을 끄고 참기름을 둘러 마무리해요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-07",
    "title": "감자조림",
    "category": "반찬",
    "method": "끓이기",
    "servings": 2,
    "ingredients": [
      {"name": "감자", "amount": "2개"},
      {"name": "양파", "amount": "1/2개"},
      {"name": "간장", "amount": "3큰술"},
      {"name": "올리고당", "amount": "1큰술"},
      {"name": "설탕", "amount": "1작은술"},
      {"name": "식용유", "amount": "1큰술"},
      {"name": "참깨", "amount": "약간"},
      {"name": "물", "amount": "150ml"}
    ],
    "steps": [
      "감자는 깍둑썰기해 찬물에 5분 담가 전분을 빼요.",
      "양파는 감자와 비슷한 크기로 썰어요.",
      "팬에 식용유를 두르고 감자를 겉면이 투명해질 때까지 볶아요.",
      "물, 간장, 설탕을 넣고 뚜껑을 덮어 중약불에서 10분 졸여요.",
      "양파와 올리고당을 넣고 국물이 거의 없어질 때까지 졸인 뒤 참깨를 뿌려요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-08",
    "title": "콩나물무침",
    "category": "반찬",
    "method": "기타",
    "servings": 2,
    "ingredients": [
      {"name": "콩나물", "amount": "200g"},
      {"name": "대파", "amount": "1/4대"},
      {"name": "다진 마늘", "amount": "1/2작은술"},
      {"name": "소금", "amount": "1/2작은술"},
      {"name": "참기름", "amount": "1큰술"},
      {"name": "참깨", "amount": "약간"}
    ],
    "steps": [
      "콩나물은 깨끗이 씻어 끓는 물에 소금을 조금 넣고 뚜껑을 덮은 채 4분 데쳐요.",
      "데친 콩나물은 체에 밭쳐 한 김 식혀요.",
      "대파는 잘게 썰어요.",
      "콩나물에 대파, 다진 마늘, 소금, 참기름, 참깨를 넣고 살살 무쳐요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-09",
    "title": "계란국",
    "category": "국&찌개",
    "method": "끓이기",
    "servings": 2,
    "ingredients": [
      {"name": "계란", "amount": "2개"},
      {"name": "대파", "amount": "1/3대"},
      {"name": "국간장", "amount": "1큰술"},
      {"name": "소금", "amount": "약간"},
      {"name": "물", "amount": "600ml"}
    ],
    "steps": [
      "냄비에 물을 붓고 끓여요.",
      "끓어오르면 국간장을 넣고 소금으로 간을 맞춰요.",
      "계란을 풀어 냄비에 천천히 둘러 붓고 젓지 않고 30초 기다려요.",
      "송송 썬 대파를 넣고 불을 꺼요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-10",
    "title": "대파 계란볶음밥",
    "category": "밥",
    "method": "볶기",
    "servings": 1,
    "ingredients": [
      {"name": "밥", "amount": "1공기"},
      {"name": "계란", "amount": "2개"},
      {"name": "대파", "amount": "1대"},
      {"name": "간장", "amount": "1작은술"},
      {"name": "소금", "amount": "약간"},
      {"name": "식용유", "amount": "2큰술"}
    ],
    "steps": [
      "대파는 잘게 송송 썰어요.",
      "팬에 식용유를 두르고 대파를 볶아 파기름을 내요.",
      "대파를 한쪽으로 밀고 계란을 넣어 스크램블해요.",
      "밥을 넣고 고루 섞으며 볶아요.",
      "팬 가장자리에 간장을 둘러 향을 내고 소금으로 간을 맞춰요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-11",
    "title": "어묵볶음",
    "category": "반찬",
    "method": "볶기",
    "servings": 2,
    "ingredients": [
      {"name": "어묵", "amount": "3장"},
      {"name": "양파", "amount": "1/4개"},
      {"name": "당근", "amount": "20g"},
      {"name": "간장", "amount": "1큰술"},
      {"name": "올리고당", "amount": "1큰술"},
      {"name": "다진 마늘", "amount": "1/2작은술"},
      {"name": "식용유", "amount": "1큰술"}
    ],
    "steps": [
      "어묵은 뜨거운 물을 부어 기름기를 빼고 길쭉하게 썰어요.",
      "양파와 당근은 채 썰어요.",
      "팬에 식용유를 두르고 다진 마늘, 양파, 당근을 볶아요.",
      "어묵을 넣고 간장과 올리고당을 넣어 1~2분 더 볶아요."
    ]
  },
  {
    "rcp_seq": "SAMPLE-12",
    "title": "시금치나물",
    "category": "반찬",
    "method": "기타",
    "servings": 2,
    "ingredients": [
      {"name": "시금치", "amount": "1단"},
      {"name": "국간장", "amount": "1작은술"},
      {"name": "다진 마늘", "amount": "1/2작은술"},
      {"name": "소금", "amount": "약간"},
      {"name": "참기름", "amount": "1큰술"},
      {"name": "참깨", "amount": "약간"}
    ],
    "steps": [
      "시금치는 뿌리를 다듬고 흐르는 물에 씻어요.",
      "끓는 물에 소금을 조금 넣고 시금치를 30초만 데쳐요.",
      "찬물에 헹궈 물기를 꼭 짜고 먹기 좋은 길이로 썰어요.",
      "국간장, 다진 마늘, 소금, 참기름을 넣고 조물조물 무친 뒤 참깨를 뿌려요."
    ]
  }
]
```

- [ ] **Step 4: 동기화·예시 레시피 CLI**

`openapi.foodsafetykorea.go.kr`은 http·https 모두 200이다(2026-09-13 확인, 샘플 키 `sample`로 5건). URL 경로에 인증키가 들어가므로 https로 부른다. 결정 파일의 http 주소와 다른 점은 이것뿐이다.

`backend/app/public_recipes.py`(새 파일):
```python
"""식약처 공공 레시피 동기화·예시 레시피 CLI. 화면 API는 recipes.py에 있다."""

import json
import math
from pathlib import Path

import click
import requests
from flask import Blueprint, current_app

from .models import PublicRecipe, db
from .recipe_parse import ingredient_key, parse_ingredients, parse_servings, split_steps

bp = Blueprint("public_recipes", __name__, cli_group=None)  # 명령을 `flask sync-public-recipes`처럼 최상위에 둔다

# http도 되지만 URL에 인증키가 들어가므로 https로 부른다 (2026-09-13 https 200 확인)
API_URL = "https://openapi.foodsafetykorea.go.kr/api/{key}/COOKRCP01/json/{start}/{end}"
PAGE_SIZE = 1000
SAMPLE_FILE = Path(__file__).parent / "data" / "sample_recipes.json"


def _short(value, limit):
    value = value.strip() if isinstance(value, str) else ""
    return value[:limit] or None


def _kcal(value):
    try:
        kcal = float(value)
    except (TypeError, ValueError):
        return None
    return kcal if math.isfinite(kcal) else None


def row_fields(row):
    """COOKRCP01 한 행 → PublicRecipe 필드."""
    title = _short(row.get("RCP_NM"), 120) or "이름 없는 레시피"
    parts = row.get("RCP_PARTS_DTLS") if isinstance(row.get("RCP_PARTS_DTLS"), str) else ""
    ingredients = parse_ingredients(parts, title)
    return {
        "rcp_seq": str(row["RCP_SEQ"]).strip()[:20],
        "title": title,
        "category": _short(row.get("RCP_PAT2"), 30),
        "method": _short(row.get("RCP_WAY2"), 30),
        "kcal": _kcal(row.get("INFO_ENG")),
        "servings": parse_servings(parts),
        "ingredients_text": parts,
        "ingredients": ingredients,
        "ingredient_keys": [ingredient_key(i["name"]) for i in ingredients],
        "steps": split_steps(row),
        "image_url": _short(row.get("ATT_FILE_NO_MAIN"), 500),
        "is_sample": False,
    }


def sample_fields(item):
    """sample_recipes.json 한 항목 → PublicRecipe 필드."""
    ingredients = item["ingredients"]
    return {
        "rcp_seq": item["rcp_seq"],
        "title": item["title"],
        "category": item["category"],
        "method": item["method"],
        "kcal": None,
        "servings": item["servings"],
        "ingredients_text": ", ".join(f"{i['name']} {i['amount']}" for i in ingredients),
        "ingredients": ingredients,
        "ingredient_keys": [ingredient_key(i["name"]) for i in ingredients],
        "steps": item["steps"],
        "image_url": None,
        "is_sample": True,
    }


def upsert(items):
    """rcp_seq 기준으로 넣거나 바꾼다. (새로 넣은 수, 바꾼 수)"""
    by_seq = {r.rcp_seq: r for r in PublicRecipe.query.all()}
    created = updated = 0
    for fields in items:
        recipe = by_seq.get(fields["rcp_seq"])
        if recipe is None:
            by_seq[fields["rcp_seq"]] = recipe = PublicRecipe(**fields)
            db.session.add(recipe)
            created += 1
        else:
            for key, value in fields.items():
                setattr(recipe, key, value)
            updated += 1
    db.session.commit()
    return created, updated


def fetch_rows(key):
    """전체 행을 PAGE_SIZE씩 받는다. 한 페이지라도 실패하면 아무것도 쓰지 않고 멈춘다."""
    rows, start, total = [], 1, None
    while total is None or start <= total:
        end = start + PAGE_SIZE - 1
        try:
            res = requests.get(API_URL.format(key=key, start=start, end=end), timeout=30)
            res.raise_for_status()
            body = res.json()["COOKRCP01"]
            code = body["RESULT"]["CODE"]
            page = body.get("row") or []
            total = int(body.get("total_count") or 0)
        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            # 요청 URL에 인증키가 들어 있으니 예외 내용은 찍지 않는다
            raise click.ClickException(f"식약처 레시피를 받지 못했어요({start}~{end}번, {type(e).__name__}).")
        if code == "INFO-200":  # 해당하는 데이터가 없음
            break
        if code != "INFO-000":
            raise click.ClickException(f"식약처 API가 오류를 돌려줬어요({code}).")
        if not page:
            break
        rows.extend(page)
        start = end + 1
    return rows


@bp.cli.command("sync-public-recipes")
def sync_public_recipes():
    """식약처 COOKRCP01 레시피 전체를 받아 public_recipes에 넣는다."""
    key = current_app.config["FOODSAFETY_API_KEY"]
    if not key:
        raise click.ClickException(
            "FOODSAFETY_API_KEY가 없어요. 키 없이 화면을 확인하려면 flask seed-sample-recipes로 예시 레시피를 넣어주세요."
        )
    items = [row_fields(r) for r in fetch_rows(key) if isinstance(r, dict) and str(r.get("RCP_SEQ") or "").strip()]
    # 진짜 레시피를 받았으면 예시 레시피는 지운다(내 레시피로 저장한 복사본은 public_recipe_id만 비워진다)
    removed = PublicRecipe.query.filter_by(is_sample=True).delete() if items else 0
    created, updated = upsert(items)
    click.echo(f"식약처 레시피 {len(items)}건을 받았어요. 새로 {created}건, 바뀐 것 {updated}건, 예시 레시피 {removed}건은 지웠어요.")


@bp.cli.command("seed-sample-recipes")
def seed_sample_recipes():
    """키 없이 추천 화면을 확인하는 예시 레시피 12개를 넣는다(여러 번 실행해도 같다)."""
    items = [sample_fields(item) for item in json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))]
    created, updated = upsert(items)
    click.echo(f"예시 레시피 {len(items)}개를 넣었어요. 새로 {created}개, 바뀐 것 {updated}개.")
```

`backend/app/__init__.py`:
- `app.config.from_mapping(...)`의 `AI_SCAN_BURST_LIMIT=...` 줄 아래에 추가한다:
```python
        FOODSAFETY_API_KEY=os.environ.get("FOODSAFETY_API_KEY") or None,
```
- 블루프린트 import·등록에 public_recipes를 추가한다(알파벳 순서 유지. 라우트는 없고 CLI 명령만 등록한다):
```python
    from .locations import bp as locations_bp
    from .public_recipes import bp as public_recipes_bp
    from .recipes import bp as recipes_bp
```
```python
    app.register_blueprint(locations_bp)
    app.register_blueprint(public_recipes_bp)
    app.register_blueprint(recipes_bp)
```

- [ ] **Step 5: 추천 API**

`backend/app/recipes.py`에서 `@bp.get("/recipes")`(목록) 바로 위에 추가한다:
```python
@bp.get("/recommendations")
@login_required
def recommendations():
    """보유 재료 일치율 순 추천(스펙 4절). 재고와 겹치는 재료가 하나도 없는 레시피는 뺀다."""
    limit = min(max(request.args.get("limit", 20, type=int), 1), 50)
    stock = inventory(g.user.id)
    urgent = {name for name, is_urgent in stock if is_urgent}
    # ponytail: 서로 다른 재료 키마다 재고 전체와 names_match로 비교한다 — 최악 O(레시피 × 재료 × 재고), 키가 겹치면 캐시로 줄어든다.
    # 공공 레시피 1,100건 × 재고 60개에서 1.5초 안(테스트). 느려지면 재고 이름 단어로 역색인을 만들어 후보만 비교한다.
    matches = {}

    def card(kind, recipe_id, title, image_url, servings, keys, names):
        results = []
        for key in keys:
            if key not in matches:
                matches[key] = match_key(key, stock)
            results.append(matches[key])
        matched = [name for name, _ in results if name]
        if not matched:
            return None
        have = sum(1 for _, has in results if has)
        urgent_names = list(dict.fromkeys(name for name in matched if name in urgent))
        rate = round(have / len(keys), 2)
        return {
            "kind": kind,
            "id": recipe_id,
            "title": title,
            "image_url": image_url,
            "servings": servings,
            "match_rate": rate,
            "have_count": have,
            "total_count": len(keys),
            "missing": [name for name, (_, has) in zip(names, results) if not has][:5],
            "urgent_used": len(urgent_names),
            "urgent_names": urgent_names,
            "score": round(rate + 0.1 * len(urgent_names), 2),
        }

    def ranked(cards):
        return sorted((c for c in cards if c), key=lambda c: (-c["score"], c["title"], c["id"]))[:limit]

    mine = ranked(
        card("mine", r.id, r.title, r.image_url, r.servings, [ingredient_key(i["name"]) for i in r.ingredients], [i["name"] for i in r.ingredients])
        for r in Recipe.query.filter_by(user_id=g.user.id)
    )
    rows = db.session.query(
        PublicRecipe.id, PublicRecipe.title, PublicRecipe.image_url, PublicRecipe.servings, PublicRecipe.ingredient_keys, PublicRecipe.is_sample
    ).all()
    public = ranked(card("public", r.id, r.title, r.image_url, r.servings, r.ingredient_keys, r.ingredient_keys) for r in rows)
    return jsonify(mine=mine, public=public, sample=bool(rows) and all(r.is_sample for r in rows), inventory_count=len(stock))
```

- [ ] **Step 6: 스펙·배포 문서 갱신**

`docs/superpowers/specs/2026-09-13-recipe-ai-design.md`에서 아래 줄을 각각 통째로 바꾼다.

4절 일치율:
```text
- **일치율:** (보유한 레시피 재료 수 / 레시피 재료 수). 임박 재료를 쓰면 정렬 가산점(+0.1/개).
```
→
```text
- **일치율:** (보유한 레시피 재료 수 / 레시피 재료 수). 임박 재료를 쓰면 정렬 가산점(+0.1/개). `물`은 늘 있는 것으로 센다. 재고와 겹치는 재료가 없는 레시피는 추천하지 않는다.
```

5절 표 recommendations:
```text
| GET | `/api/recommendations` | `{mine:[...], public:[...]}` 일치율 순, 각 항목에 missing 재료 |
```
→
```text
| GET | `/api/recommendations?limit=20` | `{mine:[...], public:[...], sample, inventory_count}` 점수 순. 항목: kind, id, title, image_url, servings, match_rate, have_count, total_count, missing(최대 5), urgent_used, urgent_names, score(= match_rate + 0.1 × urgent_used) |
```

5절 CLI:
```text
CLI: `flask sync-public-recipes` — 식약처 COOKRCP01 전체(약 1,100건)를 1,000건 단위로 받아 upsert.
```
→
```text
CLI: `flask sync-public-recipes` — 식약처 COOKRCP01 전체(약 1,100건)를 1,000건 단위로 받아 upsert(`FOODSAFETY_API_KEY` 필요, 받으면 예시 레시피는 지움). `flask seed-sample-recipes` — 키 없이 화면을 확인하는 직접 쓴 예시 레시피 12개(`is_sample`).
```

`docs/deploy.md` 환경 변수 표:
```text
| `FOODSAFETY_API_KEY` | 선택 | 레시피 추천 구현 후 | 식약처 공공데이터포털(COOKRCP01) |
```
→
```text
| `FOODSAFETY_API_KEY` | 선택 | 3단계 레시피 추천. 배포 후 한 번 `flask sync-public-recipes`(없으면 `flask seed-sample-recipes` 예시 레시피) | 식약처 공공데이터포털(COOKRCP01) |
```

- [ ] **Step 7: 통과 확인 (SQLite와 PostgreSQL)**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q -W error::DeprecationWarning && TEST_DATABASE_URL=postgresql://localhost/recipe_ai_test TEST_MIGRATE_DATABASE_URL=postgresql://localhost/recipe_ai_migrate .venv/bin/pytest -q -W error::DeprecationWarning --durations=1
```
Expected: 두 실행 모두 실패 0, 경고 0 (`297 passed`). `--durations=1`의 가장 느린 테스트는 `test_recommendations_are_fast_enough_for_full_public_db`이고 1.5초보다 한참 짧다(프로토타입: SQLite 0.76초, PostgreSQL 0.87초).

- [ ] **Step 8: 개발 DB에 예시 레시피 넣기**

키 없이 추천 화면을 보려면 개발 DB에 예시 레시피를 넣는다. `public_recipes` 행만 넣고 다른 데이터는 건드리지 않는다. 개발 서버는 자동으로 넣지 않는다.

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app seed-sample-recipes && .venv/bin/flask --app app seed-sample-recipes
```
Expected: 첫 줄 `예시 레시피 12개를 넣었어요. 새로 12개, 바뀐 것 0개.`, 둘째 줄 `… 새로 0개, 바뀐 것 12개.`

- [ ] **Step 9: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend docs/superpowers/specs/2026-09-13-recipe-ai-design.md docs/deploy.md && git status --short && git commit -m "feat: 식약처 레시피 동기화·예시 레시피 CLI, 보유 재료 일치율 추천 API" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"
```

---

### Task 3: 경로표·파라미터, 탭 표시, `useResource`, 구입일 max, 재고 요약 문구

새 화면은 만들지 않는다. 레시피 경로는 모두 지금의 `준비 중` 화면으로 연결해 둔다(T4에서 진짜 화면으로 바꾼다).

**Files:**
- Create: `frontend/src/useResource.ts`
- Modify: `frontend/src/useHashRoute.ts`, `frontend/src/App.tsx`, `frontend/src/components/TabBar.tsx`, `frontend/src/pages/More.tsx`, `frontend/src/pages/Tools.tsx`, `frontend/src/components/IngredientForm.tsx`, `frontend/src/pages/Fridge.tsx`
- Modify (문서): `docs/site/product.html`, `docs/site/portfolio.html`

**Interfaces:**
- Consumes: 기존 `api`, `User`, `ComingSoon`, `Fridge`, `More`, `Tools`, `localToday`
- Produces:
  - `useHashRoute.ts`: `ROUTES`(`"/"`, `"/recipes"`, `"/recipes/new"`, `"/recipes/mine/:id"`, `"/recipes/mine/:id/edit"`, `"/recipes/public/:id"`, `"/shopping"`, `"/meals"`, `"/more"`, `"/tools"`), 타입 `RoutePattern`, `Route {path, pattern, params}`, `matchRoute(path) -> Route | null`(`:id`는 숫자만), `useHashRoute(): Route`(모르는 경로는 `#/`로 바꾸고 `/`), `navigate(path, {replace?})`(기본은 히스토리에 쌓고 `history.state.from`을 남김, replace는 지금 칸 교체), `goBack(fallback)`(앱 안에서 왔으면 `history.back()`, 아니면 fallback으로 replace)
  - `useResource.ts`: `useResource<T>(url) -> {data: T | undefined, error: string, reload}`(마지막 응답을 모듈 Map에 두고 먼저 보여 준 뒤 다시 받는다), `forgetResources(prefix = "")`
  - `App.tsx`: `PAGES: Record<RoutePattern, (props: {route, user, onLogout}) => ReactNode>`, 경로별 스크롤 위치 복원(`history.scrollRestoration = "manual"`), 로그아웃·401에서 `forgetResources()`
  - `TabBar({ path })`: 레시피 탭은 `/recipes`와 `/recipes/…` 모두 선택 표시
  - `More`는 `navigate("/tools")`, `Tools`는 `useResource("/api/tools")`와 `goBack("/more")`. 재고(`Fridge`)는 불러오는 자원이 4개이고 시트들이 `load`를 받아 써서 이번에는 그대로 둔다.
  - `IngredientForm` 구입일 입력 `max={localToday()}`
  - 재고 요약 문구 `재료 N개 · 빨리 먹어야 할 재료 M개`(사용자 결정 2026-09-13, 이전 `곧 먹어야 할`). 앱 코드에는 이 한 곳뿐이다. 승인된 옛 시안(`docs/design/fridge-1b`, `scan-2`)과 지난 계획서는 기록이라 바꾸지 않는다. 소개 페이지(`docs/site`) 두 곳은 화면 그림이라 같이 바꾼다.

(브랜치: `feature/public-recipes-sync`가 main에 병합된 뒤 시작한다.)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/recipes-routing
```

- [ ] **Step 1: 경로표**

`frontend/src/useHashRoute.ts`를 교체한다:
```ts
import { useEffect, useState } from "react";

// ponytail: 라우터 라이브러리 대신 브라우저 해시(#/recipes/mine/3) + 작은 경로표. 뒤로가기가 그대로 동작한다.
// 경로 모양이 복잡해지면(중첩 레이아웃, 검색 파라미터) react-router의 createHashRouter로 교체.
export const ROUTES = [
  "/",
  "/recipes",
  "/recipes/new",
  "/recipes/mine/:id",
  "/recipes/mine/:id/edit",
  "/recipes/public/:id",
  "/shopping",
  "/meals",
  "/more",
  "/tools",
] as const;

export type RoutePattern = (typeof ROUTES)[number];

export interface Route {
  path: string;
  pattern: RoutePattern;
  params: Record<string, string>;
}

/** "/recipes/mine/3" → { pattern: "/recipes/mine/:id", params: { id: "3" } }. :id는 숫자만. 모르는 경로는 null */
export function matchRoute(path: string): Route | null {
  const parts = path.split("/");
  for (const pattern of ROUTES) {
    const want = pattern.split("/");
    if (want.length !== parts.length) continue;
    const params: Record<string, string> = {};
    const ok = want.every((segment, i) => {
      if (!segment.startsWith(":")) return segment === parts[i];
      params[segment.slice(1)] = parts[i];
      return /^\d+$/.test(parts[i]);
    });
    if (ok) return { path, pattern, params };
  }
  return null;
}

const currentRoute = (): Route => {
  let path = location.hash.replace(/^#/, "") || "/";
  if (path.length > 1) path = path.replace(/\/$/, ""); // "/tools/" → "/tools"
  const route = matchRoute(path);
  if (route) return route;
  location.replace("#/");
  return { path: "/", pattern: "/", params: {} };
};

/**
 * 화면 이동. 기본은 히스토리에 쌓아 폰 뒤로가기로 돌아올 수 있게 한다(상세·폼).
 * replace는 지금 칸을 바꾼다(저장 후 상세로 넘어갈 때). 탭 전환은 TabBar가 location.replace를 쓴다.
 */
export function navigate(path: string, { replace = false } = {}) {
  if (replace) history.replaceState(history.state, "", `#${path}`);
  else history.pushState({ from: location.hash.replace(/^#/, "") || "/" }, "", `#${path}`);
  // pushState·replaceState는 hashchange를 스스로 쏘지 않으므로 직접 알린다.
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** 앱 안에서 들어왔으면 뒤로가기(히스토리·스크롤 유지), 주소로 바로 열었으면 fallback으로 이동 */
export function goBack(fallback: string) {
  if ((history.state as { from?: string } | null)?.from) history.back();
  else navigate(fallback, { replace: true });
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState(currentRoute);
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
```

경로 매칭 확인(Node 24는 `.ts`를 바로 읽는다. 테스트 러너가 없어 한 줄 검사로 둔다):
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && node --input-type=module -e '
import assert from "node:assert/strict";
import { matchRoute } from "./src/useHashRoute.ts";
assert.deepEqual(matchRoute("/recipes/mine/12"), { path: "/recipes/mine/12", pattern: "/recipes/mine/:id", params: { id: "12" } });
assert.equal(matchRoute("/recipes/mine/12/edit").pattern, "/recipes/mine/:id/edit");
assert.equal(matchRoute("/recipes/public/3").params.id, "3");
assert.equal(matchRoute("/recipes/new").pattern, "/recipes/new");
assert.equal(matchRoute("/recipes/mine/abc"), null);
assert.equal(matchRoute("/nope"), null);
assert.equal(matchRoute("/").pattern, "/");
console.log("matchRoute ok");
'
```
Expected: `matchRoute ok`

- [ ] **Step 2: 불러오기 훅**

`frontend/src/useResource.ts`(새 파일):
```ts
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

// ponytail: 탭·상세를 오갈 때 마지막으로 받은 응답을 모듈 Map에 둔다(새로고침하면 비워짐). 먼저 보여 주고 뒤에서 다시 받는다.
// 캐시 무효화가 복잡해지면(여러 화면이 같은 데이터를 고침) TanStack Query 같은 라이브러리로 교체.
const cache = new Map<string, unknown>();

/** prefix로 시작하는 URL의 캐시를 지운다. 저장·삭제 뒤 목록이 옛 내용을 잠깐 보여 주지 않게. "" = 전부(로그아웃) */
export function forgetResources(prefix = "") {
  for (const key of [...cache.keys()]) if (key.startsWith(prefix)) cache.delete(key);
}

/** GET url을 불러온다. 다시 불러오는 동안에도 마지막 data를 유지한다. 오류는 error 문자열로(401은 api()가 처리). */
export function useResource<T>(url: string) {
  const [data, setData] = useState<T | undefined>(() => cache.get(url) as T | undefined);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setError("");
    try {
      const next = await api<T>(url);
      cache.set(url, next);
      setData(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [url]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, reload };
}
```

- [ ] **Step 3: App 경로 → 화면 표**

`frontend/src/App.tsx`를 교체한다:
```tsx
import { Fragment, useCallback, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { ApiError, api, onUnauthorized, type User } from "./api";
import Splash from "./components/Splash";
import TabBar from "./components/TabBar";
import ComingSoon from "./pages/ComingSoon";
import Fridge from "./pages/Fridge";
import Login from "./pages/Login";
import More from "./pages/More";
import Tools from "./pages/Tools";
import { useHashRoute, type Route, type RoutePattern } from "./useHashRoute";
import { forgetResources } from "./useResource";

interface PageProps {
  route: Route;
  user: User;
  onLogout: () => void;
}

// 경로 → 화면. 새 화면은 useHashRoute의 ROUTES와 여기에 한 줄씩 추가한다.
const PAGES: Record<RoutePattern, (props: PageProps) => ReactNode> = {
  "/": ({ user, onLogout }) => <Fridge user={user} onLogout={onLogout} />,
  "/recipes": () => <ComingSoon route="/recipes" />,
  "/recipes/new": () => <ComingSoon route="/recipes" />,
  "/recipes/mine/:id": () => <ComingSoon route="/recipes" />,
  "/recipes/mine/:id/edit": () => <ComingSoon route="/recipes" />,
  "/recipes/public/:id": () => <ComingSoon route="/recipes" />,
  "/shopping": () => <ComingSoon route="/shopping" />,
  "/meals": () => <ComingSoon route="/meals" />,
  "/more": () => <More />,
  "/tools": () => <Tools />,
};

// 경로별 마지막 스크롤 위치: 상세에서 돌아오면 목록을 보던 자리로, 처음 여는 화면은 맨 위로
const scrollTops = new Map<string, number>();
history.scrollRestoration = "manual";

export default function App() {
  // undefined: 확인 중, null: 비로그인
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [offline, setOffline] = useState(false);
  const route = useHashRoute();

  useEffect(() => {
    const onScroll = () => scrollTops.set(route.path, window.scrollY);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [route.path]);

  useLayoutEffect(() => {
    window.scrollTo(0, scrollTops.get(route.path) ?? 0);
  }, [route.path]);

  // 로그아웃·세션 만료: 다른 계정으로 들어와도 이전 사용자의 화면 캐시가 보이지 않게
  const signOut = useCallback(() => {
    forgetResources();
    setUser(null);
  }, []);

  // 시작 화면은 로그인 확인이 끝나고 최소 0.8초가 지날 때까지 보여 준다(너무 빨리 깜빡이지 않게)
  const [minSplashDone, setMinSplashDone] = useState(false);
  const [splashGone, setSplashGone] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setMinSplashDone(true), 800);
    return () => clearTimeout(timer);
  }, []);
  const hideSplash = useCallback(() => setSplashGone(true), []);
  const splash = !splashGone && <Splash leaving={minSplashDone && (user !== undefined || offline)} onGone={hideSplash} />;

  const checkMe = () => {
    setOffline(false);
    setUser(undefined);
    api<User>("/api/me").then(setUser, (e: unknown) => {
      if (e instanceof ApiError && e.status === 0) setOffline(true);
      else if (!(e instanceof ApiError && e.status === 401)) setUser(null); // 401은 전역 핸들러가 처리
    });
  };

  useEffect(() => {
    onUnauthorized(signOut);
    checkMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (offline)
    return (
      <>
        {splash}
        <div className="center">
          <p>서버에 연결할 수 없어요.</p>
          <button className="btn primary inline" onClick={checkMe}>
            다시 시도
          </button>
        </div>
      </>
    );

  if (user === undefined) return splash || <p className="center muted">불러오는 중…</p>;
  if (user === null)
    return (
      <>
        {splash}
        <Login onLogin={setUser} />
      </>
    );
  return (
    <>
      {splash}
      {/* key: 경로가 바뀌면 화면을 새로 만든다(상세 3 → 상세 4에서 이전 데이터가 남지 않게) */}
      <Fragment key={route.path}>{PAGES[route.pattern]({ route, user, onLogout: signOut })}</Fragment>
      <TabBar path={route.path} />
    </>
  );
}
```

`frontend/src/components/TabBar.tsx`를 교체한다:
```tsx
import Icon, { type IconName } from "./Icon";

interface Tab {
  path: string;
  label: string;
  icon: IconName;
  match: (path: string) => boolean;
}

// 탭 순서(사용자 결정 2026-09-13): 재고 · 레시피 · 장보기 · 식단 · 더보기. 아직 없는 기능 탭은 '준비 중' 화면을 보여 준다(사용자 결정).
export const TABS: Tab[] = [
  { path: "/", label: "재고", icon: "fridge", match: (r) => r === "/" },
  { path: "/recipes", label: "레시피", icon: "book", match: (r) => r === "/recipes" || r.startsWith("/recipes/") },
  { path: "/shopping", label: "장보기", icon: "cart", match: (r) => r === "/shopping" },
  { path: "/meals", label: "식단", icon: "calendar", match: (r) => r === "/meals" },
  { path: "/more", label: "더보기", icon: "menu", match: (r) => r === "/more" || r === "/tools" },
];

export default function TabBar({ path }: { path: string }) {
  return (
    <nav className="tabbar" aria-label="주요 메뉴">
      {TABS.map((tab) => (
        <a
          key={tab.path}
          className="tab"
          href={`#${tab.path}`}
          aria-current={tab.match(path) ? "page" : undefined}
          onClick={(e) => {
            e.preventDefault();
            location.replace("#" + tab.path); // 탭 전환은 히스토리를 쌓지 않는다
          }}
        >
          <Icon name={tab.icon} size={24} />
          <span>{tab.label}</span>
        </a>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: 더보기·주방 도구를 새 이동 함수로**

`frontend/src/pages/More.tsx`:
- `import { useInstallPrompt } from "../install";` 아래에 `import { navigate } from "../useHashRoute";`
- 목록 링크의 `onClick` 본문을 교체한다:
```tsx
              onClick={(e) => {
                e.preventDefault();
                navigate(item.path);
              }}
```

`frontend/src/pages/Tools.tsx`를 교체한다(동작은 같고 불러오기·뒤로가기만 바뀐다):
```tsx
import { useState } from "react";
import { api, type KitchenTool, type KitchenToolInput } from "../api";
import Icon from "../components/Icon";
import ToolForm from "../components/ToolForm";
import { cycleLabel, formatDate, withJosa } from "../format";
import { goBack } from "../useHashRoute";
import { useResource } from "../useResource";

function subtitle(tool: KitchenTool): string {
  const parts: string[] = [tool.category];
  if (tool.check_every_months) parts.push(`${cycleLabel(tool.check_every_months)}마다 점검`);
  if (tool.last_checked_on) parts.push(`마지막 점검 ${formatDate(tool.last_checked_on)}`);
  else if (tool.bought_on) parts.push(`${formatDate(tool.bought_on)} 구매`);
  return parts.join(" · ");
}

export default function Tools() {
  const { data: tools, error, reload: load } = useResource<KitchenTool[]>("/api/tools");
  const [editing, setEditing] = useState<KitchenTool | "new" | null>(null);

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
    if (!editing || editing === "new" || !confirm(`${withJosa(editing.name, "을", "를")} 삭제할까요?`)) return;
    await api(`/api/tools/${editing.id}`, { method: "DELETE" });
    setEditing(null);
    await load();
  };

  const due = tools?.filter((t) => t.is_due).length ?? 0;

  return (
    <div className="page">
      <a
        className="back-link"
        href="#/more"
        onClick={(e) => {
          e.preventDefault();
          goBack("/more");
        }}
      >
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

      {tools === undefined ? (
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

- [ ] **Step 5: 구입일 max, 재고 요약 문구**

`frontend/src/components/IngredientForm.tsx`의 구입일 입력에 `max`를 추가한다:
```tsx
            <input
              className="input"
              id="ingredient-purchased"
              type="date"
              value={purchasedOn}
              max={localToday()}
              onChange={(e) => setPurchasedOn(e.target.value)}
              required
            />
```

`frontend/src/pages/Fridge.tsx`: `` ` · 곧 먹어야 할 재료 ${soon}개` `` → `` ` · 빨리 먹어야 할 재료 ${soon}개` ``

`docs/site/product.html`, `docs/site/portfolio.html`: `재료 6개 · 곧 먹어야 할 재료 2개` → `재료 6개 · 빨리 먹어야 할 재료 2개` (파일마다 한 곳)

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && grep -rn "곧 먹어야" frontend/src docs/site`
Expected: 아무것도 나오지 않는다.

- [ ] **Step 6: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: `tsc --noEmit`와 `vite build`가 오류 없이 끝난다.

- [ ] **Step 7: 브라우저 확인**

개발 서버(Vite 5180, dev.sh가 이미 띄워 둠, 5173 금지)에서 개발용 로그인 후 384×832로 확인한다.
- 레시피 탭 → `준비 중` 화면, 탭에 `레시피`가 선택돼 있다. 주소창에 `#/recipes/public/1`, `#/recipes/mine/2/edit`를 넣어도 같은 화면이고 `레시피` 탭이 선택돼 있다.
- `#/recipes/mine/abc`, `#/nope` → 재고로 바뀐다.
- 더보기 → 주방 도구 → `< 더보기` → 더보기로 돌아온다(폰 뒤로가기도 같다). 주소로 `#/tools`를 바로 열고 `< 더보기`를 누르면 더보기로 간다.
- 주방 도구를 한 번 연 뒤 더보기로 갔다가 다시 열면 목록이 `불러오는 중…` 없이 바로 보인다.
- 재고 목록을 아래로 내린 채 레시피 탭 → 재고 탭으로 돌아오면 내렸던 위치에 있다. 처음 여는 탭은 맨 위부터 보인다.
- 재료 추가 시트의 구입일 달력에서 내일을 고를 수 없다. 요약 줄이 `빨리 먹어야 할 재료 N개`다.

- [ ] **Step 8: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend docs/site && git commit -m "refactor: 해시 경로표(파라미터)·화면 표, useResource 캐시와 스크롤 복원, 구입일 max, 재고 요약 문구" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"
```

---

### Task 4: 레시피 탭·상세·폼 화면

사용자 승인 완료(2026-09-13): 작은 카드, 임박 재료 배지는 노랑(`.badge.old`)에 재료 이름(`두부·대파 마저 써요`). 시안 `docs/design/recipes-3a/`(Recommend(+Dark), RecommendEmpty, Mine, MineEmpty, DetailPublic(+Dark), DetailMine, Form, FormBottom)을 따른다. `RecommendBig`(큰 사진 카드)은 쓰지 않는다. 새 CSS 클래스는 시안의 `rc-` 이름과 값을 옮겼고, 시안의 `<span>` 모형은 실제 `<button>`·`<a>`·`<input>`·`<textarea>`로 바꿨다.

승인된 시안에서 정한 것:
1. 레시피 탭 제목 `레시피`, 세그먼트 `추천 · 내 레시피 · 양념 비율`. 페이지 배경 위라 트랙은 라이트 `--handle`/선택 `--surface`, 다크는 반대(`--seg-track`, `--seg-on`). 상세에서 돌아오면 보던 칸이 남는다.
2. 추천 카드(작은 카드): 72px 사진(없으면 회색 칸 + 그릇 아이콘) · 임박 배지 · 제목 · `재료 7개 중 5개 있어요`(다 있으면 초록 체크 `재료 5개 다 있어요`) · 막대 / 아래 줄 `없는 재료` 칩 최대 3개 + `+N`. 장보기 담기는 4단계라 넣지 않는다.
3. 임박 배지 문구(사용자 결정): 1개 `두부 마저 써요`, 2개 `두부·대파 마저 써요`, 3개 이상 `두부 외 2개 마저 써요`. 없으면 배지를 숨긴다. 색은 재고의 `구입 N일째`와 같은 노랑 `.badge.old`.
4. 예시 레시피일 때 카드 위에 회색 한 줄 + 정보 아이콘 `예시 레시피로 보여줘요`.
5. 재고가 비었으면 다람이 마크 + `재고가 비어 있어요` / `재고에 재료를 넣으면 만들 수 있는 요리를 찾아줘요` + `재고로 가기`. 재고는 있는데 맞는 요리가 없으면 `지금 재고로 만들 수 있는 요리를 찾지 못했어요.`
6. 내 레시피: 목록 행 `4인분 · 재료 10개 · 추천에서 저장`, 아래 고정 `레시피 추가`. 비었으면 `저장한 레시피가 없어요.` / `추천에서 마음에 드는 레시피를 저장하거나 아래 버튼으로 직접 추가해보세요.`
7. 상세: `< 레시피`, 사진(있을 때만 188px), 제목, `2인분 · 반찬`(예시면 `· 예시 레시피`, 저장한 것이면 `· 추천에서 저장`), 흰 구역 `재료`(오른쪽 `−  2인분  +`, 1~20, 화면에서만 양 계산) · 일치 막대 · 행마다 `있음 · 재고 이름`(초록 체크) 또는 회색 `없음` 배지, 구역 `만드는 법`(초록 번호 원). 공공 레시피는 아래 고정 `내 레시피로 저장`(북마크 아이콘) → 저장한 내 레시피 상세로 바뀐다(뒤로가기하면 추천 목록). 내 레시피는 맨 아래 `수정`(테두리 버튼, 연필) 그리고 그 아래 `이 레시피 삭제`(`.btn.danger-text`, `○○을 삭제할까요?` 확인). 위쪽 수정 버튼은 없다.
8. 폼 `레시피 추가`/`레시피 수정`: 구역 1(이름, 인분 스테퍼), 구역 2 `재료`(오른쪽 힌트 `양은 비워도 괜찮아요`, 행 = 이름 · 양 104px · 휴지통, 양만 있고 이름이 빈 행은 빨간 테두리 + 아래 `재료 이름을 입력해주세요`, `+ 재료 추가`), 구역 3 `만드는 법`(번호 · 여러 줄 입력 · 휴지통, `+ 단계 추가`), 아래 고정 `취소`(테두리) · `저장`. 바뀐 내용이 있으면 `< 레시피`·`취소`에서 `작성 중인 내용이 사라져요. 나갈까요?`

레이아웃을 조금 고칠 때는 `styles.css`의 `/* ---- 3a단계 레시피 */` 블록과 세 화면의 JSX만 건드리면 된다. 상태·API 호출은 `RecommendList`·`MyRecipeList`(불러오기), `RecipeDetail`의 `save`·`remove`, `RecipeEditor`의 `submit`·`leave`에만 있다.

**Files:**
- Create: `frontend/src/pages/Recipes.tsx`, `frontend/src/pages/RecipeDetail.tsx`, `frontend/src/pages/RecipeForm.tsx`
- Modify: `frontend/src/api.ts`, `frontend/src/format.ts`, `frontend/src/components/Icon.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/ComingSoon.tsx`, `frontend/src/styles.css`
- 참고: `docs/design/recipes-3a/*.dc.html`

**Interfaces:**
- Consumes: T1·T2 API(`/api/recipes`, `/api/recipes/<id>`, `/api/public-recipes/<id>`, `/api/public-recipes/<id>/save`, `/api/recommendations`), T3 `navigate`, `goBack`, `useResource`, `forgetResources`, `PAGES`, 기존 `api`, `useAsyncAction`, `withJosa`, `Icon`, `.page`, `.topbar`, `.summary`, `.segmented`, `.list`, `.row-btn`, `.empty`, `.soon-title`, `.soon-list`, `.cta-bar`, `.btn(.primary/.secondary/.outline/.danger-text/.inline)`, `.actions`, `.field`, `.input`, `.stepper`, `.icon-btn`, `.back-link`, `.badge(.old)`, `.plain-row`, `.staple-name`, `.stock-ok`, `.hint`, `.error`, `.section-label`
- Produces:
  - 타입 `RecipeIngredient`, `RecipeIngredientStatus`, `RecipeInput`, `RecipeSource`, `RecipeSummary`, `MyRecipe`, `PublicRecipeDetail`, `RecipeDetail`, `RecommendationCard`, `Recommendations`
  - `format.ts`: `imageSrc(url)`(식약처 `http://www|openapi.foodsafetykorea.go.kr/` → https, 2026-09-13 https 200 확인), `formatAmountNumber(value)`, `scaleAmount(amount, ratio)`
  - Icon 이름 추가: `bowl`, `bookmark`, `trash`(경로는 시안 SVG 그대로)
  - `pages/Recipes.tsx`: 기본 `Recipes`, `urgentLabel(names)`, `MatchLine({have, total})`
  - `pages/RecipeDetail.tsx`: `RecipeDetail({ kind: "mine" | "public", id })`
  - `pages/RecipeForm.tsx`: `RecipeForm({ id? })`(없으면 추가, 있으면 수정)
  - CSS: `--seg-track`, `--seg-on`, `.rc-seg`, `.rc-sample`, `.rc-group`, `.rc-cards`, `.rc-card`, `.rc-thumb`, `.rc-ph`, `.rc-body`, `.rc-match(.done)`, `.rc-bar`, `.rc-missing`, `.rc-chip(.more)`, `.rc-empty`, `.rc-empty-mark`, `.rc-hero`, `.rc-head`, `.rc-sec`, `.rc-sec-head`, `.rc-serv`, `.rc-have`, `.rc-ings`, `.rc-amt`, `.rc-steps`, `.rc-num`, `.rc-actions`, `.rc-page-form`, `.rc-form`, `.rc-count`, `.rc-rows`, `.rc-ing-row`, `.input.invalid`, `.rc-err`, `.rc-step-row`, `.rc-area`, `.rc-add`, `.cta-bar .actions`

(브랜치: `feature/recipes-routing`이 main에 병합된 뒤 시작한다.)

- [ ] **Step 0: 브랜치**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git checkout main && git checkout -b feature/recipes-ui
```

- [ ] **Step 1: 타입·아이콘·양 계산**

`frontend/src/api.ts`: `export class ApiError extends Error {` 바로 위에 추가한다:
```ts
export interface RecipeIngredient {
  name: string;
  amount: string;
}

/** 상세 화면의 재료: 지금 재고와 매칭한 결과(matched_name은 재고 이름, 물처럼 늘 있는 재료는 null) */
export interface RecipeIngredientStatus extends RecipeIngredient {
  have: boolean;
  matched_name: string | null;
}

export interface RecipeInput {
  title: string;
  servings: number;
  ingredients: RecipeIngredient[];
  steps: string[];
}

export type RecipeSource = "mine" | "public" | "ai" | "youtube" | "instagram" | "text";

export interface RecipeSummary {
  id: number;
  title: string;
  servings: number;
  source: RecipeSource;
  image_url: string | null;
  ingredient_count: number;
  updated_at: string;
}

interface RecipeDetailBase {
  id: number;
  title: string;
  servings: number;
  category: string | null;
  ingredients: RecipeIngredientStatus[];
  steps: string[];
  image_url: string | null;
}

export interface MyRecipe extends RecipeDetailBase {
  kind: "mine";
  source: RecipeSource;
  source_url: string | null;
  public_recipe_id: number | null;
}

export interface PublicRecipeDetail extends RecipeDetailBase {
  kind: "public";
  method: string | null;
  kcal: number | null;
  is_sample: boolean;
}

export type RecipeDetail = MyRecipe | PublicRecipeDetail;

export interface RecommendationCard {
  kind: "mine" | "public";
  id: number;
  title: string;
  image_url: string | null;
  servings: number;
  match_rate: number;
  have_count: number;
  total_count: number;
  missing: string[];
  urgent_used: number;
  urgent_names: string[];
  score: number;
}

export interface Recommendations {
  mine: RecommendationCard[];
  public: RecommendationCard[];
  sample: boolean;
  inventory_count: number;
}
```

`frontend/src/components/Icon.tsx`의 `PATHS`에서 `download` 바로 위에 추가한다(시안 SVG 그대로):
```tsx
  bowl: (
    <>
      <path d="M3.5 11.5h17a8.5 7.5 0 0 1-17 0z" />
      <path d="M9 21h6M9.5 3.5c-.9 1.2.9 2.3 0 3.5M14.5 3.5c-.9 1.2.9 2.3 0 3.5" />
    </>
  ),
  bookmark: <path d="M6.5 3.5h11v17L12 16.5l-5.5 4z" />,
  trash: (
    <>
      <path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13" />
      <path d="M10.5 11v5M13.5 11v5" />
    </>
  ),
```

`frontend/src/format.ts` 끝에 추가한다:
```ts
/** 식약처 사진은 http 주소로 오지만 https로도 열린다(2026-09-13 확인). https 화면에서 섞인 콘텐츠로 막히지 않게 바꾼다. */
export function imageSrc(url: string | null): string | null {
  return url ? url.replace(/^http:\/\/(www|openapi)\.foodsafetykorea\.go\.kr\//, "https://$1.foodsafetykorea.go.kr/") : null;
}

// 숟가락으로 뜰 수 있는 분수 (스펙 22절과 같은 기호)
const SNAPS: [number, string][] = [[0, ""], [1 / 4, "¼"], [1 / 3, "⅓"], [1 / 2, "½"], [2 / 3, "⅔"], [3 / 4, "¾"], [1, ""]];
const FRACTIONS = Object.fromEntries(SNAPS.filter(([, symbol]) => symbol).map(([value, symbol]) => [symbol, value]));

/** 0.5 → "½", 1.5 → "1½", 0.4 → "0.4", 112.5 → "113". 10 이상은 정수, 그 아래는 가까운 분수가 있으면 분수 */
export function formatAmountNumber(value: number): string {
  if (value >= 10) return String(Math.round(value));
  const whole = Math.floor(value);
  const snap = SNAPS.find(([fraction]) => Math.abs(value - whole - fraction) < 0.04);
  if (!snap) return String(Number(value.toFixed(1)));
  const [fraction, symbol] = snap;
  return symbol ? `${whole || ""}${symbol}` : String(whole + fraction);
}

/**
 * 인분 조절: 양의 앞 숫자만 배율로 바꾼다(화면에서만, 저장하지 않음 — 스펙 23절 D1).
 * "200g" ×2 → "400g", "1/2모(150g)" ×2 → "1모(150g)", "1½큰술" ×2 → "3큰술". "약간"·"10~15개"는 그대로
 */
export function scaleAmount(amount: string, ratio: number): string {
  const match = amount.match(/^(\d+(?:\.\d+)?)?(?:([¼⅓½⅔¾])|\/(\d+))?/);
  if (ratio === 1 || !match || (match[1] === undefined && match[2] === undefined)) return amount;
  if (match[3] !== undefined && (match[1] === undefined || Number(match[3]) === 0)) return amount;
  const rest = amount.slice(match[0].length);
  if (/^\s*[~-]\s*\d/.test(rest)) return amount; // 범위(10~15개)는 어느 숫자를 바꿀지 애매해서 그대로
  let value = Number(match[1] ?? 0) + (match[2] ? FRACTIONS[match[2]] : 0);
  if (match[3] !== undefined) value /= Number(match[3]);
  return formatAmountNumber(value * ratio) + rest;
}
```

양 계산 확인:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && node --input-type=module -e '
import assert from "node:assert/strict";
import { scaleAmount, imageSrc } from "./src/format.ts";
const cases = [["200g",2,"400g"],["1/2모(150g)",2,"1모(150g)"],["1½큰술",2,"3큰술"],["약간",2,"약간"],["1/3개",3,"1개"],["1/4대",2,"½대"],["2큰술",0.5,"1큰술"],["1작은술",1.5,"1½작은술"],["3큰술",1/3,"1큰술"],["1개",0.4,"0.4개"],["500ml",1.5,"750ml"],["75g",1.5,"113g"],["½큰술",3,"1½큰술"],["2/0개",2,"2/0개"],["/2",2,"/2"],["1공기",2,"2공기"],["10~15개",2,"10~15개"],["1모",1,"1모"],["1/2대",1.5,"¾대"],["1/3개",2,"⅔개"]];
for (const [a,r,e] of cases) assert.equal(scaleAmount(a,r), e, a+" x"+r);
assert.equal(imageSrc("http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png"), "https://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png");
assert.equal(imageSrc("http://evil.example/x.png"), "http://evil.example/x.png");
assert.equal(imageSrc(null), null);
console.log("format ok");
'
```
Expected: `format ok`

- [ ] **Step 2: 스타일**

`frontend/src/styles.css` 끝에 추가한다:
```css
/* ---- 3a단계 레시피 (시안 docs/design/recipes-3a, rc- 접두사) ---- */
:root {
  --seg-track: var(--handle);
  --seg-on: var(--surface);
}

@media (prefers-color-scheme: dark) {
  :root {
    --seg-track: var(--surface);
    --seg-on: var(--handle);
  }
}

/* 페이지 배경(--bg) 위 세그먼트: --field 트랙이 배경에 묻히므로 트랙·선택 색을 따로 둔다 */
.rc-seg {
  margin: 16px 20px 0;
  background: var(--seg-track);
}

.rc-seg button[aria-pressed="true"] {
  background: var(--seg-on);
}

.rc-sample {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 20px 0;
  color: var(--text-3);
  font-size: 14px;
  line-height: 20px;
}

.rc-group {
  margin: 20px 20px 0;
}

.rc-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 12px 20px 0;
  padding: 0;
  list-style: none;
}

/* 추천 카드: 72px 사진 + 제목·일치율, 없는 재료 칩은 아래 전체 폭 */
.rc-card {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  column-gap: 14px;
  row-gap: 12px;
  padding: 16px;
  border-radius: 20px;
  background: var(--surface);
  color: inherit;
  text-decoration: none;
}

.rc-thumb {
  display: block;
  width: 72px;
  height: 72px;
  overflow: hidden;
  border-radius: 14px;
}

.rc-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.rc-ph {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--neutral-tint);
  color: var(--text-3);
}

.rc-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 2px;
  min-width: 0;
}

.rc-body .badge {
  height: 26px;
  margin-bottom: 4px;
  padding: 0 8px;
}

.rc-match {
  display: block;
  width: 100%;
  color: var(--text-2);
  font-size: 14px;
  line-height: 20px;
}

.rc-match b {
  color: var(--accent-strong);
  font-weight: 700;
}

.rc-match .done {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--accent-strong);
  font-weight: 600;
}

.rc-bar {
  display: block;
  width: 100%;
  height: 6px;
  margin-top: 8px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--neutral-tint);
}

.rc-bar i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
}

.rc-missing {
  display: flex;
  flex-wrap: wrap;
  grid-column: 1 / 3;
  align-items: center;
  gap: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.rc-missing .label {
  margin-right: 2px;
  color: var(--text-3);
  font-size: 13px;
}

.rc-chip {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 8px;
  border-radius: 7px;
  background: var(--field);
  color: var(--chip-text);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.rc-chip.more {
  color: var(--text-3);
}

.rc-empty-mark {
  display: block;
  margin: 0 auto;
  border-radius: 19px;
}

.rc-empty .muted {
  text-wrap: balance;
  word-break: keep-all;
}

.rc-empty .btn {
  margin: 20px auto 0;
}

/* 상세 */
.rc-hero {
  display: block;
  width: calc(100% - 40px);
  height: 188px;
  margin: 20px 20px 0;
  border-radius: 20px;
  background: var(--neutral-tint);
  object-fit: cover;
}

.rc-head {
  padding: 20px 20px 0;
}

.rc-head h1 {
  margin: 0;
  font-size: 26px;
  line-height: 34px;
  font-weight: 700;
  letter-spacing: -0.5px;
  word-break: keep-all;
}

.rc-sec {
  margin: 16px 20px 0;
  padding: 20px;
  border-radius: 20px;
  background: var(--surface);
}

.rc-sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.rc-sec h2 {
  margin: 0;
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
  letter-spacing: -0.3px;
}

.rc-serv {
  display: flex;
  align-items: center;
  gap: 4px;
}

.rc-serv .icon-btn {
  border-radius: 12px;
  background: var(--field);
  color: var(--text);
}

.rc-serv .icon-btn:disabled {
  opacity: 0.4;
}

.rc-serv b {
  min-width: 60px;
  font-size: 17px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.rc-have {
  margin-top: 12px;
}

.rc-ings,
.rc-steps {
  margin: 0;
  padding: 0;
  list-style: none;
}

.rc-ings {
  margin-top: 8px;
}

.rc-ings li {
  min-height: 52px;
  border-top: 1px solid var(--line);
}

.rc-ings li:first-child {
  border-top: 0;
}

.rc-amt {
  margin-left: 6px;
  color: var(--text-2);
  font-size: 15px;
  font-weight: 400;
}

.rc-ings .stock-ok svg {
  flex-shrink: 0;
  color: var(--accent-strong);
}

.rc-steps {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 14px;
}

.rc-steps li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: start;
  gap: 12px;
}

.rc-num {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 14px;
  background: var(--accent-tint);
  color: var(--accent-strong);
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.rc-steps p {
  margin: 0;
  padding-top: 2px;
  font-size: 16px;
  line-height: 24px;
  word-break: keep-all;
}

/* 수정(위)·삭제(아래) — 삭제는 .btn.danger-text 배경+테두리 그대로 */
.rc-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 24px 20px 0;
}

/* 폼 */
.rc-page-form > .error {
  margin: 16px 20px 0;
}

.rc-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.rc-count {
  display: flex;
  align-items: center;
  justify-content: center;
  font-variant-numeric: tabular-nums;
}

.rc-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
}

.rc-ing-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 104px 44px;
  align-items: center;
  gap: 8px;
}

.rc-ing-row .input {
  height: 52px;
}

.input.invalid {
  box-shadow: inset 0 0 0 1.5px var(--danger);
}

.rc-err {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: -2px 0 2px;
  color: var(--danger);
  font-size: 14px;
  line-height: 20px;
  font-weight: 600;
}

.rc-step-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 44px;
  align-items: start;
  gap: 8px;
}

.rc-step-row .rc-num {
  margin-top: 12px;
}

.rc-area {
  display: block;
  height: auto;
  min-height: 80px;
  padding: 13px 16px;
  font: inherit;
  font-size: 17px;
  line-height: 26px;
  resize: vertical;
}

.rc-add {
  min-height: 52px;
  margin-top: 14px;
  font-size: 16px;
}

.cta-bar .actions {
  max-width: 480px;
  margin: 0 auto;
}
```

- [ ] **Step 3: 레시피 탭(추천 · 내 레시피 · 양념 비율)**

`frontend/src/pages/Recipes.tsx`(새 파일):
```tsx
import { useState, type ReactNode } from "react";
import type { RecipeSummary, RecommendationCard, Recommendations } from "../api";
import Icon from "../components/Icon";
import { imageSrc } from "../format";
import { navigate } from "../useHashRoute";
import { useResource } from "../useResource";

type Segment = "recommend" | "mine" | "seasoning";

const SEGMENTS: [Segment, string][] = [
  ["recommend", "추천"],
  ["mine", "내 레시피"],
  ["seasoning", "양념 비율"],
];

// ponytail: 상세에서 돌아와도 보던 칸을 유지한다(모듈 변수, 새로고침하면 추천). 칸을 공유 링크로 열 일이 생기면 경로로 옮긴다.
let lastSegment: Segment = "recommend";

/** ["두부"] → "두부 마저 써요", ["두부", "대파"] → "두부·대파 마저 써요", 3개 이상 → "두부 외 2개 마저 써요" */
export function urgentLabel(names: string[]): string {
  if (names.length === 0) return "";
  const who = names.length <= 2 ? names.join("·") : `${names[0]} 외 ${names.length - 1}개`;
  return `${who} 마저 써요`;
}

/** "재료 7개 중 5개 있어요" + 막대 (추천 카드·상세 공통) */
export function MatchLine({ have, total }: { have: number; total: number }) {
  const percent = total ? Math.round((have / total) * 100) : 0;
  return (
    <span className="rc-match">
      {have === total ? (
        <span className="done">
          <Icon name="check" size={16} />
          재료 {total}개 다 있어요
        </span>
      ) : (
        <>
          재료 {total}개 중 <b>{have}개</b> 있어요
        </>
      )}
      <span className="rc-bar" aria-hidden="true">
        <i style={{ width: `${percent}%` }} />
      </span>
    </span>
  );
}

function RecipeLink({ path, className, children }: { path: string; className: string; children: ReactNode }) {
  return (
    <a
      className={className}
      href={`#${path}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(path);
      }}
    >
      {children}
    </a>
  );
}

function RecommendCardView({ card }: { card: RecommendationCard }) {
  const missing = card.total_count - card.have_count;
  const src = imageSrc(card.image_url);
  const urgent = urgentLabel(card.urgent_names);
  return (
    <RecipeLink path={`/recipes/${card.kind}/${card.id}`} className="rc-card">
      <span className={src ? "rc-thumb" : "rc-thumb rc-ph"}>
        {src ? <img src={src} alt="" loading="lazy" /> : <Icon name="bowl" size={28} />}
      </span>
      <span className="rc-body">
        {urgent && <span className="badge old">{urgent}</span>}
        <span className="row-title">{card.title}</span>
        <MatchLine have={card.have_count} total={card.total_count} />
      </span>
      {missing > 0 && (
        <span className="rc-missing">
          <span className="label">없는 재료</span>
          {card.missing.slice(0, 3).map((name) => (
            <span key={name} className="rc-chip">
              {name}
            </span>
          ))}
          {missing > 3 && <span className="rc-chip more">+{missing - 3}</span>}
        </span>
      )}
    </RecipeLink>
  );
}

function RecommendList() {
  const { data, error } = useResource<Recommendations>("/api/recommendations");
  if (!data)
    return error ? (
      <p className="error" role="alert">
        {error}
      </p>
    ) : (
      <p className="center muted">불러오는 중…</p>
    );

  if (data.inventory_count === 0)
    return (
      <section className="empty rc-empty">
        <img className="rc-empty-mark" src="/mark.svg" width="64" height="64" alt="" />
        <p className="soon-title">재고가 비어 있어요</p>
        <p className="muted">재고에 재료를 넣으면 만들 수 있는 요리를 찾아줘요</p>
        <button className="btn primary inline" onClick={() => location.replace("#/")}>
          <Icon name="fridge" />
          재고로 가기
        </button>
      </section>
    );

  // 내 레시피가 추천에 있을 때만 구역 이름을 붙인다(없으면 시안처럼 카드만)
  const groups = [
    { label: "내 레시피", cards: data.mine },
    { label: data.sample ? "예시 레시피" : "식약처 레시피", cards: data.public },
  ].filter((group) => group.cards.length > 0);

  if (groups.length === 0)
    return (
      <section className="empty">
        <p>지금 재고로 만들 수 있는 요리를 찾지 못했어요.</p>
        <p className="muted">재료를 더 넣거나 내 레시피를 추가해보세요.</p>
      </section>
    );

  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {data.sample && data.public.length > 0 && (
        <p className="rc-sample">
          <Icon name="info" size={16} />
          예시 레시피로 보여줘요
        </p>
      )}
      {groups.map((group) => (
        <section key={group.label} aria-label={group.label}>
          {groups.length > 1 && <h2 className="section-label rc-group">{group.label}</h2>}
          <ul className="rc-cards">
            {group.cards.map((card) => (
              <li key={`${card.kind}-${card.id}`}>
                <RecommendCardView card={card} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

function MyRecipeList() {
  const { data, error } = useResource<RecipeSummary[]>("/api/recipes");
  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data ? (
        !error && <p className="center muted">불러오는 중…</p>
      ) : data.length === 0 ? (
        <section className="empty">
          <p>저장한 레시피가 없어요.</p>
          <p className="muted">
            추천에서 마음에 드는 레시피를 저장하거나
            <br />
            아래 버튼으로 직접 추가해보세요.
          </p>
        </section>
      ) : (
        <ul className="list">
          {data.map((recipe) => (
            <li key={recipe.id}>
              <RecipeLink path={`/recipes/mine/${recipe.id}`} className="row-btn">
                <span className="row-main">
                  <span className="row-title">{recipe.title}</span>
                  <span className="row-sub">
                    {recipe.servings}인분 · 재료 {recipe.ingredient_count}개{recipe.source === "public" && " · 추천에서 저장"}
                  </span>
                </span>
                <Icon name="chevron" />
              </RecipeLink>
            </li>
          ))}
        </ul>
      )}
      <div className="cta-bar">
        <button className="btn primary" onClick={() => navigate("/recipes/new")}>
          <Icon name="plus" />
          레시피 추가
        </button>
      </div>
    </>
  );
}

// 3c단계(양념 비율 계산기) 전까지 자리만 잡는다
function SeasoningSoon() {
  return (
    <section className="empty">
      <Icon name="book" size={32} color="var(--accent-strong)" />
      <p className="soon-title">준비 중이에요</p>
      <p className="muted">곧 이런 걸 할 수 있어요.</p>
      <ul className="soon-list">
        {["불고기·제육볶음 같은 기본 양념 비율", "고기 양·인분에 맞춰 숟가락 단위로 계산", "내 입맛에 맞춘 비율 저장"].map((item) => (
          <li key={item}>
            <Icon name="check" size={16} color="var(--accent-strong)" />
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function Recipes() {
  const [segment, setSegment] = useState<Segment>(lastSegment);
  const choose = (next: Segment) => {
    lastSegment = next;
    setSegment(next);
  };

  return (
    <div className="page">
      <header className="topbar">
        <h1>레시피</h1>
      </header>
      <div className="segmented rc-seg" role="group" aria-label="레시피 보기">
        {SEGMENTS.map(([key, label]) => (
          <button key={key} aria-pressed={segment === key} onClick={() => choose(key)}>
            {label}
          </button>
        ))}
      </div>
      {segment === "recommend" && <RecommendList />}
      {segment === "mine" && <MyRecipeList />}
      {segment === "seasoning" && <SeasoningSoon />}
    </div>
  );
}
```

- [ ] **Step 4: 레시피 상세**

`frontend/src/pages/RecipeDetail.tsx`(새 파일):
```tsx
import { useState } from "react";
import { api, type MyRecipe, type RecipeDetail as Detail } from "../api";
import Icon from "../components/Icon";
import { imageSrc, scaleAmount, withJosa } from "../format";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetResources, useResource } from "../useResource";
import { MatchLine } from "./Recipes";

function BackLink() {
  return (
    <a
      className="back-link"
      href="#/recipes"
      onClick={(e) => {
        e.preventDefault();
        goBack("/recipes");
      }}
    >
      <Icon name="back" size={18} />
      레시피
    </a>
  );
}

export default function RecipeDetail({ kind, id }: { kind: "mine" | "public"; id: string }) {
  const { data: recipe, error } = useResource<Detail>(kind === "mine" ? `/api/recipes/${id}` : `/api/public-recipes/${id}`);
  const [servings, setServings] = useState<number | null>(null); // null이면 레시피 기준 인분
  const { busy, error: actionError, run } = useAsyncAction();

  if (!recipe)
    return (
      <div className="page">
        <BackLink />
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : (
          <p className="center muted">불러오는 중…</p>
        )}
      </div>
    );

  const shown = servings ?? recipe.servings;
  const ratio = shown / recipe.servings;
  const have = recipe.ingredients.filter((item) => item.have).length;
  const src = imageSrc(recipe.image_url);
  const meta = [
    `${recipe.servings}인분`,
    recipe.category,
    recipe.kind === "public" && recipe.is_sample ? "예시 레시피" : null,
    recipe.kind === "mine" && recipe.source === "public" ? "추천에서 저장" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const save = () =>
    run(async () => {
      const saved = await api<MyRecipe>(`/api/public-recipes/${recipe.id}/save`, { method: "POST" });
      forgetResources("/api/rec"); // 내 레시피 목록·추천
      navigate(`/recipes/mine/${saved.id}`, { replace: true });
    });

  const remove = () => {
    if (!confirm(`${withJosa(recipe.title, "을", "를")} 삭제할까요?`)) return;
    run(async () => {
      await api(`/api/recipes/${recipe.id}`, { method: "DELETE" });
      forgetResources("/api/rec");
      goBack("/recipes");
    });
  };

  return (
    <div className="page">
      <BackLink />
      {src && <img className="rc-hero" src={src} alt="" />}
      <header className="rc-head">
        <h1>{recipe.title}</h1>
        <p className="summary">{meta}</p>
      </header>

      <section className="rc-sec" aria-labelledby="rc-ingredients">
        <div className="rc-sec-head">
          <h2 id="rc-ingredients">재료</h2>
          <div className="rc-serv" role="group" aria-label="인분 조절">
            <button
              type="button"
              className="icon-btn"
              aria-label="인분 줄이기"
              disabled={shown <= 1}
              onClick={() => setServings(shown - 1)}
            >
              <Icon name="minus" />
            </button>
            <b aria-live="polite">{shown}인분</b>
            <button
              type="button"
              className="icon-btn"
              aria-label="인분 늘리기"
              disabled={shown >= 20}
              onClick={() => setServings(shown + 1)}
            >
              <Icon name="plus" />
            </button>
          </div>
        </div>
        {recipe.ingredients.length > 0 && (
          <div className="rc-have">
            <MatchLine have={have} total={recipe.ingredients.length} />
          </div>
        )}
        <ul className="rc-ings">
          {recipe.ingredients.map((item, index) => (
            <li key={index} className="plain-row">
              <span className="staple-name">
                {item.name}
                {item.amount && <span className="rc-amt">{scaleAmount(item.amount, ratio)}</span>}
              </span>
              {item.have ? (
                <span className="stock-ok">
                  <Icon name="check" size={16} />
                  {item.matched_name ? `있음 · ${item.matched_name}` : "있음"}
                </span>
              ) : (
                <span className="badge">없음</span>
              )}
            </li>
          ))}
        </ul>
      </section>

      {recipe.steps.length > 0 && (
        <section className="rc-sec" aria-labelledby="rc-steps">
          <h2 id="rc-steps">만드는 법</h2>
          <ol className="rc-steps">
            {recipe.steps.map((step, index) => (
              <li key={index}>
                <span className="rc-num" aria-hidden="true">
                  {index + 1}
                </span>
                <p>{step}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {actionError && (
        <p className="error" role="alert">
          {actionError}
        </p>
      )}

      {recipe.kind === "mine" ? (
        <div className="rc-actions">
          <button className="btn outline" onClick={() => navigate(`/recipes/mine/${recipe.id}/edit`)}>
            <Icon name="pencil" />
            수정
          </button>
          <button className="btn danger-text" disabled={busy} onClick={remove}>
            이 레시피 삭제
          </button>
        </div>
      ) : (
        <div className="cta-bar">
          <button className="btn primary" disabled={busy} onClick={save}>
            <Icon name="bookmark" />
            {busy ? "저장 중…" : "내 레시피로 저장"}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: 레시피 추가·수정 폼**

`frontend/src/pages/RecipeForm.tsx`(새 파일):
```tsx
import { Fragment, useState, type FormEvent } from "react";
import { api, type MyRecipe, type RecipeInput } from "../api";
import Icon from "../components/Icon";
import { useAsyncAction } from "../useAsyncAction";
import { goBack, navigate } from "../useHashRoute";
import { forgetResources, useResource } from "../useResource";

const MAX_INGREDIENTS = 50;
const MAX_STEPS = 30;
const LEAVE_CONFIRM = "작성 중인 내용이 사라져요. 나갈까요?";

interface IngredientRow {
  key: number;
  name: string;
  amount: string;
}

interface StepRow {
  key: number;
  text: string;
}

let lastKey = 0;
const newKey = () => ++lastKey;

function BackLink({ onClick }: { onClick: () => void }) {
  return (
    <a
      className="back-link"
      href="#/recipes"
      onClick={(e) => {
        e.preventDefault();
        onClick();
      }}
    >
      <Icon name="back" size={18} />
      레시피
    </a>
  );
}

function RecipeEditor({ initial }: { initial: MyRecipe | null }) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [servings, setServings] = useState(initial?.servings ?? 2);
  const [rows, setRows] = useState<IngredientRow[]>(() =>
    (initial?.ingredients ?? [{ name: "", amount: "" }]).map((item) => ({ key: newKey(), name: item.name, amount: item.amount })),
  );
  const [steps, setSteps] = useState<StepRow[]>(() =>
    (initial?.steps.length ? initial.steps : [""]).map((text) => ({ key: newKey(), text })),
  );
  const [invalidKey, setInvalidKey] = useState<number | null>(null); // 양만 있고 이름이 빈 재료 줄
  const [focusKey, setFocusKey] = useState<number | null>(null); // 방금 추가한 줄에 커서
  const { busy, error, setError, run } = useAsyncAction();

  const input = (): RecipeInput => ({
    title: title.trim(),
    servings,
    ingredients: rows
      .filter((row) => row.name.trim() || row.amount.trim())
      .map((row) => ({ name: row.name.trim(), amount: row.amount.trim() })),
    steps: steps.map((step) => step.text.trim()).filter(Boolean),
  });
  const [startJson] = useState(() => JSON.stringify(input()));
  const dirty = JSON.stringify(input()) !== startJson;

  // ponytail: 앱 안의 뒤로·취소만 확인한다. 폰의 뒤로가기 버튼은 막을 수 없어(popstate는 취소 불가) 그대로 나간다.
  const leave = () => {
    if (dirty && !confirm(LEAVE_CONFIRM)) return;
    goBack(initial ? `/recipes/mine/${initial.id}` : "/recipes");
  };

  const updateRow = (key: number, patch: Partial<IngredientRow>) =>
    setRows((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));

  const addRow = () => {
    const key = newKey();
    setRows((prev) => [...prev, { key, name: "", amount: "" }]);
    setFocusKey(key);
  };

  const addStep = () => {
    const key = newKey();
    setSteps((prev) => [...prev, { key, text: "" }]);
    setFocusKey(key);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const nameless = rows.find((row) => !row.name.trim() && row.amount.trim());
    setInvalidKey(nameless?.key ?? null);
    if (nameless) return;
    const body = input();
    if (body.ingredients.length === 0) {
      setError("재료를 하나 이상 입력해주세요.");
      return;
    }
    run(async () => {
      const saved = await api<MyRecipe>(initial ? `/api/recipes/${initial.id}` : "/api/recipes", {
        method: initial ? "PUT" : "POST",
        body,
      });
      forgetResources("/api/rec"); // 상세·내 레시피 목록·추천을 새로 받게
      if (initial) goBack(`/recipes/mine/${saved.id}`);
      else navigate(`/recipes/mine/${saved.id}`, { replace: true }); // 뒤로가기하면 목록으로
    });
  };

  return (
    <div className="page">
      <BackLink onClick={leave} />
      <header className="topbar">
        <h1>{initial ? "레시피 수정" : "레시피 추가"}</h1>
      </header>

      <form className="rc-page-form" onSubmit={submit}>
        <section className="rc-sec rc-form">
          <label className="field">
            <span className="field-label">이름</span>
            <input
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={60}
              placeholder="예: 애호박볶음"
              autoFocus={!initial}
            />
          </label>
          <div className="field">
            <span className="field-label" id="recipe-servings">
              인분
            </span>
            <div className="stepper">
              <button
                type="button"
                className="icon-btn"
                aria-label="인분 줄이기"
                disabled={servings <= 1}
                onClick={() => setServings(servings - 1)}
              >
                <Icon name="minus" />
              </button>
              <output className="input rc-count" aria-labelledby="recipe-servings" aria-live="polite">
                {servings}
              </output>
              <button
                type="button"
                className="icon-btn"
                aria-label="인분 늘리기"
                disabled={servings >= 20}
                onClick={() => setServings(servings + 1)}
              >
                <Icon name="plus" />
              </button>
            </div>
          </div>
        </section>

        <section className="rc-sec" aria-labelledby="recipe-ingredients">
          <div className="rc-sec-head">
            <h2 id="recipe-ingredients">재료</h2>
            <span className="hint">양은 비워도 괜찮아요</span>
          </div>
          <div className="rc-rows">
            {rows.map((row, index) => {
              const invalid = invalidKey === row.key;
              return (
                <Fragment key={row.key}>
                  <div className="rc-ing-row">
                    <input
                      className={invalid ? "input invalid" : "input"}
                      aria-label={`${index + 1}번째 재료 이름`}
                      aria-invalid={invalid}
                      aria-describedby={invalid ? `recipe-error-${row.key}` : undefined}
                      placeholder="재료 이름"
                      maxLength={50}
                      value={row.name}
                      autoFocus={focusKey === row.key}
                      onChange={(e) => {
                        if (invalid) setInvalidKey(null);
                        updateRow(row.key, { name: e.target.value });
                      }}
                    />
                    <input
                      className="input"
                      aria-label={`${index + 1}번째 재료 양`}
                      placeholder="양"
                      maxLength={30}
                      value={row.amount}
                      onChange={(e) => updateRow(row.key, { amount: e.target.value })}
                    />
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`${row.name.trim() || "빈 재료"} 빼기`}
                      onClick={() => setRows((prev) => prev.filter((r) => r.key !== row.key))}
                    >
                      <Icon name="trash" />
                    </button>
                  </div>
                  {invalid && (
                    <p className="rc-err" id={`recipe-error-${row.key}`} role="alert">
                      <Icon name="alert" size={16} />
                      재료 이름을 입력해주세요
                    </p>
                  )}
                </Fragment>
              );
            })}
          </div>
          <button type="button" className="btn secondary rc-add" disabled={rows.length >= MAX_INGREDIENTS} onClick={addRow}>
            <Icon name="plus" />
            재료 추가
          </button>
        </section>

        <section className="rc-sec" aria-labelledby="recipe-steps">
          <h2 id="recipe-steps">만드는 법</h2>
          <div className="rc-rows">
            {steps.map((step, index) => (
              <div key={step.key} className="rc-step-row">
                <span className="rc-num" aria-hidden="true">
                  {index + 1}
                </span>
                <textarea
                  className="input rc-area"
                  aria-label={`${index + 1}단계`}
                  rows={2}
                  maxLength={500}
                  value={step.text}
                  autoFocus={focusKey === step.key}
                  onChange={(e) =>
                    setSteps((prev) => prev.map((s) => (s.key === step.key ? { ...s, text: e.target.value } : s)))
                  }
                />
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={`${index + 1}단계 빼기`}
                  onClick={() => setSteps((prev) => prev.filter((s) => s.key !== step.key))}
                >
                  <Icon name="trash" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="btn secondary rc-add" disabled={steps.length >= MAX_STEPS} onClick={addStep}>
            <Icon name="plus" />
            단계 추가
          </button>
        </section>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <div className="cta-bar">
          <div className="actions">
            <button type="button" className="btn outline" onClick={leave}>
              취소
            </button>
            <button className="btn primary" disabled={busy}>
              {busy ? "저장 중…" : "저장"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

function EditRecipe({ id }: { id: string }) {
  const { data, error } = useResource<MyRecipe>(`/api/recipes/${id}`);
  if (data) return <RecipeEditor initial={data} />;
  return (
    <div className="page">
      <BackLink onClick={() => goBack(`/recipes/mine/${id}`)} />
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : (
        <p className="center muted">불러오는 중…</p>
      )}
    </div>
  );
}

/** /recipes/new (id 없음) · /recipes/mine/:id/edit */
export default function RecipeForm({ id }: { id?: string }) {
  return id ? <EditRecipe id={id} /> : <RecipeEditor initial={null} />;
}
```

- [ ] **Step 6: App 연결, 준비 중 화면 정리**

`frontend/src/App.tsx`:
- import에 세 줄을 추가한다(`More` 다음, 알파벳 순서):
```tsx
import More from "./pages/More";
import RecipeDetail from "./pages/RecipeDetail";
import RecipeForm from "./pages/RecipeForm";
import Recipes from "./pages/Recipes";
import Tools from "./pages/Tools";
```
- `PAGES`의 레시피 다섯 줄을 교체한다:
```tsx
  "/recipes": () => <Recipes />,
  "/recipes/new": () => <RecipeForm />,
  "/recipes/mine/:id": ({ route }) => <RecipeDetail kind="mine" id={route.params.id} />,
  "/recipes/mine/:id/edit": ({ route }) => <RecipeForm id={route.params.id} />,
  "/recipes/public/:id": ({ route }) => <RecipeDetail kind="public" id={route.params.id} />,
```

`frontend/src/pages/ComingSoon.tsx`: `PAGES`에서 `"/recipes": { … },` 항목(제목 `레시피`, 항목 4줄)을 통째로 지운다. 장보기·식단은 그대로다.

- [ ] **Step 7: 빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: `tsc --noEmit`와 `vite build`가 오류 없이 끝난다.

- [ ] **Step 8: 브라우저 확인 (예시 레시피, 키 없음)**

T2 Step 8에서 개발 DB에 예시 레시피를 넣었어야 한다. 개발 서버(Vite 5180)에서 개발용 로그인 후 384×832로 확인한다. 프로토타입에서 같은 흐름을 헤드리스 Chrome으로 돌려 콘솔 오류 0개를 확인했다.
- 재고가 비었을 때 레시피 탭 → 다람이 마크와 `재고가 비어 있어요`, `재고로 가기`가 재고로 간다.
- 재고에 두부(구입 30일 전), 대파(유통기한 오늘), 계란·양파·감자·간장을 넣고 레시피 탭 → `예시 레시피로 보여줘요`, 카드에 노랑 `두부·대파 마저 써요` 같은 배지, `재료 N개 중 M개 있어요`와 막대, 없는 재료 칩 최대 3개 + `+N`.
- 목록을 조금 내린 뒤 `감자조림` → 상세가 맨 위부터 보이고 `2인분 · 반찬 · 예시 레시피`, 물은 `있음`이다. `+`를 두 번 → `4인분`, 감자 `4개`, 양파 `1개`, 참깨 `약간` 그대로.
- 뒤로가기(`< 레시피`와 폰 뒤로가기 모두) → 추천 목록이 불러오는 중 없이 보던 위치에 있다.
- `내 레시피로 저장` → 내 레시피 상세(`… · 추천에서 저장`)로 바뀌고, 맨 아래 `수정`과 그 아래 연빨강 배경·테두리의 `이 레시피 삭제`가 있다. 뒤로가기하면 추천 목록이다. 같은 레시피를 다시 저장해도 내 레시피가 하나다.
- `수정` → 폼에 값이 채워져 있다. `+ 재료 추가` 후 양만 넣고 `저장` → 그 행이 빨간 테두리 + `재료 이름을 입력해주세요`. 휴지통으로 빼고 `저장` → 상세로 돌아와 바뀐 내용이 보인다.
- 내 레시피 칸 → `레시피 추가` → 이름만 쓰고 `< 레시피` → `작성 중인 내용이 사라져요. 나갈까요?` 확인창.
- 새 레시피를 저장하면 그 상세로 가고, 뒤로가기하면 내 레시피 목록에 새 레시피가 있다. 상세에서 삭제 → 확인 → 목록에서 사라져 있다(잠깐도 보이지 않는다).
- `양념 비율` → `준비 중이에요` 카드.
- 라이트·다크 모두 시안과 같은 색이다(세그먼트 트랙이 배경과 구분된다).

- [ ] **Step 9: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 레시피 탭(추천·내 레시피·양념 비율 준비 중), 레시피 상세(보유 표시·인분 조절), 레시피 추가·수정 폼" -m "Claude-Session: https://claude.ai/code/session_01S67Hyztb1f6Nq4BQHSGkUH"
```

---

## 3a단계 완료 기준

- 백엔드: SQLite와 PostgreSQL 테스트 모두 실패 0, 경고 0(`297 passed`). 개발 DB `flask db check` 차이 없음.
- 프론트엔드: `npm run build` 성공, T3·T4의 `node` 한 줄 검사(`matchRoute ok`, `format ok`) 통과.
- 네 브랜치가 순서대로 main에 `--no-ff` 병합됨.
- 개발 DB에 예시 레시피가 들어 있음: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app seed-sample-recipes` → `예시 레시피 12개를 넣었어요. …`(이미 넣었으면 `새로 0개, 바뀐 것 12개.`).
- 폰(갤럭시 S22 Ultra, `http://<맥 IP>:5180`, 개발용 로그인, 식약처 키 없음)에서 확인할 것:
  - 레시피 탭 `추천`: `예시 레시피로 보여줘요`, 카드가 일치율·임박 재료 순으로 보이고, 빨리 먹어야 할 재료를 쓰는 카드에 노랑 `두부 마저 써요` 같은 배지가 있다. 칩과 막대가 카드 밖으로 넘치지 않는다.
  - 카드 → 상세 → 인분 `−/+`로 양이 바뀌고(`1/2개` → `1개` 등), 뒤로가기하면 목록을 보던 위치 그대로다.
  - `내 레시피로 저장` → 내 레시피 상세, `내 레시피` 칸에 `추천에서 저장`으로 보인다.
  - `레시피 추가`로 재료 행·단계 행을 넣고 빼며 저장, `수정`, `이 레시피 삭제`(연빨강 배경·테두리, `수정` 아래)가 된다. 입력칸을 눌러도 화면이 확대되지 않는다(16px 이상).
  - 작성 중에 `< 레시피`를 누르면 확인창이 뜬다. 폰의 뒤로가기 버튼은 확인 없이 나간다(알려진 한계).
  - 재고 요약이 `빨리 먹어야 할 재료 N개`이고, 재료 추가 시트에서 내일 날짜를 구입일로 고를 수 없다.
  - 라이트·다크 모두 글자와 배지가 잘 읽힌다.
- 실제 키로 확인(선택, 키가 준비되면): `backend/.env`에 `FOODSAFETY_API_KEY`를 넣고 `flask sync-public-recipes` → `식약처 레시피 1156건을 받았어요. … 예시 레시피 12건은 지웠어요.` → 추천 카드에 식약처 사진이 https로 뜬다. 사진이 안 뜨면 배포 항목으로 남긴다.
