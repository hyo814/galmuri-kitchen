from flask import abort
from sqlalchemy.exc import IntegrityError

from .models import db


def commit_or_duplicate(message):
    """db.session.commit()하되, UNIQUE 제약 충돌은 500 대신 400으로 (동시 요청 경합 대비)."""
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(400, message)


def text(value, label, max_len):
    """앞뒤 공백을 뺀 1~max_len자 문자열. label은 조사를 포함한다(예: "이름은")."""
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_len:
        abort(400, f"{label} 1~{max_len}자로 입력해 주세요.")
    return value.strip()


def integer(value, label, lo, hi):
    """bool이 아닌 lo~hi 정수."""
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        abort(400, f"{label} {lo}~{hi} 사이 정수로 입력해 주세요.")
    return value
