from calendar import monthrange
from datetime import date, timezone

from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .ingredients import SEOUL, seoul_today
from .models import KitchenTool, db
from .validation import integer, iso_date, text

bp = Blueprint("tools", __name__, url_prefix="/api/tools")

CATEGORIES = ("조리도구", "조리기구", "칼·도마", "기타")
CATEGORY_ORDER = {c: i for i, c in enumerate(CATEGORIES)}


def add_months(day, months):
    """day에서 months개월 뒤(음수면 앞). 없는 날짜(예: 2월 31일)는 그 달 말일로."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def check_base(tool):
    """점검 기준일: last_checked_on·bought_on 중 늦은 날짜(둘 다 없으면 created_at의 서울 날짜)."""
    dates = [d for d in (tool.last_checked_on, tool.bought_on) if d]
    if dates:
        return max(dates)
    created = tool.created_at
    if created.tzinfo is None:  # SQLite는 timezone 없이 돌려준다(UTC로 저장됨)
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone(SEOUL).date()


def to_json(tool, today):
    due_on = add_months(check_base(tool), tool.check_every_months) if tool.check_every_months else None
    return {
        "id": tool.id,
        "name": tool.name,
        "category": tool.category,
        "bought_on": tool.bought_on.isoformat() if tool.bought_on else None,
        "check_every_months": tool.check_every_months,
        "last_checked_on": tool.last_checked_on.isoformat() if tool.last_checked_on else None,
        "due_on": due_on.isoformat() if due_on else None,
        "is_due": due_on is not None and due_on <= today,
        "days_until_due": (due_on - today).days if due_on else None,
    }


def _optional_date(value, message):
    if value in (None, ""):
        return None
    parsed = iso_date(value)
    if parsed is None:
        abort(400, message)
    if parsed > seoul_today():
        abort(400, "구매일은 오늘 이후일 수 없어요.")
    return parsed


def parse_fields(data, creating):
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    fields = {}
    if creating or "name" in data:
        fields["name"] = text(data.get("name"), "도구 이름은", 30)
    if creating or "category" in data:
        category = data.get("category", "조리도구")
        if category not in CATEGORIES:
            abort(400, "분류를 조리도구·조리기구·칼·도마·기타 중에서 골라주세요.")
        fields["category"] = category
    if "bought_on" in data:
        fields["bought_on"] = _optional_date(data["bought_on"], "구매일은 YYYY-MM-DD 형식으로 입력해주세요.")
    if "check_every_months" in data:
        value = data["check_every_months"]
        fields["check_every_months"] = None if value is None else integer(value, "점검 주기는", 1, 60)
    return fields


def _sort_key(row):
    return (
        not row["is_due"],
        row["due_on"] or "9999-12-31",
        CATEGORY_ORDER.get(row["category"], len(CATEGORY_ORDER)),
        row["name"],
        row["id"],
    )


@bp.get("")
@login_required
def list_tools():
    today = seoul_today()
    rows = [to_json(t, today) for t in KitchenTool.query.filter_by(user_id=g.user.id).all()]
    rows.sort(key=_sort_key)
    return jsonify(rows)


@bp.post("")
@login_required
def create_tool():
    tool = KitchenTool(user_id=g.user.id, **parse_fields(request.get_json(silent=True), creating=True))
    db.session.add(tool)
    db.session.commit()
    return jsonify(to_json(tool, seoul_today())), 201


@bp.patch("/<int:tool_id>")
@login_required
def update_tool(tool_id):
    tool = get_owned_or_404(KitchenTool, tool_id)
    for key, value in parse_fields(request.get_json(silent=True), creating=False).items():
        setattr(tool, key, value)
    db.session.commit()
    return jsonify(to_json(tool, seoul_today()))


@bp.post("/<int:tool_id>/checked")
@login_required
def mark_checked(tool_id):
    tool = get_owned_or_404(KitchenTool, tool_id)
    tool.last_checked_on = seoul_today()
    db.session.commit()
    return jsonify(to_json(tool, seoul_today()))


@bp.post("/<int:tool_id>/replaced")
@login_required
def mark_replaced(tool_id):
    tool = get_owned_or_404(KitchenTool, tool_id)
    today = seoul_today()
    tool.bought_on = today
    tool.last_checked_on = today
    db.session.commit()
    return jsonify(to_json(tool, today))


@bp.delete("/<int:tool_id>")
@login_required
def delete_tool(tool_id):
    db.session.delete(get_owned_or_404(KitchenTool, tool_id))
    db.session.commit()
    return "", 204
