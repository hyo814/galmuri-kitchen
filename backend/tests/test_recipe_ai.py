from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event as sqlalchemy_event

from app import ai, scan
from app.ingredients import SEOUL, seoul_today
from app.models import AiCall, PublicRecipe, User, db
from app.recipe_ai import clean_draft, public_image_candidates, similar_public_image
from tests.test_scan import AI_FAILURES, USAGE, ai_call_costs, ai_calls, fail_if_called

FAIL = "레시피를 만들지 못했어요. 잠시 후 다시 시도해주세요."
PHOTO = "https://www.foodsafetykorea.go.kr/uploadimg/cook/{}.jpg"


def add_ingredient(client, name, **fields):
    body = {"name": name, "purchased_on": seoul_today().isoformat(), **fields}
    assert client.post("/api/ingredients", json=body).status_code == 201


def add_public(app, *rows):
    """rows: (title, image_url). id는 넣은 순서대로 커진다."""
    with app.app_context():
        for index, (title, image_url) in enumerate(rows):
            db.session.add(PublicRecipe(rcp_seq=f"P{index}", title=title, image_url=image_url))
        db.session.commit()


def draft(title="두부조림", names=("두부", "간장"), **fields):
    return {
        "title": title,
        "servings": 2,
        "minutes": 20,
        "ingredients": [{"name": n, "amount": "1큰술"} for n in names],
        "steps": ["썰어요.", "졸여요."],
        **fields,
    }


def make(client):
    return client.post("/api/recommendations/ai")


# --- clean_draft ---


def test_clean_draft_trims_caps_and_rejects_empty():
    raw = {
        "title": "  " + "가" * 70,
        "servings": 3,
        "minutes": 20,
        "ingredients": [
            {"name": " 두부 ", "amount": " 1모 "},
            {"name": "", "amount": "1개"},
            {"name": "   ", "amount": "1개"},
            "not-a-dict",
            {"name": "두부", "amount": "2모"},
            {"name": "간장" + "나" * 60, "amount": "1" * 40},
            {"name": "소금", "amount": None},
        ],
        "steps": ["  썰어요. ", "", "  ", 3, "나" * 600],
    }
    assert clean_draft(raw) == {
        "title": "가" * 60,
        "servings": 3,
        "minutes": 20,
        "ingredients": [
            {"name": "두부", "amount": "1모"},
            {"name": ("간장" + "나" * 60)[:50], "amount": "1" * 30},
            {"name": "소금", "amount": ""},
        ],
        "steps": ["썰어요.", "나" * 500],
    }
    for servings in (0, 21, "2", True, None):
        assert clean_draft(draft(servings=servings))["servings"] == 2
    for minutes in (0, 301, 999, "20", "오분", True, None, 20.5):
        assert clean_draft(draft(minutes=minutes))["minutes"] is None
    assert clean_draft(draft(minutes=300))["minutes"] == 300
    no_minutes = draft()
    del no_minutes["minutes"]
    assert "minutes" not in clean_draft(no_minutes)  # 가져오기 초안에는 조리 시간이 없다

    many = draft(names=[f"재료{i}" for i in range(80)], steps=[f"{i}단계" for i in range(40)])
    assert (len(clean_draft(many)["ingredients"]), len(clean_draft(many)["steps"])) == (50, 30)
    assert clean_draft(draft(names=())) is None
    assert clean_draft(draft(ingredients=[{"name": " "}])) is None
    assert clean_draft(draft(title="   ")) is None
    assert clean_draft(draft(title=None)) is None
    assert clean_draft("레시피") is None
    assert clean_draft(draft(ingredients="두부", steps="썰어요")) is None
    assert clean_draft(draft(steps="썰어요"))["steps"] == []


# --- similar_public_image ---


@pytest.mark.parametrize(
    "title, expected",
    [
        ("두부 조림", PHOTO.format("tofu")),  # 정규화 이름이 같다
        ("매콤 두부조림", PHOTO.format("tofu")),  # 한쪽이 다른 쪽을 포함
        ("된장찌개 백반", PHOTO.format("doenjang")),  # 정규화 '된장찌개'를 포함
        ("찌개 된장", PHOTO.format("doenjang")),  # 토큰이 모두 겹친다(Jaccard 1)
        ("애호박 두부전", None),  # 포함도 토큰 겹침도 없다
        ("감자전", None),  # '전' 같은 짧은 조각은 포함 규칙에 걸리지 않는다
        ("김치찌개", None),  # 사진 없는 공공 레시피는 후보가 아니다
        ("파스타", None),
        ("", None),
    ],
)
def test_similar_public_image(app, title, expected):
    add_public(
        app,
        ("두부조림", PHOTO.format("tofu")),
        ("애호박전", PHOTO.format("zucchini")),
        ("계란말이", PHOTO.format("egg")),
        ("된장 찌개", PHOTO.format("doenjang")),
        ("김치찌개", None),
        ("전", PHOTO.format("jeon")),
    )
    with app.app_context():
        assert similar_public_image(title, public_image_candidates()) == expected


def test_similar_public_image_prefers_closest_then_smaller_id(app):
    add_public(
        app,
        ("두부 조림", PHOTO.format("first")),
        ("두부조림", PHOTO.format("second")),
        ("매콤한 두부조림 정식", PHOTO.format("far")),
        ("매콤 두부조림 정식", PHOTO.format("near")),
    )
    with app.app_context():
        candidates = public_image_candidates()
        assert similar_public_image("두부조림", candidates) == PHOTO.format("first")  # 같은 점수면 id 작은 것
        assert similar_public_image("매콤 두부조림 정식 백반", candidates) == PHOTO.format("near")  # 포함하는 것 중 길이 차가 작은 것


def test_similar_public_image_jaccard_tie_and_short_tokens(app):
    add_public(
        app,
        ("된장 찌개 백반", PHOTO.format("first")),
        ("찌개 된장 정식", PHOTO.format("second")),
        ("된장 국수", PHOTO.format("noodle")),
    )
    with app.app_context():
        candidates = public_image_candidates()
        assert similar_public_image("찌개 된장 전", candidates) == PHOTO.format("first")  # 둘 다 2/3 → id 작은 것
        # '전'(한 글자)은 토큰 비교에서 빠진다: {된장} vs {된장, 국수} = 0.5. 셌다면 1/3이라 사진이 없다
        assert similar_public_image("된장 전", candidates) == PHOTO.format("noodle")


# --- ai.suggest_recipes (가짜 Anthropic 클라이언트) ---


def test_suggest_recipes_sends_stock_and_schema(app, fake_anthropic):
    parsed = ai.Suggestions(
        recipes=[
            ai.AiRecipe(title="두부조림", servings=2, minutes=20, ingredients=[ai.DraftIngredient(name="두부", amount="1모")], steps=["졸여요."])
        ]
    )
    usage = SimpleNamespace(input_tokens=900, output_tokens=400)
    calls = fake_anthropic(response=SimpleNamespace(stop_reason="end_turn", parsed_output=parsed, usage=usage, model="claude-sonnet-5-answered"))
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    lines = ["두부 (빨리)", "두부 (빨리)"] + [f"재료{i}" for i in range(149)]  # 같은 이름 줄은 한 번만
    with app.app_context():
        result, tokens = ai.suggest_recipes(lines)

    assert tokens == {"model": "claude-sonnet-5-answered", "input_tokens": 900, "output_tokens": 400}
    assert result == {
        "recipes": [{"title": "두부조림", "servings": 2, "ingredients": [{"name": "두부", "amount": "1모"}], "steps": ["졸여요."], "minutes": 20}]
    }
    request = calls["parse"]
    assert (request["model"], request["output_format"]) == ("claude-sonnet-5", ai.Suggestions)
    prompt = request["messages"][0]["content"]
    assert prompt.splitlines().count("두부 (빨리)") == 1
    assert "재료98" in prompt.splitlines() and "재료99" not in prompt  # 재고는 100줄까지만 보낸다


@pytest.mark.parametrize("response, error", AI_FAILURES)
def test_suggest_recipes_failures_raise_ai_error(app, fake_anthropic, response, error):
    fake_anthropic(response=response, error=error)
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    with app.app_context(), pytest.raises(ai.AiError):
        ai.suggest_recipes(["두부"])


# --- POST /api/recommendations/ai ---


def test_ai_recipes_requires_login_and_inventory(client, login, app, monkeypatch):
    assert make(client).status_code == 401
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    monkeypatch.setattr(ai, "suggest_recipes", fail_if_called)
    res = make(client)
    assert (res.status_code, res.get_json()) == (400, {"error": "재고에 재료를 먼저 추가해주세요."})
    assert ai_calls(app) == []


def test_ai_recipes_sample_mode(client, login, app, monkeypatch):
    login()
    monkeypatch.setattr(ai, "suggest_recipes", fail_if_called)
    add_ingredient(client, "두부")
    body = make(client).get_json()
    assert body["sample"] is True
    assert [r["title"] for r in body["recipes"]] == ["두부 대파 짜글이", "애호박 두부전", "대파 계란볶음밥"]
    assert all(isinstance(r["minutes"], int) for r in body["recipes"])
    tofu = next(i for i in body["recipes"][0]["ingredients"] if i["name"] == "두부")
    assert (tofu["have"], tofu["matched_name"]) == (True, "두부")
    assert (body["recipes"][0]["urgent_names"], body["urgent_first"]) == ([], [])
    assert ai_calls(app) == []


def test_ai_recipes_attach_similar_public_image(client, login, app, monkeypatch):
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    add_public(app, ("두부조림", PHOTO.format("tofu")))
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft("두부조림"), draft("파스타")]}, USAGE))
    body = make(client).get_json()
    assert [(r["title"], r["image_url"]) for r in body["recipes"]] == [("두부조림", PHOTO.format("tofu")), ("파스타", None)]


def test_ai_recipes_off_in_production_is_503(client, login, app, monkeypatch):
    login()
    app.config["DEV_MODE"] = False
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", fail_if_called)
    res = make(client)
    assert (res.status_code, res.get_json()) == (503, {"error": "AI 레시피를 지금은 쓸 수 없어요."})


def test_ai_recipes_real_call_cleans_marks_urgent_and_logs_tokens(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    add_ingredient(client, "대파")
    add_ingredient(client, "두부", expires_on=(seoul_today() + timedelta(days=1)).isoformat())
    seen = []

    def fake_suggest(lines):
        seen.append(lines)
        raw = [
            draft(" 두부조림 ", ["두부", "간장"]),
            draft("재료 없음", ()),
            draft("대파전", ["대파", "부침가루"]),
            draft("계란국", ["계란"], minutes="10분"),
        ]
        return {"recipes": raw}, USAGE

    monkeypatch.setattr(ai, "suggest_recipes", fake_suggest)
    res = make(client)
    assert res.status_code == 200
    body = res.get_json()
    assert seen == [["두부 (빨리)", "대파"]]  # 임박 재료가 앞, (빨리) 표시
    assert body["sample"] is False
    assert body["urgent_first"] == ["두부"]
    assert body["recipes"][0] == {
        "title": "두부조림",
        "servings": 2,
        "minutes": 20,
        "ingredients": [
            {"name": "두부", "amount": "1큰술", "have": True, "matched_name": "두부"},
            {"name": "간장", "amount": "1큰술", "have": False, "matched_name": None},
        ],
        "steps": ["썰어요.", "졸여요."],
        "urgent_names": ["두부"],
        "image_url": None,
    }
    assert [(r["title"], r["urgent_names"], r["minutes"]) for r in body["recipes"][1:]] == [("대파전", [], 20), ("계란국", [], None)]
    assert ai_calls(app) == [(user.id, "recipe")]
    assert ai_call_costs(app) == [("claude-sonnet-5-answered", 1500, 120)]


def test_ai_recipes_returns_first_three_usable(client, login, app, monkeypatch):
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    add_ingredient(client, "두부")
    titles = ["가지볶음", "나물무침", "두부조림", "라면", "무국"]
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft(t) for t in titles]}, USAGE))
    assert [r["title"] for r in make(client).get_json()["recipes"]] == titles[:3]


def test_ai_recipes_failure_is_502_and_counted(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    add_ingredient(client, "두부")

    def broken(lines):
        raise ai.AiError("timeout")

    monkeypatch.setattr(ai, "suggest_recipes", broken)
    res = make(client)
    assert (res.status_code, res.get_json()) == (502, {"error": FAIL})
    assert ai_call_costs(app) == [("claude-sonnet-5", None, None)]

    # 응답은 받았지만 정리하고 나니 쓸 레시피가 없으면 같은 502, 토큰은 남긴다
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft(names=())]}, USAGE))
    res = make(client)
    assert (res.status_code, res.get_json()) == (502, {"error": FAIL})
    assert ai_calls(app) == [(user.id, "recipe"), (user.id, "recipe")]
    assert ai_call_costs(app)[1] == ("claude-sonnet-5-answered", 1500, 120)


def fix_clock(monkeypatch):
    today = date(2026, 9, 13)
    start = datetime.combine(today, time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    now = start + timedelta(hours=12)
    monkeypatch.setattr(scan, "seoul_today", lambda: today)
    monkeypatch.setattr(scan, "utcnow", lambda: now)
    return start, now


def test_recipe_daily_limit_counts_recipe_and_link_only(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft()]}, USAGE))
    start, now = fix_clock(monkeypatch)
    with app.app_context():
        other = User(provider="test", provider_id="other", nickname="x")
        db.session.add(other)
        db.session.flush()
        db.session.add_all(
            [
                *[AiCall(user_id=user.id, kind="fridge", created_at=now) for _ in range(10)],  # 사진 인식 → 안 셈
                *[AiCall(user_id=user.id, kind="recipe", created_at=start + timedelta(minutes=i)) for i in range(5)],
                *[AiCall(user_id=user.id, kind="link", created_at=start + timedelta(minutes=10 + i)) for i in range(4)],
                AiCall(user_id=user.id, kind="recipe", created_at=start - timedelta(seconds=1)),  # 서울 어제 → 안 셈
                *[AiCall(user_id=other.id, kind="recipe", created_at=now) for _ in range(10)],  # 다른 사용자 → 안 셈
            ]
        )
        db.session.commit()

    assert make(client).status_code == 200  # recipe 5 + link 4 = 9번, 10번째는 된다
    res = make(client)
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 AI 레시피는 10번까지 쓸 수 있어요. 내일 다시 써주세요."})


def test_recipe_burst_limit_separate_from_scan(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_SCAN_BURST_LIMIT=3)
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft()]}, USAGE))
    _, now = fix_clock(monkeypatch)
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="receipt", created_at=now - timedelta(seconds=5)) for _ in range(3)])
        db.session.commit()
    assert make(client).status_code == 200  # 사진 인식 연속 호출은 레시피를 막지 않는다
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="link", created_at=now - timedelta(seconds=5)) for _ in range(2)])
        db.session.commit()
    res = make(client)
    assert (res.status_code, res.get_json()) == (429, {"error": "잠시 후 다시 시도해주세요."})


def test_recipe_burst_limit_boundary(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_SCAN_BURST_LIMIT=3)
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft()]}, USAGE))
    _, now = fix_clock(monkeypatch)
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="recipe", created_at=now - timedelta(seconds=59)) for _ in range(2)])
        db.session.commit()
    assert make(client).status_code == 200  # 60초 안에 2번(한도 - 1) → 된다
    res = make(client)  # 이제 3번 → 막힌다
    assert (res.status_code, res.get_json()) == (429, {"error": "잠시 후 다시 시도해주세요."})


def test_limit_check_and_call_record_share_one_locked_transaction(client, login, app, monkeypatch):
    """세고 기록하는 사이에 다른 요청이 끼어들지 않게, PostgreSQL에서는 사용자·묶음별 잠금을 잡고 같은 트랜잭션에서 기록한다."""
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    add_ingredient(client, "두부")
    monkeypatch.setattr(ai, "suggest_recipes", lambda lines: ({"recipes": [draft()]}, USAGE))
    events = []
    with app.app_context():
        engine = db.engine

    def on_execute(conn, cursor, statement, *args):
        events.append(statement.split()[0].upper() if "pg_advisory_xact_lock" not in statement else "LOCK")

    def on_commit(conn):
        events.append("COMMIT")

    sqlalchemy_event.listen(engine, "before_cursor_execute", on_execute)
    sqlalchemy_event.listen(engine, "commit", on_commit)
    try:
        assert make(client).status_code == 200
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", on_execute)
        sqlalchemy_event.remove(engine, "commit", on_commit)
    first_insert = events.index("INSERT")
    before = events[:first_insert]
    last_commit = len(before) - 1 - before[::-1].index("COMMIT") if "COMMIT" in before else -1
    in_transaction = before[last_commit + 1 :]
    assert in_transaction.count("SELECT") >= 2  # 연속·하루 한도를 센 SELECT가 INSERT와 같은 트랜잭션
    assert events[first_insert + 1] == "COMMIT"
    assert ("LOCK" in in_transaction) == (engine.dialect.name == "postgresql")


# --- GET /api/ai-usage ---


def test_ai_usage_counts_today_by_group(client, login, app, monkeypatch):
    assert client.get("/api/ai-usage").status_code == 401
    user = login()
    app.config.update(AI_DAILY_SCAN_LIMIT=7, AI_DAILY_RECIPE_LIMIT=5)
    start, now = fix_clock(monkeypatch)
    with app.app_context():
        db.session.add_all(
            [
                AiCall(user_id=user.id, kind="fridge", created_at=now),
                AiCall(user_id=user.id, kind="memo", created_at=now),
                AiCall(user_id=user.id, kind="recipe", created_at=now),
                AiCall(user_id=user.id, kind="link", created_at=now),
                AiCall(user_id=user.id, kind="link", created_at=start + timedelta(seconds=1)),
                AiCall(user_id=user.id, kind="recipe", created_at=start - timedelta(seconds=1)),  # 어제
            ]
        )
        db.session.commit()
    assert client.get("/api/ai-usage").get_json() == {"scan": {"used": 2, "limit": 7}, "recipe": {"used": 3, "limit": 5}}


def test_ai_recipes_requires_fetch_header(raw_client):
    res = raw_client.post("/api/recommendations/ai")
    assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
