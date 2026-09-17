from datetime import timedelta

import pytest

from app.cooklog import is_seasoning, item_cost, round_won, summarize
from app.ingredients import seoul_today
from app.models import Ingredient, Recipe, db
from tests.test_meals import add_ingredient, add_recipe


def stock_ids(app, name):
    with app.app_context():
        return [i.id for i in Ingredient.query.filter_by(name=name).order_by(Ingredient.id)]


def test_round_won_and_item_cost():
    assert round_won(3870) == 3870
    assert round_won(833.33) == 830
    assert round_won(835) == 840
    assert round_won(10820, 100) == 10800
    assert item_cost(0.3, 12900, 1) == 3870
    assert item_cost(1, 2500, 3) == 830
    assert item_cost(1, 2480, 1) == 2480
    assert item_cost(2, 2480, 1) == 2480  # 비율 1로 자름
    assert item_cost(30, 4980, 300) == 500  # 498 → 500
    assert item_cost(1, None, 1) is None
    assert item_cost(1, 1000, None) is None
    assert item_cost(1, 1000, 0) is None
    assert item_cost(0.575, 11800, 1) == 6790  # 6784.999… 부동소수 경계
    assert item_cost(0.043, 10000, 2) == 220  # 214.999… 부동소수 경계


def row(cost, excluded=None):
    return {"cost": cost, "excluded": excluded}


def test_summarize():
    items = [row(3870), row(2480), row(830), row(None, "no_price"), row(None, "seasoning")]
    assert summarize(9000, 2, items) == {"ingredient_cost": 7180, "saved": 10820, "excluded_count": 1}
    assert summarize(None, 2, items) == {"ingredient_cost": 7180, "saved": None, "excluded_count": 1}
    assert summarize(9000, 2, [row(None, "no_price")]) == {"ingredient_cost": 0, "saved": None, "excluded_count": 1}
    assert summarize(3000, 1, [row(4200)])["saved"] == -1200
    assert summarize(0, 1, [row(4200)])["saved"] == -4200  # 0원도 값


def test_summarize_reads_model_rows():
    class Item:
        def __init__(self, cost, excluded):
            self.cost, self.excluded = cost, excluded

    assert summarize(9000, 1, [Item(2000, None), Item(None, "no_price")]) == {"ingredient_cost": 2000, "saved": 7000, "excluded_count": 1}


@pytest.mark.parametrize(
    "key, amount, expected",
    [
        ("고춧가루", "1큰술", True),
        ("다진 마늘", "1작은술", True),
        ("소금", "약간", True),
        ("진간장", "2", True),  # 필수품 names_match
        ("밀가루", "1컵", False),
        ("김치", "300g", False),
        ("두부", "1/2모", False),
        ("후추", "", False),
    ],
)
def test_is_seasoning(key, amount, expected):
    assert is_seasoning(key, amount, ["간장"]) is expected


def test_draft_rows_defaults(client, login, app):
    login()
    add_ingredient(client, "김치", quantity=1, unit="kg")
    add_ingredient(client, "두부", quantity=1, unit="모")
    add_ingredient(client, "대파", quantity=3, unit="대")
    add_ingredient(client, "고춧가루", quantity=100, unit="g")
    recipe = add_recipe(
        client,
        "김치찌개",
        [
            {"name": "김치", "amount": "300g"},
            {"name": "두부", "amount": "1모"},
            {"name": "대파", "amount": "1대"},
            {"name": "고춧가루", "amount": "1큰술"},
            {"name": "돼지고기", "amount": "200g"},
            {"name": "물", "amount": "400ml"},
        ],
        servings=2,
    )
    res = client.get(f"/api/recipes/{recipe['id']}/cook-draft")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    body = res.get_json()
    assert (body["recipe_id"], body["title"], body["servings"]) == (recipe["id"], "김치찌개", 2)
    rows = {r["name"]: r for r in body["rows"]}
    assert [r["name"] for r in body["rows"]] == ["김치", "두부", "대파", "고춧가루", "돼지고기"]
    assert rows["김치"] == {
        "name": "김치",
        "amount": "300g",
        "ingredient_id": stock_ids(app, "김치")[0],
        "stock_name": "김치",
        "stock_quantity": 1.0,
        "stock_unit": "kg",
        "base_amount": 0.3,
        "seasoning": False,
    }
    assert rows["대파"]["base_amount"] == 1.0
    assert (rows["고춧가루"]["seasoning"], rows["고춧가루"]["base_amount"]) == (True, None)
    assert (rows["돼지고기"]["ingredient_id"], rows["돼지고기"]["stock_name"], rows["돼지고기"]["base_amount"]) == (None, None, None)


def test_draft_unit_mismatch_and_one_stock_per_row(client, login, app):
    login()
    add_ingredient(client, "대파", quantity=1, unit="단")
    recipe = add_recipe(client, "파무침", [{"name": "대파", "amount": "1대"}, {"name": "쪽파", "amount": "2대"}, {"name": "파", "amount": "1대"}])
    rows = client.get(f"/api/recipes/{recipe['id']}/cook-draft").get_json()["rows"]
    assert [r["ingredient_id"] for r in rows] == [stock_ids(app, "대파")[0], None, None]
    assert rows[0]["base_amount"] is None  # 단 ≠ 대


def test_draft_one_stock_goes_to_first_matching_row(client, login, app):
    login()
    add_ingredient(client, "대파", quantity=2, unit="대")
    recipe = add_recipe(client, "파국", [{"name": "대파", "amount": "1대"}, {"name": "대파(고명)", "amount": "1대"}])
    rows = client.get(f"/api/recipes/{recipe['id']}/cook-draft").get_json()["rows"]
    assert [r["ingredient_id"] for r in rows] == [stock_ids(app, "대파")[0], None]


def test_draft_marks_staple_seasoning(client, login, app):
    login()
    # 굴소스는 기본 필수품(조미료 분류, 2026-09-17)이라 그대로 쓰고, "소스" 분류(사용자가 직접 만든 것)도 양념으로 치는지 따로 확인
    assert client.post("/api/staples", json={"name": "우리집 소스", "category": "소스"}).status_code == 201
    add_ingredient(client, "굴소스", quantity=500, unit="g")
    add_ingredient(client, "우리집 소스", quantity=200, unit="g")
    add_ingredient(client, "두부", quantity=1, unit="모")
    recipe = add_recipe(
        client,
        "두부조림",
        [{"name": "굴소스", "amount": "30g"}, {"name": "우리집 소스", "amount": "20g"}, {"name": "두부", "amount": "1모"}],
    )
    rows = client.get(f"/api/recipes/{recipe['id']}/cook-draft").get_json()["rows"]
    # 숟가락·약간 양이 아니어도 조미료 분류 필수품이면 양념(기본 안 빼기), 재고에는 붙는다
    assert [(r["name"], r["seasoning"], r["ingredient_id"], r["base_amount"]) for r in rows] == [
        ("굴소스", True, stock_ids(app, "굴소스")[0], 30.0),
        ("우리집 소스", True, stock_ids(app, "우리집 소스")[0], 20.0),
        ("두부", False, stock_ids(app, "두부")[0], 1.0),
    ]


def test_draft_prefers_urgent_stock(client, login, app):
    login()
    today = seoul_today()
    add_ingredient(client, "두부", expires_on=(today + timedelta(days=30)).isoformat())
    add_ingredient(client, "두부", expires_on=(today + timedelta(days=1)).isoformat())
    recipe = add_recipe(client, "두부부침", [{"name": "두부", "amount": "1모"}])
    rows = client.get(f"/api/recipes/{recipe['id']}/cook-draft").get_json()["rows"]
    assert rows[0]["ingredient_id"] == stock_ids(app, "두부")[1]


def test_draft_eat_out_and_ownership(client, login, app):
    assert client.get("/api/recipes/1/cook-draft").status_code == 401
    login("2")
    add_ingredient(client, "김치", quantity=1, unit="kg")  # 남의 재고는 붙지 않는다
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    with app.app_context():
        saved = db.session.get(Recipe, recipe["id"])
        saved.eat_out_price, saved.eat_out_source = 9000, "ai"
        db.session.commit()
    body = client.get(f"/api/recipes/{recipe['id']}/cook-draft").get_json()
    assert (body["eat_out_price"], body["eat_out_source"]) == (9000, "ai")
    assert (body["rows"][0]["ingredient_id"], body["rows"][0]["stock_name"]) == (None, None)
    assert client.get("/api/recipes/2147483648/cook-draft").status_code == 404
    login("3")
    assert client.get(f"/api/recipes/{recipe['id']}/cook-draft").status_code == 404
