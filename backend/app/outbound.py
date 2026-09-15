"""외부 HTTP 요청은 이 파일에서만 한다(스펙 17절).

- 유튜브·인스타그램: 사용자가 보낸 주소를 요청하지 않고 영상 ID·게시물 코드로 고정 호스트 주소를 다시 만든다(fetch_fixed). 쿠팡 파트너스 API도 고정 호스트(coupang.py).
- 블로그 같은 일반 주소: https·443 포트·공인 IP만(DNS 결과 전부 + 검사한 IP 하나에만 연결 + 연결된 소켓의 상대 주소),
  리다이렉트는 매번 다시 검사해 최대 3번, text/html·3MB(fetch_public_page).
  본문 글에 레시피가 없어 보이는 페이지의 본문 사진(page_images)도 같은 검사로 받는다: 사진 형식은 파일 시그니처로 보고, 전체 10초.
- 둘 다 프록시 환경변수를 쓰지 않고, 리다이렉트까지 합쳐 8초가 지나면 감시 타이머가 소켓을 끊는다.
예외 메시지에는 주소·키를 넣지 않는다(FetchError는 예외·이유 이름만 담는다).
예외: 3a의 식약처 공공 레시피 동기화 CLI(`flask sync-public-recipes`, public_recipes.py)는 고정 호스트 하나를 운영자가 직접 부르는 명령이라 이 파일을 거치지 않는다.
"""

import ipaddress
import json
import re
import socket
import threading
import time
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
import urllib3.exceptions
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool

from .scan import sniff_image_type

MAX_BYTES = 3_000_000  # 만개의레시피 한 페이지가 1.2MB쯤이다. 조금씩 읽으며 세고(_read) 전체 시간도 TOTAL_SECONDS로 막는다
CONNECT_SECONDS = 3.05
TOTAL_SECONDS = 8
MAX_REDIRECTS = 3
MAX_LINK = 500
MAX_TEXT = 10_000
MAX_LABEL = 200  # 출처 카드 제목·채널 이름
HEADERS = {"User-Agent": "galmuri-kitchen/1.0"}
FIXED_HOSTS = {"www.googleapis.com", "www.youtube.com", "www.instagram.com", "api-gateway.coupang.com"}  # 쿠팡: 파트너스 딥링크(coupang.py)
REDIRECT_CODES = {301, 302, 303, 307, 308}
MAX_IMAGE_CANDIDATES = 8  # 블로그 본문 사진 후보(요청은 차례로)
MAX_PAGE_IMAGES = 5  # AI에 함께 보내는 본문 사진
MIN_IMAGE_BYTES = 15_000  # 이보다 작으면 아이콘·여백 이미지로 본다
MAX_IMAGE_BYTES = 1_500_000  # 본문 사진 한 장(페이지 MAX_BYTES보다 작게)
MAX_IMAGE_TOTAL_BYTES = 6_000_000  # 요청 하나가 AI를 기다리며 붙잡는 사진 합계(512MB 인스턴스, base64·SDK JSON으로 몇 배가 된다)
JPEG_HEADER_BYTES = 64_000  # SOFn은 이 안에서만 찾는다
JPEG_STANDALONE = (0x01, *range(0xD0, 0xD9))  # 길이 없는 마커(TEM·RSTn·SOI)
IMAGE_TOTAL_SECONDS = 10  # 사진 요청 전체(페이지 요청 8초와 따로)
MAX_IMAGE_SIDE = 8000  # AI API가 한 변이 이보다 긴 사진을 거절한다
JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# ponytail: 파일 이름·경로 규칙으로 꾸밈 이미지를 거른다. 엉뚱한 사진이 자주 섞이면 본문 영역(article·가장 긴 글 블록) 안의 <img>만 고르거나 크기(width·height) 속성을 본다.
# loading은 요청 목록 밖에서 더했다: eggiscoming.com 게시판은 본문 사진보다 앞에 15KB가 넘는 로딩 문구 PNG 4장이 있다.
DECOR_IMAGE = re.compile(r"logo|icon|btn|button|banner|sprite|profile|emoji|avatar|loading", re.I)
YOUTUBE_HOSTS = {"youtube.com", "music.youtube.com", "youtube-nocookie.com"}
YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
PLAYLIST_ID = re.compile(r"[A-Za-z0-9_-]{2,40}")
INSTAGRAM_CODE = re.compile(r"[A-Za-z0-9_-]{5,40}")
NAVER_BLOG_PATH = re.compile(r"/([A-Za-z0-9_-]+)/(\d+)/?")
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
PLAYLIST_SIZE = 30
THUMBNAIL_HOSTS = {"i.ytimg.com", "yt3.ggpht.com", "yt3.googleusercontent.com"}
MAX_CHANNEL_TITLE = 100
MAX_DESCRIPTION = 500  # 영상 보기 화면 설명 미리보기
ISO_DURATION = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")
# is_global이어도 안에 IPv4를 담아 사설 주소로 이어질 수 있는 IPv6 대역(NAT64·IPv4 호환·IPv4 변환·사이트 로컬·6to4)
IPV6_WRAPPERS = [
    ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "::/96", "::ffff:0:0:0/96", "fec0::/10", "2002::/16")
]


class FetchError(Exception):
    """외부 요청 실패. 메시지는 예외·이유 이름뿐이다(주소·키 없음)."""


def _is_public(ip):
    try:
        address = ipaddress.ip_address(ip.split("%", 1)[0])  # IPv6 zone(%eth0) 제거
    except ValueError:
        return False
    if address.version == 6:
        if address.ipv4_mapped:
            address = address.ipv4_mapped  # ::ffff:127.0.0.1
        elif any(address in network for network in IPV6_WRAPPERS):
            return False
    return address.is_global and not address.is_multicast


def _host_key(host):
    """requests가 보내는 호스트(IDNA)와 urlsplit 호스트를 같은 모양으로. 맞지 않으면 연결하지 않는다(안전한 쪽)."""
    host = host.rstrip(".").lower()
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


class PublicOnlyHTTPSConnection(HTTPSConnection):
    """addresses가 있으면 검사한 IP 하나에만 연결한다(DNS를 다시 묻지 않고, A 레코드를 여러 개 돌지 않는다).
    연결된 소켓의 상대 주소가 공인 IP가 아니면 TLS·요청 헤더를 보내기 전에 끊는다.
    소켓은 어댑터에 dup해 모아 두고, 전체 시간이 지나면 감시 타이머가 shutdown으로 막힌 TLS·읽기를 깨운다.
    urllib3 2.x에서 connect()가 소켓을 만드는 _new_conn()을 감싼다."""

    addresses = None  # 호스트 키 → 검사한 IP
    adapter = None  # PublicOnlyAdapter(소켓 모으기·감시 타이머)

    def _new_conn(self):
        if self.addresses is None:
            sock = super()._new_conn()
        else:
            ip = self.addresses.get(_host_key(self.host))
            if ip is None:
                raise FetchError("Unchecked")
            host, self._dns_host = self._dns_host, ip
            try:
                sock = super()._new_conn()
            finally:
                self._dns_host = host  # TLS 인증서 확인·Host 헤더는 원래 호스트 이름으로
        try:
            public = _is_public(sock.getpeername()[0])
        except OSError:
            public = False
        if not public:
            sock.close()
            raise FetchError("PrivateAddress")
        if self.adapter is not None:
            self.adapter.register(sock)
        return sock


class PublicOnlyAdapter(HTTPAdapter):
    """요청 한 번(리다이렉트 포함)에만 쓴다."""

    def __init__(self, addresses=None):
        self.sockets, self.expired, self.closed = [], False, False
        self.lock = threading.Lock()  # 감시 타이머 스레드와 요청 스레드가 sockets·expired·closed를 함께 본다
        connection = type("PinnedConnection", (PublicOnlyHTTPSConnection,), {"addresses": addresses, "adapter": self})
        self.pool_class = type("PinnedPool", (HTTPSConnectionPool,), {"ConnectionCls": connection})
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"https": self.pool_class}  # http는 앞에서 거절한다

    def register(self, sock):
        """새 연결을 감시 대상에 넣는다. 이미 시간이 지났으면(타이머가 먼저 돌았으면) 연결을 닫고 멈춘다."""
        with self.lock:
            if self.expired or self.closed:
                sock.close()
                raise FetchError("TooSlow")
            self.sockets.append(sock.dup())  # 같은 연결을 가리키는 우리 fd라 다른 스레드에서 shutdown해도 안전하다

    def expire(self):
        with self.lock:
            if self.closed:  # 닫은 fd 번호는 다른 연결이 다시 쓸 수 있다
                return
            self.expired = True
            for sock in self.sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def close(self):
        with self.lock:
            self.closed = True
            sockets, self.sockets = self.sockets, []
        super().close()
        for sock in sockets:
            sock.close()


def _remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise FetchError("TooSlow")
    return left


def _read(res, deadline, adapter, limit):
    """본문을 작게(read1) 읽으며 크기·남은 시간을 매번 확인한다. 조금씩 흘려 보내는 서버도 제한 시간 안에 끊긴다."""
    chunks, size = [], 0
    while True:
        _remaining(deadline)
        chunk = res.raw.read1(8192, decode_content=True)
        if adapter.expired:
            raise FetchError("TooSlow")
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > limit:
            raise FetchError("TooLarge")
        chunks.append(chunk)


def _charset(res):
    match = re.search(r"charset=[\"']?([\w.:-]+)", res.headers.get("Content-Type", ""), re.I)
    return match.group(1) if match else None


def _check_public_url(url):
    """https·443·사용자정보 없음·IP 문자열 아님·DNS 결과가 모두 공인 IP. (호스트 키, 연결할 IP). 통과하지 못하면 FetchError."""
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
    # ponytail: getaddrinfo에는 시간 제한이 없어 감시 타이머로도 끊지 못한다. 느린 DNS가 문제면 별도 스레드로 기다린다.
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as e:
        raise FetchError(type(e).__name__) from None
    if not infos or not all(_is_public(info[4][0]) for info in infos):
        raise FetchError("PrivateAddress")
    return _host_key(host), infos[0][4][0]  # 첫 주소 하나에만 연결한다


def _fetch(url, params=None, public=False, image=False, seconds=None, json_body=None, headers=None):
    """(본문, charset, 최종 주소). public이면 매 단계 주소를 검사하고 리다이렉트를 따라간다.
    image면 Content-Type을 보지 않고(부른 쪽이 파일 시그니처로 본다) MAX_IMAGE_BYTES까지만 읽는다. seconds는 리다이렉트까지 합친 제한 시간(기본 TOTAL_SECONDS).
    json_body를 주면 POST로 보낸다(headers는 기본 헤더에 더한다)."""
    seconds = TOTAL_SECONDS if seconds is None else seconds
    addresses = {} if public else None
    adapter = PublicOnlyAdapter(addresses)
    session = requests.Session()
    session.trust_env = False  # 프록시 환경변수·.netrc를 쓰지 않는다
    session.mount("https://", adapter)
    deadline = time.monotonic() + seconds
    watchdog = threading.Timer(seconds, adapter.expire)
    watchdog.daemon = True
    watchdog.start()
    try:
        for _ in range(MAX_REDIRECTS + 1 if public else 1):
            _remaining(deadline)  # 시간이 지난 뒤 시작하는 단계는 DNS도 묻지 않는다
            if public:
                host, ip = _check_public_url(url)
                addresses[host] = ip
            timeout = (CONNECT_SECONDS, _remaining(deadline))
            res = session.request(
                "POST" if json_body is not None else "GET", url, params=params, json=json_body, headers={**HEADERS, **(headers or {})},
                timeout=timeout, allow_redirects=False, stream=True,
            )
            with res:
                if public and res.status_code in REDIRECT_CODES:
                    location = res.headers.get("Location")
                    if not location:
                        raise FetchError("BadRedirect")
                    url = urljoin(url, location)
                    continue
                if res.status_code != 200:
                    raise FetchError(f"HTTP{res.status_code}")
                if public and not image and not res.headers.get("Content-Type", "").lower().startswith("text/html"):
                    raise FetchError("NotHtml")
                return _read(res, deadline, adapter, MAX_IMAGE_BYTES if image else MAX_BYTES), _charset(res), url
        raise FetchError("TooManyRedirects")
    except (requests.RequestException, urllib3.exceptions.HTTPError, OSError, ValueError) as e:  # ValueError: 모양이 틀린 Location(urljoin)
        raise FetchError("TooSlow" if adapter.expired else type(e).__name__) from None
    finally:
        watchdog.cancel()
        watchdog.join()  # 돌고 있는 타이머가 끝난 뒤에 dup한 fd를 닫는다
        session.close()


def fetch_fixed(url, params=None, json_body=None, headers=None, seconds=None):
    """정해 둔 호스트(유튜브 API·유튜브·인스타그램·쿠팡 API)만, 리다이렉트 없이 요청한다. (본문, charset). json_body를 주면 POST."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in FIXED_HOSTS or parts.netloc != parts.hostname:
        raise FetchError("HostNotAllowed")
    return _fetch(url, params, json_body=json_body, headers=headers, seconds=seconds)[:2]


def fetch_public_page(url):
    """사용자가 준 일반 주소(블로그 등)를 요청한다. (본문, charset, 검사를 통과한 최종 주소)."""
    return _fetch(url, public=True)


def image_size(data):
    """파일 머리에서 (가로, 세로)를 읽는다(JPEG SOFn · PNG IHDR · WEBP VP8/VP8L/VP8X). 읽지 못하면 None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")) if data[12:16] == b"IHDR" and len(data) >= 24 else None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk, body = data[12:16], data[20:]
        if chunk == b"VP8 " and body[3:6] == b"\x9d\x01\x2a" and len(body) >= 10:
            return int.from_bytes(body[6:8], "little") & 0x3FFF, int.from_bytes(body[8:10], "little") & 0x3FFF
        if chunk == b"VP8L" and body[:1] == b"\x2f" and len(body) >= 5:
            bits = int.from_bytes(body[1:5], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X" and len(body) >= 10:
            return int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1
        return None
    if data[:2] != b"\xff\xd8":
        return None
    data, i = data[:JPEG_HEADER_BYTES], 2
    while i + 4 <= len(data):  # 마커(0xFF xx)와 길이(2바이트)를 따라 SOFn까지 건너뛴다. i는 매번 1 이상 늘어 끝난다
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # 채움 바이트
            i += 1
            continue
        if marker in JPEG_STANDALONE:
            i += 2
            continue
        if marker in JPEG_SOF:
            return (int.from_bytes(data[i + 7 : i + 9], "big"), int.from_bytes(data[i + 5 : i + 7], "big")) if i + 9 <= len(data) else None
        i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return None


def page_images(urls):
    """블로그 본문 사진 후보 주소를 앞에서부터 8개까지 차례로 받아 [(bytes, media_type)] 최대 5장.
    페이지와 같은 공인 주소 검사·리다이렉트 3번, 한 장 1.5MB·합계 6MB(다음 사진이 넘기면 멈춘다). JPEG·PNG·WEBP 시그니처이고 15KB 이상, 머리에서 읽은 가로·세로가 8000px 이하만.
    실패한 사진은 건너뛴다(모두 걸러지면 빈 목록 → 글만 보낸다).
    사진 요청 전체가 10초를 넘기지 않게 한 장마다 남은 시간만 준다. 사진은 저장하지 않는다."""
    images, total, deadline = [], 0, time.monotonic() + IMAGE_TOTAL_SECONDS
    for url in urls[:MAX_IMAGE_CANDIDATES]:
        left = deadline - time.monotonic()
        if left <= 0 or len(images) == MAX_PAGE_IMAGES:
            break
        try:
            data = _fetch(url, public=True, image=True, seconds=left)[0]
        except FetchError:
            continue
        media_type, size = sniff_image_type(data), image_size(data)
        if media_type and len(data) >= MIN_IMAGE_BYTES and size and 0 < min(size) and max(size) <= MAX_IMAGE_SIDE:
            if total + len(data) > MAX_IMAGE_TOTAL_BYTES:
                break
            images.append((data, media_type))
            total += len(data)
    return images


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
    if bare in YOUTUBE_HOSTS or bare == "youtu.be":
        if bare == "youtu.be":
            video_id = segments[1] if len(segments) > 1 else ""
        elif parts.path.rstrip("/") == "/watch":
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
        sizes = [thumbnails.get(size) for size in ("high", "medium", "default")]
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise FetchError("BadResponse") from None
    if snippet is None:
        return None
    thumbnail = next((s["url"] for s in sizes if isinstance(s, dict) and _https(s.get("url"))), None)
    description = snippet.get("description")
    return {
        "title": _label(snippet.get("title")),
        "description": description[:MAX_TEXT] if isinstance(description, str) else "",
        "channel_title": _label(snippet.get("channelTitle")),
        "thumbnail_url": thumbnail,
    }


def _thumbnail_url(value):
    """유튜브 이미지 호스트의 https 주소만(DB 칸 500자). 아니면 None."""
    if not isinstance(value, str) or len(value) > 500:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    return value if parts.scheme == "https" and parts.netloc in THUMBNAIL_HOSTS else None


def _thumbnail(snippet, sizes):
    thumbnails = snippet.get("thumbnails") if isinstance(snippet.get("thumbnails"), dict) else {}
    found = (thumbnails.get(size) for size in sizes)
    return next((t["url"] for t in found if isinstance(t, dict) and _thumbnail_url(t.get("url"))), None)


def _youtube_items(url, params):
    """유튜브 Data API 목록 응답의 items(1 unit). 모양이 틀리면 FetchError."""
    body, _ = fetch_fixed(url, params)
    try:
        items = json.loads(body)["items"]
    except (ValueError, KeyError, TypeError):
        raise FetchError("BadResponse") from None
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise FetchError("BadResponse")
    return items


def iso_duration(value):
    """"PT12M4S" → 724초. 0초(P0D, 생방송)·틀린 모양(P1W 등)·int 범위 밖 → None."""
    match = ISO_DURATION.fullmatch(value) if isinstance(value, str) else None
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = ((days * 24 + hours) * 60 + minutes) * 60 + seconds
    return total if 0 < total <= 2**31 - 1 else None  # DB int 칸


def channel_info(key, *, channel_id=None, handle=None, username=None):
    """채널 이름·썸네일·업로드 재생목록·영상 수(channels.list, 1 unit). 셋 중 하나로 찾는다. 없는 채널이면 None."""
    lookup = {"id": channel_id} if channel_id else {"forHandle": handle} if handle else {"forUsername": username}
    items = _youtube_items(CHANNELS_URL, {"part": "snippet,contentDetails,statistics", **lookup, "key": key})
    if not items:
        return None
    item = items[0]
    try:
        snippet = item.get("snippet") or {}
        uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
        count = (item.get("statistics") or {}).get("videoCount")
        found_id = item["id"]
    except (KeyError, TypeError, AttributeError):
        raise FetchError("BadResponse") from None
    if not (isinstance(found_id, str) and CHANNEL_ID.fullmatch(found_id) and isinstance(uploads, str) and PLAYLIST_ID.fullmatch(uploads)):
        raise FetchError("BadResponse")
    return {
        "channel_id": found_id,
        "title": _label(snippet.get("title"))[:MAX_CHANNEL_TITLE],
        "thumbnail_url": _thumbnail(snippet, ("default", "medium", "high")),
        "uploads_playlist_id": uploads,
        "video_count": int(count) if isinstance(count, str) and count.isdigit() and len(count) < 10 else None,
    }


def playlist_videos(key, playlist_id):
    """재생목록 최근 영상 30개(playlistItems.list, 1 unit). 비공개·삭제 영상(공개 날짜 없음)은 뺀다. 재생목록이 없으면 None."""
    params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": PLAYLIST_SIZE, "key": key}
    try:
        items = _youtube_items(PLAYLIST_ITEMS_URL, params)
    except FetchError as e:
        if str(e) == "HTTP404":  # playlistNotFound: 채널이 없어졌거나 비공개
            return None
        raise
    videos = []
    for item in items:
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        details = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
        video_id, published = details.get("videoId"), details.get("videoPublishedAt")
        if not (isinstance(video_id, str) and YOUTUBE_ID.fullmatch(video_id) and isinstance(published, str)):
            continue
        try:
            published_at = datetime.fromisoformat(published)
        except ValueError:
            continue
        if published_at.tzinfo is None:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": _label(snippet.get("title")),
                "thumbnail_url": _thumbnail(snippet, ("medium", "high", "default")),  # 목록 썸네일 128×72
                "published_at": published_at,
            }
        )
    return videos


def video_details(key, video_ids):
    """영상 길이(초)·설명 앞 500자(videos.list, 최대 50개, 1 unit). {video_id: {duration_seconds, description}}."""
    if not video_ids:
        return {}
    items = _youtube_items(VIDEOS_URL, {"part": "contentDetails,snippet", "id": ",".join(video_ids[:50]), "key": key})
    details = {}
    for item in items:
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        content = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
        description = snippet.get("description")
        if isinstance(item.get("id"), str):
            details[item["id"]] = {
                "duration_seconds": iso_duration(content.get("duration")),
                "description": (description.strip()[:MAX_DESCRIPTION] or None) if isinstance(description, str) else None,
            }
    return details


class _Page(HTMLParser):
    """og 메타·<title>·본문 글. script·style·noscript·nav·header·footer·form 안의 글은 버린다.
    열린 태그를 쌓아 두고 부모가 닫히면 함께 닫아, 닫히지 않은 <form>·<title>이 나머지 글을 삼키지 않게 한다."""

    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "form"}
    BLOCK = {"p", "div", "br", "li", "tr", "dd", "dt", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul", "ol", "table", "blockquote"}
    CELL = {"td", "th"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    RCDATA_CONTENT_ELEMENTS = ("textarea",)  # <title>을 글자 그대로 읽으면 닫히지 않았을 때 끝까지 삼킨다

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self.parts, self.images = {}, None, [], []
        self._open, self._title = [], None

    def end_title(self):
        if self._title is not None:
            self.title, self._title = "".join(self._title), None

    def _separator(self, tag):
        self.parts.append("\n" if tag in self.BLOCK else " " if tag in self.CELL else "")

    def handle_starttag(self, tag, attrs):
        self.end_title()
        if tag == "meta":
            attrs = dict(attrs)
            key, content = attrs.get("property") or attrs.get("name"), attrs.get("content")
            if key in ("og:title", "og:description", "og:image", "og:site_name") and content:
                self.meta.setdefault(key, content)
        elif tag == "title" and self.title is None:
            self._title = []
        elif tag == "img":  # 글과 달리 form 안의 사진도 모은다(카페24 게시판은 글 전체가 <form> 안에 있다)
            attrs = dict(attrs)
            src = attrs.get("data-src") or attrs.get("src")  # 늦게 불러오는 사진은 src가 자리 표시 이미지다
            if src:
                self.images.append(src)
        if tag not in self.VOID and tag != "title":
            self._open.append(tag)
        self._separator(tag)

    def handle_endtag(self, tag):
        self.end_title()
        if tag in self._open:
            while self._open.pop() != tag:
                pass
        self._separator(tag)

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        elif not any(tag in self.SKIP for tag in self._open):
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
    page.end_title()
    return page


def instagram_post(shortcode):
    """게시물 링크 미리보기(og:description)에서 캡션을 읽는다. 게시물 미리보기가 아니면(로그인 화면 등) None."""
    page = _parse_html(*fetch_fixed(f"https://www.instagram.com/p/{shortcode}/"))
    title = _label(page.meta.get("og:title"))
    caption = page.meta.get("og:description", "").strip()
    if not caption or not any(mark in title for mark in ("on Instagram", "Instagram에서", "Instagram의")):
        return None
    return {"caption": caption[:MAX_TEXT], "title": title, "thumbnail_url": _https(page.meta.get("og:image"))}


def _image_candidates(sources, base):
    """<img> 주소 → 최종 주소 기준 절대 https 주소. svg·gif·꾸밈 이름(DECOR_IMAGE)은 빼고, 중복 없이 8개까지."""
    found = []
    for src in sources:
        try:
            url = urljoin(base, src.strip())
            parts = urlsplit(url)
        except ValueError:
            continue
        path = parts.path.lower()
        if len(url) > MAX_LINK or parts.scheme != "https" or path.endswith((".svg", ".gif")) or DECOR_IMAGE.search(path) or url in found:
            continue  # http 주소는 https로 바꾸지 않고 뺀다
        found.append(url)
        if len(found) == MAX_IMAGE_CANDIDATES:
            break
    return found


def web_page(url):
    """공개 웹 페이지의 제목·사이트 이름·본문 글·본문 사진 후보 주소, 검사를 통과한 최종 주소. 사진은 여기서 받지 않는다(page_images)."""
    body, encoding, final_url = fetch_public_page(url)
    page = _parse_html(body, encoding)
    return {
        "title": _label(page.meta.get("og:title") or page.title),
        "site_name": _label(page.meta.get("og:site_name")) or urlsplit(final_url).hostname,
        "text": page.text(),
        "images": _image_candidates(page.images, final_url),
        "url": final_url,
    }
