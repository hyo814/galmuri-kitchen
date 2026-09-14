from datetime import datetime, time, timedelta, timezone

import pytest

from app import ai, demo, scan
from app.ingredients import SEOUL, seoul_today
from app.models import (
    AiCall,
    Ingredient,
    ItemRule,
    Recipe,
    Seasoning,
    Staple,
    StorageLocation,
    User,
    db,
    utcnow,
)

USER_TABLES = (Ingredient, StorageLocation, ItemRule, Staple, Recipe, Seasoning, AiCall)


@pytest.fixture
def demo_app(make_app):
    return make_app(DEMO_LOGIN=True, DEV_MODE=False)


def new_client(app, ip="10.0.0.1"):
    c = app.test_client()
    c.environ_base.update(HTTP_X_REQUESTED_WITH="fetch", REMOTE_ADDR=ip)
    return c


def test_demo_login_disabled_is_404(client):
    assert client.post("/api/demo-login").status_code == 404
    assert client.get("/api/auth-options").get_json()["demo_login"] is False


def test_demo_login_requires_fetch_header(demo_app):
    assert demo_app.test_client().post("/api/demo-login").status_code == 400


def test_demo_login_creates_seeded_user_and_session(demo_app):
    c = new_client(demo_app)
    assert c.get("/api/auth-options").get_json()["demo_login"] is True
    me = c.post("/api/demo-login").get_json()
    assert (me["nickname"], me["provider"], me["scan_limit"], me["recipe_limit"]) == ("체험 사용자", "demo", 3, 3)
    assert c.get("/api/me").get_json()["id"] == me["id"]

    items = c.get("/api/ingredients").get_json()
    assert len(items) == len(demo.INGREDIENTS)
    assert {i["location_kind"] for i in items} == {"fridge", "freezer", "room"}
    today = seoul_today()
    expiring = {i["name"]: i["expires_on"] for i in items if i["name"] in ("두부", "대파")}
    assert expiring == {"두부": (today + timedelta(days=1)).isoformat(), "대파": (today + timedelta(days=2)).isoformat()}
    assert len(c.get("/api/recipes").get_json()["items"]) == 2
    assert len(c.get("/api/seasonings").get_json()["items"]) == 1
    assert len(c.get("/api/staples").get_json()) == 3
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


def test_demo_ai_limits_are_lower(demo_app, monkeypatch):
    c = new_client(demo_app)
    user_id = c.post("/api/demo-login").get_json()["id"]
    demo_app.config.update(ANTHROPIC_API_KEY="test-key", AI_DAILY_RECIPE_LIMIT=10, AI_DAILY_SCAN_LIMIT=10)
    assert c.get("/api/ai-usage").get_json() == {"scan": {"used": 0, "limit": 3}, "recipe": {"used": 0, "limit": 3}}

    fixed_today = seoul_today()
    fixed_now = datetime.combine(fixed_today, time(12), tzinfo=SEOUL).astimezone(timezone.utc)
    monkeypatch.setattr(scan, "seoul_today", lambda: fixed_today)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    monkeypatch.setattr(ai, "suggest_recipes", lambda *args: pytest.fail("AI를 부르면 안 돼요"))
    with demo_app.app_context():
        db.session.add_all(AiCall(user_id=user_id, kind="recipe", created_at=fixed_now - timedelta(hours=i + 1)) for i in range(3))
        db.session.commit()
    res = c.post("/api/recommendations/ai")
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 AI 레시피는 3번까지 쓸 수 있어요. 내일 다시 써주세요."})


def test_normal_user_limits_unchanged(client, login, app):
    login()
    assert client.get("/api/me").get_json()["recipe_limit"] == app.config["AI_DAILY_RECIPE_LIMIT"]


def test_demo_login_per_ip_limit(demo_app, monkeypatch):
    monkeypatch.setattr(demo, "IP_HOURLY_LIMIT", 2)
    same = new_client(demo_app, "10.0.0.7")
    assert same.post("/api/demo-login").status_code == 200
    assert same.post("/api/demo-login").status_code == 200
    res = same.post("/api/demo-login")
    assert (res.status_code, res.get_json()) == (429, {"error": "체험하기를 너무 많이 눌렀어요. 잠시 후 다시 시도해주세요."})
    assert new_client(demo_app, "10.0.0.8").post("/api/demo-login").status_code == 200

    with demo_app.app_context():  # 한 시간이 지나면 다시 된다
        User.query.filter_by(provider="demo").update({"created_at": utcnow() - timedelta(minutes=61)})
        db.session.commit()
    assert same.post("/api/demo-login").status_code == 200


def test_demo_login_global_cap(demo_app, monkeypatch):
    monkeypatch.setattr(demo, "MAX_ACTIVE", 2)
    assert new_client(demo_app, "10.0.0.1").post("/api/demo-login").status_code == 200
    assert new_client(demo_app, "10.0.0.2").post("/api/demo-login").status_code == 200
    assert new_client(demo_app, "10.0.0.3").post("/api/demo-login").status_code == 503


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
        db.session.add(AiCall(user_id=old_demo, kind="recipe"))
        db.session.get(User, old_demo).created_at = long_ago
        db.session.commit()
        assert all(counts(old_demo)[:-1])

    result = demo_app.test_cli_runner().invoke(args=["purge-demo-users"])
    assert result.exit_code == 0 and "1개" in result.output

    with demo_app.app_context():
        assert db.session.get(User, old_demo) is None
        assert counts(old_demo) == [0] * len(USER_TABLES)
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
