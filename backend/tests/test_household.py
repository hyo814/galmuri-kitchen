import pytest

from app.household import is_household


@pytest.mark.parametrize("name", ["수세미", "두루마리 휴지", "주방세제", "쿠킹호일", "랩", "고무장갑(대)", "키친 타월", "Pororo 칫솔", "화장지 30롤", "미용티슈", "키친타올", "종이컵", "크린랩", "위생랩", "비닐랩"])
def test_household_names(name):
    assert is_household(name)


@pytest.mark.parametrize("name", ["두부", "크랩", "랩어라운드 샐러드", "대파", "비엔나소시지", "우유", "수세미오이", "호일빵", "감자 호일구이", "행주산성 막걸리"])
def test_food_names(name):
    assert not is_household(name)
