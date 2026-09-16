"""요리 채널 영상(스펙 17절). 고른 채널(기본 채널 + 내 채널)의 최근 영상을 서버에 캐시해 최신순으로 보여준다.

유튜브 Data API 사용량(units): 채널 새로 받기 = channels.list + playlistItems.list + videos.list = 3.
검색은 캐시된 제목·설명에서만 한다(search.list 100 units는 쓰지 않는다). 외부 요청은 outbound.py에서만 한다.
쿼터 보호: 새로 받기는 `ai_calls.kind = video_refresh`, 채널 추가는 `channel_add`로 기록해(토큰 없음, AI 사용량·원가에 안 셈)
사용자별 하루 새로 받기 20번·채널 추가 30번, 전체 24시간 추정 8,000 units 안에서만 유튜브를 부른다.
"""

import json
import re
import time
import zlib
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from . import outbound, scan
from .auth import login_required
from .models import AiCall, UserChannel, YoutubeChannel, YoutubeVideo, db, utcnow
from .recipe_ai import FETCH_BURST_LIMIT, FETCH_DAILY_LIMIT
from .validation import commit_or_duplicate, decode_cursor, encode_cursor, iso_datetime

bp = Blueprint("videos", __name__, url_prefix="/api", cli_group=None)  # 명령은 `flask seed-default-channels`

DEFAULT_CHANNELS_FILE = Path(__file__).parent / "data" / "default_channels.json"
PAGE_SIZE = 30
FEED_PER_CHANNEL = 12  # 전체 목록에는 채널마다 최신 12개까지만 섞는다(자주 올리는 채널이 도배하지 않게). 채널 칩·검색은 받아둔 50개 모두
MAX_QUERY = 50
SEARCH_LIMIT = 100  # 검색은 커서 없이 한 번에
MINE_LIMIT = 30
STALE_AFTER = timedelta(hours=6)
KEEP_FOR = timedelta(days=30)  # 유튜브 약관: 받은 정보를 30일 넘게 두지 않는다
REFRESH_PER_REQUEST = 3
REQUEST_SECONDS = 8  # 목록 요청 하나에서 새로 받기에 쓰는 시간. 넘으면 남은 채널은 다음 요청에서
REFRESH_DAILY_LIMIT = 20  # 사용자별 하루(서울 날짜) 새로 받기
CHANNEL_ADD_DAILY_LIMIT = 30
CHANNEL_ADD_BURST_LIMIT = 10
DAILY_UNIT_BUDGET = 8_000  # 무료 10,000 units 중 링크 가져오기·여유분을 남긴다
UNITS_PER_REFRESH = 3
UNITS_PER_ADD = 3  # 캐시된 채널 추가(0 units)도 넉넉히 센다
REFRESH_KINDS = ("video_refresh",)
CHANNEL_ADD_KINDS = ("channel_add",)
CHANNEL_LOCK_KEY = zlib.crc32(b"user_channels") & 0x7FFFFFFF
MAX_INT = 2**31 - 1
CHANNEL_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
HANDLE = re.compile(r"@[\w.-]{3,30}")  # 한글 핸들도 있다
USERNAME = re.compile(r"[A-Za-z0-9._-]{1,50}")
OFF = "영상을 지금은 볼 수 없어요."
CANNOT_ADD = "지금은 채널을 추가할 수 없어요."
CANNOT_CHANGE = "지금은 채널을 바꿀 수 없어요."
BAD_LINK = "채널 링크를 다시 확인해주세요. youtube.com/@이름 또는 youtube.com/channel/… 모양의 주소를 붙여 넣어주세요."

# 키 없는 개발 모드용 예시(시안 Videos·VideoPlay·Channels). 썸네일 없음, DB·네트워크 없음.
SAMPLE_CHANNELS = [
    {"id": 1, "title": "집밥 연구소", "video_count": 248, "is_default": False, "hidden": False},
    {"id": 2, "title": "자취요리 한 끼", "video_count": 97, "is_default": False, "hidden": False},
    {"id": 3, "title": "오늘의 반찬", "video_count": None, "is_default": True, "hidden": False},
    {"id": 4, "title": "한식 기본기", "video_count": None, "is_default": True, "hidden": False},
    {"id": 5, "title": "간단 도시락", "video_count": None, "is_default": True, "hidden": True},
]
SAMPLE_CHANNELS = [{**c, "youtube_id": None, "thumbnail_url": None, "unavailable": False} for c in SAMPLE_CHANNELS]
SAMPLE_VIDEOS = [  # (제목, 채널 id, 길이 초, 며칠 전, 설명)
    (
        "제육볶음 황금레시피, 이렇게만 하세요",
        1,
        724,
        3,
        "재료 (3인분)\n돼지고기 앞다리살 600g, 양파 1개, 대파 1대, 고추장 2큰술, 고춧가루 2큰술, 간장 2큰술, 설탕 1큰술, 다진 마늘 1큰술",
    ),
    ("냉장고 털이 두부조림 10분 완성", 2, 511, 5, "재료\n두부 1모, 대파 1/2대, 간장 3큰술, 고춧가루 1큰술, 물 반 컵"),
    ("국물이 진한 된장찌개 비법 3가지", 1, 887, 8, None),
    ("애호박 하나로 반찬 세 가지", 3, 612, 15, None),
    ("실패 없는 계란말이 모양 잡기", 2, 418, 16, None),
]


def video_mode(user):
    """on: 키 있음 / cached: 체험 계정 + 키 있음 + 받아 둔 기본 채널 영상이 있음(읽기만: 새로 받기·채널 바꾸기 없음, 유튜브 할당량을 쓰지 않는다) /
    sample: 키 없음 + 개발 모드(예시 목록) / off: 키 없음 + 운영(영상 칸 숨김)."""
    if user.provider == "demo":
        has_key = bool(current_app.config["YOUTUBE_API_KEY"])
        cached = has_key and (
            db.session.query(YoutubeVideo.id)
            .join(YoutubeChannel, YoutubeVideo.channel_id == YoutubeChannel.id)
            .filter(YoutubeChannel.is_default.is_(True), YoutubeVideo.fetched_at >= utcnow() - KEEP_FOR)
            .first()
            is not None
        )
        return "cached" if cached else "sample"
    if current_app.config["YOUTUBE_API_KEY"]:
        return "on"
    return "sample" if current_app.config["DEV_MODE"] else "off"


def parse_channel_link(value):
    """("id", UC…) | ("handle", "@이름") | ("username", 이름) | None. 사용자가 준 주소는 요청하지 않는다.
    /c/이름은 공식 조회 방법이 없어 받지 않는다(@이름이나 /channel/ 주소를 붙여 넣게 안내)."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > outbound.MAX_LINK:
        return None
    if HANDLE.fullmatch(value):
        return ("handle", value)
    if "://" not in value:
        value = f"https://{value}"  # 입력 칸 안내가 `youtube.com/@이름`이다
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or host not in CHANNEL_HOSTS:
        return None
    segments = unquote(parts.path).split("/")[1:] + ["", ""]
    first, second = segments[0], segments[1]
    if HANDLE.fullmatch(first):
        return ("handle", first)
    if first == "channel" and outbound.CHANNEL_ID.fullmatch(second):
        return ("id", second)
    if first == "user" and USERNAME.fullmatch(second):
        return ("username", second)
    return None


def visible_filter(user_id):
    """보이는 채널 = 숨기지 않은 기본 채널 ∪ 내가 추가한 채널. YoutubeChannel에 거는 조건."""
    rows = select(UserChannel.channel_id).where(UserChannel.user_id == user_id)
    return or_(
        and_(YoutubeChannel.is_default.is_(True), YoutubeChannel.id.not_in(rows.where(UserChannel.hidden.is_(True)))),
        YoutubeChannel.id.in_(rows.where(UserChannel.hidden.is_(False))),
    )


def is_stale(now):
    return or_(YoutubeChannel.fetched_at.is_(None), YoutubeChannel.fetched_at < now - STALE_AFTER)


def units_left(cost):
    """지난 24시간 추정 사용량(새로 받기 3, 채널 추가 3) + cost가 전체 예산 안인가.
    ponytail: 잠그지 않은 추정치 — 동시에 몰리면 조금 넘을 수 있어 예산을 무료 한도보다 낮게 잡았다."""
    since = scan.utcnow() - timedelta(days=1)
    counts = dict(
        db.session.query(AiCall.kind, func.count())
        .filter(AiCall.kind.in_(REFRESH_KINDS + CHANNEL_ADD_KINDS), AiCall.created_at >= since)
        .group_by(AiCall.kind)
        .all()
    )
    used = counts.get("video_refresh", 0) * UNITS_PER_REFRESH + counts.get("channel_add", 0) * UNITS_PER_ADD
    return used + cost <= DAILY_UNIT_BUDGET


def refresh_channel(channel, key, info=None):
    """채널 정보·최근 영상 50개·길이/설명을 새로 받아 영상을 통째로 바꾼다(3 units, info를 주면 2).
    채널·재생목록이 없어졌으면(삭제·비공개) 영상과 썸네일·영상 수·재생목록을 비운다(화면에 unavailable).
    요청 실패는 잠깐의 오류일 수 있어 캐시를 그대로 둔다. 성공·실패 모두 fetched_at을 지금으로.
    외부 요청을 기다리는 동안 트랜잭션을 열어 두지 않는다. 기록·예산 확인은 부르는 쪽(claim_and_refresh)이 한다."""
    pk, channel_id = channel.id, channel.channel_id
    db.session.commit()
    videos, details = None, {}
    try:
        if info is None:
            info = outbound.channel_info(key, channel_id=channel_id)
        if info is not None:
            videos = outbound.playlist_videos(key, info["uploads_playlist_id"])
        if videos:
            details = outbound.video_details(key, [v["video_id"] for v in videos])
    except outbound.FetchError as e:
        current_app.logger.warning("channel refresh failed: %s", e)  # 예외·이유 이름만(키 없음)
        db.session.execute(update(YoutubeChannel).where(YoutubeChannel.id == pk).values(fetched_at=utcnow()))
        db.session.commit()
        return
    channel = db.session.get(YoutubeChannel, pk)
    if channel is None:
        return
    now = utcnow()
    channel.fetched_at = now
    if videos is None:
        YoutubeVideo.query.filter_by(channel_id=pk).delete()
        channel.thumbnail_url = channel.video_count = channel.uploads_playlist_id = None
    else:
        channel.title = info["title"] or channel.title
        channel.thumbnail_url, channel.video_count = info["thumbnail_url"], info["video_count"]
        channel.uploads_playlist_id = info["uploads_playlist_id"]
        items = {v["video_id"]: v for v in videos}
        taken = {  # 다른 채널 행에 이미 있는 영상(UNIQUE)은 건너뛴다
            video_id
            for (video_id,) in db.session.query(YoutubeVideo.video_id).filter(
                YoutubeVideo.video_id.in_(list(items)), YoutubeVideo.channel_id != pk
            )
        }
        existing = {v.video_id: v for v in YoutubeVideo.query.filter_by(channel_id=pk)}
        for video_id, item in items.items():
            if video_id in taken:
                continue
            row = existing.pop(video_id, None) or YoutubeVideo(video_id=video_id, channel_id=pk)
            extra = details.get(video_id, {})
            row.title, row.thumbnail_url, row.published_at = item["title"], item["thumbnail_url"], item["published_at"]
            row.duration_seconds, row.description, row.fetched_at = extra.get("duration_seconds"), extra.get("description"), now
            db.session.add(row)
        for row in existing.values():
            db.session.delete(row)
    try:
        db.session.commit()
    except IntegrityError:  # 같은 영상을 다른 요청이 먼저 넣었다. 다음 새로 받기에서 맞춘다
        db.session.rollback()


def claim_and_refresh(user_id, key, pk, info=None):
    """사용자·전체 예산이 남았으면 채널을 차지하고(fetched_at 조건부 갱신, 동시 요청이 두 번 받지 않게) 기록한 뒤 새로 받는다.
    예산이 없으면 아무것도 하지 않는다(화면은 캐시된 영상을 그대로 본다)."""
    if scan.calls_today(user_id, REFRESH_KINDS) >= REFRESH_DAILY_LIMIT or not units_left(UNITS_PER_REFRESH):
        return
    now = utcnow()
    claimed = db.session.execute(update(YoutubeChannel).where(YoutubeChannel.id == pk, is_stale(now)).values(fetched_at=now)).rowcount
    if claimed:
        db.session.add(AiCall(user_id=user_id, kind="video_refresh", model=None, created_at=scan.utcnow()))
    db.session.commit()
    channel = db.session.get(YoutubeChannel, pk) if claimed else None
    if channel is not None:
        refresh_channel(channel, key, info)


def refresh_stale(user_id, key, deadline):
    """30일 넘게 새로 받지 못한 영상을 지우고, 보이는 채널 중 6시간 지난(또는 받은 적 없는) 채널을 오래된 순 3개까지,
    deadline(time.monotonic)이 지나기 전까지만 새로 받는다. 목록 첫 페이지에서만 부른다.
    ponytail: 요청 중 동기 갱신 — 채널이 많아져 목록이 늦어지면 Render cron으로 옮긴다. 채널 하나(외부 요청 3번)는 시간을 넘길 수 있다.
    ponytail: 30일 넘게 아무도 보지 않은 채널의 이름은 남는다(화면에 보일 때 먼저 새로 받는다). 약관 확인에서 문제되면 같이 비운다."""
    now = utcnow()
    YoutubeVideo.query.filter(YoutubeVideo.fetched_at < now - KEEP_FOR).delete()
    stale = (
        db.session.query(YoutubeChannel.id)
        .filter(visible_filter(user_id), is_stale(now))
        .order_by(YoutubeChannel.fetched_at.isnot(None), YoutubeChannel.fetched_at, YoutubeChannel.id)
        .limit(REFRESH_PER_REQUEST)
        .all()
    )
    db.session.commit()
    for (pk,) in stale:
        if time.monotonic() >= deadline:
            break
        claim_and_refresh(user_id, key, pk)


def sample_videos():
    now = utcnow()
    titles = {c["id"]: c["title"] for c in SAMPLE_CHANNELS}
    return [
        {
            "id": index,
            "video_id": f"sample{index:05d}",  # 11자 가짜 ID(재생되지 않는다)
            "title": title,
            "thumbnail_url": None,
            "duration_seconds": duration,
            "description": description,
            "published_at": iso_datetime(now - timedelta(days=days)),
            "channel_id": channel_id,
            "channel_title": titles[channel_id],
            "channel_thumbnail_url": None,
        }
        for index, (title, channel_id, duration, days, description) in enumerate(SAMPLE_VIDEOS, start=1)
    ]


LIST_FIELDS = ("id", "video_id", "title", "thumbnail_url", "duration_seconds", "published_at", "channel_id", "channel_title")


def video_json(video, channel, detail=False):
    body = {
        "id": video.id,
        "video_id": video.video_id,
        "title": video.title,
        "thumbnail_url": video.thumbnail_url,
        "duration_seconds": video.duration_seconds,
        "published_at": iso_datetime(video.published_at),
        "channel_id": channel.id,
        "channel_title": channel.title,
    }
    if detail:
        body.update(description=video.description, channel_thumbnail_url=channel.thumbnail_url)
    return body


def channel_json(channel, mine=False, hidden=False):
    """is_default는 화면 묶음(기본 채널)이다. 내가 추가한 뒤 기본 채널이 된 채널은 `내 채널`에 둔다.
    unavailable: 새로 받아 봤더니 채널·재생목록이 없어졌다(삭제·비공개). youtube_id: 채널 안 유튜브 검색 주소에 쓰는 UC… ID."""
    return {
        "id": channel.id,
        "youtube_id": channel.channel_id,
        "title": channel.title,
        "thumbnail_url": channel.thumbnail_url,
        "video_count": channel.video_count,
        "is_default": channel.is_default and not mine,
        "hidden": hidden,
        "unavailable": channel.fetched_at is not None and channel.uploads_playlist_id is None,
    }


@bp.get("/videos")
@login_required
def list_videos():
    """보이는 채널 영상 published_at·id 내림차순 커서 페이지(스펙 26절). q는 캐시된 제목·설명에서 찾아
    제목 일치 먼저(그 안은 최신순) 100개까지 한 번에 준다(cursor·limit은 무시, next_cursor 없음).
    새로 받기·오래된 영상 지우기는 첫 페이지(cursor 없음)에서만 한다."""
    mode = video_mode(g.user)
    if mode == "off":
        abort(503, OFF)
    limit = min(max(request.args.get("limit", PAGE_SIZE, type=int), 1), 50)
    q = request.args.get("q", "").strip()
    if len(q) > MAX_QUERY:
        abort(400, "검색어는 50자까지 입력해주세요.")
    channel = request.args.get("channel")
    if channel is not None:
        if not (channel.isascii() and channel.isdigit() and 0 < int(channel) <= MAX_INT):
            abort(400, "잘못된 요청이에요.")
        channel = int(channel)
    cursor = request.args.get("cursor")
    cursor = decode_cursor(cursor) if cursor and not q else None

    if mode == "sample":
        needle = q.lower()
        rows = [v for v in sample_videos() if channel is None or v["channel_id"] == channel]
        titled = [v for v in rows if needle in v["title"].lower()]
        described = [v for v in rows if needle not in v["title"].lower() and needle in (v["description"] or "").lower()]
        return jsonify(items=[{k: v[k] for k in LIST_FIELDS} for v in titled + described], next_cursor=None, sample=True)

    if cursor is None and mode != "cached":  # 체험 계정은 읽기만: 새로 받기 없음(유튜브 할당량을 쓰지 않는다)
        refresh_stale(g.user.id, current_app.config["YOUTUBE_API_KEY"], time.monotonic() + REQUEST_SECONDS)
    query = db.session.query(YoutubeVideo, YoutubeChannel).join(YoutubeChannel, YoutubeVideo.channel_id == YoutubeChannel.id)
    query = query.filter(visible_filter(g.user.id), YoutubeVideo.fetched_at >= utcnow() - KEEP_FOR)
    if channel is not None:
        query = query.filter(YoutubeChannel.id == channel)
    elif not q:
        # ponytail: 요청마다 창 함수로 채널별 순위를 매긴다(보이는 채널 × 30개라 가볍다). 느려지면 받을 때 순위를 저장한다
        rank = func.row_number().over(partition_by=YoutubeVideo.channel_id, order_by=(YoutubeVideo.published_at.desc(), YoutubeVideo.id.desc()))
        ranked = select(YoutubeVideo.id, rank.label("rank")).where(YoutubeVideo.fetched_at >= utcnow() - KEEP_FOR).subquery()
        query = query.filter(YoutubeVideo.id.in_(select(ranked.c.id).where(ranked.c.rank <= FEED_PER_CHANNEL)))
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        in_title = YoutubeVideo.title.ilike(pattern, escape="\\")
        # ponytail: 캐시(채널마다 최근 50개) 안에서만 찾아 결과가 적다 — 100개를 넘기면 커서에 제목 일치 여부를 넣어 페이지로 나눈다
        rows = (
            query.filter(or_(in_title, YoutubeVideo.description.ilike(pattern, escape="\\")))
            .order_by(in_title.desc(), YoutubeVideo.published_at.desc(), YoutubeVideo.id.desc())  # 제목 일치 먼저
            .limit(SEARCH_LIMIT)
            .all()
        )
        return jsonify(items=[video_json(video, ch) for video, ch in rows], next_cursor=None, sample=False)
    if cursor:
        published_at, video_pk = cursor
        query = query.filter(
            or_(YoutubeVideo.published_at < published_at, and_(YoutubeVideo.published_at == published_at, YoutubeVideo.id < video_pk))
        )
    rows = query.order_by(YoutubeVideo.published_at.desc(), YoutubeVideo.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    items = [video_json(video, ch) for video, ch in rows[:limit]]
    last = rows[limit - 1][0] if has_more else None
    return jsonify(items=items, next_cursor=encode_cursor(last.published_at, last.id) if last else None, sample=False)


@bp.get("/videos/<int:video_pk>")
@login_required
def get_video(video_pk):
    mode = video_mode(g.user)
    if mode == "off":
        abort(503, OFF)
    if mode == "sample":
        found = next((v for v in sample_videos() if v["id"] == video_pk), None)
        if found is None:
            abort(404, "찾을 수 없어요.")
        return jsonify(found)
    row = (
        db.session.query(YoutubeVideo, YoutubeChannel)
        .join(YoutubeChannel, YoutubeVideo.channel_id == YoutubeChannel.id)
        .filter(YoutubeVideo.id == video_pk, YoutubeVideo.fetched_at >= utcnow() - KEEP_FOR, visible_filter(g.user.id))
        .first()
        if video_pk <= MAX_INT
        else None
    )
    if row is None:
        abort(404, "찾을 수 없어요.")
    return jsonify(video_json(*row, detail=True))


@bp.get("/channels")
@login_required
def list_channels():
    """내가 추가한 채널(추가한 순) 다음 기본 채널. 영상 칸 채널 칩은 hidden이 아닌 것."""
    mode = video_mode(g.user)
    if mode == "off":
        abort(503, OFF)
    if mode == "sample":
        mine = sum(1 for c in SAMPLE_CHANNELS if not c["is_default"])
        return jsonify(items=SAMPLE_CHANNELS, mine_count=mine, mine_limit=MINE_LIMIT, sample=True)
    rows = (
        db.session.query(YoutubeChannel, UserChannel.hidden)
        .join(UserChannel, UserChannel.channel_id == YoutubeChannel.id)
        .filter(UserChannel.user_id == g.user.id)
        .order_by(UserChannel.created_at, UserChannel.id)
        .all()
    )
    mine = [channel for channel, hidden in rows if not hidden]
    hidden_ids = {channel.id for channel, hidden in rows if hidden}
    mine_ids = {channel.id for channel in mine}
    defaults = YoutubeChannel.query.filter(YoutubeChannel.is_default.is_(True)).order_by(YoutubeChannel.id).all()
    items = [channel_json(c, mine=True) for c in mine]
    items += [channel_json(c, hidden=c.id in hidden_ids) for c in defaults if c.id not in mine_ids]
    return jsonify(items=items, mine_count=len(mine), mine_limit=MINE_LIMIT, sample=False)


def find_channel(channel_id):
    return YoutubeChannel.query.filter_by(channel_id=channel_id).first()


def lock_user_channels(user_id):
    """PostgreSQL은 사용자별 트랜잭션 잠금으로 채널 개수 확인·추가를 한 줄로 세운다(커밋·롤백 때 풀린다)."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(:key, :user_id)"), {"key": CHANNEL_LOCK_KEY, "user_id": user_id})
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 31개가 될 수 있다. 운영은 PostgreSQL이다.


@bp.post("/channels")
@login_required
def add_channel():
    """채널 링크로 내 채널 추가. 추가는 모두 사용자별 한도로 세고, 처음 보는 채널이면 channels.list로 찾는다
    (링크 가져오기와 같은 link_fetch 한도·전체 예산 안에서). 받은 적 없는 채널은 바로 영상을 받는다(예산이 있으면)."""
    data = request.get_json(silent=True)
    link = parse_channel_link(data.get("url") if isinstance(data, dict) else None)
    if link is None:
        abort(400, BAD_LINK)
    if video_mode(g.user) != "on":
        abort(503, CANNOT_ADD)
    user_id, key = g.user.id, current_app.config["YOUTUBE_API_KEY"]
    kind, value = link
    scan.check_ai_limits(user_id, CHANNEL_ADD_KINDS, CHANNEL_ADD_DAILY_LIMIT, "채널 추가는", burst=CHANNEL_ADD_BURST_LIMIT)
    channel = find_channel(value) if kind == "id" else None
    info = None
    if channel is None and not units_left(UNITS_PER_ADD):
        abort(503, CANNOT_ADD)
    db.session.add(AiCall(user_id=user_id, kind="channel_add", model=None, created_at=scan.utcnow()))
    db.session.commit()
    if channel is None:
        scan.check_ai_limits(user_id, scan.FETCH_KINDS, FETCH_DAILY_LIMIT, "링크 가져오기는", burst=FETCH_BURST_LIMIT)
        db.session.add(AiCall(user_id=user_id, kind="link_fetch", model=None, created_at=scan.utcnow()))
        db.session.commit()
        lookup = {"id": "channel_id", "handle": "handle", "username": "username"}[kind]
        try:
            info = outbound.channel_info(key, **{lookup: value})
        except outbound.FetchError as e:
            current_app.logger.warning("channel lookup failed: %s", e)
            abort(502, "채널 정보를 가져오지 못했어요. 잠시 후 다시 시도해주세요.")
        if info is None:
            abort(404, "채널을 찾을 수 없어요.")
        if find_channel(info["channel_id"]) is None:
            fields = {k: info[k] for k in ("channel_id", "title", "thumbnail_url", "uploads_playlist_id", "video_count")}
            db.session.add(YoutubeChannel(**fields))
            try:
                db.session.commit()
            except IntegrityError:  # 다른 사용자가 같은 채널을 방금 추가했다 → 그 행을 쓴다
                db.session.rollback()
        channel = find_channel(info["channel_id"])
        # ponytail: 개수 한도에 걸리면 이 채널 행은 아무도 안 쓰는 채로 남는다(새로 받지 않으니 비용 없음).

    channel_pk = channel.id
    lock_user_channels(user_id)
    channel = db.session.get(YoutubeChannel, channel_pk)
    row = UserChannel.query.filter_by(user_id=user_id, channel_id=channel_pk).first()
    if row is not None and not row.hidden:
        abort(400, "이미 추가한 채널이에요.")
    if channel.is_default:
        if row is None:
            abort(400, "기본 채널에 이미 있어요.")
        db.session.delete(row)  # 숨겨 둔 기본 채널을 다시 보이게
        db.session.commit()
        return jsonify(channel_json(channel))
    if UserChannel.query.filter_by(user_id=user_id, hidden=False).count() >= MINE_LIMIT:
        abort(400, "채널은 30개까지 추가할 수 있어요.")
    if row is None:
        db.session.add(UserChannel(user_id=user_id, channel_id=channel_pk))
    else:
        row.hidden = False  # 기본 채널에서 빠진 채널을 숨겨 뒀던 행
    commit_or_duplicate("이미 추가한 채널이에요.")
    if db.session.get(YoutubeChannel, channel_pk).fetched_at is None:
        claim_and_refresh(user_id, key, channel_pk, info)
    return jsonify(channel_json(db.session.get(YoutubeChannel, channel_pk), mine=True)), 201


@bp.patch("/channels/<int:channel_pk>")
@login_required
def hide_channel(channel_pk):
    """기본 채널 숨기기(hidden=true 행 만들기)·다시 보이기(행 지우기)."""
    data = request.get_json(silent=True)
    hidden = data.get("hidden") if isinstance(data, dict) else None
    if not isinstance(hidden, bool):
        abort(400, "잘못된 요청이에요.")
    if video_mode(g.user) != "on":
        abort(503, CANNOT_CHANGE)
    channel = db.session.get(YoutubeChannel, channel_pk) if channel_pk <= MAX_INT else None
    row = UserChannel.query.filter_by(user_id=g.user.id, channel_id=channel_pk).first() if channel else None
    if channel is None or not channel.is_default or (row is not None and not row.hidden):
        abort(404, "찾을 수 없어요.")
    if hidden and row is None:
        db.session.add(UserChannel(user_id=g.user.id, channel_id=channel.id, hidden=True))
    elif not hidden and row is not None:
        db.session.delete(row)
    try:
        db.session.commit()
    except IntegrityError:  # 두 번 눌러 이미 숨겨졌다
        db.session.rollback()
    return jsonify(channel_json(db.session.get(YoutubeChannel, channel_pk), hidden=hidden))


@bp.delete("/channels/<int:channel_pk>")
@login_required
def delete_channel(channel_pk):
    """내가 추가한 채널 빼기. 채널·영상 행은 다른 사용자가 쓸 수 있어 남긴다.
    ponytail: 아무도 안 쓰는 채널 행 정리는 30일 영상 삭제로 충분, 쌓이면 CLI를 추가한다."""
    if video_mode(g.user) != "on":
        abort(503, CANNOT_CHANGE)
    row = UserChannel.query.filter_by(user_id=g.user.id, channel_id=channel_pk, hidden=False).first() if channel_pk <= MAX_INT else None
    if row is None:
        abort(404, "찾을 수 없어요.")
    db.session.delete(row)
    db.session.commit()
    return "", 204


@bp.cli.command("seed-default-channels")
def seed_default_channels():
    """app/data/default_channels.json([{"channel_id": "UC…", "name": "메모용 이름"}])대로 기본 채널을 켜고, 목록에서 빠진 채널은 끈다.
    YOUTUBE_API_KEY가 있으면 6시간 안에 받지 않은 채널만 새로 받는다(채널당 3 units). 목록은 사용자가 채널을 확정하기 전까지 비어 있다."""
    try:
        entries = json.loads(DEFAULT_CHANNELS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise click.ClickException(f"default_channels.json을 읽지 못했어요({type(e).__name__}).") from None
    valid = isinstance(entries, list) and all(
        isinstance(e, dict) and isinstance(e.get("channel_id"), str) and outbound.CHANNEL_ID.fullmatch(e["channel_id"]) for e in entries
    )
    if not valid:
        raise click.ClickException('default_channels.json은 [{"channel_id": "UC…", "name": "메모용 이름"}] 모양이어야 해요.')
    names = {e["channel_id"]: e.get("name") if isinstance(e.get("name"), str) else "" for e in entries}
    ids = list(names)
    YoutubeChannel.query.filter(YoutubeChannel.is_default.is_(True), YoutubeChannel.channel_id.not_in(ids)).update(
        {"is_default": False}, synchronize_session=False
    )
    existing = {c.channel_id: c for c in YoutubeChannel.query.filter(YoutubeChannel.channel_id.in_(ids))}
    for channel_id in ids:
        channel = existing.get(channel_id) or YoutubeChannel(channel_id=channel_id, title=names[channel_id].strip()[:100])
        channel.is_default = True
        db.session.add(channel)
    db.session.commit()
    key = current_app.config["YOUTUBE_API_KEY"]
    if key:
        stale = db.session.query(YoutubeChannel.id).filter(YoutubeChannel.channel_id.in_(ids), is_stale(utcnow())).order_by(YoutubeChannel.id)
        for (pk,) in stale.all():
            refresh_channel(db.session.get(YoutubeChannel, pk), key)
    click.echo(f"기본 채널 {len(ids)}개를 맞췄어요.")
