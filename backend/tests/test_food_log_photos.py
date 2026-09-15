import io
import os
from datetime import date, datetime, timezone

import pytest

from app import photos
from app.models import FoodLog, FoodLogPhoto, User, db
from tests.test_food_logs import get_day, post_log
from tests.test_shopping_notes import JPEG, PNG, add_note, as_user, photo_path
from tests.test_shopping_notes import upload as upload_note_photo

FULL = "사진 저장 공간이 가득 찼어요. 오래된 기록 사진을 지워주세요."


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("app.food_logs.seoul_today", lambda: date(2026, 9, 15))


def upload(client, log_id, data=JPEG):
    return client.post(
        f"/api/food-logs/{log_id}/photos", data={"image": (io.BytesIO(data), "a.jpg")}, content_type="multipart/form-data"
    )


def photo_first(client, data=JPEG):
    return client.post("/api/food-logs/photo", data={"image": (io.BytesIO(data), "a.jpg")}, content_type="multipart/form-data")


def new_log(client):
    return post_log(client, title="토스트").get_json()


def error(res):
    return res.status_code, res.get_json()["error"]


def stored_files(app):
    root = os.path.join(app.config["UPLOAD_DIR"], "foodlog")
    return [name for _, _, names in os.walk(root) for name in names]


def at(value):
    return lambda: datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_upload_serves_to_owner_only(client, login, app):
    user = login()
    log = new_log(client)
    res = upload(client, log["id"])
    assert res.status_code == 201
    photo = res.get_json()
    assert photo["url"].startswith(f"/api/photos/foodlog/{user.id}/") and photo["url"].endswith(".jpg")
    with open(photo_path(app, photo["url"]), "rb") as f:
        assert f.read() == JPEG
    got = client.get(photo["url"])
    assert (got.status_code, got.mimetype) == (200, "image/jpeg")
    assert got.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert got.headers["Cache-Control"] == "private, max-age=3600"

    png = upload(client, log["id"], data=PNG).get_json()
    assert png["url"].endswith(".png")
    assert get_day(client).get_json()["logs"][0]["photos"] == [photo, png]
    assert photo["id"] < png["id"]

    login("other")
    assert client.get(photo["url"]).status_code == 404
    assert upload(client, log["id"]).status_code == 404


def test_upload_errors(client, login, app, raw_client):
    login()
    log_id = new_log(client)["id"]
    url = f"/api/food-logs/{log_id}/photos"
    assert error(client.post(url, data={}, content_type="multipart/form-data")) == (400, "사진을 올려주세요.")
    assert error(upload(client, log_id, data=b"")) == (400, "사진을 올려주세요.")
    assert error(upload(client, log_id, data=JPEG[:4] + b"0" * (3 * 1024 * 1024 - 3))) == (413, "사진이 너무 커요.")
    assert error(upload(client, log_id, data=b"hello")) == (415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
    assert raw_client.post(url, data={"image": (io.BytesIO(JPEG), "a.jpg")}, content_type="multipart/form-data").status_code == 400
    assert upload(client, 2**31).status_code == 404
    assert stored_files(app) == []
    with app.app_context():
        assert FoodLogPhoto.query.count() == 0

    for _ in range(4):
        assert upload(client, log_id).status_code == 201
    assert error(upload(client, log_id)) == (400, "사진은 기록 하나에 4장까지 넣을 수 있어요.")
    assert len(stored_files(app)) == 4

    app.config["DEV_MODE"] = False  # 운영에서 R2가 없으면
    assert error(upload(client, log_id)) == (503, "사진을 지금은 올릴 수 없어요.")


def test_photo_bytes_caps(client, login, app, monkeypatch):
    login()
    note_id = add_note(client).get_json()["id"]
    assert [upload_note_photo(client, note_id).status_code for _ in range(2)] == [201, 201]  # 메모 사진은 따로 센다
    monkeypatch.setattr("app.food_logs.MAX_USER_PHOTO_BYTES", len(JPEG) * 2)
    first, second = new_log(client)["id"], new_log(client)["id"]
    assert upload(client, first).status_code == 201
    assert upload(client, second).status_code == 201  # 기록을 가로질러 센다
    assert error(upload(client, first)) == (400, FULL)
    assert error(photo_first(client)) == (400, FULL)

    monkeypatch.setattr("app.food_logs.MAX_DEMO_PHOTO_BYTES", len(JPEG))
    demo_user = login("demo-1")
    with app.app_context():
        db.session.get(User, demo_user.id).provider = "demo"
        db.session.commit()
    log_id = new_log(client)["id"]
    assert upload(client, log_id).status_code == 201
    assert error(upload(client, log_id)) == (400, FULL)


def test_delete_photo_and_log_remove_files(client, login, app):
    owner = login()
    log_id, other_id = new_log(client)["id"], new_log(client)["id"]
    photo = upload(client, log_id).get_json()
    assert client.delete(f"/api/food-logs/{log_id}/photos/{photo['id']}").status_code == 204
    assert not os.path.exists(photo_path(app, photo["url"]))
    assert client.get(photo["url"]).status_code == 404
    assert client.delete(f"/api/food-logs/{log_id}/photos/{photo['id']}").status_code == 404
    assert client.delete(f"/api/food-logs/{log_id}/photos/{2**31}").status_code == 404

    others = [upload(client, other_id).get_json() for _ in range(2)]
    assert client.delete(f"/api/food-logs/{log_id}/photos/{others[0]['id']}").status_code == 404  # 다른 기록의 사진 id
    login("intruder")
    assert client.delete(f"/api/food-logs/{other_id}/photos/{others[0]['id']}").status_code == 404
    assert client.delete(f"/api/food-logs/{other_id}").status_code == 404
    as_user(client, owner)
    assert client.delete(f"/api/food-logs/{other_id}").status_code == 204
    for p in others:
        assert not os.path.exists(photo_path(app, p["url"]))
    with app.app_context():
        assert FoodLogPhoto.query.count() == 0


MOMENTS = [
    ("2026-09-14T21:30", "breakfast", "2026-09-15"),
    ("2026-09-15T01:00", "lunch", "2026-09-15"),
    ("2026-09-15T05:59", "lunch", "2026-09-15"),
    ("2026-09-15T06:00", "dinner", "2026-09-15"),
    ("2026-09-15T11:59", "dinner", "2026-09-15"),
    ("2026-09-15T12:00", "snack", "2026-09-15"),
    ("2026-09-14T19:59", "snack", "2026-09-15"),
]


@pytest.mark.parametrize(("moment", "meal", "day"), MOMENTS)
def test_photo_first_meal_by_seoul_time(client, login, monkeypatch, moment, meal, day):
    login()
    monkeypatch.setattr("app.food_logs.utcnow", at(moment))
    res = photo_first(client)
    assert res.status_code == 201
    log = res.get_json()
    assert (log["meal"], log["eaten_on"], log["title"], log["source"], log["nutrition"]) == (meal, day, None, "manual", None)
    assert len(log["photos"]) == 1
    assert get_day(client, day).get_json()["logs"][0]["photos"] == log["photos"]


def test_photo_first_errors_leave_nothing(client, login, app, monkeypatch):
    login()
    monkeypatch.setattr("app.food_logs.utcnow", at("2026-09-15T01:00"))
    assert error(photo_first(client, data=b"hello")) == (415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
    with app.app_context():
        assert FoodLog.query.count() == 0

    for _ in range(20):
        assert post_log(client, title="밥", eaten_on="2026-09-15").status_code == 201
    assert error(photo_first(client)) == (400, "하루에 20개까지 남길 수 있어요.")
    assert stored_files(app) == []
    with app.app_context():
        assert FoodLog.query.count() == 20

    app.config["DEV_MODE"] = False
    assert error(photo_first(client)) == (503, "사진을 지금은 올릴 수 없어요.")


def test_photo_owner_check_keeps_shopping(client, login, app):
    user = login()
    note_photo = upload_note_photo(client, add_note(client).get_json()["id"]).get_json()
    log_photo = upload(client, new_log(client)["id"]).get_json()
    with app.app_context():
        keys = photos.user_photo_keys([user.id])
    assert sorted(keys) == sorted(p["url"].removeprefix("/api/photos/") for p in (note_photo, log_photo))
