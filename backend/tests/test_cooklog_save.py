import io
import json
import os
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa

from app import photos
from app.locations import default_location
from app.models import CookLog, FoodLog, Ingredient, IngredientRemoval, Recipe, StorageLocation, db
from tests.test_meals import add_recipe, make_plan, put_slot
from tests.test_shopping_notes import JPEG, as_user, photo_path

BAD = "잘못된 요청이에요."
STOCK_CHANGED = "재고가 방금 바뀌었어요. 다시 불러와주세요."
KIMCHI_STEW = [
    {"name": "김치", "amount": "300g"},
    {"name": "두부", "amount": "1모"},
    {"name": "대파", "amount": "1대"},
    {"name": "고춧가루", "amount": "1큰술"},
    {"name": "돼지고기", "amount": "200g"},
    {"name": "물", "amount": "400ml"},
]


@pytest.fixture(autouse=True)
def today(monkeypatch):
    for target in ("app.food_logs.seoul_today", "app.ingredients.seoul_today", "app.meals.seoul_today"):
        monkeypatch.setattr(target, lambda: date(2026, 9, 15))


def stock(client, name, quantity, unit, price=None):
    body = {"name": name, "quantity": quantity, "unit": unit, "purchased_on": "2026-09-10", "price": price}
    res = client.post("/api/ingredients", json=body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def cook(client, recipe_id, usages, image=None, **data):
    body = {"recipe_id": recipe_id, "servings": 2, "cooked_on": "2026-09-15", "usages": usages, "food_log": False, **data}
    form = {"data": json.dumps(body), **({"image": (io.BytesIO(image), "a.jpg")} if image else {})}
    return client.post("/api/cook-logs", data=form, content_type="multipart/form-data")


def error(res):
    return res.status_code, res.get_json()["error"]


def stock_map(client):
    return {i["name"]: i for i in client.get("/api/ingredients").get_json()}


def quantities(client):
    return {name: (i["quantity"], i["unit"]) for name, i in stock_map(client).items()}


def counts(app):
    with app.app_context():
        return CookLog.query.count(), FoodLog.query.count(), IngredientRemoval.query.count()


def kimchi_setup(client):
    ids = {
        "김치": stock(client, "김치", 1, "kg", 12900),
        "두부": stock(client, "두부", 1, "모", 2480),
        "대파": stock(client, "대파", 3, "대", 2500),
        "고춧가루": stock(client, "고춧가루", 100, "g", 3000),
    }
    recipe = add_recipe(client, "김치찌개", KIMCHI_STEW, servings=2)
    usages = [
        {"ingredient_id": ids["김치"], "amount": 0.3},
        {"ingredient_id": ids["두부"], "amount": 1},
        {"ingredient_id": ids["대파"], "amount": 1},
        {"ingredient_id": ids["고춧가루"], "amount": 5},  # 양념을 켜서 뺐다 — 재료비에는 넣지 않는다
    ]
    return recipe, ids, usages


def test_save_deducts_and_snapshots_money(client, login, app):
    login()
    recipe, ids, usages = kimchi_setup(client)
    res = cook(client, recipe["id"], usages, eat_out_price=9000)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["deducted_names"] == ["김치", "두부", "대파", "고춧가루"]
    log = body["log"]
    # 고춧가루는 가격(100g 3,000원 → 5g 150원)이 있어도 양념이라 7,180에 들어가지 않는다(Task 2 carry-over)
    assert (log["ingredient_cost"], log["saved"], log["excluded_count"]) == (7180, 10820, 1)
    assert (log["eat_out_price"], log["eat_out_source"], log["title"], log["servings"]) == (9000, "user", "김치찌개", 2)
    assert (log["recipe_id"], log["cooked_on"], log["food_log_id"], log["photo_url"]) == (recipe["id"], "2026-09-15", None, None)
    assert [(i["name"], i["excluded"], i["cost"]) for i in log["items"]] == [
        ("김치", None, 3870), ("두부", None, 2480), ("대파", None, 830), ("고춧가루", "seasoning", None), ("돼지고기", "no_price", None),
    ]
    items = {i["name"]: i for i in log["items"]}
    assert (items["돼지고기"]["amount_text"], items["돼지고기"]["used"]) == ("200g", None)
    assert items["두부"]["removed"] is True and items["김치"]["removed"] is False
    assert (items["김치"]["used"], items["김치"]["unit"], items["김치"]["price"], items["김치"]["price_quantity"]) == (0.3, "kg", 12900, 1.0)
    created = datetime.fromisoformat(log["created_at"])
    assert datetime.fromisoformat(log["undo_until"]) == created + timedelta(seconds=120)

    left = quantities(client)
    assert (left["김치"], left["대파"], left["고춧가루"]) == ((0.7, "kg"), (2.0, "대"), (95.0, "g"))
    assert "두부" not in left
    with app.app_context():
        assert [(r.name, r.reason) for r in IngredientRemoval.query.all()] == [("두부", "eaten")]
    got = client.get(f"/api/recipes/{recipe['id']}").get_json()
    assert (got["eat_out_price"], got["eat_out_source"]) == (9000, "user")


def test_overuse_and_tiny_left(client, login):
    login()
    recipe = add_recipe(client, "우유푸딩", [{"name": "우유", "amount": "1L"}])
    milk = stock(client, "우유", 1, "L", 3000)
    salt = stock(client, "소금", 1.0004, "kg")
    sugar = stock(client, "설탕", 1.002, "kg")
    usages = [{"ingredient_id": milk, "amount": 2}, {"ingredient_id": salt, "amount": 1}, {"ingredient_id": sugar, "amount": 1}]
    res = cook(client, recipe["id"], usages)
    assert res.status_code == 201, res.get_json()
    items = {i["name"]: i for i in res.get_json()["log"]["items"]}
    assert (items["우유"]["used"], items["우유"]["cost"], items["우유"]["removed"]) == (1.0, 3000, True)
    assert items["소금"]["removed"] is True
    assert items["설탕"]["removed"] is False
    left = quantities(client)
    assert "우유" not in left and "소금" not in left
    assert left["설탕"] == (0.002, "kg")


def test_counted_rules(client, login):
    login()
    recipe = add_recipe(client, "김치볶음", [{"name": "김치", "amount": "300g"}])
    kimchi = stock(client, "김치", 1, "kg", 12900)
    tofu = stock(client, "두부", 10, "모")
    no_eat_out = cook(client, recipe["id"], [{"ingredient_id": kimchi, "amount": 0.3}]).get_json()["log"]
    assert (no_eat_out["ingredient_cost"], no_eat_out["saved"]) == (3870, None)
    unpriced = cook(client, recipe["id"], [{"ingredient_id": tofu, "amount": 1}], eat_out_price=9000).get_json()["log"]
    assert (unpriced["ingredient_cost"], unpriced["saved"], unpriced["excluded_count"]) == (0, None, 1)
    pricey = cook(client, recipe["id"], [{"ingredient_id": kimchi, "amount": 5}], eat_out_price=3000, servings=1).get_json()["log"]
    assert (pricey["ingredient_cost"], pricey["saved"]) == (9030, 3000 - 9030)  # 남은 0.7kg만 뺐다


def test_eat_out_keeps_recipe_source_and_blank_does_not_clear(client, login, app):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    with app.app_context():
        saved = db.session.get(Recipe, recipe["id"])
        saved.eat_out_price, saved.eat_out_source = 9000, "ai"
        db.session.commit()
        updated_at = saved.updated_at
    log = cook(client, recipe["id"], [], eat_out_price=9000).get_json()["log"]
    assert (log["eat_out_price"], log["eat_out_source"]) == (9000, "ai")
    log = cook(client, recipe["id"], [], eat_out_price=None).get_json()["log"]
    assert (log["eat_out_price"], log["eat_out_source"]) == (None, None)
    got = client.get(f"/api/recipes/{recipe['id']}").get_json()
    assert (got["eat_out_price"], got["eat_out_source"]) == (9000, "ai")
    log = cook(client, recipe["id"], [], eat_out_price=8000).get_json()["log"]
    assert (log["eat_out_price"], log["eat_out_source"]) == (8000, "user")
    got = client.get(f"/api/recipes/{recipe['id']}").get_json()
    assert (got["eat_out_price"], got["eat_out_source"]) == (8000, "user")
    with app.app_context():
        assert db.session.get(Recipe, recipe["id"]).updated_at == updated_at  # 내 레시피 목록 순서를 지킨다


def test_food_log_created_and_slot_link(client, login, app, monkeypatch):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    other = add_recipe(client, "된장찌개", [{"name": "된장", "amount": "1큰술"}])
    res = cook(client, recipe["id"], [], food_log=True, meal="dinner")
    assert res.status_code == 201, res.get_json()
    logs = client.get("/api/food-logs?date=2026-09-15").get_json()["logs"]
    assert len(logs) == 1
    food = logs[0]
    assert (food["source"], food["place"], food["servings"], food["meal"], food["title"], food["recipe_id"]) == (
        "cook_log", "home", 1.0, "dinner", "김치찌개", recipe["id"],
    )
    assert res.get_json()["log"]["food_log_id"] == food["id"]

    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], meal="dinner", recipe_id=recipe["id"]).get_json()
    breakfast = put_slot(client, plan["id"], meal="breakfast", recipe_id=recipe["id"]).get_json()
    other_slot = put_slot(client, plan["id"], meal="lunch", recipe_id=other["id"]).get_json()

    def eaten_ids():
        return {s["id"]: s["eaten_log_id"] for s in client.get(f"/api/meal-plans/{plan['id']}").get_json()["slots"]}

    linked = cook(client, recipe["id"], [], food_log=True, meal_slot_id=slot["id"]).get_json()["log"]
    food = next(f for f in client.get("/api/food-logs?date=2026-09-15").get_json()["logs"] if f["id"] == linked["food_log_id"])
    assert (food["source"], food["meal"], food["meal_slot_id"]) == ("cook_log", "dinner", slot["id"])
    assert eaten_ids()[slot["id"]] == food["id"]

    # 9/15 칸에서 열었지만 날짜를 9/14로 바꿨다 — 칸에 붙이지 않는다(개정 1 P7)
    moved = cook(client, recipe["id"], [], food_log=True, meal_slot_id=breakfast["id"], cooked_on="2026-09-14", meal="lunch")
    assert moved.status_code == 201, moved.get_json()
    food = client.get("/api/food-logs?date=2026-09-14").get_json()["logs"][0]
    assert (food["meal"], food["meal_slot_id"], food["source"], food["id"]) == ("lunch", None, "cook_log", moved.get_json()["log"]["food_log_id"])
    assert eaten_ids()[breakfast["id"]] is None

    # 이미 먹은 칸 — 일기만 남기고 먹은 기록은 만들지 않는다(결정 16)
    assert client.post(f"/api/meal-slots/{breakfast['id']}/eaten").status_code == 201
    before = len(client.get("/api/food-logs?date=2026-09-15").get_json()["logs"])
    again = cook(client, recipe["id"], [], food_log=True, meal_slot_id=breakfast["id"])
    assert again.status_code == 201, again.get_json()
    assert again.get_json()["log"]["food_log_id"] is None
    assert len(client.get("/api/food-logs?date=2026-09-15").get_json()["logs"]) == before

    assert error(cook(client, recipe["id"], [], food_log=True, meal_slot_id=other_slot["id"])) == (400, BAD)
    assert error(cook(client, recipe["id"], [], food_log=True)) == (400, "끼니를 골라주세요.")

    tofu = stock(client, "두부", 1, "모")
    monkeypatch.setattr("app.food_logs.MAX_PER_DAY", 0)
    capped = cook(client, recipe["id"], [{"ingredient_id": tofu, "amount": 1}], food_log=True, meal="lunch")
    assert error(capped) == (400, "하루에 0개까지 남길 수 있어요.")
    assert quantities(client)["두부"] == (1.0, "모")


def test_photo_saved_and_owner_only(client, login, app):
    user = login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    res = cook(client, recipe["id"], [], image=JPEG)
    assert res.status_code == 201, res.get_json()
    url = res.get_json()["log"]["photo_url"]
    assert url.startswith(f"/api/photos/cooklog/{user.id}/") and url.endswith(".jpg")
    with open(photo_path(app, url), "rb") as f:
        assert f.read() == JPEG
    assert client.get(url).status_code == 200
    with app.app_context():
        assert url.removeprefix("/api/photos/") in photos.user_photo_keys([user.id])
    login("other")
    assert client.get(url).status_code == 404


def test_photo_failure_rolls_back_everything(client, login, app, monkeypatch):
    login()
    recipe, ids, usages = kimchi_setup(client)
    before = quantities(client)

    def unchanged():
        assert quantities(client) == before
        assert counts(app) == (0, 0, 0)

    app.config["DEV_MODE"] = False  # 운영에서 R2가 없으면
    assert error(cook(client, recipe["id"], usages, image=JPEG, food_log=True, meal="dinner")) == (503, "사진을 지금은 올릴 수 없어요.")
    unchanged()
    app.config["DEV_MODE"] = True

    def boom(*args, **kwargs):
        from flask import abort

        abort(503, "사진을 지금은 올릴 수 없어요.")

    with monkeypatch.context() as m:
        m.setattr("app.storage.put", boom)
        assert error(cook(client, recipe["id"], usages, image=JPEG, food_log=True, meal="dinner")) == (503, "사진을 지금은 올릴 수 없어요.")
    unchanged()
    assert cook(client, recipe["id"], usages, image=b"hello").status_code == 415
    unchanged()
    monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", 1)
    assert error(cook(client, recipe["id"], usages, image=JPEG)) == (400, "사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요.")
    unchanged()


def test_commit_conflict_deletes_uploaded_photo(client, login, app, monkeypatch, caplog):
    login()
    recipe, ids, usages = kimchi_setup(client)
    before = quantities(client)

    def conflict():
        raise sa.exc.IntegrityError("INSERT", {}, Exception("unique"))

    with monkeypatch.context() as m:
        m.setattr("app.cooklog.db.session.commit", conflict)
        assert error(cook(client, recipe["id"], usages, image=JPEG)) == (400, STOCK_CHANGED)
    assert "cook log save conflict: IntegrityError" in caplog.text
    assert quantities(client) == before
    assert counts(app) == (0, 0, 0)
    root = os.path.join(app.config["UPLOAD_DIR"], "cooklog")
    assert not [name for _, _, names in os.walk(root) for name in names]


VALIDATION = [
    ({"data": None}, BAD),
    ({"data": "[]"}, BAD),
    ({"data": "x"}, BAD),
    ({"recipe_id": True}, BAD),
    ({"recipe_id": "1"}, BAD),
    ({"servings": 0}, "인분은 1~20 사이 정수로 입력해주세요."),
    ({"servings": 21}, "인분은 1~20 사이 정수로 입력해주세요."),
    ({"servings": "2"}, "인분은 1~20 사이 정수로 입력해주세요."),
    ({"cooked_on": "2026-09-16"}, "아직 오지 않은 날은 남길 수 없어요."),
    ({"cooked_on": None}, "날짜를 골라주세요."),
    ({"rating": 6}, "별점은 1~5 사이 정수로 입력해주세요."),
    ({"memo": "가" * 501}, "메모는 500자까지 입력해주세요."),
    ({"memo": "a\x00"}, BAD),
    ({"memo": 3}, BAD),
    ({"eat_out_price": -1}, "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."),
    ({"eat_out_price": 1000001}, "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."),
    ({"eat_out_price": True}, "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."),
    ({"eat_out_price": "9000"}, "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."),
    ({"usages": "many"}, BAD),
    ({"usages": [{"ingredient_id": 1, "amount": 1}] * 51}, BAD),
    ({"usages": [{"ingredient_id": 1, "amount": 1}, {"ingredient_id": 1, "amount": 1}]}, BAD),
    ({"usages": [{"ingredient_id": True, "amount": 1}]}, BAD),
    ({"usages": [{"ingredient_id": 2**31, "amount": 1}]}, BAD),
    ({"usages": ["x"]}, BAD),
    ({"usages": [{"ingredient_id": 1, "amount": 0}]}, "쓴 양은 0보다 커야 해요."),
    ({"usages": [{"ingredient_id": 1, "amount": -1}]}, "쓴 양은 0보다 커야 해요."),
    ({"usages": [{"ingredient_id": 1, "amount": "1"}]}, "쓴 양은 0보다 커야 해요."),
    ({"usages": [{"ingredient_id": 1, "amount": 100001}]}, "쓴 양은 0보다 커야 해요."),
    ({"usages": [{"ingredient_id": 1, "amount": True}]}, "쓴 양은 0보다 커야 해요."),
    ({"food_log": "yes"}, BAD),
]


@pytest.mark.parametrize("override, message", VALIDATION)
def test_validation(client, login, app, override, message):
    login()
    recipe, ids, usages = kimchi_setup(client)
    before = quantities(client)
    if "data" in override:
        form = {} if override["data"] is None else {"data": override["data"]}
        res = client.post("/api/cook-logs", data=form, content_type="multipart/form-data")
    else:
        fields = {"usages": [{"ingredient_id": ids["김치"], "amount": 0.3}], **override}
        res = cook(client, fields.pop("recipe_id", recipe["id"]), fields.pop("usages"), **fields)
    assert error(res) == (400, message)
    assert quantities(client) == before
    assert counts(app) == (0, 0, 0)
    got = client.get(f"/api/recipes/{recipe['id']}").get_json()
    assert got["eat_out_price"] is None


def test_nan_amount_rejected(client, login, app):
    login()
    recipe, ids, usages = kimchi_setup(client)
    body = '{"recipe_id": %d, "servings": 2, "cooked_on": "2026-09-15", "food_log": false, "usages": [{"ingredient_id": %d, "amount": NaN}]}'
    res = client.post("/api/cook-logs", data={"data": body % (recipe["id"], ids["김치"])}, content_type="multipart/form-data")
    assert error(res) == (400, "쓴 양은 0보다 커야 해요.")


def test_stock_changed_and_ownership(client, raw_client, login, app, monkeypatch):
    assert cook(client, 1, []).status_code == 401
    login("2")
    others = stock(client, "김치", 1, "kg")
    other_recipe = add_recipe(client, "남의 찌개", [{"name": "김치", "amount": "1kg"}])
    login()
    recipe, ids, usages = kimchi_setup(client)
    before = quantities(client)
    assert client.delete(f"/api/ingredients/{ids['두부']}").status_code == 204
    before.pop("두부")
    assert error(cook(client, recipe["id"], usages)) == (400, STOCK_CHANGED)
    assert error(cook(client, recipe["id"], [usages[0], {"ingredient_id": others, "amount": 0.1}])) == (400, STOCK_CHANGED)
    assert quantities(client) == before
    assert cook(client, other_recipe["id"], []).status_code == 404
    assert cook(client, 2**31, []).status_code == 404
    form = {"data": json.dumps({"recipe_id": recipe["id"], "servings": 2, "cooked_on": "2026-09-15", "usages": [], "food_log": False})}
    assert raw_client.post("/api/cook-logs", data=form, content_type="multipart/form-data").status_code == 400
    monkeypatch.setattr("app.cooklog.MAX_COOK_LOGS", 1)
    assert cook(client, recipe["id"], []).status_code == 201
    assert error(cook(client, recipe["id"], [])) == (400, "요리 일기는 1개까지 남길 수 있어요.")


def test_save_reads_locked_quantity_not_stale_draft(client, login, app, monkeypatch):
    """초안(잠금 전)이 읽은 수량이 아니라 FOR UPDATE로 다시 읽은 수량에서 뺀다(다른 요청이 그사이 고친 경우)."""
    login()
    recipe, ids, usages = kimchi_setup(client)
    from app import cooklog

    real = cooklog.draft_rows

    held = []

    def draft_then_edit(recipe_obj, user_id):
        rows = real(recipe_obj, user_id)
        held.extend(Ingredient.query.filter_by(user_id=user_id).all())  # 세션이 옛 수량을 들고 있는 상태
        stmt = sa.update(Ingredient).where(Ingredient.id == ids["김치"]).values(quantity=0.5)
        db.session.execute(stmt, execution_options={"synchronize_session": False})
        return rows

    monkeypatch.setattr("app.cooklog.draft_rows", draft_then_edit)
    assert cook(client, recipe["id"], usages[:1]).status_code == 201
    assert quantities(client)["김치"] == (0.2, "kg")


def test_undo_restores_quantities_and_deleted_rows(client, login, app):
    login()
    recipe, ids, usages = kimchi_setup(client)
    tofu_before = stock_map(client)["두부"]
    res = cook(client, recipe["id"], usages, image=JPEG, eat_out_price=9000, food_log=True, meal="dinner")
    assert res.status_code == 201, res.get_json()
    log = res.get_json()["log"]
    food_id = log["food_log_id"]
    upload = client.post(f"/api/food-logs/{food_id}/photos", data={"image": (io.BytesIO(JPEG), "b.jpg")}, content_type="multipart/form-data")
    assert upload.status_code == 201
    files = [photo_path(app, log["photo_url"]), photo_path(app, upload.get_json()["url"])]
    assert all(os.path.exists(f) for f in files)

    res = client.post(f"/api/cook-logs/{log['id']}/undo")
    assert res.status_code == 200, res.get_json()
    assert res.get_json() == {"restored": ["김치", "두부", "대파", "고춧가루"], "skipped": []}
    items = stock_map(client)
    assert {n: (i["quantity"], i["unit"]) for n, i in items.items()} == {
        "김치": (1.0, "kg"), "두부": (1.0, "모"), "대파": (3.0, "대"), "고춧가루": (100.0, "g"),
    }
    tofu = items["두부"]
    assert tofu["id"] != tofu_before["id"]
    assert (tofu["price"], tofu["location_id"], tofu["purchased_on"], tofu["expires_on"]) == (
        2480, tofu_before["location_id"], tofu_before["purchased_on"], tofu_before["expires_on"],
    )
    with app.app_context():
        assert db.session.get(Ingredient, tofu["id"]).price_quantity == 1.0
    assert counts(app) == (0, 0, 0)
    assert not any(os.path.exists(f) for f in files)
    assert client.post(f"/api/cook-logs/{log['id']}/undo").status_code == 404


def test_undo_adds_on_top_of_edits_and_skips_changed(client, login):
    login()
    recipe, ids, usages = kimchi_setup(client)
    log = cook(client, recipe["id"], usages).get_json()["log"]
    assert client.patch(f"/api/ingredients/{ids['김치']}", json={"quantity": 0.5}).status_code == 200
    assert client.patch(f"/api/ingredients/{ids['대파']}", json={"unit": "단"}).status_code == 200
    assert client.delete(f"/api/ingredients/{ids['고춧가루']}").status_code == 204
    res = client.post(f"/api/cook-logs/{log['id']}/undo")
    assert res.get_json() == {"restored": ["김치", "두부"], "skipped": ["대파", "고춧가루"]}
    left = quantities(client)
    assert left["김치"] == (0.8, "kg")
    assert left["대파"] == (2.0, "단")
    assert "고춧가루" not in left


def test_undo_deleted_location_uses_default(client, login, app):
    user = login()
    recipe, ids, usages = kimchi_setup(client)
    with app.app_context():
        spare = StorageLocation(user_id=user.id, name="김치냉장고", kind="fridge", sort_order=9)
        db.session.add(spare)
        db.session.commit()
        spare_id = spare.id
    assert client.patch(f"/api/ingredients/{ids['두부']}", json={"location_id": spare_id}).status_code == 200
    log = cook(client, recipe["id"], [usages[1]]).get_json()["log"]
    with app.app_context():
        db.session.delete(db.session.get(StorageLocation, spare_id))
        db.session.commit()
    assert client.post(f"/api/cook-logs/{log['id']}/undo").status_code == 200
    with app.app_context():
        tofu = Ingredient.query.filter_by(name="두부").one()
        assert tofu.location_id == default_location(user.id).id != spare_id


def test_undo_window(client, login, app, monkeypatch):
    user = login()
    recipe, ids, usages = kimchi_setup(client)
    log = cook(client, recipe["id"], usages).get_json()["log"]
    before = quantities(client)
    created = datetime.fromisoformat(log["created_at"])
    monkeypatch.setattr("app.cooklog.utcnow", lambda: created + timedelta(seconds=121))
    assert error(client.post(f"/api/cook-logs/{log['id']}/undo")) == (400, "되돌릴 수 있는 시간이 지났어요. 재고는 직접 고쳐주세요.")
    assert quantities(client) == before
    assert counts(app)[0] == 1
    monkeypatch.setattr("app.cooklog.utcnow", lambda: created + timedelta(seconds=119))
    login("other")
    assert client.post(f"/api/cook-logs/{log['id']}/undo").status_code == 404
    assert client.post("/api/cook-logs/2147483648/undo").status_code == 404
    as_user(client, user)
    assert client.post(f"/api/cook-logs/{log['id']}/undo").status_code == 200
