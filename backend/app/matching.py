import re

# ponytail: 부분 문자열 매칭 — "파"가 "파프리카"에 걸리는 오류 가능. 문제되면 동의어 사전이나 AI 매칭으로 교체 (스펙 4절)


def normalize(name):
    """괄호와 그 안 내용 제거 → 공백 제거 → 소문자."""
    return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", name)).lower()


def names_match(a, b):
    a, b = normalize(a), normalize(b)
    return bool(a) and bool(b) and (a in b or b in a)


def keyword_in(keyword, name):
    keyword = normalize(keyword)
    return bool(keyword) and keyword in normalize(name)
