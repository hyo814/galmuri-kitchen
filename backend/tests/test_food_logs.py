from datetime import date

import pytest

from app import food_logs
from app.models import FoodLog, FoodSearch, UnitWeightEstimate, User, db, utcnow
from tests.test_meal_ai import apply, new_dish
from tests.test_meals import add_recipe, make_plan, put_slot
from tests.test_nutrition import add_foods, cached

DAY = {"eaten_on": "2026-09-14", "meal": "lunch"}
BAD = "잘못된 요청이에요."
MISSING = object()


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("app.food_logs.seoul_today", lambda: date(2026, 9, 15))


def post_log(client, **body):
    return client.post("/api/food-logs", json={k: v for k, v in {**DAY, **body}.items() if v is not MISSING})


def patch_log(client, log_id, **body):
    return client.patch(f"/api/food-logs/{log_id}", json=body)


def get_day(client, on="2026-09-14"):
    return client.get(f"/api/food-logs?date={on}")


def error(res):
    return res.status_code, res.get_json()["error"]


def dish(app, code="D1", name="제육덮밥", kcal=185, **others):
    add_foods(app, cached(code, name, kcal, group="음식", source="api", **others))


def test_requires_login_and_csrf(client, raw_client):
    assert get_day(client).status_code == 401
    assert raw_client.post("/api/food-logs", json={**DAY, "title": "밥"}).status_code == 400


def test_create_text_log_and_day_list(client, login):
    login()
    res = post_log(client, title=" 제육덮밥 ", place="out", rating=3, memo="회사 앞 · 조금 짰어요")
    assert res.status_code == 201
    log = res.get_json()
    assert {k: v for k, v in log.items() if k not in ("id", "created_at")} == {
        "eaten_on": "2026-09-14", "meal": "lunch", "source": "manual", "title": "제육덮밥", "recipe_id": None, "meal_slot_id": None,
        "slot_servings": None, "food_code": None, "servings": 1.0, "grams": None, "place": "out", "rating": 3,
        "memo": "회사 앞 · 조금 짰어요", "nutrition": None, "approx": False, "nutrition_pending": False,
    }

    res = get_day(client)
    assert res.headers["Cache-Control"] == "no-store"
    body = res.get_json()
    assert (body["date"], [row["id"] for row in body["logs"]]) == ("2026-09-14", [log["id"]])
    assert get_day(client, "2026-09-13").get_json()["logs"] == []
    assert error(get_day(client, "2026-9-1")) == (400, "날짜를 다시 확인해주세요.")
    assert error(get_day(client, "1999-12-31")) == (400, "날짜를 다시 확인해주세요.")


def test_create_food_log_serving_and_grams(client, login, app):
    login()
    dish(app, serving_g=400, carbs_g=22.0, sugars_g=5.5, sodium_mg=410)
    dish(app, "D2", "떡볶이", 200)

    log = post_log(client, food_code="D1", servings=0.5, title="무시").get_json()
    assert (log["title"], log["food_code"], log["servings"], log["grams"], log["approx"]) == ("제육덮밥", "D1", 0.5, None, True)
    assert log["nutrition"] == {"kcal": 370, "carbs_g": 44.0, "protein_g": None, "fat_g": None, "sugars_g": 11.0, "sodium_mg": 820}

    log = post_log(client, food_code="D1", grams=300).get_json()
    assert (log["nutrition"]["kcal"], log["servings"], log["grams"]) == (555, None, 300)

    assert error(post_log(client, food_code="D2", servings=1)) == (400, "이 음식은 g으로 입력해주세요.")
    assert post_log(client, food_code="D2", grams=200).status_code == 201


def test_create_recipe_log_uses_per_serving(client, login, app):
    login()
    add_foods(
        app,
        cached("T1", "두부", kcal=84, protein_g=9.3, group="원재료성"),
        cached("S1", "간장", kcal=53, sodium_mg=5000, group="가공식품"),
        FoodSearch(query_key="두부", total=1, searched_at=utcnow()),
        FoodSearch(query_key="간장", total=1, searched_at=utcnow()),
        UnitWeightEstimate(name_key="두부", unit="모", grams=300, source="sample"),
    )
    recipe = add_recipe(client, "두부조림", [{"name": "두부", "amount": "1모"}, {"name": "간장", "amount": "2큰술"}], servings=2)

    log = post_log(client, recipe_id=recipe["id"], servings=1.5, title="무시").get_json()
    assert (log["title"], log["recipe_id"], log["source"], log["servings"]) == ("두부조림", recipe["id"], "manual", 1.5)
    assert log["nutrition"]["kcal"] == round(134 * 1.5) == 201
    assert (log["approx"], log["nutrition_pending"]) == (True, False)


def test_pending_recipe_is_recomputed_on_day_get(client, login, app):
    login()
    recipe = add_recipe(client, "양배추찜", [{"name": "양배추", "amount": "100g"}])
    log = post_log(client, recipe_id=recipe["id"]).get_json()
    assert (log["nutrition"], log["nutrition_pending"]) == (None, True)
    assert get_day(client).get_json()["nutrition_pending_recipe_ids"] == [recipe["id"]]

    add_foods(app, FoodSearch(query_key="양배추", total=1, searched_at=utcnow()), cached("C1", "양배추", kcal=31))
    body = get_day(client).get_json()
    assert (body["logs"][0]["nutrition"]["kcal"], body["logs"][0]["nutrition_pending"]) == (31, False)
    assert body["nutrition_pending_recipe_ids"] == []


def test_snapshot_kept_when_recipe_changes_or_is_deleted(client, login, app):
    login()
    add_foods(app, cached("T1", "두부", kcal=84), UnitWeightEstimate(name_key="두부", unit="모", grams=100, source="sample"))
    recipe = add_recipe(client, "두부부침", [{"name": "두부", "amount": "1모"}])
    log = post_log(client, recipe_id=recipe["id"]).get_json()
    assert (log["nutrition"]["kcal"], log["approx"]) == (84, True)

    changed = {"title": "두부부침", "servings": 1, "ingredients": [{"name": "두부", "amount": "300g"}], "steps": []}
    assert client.put(f"/api/recipes/{recipe['id']}", json=changed).status_code == 200
    assert get_day(client).get_json()["logs"][0]["nutrition"]["kcal"] == 84

    assert client.delete(f"/api/recipes/{recipe['id']}").status_code == 204
    kept = get_day(client).get_json()["logs"][0]
    assert (kept["recipe_id"], kept["title"], kept["nutrition"]) == (None, "두부부침", log["nutrition"])
    patched = patch_log(client, log["id"], servings=2).get_json()
    assert (patched["nutrition"]["kcal"], patched["servings"], patched["approx"]) == (168, 2.0, True)

    # 계산 중(일부 값 있음)이던 기록의 레시피를 지우면 하루 GET이 값을 두고 계산 중만 끈다
    partial = add_recipe(client, "두부양배추", [{"name": "두부", "amount": "100g"}, {"name": "양배추", "amount": "100g"}])
    pending = post_log(client, recipe_id=partial["id"], meal="dinner").get_json()
    assert (pending["nutrition"]["kcal"], pending["nutrition_pending"]) == (84, True)
    assert client.delete(f"/api/recipes/{partial['id']}").status_code == 204
    body = get_day(client).get_json()
    row = next(r for r in body["logs"] if r["id"] == pending["id"])
    assert (row["nutrition"], row["nutrition_pending"], body["nutrition_pending_recipe_ids"]) == (pending["nutrition"], False, [])

    # 식단 칸 기록: 칸은 남고 레시피만 지워져도 다시 계산하지 않고 비율로 고친다
    slot_recipe = add_recipe(client, "두부구이", [{"name": "두부", "amount": "100g"}])
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="breakfast", recipe_id=slot_recipe["id"]).get_json()
    slot_log = post_log(client, meal_slot_id=slot["id"]).get_json()
    assert client.delete(f"/api/recipes/{slot_recipe['id']}").status_code == 204
    patched = patch_log(client, slot_log["id"], servings=2).get_json()
    assert (patched["nutrition"]["kcal"], patched["meal_slot_id"]) == (168, slot["id"])


def test_create_from_meal_slot(client, login):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "1컵"}])
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", recipe_id=recipe["id"], servings=2).get_json()

    res = post_log(client, meal_slot_id=slot["id"], eaten_on="2026-09-01", meal="snack", title="무시", source="manual")
    assert res.status_code == 201
    log = res.get_json()
    assert {k: log[k] for k in ("eaten_on", "meal", "source", "title", "recipe_id", "meal_slot_id", "slot_servings", "servings")} == {
        "eaten_on": "2026-09-14", "meal": "dinner", "source": "meal_plan", "title": "김치찌개", "recipe_id": recipe["id"],
        "meal_slot_id": slot["id"], "slot_servings": 2, "servings": 1.0,
    }

    assert error(post_log(client, meal_slot_id=slot["id"])) == (400, "이미 먹었어요로 남긴 칸이에요.")
    future = put_slot(client, plan["id"], date="2026-09-16", meal="dinner", title="카레").get_json()
    assert error(post_log(client, meal_slot_id=future["id"])) == (400, "아직 오지 않은 날은 남길 수 없어요.")

    login("2")
    assert post_log(client, meal_slot_id=future["id"]).status_code == 404


def test_create_slot_race_400(client, login, app, monkeypatch):
    user = login()
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14").get_json()
    real = food_logs.fill_snapshots

    def racing(logs):
        real(logs)
        db.session.add(FoodLog(user_id=user.id, eaten_on=date(2026, 9, 14), meal="lunch", title="먼저 남김", meal_slot_id=slot["id"]))

    monkeypatch.setattr("app.food_logs.fill_snapshots", racing)
    assert error(post_log(client, meal_slot_id=slot["id"])) == (400, food_logs.SLOT_TAKEN)
    with app.app_context():
        assert FoodLog.query.count() == 0


def test_patch_fields_and_recompute(client, login, app):
    login()
    dish(app, serving_g=400)
    log = post_log(client, food_code="D1", place="out", rating=4, memo="맛있어요").get_json()
    assert (log["servings"], log["nutrition"]["kcal"]) == (1.0, 740)

    assert patch_log(client, log["id"], servings=2).get_json()["nutrition"]["kcal"] == 1480
    patched = patch_log(client, log["id"], grams=300).get_json()
    assert (patched["servings"], patched["grams"], patched["nutrition"]["kcal"]) == (None, 300, 555)
    patched = patch_log(client, log["id"], servings=1).get_json()
    assert (patched["servings"], patched["grams"], patched["nutrition"]["kcal"]) == (1.0, None, 740)

    patched = patch_log(client, log["id"], rating=None, memo="  ", place=None).get_json()
    assert (patched["rating"], patched["memo"], patched["place"], patched["nutrition"]["kcal"]) == (None, None, None, 740)

    patched = patch_log(client, log["id"], title="샐러드").get_json()
    assert (patched["title"], patched["food_code"], patched["nutrition"], patched["approx"]) == ("샐러드", None, None, False)

    patched = patch_log(client, log["id"], meal="dinner", eaten_on="2026-09-13").get_json()
    assert (patched["meal"], patched["eaten_on"]) == ("dinner", "2026-09-13")
    assert [row["id"] for row in get_day(client, "2026-09-13").get_json()["logs"]] == [log["id"]]

    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", title="요거트볼").get_json()
    slot_log = post_log(client, meal_slot_id=slot["id"]).get_json()
    patched = patch_log(client, slot_log["id"], title="요거트").get_json()
    assert (patched["title"], patched["meal_slot_id"], patched["slot_servings"], patched["source"]) == ("요거트", None, None, "meal_plan")
    assert get_day(client).get_json()["plan_slots"][0]["id"] == slot["id"]  # 연결을 끊은 칸은 다시 제안한다


@pytest.mark.parametrize(
    "body, message",
    [
        ({"eaten_on": MISSING}, "날짜를 골라주세요."),
        ({"eaten_on": "2026-09-16"}, "아직 오지 않은 날은 남길 수 없어요."),
        ({"eaten_on": "1999-12-31"}, "날짜를 다시 확인해주세요."),
        ({"meal": "brunch"}, "끼니를 골라주세요."),
        ({"recipe_id": 1, "food_code": "D1"}, BAD),
        ({"title": ""}, "무엇을 먹었는지는 1~60자로 입력해주세요."),
        ({"title": "가" * 61}, "무엇을 먹었는지는 1~60자로 입력해주세요."),
        ({"food_code": "없는코드"}, "음식을 다시 골라주세요."),
        ({"recipe_id": "1"}, BAD),
        ({"recipe_id": True}, BAD),
        ({"servings": 0}, "인분은 0.5~20 사이로 입력해주세요."),
        ({"servings": 0.3}, "인분은 0.5~20 사이로 입력해주세요."),
        ({"servings": 20.5}, "인분은 0.5~20 사이로 입력해주세요."),
        ({"servings": True}, "인분은 0.5~20 사이로 입력해주세요."),
        ({"servings": "1"}, "인분은 0.5~20 사이로 입력해주세요."),
        ({"grams": 100}, BAD),
        ({"food_code": "D1", "grams": 0}, "먹은 양은 1~3000g 사이로 입력해주세요."),
        ({"food_code": "D1", "grams": 3001}, "먹은 양은 1~3000g 사이로 입력해주세요."),
        ({"food_code": "D1", "grams": 1.5}, "먹은 양은 1~3000g 사이로 입력해주세요."),
        ({"place": "cafe"}, BAD),
        ({"rating": 0}, "만족도는 1~5 사이 정수로 입력해주세요."),
        ({"rating": 6}, "만족도는 1~5 사이 정수로 입력해주세요."),
        ({"rating": True}, "만족도는 1~5 사이 정수로 입력해주세요."),
        ({"memo": "가" * 201}, "메모는 200자까지 입력해주세요."),
        ({"memo": "a\x00"}, BAD),
        ({"memo": 123}, BAD),
    ],
)
def test_validation(client, login, app, body, message):
    login()
    dish(app, serving_g=400)
    assert error(post_log(client, **{"title": "밥", **body})) == (400, message)
    with app.app_context():
        assert FoodLog.query.count() == 0


def test_validation_body_not_dict(client, login):
    login()
    assert error(client.post("/api/food-logs", json=[])) == (400, BAD)


def test_ownership(client, login):
    login("other")
    other_recipe = add_recipe(client, "남의 레시피", [{"name": "두부", "amount": "100g"}])
    other_log = post_log(client, title="남의 기록").get_json()

    login()
    assert post_log(client, recipe_id=other_recipe["id"]).status_code == 404
    assert patch_log(client, other_log["id"], title="내 것").status_code == 404
    assert client.delete(f"/api/food-logs/{other_log['id']}").status_code == 404
    assert patch_log(client, 2147483648, title="내 것").status_code == 404
    assert client.delete("/api/food-logs/2147483648").status_code == 404
    assert get_day(client).get_json()["logs"] == []


def test_caps(client, login, monkeypatch):
    login()
    first = post_log(client, title="밥").get_json()
    for _ in range(19):
        assert post_log(client, title="밥").status_code == 201
    assert error(post_log(client, title="밥")) == (400, "하루에 20개까지 남길 수 있어요.")
    assert patch_log(client, first["id"], eaten_on="2026-09-14", meal="dinner").status_code == 200  # 같은 날은 세지 않는다
    moved = post_log(client, title="밥", eaten_on="2026-09-13")
    assert moved.status_code == 201

    monkeypatch.setattr("app.food_logs.MAX_LOGS", 21)
    assert error(post_log(client, title="밥", eaten_on="2026-09-12")) == (400, "먹은 기록은 21개까지 남길 수 있어요.")
    assert error(patch_log(client, moved.get_json()["id"], eaten_on="2026-09-14")) == (400, "하루에 20개까지 남길 수 있어요.")
    assert patch_log(client, moved.get_json()["id"], eaten_on="2026-09-12").status_code == 200  # 옮기기는 전체 상한을 세지 않는다


def test_day_plan_slot_suggestions(client, login):
    login("other")
    other_plan = make_plan(client).get_json()
    put_slot(client, other_plan["id"], date="2026-09-14", title="남의 칸")

    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "1컵"}])
    plan = make_plan(client).get_json()
    put_slot(client, plan["id"], date="2026-09-14", meal="snack", title="요거트")
    put_slot(client, plan["id"], date="2026-09-14", meal="lunch", recipe_id=recipe["id"])
    eaten = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", title="카레").get_json()
    put_slot(client, plan["id"], date="2026-09-16", meal="lunch", title="미래")
    assert post_log(client, meal_slot_id=eaten["id"]).status_code == 201

    slots = get_day(client).get_json()["plan_slots"]
    assert [s["title"] for s in slots] == ["김치찌개", "요거트"]
    assert slots[0] == {"id": slots[0]["id"], "meal": "lunch", "title": "김치찌개", "servings": 2, "recipe_id": recipe["id"]}
    assert get_day(client, "2026-09-16").get_json()["plan_slots"] == []


def test_delete_and_cascades(client, login, app):
    user = login()
    log = post_log(client, title="밥").get_json()
    assert client.delete(f"/api/food-logs/{log['id']}").status_code == 204
    assert get_day(client).get_json()["logs"] == []

    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14").get_json()
    slot_log = post_log(client, meal_slot_id=slot["id"]).get_json()
    assert client.delete(f"/api/meal-slots/{slot['id']}").status_code == 204
    assert [(r["id"], r["meal_slot_id"], r["title"]) for r in get_day(client).get_json()["logs"]] == [(slot_log["id"], None, "직접 쓰기")]

    slot = put_slot(client, plan["id"], date="2026-09-14", meal="dinner").get_json()
    assert post_log(client, meal_slot_id=slot["id"]).status_code == 201
    assert client.delete(f"/api/meal-plans/{plan['id']}").status_code == 204
    assert [r["meal_slot_id"] for r in get_day(client).get_json()["logs"]] == [None, None]

    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert FoodLog.query.count() == 0


def test_nutrition_off_mode(client, login, app):
    login()
    add_foods(app, cached("T1", "두부", kcal=84))
    recipe = add_recipe(client, "두부부침", [{"name": "두부", "amount": "100g"}])
    plan = make_plan(client).get_json()
    body = {"dishes": [new_dish("된장국")], "slots": [{"date": "2026-09-14", "meal": "dinner", "dish": 0, "est_kcal": 420}]}
    assert apply(client, plan["id"], body).status_code == 201
    app.config.update(DEV_MODE=False)

    log = post_log(client, recipe_id=recipe["id"]).get_json()
    assert (log["nutrition"], log["nutrition_pending"], log["approx"]) == (None, False, False)

    slot = client.get(f"/api/meal-plans/{plan['id']}").get_json()["slots"][0]
    slot_log = post_log(client, meal_slot_id=slot["id"]).get_json()
    assert (slot_log["nutrition"]["kcal"], slot_log["approx"], slot_log["slot_servings"]) == (420, True, 2)

    patched = patch_log(client, slot_log["id"], title="요거트").get_json()
    assert (patched["nutrition"], patched["meal_slot_id"], patched["recipe_id"], patched["source"]) == (None, None, None, "meal_plan")


def test_patch_slot_log_rules(client, login):
    login()
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="비빔밥").get_json()
    other = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", title="카레").get_json()
    log = post_log(client, meal_slot_id=slot["id"]).get_json()
    assert post_log(client, meal_slot_id=other["id"]).status_code == 201

    assert error(patch_log(client, log["id"], meal_slot_id=other["id"])) == (400, "이미 먹었어요로 남긴 칸이에요.")
    assert error(patch_log(client, log["id"], eaten_on="2026-09-16")) == (400, "아직 오지 않은 날은 남길 수 없어요.")
    assert error(client.patch(f"/api/food-logs/{log['id']}", json=[])) == (400, BAD)

    patched = patch_log(client, log["id"], meal="snack").get_json()  # 같은 날 끼니만 옮기면 칸 연결은 둔다
    assert (patched["meal"], patched["meal_slot_id"]) == ("snack", slot["id"])
    patched = patch_log(client, log["id"], eaten_on="2026-09-13").get_json()
    assert (patched["eaten_on"], patched["meal_slot_id"], patched["source"]) == ("2026-09-13", None, "meal_plan")
    assert [s["id"] for s in get_day(client).get_json()["plan_slots"]] == [slot["id"]]


def test_ai_slot_without_recipe_rescales(client, login):
    login()
    plan = make_plan(client).get_json()
    body = {"dishes": [new_dish("된장국")], "slots": [{"date": "2026-09-14", "meal": "dinner", "dish": 0, "est_kcal": 420}]}
    assert apply(client, plan["id"], body).status_code == 201
    slot = client.get(f"/api/meal-plans/{plan['id']}").get_json()["slots"][0]
    assert client.delete(f"/api/recipes/{slot['recipe_id']}").status_code == 204

    log = post_log(client, meal_slot_id=slot["id"]).get_json()
    assert (log["recipe_id"], log["nutrition"]["kcal"], log["servings"]) == (None, 420, 1.0)
    patched = patch_log(client, log["id"], servings=2).get_json()
    assert (patched["nutrition"]["kcal"], patched["approx"]) == (840, True)


def test_nutrition_off_keeps_snapshots(client, login, app):
    login()
    add_foods(app, cached("T1", "두부", kcal=84))
    recipe = add_recipe(client, "두부부침", [{"name": "두부", "amount": "100g"}])
    partial = add_recipe(client, "두부양배추", [{"name": "두부", "amount": "100g"}, {"name": "양배추", "amount": "100g"}])
    log = post_log(client, recipe_id=recipe["id"]).get_json()
    pending = post_log(client, recipe_id=partial["id"], meal="dinner").get_json()
    assert (log["nutrition"]["kcal"], pending["nutrition"]["kcal"], pending["nutrition_pending"]) == (84, 84, True)

    app.config.update(DEV_MODE=False)
    patched = patch_log(client, log["id"], servings=2).get_json()
    assert (patched["nutrition"]["kcal"], patched["servings"]) == (168, 2.0)
    body = get_day(client).get_json()
    row = next(r for r in body["logs"] if r["id"] == pending["id"])
    assert (row["nutrition"], row["nutrition_pending"], body["nutrition_pending_recipe_ids"]) == (pending["nutrition"], False, [])
