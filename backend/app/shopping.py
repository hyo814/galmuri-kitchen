import math
import re
import uuid
import zlib
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import text as sql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload
from werkzeug.exceptions import BadRequest

from . import storage
from .auth import get_owned_or_404, login_required
from .household import is_household
from .ingredients import check_ingredient_cap, seoul_today
from .ingredients import parse_fields as ingredient_fields
from .locations import choose_location, owned_location, user_locations
from .matching import match_prepared, normalize, prepare
from .models import Ingredient, ShoppingItem, ShoppingNote, ShoppingNotePhoto, db, utcnow
from .scan import sniff_image_type
from .validation import commit_or_duplicate, iso_date, iso_datetime, text

# 장보기 목록(스펙 16·19·28절). 오프라인 기기가 다시 보내도 괜찮게: 추가는 client_id로 한 번만, 체크는 마지막 변경 우선.
bp = Blueprint("shopping", __name__, url_prefix="/api/shopping")

MAX_SHOPPING_ITEMS = 300  # 사용자당, 산 것(stocked_at 있음) 제외
MAX_STOCKED_ITEMS = 300  # 산 것은 따로 사용자당 300개, 재고에 넣기·산 것으로 옮기기에서 넘으면 오래된 것부터 지운다
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
MAX_NOTES = 20  # 사용자당
MAX_PHOTOS = 10  # 메모당(시안 `사진 2 / 10`)
MAX_PHOTO_BYTES = 3 * 1024 * 1024  # 한 장. 화면은 긴 변 1568px로 줄여 올린다(19절)
MAX_USER_PHOTO_BYTES = 200 * 1024 * 1024  # 사용자당 메모 사진 합계
MAX_BODY = 2000
MAX_PLACE = 30
NOTE_CONFLICT = "다른 기기에서 먼저 고친 메모가 있어요."

LIST_CHANGED = "목록이 방금 바뀌었어요. 다시 불러와주세요."
EDIT_KEYS = ("name", "quantity", "unit", "planned_on", "location_id", "household")
STOCK_KEYS = ("name", "quantity", "unit", "location_id")
NO_LOCATIONS = "보관 위치를 먼저 만들어주세요."  # 시안 StockIn에 유통기한·가격 칸이 없어 받지 않는다
CHECK_KEYS = ("done", "changed_at")
_CLIENT_ID = re.compile(r"[A-Za-z0-9-]{1,36}")


def _utc(value):
    """SQLite는 tz 없이 돌려주므로 UTC로 본다."""
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value):
    return iso_datetime(value) if value else None


def _client_id(value):
    if value is not None and not (isinstance(value, str) and _CLIENT_ID.fullmatch(value)):
        abort(400, BAD_REQUEST)
    return value


def photo_json(photo):
    return {"id": photo.id, "client_id": photo.client_id, "url": f"/api/photos/{photo.photo_key}"}


def note_json(note):
    return {
        "id": note.id,
        "client_id": note.client_id,
        "place": note.place,
        "body": note.body,
        "updated_at": iso_datetime(note.updated_at),
        "photos": [photo_json(p) for p in note.photos],
    }


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
        "household": item.household,
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


def _ids_or_400(values, max_len):
    """1~max_len개의 DB int 범위 id 목록."""
    if not isinstance(values, list) or not 1 <= len(values) <= max_len:
        abort(400, BAD_REQUEST)
    if not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 2**31 - 1 for v in values):
        abort(400, BAD_REQUEST)
    return values


def _trim_stocked(user_id):
    """산 것은 사용자당 MAX_STOCKED_ITEMS개까지. 넘으면 오래된 것(stocked_at·id 오름차순)부터 지운다."""
    rows = (
        db.session.query(ShoppingItem.id)
        .filter(ShoppingItem.user_id == user_id, ShoppingItem.stocked_at.is_not(None))
        .order_by(ShoppingItem.stocked_at.desc(), ShoppingItem.id.desc())
        .offset(MAX_STOCKED_ITEMS)
    )
    old = [item_id for (item_id,) in rows.all()]
    if old:
        ShoppingItem.query.filter(ShoppingItem.id.in_(old)).delete(synchronize_session=False)


def parse_fields(data, creating, locations=None):
    """추가·일괄 담기·고치기 공통 칸. 고치기(creating=False)는 보낸 칸만 바꾸고, planned_on·location_id는 null로 비운다.
    household(생활용품)는 참/거짓, 추가할 때 안 보내면 이름으로 짐작한다(고치기는 보낸 때만 바꾼다)."""
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
    if "household" in data:
        if not isinstance(data["household"], bool):
            abort(400, BAD_REQUEST)
        fields["household"] = data["household"]
    elif creating:
        fields["household"] = is_household(fields["name"])
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
    _lock_user_items(g.user.id)  # 재고에 넣기·산 것으로 옮기기와 같은 잠금 순서(사용자 잠금 → 행)
    # ponytail: 7일 지난 산 것은 이 요청 때 지운다(크론 없음). 오래 안 열면 그만큼 남아 있지만 보이지 않는다.
    ShoppingItem.query.filter(ShoppingItem.user_id == g.user.id, ShoppingItem.stocked_at < cutoff).delete(synchronize_session=False)
    db.session.commit()
    rows = ShoppingItem.query.options(joinedload(ShoppingItem.location)).filter_by(user_id=g.user.id)
    items = rows.filter(ShoppingItem.stocked_at.is_(None)).order_by(ShoppingItem.created_at, ShoppingItem.id).all()
    stocked = rows.filter(ShoppingItem.stocked_at.is_not(None)).order_by(ShoppingItem.stocked_at.desc(), ShoppingItem.id.desc()).all()
    notes = (
        ShoppingNote.query.options(selectinload(ShoppingNote.photos))
        .filter_by(user_id=g.user.id)
        .order_by(ShoppingNote.updated_at.desc(), ShoppingNote.id.desc())
        .all()
    )
    res = jsonify(
        items=[item_json(i) for i in items],
        stocked=[item_json(i) for i in stocked],
        notes=[note_json(n) for n in notes],
        today=seoul_today().isoformat(),
    )
    res.headers["Cache-Control"] = "no-store"
    return res


@bp.post("/items")
@login_required
def create_item():
    data = _json_object()
    client_id = _client_id(data.get("client_id"))
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


def _note_fields(data):
    """메모 칸(place·body). body는 자동 저장 중인 글이라 앞뒤 공백을 그대로 둔다(빈 문자열 허용)."""
    place, body = data.get("place"), data.get("body")
    if not isinstance(body, str) or not (place is None or isinstance(place, str)):
        abort(400, BAD_REQUEST)
    if "\x00" in body or (place and "\x00" in place):  # PostgreSQL이 받지 않아 500이 되고 기기가 계속 다시 보낸다
        abort(400, BAD_REQUEST)
    if len(body) > MAX_BODY:
        abort(400, f"메모는 {MAX_BODY}자까지 쓸 수 있어요.")
    place = place.strip() if place else None
    if place and len(place) > MAX_PLACE:
        abort(400, f"장소는 {MAX_PLACE}자까지 입력해주세요.")
    return {"place": place or None, "body": body}


def _owned_note(note_id, lock=False):
    note = db.session.get(ShoppingNote, note_id, with_for_update=lock) if note_id <= 2**31 - 1 else None
    if note is None or note.user_id != g.user.id:
        abort(404, "찾을 수 없어요.")
    return note


@bp.post("/notes")
@login_required
def create_note():
    """{place?, body, client_id?, edited_at?}. edited_at은 오프라인에서 만든 시각 — 그 뒤에 고친 PUT이 409가 나지 않게."""
    data = _json_object()
    client_id = _client_id(data.get("client_id"))
    fields = _note_fields(data)
    edited_at = _changed_at(data["edited_at"]) if "edited_at" in data else utcnow()
    _lock_user_items(g.user.id)
    if client_id is not None:
        existing = ShoppingNote.query.filter_by(user_id=g.user.id, client_id=client_id).first()
        if existing is not None:
            return jsonify(note_json(existing))
    if ShoppingNote.query.filter_by(user_id=g.user.id).count() >= MAX_NOTES:
        abort(400, f"메모는 {MAX_NOTES}개까지 둘 수 있어요.")
    note = ShoppingNote(user_id=g.user.id, client_id=client_id, updated_at=edited_at, **fields)
    db.session.add(note)
    commit_or_duplicate(BAD_REQUEST)
    return jsonify(note_json(note)), 201


@bp.put("/notes/<int:note_id>")
@login_required
def update_note(note_id):
    """{place, body, edited_at}. 서버 메모가 더 늦게 저장됐으면 409와 서버 메모(기기가 자기 글을 따로 보관한다)."""
    data = _json_object()
    fields = _note_fields(data)
    edited_at = _changed_at(data.get("edited_at"))
    note = _owned_note(note_id, lock=True)
    # ponytail: 기기 시계 비교 — 체크(done_changed_at)와 같은 한계. 시계가 크게 틀린 기기는 순서가 틀릴 수 있다.
    if _utc(note.updated_at) > edited_at:
        return jsonify(error=NOTE_CONFLICT, note=note_json(note)), 409
    note.place, note.body, note.updated_at = fields["place"], fields["body"], edited_at
    db.session.commit()
    return jsonify(note_json(note))


@bp.delete("/notes/<int:note_id>")
@login_required
def delete_note(note_id):
    _lock_user_items(g.user.id)  # 사진 올리기와 한 줄로: 사진 목록을 읽은 뒤 들어온 사진 파일이 주인 없이 남지 않게
    note = _owned_note(note_id)
    keys = [p.photo_key for p in note.photos]
    db.session.delete(note)
    db.session.commit()
    storage.delete(keys)  # 커밋 뒤에 — 커밋이 실패하면 파일은 남아 있어야 한다
    return "", 204


@bp.post("/notes/<int:note_id>/photos")
@login_required
def upload_photo(note_id):
    if storage.mode() != "local":
        abort(503, "사진을 지금은 올릴 수 없어요.")
    note = _owned_note(note_id)
    image = request.files.get("image")  # 10MB 초과는 여기서 413
    client_id = _client_id(request.form.get("client_id"))
    data = image.read() if image is not None else b""
    if not data:
        abort(400, "사진을 올려주세요.")
    if len(data) > MAX_PHOTO_BYTES:
        abort(413, "사진이 너무 커요.")
    media_type = sniff_image_type(data)  # 선언된 Content-Type이 아니라 파일 서명을 믿는다
    if media_type is None:
        abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
    _lock_user_items(g.user.id)
    if client_id is not None:
        existing = ShoppingNotePhoto.query.filter_by(note_id=note.id, client_id=client_id).first()
        if existing is not None:  # 오프라인에서 다시 보낸 사진
            return jsonify(photo_json(existing))
    if ShoppingNotePhoto.query.filter_by(note_id=note.id).count() >= MAX_PHOTOS:
        abort(400, f"사진은 메모 하나에 {MAX_PHOTOS}장까지 넣을 수 있어요.")
    used = (
        db.session.query(db.func.coalesce(db.func.sum(ShoppingNotePhoto.size), 0))
        .join(ShoppingNote)
        .filter(ShoppingNote.user_id == g.user.id)
        .scalar()
    )
    if used + len(data) > MAX_USER_PHOTO_BYTES:
        abort(400, "사진 저장 공간이 가득 찼어요. 오래된 메모 사진을 지워주세요.")
    # ponytail: 서버는 EXIF(촬영 위치 등)를 지우지 않고 받은 바이트 그대로 둔다. 화면(Task 10)이 캔버스로 다시 인코딩해 올리므로
    # 메타데이터가 빠진다. 다른 경로로 올린 원본이 문제되면 서버에서 Pillow로 다시 저장하는 것을 더한다.
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[media_type]
    key = f"shopping/{g.user.id}/{uuid.uuid4().hex}.{ext}"
    storage.put(key, data, media_type)
    photo = ShoppingNotePhoto(note_id=note.id, client_id=client_id, photo_key=key, size=len(data))
    db.session.add(photo)
    try:
        db.session.commit()
    except Exception as e:  # 행이 없으면 방금 올린 파일도 남기지 않는다
        db.session.rollback()
        storage.delete([key])
        if isinstance(e, IntegrityError):  # 그사이 메모가 지워졌거나 같은 client_id가 동시에 왔다
            abort(400, BAD_REQUEST)
        raise
    return jsonify(photo_json(photo)), 201


@bp.delete("/notes/<int:note_id>/photos/<int:photo_id>")
@login_required
def delete_photo(note_id, photo_id):
    note = _owned_note(note_id)
    photo = db.session.get(ShoppingNotePhoto, photo_id) if photo_id <= 2**31 - 1 else None
    if photo is None or photo.note_id != note.id:
        abort(404, "찾을 수 없어요.")
    key = photo.photo_key
    db.session.delete(photo)
    db.session.commit()
    storage.delete([key])
    return "", 204


@bp.get("/stock-draft")
@login_required
def stock_draft():
    """재고에 넣기 화면 초안: 체크했고 아직 안 넣은 항목(목록 순서)과 위치 프리필(스펙 23절 D3).
    위치 이유 item(항목에 정한 위치) → same_name(이름이 같은 가장 최근 재료의 위치) → default(첫 냉장 위치)
    → none(보관 위치가 하나도 없음, location_id null — 화면이 고르게 한다)."""
    items = (
        ShoppingItem.query.filter(ShoppingItem.user_id == g.user.id, ShoppingItem.done_at.is_not(None), ShoppingItem.stocked_at.is_(None))
        .order_by(ShoppingItem.created_at, ShoppingItem.id)
        .all()
    )
    latest = {}
    if any(item.location_id is None for item in items):
        # ponytail: 내 재료(최대 2000개) 이름을 모두 읽어 비교한다. 느려지면 이름으로 좁혀 조회한다.
        rows = (
            db.session.query(Ingredient.name, Ingredient.location_id)
            .filter(Ingredient.user_id == g.user.id)
            .order_by(Ingredient.created_at, Ingredient.id)
        )
        latest = {normalize(name): location_id for name, location_id in rows.all()}  # 뒤(최근)가 앞을 덮는다
    locations = user_locations(g.user.id)
    fallback = choose_location(locations, None).id if locations else None
    result = []
    for item in items:
        if item.location_id is not None:
            location_id, reason = item.location_id, "item"
        elif (location_id := latest.get(normalize(item.name))) is not None:
            reason = "same_name"
        else:
            location_id, reason = fallback, "default" if fallback is not None else "none"
        result.append(
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "household": item.household,
                "location_id": location_id,
                "location_reason": reason,
            }
        )
    res = jsonify(purchased_on=seoul_today().isoformat(), items=result)
    res.headers["Cache-Control"] = "no-store"
    return res


@bp.post("/items/stock")
@login_required
def stock_items():
    """체크한 항목을 재고로 옮긴다. 재료 생성과 stocked_at 기록은 한 트랜잭션이고, 하나라도 틀리면 아무것도 하지 않는다.
    `{id, skip: true}` 줄은 재료를 만들지 않고 산 것으로만 옮긴다(생활용품 등)."""
    data = _json_object()
    rows = data.get("items")
    # 체크한 항목은 목록 상한(300개)까지 있을 수 있어 한 번에 모두 받는다(재료 2000개 상한은 그대로).
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SHOPPING_ITEMS:
        abort(400, f"재료를 1~{MAX_SHOPPING_ITEMS}개 보내주세요.")
    if not all(isinstance(row, dict) and isinstance(row.get("skip", False), bool) for row in rows):
        abort(400, BAD_REQUEST)
    ids = _ids_or_400([row.get("id") for row in rows], MAX_SHOPPING_ITEMS)
    if len(set(ids)) != len(ids):
        abort(400, BAD_REQUEST)
    purchased_on = iso_date(data.get("purchased_on"))
    if purchased_on is None:
        abort(400, "날짜 형식이 올바르지 않아요.")
    if purchased_on > seoul_today():
        abort(400, "산 날은 오늘보다 뒤일 수 없어요.")

    # 사용자 잠금 → 행 잠금(id 순, PostgreSQL FOR UPDATE) 순서로, 같은 항목을 동시에 두 번 보내도 재고에 한 번만 들어간다.
    _lock_user_items(g.user.id)
    items = (
        ShoppingItem.query.filter(ShoppingItem.id.in_(ids), ShoppingItem.user_id == g.user.id)
        .order_by(ShoppingItem.id)
        .with_for_update()
        .all()
    )
    if len(items) == len(ids) and all(item.stocked_at is not None for item in items):
        return jsonify(created=0)  # 이미 넣은 요청을 다시 보냄(응답을 못 받은 기기) — 두 번 넣지 않는다
    if len(items) != len(ids) or any(item.done_at is None or item.stocked_at is not None for item in items):
        abort(400, LIST_CHANGED)

    locations = user_locations(g.user.id)
    if not locations and not all(row.get("skip") for row in rows):
        abort(400, NO_LOCATIONS)
    parsed, errors = [], []
    for index, row in enumerate(rows):
        if row.get("skip"):
            continue
        body = {key: row[key] for key in STOCK_KEYS if key in row}
        try:
            parsed.append(ingredient_fields({**body, "purchased_on": purchased_on.isoformat()}, creating=True, locations=locations))
        except BadRequest as e:
            errors.append({"index": index, "error": e.description})
    if errors:
        first = errors[0]
        return jsonify(error=f"{first['index'] + 1}번째 재료: {first['error']}", errors=errors), 400
    check_ingredient_cap(g.user.id, len(parsed))

    now = utcnow()
    db.session.add_all([Ingredient(user_id=g.user.id, **fields) for fields in parsed])
    for item in items:
        item.stocked_at = now
    try:
        db.session.flush()
    except IntegrityError:  # 불러온 뒤 지워진 보관 위치
        db.session.rollback()
        abort(400, LOCATION_CHANGED)
    _trim_stocked(g.user.id)
    commit_or_duplicate(LOCATION_CHANGED)
    return jsonify(created=len(parsed)), 201


@bp.post("/items/match")
@login_required
def match_items():
    """영수증·주문 스캔으로 재고에 넣은 이름과 맞는 목록 항목(산 것 제외) — `장보기에서 빼기` 제안용(스펙 16절)."""
    names = _json_object().get("names")
    if not isinstance(names, list) or not 1 <= len(names) <= BULK_MAX or not all(isinstance(n, str) and len(n) <= 50 for n in names):
        abort(400, BAD_REQUEST)
    keys = [prepare(name) for name in names]
    listed = (
        ShoppingItem.query.filter(ShoppingItem.user_id == g.user.id, ShoppingItem.stocked_at.is_(None))
        .order_by(ShoppingItem.created_at, ShoppingItem.id)
        .all()
    )
    matched = [item for item in listed if any(match_prepared(prepare(item.name), key) for key in keys)]
    return jsonify(items=[{"id": item.id, "name": item.name} for item in matched])


@bp.post("/items/mark-stocked")
@login_required
def mark_stocked():
    """스캔으로 이미 재고에 넣은 항목을 산 것으로 옮긴다(재료는 만들지 않음). 내 목록에 없는 id는 조용히 넘긴다."""
    ids = _ids_or_400(_json_object().get("ids"), MAX_SHOPPING_ITEMS)
    _lock_user_items(g.user.id)
    ShoppingItem.query.filter(
        ShoppingItem.id.in_(ids), ShoppingItem.user_id == g.user.id, ShoppingItem.stocked_at.is_(None)
    ).update({"stocked_at": utcnow()}, synchronize_session=False)
    _trim_stocked(g.user.id)
    db.session.commit()
    return "", 204
