"""요리 채널 영상(스펙 17절). 고른 채널(기본 채널 + 내 채널)의 최근 영상을 서버에 캐시해 최신순으로 보여준다.

유튜브 Data API 사용량(units): 채널 새로 받기 = channels.list + playlistItems.list + videos.list = 3.
검색은 캐시된 제목에서만 한다(search.list 100 units는 쓰지 않는다). 외부 요청은 outbound.py에서만 한다.
"""

import base64
import json
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from . import outbound, scan
from .auth import login_required
from .models import AiCall, UserChannel, YoutubeChannel, YoutubeVideo, db, utcnow
from .recipe_ai import FETCH_BURST_LIMIT, FETCH_DAILY_LIMIT
from .recipes import _decode_cursor
from .validation import commit_or_duplicate, iso_datetime

bp = Blueprint("videos", __name__, url_prefix="/api", cli_group=None)  # 명령은 `flask seed-default-channels`

DEFAULT_CHANNELS_FILE = Path(__file__).parent / "data" / "default_channels.json"
PAGE_SIZE = 30
MAX_QUERY = 50
MINE_LIMIT = 30
STALE_AFTER = timedelta(hours=6)
KEEP_FOR = timedelta(days=30)  # 유튜브 약관: 받은 정보를 30일 넘게 두지 않는다
REFRESH_PER_REQUEST = 3
MAX_INT = 2**31 - 1
CHANNEL_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
HANDLE = re.compile(r"@[\w.-]{3,30}")  # 한글 핸들도 있다
USERNAME = re.compile(r"[A-Za-z0-9._-]{1,50}")
OFF = "영상을 지금은 볼 수 없어요."
CANNOT_ADD = "지금은 채널을 추가할 수 없어요."
CANNOT_CHANGE = "지금은 채널을 바꿀 수 없어요."

# 키 없는 개발 모드용 예시(시안 Videos·VideoPlay·Channels). 썸네일 없음, DB·네트워크 없음.
SAMPLE_CHANNELS = [
    {"id": 1, "title": "집밥 연구소", "thumbnail_url": None, "video_count": 248, "is_default": False, "hidden": False},
    {"id": 2, "title": "자취요리 한 끼", "thumbnail_url": None, "video_count": 97, "is_default": False, "hidden": False},
    {"id": 3, "title": "오늘의 반찬", "thumbnail_url": None, "video_count": None, "is_default": True, "hidden": False},
    {"id": 4, "title": "한식 기본기", "thumbnail_url": None, "video_count": None, "is_default": True, "hidden": False},
    {"id": 5, "title": "간단 도시락", "thumbnail_url": None, "video_count": None, "is_default": True, "hidden": True},
]
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


def video_mode():
    """on: 키 있음 / sample: 키 없음 + 개발 모드(예시 목록) / off: 키 없음 + 운영(영상 칸 숨김)"""
    if current_app.config["YOUTUBE_API_KEY"]:
        return "on"
    return "sample" if current_app.config["DEV_MODE"] else "off"


def parse_channel_link(value):
    """("id", UC…) | ("handle", "@이름") | ("username", 이름) | None. 사용자가 준 주소는 요청하지 않는다.
    /c/이름은 공식 조회 방법이 없어 같은 이름의 핸들로 찾아본다(예전 맞춤 주소는 대부분 핸들과 같다)."""
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
    if first == "c" and HANDLE.fullmatch(f"@{second}"):
        return ("handle", f"@{second}")
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


def refresh_channel(channel, key, info=None):
    """채널 정보·최근 영상 30개·길이/설명을 새로 받아 영상을 통째로 바꾼다(3 units, info를 주면 2).
    채널·재생목록이 없어졌으면(삭제·비공개) 영상을 지운다. 성공·실패 모두 fetched_at을 지금으로.
    외부 요청을 기다리는 동안 트랜잭션을 열어 두지 않는다."""
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
    else:
        channel.title = info["title"] or channel.title
        channel.thumbnail_url, channel.video_count = info["thumbnail_url"], info["video_count"]
        channel.uploads_playlist_id = info["uploads_playlist_id"]
        existing = {v.video_id: v for v in YoutubeVideo.query.filter_by(channel_id=pk)}
        for item in {v["video_id"]: v for v in videos}.values():
            row = existing.pop(item["video_id"], None) or YoutubeVideo(video_id=item["video_id"], channel_id=pk)
            extra = details.get(item["video_id"], {})
            row.title, row.thumbnail_url, row.published_at = item["title"], item["thumbnail_url"], item["published_at"]
            row.duration_seconds, row.description, row.fetched_at = extra.get("duration_seconds"), extra.get("description"), now
            db.session.add(row)
        for row in existing.values():
            db.session.delete(row)
    try:
        db.session.commit()
    except IntegrityError:  # 같은 영상을 다른 요청이 먼저 넣었다. 다음 새로 받기에서 맞춘다
        db.session.rollback()


def refresh_stale(user_id, key):
    """30일 넘게 새로 받지 못한 영상을 지우고, 보이는 채널 중 6시간 지난(또는 받은 적 없는) 채널을 오래된 순 3개까지 새로 받는다.
    채널마다 먼저 fetched_at을 조건부로 바꿔 차지해, 동시에 온 요청이 같은 채널을 두 번 받지 않는다.
    ponytail: 요청 중 동기 갱신·요청당 3개 — 채널이 많아져 목록이 늦어지면 Render cron으로 옮긴다. 쿼터: 채널당 하루 최대 12 units.
    ponytail: 30일 넘게 아무도 보지 않은 채널의 이름·썸네일은 남는다(화면에 보일 때 먼저 새로 받는다). 약관 확인에서 문제되면 같이 비운다."""
    now = utcnow()
    YoutubeVideo.query.filter(YoutubeVideo.fetched_at < now - KEEP_FOR).delete()
    stale_before = now - STALE_AFTER
    is_stale = or_(YoutubeChannel.fetched_at.is_(None), YoutubeChannel.fetched_at < stale_before)
    stale = (
        db.session.query(YoutubeChannel.id)
        .filter(visible_filter(user_id), is_stale)
        .order_by(YoutubeChannel.fetched_at.isnot(None), YoutubeChannel.fetched_at, YoutubeChannel.id)
        .limit(REFRESH_PER_REQUEST)
        .all()
    )
    db.session.commit()
    for (pk,) in stale:
        claimed = db.session.execute(update(YoutubeChannel).where(YoutubeChannel.id == pk, is_stale).values(fetched_at=now)).rowcount
        db.session.commit()
        channel = db.session.get(YoutubeChannel, pk) if claimed else None
        if channel is not None:
            refresh_channel(channel, key)


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
    """is_default는 화면 묶음(기본 채널)이다. 내가 추가한 뒤 기본 채널이 된 채널은 `내 채널`에 둔다."""
    return {
        "id": channel.id,
        "title": channel.title,
        "thumbnail_url": channel.thumbnail_url,
        "video_count": channel.video_count,
        "is_default": channel.is_default and not mine,
        "hidden": hidden,
    }


@bp.get("/videos")
@login_required
def list_videos():
    """보이는 채널 영상 published_at·id 내림차순 커서 페이지(스펙 26절). q는 캐시된 제목에서만 찾는다."""
    mode = video_mode()
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
    cursor = _decode_cursor(cursor) if cursor else None

    if mode == "sample":
        items = [
            {k: v[k] for k in LIST_FIELDS}
            for v in sample_videos()
            if (channel is None or v["channel_id"] == channel) and q.lower() in v["title"].lower()
        ]
        return jsonify(items=items, next_cursor=None, sample=True)

    refresh_stale(g.user.id, current_app.config["YOUTUBE_API_KEY"])
    query = db.session.query(YoutubeVideo, YoutubeChannel).join(YoutubeChannel, YoutubeVideo.channel_id == YoutubeChannel.id)
    query = query.filter(visible_filter(g.user.id))
    if channel is not None:
        query = query.filter(YoutubeChannel.id == channel)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(YoutubeVideo.title.ilike(f"%{escaped}%", escape="\\"))
    if cursor:
        published_at, video_pk = cursor
        query = query.filter(
            or_(YoutubeVideo.published_at < published_at, and_(YoutubeVideo.published_at == published_at, YoutubeVideo.id < video_pk))
        )
    rows = query.order_by(YoutubeVideo.published_at.desc(), YoutubeVideo.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    items = [video_json(video, ch) for video, ch in rows[:limit]]
    next_cursor = _encode_cursor(rows[limit - 1][0]) if has_more else None
    return jsonify(items=items, next_cursor=next_cursor, sample=False)


def _encode_cursor(video):
    return base64.urlsafe_b64encode(f"{iso_datetime(video.published_at)}|{video.id}".encode()).decode()


@bp.get("/videos/<int:video_pk>")
@login_required
def get_video(video_pk):
    mode = video_mode()
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
        .filter(YoutubeVideo.id == video_pk, visible_filter(g.user.id))
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
    mode = video_mode()
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


@bp.post("/channels")
@login_required
def add_channel():
    """채널 링크로 내 채널 추가. 처음 보는 채널이면 channels.list로 찾고(외부 요청은 링크 가져오기와 같은 한도로 센다) 바로 영상을 받는다."""
    data = request.get_json(silent=True)
    link = parse_channel_link(data.get("url") if isinstance(data, dict) else None)
    if link is None:
        abort(400, "채널 링크(youtube.com/@이름)를 붙여 넣어주세요.")
    if video_mode() != "on":
        abort(503, CANNOT_ADD)
    user_id, key = g.user.id, current_app.config["YOUTUBE_API_KEY"]
    kind, value = link
    channel = YoutubeChannel.query.filter_by(channel_id=value).first() if kind == "id" else None
    info = None
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
        channel = YoutubeChannel.query.filter_by(channel_id=info["channel_id"]).first()

    row = UserChannel.query.filter_by(user_id=user_id, channel_id=channel.id).first() if channel else None
    if row is not None and not row.hidden:
        abort(400, "이미 추가한 채널이에요.")
    if channel is not None and channel.is_default:
        if row is None:
            abort(400, "기본 채널에 이미 있어요.")
        db.session.delete(row)  # 숨겨 둔 기본 채널을 다시 보이게
        db.session.commit()
        return jsonify(channel_json(channel))
    # ponytail: 개수 확인과 추가 사이에 잠그지 않는다 — 동시에 보내면 31개가 될 수 있다. 문제되면 사용자 잠금을 잡는다.
    if UserChannel.query.filter_by(user_id=user_id, hidden=False).count() >= MINE_LIMIT:
        abort(400, "채널은 30개까지 추가할 수 있어요.")
    new_channel = channel is None
    if new_channel:
        channel = YoutubeChannel(
            channel_id=info["channel_id"],
            title=info["title"],
            thumbnail_url=info["thumbnail_url"],
            uploads_playlist_id=info["uploads_playlist_id"],
            video_count=info["video_count"],
            fetched_at=utcnow(),  # 차지해 두고 아래에서 바로 받는다
        )
        db.session.add(channel)
        try:
            db.session.flush()
        except IntegrityError:  # 같은 채널을 다른 사용자가 방금 추가했다
            db.session.rollback()
            abort(400, "잠시 후 다시 시도해주세요.")
    if row is None:
        db.session.add(UserChannel(user_id=user_id, channel_id=channel.id))
    else:
        row.hidden = False  # 기본 채널에서 빠진 채널을 숨겨 뒀던 행
    commit_or_duplicate("이미 추가한 채널이에요.")
    if new_channel:
        refresh_channel(channel, key, info)
    return jsonify(channel_json(db.session.get(YoutubeChannel, channel.id), mine=True)), 201


@bp.patch("/channels/<int:channel_pk>")
@login_required
def hide_channel(channel_pk):
    """기본 채널 숨기기(hidden=true 행 만들기)·다시 보이기(행 지우기)."""
    data = request.get_json(silent=True)
    hidden = data.get("hidden") if isinstance(data, dict) else None
    if not isinstance(hidden, bool):
        abort(400, "잘못된 요청이에요.")
    if video_mode() != "on":
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
    if video_mode() != "on":
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
    YOUTUBE_API_KEY가 있으면 각 채널을 새로 받는다(채널당 3 units). 목록은 사용자가 채널을 확정하기 전까지 비어 있다."""
    try:
        entries = json.loads(DEFAULT_CHANNELS_FILE.read_text(encoding="utf-8"))
        valid = isinstance(entries, list) and all(
            isinstance(e, dict) and isinstance(e.get("channel_id"), str) and outbound.CHANNEL_ID.fullmatch(e["channel_id"]) for e in entries
        )
    except ValueError:
        valid = False
    if not valid:
        raise click.ClickException('default_channels.json은 [{"channel_id": "UC…", "name": "메모용 이름"}] 모양이어야 해요.')
    names = {e["channel_id"]: e.get("name") if isinstance(e.get("name"), str) else "" for e in entries}
    ids = list(names)
    YoutubeChannel.query.filter(YoutubeChannel.is_default.is_(True), YoutubeChannel.channel_id.not_in(ids)).update(
        {"is_default": False}, synchronize_session=False
    )
    existing = {c.channel_id: c for c in YoutubeChannel.query.filter(YoutubeChannel.channel_id.in_(ids))}
    channels = []
    for channel_id in ids:
        channel = existing.get(channel_id) or YoutubeChannel(channel_id=channel_id, title=names[channel_id].strip()[:100])
        channel.is_default = True
        db.session.add(channel)
        channels.append(channel)
    db.session.commit()
    key = current_app.config["YOUTUBE_API_KEY"]
    if key:
        for channel in channels:
            refresh_channel(channel, key)
    click.echo(f"기본 채널 {len(ids)}개를 맞췄어요.")
