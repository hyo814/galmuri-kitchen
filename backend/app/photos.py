from flask import Blueprint, abort, g

from . import storage
from .auth import login_required
from .models import ShoppingNote, ShoppingNotePhoto

# 사진 보기(스펙 5절). 내 키이고 행이 있어야 보여준다 — 남의 키·지운 사진은 404.
bp = Blueprint("photos", __name__, url_prefix="/api/photos")


@bp.get("/<path:key>")
@login_required
def photo(key):
    # ponytail: 지금은 장보기 메모 사진만. 5단계 조리 기록·4b 먹은 기록 사진은 접두사와 행 확인을 여기에 더한다.
    owned = (
        key.startswith(f"shopping/{g.user.id}/")
        and ShoppingNotePhoto.query.join(ShoppingNote)
        .filter(ShoppingNotePhoto.photo_key == key, ShoppingNote.user_id == g.user.id)
        .first()
    )
    if not owned:
        abort(404, "찾을 수 없어요.")
    return storage.photo_response(key)
