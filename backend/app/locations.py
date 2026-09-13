from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import func

from .auth import get_owned_or_404, login_required
from .models import Ingredient, StorageLocation, db
from .validation import commit_or_duplicate, text

bp = Blueprint("locations", __name__, url_prefix="/api/locations")

KINDS = ("fridge", "freezer", "room")
INVALID_LOCATION = "보관 위치를 다시 선택해 주세요."


def user_locations(user_id):
    return (
        StorageLocation.query.filter_by(user_id=user_id)
        .order_by(StorageLocation.sort_order, StorageLocation.id)
        .all()
    )


def choose_location(locations, value):
    """미리 불러온 내 위치 목록에서 고른다. value가 None이면 첫 냉장(fridge) 위치, 없으면 첫 위치."""
    if not locations:
        abort(400, "보관 위치를 먼저 만들어 주세요.")
    if value is None:
        return next((l for l in locations if l.kind == "fridge"), locations[0])
    location = next((l for l in locations if not isinstance(value, bool) and l.id == value), None)
    if location is None:
        abort(400, INVALID_LOCATION)
    return location


def default_location(user_id):
    return choose_location(user_locations(user_id), None)


def owned_location(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2**31 - 1:
        abort(400, INVALID_LOCATION)
    location = db.session.get(StorageLocation, value)
    if location is None or location.user_id != g.user.id:
        abort(400, INVALID_LOCATION)
    return location


def item_counts(user_id):
    rows = (
        db.session.query(Ingredient.location_id, func.count(Ingredient.id))
        .filter(Ingredient.user_id == user_id)
        .group_by(Ingredient.location_id)
        .all()
    )
    return dict(rows)


def to_json(location, count):
    return {"id": location.id, "name": location.name, "kind": location.kind, "item_count": count}


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    return data


def _kind(value):
    if value not in KINDS:
        abort(400, "보관 종류를 냉장·냉동·실온 중에서 골라 주세요.")
    return value


def _unique_name(value, exclude_id=None):
    name = text(value, "위치 이름은", 20)
    query = StorageLocation.query.filter_by(user_id=g.user.id, name=name)
    if exclude_id is not None:
        query = query.filter(StorageLocation.id != exclude_id)
    if query.first():
        abort(400, "이미 있는 위치 이름이에요.")
    return name


@bp.get("")
@login_required
def list_locations():
    counts = item_counts(g.user.id)
    return jsonify([to_json(l, counts.get(l.id, 0)) for l in user_locations(g.user.id)])


@bp.post("")
@login_required
def create_location():
    data = _json_body()
    name = _unique_name(data.get("name"))
    kind = _kind(data.get("kind"))
    last = db.session.query(func.max(StorageLocation.sort_order)).filter(StorageLocation.user_id == g.user.id).scalar()
    location = StorageLocation(
        user_id=g.user.id, name=name, kind=kind, sort_order=0 if last is None else last + 1
    )
    db.session.add(location)
    commit_or_duplicate("이미 있는 위치 이름이에요.")
    return jsonify(to_json(location, 0)), 201


@bp.patch("/<int:location_id>")
@login_required
def update_location(location_id):
    location = get_owned_or_404(StorageLocation, location_id)
    data = _json_body()
    if "name" in data:
        location.name = _unique_name(data["name"], exclude_id=location.id)
    if "kind" in data:
        location.kind = _kind(data["kind"])
    commit_or_duplicate("이미 있는 위치 이름이에요.")
    return jsonify(to_json(location, item_counts(g.user.id).get(location.id, 0)))


@bp.delete("/<int:location_id>")
@login_required
def delete_location(location_id):
    location = get_owned_or_404(StorageLocation, location_id)
    if Ingredient.query.filter_by(location_id=location.id).first():
        abort(400, "이 위치에 있는 재료를 먼저 옮겨 주세요.")
    if StorageLocation.query.filter_by(user_id=g.user.id).count() <= 1:
        abort(400, "위치는 하나 이상 있어야 해요.")
    db.session.delete(location)
    db.session.commit()
    return "", 204
