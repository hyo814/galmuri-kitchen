"""집밥 리포트(스펙 27·29절). 한 달 요리 일기·먹은 기록·버린 재료를 모은다(결정 21~23)."""

from datetime import datetime, time, timedelta, timezone

from flask import Blueprint, g, jsonify, request

from .auth import login_required
from .food_logs import _next_month, month_json, month_start  # 다음 달 1일은 4b-3 것을 그대로(개정 1 P19)
from .ingredients import SEOUL, seoul_today
from .matching import title_key
from .models import CookLog, IngredientRemoval, db

bp = Blueprint("cook_report", __name__, url_prefix="/api")

MAX_DISCARDED_NAMES = 20
TOP_SAVED = 3


def seoul_bounds(first):
    """서울 달 [1일 00:00, 다음 달 1일 00:00)을 UTC 시각 두 개로(결정 21)."""
    start = datetime.combine(first, time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    return start, datetime.combine(_next_month(first), time.min, tzinfo=SEOUL).astimezone(timezone.utc)


def _cooked_in(user_id, first):
    """그 달 요리 일기 조건. cooked_on은 날짜로 비교한다(결정 21)."""
    return CookLog.user_id == user_id, CookLog.cooked_on >= first, CookLog.cooked_on < _next_month(first)


def _discarded_in(user_id, first):
    """그 달 `버렸어요` 기록 조건. created_at은 UTC로 저장돼 서울 달 경계를 UTC로 바꿔 비교한다(결정 21)."""
    start, end = seoul_bounds(first)
    return (
        IngredientRemoval.user_id == user_id, IngredientRemoval.reason == "discarded",
        IngredientRemoval.created_at >= start, IngredientRemoval.created_at < end,
    )


def month_counts(user_id, first):
    """(요리 수, 버린 재료 수) — 지난달 대비 줄용."""
    return CookLog.query.filter(*_cooked_in(user_id, first)).count(), IngredientRemoval.query.filter(*_discarded_in(user_id, first)).count()


def top_saved(logs):
    """결정 23. saved가 있는 일기를 title_key로 묶어 합, 양수만, (합 내림차순, 가장 늦은 cooked_on·id 내림차순) 3개 → [{title(가장 최근 제목), saved}]."""
    sums, latest = {}, {}
    for log in sorted((log for log in logs if log.saved is not None), key=lambda log: (log.cooked_on, log.id)):
        key = title_key(log.title)
        sums[key] = sums.get(key, 0) + log.saved
        latest[key] = log  # 날짜·id 순으로 돌아 마지막이 가장 최근 일기
    ranked = sorted(latest, key=lambda key: (sums[key], latest[key].cooked_on, latest[key].id), reverse=True)
    return [{"title": latest[key].title, "saved": sums[key]} for key in ranked if sums[key] > 0][:TOP_SAVED]


def report_json(user_id, first):
    """→ {month, today, cooked, counted, saved_total, excluded_ingredients, logged_days, home, out, home_percent,
    discarded, discarded_names, discarded_more, top_saved, previous: {cooked, discarded}}
    기록한 날·집밥 비율은 먹은 기록 달력 요약(month_json)을 그대로 쓴다 — 두 화면이 같은 규칙(결정 21, 개정 1 S12).
    ponytail: 한 달 일기·먹은 기록을 파이썬에서 묶는다(요리 일기는 한 달 보통 수십 개) — 느리면 GROUP BY 쿼리로.
    month_json이 사진·kcal까지 읽어 쿼리가 둘 더 들지만 먹은 기록은 하루 20개 상한이라 한 달 620줄까지다."""
    logs = (
        db.session.query(CookLog.id, CookLog.title, CookLog.cooked_on, CookLog.saved, CookLog.excluded_count)
        .filter(*_cooked_in(user_id, first))
        .all()
    )
    counted = [log for log in logs if log.saved is not None]
    names = [
        name for (name,) in db.session.query(IngredientRemoval.name)
        .filter(*_discarded_in(user_id, first))
        .order_by(IngredientRemoval.created_at.desc(), IngredientRemoval.id.desc())
    ]
    unique = list(dict.fromkeys(names))  # 최근 순 그대로 같은 이름만 뺀다
    summary = month_json(user_id, first)["summary"]
    previous_cooked, previous_discarded = month_counts(user_id, (first - timedelta(days=1)).replace(day=1))
    return {
        "month": first.strftime("%Y-%m"), "today": seoul_today().isoformat(),
        "cooked": len(logs), "counted": len(counted),
        "saved_total": sum(log.saved for log in counted),
        "excluded_ingredients": sum(log.excluded_count for log in counted),
        **{key: summary[key] for key in ("logged_days", "home", "out", "home_percent")},
        "discarded": len(names), "discarded_names": unique[:MAX_DISCARDED_NAMES],
        "discarded_more": max(len(unique) - MAX_DISCARDED_NAMES, 0),
        "top_saved": top_saved(logs),
        "previous": {"cooked": previous_cooked, "discarded": previous_discarded},
    }


@bp.get("/cook-report")
@login_required
def month_report():
    res = jsonify(report_json(g.user.id, month_start(request.args.get("month"))))
    res.headers["Cache-Control"] = "no-store"  # 식습관·지출 정보
    return res
