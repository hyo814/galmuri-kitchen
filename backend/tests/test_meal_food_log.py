from datetime import date

import pytest

from app import food_logs
from app.models import FoodLog, db
from tests.test_meal_ai import apply, new_dish
from tests.test_meals import add_recipe, make_plan, put_slot

BAD = "잘못된 요청이에요."


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("app.meals.seoul_today", lambda: date(2026, 9, 15))
    monkeypatch.setattr("app.food_logs.seoul_today", lambda: date(2026, 9, 15))


def eat(client, slot_id):
    return client.post(f"/api/meal-slots/{slot_id}/eaten")


def get_plan(client, plan_id):
    return client.get(f"/api/meal-plans/{plan_id}")


def get_day(client, on="2026-09-14"):
    return client.get(f"/api/food-logs?date={on}")


def error(res):
    return res.status_code, res.get_json()["error"]


def test_eaten_creates_log_once(client, login, app):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "1컵"}])
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", recipe_id=recipe["id"], servings=2).get_json()
    other = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="샐러드").get_json()

    res = eat(client, slot["id"])
    assert res.status_code == 201
    log = res.get_json()
    assert {k: log[k] for k in ("source", "place", "servings", "eaten_on", "meal", "title", "recipe_id", "meal_slot_id", "slot_servings")} == {
        "source": "meal_plan", "place": "home", "servings": 1.0, "eaten_on": "2026-09-14", "meal": "dinner",
        "title": "김치찌개", "recipe_id": recipe["id"], "meal_slot_id": slot["id"], "slot_servings": 2,
    }

    res2 = eat(client, slot["id"])
    assert res2.status_code == 200
    assert res2.get_json()["id"] == log["id"]
    with app.app_context():
        assert FoodLog.query.count() == 1

    plan_body = get_plan(client, plan["id"]).get_json()
    slots = {s["id"]: s["eaten_log_id"] for s in plan_body["slots"]}
    assert slots[slot["id"]] == log["id"]
    assert slots[other["id"]] is None

    plan_slots = get_day(client).get_json()["plan_slots"]
    assert slot["id"] not in [s["id"] for s in plan_slots]


def test_eaten_snapshot_uses_slot_nutrition(client, login):
    login()
    body = {
        "dishes": [new_dish("잡탕", ingredients=[{"name": "두부", "amount": "100g"}])],
        "slots": [{"date": "2026-09-14", "meal": "lunch", "dish": 0, "est_kcal": 420}],
    }
    plan = make_plan(client, start_on="2026-09-14").get_json()
    assert apply(client, plan["id"], body).status_code == 201
    slot = get_plan(client, plan["id"]).get_json()["slots"][0]

    log = eat(client, slot["id"]).get_json()
    assert (log["nutrition"]["kcal"], log["approx"]) == (420, True)


def test_future_slot_rejected(client, login, app):
    login()
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-16", meal="dinner", title="카레").get_json()

    assert error(eat(client, slot["id"])) == (400, food_logs.FUTURE)
    with app.app_context():
        assert FoodLog.query.count() == 0


def test_overwrite_slot_unlinks_log(client, login, app):
    login()
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="직접 쓰기").get_json()

    log = eat(client, slot["id"]).get_json()
    overwritten = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="다른 요리").get_json()
    assert overwritten["eaten_log_id"] is None

    with app.app_context():
        kept = db.session.get(FoodLog, log["id"])
        assert (kept.meal_slot_id, kept.title) == (None, "직접 쓰기")

    res = eat(client, overwritten["id"])
    assert res.status_code == 201
    assert res.get_json()["id"] != log["id"]


def test_delete_slot_or_plan_keeps_log(client, login, app):
    login()
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="직접 쓰기").get_json()
    log = eat(client, slot["id"]).get_json()

    assert client.delete(f"/api/meal-slots/{slot['id']}").status_code == 204
    with app.app_context():
        assert db.session.get(FoodLog, log["id"]).meal_slot_id is None

    other_slot = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", title="다른 끼니").get_json()
    other_log = eat(client, other_slot["id"]).get_json()
    assert client.delete(f"/api/meal-plans/{plan['id']}").status_code == 204
    with app.app_context():
        assert db.session.get(FoodLog, other_log["id"]) is not None


def test_ownership_and_csrf(client, raw_client, login):
    login()
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="직접 쓰기").get_json()

    login("2")
    assert eat(client, slot["id"]).status_code == 404
    assert client.post(f"/api/meal-slots/{2**31}/eaten").status_code == 404
    assert raw_client.post(f"/api/meal-slots/{slot['id']}/eaten").status_code == 400


def test_no_login_401(raw_client):
    raw_client.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    assert raw_client.post("/api/meal-slots/1/eaten").status_code == 401


def test_slot_responses_have_eaten_key(client, login):
    login()
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="직접 쓰기").get_json()
    assert slot["eaten_log_id"] is None

    patched = client.patch(f"/api/meal-slots/{slot['id']}", json={"servings": 2}).get_json()
    assert patched["eaten_log_id"] is None

    put_slot(client, plan["id"], date="2026-09-15", meal="lunch", title="복사할 칸")
    copied = client.post(f"/api/meal-plans/{plan['id']}/copy-week", json={"from_on": "2026-09-14", "weeks": 1}).get_json()
    assert all("eaten_log_id" in s for s in copied["plan"]["slots"])
    week_later = next(s for s in copied["plan"]["slots"] if s["date"] == "2026-09-21")
    assert week_later["eaten_log_id"] is None


def test_caps_apply(client, login, app, monkeypatch):
    login()
    monkeypatch.setattr("app.food_logs.MAX_PER_DAY", 1)
    with app.app_context():
        db.session.add(FoodLog(user_id=1, eaten_on=date(2026, 9, 14), meal="lunch", title="이미 있음"))
        db.session.commit()

    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", title="직접 쓰기").get_json()
    assert error(eat(client, slot["id"])) == (400, "하루에 1개까지 남길 수 있어요.")


def test_eaten_race_returns_existing(client, login, app, monkeypatch):
    user = login()
    plan = make_plan(client, start_on="2026-09-14").get_json()
    slot = put_slot(client, plan["id"], date="2026-09-14", meal="dinner", title="직접 쓰기").get_json()

    def fake_with_row(data):
        db.session.add(FoodLog(user_id=user.id, eaten_on=date(2026, 9, 14), meal="dinner", title="먼저 남김", meal_slot_id=slot["id"]))
        db.session.commit()
        return None

    monkeypatch.setattr("app.food_logs.create_log", fake_with_row)
    res = eat(client, slot["id"])
    assert res.status_code == 200
    assert res.get_json()["title"] == "먼저 남김"
    with app.app_context():
        assert FoodLog.query.count() == 1

    slot2 = put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="직접 쓰기2").get_json()

    def fake_empty(data):
        return None

    monkeypatch.setattr("app.food_logs.create_log", fake_empty)
    assert error(eat(client, slot2["id"])) == (400, BAD)
