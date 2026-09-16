"""찾지 못함·오류로 끝난 AI 호출(스펙 7절 헛호출, 2026-09-16 사용자 승인).
사용자마다 하루(서울) 3번까지 kind에 _miss를 붙여 하루 한도·사용량에서 빼고, 전체 AI 예산·연속 호출 한도에는 그대로 센다."""

from datetime import timedelta

import pytest
from sqlalchemy import event as sqlalchemy_event

from app import ai
from app.models import AiCall, User, db, utcnow
from tests.test_meal_ai import draft as meal_draft
from tests.test_meals import add_recipe, make_plan
from tests.test_recipe_ai import add_ingredient, draft, fix_clock, import_, import_photos, make
from tests.test_scan import FOUND, JPEG_BYTES, USAGE, ai_call_costs, ai_calls, fail_if_called, upload

MISS_KINDS = ["fridge_miss", "receipt_miss", "order_miss", "memo_miss", "recipe_miss", "link_miss", "recipe_photo_miss", "meal_miss", "eat_out_miss"]


def broken(*args):
    raise ai.AiError("timeout")


def scan_memo(client, monkeypatch, fake):
    monkeypatch.setattr(ai, "extract", fake)
    return upload(client, kind="memo")


def ai_recipes(client, monkeypatch, fake):
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", fake)
    return make(client)


def text_import(client, monkeypatch, fake):
    monkeypatch.setattr(ai, "extract_recipe", fake)
    return import_(client, text="오늘은 날씨가 좋아서 산책을 했어요.")


def photo_import(client, monkeypatch, fake):
    monkeypatch.setattr(ai, "extract_recipe_from_images", fake)
    return import_photos(client, JPEG_BYTES)


def meal_ai_draft(client, monkeypatch, fake):
    monkeypatch.setattr(ai, "draft_meals", fake)
    return meal_draft(client, make_plan(client).get_json()["id"])


def eat_out(client, monkeypatch, fake):
    monkeypatch.setattr(ai, "estimate_eat_out", fake)
    recipe = add_recipe(client, "된장찌개", [{"name": "두부", "amount": "1모"}])
    return client.post(f"/api/recipes/{recipe['id']}/eat-out-estimate")


# (kind, 요청, 쓸 것이 없는 AI 응답, 그때 상태)
ENDPOINTS = [
    ("memo", scan_memo, {"items": [{"name": "  "}], "purchased_on": None}, 200),  # 정리하고 나면 재료 0개
    ("recipe", ai_recipes, {"recipes": [draft(names=())]}, 502),
    ("link", text_import, {"found": False, "recipe": None}, 422),
    ("recipe_photo", photo_import, {"found": True, "recipe": draft(names=())}, 422),  # 찾았다지만 쓸 재료가 없다
    ("meal", meal_ai_draft, {"dishes": [], "slots": []}, 502),
    ("eat_out", eat_out, {"price": 500}, 502),  # 1,000~100,000원 밖
]


@pytest.mark.parametrize("kind, request_, nothing, status", ENDPOINTS)
def test_errors_and_empty_results_are_free_misses(client, login, app, monkeypatch, kind, request_, nothing, status):
    """AiError와 쓸 것이 없는 응답은 <kind>_miss로 남아 하루 한도·사용량에 세지 않는다. 응답을 받았으면 토큰은 그대로 남긴다."""
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    assert request_(client, monkeypatch, broken).status_code == 502
    assert request_(client, monkeypatch, lambda *args: (nothing, USAGE)).status_code == status
    assert ai_calls(app) == [(user.id, f"{kind}_miss")] * 2
    assert ai_call_costs(app) == [("claude-sonnet-5", None, None), ("claude-sonnet-5-answered", 1500, 120)]
    assert client.get("/api/ai-usage").get_json() == {"scan": {"used": 0, "limit": 10}, "recipe": {"used": 0, "limit": 10}}


def test_only_three_misses_a_day_are_free(client, login, app, monkeypatch):
    """헛호출은 사진 인식·AI 레시피를 합쳐 사용자마다 하루 3번까지 세지 않고, 4번째부터는 원래 kind로 센다."""
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_SCAN_BURST_LIMIT=10)
    start, _ = fix_clock(monkeypatch)
    with app.app_context():
        other = User(provider="test", provider_id="other", nickname="x")
        db.session.add(other)
        db.session.flush()
        db.session.add_all(
            [
                AiCall(user_id=user.id, kind="link_miss", created_at=start + timedelta(hours=1)),  # AI 레시피 헛호출도 함께 센다
                AiCall(user_id=user.id, kind="fridge_miss", created_at=start - timedelta(seconds=1)),  # 서울 어제 → 안 셈
                *[AiCall(user_id=other.id, kind="receipt_miss", created_at=start + timedelta(hours=1)) for _ in range(3)],  # 다른 사용자
            ]
        )
        db.session.commit()

    monkeypatch.setattr(ai, "extract", broken)
    assert upload(client, kind="receipt").status_code == 502  # 오늘 두 번째 헛호출
    monkeypatch.setattr(ai, "extract", lambda kind, images: ({"items": [], "purchased_on": None}, USAGE))
    assert upload(client, kind="fridge").status_code == 200  # 세 번째
    assert upload(client, kind="order").status_code == 200  # 네 번째부터는 센다
    monkeypatch.setattr(ai, "extract", broken)
    assert upload(client, kind="memo").status_code == 502
    mine = [kind for user_id, kind in ai_calls(app) if user_id == user.id]
    assert mine[2:] == ["receipt_miss", "fridge_miss", "order", "memo"]
    assert client.get("/api/ai-usage").get_json()["scan"] == {"used": 2, "limit": 10}


def test_free_misses_leave_daily_limit_open(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_DAILY_SCAN_LIMIT=2)
    start, _ = fix_clock(monkeypatch)
    with app.app_context():
        kinds = ["receipt", "fridge_miss", "memo_miss", "recipe_miss"]
        db.session.add_all(AiCall(user_id=user.id, kind=k, created_at=start + timedelta(hours=1)) for k in kinds)
        db.session.commit()
    monkeypatch.setattr(ai, "extract", lambda kind, images: (FOUND, USAGE))
    assert upload(client).status_code == 200  # 헛호출 3번은 세지 않아 두 번째가 된다
    res = upload(client)
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 사진 인식은 2번까지 쓸 수 있어요. 내일 다시 써주세요."})


def test_misses_count_toward_burst_limit(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_SCAN_BURST_LIMIT=3)
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "extract", fail_if_called)
    monkeypatch.setattr(ai, "suggest_recipes", fail_if_called)
    _, now = fix_clock(monkeypatch)
    with app.app_context():
        kinds = ["fridge_miss", "memo_miss", "order_miss", "recipe_miss", "link_miss", "meal_miss"]
        db.session.add_all(AiCall(user_id=user.id, kind=k, created_at=now - timedelta(seconds=5)) for k in kinds)
        db.session.commit()
    for res in (upload(client), make(client)):
        assert (res.status_code, res.get_json()) == (429, {"error": "잠시 후 다시 시도해주세요."})


def test_misses_count_toward_global_ai_budgets(app):
    """로그인 사용자 전체 AI 예산과 체험 전체 AI 예산은 헛호출도 모두 센다."""
    app.config.update(USER_AI_GLOBAL_DAILY=len(MISS_KINDS), DEMO_AI_GLOBAL_DAILY=len(MISS_KINDS))
    with app.app_context():
        for demo in (False, True):
            db.session.add_all(AiCall(user_id=None, demo=demo, kind=k, created_at=utcnow()) for k in MISS_KINDS[:-1])
        db.session.commit()
        assert (ai.user_ai_budget_spent(), ai.demo_ai_budget_spent()) == (False, False)
        for demo in (False, True):
            db.session.add(AiCall(user_id=None, demo=demo, kind=MISS_KINDS[-1], created_at=utcnow()))
        db.session.commit()
        assert (ai.user_ai_budget_spent(), ai.demo_ai_budget_spent()) == (True, True)


def test_miss_count_and_relabel_share_one_locked_transaction(client, login, app, monkeypatch):
    """동시에 끝난 헛호출이 같은 개수를 보고 함께 빠지지 않게, PostgreSQL에서는 사용자별 잠금을 잡고 세고 바꾼다."""
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    monkeypatch.setattr(ai, "extract", broken)
    events = []
    with app.app_context():
        engine = db.engine

    def on_execute(conn, cursor, statement, *args):
        events.append("LOCK" if "pg_advisory_xact_lock" in statement else statement.split()[0].upper())

    def on_commit(conn):
        events.append("COMMIT")

    sqlalchemy_event.listen(engine, "before_cursor_execute", on_execute)
    sqlalchemy_event.listen(engine, "commit", on_commit)
    try:
        assert upload(client).status_code == 502
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", on_execute)
        sqlalchemy_event.remove(engine, "commit", on_commit)
    update = events.index("UPDATE")  # 오류라 토큰 기록은 없다 — 유일한 UPDATE가 kind 바꾸기
    last_commit = update - 1 - events[:update][::-1].index("COMMIT")
    in_transaction = events[last_commit + 1 : update]
    assert "SELECT" in in_transaction and events[update + 1] == "COMMIT"
    assert ("LOCK" in in_transaction) == (engine.dialect.name == "postgresql")
