import pytest

from app.recipe_parse import MAX_INGREDIENTS, ingredient_key, parse_ingredients, parse_servings, split_steps


def pairs(text, title=""):
    return [(i["name"], i["amount"]) for i in parse_ingredients(text, title)]


def test_parses_dish_title_line_and_section_header():
    # 식약처 COOKRCP01 RCP_PARTS_DTLS 모양: 첫 줄은 요리 이름, 중간에 "고명" 같은 제목 줄
    text = "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개)\n고명\n시금치 10g(3줄기)"
    assert pairs(text, "새우 두부 계란찜") == [
        ("연두부", "75g(3/4모)"),
        ("칵테일새우", "20g(5마리)"),
        ("달걀", "30g(1/2개)"),
        ("시금치", "10g(3줄기)"),
    ]


def test_strips_bullets_labels_and_serving_brackets():
    text = (
        "[1인분]조선부추 50g, 날콩가루 7g(1⅓작은술)\n"
        "·양념장 : 저염간장 3g(2/3작은술), 다진 마늘 2g(1/2쪽), 참깨 약간\n"
        "●주재료 :\n두부 1/2모(150g)\n[양념장]\n고춧가루 1작은술(5g)"
    )
    assert pairs(text) == [
        ("조선부추", "50g"),
        ("날콩가루", "7g(1⅓작은술)"),
        ("저염간장", "3g(2/3작은술)"),
        ("다진 마늘", "2g(1/2쪽)"),
        ("참깨", "약간"),
        ("두부", "1/2모(150g)"),
        ("고춧가루", "1작은술(5g)"),
    ]


def test_dish_name_suffix_line_is_dropped():
    assert pairs("북엇국\n북어채 25g(15개), 물 300ml(1½컵)", "사과 새우 북엇국") == [
        ("북어채", "25g(15개)"),
        ("물", "300ml(1½컵)"),
    ]


@pytest.mark.parametrize(
    "item, expected",
    [
        ("돼지고기 200g", ("돼지고기", "200g")),
        ("소금 약간", ("소금", "약간")),
        ("다진 마늘 1작은술(5g)", ("다진 마늘", "1작은술(5g)")),
        ("두부 1/2모(150g)", ("두부", "1/2모(150g)")),
        ("7분도쌀 100g", ("7분도쌀", "100g")),
        ("오메가3 달걀 2개", ("오메가3 달걀", "2개")),
        ("대파1대", ("대파", "1대")),
        ("대파½대", ("대파", "½대")),  # R3: 붙어 쓴 양이 분수 글리프로 시작해도 잘라낸다
        ("½큰술 참기름", ("½큰술 참기름", "")),  # 이름이 없으면 확신이 없으니 통째로 이름
        ("후추", ("후추", "")),
        ("소금(1g, 약간)", ("소금(1g, 약간)", "")),  # 괄호 안 쉼표로 나누지 않는다
    ],
)
def test_splits_trailing_amount(item, expected):
    assert pairs(item) == [expected]


@pytest.mark.parametrize("marker", ["적당량", "적당히", "조금", "소량", "취향껏"])
def test_splits_word_amount_markers(marker):
    assert pairs(f"소금 {marker}") == [("소금", marker)]


def test_long_item_skips_regex_and_finishes_quickly():
    # R2: _SPACED/_ATTACHED의 역추적 최악의 경우를 피하려 200자 넘는 항목은 정규식 없이 통째로 이름으로 둔다
    import time

    text = "가1" + "." * 5000 + " "
    start = time.perf_counter()
    result = parse_ingredients(text)
    assert time.perf_counter() - start < 0.2
    assert len(result) == 1


def test_drops_empty_dedupes_and_caps():
    assert pairs("대파 1대,, 대파 2대,\n 양파 1개 ,") == [("대파", "1대"), ("양파", "1개")]
    many = ", ".join(f"재료{i} 1개" for i in range(80))
    assert len(parse_ingredients(many)) == MAX_INGREDIENTS
    long = parse_ingredients("가" * 70 + " " + "1" * 40 + "g")[0]
    assert (len(long["name"]), len(long["amount"])) == (50, 30)
    assert parse_ingredients(None) == [] and parse_ingredients("") == []


def test_split_steps_strips_numbers_and_trailing_marks():
    row = {
        "MANUAL01": "1. 손질된 새우를 끓는 물에 데쳐 건진다.a",
        "MANUAL02": "2. 연두부와 달걀을 믹서에 간다.b\n",
        "MANUAL03": "",
        "MANUAL04": "  ",
        "MANUAL05": "5. 1.5컵의 물을 붓고 끓인다.",
        "MANUAL20": "10분 정도 찐다.",
        "MANUAL21": "21번째는 없는 칸이다.",
    }
    assert split_steps(row) == ["손질된 새우를 끓는 물에 데쳐 건진다.", "연두부와 달걀을 믹서에 간다.", "1.5컵의 물을 붓고 끓인다.", "10분 정도 찐다."]


@pytest.mark.parametrize(
    "text, expected",
    [("[1인분]조선부추 50g", 1), ("재료(4인분) 감자 2개", 4), ("감자 2개", 2), ("[40인분] 쌀", 2), (None, 2)],
)
def test_parse_servings(text, expected):
    assert parse_servings(text) == expected


def test_ingredient_key_is_lowercase_words_without_parentheses():
    assert ingredient_key("유정란 계란 (특란)") == "유정란 달걀"  # 동의어는 한 표기로(matching.SYNONYMS)
    assert ingredient_key("Egg/Milk") == "egg milk"
    assert ingredient_key("대파1대") == "대파 1대"
