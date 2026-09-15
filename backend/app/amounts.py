"""레시피 재료 양 글자 → (수량, 단위). 식단 장보기 합산용(스펙 23절 D4). 순수 함수만 두어 DB 없이 테스트한다.

ponytail: 규칙 기반이다. '10~15개'·'약간'처럼 셀 수 없으면 None으로 두고 화면에서 사용자가 고른다.
"""

import re

_PARENS = re.compile(r"\([^)]*\)")
_UNIT = r"([^\d\s~\-–/.,¼⅓½⅔¾]{0,10})"
_NATIVE = {"하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
_NATIVE_RE = re.compile(rf"(하나|한|둘|두|셋|세(?!트)|넷|네|다섯|여섯|일곱|여덟|아홉|열)\s*{_UNIT}")
_MIXED_RE = re.compile(rf"(\d+)\s+(\d+)/(\d+)\s*{_UNIT}")  # "2 1/2컵"
_SIMPLE_RE = re.compile(rf"(\d+(?:\.\d+)?)?(?:/(\d+))?([¼⅓½⅔¾])?\s*{_UNIT}")  # "200g" "1/2모" "1½큰술" "½개"
_FRACTIONS = {"¼": 1 / 4, "⅓": 1 / 3, "½": 1 / 2, "⅔": 2 / 3, "¾": 3 / 4}
_SCALE = {"kg": ("g", 1000), "l": ("ml", 1000)}  # 같은 단위끼리 더하고 빼려고 작은 단위로 바꾼다
SPOON_UNITS = {"큰술", "작은술", "숟가락", "스푼", "티스푼", "컵", "꼬집", "t", "ts", "tbsp", "tsp"}


def parse_amount(text):
    """'200g' → (200.0, 'g'), '1/2모(150g)' → (0.5, '모'), '1½큰술' → (1.5, '큰술'), '두 개' → (2.0, '개'),
    '2' → (2.0, '개'), '1.5kg' → (1500.0, 'g'), '1L' → (1000.0, 'ml'). '약간'·'10~15개'·''·'0개'는 None."""
    s = _PARENS.sub("", text or "").strip()
    if m := _NATIVE_RE.fullmatch(s):
        value, unit = float(_NATIVE[m.group(1)]), m.group(2)
    elif m := _MIXED_RE.fullmatch(s):
        whole, num, den, unit = m.groups()
        if int(den) == 0:
            return None
        value = int(whole) + int(num) / int(den)
    elif m := _SIMPLE_RE.fullmatch(s):
        number, den, symbol, unit = m.groups()
        if not number and not symbol:
            return None
        if den and (not number or symbol or int(den) == 0):
            return None
        value = float(number or 0) / (int(den) if den else 1) + _FRACTIONS.get(symbol, 0)
    else:
        return None
    if value <= 0:
        return None
    unit = unit or "개"
    base = _SCALE.get(unit.lower())
    return (value * base[1], base[0]) if base else (value, unit)


def is_spoon(unit):
    return unit.lower() in SPOON_UNITS


def in_unit(amount_text, unit):
    """레시피 양 글자를 재고 단위 수량으로(23절 D2). '300g'·'kg' → 0.3, '1/2모'·'모' → 0.5, '1L'·'ml' → 1000.0.
    단위가 다르거나(대소문자 무시) 못 읽거나 재고 단위에 숫자가 들었으면(30구) None."""
    if not unit or any(ch.isdigit() for ch in unit):
        return None
    parsed, target = parse_amount(amount_text), parse_amount(f"1{unit}")
    if parsed is None or target is None or parsed[1].lower() != target[1].lower():
        return None
    return parsed[0] / target[0]
