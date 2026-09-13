import pytest

from app import database_url
from app.auth import upsert_user
from app.models import User


def test_me_requires_login(client):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.get_json() == {"error": "로그인이 필요해요."}


def test_dev_login_then_me(client):
    assert client.post("/api/dev-login").status_code == 200
    assert client.get("/api/me").get_json()["nickname"] == "개발자"


def test_dev_login_reuses_same_user(client):
    first = client.post("/api/dev-login").get_json()["id"]
    second = client.post("/api/dev-login").get_json()["id"]
    assert first == second
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
