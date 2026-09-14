"""외부 HTTP 요청은 이 파일에서만 한다(스펙 17절).

- 유튜브·인스타그램: 사용자가 보낸 주소를 요청하지 않고 영상 ID·게시물 코드로 고정 호스트 주소를 다시 만든다(fetch_fixed).
- 블로그 같은 일반 주소: https·443 포트·공인 IP만(DNS 결과 전부 + 연결된 소켓의 상대 주소), 리다이렉트는 매번 다시 검사해 최대 3번,
  text/html·1MB·8초 이내(fetch_public_page).
예외 메시지에는 주소·키를 넣지 않는다(FetchError는 예외 이름만 담는다).
"""

import ipaddress
import json
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool

MAX_BYTES = 1_000_000
CONNECT_SECONDS = 3.05
TOTAL_SECONDS = 8
MAX_REDIRECTS = 3
MAX_LINK = 500
MAX_TEXT = 10_000
MAX_LABEL = 200  # 출처 카드 제목·채널 이름
HEADERS = {"User-Agent": "galmuri-kitchen/1.0"}
FIXED_HOSTS = {"www.googleapis.com", "www.youtube.com", "www.instagram.com"}
REDIRECT_CODES = {301, 302, 303, 307, 308}
YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
INSTAGRAM_CODE = re.compile(r"[A-Za-z0-9_-]{5,40}")
NAVER_BLOG_PATH = re.compile(r"/([A-Za-z0-9_-]+)/(\d+)/?")
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class FetchError(Exception):
    """외부 요청 실패. 메시지는 예외·이유 이름뿐이다(주소·키 없음)."""


def _is_public(ip):
    try:
        address = ipaddress.ip_address(ip.split("%", 1)[0])  # IPv6 zone(%eth0) 제거
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped  # ::ffff:127.0.0.1
    return address.is_global and not address.is_multicast


class PublicOnlyHTTPSConnection(HTTPSConnection):
    """연결된 소켓의 상대 주소가 공인 IP가 아니면 TLS·요청 헤더를 보내기 전에 끊는다(DNS 재바인딩 방지).
    urllib3 2.x의 connect()가 소켓을 만드는 _new_conn()을 감싼다."""

    def _new_conn(self):
        sock = super()._new_conn()
        try:
            public = _is_public(sock.getpeername()[0])
        except OSError:
            public = False
        if not public:
            sock.close()
            raise FetchError("PrivateAddress")
        return sock


class PublicOnlyPool(HTTPSConnectionPool):
    ConnectionCls = PublicOnlyHTTPSConnection


class PublicOnlyAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"https": PublicOnlyPool}  # http는 앞에서 거절한다


def public_session():
    session = requests.Session()
    session.trust_env = False  # 프록시 환경변수·.netrc를 쓰지 않는다
    session.mount("https://", PublicOnlyAdapter())
    return session


def _read(res, started):
    """본문을 스트리밍으로 읽으며 크기·전체 시간을 확인한다."""
    chunks, size = [], 0
    try:
        for chunk in res.iter_content(8192):
            size += len(chunk)
            if size > MAX_BYTES:
                raise FetchError("TooLarge")
            if time.monotonic() - started > TOTAL_SECONDS:
                raise FetchError("TooSlow")
            chunks.append(chunk)
    except requests.RequestException as e:
        raise FetchError(type(e).__name__) from None
    return b"".join(chunks)


def _charset(res):
    match = re.search(r"charset=[\"']?([\w.:-]+)", res.headers.get("Content-Type", ""), re.I)
    return match.group(1) if match else None


def fetch_fixed(url, params=None):
    """정해 둔 호스트(유튜브 API·유튜브·인스타그램)만 요청한다. (본문, charset)."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in FIXED_HOSTS or parts.netloc != parts.hostname:
        raise FetchError("HostNotAllowed")
    started = time.monotonic()
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=(CONNECT_SECONDS, TOTAL_SECONDS), allow_redirects=False, stream=True)
    except requests.RequestException as e:
        raise FetchError(type(e).__name__) from None
    with res:
        if res.status_code != 200:
            raise FetchError(f"HTTP{res.status_code}")
        return _read(res, started), _charset(res)


def _check_public_url(url):
    """https·443·사용자정보 없음·IP 문자열 아님·DNS 결과가 모두 공인 IP. 통과하지 못하면 FetchError."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError("BadUrl") from None
    host = parts.hostname
    if parts.scheme != "https" or port not in (None, 443) or "@" in parts.netloc or not host or len(host) > 253:
        raise FetchError("BadUrl")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise FetchError("IpLiteral")
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as e:
        raise FetchError(type(e).__name__) from None
    if not infos or not all(_is_public(info[4][0]) for info in infos):
        raise FetchError("PrivateAddress")


def fetch_public_page(url):
    """사용자가 준 일반 주소(블로그 등)를 요청한다. (본문, charset, 검사를 통과한 최종 주소)."""
    started = time.monotonic()
    with public_session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            _check_public_url(url)
            if time.monotonic() - started > TOTAL_SECONDS:
                raise FetchError("TooSlow")
            try:
                res = session.get(url, headers=HEADERS, timeout=(CONNECT_SECONDS, TOTAL_SECONDS), allow_redirects=False, stream=True)
            except requests.RequestException as e:
                raise FetchError(type(e).__name__) from None
            with res:
                if res.status_code in REDIRECT_CODES:
                    location = res.headers.get("Location")
                    if not location:
                        raise FetchError("BadRedirect")
                    url = urljoin(url, location)
                    continue
                if res.status_code != 200:
                    raise FetchError(f"HTTP{res.status_code}")
                if not res.headers.get("Content-Type", "").lower().startswith("text/html"):
                    raise FetchError("NotHtml")
                return _read(res, started), _charset(res), url
    raise FetchError("TooManyRedirects")


def parse_link(value):
    """("youtube", 영상 ID) | ("instagram", 게시물 코드) | ("web", https 주소) | None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_LINK:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    bare = host[4:] if host.startswith("www.") else host[2:] if host.startswith("m.") else host
    segments = parts.path.split("/")
    if bare in ("youtube.com", "youtu.be"):
        if bare == "youtu.be":
            video_id = segments[1] if len(segments) > 1 else ""
        elif parts.path == "/watch":
            video_id = parse_qs(parts.query).get("v", [""])[0]
        elif len(segments) > 2 and segments[1] in ("shorts", "live", "embed"):
            video_id = segments[2]
        else:
            return None
        return ("youtube", video_id) if YOUTUBE_ID.fullmatch(video_id) else None
    if bare == "instagram.com":
        if len(segments) > 2 and segments[1] in ("p", "reel", "reels") and INSTAGRAM_CODE.fullmatch(segments[2]):
            return ("instagram", segments[2])
        return None
    if parts.scheme != "https":
        return None
    naver = NAVER_BLOG_PATH.fullmatch(parts.path)
    if host == "blog.naver.com" and naver:  # PC 주소는 본문이 iframe이라 모바일 주소로 읽는다
        return ("web", f"https://m.blog.naver.com/{naver.group(1)}/{naver.group(2)}")
    return ("web", value)


def _label(value):
    return value.strip()[:MAX_LABEL].strip() if isinstance(value, str) else ""


def _https(value):
    return value if isinstance(value, str) and value.startswith("https://") and len(value) <= 1000 else None


def video_snippet(video_id, key):
    """유튜브 영상 제목·설명·채널 이름·썸네일(videos.list, 1 unit). 없는 영상이면 None."""
    body, _ = fetch_fixed(VIDEOS_URL, {"part": "snippet", "id": video_id, "key": key})
    try:
        items = json.loads(body)["items"]
        snippet = items[0]["snippet"] if items else None
        thumbnails = snippet.get("thumbnails", {}) if snippet else {}
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise FetchError("BadResponse") from None
    if snippet is None:
        return None
    thumbnail = next((thumbnails[size].get("url") for size in ("high", "medium", "default") if isinstance(thumbnails.get(size), dict)), None)
    description = snippet.get("description")
    return {
        "title": _label(snippet.get("title")),
        "description": description[:MAX_TEXT] if isinstance(description, str) else "",
        "channel_title": _label(snippet.get("channelTitle")),
        "thumbnail_url": _https(thumbnail),
    }


class _Page(HTMLParser):
    """og 메타·<title>·본문 글. script·style·noscript·nav·header·footer·form 안의 글은 버린다."""

    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "form"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul", "ol", "table", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self.parts = {}, None, []
        self._skip, self._title = 0, None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "meta":
            attrs = dict(attrs)
            key, content = attrs.get("property") or attrs.get("name"), attrs.get("content")
            if key in ("og:title", "og:description", "og:image", "og:site_name") and content:
                self.meta.setdefault(key, content)
        elif tag == "title" and self.title is None:
            self._title = []
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title" and self._title is not None:
            self.title, self._title = "".join(self._title), None
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        elif not self._skip:
            self.parts.append(data)

    def text(self):
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)[:MAX_TEXT]


def _parse_html(body, encoding):
    # ponytail: charset이 헤더에 없으면 UTF-8로 읽는다. EUC-KR인데 헤더에 안 밝힌 옛 블로그가 깨지면 <meta charset>을 본다.
    try:
        html = body.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")
    page = _Page()
    page.feed(html)
    page.close()
    return page


def instagram_post(shortcode):
    """게시물 링크 미리보기(og:description)에서 캡션을 읽는다. 캡션이 없으면(로그인 화면 등) None."""
    page = _parse_html(*fetch_fixed(f"https://www.instagram.com/p/{shortcode}/"))
    caption = page.meta.get("og:description", "").strip()
    if not caption:
        return None
    return {"caption": caption[:MAX_TEXT], "title": _label(page.meta.get("og:title")), "thumbnail_url": _https(page.meta.get("og:image"))}


def web_page(url):
    """공개 웹 페이지의 제목·사이트 이름·본문 글, 검사를 통과한 최종 주소. 사진은 받지 않는다."""
    body, encoding, final_url = fetch_public_page(url)
    page = _parse_html(body, encoding)
    return {
        "title": _label(page.meta.get("og:title") or page.title),
        "site_name": _label(page.meta.get("og:site_name")) or urlsplit(final_url).hostname,
        "text": page.text(),
        "url": final_url,
    }
