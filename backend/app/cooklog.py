"""요리 일기(스펙 29절). 요리했어요 초안·저장·되돌리기·목록·상세. 쓴 재료는 저장할 때 스냅숏(결정 1·7·8).
레시피 없이 쓴 일기(manual, 추가 2026-09-16)는 쓴 재료 줄 없이 이름·적은 재료비만 남긴다."""

import json
import logging
import math
import uuid
import zlib
from datetime import datetime, time, timedelta, timezone

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import and_, or_, text as sql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from . import food_logs, meals, photos, storage
from .amounts import SPOON_UNITS, in_unit, parse_amount
from .auth import get_owned_or_404, login_required
from .ingredients import seasoning_names
from .locations import default_location
from .matching import match_prepared, names_match, normalize, prepare
from .models import CookLog, CookLogItem, Ingredient, IngredientRemoval, Recipe, StorageLocation, db, utcnow
from .nutrition import TRACE_WORDS
from .recipe_parse import ingredient_key
from .recipes import ALWAYS_HAVE, inventory_rows
from .validation import decode_cursor, encode_cursor, integer, iso_datetime, memo, text

bp = Blueprint("cooklog", __name__, url_prefix="/api")

log = logging.getLogger(__name__)

LIST_PAGE = 20
MAX_COOK_LOGS = 5000
MAX_USAGES = 50
MAX_MEMO = 500
MAX_WON = 1_000_000  # 사 먹으면 얼마(1인분)·직접 적은 재료비
MAX_AMOUNT = 100_000
UNDO_SECONDS = 120
MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_USER_PHOTO_BYTES = 200 * 1024 * 1024  # 메모·먹은 기록 사진과 따로 센다(결정 19)
MAX_DEMO_PHOTO_BYTES = 20 * 1024 * 1024
LOCK_KEY = zlib.crc32(b"cook_logs") & 0x7FFFFFFF
STOCK_CHANGED = "재고가 방금 바뀌었어요. 다시 불러와주세요."
UNDO_EXPIRED = "되돌릴 수 있는 시간이 지났어요. 재고는 직접 고쳐주세요."
PHOTO_FULL = "사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요."
EAT_OUT_ERROR = "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."
COST_ERROR = "재료비는 0~1,000,000원 사이 숫자로 입력해주세요."
AMOUNT_ERROR = "쓴 양은 0보다 커야 해요."
PATCH_FIELDS = {"cooked_on", "rating", "memo", "eat_out_price"}  # 결정 18: 고치기는 이 칸만 받는다
MANUAL_PATCH_FIELDS = PATCH_FIELDS | {"ingredient_cost"}  # 직접 쓴 일기는 재료비도 고친다
MANUAL_ONLY = {"title", "ingredient_cost"}  # 레시피 일기는 이름을 레시피에서, 재료비를 쓴 재료 줄에서 얻는다
MANUAL_FIELDS = MANUAL_PATCH_FIELDS | MANUAL_ONLY | {"manual", "servings", "food_log", "meal"}  # 레시피·쓴 재료·식단 칸은 받지 않는다

SEASONING_SPOONS = SPOON_UNITS - {"컵"}  # 결정 5: 컵은 밀가루·쌀처럼 많이 쓰는 양이라 양념으로 보지 않는다


def is_seasoning(key, amount, staples):
    """결정 5. key는 ingredient_key(재료 이름), staples는 seasoning_names(user_id)."""
    if any(names_match(key, s) for s in staples):
        return True
    text = (amount or "").strip()
    if text in TRACE_WORDS:
        return True
    parsed = parse_amount(text)
    return parsed is not None and parsed[1].lower() in SEASONING_SPOONS


def round_won(value, step=10):
    """0.5는 올린다(파이썬 round의 짝수 반올림을 쓰지 않는다). 음수는 쓰지 않는다.
    소수 여섯째 자리로 먼저 맞춰 0.575 × 11800 = 6784.999…처럼 부동소수 오차로 0.5 경계를 놓치지 않는다."""
    return int(math.floor(round(value / step, 6) + 0.5)) * step


def item_cost(used, price, price_quantity):
    """결정 10·13. 구입 가격 × min(쓴 양 ÷ 구입 수량, 1), 10원 단위. 가격·구입 수량이 없으면 None."""
    if price is None or not price_quantity:
        return None
    return round_won(price * min(used / price_quantity, 1))


def _get(item, key):
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def summarize(eat_out_price, servings, items):
    """items: excluded·cost 속성(또는 키)을 가진 줄. 결정 13·14.
    → {"ingredient_cost": 가격 있는 줄 cost 합, "saved": 사 먹으면 × 인분 − 재료비 | None, "excluded_count": excluded == 'no_price' 수}"""
    costs = [cost for cost in (_get(item, "cost") for item in items) if cost is not None]
    total = sum(costs)
    return {
        "ingredient_cost": total,
        "saved": eat_out_price * servings - total if eat_out_price is not None and costs else None,
        "excluded_count": sum(1 for item in items if _get(item, "excluded") == "no_price"),
    }


def draft_rows(recipe, user_id):
    """결정 4·5. 레시피 재료 → [{name, amount, ingredient_id, stock_name, stock_quantity, stock_unit, base_amount, seasoning}].
    재고 순서는 recipes.inventory_rows(user_id)를 그대로 쓴다(따로 정렬하지 않는다, 개정 1 P18).
    물(normalize(key) in ALWAYS_HAVE)은 뺀다. 재고 한 행은 먼저 맞은 재료 하나에만."""
    staples = seasoning_names(user_id)
    stock = [(item, prepare(item.name)) for item, _ in inventory_rows(user_id)]
    rows = []
    for ingredient in recipe.ingredients:
        key, amount = ingredient_key(ingredient["name"]), ingredient["amount"]
        if normalize(key) in ALWAYS_HAVE:
            continue
        key_prepared = prepare(key)
        index = next((n for n, (_, prepared) in enumerate(stock) if match_prepared(key_prepared, prepared)), None)
        item = stock.pop(index)[0] if index is not None else None
        rows.append({
            "name": ingredient["name"],
            "amount": amount,
            "ingredient_id": item.id if item else None,
            "stock_name": item.name if item else None,
            "stock_quantity": item.quantity if item else None,
            "stock_unit": item.unit if item else None,
            "base_amount": in_unit(amount, item.unit) if item else None,
            "seasoning": is_seasoning(key, amount, staples),
        })
    return rows


@bp.get("/recipes/<int:recipe_id>/cook-draft")
@login_required
def cook_draft(recipe_id):
    recipe = get_owned_or_404(Recipe, recipe_id)
    res = jsonify({
        "recipe_id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "eat_out_price": recipe.eat_out_price,
        "eat_out_source": recipe.eat_out_source,
        "rows": draft_rows(recipe, g.user.id),
    })
    res.headers["Cache-Control"] = "no-store"  # 식습관·지출 정보
    return res


def lock_user(user_id):
    """PostgreSQL 사용자 잠금(결정 9). 트랜잭션이 끝나면 풀린다. SQLite(개발)는 잠그지 않는다."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(sql("SELECT pg_advisory_xact_lock(:key, :user_id)"), {"key": LOCK_KEY, "user_id": user_id})


def aware(value):
    """SQLite는 시간대 없이 돌려준다(UTC로 저장됨) — detail_json·undo 시간 비교·Task 5가 같이 쓴다(개정 1 P4·S14)."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def photo_url(cook_log):
    return f"/api/photos/{cook_log.photo_key}" if cook_log.photo_key else None


def cost_known(cook_log):
    """재료비를 아는가. 레시피 일기는 늘(가격 있는 줄이 없으면 0). 직접 쓴 일기는 비우면 0으로 저장해 아낀 돈이 있거나 0보다 크면 안다.
    ponytail: 사 먹으면 얼마 없이 0원을 적은 일기는 빈 칸과 구별하지 못한다 — 칸 하나(manual)로 두려고 받아들인 한계, 문제되면 재료비 입력 여부 칸을 더한다."""
    return not cook_log.manual or cook_log.saved is not None or cook_log.ingredient_cost > 0


def list_json(cook_log):
    return {"id": cook_log.id, "recipe_id": cook_log.recipe_id, "manual": cook_log.manual, "title": cook_log.title,
            "cooked_on": cook_log.cooked_on.isoformat(), "servings": cook_log.servings, "rating": cook_log.rating, "memo": cook_log.memo,
            "photo_url": photo_url(cook_log), "eat_out_price": cook_log.eat_out_price, "eat_out_source": cook_log.eat_out_source,
            "ingredient_cost": cook_log.ingredient_cost if cost_known(cook_log) else None, "saved": cook_log.saved, "excluded_count": cook_log.excluded_count,
            "created_at": iso_datetime(cook_log.created_at)}


def item_json(item):
    return {"name": item.name, "amount_text": item.amount_text, "used": item.used, "unit": item.unit, "removed": item.removed,
            "price": item.price, "price_quantity": item.price_quantity, "cost": item.cost, "excluded": item.excluded}


def detail_json(cook_log):
    return {**list_json(cook_log), "items": [item_json(i) for i in cook_log.items], "food_log_id": cook_log.food_log_id,
            "undo_until": iso_datetime(aware(cook_log.created_at) + timedelta(seconds=UNDO_SECONDS))}


def parse_common(data, cook_log, creating):
    """고치기(Task 5)와 같이 쓰는 칸. 보낸 칸만(creating이면 cooked_on 필수)."""
    if creating or "cooked_on" in data:
        cook_log.cooked_on = food_logs.eaten_date(data.get("cooked_on"))
    if "rating" in data:
        cook_log.rating = None if data["rating"] is None else integer(data["rating"], "별점은", 1, 5)
    if "memo" in data:
        cook_log.memo = memo(data["memo"], MAX_MEMO)
    if "eat_out_price" in data:
        apply_eat_out(cook_log, won(data["eat_out_price"], EAT_OUT_ERROR))


def won(value, message):
    """None 또는 bool 아닌 0~MAX_WON 정수. 아니면 400 message."""
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_WON):
        abort(400, message)
    return value


def manual_money(cook_log, cost, known):
    """직접 쓴 일기(추가 2026-09-16): 재료비는 적은 값(비우면 0), 아낀 돈은 사 먹으면 얼마와 재료비를 둘 다 알 때만(결정 14와 같게 모르면 None)."""
    cook_log.ingredient_cost = cost or 0
    both = known and cook_log.eat_out_price is not None
    cook_log.saved = cook_log.eat_out_price * cook_log.servings - cook_log.ingredient_cost if both else None
    cook_log.excluded_count = 0


def apply_eat_out(cook_log, value):
    """결정 11. value가 None이면 일기 칸만 비우고 레시피는 그대로. 레시피 값과 같으면 출처도 레시피 출처,
    다르면 'user'로 일기·레시피를 함께 바꾼다(레시피는 updated_at을 그대로 넣어 목록 순서를 지킨다)."""
    recipe = cook_log.recipe
    cook_log.eat_out_price = value
    if value is None:
        cook_log.eat_out_source = None
    elif recipe is not None and recipe.eat_out_price == value:
        cook_log.eat_out_source = recipe.eat_out_source
    else:
        cook_log.eat_out_source = "user"
        if recipe is not None:
            recipe.eat_out_price, recipe.eat_out_source = value, "user"
            flag_modified(recipe, "updated_at")  # UPDATE에 지금 값을 넣어 onupdate가 돌지 않게


def check_photo_room(user, size, excluding=None):
    """사용자 일기 사진 합계(excluding 일기의 사진은 빼고) + size가 한도(체험 20MB)를 넘으면 400 PHOTO_FULL."""
    query = db.session.query(db.func.coalesce(db.func.sum(CookLog.photo_size), 0)).filter(CookLog.user_id == user.id)
    if excluding is not None:
        query = query.filter(CookLog.id != excluding.id)
    if query.scalar() + size > (MAX_DEMO_PHOTO_BYTES if user.provider == "demo" else MAX_USER_PHOTO_BYTES):
        abort(400, PHOTO_FULL)


def new_photo_key(user_id, ext):
    return f"cooklog/{user_id}/{uuid.uuid4().hex}.{ext}"


def parse_usages(value):
    """[{ingredient_id, amount}] 0~MAX_USAGES개, id 겹치지 않음(아니면 BAD_REQUEST), amount는 소수 셋째 자리로 맞춘 뒤 0 < x ≤ MAX_AMOUNT 유한수(아니면 AMOUNT_ERROR).
    셋째 자리로 맞춰야 뺀 양(used)과 되돌린 양이 재고 반올림(round 3)과 어긋나지 않는다."""
    if not isinstance(value, list) or len(value) > MAX_USAGES:
        abort(400, food_logs.BAD_REQUEST)
    seen = set()
    for usage in value:
        item_id = usage.get("ingredient_id") if isinstance(usage, dict) else None
        if isinstance(item_id, bool) or not isinstance(item_id, int) or not 1 <= item_id <= 2**31 - 1 or item_id in seen:
            abort(400, food_logs.BAD_REQUEST)
        seen.add(item_id)
        amount = usage.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            abort(400, AMOUNT_ERROR)
        usage["amount"] = amount = round(amount, 3)
        if not 0 < amount <= MAX_AMOUNT:
            abort(400, AMOUNT_ERROR)
    return value


def _form_json():
    try:
        data = json.loads(request.form.get("data") or "null")
    except (ValueError, RecursionError):
        data = None
    if not isinstance(data, dict):
        abort(400, food_logs.BAD_REQUEST)
    return data


@bp.post("/cook-logs")
@login_required
def create_cook_log():
    """multipart data(JSON) + 선택 image → 201 {log, deducted_names}. 순서는 스펙 29절 구현 세부(요리 일기 저장).
    data.manual이면 레시피 없이 쓴 일기(추가 2026-09-16): title·ingredient_cost를 받고 재고는 건드리지 않는다.
    ponytail: R2에 올리는 동안(최대 수 초) 사용자 잠금·재료 행 잠금을 잡고 있다 — 같은 사용자 요청만 기다린다."""
    data = _form_json()
    manual = data.get("manual", False)
    if not isinstance(manual, bool) or not (set(data) <= MANUAL_FIELDS if manual else not MANUAL_ONLY & set(data)):
        abort(400, food_logs.BAD_REQUEST)
    lock_user(g.user.id)  # 레시피(사 먹으면 얼마)·재료 행보다 먼저 — 모든 쓰기가 같은 순서로 잠근다(교착 방지)
    recipe = None if manual else get_owned_or_404(Recipe, food_logs._id(data.get("recipe_id")))
    title = text(data.get("title"), "요리 이름은", 60) if manual else recipe.title
    servings = integer(data.get("servings"), "인분은", 1, 20)
    cook_log = CookLog(user_id=g.user.id, recipe=recipe, manual=manual, title=title, servings=servings)
    parse_common(data, cook_log, creating=True)
    cost = won(data.get("ingredient_cost"), COST_ERROR)
    usages = [] if manual else parse_usages(data.get("usages"))

    make_food = data.get("food_log", True)
    if not isinstance(make_food, bool):
        abort(400, food_logs.BAD_REQUEST)
    slot = None
    if data.get("meal_slot_id") is not None:
        slot = meals._owned_slot(food_logs._id(data["meal_slot_id"]))
        if slot.recipe_id != recipe.id:
            abort(400, food_logs.BAD_REQUEST)
    on_slot_day = slot is not None and slot.date == cook_log.cooked_on
    meal = data.get("meal")
    if make_food and not on_slot_day and meal not in meals.MEALS:
        abort(400, "끼니를 골라주세요.")

    image = None
    if "image" in request.files:
        if storage.mode() == "off":
            abort(503, storage.UPLOAD_UNAVAILABLE)
        image = photos.read_image(MAX_PHOTO_BYTES)

    if CookLog.query.filter_by(user_id=g.user.id).count() >= MAX_COOK_LOGS:  # 상한 확인은 사용자 잠금 안에서(결정 20)
        abort(400, f"요리 일기는 {MAX_COOK_LOGS}개까지 남길 수 있어요.")
    if image is not None:
        check_photo_room(g.user, len(image[0]))

    rows = [] if manual else draft_rows(recipe, g.user.id)  # 차감 전 재고로 판정
    ids = [usage["ingredient_id"] for usage in usages]
    # populate_existing: draft_rows가 잠그기 전에 읽어 둔 같은 행의 옛 수량을 쓰지 않게 잠근 뒤 값으로 덮는다
    locked = (
        Ingredient.query.filter(Ingredient.id.in_(ids), Ingredient.user_id == g.user.id)
        .order_by(Ingredient.id).with_for_update().populate_existing().all()
    )
    if len(locked) != len(ids):
        abort(400, STOCK_CHANGED)  # 지운 id·남의 id를 같은 문구로(결정 9)
    stock = {item.id: item for item in locked}
    by_id = {row["ingredient_id"]: row for row in rows if row["ingredient_id"] is not None}
    staples = None
    deducted_names = []
    for usage in usages:
        item = stock[usage["ingredient_id"]]
        before, amount = item.quantity, usage["amount"]
        left = round(before - amount, 3)
        used = min(amount, before) if left < 0.001 else round(before - left, 3)  # 남는 줄은 실제로 줄어든 양 — 되돌리면 정확히 원래 수량
        row = by_id.get(item.id)
        if row is not None:
            seasoning = row["seasoning"]
        else:
            staples = seasoning_names(g.user.id) if staples is None else staples
            seasoning = is_seasoning(ingredient_key(item.name), "", staples)
        excluded = "seasoning" if seasoning else ("no_price" if item.price is None or not item.price_quantity else None)
        line = CookLogItem(
            name=item.name, used=used, unit=item.unit, quantity_before=before, location_id=item.location_id,
            purchased_on=item.purchased_on, expires_on=item.expires_on, price=item.price, price_quantity=item.price_quantity,
            cost=item_cost(used, item.price, item.price_quantity) if excluded is None else None,  # 양념은 cost None — summarize가 합에 넣지 않게
            excluded=excluded,
        )
        cook_log.items.append(line)  # 관계에 붙여야 summarize(cook_log.items)가 본다(개정 1 P3)
        deducted_names.append(item.name)
        if left < 0.001:
            line.removed, line.removal = True, IngredientRemoval(user_id=g.user.id, name=item.name, reason="eaten")
            db.session.delete(item)
        else:
            item.quantity, line.ingredient = left, item
    for row in rows:
        if row["ingredient_id"] is None and not row["seasoning"]:
            cook_log.items.append(CookLogItem(name=row["name"][:50], amount_text=row["amount"][:30] or None, excluded="no_price"))
    if manual:
        manual_money(cook_log, cost, cost is not None)
    else:
        for key, value in summarize(cook_log.eat_out_price, servings, cook_log.items).items():
            setattr(cook_log, key, value)

    if make_food and not (slot is not None and slot.food_log is not None):  # 이미 먹은 칸은 SLOT_TAKEN 대신 만들지 않는다(결정 16)
        what = {"title": cook_log.title} if manual else {"recipe_id": recipe.id}  # 직접 쓴 일기는 이름만 적은 먹은 기록(영양 없음)
        fields = {"meal_slot_id": slot.id} if on_slot_day else {**what, "eaten_on": cook_log.cooked_on.isoformat(), "meal": meal}
        food = food_logs.build_log({**fields, "place": "home"})
        food.source = "cook_log"
        cook_log.food_log = food

    db.session.add(cook_log)
    keys = []
    if image is not None:
        data_bytes, media_type, ext = image
        keys.append(new_photo_key(g.user.id, ext))
        storage.put(keys[0], data_bytes, media_type)  # 저장소 오류는 503 — 커밋 전이라 모두 되돌려진다
        cook_log.photo_key, cook_log.photo_size = keys[0], len(data_bytes)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        storage.delete(keys)
        if isinstance(e, IntegrityError):
            # 흔한 원인은 같은 칸 food_logs.meal_slot_id UNIQUE 경합(위에서 slot.food_log를 먼저 봐서 드묾, 개정 1 T4④)
            log.warning("cook log save conflict: %s", type(e).__name__)
            abort(400, STOCK_CHANGED)
        raise
    return jsonify(log=detail_json(cook_log), deducted_names=deducted_names), 201


@bp.post("/cook-logs/<int:log_id>/undo")
@login_required
def undo_cook_log(log_id):
    """결정 7·8. 저장 뒤 UNDO_SECONDS 안이면 뺀 양을 더하고 지운 재료를 스냅숏으로 되살린 뒤 일기·먹은 기록·다 먹었어요 기록·사진을 지운다.
    사용자 잠금을 먼저 잡고 일기를 읽는다 — 동시에 두 번 보내면 뒤 요청은 지워진 일기를 보고 404(두 번 더하지 않게)."""
    lock_user(g.user.id)
    cook_log = get_owned_or_404(CookLog, log_id)
    if utcnow() > aware(cook_log.created_at) + timedelta(seconds=UNDO_SECONDS):
        abort(400, UNDO_EXPIRED)
    restored, skipped, fallback = [], [], None
    for item in cook_log.items:
        if item.removed:
            location = db.session.get(StorageLocation, item.location_id) if item.location_id is not None else None
            if location is None or location.user_id != g.user.id:
                fallback = fallback or default_location(g.user.id)
                location = fallback
            db.session.add(Ingredient(
                user_id=g.user.id, name=item.name, quantity=item.quantity_before, unit=item.unit, location_id=location.id,
                purchased_on=item.purchased_on, expires_on=item.expires_on, price=item.price, price_quantity=item.price_quantity,
            ))
            restored.append(item.name)
            if item.removal is not None:
                db.session.delete(item.removal)
        elif item.used is not None:
            ingredient = (
                Ingredient.query.filter_by(id=item.ingredient_id, user_id=g.user.id).with_for_update().populate_existing().first()
                if item.ingredient_id is not None else None
            )
            if ingredient is None or ingredient.unit != item.unit:
                skipped.append(item.name)  # 사용자가 지웠거나 단위를 바꿨다
            else:
                ingredient.quantity = round(ingredient.quantity + item.used, 3)  # 그사이 고친 수량 위에 더한다
                restored.append(item.name)
    keys = [cook_log.photo_key] if cook_log.photo_key else []
    if cook_log.food_log is not None:
        keys += [p.photo_key for p in cook_log.food_log.photos]  # 그사이 먹은 기록에 붙인 사진 파일도(개정 1 D15)
        db.session.delete(cook_log.food_log)
    db.session.delete(cook_log)
    db.session.commit()
    storage.delete(keys)  # 커밋 뒤에 — 실패는 로그만
    return jsonify(restored=restored, skipped=skipped)


def day_cursor(day, row_id):
    """결정 20: 날짜를 UTC 자정 시각으로 기존 커서에 넣는다."""
    return encode_cursor(datetime.combine(day, time.min, tzinfo=timezone.utc), row_id)


@bp.get("/cook-logs")
@login_required
def list_cook_logs():
    """결정 20. cooked_on·id 내림차순 커서 페이지, limit 1~50(기본 20)."""
    limit = min(max(request.args.get("limit", LIST_PAGE, type=int), 1), 50)
    query = CookLog.query.filter_by(user_id=g.user.id)
    cursor = request.args.get("cursor")
    if cursor:
        when, row_id = decode_cursor(cursor)
        day = when.date()
        query = query.filter(or_(CookLog.cooked_on < day, and_(CookLog.cooked_on == day, CookLog.id < row_id)))
    logs = query.order_by(CookLog.cooked_on.desc(), CookLog.id.desc()).limit(limit + 1).all()
    has_more = len(logs) > limit
    logs = logs[:limit]
    next_cursor = day_cursor(logs[-1].cooked_on, logs[-1].id) if has_more else None
    res = jsonify(items=[list_json(c) for c in logs], next_cursor=next_cursor)
    res.headers["Cache-Control"] = "no-store"  # 식습관·지출 정보
    return res


@bp.get("/cook-logs/<int:log_id>")
@login_required
def get_cook_log(log_id):
    res = jsonify(detail_json(get_owned_or_404(CookLog, log_id)))
    res.headers["Cache-Control"] = "no-store"
    return res


@bp.patch("/cook-logs/<int:log_id>")
@login_required
def update_cook_log(log_id):
    """결정 18. 인분·쓴 재료는 고치지 않는다(화면에 따로 안내가 있다). eat_out_price를 보내면 세 칸을 다시 계산한다.
    직접 쓴 일기는 재료비(ingredient_cost)도 고치고, 안 보냈으면 적어 둔 재료비로 다시 계산한다."""
    cook_log = get_owned_or_404(CookLog, log_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not set(data) <= (MANUAL_PATCH_FIELDS if cook_log.manual else PATCH_FIELDS):
        abort(400, food_logs.BAD_REQUEST)
    if "ingredient_cost" in data:
        cost = won(data["ingredient_cost"], COST_ERROR)
        known = cost is not None
    else:
        cost, known = cook_log.ingredient_cost, cost_known(cook_log)  # 다시 계산하기 전(saved가 그대로일 때) 읽는다
    parse_common(data, cook_log, creating=False)
    if cook_log.manual and ("eat_out_price" in data or "ingredient_cost" in data):
        manual_money(cook_log, cost, known)
    elif "eat_out_price" in data:
        for key, value in summarize(cook_log.eat_out_price, cook_log.servings, cook_log.items).items():
            setattr(cook_log, key, value)
    db.session.commit()
    return jsonify(detail_json(cook_log))


@bp.delete("/cook-logs/<int:log_id>")
@login_required
def delete_cook_log(log_id):
    """결정 17. 일기·사진만 지운다 — 재고·먹은 기록은 그대로 둔다.
    사용자 잠금을 먼저 잡고 그 뒤에 읽는다 — PUT 사진 바꾸기와 같은 순서라 동시에 와도 사진 키를 놓치지 않는다(리뷰 I1)."""
    lock_user(g.user.id)
    cook_log = get_owned_or_404(CookLog, log_id)
    keys = [cook_log.photo_key] if cook_log.photo_key else []
    db.session.delete(cook_log)
    db.session.commit()
    storage.delete(keys)
    return "", 204


def _relocked_cook_log(log_id):
    """사용자 잠금을 잡은 뒤 다시 읽는다(populate_existing — 이미 세션에 있는 옛 값을 돌려주지 않게).
    그사이 지워졌으면 예외 없이 None(리뷰 I1: db.session.refresh는 지워진 행에서 InvalidRequestError를 던진다)."""
    cook_log = db.session.get(CookLog, log_id, populate_existing=True)
    if cook_log is None or cook_log.user_id != g.user.id:
        return None
    return cook_log


@bp.put("/cook-logs/<int:log_id>/photo")
@login_required
def replace_cook_log_photo(log_id):
    if storage.mode() == "off":
        abort(503, storage.UPLOAD_UNAVAILABLE)
    cook_log = get_owned_or_404(CookLog, log_id)  # 사진을 읽기 전 빨리 실패(남의·없는 id)
    data_bytes, media_type, ext = photos.read_image(MAX_PHOTO_BYTES)
    lock_user(g.user.id)
    cook_log = _relocked_cook_log(log_id)  # 잠근 뒤 다시 읽어야 동시 PUT의 결과 위에서 old를 계산한다(리뷰 I1)
    if cook_log is None:
        abort(404, "찾을 수 없어요.")
    check_photo_room(g.user, len(data_bytes), excluding=cook_log)
    key = new_photo_key(g.user.id, ext)
    storage.put(key, data_bytes, media_type)
    old = cook_log.photo_key  # 잠근 뒤 다시 읽은 값 — 동시에 바뀐 사진도 정확히 지운다
    cook_log.photo_key, cook_log.photo_size = key, len(data_bytes)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        storage.delete([key])  # 실패하면 새로 올린 파일을 지운다
        raise
    storage.delete([old] if old else [])
    return jsonify(detail_json(cook_log))


@bp.delete("/cook-logs/<int:log_id>/photo")
@login_required
def delete_cook_log_photo(log_id):
    """사용자 잠금을 먼저 잡는다(리뷰 I1) — PUT 사진 바꾸기와 같은 순서."""
    lock_user(g.user.id)
    cook_log = get_owned_or_404(CookLog, log_id)
    old = cook_log.photo_key
    cook_log.photo_key, cook_log.photo_size = None, None
    db.session.commit()
    storage.delete([old] if old else [])
    return "", 204


def cooked_counts(recipe_ids, user_id):
    """요리 일기 쓰기 시트의 레시피 줄(29절 추가 2026-09-16) → {recipe_id: {count, last_on}}(일기가 없는 레시피는 빠짐). 쿼리 하나."""
    if not recipe_ids:
        return {}
    rows = (
        db.session.query(CookLog.recipe_id, db.func.count(CookLog.id), db.func.max(CookLog.cooked_on))
        .filter(CookLog.user_id == user_id, CookLog.recipe_id.in_(recipe_ids))
        .group_by(CookLog.recipe_id)
    )
    return {recipe_id: {"count": count, "last_on": last_on.isoformat()} for recipe_id, count, last_on in rows}


def recipe_cooked(recipe_id, user_id):
    """레시피 상세 요리 표시(결정 26). 없으면 None, 있으면 {count, last_on, last_rating} — 마지막은 cooked_on·id가 가장 큰 일기."""
    logs = CookLog.query.filter_by(recipe_id=recipe_id, user_id=user_id)
    count = logs.count()
    if not count:
        return None
    last = logs.order_by(CookLog.cooked_on.desc(), CookLog.id.desc()).first()
    return {"count": count, "last_on": last.cooked_on.isoformat(), "last_rating": last.rating}
