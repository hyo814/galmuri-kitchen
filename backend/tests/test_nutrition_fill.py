import math
from types import SimpleNamespace
from datetime import datetime, time, timedelta, timezone

import pytest

from app import ai, scan
from app.ingredients import SEOUL, seoul_today
from app.models import AiCall, FoodNutrient, FoodSearch, UnitWeightEstimate, User, db
from sqlalchemy.exc import IntegrityError

from app.models import utcnow
from app.nutrition import NutritionContext, clean_guess, search_terms, store_guess
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

    def fake(key, name, page, seconds=None):
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
    recipe_id = make_recipe(client, ("두부(부침용 3kg)", "1모"), ("배추김치", "200g"), ("참깨소스", "1큰술"), ("들깨가루", "1큰술"))
    assert client.put("/api/food-matches", json={"name": "참깨소스", "food_code": None}).status_code == 204

    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": []})
    assert asked == ["두부", "배추김치", "들깨가루"]  # 참깨소스는 기억이 있어 찾지 않는다
    # 들깨가루는 찾아봤지만 후보가 없어 AI 추정 목록에 들어간다(개정 1)
    assert ai_calls == [([("두부", "모")], ["참깨소스", "들깨가루"])]  # 괄호 속 설명은 모델에 보내지 않는다
    with app.app_context():
        assert [(c.model, c.input_tokens, c.output_tokens) for c in AiCall.query.filter_by(kind="nutrition")] == [("m", 10, 20)]
        assert FoodNutrient.query.filter_by(food_code="ai:참깨소스").one().group_name == "추정"
    assert [r["status"] for r in rows_of(client, recipe_id)] == ["estimated", "ok", "estimated", "estimated"]

    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert (len(asked), len(ai_calls)) == (3, 1)


def test_countable_unmatched_food_gets_weight_and_food_in_one_fill(client, login, app, monkeypatch):
    """I1: 찾아봤지만 후보가 없는 셀 수 있는 재료는 식품 영양과 단위 무게를 한 번에 추정한다(채우기는 레시피마다 한 번)."""
    app.config.update(FOOD_NUTRITION_API_KEY="k", ANTHROPIC_API_KEY="k")
    fake_pages(monkeypatch, {})
    ai_calls = []

    def fake_ai(weights, foods):
        ai_calls.append((weights, foods))
        return guess_for(weights, foods), USAGE

    monkeypatch.setattr("app.ai.estimate_nutrition", fake_ai)
    login()
    recipe_id = make_recipe(client, ("새송이버섯", "2개"), ("느타리버섯", "100g"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert ai_calls == [([("새송이버섯", "개")], ["새송이버섯", "느타리버섯"])]
    assert [r["status"] for r in rows_of(client, recipe_id)] == ["estimated", "estimated"]


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
        {"name": "버터", **good, "carbs_g": 40, "protein_g": 30, "fat_g": 31},  # 탄단지 합 100 넘음
        {"name": "꿀", **good, "carbs_g": 10, "sugars_g": 11},  # 당류가 탄수화물보다 많음
    ]
    food_names = ["참깨소스", "들깨가루", "굴소스", "마요네즈", "케첩", "버터", "꿀"]
    weights, foods = clean_guess({"weights": raw_weights, "foods": raw_foods}, weight_pairs, food_names)
    assert weights == {("두부", "모"): 300, ("애호박", "개"): 250.5}
    assert foods == {"참깨소스": {"name": "참깨소스", **good}}
    assert clean_guess(None, weight_pairs, food_names) == ({}, {})
    assert clean_guess({"weights": "x", "foods": [1]}, weight_pairs, food_names) == ({}, {})


def fixed_clock(monkeypatch):
    fixed_today = seoul_today()
    fixed_now = datetime.combine(fixed_today, time(12), tzinfo=SEOUL).astimezone(timezone.utc)
    monkeypatch.setattr(scan, "seoul_today", lambda: fixed_today)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    return fixed_now


def add_calls(app, user_id, count, at, kind="nutrition", demo=False):
    with app.app_context():
        db.session.add_all(AiCall(user_id=user_id, kind=kind, demo=demo, created_at=at - timedelta(hours=1, minutes=i)) for i in range(count))
        db.session.commit()


def login_demo(app, login, provider_id):
    user = login(provider_id)
    with app.app_context():
        db.session.get(User, user.id).provider = "demo"
        db.session.commit()
    return user


def on_mode_with_tofu(app, monkeypatch):
    """두부는 캐시에서 자동 맞추기 → 무게만 AI가 필요하다."""
    app.config.update(FOOD_NUTRITION_API_KEY="k", ANTHROPIC_API_KEY="k")
    monkeypatch.setattr("app.foods.fetch_page", fail)
    add_foods(app, cached("T1", "두부"))
    ai_calls = []

    def fake_ai(weights, foods):
        ai_calls.append((weights, foods))
        return guess_for(weights, foods), USAGE

    monkeypatch.setattr("app.ai.estimate_nutrition", fake_ai)
    return ai_calls


def test_ai_limit_or_error_without_error(client, login, app, monkeypatch):
    ai_calls = on_mode_with_tofu(app, monkeypatch)
    fixed_now = fixed_clock(monkeypatch)

    # ① 하루 20번을 다 쓰면 계산 중으로 두지 않고 무게를 알려달라고 한다(I2, 고르기로 고칠 수 있게)
    user = login("1")
    add_calls(app, user.id, 19, fixed_now)
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "pending"
    add_calls(app, user.id, 1, fixed_now)
    assert rows_of(client, recipe_id)[0]["status"] == "needs_weight"
    res = fill(client, [recipe_id])
    assert (res.status_code, res.get_json()) == (200, {"pending_recipe_ids": []})

    # ② 체험 계정은 하루 2번
    demo_user = login_demo(app, login, "2")
    add_calls(app, demo_user.id, 2, fixed_now, demo=True)
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "needs_weight"
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert ai_calls == []

    # ②-1 60초 10번(연속)은 곧 풀리므로 계산 중으로 남는다
    user4 = login("4")
    with app.app_context():
        db.session.add_all(AiCall(user_id=user4.id, kind="nutrition", created_at=fixed_now - timedelta(seconds=5)) for _ in range(10))
        db.session.commit()
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": [recipe_id]}
    assert ai_calls == []

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


def test_nutrition_limit_is_separate_from_ai_recipes_and_allows_19(client, login, app, monkeypatch):
    ai_calls = on_mode_with_tofu(app, monkeypatch)
    fixed_now = fixed_clock(monkeypatch)
    user = login()
    add_calls(app, user.id, 20, fixed_now, kind="recipe")
    add_calls(app, user.id, 19, fixed_now)
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert len(ai_calls) == 1


def test_demo_user_gets_two_nutrition_calls(client, login, app, monkeypatch):
    ai_calls = on_mode_with_tofu(app, monkeypatch)
    fixed_now = fixed_clock(monkeypatch)
    demo_user = login_demo(app, login, "1")
    add_calls(app, demo_user.id, 1, fixed_now, demo=True)
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    with app.app_context():
        assert [c.demo for c in AiCall.query.filter_by(user_id=demo_user.id, input_tokens=10)] == [True]
    assert len(ai_calls) == 1


def test_demo_nutrition_global_cap_skips_ai_and_stops_pending(client, login, app, monkeypatch):
    ai_calls = on_mode_with_tofu(app, monkeypatch)
    fixed_now = fixed_clock(monkeypatch)
    assert app.config["DEMO_NUTRITION_GLOBAL_DAILY"] == 30
    app.config.update(DEMO_NUTRITION_GLOBAL_DAILY=2)
    add_calls(app, None, 1, fixed_now, demo=True)
    add_calls(app, None, 5, fixed_now)  # 일반 사용자 호출은 체험 전체 한도에 세지 않는다
    add_calls(app, None, 3, fixed_now - timedelta(days=1), demo=True)  # 어제 호출도 세지 않는다
    demo_user = login_demo(app, login, "1")
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "pending"

    add_calls(app, None, 1, fixed_now, demo=True)  # 오늘 체험 전체 2번 → 다 씀
    assert rows_of(client, recipe_id)[0]["status"] == "needs_weight"  # 끝없이 계산 중으로 두지 않는다
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert ai_calls == []
    with app.app_context():
        assert AiCall.query.filter_by(user_id=demo_user.id).count() == 0

    login("2")  # 일반 사용자는 체험 한도와 무관
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    assert len(ai_calls) == 1


def test_demo_with_spent_ai_budget_does_not_store_sample_values(client, login, app, monkeypatch):
    on_mode_with_tofu(app, monkeypatch)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    app.config.update(DEMO_AI_GLOBAL_DAILY=1)
    with app.app_context():
        db.session.add(AiCall(user_id=None, demo=True, kind="recipe", created_at=utcnow()))
        db.session.commit()
    login_demo(app, login, "1")
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "needs_weight"
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}
    with app.app_context():
        assert (UnitWeightEstimate.query.count(), FoodNutrient.query.filter_by(source="ai").count()) == (0, 0)


def test_user_ai_global_budget_skips_ai_and_stops_pending(client, login, app, monkeypatch):
    on_mode_with_tofu(app, monkeypatch)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    app.config.update(USER_AI_GLOBAL_DAILY=1)
    login()
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "pending"
    add_calls(app, None, 1, utcnow(), kind="recipe")  # 로그인 사용자 전체 AI 예산을 다 씀 → 오류 없이 AI 추정만 끈다
    assert rows_of(client, recipe_id)[0]["status"] == "needs_weight"
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}


def test_store_guess_retries_after_concurrent_insert(app, monkeypatch):
    with app.app_context():
        real_commit, commits = db.session.commit, []

        def racing_commit():
            commits.append(1)
            if len(commits) == 1:  # 다른 요청이 두부 모를 먼저 넣었다
                db.session.rollback()
                db.session.add(UnitWeightEstimate(name_key="두부", unit="모", grams=250, source="ai"))
                real_commit()
                raise IntegrityError("INSERT", {}, Exception("unique"))
            real_commit()

        monkeypatch.setattr(db.session, "commit", racing_commit)
        store_guess({("두부", "모"): 300.0, ("대파", "대"): 100.0}, {"참깨소스": {"name": "참깨소스", **ai.SAMPLE_FOOD}}, "ai")
        monkeypatch.undo()
        assert len(commits) == 2
        assert sorted((w.name_key, w.unit, w.grams) for w in UnitWeightEstimate.query) == [("대파", "대", 100), ("두부", "모", 250)]
        assert FoodNutrient.query.filter_by(food_code="ai:참깨소스").count() == 1


def test_deadline_after_search_skips_fallback_and_ai(client, login, app, monkeypatch):
    app.config.update(FOOD_NUTRITION_API_KEY="k", ANTHROPIC_API_KEY="k")
    clock = [0.0]
    monkeypatch.setattr("app.nutrition.time", SimpleNamespace(monotonic=lambda: clock[0]))
    asked = []

    def slow_page(key, name, page, seconds=None):
        asked.append(name)
        clock[0] += 10  # 찾기 한 번에 예산(8초)을 다 썼다
        return [], 0

    monkeypatch.setattr("app.foods.fetch_page", slow_page)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    login()
    recipe_id = make_recipe(client, ("돼지고기 앞다리살", "200g"), ("두부", "1모"))
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": [recipe_id]}
    assert asked == ["돼지고기앞다리살"]  # 두 번째 말도, 다음 재료도 찾지 않고 AI도 부르지 않는다


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


def test_fetch_limit_makes_unsearched_rows_pickable_not_pending(client, login, app, monkeypatch):
    """I2: 오늘 식품 DB 찾기 한도를 다 쓰면 안 찾아본 재료는 '맞는 식품을 골라주세요'(unmatched)로 — 끝없이 계산 중으로 두지 않는다."""
    app.config.update(FOOD_NUTRITION_API_KEY="k", ANTHROPIC_API_KEY="k")
    monkeypatch.setattr("app.foods.fetch_page", fail)
    monkeypatch.setattr("app.ai.estimate_nutrition", fail)
    user = login()
    recipe_id = make_recipe(client, ("두부", "1모"))
    assert rows_of(client, recipe_id)[0]["status"] == "pending"
    with app.app_context():
        db.session.add_all(AiCall(user_id=user.id, kind="food_fetch", created_at=utcnow()) for _ in range(300))
        db.session.commit()
    row = rows_of(client, recipe_id)[0]
    assert (row["status"], row["pending_reason"]) == ("unmatched", None)
    assert fill(client, [recipe_id]).get_json() == {"pending_recipe_ids": []}


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


def test_context_multiword_fallback_auto_match(app):
    with app.app_context():
        user = User(provider="test", provider_id="1", nickname="u")
        db.session.add_all([user, cached("P1", "돼지고기_앞다리_생것"), cached("P2", "돼지고기_삼겹살_생것"),
                            FoodSearch(query_key="돼지고기목살", total=0, searched_at=utcnow())])
        db.session.commit()
        recipe = SimpleNamespace(servings=1, ingredients=[{"name": "돼지고기 앞다리살", "amount": "300g"}, {"name": "돼지고기 목살", "amount": "300g"}])
        context = NutritionContext(user, [recipe])
        shoulder = context.resolve("돼지고기앞다리살")
        assert (shoulder["state"], shoulder["food"]["food_code"]) == ("auto", "P1")
        assert context.resolve("돼지고기목살")["state"] == "estimate_missing"  # 목살 조각이 없으면 추정 쪽 그대로
