from app.ingredients import seoul_today
from app.models import Ingredient, Recipe, db


def create_ingredient(client, **fields):
    body = {"name": "우유", "quantity": 1, "unit": "개", "purchased_on": seoul_today().isoformat(), **fields}
    return client.post("/api/ingredients", json=body)


def create_recipe(client, **fields):
    body = {
        "title": "대파 계란볶음밥",
        "servings": 1,
        "ingredients": [{"name": "대파", "amount": "1대"}],
        "steps": [],
        **fields,
    }
    return client.post("/api/recipes", json=body)


def price_quantity_of(app, item_id):
    with app.app_context():
        return db.session.get(Ingredient, item_id).price_quantity


def test_create_sets_price_quantity(client, login, app):
    login()
    with_price = create_ingredient(client, name="깐마늘", quantity=300, unit="g", price=4980).get_json()
    assert price_quantity_of(app, with_price["id"]) == 300.0

    without_price = create_ingredient(client, name="대파", quantity=2, unit="대").get_json()
    assert price_quantity_of(app, without_price["id"]) is None

    bulk = client.post(
        "/api/ingredients/bulk",
        json={
            "items": [
                {"name": "두부", "quantity": 1, "unit": "모", "purchased_on": seoul_today().isoformat(), "price": 2480},
                {"name": "김치", "quantity": 1, "unit": "kg", "purchased_on": seoul_today().isoformat()},
            ]
        },
    ).get_json()
    assert price_quantity_of(app, bulk[0]["id"]) == 1.0
    assert price_quantity_of(app, bulk[1]["id"]) is None


def test_patch_rules(client, login, app):
    login()
    item = create_ingredient(client, name="깐마늘", quantity=300, unit="g", price=4980).get_json()
    item_id = item["id"]

    client.patch(f"/api/ingredients/{item_id}", json={"quantity": 100})
    assert price_quantity_of(app, item_id) == 300.0  # 수량만은 안 바뀜

    full_body = {
        "name": "깐마늘",
        "quantity": 90,
        "unit": "g",
        "price": 4980,
        "purchased_on": seoul_today().isoformat(),
        "location_id": item["location_id"],
    }
    client.patch(f"/api/ingredients/{item_id}", json=full_body)
    assert price_quantity_of(app, item_id) == 300.0  # 폼처럼 전체 body를 보내도 price·unit이 그대로면 안 바뀜 (개정 1 P17)

    client.patch(f"/api/ingredients/{item_id}", json={"quantity": 100})
    assert price_quantity_of(app, item_id) == 300.0

    client.patch(f"/api/ingredients/{item_id}", json={"price": 5000})
    assert price_quantity_of(app, item_id) == 100.0

    client.patch(f"/api/ingredients/{item_id}", json={"unit": "kg", "quantity": 0.1})
    assert price_quantity_of(app, item_id) == 0.1

    client.patch(f"/api/ingredients/{item_id}", json={"price": None})
    assert price_quantity_of(app, item_id) is None

    client.patch(f"/api/ingredients/{item_id}", json={"price": 3000})
    assert price_quantity_of(app, item_id) == 0.1


def test_recipe_json_has_eat_out_fields(client, login, app):
    login()
    created = create_recipe(client).get_json()
    assert (created["eat_out_price"], created["eat_out_source"]) == (None, None)

    recipe_id = created["id"]
    fetched = client.get(f"/api/recipes/{recipe_id}").get_json()
    assert (fetched["eat_out_price"], fetched["eat_out_source"]) == (None, None)

    with app.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        recipe.eat_out_price, recipe.eat_out_source = 9000, "ai"
        db.session.commit()

    fetched = client.get(f"/api/recipes/{recipe_id}").get_json()
    assert (fetched["eat_out_price"], fetched["eat_out_source"]) == (9000, "ai")

    put_body = {
        "title": "대파 계란볶음밥",
        "servings": 1,
        "ingredients": [{"name": "대파", "amount": "1대"}],
        "steps": [],
        "eat_out_price": 1,
    }
    updated = client.put(f"/api/recipes/{recipe_id}", json=put_body).get_json()
    assert (updated["eat_out_price"], updated["eat_out_source"]) == (9000, "ai")
