"""우리 집 비법(스펙 18-B). 한 줄짜리 요령을 적어 두면 AI 레시피를 만들 때 함께 넘긴다(recipe_ai.py)."""

from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .models import CookingTip, db
from .validation import text

bp = Blueprint("cooking_tips", __name__, url_prefix="/api/cooking-tips")

MAX_TIPS = 30  # 사용자당. AI 프롬프트에 통째로 들어가므로 무한정 늘리지 않는다
MAX_LENGTH = 100  # models.CookingTip.body와 같다


def to_json(tip):
    return {"id": tip.id, "body": tip.body}


def user_tips(user_id, limit=MAX_TIPS):
    """오래 적은 순. AI 프롬프트도 이 순서를 쓴다."""
    return CookingTip.query.filter_by(user_id=user_id).order_by(CookingTip.id).limit(limit).all()


@bp.get("")
@login_required
def list_tips():
    return jsonify([to_json(tip) for tip in user_tips(g.user.id)])


@bp.post("")
@login_required
def create_tip():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    body = text(data.get("body"), "비법은", MAX_LENGTH)
    if CookingTip.query.filter_by(user_id=g.user.id).count() >= MAX_TIPS:
        abort(400, f"비법은 {MAX_TIPS}개까지 적을 수 있어요.")
    tip = CookingTip(user_id=g.user.id, body=body)
    db.session.add(tip)
    db.session.commit()
    return jsonify(to_json(tip)), 201


@bp.patch("/<int:tip_id>")
@login_required
def update_tip(tip_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    tip = get_owned_or_404(CookingTip, tip_id)
    tip.body = text(data.get("body"), "비법은", MAX_LENGTH)
    db.session.commit()
    return jsonify(to_json(tip))


@bp.delete("/<int:tip_id>")
@login_required
def delete_tip(tip_id):
    db.session.delete(get_owned_or_404(CookingTip, tip_id))
    db.session.commit()
    return "", 204
