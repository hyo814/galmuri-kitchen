import io
import json
import socket
import time

import pytest
import requests
import urllib3.connection
import urllib3.util.connection

from app import outbound
from app.outbound import FetchError

REAL_SEND = requests.Session.send  # 차단 픽스처가 바꾸기 전
VIDEO_ID = "dQw4w9WgXcQ"
HTML = {"Content-Type": "text/html; charset=utf-8"}
PAGE = "https://recipe.example.com/a"


class Raw(io.BytesIO):
    """urllib3 응답처럼 read1(amt, decode_content=)을 받는다. 한 번에 최대 3바이트씩 준다."""

    def read1(self, amt=-1, decode_content=None):
        return super().read1(min(amt, 3))


def response(status=200, body=b"", headers=None):
    res = requests.Response()
    res.status_code = status
    res.headers.update(HTML if headers is None else headers)
    res.raw = Raw(body)
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
    """requests.Session.send를 가짜로. 보낸 (url, kwargs, 헤더)를 돌려준다. 예외를 넣으면 그 예외를 낸다."""
    sent = []

    def send(self, request, **kwargs):
        sent.append((request.url, kwargs, dict(request.headers)))
        res = responses.pop(0)
        if isinstance(res, Exception):
            raise res
        return res

    monkeypatch.setattr(requests.Session, "send", send)
    return sent


class FakeSocket:
    def __init__(self, ip):
        self.ip, self.closed, self.dups, self.shutdowns = ip, False, 0, 0

    def shutdown(self, how):
        self.shutdowns += 1

    def getpeername(self):
        return (self.ip, 443)

    def dup(self):
        self.dups += 1
        return FakeSocket(self.ip)

    def close(self):
        self.closed = True


# --- parse_link ---


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://youtu.be/dQw4w9WgXcQ?si=x", ("youtube", VIDEO_ID)),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10", ("youtube", VIDEO_ID)),
        ("https://www.youtube.com/watch/?v=dQw4w9WgXcQ", ("youtube", VIDEO_ID)),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=x", ("youtube", VIDEO_ID)),
        ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", ("youtube", VIDEO_ID)),
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


# --- 공인 주소 판별 ---


@pytest.mark.parametrize(
    "ip, public",
    [
        ("93.184.216.34", True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("100.64.0.1", False),
        ("::1", False),
        ("fd00::1", False),
        ("fe80::1%en0", False),
        ("::ffff:127.0.0.1", False),
        ("64:ff9b::a9fe:a9fe", False),  # NAT64 → 169.254.169.254
        ("64:ff9b:1::1", False),
        ("::7f00:1", False),  # IPv4 호환 → 127.0.0.1
        ("::ffff:0:a00:1", False),  # IPv4 변환 → 10.0.0.1
        ("fec0::1", False),  # 사이트 로컬
        ("2002:7f00:1::", False),  # 6to4
        ("224.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public(ip, public):
    assert outbound._is_public(ip) is public


# --- fetch_fixed ---


def test_fetch_fixed_refuses_other_hosts_and_redirects(monkeypatch):
    monkeypatch.setattr(requests.Session, "send", fail_if_called)
    for url in ("https://evil.example.com/", "http://www.youtube.com/", "https://www.youtube.com.evil.com/", "https://a@www.youtube.com/"):
        with pytest.raises(FetchError):
            outbound.fetch_fixed(url)

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    sent = fake_send(monkeypatch, [response(302, headers={"Location": "https://evil.example.com/"})])
    with pytest.raises(FetchError):
        outbound.fetch_fixed("https://www.instagram.com/p/C1a2B3c4D5e/")
    url, kwargs, headers = sent[0]
    assert (len(sent), kwargs["allow_redirects"], kwargs["proxies"], headers["User-Agent"]) == (1, False, {}, "galmuri-kitchen/1.0")


def test_request_exception_message_has_no_key(monkeypatch):
    fake_send(monkeypatch, [requests.ConnectionError("https://www.googleapis.com/youtube/v3/videos?key=SECRET")])
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
    [
        ["127.0.0.1"],
        ["10.0.0.5"],
        ["169.254.169.254"],
        ["192.168.0.2"],
        ["172.16.3.4"],
        ["100.64.0.1"],
        ["::1"],
        ["fd00::1"],
        ["::ffff:127.0.0.1"],
        ["64:ff9b::a9fe:a9fe"],
        ["93.184.216.34", "10.0.0.5"],
        [],
    ],
)
def test_fetch_public_page_refuses_private_dns(monkeypatch, ips):
    fake_dns(monkeypatch, {"recipe.example.com": ips})
    monkeypatch.setattr(requests.Session, "send", fail_if_called)
    with pytest.raises(FetchError):
        outbound.fetch_public_page(PAGE)


def test_fetch_public_page_dns_error_is_fetch_error(monkeypatch):
    def gaierror(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(outbound.socket, "getaddrinfo", gaierror)
    with pytest.raises(FetchError):
        outbound.fetch_public_page("https://nope.example.com/")


def test_adapter_uses_public_only_connection():
    adapter = outbound.PublicOnlyAdapter({"recipe.example.com": "93.184.216.34"})
    pool = adapter.poolmanager.connection_from_url(PAGE)
    assert issubclass(pool.ConnectionCls, outbound.PublicOnlyHTTPSConnection)
    assert pool.ConnectionCls.addresses == {"recipe.example.com": "93.184.216.34"}
    assert pool.ConnectionCls.adapter is adapter


def test_connection_after_watchdog_fired_is_closed(monkeypatch):
    """감시 타이머가 먼저 돌았으면 그 뒤에 만든 연결도 닫고 멈춘다. 어댑터를 닫은 뒤의 타이머는 fd를 건드리지 않는다."""
    monkeypatch.setattr(urllib3.util.connection, "create_connection", lambda address, *args, **kwargs: FakeSocket("93.184.216.34"))
    adapter = outbound.PublicOnlyAdapter({"recipe.example.com": "93.184.216.34"})
    connection = adapter.pool_class.ConnectionCls
    sock = connection("recipe.example.com", 443)._new_conn()
    assert (sock.dups, len(adapter.sockets)) == (1, 1)
    adapter.expire()
    assert adapter.sockets[0].shutdowns == 1

    late = FakeSocket("93.184.216.34")
    monkeypatch.setattr(urllib3.util.connection, "create_connection", lambda address, *args, **kwargs: late)
    with pytest.raises(FetchError) as caught:
        connection("recipe.example.com", 443)._new_conn()
    assert (str(caught.value), late.closed, late.dups, len(adapter.sockets)) == ("TooSlow", True, 0, 1)

    dup = adapter.sockets[0]
    adapter.close()
    adapter.expire()
    assert (dup.closed, dup.shutdowns, adapter.sockets) == (True, 1, [])


def test_hop_after_deadline_does_not_resolve(monkeypatch):
    monkeypatch.setattr(outbound.socket, "getaddrinfo", fail_if_called)
    monkeypatch.setattr(requests.Session, "send", fail_if_called)
    calls = []
    monkeypatch.setattr(outbound.time, "monotonic", lambda: calls.append(1) or (0 if len(calls) == 1 else 9))
    with pytest.raises(FetchError) as caught:
        outbound.fetch_public_page(PAGE)
    assert str(caught.value) == "TooSlow"


@pytest.mark.parametrize("ip", ["10.0.0.1", "127.0.0.1", "::1", "169.254.169.254"])
def test_public_only_connection_checks_peer(monkeypatch, ip):
    """연결된 소켓의 상대 주소가 사설이면 TLS·헤더를 보내기 전에 끊는다."""
    sock = FakeSocket(ip)
    monkeypatch.setattr(urllib3.connection.HTTPConnection, "_new_conn", lambda self: sock)
    monkeypatch.setattr(urllib3.connection, "_ssl_wrap_socket_and_match_hostname", fail_if_called)
    with pytest.raises(FetchError):
        outbound.PublicOnlyHTTPSConnection("recipe.example.com", 443).connect()
    assert sock.closed


def test_pinned_connection_connects_only_to_checked_ip(monkeypatch):
    """DNS를 다시 묻지 않고 검사한 IP 하나에만 연결한다. 인증서·Host 헤더용 호스트 이름은 그대로, 소켓은 dup해 모은다."""
    seen = []

    def create_connection(address, *args, **kwargs):
        seen.append(address)
        return FakeSocket("93.184.216.34")

    monkeypatch.setattr(urllib3.util.connection, "create_connection", create_connection)
    adapter = outbound.PublicOnlyAdapter({"recipe.example.com": "93.184.216.34"})
    sockets = adapter.sockets
    pinned = adapter.pool_class.ConnectionCls
    conn = pinned("Recipe.Example.com.", 443)
    sock = conn._new_conn()
    assert seen == [("93.184.216.34", 443)] and conn.host == "Recipe.Example.com"
    assert not sock.closed and sock.dups == 1 and len(sockets) == 1

    with pytest.raises(FetchError):
        pinned("other.example.com", 443)._new_conn()  # 검사하지 않은 호스트
    assert len(seen) == 1


def test_fetch_public_page_connects_once_and_stops_before_sending(monkeypatch):
    """진짜 requests·urllib3 경로: A 레코드가 많아도 한 번만 연결하고, 상대 주소가 사설이면 TLS 전에 FetchError(재시도 없음)."""
    fake_dns(monkeypatch, {"recipe.example.com": [f"93.184.216.{i}" for i in range(30)]})
    monkeypatch.setattr(requests.Session, "send", REAL_SEND)
    seen, sockets = [], []

    def create_connection(address, *args, **kwargs):
        seen.append(address)
        sockets.append(FakeSocket("10.0.0.1"))
        return sockets[-1]

    monkeypatch.setattr(urllib3.util.connection, "create_connection", create_connection)
    monkeypatch.setattr(urllib3.connection, "_ssl_wrap_socket_and_match_hostname", fail_if_called)
    with pytest.raises(FetchError):
        outbound.fetch_public_page(PAGE)
    assert seen == [("93.184.216.0", 443)] and sockets[0].closed


def test_fetch_public_page_revalidates_redirects(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    asked = fake_dns(
        monkeypatch, {"recipe.example.com": ["93.184.216.34"], "internal.example": ["10.0.0.9"], "cdn.example.com": ["2606:2800:220:1:248:1893:25c8:1946"]}
    )

    # 사설 주소로 가는 리다이렉트 → 따라가지 않는다
    sent = fake_send(monkeypatch, [response(302, headers={"Location": "https://internal.example/"})])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(PAGE)
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
    body, encoding, final_url = outbound.fetch_public_page(PAGE)
    assert [s[0] for s in sent] == [PAGE, "https://cdn.example.com/b", "https://cdn.example.com/c?x=1"]
    assert (body.decode(encoding), final_url) == ("<p>본문</p>", "https://cdn.example.com/c?x=1")

    # 리다이렉트는 3번까지
    fake_send(monkeypatch, [response(302, headers={"Location": f"/r{i}"}) for i in range(4)] + [response(200, b"<p>x</p>")])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(PAGE)
    fake_send(monkeypatch, [response(302, headers={"Location": f"/r{i}"}) for i in range(3)] + [response(200, b"<p>x</p>")])
    assert outbound.fetch_public_page(PAGE)[2] == "https://recipe.example.com/r2"

    # Location 없음, http로 내려가는 리다이렉트, 200이 아닌 응답
    # Location 모양이 틀린 리다이렉트(urljoin ValueError)도 FetchError
    malformed = response(302, headers={"Location": "https://[x"})
    for res in (response(302, headers={}), response(302, headers={"Location": "http://recipe.example.com/"}), response(404), malformed):
        fake_send(monkeypatch, [res])
        with pytest.raises(FetchError):
            outbound.fetch_public_page(PAGE)


def test_fetch_public_page_requires_html_and_caps_size(monkeypatch):
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})

    fake_send(monkeypatch, [response(200, b"{}", {"Content-Type": "application/json"})])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(PAGE)

    fake_send(monkeypatch, [response(200, b"<p>ok</p>", {"Content-Type": "text/html"})])
    assert outbound.fetch_public_page(PAGE)[:2] == (b"<p>ok</p>", None)  # charset이 없으면 None

    monkeypatch.setattr(outbound, "MAX_BYTES", 10)
    fake_send(monkeypatch, [response(200, b"x" * 20)])
    with pytest.raises(FetchError):
        outbound.fetch_public_page(PAGE)
    fake_send(monkeypatch, [response(200, b"x" * 10)])
    assert outbound.fetch_public_page(PAGE)[0] == b"x" * 10


def test_fetch_public_page_deadline_after_request_went_out(monkeypatch):
    """요청을 보낸 뒤 조금씩 흘려 보내는 서버: 읽을 때마다 전체 남은 시간을 본다."""
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    calls = []

    def clock():
        calls.append(1)
        return 0 if len(calls) <= 3 else 9  # 시작·DNS 전·요청 전에는 0초, 첫 읽기 때 9초

    monkeypatch.setattr(outbound.time, "monotonic", clock)
    sent = fake_send(monkeypatch, [response(200, b"<p>slow</p>")])
    with pytest.raises(FetchError) as caught:
        outbound.fetch_public_page(PAGE)
    assert (len(sent), str(caught.value)) == (1, "TooSlow")
    assert sent[0][1]["timeout"] == (3.05, 8)


def test_watchdog_cuts_blocked_read(monkeypatch):
    """한 번의 읽기가 막혀 있어도(읽기 시간 제한은 recv마다라 우회된다) 감시 타이머가 소켓을 끊어 제한 시간에 끝난다."""
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    monkeypatch.setattr(outbound, "TOTAL_SECONDS", 0.3)
    server, client = socket.socketpair()
    client.settimeout(3)  # 감시 타이머가 동작하지 않으면 3초 뒤에야 끝나 아래 시간 확인에서 실패한다

    class BlockingRaw:
        def read1(self, amt, decode_content=None):
            return client.recv(amt)

        def close(self):
            pass

    def send(self, request, **kwargs):
        self.get_adapter(request.url).register(client)  # 진짜 연결이면 PublicOnlyHTTPSConnection이 넣는다
        res = response(200)
        res.raw = BlockingRaw()
        return res

    monkeypatch.setattr(requests.Session, "send", send)
    started = time.monotonic()
    try:
        with pytest.raises(FetchError) as caught:
            outbound.fetch_public_page(PAGE)
    finally:
        server.close()
        client.close()
    assert time.monotonic() - started < 2 and str(caught.value) == "TooSlow"


def test_network_is_blocked_without_fakes():
    """가짜를 깜빡하면 FetchError로 조용히 넘어가지 않고 차단 픽스처의 AssertionError가 난다."""
    with pytest.raises(AssertionError):
        outbound.fetch_public_page(PAGE)
    with pytest.raises(AssertionError):
        outbound.fetch_fixed("https://www.instagram.com/p/C1a2B3c4D5e/")


# --- video_snippet · instagram_post · web_page ---


def test_video_snippet_builds_fixed_url_and_parses(monkeypatch):
    snippet = {
        "title": "제육볶음 황금레시피",
        "description": "재료: 돼지고기 600g",
        "channelTitle": "집밥 연구소",
        "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/x/default.jpg"}, "high": {"url": "https://i.ytimg.com/vi/x/hq.jpg"}},
    }
    bodies = [
        {"items": [{"snippet": snippet}]},
        {"items": []},
        {"items": [{"snippet": {"title": 3, "thumbnails": {"high": {"url": "http://x/y.jpg"}}}}]},
        {"items": [{"snippet": {"thumbnails": {"high": {"width": 480}, "medium": {"url": "https://i.ytimg.com/vi/x/mq.jpg"}}}}]},
    ]
    json_type = {"Content-Type": "application/json; charset=UTF-8"}
    sent = fake_send(monkeypatch, [response(200, json.dumps(body).encode(), json_type) for body in bodies] + [response(200, b"not json")])
    assert outbound.video_snippet(VIDEO_ID, "k") == {
        "title": "제육볶음 황금레시피",
        "description": "재료: 돼지고기 600g",
        "channel_title": "집밥 연구소",
        "thumbnail_url": "https://i.ytimg.com/vi/x/hq.jpg",
    }
    assert sent[0][0] == f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={VIDEO_ID}&key=k"
    assert outbound.video_snippet(VIDEO_ID, "k") is None
    assert outbound.video_snippet(VIDEO_ID, "k") == {"title": "", "description": "", "channel_title": "", "thumbnail_url": None}
    assert outbound.video_snippet(VIDEO_ID, "k")["thumbnail_url"] == "https://i.ytimg.com/vi/x/mq.jpg"  # high에 주소가 없으면 medium
    with pytest.raises(FetchError):
        outbound.video_snippet(VIDEO_ID, "k")


def test_instagram_post_reads_og_tags(monkeypatch):
    pages = [
        b'<html><head><meta property="og:title" content="cook on Instagram: &quot;\xec\xb0\xb8\xec\xb9\x98\xeb\xa7\x88\xec\x9a\x94&quot;">'
        b'<meta property="og:description" content="&quot;\xec\xb4\x88\xea\xb0\x84\xeb\x8b\xa8&quot; \xec\x9e\xac\xeb\xa3\x8c: \xeb\xb0\xa5">'
        b'<meta property="og:image" content="https://scontent.cdninstagram.com/a.jpg?x=1&amp;y=2"></head></html>',
        b"<html><head><title>Login</title></head></html>",
        # 로그인 화면: 설명은 있지만 게시물 미리보기가 아니다
        b'<html><head><meta property="og:title" content="Instagram">'
        b'<meta property="og:description" content="Create an account or log in to Instagram - Share what you&#x27;re into with the people who get you."></head></html>',
    ]
    sent = fake_send(monkeypatch, [response(200, page) for page in pages])
    assert outbound.instagram_post("C1a2B3c4D5e") == {
        "caption": '"초간단" 재료: 밥',
        "title": 'cook on Instagram: "참치마요"',
        "thumbnail_url": "https://scontent.cdninstagram.com/a.jpg?x=1&y=2",
    }
    assert sent[0][0] == "https://www.instagram.com/p/C1a2B3c4D5e/"
    assert outbound.instagram_post("C1a2B3c4D5e") is None
    assert outbound.instagram_post("C1a2B3c4D5e") is None


def fake_pages(monkeypatch, *pages):
    """pages: (html, 최종 주소, charset)."""
    pages = list(pages)

    def fetch(url):
        html, final, encoding = pages.pop(0)
        return html.encode(), encoding, final

    monkeypatch.setattr(outbound, "fetch_public_page", fetch)


def test_web_page_extracts_title_site_and_text(monkeypatch):
    fake_pages(
        monkeypatch,
        (
            "<html><head><title>무시</title><meta property='og:title' content='제육볶음 만들기'><meta property='og:site_name' content='요리 블로그'>"
            "<style>.a{color:red}</style><script>alert('지시')</script></head><body><nav>메뉴 홈</nav><header>머리</header>"
            "<h1>제육볶음</h1><p>재료:   돼지고기 600g</p>\n\n\n<ul><li>양파 1개</li><li>대파</li></ul><form>댓글 쓰기</form><footer>꼬리</footer></body></html>",
            "https://recipe.example.com/final",
            "utf-8",
        ),
        ("<html><head><title> 두부조림 </title></head><body><p>" + "가" * 12_000 + "</p></body></html>", "https://Cook.Example.com/x", "utf-8"),
    )
    assert outbound.web_page(PAGE) == {
        "title": "제육볶음 만들기",
        "site_name": "요리 블로그",
        "text": "제육볶음\n재료: 돼지고기 600g\n양파 1개\n대파",
        "url": "https://recipe.example.com/final",
        "images": [],
    }
    second = outbound.web_page("https://cook.example.com/x")
    assert (second["title"], second["site_name"], len(second["text"])) == ("두부조림", "cook.example.com", 10_000)


def test_web_page_cells_breaks_and_unclosed_tags(monkeypatch):
    fake_pages(
        monkeypatch,
        (
            "<table><tr><th>재료</th><th>양</th></tr><tr><td>양파</td><td>1개</td></tr></table>"
            "<dl><dt>대파</dt><dd>1대</dd></dl>고추장<br/>2큰술<br>간장"
            "<div><form><input name=q>검색</div><p>만드는 법: 볶아요.</p>",  # 닫히지 않은 form은 부모 div와 함께 닫힌다
            PAGE,
            "utf-8",
        ),
        ("<html><head><title>제육볶음<body><p>재료: 돼지고기</p></body>", PAGE, None),  # 닫히지 않은 title
        ("<p>재료: 두부</p>", PAGE, "x-unknown-charset"),  # 모르는 charset → UTF-8
        ("<body><p>본문</p><form>닫히지 않은 폼</body><p>꼬리 글</p>", PAGE, "utf-8"),
    )
    assert outbound.web_page(PAGE)["text"] == "재료 양\n양파 1개\n대파\n1대\n고추장\n2큰술\n간장\n만드는 법: 볶아요."
    unclosed = outbound.web_page(PAGE)
    assert (unclosed["title"], unclosed["text"]) == ("제육볶음", "재료: 돼지고기")
    assert outbound.web_page(PAGE)["text"] == "재료: 두부"
    assert outbound.web_page(PAGE)["text"] == "본문\n꼬리 글"


def test_web_page_image_candidates(monkeypatch):
    """본문 사진 후보: <img> data-src·src 문서 순서, 최종 주소 기준 절대 주소, https만, svg·gif·꾸밈 이름 제외, 중복 제거, 8개까지.
    form 안의 사진도 넣는다(카페24 게시판은 글 전체가 <form> 안에 있다)."""
    fake_pages(
        monkeypatch,
        (
            "<header><img src='/skin/LOGO_top.png'></header>"
            "<img src='/skin/loading/text_1.png'><img src='spacer.gif'><img src='/a/arrow.SVG'>"
            "<form><img src='/upload/1.jpg'></form>"
            "<img src='placeholder.gif' data-src='/upload/2.jpg'>"
            "<img src='http://recipe.example.com/upload/plain.jpg'>"
            "<img src='//cdn.example.com/upload/3.webp?w=1000'>"
            "<img src='/upload/1.jpg'>"  # 중복
            "<img src='/icons/x.png'><img src='/btn_ok.jpg'><img src='/button/go.png'><img src='/banner/a.jpg'><img src='/sprite.png'>"
            "<img src='/user/profile.jpg'><img src='/emoji/a.png'><img src='/avatar/1.jpg'><img><img src=''>"
            "<img src='https://other.example.com/p/4.png'><img src='5.jpg'><img src='../6.jpeg'>"
            "<img src='/" + "a" * 490 + ".jpg'>"  # 500자 넘는 주소
            "<img src='/7.jpg'><img src='/8.jpg'><img src='/9.jpg'>",
            "https://recipe.example.com/post/final",
            "utf-8",
        ),
    )
    assert outbound.web_page(PAGE)["images"] == [
        "https://recipe.example.com/upload/1.jpg",
        "https://recipe.example.com/upload/2.jpg",
        "https://cdn.example.com/upload/3.webp?w=1000",
        "https://other.example.com/p/4.png",
        "https://recipe.example.com/post/5.jpg",
        "https://recipe.example.com/6.jpeg",
        "https://recipe.example.com/7.jpg",
        "https://recipe.example.com/8.jpg",
    ]


def jpeg(width, height, sof=0xC0):
    """APP0·DHT(SOF 아님) 뒤에 SOFn이 있는 작은 JPEG 머리."""
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\0" + b"\0" * 9
    dht = b"\xff\xc4" + (5).to_bytes(2, "big") + b"\0" * 3
    frame = b"\xff" + bytes([sof]) + (17).to_bytes(2, "big") + b"\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x03" + b"\0" * 9
    return b"\xff\xd8" + app0 + dht + b"\xff\xff" + frame  # 마커 앞 채움 0xFF도 건너뛴다


def png(width, height):
    return b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\0\0\0"


def webp(chunk, payload):
    return b"RIFF" + (len(payload) + 12).to_bytes(4, "little") + b"WEBP" + chunk + len(payload).to_bytes(4, "little") + payload


def webp_lossy(width, height):
    return webp(b"VP8 ", b"\0\0\0" + b"\x9d\x01\x2a" + width.to_bytes(2, "little") + height.to_bytes(2, "little"))


def webp_lossless(width, height):
    bits = (width - 1) | ((height - 1) << 14)
    return webp(b"VP8L", b"\x2f" + bits.to_bytes(4, "little"))


def webp_extended(width, height):
    return webp(b"VP8X", b"\0" * 4 + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little"))


@pytest.mark.parametrize(
    "data, size",
    [
        (jpeg(1000, 1333), (1000, 1333)),
        (jpeg(640, 8000, sof=0xC2), (640, 8000)),  # 프로그레시브
        (png(1200, 900), (1200, 900)),
        (webp_lossy(800, 600), (800, 600)),
        (webp_lossless(8000, 1), (8000, 1)),
        (webp_extended(16383, 12000), (16383, 12000)),
        (b"\xff\xd8\xff" + b"j" * 40, None),  # SOF가 없다
        (jpeg(10, 10)[:30], None),  # 머리가 잘렸다
        (b"\x89PNG\r\n\x1a\n" + b"p" * 40, None),
        (webp(b"ALPH", b"\0" * 10), None),
        (webp_lossy(800, 600)[:25], None),
        (b"GIF89a" + b"\0" * 20, None),
        pytest.param(b"\xff\xd8" + b"\xff" * 100_000, None, id="jpeg-fill-only"),
        pytest.param(b"\xff\xd8" + b"\xff\xe0\0\0" * 30_000, None, id="jpeg-zero-length-segments"),
        pytest.param(b"\xff\xd8" + b"\xff\xd0" * 40_000 + jpeg(10, 10)[2:], None, id="jpeg-sof-after-64kb"),
        pytest.param(b"\xff\xd8" + b"\xff\xd0" * 1_000 + jpeg(10, 20)[2:], (10, 20), id="jpeg-rst-markers-skipped"),
    ],
)
def test_image_size_reads_file_header(data, size):
    assert outbound.image_size(data) == size


IMAGE = jpeg(1000, 1333)  # 테스트에서는 MIN_IMAGE_BYTES를 20으로 줄인다


def test_page_images_filters_and_skips_failures(monkeypatch):
    monkeypatch.setattr(outbound, "MIN_IMAGE_BYTES", 20)
    monkeypatch.setattr(outbound, "MAX_IMAGE_BYTES", 100)  # 본문 사진은 페이지(MAX_BYTES)보다 작게 받는다
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"], "internal.example": ["10.0.0.9"]})
    png = globals()["png"](1200, 900)
    webp = webp_extended(800, 600) + b"w" * 10
    sent = fake_send(
        monkeypatch,
        [
            response(200, b"<html>" + b"x" * 40, {"Content-Type": "image/jpeg"}),  # 선언만 사진 → 건너뜀
            response(200, b"\xff\xd8\xff" + b"j" * 5, {"Content-Type": "image/jpeg"}),  # 너무 작음(아이콘·여백)
            response(200, b"\xff\xd8\xff" + b"j" * 200, {"Content-Type": "image/jpeg"}),  # 너무 큼
            response(302, headers={"Location": "https://[x"}),  # 잘못된 리다이렉트 주소(urljoin ValueError)
            response(302, headers={"Location": "https://internal.example/x.jpg"}),  # 사설 주소로 리다이렉트
            requests.ConnectionError("boom"),
            response(200, IMAGE, {"Content-Type": "text/html"}),  # 선언된 형식은 보지 않는다
            response(200, png, {}),
            response(200, webp, {"Content-Type": "application/octet-stream"}),
        ],
    )
    urls = [f"https://recipe.example.com/{i}.jpg" for i in range(9)]
    # 후보는 앞 8개만 받는다: 앞의 6개는 건너뛰고 7·8번째만 사진(9번째 webp는 요청하지 않는다)
    assert outbound.page_images(urls) == [(IMAGE, "image/jpeg"), (png, "image/png")]
    assert len(sent) == 8

    sent = fake_send(monkeypatch, [response(200, IMAGE, {"Content-Type": "image/jpeg"}), response(200, png, {}), response(200, webp, {})])
    assert outbound.page_images(urls[:3]) == [(IMAGE, "image/jpeg"), (png, "image/png"), (webp, "image/webp")]
    url, kwargs, headers = sent[0]
    assert (url, kwargs["allow_redirects"], kwargs["proxies"], headers["User-Agent"]) == (urls[0], False, {}, "galmuri-kitchen/1.0")
    assert kwargs["timeout"][1] <= 10


def test_page_images_skip_oversize_and_unreadable(monkeypatch):
    """AI API는 한 변이 8000px를 넘는 사진을 거절한다(502면 하루 한도만 쓴다). 넘거나 머리를 읽지 못하면 건너뛴다."""
    monkeypatch.setattr(outbound, "MIN_IMAGE_BYTES", 20)
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    ok = [jpeg(8000, 8000), png(1, 8000), webp_lossless(640, 480)]
    bad = [jpeg(1000, 8001), png(8001, 10), webp_extended(640, 9000), b"\xff\xd8\xff" + b"j" * 40]
    fake_send(monkeypatch, [response(200, data, {}) for data in (bad[0], ok[0], bad[1], ok[1], bad[2], bad[3], ok[2])])
    urls = [f"https://recipe.example.com/{i}.jpg" for i in range(7)]
    assert outbound.page_images(urls) == [(ok[0], "image/jpeg"), (ok[1], "image/png"), (ok[2], "image/webp")]

    fake_send(monkeypatch, [response(200, data, {}) for data in bad])
    assert outbound.page_images(urls[:4]) == []  # 모두 걸러지면 빈 목록 → 가져오기는 글만 보낸다


def test_page_images_total_byte_budget(monkeypatch):
    """요청 하나가 붙잡는 사진 바이트를 6MB로 막는다(512MB 인스턴스). 다음 사진이 넘기면 거기서 멈춘다."""
    monkeypatch.setattr(outbound, "MIN_IMAGE_BYTES", 20)
    monkeypatch.setattr(outbound, "MAX_IMAGE_BYTES", 100)
    monkeypatch.setattr(outbound, "MAX_IMAGE_TOTAL_BYTES", 250)
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    image = IMAGE + b"j" * (90 - len(IMAGE))
    small = IMAGE
    sent = fake_send(monkeypatch, [response(200, image, {}), response(200, image, {}), response(200, image, {}), response(200, small, {})])
    assert outbound.page_images([f"https://recipe.example.com/{i}.jpg" for i in range(4)]) == [(image, "image/jpeg")] * 2
    assert len(sent) == 3  # 세 번째에서 180 + 90 > 250 → 멈추고 네 번째는 요청하지 않는다


def test_page_images_stop_at_five(monkeypatch):
    monkeypatch.setattr(outbound, "MIN_IMAGE_BYTES", 20)
    fake_dns(monkeypatch, {"recipe.example.com": ["93.184.216.34"]})
    sent = fake_send(monkeypatch, [response(200, IMAGE, {}) for _ in range(8)])
    assert outbound.page_images([f"https://recipe.example.com/{i}.jpg" for i in range(8)]) == [(IMAGE, "image/jpeg")] * 5
    assert len(sent) == 5


def test_page_images_share_ten_second_budget(monkeypatch):
    """사진 요청 전체가 10초 안에서 끝난다. 한 장마다 남은 시간만 주고, 시간이 다 되면 나머지는 요청하지 않는다."""
    now, given = [0.0], []

    def fetch(url, params=None, public=False, image=False, seconds=None):
        assert public and image
        given.append(seconds)
        now[0] += 4
        return IMAGE, None, url

    monkeypatch.setattr(outbound.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(outbound, "_fetch", fetch)
    monkeypatch.setattr(outbound, "MIN_IMAGE_BYTES", 20)
    assert len(outbound.page_images([f"https://recipe.example.com/{i}.jpg" for i in range(8)])) == 3
    assert given == [10, 6, 2]


# --- 요리 채널: channel_info · playlist_videos · video_details ---

CHANNEL_ID = "UCabcdefghijklmnopqrstuv"
JSON_TYPE = {"Content-Type": "application/json; charset=UTF-8"}


def json_response(body, status=200):
    return response(status, json.dumps(body).encode(), JSON_TYPE)


def test_channel_info_by_handle_and_empty(monkeypatch):
    item = {
        "id": CHANNEL_ID,
        "snippet": {"title": "집밥 연구소", "thumbnails": {"default": {"url": "https://yt3.ggpht.com/a=s88"}}},
        "contentDetails": {"relatedPlaylists": {"uploads": "UUabcdefghijklmnopqrstuv"}},
        "statistics": {"videoCount": "248"},
    }
    sent = fake_send(
        monkeypatch,
        [
            json_response({"items": [item]}),
            json_response({"items": []}),
            json_response({"items": [{**item, "statistics": {}, "id": "not-a-channel"}]}),
            json_response({"items": [{"id": CHANNEL_ID}]}),
        ],
    )
    assert outbound.channel_info("k", handle="@집밥") == {
        "channel_id": CHANNEL_ID,
        "title": "집밥 연구소",
        "thumbnail_url": "https://yt3.ggpht.com/a=s88",
        "uploads_playlist_id": "UUabcdefghijklmnopqrstuv",
        "video_count": 248,
    }
    assert sent[0][0].startswith("https://www.googleapis.com/youtube/v3/channels?part=snippet%2CcontentDetails%2Cstatistics&forHandle=%40")
    assert sent[0][0].endswith("&key=k") and sent[0][1]["allow_redirects"] is False
    assert outbound.channel_info("k", channel_id=CHANNEL_ID) is None
    assert f"id={CHANNEL_ID}" in sent[1][0]
    with pytest.raises(FetchError):
        outbound.channel_info("k", username="maangchi")  # 모양이 틀린 채널 ID
    assert "forUsername=maangchi" in sent[2][0]
    with pytest.raises(FetchError):
        outbound.channel_info("k", channel_id=CHANNEL_ID)  # contentDetails 없음


def test_playlist_videos_skips_private_and_404_is_none(monkeypatch):
    items = [
        {
            "snippet": {"title": "제육볶음", "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/a/mq.jpg"}}},
            "contentDetails": {"videoId": VIDEO_ID, "videoPublishedAt": "2026-09-11T09:00:00Z"},
        },
        {"snippet": {"title": "Private video"}, "contentDetails": {"videoId": "abcdefghijk"}},  # 비공개: 공개 날짜 없음
        {"snippet": {"title": "이상한 ID"}, "contentDetails": {"videoId": "bad", "videoPublishedAt": "2026-09-11T09:00:00Z"}},
        {"snippet": {"title": "날짜 틀림"}, "contentDetails": {"videoId": "abcdefghij2", "videoPublishedAt": "어제"}},
    ]
    sent = fake_send(monkeypatch, [json_response({"items": items}), response(404, b"{}", JSON_TYPE), response(500, b"{}", JSON_TYPE)])
    videos = outbound.playlist_videos("k", "UUabc")
    assert [(v["video_id"], v["title"], v["thumbnail_url"]) for v in videos] == [(VIDEO_ID, "제육볶음", "https://i.ytimg.com/vi/a/mq.jpg")]
    assert videos[0]["published_at"].isoformat() == "2026-09-11T09:00:00+00:00"
    assert sent[0][0] == "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet%2CcontentDetails&playlistId=UUabc&maxResults=50&key=k"
    assert outbound.playlist_videos("k", "UUgone") is None
    with pytest.raises(FetchError):
        outbound.playlist_videos("k", "UUabc")


def test_video_details_and_iso_duration(monkeypatch):
    good = {"PT12M4S": 724, "PT1H2S": 3602, "PT1H2M3S": 3723, "P1DT1S": 86401}
    assert {v: outbound.iso_duration(v) for v in good} == good
    for bad in ("P0D", "PT", "P", "P1W", "12:04", None, "PT1.5S", "P99999999D", f"PT{2**31}S"):
        assert outbound.iso_duration(bad) is None, bad
    assert outbound.iso_duration(f"PT{2**31 - 1}S") == 2**31 - 1
    items = [
        {"id": VIDEO_ID, "contentDetails": {"duration": "PT12M4S"}, "snippet": {"description": "  재료 " + "가" * 600}},
        {"id": "abcdefghijk", "contentDetails": {"duration": "P0D"}, "snippet": {"description": ""}},
    ]
    sent = fake_send(monkeypatch, [json_response({"items": items})])
    details = outbound.video_details("k", [VIDEO_ID, "abcdefghijk"])
    assert details[VIDEO_ID]["duration_seconds"] == 724 and len(details[VIDEO_ID]["description"]) == 500
    assert details[VIDEO_ID]["description"].startswith("재료 가")
    assert details["abcdefghijk"] == {"duration_seconds": None, "description": None}
    assert sent[0][0] == f"https://www.googleapis.com/youtube/v3/videos?part=contentDetails%2Csnippet&id={VIDEO_ID}%2Cabcdefghijk&key=k"
    assert outbound.video_details("k", []) == {}  # 요청 없음


def test_youtube_thumbnails_only_from_youtube_image_hosts():
    snippet = lambda url: {"thumbnails": {"default": {"url": url}}}  # noqa: E731
    for url in ("https://i.ytimg.com/vi/a/mq.jpg", "https://yt3.ggpht.com/a=s88", "https://yt3.googleusercontent.com/a"):
        assert outbound._thumbnail(snippet(url), ("default",)) == url
    for url in ("http://i.ytimg.com/a.jpg", "https://evil.example/a.jpg", "https://i.ytimg.com.evil.example/a.jpg", "https://u@i.ytimg.com/a", "https://i.ytimg.com/" + "a" * 500):
        assert outbound._thumbnail(snippet(url), ("default",)) is None
