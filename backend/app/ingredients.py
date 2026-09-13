import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.orm import joinedload

from .auth import get_owned_or_404, login_required
from .locations import default_location, owned_location
from .matching import keyword_in
from .models import Ingredient, ItemRule, db
from .validation import text

bp = Blueprint("ingredients", __name__, url_prefix="/api/ingredients")

URGENT_DAYS = 3  # 유통기한까지 3일 이내(지난 것 포함)면 임박
OLD_DAYS_BY_KIND = {"fridge": 7, "freezer": 60, "room": None}  # 유통기한이 없을 때 오래됨 기준(일), room은 표시 안 함
SEVERITY = {"ok": 0, "old": 1, "urgent": 2, "danger": 3}
STATUS_RANK = {"danger": 0, "urgent": 1, "old": 2, "ok": 3}
SEOUL = ZoneInfo("Asia/Seoul")


def seoul_today():
    return datetime.now(SEOUL).date()


def ingredient_status(purchased_on, expires_on, today, kind="fridge", rule=None):
    """판정 우선순위 (사용자 결정 2026-09-13, 스펙 14절):
    1. 유통기한(expires_on)이 있으면 그것만 본다: D-3 이내면 urgent, 아니면 ok. 품목 규칙은 쓰지 않는다.
    2. 냉동(freezer) 위치면 품목 규칙을 쓰지 않고 위치 종류 기준(60일).
    3. 그 외 매칭되는 품목 규칙이 있으면 규칙.
    4. 없으면 위치 종류 기준.
    """
    if expires_on is not None:
        return "urgent" if (expires_on - today).days <= URGENT_DAYS else "ok"
    age = (today - purchased_on).days
    if kind != "freezer" and rule is not None:
        warn_days, danger_days = rule
        return "danger" if age >= danger_days else "old" if age >= warn_days else "ok"
    old_days = OLD_DAYS_BY_KIND[kind]
    return "old" if old_days is not None and age >= old_days else "ok"


def matching_rule(name, rules):
    """이름에 키워드가 들어가는 규칙 중 빨강 일수가 가장 짧은 규칙의 (warn_days, danger_days).
    동률이면 노랑 일수, 그다음 id로 결정해 매번 같은 규칙을 고른다."""
    matched = [r for r in rules if keyword_in(r.keyword, name)]
    if not matched:
        return None
    best = min(matched, key=lambda r: (r.danger_days, r.warn_days, r.id))
    return best.warn_days, best.danger_days


def user_rules(user_id):
    return ItemRule.query.filter_by(user_id=user_id).order_by(ItemRule.id).all()


def status_of(item, today, rules):
    return ingredient_status(
        item.purchased_on, item.expires_on, today, item.location.kind, matching_rule(item.name, rules)
    )


def to_json(item, today, rules):
    return {
        "id": item.id,
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "purchased_on": item.purchased_on.isoformat(),
        "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        "status": status_of(item, today, rules),
        "location_id": item.location_id,
        "location_name": item.location.name,
        "location_kind": item.location.kind,
        "days_left": (item.expires_on - today).days if item.expires_on else None,
        "days_since_purchase": (today - item.purchased_on).days,
    }


def _date(value, label):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(400, f"{label}은 YYYY-MM-DD 형식으로 입력해 주세요.")


def parse_fields(data, creating):
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    fields = {}
    if creating or "name" in data:
        fields["name"] = text(data.get("name"), "이름은", 50)
    if creating or "quantity" in data:
        if isinstance(data.get("quantity"), bool):
            abort(400, "수량은 숫자로 입력해 주세요.")
        try:
            quantity = float(data.get("quantity", 1))
        except (TypeError, ValueError):
            abort(400, "수량은 숫자로 입력해 주세요.")
        if not (math.isfinite(quantity) and quantity > 0):
            abort(400, "수량은 0보다 커야 해요.")
        fields["quantity"] = quantity
    if creating or "unit" in data:
        raw = data.get("unit")
        if raw is None or raw == "":
            fields["unit"] = "개"
        elif not isinstance(raw, str):
            abort(400, "단위는 1~10자로 입력해 주세요.")
        elif not raw.strip():
            fields["unit"] = "개"
        else:
            fields["unit"] = text(raw, "단위는", 10)
    if creating or "purchased_on" in data:
        fields["purchased_on"] = _date(data.get("purchased_on"), "구입일")
    if "expires_on" in data:
        value = data["expires_on"]
        fields["expires_on"] = _date(value, "유통기한") if value else None
    if creating or "location_id" in data:
        value = data.get("location_id")
        location = default_location(g.user.id) if creating and value is None else owned_location(value)
        fields["location_id"] = location.id
    return fields


@bp.get("")
@login_required
def list_ingredients():
    today = seoul_today()
    rules = user_rules(g.user.id)
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=g.user.id).all()
    items.sort(
        key=lambda i: (STATUS_RANK[status_of(i, today, rules)], i.expires_on or date.max, i.purchased_on, i.id)
    )
    return jsonify([to_json(i, today, rules) for i in items])


@bp.post("")
@login_required
def create_ingredient():
    item = Ingredient(user_id=g.user.id, **parse_fields(request.get_json(silent=True), creating=True))
    db.session.add(item)
    db.session.commit()
    return jsonify(to_json(item, seoul_today(), user_rules(g.user.id))), 201


@bp.patch("/<int:item_id>")
@login_required
def update_ingredient(item_id):
    item = get_owned_or_404(Ingredient, item_id)
    for key, value in parse_fields(request.get_json(silent=True), creating=False).items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify(to_json(item, seoul_today(), user_rules(g.user.id)))


@bp.delete("/<int:item_id>")
@login_required
def delete_ingredient(item_id):
    db.session.delete(get_owned_or_404(Ingredient, item_id))
    db.session.commit()
    return "", 204
