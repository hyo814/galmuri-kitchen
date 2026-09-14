import math
import zlib
from datetime import datetime, time, timedelta, timezone

from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import text

from . import ai
from .auth import ai_daily_limit, login_required
from .household import is_household
from .ingredients import SEOUL, seoul_today
from .locations import KINDS
from .models import AiCall, db, utcnow
from .validation import iso_date

bp = Blueprint("scan", __name__, url_prefix="/api/scan")

UPLOAD_KINDS = ("fridge", "receipt", "order", "memo")
SCAN_KINDS = ("fridge", "receipt", "order", "memo")  # 일일 한도를 함께 세는 kind (memo는 장보기 메모 사진)
RECIPE_KINDS = ("recipe", "link", "recipe_photo", "meal")  # AI 레시피 제안 + 링크·글·사진 가져오기 + AI 식단 초안(스펙 20절)
FETCH_KINDS = ("link_fetch",)  # 링크 가져오기의 외부 요청(AI 호출 아님, 토큰 없음). AI 한도·사용량에는 세지 않는다
MAX_ITEMS = 50
MAX_QUANTITY = 9999
MAX_PRICE = 10_000_000
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


def calls_today(user_id, kinds, day=None):
    """오늘(서울 날짜, day를 주면 그날) 이 사용자가 kinds로 쓴 AI 호출 횟수. created_at은 UTC로 저장되므로 서울 하루를 UTC 구간으로 바꿔 센다."""
    start = datetime.combine(day or seoul_today(), time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    return AiCall.query.filter(
        AiCall.user_id == user_id,
        AiCall.kind.in_(kinds),
        AiCall.created_at >= start,
        AiCall.created_at < start + timedelta(days=1),
    ).count()


def calls_recent(user_id, kinds):
    """지난 60초 안에 이 사용자가 kinds로 보낸 AI 호출 횟수. 짧은 시간에 몰아 보내는 것(동시 진행 호출 포함)을 막는다."""
    cutoff = utcnow() - timedelta(seconds=BURST_WINDOW_SECONDS)
    return AiCall.query.filter(
        AiCall.user_id == user_id,
        AiCall.kind.in_(kinds),
        AiCall.created_at >= cutoff,
    ).count()


def check_ai_limits(user_id, kinds, limit, what, burst=None):
    """연속 호출(burst, 없으면 AI_SCAN_BURST_LIMIT)·하루 한도를 넘으면 429. what은 문구 주어(예: "사진 인식은").
    바로 뒤에 start_ai_call을 불러 같은 트랜잭션에서 기록해야 한다(그 사이에 커밋하지 않는다).
    PostgreSQL은 사용자·kind 묶음별 트랜잭션 잠금을 잡아, 동시에 온 요청이 같은 개수를 보고 함께 통과하지 못하게 한다(커밋·롤백 때 풀린다)."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:group_key, :user_id)"),
            {"group_key": zlib.crc32(",".join(kinds).encode()) & 0x7FFFFFFF, "user_id": user_id},
        )
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 한도를 조금 넘을 수 있다. 운영은 PostgreSQL이다.
    if calls_recent(user_id, kinds) >= (burst or current_app.config["AI_SCAN_BURST_LIMIT"]):
        abort(429, "잠시 후 다시 시도해주세요.")
    if calls_today(user_id, kinds) >= limit:
        abort(429, f"오늘 {what} {limit}번까지 쓸 수 있어요. 내일 다시 써주세요.")


def start_ai_call(user_id, kind):
    """AI로 보낸 호출은 성공·실패와 관계없이 센다(실패도 비용이 들어 남용을 막기 위해). 호출 직전에 부른다.
    커밋하면 check_ai_limits가 잡은 잠금이 풀린다.
    created_at을 명시적으로 넣는다: 모델 기본값(utcnow) 대신 이 모듈의 utcnow를 써서
    calls_today/calls_recent와 같은 시계를 보게 한다(테스트에서 시계를 고정하기 쉽다)."""
    demo = g.user.provider == "demo"  # 사용자가 지워져도 전체 체험 AI 예산에 세도록 남긴다
    call = AiCall(user_id=user_id, kind=kind, demo=demo, model=current_app.config["CLAUDE_MODEL"], created_at=utcnow())
    db.session.add(call)
    db.session.commit()
    return call


def finish_ai_call(call, usage):
    # ponytail: 응답은 받았지만 AiError가 되는 호출(refusal·max_tokens·스키마 불일치)의 토큰은 버려진다.
    # 그런 호출이 잦아 원가가 어긋나면 AiError에 usage를 실어 기록한다.
    call.model, call.input_tokens, call.output_tokens = usage["model"], usage["input_tokens"], usage["output_tokens"]
    db.session.commit()


def _quantity(value):
    if isinstance(value, bool):
        return 1
    try:
        quantity = float(value)
    except (TypeError, ValueError, OverflowError):  # OverflowError: 10**400 같은 거대한 정수
        return 1
    return min(quantity, MAX_QUANTITY) if math.isfinite(quantity) and quantity > 0 else 1


def _purchased_on(value, today):
    day = iso_date(value)
    return day.isoformat() if day and day <= today else None


def _price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not (0 < value <= MAX_PRICE):
        return None
    return round(value)


def clean_result(kind, raw, today):
    """AI(또는 예시) 결과를 화면에 넘기기 전에 정리한다. 모델 출력은 믿지 않는다.
    memo만 줄마다 household(생활용품)를 붙인다 — 참/거짓이 아니면 이름으로 짐작한다."""
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
        name = name.strip()[:50].strip()
        item = {
            "name": name,
            "quantity": _quantity(row.get("quantity")),
            "unit": unit or "개",
            "location_kind": location_kind if location_kind in KINDS else "fridge",
            "price": None if kind in ai.NO_PRICE_KINDS else _price(row.get("price")),
        }
        if kind == "memo":
            household = row.get("household")
            item["household"] = household if isinstance(household, bool) else is_household(name)
        items.append(item)
    purchased_on = None if kind in ai.NO_PRICE_KINDS else _purchased_on(raw.get("purchased_on"), today)
    return {"items": items, "purchased_on": purchased_on}


@bp.post("")
@login_required
def scan():
    kind = request.args.get("kind")
    if kind not in UPLOAD_KINDS:
        abort(400, "스캔 종류가 올바르지 않아요.")
    image = request.files.get("image")  # 10MB 초과는 여기서 413
    if image is None:
        abort(400, "사진을 올려주세요.")
    data = image.read()
    if not data:
        abort(400, "사진을 올려주세요.")
    media_type = sniff_image_type(data)  # 선언된 Content-Type이 아니라 파일 시그니처를 믿는다
    if media_type is None:
        abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")

    today = seoul_today()
    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, "사진 인식을 지금은 쓸 수 없어요.")
    if mode == "sample":
        return jsonify(**clean_result(kind, ai.sample_result(kind, today), today), sample=True)

    check_ai_limits(g.user.id, SCAN_KINDS, ai_daily_limit(g.user, "AI_DAILY_SCAN_LIMIT"), "사진 인식은")
    # 업로드 검증(kind·사진 유무·형식)에서 걸린 요청은 세지 않는다.
    call = start_ai_call(g.user.id, kind)
    try:
        raw, usage = ai.extract(kind, data, media_type)
    except ai.AiError:
        abort(502, "인식에 실패했어요. 직접 입력해주세요.")
    finish_ai_call(call, usage)
    return jsonify(**clean_result(kind, raw, today), sample=False)
