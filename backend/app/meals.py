from datetime import timedelta

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from . import ai, scan
from .amounts import is_spoon, parse_amount
from .auth import ai_daily_limit, get_owned_or_404, login_required
from .ingredients import seoul_today
from .matching import match_prepared, normalize, prepare
from .models import Ingredient, MealPlan, MealSlot, Recipe, ShoppingItem, db
from .recipe_ai import _int_in, clean_draft, public_image_candidates, similar_public_image
from .recipes import ALWAYS_HAVE, _prepared_stock, check_recipe_cap, inventory, match_summary, parse_recipe, stock_context
from .validation import commit_or_duplicate, integer, iso_date, text

# 식단·칸(스펙 20절, 4b-1). 셀프 배치·주 복사·AI 초안.
bp = Blueprint("meals", __name__, url_prefix="/api")

MEALS = ("breakfast", "lunch", "dinner", "snack")
MAX_PLANS = 50  # 사용자당(26절 표)
MAX_DAYS = 31
NOT_FOUND = "찾을 수 없어요."
OUT_OF_RANGE = "식단 기간 밖의 날짜예요."
SLOT_TAKEN = "방금 채운 칸이에요. 다시 불러와주세요."


def _end_on(plan):
    return plan.start_on + timedelta(days=plan.days - 1)


def plan_summary(plan, filled):
    return {
        "id": plan.id,
        "name": plan.name,
        "start_on": plan.start_on.isoformat(),
        "end_on": _end_on(plan).isoformat(),
        "days": plan.days,
        "default_servings": plan.default_servings,
        "filled": filled,
        "total": plan.days * 4,
    }


def slot_json(slot, prepared_stock, urgent):
    if slot.recipe_id is None:
        have_count, total_count, urgent_names = None, None, []
    else:
        summary = match_summary(slot.recipe.ingredients, prepared_stock, urgent)
        have_count, total_count, urgent_names = summary["have_count"], summary["total_count"], summary["urgent_names"]
    return {
        "id": slot.id,
        "date": slot.date.isoformat(),
        "meal": slot.meal,
        "recipe_id": slot.recipe_id,
        "title": slot.title,
        "servings": slot.servings,
        "est_kcal": slot.est_kcal,
        "have_count": have_count,
        "total_count": total_count,
        "urgent_names": urgent_names,
    }


def plan_json(plan, prepared_stock, urgent):
    return {
        **plan_summary(plan, len(plan.slots)),
        "goal_kcal": plan.goal_kcal,
        "goal_note": plan.goal_note,
        "slots": [slot_json(s, prepared_stock, urgent) for s in plan.slots],
    }


def _owned_plan_with_slots(plan_id):
    """plan_json용: 칸 목록은 레시피까지 selectinload로 한 번에(N+1 방지)."""
    if not 0 < plan_id <= 2**31 - 1:
        abort(404, NOT_FOUND)
    plan = (
        MealPlan.query.options(selectinload(MealPlan.slots).selectinload(MealSlot.recipe))
        .filter_by(id=plan_id, user_id=g.user.id)
        .first()
    )
    if plan is None:
        abort(404, NOT_FOUND)
    return plan


def _owned_slot(slot_id):
    """칸 → 식단 → user_id 확인, 아니면 404."""
    if not 0 < slot_id <= 2**31 - 1:
        abort(404, NOT_FOUND)
    slot = (
        MealSlot.query.join(MealPlan, MealSlot.plan_id == MealPlan.id)
        .filter(MealSlot.id == slot_id, MealPlan.user_id == g.user.id)
        .first()
    )
    if slot is None:
        abort(404, NOT_FOUND)
    return slot


def _apply_goals(plan, data):
    """보낸 목표 칸만 검증해 식단에 넣는다(PATCH·AI 초안 공통)."""
    if "goal_kcal" in data:
        value = data["goal_kcal"]
        plan.goal_kcal = None if value is None else integer(value, "하루 목표 칼로리는", 500, 5000)
    if "goal_note" in data:
        value = data["goal_note"]
        if value is not None and not isinstance(value, str):
            abort(400, "잘못된 요청이에요.")
        value = value.strip() if value else None
        if value and len(value) > 100:
            abort(400, "메모는 100자까지 입력해주세요.")
        plan.goal_note = value or None


@bp.get("/meal-plans")
@login_required
def list_meal_plans():
    plans = MealPlan.query.filter_by(user_id=g.user.id).order_by(MealPlan.start_on.desc(), MealPlan.id.desc()).all()
    counts = {}
    if plans:
        rows = (
            db.session.query(MealSlot.plan_id, func.count(MealSlot.id))
            .filter(MealSlot.plan_id.in_([p.id for p in plans]))
            .group_by(MealSlot.plan_id)
            .all()
        )
        counts = dict(rows)
    latest = MealPlan.query.filter_by(user_id=g.user.id).order_by(MealPlan.created_at.desc(), MealPlan.id.desc()).first()
    return jsonify(
        items=[plan_summary(p, counts.get(p.id, 0)) for p in plans],
        default_servings=latest.default_servings if latest else 1,
    )


@bp.post("/meal-plans")
@login_required
def create_meal_plan():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    name = text(data.get("name"), "식단 이름은", 30)
    start_on = iso_date(data.get("start_on"))
    if start_on is None:
        abort(400, "시작일을 골라주세요.")
    days = integer(data.get("days"), "기간은", 1, MAX_DAYS)
    default_servings = integer(data.get("default_servings"), "기본 인분은", 1, 20)
    if MealPlan.query.filter_by(user_id=g.user.id).count() >= MAX_PLANS:
        abort(400, f"식단은 {MAX_PLANS}개까지 만들 수 있어요. 지난 식단을 지워주세요.")
    plan = MealPlan(user_id=g.user.id, name=name, start_on=start_on, days=days, default_servings=default_servings)
    db.session.add(plan)
    db.session.commit()
    prepared_stock, urgent = stock_context(g.user.id)
    return jsonify(plan_json(plan, prepared_stock, urgent)), 201


@bp.get("/meal-plans/<int:plan_id>")
@login_required
def get_meal_plan(plan_id):
    plan = _owned_plan_with_slots(plan_id)
    prepared_stock, urgent = stock_context(g.user.id)
    return jsonify(plan_json(plan, prepared_stock, urgent))


@bp.patch("/meal-plans/<int:plan_id>")
@login_required
def update_meal_plan(plan_id):
    plan = get_owned_or_404(MealPlan, plan_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    if "name" in data:
        plan.name = text(data["name"], "식단 이름은", 30)
    range_changed = "start_on" in data or "days" in data
    if "start_on" in data:
        start_on = iso_date(data["start_on"])
        if start_on is None:
            abort(400, "시작일을 골라주세요.")
        plan.start_on = start_on
    if "days" in data:
        plan.days = integer(data["days"], "기간은", 1, MAX_DAYS)
    if "default_servings" in data:
        plan.default_servings = integer(data["default_servings"], "기본 인분은", 1, 20)
    _apply_goals(plan, data)
    if range_changed:
        # 결정 1: 기간을 줄이거나 시작일을 옮기면 새 기간 밖의 칸은 같은 커밋에서 지운다.
        end_on = _end_on(plan)
        MealSlot.query.filter(
            MealSlot.plan_id == plan.id, or_(MealSlot.date < plan.start_on, MealSlot.date > end_on)
        ).delete(synchronize_session=False)
    db.session.commit()
    prepared_stock, urgent = stock_context(g.user.id)
    return jsonify(plan_json(_owned_plan_with_slots(plan.id), prepared_stock, urgent))


@bp.delete("/meal-plans/<int:plan_id>")
@login_required
def delete_meal_plan(plan_id):
    db.session.delete(get_owned_or_404(MealPlan, plan_id))
    db.session.commit()
    return "", 204


@bp.put("/meal-plans/<int:plan_id>/slots")
@login_required
def put_meal_slot(plan_id):
    plan = get_owned_or_404(MealPlan, plan_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    date = iso_date(data.get("date"))
    if date is None or not plan.start_on <= date <= _end_on(plan):
        abort(400, OUT_OF_RANGE)
    meal = data.get("meal")
    if meal not in MEALS:
        abort(400, "잘못된 요청이에요.")
    servings = integer(data["servings"], "인분은", 1, 20) if "servings" in data else plan.default_servings

    recipe_id = data.get("recipe_id")
    if recipe_id is not None:
        if isinstance(recipe_id, bool) or not isinstance(recipe_id, int):
            abort(400, "잘못된 요청이에요.")
        recipe = get_owned_or_404(Recipe, recipe_id)
        title = recipe.title  # 보낸 title은 무시
    else:
        title = text(data.get("title"), "무엇을 먹을지는", 60)

    slot = MealSlot.query.filter_by(plan_id=plan.id, date=date, meal=meal).first()
    if slot is None:
        slot = MealSlot(plan_id=plan.id, date=date, meal=meal)
        db.session.add(slot)
    slot.recipe_id = recipe_id
    slot.title = title
    slot.servings = servings
    slot.est_kcal = None  # 덮어쓸 때는 비운다(8: AI 초안으로 채운 칸만 값이 있다)
    commit_or_duplicate(SLOT_TAKEN)
    prepared_stock, urgent = stock_context(g.user.id)
    return jsonify(slot_json(slot, prepared_stock, urgent))


@bp.post("/meal-plans/<int:plan_id>/copy-week")
@login_required
def copy_meal_week(plan_id):
    plan = get_owned_or_404(MealPlan, plan_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    from_on = iso_date(data.get("from_on"))
    end_on = _end_on(plan)
    if from_on is None or not plan.start_on <= from_on <= end_on or (from_on - plan.start_on).days % 7 != 0:
        abort(400, "잘못된 요청이에요.")
    weeks = integer(data.get("weeks"), "복사할 주는", 1, 4)

    week_end = from_on + timedelta(days=6)
    originals = [s for s in plan.slots if from_on <= s.date <= week_end]
    if not originals:
        abort(400, "이번 주에 채운 칸이 없어요.")

    need_end = from_on + timedelta(days=7 * (weeks + 1) - 1)
    if (need_end - plan.start_on).days + 1 > MAX_DAYS:
        possible_weeks = (plan.start_on + timedelta(days=30) - week_end).days // 7
        if possible_weeks <= 0:
            abort(400, "이 주는 더 복사할 수 없어요.")
        abort(400, f"식단은 31일까지라 {possible_weeks}주까지 복사할 수 있어요.")

    if need_end > end_on:
        plan.days = (need_end - plan.start_on).days + 1  # 결정(2026-09-14): 기간을 넘으면 자동으로 늘린다

    existing = {(s.date, s.meal) for s in plan.slots}
    copied = kept = 0
    for slot in originals:
        for k in range(1, weeks + 1):
            key = (slot.date + timedelta(days=7 * k), slot.meal)
            if key in existing:
                kept += 1
                continue
            db.session.add(MealSlot(
                plan_id=plan.id, date=key[0], meal=slot.meal,
                recipe_id=slot.recipe_id, title=slot.title, servings=slot.servings, est_kcal=slot.est_kcal,
            ))
            existing.add(key)
            copied += 1

    commit_or_duplicate(SLOT_TAKEN)
    prepared_stock, urgent = stock_context(g.user.id)
    return jsonify(
        plan=plan_json(_owned_plan_with_slots(plan.id), prepared_stock, urgent), copied=copied, kept=kept
    )


@bp.patch("/meal-slots/<int:slot_id>")
@login_required
def update_meal_slot(slot_id):
    slot = _owned_slot(slot_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    slot.servings = integer(data.get("servings"), "인분은", 1, 20)
    db.session.commit()
    prepared_stock, urgent = stock_context(g.user.id)
    return jsonify(slot_json(slot, prepared_stock, urgent))


@bp.delete("/meal-slots/<int:slot_id>")
@login_required
def delete_meal_slot(slot_id):
    db.session.delete(_owned_slot(slot_id))
    db.session.commit()
    return "", 204


AI_DRAFT_FAIL = "식단 초안을 만들지 못했어요. 잠시 후 다시 시도해주세요."
MAX_DRAFT_DAYS = 7  # 결정 5: 보고 있는 한 주만(최대 28칸)
MAX_DRAFT_DISHES = 30
MAX_MINE = 100
RECIPE_CHANGED = "레시피가 방금 바뀌었어요. 초안을 다시 만들어주세요."


def clean_meal_draft(raw, empty_keys, mine_by_id, prepared_stock, urgent, candidates):
    """AI(또는 예시) 식단 초안을 정리한다. 모델 출력은 믿지 않는다. 쓸 칸이 없으면 None.
    empty_keys: {(날짜 iso, 끼니)} 빈 칸, mine_by_id: 이번 요청에 보낸 내 레시피 {id: {title, servings, ingredients, image_url}}."""
    raw = raw if isinstance(raw, dict) else {}
    dishes = []  # 원래 번호 그대로, 못 쓰는 번호는 None
    for row in raw.get("dishes")[:MAX_DRAFT_DISHES] if isinstance(raw.get("dishes"), list) else []:
        if not isinstance(row, dict):
            dishes.append(None)
            continue
        est_kcal = _int_in(row.get("kcal_per_serving"), 1, 3000)
        mine_id = row.get("mine_id")
        recipe = mine_by_id.get(mine_id) if isinstance(mine_id, int) and not isinstance(mine_id, bool) else None
        if recipe is not None:
            dishes.append({
                "recipe_id": mine_id, "title": recipe["title"], "servings": recipe["servings"], "est_kcal": est_kcal,
                "ingredients": [], "steps": [],
                "urgent_names": match_summary(recipe["ingredients"], prepared_stock, urgent)["urgent_names"],
                "image_url": recipe["image_url"],
            })
            continue
        draft = clean_draft(row)
        dishes.append(draft and {
            "recipe_id": None, "title": draft["title"], "servings": draft["servings"], "est_kcal": est_kcal,
            "ingredients": draft["ingredients"], "steps": draft["steps"],
            "urgent_names": match_summary(draft["ingredients"], prepared_stock, urgent)["urgent_names"],
            "image_url": similar_public_image(draft["title"], candidates),
        })

    slots, seen = [], set()
    for row in raw.get("slots") if isinstance(raw.get("slots"), list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str) or not isinstance(row.get("meal"), str):
            continue
        key = (row["date"], row["meal"])
        if key not in empty_keys or key in seen:
            continue
        seen.add(key)
        options = []
        for index in row.get("dishes") if isinstance(row.get("dishes"), list) else []:
            if _int_in(index, 0, len(dishes) - 1) is not None and dishes[index] and index not in options:
                options.append(index)
                if len(options) == 3:
                    break
        if options:
            slots.append((key, options))
    if not slots:
        return None

    slots.sort(key=lambda slot: (slot[0][0], MEALS.index(slot[0][1])))
    renumber = {}
    for _, options in slots:
        for index in options:
            renumber.setdefault(index, len(renumber))
    return {
        "dishes": [dishes[index] for index in renumber],  # dict는 넣은 순서를 지킨다
        "slots": [{"date": d, "meal": m, "options": [renumber[i] for i in options]} for (d, m), options in slots],
    }


@bp.post("/meal-plans/<int:plan_id>/ai-draft")
@login_required
def draft_meal_plan(plan_id):
    """빈 칸마다 요리 3개(추천 + `다른 걸로` 후보 2개)를 한 번에 받는다. 칸은 저장하지 않는다(목표 두 칸만 식단에 저장)."""
    plan = get_owned_or_404(MealPlan, plan_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    start_on = iso_date(data.get("start_on"))
    days = integer(data.get("days"), "기간은", 1, MAX_DRAFT_DAYS)
    if start_on is None or start_on < plan.start_on or start_on + timedelta(days=days - 1) > _end_on(plan):
        abort(400, OUT_OF_RANGE)
    meals = data.get("meals")
    if (
        not isinstance(meals, list) or not 1 <= len(meals) <= len(MEALS)
        or not all(isinstance(m, str) and m in MEALS for m in meals) or len(set(meals)) != len(meals)
    ):
        abort(400, "끼니를 하나 이상 골라주세요.")
    _apply_goals(plan, data)

    dates = [start_on + timedelta(days=i) for i in range(days)]
    filled = {(s.date, s.meal): s for s in plan.slots}
    empty = [(d.isoformat(), m) for d in dates for m in MEALS if m in meals and (d, m) not in filled]
    if not empty:
        abort(400, "채울 빈 칸이 없어요.")
    kept = [(d.isoformat(), m, filled[(d, m)].title) for d in dates for m in MEALS if m in meals and (d, m) in filled]

    user_id = g.user.id
    stock = inventory(user_id)  # 비어도 진행한다(재고 없이도 식단은 짠다)
    prepared_stock, urgent = _prepared_stock(stock), {name for name, is_urgent in stock if is_urgent}
    recent = Recipe.query.filter_by(user_id=user_id).order_by(Recipe.updated_at.desc(), Recipe.id.desc()).limit(MAX_MINE)
    # 커밋하면 객체가 만료돼 행마다 다시 읽으므로 쓸 값만 먼저 꺼내 둔다(최근 수정 순, dict는 순서를 지킨다)
    mine_by_id = {r.id: {"title": r.title, "servings": r.servings, "ingredients": r.ingredients, "image_url": r.image_url} for r in recent}
    goal_kcal, goal_note = plan.goal_kcal, plan.goal_note
    db.session.commit()  # 목표 두 칸은 다음에 미리 채우도록 저장한다

    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, "AI 식단 초안을 지금은 쓸 수 없어요.")
    if mode == "sample":
        raw = ai.sample_meal_draft(empty)
    else:
        scan.check_ai_limits(user_id, scan.RECIPE_KINDS, ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT"), "AI 레시피는")
        call = scan.start_ai_call(user_id, "meal")
        try:
            raw, usage = ai.draft_meals(
                empty,
                [f"{name} (빨리)" if is_urgent else name for name, is_urgent in stock],
                [(recipe_id, r["title"]) for recipe_id, r in mine_by_id.items()],
                kept,
                goal_kcal,
                goal_note,
            )
        except ai.AiError:
            abort(502, AI_DRAFT_FAIL)
        scan.finish_ai_call(call, usage)

    result = clean_meal_draft(raw, set(empty), mine_by_id, prepared_stock, urgent, public_image_candidates())
    if result is None:
        abort(502, AI_DRAFT_FAIL)
    return jsonify(
        **result, kept=[{"date": d, "meal": m, "title": title} for d, m, title in kept], sample=mode == "sample"
    )


@bp.post("/meal-plans/<int:plan_id>/ai-draft/apply")
@login_required
def apply_meal_draft(plan_id):
    """초안 넣기: 아직 빈 칸만 채우고, 새 요리는 요리마다 한 번만 내 레시피(source ai)로 저장한다. AI를 부르지 않는다."""
    plan = get_owned_or_404(MealPlan, plan_id)
    data = request.get_json(silent=True)
    dishes = data.get("dishes") if isinstance(data, dict) else None
    rows = data.get("slots") if isinstance(data, dict) else None
    if (
        not isinstance(dishes, list) or not 1 <= len(dishes) <= MAX_DRAFT_DISHES
        or not isinstance(rows, list) or not 1 <= len(rows) <= MAX_DRAFT_DAYS * len(MEALS)
    ):
        abort(400, "잘못된 요청이에요.")

    end_on, slots, seen = _end_on(plan), [], set()
    for row in rows:
        row = row if isinstance(row, dict) else {}
        date, meal, dish = iso_date(row.get("date")), row.get("meal"), _int_in(row.get("dish"), 0, len(dishes) - 1)
        est_kcal = row.get("est_kcal")
        if (
            date is None or not plan.start_on <= date <= end_on or meal not in MEALS or dish is None
            or (est_kcal is not None and _int_in(est_kcal, 1, 3000) is None) or (date, meal) in seen
        ):
            abort(400, "잘못된 요청이에요.")
        seen.add((date, meal))
        slots.append((date, meal, dish, est_kcal))

    filled = {(s.date, s.meal) for s in plan.slots}
    recipes, new_fields = {}, {}  # 칸이 쓰는 요리만 본다: 번호 → 내 레시피 / 새 요리 필드
    for _, _, index, _ in slots:
        if index in recipes or index in new_fields:
            continue
        dish = dishes[index]
        if isinstance(dish, dict) and "recipe_id" in dish:
            recipe_id = _int_in(dish["recipe_id"], 1, 2**31 - 1)
            recipe = Recipe.query.filter_by(id=recipe_id, user_id=g.user.id).first() if recipe_id else None
            if recipe is None:
                abort(400, RECIPE_CHANGED)
            recipes[index] = recipe
        else:
            fields = parse_recipe(dish)
            fields.pop("source_url", None)
            new_fields[index] = fields
    # 새 요리를 쓰는 칸이 모두 이미 찼으면 그 요리는 만들지 않는다.
    to_create = {i for d, m, i, _ in slots if i in new_fields and (d, m) not in filled}
    if to_create:
        check_recipe_cap(len(to_create))
        candidates = public_image_candidates()
        for index in sorted(to_create):
            fields = new_fields[index]
            recipes[index] = Recipe(
                user_id=g.user.id, **fields, source="ai", image_url=similar_public_image(fields["title"], candidates)
            )
            db.session.add(recipes[index])

    kept = 0
    for date, meal, index, est_kcal in slots:
        if (date, meal) in filled:
            kept += 1
            continue
        recipe = recipes[index]
        db.session.add(MealSlot(
            plan_id=plan.id, date=date, meal=meal, recipe=recipe, title=recipe.title,
            servings=plan.default_servings, est_kcal=est_kcal,
        ))
    commit_or_duplicate(SLOT_TAKEN)
    return jsonify(filled=len(slots) - kept, kept=kept, created_recipes=len(to_create)), 201


def shopping_rows(needs, stock, listed, today):
    """식단 장보기 미리보기 분류(스펙 23절 D4, 20절 구현 세부). 순수 함수, DB 없이 테스트한다.
    needs=[(이름, 양 글자, 인분 배율, 끼니 날짜)], stock=[(이름, 수량, 단위)], listed=[장보기 목록(stocked_at NULL) 이름]."""
    listed_norm = {normalize(name) for name in listed}
    stock_prepared = [(prepare(name), quantity, unit) for name, quantity, unit in stock]

    order = []
    groups = {}
    for name, amount, ratio, on in needs:
        if normalize(name) in ALWAYS_HAVE:
            continue
        key = normalize(name) or name
        group = groups.get(key)
        if group is None:
            group = groups[key] = {"name": name, "dates": [], "need": {}, "need_extra": [], "_seen": set()}
            order.append(key)
        group["dates"].append(on)
        parsed = parse_amount(amount)
        if parsed and not is_spoon(parsed[1]):
            value, unit = parsed
            group["need"][unit] = group["need"].get(unit, 0) + value * ratio
        else:
            piece = (amount or "").strip()
            if piece and piece not in group["_seen"]:
                group["_seen"].add(piece)
                group["need_extra"].append(piece)

    buckets = {"buy": [], "manual": [], "skip": []}
    for index, key in enumerate(order):
        group = groups[key]
        name = group["name"]
        planned_on = max(today, min(group["dates"]) - timedelta(days=1))
        prepared_name = prepare(name)
        matched = [(quantity, unit) for prepared, quantity, unit in stock_prepared if match_prepared(prepared_name, prepared)]
        has_stock = bool(matched)
        have = {}
        for quantity, unit in matched:
            parsed = parse_amount(f"{quantity:g}{unit}")
            if parsed:
                value, u = parsed
                have[u] = have.get(u, 0) + value

        need = group["need"]
        row = {
            "name": name,
            "planned_on": planned_on.isoformat(),
            "need": [{"quantity": round(value, 2), "unit": unit} for unit, value in need.items()],
            "need_extra": group["need_extra"],
            "have": [{"quantity": round(value, 2), "unit": unit} for unit, value in have.items()],
        }

        def add(bucket, quantity, unit, reason):
            row["quantity"], row["unit"], row["reason"] = quantity, unit, reason
            buckets[bucket].append((planned_on.isoformat(), index, row))

        if normalize(name) in listed_norm:
            add("skip", None, None, "listed")
        elif not need:
            add("skip", None, None, "enough") if has_stock else add("manual", 1, "개", None)
        elif len(need) >= 2:
            first_unit = next(iter(need))
            add("manual", round(need[first_unit], 2), first_unit, None)
        else:
            (unit, amount_needed), = need.items()
            if unit not in have and have:
                add("manual", round(amount_needed, 2), unit, None)
            else:
                short = amount_needed - have.get(unit, 0)
                add("buy", round(short, 2), unit, None) if short > 0.001 else add("skip", None, None, "enough")

    return {
        bucket: [entry_row for _, _, entry_row in sorted(entries, key=lambda entry: (entry[0], entry[1]))]
        for bucket, entries in buckets.items()
    }


@bp.get("/meal-plans/<int:plan_id>/shopping-preview")
@login_required
def meal_plan_shopping_preview(plan_id):
    """결정 2: 오늘 이후(오늘 포함) 레시피 칸만 계산한다. 담기는 여기서 하지 않는다(화면이 bulk로)."""
    plan = _owned_plan_with_slots(plan_id)
    today = seoul_today()
    start_on = max(today, plan.start_on)
    end_on = _end_on(plan)

    needs, recipe_slot_count = [], 0
    for slot in plan.slots:
        if slot.date < start_on or slot.recipe_id is None:
            continue
        recipe_slot_count += 1
        ratio = slot.servings / max(slot.recipe.servings, 1)  # 방어: servings는 0 이하일 수 없지만 혹시나
        for ingredient in slot.recipe.ingredients:
            needs.append((ingredient["name"], ingredient["amount"], ratio, slot.date))

    user_id = g.user.id
    stock = [(i.name, i.quantity, i.unit) for i in Ingredient.query.filter_by(user_id=user_id).all()]
    listed = [
        name for (name,) in db.session.query(ShoppingItem.name)
        .filter(ShoppingItem.user_id == user_id, ShoppingItem.stocked_at.is_(None))
        .all()
    ]

    rows = shopping_rows(needs, stock, listed, today)
    return jsonify(
        start_on=start_on.isoformat(), end_on=end_on.isoformat(), recipe_slot_count=recipe_slot_count, **rows
    )
