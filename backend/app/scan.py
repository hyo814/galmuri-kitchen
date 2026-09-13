import math
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, abort, current_app, g, jsonify, request

from . import ai
from .auth import login_required
from .ingredients import SEOUL, seoul_today
from .locations import KINDS
from .models import AiCall, db

bp = Blueprint("scan", __name__, url_prefix="/api/scan")

UPLOAD_KINDS = ("fridge", "receipt", "order")
SCAN_KINDS = ("fridge", "receipt", "order", "memo")  # 일일 한도를 함께 세는 kind (memo는 4단계 장보기 메모 사진)
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
MAX_ITEMS = 50
MAX_QUANTITY = 9999


def scans_today(user_id):
    """오늘(서울 날짜) 이 사용자가 쓴 사진 인식 횟수. created_at은 UTC로 저장되므로 서울 하루를 UTC 구간으로 바꿔 센다."""
    start = datetime.combine(seoul_today(), time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    # ponytail: 세고 나서 호출하므로 동시에 여러 장을 보내면 한도를 조금 넘을 수 있다. 문제되면 사용자 단위 잠금
    return AiCall.query.filter(
        AiCall.user_id == user_id,
        AiCall.kind.in_(SCAN_KINDS),
        AiCall.created_at >= start,
        AiCall.created_at < start + timedelta(days=1),
    ).count()


def _quantity(value):
    if isinstance(value, bool):
        return 1
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return 1
    return min(quantity, MAX_QUANTITY) if math.isfinite(quantity) and quantity > 0 else 1


def _purchased_on(value, today):
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return day.isoformat() if day <= today else None


def clean_result(kind, raw, today):
    """AI(또는 예시) 결과를 화면에 넘기기 전에 정리한다. 모델 출력은 믿지 않는다."""
    raw = raw if isinstance(raw, dict) else {}
    rows = raw.get("items") if isinstance(raw.get("items"), list) else []
    items = []
    for row in rows:
        if len(items) == MAX_ITEMS:
            break
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        unit = row.get("unit").strip()[:10].strip() if isinstance(row.get("unit"), str) else ""
        location_kind = row.get("location_kind")
        items.append(
            {
                "name": name.strip()[:50].strip(),
                "quantity": _quantity(row.get("quantity")),
                "unit": unit or "개",
                "location_kind": location_kind if location_kind in KINDS else "fridge",
            }
        )
    purchased_on = None if kind == "fridge" else _purchased_on(raw.get("purchased_on"), today)
    return {"items": items, "purchased_on": purchased_on}


@bp.post("")
@login_required
def scan():
    kind = request.args.get("kind")
    if kind not in UPLOAD_KINDS:
        abort(400, "스캔 종류가 올바르지 않아요.")
    image = request.files.get("image")  # 10MB 초과는 여기서 413
    if image is None:
        abort(400, "사진을 올려 주세요.")
    if image.mimetype not in IMAGE_TYPES:
        abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
    data = image.read()
    if not data:
        abort(400, "사진을 올려 주세요.")

    today = seoul_today()
    mode = ai.scan_mode()
    if mode == "off":
        abort(503, "사진 인식을 지금은 쓸 수 없어요.")
    if mode == "sample":
        return jsonify(**clean_result(kind, ai.sample_result(kind, today), today), sample=True)

    limit = current_app.config["AI_DAILY_SCAN_LIMIT"]
    if scans_today(g.user.id) >= limit:
        abort(429, f"오늘 사진 인식은 {limit}번까지 쓸 수 있어요. 내일 다시 써 주세요.")
    try:
        raw = ai.extract(kind, data, image.mimetype)
    except ai.AiError:
        abort(502, "인식에 실패했어요. 직접 입력해 주세요.")
    db.session.add(AiCall(user_id=g.user.id, kind=kind))  # 성공한 호출만 한도에 센다 (스펙 7절)
    db.session.commit()
    return jsonify(**clean_result(kind, raw, today), sample=False)
