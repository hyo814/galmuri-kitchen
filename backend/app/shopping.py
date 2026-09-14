import math
import re
import zlib
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import text as sql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from werkzeug.exceptions import BadRequest

from .auth import get_owned_or_404, login_required
from .ingredients import seoul_today
from .locations import choose_location, owned_location, user_locations
from .matching import match_prepared, prepare
from .models import ShoppingItem, db, utcnow
from .validation import commit_or_duplicate, iso_date, iso_datetime, text

# 장보기 목록(스펙 16·19·28절). 오프라인 기기가 다시 보내도 괜찮게: 추가는 client_id로 한 번만, 체크는 마지막 변경 우선.
bp = Blueprint("shopping", __name__, url_prefix="/api/shopping")

MAX_SHOPPING_ITEMS = 300  # 사용자당, 산 것(stocked_at 있음) 제외
# ponytail: 산 것은 이 태스크에서 만드는 API가 없어 세지 않는다. Task 2 재고에 넣기에서 넘으면 오래된 산 것부터 지운다.
MAX_STOCKED_ITEMS = 300
BULK_MAX = 50
SOURCES = ("manual", "recipe", "staple", "urgent", "meal_plan", "memo")
STOCKED_KEEP_DAYS = 7
STALE_BEFORE_CREATED = timedelta(days=1)  # 항목을 만들기 하루 전보다 이른 체크 시각은 틀린 기기 시계로 보고 무시한다
FUTURE_SKEW = timedelta(minutes=10)
LOCK_KEY = zlib.crc32(b"shopping_items") & 0x7FFFFFFF
BAD_REQUEST = "잘못된 요청이에요."
QUANTITY_ERROR = "수량은 0보다 커야 해요."
CAP_ERROR = f"장보기 목록은 {MAX_SHOPPING_ITEMS}개까지 담을 수 있어요. 필요 없는 항목을 빼주세요."
LOCATION_CHANGED = "선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요."
EDIT_KEYS = ("name", "quantity", "unit", "planned_on", "location_id")
CHECK_KEYS = ("done", "changed_at")
_CLIENT_ID = re.compile(r"[A-Za-z0-9-]{1,36}")


def _utc(value):
    """SQLite는 tz 없이 돌려주므로 UTC로 본다."""
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value):
    return iso_datetime(value) if value else None


def item_json(item):
    return {
        "id": item.id,
        "client_id": item.client_id,
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "planned_on": item.planned_on.isoformat() if item.planned_on else None,
        "location_id": item.location_id,
        "location_name": item.location.name if item.location_id else None,
        "source": item.source,
        "source_label": item.source_label,
        "done_at": _iso(item.done_at),
        "done_changed_at": _iso(item.done_changed_at),
        "stocked_at": _iso(item.stocked_at),
        "created_at": iso_datetime(item.created_at),
    }


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, BAD_REQUEST)
    return data


def _lock_user_items(user_id):
    """PostgreSQL은 사용자별 트랜잭션 잠금으로 client_id 확인·개수 확인·추가를 한 줄로 세운다(커밋·롤백 때 풀린다)."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(sql("SELECT pg_advisory_xact_lock(:key, :user_id)"), {"key": LOCK_KEY, "user_id": user_id})
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 301개가 되거나 같은 client_id가 400으로 끝날 수 있다.


def _check_cap(user_id, new_count):
    listed = ShoppingItem.query.filter(ShoppingItem.user_id == user_id, ShoppingItem.stocked_at.is_(None)).count()
    if listed + new_count > MAX_SHOPPING_ITEMS:
        abort(400, CAP_ERROR)


def parse_fields(data, creating, locations=None):
    """추가·일괄 담기·고치기 공통 칸. 고치기(creating=False)는 보낸 칸만 바꾸고, planned_on·location_id는 null로 비운다."""
    if not isinstance(data, dict):
        abort(400, BAD_REQUEST)
    fields = {}
    if creating or "name" in data:
        fields["name"] = text(data.get("name"), "이름은", 50)
    if creating or "quantity" in data:
        value = data.get("quantity", 1)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            abort(400, QUANTITY_ERROR)
        try:
            value = float(value)
        except OverflowError:  # 10**400 같은 거대한 정수
            abort(400, QUANTITY_ERROR)
        if not (math.isfinite(value) and value > 0):
            abort(400, QUANTITY_ERROR)
        fields["quantity"] = value
    if creating or "unit" in data:
        raw = data.get("unit")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            fields["unit"] = "개"
        else:
            fields["unit"] = text(raw, "단위는", 10)
    if creating or "planned_on" in data:
        value = data.get("planned_on")
        if value is None:
            fields["planned_on"] = None
        elif (day := iso_date(value)) is None:
            abort(400, "날짜 형식이 올바르지 않아요.")
        else:
            fields["planned_on"] = day
    if creating or "location_id" in data:
        value = data.get("location_id")
        if value is None:
            fields["location_id"] = None
        else:
            location = choose_location(locations, value) if locations is not None else owned_location(value)
            fields["location_id"] = location.id
    return fields


def _source(data):
    source = data.get("source", "manual")
    if source not in SOURCES:
        abort(400, BAD_REQUEST)
    label = data.get("source_label")
    if label is None or (isinstance(label, str) and not label.strip()):
        return source, None
    return source, text(label, "출처 이름은", 60)


def _changed_at(value):
    """시간대가 붙은 ISO 시각을 UTC로. 10분 넘게 미래면 서버 시각으로 자른다."""
    try:
        when = datetime.fromisoformat(value)
        if when.tzinfo is None:
            abort(400, BAD_REQUEST)
        when = when.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        abort(400, BAD_REQUEST)
    now = utcnow()
    # ponytail: 미래로 틀린 기기의 체크는 서버 시각으로 잘려, 그 뒤 몇 분 안에 제대로 된 기기가 한 더 이른 시각의 변경을 이긴다(허용).
    return now if when > now + FUTURE_SKEW else when


@bp.get("")
@login_required
def snapshot():
    """목록·산 것·메모를 한 번에(오프라인 보관용, 페이지 없음 — 스펙 26절 예외)."""
    cutoff = utcnow() - timedelta(days=STOCKED_KEEP_DAYS)
    # ponytail: 7일 지난 산 것은 이 요청 때 지운다(크론 없음). 오래 안 열면 그만큼 남아 있지만 보이지 않는다.
    ShoppingItem.query.filter(ShoppingItem.user_id == g.user.id, ShoppingItem.stocked_at < cutoff).delete(synchronize_session=False)
    db.session.commit()
    rows = ShoppingItem.query.options(joinedload(ShoppingItem.location)).filter_by(user_id=g.user.id)
    items = rows.filter(ShoppingItem.stocked_at.is_(None)).order_by(ShoppingItem.created_at, ShoppingItem.id).all()
    stocked = rows.filter(ShoppingItem.stocked_at.is_not(None)).order_by(ShoppingItem.stocked_at.desc(), ShoppingItem.id.desc()).all()
    res = jsonify(
        items=[item_json(i) for i in items],
        stocked=[item_json(i) for i in stocked],
        notes=[],
        today=seoul_today().isoformat(),
    )
    res.headers["Cache-Control"] = "no-store"
    return res


@bp.post("/items")
@login_required
def create_item():
    data = _json_object()
    client_id = data.get("client_id")
    if client_id is not None and not (isinstance(client_id, str) and _CLIENT_ID.fullmatch(client_id)):
        abort(400, BAD_REQUEST)
    _lock_user_items(g.user.id)
    if client_id is not None:
        existing = ShoppingItem.query.filter_by(user_id=g.user.id, client_id=client_id).first()
        if existing is not None:  # 오프라인에서 다시 보낸 추가
            return jsonify(item_json(existing))
    location_id = data.get("location_id")
    if client_id is not None and location_id is not None:
        # 오프라인에서 담은 뒤 그 위치가 지워졌어도 담은 것은 잃지 않는다(위치만 비운다). 온라인 요청은 400 그대로.
        try:
            owned_location(location_id)
        except BadRequest:
            data = {**data, "location_id": None}
    fields = parse_fields(data, creating=True)
    source, source_label = _source(data)
    _check_cap(g.user.id, 1)
    item = ShoppingItem(user_id=g.user.id, client_id=client_id, source=source, source_label=source_label, **fields)
    db.session.add(item)
    commit_or_duplicate(LOCATION_CHANGED)
    return jsonify(item_json(item)), 201


@bp.post("/items/bulk")
@login_required
def create_items_bulk():
    """레시피 없는 재료·메모 사진 결과를 한 번에 담는다. 목록에 있는 이름·요청 안에서 겹치는 이름은 건너뛰고,
    하나라도 틀리면 아무것도 만들지 않는다."""
    data = _json_object()
    source, source_label = _source(data)
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= BULK_MAX:
        abort(400, f"살 것을 1~{BULK_MAX}개 보내주세요.")
    locations = user_locations(g.user.id)
    rows, errors = [], []
    for index, item in enumerate(items):
        try:
            rows.append(parse_fields(item, creating=True, locations=locations))
        except BadRequest as e:
            errors.append({"index": index, "error": e.description})
    if errors:
        first = errors[0]
        return jsonify(error=f"{first['index'] + 1}번째 재료: {first['error']}", errors=errors), 400

    _lock_user_items(g.user.id)
    listed = db.session.query(ShoppingItem.name).filter(ShoppingItem.user_id == g.user.id, ShoppingItem.stocked_at.is_(None))
    seen = [prepare(name) for (name,) in listed.all()]
    created, skipped = [], []
    for fields in rows:
        key = prepare(fields["name"])
        if any(match_prepared(key, other) for other in seen):
            skipped.append(fields["name"])
            continue
        seen.append(key)
        created.append(ShoppingItem(user_id=g.user.id, source=source, source_label=source_label, **fields))
    _check_cap(g.user.id, len(created))
    db.session.add_all(created)
    try:
        db.session.flush()  # 커밋 전에 응답을 만들어 커밋 후 만료로 인한 N+1 조회를 피한다
    except IntegrityError:  # 불러온 뒤 지워진 보관 위치
        db.session.rollback()
        abort(400, LOCATION_CHANGED)
    result = [item_json(i) for i in created]
    commit_or_duplicate(LOCATION_CHANGED)
    return jsonify(created=result, skipped=skipped), 201


@bp.patch("/items/<int:item_id>")
@login_required
def update_item(item_id):
    """고치기({name, quantity, …}, 도착 순서대로 덮어씀) 또는 체크({done, changed_at}, 마지막 변경 우선). 섞으면 400."""
    data = _json_object()
    checking = any(k in data for k in CHECK_KEYS)
    # 체크는 행을 잠가(PostgreSQL FOR UPDATE, SQLite는 무시) 동시에 온 두 체크가 같은 옛 값을 보고 비교하지 않게 한다.
    item = db.session.get(ShoppingItem, item_id, with_for_update=checking) if item_id <= 2**31 - 1 else None
    if item is None or item.user_id != g.user.id or item.stocked_at is not None:  # 산 것은 고치지 않는다
        abort(404, "찾을 수 없어요.")
    if checking:
        if any(k in data for k in EDIT_KEYS) or not isinstance(data.get("done"), bool):
            abort(400, BAD_REQUEST)
        changed_at = _changed_at(data.get("changed_at"))
        # ponytail: 기기 시계 차이만큼 순서가 틀릴 수 있다(한 사용자·기기 몇 대라 허용). 문제되면 서버 수신 순서로 바꾼다.
        stale = changed_at < _utc(item.created_at) - STALE_BEFORE_CREATED or (
            item.done_changed_at is not None and changed_at < _utc(item.done_changed_at)
        )
        if not stale:  # 같은 시각이면 나중에 도착한 것을 따른다
            item.done_at = changed_at if data["done"] else None
            item.done_changed_at = changed_at
    else:
        for key, value in parse_fields(data, creating=False).items():
            setattr(item, key, value)
    commit_or_duplicate(LOCATION_CHANGED)
    return jsonify(item_json(item))


@bp.delete("/items/<int:item_id>")
@login_required
def delete_item(item_id):
    db.session.delete(get_owned_or_404(ShoppingItem, item_id))
    db.session.commit()
    return "", 204
