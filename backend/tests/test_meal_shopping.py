from datetime import date

import pytest

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
    assert (row["need"], row["need_spoon"], row["need_extra"]) == ([], [{"quantity": 2, "unit": "큰술"}], [])
    assert (row["quantity"], row["unit"]) == (1, "개")  # need가 비었을 때 기본값(재고가 없을 때 담는 한 통과 같은 값)


def test_spoon_unit_without_stock_is_seasoning_one_pack():
    # 된장 2큰술: 재고에 전혀 없으면 양념 묶음(화면 체크 꺼짐, 담으면 한 통 1개) — 집에 있는데 재고에 안 넣은 양념을 자동으로 담지 않게.
    # `단위가 달라요`는 진짜 단위 충돌만(AI 초안 레시피 11개를 넣으면 양념 11줄이 그 묶음에 섞였다)
    needs = [("된장", "2큰술", 1, date(2026, 9, 16)), ("된장", "1큰술", 2, date(2026, 9, 17)), ("된장", "2큰술", 1, date(2026, 9, 18))]
    result = shopping_rows(needs, [], [], TODAY)
    assert result["buy"] == [] and result["manual"] == [] and result["skip"] == []
    row = by_name(result["seasoning"], "된장")
    assert (row["quantity"], row["unit"], row["reason"]) == (1, "개", None)
    assert (row["need"], row["have"], row["need_extra"]) == ([], [], [])
    assert row["need_spoon"] == [{"quantity": 6, "unit": "큰술"}]  # 2 + 1×2 + 2 — 인분 배율을 곱해 더한다
    assert row["planned_on"] == "2026-09-15"


def test_spoon_amounts_scaled_and_summed_per_unit():
    # 체험 식단: 된장 2큰술 × 2·2·3인분(레시피 2인분) = 7큰술, 다진 마늘 1작은술 × 1·1·1·1·1.5 = 5½작은술. 못 읽는 글자(약간)만 한 번씩 남긴다
    days = [date(2026, 9, 16), date(2026, 9, 18), date(2026, 9, 22)]
    needs = [("된장", "2큰술", ratio, on) for ratio, on in zip([1, 1, 1.5], days)]
    needs += [("다진 마늘", "1작은술", ratio, date(2026, 9, 16)) for ratio in [1, 1, 1, 1, 1.5]]
    needs += [("소금", "1큰술", 1 / 3, date(2026, 9, 16)), ("소금", "1작은술", 1, date(2026, 9, 17)), ("소금", "약간", 1, date(2026, 9, 17)), ("소금", "약간", 2, date(2026, 9, 18))]
    seasoning = shopping_rows(needs, [], [], TODAY)["seasoning"]
    assert by_name(seasoning, "된장")["need_spoon"] == [{"quantity": 7, "unit": "큰술"}]
    assert by_name(seasoning, "다진 마늘")["need_spoon"] == [{"quantity": 5.5, "unit": "작은술"}]
    salt = by_name(seasoning, "소금")
    assert (salt["need_spoon"], salt["need_extra"]) == ([{"quantity": 0.33, "unit": "큰술"}, {"quantity": 1, "unit": "작은술"}], ["약간"])


@pytest.mark.parametrize(
    "amounts, need_spoon, need_extra",
    [
        ([""], [], []),  # 공공 레시피 절반은 양이 이름 안에 있다(`돼지고기(50g)`)
        (["2컵", "1컵"], [{"quantity": 5, "unit": "컵"}], []),  # 2컵 × 2 + 1컵. 컵은 쌀·우유처럼 많이 쓰는 양(29절 결정 5)
        (["10~15마리"], [], ["10~15마리"]),
        (["200~300g"], [], ["200~300g"]),
        (["1큰술", ""], [{"quantity": 2, "unit": "큰술"}], []),  # 양념 양과 빈 양이 섞이면 양념으로 보지 않는다
    ],
)
def test_blank_cup_range_amounts_without_stock_stay_manual(amounts, need_spoon, need_extra):
    needs = [("재료(50g)", amount, 2 if index == 0 else 1, date(2026, 9, 16)) for index, amount in enumerate(amounts)]
    result = shopping_rows(needs, [], [], TODAY)
    assert result["buy"] == [] and result["seasoning"] == [] and result["skip"] == []
    row = by_name(result["manual"], "재료(50g)")
    assert (row["quantity"], row["unit"], row["need"], row["need_spoon"], row["need_extra"]) == (1, "개", [], need_spoon, need_extra)


def test_listed_spoon_ingredient_is_skipped_not_seasoning():
    needs = [("된장", "2큰술", 1, date(2026, 9, 16))]
    result = shopping_rows(needs, [], ["된장"], TODAY)
    assert result["seasoning"] == []
    assert by_name(result["skip"], "된장")["reason"] == "listed"


def test_manual_tiny_scaled_amount_clamped_to_min():
    # 1판 × 0.001 인분 배율 → 반올림하면 0이라 최소 1로 올린다(bulk 담기 400 방지)
    needs = [("달걀", "1판", 0.001, date(2026, 9, 16))]
    stock = [("계란", 1, "개")]  # 단위가 달라 manual로 간다
    row = by_name(shopping_rows(needs, stock, [], TODAY)["manual"], "달걀")
    assert (row["quantity"], row["unit"], row["reason"]) == (1, "판", None)


def test_manual_quantity_rounds_up_to_whole_number():
    needs = [("대파", "1/2대", 5, date(2026, 9, 16))]  # 2.5대, 재고는 단 → 단위가 달라요
    row = by_name(shopping_rows(needs, [("대파", 1, "단")], [], TODAY)["manual"], "대파")
    assert (row["quantity"], row["unit"]) == (3, "대")
    assert row["need"] == [{"quantity": 2.5, "unit": "대"}]


def test_buy_rounds_up_to_whole_number_for_count_and_weight():
    # 운영에서 `0.67개 담기`·`16.67g 담기`가 보였다 — 담을 양은 정수로 올린다(모자라게 사지 않게), 필요·있음 양은 그대로 둔다
    needs = [("애호박", "1/3개", 5, date(2026, 9, 16)), ("돼지고기 앞다리살", "925g", 2 / 3, date(2026, 9, 16))]
    stock = [("애호박", 1, "개"), ("돼지고기 앞다리살", 600, "g")]
    buy = shopping_rows(needs, stock, [], TODAY)["buy"]
    zucchini, pork = by_name(buy, "애호박"), by_name(buy, "돼지고기 앞다리살")
    assert (zucchini["quantity"], zucchini["unit"], zucchini["need"]) == (1, "개", [{"quantity": 1.67, "unit": "개"}])
    assert (pork["quantity"], pork["unit"], pork["need"]) == (17, "g", [{"quantity": 616.67, "unit": "g"}])
    assert all(isinstance(row["quantity"], int) for row in buy)


def test_buy_whole_shortfall_is_not_bumped():
    needs = [("두부", "1/2모", 6, date(2026, 9, 16))]  # 3모 − 1모 = 딱 2모
    row = by_name(shopping_rows(needs, [("두부", 1, "모")], [], TODAY)["buy"], "두부")
    assert row["quantity"] == 2


def test_uncountable_without_stock_is_seasoning_one_pack():
    needs = [("소금", "약간", 1, date(2026, 9, 16))]
    result = shopping_rows(needs, [], [], TODAY)
    assert result["buy"] == [] and result["manual"] == []
    row = by_name(result["seasoning"], "소금")
    assert (row["quantity"], row["unit"], row["reason"]) == (1, "개", None)
    assert (row["need_spoon"], row["need_extra"]) == ([], ["약간"])


def test_spoon_unit_with_stock_in_other_unit_still_skips():
    # 숟가락 양만 있으면 재고 단위와 맞춰 볼 수 없다 — 이름이 같은 재고가 있으면 충분해요(단위가 달라요 아님)
    needs = [("고춧가루", "1큰술", 1, date(2026, 9, 16))]
    result = shopping_rows(needs, [("고춧가루", 500, "g")], [], TODAY)
    assert result["buy"] == [] and result["manual"] == [] and result["seasoning"] == []
    assert by_name(result["skip"], "고춧가루")["reason"] == "enough"


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
    assert body["buy"] == [] and body["manual"] == [] and body["seasoning"] == [] and body["skip"] == []
