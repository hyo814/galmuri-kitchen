from types import SimpleNamespace

import pytest

from app import foods, nutrition
from app.models import FoodMatch, FoodNutrient, FoodSearch, UnitWeightEstimate, User, db, utcnow
from app.nutrition import NutritionContext, auto_match, fixed_grams, ingredient_row, match_key, recipe_nutrition

WEIGHT_ERROR = "무게는 0.1~5000g 사이로 입력해주세요."
BAD = "잘못된 요청이에요."
PICK_AGAIN = "식품을 다시 골라주세요."


def food(code, name, kcal, group="원재료성", **others):
    return {"food_code": code, "name": name, "group": group, "kcal": kcal, **{n: others.get(n) for n in foods.NUTRIENTS[1:]}}


def res(state, food=None, unit_grams=None, key="x"):
    return {"key": key, "state": state, "food": food, "unit_grams": unit_grams or {}}


def cached(code, name, kcal=100, group="원재료성", source="sample", **others):
    return FoodNutrient(food_code=code, name=name, name_key=foods.food_name_key(name), group_name=group, kcal=kcal,
                        source=source, fetched_at=utcnow(), **others)


TOFU = food("T1", "두부", 84, protein_g=9.3)
SOY = food("S1", "간장", 60, sodium_mg=5000)
ZERO = dict.fromkeys(foods.NUTRIENTS, 0.0)


# --- 순수 함수 ---


def test_match_key():
    assert match_key("돼지고기 앞다리살(국산)") == "돼지고기앞다리살"
    assert match_key("()") == ""


@pytest.mark.parametrize(
    "unit, grams",
    [("g", 1), ("ml", 1), ("G", 1), ("ML", 1), ("큰술", 15), ("컵", 200), ("꼬집", 0.5), ("모", None), ("개", None),
     # Ruling 10: 큰 T로 시작하면 큰술(단 tsp는 대소문자 무관 작은술), 작은 t·ts는 작은술
     ("T", 15), ("Ts", 15), ("TS", 15), ("Tbs", 15), ("Tbsp", 15), ("tbsp", 15), ("TBSP", 15),
     ("t", 5), ("ts", 5), ("tsp", 5), ("TSP", 5), ("Tsp", 5)],
)
def test_fixed_grams(unit, grams):
    assert fixed_grams(unit) == grams


@pytest.mark.parametrize(
    "item, resolved, can_estimate, expected",
    [
        ({"name": "물", "amount": "500ml"}, res("unsearched"), True, {"status": "trace", "values": ZERO, "pending_reason": None}),
        ({"name": "소금", "amount": "약간"}, res("matched", food("N1", "소금", 0)), True, {"status": "trace", "values": ZERO}),
        ({"name": "두부", "amount": "10~15개"}, res("matched", TOFU), True, {"status": "unknown_amount", "values": None, "pending_reason": None}),
        ({"name": "대파", "amount": "1대"}, res("unsearched"), True, {"status": "pending", "pending_reason": "search"}),
        ({"name": "대파", "amount": "1대"}, res("unmatched"), True, {"status": "unmatched", "pending_reason": None, "food": None}),
        ({"name": "대파", "amount": "100g"}, res("estimate_missing"), True,
         {"status": "pending", "pending_reason": "food", "estimate_food": True, "food": None}),
        ({"name": "대파", "amount": "100g"}, res("estimate_missing"), False, {"status": "no_estimate", "pending_reason": None}),
        ({"name": "두부", "amount": "1모"}, res("matched", TOFU), True,
         {"status": "pending", "pending_reason": "weight", "countable": True, "grams": None}),
        ({"name": "두부", "amount": "1모"}, res("matched", TOFU), False, {"status": "needs_weight", "pending_reason": None, "countable": True}),
        ({"name": "두부", "amount": "1모"}, res("matched", TOFU, {"모": (300, "user")}), False,
         {"status": "ok", "grams": 300.0, "unit_grams": 300.0, "unit_grams_source": "user", "kcal_per_serving": 252,
          "food": {"food_code": "T1", "name": "두부", "group": "원재료성", "kcal": 84}, "estimate_food": False}),
        ({"name": "두부", "amount": "1모"}, res("auto", TOFU, {"모": (300, "ai")}), False,
         {"status": "estimated", "grams": 300.0, "unit_grams_source": "ai"}),
        ({"name": "두부", "amount": "1모"}, res("auto", TOFU, {"모": (300, "sample")}), False,
         {"status": "estimated", "grams": 300.0, "unit_grams_source": "sample"}),
        ({"name": "간장", "amount": "2큰술"}, res("matched", SOY), False,
         {"status": "ok", "grams": 30.0, "countable": False, "unit_grams": None, "quantity": 2.0, "unit": "큰술"}),
        ({"name": "김치", "amount": "100g"}, res("estimate", food("ai:김치", "김치", 18, group="추정")), False,
         {"status": "estimated", "food": None, "estimate_food": True, "kcal_per_serving": 18}),
    ],
    ids=["water", "trace-word", "unknown-amount", "unsearched", "unmatched", "estimate-missing-can", "estimate-missing-cannot",
         "weight-missing-can", "weight-missing-cannot", "user-weight", "ai-weight", "sample-weight", "spoon", "estimate"],
)
def test_ingredient_row_statuses(item, resolved, can_estimate, expected):
    row = ingredient_row(item, resolved, can_estimate, 1)
    assert {key: row[key] for key in expected} == expected
    assert (row["name"], row["amount"]) == (item["name"], item["amount"])


def test_recipe_nutrition_mockup_example():
    ingredients = [
        {"name": "돼지고기 앞다리살", "amount": "300g"},
        {"name": "김치", "amount": "1/2포기"},
        {"name": "두부", "amount": "1/2모"},
    ]
    resolved = {
        "돼지고기앞다리살": res("matched", food("P1", "돼지고기 앞다리", 132), key="돼지고기앞다리살"),
        "김치": res("matched", food("K1", "배추김치", 18), {"포기": (1000, "ai")}, key="김치"),
        "두부": res("unmatched", key="두부"),
    }
    result = recipe_nutrition(ingredients, 2, resolved, True)
    assert result["per_serving"]["kcal"] == 243
    assert [row["kcal_per_serving"] for row in result["ingredients"]] == [198, 45, None]
    assert (result["approx"], result["estimated_count"], result["missing_count"], result["usable"], result["pending"]) == (True, 1, 1, True, False)
    assert result["servings"] == 2
    assert all("values" not in row for row in result["ingredients"])


def test_recipe_nutrition_rounding_and_none_nutrients():
    beef = food("B1", "소고기", 100, carbs_g=10, protein_g=5, fat_g=1, sugars_g=None, sodium_mg=100)
    ingredients = [{"name": "소고기", "amount": "100g"}]
    resolved = {"소고기": res("matched", beef, key="소고기")}
    assert recipe_nutrition(ingredients, 3, resolved, True)["per_serving"] == {
        "kcal": 33, "carbs_g": 3.3, "protein_g": 1.7, "fat_g": 0.3, "sugars_g": 0.0, "sodium_mg": 33,
    }
    assert recipe_nutrition(ingredients, 0, resolved, True)["per_serving"]["kcal"] == 100

    missing = recipe_nutrition([{"name": "두부", "amount": "1모"}], 2, {"두부": res("unmatched", key="두부")}, True)
    assert (missing["per_serving"], missing["usable"], missing["missing_count"]) == (None, False, 1)

    trace = recipe_nutrition([{"name": "물", "amount": "1컵"}, {"name": "소금", "amount": "약간"}], 2,
                             {"물": res("unsearched", key="물"), "소금": res("unsearched", key="소금")}, True)
    assert trace["per_serving"] == {"kcal": 0, "carbs_g": 0.0, "protein_g": 0.0, "fat_g": 0.0, "sugars_g": 0.0, "sodium_mg": 0}
    assert (trace["approx"], trace["pending"], trace["usable"], trace["missing_count"]) == (False, False, True, 0)


def test_recipe_nutrition_trace_with_pending_has_no_per_serving():
    result = recipe_nutrition([{"name": "물", "amount": "1컵"}, {"name": "양파", "amount": "1개"}], 1,
                              {"물": res("unsearched", key="물"), "양파": res("unsearched", key="양파")}, True)
    assert (result["per_serving"], result["pending"], result["usable"]) == (None, True, False)


def test_recipe_nutrition_rounds_half_up():
    beef = food("B1", "소고기", 100, sodium_mg=1)
    result = recipe_nutrition([{"name": "소고기", "amount": "261g"}, {"name": "소고기", "amount": "0.25g"}], 2,
                              {"소고기": res("matched", beef, key="소고기")}, True)
    assert [line["grams"] for line in result["ingredients"]] == [261.0, 0.3]
    assert result["per_serving"]["kcal"] == 131  # 261.25 / 2 = 130.625
    assert result["ingredients"][0]["kcal_per_serving"] == 131  # 130.5
    assert result["per_serving"]["sodium_mg"] == 1  # 2.6125 / 2 = 1.30625


def test_recipe_nutrition_empty_key_is_left_out_not_pending():
    result = recipe_nutrition([{"name": "+", "amount": "1개"}, {"name": "(고명)", "amount": "1개"}, {"name": "소금", "amount": "1g"}], 1,
                              {"소금": res("matched", food("N1", "소금", 0, sodium_mg=38000), key="소금")}, True)
    assert [line["status"] for line in result["ingredients"]] == ["unknown_amount", "unknown_amount", "ok"]
    assert [line["key"] for line in result["ingredients"]] == ["", "", "소금"]
    assert (result["pending"], result["approx"], result["missing_count"], result["per_serving"]["sodium_mg"]) == (False, True, 2, 380)


def row(name, group="원재료성"):
    return FoodNutrient(name=name, group_name=group)


def test_auto_match_rules():
    # ① 원재료성 후보가 있으면 이름이 같은 음식보다 먼저, '대파'는 둘째 조각이어도 된다
    green_onion, dish = row("파_대파_생것"), row("대파", "음식")
    assert auto_match("대파", [dish, green_onion]) is green_onion
    # ① '생것' 조각 있음 → 조각 수 → 이름 길이 → 이름 순
    leg, belly, boiled = row("돼지고기_뒷다리_생것"), row("돼지고기_삼겹살_생것"), row("돼지고기_삶은것")
    assert auto_match("돼지고기", [boiled, belly, leg]) is leg
    assert auto_match("돼지고기", [boiled]) is boiled
    # ② 원재료성 없음: normalize(이름) == 키인 행이 딱 하나
    tofu = row("두부", "가공식품")
    assert auto_match("두부", [row("두부_부침용", "음식"), tofu]) is tofu
    # ③ 그 밖은 못 맞춤
    assert auto_match("두부", [row("두부", "가공식품"), row("두부 ", "음식")]) is None
    assert auto_match("두부", [row("두부_부침용", "음식")]) is None
    assert auto_match("두부", []) is None


# --- NutritionContext ---


def make_user(provider_id):
    user = User(provider="test", provider_id=provider_id, nickname="u")
    db.session.add(user)
    db.session.commit()
    return user


def test_context_resolves_match_auto_and_estimates(app):
    with app.app_context():
        me, other = make_user("1"), make_user("2")
        db.session.add_all([
            cached("T1", "두부_부침용", group="원재료성"),
            cached("T2", "두부조림", group="음식"),
            cached("ai:김치", "김치", kcal=18, group="추정", source="ai"),
            cached("ai:두부", "두부", kcal=1, group="추정", source="ai"),
            cached("P1", "돼지고기 가공품", kcal=250, group="가공식품", sodium_mg=500),
            cached("X1", "양파_생것", source="ai"),  # source ai는 자동 맞추기 후보가 아니다
            FoodSearch(query_key="대파", total=0, searched_at=utcnow()),
            FoodSearch(query_key="양배추", total=3, searched_at=utcnow()),
            UnitWeightEstimate(name_key="두부", unit="모", grams=300, source="ai"),
            FoodMatch(user_id=me.id, ingredient_key="김치", food_code=None, unit_grams={}),
            FoodMatch(user_id=me.id, ingredient_key="돼지고기", food_code="P1", unit_grams={"근": 600}),
            FoodMatch(user_id=me.id, ingredient_key="양배추", food_code="GONE", unit_grams={}),
            FoodMatch(user_id=other.id, ingredient_key="양파", food_code="T2", unit_grams={"개": 1}),
        ])
        db.session.commit()
        recipes = [SimpleNamespace(servings=2, ingredients=[{"name": "두부", "amount": "1모"}, {"name": "김치", "amount": "100g"}, {"name": "대파", "amount": "1대"}]),
                   SimpleNamespace(servings=1, ingredients=[{"name": n, "amount": "1개"} for n in ("양파", "돼지고기", "양배추", "물")])]
        context = NutritionContext(me, recipes)
        assert context.can_estimate is True

        tofu = context.resolve("두부")
        assert (tofu["state"], tofu["food"]["food_code"], tofu["unit_grams"]) == ("auto", "T1", {"모": (300, "ai")})
        kimchi = context.resolve("김치")
        assert (kimchi["state"], kimchi["food"]["kcal"]) == ("estimate", 18)
        assert context.resolve("대파")["state"] == "estimate_missing"
        assert (context.resolve("양파")["state"], context.resolve("양파")["unit_grams"]) == ("unsearched", {})
        pork = context.resolve("돼지고기")
        assert (pork["state"], pork["food"]["name"], pork["food"]["sodium_mg"], pork["unit_grams"]) == ("matched", "돼지고기 가공품", 500, {"근": (600, "user")})
        cabbage = context.resolve("양배추")
        assert (cabbage["state"], cabbage["food"]) == ("unmatched", None)

        result = context.recipe(recipes[0])
        assert [r["status"] for r in result["ingredients"]] == ["estimated", "estimated", "pending"]


def test_context_user_weight_beats_shared_estimate(app):
    with app.app_context():
        me = make_user("1")
        db.session.add_all([
            cached("T1", "두부"),
            UnitWeightEstimate(name_key="두부", unit="모", grams=300, source="ai"),
            UnitWeightEstimate(name_key="두부", unit="판", grams=900, source="sample"),
            FoodMatch(user_id=me.id, ingredient_key="두부", food_code="T1", unit_grams={"모": 280}),
        ])
        db.session.commit()
        context = NutritionContext(me, [SimpleNamespace(servings=1, ingredients=[{"name": "두부", "amount": "1모"}])])
        assert context.resolve("두부")["unit_grams"] == {"모": (280, "user"), "판": (900, "sample")}


# --- API ---


def recipe_body(*ingredients, servings=2):
    return {"title": "두부조림", "servings": servings, "ingredients": [{"name": n, "amount": a} for n, a in ingredients]}


def add_foods(app, *rows):
    with app.app_context():
        db.session.add_all(rows)
        db.session.commit()


def test_recipe_nutrition_endpoint(client, raw_client, login, app):
    login()
    add_foods(app, cached("T1", "두부", kcal=84), cached("S1", "간장", kcal=60))
    recipe_id = client.post("/api/recipes", json=recipe_body(("두부", "300g"), ("간장", "2큰술"))).get_json()["id"]

    res = client.get(f"/api/recipes/{recipe_id}/nutrition")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    body = res.get_json()
    assert sorted(body) == sorted(["servings", "per_serving", "approx", "estimated_count", "missing_count", "pending", "usable", "ingredients"])
    assert body["per_serving"]["kcal"] == (252 + 18) / 2
    assert [r["status"] for r in body["ingredients"]] == ["ok", "ok"]
    assert body["ingredients"][0]["food"] == {"food_code": "T1", "name": "두부", "group": "원재료성", "kcal": 84}

    assert raw_client.get(f"/api/recipes/{recipe_id}/nutrition").status_code == 401
    assert client.get("/api/recipes/99999999999/nutrition").status_code == 404

    login("2")
    assert client.get(f"/api/recipes/{recipe_id}/nutrition").status_code == 404

    app.config.update(DEV_MODE=False)
    res = client.get(f"/api/recipes/{recipe_id}/nutrition")
    assert (res.status_code, res.get_json()["error"]) == (503, foods.OFF)
    res = client.put("/api/food-matches", json={"name": "두부", "food_code": None})
    assert (res.status_code, res.get_json()["error"]) == (503, foods.OFF)


def test_put_food_match_and_recompute(client, login, app):
    login()
    add_foods(app, cached("T1", "두부", kcal=84), cached("T2", "순두부", kcal=46))
    recipe_id = client.post("/api/recipes", json=recipe_body(("두부", "1/2모"))).get_json()["id"]
    url = f"/api/recipes/{recipe_id}/nutrition"
    assert client.get(url).get_json()["ingredients"][0]["status"] == "pending"  # 자동 맞춤(두부)은 됐지만 무게를 모른다

    res = client.put("/api/food-matches", json={"name": "두부", "food_code": "T2", "unit": "모", "unit_grams": 280})
    assert res.status_code == 204
    line = client.get(url).get_json()["ingredients"][0]
    assert (line["status"], line["food"]["name"], line["unit_grams"], line["unit_grams_source"], line["grams"]) == ("ok", "순두부", 280.0, "user", 140.0)

    assert client.put("/api/food-matches", json={"name": "두부", "food_code": None}).status_code == 204
    line = client.get(url).get_json()["ingredients"][0]
    assert (line["estimate_food"], line["status"], line["pending_reason"], line["food"]) == (True, "pending", "food", None)
    assert (line["unit_grams"], line["unit_grams_source"]) == (280.0, "user")

    # 단위 무게 지우기(None)
    assert client.put("/api/food-matches", json={"name": "두부 (국산)", "food_code": "T1", "unit": "모", "unit_grams": None}).status_code == 204
    with app.app_context():
        match = FoodMatch.query.one()
        assert (match.ingredient_key, match.food_code, match.unit_grams) == ("두부", "T1", {})


@pytest.mark.parametrize(
    "body, message",
    [
        ({"name": "", "food_code": None}, "재료 이름은 1~50자로 입력해주세요."),
        ({"name": "가" * 51, "food_code": None}, "재료 이름은 1~50자로 입력해주세요."),
        ({"name": "()", "food_code": None}, BAD),
        ({"name": "두부"}, BAD),
        ({"name": "두부", "food_code": "없는코드"}, PICK_AGAIN),
        ({"name": "두부", "food_code": "ai:두부"}, PICK_AGAIN),
        ({"name": "두부", "food_code": 123}, PICK_AGAIN),
        ({"name": "두부", "food_code": "T1", "unit": "g", "unit_grams": 300}, BAD),
        ({"name": "두부", "food_code": "T1", "unit": "큰술", "unit_grams": 300}, BAD),
        ({"name": "두부", "food_code": "T1", "unit": "", "unit_grams": 300}, BAD),
        ({"name": "두부", "food_code": "T1", "unit": "가" * 11, "unit_grams": 300}, BAD),
        ({"name": "두부", "food_code": "T1", "unit": 3, "unit_grams": 300}, BAD),
        ({"name": "두부", "food_code": "T1", "unit": "모", "unit_grams": 0}, WEIGHT_ERROR),
        ({"name": "두부", "food_code": "T1", "unit": "모", "unit_grams": 5000.1}, WEIGHT_ERROR),
        ({"name": "두부", "food_code": "T1", "unit": "모", "unit_grams": True}, WEIGHT_ERROR),
        ({"name": "두부", "food_code": "T1", "unit": "모", "unit_grams": "300"}, WEIGHT_ERROR),
        ([], BAD),
    ],
)
def test_put_food_match_validation(client, login, app, body, message):
    login()
    add_foods(app, cached("T1", "두부"), cached("ai:두부", "두부", source="ai"))
    res = client.put("/api/food-matches", json=body)
    assert (res.status_code, res.get_json()) == (400, {"error": message})
    with app.app_context():
        assert FoodMatch.query.count() == 0


def test_put_food_match_rounds_weight(client, login, app):
    login()
    add_foods(app, cached("T1", "두부"))
    assert client.put("/api/food-matches", json={"name": "두부", "food_code": "T1", "unit": "모", "unit_grams": 280.26}).status_code == 204
    with app.app_context():
        assert FoodMatch.query.one().unit_grams == {"모": 280.3}


def test_put_food_match_cap(client, login, app):
    login()
    with app.app_context():
        user_id = User.query.filter_by(provider_id="1").one().id
        db.session.add_all(FoodMatch(user_id=user_id, ingredient_key=f"재료{i}", food_code=None, unit_grams={}) for i in range(nutrition.MAX_MATCHES))
        db.session.commit()
    res = client.put("/api/food-matches", json={"name": "새재료", "food_code": None})
    assert (res.status_code, res.get_json()) == (400, {"error": "식품은 2000개까지 기억할 수 있어요."})
    assert client.put("/api/food-matches", json={"name": "재료1", "food_code": None}).status_code == 204


def test_put_food_match_unit_cap(client, login, app):
    login()
    add_foods(app, cached("T1", "두부"))
    with app.app_context():
        user_id = User.query.filter_by(provider_id="1").one().id
        db.session.add(FoodMatch(user_id=user_id, ingredient_key="두부", food_code="T1", unit_grams={f"u{i}": 1 for i in range(nutrition.MAX_UNITS)}))
        db.session.commit()
    res = client.put("/api/food-matches", json={"name": "두부", "food_code": "T1", "unit": "모", "unit_grams": 300})
    assert (res.status_code, res.get_json()) == (400, {"error": BAD})
    assert client.put("/api/food-matches", json={"name": "두부", "food_code": "T1", "unit": "u1", "unit_grams": 300}).status_code == 204


def test_context_dedupes_candidates_across_like_batches(app):
    with app.app_context():
        me = make_user("1")
        db.session.add(cached("D1", "대파", group="가공식품"))
        db.session.commit()
        names = ["대파", "파"] + [f"라{i:03d}" for i in range(60)]
        batches = nutrition._chunks(set(names), nutrition.LIKE_CHUNK)
        assert "대파" in batches[0] and "파" in batches[1]  # '%대파%'·'%파%' 두 쿼리 모두 D1을 돌려준다
        context = NutritionContext(me, [SimpleNamespace(servings=1, ingredients=[{"name": n, "amount": "10g"} for n in names])])
        assert len(context.candidates["대파"]) == 1
        assert context.resolve("대파")["state"] == "auto"


def test_context_skips_empty_key(app, monkeypatch):
    with app.app_context():
        me = make_user("1")
        context = NutritionContext(me, [])
        resolved = []
        real = context.resolve
        monkeypatch.setattr(context, "resolve", lambda key: resolved.append(key) or real(key))
        result = context.recipe(SimpleNamespace(servings=1, ingredients=[{"name": "·", "amount": "1개"}, {"name": "양파", "amount": "1개"}]))
        assert resolved == ["양파"]
        assert [line["status"] for line in result["ingredients"]] == ["unknown_amount", "pending"]


def test_context_candidate_lookup_batches_and_escapes(app):
    with app.app_context():
        me = make_user("1")
        db.session.add_all([cached("L1", "재료119_생것"), cached("L2", "100%주스_생것"), cached("L3", "100X주스", group="음식")])
        db.session.commit()
        names = [f"재료{i}" for i in range(120)] + ["100%주스"]
        context = NutritionContext(me, [SimpleNamespace(servings=1, ingredients=[{"name": n, "amount": "1개"} for n in names])])
        assert context.resolve("재료119")["food"]["food_code"] == "L1"
        assert context.resolve("재료1")["state"] == "unsearched"  # '재료119'는 '재료1' LIKE에 걸리지만 조각이 달라 후보가 아니다
        assert context.resolve("100%주스")["food"]["food_code"] == "L2"


def test_candidate_lookup_uses_like_and_skips_remembered_keys(app):
    """C1: 한국어 이름·소문자 키라 ILIKE(lower 비교) 대신 LIKE. 기억이 있는 재료(와 그 여러 낱말 대체 키)는 후보를 찾지 않는다."""
    from sqlalchemy import event

    with app.app_context():
        me = make_user("1")
        db.session.add_all([cached("T1", "두부"), cached("D1", "파_대파_생것"),
                            FoodMatch(user_id=me.id, ingredient_key="두부", food_code="T1", unit_grams={}),
                            FoodMatch(user_id=me.id, ingredient_key="돼지고기앞다리살", food_code=None, unit_grams={})])
        db.session.commit()
        seen = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            if "food_nutrients" in statement and "LIKE" in statement.upper():
                seen.append((statement, str(parameters)))

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            names = ["두부", "돼지고기 앞다리살", "대파"]
            context = NutritionContext(me, [SimpleNamespace(servings=1, ingredients=[{"name": n, "amount": "100g"} for n in names])])
            assert [r["food_code"] for r in foods.search_items("대파")] == ["D1"]
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        assert len(seen) == 2
        for statement, params in seen:
            assert "ILIKE" not in statement.upper() and "lower(" not in statement.lower()
        assert "%대파%" in seen[0][1]
        assert "%두부%" not in seen[0][1] and "돼지고기" not in seen[0][1]
        assert context.resolve("대파")["food"]["food_code"] == "D1"
        assert context.resolve("두부")["state"] == "matched"
