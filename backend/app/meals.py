from datetime import timedelta

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from .auth import get_owned_or_404, login_required
from .models import MealPlan, MealSlot, Recipe, db
from .recipes import match_summary, stock_context
from .validation import commit_or_duplicate, integer, iso_date, text

# 식단·칸(스펙 20절, 4b-1). 셀프 배치만(복사·AI 초안은 뒤 태스크).
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


def _goal_note(value):
    if value is None:
        return None
    if not isinstance(value, str):
        abort(400, "잘못된 요청이에요.")
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > 100:
        abort(400, "메모는 100자까지 입력해주세요.")
    return trimmed


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
    if "goal_kcal" in data:
        value = data["goal_kcal"]
        plan.goal_kcal = None if value is None else integer(value, "하루 목표 칼로리는", 500, 5000)
    if "goal_note" in data:
        plan.goal_note = _goal_note(data["goal_note"])
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
