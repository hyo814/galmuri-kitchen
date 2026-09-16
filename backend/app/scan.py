import io
import json
import math
import zlib
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import text

from . import ai
from .auth import ai_daily_limit, login_required
from .household import is_household
from .ingredients import SEOUL, seoul_today
from .locations import KINDS
from .matching import normalize
from .models import AiCall, db, utcnow
from .validation import iso_date

bp = Blueprint("scan", __name__, url_prefix="/api/scan", cli_group=None)  # 명령은 `flask make-sample-scans`

UPLOAD_KINDS = ("fridge", "receipt", "order", "memo")
SCAN_KINDS = ("fridge", "receipt", "order", "memo")  # 일일 한도를 함께 세는 kind (memo는 장보기 메모 사진)
RECIPE_KINDS = ("recipe", "link", "recipe_photo", "meal", "eat_out")  # AI 레시피 제안 + 링크·글·사진 가져오기 + AI 식단 초안(스펙 20절) + eat_out: 사 먹으면 얼마 추정(29절 결정 11)
NUTRITION_KINDS = ("nutrition",)  # 영양 채우기 AI 단위 무게·영양 추정(스펙 21절). AI 레시피 한도·체험 전체 AI 예산과 따로, /api/ai-usage에는 안 보인다
MISS_FREE_DAILY = 3  # 헛호출(찾지 못함·오류) 중 사용자마다 하루(서울) 이만큼은 하루 한도·사용량에 세지 않는다(스펙 7절)


def miss_kinds(kinds):
    """kinds의 헛호출 kind(<kind>_miss). 하루 한도·/api/ai-usage에는 안 세고 전체 AI 예산·연속 호출 한도에는 센다."""
    return tuple(f"{kind}_miss" for kind in kinds)


MISS_KINDS = miss_kinds(SCAN_KINDS + RECIPE_KINDS)
AI_KINDS = SCAN_KINDS + RECIPE_KINDS + NUTRITION_KINDS + MISS_KINDS  # Claude를 부르는 kind 전체(로그인 사용자 전체 AI 예산, ai.user_ai_budget_spent)
FETCH_KINDS = ("link_fetch",)  # 링크 가져오기의 외부 요청(AI 호출 아님, 토큰 없음). AI 한도·사용량에는 세지 않는다
MAX_ITEMS = 50
MAX_PHOTOS = 5  # 한 번에 읽는 사진 수(AI 호출은 한 번)
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


def _lock(user_id, kinds):
    """PostgreSQL은 사용자·kind 묶음별 트랜잭션 잠금을 잡아, 동시에 온 요청이 같은 개수를 보고 함께 통과하지 못하게 한다(커밋·롤백 때 풀린다)."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:group_key, :user_id)"),
            {"group_key": zlib.crc32(",".join(kinds).encode()) & 0x7FFFFFFF, "user_id": user_id},
        )
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 한도를 조금 넘을 수 있다. 운영은 PostgreSQL이다.


def check_ai_limits(user_id, kinds, limit, what, burst=None):
    """연속 호출(burst, 없으면 AI_SCAN_BURST_LIMIT, 헛호출 포함)·하루 한도(헛호출 뺌)를 넘거나, Claude를 부르는 kinds인데
    로그인 사용자 전체 AI 예산(ai.user_ai_budget_spent)을 다 쓰면 429.
    what은 문구 주어(예: "사진 인식은"). 체험 계정은 전체 체험 예산(ai.scan_mode)을 따로 본다.
    바로 뒤에 start_ai_call을 불러 같은 트랜잭션에서 기록해야 한다(그 사이에 커밋하지 않는다)."""
    _lock(user_id, kinds)
    if calls_recent(user_id, kinds + miss_kinds(kinds)) >= (burst or current_app.config["AI_SCAN_BURST_LIMIT"]):
        abort(429, "잠시 후 다시 시도해주세요.")
    if calls_today(user_id, kinds) >= limit:
        abort(429, f"오늘 {what} {limit}번까지 쓸 수 있어요. 내일 다시 써주세요.")
    if set(kinds) <= set(AI_KINDS) and g.user.provider != "demo" and ai.user_ai_budget_spent():
        abort(429, "오늘 준비한 AI 사용량이 모두 찼어요. 조금 뒤에 다시 써주세요.")


def start_ai_call(user_id, kind):
    """AI로 보내기 직전에 기록해 센다(찾지 못함·오류로 끝나면 miss_ai_call이 헛호출로 바꾼다).
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


def miss_ai_call(call):
    """쓸 것이 없거나(재료 0개·레시피 없음 등) AiError로 끝난 호출. 이 사용자의 오늘 헛호출이 MISS_FREE_DAILY번보다 적으면
    kind에 _miss를 붙여 하루 한도에서 빼고, 아니면 그대로 센다(헛호출을 되풀이해 비용을 쓰지 못하게). 토큰 기록은 그대로다."""
    _lock(call.user_id, MISS_KINDS)
    if calls_today(call.user_id, MISS_KINDS) < MISS_FREE_DAILY:
        call.kind = miss_kinds([call.kind])[0]
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


def clean_result(kind, raw, today, merge=False):
    """AI(또는 예시) 결과를 화면에 넘기기 전에 정리한다. 모델 출력은 믿지 않는다.
    memo만 줄마다 household(생활용품)를 붙인다 — 참/거짓이 아니면 이름으로 짐작한다.
    merge(사진 여러 장): 이름(normalize)·단위·보관 종류가 같은 줄은 하나로 합친다."""
    raw = raw if isinstance(raw, dict) else {}
    rows = raw.get("items") if isinstance(raw.get("items"), list) else []
    items, seen = [], {}
    for row in rows:
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
        key = (normalize(name), item["unit"], item["location_kind"])
        if merge and key in seen:
            # ponytail: 겹쳐 찍힌 같은 물건이 흔해 수량은 더하지 않고 큰 쪽을 남긴다. 영수증 두 장에 같은 물건을 따로 산 줄이
            # 있으면 적게 잡힌다 — 확인 화면에서 고친다. 잦으면 AI가 사진 번호를 함께 적게 해 다른 사진끼리만 합친다.
            kept = seen[key]
            kept["quantity"] = max(kept["quantity"], item["quantity"])
            if kept["price"] is None:
                kept["price"] = item["price"]
            continue
        if len(items) == MAX_ITEMS:
            continue  # 합칠 줄은 끝까지 본다(모델 출력 길이는 max_tokens로 묶여 있다)
        seen[key] = item
        items.append(item)
    purchased_on = None if kind in ai.NO_PRICE_KINDS else _purchased_on(raw.get("purchased_on"), today)
    return {"items": items, "purchased_on": purchased_on}


@bp.post("")
@login_required
def scan():
    kind = request.args.get("kind")
    if kind not in UPLOAD_KINDS:
        abort(400, "스캔 종류가 올바르지 않아요.")
    files = request.files.getlist("image")  # 10MB 초과(모든 사진 합)는 여기서 413
    if len(files) > MAX_PHOTOS:
        abort(400, f"사진은 {MAX_PHOTOS}장까지 올려주세요.")
    images = []
    for file in files:
        data = file.read()
        if not data:
            abort(400, "사진을 올려주세요.")
        media_type = sniff_image_type(data)  # 선언된 Content-Type이 아니라 파일 시그니처를 믿는다
        if media_type is None:
            abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
        images.append((data, media_type))
    if not images:
        abort(400, "사진을 올려주세요.")

    today = seoul_today()
    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, "사진 인식을 지금은 쓸 수 없어요.")
    if mode == "sample":
        # 체험 계정이 예시 사진을 보냈으면 그 사진을 미리 실제 AI로 읽어 둔 결과를 준다(스펙 31절). 모르는 id는 일반 예시 결과
        stored = ai.sample_scans().get(request.form.get("sample")) if g.user.provider == "demo" else None
        raw = stored if stored and stored["kind"] == kind else ai.sample_result(kind, today)
        return jsonify(**clean_result(kind, raw, today), sample=True)

    check_ai_limits(g.user.id, SCAN_KINDS, ai_daily_limit(g.user, "AI_DAILY_SCAN_LIMIT"), "사진 인식은")
    # 업로드 검증(kind·사진 수·사진 유무·형식)에서 걸린 요청은 세지 않는다. 여러 장이어도 한 번 부르고 한 번 센다.
    call = start_ai_call(g.user.id, kind)
    try:
        raw, usage = ai.extract(kind, images)
    except ai.AiError:
        miss_ai_call(call)
        abort(502, "인식에 실패했어요. 직접 입력해주세요.")
    finish_ai_call(call, usage)
    result = clean_result(kind, raw, today, merge=len(images) > 1)
    if not result["items"]:
        miss_ai_call(call)
    return jsonify(**result, sample=False)


SAMPLE_PHOTO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"
SAMPLE_MAX_SIDE = 1568  # frontend/src/image.ts resizeImage와 같은 긴 변


@bp.cli.command("make-sample-scans")
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("ids", nargs=-1)
def make_sample_scans(folder, ids):
    """FOLDER의 예시 사진(<id>.jpg·.jpeg·.png, id는 ai.SAMPLE_PHOTOS)을 사진 정보(EXIF)를 뺀 긴 변 1568px JPEG로
    frontend/public/samples/<id>.jpg에 쓰고, 실제 AI로 한 번씩 읽어 app/data/sample_scans.json에 합친다(스펙 31절).
    IDS를 주면 그 사진만 다시 만든다. 사진은 올리기 전에 개인 정보(카드 번호·이름·주소·전화번호)를 가려 둔다."""
    try:
        from PIL import Image, ImageOps  # 이 명령에서만 쓴다(운영 서버에는 없음)
    except ImportError:
        raise click.ClickException("Pillow가 필요해요: .venv/bin/pip install Pillow") from None
    if not current_app.config["ANTHROPIC_API_KEY"]:
        raise click.ClickException("ANTHROPIC_API_KEY가 없어요(backend/.env).")
    unknown = [i for i in ids if i not in ai.SAMPLE_PHOTOS]
    if unknown:
        raise click.ClickException(f"모르는 사진 id: {', '.join(unknown)} (쓸 수 있는 id: {', '.join(ai.SAMPLE_PHOTOS)})")
    photos = {}
    for sample_id in ids or ai.SAMPLE_PHOTOS:
        found = [folder / f"{sample_id}{ext}" for ext in (".jpg", ".jpeg", ".png") if (folder / f"{sample_id}{ext}").is_file()]
        if found:
            photos[sample_id] = found[0]
        elif ids:
            raise click.ClickException(f"{folder}에 {sample_id}.jpg(.png)가 없어요.")
    if not photos:
        raise click.ClickException(f"{folder}에 예시 사진이 없어요 ({', '.join(f'{i}.jpg' for i in ai.SAMPLE_PHOTOS)}).")

    stored = ai.sample_scans()
    SAMPLE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    for sample_id, path in photos.items():
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")  # 회전을 반영한 뒤 새로 저장하므로 EXIF는 따라가지 않는다
                image.thumbnail((SAMPLE_MAX_SIDE, SAMPLE_MAX_SIDE))
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=85)
        except OSError as e:  # 사진이 아니거나 깨진 파일(PIL.UnidentifiedImageError도 OSError)
            raise click.ClickException(f"{path.name} 파일을 사진으로 열지 못했어요({e}).") from None
        data = buffer.getvalue()
        kind = ai.SAMPLE_PHOTOS[sample_id]
        try:
            raw, usage = ai.extract(kind, [(data, "image/jpeg")])
        except ai.AiError as e:
            raise click.ClickException(f"{sample_id} 사진을 읽지 못했어요({e}).") from None
        (SAMPLE_PHOTO_DIR / f"{sample_id}.jpg").write_bytes(data)
        stored[sample_id] = {"kind": kind, **clean_result(kind, raw, seoul_today())}
        # 사진마다 바로 저장한다 — 뒤 사진이 실패해도 새 사진 옆에 옛 결과가 남거나 이미 쓴 AI 호출이 버려지지 않게
        ai.SAMPLE_SCANS_FILE.write_text(json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        click.echo(f"{sample_id}: 재료 {len(stored[sample_id]['items'])}개 (토큰 {usage['input_tokens']}+{usage['output_tokens']})")
    click.echo(f"{ai.SAMPLE_SCANS_FILE.name}에 {len(stored)}장을 저장했어요.")
