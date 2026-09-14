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
        self.ip, self.closed, self.dups = ip, False, 0

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
    assert pool.ConnectionCls.sockets is adapter.sockets


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
    sockets = []
    pinned = type("Pinned", (outbound.PublicOnlyHTTPSConnection,), {"addresses": {"recipe.example.com": "93.184.216.34"}, "sockets": sockets})
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
    for res in (response(302, headers={}), response(302, headers={"Location": "http://recipe.example.com/"}), response(404)):
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
        return 0 if len(calls) <= 2 else 9  # 시작·요청 전에는 0초, 첫 읽기 때 9초

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
        self.get_adapter(request.url).sockets.append(client.dup())  # 진짜 연결이면 PublicOnlyHTTPSConnection이 넣는다
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
