import io
import os

import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from werkzeug.exceptions import HTTPException

from app import storage

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20


def test_mode_fails_closed_outside_dev(app):
    with app.app_context():
        assert storage.mode() == "local"
        app.config["DEV_MODE"] = False  # 운영: R2가 없으면 로컬 디스크에 두지 않는다
        assert storage.mode() == "off"
        app.config.update(R2_ACCOUNT_ID="a", R2_ACCESS_KEY_ID="b", R2_SECRET_ACCESS_KEY="c", R2_BUCKET="d")
        assert storage.mode() == "r2"


def test_local_put_serves_with_headers_and_delete(app):
    key = "shopping/1/abc.jpg"
    with app.app_context():
        storage.put(key, JPEG, "image/jpeg")
        path = os.path.join(app.config["UPLOAD_DIR"], "shopping", "1", "abc.jpg")
        assert open(path, "rb").read() == JPEG
        with app.test_request_context():
            res = storage.photo_response(key)
            res.direct_passthrough = False
            assert res.status_code == 200
            assert res.get_data() == JPEG
            assert res.mimetype == "image/jpeg"
            assert res.headers["X-Content-Type-Options"] == "nosniff"
            assert res.headers["Cache-Control"] == "private, max-age=3600"
            assert res.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
            res.close()
        storage.delete([key, "shopping/1/missing.jpg"])  # 없는 키는 조용히 넘어간다
        assert not os.path.exists(path)


@pytest.mark.parametrize("key", ["../x.jpg", "shopping/../../x.jpg", "/etc/x.jpg"])
def test_unsafe_keys_rejected(app, key):
    with app.app_context():
        with pytest.raises(ValueError):
            storage.put(key, JPEG, "image/jpeg")
        with app.test_request_context(), pytest.raises(HTTPException) as e:
            storage.photo_response(key)
        assert e.value.code == 404
        storage.delete([key])  # 조용히 무시
    assert not os.path.exists(os.path.join(os.path.dirname(app.config["UPLOAD_DIR"]), "x.jpg"))


R2 = {"R2_ACCOUNT_ID": "acc", "R2_ACCESS_KEY_ID": "kid", "R2_SECRET_ACCESS_KEY": "shh-secret", "R2_BUCKET": "bucket"}


def add_photo(client, r2):
    note_id = client.post("/api/shopping/notes", json={"body": "메모"}).get_json()["id"]
    r2.add_response(
        "put_object", {}, {"Bucket": "bucket", "Key": ANY, "Body": ANY, "ContentType": "image/jpeg"}
    )
    res = client.post(
        f"/api/shopping/notes/{note_id}/photos",
        data={"image": (io.BytesIO(JPEG), "a.jpg")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    return note_id, res.get_json()


@pytest.fixture
def r2(app, monkeypatch):
    """네트워크 없이: 진짜 설정으로 만든 클라이언트에 Stubber를 끼운다."""
    app.config.update(R2, DEV_MODE=False)
    s3 = storage._r2_client.__wrapped__("acc", "kid", "shh-secret")  # 캐시를 거치지 않고 테스트마다 새로
    monkeypatch.setattr(storage, "_client", lambda: s3)
    with Stubber(s3) as stub:
        yield stub
        stub.assert_no_pending_responses()


def test_r2_client_config():
    s3 = storage._r2_client.__wrapped__("acc", "kid", "shh-secret")
    assert s3.meta.endpoint_url == "https://acc.r2.cloudflarestorage.com"
    assert s3.meta.region_name == "auto"
    cfg = s3.meta.config
    assert (cfg.signature_version, cfg.connect_timeout, cfg.read_timeout) == ("s3v4", 3, 10)
    assert cfg.retries["total_max_attempts"] == 2


def test_r2_upload_serve_delete(client, login, r2):
    login()
    note_id, photo = add_photo(client, r2)
    key = photo["url"].removeprefix("/api/photos/")

    r2.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(JPEG), len(JPEG)), "ContentLength": len(JPEG), "ContentType": "text/html"},
        {"Bucket": "bucket", "Key": key},
    )
    got = client.get(photo["url"])
    assert (got.status_code, got.data, got.mimetype) == (200, JPEG, "image/jpeg")  # 저장된 Content-Type이 아니라 키 확장자
    assert got.headers["X-Content-Type-Options"] == "nosniff"
    assert got.headers["Cache-Control"] == "private, max-age=3600"
    assert got.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"

    r2.add_response("delete_objects", {}, {"Bucket": "bucket", "Delete": {"Objects": [{"Key": key}], "Quiet": True}})
    assert client.delete(f"/api/shopping/notes/{note_id}/photos/{photo['id']}").status_code == 204
    assert client.get(photo["url"]).status_code == 404  # 행이 없으면 R2를 부르지 않는다(남은 응답 없음으로 확인)


def test_r2_delete_batches_1000(app, r2):
    """delete_objects는 한 번에 1000개까지만 받는다 — 1001개는 두 번(1000 + 1)에 나눠 보낸다."""
    keys = [f"shopping/1/{i}.jpg" for i in range(1001)]
    r2.add_response("delete_objects", {}, {"Bucket": "bucket", "Delete": {"Objects": [{"Key": k} for k in keys[:1000]], "Quiet": True}})
    r2.add_response("delete_objects", {}, {"Bucket": "bucket", "Delete": {"Objects": [{"Key": keys[1000]}], "Quiet": True}})
    with app.app_context():
        storage.delete(keys)  # r2 fixture의 assert_no_pending_responses가 정확히 2번 불렀는지 확인한다


def test_r2_owner_check_before_any_call(client, login, r2, monkeypatch):
    login()
    _, photo = add_photo(client, r2)
    login("other")

    def no_call():
        raise AssertionError("소유자 확인 전에 R2를 부르면 안 돼요")

    monkeypatch.setattr(storage, "_client", no_call)
    assert client.get(photo["url"]).status_code == 404
    with client.session_transaction() as s:
        s.clear()
    assert client.get(photo["url"]).status_code == 401


def test_r2_missing_object_404_and_errors_503(client, login, r2, monkeypatch, caplog):
    login()
    note_id, photo = add_photo(client, r2)
    key = photo["url"].removeprefix("/api/photos/")

    r2.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    assert client.get(photo["url"]).status_code == 404
    r2.add_client_error("get_object", service_error_code="InternalError", http_status_code=500)
    res = client.get(photo["url"])
    assert (res.status_code, res.get_json()) == (503, {"error": "사진을 지금은 볼 수 없어요."})

    r2.add_client_error("put_object", service_error_code="InternalError", http_status_code=500)
    res = client.post(
        f"/api/shopping/notes/{note_id}/photos",
        data={"image": (io.BytesIO(JPEG), "a.jpg")},
        content_type="multipart/form-data",
    )
    assert (res.status_code, res.get_json()) == (503, {"error": "사진을 지금은 올릴 수 없어요."})

    class Down:  # 연결 실패
        def __getattr__(self, name):
            def fail(**kwargs):
                raise EndpointConnectionError(endpoint_url="https://acc.r2.cloudflarestorage.com")

            return fail

    monkeypatch.setattr(storage, "_client", lambda: Down())
    assert client.get(photo["url"]).status_code == 503
    assert client.delete(f"/api/shopping/notes/{note_id}").status_code == 204  # 지우기 실패는 로그만
    assert len(client.get("/api/shopping").get_json()["notes"]) == 0
    assert key not in caplog.text and "shh-secret" not in caplog.text
