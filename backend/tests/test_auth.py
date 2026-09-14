import pytest

from app import create_app, database_url
from app.auth import upsert_user
from app.models import User, db
from tests.conftest import TEST_DATABASE_URL


def test_me_requires_login(client):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.get_json() == {"error": "로그인이 필요해요."}


def test_dev_login_then_me(client):
    assert client.post("/api/dev-login").status_code == 200
    me = client.get("/api/me").get_json()
    assert me["nickname"] == "개발자"
    assert me["provider"] == "dev"


def test_dev_login_reuses_same_user(client, app):
    first = client.post("/api/dev-login").get_json()["id"]
    second = client.post("/api/dev-login").get_json()["id"]
    assert first == second
    with app.app_context():
        assert User.query.count() == 1


def test_dev_login_hidden_without_dev_mode(make_app):
    c = make_app(DEV_MODE=False).test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    assert c.post("/api/dev-login").status_code == 404
    assert c.get("/api/auth-options").get_json() == {"providers": [], "dev_login": False}


def test_logout_clears_session(client):
    client.post("/api/dev-login")
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_mutation_without_fetch_header_rejected(raw_client):
    res = raw_client.post("/api/dev-login")
    assert res.status_code == 400
    assert res.get_json() == {"error": "잘못된 요청이에요."}


def test_unknown_api_route_is_json_404(client):
    res = client.get("/api/nope")
    assert res.status_code == 404
    assert res.get_json() == {"error": "찾을 수 없어요."}


def test_upsert_user_updates_nickname(app):
    with app.app_context():
        first = upsert_user("kakao", "1", "옛이름")
        second = upsert_user("kakao", "1", "새이름")
        assert first.id == second.id
        assert second.nickname == "새이름"
        assert upsert_user("kakao", "2", None).nickname == "사용자"


def test_database_url_normalizes_render_postgres():
    assert database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("sqlite:///dev.sqlite3") == "sqlite:///dev.sqlite3"


def test_secret_key_required(make_app):
    with pytest.raises(RuntimeError):
        make_app(SECRET_KEY=None)


def test_dev_mode_refused_on_render(make_app, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError):
        make_app()


def test_blank_ai_env_values_fall_back_to_defaults(monkeypatch):
    # 배포 환경에서 값이 비어있는 채로 설정된 경우("") os.environ.get(...)의
    # 기본값은 적용되지 않으므로, 빈 문자열은 명시적으로 걸러내야 한다.
    monkeypatch.setenv("SECRET_KEY", "test")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("CLAUDE_MODEL", "")
    monkeypatch.setenv("AI_DAILY_SCAN_LIMIT", "")
    monkeypatch.setenv("AI_SCAN_BURST_LIMIT", "")

    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": database_url(TEST_DATABASE_URL),
        "SESSION_COOKIE_SECURE": False,
    })

    assert app.config["ANTHROPIC_API_KEY"] is None
    assert app.config["CLAUDE_MODEL"] == "claude-sonnet-5"
    assert app.config["AI_DAILY_SCAN_LIMIT"] == 10
    assert app.config["AI_SCAN_BURST_LIMIT"] == 3

    with app.app_context():
        db.create_all()
        try:
            client = app.test_client()
            client.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
            dev = client.post("/api/dev-login").get_json()
            assert (dev["scan"], dev["scan_limit"]) == ("sample", 10)
        finally:
            db.session.remove()
            db.engine.dispose()


def test_me_reports_scan_mode_and_limit(client, app):
    dev = client.post("/api/dev-login").get_json()
    assert (dev["scan"], dev["scan_limit"]) == ("sample", 10)
    assert client.get("/api/me").get_json()["scan"] == "sample"
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_DAILY_SCAN_LIMIT=5)
    me = client.get("/api/me").get_json()
    assert (me["scan"], me["scan_limit"]) == ("on", 5)
    app.config.update(ANTHROPIC_API_KEY=None, DEV_MODE=False)
    assert client.get("/api/me").get_json()["scan"] == "off"


def test_me_includes_recipe_limit(client, app):
    assert client.post("/api/dev-login").get_json()["recipe_limit"] == 10
    app.config["AI_DAILY_RECIPE_LIMIT"] = 4
    assert client.get("/api/me").get_json()["recipe_limit"] == 4


def test_me_includes_videos_mode(client, app):
    assert client.post("/api/dev-login").get_json()["videos"] == "sample"
    app.config["YOUTUBE_API_KEY"] = "k"
    assert client.get("/api/me").get_json()["videos"] == "on"
    app.config.update(YOUTUBE_API_KEY=None, DEV_MODE=False)
    assert client.get("/api/me").get_json()["videos"] == "off"


def test_me_includes_shop_affiliates(client, app):
    assert client.post("/api/dev-login").get_json()["shop_affiliates"] == {}
    app.config["COUPANG_PARTNERS_ID"] = "AF123"
    assert client.get("/api/me").get_json()["shop_affiliates"] == {"coupang": "AF123"}


def test_coupang_partners_id_from_env(make_app, monkeypatch):
    monkeypatch.setenv("COUPANG_PARTNERS_ID", "")
    assert make_app().config["COUPANG_PARTNERS_ID"] is None
    monkeypatch.setenv("COUPANG_PARTNERS_ID", "AF123")
    assert make_app().config["COUPANG_PARTNERS_ID"] == "AF123"
