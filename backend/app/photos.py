from flask import Blueprint, abort, g, request

from . import storage
from .auth import login_required
from .models import FoodLog, FoodLogPhoto, ShoppingNote, ShoppingNotePhoto, db
from .scan import sniff_image_type

# 사진 보기(스펙 5절)와 올리기 검사(장보기 메모·먹은 기록이 함께 쓴다). 내 키이고 행이 있어야 보여준다 — 남의 키·지운 사진은 404.
bp = Blueprint("photos", __name__, url_prefix="/api/photos")

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def read_image(max_bytes):
    """request.files['image'] → (data, media_type, ext). 10MB 초과는 파일을 읽을 때 413(MAX_CONTENT_LENGTH).
    없음·빈 파일 400 '사진을 올려주세요.' → max_bytes 초과 413 '사진이 너무 커요.' → 서명이 JPG·PNG·WEBP 아님 415 '사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.'"""
    image = request.files.get("image")
    data = image.read() if image is not None else b""
    if not data:
        abort(400, "사진을 올려주세요.")
    if len(data) > max_bytes:
        abort(413, "사진이 너무 커요.")
    media_type = sniff_image_type(data)  # 선언된 Content-Type이 아니라 파일 서명을 믿는다
    if media_type not in EXTENSIONS:
        abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
    return data, media_type, EXTENSIONS[media_type]


def user_photo_keys(user_ids):
    """이 사용자들의 모든 사진 키(장보기 메모 + 먹은 기록). 체험 계정 정리·회원 탈퇴가 커밋 뒤 storage.delete에 넘긴다(결정 17)."""
    notes = db.session.query(ShoppingNotePhoto.photo_key).join(ShoppingNote).filter(ShoppingNote.user_id.in_(user_ids))
    logs = db.session.query(FoodLogPhoto.photo_key).join(FoodLog).filter(FoodLog.user_id.in_(user_ids))
    return [key for (key,) in notes] + [key for (key,) in logs]


@bp.get("/<path:key>")
@login_required
def photo(key):
    # ponytail: 5단계 조리 기록 사진은 접두사와 행 확인을 여기에 더한다.
    if key.startswith(f"shopping/{g.user.id}/"):
        owned = (
            ShoppingNotePhoto.query.join(ShoppingNote)
            .filter(ShoppingNotePhoto.photo_key == key, ShoppingNote.user_id == g.user.id)
            .first()
        )
    elif key.startswith(f"foodlog/{g.user.id}/"):
        owned = FoodLogPhoto.query.join(FoodLog).filter(FoodLogPhoto.photo_key == key, FoodLog.user_id == g.user.id).first()
    else:
        owned = None
    if not owned:
        abort(404, "찾을 수 없어요.")
    return storage.photo_response(key)
