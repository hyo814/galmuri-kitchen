from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .matching import staple_matches
from .models import Ingredient, Staple, db
from .validation import commit_or_duplicate, text

bp = Blueprint("staples", __name__, url_prefix="/api/staples")

CATEGORY_ORDER = {"조미료": 0, "야채": 1, "기타": 2}
# "가졌던 것만 배너에"(사용자 결정 2026-09-17): 재고에 있으면 in_stock, 없고 한 번이라도 있었으면(had_stock) missing,
# 한 번도 없었으면 unstocked — 배너·장보기 '떨어진 필수품 담기'는 missing만 쓴다(unstocked는 필수품 시트에만 보인다).
STATUS_ORDER = {"missing": 0, "unstocked": 1, "in_stock": 2}


def ingredient_names(user_id):
    return [
        name
        for (name,) in db.session.query(Ingredient.name)
        .filter(Ingredient.user_id == user_id)
        .order_by(Ingredient.id)
        .all()
    ]


def to_json(staple, names):
    matched = next((n for n in names if staple_matches(staple.name, n)), None)
    in_stock = matched is not None
    status = "in_stock" if in_stock else "missing" if staple.had_stock else "unstocked"
    return {
        "id": staple.id,
        "name": staple.name,
        "category": staple.category,
        "in_stock": in_stock,
        "matched_name": matched,
        "status": status,
    }


@bp.get("")
@login_required
def list_staples():
    names = ingredient_names(g.user.id)
    staples = Staple.query.filter_by(user_id=g.user.id).all()
    for staple in staples:
        # 재고에서 처음 발견되면 "가졌던 적 있음"으로 확정한다 — 한 번 켜지면 꺼지지 않는다(배너에서 완전히 빠지지 않게)
        if not staple.had_stock and any(staple_matches(staple.name, n) for n in names):
            staple.had_stock = True
    if db.session.dirty:
        db.session.commit()
    rows = [to_json(s, names) for s in staples]
    rows.sort(
        key=lambda r: (STATUS_ORDER[r["status"]], CATEGORY_ORDER.get(r["category"], len(CATEGORY_ORDER)), r["category"], r["name"])
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
    # 직접 추가는 명시적으로 원한 것이니 곧장 "가졌던 것"으로(기존 동작 유지 — 재고가 없으면 바로 떨어짐으로 보인다)
    staple = Staple(user_id=g.user.id, name=name, category=category, had_stock=True)
    db.session.add(staple)
    commit_or_duplicate("이미 등록된 필수품이에요.")
    return jsonify(to_json(staple, ingredient_names(g.user.id))), 201


@bp.delete("/<int:staple_id>")
@login_required
def delete_staple(staple_id):
    db.session.delete(get_owned_or_404(Staple, staple_id))
    db.session.commit()
    return "", 204
