import hashlib
import hmac
import io
import os
from datetime import datetime, time, timedelta, timezone

import pytest

from app import ai, demo, outbound, scan
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
from tests.test_shopping_notes import add_note, photo_path, upload

USER_TABLES = (Ingredient, StorageLocation, ItemRule, Staple, Recipe, Seasoning, AiCall)


@pytest.fixture
def demo_app(make_app):
    return make_app(DEMO_LOGIN=True, DEV_MODE=False)


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


def test_normal_user_ignores_demo_budget(client, login, app, fake_anthropic):
    login()
    app.config.update(ANTHROPIC_API_KEY="test-key", DEMO_AI_GLOBAL_DAILY=1)
    use_demo_budget(app, 3)
    assert client.get("/api/me").get_json()["scan"] == "on"


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


TOO_MANY = (429, {"error": "체험하기를 너무 많이 눌렀어요. 잠시 후 다시 시도해주세요."})


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

    result = demo_app.test_cli_runner().invoke(args=["purge-demo-users"])
    assert result.exit_code == 0 and "1개" in result.output

    with demo_app.app_context():
        assert db.session.get(User, old_demo) is None
        assert counts(old_demo) == [0] * len(USER_TABLES)
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
