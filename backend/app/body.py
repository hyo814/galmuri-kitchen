import math

from flask import Blueprint, abort, g, jsonify, request

from .auth import login_required
from .ingredients import seoul_today
from .models import BodyProfile, db
from .validation import commit_or_duplicate, integer, iso_datetime

# 몸 정보(스펙 21절, 4b-2). 하루 목표 kcal 자체는 저장하지 않고 화면이 계산한다(결정 2, src/nutrition/body.ts).
bp = Blueprint("body", __name__, url_prefix="/api")

SEXES = ("female", "male")
ACTIVITIES = ("sedentary", "light", "moderate", "active", "very_active")
GOALS = ("maintain", "lose", "gain")
MIN_AGE, MAX_AGE = 20, 99  # 연 나이. Mifflin–St Jeor는 성인 공식(결정 1)
SAVE_RACE = "방금 저장했어요. 다시 불러와주세요."


def _number(value, label, lo, hi):
    """bool이 아닌 lo~hi 숫자, 소수 첫째 자리로 반올림."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        abort(400, f"{label} {lo}~{hi} 사이 숫자로 입력해주세요.")
    return round(float(value), 1)


def profile_json(profile):
    return {
        "sex": profile.sex, "birth_year": profile.birth_year, "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg, "activity": profile.activity, "goal": profile.goal,
        "updated_at": iso_datetime(profile.updated_at),
    }


def _my_profile():
    return BodyProfile.query.filter_by(user_id=g.user.id).first()


@bp.get("/body-profile")
@login_required
def get_body_profile():
    profile = _my_profile()
    res = jsonify(profile=profile_json(profile) if profile else None)
    res.headers["Cache-Control"] = "no-store"  # 건강 정보
    return res


@bp.put("/body-profile")
@login_required
def put_body_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    sex = data.get("sex")
    if sex not in SEXES:
        abort(400, "성별을 골라주세요.")
    this_year = seoul_today().year
    birth_year = integer(data.get("birth_year"), "태어난 해는", this_year - MAX_AGE, this_year - MIN_AGE)
    height_cm = _number(data.get("height_cm"), "키는", 120, 230)
    weight_kg = _number(data.get("weight_kg"), "몸무게는", 30, 250)
    activity = data.get("activity")
    if activity not in ACTIVITIES:
        abort(400, "활동량을 골라주세요.")
    goal = data.get("goal")
    if goal not in GOALS:
        abort(400, "목표를 골라주세요.")

    profile = _my_profile()
    if profile is None:
        profile = BodyProfile(user_id=g.user.id)
        db.session.add(profile)
    profile.sex, profile.birth_year = sex, birth_year
    profile.height_cm, profile.weight_kg = height_cm, weight_kg
    profile.activity, profile.goal = activity, goal
    commit_or_duplicate(SAVE_RACE)  # 처음 저장이 동시에 두 번 오면 UNIQUE(user_id) 충돌
    return jsonify(profile=profile_json(profile))


@bp.delete("/body-profile")
@login_required
def delete_body_profile():
    profile = _my_profile()
    if profile is not None:
        db.session.delete(profile)
        db.session.commit()
    return "", 204
