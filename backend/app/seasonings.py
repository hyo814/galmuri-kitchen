from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .models import Seasoning, db
from .validation import commit_or_duplicate, iso_datetime, text

# 사용자 "내 비율"만 저장한다(스펙 22절). 계산은 전부 화면(frontend/src/seasoning.ts)에서 한다.
# ponytail: 기본 양념을 고치는 것은 화면이 기본 양념 내용을 폼에 채워 POST(복사)로 한다(`이 비율 고쳐서 내 비율로`). 서버에 기본 양념 행·숨기기가 없다.
bp = Blueprint("seasonings", __name__, url_prefix="/api/seasonings")

MAX_SEASONINGS_PER_USER = 100
MAX_ITEMS = 30
MIN_AMOUNT = 0.01  # 5e-324 같은 값이 계산 화면에서 0·약간으로 무너지지 않게
MAX_AMOUNT = 10000  # 화면 parseAmountInput 상한과 같다
UNITS = ("큰술", "작은술", "컵", "ml", "g", "개", "꼬집")
BASIS_UNITS = {"main_weight": ("g",), "servings": ("인분",), "yield": ("컵", "ml")}
DUPLICATE_ERROR = "같은 이름의 비율이 있어요."


def _amount(value):
    """bool이 아닌 MIN_AMOUNT~MAX_AMOUNT 숫자면 그대로, 아니면 None. NaN·Infinity는 비교에서 걸러진다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_AMOUNT <= value <= MAX_AMOUNT:
        return None
    return value


def _items(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ITEMS:
        abort(400, f"양념을 1~{MAX_ITEMS}개 입력해주세요.")
    rows = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            abort(400, "잘못된 요청이에요.")
        name = text(item.get("name"), f"{index}번째 양념 이름은", 30)
        amount = _amount(item.get("amount"))
        if amount is None:
            abort(400, f"{index}번째 양념 양을 다시 확인해주세요.")
        if item.get("unit") not in UNITS:
            abort(400, f"{index}번째 양념 단위를 다시 골라주세요.")
        rows.append({"name": name, "amount": amount, "unit": item["unit"]})
    return rows


def parse_seasoning(data):
    """생성·수정(PUT) 공통, 전체 교체."""
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    name = text(data.get("name"), "이름은", 30)
    basis, basis_unit = data.get("basis"), data.get("basis_unit")
    if not isinstance(basis, str) or basis_unit not in BASIS_UNITS.get(basis, ()):
        abort(400, "기준을 다시 확인해주세요.")
    basis_amount = _amount(data.get("basis_amount"))
    if basis_amount is None or (basis == "servings" and not (basis_amount <= 20 and basis_amount % 1 == 0)):
        abort(400, "기준 양을 다시 확인해주세요.")
    main_ingredient = data.get("main_ingredient") if basis == "main_weight" else None  # 다른 기준이면 보지도 저장하지도 않는다
    if main_ingredient is not None and (not isinstance(main_ingredient, str) or len(main_ingredient.strip()) > 50):
        abort(400, "주재료는 50자까지 입력해주세요.")
    return {
        "name": name,
        "basis": basis,
        "basis_amount": basis_amount,
        "basis_unit": basis_unit,
        "main_ingredient": (main_ingredient.strip() or None) if main_ingredient else None,
        "items": _items(data.get("items")),
    }


def seasoning_json(s):
    return {
        "id": s.id,
        "name": s.name,
        "basis": s.basis,
        "basis_amount": s.basis_amount,
        "basis_unit": s.basis_unit,
        "main_ingredient": s.main_ingredient,
        "items": s.items,
        "source": "user",
        "source_note": None,
        "updated_at": iso_datetime(s.updated_at),
    }


@bp.get("")
@login_required
def list_seasonings():
    """updated_at·id 내림차순. 사용자당 100개라 페이지 없음(스펙 26절)."""
    rows = Seasoning.query.filter_by(user_id=g.user.id).order_by(Seasoning.updated_at.desc(), Seasoning.id.desc()).all()
    return jsonify(items=[seasoning_json(s) for s in rows])


@bp.post("")
@login_required
def create_seasoning():
    fields = parse_seasoning(request.get_json(silent=True))
    # ponytail: 세고 넣기라 동시에 들어온 POST 두 개가 101개를 만들 수 있다. 문제가 되면 사용자별 잠금(SELECT … FOR UPDATE)으로.
    if Seasoning.query.filter_by(user_id=g.user.id).count() >= MAX_SEASONINGS_PER_USER:
        abort(400, f"양념 비율은 {MAX_SEASONINGS_PER_USER}개까지 저장할 수 있어요.")
    seasoning = Seasoning(user_id=g.user.id, **fields)
    db.session.add(seasoning)
    commit_or_duplicate(DUPLICATE_ERROR)
    return jsonify(seasoning_json(seasoning)), 201


@bp.get("/<int:seasoning_id>")
@login_required
def get_seasoning(seasoning_id):
    return jsonify(seasoning_json(get_owned_or_404(Seasoning, seasoning_id)))


@bp.put("/<int:seasoning_id>")
@login_required
def update_seasoning(seasoning_id):
    seasoning = get_owned_or_404(Seasoning, seasoning_id)
    for key, value in parse_seasoning(request.get_json(silent=True)).items():
        setattr(seasoning, key, value)
    commit_or_duplicate(DUPLICATE_ERROR)  # 내용이 똑같은 PUT은 바뀐 칸이 없어 updated_at도 그대로다(목록 순서 유지)
    return jsonify(seasoning_json(seasoning))


@bp.delete("/<int:seasoning_id>")
@login_required
def delete_seasoning(seasoning_id):
    db.session.delete(get_owned_or_404(Seasoning, seasoning_id))
    db.session.commit()
    return "", 204
