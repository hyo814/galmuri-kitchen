import pytest

from app.matching import head_is, keyword_in, names_match, normalize, staple_matches, tokens


def test_normalize_drops_parentheses_spaces_and_case():
    assert normalize(" 진 간장 (500ml) ") == "진간장"
    assert normalize("Egg 10구") == "egg10구"
    assert normalize("계란 (특란)") == "달걀"  # 동의어는 한 표기로


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("대파", "대파", True),
        ("간장", "진간장 (500ml)", True),
        ("진간장", "간장", True),
        ("Egg", "egg 10구", True),
        ("대파", "양파", False),
        ("", "양파", False),
        ("(국산)", "양파", False),
        ("파", "양파", False),
        ("대파", "대파 1단", True),
        ("고추", "고추장", False),
        ("고추", "청양고추", True),
        ("무", "단무지", False),
        ("간장", "간장게장", False),
        ("소금", "맛소금", True),
        ("달걀", "유정란 달걀 10구", True),
        ("돼지고기", "돼지고기 앞다리살", True),
        ("대파", "대파(국산)1단", True),
        ("대파", "대파1단", True),
        ("계란", "달걀", True),
        ("달걀", "유정란 계란 (특란) 10구", True),
        ("계란말이", "달걀말이", True),
        ("소금", "천일염", False),  # 표기가 아예 달라 동의어를 추가하지 않은 한계(정확한 사용자 결정 없어 보류)
        # 깨소금은 소금의 한 종류가 아니라 다른 조미료 — 둘 다 기본 필수품이라 오탐이 "있음"으로 잘못 보였다(2026-09-18 수정).
        # names_match·match_prepared(재료 vs 레시피 재료 등에도 쓴다)에 그대로 둔다 — 필수품 쪽에만 좁히지 않는다(검토 완료).
        ("소금", "깨소금", False),
        ("깨소금", "소금", False),
        ("소금", "청정원 깨소금 50g", False),
        ("깨소금", "청정원 깨소금 50g", True),  # 진짜 깨소금은 그대로 매칭
        ("소금", "구운소금", True),  # 진짜 소금 종류는 그대로 매칭(예외는 깨소금 하나뿐)
    ],
)
def test_names_match(a, b, expected):
    assert names_match(a, b) is expected


@pytest.mark.parametrize(
    "staple, ingredient, expected",
    [
        # 정상 방향(필수품 ⊆ 재료, 필수품이 짧거나 같음): names_match와 같은 규칙 그대로
        ("대파", "대파 1단", True),
        ("대파", "대파(국산)1단", True),
        ("고추", "청양고추", True),
        ("고추", "고추장", False),
        ("멸치 액젓", "멸치 액젓 500ml", True),
        ("토마토 파스타 소스", "오뚜기 토마토 파스타소스", True),
        ("돼지고기", "돼지고기 앞다리살", True),
        # 역방향(재료가 더 짧음)은 필수품이 한 낱말일 때만: 진간장은 한 낱말이라 재료 "간장"과 맞는다(기존 동작 유지)
        ("진간장", "간장", True),
        ("국간장", "간장", True),
        # 리뷰로 발견된 오탐(2026-09-18): 여러 낱말 필수품은 역방향으로 절대 안 맞는다 —
        # 재료 하나만으로 여러 낱말 필수품 전체가 "있어요"로 잘못 보이던 문제(양념 판정·필수품 상태·백필 전부 영향)
        ("토마토 파스타 소스", "토마토", False),
        ("크림 파스타 소스", "파스타", False),
        ("크림 파스타 소스", "크림", False),
        ("휘핑 크림", "크림", False),
        ("불고기 양념 소스", "불고기", False),
        ("돼지 갈비 양념 소스", "갈비", False),
        ("돼지 갈비 양념 소스", "돼지", False),
        ("멸치 액젓", "멸치", False),
        ("스위트 칠리 소스", "칠리", False),
        ("짜장 소스", "짜장", False),
        ("불닭 소스", "불닭", False),
        # 한 낱말이어도 부분 문자열(접미사 아님)은 역방향에서 막는다 — 다른 물건(2026-09-18)
        ("올리브유", "올리브", False),
        ("파스타면", "파스타", False),
        # 필수품 전용 별칭(STAPLE_ALIASES) — 전역 SYNONYMS에는 없다(food_matches 캐시 키 보호, 2026-09-18)
        ("케찹", "오뚜기 케첩", True),
        ("케찹", "하인즈 케찹", True),
        ("고추가루", "태양초 고춧가루", True),
        ("고추가루", "굵은 고춧가루", True),
        ("후추", "후춧가루", True),
        ("후추", "오뚜기 후춧가루", True),
        ("후추", "통후추", True),
        # 소금/깨소금 예외는 staple_matches에서도 그대로
        ("소금", "깨소금", False),
        ("소금", "청정원 깨소금 50g", False),
        ("깨소금", "청정원 깨소금 50g", True),
        ("소금", "구운소금", True),
        # 이름 다듬기(2026-09-18): 기본 치즈→치즈, 뿌리는 치즈→파마산 치즈, 생선 종류→생선, 파스타면→파스타
        ("치즈", "슬라이스 치즈", True),
        ("치즈", "모짜렐라치즈", True),
        ("파마산 치즈", "파마산 치즈 가루", True),
        ("생선", "생선", True),
        ("파스타", "파스타면", True),
        ("파스타", "스파게티 파스타", True),
    ],
)
def test_staple_matches(staple, ingredient, expected):
    assert staple_matches(staple, ingredient) is expected


def test_staple_matches_synonym_is_not_global():
    # 케찹↔케첩은 필수품 전용 별칭이지 전역 SYNONYMS가 아니다 — names_match(레시피·영양 캐시 키 등에 쓰는 일반 매칭)는 그대로 다르다
    assert names_match("케찹", "오뚜기 케첩") is False
    assert staple_matches("케찹", "오뚜기 케첩") is True


def test_staple_matches_cheese_does_not_break_on_parmesan_staple():
    # "치즈"·"파마산 치즈" 둘 다 기본 필수품(2026-09-18) — 재고에 파마산 치즈만 있어도 "치즈"가 정방향(치즈 ⊆ 파마산 치즈)으로
    # 맞는 건 의도한 동작(치즈는 파마산 치즈의 상위어라 자연스럽다). 역방향(파마산 치즈가 치즈만으로 맞는 것)은 여러 낱말이라 안 된다.
    assert staple_matches("치즈", "파마산 치즈") is True
    assert staple_matches("파마산 치즈", "치즈") is False


@pytest.mark.parametrize(
    "name, word, expected",
    [
        ("청정원 순창 고추장 500g", "고추장", True),
        ("진간장 (500ml)", "간장", True),
        ("초고추장", "고추장", True),
        ("굴소스", "굴소스", True),
        ("고추장 불고기 500g", "고추장", False),
        ("간장 닭갈비", "간장", False),
        ("된장 삼겹살", "된장", False),
        ("굴소스 볶음밥", "굴소스", False),
        ("참치마요네즈 샐러드", "마요네즈", False),
    ],
)
def test_head_is(name, word, expected):
    assert head_is(name, word) is expected


def test_keyword_in_is_one_way():
    assert keyword_in("계란", "유정란 계란 10구")
    assert not keyword_in("유정란 계란", "계란")
    assert not keyword_in("", "계란")


def test_tokens_split_words_without_parentheses():
    assert tokens("유정란 계란 (특란) 10구") == ["유정란", "달걀", "10구"]  # 동의어는 한 표기로
    assert tokens("[컬리] 무농약 대파/1단") == ["컬리", "무농약", "대파", "1단"]
    assert tokens("대파(국산)1단") == ["대파", "1단"]


@pytest.mark.parametrize(
    "a, b",
    [
        ("파김", "파 김"),
        ("간장", "진간장"),
        ("대파", "청양고추"),
        ("돼지고기", "돼지고기 앞다리살"),
    ],
)
def test_names_match_is_symmetric(a, b):
    assert names_match(a, b) == names_match(b, a)


@pytest.mark.parametrize(
    "keyword, name, expected",
    [
        ("빵", "식빵", True),
        ("빵", "빵가루", False),
        ("햄", "햄버거", False),
        ("두부", "순두부", True),
        ("주스", "오렌지주스 (1L)", True),
        ("소시지", "비엔나소시지", True),
    ],
)
def test_keyword_in_short_keywords(keyword, name, expected):
    assert keyword_in(keyword, name) is expected
