from datetime import date, datetime, timezone

import pytest

from app.models import CookLog, FoodLog, FoodLogPhoto, User, db

BAD = "잘못된 요청이에요."
RANGE = "날짜를 다시 확인해주세요."


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("app.food_logs.seoul_today", lambda: date(2026, 9, 15))


def get_month(client, month="2026-09"):
    return client.get("/api/food-logs/month", query_string={} if month is None else {"month": month})


def error(res):
    return res.status_code, res.get_json()["error"]


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def add_log(app, user_id, eaten_on, meal, **kwargs):
    with app.app_context():
        log = FoodLog(user_id=user_id, eaten_on=eaten_on, meal=meal, source="manual", **kwargs)
        db.session.add(log)
        db.session.commit()
        return log.id


def add_photo(app, log_id, key, size=1):
    with app.app_context():
        db.session.add(FoodLogPhoto(log_id=log_id, photo_key=key, size=size))
        db.session.commit()


def test_month_days_and_summary(client, login, app):
    user = login()
    uid = user.id
    add_log(app, uid, date(2026, 9, 1), "breakfast", kcal=700, place="home")
    add_log(app, uid, date(2026, 9, 1), "lunch", kcal=720, place="home")
    dinner_id = add_log(app, uid, date(2026, 9, 2), "dinner", kcal=1780, approx=True, place="out")
    add_photo(app, dinner_id, f"foodlog/{uid}/b.jpg")  # 먼저 올려서 id가 작다 → 첫 사진
    add_photo(app, dinner_id, f"foodlog/{uid}/z.jpg")
    lunch3_id = add_log(app, uid, date(2026, 9, 3), "lunch")
    add_photo(app, lunch3_id, f"foodlog/{uid}/c.jpg")
    add_log(app, uid, date(2026, 8, 31), "dinner", kcal=500)
    add_log(app, uid, date(2026, 10, 1), "breakfast", kcal=500)

    body = get_month(client).get_json()
    assert [d["date"] for d in body["days"]] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert isinstance(body["today"], str)

    day1, day2, day3 = body["days"]
    assert {k: day1[k] for k in ("meals", "count", "kcal", "approx", "photo_url", "cooked")} == {
        "meals": 2, "count": 2, "kcal": 1420, "approx": False, "photo_url": None, "cooked": False,
    }
    assert day2["photo_url"] == f"/api/photos/foodlog/{uid}/b.jpg"
    assert day2["approx"] is True
    assert (day3["kcal"], day3["approx"], day3["meals"]) == (None, False, 1)
    assert day3["photo_url"] == f"/api/photos/foodlog/{uid}/c.jpg"

    assert body["summary"] == {
        "logged_days": 3, "avg_kcal": 1600, "avg_approx": True, "home": 2, "out": 1, "home_percent": 67,
    }


def test_first_photo_follows_meal_order(client, login, app):
    user = login()
    uid = user.id
    dinner_id = add_log(app, uid, date(2026, 9, 5), "dinner", created_at=at("2026-09-05T09:00:00"))
    add_photo(app, dinner_id, f"foodlog/{uid}/x.jpg")
    lunch_id = add_log(app, uid, date(2026, 9, 5), "lunch", created_at=at("2026-09-05T12:00:00"))
    add_photo(app, lunch_id, f"foodlog/{uid}/y.jpg")
    add_log(app, uid, date(2026, 9, 5), "breakfast", created_at=at("2026-09-05T06:00:00"))

    body = get_month(client).get_json()
    assert body["days"][0]["photo_url"] == f"/api/photos/foodlog/{uid}/y.jpg"


def add_cook(app, user_id, cooked_on, photo_key=None):
    with app.app_context():
        db.session.add(CookLog(user_id=user_id, title="김치찌개", cooked_on=cooked_on, servings=1, photo_key=photo_key))
        db.session.commit()


def test_month_marks_cook_days(client, login, app):
    uid = login().id
    add_log(app, uid, date(2026, 9, 2), "lunch")
    add_cook(app, uid, date(2026, 9, 2))  # 사진 없는 일기가 먼저여도 사진이 있는 첫 일기를 쓴다
    add_cook(app, uid, date(2026, 9, 2), f"cooklog/{uid}/k.jpg")
    add_cook(app, uid, date(2026, 9, 5))
    add_cook(app, uid, date(2026, 8, 31), f"cooklog/{uid}/p.jpg")
    add_cook(app, uid, date(2026, 10, 1), f"cooklog/{uid}/n.jpg")

    body = get_month(client).get_json()
    assert [d["date"] for d in body["days"]] == ["2026-09-02", "2026-09-05"]
    day2, day5 = body["days"]
    assert (day2["cooked"], day2["photo_url"], day2["meals"]) == (True, f"/api/photos/cooklog/{uid}/k.jpg", 1)
    assert day5 == {"date": "2026-09-05", "meals": 0, "count": 0, "kcal": None, "approx": False, "photo_url": None, "cooked": True}
    assert body["summary"]["logged_days"] == 2

    photo_log = add_log(app, uid, date(2026, 9, 7), "lunch")
    add_photo(app, photo_log, f"foodlog/{uid}/f.jpg")
    add_cook(app, uid, date(2026, 9, 7), f"cooklog/{uid}/m.jpg")
    days = get_month(client).get_json()["days"]
    assert [d["date"] for d in days] == ["2026-09-02", "2026-09-05", "2026-09-07"]  # 요리만 있는 날도 날짜 순
    assert (days[2]["cooked"], days[2]["photo_url"]) == (True, f"/api/photos/foodlog/{uid}/f.jpg")  # 먹은 기록 사진이 먼저


def test_same_meal_counts_once_for_dots(client, login, app):
    user = login()
    uid = user.id
    add_log(app, uid, date(2026, 9, 7), "lunch", title="밥1")
    add_log(app, uid, date(2026, 9, 7), "lunch", title="밥2")
    add_log(app, uid, date(2026, 9, 7), "lunch", title="밥3")

    day = get_month(client).get_json()["days"][0]
    assert (day["meals"], day["count"]) == (1, 3)


def test_empty_month_and_other_users(client, login, app):
    login()
    with app.app_context():
        other = User(provider="test", provider_id="2", nickname="other")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    add_log(app, other_id, date(2026, 9, 3), "lunch", kcal=400, place="home")
    add_cook(app, other_id, date(2026, 9, 4))

    body = get_month(client).get_json()
    assert body == {
        "month": "2026-09", "today": body["today"], "days": [],
        "summary": {"logged_days": 0, "avg_kcal": None, "avg_approx": False, "home": 0, "out": 0, "home_percent": None},
    }


@pytest.mark.parametrize("month", [None, "2026-9", "2026-13", "abcd-ef", "2026-09-01"])
def test_month_validation_bad_request(client, login, month):
    login()
    assert error(get_month(client, month)) == (400, BAD)


@pytest.mark.parametrize("month", ["1999-12", "2101-01"])
def test_month_validation_out_of_range(client, login, month):
    login()
    assert error(get_month(client, month)) == (400, RANGE)


def test_requires_login(client):
    assert get_month(client).status_code == 401


def test_cache_control_no_store(client, login):
    login()
    assert get_month(client).headers["Cache-Control"] == "no-store"
