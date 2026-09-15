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
def empty_cache(monkeypatch):
    coupang._cache.clear()
    monkeypatch.setattr(coupang, "_paused_until", 0.0)
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


def deeplink_response(body):
    return lambda self, request, **kwargs: response(200, json.dumps(body).encode(), {})


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
    assert kwargs["timeout"][1] <= coupang.TIMEOUT_SECONDS  # 3초 제한이 requests까지 간다(넘으면 감시 타이머가 끊는다)


@pytest.mark.parametrize(
    "body",
    [
        {"rCode": "1", "rMessage": "error"},
        {"rCode": "0", "data": []},
        {"rCode": "0", "data": [{"shortenUrl": "https://evil.example.com/a"}]},
        {"rCode": "0", "data": [{"shortenUrl": "http://link.coupang.com/a/x"}]},
        {"rCode": "0", "data": [{"shortenUrl": "https://evil.com\\.coupang.com/a"}]},  # urlsplit 호스트는 *.coupang.com, 브라우저는 evil.com
        {"rCode": "0", "data": [{"shortenUrl": "https://link.coupang.com/a/x\r\nSet-Cookie: a=b"}]},
        {"rCode": "0", "data": [{"shortenUrl": "https://link.coupang.com:8443/a/x"}]},
        {"rCode": "0", "data": [{"shortenUrl": "https://link.coupang.com/a/x?next=https://evil.com"}]},
        {"rCode": "0", "data": [{"shortenUrl": "https://evil.coupang.com/a/x"}]},
        {"rCode": "0", "data": [{"shortenUrl": 123}]},
    ],
)
def test_deeplink_rejects_bad_responses(monkeypatch, body):
    monkeypatch.setattr(requests.Session, "send", deeplink_response(body))
    with pytest.raises((ValueError, IndexError, KeyError)):
        coupang.deeplink(PLAIN, "a", "b")


def test_go_without_login_redirects_to_plain(client, app, keys, fake_deeplink):
    calls = fake_deeplink()
    res = go(client)
    assert (res.status_code, res.headers["Location"]) == (302, PLAIN)
    assert go(client, "https://evil.example.com/np/search?q=a").status_code == 400
    assert calls == []
    with app.app_context():
        assert AiCall.query.count() == 0


def test_go_demo_user_gets_plain_without_api(client, login, app, keys, fake_deeplink):
    calls = fake_deeplink()
    user = login()
    with app.app_context():
        db.session.get(type(user), user.id).provider = "demo"
        db.session.commit()
    assert go(client).headers["Location"] == PLAIN
    assert client.get("/api/me").get_json()["shop_affiliates"] == {}  # 광고 표시도 없다
    assert calls == []
    with app.app_context():
        assert AiCall.query.count() == 0


def test_go_bad_shorten_url_end_to_end_falls_back_to_plain(client, login, app, keys, monkeypatch):
    body = {"rCode": "0", "data": [{"shortenUrl": "https://evil.com\\.coupang.com/a"}]}
    monkeypatch.setattr(requests.Session, "send", deeplink_response(body))
    login()
    res = go(client)
    assert (res.status_code, res.headers["Location"]) == (302, PLAIN)


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


@pytest.mark.parametrize(
    "error, paused",
    [(FetchError("TooSlow"), False), (KeyError("data"), False), (ValueError("rCode"), True), (FetchError("HTTP429"), True)],
)
def test_go_api_error_falls_back_to_plain_and_cools_down(client, login, app, keys, fake_deeplink, caplog, monkeypatch, error, paused):
    calls = fake_deeplink(error)
    user = login()
    assert go(client).headers["Location"] == PLAIN
    with app.app_context():
        assert [(c.user_id, c.kind) for c in AiCall.query.all()] == [(user.id, "shop_link")]  # 실패한 호출도 기록한다
    assert go(client).headers["Location"] == PLAIN
    assert len(calls) == 1  # 실패한 주소는 10분 동안 다시 부르지 않는다
    assert type(error).__name__ in caplog.text
    assert "test-secret" not in caplog.text and "coupang.com/np" not in caplog.text

    other = "https://www.coupang.com/np/search?q=%EB%91%90%EB%B6%80"
    assert go(client, other).headers["Location"] == other
    assert len(calls) == (1 if paused else 2)  # rCode·429 뒤에는 다른 주소도 10분 쉰다

    monkeypatch.setattr(coupang, "_paused_until", 0.0)
    coupang._cache.clear()
    assert go(client, other).headers["Location"] == other
    assert len(calls) == (2 if paused else 3)  # 쉬는 시간이 지나면 다시 부른다


def test_go_budget_falls_back_to_plain(client, login, app, keys, fake_deeplink):
    calls = fake_deeplink()
    user = login()
    now = utcnow()
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="shop_link", created_at=now - timedelta(hours=2)) for _ in range(20)])
        db.session.add_all([AiCall(user_id=user.id, kind="shop_link", created_at=now - timedelta(minutes=5)) for _ in range(9)])
        db.session.commit()
    assert go(client).headers["Location"] == SHORT  # 10번째 호출은 된다(1시간 안 9번 기록)
    coupang._cache.clear()
    assert go(client).headers["Location"] == PLAIN  # 11번째는 사용자 1시간 10번에 걸린다
    assert len(calls) == 1

    other = login("2")  # 이제 이 클라이언트는 다른 사용자
    with app.app_context():
        db.session.add_all([AiCall(user_id=user.id, kind="shop_link", created_at=now) for _ in range(coupang.GLOBAL_HOURLY - 11)])
        db.session.commit()  # 1시간 안 전체 79번
    coupang._cache.clear()
    assert go(client).headers["Location"] == SHORT  # 전체 80번째는 된다
    coupang._cache.clear()
    assert go(client).headers["Location"] == PLAIN  # 81번째는 전체 1시간 80번에 걸린다
    with app.app_context():
        assert AiCall.query.filter_by(user_id=other.id).count() == 1
    assert len(calls) == 2


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(coupang, "CACHE_SIZE", 2)
    for i in range(3):
        coupang._remember(f"u{i}", f"s{i}")
    assert (coupang._cached("u0"), coupang._cached("u1"), coupang._cached("u2")) == (None, "s1", "s2")
    coupang._remember("u3", "s3", seconds=-1)
    assert coupang._cached("u3") is None  # 24시간 지난 링크


def test_me_shop_affiliates_needs_both_keys(client, app):
    assert client.post("/api/dev-login").get_json()["shop_affiliates"] == {}
    app.config.update(COUPANG_PARTNERS_ID="AF123", COUPANG_ACCESS_KEY="a")
    assert client.get("/api/me").get_json()["shop_affiliates"] == {}
    app.config.update(COUPANG_SECRET_KEY="s")
    assert client.get("/api/me").get_json()["shop_affiliates"] == {"coupang": True}  # 키·트래킹 코드는 넘기지 않는다

