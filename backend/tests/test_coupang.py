import json
from datetime import UTC, datetime, timedelta

import pytest
import requests

from app import coupang
from app.models import AiCall, db, utcnow
from app.outbound import FetchError
from tests.test_outbound import response

PLAIN = "https://www.coupang.com/np/search?q=%EB%8C%80%ED%8C%8C"  # storeLinks.ts가 만드는 모양(대파)
SHORT = "https://link.coupang.com/a/abc123"
GO = "/api/shop-links/coupang/go"


@pytest.fixture(autouse=True)
def empty_cache():
    coupang._cache.clear()
    yield
    coupang._cache.clear()


@pytest.fixture
def keys(app):
    app.config.update(COUPANG_ACCESS_KEY="test-access", COUPANG_SECRET_KEY="test-secret")


@pytest.fixture
def fake_deeplink(monkeypatch):
    calls = []

    def _fake(result=SHORT):
        def deeplink(plain, access, secret):
            calls.append((plain, access, secret))
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(coupang, "deeplink", deeplink)
        return calls

    return _fake


def go(client, url=PLAIN):
    return client.get(GO, query_string={"url": url})


def test_authorization_matches_documented_hmac():
    # 문서(Creating HMAC Signature): signed-date(yyMMdd'T'HHmmss'Z') + method + path + query → HmacSHA256 hex.
    # 기대값은 이 코드가 아니라 openssl로 따로 계산했다:
    # printf '%s' "260915T010203ZPOST/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink" | openssl dgst -sha256 -hmac test-secret
    now = datetime(2026, 9, 15, 1, 2, 3, tzinfo=UTC)
    header = coupang.authorization("test-access", "test-secret", "POST", coupang.DEEPLINK_PATH, now=now)
    assert header == (
        "CEA algorithm=HmacSHA256, access-key=test-access, signed-date=260915T010203Z, "
        "signature=89ba557a6e32614c173b665d0207fb0441aaf9e2605a61a78bfe4771de9bc57b"
    )


def test_deeplink_posts_signed_json_to_fixed_host(monkeypatch):
    sent = []

    def send(self, request, **kwargs):
        sent.append((request.method, request.url, dict(request.headers), json.loads(request.body), kwargs))
        body = {"rCode": "0", "rMessage": "", "data": [{"originalUrl": PLAIN, "shortenUrl": SHORT, "landingUrl": "x"}]}
        return response(200, json.dumps(body).encode(), {"Content-Type": "application/json"})

    monkeypatch.setattr(requests.Session, "send", send)
    assert coupang.deeplink(PLAIN, "test-access", "test-secret") == SHORT
    method, url, headers, body, kwargs = sent[0]
    assert (method, url, body) == ("POST", "https://api-gateway.coupang.com" + coupang.DEEPLINK_PATH, {"coupangUrls": [PLAIN]})
    assert headers["Authorization"].startswith("CEA algorithm=HmacSHA256, access-key=test-access, signed-date=")
    assert "test-secret" not in headers["Authorization"]
    assert kwargs["allow_redirects"] is False and kwargs["proxies"] == {}


@pytest.mark.parametrize(
    "body",
    [
        {"rCode": "1", "rMessage": "error"},
        {"rCode": "0", "data": []},
        {"rCode": "0", "data": [{"shortenUrl": "https://evil.example.com/a"}]},
        {"rCode": "0", "data": [{"shortenUrl": "http://link.coupang.com/a/x"}]},
    ],
)
def test_deeplink_rejects_bad_responses(monkeypatch, body):
    monkeypatch.setattr(requests.Session, "send", lambda self, request, **kwargs: response(200, json.dumps(body).encode(), {}))
    with pytest.raises((ValueError, IndexError, KeyError)):
        coupang.deeplink(PLAIN, "a", "b")


def test_go_requires_login(client):
    assert go(client).status_code == 401


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://www.coupang.com/np/search?q=a",
        "https://coupang.com/np/search?q=a",
        "https://www.coupang.com.evil.com/np/search?q=a",
        "https://a@www.coupang.com/np/search?q=a",
        "https://www.coupang.com:444/np/search?q=a",
        "https://www.coupang.com/vp/products/1",
        "https://www.coupang.com/np/search",
        "https://www.coupang.com/np/search?q=",
        "https://www.coupang.com/np/search?q=a&q=b",
        "https://www.coupang.com/np/search?q=a&next=https://evil.example.com",
        "https://www.coupang.com/np/search?q=a&sorter=evil",
        "https://www.coupang.com/np/search?q=a#x",
        "https://www.coupang.com/np/search?q=" + "가" * 51,
    ],
)
def test_go_rejects_other_urls(client, login, keys, fake_deeplink, url):
    calls = fake_deeplink()
    login()
    assert go(client, url).status_code == 400
    assert calls == []


def test_go_without_keys_redirects_to_plain(client, login, app, fake_deeplink):
    calls = fake_deeplink()
    login()
    res = go(client, "https://www.coupang.com/np/search?q=%EB%8C%80%ED%8C%8C&sorter=salePriceAsc")
    assert (res.status_code, res.headers["Location"]) == (302, PLAIN + "&sorter=salePriceAsc")
    assert calls == []
    app.config.update(COUPANG_ACCESS_KEY="only-one")
    assert go(client).headers["Location"] == PLAIN
    assert calls == []


def test_go_redirects_to_affiliate_link_and_caches(client, login, app, keys, fake_deeplink):
    calls = fake_deeplink()
    user = login()
    res = go(client)
    assert (res.status_code, res.headers["Location"], res.headers["Cache-Control"]) == (302, SHORT, "no-store")
    assert go(client).headers["Location"] == SHORT
    assert calls == [(PLAIN, "test-access", "test-secret")]  # 두 번째는 기억한 링크
    with app.app_context():
        assert [(c.user_id, c.kind, c.model) for c in AiCall.query.all()] == [(user.id, "shop_link", None)]


@pytest.mark.parametrize("error", [FetchError("TooSlow"), ValueError("rCode"), KeyError("data")])
def test_go_api_error_falls_back_to_plain(client, login, keys, fake_deeplink, caplog, error):
    calls = fake_deeplink(error)
    login()
    assert go(client).headers["Location"] == PLAIN
    assert go(client).headers["Location"] == PLAIN
    assert len(calls) == 2  # 실패는 기억하지 않는다
    assert type(error).__name__ in caplog.text
    assert "test-secret" not in caplog.text and "coupang.com/np" not in caplog.text


def test_go_budget_falls_back_to_plain(client, login, app, keys, fake_deeplink):
    calls = fake_deeplink()
    user = login()
    now = utcnow()
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="shop_link", created_at=now - timedelta(hours=2)) for _ in range(20)])
        db.session.add_all([AiCall(user_id=user.id, kind="shop_link", created_at=now - timedelta(minutes=5)) for _ in range(10)])
        db.session.commit()
    assert go(client).headers["Location"] == PLAIN  # 사용자 1시간 10번
    assert calls == []

    other = login("2")
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="shop_link", created_at=now) for _ in range(coupang.GLOBAL_HOURLY - 10)])
        db.session.commit()
    assert go(client).headers["Location"] == PLAIN  # 전체 1시간 80번
    with app.app_context():
        assert AiCall.query.filter_by(user_id=other.id).count() == 0
    assert calls == []


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(coupang, "CACHE_SIZE", 2)
    for i in range(3):
        coupang._remember(f"u{i}", f"s{i}")
    assert (coupang._cached("u0"), coupang._cached("u1"), coupang._cached("u2")) == (None, "s1", "s2")
    monkeypatch.setattr(coupang, "CACHE_SECONDS", -1)
    coupang._remember("u3", "s3")
    assert coupang._cached("u3") is None  # 24시간 지난 링크


def test_me_shop_affiliates_needs_both_keys(client, app):
    assert client.post("/api/dev-login").get_json()["shop_affiliates"] == {}
    app.config.update(COUPANG_PARTNERS_ID="AF123", COUPANG_ACCESS_KEY="a")
    assert client.get("/api/me").get_json()["shop_affiliates"] == {}
    app.config.update(COUPANG_SECRET_KEY="s")
    assert client.get("/api/me").get_json()["shop_affiliates"] == {"coupang": True}  # 키·트래킹 코드는 넘기지 않는다

