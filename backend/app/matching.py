import re

# ponytail: 이름 매칭은 규칙 기반이다. 오탐·누락이 문제되면 동의어 사전이나 AI 매칭으로 교체 (스펙 4절)
_PARENS = re.compile(r"\([^)]*\)")
_TOKEN_SPLIT = re.compile(r"[\s,/·\[\]*+&]+")
# ponytail: 같은 재료의 다른 이름은 앞 표기를 뒤 표기로 바꿔 비교한다(부분 문자열 치환 — 계란말이 → 달걀말이). 늘어나면 여기에 더한다.
# 케찹·고추가루·후추의 표기 차이(케첩·고춧가루·후춧가루)는 여기(전역)에 넣지 않는다 — food_matches.ingredient_key·
# unit_weight_estimates.name_key·food_searches.query_key·food_nutrients.name_key 등 이 normalize로 만든 저장된 키가
# 어긋나 버린다(2026-09-18, 리뷰). 필수품 전용 별칭은 아래 STAPLE_ALIASES에 따로 둔다.
SYNONYMS = {"계란": "달걀"}
# 2글자 이름의 접미 규칙(아래 _match_one_way_prepared)은 우연히 표기가 겹치면 다른 물건도 매칭한다.
# 깨소금은 소금의 한 종류가 아니라 다른 조미료라 "깨소금이 있으면 소금도 있다"로 보이면 안 된다(둘 다 기본 필수품 이름, 2026-09-18).
# 진간장·국간장·양조간장은 서로 3글자라 완전히 같은 문자열일 때만 매칭돼(부분 문자열 규칙) 이런 충돌이 없다 — 예외를 더 두지 않는다.
# names_match·match_prepared(재료 vs 레시피 재료 등 여러 곳에서 쓴다)에도 그대로 둔다 — "레시피에 소금이 필요한데
# 깨소금만 있어도 있다고 본다"도 같은 종류의 오탐이라, 필수품 쪽에만 좁히지 않는다(2026-09-18, 검토 완료).
SUFFIX_NON_MATCHES = {("소금", "깨소금")}
# 필수품 전용 표기 별칭(2026-09-18) — staple_matches에서만 쓴다. 전역 SYNONYMS와 달리 저장된 키에 영향 없다.
STAPLE_ALIASES = {"케찹": ("케첩",), "고추가루": ("고춧가루",), "후추": ("후춧가루",)}


def _canonical(text):
    for word, canonical in SYNONYMS.items():
        text = text.replace(word, canonical)
    return text


def title_key(text):
    """요리 제목 비교 키: 공백 제거 → 소문자 → 동의어. normalize와 달리 괄호 속은 남긴다(`두부조림(매운맛)` ≠ `두부조림(간장)`)."""
    return _canonical(re.sub(r"\s+", "", text).lower())


def normalize(name):
    """괄호와 그 안 내용 제거 → 공백 제거 → 소문자 → 동의어를 한 표기로(계란 → 달걀)."""
    return _canonical(re.sub(r"\s+", "", _PARENS.sub("", name)).lower())


def tokens(name):
    """괄호와 그 안 내용을 공백으로 치환하고 숫자 앞에도 공백을 넣은 뒤 공백·구분 기호로 나눈 소문자 단어들.
    동의어는 normalize와 같이 바꾼다. "유정란 계란 (특란) 10구" → ["유정란", "달걀", "10구"], "대파(국산)1단" → ["대파", "1단"], "대파1단" → ["대파", "1단"]"""
    spaced = _canonical(re.sub(r"(\d+)", r" \1", _PARENS.sub(" ", name)).lower())
    return [t for t in _TOKEN_SPLIT.split(spaced) if t]


def _short_match(short, name, allow_suffix):
    return any(word == short or (allow_suffix and word.endswith(short)) for word in tokens(name))


def prepare(name):
    """normalize·tokens를 한 번만 계산해 둔다(추천처럼 하나를 여러 번 비교할 때 재계산을 피한다). fix round 1 (S1 성능)."""
    norm = normalize(name)
    return norm, len(norm), tokens(name)


def _match_one_way_prepared(short_norm, short_len, long_norm, long_tokens):
    if short_len >= 3:
        return short_norm in long_norm
    return short_len > 0 and any(
        word == short_norm
        or (short_len == 2 and word.endswith(short_norm) and (short_norm, word) not in SUFFIX_NON_MATCHES)
        for word in long_tokens
    )


def match_prepared(a, b):
    """names_match와 같은 규칙이지만 양쪽 다 prepare()로 미리 계산해 둔 값을 받는다."""
    a_norm, a_len, a_tokens = a
    b_norm, b_len, b_tokens = b
    if not a_norm or not b_norm:
        return False
    if a_len == b_len:
        return _match_one_way_prepared(a_norm, a_len, b_norm, b_tokens) or _match_one_way_prepared(b_norm, b_len, a_norm, a_tokens)
    if a_len < b_len:
        return _match_one_way_prepared(a_norm, a_len, b_norm, b_tokens)
    return _match_one_way_prepared(b_norm, b_len, a_norm, a_tokens)


def names_match(a, b):
    """이름 매칭(양방향). 짧은 이름 오탐을 막는다(사용성 점검 C4).
    - 짧은 쪽이 3글자 이상: 부분 문자열
    - 2글자: 긴 쪽 단어가 같거나 그 이름으로 끝날 때 (대파 1단·청양고추·진간장 O / 고추장·간장게장 X)
    - 1글자: 긴 쪽 단어와 정확히 같을 때 (파→양파 X, 무→단무지 X)
    길이가 같으면 양방향(a가 짧은 쪽/b가 짧은 쪽) 모두 확인해 대칭을 보장한다.
    필수품↔재료 비교에는 이 함수 대신 staple_matches를 쓴다(여러 단어 필수품 오탐 방지).
    """
    return match_prepared(prepare(a), prepare(b))


def _staple_matches_one(staple, ingredient):
    staple_norm, staple_len, staple_tokens = prepare(staple)
    ing_norm, ing_len, ing_tokens = prepare(ingredient)
    if not staple_norm or not ing_norm:
        return False
    if staple_len <= ing_len:
        # 필수품 ⊆ 재료(필수품이 짧거나 같음): names_match와 같은 1·2·3글자 이상 규칙 — 대파 ⊆ "대파 1단" 같은 정상 경우.
        return _match_one_way_prepared(staple_norm, staple_len, ing_norm, ing_tokens)
    # 재료 ⊆ 필수품(재료가 더 짧음, 역방향): 필수품이 한 낱말이고 재료로 끝날 때만(부분 문자열 금지, 1글자 재료는 매칭 안 함).
    # 여러 낱말 필수품(예: "토마토 파스타 소스")은 이 방향으로 절대 안 맞는다 — 재료 "토마토"가 거기 맞아 버리던 오탐 방지.
    # 접미사로만 받는 이유: "올리브"가 "올리브유"의 앞부분과 같다고 다른 물건(기름)까지 맞다고 보면 안 된다(2026-09-18).
    if ing_len < 2 or len(staple_tokens) > 1:
        return False
    return staple_norm.endswith(ing_norm) and (ing_norm, staple_norm) not in SUFFIX_NON_MATCHES


def staple_matches(staple, ingredient):
    """필수품↔재료 전용 매칭(names_match와 달리 방향을 구별한다, 2026-09-18 — 리뷰로 발견된 오탐 수정).
    필수품 ⊆ 재료(필수품이 짧거나 같음)는 names_match와 같은 1·2·3글자 이상 규칙 그대로.
    재료 ⊆ 필수품(재료가 더 짧음)은 필수품이 한 낱말(공백 없음)이고 접미사로 끝날 때만 — 부분 문자열은 안 된다.
    여러 낱말 필수품(예: "토마토 파스타 소스", "돼지 갈비 양념 소스")은 이 역방향으로 절대 매칭되지 않는다 —
    재료 "토마토"·"돼지"가 그런 필수품에 우연히 맞아 버리던 오탐(cooklog.is_seasoning·staples 상태·마이그레이션 백필 전부에
    영향을 줬다)을 막는다. 케찹·고추가루·후추는 여기서만 실제 상품 표기 별칭(STAPLE_ALIASES)을 함께 본다."""
    return any(_staple_matches_one(name, ingredient) for name in (staple,) + STAPLE_ALIASES.get(staple, ()))


def head_is(name, word):
    """이름의 마지막 단어(숫자로 시작하는 용량·개수 제외)가 word로 끝나는지. "청정원 순창 고추장 500g" → 고추장 O, "고추장 불고기" → X"""
    word = normalize(word)
    words = [t for t in tokens(name) if not t[0].isdigit()]
    return bool(word and words) and words[-1].endswith(word)


def keyword_in(keyword, name):
    """품목 규칙 키워드가 재료 이름에 들어가는지(한 방향).
    2글자 이하 키워드는 단어가 같거나 그 키워드로 끝날 때만 (식빵·순두부 O / 빵가루·햄버거 X)."""
    keyword = normalize(keyword)
    if not keyword:
        return False
    if len(keyword) >= 3:
        return keyword in normalize(name)
    return _short_match(keyword, name, allow_suffix=True)
