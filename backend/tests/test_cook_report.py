from datetime import date, datetime, timezone

import pytest

from app.ingredients import SEOUL
from app.models import CookLog, FoodLog, IngredientRemoval, User, db

BAD = "잘못된 요청이에요."
RANGE = "날짜를 다시 확인해주세요."
EMPTY = {
    "cooked": 0, "counted": 0, "saved_total": 0, "excluded_ingredients": 0, "logged_days": 0, "home": 0, "out": 0,
    "home_percent": None, "discarded": 0, "discarded_names": [], "discarded_more": 0, "top_saved": [],
    "previous": {"cooked": 0, "discarded": 0},
}


def get_report(client, month="2026-09"):
    return client.get("/api/cook-report", query_string={} if month is None else {"month": month})


def add_rows(app, *rows):
    with app.app_context():
        db.session.add_all(rows)
        db.session.commit()


def cook(user_id, title, on, saved=None, excluded=0):
    return CookLog(user_id=user_id, title=title, cooked_on=on, servings=1, saved=saved, excluded_count=excluded)


def removal(user_id, name, created_at, reason="discarded"):
    return IngredientRemoval(user_id=user_id, name=name, reason=reason, created_at=created_at)


def seoul(*args):
    """서울 시각 → UTC. SQLite는 시간대를 버리고 벽시계 값만 저장해서 앱처럼 UTC로 넣는다."""
    return datetime(*args, tzinfo=SEOUL).astimezone(timezone.utc)


def other_user(app):
    with app.app_context():
        other = User(provider="test", provider_id="2", nickname="other")
        db.session.add(other)
        db.session.commit()
        return other.id


def test_report_totals(client, login, app):
    uid = login().id
    add_rows(
        app,
        cook(uid, "부대찌개", date(2026, 9, 13), 23100, 0),
        cook(uid, "제육볶음", date(2026, 9, 7), 12400, 2),
        cook(uid, "된장찌개", date(2026, 9, 10), 9800, 1),
        cook(uid, "김치찌개", date(2026, 9, 15), 10820, 1),
        cook(uid, "김치찌개", date(2026, 9, 2), -800, 0),
        cook(uid, "계란말이", date(2026, 9, 12), None, 2),
        cook(uid, "지난달", date(2026, 8, 31), 5000),
        cook(uid, "다음달", date(2026, 10, 1), 5000),
        FoodLog(user_id=uid, eaten_on=date(2026, 9, 1), meal="lunch", place="home"),
        FoodLog(user_id=uid, eaten_on=date(2026, 9, 1), meal="dinner", place="out"),
        FoodLog(user_id=uid, eaten_on=date(2026, 9, 13), meal="dinner", place="home"),
        FoodLog(user_id=uid, eaten_on=date(2026, 9, 20), meal="lunch"),
        removal(uid, "애호박", seoul(2026, 9, 14, 10)),
        removal(uid, "콩나물", seoul(2026, 9, 3, 12)),
        removal(uid, "애호박", seoul(2026, 9, 2, 12)),
        removal(uid, "두부", seoul(2026, 9, 5, 12), reason="eaten"),
        removal(uid, "우유", datetime(2026, 8, 31, 15, 30, tzinfo=timezone.utc)),  # 서울 9/1 00:30
        removal(uid, "양파", datetime(2026, 8, 31, 14, 59, tzinfo=timezone.utc)),  # 서울 8/31 23:59
    )

    res = get_report(client)
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    body = res.get_json()
    assert (body.pop("month"), isinstance(body.pop("today"), str)) == ("2026-09", True)
    assert body == {
        "cooked": 6, "counted": 5, "saved_total": 55320, "excluded_ingredients": 4, "logged_days": 8,
        "home": 2, "out": 1, "home_percent": 67,
        "discarded": 4, "discarded_names": ["애호박", "콩나물", "우유"], "discarded_more": 0,
        "top_saved": [{"title": "부대찌개", "saved": 23100}, {"title": "제육볶음", "saved": 12400}, {"title": "김치찌개", "saved": 10020}],
        "previous": {"cooked": 1, "discarded": 1},
    }


def test_top_saved_positive_and_ties(client, login, app):
    uid = login().id
    add_rows(
        app,
        cook(uid, "B", date(2026, 9, 3), 5000),  # id는 A보다 작아도 날짜가 늦어 먼저
        cook(uid, "A", date(2026, 9, 1), 5000),
        cook(uid, "C", date(2026, 9, 4), -100),
        cook(uid, "D", date(2026, 9, 5), 0),
    )
    assert get_report(client).get_json()["top_saved"] == [{"title": "B", "saved": 5000}, {"title": "A", "saved": 5000}]

    add_rows(app, cook(uid, "계란 말이", date(2026, 9, 6), 4000), cook(uid, "달걀말이", date(2026, 9, 8), 3000))
    assert get_report(client).get_json()["top_saved"] == [
        {"title": "달걀말이", "saved": 7000}, {"title": "B", "saved": 5000}, {"title": "A", "saved": 5000},
    ]


def test_discarded_names_cap(client, login, app):
    uid = login().id
    add_rows(app, *(removal(uid, f"재료{i:02d}", seoul(2026, 9, 1, 12, i)) for i in range(23)))
    body = get_report(client).get_json()
    assert body["discarded"] == 23
    assert body["discarded_names"] == [f"재료{i:02d}" for i in range(22, 2, -1)]
    assert body["discarded_more"] == 3


def test_empty_and_other_users(client, login, app):
    login()
    other = other_user(app)
    add_rows(
        app,
        cook(other, "김치찌개", date(2026, 9, 2), 5000, 1),
        cook(other, "김치찌개", date(2026, 8, 2), 5000),
        FoodLog(user_id=other, eaten_on=date(2026, 9, 1), meal="lunch", place="home"),
        removal(other, "애호박", seoul(2026, 9, 3, 12)),
        removal(other, "콩나물", seoul(2026, 8, 3, 12)),
    )
    body = get_report(client).get_json()
    assert {k: v for k, v in body.items() if k not in ("month", "today")} == EMPTY


@pytest.mark.parametrize("month, expected", [
    (None, BAD), ("2026-9", BAD), ("2026-13", BAD), ("2026-09-01", BAD), ("1999-12", RANGE),
])
def test_month_validation(client, login, month, expected):
    login()
    res = get_report(client, month)
    assert (res.status_code, res.get_json()["error"]) == (400, expected)


def test_requires_login(client):
    assert get_report(client).status_code == 401


def test_previous_crosses_year(client, login, app):
    uid = login().id
    add_rows(app, cook(uid, "떡국", date(2025, 12, 31)), removal(uid, "파", seoul(2025, 12, 31, 23, 59)))
    body = get_report(client, "2026-01").get_json()
    assert (body["cooked"], body["previous"]) == (0, {"cooked": 1, "discarded": 1})
