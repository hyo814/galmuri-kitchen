from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .matching import names_match
from .models import Ingredient, Staple, db
from .validation import commit_or_duplicate, text

bp = Blueprint("staples", __name__, url_prefix="/api/staples")

CATEGORY_ORDER = {"조미료": 0, "야채": 1, "기타": 2}


def ingredient_names(user_id):
    return [name for (name,) in db.session.query(Ingredient.name).filter(Ingredient.user_id == user_id).all()]


def to_json(staple, names):
    matched = next((n for n in names if names_match(staple.name, n)), None)
    return {
        "id": staple.id,
        "name": staple.name,
        "category": staple.category,
        "in_stock": matched is not None,
        "matched_name": matched,
    }


@bp.get("")
@login_required
def list_staples():
    names = ingredient_names(g.user.id)
    rows = [to_json(s, names) for s in Staple.query.filter_by(user_id=g.user.id).all()]
    rows.sort(
        key=lambda r: (r["in_stock"], CATEGORY_ORDER.get(r["category"], len(CATEGORY_ORDER)), r["category"], r["name"])
    )
    return jsonify(rows)


@bp.post("")
@login_required
def create_staple():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    name = text(data.get("name"), "필수품 이름은", 50)
    category = text(data.get("category", "기타"), "분류는", 10)
    if Staple.query.filter_by(user_id=g.user.id, name=name).first():
        abort(400, "이미 등록된 필수품이에요.")
    staple = Staple(user_id=g.user.id, name=name, category=category)
    db.session.add(staple)
    commit_or_duplicate("이미 등록된 필수품이에요.")
    return jsonify(to_json(staple, ingredient_names(g.user.id))), 201


@bp.delete("/<int:staple_id>")
@login_required
def delete_staple(staple_id):
    db.session.delete(get_owned_or_404(Staple, staple_id))
    db.session.commit()
    return "", 204
