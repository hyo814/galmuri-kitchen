from datetime import date

import app.meals as meals_module
from app.meals import shopping_rows
from tests.test_meals import add_ingredient, add_recipe, make_plan, put_slot

TODAY = date(2026, 9, 15)


def by_name(rows, name):
    return next(r for r in rows if r["name"] == name)


def test_buy_short_amount():
    needs = [("두부", "2모", 1, date(2026, 9, 16))]
    stock = [("두부", 1, "모")]
    result = shopping_rows(needs, stock, [], TODAY)
    assert result["skip"] == [] and result["manual"] == []
    row = by_name(result["buy"], "두부")
    assert (row["quantity"], row["unit"], row["reason"]) == (1, "모", None)
    assert row["need"] == [{"quantity": 2, "unit": "모"}]
    assert row["have"] == [{"quantity": 1, "unit": "모"}]


def test_buy_grams():
    needs = [("돼지고기 앞다리살", "400g", 1, date(2026, 9, 16))]
    stock = [("돼지고기 앞다리살", 200, "g")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["buy"], "돼지고기 앞다리살")
    assert (row["quantity"], row["unit"]) == (200, "g")


def test_buy_no_stock():
    needs = [("청양고추", "2개", 1, date(2026, 9, 16))]
    row = by_name(shopping_rows(needs, [], [], TODAY)["buy"], "청양고추")
    assert (row["quantity"], row["unit"]) == (2, "개")
    assert row["have"] == []


def test_buy_planned_on_day_before_meal():
    needs = [("애호박", "2개", 1, date(2026, 9, 17))]
    stock = [("애호박", 1, "개")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["buy"], "애호박")
    assert (row["quantity"], row["planned_on"]) == (1, "2026-09-16")


def test_manual_unit_mismatch_with_synonym():
    needs = [("달걀", "2판", 1, date(2026, 9, 16))]
    stock = [("계란", 8, "개")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["manual"], "달걀")
    assert (row["quantity"], row["unit"], row["reason"]) == (2, "판", None)
    assert row["have"] == [{"quantity": 8, "unit": "개"}]


def test_manual_unit_mismatch():
    needs = [("대파", "4대", 1, date(2026, 9, 16))]
    stock = [("대파", 1, "단")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["manual"], "대파")
    assert (row["quantity"], row["unit"]) == (4, "대")


def test_skip_listed():
    needs = [("양파", "2개", 1, date(2026, 9, 16))]
    result = shopping_rows(needs, [], ["양파"], TODAY)
    row = by_name(result["skip"], "양파")
    assert row["reason"] == "listed"
    assert (row["quantity"], row["unit"]) == (2, "개")  # Task 9 계약: quantity·unit은 null 아님
    assert result["buy"] == [] and result["manual"] == []


def test_skip_enough():
    needs = [("김치", "1/2포기", 1, date(2026, 9, 16))]
    stock = [("김치", 1, "포기")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["skip"], "김치")
    assert row["reason"] == "enough"
    assert (row["quantity"], row["unit"]) == (0.5, "포기")


def test_skip_enough_tiny_fraction_not_buy_zero():
    # 1모 × 1/3 인분 배율(0.3333...) − 재고 0.33모 = 반올림하면 0이라 buy 0.0 대신 skip enough
    needs = [("두부", "1모", 1 / 3, date(2026, 9, 16))]
    stock = [("두부", 0.33, "모")]
    result = shopping_rows(needs, stock, [], TODAY)
    assert result["buy"] == []
    row = by_name(result["skip"], "두부")
    assert row["reason"] == "enough"
    assert (row["quantity"], row["unit"]) == (0.33, "모")


def test_planned_on_today_when_meal_already_passed():
    needs = [("두부", "1모", 1, date(2026, 9, 14))]  # 오늘(9/15)보다 이전 끼니
    row = by_name(shopping_rows(needs, [], [], TODAY)["buy"], "두부")
    assert row["planned_on"] == TODAY.isoformat()


def test_planned_on_today_for_todays_meal():
    needs = [("두부", "1모", 1, TODAY)]  # 오늘 끼니: 전날(9/14)은 지났으니 오늘 산다
    row = by_name(shopping_rows(needs, [], [], TODAY)["buy"], "두부")
    assert row["planned_on"] == TODAY.isoformat()


def test_two_slots_same_ingredient_sum_with_ratio():
    needs = [
        ("두부", "1모", 2, date(2026, 9, 16)),
        ("두부", "1/2모", 1, date(2026, 9, 17)),
    ]
    row = by_name(shopping_rows(needs, [], [], TODAY)["buy"], "두부")
    assert row["need"] == [{"quantity": 2.5, "unit": "모"}]


def test_sum_kg_and_g():
    needs = [
        ("돼지고기", "1kg", 1, date(2026, 9, 16)),
        ("돼지고기", "200g", 1, date(2026, 9, 16)),
    ]
    row = by_name(shopping_rows(needs, [], [], TODAY)["buy"], "돼지고기")
    assert row["need"] == [{"quantity": 1200, "unit": "g"}]


def test_spoon_unit_with_stock_skips_enough():
    needs = [("간장", "2큰술", 1, date(2026, 9, 16))]
    stock = [("간장", 1, "병")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["skip"], "간장")
    assert row["reason"] == "enough"
    assert row["need"] == []
    assert row["need_extra"] == ["2큰술"]
    assert (row["quantity"], row["unit"]) == (1, "개")  # need가 비었을 때 기본값(manual과 같은 폴백)


def test_manual_tiny_scaled_amount_clamped_to_min():
    # 1판 × 0.001 인분 배율 → 반올림하면 0이라 최소 0.01로 올린다(bulk 담기 400 방지)
    needs = [("달걀", "1판", 0.001, date(2026, 9, 16))]
    stock = [("계란", 1, "개")]  # 단위가 달라 manual로 간다
    row = by_name(shopping_rows(needs, stock, [], TODAY)["manual"], "달걀")
    assert (row["quantity"], row["unit"], row["reason"]) == (0.01, "판", None)
    assert row["quantity"] >= 0.01


def test_uncountable_without_stock_is_manual_with_extra():
    needs = [("소금", "약간", 1, date(2026, 9, 16))]
    row = by_name(shopping_rows(needs, [], [], TODAY)["manual"], "소금")
    assert (row["quantity"], row["unit"]) == (1, "개")
    assert row["need_extra"] == ["약간"]


def test_always_have_water_excluded():
    needs = [("물", "2L", 1, date(2026, 9, 16))]
    result = shopping_rows(needs, [], [], TODAY)
    assert result["buy"] == [] and result["manual"] == [] and result["skip"] == []


def test_two_different_units_is_manual_with_first_unit():
    needs = [
        ("대파", "2개", 1, date(2026, 9, 16)),
        ("대파", "200g", 1, date(2026, 9, 16)),
    ]
    row = by_name(shopping_rows(needs, [], [], TODAY)["manual"], "대파")
    assert (row["quantity"], row["unit"], row["reason"]) == (2, "개", None)
    assert row["need"] == [{"quantity": 2, "unit": "개"}, {"quantity": 200, "unit": "g"}]


def test_synonyms_grouped_under_first_name_seen():
    needs = [("계란", "2개", 1, date(2026, 9, 16)), ("달걀", "1개", 1, date(2026, 9, 17))]
    result = shopping_rows(needs, [], [], TODAY)
    assert [row["name"] for row in result["buy"]] == ["계란"]
    assert (result["buy"][0]["quantity"], result["buy"][0]["unit"]) == (3, "개")


def test_same_unit_stock_counts_even_with_other_unit_stock():
    needs = [("두부", "2모", 1, date(2026, 9, 16))]
    stock = [("두부", 1, "모"), ("두부", 300, "g")]
    row = by_name(shopping_rows(needs, stock, [], TODAY)["buy"], "두부")
    assert (row["quantity"], row["unit"]) == (1, "모")
    assert row["have"] == [{"quantity": 1, "unit": "모"}, {"quantity": 300, "unit": "g"}]


def test_stock_with_unreadable_unit_has_stock_but_empty_have():
    stock = [("간장", 1, "~"), ("두부", 1, "~")]
    result = shopping_rows([("간장", "2큰술", 1, date(2026, 9, 16)), ("두부", "2모", 1, date(2026, 9, 16))], stock, [], TODAY)
    assert by_name(result["skip"], "간장")["reason"] == "enough"  # 재고는 있다(has_stock)
    row = by_name(result["buy"], "두부")  # 양을 못 읽으니 전부 산다
    assert (row["quantity"], row["unit"], row["have"]) == (2, "모", [])


def test_large_stock_quantity_is_read():
    needs = [("쌀", "2kg", 1, date(2026, 9, 16))]
    stock = [("쌀", 1_500_000, "g")]  # :g였으면 1.5e+06g로 읽지 못해 2kg을 다 샀다
    row = by_name(shopping_rows(needs, stock, [], TODAY)["skip"], "쌀")
    assert row["have"] == [{"quantity": 1_500_000, "unit": "g"}]


def test_blank_normalized_name_is_not_marked_listed():
    needs = [("(국산)", "1개", 1, date(2026, 9, 16))]
    result = shopping_rows(needs, [], ["(수입)"], TODAY)
    assert result["skip"] == []
    assert by_name(result["buy"], "(국산)")["reason"] is None


def test_ordering_within_bucket_by_planned_on_then_first_seen():
    needs = [
        ("나중", "1개", 1, date(2026, 9, 20)),
        ("먼저", "1개", 1, date(2026, 9, 18)),
        ("동점1", "1개", 1, date(2026, 9, 18)),
        ("동점2", "1개", 1, date(2026, 9, 18)),
    ]
    result = shopping_rows(needs, [], [], TODAY)
    names = [row["name"] for row in result["buy"]]
    assert names == ["먼저", "동점1", "동점2", "나중"]


# --- API ---


def test_preview_uses_servings_ratio_and_today_onward(client, login, app, monkeypatch):
    monkeypatch.setattr(meals_module, "seoul_today", lambda: TODAY)
    login()
    recipe = add_recipe(client, "두부조림", [{"name": "두부", "amount": "1모"}], servings=2)
    plan = make_plan(client, start_on="2026-09-14", days=7).get_json()
    put_slot(client, plan["id"], date="2026-09-14", meal="lunch", recipe_id=recipe["id"])
    put_slot(client, plan["id"], date="2026-09-16", meal="dinner", recipe_id=recipe["id"], servings=4)
    put_slot(client, plan["id"], date="2026-09-16", meal="lunch", title="직접 쓰기")

    res = client.get(f"/api/meal-plans/{plan['id']}/shopping-preview")
    assert res.status_code == 200
    body = res.get_json()
    assert (body["name"], body["start_on"], body["end_on"], body["recipe_slot_count"]) == ("9월 셋째 주", "2026-09-15", "2026-09-20", 1)
    row = by_name(body["manual"] + body["buy"] + body["skip"], "두부")
    assert row["need"] == [{"quantity": 2, "unit": "모"}]
    assert row["planned_on"] == "2026-09-15"


def test_preview_only_this_users_stock_and_listed(client, login, app, monkeypatch):
    monkeypatch.setattr(meals_module, "seoul_today", lambda: TODAY)
    login("owner")
    recipe = add_recipe(client, "두부조림", [{"name": "두부", "amount": "1모"}], servings=1)
    plan = make_plan(client, start_on="2026-09-15", days=7).get_json()
    put_slot(client, plan["id"], date="2026-09-15", meal="lunch", recipe_id=recipe["id"])
    add_ingredient(client, "두부", quantity=1, unit="모")
    assert client.post(
        "/api/shopping/items/bulk", json={"source": "manual", "items": [{"name": "두부", "quantity": 1, "unit": "모"}]}
    ).status_code == 201

    login("other")
    other_recipe = add_recipe(client, "다른식단", [{"name": "두부", "amount": "1모"}], servings=1)
    other_plan = make_plan(client, name="다른", start_on="2026-09-15", days=7).get_json()
    put_slot(client, other_plan["id"], date="2026-09-15", meal="lunch", recipe_id=other_recipe["id"])
    add_ingredient(client, "당근", quantity=5, unit="개")

    res = client.get(f"/api/meal-plans/{other_plan['id']}/shopping-preview")
    assert res.status_code == 200
    body = res.get_json()
    row = by_name(body["manual"] + body["buy"] + body["skip"], "두부")
    assert row["reason"] != "listed"
    assert row["have"] == []


def test_preview_other_user_404(client, login):
    login("owner")
    plan = make_plan(client).get_json()

    login("intruder")
    res = client.get(f"/api/meal-plans/{plan['id']}/shopping-preview")
    assert res.status_code == 404


def test_preview_past_plan_empty(client, login, monkeypatch):
    monkeypatch.setattr(meals_module, "seoul_today", lambda: date(2026, 10, 1))
    login()
    plan = make_plan(client, start_on="2026-09-14", days=7).get_json()
    recipe = add_recipe(client, "두부조림", [{"name": "두부", "amount": "1모"}], servings=1)
    put_slot(client, plan["id"], date="2026-09-15", meal="lunch", recipe_id=recipe["id"])

    res = client.get(f"/api/meal-plans/{plan['id']}/shopping-preview")
    assert res.status_code == 200
    body = res.get_json()
    assert body["recipe_slot_count"] == 0
    assert body["buy"] == [] and body["manual"] == [] and body["skip"] == []
