import pytest

from app.matching import keyword_in, names_match, normalize, tokens


def test_normalize_drops_parentheses_spaces_and_case():
    assert normalize(" 진 간장 (500ml) ") == "진간장"
    assert normalize("Egg 10구") == "egg10구"


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
    ],
)
def test_names_match(a, b, expected):
    assert names_match(a, b) is expected


def test_keyword_in_is_one_way():
    assert keyword_in("계란", "유정란 계란 10구")
    assert not keyword_in("유정란 계란", "계란")
    assert not keyword_in("", "계란")


def test_tokens_split_words_without_parentheses():
    assert tokens("유정란 계란 (특란) 10구") == ["유정란", "계란", "10구"]
    assert tokens("[컬리] 무농약 대파/1단") == ["컬리", "무농약", "대파", "1단"]


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
