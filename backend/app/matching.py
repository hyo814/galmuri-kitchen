import re

# ponytail: 이름 매칭은 규칙 기반이다. 오탐·누락이 문제되면 동의어 사전이나 AI 매칭으로 교체 (스펙 4절)
_PARENS = re.compile(r"\([^)]*\)")
_TOKEN_SPLIT = re.compile(r"[\s,/·\[\]*+&]+")


def normalize(name):
    """괄호와 그 안 내용 제거 → 공백 제거 → 소문자."""
    return re.sub(r"\s+", "", _PARENS.sub("", name)).lower()


def tokens(name):
    """괄호 내용을 뺀 뒤 공백·구분 기호로 나눈 소문자 단어들. "유정란 계란 (특란) 10구" → ["유정란", "계란", "10구"]"""
    return [t for t in _TOKEN_SPLIT.split(_PARENS.sub("", name).lower()) if t]


def _short_match(short, name, allow_suffix):
    return any(word == short or (allow_suffix and word.endswith(short)) for word in tokens(name))


def names_match(a, b):
    """필수품↔재료 매칭(양방향). 짧은 이름 오탐을 막는다(사용성 점검 C4).
    - 짧은 쪽이 3글자 이상: 부분 문자열
    - 2글자: 긴 쪽 단어가 같거나 그 이름으로 끝날 때 (대파 1단·청양고추·진간장 O / 고추장·간장게장 X)
    - 1글자: 긴 쪽 단어와 정확히 같을 때 (파→양파 X, 무→단무지 X)
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if len(na) > len(nb):
        a, b, na, nb = b, a, nb, na
    if len(na) >= 3:
        return na in nb
    return _short_match(na, b, allow_suffix=len(na) == 2)


def keyword_in(keyword, name):
    """품목 규칙 키워드가 재료 이름에 들어가는지(한 방향).
    2글자 이하 키워드는 단어가 같거나 그 키워드로 끝날 때만 (식빵·순두부 O / 빵가루·햄버거 X)."""
    keyword = normalize(keyword)
    if not keyword:
        return False
    if len(keyword) >= 3:
        return keyword in normalize(name)
    return _short_match(keyword, name, allow_suffix=True)
