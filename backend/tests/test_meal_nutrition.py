from app.models import FoodSearch, UnitWeightEstimate, utcnow
from tests.test_meal_ai import apply, new_dish
from tests.test_meals import add_recipe, make_plan, put_slot
from tests.test_nutrition import add_foods, cached


def get_plan(client, plan_id):
    return client.get(f"/api/meal-plans/{plan_id}")


def test_recipe_slot_uses_calculated_per_serving(client, login, app):
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
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"], recipe_id=recipe["id"], servings=3).get_json()

    assert slot["nutrition"]["kcal"] == round((252 + 15.9) / 2) == 134
    assert (slot["nutrition"]["source"], slot["nutrition"]["approx"]) == ("calc", True)
    # 값이 빠진 영양소는 레시피 계산의 incomplete를 그대로(결정 14 개정 2) — 두부는 단백질만, 간장은 나트륨만 있다
    assert slot["nutrition"]["incomplete"] == {
        "carbs_g": ["두부", "간장"], "protein_g": ["간장"], "fat_g": ["두부", "간장"], "sugars_g": ["두부", "간장"], "sodium_mg": ["두부"],
    }
    assert get_plan(client, plan["id"]).get_json()["nutrition_pending_recipe_ids"] == []


def test_mostly_missing_recipe_falls_back_to_est_kcal(client, login, app):
    login()
    add_foods(app, cached("T1", "두부", kcal=84, group="원재료성"))
    body = {
        "dishes": [new_dish("잡탕", ingredients=[{"name": "두부", "amount": "100g"}, {"name": "소금", "amount": "1g"}, {"name": "후추", "amount": "1g"}])],
        "slots": [{"date": "2026-09-15", "meal": "lunch", "dish": 0, "est_kcal": 420}],
    }
    plan = make_plan(client).get_json()
    assert apply(client, plan["id"], body).status_code == 201

    slot = get_plan(client, plan["id"]).get_json()["slots"][0]
    assert slot["nutrition"] == {
        "kcal": 420, "carbs_g": None, "protein_g": None, "fat_g": None, "sugars_g": None, "sodium_mg": None,
        "approx": True, "source": "ai", "incomplete": {},
    }

    # 같은 레시피를 PUT으로 다시 넣으면(계산 줄은 여전히 모자라지만) est_kcal이 비워져 계산값(약)으로 바뀐다
    slot = put_slot(client, plan["id"], date="2026-09-15", meal="lunch", recipe_id=slot["recipe_id"]).get_json()
    assert (slot["nutrition"]["source"], slot["nutrition"]["approx"]) == ("calc", True)
    assert slot["nutrition"]["incomplete"] == dict.fromkeys(("carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg"), ["두부"])


def test_text_slots(client, login, app):
    login()
    plan = make_plan(client).get_json()

    direct = put_slot(client, plan["id"], date="2026-09-15", meal="lunch", title="직접 쓰기").get_json()
    assert direct["nutrition"] is None

    body = {"dishes": [new_dish("된장국")], "slots": [{"date": "2026-09-16", "meal": "dinner", "dish": 0, "est_kcal": 310}]}
    assert apply(client, plan["id"], body).status_code == 201
    slots = get_plan(client, plan["id"]).get_json()["slots"]
    ai_slot = next(s for s in slots if s["date"] == "2026-09-16")
    assert ai_slot["recipe_id"] is not None

    assert client.delete(f"/api/recipes/{ai_slot['recipe_id']}").status_code == 204
    ai_slot = next(s for s in get_plan(client, plan["id"]).get_json()["slots"] if s["date"] == "2026-09-16")
    assert ai_slot["recipe_id"] is None
    assert ai_slot["nutrition"] == {
        "kcal": 310, "carbs_g": None, "protein_g": None, "fat_g": None, "sugars_g": None, "sodium_mg": None,
        "approx": True, "source": "ai", "incomplete": {},
    }


def test_pending_ids_listed_once(client, login):
    login()
    recipe = add_recipe(client, "미역국", [{"name": "미역", "amount": "1줌"}])
    plan = make_plan(client).get_json()
    put_slot(client, plan["id"], date="2026-09-15", meal="lunch", recipe_id=recipe["id"])
    put_slot(client, plan["id"], date="2026-09-16", meal="dinner", recipe_id=recipe["id"])

    body = get_plan(client, plan["id"]).get_json()
    assert body["nutrition_pending_recipe_ids"] == [recipe["id"]]
    assert all(s["nutrition"] is None for s in body["slots"])


def test_put_and_patch_slot_return_nutrition(client, login):
    login()
    plan = make_plan(client).get_json()
    slot = put_slot(client, plan["id"]).get_json()
    assert "nutrition" in slot
    res = client.patch(f"/api/meal-slots/{slot['id']}", json={"servings": 2})
    assert "nutrition" in res.get_json()


def test_nutrition_off_mode_only_est_kcal(client, login, app):
    login()
    recipe = add_recipe(client, "두부조림", [{"name": "두부", "amount": "1모"}])
    plan = make_plan(client).get_json()

    body = {"dishes": [new_dish("된장국")], "slots": [{"date": "2026-09-16", "meal": "dinner", "dish": 0, "est_kcal": 500}]}
    assert apply(client, plan["id"], body).status_code == 201

    app.config.update(DEV_MODE=False)
    slot = put_slot(client, plan["id"], date="2026-09-15", meal="lunch", recipe_id=recipe["id"]).get_json()
    assert slot["nutrition"] is None

    body = get_plan(client, plan["id"]).get_json()
    ai_slot = next(s for s in body["slots"] if s["date"] == "2026-09-16")
    assert (ai_slot["nutrition"]["kcal"], ai_slot["nutrition"]["source"]) == (500, "ai")
    assert body["nutrition_pending_recipe_ids"] == []


def test_same_recipe_in_many_slots_is_calculated_once(client, login, app, monkeypatch):
    """M1: 같은 레시피 칸이 여럿이어도 레시피 영양은 한 번만 계산한다."""
    from app.nutrition import NutritionContext

    login()
    recipe = add_recipe(client, "두부조림", [{"name": "두부", "amount": "100g"}])
    plan = make_plan(client).get_json()
    for date in ("2026-09-15", "2026-09-16", "2026-09-17"):
        put_slot(client, plan["id"], date=date, recipe_id=recipe["id"])
    calls = []
    real = NutritionContext.recipe
    monkeypatch.setattr(NutritionContext, "recipe", lambda self, r: calls.append(r.id) or real(self, r))
    assert len(get_plan(client, plan["id"]).get_json()["slots"]) == 3
    assert calls == [recipe["id"]]
