import math
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, abort, current_app, g, jsonify, request

from . import ai
from .auth import login_required
from .ingredients import SEOUL, seoul_today
from .locations import KINDS
from .models import AiCall, db, utcnow

bp = Blueprint("scan", __name__, url_prefix="/api/scan")

UPLOAD_KINDS = ("fridge", "receipt", "order")
SCAN_KINDS = ("fridge", "receipt", "order", "memo")  # 일일 한도를 함께 세는 kind (memo는 4단계 장보기 메모 사진)
MAX_ITEMS = 50
MAX_QUANTITY = 9999
BURST_WINDOW_SECONDS = 60


def sniff_image_type(data):
    """선언된 Content-Type은 클라이언트가 마음대로 붙일 수 있으므로 믿지 않고, 파일 시그니처(매직 넘버)로 실제 형식을 판별한다."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


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


def scans_recent(user_id):
    """지난 60초 안에 이 사용자가 보낸 사진 인식 횟수. 짧은 시간에 몰아 보내는 것(계정당 동시 진행 스캔 포함)을 막는다."""
    cutoff = utcnow() - timedelta(seconds=BURST_WINDOW_SECONDS)
    return AiCall.query.filter(
        AiCall.user_id == user_id,
        AiCall.kind.in_(SCAN_KINDS),
        AiCall.created_at >= cutoff,
    ).count()


def _quantity(value):
    if isinstance(value, bool):
        return 1
    try:
        quantity = float(value)
    except (TypeError, ValueError, OverflowError):  # OverflowError: 10**400 같은 거대한 정수
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
    data = image.read()
    if not data:
        abort(400, "사진을 올려 주세요.")
    media_type = sniff_image_type(data)  # 선언된 Content-Type이 아니라 파일 시그니처를 믿는다
    if media_type is None:
        abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")

    today = seoul_today()
    mode = ai.scan_mode()
    if mode == "off":
        abort(503, "사진 인식을 지금은 쓸 수 없어요.")
    if mode == "sample":
        return jsonify(**clean_result(kind, ai.sample_result(kind, today), today), sample=True)

    if scans_recent(g.user.id) >= current_app.config["AI_SCAN_BURST_LIMIT"]:
        abort(429, "잠시 후 다시 시도해 주세요.")
    limit = current_app.config["AI_DAILY_SCAN_LIMIT"]
    if scans_today(g.user.id) >= limit:
        abort(429, f"오늘 사진 인식은 {limit}번까지 쓸 수 있어요. 내일 다시 써 주세요.")

    # AI로 보낸 호출은 성공·실패와 관계없이 센다(실패도 비용이 들어 남용을 막기 위해).
    # 업로드 검증(kind·사진 유무·형식)에서 걸린 요청은 세지 않는다.
    # created_at을 명시적으로 넣는다: 모델 기본값(utcnow) 대신 이 모듈의 utcnow를 써서
    # scans_today/scans_recent와 같은 시계를 보게 한다(테스트에서 시계를 고정하기 쉽다).
    db.session.add(AiCall(user_id=g.user.id, kind=kind, created_at=utcnow()))
    db.session.commit()
    try:
        raw = ai.extract(kind, data, media_type)
    except ai.AiError:
        abort(502, "인식에 실패했어요. 직접 입력해 주세요.")
    return jsonify(**clean_result(kind, raw, today), sample=False)
