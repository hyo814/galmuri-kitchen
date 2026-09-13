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
