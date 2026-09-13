import pytest

from app.matching import keyword_in, names_match, normalize


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
    ],
)
def test_names_match(a, b, expected):
    assert names_match(a, b) is expected


def test_keyword_in_is_one_way():
    assert keyword_in("계란", "유정란 계란 10구")
    assert not keyword_in("유정란 계란", "계란")
    assert not keyword_in("", "계란")
