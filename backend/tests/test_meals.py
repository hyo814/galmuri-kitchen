from datetime import date

import pytest

import app.meals as meals_module
from app.ingredients import seoul_today
from app.models import MealPlan, MealSlot, User, db

DEFAULT_PLAN = {"name": "9월 셋째 주", "start_on": "2026-09-14", "days": 7, "default_servings": 2}


def make_plan(client, **overrides):
    return client.post("/api/meal-plans", json={**DEFAULT_PLAN, **overrides})


def add_ingredient(client, name, **fields):
    body = {"name": name, "purchased_on": seoul_today().isoformat(), **fields}
    assert client.post("/api/ingredients", json=body).status_code == 201


def add_recipe(client, title, ingredients, **fields):
    body = {"title": title, "servings": 1, "ingredients": ingredients, "steps": [], **fields}
    return client.post("/api/recipes", json=body).get_json()


def put_slot(client, plan_id, **overrides):
    body = {"date": "2026-09-15", "meal": "lunch", "title": "직접 쓰기", **overrides}
    return client.put(f"/api/meal-plans/{plan_id}/slots", json=body)


def test_requires_login_and_csrf(client, raw_client):
    assert client.get("/api/meal-plans").status_code == 401
    assert raw_client.post("/api/meal-plans", json=DEFAULT_PLAN).status_code == 400


def test_create_and_list_with_default_servings(client, login):
    login()
    assert client.get("/api/meal-plans").get_json() == {"items": [], "default_servings": 1}

    res = make_plan(client, default_servings=3)
    assert res.status_code == 201
    plan = res.get_json()
    assert (plan["start_on"], plan["end_on"], plan["days"], plan["total"], plan["filled"], plan["slots"]) == (
        "2026-09-14", "2026-09-20", 7, 28, 0, [],
    )
    assert plan["default_servings"] == 3

    assert client.get("/api/meal-plans").get_json()["default_servings"] == 3

    make_plan(client, name="10월 첫째 주", start_on="2026-10-01", default_servings=2)
    body = client.get("/api/meal-plans").get_json()
    assert body["default_servings"] == 2
    assert [item["start_on"] for item in body["items"]] == ["2026-10-01", "2026-09-14"]


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"name": None}, "식단 이름은 1~30자로 입력해주세요."),
        ({"name": "가" * 31}, "식단 이름은 1~30자로 입력해주세요."),
        ({"start_on": "2026/09/14"}, "시작일을 골라주세요."),
        ({"start_on": None}, "시작일을 골라주세요."),
        ({"days": 0}, "기간은 1~31 사이 정수로 입력해주세요."),
        ({"days": 32}, "기간은 1~31 사이 정수로 입력해주세요."),
        ({"days": True}, "기간은 1~31 사이 정수로 입력해주세요."),
        ({"days": "7"}, "기간은 1~31 사이 정수로 입력해주세요."),
        ({"default_servings": 0}, "기본 인분은 1~20 사이 정수로 입력해주세요."),
        ({"default_servings": 21}, "기본 인분은 1~20 사이 정수로 입력해주세요."),
    ],
)
def test_create_validation(client, login, overrides, message):
    login()
    res = make_plan(client, **overrides)
    assert (res.status_code, res.get_json()["error"]) == (400, message)


def test_plan_cap_50(client, login, app):
    user = login()
    with app.app_context():
        db.session.add_all(
            MealPlan(user_id=user.id, name=f"식단{i}", start_on=date(2026, 1, 1), days=7, default_servings=1)
            for i in range(meals_module.MAX_PLANS)
        )
        db.session.commit()
    res = make_plan(client)
    assert res.status_code == 400
    assert res.get_json()["error"] == f"식단은 {meals_module.MAX_PLANS}개까지 만들 수 있어요. 지난 식단을 지워주세요."


def test_put_slot_recipe_text_and_overwrite(client, login):
    login()
    plan = make_plan(client).get_json()
    recipe = add_recipe(client, "라면", [{"name": "라면", "amount": "1개"}])

    res = client.put(f"/api/meal-plans/{plan['id']}/slots", json={"date": "2026-09-15", "meal": "lunch", "recipe_id": recipe["id"]})
    assert res.status_code == 200
    slot = res.get_json()
    assert (slot["title"], slot["recipe_id"], slot["servings"]) == ("라면", recipe["id"], 2)  # 식단 기본 인분(2)
    assert slot["have_count"] is not None and slot["total_count"] == 1

    res2 = client.put(
        f"/api/meal-plans/{plan['id']}/slots",
        json={"date": "2026-09-15", "meal": "lunch", "title": "라면에 달걀 하나", "servings": 3},
    )
    assert res2.status_code == 200
    slot2 = res2.get_json()
    assert (slot2["id"], slot2["title"], slot2["recipe_id"], slot2["est_kcal"], slot2["servings"]) == (
        slot["id"], "라면에 달걀 하나", None, None, 3,
    )

    detail = client.get(f"/api/meal-plans/{plan['id']}").get_json()
    assert detail["filled"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"date": "2026-09-13"},
        {"date": "2026-09-21"},
        {"date": None},
        {"date": "2026-09-15", "meal": "brunch"},
        {"title": ""},
        {"title": "가" * 61},
        {"servings": 21},
    ],
)
def test_put_slot_validation(client, login, overrides):
    login()
    plan = make_plan(client).get_json()
    res = put_slot(client, plan["id"], **overrides)
    assert res.status_code == 400


def test_put_slot_out_of_range_message(client, login):
    login()
    plan = make_plan(client).get_json()
    assert put_slot(client, plan["id"], date="2026-09-13").get_json()["error"] == meals_module.OUT_OF_RANGE
    assert put_slot(client, plan["id"], date="2026-09-21").get_json()["error"] == meals_module.OUT_OF_RANGE


def test_put_slot_recipe_id_not_found_or_others(client, login):
    owner = login("owner")
    plan = make_plan(client).get_json()

    login("other")
    other_recipe = add_recipe(client, "다른 사람 레시피", [{"name": "당근", "amount": "1개"}])

    with client.session_transaction() as s:  # 세션을 owner로 되돌린다(login()은 매번 새 사용자를 만든다)
        s["user_id"], s["pid"] = owner.id, owner.provider_id

    assert put_slot(client, plan["id"], recipe_id=other_recipe["id"]).status_code == 404
    assert put_slot(client, plan["id"], recipe_id=999999).status_code == 404


def test_plan_detail_marks_urgent_and_counts(client, login):
    login()
    add_ingredient(client, "두부", expires_on=seoul_today().isoformat())
    recipe = add_recipe(
        client, "김치찌개",
        [{"name": "김치", "amount": "300g"}, {"name": "두부", "amount": "1모"}, {"name": "대파", "amount": "1대"}],
    )
    plan = make_plan(client).get_json()
    put_slot(client, plan["id"], date="2026-09-15", meal="dinner", recipe_id=recipe["id"])

    detail = client.get(f"/api/meal-plans/{plan['id']}").get_json()
    assert detail["filled"] == 1
    slot = detail["slots"][0]
    assert (slot["have_count"], slot["total_count"], slot["urgent_names"]) == (1, 3, ["두부"])


def test_patch_slot_servings_and_delete_slot(client, login):
    login()
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"]).get_json()

    res = client.patch(f"/api/meal-slots/{slot['id']}", json={"servings": 4})
    assert (res.status_code, res.get_json()["servings"]) == (200, 4)

    assert client.patch(f"/api/meal-slots/{slot['id']}", json={"servings": 0}).status_code == 400

    assert client.delete(f"/api/meal-slots/{slot['id']}").status_code == 204

    detail = client.get(f"/api/meal-plans/{plan['id']}").get_json()
    assert detail["filled"] == 0


def test_patch_plan_fields_and_trim_slots_outside_range(client, login):
    login()
    plan = make_plan(client).get_json()
    put_slot(client, plan["id"], date="2026-09-14", meal="lunch", title="월요일 점심")
    put_slot(client, plan["id"], date="2026-09-20", meal="dinner", title="일요일 저녁")

    res = client.patch(f"/api/meal-plans/{plan['id']}", json={"days": 3})
    assert res.status_code == 200
    assert [s["date"] for s in res.get_json()["slots"]] == ["2026-09-14"]

    res = client.patch(f"/api/meal-plans/{plan['id']}", json={"start_on": "2026-09-15"})
    assert res.get_json()["slots"] == []

    res = client.patch(f"/api/meal-plans/{plan['id']}", json={"goal_kcal": 1800, "goal_note": " 단백질 위주 "})
    assert (res.status_code, res.get_json()["goal_kcal"], res.get_json()["goal_note"]) == (200, 1800, "단백질 위주")

    assert client.patch(f"/api/meal-plans/{plan['id']}", json={"goal_kcal": 400}).status_code == 400
    assert client.patch(f"/api/meal-plans/{plan['id']}", json={"goal_note": "가" * 101}).status_code == 400

    res = client.patch(f"/api/meal-plans/{plan['id']}", json={"goal_kcal": None})
    assert (res.status_code, res.get_json()["goal_kcal"]) == (200, None)


def test_other_users_plan_and_slot_404(client, login):
    login("owner")
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"]).get_json()

    login("intruder")
    assert client.get(f"/api/meal-plans/{plan['id']}").status_code == 404
    assert client.patch(f"/api/meal-plans/{plan['id']}", json={"name": "가로채기"}).status_code == 404
    assert client.delete(f"/api/meal-plans/{plan['id']}").status_code == 404
    assert put_slot(client, plan["id"], date="2026-09-16").status_code == 404
    assert client.patch(f"/api/meal-slots/{slot['id']}", json={"servings": 2}).status_code == 404
    assert client.delete(f"/api/meal-slots/{slot['id']}").status_code == 404

    huge = 2**31
    assert client.get(f"/api/meal-plans/{huge}").status_code == 404
    assert client.patch(f"/api/meal-slots/{huge}", json={"servings": 2}).status_code == 404


def test_deleting_recipe_keeps_slot_as_text(client, login):
    login()
    recipe = add_recipe(client, "라면", [{"name": "라면", "amount": "1개"}])
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], date="2026-09-15", meal="lunch", recipe_id=recipe["id"]).get_json()

    assert client.delete(f"/api/recipes/{recipe['id']}").status_code == 204

    detail = client.get(f"/api/meal-plans/{plan['id']}").get_json()
    kept = detail["slots"][0]
    assert (kept["id"], kept["recipe_id"], kept["title"], kept["have_count"]) == (slot["id"], None, "라면", None)


def test_user_delete_cascades(client, login, app):
    user = login()
    plan = make_plan(client).get_json()
    put_slot(client, plan["id"])

    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert MealPlan.query.count() == 0
        assert MealSlot.query.count() == 0
