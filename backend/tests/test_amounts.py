import pytest

from app.amounts import in_unit, is_spoon, parse_amount


@pytest.mark.parametrize(
    "text, expected",
    [
        ("200g", (200.0, "g")),
        ("1/2모(150g)", (0.5, "모")),
        ("1½큰술", (1.5, "큰술")),
        ("두 개", (2.0, "개")),
        ("2", (2.0, "개")),
        ("1.5kg", (1500.0, "g")),
        ("1L", (1000.0, "ml")),
        ("약간", None),
        ("10~15개", None),
        ("", None),
        ("0개", None),
        ("1모", (1.0, "모")),
        ("½개", (0.5, "개")),
        ("2 1/2컵", (2.5, "컵")),
        ("1/2포기", (0.5, "포기")),
        ("한 줌", (1.0, "줌")),
        ("1세트", (1.0, "세트")),
        ("세트", None),
        ("적당량", None),
        ("100g-200g", None),
        ("1/0개", None),
        ("/2개", None),
        ("1/2½개", None),
        ("200 g", (200.0, "g")),
        ("1.5L", (1500.0, "ml")),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


def test_is_spoon():
    assert is_spoon("큰술") is True
    assert is_spoon("모") is False


@pytest.mark.parametrize(
    "amount_text, unit, expected",
    [
        ("300g", "g", 300.0),
        ("300g", "kg", 0.3),
        ("1.5kg", "g", 1500.0),
        ("1/2모", "모", 0.5),
        ("1L", "ml", 1000.0),
        ("200ml", "L", 0.2),
        ("2", "개", 2.0),
        ("1대", "단", None),
        ("약간", "g", None),
        ("300g", "", None),
        ("10개", "30구", None),
        ("1큰술", "큰술", 1.0),
        ("300g", "G", 300.0),
        ("1KG", "g", 1000.0),
    ],
)
def test_in_unit(amount_text, unit, expected):
    assert in_unit(amount_text, unit) == expected
