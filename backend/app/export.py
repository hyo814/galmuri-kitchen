"""데이터 내보내기(스펙 27절): 재고·내 레시피·내 양념 비율·장보기·식단·먹은 기록을 CSV로 묶은 zip. 하루(서울) 5번까지."""

import csv
import io
import os
import tempfile
import zipfile
import zlib
from datetime import timedelta, timezone

from flask import Blueprint, abort, g, jsonify, request, send_file
from sqlalchemy import case, or_, text
from sqlalchemy.orm import joinedload, selectinload

from . import scan
from .auth import login_required
from .ingredients import SEOUL, seoul_today
from .meals import MEALS
from .models import AiCall, CookLog, FoodLog, Ingredient, MealPlan, MealSlot, Recipe, Seasoning, ShoppingItem, ShoppingNote, db
from .shopping import STOCKED_KEEP_DAYS

bp = Blueprint("export", __name__, url_prefix="/api/export")

DAILY_LIMIT = 5
KINDS = ("export",)  # ai_calls 기록(모델·토큰 없음). AI 한도·사용량에는 세지 않는다
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "＝", "＋", "－", "＠")
SOURCE_LABELS = {  # 화면 format.ts의 SOURCE_LABEL과 같게(화면은 mine을 비워 두지만 CSV는 칸이 비지 않게 이름을 붙인다)
    "mine": "직접 입력",
    "public": "추천에서 저장",
    "ai": "AI가 만든 레시피",
    "youtube": "유튜브에서 가져옴",
    "instagram": "인스타그램에서 가져옴",
    "blog": "블로그에서 가져옴",
    "text": "붙여넣은 글에서 가져옴",
    "photo": "사진에서 가져옴",
}
BASIS_LABELS = {"main_weight": "주재료 무게", "servings": "인분", "yield": "완성량"}
SHOPPING_SOURCE_LABELS = {  # 화면 sync.ts의 sourceTag와 같게(직접 담은 것도 CSV는 칸이 비지 않게 이름을 붙인다)
    "manual": "직접 담음",
    "recipe": "레시피",
    "staple": "필수품",
    "urgent": "곧 떨어져요",
    "meal_plan": "식단",
    "memo": "메모 사진",
}
MEAL_LABELS = {"breakfast": "아침", "lunch": "점심", "dinner": "저녁", "snack": "간식"}
PLACE_LABELS = {"home": "집밥", "out": "외식"}
FOOD_LOG_SOURCE_LABELS = {"manual": "직접", "meal_plan": "식단", "cook_log": "요리 일기"}
FOOD_LOG_HEADER = ["날짜", "끼니", "무엇을 먹었나요", "어디서", "인분", "먹은 양(g)", "kcal", "탄수화물(g)", "단백질(g)", "지방(g)",
                   "당류(g)", "나트륨(mg)", "추정", "만족도", "메모", "남긴 방법", "사진 수", "사진 파일 이름", "남긴 시각"]
EAT_OUT_SOURCE_LABELS = {"user": "직접", "ai": "추정", "sample": "추정"}
COOK_LOG_HEADER = ["날짜", "요리", "인분", "별점", "메모", "사 먹으면(1인분·원)", "사 먹으면 출처", "재료비(원)", "아낀 돈(원)",
                   "가격 제외 재료 수", "쓴 재료", "사진 파일 이름", "남긴 시각"]
SPOOL_BYTES = 5_000_000  # 이보다 크면 메모리 대신 임시 파일에 zip을 만든다
BATCH = 200


def seoul_time(value):
    """UTC(또는 tz 없는 SQLite) datetime → 서울 시각 `YYYY-MM-DD HH:MM`. 없으면 빈 칸."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return f"{value.astimezone(SEOUL):%Y-%m-%d %H:%M}"


def shopping_rows():
    """shopping.csv에 담는 장보기 항목: 목록 + 7일 안에 산 것(요약 개수와 같게)."""
    cutoff = scan.utcnow() - timedelta(days=STOCKED_KEEP_DAYS)
    return owned(ShoppingItem).filter(or_(ShoppingItem.stocked_at.is_(None), ShoppingItem.stocked_at >= cutoff))


def meal_rows():
    """meals.csv에 담는 식단 칸: 내 식단의 채운 칸 전부(식단 이름과 함께), 식단 시작일 → 날짜 → 끼니 순."""
    meal_order = case(*[(MealSlot.meal == meal, index) for index, meal in enumerate(MEALS)], else_=len(MEALS))
    return (
        db.session.query(MealSlot, MealPlan.name)
        .join(MealPlan, MealSlot.plan_id == MealPlan.id)
        .filter(MealPlan.user_id == g.user.id)
        .order_by(MealPlan.start_on, MealPlan.id, MealSlot.date, meal_order)
    )


def food_log_rows():
    """food_logs.csv에 담는 내 먹은 기록: 날짜 → 끼니(MEALS 순) → 남긴 순(created_at, id)."""
    meal_order = case(*[(FoodLog.meal == meal, index) for index, meal in enumerate(MEALS)], else_=len(MEALS))
    return owned(FoodLog).options(selectinload(FoodLog.photos)).order_by(FoodLog.eaten_on, meal_order, FoodLog.created_at, FoodLog.id)


@bp.before_request
def require_fetch_header():
    # 내려받기는 하루 한도를 쓰므로 GET이어도 다른 사이트의 링크로 부를 수 없게 한다(__init__.require_fetch_header와 같은 헤더).
    if request.headers.get("X-Requested-With") != "fetch":
        abort(400, "잘못된 요청이에요.")


def safe(value):
    """엑셀이 수식으로 읽지 않도록 = + - @ 탭 CR(전각 포함)로 시작하는 글자 칸 앞에 '를 붙인다(CSV injection). 앞 공백은 건너뛰고도 본다."""
    if isinstance(value, str) and (value.startswith(FORMULA_STARTS) or value.lstrip().startswith(FORMULA_STARTS)):
        return "'" + value
    return value


def number(value):
    """1.0 → 1, 나머지는 그대로(csv가 가장 짧은 표현으로 쓴다)."""
    return int(value) if float(value).is_integer() else float(value)


def used_text(item):
    """'김치 0.3kg' · 재고에 없던 재료는 '돼지고기 200g' · 양이 없으면 이름만."""
    if item.used is not None:
        return f"{item.name} {number(item.used)}{item.unit or ''}"
    return f"{item.name} {item.amount_text}".strip()


def write_csv(archive, name, header, rows):
    with io.TextIOWrapper(archive.open(name, "w"), encoding="utf-8-sig", newline="") as out:  # BOM: 엑셀이 UTF-8 한글을 알아본다
        writer = csv.writer(out)
        writer.writerow(header)
        for row in rows:
            writer.writerow([safe(cell) for cell in row])


def owned(model):
    return model.query.filter_by(user_id=g.user.id)


def remaining(day=None):
    return max(0, DAILY_LIMIT - scan.calls_today(g.user.id, KINDS, day))


@bp.get("/summary")
@login_required
def summary():
    return jsonify(
        ingredients=owned(Ingredient).count(),
        recipes=owned(Recipe).count(),
        seasonings=owned(Seasoning).count(),
        shopping=shopping_rows().count(),
        memos=owned(ShoppingNote).count(),
        meals=meal_rows().count(),
        food_logs=owned(FoodLog).count(),
        cook_logs=owned(CookLog).count(),
        limit=DAILY_LIMIT,
        remaining=remaining(),
    )


@bp.get("")
@login_required
def export():
    if db.session.get_bind().dialect.name == "postgresql":  # scan.check_ai_limits와 같은 사용자별 잠금
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:group_key, :user_id)"),
            {"group_key": zlib.crc32(",".join(KINDS).encode()) & 0x7FFFFFFF, "user_id": g.user.id},
        )
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 한도를 조금 넘을 수 있다.
    today = seoul_today()
    if remaining(today) <= 0:
        abort(429, f"오늘 내보내기는 {DAILY_LIMIT}번까지 할 수 있어요. 내일 다시 해주세요.")
    # ponytail: 만들기 전에 기록하고 커밋한다(잠금 해제) — 만들다 오류가 나도 한 번 쓴 것으로 센다. 잦으면 실패 때 기록을 지운다.
    db.session.add(AiCall(user_id=g.user.id, kind="export", model=None, created_at=scan.utcnow()))
    db.session.commit()

    # ponytail: 행은 BATCH개씩 읽고 zip은 SPOOL_BYTES를 넘으면 임시 파일로 넘긴다. 상한은 재료 2000개·레시피 1000개
    # (재료 50·단계 30×500자)·양념 100개라 최악 수십 MB. 상한을 크게 올리면 비동기 작업·저장소 링크로 바꾼다.
    ingredients = (
        owned(Ingredient).options(joinedload(Ingredient.location)).order_by(Ingredient.purchased_on.asc().nulls_last(), Ingredient.id).yield_per(BATCH)
    )
    recipes = owned(Recipe).order_by(Recipe.updated_at.desc(), Recipe.id.desc()).yield_per(BATCH)
    seasonings = owned(Seasoning).order_by(Seasoning.id).yield_per(BATCH)
    shopping_items = (
        shopping_rows()
        .options(joinedload(ShoppingItem.location))
        .order_by(ShoppingItem.created_at, ShoppingItem.id)
        .yield_per(BATCH)
    )
    shopping_notes = (
        owned(ShoppingNote)
        .options(selectinload(ShoppingNote.photos))
        .order_by(ShoppingNote.updated_at.desc(), ShoppingNote.id.desc())
        .yield_per(BATCH)
    )
    meals = meal_rows().yield_per(BATCH)
    food_logs = food_log_rows().yield_per(BATCH)
    cook_logs = owned(CookLog).options(selectinload(CookLog.items)).order_by(CookLog.cooked_on, CookLog.id).yield_per(BATCH)
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
        write_csv(
            archive,
            "ingredients.csv",
            ["이름", "수량", "단위", "보관 위치", "구입일", "유통기한", "가격(원)"],
            (
                [i.name, number(i.quantity), i.unit, i.location.name, i.purchased_on or "", i.expires_on or "", "" if i.price is None else i.price]
                for i in ingredients
            ),
        )
        write_csv(
            archive,
            "recipes.csv",
            ["제목", "인분", "재료", "만드는 법", "출처", "출처 링크", "사진 주소"],
            (
                [
                    r.title,
                    r.servings,
                    "; ".join(f"{x['name']} {x['amount']}".strip() for x in r.ingredients),
                    "\n".join(f"{n}. {step}" for n, step in enumerate(r.steps, 1)),  # 따옴표로 감싼 칸 안 줄바꿈(엑셀이 한 칸으로 읽는다)
                    SOURCE_LABELS.get(r.source, r.source),
                    r.source_url or "",
                    r.image_url or "",
                ]
                for r in recipes
            ),
        )
        write_csv(
            archive,
            "seasonings.csv",
            ["이름", "기준", "기준 양", "기준 단위", "주재료", "양념"],
            (
                [
                    s.name,
                    BASIS_LABELS.get(s.basis, s.basis),
                    number(s.basis_amount),
                    s.basis_unit,
                    s.main_ingredient or "",
                    "; ".join(f"{x['name']} {number(x['amount'])}{x['unit']}" for x in s.items),
                ]
                for s in seasonings
            ),
        )
        write_csv(
            archive,
            "shopping.csv",
            ["이름", "수량", "단위", "생활용품", "살 날", "넣을 위치", "체크", "산 날(재고에 넣은 날)", "출처", "출처 이름", "담은 날"],
            (
                [
                    i.name,
                    number(i.quantity),
                    i.unit,
                    "예" if i.household else "",
                    i.planned_on or "",
                    i.location.name if i.location_id else "",
                    "예" if i.done_at else "",
                    seoul_time(i.stocked_at),
                    SHOPPING_SOURCE_LABELS.get(i.source, i.source),
                    i.source_label or "",
                    seoul_time(i.created_at),
                ]
                for i in shopping_items
            ),
        )
        write_csv(
            archive,
            "shopping_memos.csv",
            ["장소", "메모", "사진 수", "사진 파일 이름", "고친 시각"],
            (
                [
                    n.place or "",
                    n.body,
                    len(n.photos),
                    "; ".join(os.path.basename(p.photo_key) for p in n.photos),
                    seoul_time(n.updated_at),
                ]
                for n in shopping_notes
            ),
        )
        write_csv(
            archive,
            "meals.csv",
            ["식단 이름", "날짜", "끼니", "요리", "인분", "레시피에서", "1인분 추정 kcal"],
            (
                [
                    plan_name,
                    slot.date,
                    MEAL_LABELS.get(slot.meal, slot.meal),
                    slot.title,
                    slot.servings,
                    "예" if slot.recipe_id is not None else "아니요",
                    "" if slot.est_kcal is None else slot.est_kcal,
                ]
                for slot, plan_name in meals
            ),
        )
        write_csv(
            archive,
            "food_logs.csv",
            FOOD_LOG_HEADER,
            (
                [
                    log.eaten_on,
                    MEAL_LABELS[log.meal],
                    log.title or "사진 기록",
                    PLACE_LABELS.get(log.place, ""),
                    "" if log.servings is None else number(log.servings),
                    "" if log.grams is None else log.grams,
                    "" if log.kcal is None else number(log.kcal),
                    "" if log.carbs_g is None else number(log.carbs_g),
                    "" if log.protein_g is None else number(log.protein_g),
                    "" if log.fat_g is None else number(log.fat_g),
                    "" if log.sugars_g is None else number(log.sugars_g),
                    "" if log.sodium_mg is None else number(log.sodium_mg),
                    "예" if log.approx else "",
                    "" if log.rating is None else log.rating,
                    log.memo or "",
                    FOOD_LOG_SOURCE_LABELS.get(log.source, log.source),
                    len(log.photos),
                    "; ".join(os.path.basename(p.photo_key) for p in log.photos),
                    seoul_time(log.created_at),
                ]
                for log in food_logs
            ),
        )
        write_csv(
            archive,
            "cook_logs.csv",
            COOK_LOG_HEADER,
            (
                [
                    log.cooked_on,
                    log.title,
                    log.servings,
                    "" if log.rating is None else log.rating,
                    log.memo or "",
                    "" if log.eat_out_price is None else log.eat_out_price,
                    EAT_OUT_SOURCE_LABELS.get(log.eat_out_source, ""),
                    log.ingredient_cost,
                    "" if log.saved is None else log.saved,
                    log.excluded_count,
                    "; ".join(used_text(i) for i in log.items),
                    os.path.basename(log.photo_key) if log.photo_key else "",
                    seoul_time(log.created_at),
                ]
                for log in cook_logs
            ),
        )
    spool.seek(0)
    filename = f"galmuri-kitchen-{today:%Y%m%d}.zip"
    res = send_file(spool, mimetype="application/zip", as_attachment=True, download_name=filename)
    res.headers["Content-Disposition"] = f'attachment; filename="{filename}"'  # 화면과 맞춘 따옴표 형식(send_file은 따옴표를 뺀다)
    res.headers["Cache-Control"] = "no-store"
    res.headers["X-Content-Type-Options"] = "nosniff"
    return res
