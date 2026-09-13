"""식약처 COOKRCP01 레시피 원문 정리. 순수 함수만 두어 네트워크 없이 테스트한다.

ponytail: 규칙 기반 파서다. 확신이 없으면 문자열 전체를 이름으로 두고 양은 ""로 둔다(버리지 않는다).
원문 모양이 더 다양하면 규칙을 늘리기보다 AI 정리(3b)로 교체한다.
"""

import re

from .matching import normalize, tokens

MAX_INGREDIENTS = 50
MAX_NAME = 50
MAX_AMOUNT = 30
MAX_STEP = 500
DEFAULT_SERVINGS = 2

_BULLET = re.compile(r"^[\s●○•·▶▷■□◆◇※*-]+")
_BRACKET = re.compile(r"^[\[【<]([^\]】>]*)[\]】>]\s*")  # "[1인분]", "[양념장]"
_LABEL = re.compile(r"^[^,:：()]{1,20}[:：]\s*")  # "양념장 : ", "주재료:"
_LEAD_WORD = re.compile(r"^(?:주재료|부재료|재료)\s+")
_HEADER_WORDS = {"재료", "주재료", "부재료", "양념", "양념장", "소스", "고명", "육수", "드레싱", "반죽", "토핑", "곁들임"}
_AMOUNT_START = r"(?:\d|[½⅓⅔¼¾⅛]|약간|적당량|적당히|조금|소량|취향껏)"
_SPACED = re.compile(rf"^(.+?)\s+({_AMOUNT_START}.*)$")  # "다진 마늘 1작은술(5g)"
_ATTACHED = re.compile(r"^(.*[가-힣])(\d[\d./]*[^\s\d(]*(?:\([^)]*\))?)$")  # "대파1대" (양 안에 공백 없음)
_STEP_NO = re.compile(r"^\d+[.)](?!\d)\s*")  # "1. " (1.5컵은 그대로)
_STEP_MARK = re.compile(r"(?<=[.!?])\s*[a-zA-Z]$")  # 원문 단계 끝의 "a", "b"
_SERVINGS = re.compile(r"(\d+)\s*인분")


def _split_items(line):
    """괄호 밖 쉼표로 나눈다. "소금(1g, 약간), 후추" → ["소금(1g, 약간)", " 후추"]"""
    items, depth, start = [], 0, 0
    for index, char in enumerate(line):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char in ",，" and depth == 0:
            items.append(line[start:index])
            start = index + 1
    items.append(line[start:])
    return items


def _clean_item(item):
    item = _BULLET.sub("", item).strip()
    while match := _BRACKET.match(item):
        item = item[match.end() :].strip()
    item = _LABEL.sub("", item, count=1)
    return _LEAD_WORD.sub("", item, count=1).strip()


def _name_amount(item):
    match = _SPACED.match(item) or _ATTACHED.match(item)
    if not match or match.group(1).count("(") != match.group(1).count(")"):  # 괄호 안에서 자르지 않는다
        return item, ""
    return match.group(1).strip(), match.group(2).strip()


def parse_ingredients(text, title=""):
    """RCP_PARTS_DTLS → [{name, amount}]. 제목 줄·구역 제목을 빼고, 이름이 같으면 처음 것만, 최대 50개."""
    title_key = normalize(title or "")
    result, seen = [], set()
    for line in (text or "").splitlines():
        for raw in _split_items(line):
            item = _clean_item(raw)
            if not item:
                continue
            name, amount = _name_amount(item)
            key = normalize(name)
            is_header = key in _HEADER_WORDS or (title_key and (key == title_key or (len(key) >= 3 and title_key.endswith(key))))
            if not key or key in seen or (not amount and is_header):
                continue
            seen.add(key)
            result.append({"name": name[:MAX_NAME].strip(), "amount": amount[:MAX_AMOUNT].strip()})
            if len(result) == MAX_INGREDIENTS:
                return result
    return result


def split_steps(row):
    """MANUAL01~MANUAL20 중 내용이 있는 칸. 앞 번호("1. ")와 끝 표시 글자("a")는 뗀다(화면이 번호를 붙인다)."""
    steps = []
    for number in range(1, 21):
        value = row.get(f"MANUAL{number:02d}")
        if not isinstance(value, str):
            continue
        step = _STEP_MARK.sub("", _STEP_NO.sub("", " ".join(value.split())))
        if step:
            steps.append(step[:MAX_STEP])
    return steps


def parse_servings(text):
    """원문에 "N인분"이 있으면 그 값(1~20), 없으면 2 (스펙 23절 D1)."""
    match = _SERVINGS.search(text or "")
    servings = int(match.group(1)) if match else DEFAULT_SERVINGS
    return servings if 1 <= servings <= 20 else DEFAULT_SERVINGS


def ingredient_key(name):
    """매칭용 이름: 괄호 내용을 빼고 소문자 단어를 공백 하나로 잇는다. names_match와 같은 단어 경계를 유지한다."""
    return " ".join(tokens(name))
