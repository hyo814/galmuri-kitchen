import pytest
from authlib.integrations.base_client import OAuthError

from app.models import User


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


@pytest.fixture
def oauth_app(make_app):
    # app context를 붙잡지 않는다: 요청마다 새 세션을 써야 commit 누락이 테스트에서 드러난다 (conftest의 app 픽스처와 같은 이유)
    return make_app(
        KAKAO_CLIENT_ID="kid",
        KAKAO_CLIENT_SECRET="ksecret",
        GOOGLE_CLIENT_ID="gid",
        GOOGLE_CLIENT_SECRET="gsecret",
        NAVER_CLIENT_ID="nid",
        NAVER_CLIENT_SECRET="nsecret",
    )


def oauth_client(app, name):
    return app.extensions["recipe_oauth"].create_client(name)


def test_auth_options_lists_configured_providers(oauth_app):
    assert oauth_app.test_client().get("/api/auth-options").get_json()["providers"] == ["kakao", "naver", "google"]


def test_unconfigured_provider_is_404(client):
    assert client.get("/auth/login/kakao").status_code == 404
    assert client.get("/auth/login/naver").status_code == 404
    assert client.get("/auth/login/apple").status_code == 404


def test_kakao_login_redirects_to_kakao(oauth_app):
    res = oauth_app.test_client().get("/auth/login/kakao")
    assert res.status_code == 302
    assert res.location.startswith("https://kauth.kakao.com/oauth/authorize")
    assert "client_id=kid" in res.location


def test_kakao_callback_logs_in(oauth_app, monkeypatch):
    kakao = oauth_client(oauth_app, "kakao")
    monkeypatch.setattr(kakao, "authorize_access_token", lambda: {"access_token": "t"})
    monkeypatch.setattr(
        kakao, "get", lambda url, token: FakeResponse({"id": 42, "properties": {"nickname": "냉장고왕"}})
    )
    c = oauth_app.test_client()
    res = c.get("/auth/callback/kakao")
    assert res.status_code == 302
    assert res.location == "/"
    assert c.get("/api/me").get_json()["nickname"] == "냉장고왕"
    with oauth_app.app_context():
        assert User.query.filter_by(provider="kakao", provider_id="42").count() == 1


def test_naver_login_redirects_to_naver(oauth_app):
    res = oauth_app.test_client().get("/auth/login/naver")
    assert res.status_code == 302
    assert res.location.startswith("https://nid.naver.com/oauth2.0/authorize")
    assert "client_id=nid" in res.location


def test_naver_callback_logs_in(oauth_app, monkeypatch):
    naver = oauth_client(oauth_app, "naver")
    monkeypatch.setattr(naver, "authorize_access_token", lambda: {"access_token": "t"})
    calls = []

    def get(url, token):
        calls.append(url)
        return FakeResponse({"resultcode": "00", "response": {"id": "n-abc", "nickname": "네이버요리사"}})

    monkeypatch.setattr(naver, "get", get)
    c = oauth_app.test_client()
    assert c.get("/auth/callback/naver").location == "/"
    assert calls == ["v1/nid/me"]
    assert c.get("/api/me").get_json()["nickname"] == "네이버요리사"
    with oauth_app.app_context():
        assert User.query.filter_by(provider="naver", provider_id="n-abc").count() == 1


def test_naver_callback_without_id_fails(oauth_app, monkeypatch):
    naver = oauth_client(oauth_app, "naver")
    monkeypatch.setattr(naver, "authorize_access_token", lambda: {"access_token": "t"})
    monkeypatch.setattr(naver, "get", lambda url, token: FakeResponse({"resultcode": "024", "message": "Authentication failed"}))
    assert oauth_app.test_client().get("/auth/callback/naver").location == "/?login_error=1"


def test_naver_userinfo_non_json_fails(oauth_app, monkeypatch):
    naver = oauth_client(oauth_app, "naver")
    monkeypatch.setattr(naver, "authorize_access_token", lambda: {"access_token": "t"})

    class NotJson:
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(naver, "get", lambda url, token: NotJson())
    assert oauth_app.test_client().get("/auth/callback/naver").location == "/?login_error=1"


def test_callback_state_mismatch_fails(oauth_app):
    # 로그인 시작 없이 콜백만 오면 세션에 state가 없어 CSRF 검증에서 막힌다
    res = oauth_app.test_client().get("/auth/callback/naver?code=x&state=forged")
    assert res.location == "/?login_error=1"


def test_google_callback_logs_in(oauth_app, monkeypatch):
    google = oauth_client(oauth_app, "google")
    monkeypatch.setattr(google, "authorize_access_token", lambda: {"userinfo": {"sub": "g-1", "name": "구글사용자"}})
    c = oauth_app.test_client()
    assert c.get("/auth/callback/google").location == "/"
    assert c.get("/api/me").get_json()["nickname"] == "구글사용자"


def test_callback_error_redirects_with_flag(oauth_app, monkeypatch, caplog):
    kakao = oauth_client(oauth_app, "kakao")

    def denied():
        raise OAuthError(error="access_denied")

    monkeypatch.setattr(kakao, "authorize_access_token", denied)
    with caplog.at_level("WARNING"):
        res = oauth_app.test_client().get("/auth/callback/kakao")
    assert res.location == "/?login_error=1"
    assert any("kakao" in r.message and "callback failed" in r.message for r in caplog.records)
