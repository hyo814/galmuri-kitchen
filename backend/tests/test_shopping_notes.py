import io
import os
from datetime import datetime, timedelta, timezone

from app import shopping
from app.models import ShoppingNote, ShoppingNotePhoto, User, db

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 20
CONFLICT = "다른 기기에서 먼저 고친 메모가 있어요."


def add_note(client, **body):
    return client.post("/api/shopping/notes", json={"body": "세일 수요일까지", **body})


def upload(client, note_id, data=JPEG, **form):
    return client.post(
        f"/api/shopping/notes/{note_id}/photos",
        data={"image": (io.BytesIO(data), "a.jpg"), **form},
        content_type="multipart/form-data",
    )


def ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def photo_path(app, url):
    return os.path.join(app.config["UPLOAD_DIR"], url.removeprefix("/api/photos/"))


def as_user(client, user):
    with client.session_transaction() as s:
        s["user_id"] = user.id
        s["pid"] = user.provider_id  # login_required가 세션 pid를 확인한다


def test_requires_login(client):
    assert client.get("/api/photos/shopping/1/a.jpg").status_code == 401
    assert add_note(client).status_code == 401


def test_create_note_resend_and_validation(client, login):
    login()
    res = add_note(client, place=" 이마트 성수점 ", client_id="n-1")
    assert res.status_code == 201
    note = res.get_json()
    assert (note["place"], note["body"], note["client_id"], note["photos"]) == ("이마트 성수점", "세일 수요일까지", "n-1", [])
    again = add_note(client, body="다른 내용", client_id="n-1")
    assert (again.status_code, again.get_json()["id"]) == (200, note["id"])

    empty = add_note(client, body="", place="  ")
    assert empty.status_code == 201
    assert (empty.get_json()["body"], empty.get_json()["place"]) == ("", None)
    assert add_note(client, body="가" * 2001).get_json() == {"error": "메모는 2000자까지 쓸 수 있어요."}
    assert add_note(client, place="가" * 31).get_json() == {"error": "장소는 30자까지 입력해주세요."}
    for bad in ({"body": 3}, {"place": 3}, {"client_id": "x" * 37}, {"edited_at": "2026-09-14T00:00:00"}, {"body": "a\x00b"}, {"place": "이\x00마트"}):
        res = add_note(client, **bad)
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})


def test_note_cap_20_but_resend_still_200(client, login):
    login()
    for i in range(20):
        assert add_note(client, client_id=f"n-{i}").status_code == 201
    res = add_note(client)
    assert (res.status_code, res.get_json()) == (400, {"error": "메모는 20개까지 둘 수 있어요."})
    assert add_note(client, client_id="n-3").status_code == 200


def test_put_last_save_wins_with_conflict(client, login):
    login()
    note_id = add_note(client, edited_at=ago(5)).get_json()["id"]
    t1, t2, t3 = ago(3), ago(2), ago(1)
    saved = client.put(f"/api/shopping/notes/{note_id}", json={"place": "이마트", "body": "서버", "edited_at": t2})
    assert saved.status_code == 200
    assert datetime.fromisoformat(saved.get_json()["updated_at"]) == datetime.fromisoformat(t2)

    stale = client.put(f"/api/shopping/notes/{note_id}", json={"place": None, "body": "옛 기기", "edited_at": t1})
    assert stale.status_code == 409
    assert stale.get_json()["error"] == CONFLICT
    assert (stale.get_json()["note"]["body"], stale.get_json()["note"]["place"]) == ("서버", "이마트")

    newer = {"place": None, "body": "새 기기", "edited_at": t3}
    for _ in range(2):  # 같은 요청을 다시 보내도 409가 나지 않는다
        res = client.put(f"/api/shopping/notes/{note_id}", json=newer)
        assert res.status_code == 200
        assert (res.get_json()["body"], res.get_json()["place"]) == ("새 기기", None)
        assert datetime.fromisoformat(res.get_json()["updated_at"]) == datetime.fromisoformat(t3)


def test_put_validation_and_future_clamp(client, login):
    login()
    note_id = add_note(client).get_json()["id"]
    url = f"/api/shopping/notes/{note_id}"
    for bad in ({"body": "x"}, {"body": "x", "edited_at": "2026-09-14T00:00:00"}, {"edited_at": ago(0)}):
        assert client.put(url, json=bad).status_code == 400
    assert client.put(url, json={"body": "가" * 2001, "edited_at": ago(0)}).get_json() == {"error": "메모는 2000자까지 쓸 수 있어요."}
    res = client.put(url, json={"body": "\x00", "edited_at": ago(0)})  # PostgreSQL이 받지 않는 글자 → 500 대신 400
    assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    res = client.put(url, json={"body": "미래", "edited_at": future})
    assert datetime.fromisoformat(res.get_json()["updated_at"]) < datetime.now(timezone.utc) + timedelta(minutes=1)
    assert client.put("/api/shopping/notes/999999", json={"body": "x", "edited_at": ago(0)}).status_code == 404


def test_snapshot_includes_notes_newest_first_with_photos(client, login):
    login()
    older = add_note(client, body="옛 메모", edited_at=ago(2)).get_json()
    newer = add_note(client, body="새 메모", edited_at=ago(1)).get_json()
    photo = upload(client, older["id"], client_id="p-1").get_json()
    notes = client.get("/api/shopping").get_json()["notes"]
    assert [n["id"] for n in notes] == [newer["id"], older["id"]]
    assert notes[1]["photos"] == [photo]
    assert set(notes[1]) == {"id", "client_id", "place", "body", "updated_at", "photos"}


def test_upload_photo_serves_to_owner(client, login, app):
    user = login()
    note_id = add_note(client).get_json()["id"]
    res = upload(client, note_id, client_id="p-1")
    assert res.status_code == 201
    photo = res.get_json()
    assert set(photo) == {"id", "client_id", "url"}
    assert photo["client_id"] == "p-1"
    assert photo["url"].startswith(f"/api/photos/shopping/{user.id}/") and photo["url"].endswith(".jpg")
    assert open(photo_path(app, photo["url"]), "rb").read() == JPEG

    got = client.get(photo["url"])
    assert (got.status_code, got.data, got.mimetype) == (200, JPEG, "image/jpeg")
    assert got.headers["X-Content-Type-Options"] == "nosniff"
    assert got.headers["Cache-Control"] == "private, max-age=3600"
    assert got.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"

    again = upload(client, note_id, client_id="p-1")
    assert (again.status_code, again.get_json()) == (200, photo)
    assert len(os.listdir(os.path.dirname(photo_path(app, photo["url"])))) == 1  # 다시 보내도 파일은 하나

    png = upload(client, note_id, data=PNG).get_json()
    assert png["url"].endswith(".png")
    assert client.get(png["url"]).mimetype == "image/png"
    webp = upload(client, note_id, data=WEBP).get_json()
    assert webp["url"].endswith(".webp")
    assert client.get(webp["url"]).mimetype == "image/webp"


def test_polyglot_jpeg_is_served_as_image_only(client, login):
    login()
    note_id = add_note(client).get_json()["id"]
    polyglot = b"\xff\xd8\xff\xe0<html><script>alert(1)</script></html>"
    photo = upload(client, note_id, data=polyglot).get_json()
    got = client.get(photo["url"])
    assert (got.status_code, got.data, got.mimetype) == (200, polyglot, "image/jpeg")
    assert got.headers["X-Content-Type-Options"] == "nosniff"
    assert got.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"


def test_upload_photo_errors(client, login, app, monkeypatch):
    login()
    note_id = add_note(client).get_json()["id"]
    url = f"/api/shopping/notes/{note_id}/photos"
    res = client.post(url, data={}, content_type="multipart/form-data")
    assert (res.status_code, res.get_json()) == (400, {"error": "사진을 올려주세요."})
    assert upload(client, note_id, data=b"").get_json() == {"error": "사진을 올려주세요."}
    res = upload(client, note_id, data=b"%PDF-1.4 fake")
    assert (res.status_code, res.get_json()) == (415, {"error": "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요."})
    assert upload(client, note_id, client_id="x" * 37).status_code == 400
    assert upload(client, note_id, data=b"x" * (10 * 1024 * 1024 + 1)).status_code == 413
    res = upload(client, note_id, data=JPEG[:4] + b"0" * (3 * 1024 * 1024 - 3))  # 한 장 3MB 넘음
    assert (res.status_code, res.get_json()) == (413, {"error": "사진이 너무 커요."})
    assert upload(client, note_id, data=JPEG[:4] + b"0" * (3 * 1024 * 1024 - 4)).status_code == 201
    assert upload(client, 999999).status_code == 404

    for _ in range(9):
        assert upload(client, note_id).status_code == 201
    res = upload(client, note_id)
    assert (res.status_code, res.get_json()) == (400, {"error": "사진은 메모 하나에 10장까지 넣을 수 있어요."})

    app.config["DEV_MODE"] = False  # 운영에서 R2가 없으면
    res = upload(client, note_id)
    assert (res.status_code, res.get_json()) == (503, {"error": "사진을 지금은 올릴 수 없어요."})


def test_user_total_photo_bytes_cap(client, login, monkeypatch):
    login()
    monkeypatch.setattr(shopping, "MAX_USER_PHOTO_BYTES", len(JPEG) * 3)
    first, second = add_note(client).get_json()["id"], add_note(client).get_json()["id"]
    assert upload(client, first).status_code == 201
    assert upload(client, second).status_code == 201  # 메모를 가로질러 센다
    photo = upload(client, second).get_json()
    res = upload(client, first)
    assert (res.status_code, res.get_json()) == (400, {"error": "사진 저장 공간이 가득 찼어요. 오래된 메모 사진을 지워주세요."})
    assert upload(client, second, client_id="none-yet").status_code == 400
    assert client.delete(f"/api/shopping/notes/{second}/photos/{photo['id']}").status_code == 204
    assert upload(client, first).status_code == 201


def test_demo_user_photo_bytes_cap_is_smaller(client, login, app, monkeypatch):
    assert (shopping.MAX_DEMO_PHOTO_BYTES, shopping.MAX_USER_PHOTO_BYTES) == (20 * 1024 * 1024, 200 * 1024 * 1024)
    monkeypatch.setattr(shopping, "MAX_DEMO_PHOTO_BYTES", len(JPEG))
    demo_user = login("demo-1")
    with app.app_context():
        db.session.get(User, demo_user.id).provider = "demo"
        db.session.commit()
    note_id = add_note(client).get_json()["id"]
    assert upload(client, note_id).status_code == 201
    res = upload(client, note_id)
    assert (res.status_code, res.get_json()) == (400, {"error": "사진 저장 공간이 가득 찼어요. 오래된 메모 사진을 지워주세요."})
    login("normal")  # 일반 사용자는 200MB 그대로
    note_id = add_note(client).get_json()["id"]
    assert [upload(client, note_id).status_code for _ in range(2)] == [201, 201]


def test_delete_photo_removes_file(client, login, app):
    login()
    note_id = add_note(client).get_json()["id"]
    photo = upload(client, note_id).get_json()
    assert client.delete(f"/api/shopping/notes/{note_id}/photos/{photo['id']}").status_code == 204
    assert client.get(photo["url"]).status_code == 404
    assert not os.path.exists(photo_path(app, photo["url"]))
    assert client.delete(f"/api/shopping/notes/{note_id}/photos/{photo['id']}").status_code == 404


def test_delete_note_removes_photo_files(client, login, app):
    login()
    note_id = add_note(client).get_json()["id"]
    photos = [upload(client, note_id).get_json() for _ in range(2)]
    assert client.delete(f"/api/shopping/notes/{note_id}").status_code == 204
    assert client.get("/api/shopping").get_json()["notes"] == []
    for photo in photos:
        assert client.get(photo["url"]).status_code == 404
        assert not os.path.exists(photo_path(app, photo["url"]))
    assert client.delete(f"/api/shopping/notes/{note_id}").status_code == 404


def test_other_users_notes_photos_and_keys_are_404(client, login, app):
    owner = login()
    note_id = add_note(client).get_json()["id"]
    photo = upload(client, note_id).get_json()

    intruder = login("other")
    mine_note = add_note(client).get_json()["id"]
    assert client.put(f"/api/shopping/notes/{note_id}", json={"body": "x", "edited_at": ago(0)}).status_code == 404
    assert upload(client, note_id).status_code == 404
    assert client.delete(f"/api/shopping/notes/{note_id}/photos/{photo['id']}").status_code == 404
    assert client.delete(f"/api/shopping/notes/{mine_note}/photos/{photo['id']}").status_code == 404  # 내 메모 id로 남의 사진
    assert client.delete(f"/api/shopping/notes/{note_id}").status_code == 404
    assert client.get(photo["url"]).status_code == 404
    # 내 접두사로 바꿔도 행이 없으면 404, 경로 조작도 404
    key = photo["url"].removeprefix("/api/photos/")
    assert client.get(f"/api/photos/shopping/{intruder.id}/{key.rsplit('/', 1)[1]}").status_code == 404
    name = key.rsplit("/", 1)[1]
    for tricky in (
        f"shopping/{intruder.id}/../{owner.id}/{name}",
        f"shopping/{intruder.id}/%2e%2e%2f{owner.id}/{name}",
        f"shopping/{intruder.id}/%2e%2e/{owner.id}/{name}",
        f"shopping/{intruder.id}/..\\{owner.id}\\{name}",
        f"shopping/{intruder.id}/..%5c{owner.id}%5c{name}",
        f"shopping/{intruder.id}//{owner.id}/{name}",
        f"/shopping/{owner.id}/{name}",
        f"shopping//{owner.id}/{name}",
    ):
        assert client.get(f"/api/photos/{tricky}", follow_redirects=True).status_code == 404, tricky
    assert client.get("/api/shopping").get_json()["notes"][0]["id"] == mine_note

    as_user(client, owner)
    assert client.get(photo["url"]).status_code == 200


def test_user_delete_cascades(client, login, app):
    user = login()
    note_id = add_note(client).get_json()["id"]
    upload(client, note_id)
    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert db.session.get(ShoppingNote, note_id) is None
        assert ShoppingNotePhoto.query.count() == 0


def backdate(app, note_id, hours):
    """만든 시각(서버)·저장 시각을 hours시간 전으로."""
    with app.app_context():
        note = db.session.get(ShoppingNote, note_id)
        note.created_at = note.updated_at = datetime.now(timezone.utc) - timedelta(hours=hours)
        db.session.commit()


def test_snapshot_removes_empty_notes_older_than_a_day(client, login, app):
    owner = login()
    old_empty = add_note(client, body="", place="  ").get_json()["id"]
    old_blank = add_note(client, body=" \n ").get_json()["id"]
    young_empty = add_note(client, body="").get_json()["id"]
    offline_empty = add_note(client, body="", edited_at=ago(48)).get_json()["id"]  # 오프라인에서 이틀 전에 만들어 방금 보낸 메모
    place_only = add_note(client, body="", place="이마트").get_json()["id"]
    body_only = add_note(client, body="  두부 ").get_json()["id"]
    with_photo = add_note(client, body="").get_json()["id"]
    assert upload(client, with_photo).status_code == 201
    for note_id in (old_empty, old_blank, place_only, body_only, with_photo):
        backdate(app, note_id, 25)
    backdate(app, young_empty, 23)

    login("other")
    others_empty = add_note(client, body="").get_json()["id"]
    backdate(app, others_empty, 25)

    as_user(client, owner)
    ids = {n["id"] for n in client.get("/api/shopping").get_json()["notes"]}
    assert ids == {young_empty, offline_empty, place_only, body_only, with_photo}
    with app.app_context():
        assert db.session.get(ShoppingNote, old_empty) is None and db.session.get(ShoppingNote, old_blank) is None
        assert db.session.get(ShoppingNote, others_empty) is not None  # 남의 빈 메모는 그대로
