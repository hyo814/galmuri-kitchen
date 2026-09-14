import logging
import os

from flask import abort, current_app, send_from_directory
from werkzeug.security import safe_join

# 사진 저장소(스펙 3절): R2 | 개발용 로컬 폴더(UPLOAD_DIR, DEV_MODE일 때만) | 그 밖에는 off(사진 올리기 503).
# 키는 서버가 만든다(`shopping/<user_id>/<hex>.<ext>`). 보여주기 전 소유자 확인은 photos.py가 한다.
R2_KEYS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
log = logging.getLogger(__name__)


def mode():
    if all(current_app.config.get(k) for k in R2_KEYS):
        return "r2"
    # 닫힌 쪽이 기본: 개발 모드가 아니면 로컬 디스크에 두지 않는다(Render 디스크는 배포 때 지워진다).
    return "local" if current_app.config.get("DEV_MODE") else "off"


def _r2_not_connected():
    # ponytail: R2는 아직 연결하지 않았다(boto3 미설치 — 새 의존성은 배포 태스크에서). 연결할 때 boto3를 고정하고
    # put_object / delete_objects / 만료 5분 presigned GET 302를 여기 세 곳에 넣는다. 그 전까지 R2 값이 있으면 사진은 503.
    raise NotImplementedError("R2 storage is not connected yet")


def _local_path(key):
    path = safe_join(current_app.config["UPLOAD_DIR"], key)  # `..`·앞 `/`면 None
    if path is None:
        raise ValueError("unsafe key")
    return path


def put(key, data, content_type):
    if mode() != "local":
        _r2_not_connected()
    path = _local_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def delete(keys):
    """없는 키·실패는 로그만 남긴다(행은 이미 지워졌다)."""
    for key in keys:
        if mode() != "local":
            log.warning("photo delete skipped: R2 not connected")
            continue
        try:
            os.remove(_local_path(key))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("photo delete failed: %s", type(e).__name__)


def photo_response(key):
    if mode() != "local":
        abort(503, "사진을 지금은 볼 수 없어요.")
    res = send_from_directory(current_app.config["UPLOAD_DIR"], key)  # 경로 조작·없는 파일은 404
    res.headers["Cache-Control"] = "private, max-age=3600"
    res.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"  # 주소를 직접 열어도 스크립트가 돌지 않게
    res.headers["X-Content-Type-Options"] = "nosniff"
    return res
