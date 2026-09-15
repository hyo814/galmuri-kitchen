import math
from datetime import datetime, time, timedelta, timezone

import pytest

from app import ai, scan
from app.ingredients import SEOUL, seoul_today
from app.models import AiCall, FoodNutrient, UnitWeightEstimate, User, db
from app.nutrition import clean_guess, search_terms
from tests.test_nutrition import add_foods, cached, recipe_body

BAD = "잘못된 요청이에요."
USAGE = {"model": "m", "input_tokens": 10, "output_tokens": 20}


def fail(*args, **kwargs):
    raise AssertionError("부르면 안 돼요")


def fill(client, ids):
    return client.post("/api/nutrition/fill", json={"recipe_ids": ids})


def make_recipe(client, *ingredients):
    return client.post("/api/recipes", json=recipe_body(*ingredients)).get_json()["id"]


def rows_of(client, recipe_id):
    return client.get(f"/api/recipes/{recipe_id}/nutrition").get_json()["ingredients"]


def api_row(code, name, group):
    return {"FOOD_CD": code, "FOOD_NM_KR": name, "DB_GRP_NM": group, "SERVING_SIZE": "100g",
            "AMT_NUM1": "80", "AMT_NUM3": "8", "AMT_NUM4": "4", "AMT_NUM6": "2", "AMT_NUM7": "1", "AMT_NUM13": "10"}


def fake_pages(monkeypatch, by_name):
    """fetch_page를 가짜로. 받은 검색어를 순서대로 모은다."""
    asked = []

    def fake(key, name, page):
        asked.append(name)
        rows = by_name.get(name, [])
        return rows, len(rows)

    monkeypatch.setattr("app.foods.fetch_page", fake)
    return asked


def guess_for(weights, foods):
    return {"weights": [{"name": n, "unit": u, "grams": 300} for n, u in weights],
            "foods": [{"name": n, **ai.SAMPLE_FOOD} for n in foods]}


def test_search_terms():
    assert search_terms("두부") == ["두부"]
    assert search_terms("돼지고기 앞다리살") == ["돼지고기 앞다리살", "돼지고기"]
    assert search_terms("앞다리 돼지") == ["앞다리 돼지", "앞다리"]  # 같은 길이면 앞 낱말


def test_sample_mode_fills_without_network_or_records(client, login, app, monkeypatch):
    monkeypatch.setattr("app.foods.fetch_page", fail)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    login()
    recipe_id = make_recipe(client, ("두부", "1/2모"), ("대파", "1대"), ("소금", "약간"))

    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": []})
    tofu, leek, salt = rows_of(client, recipe_id)
    assert (tofu["status"], tofu["food"]["food_code"], tofu["unit_grams"], tofu["unit_grams_source"]) == ("estimated", "SAMPLE-01", 300, "sample")
    assert (leek["status"], leek["unit_grams"]) == ("estimated", 100)
    assert salt["status"] == "trace"
    with app.app_context():
        assert AiCall.query.count() == 0


def test_on_mode_searches_then_estimates_once(client, login, app, monkeypatch):
    app.config.update(FOOD_NUTRITION_API_KEY="k", ANTHROPIC_API_KEY="k")
    asked = fake_pages(monkeypatch, {"두부": [api_row("D1", "두부", "원재료성")], "배추김치": [api_row("K1", "배추김치", "가공식품")]})
    ai_calls = []

    def fake_ai(weights, foods):
        ai_calls.append((weights, foods))
        return guess_for(weights, foods), USAGE

    monkeypatch.setattr("app.ai.estimate_nutrition", fake_ai)
    login()
    recipe_id = make_recipe(client, ("두부", "1모"), ("배추김치", "200g"), ("참깨소스", "1큰술"), ("들깨가루", "1큰술"))
    assert client.put("/api/food-matches", json={"name": "참깨소스", "food_code": None}).status_code == 204

    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": []})
    assert asked == ["두부", "배추김치", "들깨가루"]  # 참깨소스는 기억이 있어 찾지 않는다
    # 들깨가루는 찾아봤지만 후보가 없어 AI 추정 목록에 들어간다(개정 1)
    assert ai_calls == [([("두부", "모")], ["참깨소스", "들깨가루"])]
    with app.app_context():
        assert [(c.model, c.input_tokens, c.output_tokens) for c in AiCall.query.filter_by(kind="nutrition")] == [("m", 10, 20)]
        assert FoodNutrient.query.filter_by(food_code="ai:참깨소스").one().group_name == "추정"
    assert [r["status"] for r in rows_of(client, recipe_id)] == ["estimated", "ok", "estimated", "estimated"]

    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert (len(asked), len(ai_calls)) == (3, 1)


def test_multiword_fallback_search(client, login, app, monkeypatch):
    app.config.update(FOOD_NUTRITION_API_KEY="k", DEV_MODE=False)
    asked = fake_pages(monkeypatch, {"돼지고기": [api_row("P1", "돼지고기_앞다리_생것", "원재료성")]})
    login()
    recipe_id = make_recipe(client, ("돼지고기 앞다리살", "200g"), ("두부", "300g"))
    assert fill(client, [recipe_id]).status_code == 200
    assert asked == ["돼지고기앞다리살", "돼지고기", "두부"]  # 두부는 0건이지만 한 낱말이라 다시 찾지 않는다


def test_clean_guess_drops_bad_rows():
    weight_pairs = [("두부", "모"), ("대파", "대"), ("감자", "개"), ("양파", "개"), ("애호박", "개"), ("오이", "개")]
    raw_weights = [
        {"name": "두부", "unit": "모", "grams": 300},
        {"name": "두부", "unit": "모", "grams": 250},  # 같은 줄 두 번
        {"name": "두부", "unit": "판", "grams": 900},  # 요청 안 한 단위
        {"name": "당근", "unit": "개", "grams": 100},  # 요청 안 한 이름
        {"name": "대파", "unit": "대", "grams": 0},
        {"name": "감자", "unit": "개", "grams": 9999},
        {"name": "양파", "unit": "개", "grams": -1},
        {"name": "오이", "unit": "개", "grams": True},
        {"name": "오이", "unit": "개", "grams": "많이"},
        "두부",
        {"name": "애호박 ", "unit": "개", "grams": 250.5},
    ]
    good = dict(ai.SAMPLE_FOOD)
    raw_foods = [
        {"name": "참깨소스", **good},
        {"name": "참깨소스", **good, "kcal": 1},  # 같은 줄 두 번
        {"name": "들깨가루", **good, "kcal": 950},
        {"name": "굴소스", **good, "sodium_mg": 50000},
        {"name": "김치", **good},  # 요청 안 한 이름
        {"name": "마요네즈", **{k: v for k, v in good.items() if k != "fat_g"}},
        {"name": "케첩", **good, "sugars_g": math.inf},
    ]
    food_names = ["참깨소스", "들깨가루", "굴소스", "마요네즈", "케첩"]
    weights, foods = clean_guess({"weights": raw_weights, "foods": raw_foods}, weight_pairs, food_names)
    assert weights == {("두부", "모"): 300, ("애호박", "개"): 250.5}
    assert foods == {"참깨소스": {"name": "참깨소스", **good}}
    assert clean_guess(None, weight_pairs, food_names) == ({}, {})
    assert clean_guess({"weights": "x", "foods": [1]}, weight_pairs, food_names) == ({}, {})


def test_ai_limit_or_error_leaves_pending_without_error(client, login, app, monkeypatch):
    app.config.update(FOOD_NUTRITION_API_KEY="k", ANTHROPIC_API_KEY="k")
    monkeypatch.setattr("app.foods.fetch_page", fail)
    add_foods(app, cached("T1", "두부"))  # 자동 맞추기 → 무게만 AI가 필요하다
    fixed_today = seoul_today()
    fixed_now = datetime.combine(fixed_today, time(12), tzinfo=SEOUL).astimezone(timezone.utc)
    monkeypatch.setattr(scan, "seoul_today", lambda: fixed_today)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)

    def used(user_id, count):
        with app.app_context():
            db.session.add_all(AiCall(user_id=user_id, kind="nutrition", created_at=fixed_now - timedelta(hours=1, minutes=i)) for i in range(count))
            db.session.commit()

    # ① 하루 20번
    user = login("1")
    used(user.id, 20)
    recipe_id = make_recipe(client, ("두부", "1모"))
    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": [recipe_id]})

    # ② 체험 계정 3번
    demo_user = login("2")
    with app.app_context():
        db.session.get(User, demo_user.id).provider = "demo"
        db.session.commit()
    used(demo_user.id, 3)
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": [recipe_id]}

    # ③ AI 실패: 기록은 남고 토큰은 없다
    def broken(weights, foods):
        raise ai.AiError("boom")

    monkeypatch.setattr("app.ai.estimate_nutrition", broken)
    user3 = login("3")
    recipe_id = make_recipe(client, ("두부", "1모"))
    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": [recipe_id]})
    with app.app_context():
        assert [(c.kind, c.input_tokens) for c in AiCall.query.filter_by(user_id=user3.id)] == [("nutrition", None)]
        assert UnitWeightEstimate.query.count() == 0

    # ④ 체험 전체 AI 예산을 다 써 sample이 돼도 예시 값을 공유 캐시에 넣지 않는다
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    app.config.update(DEMO_AI_GLOBAL_DAILY=1)
    demo_user2 = login("4")
    with app.app_context():
        db.session.get(User, demo_user2.id).provider = "demo"
        db.session.add(AiCall(user_id=demo_user2.id, demo=True, kind="nutrition", created_at=fixed_now))
        db.session.commit()
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": [recipe_id]}
    with app.app_context():
        assert (UnitWeightEstimate.query.count(), FoodNutrient.query.filter_by(source="ai").count()) == (0, 0)


def test_time_budget_and_fetch_limit_stop_searching(client, login, app, monkeypatch):
    app.config.update(FOOD_NUTRITION_API_KEY="k", DEV_MODE=False)
    asked = fake_pages(monkeypatch, {})
    login()
    recipe_id = make_recipe(client, ("두부", "1모"), ("대파", "1대"))

    monkeypatch.setattr("app.nutrition.FILL_SECONDS", 0)
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": [recipe_id]}
    assert asked == []

    monkeypatch.setattr("app.nutrition.FILL_SECONDS", 8)
    searched = []

    def limited(name, user):
        searched.append(name)
        return False

    monkeypatch.setattr("app.foods.search_and_cache", limited)
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": [recipe_id]}
    assert searched == ["두부"]


def test_ai_off_makes_needs_weight_not_pending(client, login, app, monkeypatch):
    app.config.update(FOOD_NUTRITION_API_KEY="k", DEV_MODE=False)
    monkeypatch.setattr("app.foods.fetch_page", fail)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    add_foods(app, cached("T1", "두부"))
    login()
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "needs_weight"
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}


@pytest.mark.parametrize("body", [
    {}, None, {"recipe_ids": None}, {"recipe_ids": []}, {"recipe_ids": list(range(1, 33))}, {"recipe_ids": ["1"]},
    {"recipe_ids": [True]}, {"recipe_ids": [1, 1]}, {"recipe_ids": [0]}, {"recipe_ids": [1.0]}, {"recipe_ids": [1, 2**31]},
    {"recipe_ids": [[1]]}, {"recipe_ids": [{}]}, {"recipe_ids": "1"},
])
def test_fill_validation(client, login, body):
    login()
    res = client.post("/api/nutrition/fill", json=body)
    assert (res.status_code, res.get_json()) == (400, {"error": BAD})


def test_fill_ownership_and_access(client, raw_client, login, app, monkeypatch):
    monkeypatch.setattr("app.foods.fetch_page", fail)
    assert fill(client, [1]).status_code == 401
    login()
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert raw_client.post("/api/nutrition/fill", json={"recipe_ids": [recipe_id]}).status_code == 400
    assert fill(client, list(range(1, 32))).status_code == 200  # 31개까지

    login("2")
    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": []})

    app.config.update(DEV_MODE=False)
    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()["error"]) == (503, "영양 계산을 지금은 쓸 수 없어요.")
