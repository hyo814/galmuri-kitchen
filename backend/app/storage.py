import functools
import logging
import mimetypes
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import Response, abort, current_app, send_from_directory
from werkzeug.security import safe_join

# 사진 저장소(스펙 3절): R2 | 개발용 로컬 폴더(UPLOAD_DIR, DEV_MODE일 때만) | 그 밖에는 off(사진 올리기 503).
# 키는 서버가 만든다(`shopping/<user_id>/<hex>.<ext>`). 보여주기 전 소유자 확인은 photos.py가 한다.
R2_KEYS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
UPLOAD_UNAVAILABLE = "사진을 지금은 올릴 수 없어요."
VIEW_UNAVAILABLE = "사진을 지금은 볼 수 없어요."
log = logging.getLogger(__name__)


def mode():
    if all(current_app.config.get(k) for k in R2_KEYS):
        return "r2"
    # 닫힌 쪽이 기본: 개발 모드가 아니면 로컬 디스크에 두지 않는다(Render 디스크는 배포 때 지워진다).
    return "local" if current_app.config.get("DEV_MODE") else "off"


@functools.cache
def _r2_client(account_id, access_key_id, secret_access_key):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(
            signature_version="s3v4",
            connect_timeout=3,
            read_timeout=10,
            retries={"total_max_attempts": 2, "mode": "standard"},  # 처음 한 번 + 다시 한 번
            # boto3 1.36+가 기본으로 붙이는 체크섬은 필요한 요청에만(R2 호환 안내)
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _client():
    """테스트는 이 함수를 가짜(botocore Stubber)로 바꾼다."""
    c = current_app.config
    return _r2_client(c["R2_ACCOUNT_ID"], c["R2_ACCESS_KEY_ID"], c["R2_SECRET_ACCESS_KEY"])


def _local_path(key):
    path = safe_join(current_app.config["UPLOAD_DIR"], key)  # `..`·앞 `/`면 None
    if path is None:
        raise ValueError("unsafe key")
    return path


def put(key, data, content_type):
    if mode() == "r2":
        try:
            _client().put_object(Bucket=current_app.config["R2_BUCKET"], Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as e:
            log.warning("photo upload failed: %s", type(e).__name__)  # 키·비밀값은 남기지 않는다
            abort(503, UPLOAD_UNAVAILABLE)
        return
    if mode() != "local":
        abort(503, UPLOAD_UNAVAILABLE)
    path = _local_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def delete(keys):
    """없는 키·실패는 로그만 남긴다(행은 이미 지워졌다)."""
    if not keys:
        return
    if mode() == "r2":
        # ponytail: 실패하면 R2에 파일이 남는다(행은 이미 없음). 쌓이면 접두사로 훑어 지우는 정리 작업을 더한다.
        try:
            client, bucket = _client(), current_app.config["R2_BUCKET"]
            for i in range(0, len(keys), 1000):  # delete_objects는 한 번에 1000개까지만 받는다
                batch = keys[i : i + 1000]
                res = client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
                if res.get("Errors"):
                    log.warning("photo delete failed: %d objects", len(res["Errors"]))
        except (BotoCoreError, ClientError) as e:
            log.warning("photo delete failed: %s", type(e).__name__)
        return
    if mode() != "local":
        log.warning("photo delete skipped: storage off")
        return
    for key in keys:
        try:
            os.remove(_local_path(key))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("photo delete failed: %s", type(e).__name__)


def _r2_response(key):
    try:
        obj = _client().get_object(Bucket=current_app.config["R2_BUCKET"], Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            abort(404, "찾을 수 없어요.")
        log.warning("photo read failed: %s", code)
        abort(503, VIEW_UNAVAILABLE)
    except BotoCoreError as e:
        log.warning("photo read failed: %s", type(e).__name__)
        abort(503, VIEW_UNAVAILABLE)
    # ponytail: R2 → Render → 폰으로 흘려보낸다(같은 주소라 CORS 없이 보안 헤더 그대로). 사진 바이트와 워커 시간이 Render를 거치는 게 한계 —
    # 보기가 많아지면 만료 5분 presigned URL 302로 바꾸고 버킷 CORS에 앱 주소 GET을 연다.
    body = obj["Body"]
    res = Response(
        body.iter_chunks(64 * 1024),
        mimetype=mimetypes.guess_type(key)[0] or "application/octet-stream",  # 저장된 값보다 서버가 만든 키의 확장자를 믿는다
        direct_passthrough=True,
    )
    if obj.get("ContentLength") is not None:
        res.content_length = obj["ContentLength"]
    res.call_on_close(body.close)
    return res


def photo_response(key):
    if mode() == "r2":
        res = _r2_response(key)
    elif mode() == "local":
        res = send_from_directory(current_app.config["UPLOAD_DIR"], key)  # 경로 조작·없는 파일은 404
    else:
        abort(503, VIEW_UNAVAILABLE)
    res.headers["Cache-Control"] = "private, max-age=3600"
    res.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"  # 주소를 직접 열어도 스크립트가 돌지 않게
    res.headers["X-Content-Type-Options"] = "nosniff"
    return res
