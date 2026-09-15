import base64
import binascii
import re
from datetime import date, datetime, timezone

from flask import abort
from sqlalchemy.exc import IntegrityError

from .models import db

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


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
        abort(400, f"{label} 1~{max_len}자로 입력해주세요.")
    return value.strip()


def memo(value, max_len):
    """None 또는 문자열(아니면·NUL 글자면 400 '잘못된 요청이에요.'). strip 뒤 비면 None, max_len자 넘으면 400(먹은 기록·요리 일기가 함께 쓴다, 개정 1 D14)."""
    if value is not None and (not isinstance(value, str) or "\x00" in value):
        abort(400, "잘못된 요청이에요.")
    value = value.strip() if value else None
    if value and len(value) > max_len:
        abort(400, f"메모는 {max_len}자까지 입력해주세요.")
    return value or None


def integer(value, label, lo, hi):
    """bool이 아닌 lo~hi 정수."""
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        abort(400, f"{label} {lo}~{hi} 사이 정수로 입력해주세요.")
    return value


def iso_date(value):
    """YYYY-MM-DD 문자열만 날짜로 바꾸고, 아니면 None. date.fromisoformat은 3.11부터 20260101도 받아서 모양을 먼저 거른다."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def iso_datetime(value):
    """시간대가 붙은 ISO 문자열. SQLite는 tz 없이 돌려주므로 UTC로 본다."""
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def encode_cursor(when, row_id):
    """목록 커서(불투명 문자열): 시각|id. 시각·id 내림차순 페이지에서 마지막 행으로 만든다."""
    return base64.urlsafe_b64encode(f"{iso_datetime(when)}|{row_id}".encode()).decode()


def decode_cursor(value):
    """(시각, id). 모양이 틀리거나 id가 DB int 범위 밖이면 400."""
    try:
        raw = base64.urlsafe_b64decode(value.encode()).decode()
        when_iso, id_text = raw.rsplit("|", 1)
        when, row_id = datetime.fromisoformat(when_iso), int(id_text)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        abort(400, "잘못된 요청이에요.")
    if not 0 < row_id <= 2**31 - 1:  # M4: DB int 컬럼 범위 밖(Postgres에서 500 나던 값) → 400
        abort(400, "잘못된 요청이에요.")
    return when, row_id
