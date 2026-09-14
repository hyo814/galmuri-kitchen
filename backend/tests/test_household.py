import pytest

from app.household import is_household


@pytest.mark.parametrize("name", ["수세미", "두루마리 휴지", "주방세제", "쿠킹호일", "랩", "고무장갑(대)", "키친 타월", "Pororo 칫솔"])
def test_household_names(name):
    assert is_household(name)


@pytest.mark.parametrize("name", ["두부", "크랩", "랩어라운드 샐러드", "대파", "비엔나소시지", "우유"])
def test_food_names(name):
    assert not is_household(name)
