"""먹은 기록(스펙 21·24절). 기록 CRUD·하루·한 달·사진. 영양은 저장할 때 스냅숏(결정 2·5)."""

import re
import uuid
from datetime import date
from itertools import groupby

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from . import meals, storage
from .auth import get_owned_or_404, login_required
from .foods import NUTRIENTS, food_by_code, nutrition_mode
from .ingredients import SEOUL, seoul_today
from .meals import MEALS, meal_date
from .models import CookLog, FoodLog, FoodLogPhoto, MealPlan, MealSlot, Recipe, db, utcnow
from .nutrition import _round0, _round1
from .photos import read_image
from .validation import integer, iso_datetime, memo, text

bp = Blueprint("food_logs", __name__, url_prefix="/api")

MAX_PER_DAY = 20
MAX_LOGS = 10000
PLACES = ("home", "out")
MAX_MEMO = 200
MAX_PLAN_SUGGESTIONS = 8
BAD_REQUEST = "잘못된 요청이에요."
FUTURE = "아직 오지 않은 날은 남길 수 없어요."
SLOT_TAKEN = "이미 먹었어요로 남긴 칸이에요."
SERVINGS_ERROR = "인분은 0.5~20 사이로 입력해주세요."
GRAMS_ERROR = "먹은 양은 1~3000g 사이로 입력해주세요."
FIELDS_WHAT = ("meal_slot_id", "recipe_id", "food_code", "title")
FIELDS_AMOUNT = ("servings", "grams")
MAX_PHOTOS = 4
# 장보기 메모 사진과 같은 숫자(결정 9). 테스트가 app.shopping.*·app.food_logs.*를 따로 monkeypatch하고 합계도 따로 세서 공유하지 않는다(개정 1 D6)
MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_USER_PHOTO_BYTES = 200 * 1024 * 1024
MAX_DEMO_PHOTO_BYTES = 20 * 1024 * 1024
PHOTO_FULL = "사진 저장 공간이 가득 찼어요. 오래된 기록 사진을 지워주세요."


def meal_for_time(moment):
    """결정 8: 서울 시(時) 5–9 아침 · 10–14 점심 · 15–20 저녁 · 그 밖 간식.
    ponytail: 화면 cooklog/cook.ts cookMeal에 같은 시간표가 있다 — 바꾸면 둘 다."""
    hour = moment.astimezone(SEOUL).hour
    return "breakfast" if 5 <= hour < 10 else "lunch" if 10 <= hour < 15 else "dinner" if 15 <= hour < 21 else "snack"


def photo_json(photo):
    return {"id": photo.id, "url": f"/api/photos/{photo.photo_key}"}


def log_json(log):
    return {
        "id": log.id, "eaten_on": log.eaten_on.isoformat(), "meal": log.meal, "source": log.source,
        "title": log.title, "recipe_id": log.recipe_id, "meal_slot_id": log.meal_slot_id,
        "slot_servings": log.meal_slot.servings if log.meal_slot is not None else None,
        "food_code": log.food_code, "servings": log.servings, "grams": log.grams,
        "place": log.place, "rating": log.rating, "memo": log.memo,
        "nutrition": None if log.kcal is None else {k: getattr(log, k) for k in NUTRIENTS},
        "approx": log.approx, "nutrition_pending": log.nutrition_pending,
        "created_at": iso_datetime(log.created_at),
        "photos": [photo_json(p) for p in log.photos],
    }


def _meal_order(column):
    return case({meal: i for i, meal in enumerate(MEALS)}, value=column)


def _id(value):
    if isinstance(value, bool) or not isinstance(value, int):
        abort(400, BAD_REQUEST)
    return value


def eaten_date(value):
    """날짜 칸. 모양이 틀리면 400 '날짜를 골라주세요.', 2000~2100 밖은 meal_date 문구, 오늘(서울) 뒤면 FUTURE."""
    day = meal_date(value)
    if day is None:
        abort(400, "날짜를 골라주세요.")
    if day > seoul_today():
        abort(400, FUTURE)
    return day


_MONTH = re.compile(r"(\d{4})-(\d{2})")


def month_start(value):
    """'2026-09' → date(2026, 9, 1). fullmatch라야 '2026-09-01'(개정 1 D12)이 걸러진다."""
    match = _MONTH.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        abort(400, BAD_REQUEST)
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        abort(400, BAD_REQUEST)
    if not 2000 <= year <= 2100:
        abort(400, "날짜를 다시 확인해주세요.")
    return date(year, month, 1)


def _next_month(first):
    return date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)


def month_json(user_id, first):
    """결정 11. 그 달 내 기록(끼니 순 → created_at → id, 사진 selectinload)을 날짜별로 묶고, 요리 일기 날을 cooked로 표시한다(5단계 결정 27).
    ponytail: 한 달 기록(최대 620줄)을 파이썬에서 묶는다 — 느리면 날짜별 GROUP BY와 첫 사진 서브쿼리로 바꾼다."""
    logs = (
        FoodLog.query.options(selectinload(FoodLog.photos))
        .filter(FoodLog.user_id == user_id, FoodLog.eaten_on >= first, FoodLog.eaten_on < _next_month(first))
        .order_by(FoodLog.eaten_on, _meal_order(FoodLog.meal), FoodLog.created_at, FoodLog.id)
        .all()
    )
    cooks = (
        db.session.query(CookLog.cooked_on, CookLog.photo_key)
        .filter(CookLog.user_id == user_id, CookLog.cooked_on >= first, CookLog.cooked_on < _next_month(first))
        .order_by(CookLog.cooked_on, CookLog.id)
        .all()
    )
    days, home, out, kcal_days = [], 0, 0, []
    for day, day_logs in groupby(logs, key=lambda log: log.eaten_on):
        day_logs = list(day_logs)
        counted = [log for log in day_logs if log.kcal is not None]  # kcal 있는 기록만 합·약 계산에 넣는다(결정 11)
        kcal = sum(log.kcal for log in counted) if counted else None
        approx = any(log.approx for log in counted)
        photo_url = next((photo_json(log.photos[0])["url"] for log in day_logs if log.photos), None)
        days.append({
            "date": day.isoformat(), "meals": len({log.meal for log in day_logs}), "count": len(day_logs),
            "kcal": kcal, "approx": approx, "photo_url": photo_url, "cooked": False,
        })
        home += sum(1 for log in day_logs if log.place == "home")
        out += sum(1 for log in day_logs if log.place == "out")
        if kcal is not None:
            kcal_days.append((kcal, approx))
    # 결정 21·27: 요리 일기 날은 cooked, 요리만 있는 날도 days에 넣어 len(days)가 곧 기록한 날 합집합(개정 1 S12).
    # 사진 URL은 cooklog를 import하지 않고 직접 만든다(순환 import, 개정 1 P5)
    by_date = {cell["date"]: cell for cell in days}
    for day, photo_key in cooks:
        cell = by_date.setdefault(day.isoformat(), {
            "date": day.isoformat(), "meals": 0, "count": 0, "kcal": None, "approx": False, "photo_url": None,
        })
        cell["cooked"] = True
        if cell["photo_url"] is None and photo_key:  # 먹은 기록 사진이 먼저, 없으면 사진이 있는 첫 일기
            cell["photo_url"] = f"/api/photos/{photo_key}"
    days = sorted(by_date.values(), key=lambda cell: cell["date"])
    return {
        "days": days,
        "summary": {
            "logged_days": len(days),
            "avg_kcal": round(sum(k for k, _ in kcal_days) / len(kcal_days)) if kcal_days else None,
            "avg_approx": any(a for _, a in kcal_days),
            "home": home, "out": out,
            "home_percent": round(home * 100 / (home + out)) if home + out else None,
        },
    }


def check_caps(user_id, day, moving_from=None):
    """그날 기록이 MAX_PER_DAY개 이상이면 400 f'하루에 {MAX_PER_DAY}개까지 남길 수 있어요.', 전체가 MAX_LOGS개 이상이면
    f'먹은 기록은 {MAX_LOGS}개까지 남길 수 있어요.'(새로 만들 때만). moving_from은 PATCH로 날짜를 옮길 때 원래 날짜(같으면 세지 않음).
    ponytail: 상한 확인은 잠그지 않는다(결정 10) — 동시에 보내면 하루 21개가 될 수 있다. 문제되면 shopping._lock_user_items처럼 사용자 잠금을 더한다."""
    if moving_from == day:
        return
    if FoodLog.query.filter_by(user_id=user_id, eaten_on=day).count() >= MAX_PER_DAY:
        abort(400, f"하루에 {MAX_PER_DAY}개까지 남길 수 있어요.")
    if moving_from is None and FoodLog.query.filter_by(user_id=user_id).count() >= MAX_LOGS:
        abort(400, f"먹은 기록은 {MAX_LOGS}개까지 남길 수 있어요.")


def servings_value(value):
    """bool 아닌 0.5~20 숫자, 0.5 단위(value * 2가 정수). 아니면 400 SERVINGS_ERROR."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.5 <= value <= 20 or (value * 2) % 1:
        abort(400, SERVINGS_ERROR)
    return float(value)


def apply_fields(log, data, creating):
    """보낸 칸을 검증해 log에 넣는다. 돌려주는 값: 무엇을 바꿨으면 'what', 양만 바꿨으면 'amount', 영양과 상관없으면 None.
    관계는 언제나 객체로만 넣고 뺀다(log.recipe·log.meal_slot) — flush 전 FK 칸이 None·옛 값이라 fill_snapshots가 틀린 값을 읽지 않게(개정 1 D2).
    PATCH로 무엇을 바꾸면 칸 연결은 끊고 source는 그대로 둔다(처음 어떻게 남겼는지 기록, 개정 1 T2⑤). body가 dict인지는 호출 측이 본다."""
    what = creating or any(key in data for key in FIELDS_WHAT)
    amount = any(key in data for key in FIELDS_AMOUNT)
    from_slot, food = False, None
    if what:
        slot_id, recipe_id, code = (data.get(key) for key in FIELDS_WHAT[:3])
        if sum(value is not None for value in (slot_id, recipe_id, code)) > 1:
            abort(400, BAD_REQUEST)
        if slot_id is not None:
            slot = meals._owned_slot(_id(slot_id))
            if slot.food_log is not None and slot.food_log is not log:
                abort(400, SLOT_TAKEN)
            log.meal_slot, log.recipe, log.food_code, log.title = slot, slot.recipe, None, slot.title
            log.eaten_on, log.meal, log.source = eaten_date(slot.date.isoformat()), slot.meal, "meal_plan"
            from_slot = True
        elif recipe_id is not None:
            recipe = get_owned_or_404(Recipe, _id(recipe_id))
            log.meal_slot, log.recipe, log.food_code, log.title = None, recipe, None, recipe.title
        elif code is not None:
            food = food_by_code(code)
            if food is None:
                abort(400, "음식을 다시 골라주세요.")
            log.meal_slot, log.recipe, log.food_code, log.title = None, None, code, food.name[:60]
        else:
            log.meal_slot, log.recipe, log.food_code = None, None, None
            log.title = text(data.get("title"), "무엇을 먹었는지는", 60)

    if not from_slot:
        if creating or "eaten_on" in data:
            log.eaten_on = eaten_date(data.get("eaten_on"))
        if creating or "meal" in data:
            if data.get("meal") not in MEALS:
                abort(400, "끼니를 골라주세요.")
            log.meal = data["meal"]
    if log.meal_slot is not None and log.eaten_on != log.meal_slot.date:
        log.meal_slot = None  # 칸 날짜 밖으로 옮기면 연결만 끊는다(source 그대로). 같은 날 끼니만 옮기면 둔다

    if what or amount:
        servings, grams = data.get("servings"), data.get("grams")
        if log.food_code is not None:
            if servings is not None and grams is not None:
                abort(400, BAD_REQUEST)
            if grams is not None:
                if isinstance(grams, bool) or not isinstance(grams, int) or not 1 <= grams <= 3000:
                    abort(400, GRAMS_ERROR)
                log.servings, log.grams = None, grams  # 보낸 쪽만 남긴다 — 둘 다 남으면 fill_snapshots가 grams를 우선한다(개정 1 P9)
            else:
                log.servings, log.grams = servings_value(1 if servings is None else servings), None
                food = food or food_by_code(log.food_code)
                if food is None or food.serving_g is None:
                    abort(400, "이 음식은 g으로 입력해주세요.")
        elif log.title is None:  # 사진 기록: 무엇이 없으면 양도 없다
            log.servings = log.grams = None
        else:
            if grams is not None:
                abort(400, BAD_REQUEST)
            log.servings, log.grams = servings_value(1 if servings is None else servings), None

    if "place" in data:
        if data["place"] is not None and data["place"] not in PLACES:
            abort(400, BAD_REQUEST)
        log.place = data["place"]
    if "rating" in data:
        log.rating = None if data["rating"] is None else integer(data["rating"], "만족도는", 1, 5)
    if "memo" in data:
        log.memo = memo(data["memo"], MAX_MEMO)
    return "what" if what else "amount" if amount else None


def scaled(per, factor):
    """per(영양소 dict, 값 None 가능) × factor. kcal·sodium_mg는 _round0, 나머지 _round1(.5 올림 — 화면 Math.round와 같게, 개정 1 S2).
    per가 None이면 모두 None."""
    return {k: None if per is None or per.get(k) is None else (_round0(per[k] * factor) if k in ("kcal", "sodium_mg") else _round1(per[k] * factor)) for k in NUTRIENTS}


def has_source(log):
    """다시 계산할 출처(레시피·음식 코드)가 남았고 영양 모드가 off가 아닌가. 아니면 kcal을 두고 비율 조정만(개정 1 D4).
    off면 fill_snapshots가 레시피·음식을 계산하지 않아 스냅숏을 지우게 된다.
    식단 칸만 남은 기록은 세지 않는다 — 칸 기록의 레시피는 칸 레시피와 같아서, 레시피가 지워지면 칸도 레시피를 잃어
    다시 계산하면 스냅숏이 비거나(칸 AI 추정 kcal이 없을 때) 다른 값으로 바뀐다."""
    return (log.recipe is not None or log.food_code is not None) and nutrition_mode(g.user) != "off"


def rescale(log, factor):
    """출처가 사라진 기록의 양만 바뀌었을 때: 기존 영양 × factor(새 인분 ÷ 옛 인분), pending 끔. approx는 그대로(결정 2)."""
    for key, value in scaled({k: getattr(log, k) for k in NUTRIENTS}, factor).items():
        setattr(log, key, value)
    log.nutrition_pending = False


def build_log(data):
    """create_log의 커밋 전 부분. 요리 저장(cooklog)이 같은 트랜잭션 안에서 쓴다(5단계 개정 1 P6).
    no_autoflush 안에서 apply_fields(creating=True) → add → check_caps → fill_snapshots. 커밋·IntegrityError 처리는 호출 측."""
    log = FoodLog(user_id=g.user.id, source="manual")
    with db.session.no_autoflush:  # 검사·계산 쿼리가 반쯤 찬 행을 먼저 INSERT하지 않게
        apply_fields(log, data, creating=True)
        db.session.add(log)
        check_caps(g.user.id, log.eaten_on)
        fill_snapshots([log])
    return log


def create_log(data):
    """POST /api/food-logs와 칸 먹었어요(Task 5)가 함께 쓰는 만들기(개정 1 P5·D1·D3). 커밋까지 한다.
    같은 칸 UNIQUE 경합(그 밖 IntegrityError 포함)이면 rollback 뒤 None — 호출 측이 400 SLOT_TAKEN 또는 기존 기록 200."""
    log = build_log(data)
    try:
        db.session.flush()
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return None
    return log


def fill_snapshots(logs):
    """무엇·양이 바뀐 기록들의 영양 칸을 채운다(결정 5, 커밋은 호출 측). g.user로 계산한다.
    관계 객체(log.recipe·log.meal_slot)로만 읽는다 — FK 칸은 flush 전 값이 틀릴 수 있다(개정 1 D2)."""
    results = meals.nutrition_results([log.recipe for log in logs if log.recipe is not None])  # off면 {}
    mode = nutrition_mode(g.user)
    for log in logs:
        per, factor, approx, pending = None, 1, False, False
        if log.food_code is not None:
            food = food_by_code(log.food_code) if mode != "off" else None
            grams = log.grams if log.grams is not None else ((food.serving_g or 0) * (log.servings or 0) if food else 0)
            if food and grams:
                per, factor, approx = {k: getattr(food, k) for k in NUTRIENTS}, grams / 100, True
        elif log.recipe is not None or log.meal_slot is not None:
            result = results.get(log.recipe.id) if log.recipe is not None else None
            slot = log.meal_slot if log.meal_slot is not None and log.meal_slot.recipe is log.recipe else None
            if slot is not None:
                slot_per = meals.slot_nutrition(slot, result)
            elif result and result["per_serving"]:
                slot_per = {**result["per_serving"], "approx": result["approx"] or not result["usable"]}
            else:
                slot_per = None
            if slot_per:
                per, factor, approx = slot_per, log.servings or 1, slot_per["approx"]
            pending = bool(result and result["pending"])
        values = scaled(per, factor)
        for key, value in values.items():
            setattr(log, key, value)
        log.approx = approx and values["kcal"] is not None
        log.nutrition_pending = pending


@bp.get("/food-logs")
@login_required
def day_food_logs():
    day = meal_date(request.args.get("date"))
    if day is None:
        abort(400, "날짜를 다시 확인해주세요.")
    logs = (
        FoodLog.query.options(selectinload(FoodLog.meal_slot), selectinload(FoodLog.recipe), selectinload(FoodLog.photos))
        .filter_by(user_id=g.user.id, eaten_on=day)
        .order_by(_meal_order(FoodLog.meal), FoodLog.created_at, FoodLog.id)
        .all()
    )
    pending = [log for log in logs if log.nutrition_pending]
    if pending:
        # ponytail: GET이 행을 고친다 — 한 날짜 최대 20줄이라 가볍고, 따로 다시 계산 API를 두지 않는다(결정 2).
        # 멱등 — 서버 캐시만 읽어 같은 값을 채우므로 GET이 여러 번 와도 결과가 같다
        for log in pending:
            if not has_source(log):
                log.nutrition_pending = False  # 출처가 지워진 기록은 값을 두고 계산 중만 끈다(개정 1 D4)
        fill_snapshots([log for log in pending if has_source(log)])
        if any(db.session.is_modified(log) for log in pending):
            db.session.commit()

    slots = [] if day > seoul_today() else (
        MealSlot.query.join(MealPlan, MealSlot.plan_id == MealPlan.id)
        .filter(MealPlan.user_id == g.user.id, MealSlot.date == day, ~MealSlot.food_log.has())
        .order_by(_meal_order(MealSlot.meal), MealPlan.start_on.desc(), MealSlot.id)
        .limit(MAX_PLAN_SUGGESTIONS)
        .all()
    )
    res = jsonify(
        date=day.isoformat(),
        logs=[log_json(log) for log in logs],
        plan_slots=[{"id": s.id, "meal": s.meal, "title": s.title, "servings": s.servings, "recipe_id": s.recipe_id} for s in slots],
        cook_logs=[
            {"id": c.id, "title": c.title, "photo_url": f"/api/photos/{c.photo_key}" if c.photo_key else None}
            for c in CookLog.query.filter_by(user_id=g.user.id, cooked_on=day).order_by(CookLog.id)
        ],
        nutrition_pending_recipe_ids=sorted({log.recipe_id for log in logs if log.nutrition_pending and log.recipe_id is not None}),
    )
    res.headers["Cache-Control"] = "no-store"  # 건강·식습관 정보
    return res


@bp.get("/food-logs/month")
@login_required
def month_food_logs():
    first = month_start(request.args.get("month"))
    res = jsonify(month=first.strftime("%Y-%m"), today=seoul_today().isoformat(), **month_json(g.user.id, first))
    res.headers["Cache-Control"] = "no-store"  # 건강·식습관 정보
    return res


@bp.post("/food-logs")
@login_required
def create_food_log():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, BAD_REQUEST)
    log = create_log(data)
    if log is None:
        abort(400, SLOT_TAKEN if data.get("meal_slot_id") is not None else BAD_REQUEST)
    return jsonify(log_json(log)), 201


@bp.patch("/food-logs/<int:log_id>")
@login_required
def update_food_log(log_id):
    log = get_owned_or_404(FoodLog, log_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, BAD_REQUEST)
    old_servings, old_day = log.servings, log.eaten_on
    with db.session.no_autoflush:
        changed = apply_fields(log, data, creating=False)
        check_caps(g.user.id, log.eaten_on, moving_from=old_day)
        if changed == "what" or (changed == "amount" and has_source(log)):
            fill_snapshots([log])
        elif changed == "amount" and log.kcal is not None and old_servings and log.servings:
            rescale(log, log.servings / old_servings)
    try:
        db.session.flush()
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(400, SLOT_TAKEN if data.get("meal_slot_id") is not None else BAD_REQUEST)
    return jsonify(log_json(log))


@bp.delete("/food-logs/<int:log_id>")
@login_required
def delete_food_log(log_id):
    log = get_owned_or_404(FoodLog, log_id)
    keys = [p.photo_key for p in log.photos]
    db.session.delete(log)
    db.session.commit()
    storage.delete(keys)  # 커밋 뒤에 — 커밋이 실패하면 파일은 남아 있어야 한다
    return "", 204


def _check_photo_room(log, size):
    """기록당 MAX_PHOTOS장(400 '사진은 기록 하나에 4장까지 넣을 수 있어요.'), 사용자 먹은 기록 사진 합계(체험은 20MB, 400 PHOTO_FULL).
    ponytail: 사진 수·합계 확인은 잠그지 않는다 — 동시에 올리면 5장이 될 수 있다(메모 사진은 사용자 잠금을 쓰지만 먹은 기록은 오프라인 재전송이 없어 드묾)."""
    if len(log.photos) >= MAX_PHOTOS:
        abort(400, f"사진은 기록 하나에 {MAX_PHOTOS}장까지 넣을 수 있어요.")
    used = (
        db.session.query(db.func.coalesce(db.func.sum(FoodLogPhoto.size), 0))
        .join(FoodLog)
        .filter(FoodLog.user_id == g.user.id)
        .scalar()
    )
    if used + size > (MAX_DEMO_PHOTO_BYTES if g.user.provider == "demo" else MAX_USER_PHOTO_BYTES):
        abort(400, PHOTO_FULL)


def _store_photo(log, data, media_type, ext):
    """키 foodlog/<uid>/<hex>.<ext>로 storage.put → FoodLogPhoto 추가 → 커밋. 커밋이 실패하면 방금 올린 파일을 지우고
    IntegrityError면 400 BAD_REQUEST(그사이 기록이 지워짐), 그 밖 예외는 다시 던진다(shopping.upload_photo와 같은 모양, 개정 1 T3①).
    EXIF는 화면이 다시 인코딩해 빠진다(결정 9, 서버는 받은 바이트 그대로)."""
    key = f"foodlog/{g.user.id}/{uuid.uuid4().hex}.{ext}"
    storage.put(key, data, media_type)
    photo = FoodLogPhoto(photo_key=key, size=len(data))
    log.photos.append(photo)
    try:
        db.session.commit()
    except Exception as e:  # 행이 없으면 방금 올린 파일도 남기지 않는다(사진만 먼저면 기록도 함께 되돌린다)
        db.session.rollback()
        storage.delete([key])
        if isinstance(e, IntegrityError):
            abort(400, BAD_REQUEST)
        raise
    return photo


@bp.post("/food-logs/<int:log_id>/photos")
@login_required
def upload_food_log_photo(log_id):
    if storage.mode() == "off":
        abort(503, storage.UPLOAD_UNAVAILABLE)
    log = get_owned_or_404(FoodLog, log_id)
    data, media_type, ext = read_image(MAX_PHOTO_BYTES)
    _check_photo_room(log, len(data))
    return jsonify(photo_json(_store_photo(log, data, media_type, ext))), 201


@bp.delete("/food-logs/<int:log_id>/photos/<int:photo_id>")
@login_required
def delete_food_log_photo(log_id, photo_id):
    log = get_owned_or_404(FoodLog, log_id)
    photo = db.session.get(FoodLogPhoto, photo_id) if photo_id <= 2**31 - 1 else None
    if photo is None or photo.log_id != log.id:
        abort(404, "찾을 수 없어요.")
    key = photo.photo_key
    db.session.delete(photo)
    db.session.commit()
    storage.delete([key])
    return "", 204


@bp.post("/food-logs/photo")
@login_required
def create_photo_log():
    """사진만 먼저(결정 8). 사진과 기록을 한 요청에 — 따로 보내면 사진 실패 때 빈 기록이 남아서. 끼니·날짜는 서버 시각의 서울 시각."""
    if storage.mode() == "off":
        abort(503, storage.UPLOAD_UNAVAILABLE)
    data, media_type, ext = read_image(MAX_PHOTO_BYTES)
    now = utcnow()
    day = now.astimezone(SEOUL).date()
    check_caps(g.user.id, day)
    log = FoodLog(user_id=g.user.id, eaten_on=day, meal=meal_for_time(now), source="manual")
    _check_photo_room(log, len(data))
    db.session.add(log)
    _store_photo(log, data, media_type, ext)
    return jsonify(log_json(log)), 201
