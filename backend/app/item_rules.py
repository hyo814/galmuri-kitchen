from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .models import ItemRule, db
from .validation import commit_or_duplicate, integer, text

bp = Blueprint("item_rules", __name__, url_prefix="/api/item-rules")

MAX_DAYS = 3650


def to_json(rule):
    return {
        "id": rule.id,
        "keyword": rule.keyword,
        "warn_days": rule.warn_days,
        "danger_days": rule.danger_days,
        "source": rule.source,
    }


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    return data


def _keyword(value, exclude_id=None):
    keyword = text(value, "품목 이름은", 20)
    query = ItemRule.query.filter_by(user_id=g.user.id, keyword=keyword)
    if exclude_id is not None:
        query = query.filter(ItemRule.id != exclude_id)
    if query.first():
        abort(400, "이미 있는 품목이에요.")
    return keyword


def _check_order(warn_days, danger_days):
    if danger_days <= warn_days:
        abort(400, "빨강 경고 일수는 노랑보다 커야 해요.")


@bp.get("")
@login_required
def list_rules():
    rules = ItemRule.query.filter_by(user_id=g.user.id).order_by(ItemRule.keyword).all()
    return jsonify([to_json(r) for r in rules])


@bp.post("")
@login_required
def create_rule():
    data = _json_body()
    keyword = _keyword(data.get("keyword"))
    warn_days = integer(data.get("warn_days"), "노랑 경고 일수는", 1, MAX_DAYS)
    danger_days = integer(data.get("danger_days"), "빨강 경고 일수는", 1, MAX_DAYS)
    _check_order(warn_days, danger_days)
    rule = ItemRule(user_id=g.user.id, keyword=keyword, warn_days=warn_days, danger_days=danger_days, source="user")
    db.session.add(rule)
    commit_or_duplicate("이미 있는 품목이에요.")
    return jsonify(to_json(rule)), 201


@bp.patch("/<int:rule_id>")
@login_required
def update_rule(rule_id):
    rule = get_owned_or_404(ItemRule, rule_id)
    data = _json_body()
    keyword = _keyword(data["keyword"], exclude_id=rule.id) if "keyword" in data else rule.keyword
    warn_days = integer(data["warn_days"], "노랑 경고 일수는", 1, MAX_DAYS) if "warn_days" in data else rule.warn_days
    danger_days = (
        integer(data["danger_days"], "빨강 경고 일수는", 1, MAX_DAYS) if "danger_days" in data else rule.danger_days
    )
    _check_order(warn_days, danger_days)
    rule.keyword, rule.warn_days, rule.danger_days, rule.source = keyword, warn_days, danger_days, "user"
    commit_or_duplicate("이미 있는 품목이에요.")
    return jsonify(to_json(rule))


@bp.delete("/<int:rule_id>")
@login_required
def delete_rule(rule_id):
    db.session.delete(get_owned_or_404(ItemRule, rule_id))
    db.session.commit()
    return "", 204
