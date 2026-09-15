import json

import pytest

from app import foods, outbound
from app.models import AiCall
from tests.test_foods import item, make_fetch, make_user, page
from tests.test_nutrition import add_foods, cached

# --- serving_grams ---


@pytest.mark.parametrize(
    "value, expected",
    [
        ("400g", 400.0),
        ("400 G", 400.0),
        ("1,000g", 1000.0),
        ("250ml", 250.0),
        (400, 400.0),
        ("0g", None),
        ("6000g", None),
        ("", None),
        (None, None),
        ("1회", None),
        (True, None),
    ],
)
def test_serving_grams(value, expected):
    assert foods.serving_grams(value) == expected


# --- row_fields reads serving ---


def test_row_fields_reads_serving():
    assert foods.row_fields(item("D1", "제육덮밥", group="음식", serving="400g"))["serving_g"] == 400.0
    assert foods.row_fields(item("D1", "제육덮밥", group="음식"))["serving_g"] is None


# --- dish_items ---


def test_dish_items_only_dishes_in_order(app):
    add_foods(
        app,
        cached("D1", "제육덮밥", 185.4, group="음식", source="api", serving_g=400),
        cached("D2", "제육볶음", 190, group="음식", source="api"),
        cached("D3", "제육덮밥소스", 50, group="가공식품", source="api"),
        cached("ai:제육덮밥", "제육덮밥", 500, group="추정", source="ai"),
    )
    with app.app_context():
        assert [r["name"] for r in foods.dish_items("제육덮밥")] == ["제육덮밥"]
        assert [r["name"] for r in foods.dish_items("제육 덮밥")] == ["제육덮밥"]
        assert [r["name"] for r in foods.dish_items("제육")] == ["제육덮밥", "제육볶음"]
        assert foods.dish_items("100%") == []

        first = foods.dish_items("제육덮밥")[0]
        assert set(first) == {"food_code", "name", "serving_g", "kcal", "carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg"}
        assert first["kcal"] == 185.4  # 반올림하지 않는다(search_items와 다름)


# --- food_by_code ---


def test_food_by_code(app):
    add_foods(
        app,
        cached("D1", "제육덮밥", 185, group="음식", source="api"),
        cached("ai:x", "다른음식", 100, group="추정", source="ai"),
    )
    with app.app_context():
        assert foods.food_by_code("D1").food_code == "D1"
        assert foods.food_by_code("ai:x") is None
        assert foods.food_by_code("NOPE") is None
        assert foods.food_by_code(123) is None
        assert foods.food_by_code("") is None


# --- GET /api/foods/dishes ---


def test_dishes_endpoint(client, raw_client, login, app, monkeypatch):
    login()

    assert raw_client.get("/api/foods/dishes?q=제육덮밥").status_code == 401

    res = client.get("/api/foods/dishes", query_string={"q": "  "})
    assert (res.status_code, res.get_json()["error"]) == (400, "찾을 음식 이름을 입력해주세요.")
    res = client.get("/api/foods/dishes", query_string={"q": "()"})
    assert (res.status_code, res.get_json()["error"]) == (400, "찾을 음식 이름을 입력해주세요.")

    app.config.update(DEV_MODE=False)
    res = client.get("/api/foods/dishes?q=제육덮밥")
    assert (res.status_code, res.get_json()["error"]) == (503, foods.OFF)
    app.config.update(DEV_MODE=True)

    def fail(*a, **k):
        raise AssertionError("sample 모드는 fetch_page를 부르면 안 돼요")

    monkeypatch.setattr(foods, "fetch_page", fail)

    res = client.get("/api/foods/dishes?q=제육덮밥")
    body = res.get_json()
    assert res.status_code == 200
    assert body["items"][0] == {
        "food_code": "SAMPLE-18", "name": "제육덮밥", "serving_g": 400.0, "kcal": 185.0,
        "carbs_g": 22.0, "protein_g": 8.5, "fat_g": 6.8, "sugars_g": 5.5, "sodium_mg": 410.0,
    }
    assert body["searched"] is True
    with app.app_context():
        assert AiCall.query.count() == 0


def test_on_mode_stores_serving_from_api(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    client = app.test_client()
    client.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    with app.app_context():
        user = make_user()
        user_id = user.id
    with client.session_transaction() as s:
        s["user_id"], s["pid"] = user_id, "1"

    fetch, _ = make_fetch([page([item("D1", "제육덮밥", group="음식", kcal="185", serving="400g")], 1)])
    monkeypatch.setattr(outbound, "fetch_fixed", fetch)

    res = client.get("/api/foods/dishes?q=제육덮밥")
    body = res.get_json()
    assert res.status_code == 200
    assert body["items"][0]["serving_g"] == 400.0


# --- sample_foods.json ---


def test_sample_dishes_have_serving():
    rows = json.loads(foods.SAMPLE_FILE.read_text(encoding="utf-8"))
    dishes = [row for row in rows if row.get("group") == "음식"]
    assert dishes
    for row in dishes:
        assert foods.serving_grams(row.get("serving_g")) is not None
