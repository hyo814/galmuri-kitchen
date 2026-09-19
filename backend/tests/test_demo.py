import hashlib
import hmac
import io
import json
import os
from collections import Counter
from datetime import datetime, time, timedelta, timezone

import pytest

from app import ai, auth, cooklog, defaults, demo, meals, outbound, scan, videos
from app.ingredients import SEOUL, seoul_today
from app.models import (
    AiCall,
    CookLog,
    FoodLog,
    Ingredient,
    ItemRule,
    MealPlan,
    MealSlot,
    Recipe,
    Seasoning,
    ShoppingItem,
    ShoppingNote,
    Staple,
    StorageLocation,
    User,
    YoutubeChannel,
    YoutubeVideo,
    db,
    utcnow,
)
from tests.test_shopping_notes import JPEG, add_note, photo_path, upload
from tests.test_videos import make_channel, vid

USER_TABLES = (Ingredient, StorageLocation, ItemRule, Staple, Recipe, Seasoning, ShoppingItem, ShoppingNote, MealPlan, AiCall)


@pytest.fixture
def demo_app(make_app):
    # IP 한도는 설정값(기본 30·100). 테스트는 작게 잡아 경계를 확인한다
    return make_app(DEMO_LOGIN=True, DEV_MODE=False, DEMO_IP_HOURLY_LIMIT=3, DEMO_IP_DAILY_LIMIT=10)


def new_client(app, ip="10.0.0.1"):
    c = app.test_client()
    c.environ_base.update(HTTP_X_REQUESTED_WITH="fetch", REMOTE_ADDR=ip)
    return c


def fail_if_called(*args, **kwargs):
    raise AssertionError("AI·유튜브를 부르면 안 돼요")


def test_demo_login_disabled_is_404(client):
    assert client.post("/api/demo-login").status_code == 404
    assert client.get("/api/auth-options").get_json()["demo_login"] is False


def test_demo_login_requires_fetch_header(demo_app):
    assert demo_app.test_client().post("/api/demo-login").status_code == 400


def test_demo_login_creates_seeded_user_and_session(demo_app):
    c = new_client(demo_app)
    assert c.get("/api/auth-options").get_json()["demo_login"] is True
    me = c.post("/api/demo-login").get_json()
    assert (me["nickname"], me["provider"], me["scan_limit"], me["recipe_limit"]) == ("체험 사용자", "demo", 5, 5)
    assert c.get("/api/me").get_json()["id"] == me["id"]

    items = c.get("/api/ingredients").get_json()
    assert len(items) == len(demo.INGREDIENTS)
    assert {i["location_kind"] for i in items} == {"fridge", "freezer", "room"}
    today = seoul_today()
    expiring = {i["name"]: i["expires_on"] for i in items if i["name"] in ("두부", "대파")}
    assert expiring == {"두부": (today + timedelta(days=1)).isoformat(), "대파": (today + timedelta(days=2)).isoformat()}
    assert len(c.get("/api/recipes").get_json()["items"]) == 2
    assert len(c.get("/api/seasonings").get_json()["items"]) == 1
    # 기본 필수품(2026-09-17) + 체험 전용 간장 1개(대파·달걀은 기본 필수품과 겹쳐 demo.STAPLES에서 뺐다)
    staples = c.get("/api/staples").get_json()
    assert len(staples) == len(defaults.DEFAULT_STAPLES) + 1
    # "가졌던 것만 배너에": 재고와 맞는 기본 필수품(대파·양파·감자·달걀·김치·돼지고기·우유)은 in_stock이라 안 뜨고,
    # 나머지 기본 필수품은 한 번도 없던 것(unstocked)이라 배너에서 빠진다 — 체험 첫 화면은 지금처럼 간장 하나만 떨어짐
    missing = [s["name"] for s in staples if s["status"] == "missing"]
    assert missing == ["간장"]
    assert len(c.get("/api/locations").get_json()) == 3
    assert len(c.get("/api/item-rules").get_json()) > 0
    assert c.get("/api/export/summary").status_code == 200

    with demo_app.app_context():
        user = db.session.get(User, me["id"])
        assert "10.0.0.1" not in user.provider_id  # IP는 해시로만

    assert c.post("/api/logout").status_code == 200
    assert c.get("/api/me").status_code == 401


def test_demo_users_are_isolated(demo_app):
    a, b = new_client(demo_app), new_client(demo_app)
    a_id = a.post("/api/demo-login").get_json()["id"]
    b_id = b.post("/api/demo-login").get_json()["id"]
    assert a_id != b_id
    a_item = a.get("/api/ingredients").get_json()[0]["id"]
    b_ids = {i["id"] for i in b.get("/api/ingredients").get_json()}
    assert a_item not in b_ids
    assert b.delete(f"/api/ingredients/{a_item}").status_code == 404
    assert len(a.get("/api/ingredients").get_json()) == len(demo.INGREDIENTS)


def test_demo_login_seeds_food_logs(demo_app, make_app):
    a, b = new_client(demo_app, "10.0.0.1"), new_client(demo_app, "10.0.0.2")
    a_id = a.post("/api/demo-login").get_json()["id"]
    b_id = b.post("/api/demo-login").get_json()["id"]
    with demo_app.app_context():
        assert FoodLog.query.filter_by(user_id=a_id).count() == len(demo.FOOD_LOGS) == 3
        assert FoodLog.query.filter_by(user_id=b_id).count() == 3
        a_ids = {log.id for log in FoodLog.query.filter_by(user_id=a_id)}
        b_ids = {log.id for log in FoodLog.query.filter_by(user_id=b_id)}
        assert a_ids.isdisjoint(b_ids)  # 다른 체험 계정과 섞이지 않음

    today = seoul_today()
    yesterday = (today - timedelta(days=1)).isoformat()

    # ① 기존 demo_app(DEV_MODE=False, 키 없음 = 영양 off): pending은 값 없이 꺼진다
    body = a.get(f"/api/food-logs?date={yesterday}").get_json()
    by_meal = {log["meal"]: log for log in body["logs"]}
    dinner = by_meal["dinner"]
    assert dinner["title"] == "김치찌개" and dinner["recipe_id"] is not None
    assert (dinner["nutrition"], dinner["nutrition_pending"]) == (None, False)
    assert body["nutrition_pending_recipe_ids"] == []
    lunch = by_meal["lunch"]
    assert (lunch["title"], lunch["place"], lunch["memo"]) == ("제육덮밥", "out", "회사 앞 · 조금 짰어요")

    today_body = a.get(f"/api/food-logs?date={today.isoformat()}").get_json()
    assert [log["title"] for log in today_body["logs"]] == ["토스트"]

    # ② sample 모드(DEV_MODE=True, 키 없음): 캐시에 FoodSearch가 없어 김치찌개는 계산 중으로 남는다
    sample_app = make_app(DEMO_LOGIN=True, DEV_MODE=True, DEMO_IP_HOURLY_LIMIT=3, DEMO_IP_DAILY_LIMIT=10)
    sc = new_client(sample_app)
    sc.post("/api/demo-login")
    sample_body = sc.get(f"/api/food-logs?date={yesterday}").get_json()
    sample_dinner = next(log for log in sample_body["logs"] if log["meal"] == "dinner")
    assert sample_dinner["nutrition_pending"] is True
    assert sample_dinner["recipe_id"] in sample_body["nutrition_pending_recipe_ids"]


def test_demo_login_seeds_cook_diary(demo_app):
    a, b = new_client(demo_app, "10.0.0.1"), new_client(demo_app, "10.0.0.2")
    a_id = a.post("/api/demo-login").get_json()["id"]
    b_id = b.post("/api/demo-login").get_json()["id"]

    logs = a.get("/api/cook-logs").get_json()["items"]
    assert [log["title"] for log in logs] == ["김치찌개", "된장찌개", "김치찌개"]
    first, second = logs[0], logs[1]
    assert (first["saved"], first["rating"], first["memo"]) == (10400, 4, "두부 마저 썼어요")
    assert (second["excluded_count"], second["saved"]) == (2, 14760)

    month = (seoul_today() - timedelta(days=1)).strftime("%Y-%m")  # 애호박은 하루 전에 버린 걸로 들어가 매달 1일엔 지난달 리포트에 있다
    report = a.get(f"/api/cook-report?month={month}").get_json()
    assert "애호박" in report["discarded_names"]

    tubu = next(i for i in a.get("/api/ingredients").get_json() if i["name"] == "두부")
    assert tubu["price"] == 2480
    with demo_app.app_context():
        assert db.session.get(Ingredient, tubu["id"]).price_quantity == 1.0

    recipes = a.get("/api/recipes").get_json()["items"]
    detail = {r["title"]: a.get(f"/api/recipes/{r['id']}").get_json() for r in recipes}
    assert (detail["김치찌개"]["eat_out_price"], detail["김치찌개"]["eat_out_source"]) == (9000, "sample")
    assert (detail["된장찌개"]["eat_out_price"], detail["된장찌개"]["eat_out_source"]) == (8000, "user")

    with demo_app.app_context():
        assert AiCall.query.count() == 0
        assert CookLog.query.filter_by(user_id=a_id).count() == len(demo.COOK_LOGS) == 3
        assert CookLog.query.filter_by(user_id=b_id).count() == 3
        a_ids = {log.id for log in CookLog.query.filter_by(user_id=a_id)}
        b_ids = {log.id for log in CookLog.query.filter_by(user_id=b_id)}
        assert a_ids.isdisjoint(b_ids)  # 다른 체험 계정과 섞이지 않음


def test_demo_seeded_cook_logs_cannot_be_undone(demo_app):
    # 예시 요리 일기는 요리한 날 저녁(서울 19시)에 남긴 것으로 — 체험하기 직후 120초 동안 되돌리기가 받아 주지 않게
    c = new_client(demo_app)
    c.post("/api/demo-login")
    logs = c.get("/api/cook-logs").get_json()["items"]
    assert len(logs) == len(demo.COOK_LOGS)
    for log in logs:
        created = datetime.fromisoformat(log["created_at"])
        assert created.astimezone(SEOUL).replace(tzinfo=None) == datetime.combine(datetime.fromisoformat(log["cooked_on"]).date(), time(19))
        res = c.post(f"/api/cook-logs/{log['id']}/undo")
        assert (res.status_code, res.get_json()["error"]) == (400, "되돌릴 수 있는 시간이 지났어요. 재고는 직접 고쳐주세요.")
    assert len(c.get("/api/cook-logs").get_json()["items"]) == len(demo.COOK_LOGS)


def test_demo_cook_log_whose_19h_is_ahead_still_cannot_be_undone(demo_app, monkeypatch):
    # 오늘 요리한 예시 일기를 19시 전에 만들면 만든 시각(19시)이 미래라 되돌리기 창이 다시 열린다 — 시각에 기대지 않게 하루 뒤 일기로 확인한다
    ahead_log = (-1, "된장찌개", 2, 4, None, [("두부", 0.5, "모", 2480, 1, None)], [])
    monkeypatch.setattr(demo, "COOK_LOGS", [ahead_log, *demo.COOK_LOGS])
    c = new_client(demo_app)
    c.post("/api/demo-login")
    logs = c.get("/api/cook-logs").get_json()["items"]
    assert len(logs) == 4
    closed = utcnow() - timedelta(seconds=cooklog.UNDO_SECONDS)
    for log in logs:
        assert datetime.fromisoformat(log["created_at"]) < closed
        assert c.post(f"/api/cook-logs/{log['id']}/undo").status_code == 400
    assert len(c.get("/api/cook-logs").get_json()["items"]) == 4


def test_demo_login_seeds_shopping_list(demo_app):
    c = new_client(demo_app)
    c.post("/api/demo-login")
    body = c.get("/api/shopping").get_json()
    items, stocked, notes = body["items"], body["stocked"], body["notes"]
    assert len(items) == len(demo.SHOPPING_ITEMS) == 7
    assert len(stocked) == 1
    assert len(notes) == 1

    by_name = {i["name"]: i for i in items}
    assert (by_name["두부"]["source"], by_name["두부"]["source_label"]) == ("recipe", "된장찌개")
    assert (by_name["청양고추"]["source"], by_name["청양고추"]["source_label"]) == ("recipe", "된장찌개")
    assert by_name["대파"]["source"] == "urgent"
    assert (by_name["계란"]["source"], by_name["간장"]["source"]) == ("staple", "staple")
    assert by_name["두부"]["location_name"] == "냉장실"
    assert by_name["수세미"]["household"] is True and by_name["수세미"]["location_id"] is None

    checked = {i["name"] for i in items if i["done_at"]}
    assert checked == {"대파", "우유"}
    for i in items:
        assert (i["done_at"] is not None) == (i["done_changed_at"] is not None)

    today = seoul_today().isoformat()
    this_week = (seoul_today() + timedelta(days=3)).isoformat()
    assert {i["name"] for i in items if i["planned_on"] == today} == {"두부", "대파", "청양고추"}
    assert {i["name"] for i in items if i["planned_on"] == this_week} == {"계란", "우유", "수세미"}
    assert {i["name"] for i in items if i["planned_on"] is None} == {"간장"}

    assert stocked[0]["name"] == "양파" and stocked[0]["stocked_at"] is not None

    assert notes[0]["place"] == "이마트 성수점"
    assert "두부 2+1" in notes[0]["body"]
    assert notes[0]["photos"] == []


def test_demo_users_shopping_is_isolated(demo_app):
    a, b = new_client(demo_app), new_client(demo_app)
    a_id = a.post("/api/demo-login").get_json()["id"]
    b_id = b.post("/api/demo-login").get_json()["id"]
    a_ids = {i["id"] for i in a.get("/api/shopping").get_json()["items"]}
    b_item = b.get("/api/shopping").get_json()["items"][0]
    assert b_item["id"] not in a_ids
    assert a.delete(f"/api/shopping/items/{b_item['id']}").status_code == 404
    with demo_app.app_context():
        assert ShoppingItem.query.filter_by(user_id=a_id).count() == len(demo.SHOPPING_ITEMS) + 1
        assert ShoppingItem.query.filter_by(user_id=b_id).count() == len(demo.SHOPPING_ITEMS) + 1
        assert ShoppingNote.query.filter_by(user_id=a_id).count() == 1
        assert ShoppingNote.query.filter_by(user_id=b_id).count() == 1


def test_demo_login_creates_meal_plan(demo_app):
    c = new_client(demo_app)
    me = c.post("/api/demo-login").get_json()
    today = seoul_today()

    def day(n):
        return (today + timedelta(days=n)).isoformat()

    plans = c.get("/api/meal-plans").get_json()["items"]
    assert len(plans) == 1
    summary = plans[0]
    assert summary["name"] == demo.default_plan_name(today, demo.MEAL_PLAN_DAYS)
    assert (summary["start_on"], summary["days"], summary["default_servings"]) == (today.isoformat(), demo.MEAL_PLAN_DAYS, demo.MEAL_PLAN_SERVINGS)
    assert summary["filled"] == len(demo.MEAL_PLAN_SLOTS) == 11

    plan = c.get(f"/api/meal-plans/{summary['id']}").get_json()
    slots = {(s["date"], s["meal"]): s for s in plan["slots"]}
    assert len(slots) == 11
    # 주 보기에 빈 날이 없다: 저녁은 매일, 점심은 사흘, 아침은 하루, 간식은 없다(AI 초안이 채울 빈 칸이 남게)
    assert Counter(meal for _, meal in slots) == {"dinner": 7, "lunch": 3, "breakfast": 1}
    assert {date for date, meal in slots if meal == "dinner"} == {day(n) for n in range(demo.MEAL_PLAN_DAYS)}
    # 오늘 저녁은 레시피 칸 — 먹었어요·요리했어요를 바로 눌러 볼 수 있다. 오늘 아침은 먹은 기록(토스트)과 겹치지 않게 비운다
    assert (slots[(day(0), "dinner")]["title"], slots[(day(0), "dinner")]["recipe_id"] is not None) == ("된장찌개", True)
    assert [meal for date, meal in slots if date == day(0)] == ["dinner"]
    assert (slots[(day(1), "lunch")]["title"], slots[(day(1), "lunch")]["recipe_id"] is not None) == ("김치찌개", True)
    breakfast = slots[(day(1), "breakfast")]
    assert (breakfast["title"], breakfast["recipe_id"], breakfast["servings"]) == ("토스트", None, demo.MEAL_PLAN_SERVINGS)
    # 마지막 날 저녁 된장찌개만 일부러 3인분(장보기 미리보기에 체크된 줄이 생기게). 오늘 저녁은 요리했어요 E2E가 쓰는 2인분 그대로
    assert {key: slot["servings"] for key, slot in slots.items() if slot["servings"] != demo.MEAL_PLAN_SERVINGS} == {(day(6), "dinner"): 3}
    assert (slots[(day(6), "dinner")]["title"], slots[(day(0), "dinner")]["servings"]) == ("된장찌개", 2)

    # 예시 레시피 둘을 쓰되 같은 레시피를 같은 날·이어진 날에 두지 않는다
    recipe_days = {}
    for (date, _), slot in slots.items():
        if slot["recipe_id"] is not None:
            recipe_days.setdefault(slot["title"], []).append(datetime.fromisoformat(date))
    assert set(recipe_days) == {"된장찌개", "김치찌개"}
    for days in recipe_days.values():
        days.sort()
        assert all((later - earlier).days >= 2 for earlier, later in zip(days, days[1:]))

    # 직접 쓰기 칸은 AI 초안 칸처럼 1인분 kcal(est_kcal)을 갖고 영양으로 보인다(영양 계산이 꺼진 서버에서도). 레시피 칸은 계산에 맡긴다
    direct = [slot for slot in slots.values() if slot["recipe_id"] is None]
    assert len(direct) == 6 and len({slot["title"] for slot in direct}) == 6
    for slot in direct:
        assert 1 <= slot["est_kcal"] <= 3000
        assert (slot["nutrition"]["kcal"], slot["nutrition"]["approx"], slot["nutrition"]["source"]) == (slot["est_kcal"], True, "ai")
    assert all(slot["est_kcal"] is None for slot in slots.values() if slot["recipe_id"] is not None)

    with demo_app.app_context():
        assert MealSlot.query.join(MealPlan).filter(MealPlan.user_id == me["id"]).count() == len(demo.MEAL_PLAN_SLOTS)


def test_demo_meal_plan_shopping_preview_starts_with_one_checked_row(demo_app):
    # 애호박 재고는 ½개라(된장찌개 ⅓개 × 1 + 1 + 1.5인분 배율 = 1.17개) 체크된 줄 하나로 시작한다(0개 담기로 시작하지 않게).
    # 재고에 없는 숟가락 양 재료는 양념 묶음(담으면 1개, 필요 양은 인분 배율을 곱해 더한 값) — 운영에서 네 줄이 `단위가 달라요`에 섞여 있었다
    c = new_client(demo_app)
    c.post("/api/demo-login")
    plan_id = c.get("/api/meal-plans").get_json()["items"][0]["id"]
    body = c.get(f"/api/meal-plans/{plan_id}/shopping-preview").get_json()
    assert body["recipe_slot_count"] == 5
    assert body["manual"] == []
    assert [(row["name"], row["quantity"], row["unit"], row["need"], row["have"], row["planned_on"]) for row in body["buy"]] == [
        ("애호박", 1, "개", [{"quantity": 1.17, "unit": "개"}], [{"quantity": 0.5, "unit": "개"}], seoul_today().isoformat()),
    ]
    spoon = lambda value, unit: ([{"quantity": value, "unit": unit}], [])  # noqa: E731
    assert {row["name"]: (row["quantity"], row["unit"], row["need"], row["have"]) for row in body["seasoning"]} == {
        name: (1, "개", [], []) for name in ("된장", "다진 마늘", "고춧가루", "식용유")
    }
    assert {row["name"]: (row["need_spoon"], row["need_extra"]) for row in body["seasoning"]} == {
        "된장": spoon(7, "큰술"),  # 2큰술 × 2·2·3인분(레시피 2인분)
        "다진 마늘": spoon(5.5, "작은술"),  # 된장찌개 셋 + 김치찌개 둘
        "고춧가루": spoon(2, "큰술"),
        "식용유": spoon(2, "큰술"),
    }
    assert {row["name"]: row["reason"] for row in body["skip"]} == {
        "두부": "listed", "대파": "listed", "청양고추": "listed",
        "감자": "enough", "양파": "enough", "김치": "enough", "돼지고기": "enough",
    }


def test_demo_meal_plan_shopping_still_has_checked_row_after_midnight(demo_app, monkeypatch):
    # 체험 계정은 24시간 산다 — 자정을 넘겨 오늘 저녁 칸이 빠져도(⅓ × 1 + 1.5 = 0.83개 > 재고 ½개) 체크된 줄이 남는다
    c = new_client(demo_app)
    c.post("/api/demo-login")
    plan_id = c.get("/api/meal-plans").get_json()["items"][0]["id"]
    tomorrow = seoul_today() + timedelta(days=1)
    monkeypatch.setattr(meals, "seoul_today", lambda: tomorrow)
    body = c.get(f"/api/meal-plans/{plan_id}/shopping-preview").get_json()
    assert (body["start_on"], body["recipe_slot_count"]) == (tomorrow.isoformat(), 4)
    assert [(row["name"], row["quantity"], row["need"], row["planned_on"]) for row in body["buy"]] == [
        ("애호박", 1, [{"quantity": 0.83, "unit": "개"}], tomorrow.isoformat()),
    ]


def test_demo_users_meal_plan_is_isolated(demo_app):
    a, b = new_client(demo_app), new_client(demo_app)
    a_id = a.post("/api/demo-login").get_json()["id"]
    b_id = b.post("/api/demo-login").get_json()["id"]
    a_plan_id = a.get("/api/meal-plans").get_json()["items"][0]["id"]
    assert b.get(f"/api/meal-plans/{a_plan_id}").status_code == 404
    with demo_app.app_context():
        assert MealPlan.query.filter_by(user_id=a_id).count() == 1
        assert MealPlan.query.filter_by(user_id=b_id).count() == 1


def test_demo_ai_limits_are_lower(demo_app, monkeypatch):
    c = new_client(demo_app)
    user_id = c.post("/api/demo-login").get_json()["id"]
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", AI_DAILY_RECIPE_LIMIT=10, AI_DAILY_SCAN_LIMIT=10)
    assert c.get("/api/ai-usage").get_json() == {"scan": {"used": 0, "limit": 5}, "recipe": {"used": 0, "limit": 5}}

    fixed_today = seoul_today()
    fixed_now = datetime.combine(fixed_today, time(12), tzinfo=SEOUL).astimezone(timezone.utc)
    monkeypatch.setattr(scan, "seoul_today", lambda: fixed_today)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    monkeypatch.setattr(ai, "suggest_recipes", lambda *args: pytest.fail("AI를 부르면 안 돼요"))
    with demo_app.app_context():
        db.session.add_all(AiCall(user_id=user_id, kind="recipe", created_at=fixed_now - timedelta(hours=i + 1)) for i in range(5))
        db.session.commit()
    res = c.post("/api/recommendations/ai")
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 AI 레시피는 5번까지 쓸 수 있어요. 내일 다시 써주세요."})


def use_demo_budget(app, count):
    with app.app_context():
        db.session.add_all(AiCall(user_id=None, demo=True, kind="fridge", created_at=utcnow()) for _ in range(count))
        db.session.commit()


def test_demo_ai_global_budget_falls_back_to_sample(demo_app, monkeypatch):
    c = new_client(demo_app)
    c.post("/api/demo-login")
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", DEMO_AI_GLOBAL_DAILY=5)
    assert c.get("/api/me").get_json()["scan"] == "on"
    for name in ("extract", "suggest_recipes", "extract_recipe"):
        monkeypatch.setattr(ai, name, fail_if_called)
    use_demo_budget(demo_app, 4)
    with demo_app.app_context():  # 일반 사용자 호출·24시간 넘은 호출은 체험 예산에 세지 않는다
        db.session.add(AiCall(user_id=None, demo=False, kind="recipe", created_at=utcnow()))
        db.session.add(AiCall(user_id=None, demo=True, kind="recipe", created_at=utcnow() - timedelta(hours=25)))
        db.session.commit()
    assert c.get("/api/me").get_json()["scan"] == "on"
    use_demo_budget(demo_app, 1)
    assert c.get("/api/me").get_json()["scan"] == "sample"

    scan_res = c.post("/api/scan?kind=receipt", data={"image": (io.BytesIO(b"\xff\xd8\xff" + b"jpeg"), "a.jpg", "image/jpeg")})
    assert scan_res.status_code == 200 and scan_res.get_json()["sample"] is True
    recipes = c.post("/api/recommendations/ai")
    assert recipes.status_code == 200 and recipes.get_json()["sample"] is True
    imported = c.post("/api/recipes/import", json={"text": "두부 1모를 썰어 대파와 함께 간장에 조려요. " * 3})
    assert imported.status_code == 200 and imported.get_json()["sample"] is True


def test_demo_budget_counts_eat_out_calls(demo_app):
    c = new_client(demo_app)
    user_id = c.post("/api/demo-login").get_json()["id"]
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", DEMO_AI_GLOBAL_DAILY=1)
    with demo_app.app_context():
        db.session.add(AiCall(user_id=user_id, demo=True, kind="eat_out", created_at=utcnow()))
        db.session.commit()
        assert ai.scan_mode(db.session.get(User, user_id)) == "sample"


def test_nutrition_calls_do_not_spend_demo_ai_budget(demo_app):
    c = new_client(demo_app)
    user_id = c.post("/api/demo-login").get_json()["id"]
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", DEMO_AI_GLOBAL_DAILY=1)
    with demo_app.app_context():
        db.session.add(AiCall(user_id=user_id, demo=True, kind="nutrition", created_at=utcnow()))
        db.session.commit()
        assert ai.scan_mode(db.session.get(User, user_id)) == "on"  # 영양 추정은 따로 센다(Ruling 11)


def test_normal_user_ignores_demo_budget(client, login, app, fake_anthropic):
    login()
    app.config.update(ANTHROPIC_API_KEY="test-key", DEMO_AI_GLOBAL_DAILY=1)
    use_demo_budget(app, 3)
    assert client.get("/api/me").get_json()["scan"] == "on"


USER_BUDGET_FULL = "오늘 준비한 AI 사용량이 모두 찼어요. 조금 뒤에 다시 써주세요."


def use_user_budget(app, count, kind="fridge", demo=False, hours_ago=0):
    with app.app_context():
        at = utcnow() - timedelta(hours=hours_ago)
        db.session.add_all(AiCall(user_id=None, demo=demo, kind=kind, created_at=at) for _ in range(count))
        db.session.commit()


def test_user_ai_global_budget_blocks_logged_in_users(client, login, app, monkeypatch):
    login()
    app.config.update(ANTHROPIC_API_KEY="test-key", USER_AI_GLOBAL_DAILY=3)
    for name in ("extract", "extract_recipe"):
        monkeypatch.setattr(ai, name, fail_if_called)
    use_user_budget(app, 1, kind="nutrition")  # 영양 추정·사 먹으면 얼마도 Claude 비용이라 센다
    use_user_budget(app, 1, kind="eat_out")
    use_user_budget(app, 5, kind="link_fetch")  # 외부 요청 기록(AI 아님)은 안 셈
    use_user_budget(app, 5, hours_ago=25)  # 24시간 넘은 호출은 안 셈
    use_user_budget(app, 5, kind="recipe", demo=True)  # 체험 계정 호출은 체험 예산에만 센다
    with app.app_context():
        assert ai.user_ai_budget_spent() is False
    use_user_budget(app, 1, kind="recipe")
    with app.app_context():
        assert ai.user_ai_budget_spent() is True

    res = client.post("/api/scan?kind=receipt", data={"image": (io.BytesIO(b"\xff\xd8\xff" + b"jpeg"), "a.jpg", "image/jpeg")})
    assert (res.status_code, res.get_json()) == (429, {"error": USER_BUDGET_FULL})
    res = client.post("/api/recipes/import", json={"text": "두부 1모를 썰어 대파와 함께 간장에 조려요. " * 3})
    assert (res.status_code, res.get_json()) == (429, {"error": USER_BUDGET_FULL})
    with app.app_context():
        assert AiCall.query.filter(AiCall.created_at >= utcnow() - timedelta(hours=1)).count() == 13  # 막힌 요청은 기록하지 않는다


def test_user_ai_global_budget_blocks_link_import_before_fetch(client, login, app, monkeypatch):
    login()
    app.config.update(ANTHROPIC_API_KEY="test-key", USER_AI_GLOBAL_DAILY=1)
    for name in ("web_page", "page_images", "video_snippet", "instagram_post"):
        monkeypatch.setattr(outbound, name, fail_if_called)  # 예산을 다 썼으면 링크 주소에 요청하지 않는다
    monkeypatch.setattr(ai, "extract_recipe", fail_if_called)
    use_user_budget(app, 1, kind="link")
    res = client.post("/api/recipes/import", json={"url": "https://blog.example.com/tofu"})
    assert (res.status_code, res.get_json()) == (429, {"error": USER_BUDGET_FULL})
    with app.app_context():
        assert AiCall.query.filter_by(kind="link_fetch").count() == 0


def test_demo_user_ignores_user_ai_global_budget(demo_app, monkeypatch):
    c = new_client(demo_app)
    c.post("/api/demo-login")
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", USER_AI_GLOBAL_DAILY=1)
    use_user_budget(demo_app, 3)
    usage = {"model": "m", "input_tokens": 1, "output_tokens": 1}
    monkeypatch.setattr(ai, "extract", lambda *args, **kwargs: ({"items": [], "purchased_on": None}, usage))
    res = c.post("/api/scan?kind=receipt", data={"image": (io.BytesIO(b"\xff\xd8\xff" + b"jpeg"), "a.jpg", "image/jpeg")})
    assert (res.status_code, res.get_json()["sample"]) == (200, False)


def test_demo_ai_calls_are_marked_demo(demo_app, monkeypatch):
    c = new_client(demo_app)
    c.post("/api/demo-login")
    demo_app.config["ANTHROPIC_API_KEY"] = "test-key"
    usage = {"model": "m", "input_tokens": 1, "output_tokens": 1}
    monkeypatch.setattr(ai, "suggest_recipes", lambda *args: ({"recipes": ai.SAMPLE_SUGGESTIONS}, usage))
    monkeypatch.setattr(outbound, "web_page", fail_if_called)
    assert c.post("/api/recommendations/ai").status_code == 200
    with demo_app.app_context():
        assert [(a.kind, a.demo) for a in AiCall.query.all()] == [("recipe", True)]


STORED_SCANS = {
    "ereceipt": {"kind": "receipt", "items": [{"name": "애호박", "quantity": 1, "unit": "개", "location_kind": "fridge", "price": 1580}], "purchased_on": "2026-08-18"},
    "fridge": {"kind": "fridge", "items": [{"name": "달걀", "quantity": 12, "unit": "개", "location_kind": "fridge", "price": None}], "purchased_on": None},
    "order": {"kind": "order", "items": [], "purchased_on": None},  # 모르는 id는 무시한다
}


@pytest.fixture
def stored_scans(tmp_path, monkeypatch):
    path = tmp_path / "sample_scans.json"
    path.write_text(json.dumps(STORED_SCANS, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ai, "SAMPLE_SCANS_FILE", path)


def scan_photo(c, kind, sample=None):
    data = {"image": (io.BytesIO(b"\xff\xd8\xff" + b"jpeg"), "a.jpg", "image/jpeg")}
    if sample:
        data["sample"] = sample
    return c.post(f"/api/scan?kind={kind}", data=data)


def test_demo_sample_photo_in_sample_mode_returns_stored_result(demo_app, stored_scans, monkeypatch):
    c = new_client(demo_app)
    assert c.post("/api/demo-login").get_json()["scan_samples"] == []  # 키 없는 운영(off)이면 숨긴다
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", DEMO_AI_GLOBAL_DAILY=1)
    use_demo_budget(demo_app, 1)
    monkeypatch.setattr(ai, "extract", fail_if_called)
    assert c.get("/api/me").get_json()["scan_samples"] == ["ereceipt", "fridge"]
    res = scan_photo(c, "receipt", "ereceipt").get_json()
    assert res == {**{k: v for k, v in STORED_SCANS["ereceipt"].items() if k != "kind"}, "sample": True}
    assert scan_photo(c, "fridge", "fridge").get_json()["items"][0]["name"] == "달걀"
    # 모르는 id·종류가 다른 id·파일 없음은 일반 예시 결과
    generic = [row[0] for row in ai.SAMPLES["receipt"]]
    for sample in ("receipt", "../x", "fridge"):
        assert [i["name"] for i in scan_photo(c, "receipt", sample).get_json()["items"]] == generic
    monkeypatch.setattr(ai, "SAMPLE_SCANS_FILE", ai.SAMPLE_SCANS_FILE.with_name("missing.json"))
    assert [i["name"] for i in scan_photo(c, "receipt", "ereceipt").get_json()["items"]] == generic
    assert c.get("/api/me").get_json()["scan_samples"] == []
    with demo_app.app_context():
        assert AiCall.query.count() == 1  # use_demo_budget만 — 예시 결과는 세지 않는다


def test_demo_sample_photo_in_real_mode_calls_ai_and_counts(demo_app, stored_scans, monkeypatch):
    c = new_client(demo_app)
    c.post("/api/demo-login")
    demo_app.config["ANTHROPIC_API_KEY"] = "test-key"
    seen = []

    def fake_extract(kind, images, locations=()):
        seen.append(kind)
        return {"items": [{"name": "고등어", "quantity": 1, "unit": "팩", "location_kind": "fridge", "price": 24980}], "purchased_on": None}, {
            "model": "m", "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(ai, "extract", fake_extract)
    res = scan_photo(c, "receipt", "ereceipt").get_json()
    assert (res["sample"], [i["name"] for i in res["items"]], seen) == (False, ["고등어"], ["receipt"])
    assert c.get("/api/ai-usage").get_json()["scan"] == {"used": 1, "limit": 5}
    with demo_app.app_context():
        assert [(a.kind, a.demo) for a in AiCall.query.all()] == [("receipt", True)]


def test_non_demo_user_sample_field_is_ignored(client, login, stored_scans, monkeypatch):
    login()
    monkeypatch.setattr(ai, "extract", fail_if_called)
    assert client.get("/api/me").get_json()["scan_samples"] == []
    res = scan_photo(client, "receipt", "ereceipt").get_json()  # 개발 모드 키 없음 = 예시 결과
    assert [i["name"] for i in res["items"]] == [row[0] for row in ai.SAMPLES["receipt"]]


def test_sample_scans_file_is_read_again_only_when_it_changes(tmp_path, monkeypatch):
    path = tmp_path / "sample_scans.json"
    monkeypatch.setattr(ai, "SAMPLE_SCANS_FILE", path)
    assert ai.sample_scans() == {}  # 파일 없음
    path.write_text(json.dumps({"fridge": STORED_SCANS["fridge"]}), encoding="utf-8")
    ai.sample_scans().clear()  # 부른 쪽이 바꿔도 기억한 값은 그대로
    hits = ai._read_sample_scans.cache_info().hits
    assert ai.sample_scans() == {"fridge": STORED_SCANS["fridge"]}
    assert ai._read_sample_scans.cache_info().hits == hits + 1  # 파일을 다시 읽지 않았다
    path.write_text(json.dumps(STORED_SCANS), encoding="utf-8")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))  # 같은 순간에 고쳐도 시각이 달라지게
    assert sorted(ai.sample_scans()) == ["ereceipt", "fridge"]  # 서버를 다시 켜지 않아도 새 내용


def test_demo_videos_are_sample_even_with_key(demo_app):
    demo_app.config["YOUTUBE_API_KEY"] = "k"
    c = new_client(demo_app)
    assert c.post("/api/demo-login").get_json()["videos"] == "sample"
    body = c.get("/api/videos").get_json()
    assert body["sample"] is True
    assert c.get("/api/channels").get_json()["sample"] is True
    assert c.post("/api/channels", json={"url": "https://www.youtube.com/@cook"}).status_code == 503
    with demo_app.app_context():
        assert AiCall.query.count() == 0


def test_demo_reads_cached_default_channel_videos_without_refresh(demo_app, monkeypatch):
    demo_app.config["YOUTUBE_API_KEY"] = "k"
    default = make_channel(
        demo_app,
        "D",
        default=True,
        fetched_ago=timedelta(hours=7),  # 일반 사용자라면 새로 받을 만큼 오래됨 — 체험 계정은 그래도 새로 받지 않는다
        videos_=[("v1", 1, "제육볶음 황금레시피"), ("v2", 2, "두부조림")],
    )
    other = make_channel(demo_app, "O", videos_=[("o1", 1, "안 보이는 채널 영상")])  # 기본 채널이 아니라 체험 계정에는 안 보임
    with demo_app.app_context():
        db.session.add(
            YoutubeVideo(
                video_id=vid("old"),
                channel_id=default,
                title="30일 넘어 캐시에서 빠진 제육 영상",  # 제목·설명 모두 검색어에 걸려도 검색 결과에서 빠진다
                description="제육 양념",
                published_at=utcnow() - timedelta(days=40),
                fetched_at=utcnow() - videos.KEEP_FOR - timedelta(days=1),
            )
        )
        db.session.commit()
        channel_fetched_at = db.session.get(YoutubeChannel, default).fetched_at
        other_video_id = YoutubeVideo.query.filter_by(channel_id=other).one().id

    for name in ("channel_info", "playlist_videos", "video_details"):
        monkeypatch.setattr(outbound, name, fail_if_called)
    monkeypatch.setattr(videos, "refresh_stale", fail_if_called)  # 목록 첫 페이지에서도 새로 받지 않음을 못박는다

    c = new_client(demo_app)
    assert c.post("/api/demo-login").get_json()["videos"] == "cached"

    body = c.get("/api/videos").get_json()
    assert body["sample"] is False
    assert {v["title"] for v in body["items"]} == {"제육볶음 황금레시피", "두부조림"}

    q_body = c.get("/api/videos?q=제육").get_json()
    assert [v["title"] for v in q_body["items"]] == ["제육볶음 황금레시피"]

    visible_id = next(v["id"] for v in body["items"] if v["title"] == "제육볶음 황금레시피")
    assert c.get(f"/api/videos/{visible_id}").status_code == 200
    assert c.get(f"/api/videos/{other_video_id}").status_code == 404

    channels_body = c.get("/api/channels").get_json()
    assert channels_body["sample"] is False
    assert [ch["id"] for ch in channels_body["items"]] == [default]

    assert c.post("/api/channels", json={"url": "https://www.youtube.com/@cook"}).status_code == 503
    assert c.patch(f"/api/channels/{default}", json={"hidden": True}).status_code == 503
    assert c.delete(f"/api/channels/{default}").status_code == 503

    with demo_app.app_context():
        assert YoutubeVideo.query.filter_by(video_id=vid("old")).count() == 1  # 체험 계정 요청으로는 지우지 않는다
        assert db.session.get(YoutubeChannel, default).fetched_at == channel_fetched_at  # 새로 받지 않아 그대로
        assert AiCall.query.count() == 0


def test_demo_video_import_calls_youtube_only_within_demo_ai_limit(demo_app, monkeypatch):
    # 체험 계정이 실제 영상에서 `레시피로 가져오기`를 누르면 링크 가져오기와 같은 길: AI 레시피 한도 검사를 먼저 통과해야
    # videos.list(1 unit)를 부른다. 하루 한도(DEMO_AI_DAILY_LIMIT)를 다 쓰면 429이고 유튜브는 부르지 않는다
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", YOUTUBE_API_KEY="k", AI_SCAN_BURST_LIMIT=100)  # 60초 연속 한도(기본 3)는 따로 막는다
    c = new_client(demo_app)
    c.post("/api/demo-login")
    fetched = []

    def snippet(video_id, key):
        fetched.append(video_id)
        return {"title": "제육볶음 황금레시피", "description": "돼지고기 600g, 양파 1개를 볶아요. " * 3, "channel_title": "집밥 연구소", "thumbnail_url": None}

    recipe = {"title": "제육볶음", "servings": 2, "ingredients": [{"name": "돼지고기", "amount": "600g"}], "steps": ["볶아요."]}
    monkeypatch.setattr(outbound, "video_snippet", snippet)
    monkeypatch.setattr(ai, "extract_recipe", lambda text, images: ({"found": True, "recipes": [recipe]}, {"model": "m", "input_tokens": 1, "output_tokens": 1}))
    url = {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    for _ in range(auth.DEMO_AI_DAILY_LIMIT):
        assert c.post("/api/recipes/import", json=url).status_code == 200
    blocked = c.post("/api/recipes/import", json=url)
    assert (blocked.status_code, blocked.get_json()["error"]) == (429, f"오늘 AI 레시피는 {auth.DEMO_AI_DAILY_LIMIT}번까지 쓸 수 있어요. 내일 다시 써주세요.")
    assert len(fetched) == auth.DEMO_AI_DAILY_LIMIT


def test_demo_gets_sample_when_cached_default_videos_are_too_old(demo_app):
    demo_app.config["YOUTUBE_API_KEY"] = "k"
    default = make_channel(demo_app, "D", default=True, videos_=[("old", 1, "오래된 영상")])
    with demo_app.app_context():
        video = YoutubeVideo.query.filter_by(channel_id=default).one()
        video.fetched_at = utcnow() - videos.KEEP_FOR - timedelta(days=1)
        db.session.commit()
    c = new_client(demo_app)
    assert c.post("/api/demo-login").get_json()["videos"] == "sample"


def test_login_required_checks_provider_id(client, login, app):
    user = login()
    assert client.get("/api/me").status_code == 200
    with client.session_transaction() as s:
        s["pid"] = "someone-else"
    assert client.get("/api/me").status_code == 401
    with client.session_transaction() as s:
        s.pop("pid")
        s["user_id"] = user.id
    assert client.get("/api/me").status_code == 401


def test_normal_user_limits_unchanged(client, login, app):
    login()
    assert client.get("/api/me").get_json()["recipe_limit"] == app.config["AI_DAILY_RECIPE_LIMIT"]


TOO_MANY = (429, {"error": "지금 같은 인터넷으로 체험하는 분이 많아요. 잠시 뒤 다시 누르거나 카카오·네이버로 로그인해주세요."})


def age_demo_users(app, **delta):
    with app.app_context():
        User.query.filter_by(provider="demo").update({"created_at": utcnow() - timedelta(**delta)})
        db.session.commit()


def test_demo_login_per_ip_hourly_and_daily_limit(demo_app):
    same = new_client(demo_app, "10.0.0.7")
    for _ in range(3):
        assert same.post("/api/demo-login").status_code == 200
    res = same.post("/api/demo-login")
    assert (res.status_code, res.get_json()) == TOO_MANY
    assert new_client(demo_app, "10.0.0.8").post("/api/demo-login").status_code == 200

    for batch in (3, 3, 1):  # 한 시간마다 3개씩, 24시간에 10개까지
        age_demo_users(demo_app, minutes=61)
        for _ in range(batch):
            assert same.post("/api/demo-login").status_code == 200
    age_demo_users(demo_app, minutes=61)
    res = same.post("/api/demo-login")
    assert (res.status_code, res.get_json()) == TOO_MANY
    age_demo_users(demo_app, hours=25)  # 하루 지나면(만료 계정도 지워지고) 다시 된다
    assert same.post("/api/demo-login").status_code == 200


def test_demo_ip_limits_come_from_env(make_app, monkeypatch):
    monkeypatch.delenv("DEMO_IP_HOURLY_LIMIT", raising=False)
    monkeypatch.delenv("DEMO_IP_DAILY_LIMIT", raising=False)
    app = make_app(DEMO_LOGIN=True, DEV_MODE=False)
    assert (app.config["DEMO_IP_HOURLY_LIMIT"], app.config["DEMO_IP_DAILY_LIMIT"]) == (30, 100)  # 한 사무실 주소 뒤 여러 심사위원
    assert [new_client(app, "10.0.0.7").post("/api/demo-login").status_code for _ in range(4)] == [200] * 4
    monkeypatch.setenv("DEMO_IP_HOURLY_LIMIT", "1")
    monkeypatch.setenv("DEMO_IP_DAILY_LIMIT", "2")
    app = make_app(DEMO_LOGIN=True, DEV_MODE=False)
    assert (app.config["DEMO_IP_HOURLY_LIMIT"], app.config["DEMO_IP_DAILY_LIMIT"]) == (1, 2)
    assert [new_client(app, "10.0.0.7").post("/api/demo-login").status_code for _ in range(2)] == [200, 429]


def test_ipv6_is_limited_per_64(demo_app):
    for suffix in ("1", "2", "ffff:1"):
        assert new_client(demo_app, f"2001:db8:0:1::{suffix}").post("/api/demo-login").status_code == 200
    assert (new_client(demo_app, "2001:db8:0:1:abcd::9").post("/api/demo-login").status_code) == 429
    assert new_client(demo_app, "2001:db8:0:2::1").post("/api/demo-login").status_code == 200


def test_ip_key_uses_derived_secret_and_trusted_proxy_hop(demo_app):
    with demo_app.test_request_context():
        assert demo.ip_key("10.0.0.1") != hmac.new(b"test", b"10.0.0.1", hashlib.sha256).hexdigest()[:16]
    # 앞단 프록시 한 단계(TRUSTED_PROXY_HOPS=1): 사용자가 끼워 넣은 앞쪽 값은 무시하고 마지막 값을 본다
    spoofed = [new_client(demo_app, "127.0.0.1") for _ in range(4)]
    for index, c in enumerate(spoofed):
        c.environ_base["HTTP_X_FORWARDED_FOR"] = f"9.9.9.{index}, 203.0.113.5"
    assert [c.post("/api/demo-login").status_code for c in spoofed] == [200, 200, 200, 429]


def test_demo_login_recycles_oldest_when_full(demo_app, monkeypatch):
    monkeypatch.setattr(demo, "MAX_ACTIVE", 2)
    first = new_client(demo_app, "10.0.0.1")
    first_id = first.post("/api/demo-login").get_json()["id"]
    age_demo_users(demo_app, minutes=10)
    assert new_client(demo_app, "10.0.0.2").post("/api/demo-login").status_code == 200
    assert new_client(demo_app, "10.0.0.3").post("/api/demo-login").status_code == 200  # 가득 차도 막히지 않는다
    with demo_app.app_context():
        assert User.query.filter_by(provider="demo").count() == 2
        assert Ingredient.query.filter_by(user_id=first_id).count() == 0
    assert first.get("/api/me").status_code == 401  # 지워진 첫 계정의 세션은 끝난다(SQLite id 재사용에도 pid로 막힌다)


def test_demo_login_hard_ceiling(demo_app, monkeypatch):
    for index in range(3):
        assert new_client(demo_app, f"10.0.1.{index}").post("/api/demo-login").status_code == 200
    monkeypatch.setattr(demo, "MAX_ACTIVE", 1)
    monkeypatch.setattr(demo, "PURGE_BATCH", 1)  # 한 번에 1개만 지울 수 있는데 3개를 지워야 한다
    res = new_client(demo_app, "10.0.1.9").post("/api/demo-login")
    assert res.status_code == 503
    with demo_app.app_context():
        assert User.query.filter_by(provider="demo").count() == 2  # 지운 1개는 남기고 새로 만들지 않는다


def counts(user_id):
    return [model.query.filter_by(user_id=user_id).count() for model in USER_TABLES]


def test_purge_deletes_only_expired_demo_users(demo_app):
    old_demo = new_client(demo_app, "10.0.0.1").post("/api/demo-login").get_json()["id"]
    fresh_demo = new_client(demo_app, "10.0.0.2").post("/api/demo-login").get_json()["id"]
    with demo_app.app_context():
        long_ago = utcnow() - timedelta(hours=25)
        normal = User(provider="kakao", provider_id="1", nickname="오래된 사용자", created_at=long_ago)
        db.session.add(normal)
        db.session.flush()
        normal_id = normal.id
        location = StorageLocation(user_id=normal_id, name="냉장실", kind="fridge")
        db.session.add(location)
        db.session.flush()
        db.session.add(Ingredient(user_id=normal_id, location_id=location.id, name="두부", purchased_on=seoul_today()))
        db.session.add(AiCall(user_id=old_demo, demo=True, kind="recipe"))
        db.session.get(User, old_demo).created_at = long_ago
        db.session.commit()
        assert all(counts(old_demo)[:-1])
        assert MealSlot.query.join(MealPlan).filter(MealPlan.user_id == old_demo).count() == len(demo.MEAL_PLAN_SLOTS)

    result = demo_app.test_cli_runner().invoke(args=["purge-demo-users"])
    assert result.exit_code == 0 and "1개" in result.output

    with demo_app.app_context():
        assert db.session.get(User, old_demo) is None
        assert counts(old_demo) == [0] * len(USER_TABLES)
        assert MealSlot.query.join(MealPlan).filter(MealPlan.user_id == old_demo).count() == 0  # CASCADE: 칸도 함께 지워진다
        kept = AiCall.query.filter_by(user_id=None).all()  # AI 호출 기록은 사용자만 비우고 남는다(원가·체험 예산)
        assert [(a.kind, a.demo) for a in kept] == [("recipe", True)]
        assert db.session.get(User, fresh_demo) is not None
        assert counts(fresh_demo)[0] == len(demo.INGREDIENTS)
        assert db.session.get(User, normal_id) is not None
        assert counts(normal_id)[0] == 1


def test_demo_login_purges_expired_on_the_way(demo_app):
    c = new_client(demo_app)
    expired = c.post("/api/demo-login").get_json()["id"]
    with demo_app.app_context():
        user = db.session.get(User, expired)
        user.created_at = utcnow() - timedelta(hours=25)
        expired_provider_id = user.provider_id
        db.session.commit()
    assert c.get("/api/me").status_code == 200
    assert c.post("/api/demo-login").status_code == 200
    with demo_app.app_context():  # SQLite는 지운 id를 다시 쓸 수 있어 provider_id로 확인한다
        assert User.query.filter_by(provider_id=expired_provider_id).count() == 0
        assert User.query.count() == 1
    # 이전 세션의 사용자가 지워져도 새로 로그인한 세션은 그대로 쓴다
    assert c.get("/api/me").get_json()["provider"] == "demo"


def demo_photo(app, ip):
    """체험 계정을 만들고 메모 사진 한 장을 올린다(DEV_MODE 로컬 저장소). (사용자 id, 사진 파일 경로)"""
    c = new_client(app, ip)
    me = c.post("/api/demo-login").get_json()
    photo = upload(c, add_note(c).get_json()["id"]).get_json()
    path = photo_path(app, photo["url"])
    assert os.path.exists(path)
    return me["id"], path


def test_purge_deletes_demo_photo_files(make_app):
    app = make_app(DEMO_LOGIN=True, DEV_MODE=True)
    old_id, old_path = demo_photo(app, "10.0.0.1")
    _, fresh_path = demo_photo(app, "10.0.0.2")
    with app.app_context():
        db.session.get(User, old_id).created_at = utcnow() - timedelta(hours=25)
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-demo-users"])
    assert result.exit_code == 0 and "1개" in result.output
    assert not os.path.exists(old_path)
    assert os.path.exists(fresh_path)


def test_purge_deletes_food_log_photo_files(make_app):
    app = make_app(DEMO_LOGIN=True, DEV_MODE=True)
    paths = {}
    for ip in ("10.0.0.1", "10.0.0.2"):
        c = new_client(app, ip)
        user_id = c.post("/api/demo-login").get_json()["id"]
        res = c.post("/api/food-logs/photo", data={"image": (io.BytesIO(JPEG), "a.jpg")}, content_type="multipart/form-data")
        assert res.status_code == 201
        paths[user_id] = photo_path(app, res.get_json()["photos"][0]["url"])
        assert os.path.exists(paths[user_id])
    old_id, fresh_id = paths
    with app.app_context():
        db.session.get(User, old_id).created_at = utcnow() - timedelta(hours=25)
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-demo-users"])
    assert result.exit_code == 0 and "1개" in result.output
    assert not os.path.exists(paths[old_id])
    assert os.path.exists(paths[fresh_id])


def test_demo_login_recycle_and_expiry_delete_photo_files(make_app, monkeypatch):
    app = make_app(DEMO_LOGIN=True, DEV_MODE=True)
    _, expired_path = demo_photo(app, "10.0.0.1")
    age_demo_users(app, hours=25)
    _, oldest_path = demo_photo(app, "10.0.0.2")
    monkeypatch.setattr(demo, "MAX_ACTIVE", 1)
    _, kept_path = demo_photo(app, "10.0.0.3")  # 만료 계정은 지나가며, 가장 오래된 계정은 재활용으로 지운다
    assert not os.path.exists(expired_path)
    assert not os.path.exists(oldest_path)
    assert os.path.exists(kept_path)
