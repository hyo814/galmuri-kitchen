import time
from datetime import datetime, timezone

import pytest

import app.recipes as recipes_module
from app.ingredients import seoul_today
from app.models import Ingredient, PublicRecipe, Recipe, StorageLocation, User, db
from app.recipe_parse import ingredient_key
from app.validation import encode_cursor

BODY = {
    "title": "대파 계란볶음밥",
    "servings": 1,
    "ingredients": [{"name": "대파", "amount": "1대"}, {"name": "계란", "amount": "2개"}, {"name": "밥", "amount": ""}],
    "steps": ["대파를 썰어요.", "  ", "계란과 밥을 볶아요."],
}


def create(client, **fields):
    return client.post("/api/recipes", json={**BODY, **fields})


def list_recipes(client, query=""):
    return client.get(f"/api/recipes{query}").get_json()


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
    res = create(client)
    assert res.status_code == 201
    recipe = res.get_json()
    assert recipe == {
        "kind": "mine",
        "id": recipe["id"],
        "title": "대파 계란볶음밥",
        "servings": 1,
        "category": None,
        "ingredients": [
            {"name": "대파", "amount": "1대", "have": True, "matched_name": "대파(국산) 1단", "stock_quantity": 1.0, "stock_unit": "개"},
            {"name": "계란", "amount": "2개", "have": False, "matched_name": None, "stock_quantity": None, "stock_unit": None},
            {"name": "밥", "amount": "", "have": False, "matched_name": None, "stock_quantity": None, "stock_unit": None},
        ],
        "steps": ["대파를 썰어요.", "계란과 밥을 볶아요."],
        "source": "mine",  # source를 보내지 않으면 직접 쓴 레시피
        "source_url": None,
        "public_recipe_id": None,
        "image_url": None,
        "eat_out_price": None,
        "eat_out_source": None,
    }
    second = create(client, title="계란국").get_json()

    listed_body = list_recipes(client)
    listed = listed_body["items"]
    assert [(r["title"], r["servings"], r["source"], r["ingredient_count"]) for r in listed] == [
        ("계란국", 1, "mine", 3),
        ("대파 계란볶음밥", 1, "mine", 3),
    ]
    assert set(listed[0]) == {"id", "title", "servings", "source", "image_url", "ingredient_count", "updated_at"}
    assert listed_body["next_cursor"] is None
    assert client.get(f"/api/recipes/{recipe['id']}").get_json() == {**recipe, "cooked": None}  # GET 상세에만 cooked가 붙는다(29절 결정 26)

    res = client.put(
        f"/api/recipes/{recipe['id']}",
        json={"title": " 볶음밥 ", "servings": 3, "ingredients": [{"name": " 밥 ", "amount": " 1공기 "}], "steps": []},
    )
    assert res.status_code == 200
    updated = res.get_json()
    assert (updated["title"], updated["servings"], updated["ingredients"], updated["steps"]) == (
        "볶음밥",
        3,
        [{"name": "밥", "amount": "1공기", "have": False, "matched_name": None, "stock_quantity": None, "stock_unit": None}],
        [],
    )

    assert client.delete(f"/api/recipes/{second['id']}").status_code == 204
    assert [r["title"] for r in list_recipes(client)["items"]] == ["볶음밥"]


def test_egg_synonym_marks_have(client, login):
    login()
    add_ingredient(client, "달걀 10구")
    ingredients = create(client).get_json()["ingredients"]
    assert ingredients[1] == {
        "name": "계란", "amount": "2개", "have": True, "matched_name": "달걀 10구", "stock_quantity": 1.0, "stock_unit": "개",
    }


def test_ingredient_shows_matched_stock_amount(client, login):
    """29절: 레시피 상세 재료 줄에 매칭된 재고의 남은 양(stock_quantity·stock_unit)을 담는다."""
    login()
    add_ingredient(client, "대파(국산) 1단", quantity=300, unit="g")
    ingredients = create(client).get_json()["ingredients"]
    assert ingredients[0]["stock_quantity"] == 300
    assert ingredients[0]["stock_unit"] == "g"


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
    assert list_recipes(client) == {"items": [], "next_cursor": None}


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


def test_create_recipe_accepts_import_sources_and_image(client, login, app):
    login()
    for source in ("ai", "youtube", "blog"):
        recipe = create(client, source=source).get_json()
        assert client.get(f"/api/recipes/{recipe['id']}").get_json()["source"] == source
    for source in ("public", "hack", None, 1):
        res = create(client, source=source)
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})

    photo = "https://www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.jpg"
    add_public(app, image_url=photo)
    res = create(client, source="ai", image_url=photo)
    assert (res.status_code, res.get_json()["image_url"]) == (201, photo)
    assert create(client, image_url=None).get_json()["image_url"] is None
    for bad in (
        "https://www.foodsafetykorea.go.kr/uploadimg/cook/other.jpg",  # 식약처 주소여도 공공 레시피에 없는 사진
        "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.jpg",
        "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        "javascript:alert(1)",
        "https://evil.example\\@www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.jpg",
        "https://u:p@www.foodsafetykorea.go.kr/uploadimg/cook/10_00100_2.jpg",
        "https://www.foodsafetykorea.go.kr.evil.example/uploadimg/cook/10_00100_2.jpg",
        "https://[",
        photo + "\x00",
        "",
        photo + "a" * 500,
        [photo],
    ):
        res = create(client, source="ai", image_url=bad)
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."}), bad
    for source in ("mine", "youtube"):  # 사진은 AI 레시피에만 붙인다
        res = create(client, source=source, image_url=photo)
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
    res = create(client, image_url=photo)
    assert res.status_code == 400

    recipe = create(client, source="ai", image_url=photo).get_json()
    res = client.put(f"/api/recipes/{recipe['id']}", json={**BODY, "source": "youtube", "image_url": None})
    assert (res.status_code, res.get_json()["source"], res.get_json()["image_url"]) == (200, "ai", photo)


def test_put_keeps_source_url_when_not_sent(client, login):
    login()
    recipe = create(client, source_url="https://example.com/r/1").get_json()
    res = client.put(f"/api/recipes/{recipe['id']}", json={**BODY, "title": "새 제목"})
    assert res.get_json()["source_url"] == "https://example.com/r/1"


def test_other_users_recipe_is_404(client, login):
    login("owner")
    recipe = create(client).get_json()
    login("intruder")
    assert list_recipes(client) == {"items": [], "next_cursor": None}
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
            {"name": "두부", "amount": "1모", "have": False, "matched_name": None, "stock_quantity": None, "stock_unit": None},
            {"name": "진간장", "amount": "2큰술", "have": True, "matched_name": "간장 (500ml)", "stock_quantity": 1.0, "stock_unit": "개"},
            {"name": "물", "amount": "100ml", "have": True, "matched_name": None, "stock_quantity": None, "stock_unit": None},  # 물은 늘 있는 것으로 본다
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


# --- fix round 1 ---


def test_deeply_nested_json_body_returns_400_not_500(client, login):
    # R1: 중첩 배열이 아주 깊어도(파싱기에 따라 RecursionError가 날 수 있어도) 앱은 500이 아니라 400을 준다
    from app import DEFAULT_MESSAGES

    login()
    body = "[" * 100000 + "]" * 100000
    res = client.post("/api/recipes", data=body, content_type="application/json")
    assert (res.status_code, res.get_json()) == (400, {"error": DEFAULT_MESSAGES[400]})


def test_recursion_error_returns_400_json(client, login, monkeypatch):
    # R1: 파서 환경과 상관없이 RecursionError 처리기가 실제로 JSON 400을 주는지 확인한다
    from app import DEFAULT_MESSAGES

    def boom(*_args, **_kwargs):
        raise RecursionError("too deep")

    monkeypatch.setattr(recipes_module, "parse_recipe", boom)
    login()
    res = client.post("/api/recipes", json={"title": "x"})
    assert (res.status_code, res.get_json()) == (400, {"error": DEFAULT_MESSAGES[400]})


def test_steps_raw_list_over_100_rejected_before_filtering_empties(client, login):
    # R4: 빈 문자열만 101개 보내면 다듬은 뒤엔 0개지만, 원본 길이 자체를 먼저 막는다(all()로 다 훑지 않는다)
    login()
    res = create(client, steps=[""] * 101)
    assert (res.status_code, res.get_json()) == (400, {"error": "만드는 법을 다시 확인해주세요."})


def test_save_public_recipe_race_returns_existing_recipe(client, login, app, monkeypatch):
    # R5: 동시에 두 번 눌러 사전 확인은 못 보고(첫 first() 호출을 흉내로 None) 지나갔지만
    # 실제 INSERT가 UNIQUE(user_id, public_recipe_id)에 걸리면, 이긴 쪽 레시피를 200으로 돌려준다.
    user = login()
    recipe_id = add_public(app)
    with app.app_context():
        winner = Recipe(
            user_id=user.id,
            title="두부조림",
            servings=2,
            ingredients=[{"name": "두부", "amount": "1모"}, {"name": "간장", "amount": "2큰술"}],
            steps=["두부를 썰어요.", "간장에 졸여요."],
            source="public",
            public_recipe_id=recipe_id,
        )
        db.session.add(winner)
        db.session.commit()
        winner_id = winner.id
        QueryClass = type(Recipe.query)

    real_first = QueryClass.first
    calls = []

    def fake_first(self):
        calls.append(1)
        if len(calls) == 1:  # 사전 확인 시점엔 아직 못 본 척한다(동시 요청 흉내)
            return None
        return real_first(self)

    monkeypatch.setattr(QueryClass, "first", fake_first)
    res = client.post(f"/api/public-recipes/{recipe_id}/save")
    assert (res.status_code, res.get_json()["id"]) == (200, winner_id)
    with app.app_context():
        assert Recipe.query.filter_by(user_id=user.id).count() == 1


def test_recipe_at_max_boundaries_is_created(client, login):
    # R6: 제목 60자, 인분 20, 재료 50개(양 30자), 단계 30개(그중 하나 500자) → 201
    login()
    ingredients = [{"name": f"재료{i}", "amount": "1" * 30} for i in range(50)]
    steps = ["단계"] * 29 + ["가" * 500]
    res = create(client, title="가" * 60, servings=20, ingredients=ingredients, steps=steps)
    assert res.status_code == 201
    body = res.get_json()
    assert (len(body["title"]), body["servings"], len(body["ingredients"]), len(body["steps"])) == (60, 20, 50, 30)
    assert body["ingredients"][0]["amount"] == "1" * 30
    assert len(body["steps"][-1]) == 500


def test_max_recipes_per_user_is_1000():
    assert recipes_module.MAX_RECIPES_PER_USER == 1000


def test_save_public_recipe_out_of_range_id_is_404(client, login):
    login()
    assert client.post(f"/api/public-recipes/{2**40}/save").status_code == 404


# --- fix round 1 (P-B2: 내 레시피 커서 페이지네이션) ---


def _make_recipes(app, user_id, count):
    from datetime import datetime, timedelta, timezone

    with app.app_context():
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        recipes = [
            Recipe(user_id=user_id, title=f"레시피{i:02d}", servings=2, ingredients=[{"name": "재료", "amount": ""}], steps=[], source="mine")
            for i in range(count)
        ]
        db.session.add_all(recipes)
        db.session.flush()
        for i, r in enumerate(recipes):
            r.updated_at = base + timedelta(seconds=i // 2)  # 둘씩 짝지어 같은 시각(동률 처리 확인용)
        db.session.commit()
        return [r.id for r in recipes]


def test_recipe_list_cursor_pages_through_65_without_duplicates_or_gaps(client, login, app):
    user = login()
    ids = _make_recipes(app, user.id, 65)

    pages, seen = [], []
    cursor = None
    for _ in range(10):
        body = list_recipes(client, f"?cursor={cursor}" if cursor else "")
        pages.append(len(body["items"]))
        seen.extend(r["id"] for r in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == [30, 30, 5]
    assert sorted(seen) == sorted(ids)
    assert len(seen) == len(set(seen)) == 65


def test_recipe_list_invalid_cursor_is_400(client, login):
    login()
    res = client.get("/api/recipes?cursor=not-a-valid-cursor!!")
    assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})


def test_recipe_list_pagination_never_leaks_other_users_recipes(client, login, app):
    owner = login("owner")
    owner_ids = _make_recipes(app, owner.id, 40)

    intruder = login("intruder")
    _make_recipes(app, intruder.id, 5)

    with client.session_transaction() as s:  # 세션을 owner로 되돌린다(login()은 매번 새 사용자를 만든다)
        s["user_id"], s["pid"] = owner.id, owner.provider_id
    seen = []
    cursor = None
    for _ in range(10):
        body = list_recipes(client, f"?cursor={cursor}" if cursor else "")
        seen.extend(r["id"] for r in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(owner_ids)


# --- 3a final review fix wave ---


def test_recipe_list_cursor_id_out_of_range_is_400(client, login):
    # M4: 커서 안의 id가 DB int 컬럼 범위를 넘으면(Postgres에서 500이 나던 값) 조회 없이 400
    login()
    huge = encode_cursor(datetime(2026, 1, 1, tzinfo=timezone.utc), 2**31)
    zero = encode_cursor(datetime(2026, 1, 1, tzinfo=timezone.utc), 0)
    for cursor in (huge, zero):
        res = client.get(f"/api/recipes?cursor={cursor}")
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})


def test_recipe_detail_annotate_is_fast_with_large_inventory(client, login, app):
    # M7: annotate가 추천과 같은 준비된 재고(_prepared_stock) + 빠른 매칭(_match_key_fast)을 쓰는지.
    # 맞는 재고 50개를 뒤쪽(1950~1999, id가 커서 매칭 순서도 맨 뒤)에만 두고 앞 1,950개는 안 맞는 채움 이름으로 둔다 — 앞쪽에
    # 바로 맞으면 미준비 구현(비교마다 정규식으로 다시 prepare)도 우연히 빨리 끝나 회귀를 못 잡는다(리뷰 minor).
    # 이렇게 하면 재료 50개 × 재고 최대 2,000개를 거의 다 훑어야 한다(약 98,000번 비교). 미준비 구현은 이 테스트에서 약 0.42초(재리뷰 실측).
    words = ["대파", "양파", "두부", "계란", "감자", "당근", "애호박", "돼지고기", "소고기", "닭가슴살",
             "김치", "콩나물", "시금치", "표고버섯", "고추", "마늘", "간장", "고추장", "된장", "설탕"]
    user = login()
    with app.app_context():
        location = StorageLocation.query.filter_by(user_id=user.id).first()
        db.session.add_all(
            Ingredient(user_id=user.id, location_id=location.id, name=f"안맞는재료{i}", purchased_on=seoul_today())
            for i in range(1950)
        )
        db.session.add_all(
            Ingredient(user_id=user.id, location_id=location.id, name=f"{words[i % 20]} {1950 + i}", purchased_on=seoul_today())
            for i in range(50)
        )
        db.session.commit()
    ingredients = [{"name": words[i % 20], "amount": "1개"} for i in range(50)]
    recipe = create(client, ingredients=ingredients).get_json()

    started = time.perf_counter()
    res = client.get(f"/api/recipes/{recipe['id']}")
    elapsed = time.perf_counter() - started
    assert res.status_code == 200
    assert all(row["have"] for row in res.get_json()["ingredients"])
    # 0.3초: 상세가 이제 cooked 계산으로 인덱스된 COUNT 쿼리 하나를 더 한다(29절 결정 26, Task 5) —
    # 준비된 구현은 이 안에 들어오고, 미준비 구현(약 0.42초)은 걸린다.
    assert elapsed < 0.3, f"{elapsed:.3f}s"


# --- 4b-1 Task 1: stock_context/match_summary, /api/recipes/choices ---


def test_match_summary_counts_and_urgent_names(client, login, app):
    user = login()
    add_ingredient(client, "두부", expires_on=seoul_today().isoformat())
    add_ingredient(client, "대파")
    ingredients = [{"name": "두부", "amount": "1모"}, {"name": "대파", "amount": "1대"}, {"name": "돼지고기", "amount": "200g"}]
    with app.app_context():
        prepared_stock, urgent = recipes_module.stock_context(user.id)
        summary = recipes_module.match_summary(ingredients, prepared_stock, urgent)
    assert summary == {"have_count": 2, "total_count": 3, "urgent_names": ["두부"]}


def test_recipe_choices_sorted_by_match_and_filtered(client, login, app):
    login()
    add_ingredient(client, "대파")
    add_ingredient(client, "두부")
    full = create(client, title="김치찌개", ingredients=[{"name": "대파", "amount": "1대"}, {"name": "두부", "amount": "1모"}]).get_json()
    half = create(client, title="된장찌개", ingredients=[{"name": "대파", "amount": "1대"}, {"name": "소고기", "amount": "200g"}]).get_json()
    none_match = create(client, title="볶음밥", ingredients=[{"name": "당근", "amount": "1개"}, {"name": "양파", "amount": "1개"}]).get_json()

    body = client.get("/api/recipes/choices").get_json()
    ids = [item["id"] for item in body["items"]]
    assert ids == [full["id"], half["id"], none_match["id"]]
    by_id = {item["id"]: item for item in body["items"]}
    assert (by_id[full["id"]]["have_count"], by_id[full["id"]]["total_count"]) == (2, 2)
    assert (by_id[none_match["id"]]["have_count"], by_id[none_match["id"]]["total_count"]) == (0, 2)

    filtered = client.get("/api/recipes/choices?q=찌개").get_json()["items"]
    assert {item["id"] for item in filtered} == {full["id"], half["id"]}

    assert client.get(f"/api/recipes/choices?q={'가' * 51}").status_code == 200

    login("other")
    assert client.get("/api/recipes/choices?q=찌개").get_json()["items"] == []


def test_recipe_choices_handles_recipe_with_no_ingredients(client, login, app):
    # fix round 1: 공공 레시피 저장·동기화는 빈 RCP_PARTS_DTLS를 ingredients=[]로 그대로 둘 수 있다(POST /recipes API는
    # 1개 이상을 요구해 막지만, save/sync 경로는 검증을 거치지 않는다) — 0/0 점수 계산이 500을 내면 안 된다.
    user = login()
    with app.app_context():
        db.session.add(Recipe(user_id=user.id, title="재료 없음", servings=1, ingredients=[], steps=[]))
        db.session.commit()

    res = client.get("/api/recipes/choices")
    assert res.status_code == 200
    item = res.get_json()["items"][0]
    assert (item["title"], item["have_count"], item["total_count"], item["urgent_names"]) == ("재료 없음", 0, 0, [])
