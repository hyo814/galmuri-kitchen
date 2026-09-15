"""쿠팡 파트너스 제휴 링크(스펙 16·25절).

화면(storeLinks.ts)이 만든 일반 쿠팡 검색 주소를 `GET /api/shop-links/coupang/go?url=`로 보내면
파트너스 딥링크 API로 바꿔 302로 보낸다. 새 창 링크(<a target=_blank>)라 팝업 차단에 걸리지 않는다.
- 키(COUPANG_ACCESS_KEY·COUPANG_SECRET_KEY)가 없거나, 로그인 안 됨·체험 계정이거나, API가 실패·3초를 넘기거나,
  호출 한도에 걸리면 일반 주소로 보낸다. 실패한 주소는 10분, rCode 오류·HTTP 429 뒤에는 모든 호출을 10분 쉰다.
- 쿠팡 한도는 딥링크 1시간 100번(넘기면 24시간 차단, 3번이면 파트너스 기능 전체 차단) → 전체 1시간 80번·사용자 1시간 10번,
  같은 주소는 24시간 기억한다.
서명: https://developers.coupang.com/hc/en-us/articles/360033461914-Creating-HMAC-Signature
"""

import hashlib
import hmac
import json
import re
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, quote, urlsplit

from flask import Blueprint, abort, current_app, redirect, request

from . import outbound
from .auth import current_user
from .models import AiCall, db, utcnow

bp = Blueprint("coupang", __name__)

API_HOST = "https://api-gateway.coupang.com"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
TIMEOUT_SECONDS = 3
GLOBAL_HOURLY = 80  # 쿠팡 한도 100번/시간보다 여유 있게(gunicorn 워커끼리 동시에 세면 몇 번 넘칠 수 있다)
USER_HOURLY = 10
CACHE_SECONDS = 24 * 60 * 60
FAILURE_SECONDS = 10 * 60  # 실패한 주소는 이만큼 일반 주소로 기억하고, rCode 오류·429 뒤에는 모든 호출을 쉰다
# 딥링크 단축 링크 모양(https://link.coupang.com/a/xxxx). 포트·쿼리·백슬래시·줄바꿈이 섞이면 따르지 않는다
SHORTEN_URL = re.compile(r"https://link\.coupang\.com/[A-Za-z0-9/_\-]+")
CACHE_SIZE = 500
KIND = "shop_link"  # ai_calls 기록(AI 호출 아님, 토큰 없음). AI 한도·사용량에는 세지 않는다
# storeLinks.ts 쿠팡 칸의 sorter 값. 표를 고치면 여기도 고친다
SORTERS = {"salePriceAsc", "saleCountDesc", "latestAsc"}
MAX_QUERY = 50  # storeLinks.ts searchQuery와 같은 글자 수

# ponytail: 프로세스 메모리 캐시라 워커(2개)마다 따로이고 재시작하면 비어 같은 주소를 하루 몇 번 더 부를 수 있다. 모자라면 DB 표로 옮긴다
_cache = OrderedDict()
_lock = threading.Lock()
_paused_until = 0.0  # 프로세스마다. rCode 오류·HTTP 429 뒤 이 시각(monotonic)까지 API를 부르지 않는다


def authorization(access_key, secret_key, method, path, query="", now=None):
    """CEA HMAC 헤더. 서명할 문장 = signed-date(yyMMdd'T'HHmmss'Z', UTC) + method + path + query('?' 없이)."""
    signed = (now or datetime.now(UTC)).strftime("%y%m%dT%H%M%SZ")
    signature = hmac.new(secret_key.encode(), f"{signed}{method}{path}{query}".encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={signed}, signature={signature}"


def plain_search_url(value):
    """www.coupang.com/np/search 검색 주소만(q 필수 50자 이하, sorter는 표에 있는 값만). 통과하면 다시 만든 주소, 아니면 None."""
    if not value or len(value) > 2000:
        return None
    try:
        parts = urlsplit(value)
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    args = dict(pairs)
    if (
        parts.scheme != "https" or parts.netloc != "www.coupang.com" or parts.path != "/np/search" or parts.fragment
        or len(args) != len(pairs) or not set(args) <= {"q", "sorter"}
        or not args.get("q", "").strip() or len(args["q"]) > MAX_QUERY
        or ("sorter" in args and args["sorter"] not in SORTERS)
    ):
        return None
    url = f"https://www.coupang.com/np/search?q={quote(args['q'], safe='')}"
    return url + (f"&sorter={args['sorter']}" if "sorter" in args else "")


def deeplink(plain, access_key, secret_key):
    """일반 쿠팡 주소 → 파트너스 단축 링크. 실패하면 FetchError·ValueError 계열 예외."""
    body, _ = outbound.fetch_fixed(
        API_HOST + DEEPLINK_PATH,
        json_body={"coupangUrls": [plain]},
        headers={"Authorization": authorization(access_key, secret_key, "POST", DEEPLINK_PATH)},
        seconds=TIMEOUT_SECONDS,
    )
    data = json.loads(body)
    if str(data.get("rCode")) != "0":
        raise ValueError("rCode")
    url = data["data"][0]["shortenUrl"]
    # urlsplit 호스트 검사는 `\`·줄바꿈을 브라우저와 다르게 읽어 우회된다 → 문자열 전체를 좁은 모양으로만 받는다
    if not isinstance(url, str) or not SHORTEN_URL.fullmatch(url):
        raise ValueError("NotShortenUrl")
    return url


def _cached(plain):
    with _lock:
        hit = _cache.get(plain)
        if hit and hit[1] > time.monotonic():
            _cache.move_to_end(plain)
            return hit[0]
    return None


def _remember(plain, url, seconds=CACHE_SECONDS):
    with _lock:
        _cache[plain] = (url, time.monotonic() + seconds)
        _cache.move_to_end(plain)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def _within_budget(user_id):
    since = utcnow() - timedelta(hours=1)
    recent = AiCall.query.filter(AiCall.kind == KIND, AiCall.created_at >= since)
    return recent.count() < GLOBAL_HOURLY and recent.filter(AiCall.user_id == user_id).count() < USER_HOURLY


def affiliate_url(plain, user):
    """user가 None(로그인 안 됨)이거나 체험 계정이면 API도 기록도 없이 일반 주소."""
    global _paused_until
    access, secret = current_app.config["COUPANG_ACCESS_KEY"], current_app.config["COUPANG_SECRET_KEY"]
    if not (access and secret) or user is None or user.provider == "demo":
        return plain
    if cached := _cached(plain):
        return cached
    if time.monotonic() < _paused_until or not _within_budget(user.id):
        return plain
    # 실패한 호출도 쿠팡 한도에 세므로 부르기 전에 기록한다. 외부 요청을 기다리는 동안 DB 연결을 잡지 않게 커밋한다
    db.session.add(AiCall(user_id=user.id, kind=KIND, model=None, created_at=utcnow()))
    db.session.commit()
    try:
        url = deeplink(plain, access, secret)
    except (outbound.FetchError, ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        pause = str(e) in ("rCode", "HTTP429")  # 쿠팡이 거절했다 → 한도를 더 쓰지 않게 모두 쉰다
        current_app.logger.warning("coupang deeplink failed: %s%s", type(e).__name__, f" {e}" if pause else "")  # 주소·키는 남기지 않는다
        if pause:
            _paused_until = time.monotonic() + FAILURE_SECONDS
        _remember(plain, plain, FAILURE_SECONDS)
        return plain
    _remember(plain, url)
    return url


@bp.get("/api/shop-links/coupang/go")
def go():
    """로그인이 풀린 새 창에서도 JSON 401 대신 일반 검색 결과로 보낸다(API 호출·기록 없음)."""
    plain = plain_search_url(request.args.get("url", ""))
    if plain is None:
        abort(400)
    res = redirect(affiliate_url(plain, current_user()), 302)
    res.headers["Cache-Control"] = "no-store"
    res.headers["Referrer-Policy"] = "no-referrer"
    return res
