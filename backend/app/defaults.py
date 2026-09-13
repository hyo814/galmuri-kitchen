from .models import ItemRule, StorageLocation, db

DEFAULT_LOCATIONS = [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]


def _mfds(reference_days):
    """식약처 소비기한 참고값은 제조일 기준이라, 구입일 기준으로는 80%(내림)에서 빨강, 그 3일 전부터 노랑."""
    danger = reference_days * 8 // 10
    return danger - 3, danger


# 기본 품목 규칙 (키워드, 노랑 일수, 빨강 일수, 출처). 기준일은 구입일. 스펙 14절.
# 식약처 「식품유형별 소비기한 설정 보고서」 참고값: 두부 23, 발효유 32, 과채주스 35, 빵류 31, 어묵 42, 소시지 56, 햄 57일
#   https://www.foodnews.co.kr/news/articleView.html?idxno=99913
#   https://www.lecturernews.com/news/articleView.html?idxno=113115
# 달걀·계란: 식약처 권장 산란일 기준 45일, 가정 냉장 3~5주 → 구입일 기준 30일 (사용자 결정 2026-09-13)
# 우유: 참고값 없음(우유류 소비기한 표시제 2031년 적용) → 규칙 없이 포장 소비기한 입력을 안내
DEFAULT_RULES = [
    ("달걀", 25, 30, "user"),
    ("계란", 25, 30, "user"),
    ("두부", *_mfds(23), "mfds"),
    ("요거트", *_mfds(32), "mfds"),
    ("요구르트", *_mfds(32), "mfds"),
    ("주스", *_mfds(35), "mfds"),
    ("빵", *_mfds(31), "mfds"),
    ("어묵", *_mfds(42), "mfds"),
    ("소시지", *_mfds(56), "mfds"),
    ("햄", *_mfds(57), "mfds"),
]


def seed_user_defaults(user_id):
    """새 사용자에게 기본 보관 위치와 품목 규칙을 만든다. commit은 호출 측에서."""
    for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
        db.session.add(StorageLocation(user_id=user_id, name=name, kind=kind, sort_order=order))
    for keyword, warn_days, danger_days, source in DEFAULT_RULES:
        db.session.add(
            ItemRule(user_id=user_id, keyword=keyword, warn_days=warn_days, danger_days=danger_days, source=source)
        )
