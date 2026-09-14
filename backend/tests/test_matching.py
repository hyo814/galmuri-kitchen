import pytest

from app.matching import head_is, keyword_in, names_match, normalize, tokens


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
    ],
)
def test_names_match(a, b, expected):
    assert names_match(a, b) is expected


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
