import os

import pytest
from werkzeug.exceptions import HTTPException

from app import storage

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 20


def test_mode_local_off_r2(app, monkeypatch):
    with app.app_context():
        assert storage.mode() == "local"
        monkeypatch.setenv("RENDER", "1")
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
            assert res.headers["Cache-Control"] == "private, max-age=86400"
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


def test_r2_not_connected_yet(app):
    app.config.update(R2_ACCOUNT_ID="a", R2_ACCESS_KEY_ID="b", R2_SECRET_ACCESS_KEY="c", R2_BUCKET="d")
    with app.app_context():
        with pytest.raises(NotImplementedError):
            storage.put("shopping/1/a.jpg", JPEG, "image/jpeg")
        with app.test_request_context(), pytest.raises(HTTPException) as e:
            storage.photo_response("shopping/1/a.jpg")
        assert e.value.code == 503
        storage.delete(["shopping/1/a.jpg"])  # 로그만
