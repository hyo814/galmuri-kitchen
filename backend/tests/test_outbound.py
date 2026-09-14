import io
import json
import socket

import pytest
import requests
import urllib3.connection

from app import outbound
from app.outbound import FetchError

REAL_SEND = requests.Session.send  # 차단 픽스처가 바꾸기 전
VIDEO_ID = "dQw4w9WgXcQ"
HTML = {"Content-Type": "text/html; charset=utf-8"}


def response(status=200, body=b"", headers=None):
    res = requests.Response()
    res.status_code = status
    res.headers.update(HTML if headers is None else headers)
    res.raw = io.BytesIO(body)
    return res


def fail_if_called(*args, **kwargs):
    raise AssertionError("요청하면 안 돼요")


def fake_dns(monkeypatch, table):
    """table: 호스트 → IP 목록. 부른 호스트를 돌려준다."""
    asked = []

    def getaddrinfo(host, port, *args, **kwargs):
        asked.append(host)
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port, 0, 0) if ":" in ip else (ip, port))
            for ip in table[host]
        ]

    monkeypatch.setattr(outbound.socket, "getaddrinfo", getaddrinfo)
    return asked


def fake_send(monkeypatch, responses):
    """requests.Session.send를 가짜로. 보낸 (url, kwargs, 헤더)를 돌려준다."""
    sent = []

    def send(self, request, **kwargs):
        sent.append((request.url, kwargs, dict(request.headers)))
        return responses.pop(0)

    monkeypatch.setattr(requests.Session, "send", send)
    return sent


# --- parse_link ---


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://youtu.be/dQw4w9WgXcQ?si=x", ("youtube", VIDEO_ID)),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10", ("youtube", VIDEO_ID)),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", ("youtube", VIDEO_ID)),
        ("  http://youtube.com/watch?v=dQw4w9WgXcQ ", ("youtube", VIDEO_ID)),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", ("youtube", VIDEO_ID)),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", ("youtube", VIDEO_ID)),
        ("https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=1", ("instagram", "C1a2B3c4D5e")),
        ("http://instagram.com/p/C1a2B3c4D5e/", ("instagram", "C1a2B3c4D5e")),
        ("https://blog.naver.com/cook/2231", ("web", "https://m.blog.naver.com/cook/2231")),
        ("https://recipe.example.com/a", ("web", "https://recipe.example.com/a")),
        ("https://www.youtube.com/watch?v=short", None),
        ("https://www.youtube.com/@channel", None),
        ("https://www.instagram.com/p/abc/", None),
        ("http://recipe.example.com/a", None),
        ("javascript:alert(1)", None),
        ("ftp://youtu.be/dQw4w9WgXcQ", None),
        ("https://", None),
        ("https://recipe.example.com/" + "a" * 474, None),  # 501자
        (None, None),
        (123, None),
    ],
)
def test_parse_link(value, expected):
    assert outbound.parse_link(value) == expected


# --- fetch_fixed ---


def test_fetch_fixed_refuses_other_hosts_and_redirects(monkeypatch):
    monkeypatch.setattr(requests, "get", fail_if_called)
    for url in ("https://evil.example.com/", "http://www.youtube.com/", "https://www.youtube.com.evil.com/"):
        with pytest.raises(FetchError):
            outbound.fetch_fixed(url)

    seen = []

    def get(url, **kwargs):
        seen.append((url, kwargs))
        return response(302, headers={"Location": "https://evil.example.com/"})

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(FetchError):
        outbound.fetch_fixed("https://www.instagram.com/p/C1a2B3c4D5e/")
    assert seen[0][1]["allow_redirects"] is False
    assert seen[0][1]["headers"]["User-Agent"] == "galmuri-kitchen/1.0"


def test_request_exception_message_has_no_key(monkeypatch):
    def broken(url, **kwargs):
        raise requests.ConnectionError("https://www.googleapis.com/youtube/v3/videos?key=SECRET")

    monkeypatch.setattr(requests, "get", broken)
    with pytest.raises(FetchError) as caught:
        outbound.video_snippet(VIDEO_ID, "SECRET")
    assert "SECRET" not in str(caught.value) and str(caught.value) == "ConnectionError"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


# --- fetch_public_page ---


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://a@example.com/",
        "https://a:b@example.com/",
        "https://example.com:8443/",
        "https://example.com:bad/",
        "https:///path",
        "https://" + "a" * 250 + ".com/",
    ],
)
def test_fetch_public_page_refuses_bad_urls(monkeypatch, url):
    monkeypatch.setattr(outbound.socket, "getaddrinfo", fail_if_called)
    monkeypatch.setattr(requests.Session, "send", fail_if_called)
    with pytest.raises(FetchError):
        outbound.fetch_public_page(url)


@pytest.mark.parametrize(
    "ips",
    [["127.0.0.1"], ["10.0.0.5"], ["169.254.169.254"], ["192.168.0.2"], ["172.16.3.4"], ["100.64.0.1"], ["::1"], ["fd00::1"], ["::ffff:127.0.0.1"], ["93.184.216.34", "10.0.0.5"], []],
)
def test_fetch_public_page_refuses_private_dns(monkeypatch, ips):
    fake_dns(monkeypatch, {"recipe.example.com": ips})
    monkeypatch.setattr(requests.Session, "send", fail_if_called)
    with pytest.raises(FetchError):
        outbound.fetch_public_page("https://recipe.example.com/a")


def test_fetch_public_page_dns_error_is_fetch_error(monkeypatch):
    def gaierror(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(outbound.socket, "getaddrinfo", gaierror)
    with pytest.raises(FetchError):
        outbound.fetch_public_page("https://nope.example.com/")


def test_public_session_checks_peer_and_ignores_proxy_env():
    session = outbound.public_session()
    assert session.trust_env is False
    pool = session.get_adapter("https://recipe.example.com/").poolmanager.connection_from_url("https://recipe.example.com/")
    assert pool.ConnectionCls is outbound.PublicOnlyHTTPSConnection


class FakeSocket:
    def __init__(self, ip):
        self.ip, self.closed = ip, False

    def getpeername(self):
        return (self.ip, 443)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("ip", ["10.0.0.1", "127.0.0.1", "::1", "169.254.169.254"])
def test_public_only_connection_checks_peer(monkeypatch, ip):
    """DNS 검사 뒤 주소가 바뀌어도(재바인딩) 연결된 소켓의 상대 주소를 보고 TLS·헤더를 보내기 전에 끊는다."""
    sock = FakeSocket(ip)
    monkeypatch.setattr(urllib3.connection.HTTPConnection, "_new_conn", lambda self: sock)
    monkeypatch.setattr(urllib3.connection, "_ssl_wrap_socket_and_match_hostname", fail_if_called)
    with pytest.raises(FetchError):
        outbound.PublicOnlyHTTPSConnection("recipe.example.com", 443).connect()
    assert sock.closed


def test_fetch_public_page_rebinding_stops_before_sending(monkeypatch):
    """DNS 검사는 공인 IP였지만 실제 연결은 사설 IP: 진짜 requests·urllib3 경로에서 요청을 보내기 전에 FetchError(재시도 없음)."""
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    monkeypatch.setattr(requests.Session, "send", REAL_SEND)
    sockets = []

    def new_conn(self):
        sockets.append(FakeSocket("10.0.0.1"))
        return sockets[-1]

    monkeypatch.setattr(urllib3.connection.HTTPConnection, "_new_conn", new_conn)
    monkeypatch.setattr(urllib3.connection, "_ssl_wrap_socket_and_match_hostname", fail_if_called)
    with pytest.raises(FetchError):
        outbound.fetch_public_page("https://recipe.example.com/a")
    assert len(sockets) == 1 and sockets[0].closed


def test_public_only_connection_allows_public_peer(monkeypatch):
    sock = FakeSocket("93.184.216.34")
    monkeypatch.setattr(urllib3.connection.HTTPConnection, "_new_conn", lambda self: sock)
    assert outbound.PublicOnlyHTTPSConnection("recipe.example.com", 443)._new_conn() is sock
    assert not sock.closed


def test_fetch_public_page_revalidates_redirects(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    asked = fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"], "internal.example": ["10.0.0.9"], "cdn.example.com": ["2606:2800:220:1:248:1893:25c8:1946"]})

    # 사설 주소로 가는 리다이렉트 → 따라가지 않는다
    sent = fake_send(monkeypatch, [response(302, headers={"Location": "https://internal.example/"})])
    with pytest.raises(FetchError):
        outbound.fetch_public_page("https://recipe.example.com/a")
    assert len(sent) == 1 and asked == ["recipe.example.com", "internal.example"]
    url, kwargs, headers = sent[0]
    assert (kwargs["allow_redirects"], kwargs["proxies"], headers["User-Agent"]) == (False, {}, "galmuri-kitchen/1.0")

    # 공인 주소 → 따라가고, 상대 경로는 같은 호스트로
    sent = fake_send(
        monkeypatch,
        [
            response(301, headers={"Location": "https://cdn.example.com/b"}),
            response(308, headers={"Location": "/c?x=1"}),
            response(200, "<p>본문</p>".encode("euc-kr"), {"Content-Type": "text/html; charset=EUC-KR"}),
        ],
    )
    body, encoding, final_url = outbound.fetch_public_page("https://recipe.example.com/a")
    assert [s[0] for s in sent] == ["https://recipe.example.com/a", "https://cdn.example.com/b", "https://cdn.example.com/c?x=1"]
    assert (body.decode(encoding), final_url) == ("<p>본문</p>", "https://cdn.example.com/c?x=1")

    # 리다이렉트는 3번까지
    fake_send(monkeypatch, [response(302, headers={"Location": f"/r{i}"}) for i in range(4)] + [response(200, b"<p>x</p>")])
    with pytest.raises(FetchError):
        outbound.fetch_public_page("https://recipe.example.com/a")
    fake_send(monkeypatch, [response(302, headers={"Location": f"/r{i}"}) for i in range(3)] + [response(200, b"<p>x</p>")])
    assert outbound.fetch_public_page("https://recipe.example.com/a")[2] == "https://recipe.example.com/r2"

    # Location 없음, http로 내려가는 리다이렉트, 200이 아닌 응답
    for res in (response(302, headers={}), response(302, headers={"Location": "http://recipe.example.com/"}), response(404)):
        fake_send(monkeypatch, [res])
        with pytest.raises(FetchError):
            outbound.fetch_public_page("https://recipe.example.com/a")


def test_fetch_public_page_requires_html_and_caps_size_time(monkeypatch):
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    page = "https://recipe.example.com/a"

    fake_send(monkeypatch, [response(200, b"{}", {"Content-Type": "application/json"})])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(page)

    fake_send(monkeypatch, [response(200, b"<p>ok</p>", {"Content-Type": "text/html"})])
    assert outbound.fetch_public_page(page)[:2] == (b"<p>ok</p>", None)  # charset이 없으면 None

    monkeypatch.setattr(outbound, "MAX_BYTES", 10)
    fake_send(monkeypatch, [response(200, b"x" * 20)])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(page)
    fake_send(monkeypatch, [response(200, b"x" * 10)])
    assert outbound.fetch_public_page(page)[0] == b"x" * 10

    monkeypatch.setattr(outbound, "MAX_BYTES", 1_000_000)
    calls = []

    def clock():
        calls.append(1)
        return 0 if len(calls) == 1 else 9  # 시작 뒤 9초

    monkeypatch.setattr(outbound.time, "monotonic", clock)
    fake_send(monkeypatch, [response(200, b"<p>slow</p>")])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(page)


def test_network_is_blocked_without_fakes():
    """가짜를 깜빡하면 FetchError로 조용히 넘어가지 않고 차단 픽스처의 AssertionError가 난다."""
    with pytest.raises(AssertionError):
        outbound.fetch_public_page("https://recipe.example.com/a")
    with pytest.raises(AssertionError):
        outbound.fetch_fixed("https://www.instagram.com/p/C1a2B3c4D5e/")


# --- video_snippet · instagram_post · web_page ---


def test_video_snippet_builds_fixed_url_and_parses(monkeypatch):
    seen = []
    snippet = {
        "title": "제육볶음 황금레시피",
        "description": "재료: 돼지고기 600g",
        "channelTitle": "집밥 연구소",
        "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/x/default.jpg"}, "high": {"url": "https://i.ytimg.com/vi/x/hq.jpg"}},
    }
    bodies = [{"items": [{"snippet": snippet}]}, {"items": []}, {"items": [{"snippet": {"title": 3, "thumbnails": {"high": {"url": "http://x/y.jpg"}}}}]}]

    def get(url, **kwargs):
        seen.append((url, kwargs["params"]))
        return response(200, json.dumps(bodies.pop(0)).encode(), {"Content-Type": "application/json; charset=UTF-8"})

    monkeypatch.setattr(requests, "get", get)
    assert outbound.video_snippet(VIDEO_ID, "k") == {
        "title": "제육볶음 황금레시피",
        "description": "재료: 돼지고기 600g",
        "channel_title": "집밥 연구소",
        "thumbnail_url": "https://i.ytimg.com/vi/x/hq.jpg",
    }
    assert seen[0] == ("https://www.googleapis.com/youtube/v3/videos", {"part": "snippet", "id": VIDEO_ID, "key": "k"})
    assert outbound.video_snippet(VIDEO_ID, "k") is None
    assert outbound.video_snippet(VIDEO_ID, "k") == {"title": "", "description": "", "channel_title": "", "thumbnail_url": None}

    monkeypatch.setattr(requests, "get", lambda url, **kwargs: response(200, b"not json"))
    with pytest.raises(FetchError):
        outbound.video_snippet(VIDEO_ID, "k")


def test_instagram_post_reads_og_tags(monkeypatch):
    seen = []
    pages = [
        b'<html><head><meta property="og:title" content="cook on Instagram: &quot;\xec\xb0\xb8\xec\xb9\x98\xeb\xa7\x88\xec\x9a\x94&quot;">'
        b'<meta property="og:description" content="&quot;\xec\xb4\x88\xea\xb0\x84\xeb\x8b\xa8&quot; \xec\x9e\xac\xeb\xa3\x8c: \xeb\xb0\xa5">'
        b'<meta property="og:image" content="https://scontent.cdninstagram.com/a.jpg?x=1&amp;y=2"></head></html>',
        b"<html><head><title>Login</title></head></html>",
    ]

    def get(url, **kwargs):
        seen.append(url)
        return response(200, pages.pop(0))

    monkeypatch.setattr(requests, "get", get)
    assert outbound.instagram_post("C1a2B3c4D5e") == {
        "caption": '"초간단" 재료: 밥',
        "title": 'cook on Instagram: "참치마요"',
        "thumbnail_url": "https://scontent.cdninstagram.com/a.jpg?x=1&y=2",
    }
    assert seen == ["https://www.instagram.com/p/C1a2B3c4D5e/"]
    assert outbound.instagram_post("C1a2B3c4D5e") is None


def test_web_page_extracts_title_site_and_text(monkeypatch):
    pages = [
        (
            "<html><head><title>무시</title><meta property='og:title' content='제육볶음 만들기'><meta property='og:site_name' content='요리 블로그'>"
            "<style>.a{color:red}</style><script>alert('지시')</script></head><body><nav>메뉴 홈</nav><header>머리</header>"
            "<h1>제육볶음</h1><p>재료:   돼지고기 600g</p>\n\n\n<ul><li>양파 1개</li><li>대파</li></ul><form>댓글 쓰기</form><footer>꼬리</footer></body></html>",
            "https://recipe.example.com/final",
        ),
        ("<html><head><title> 두부조림 </title></head><body><p>" + "가" * 12_000 + "</p></body></html>", "https://Cook.Example.com/x"),
    ]

    def fetch(url):
        html, final = pages.pop(0)
        return html.encode(), "utf-8", final

    monkeypatch.setattr(outbound, "fetch_public_page", fetch)
    assert outbound.web_page("https://recipe.example.com/a") == {
        "title": "제육볶음 만들기",
        "site_name": "요리 블로그",
        "text": "제육볶음\n재료: 돼지고기 600g\n양파 1개\n대파",
        "url": "https://recipe.example.com/final",
    }
    second = outbound.web_page("https://cook.example.com/x")
    assert (second["title"], second["site_name"], len(second["text"])) == ("두부조림", "cook.example.com", 10_000)
