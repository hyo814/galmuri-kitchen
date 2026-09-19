import pytest
import importlib.util
from pathlib import Path

from app.defaults import DEFAULT_RULES, DEFAULT_STAPLES, DEFAULT_TOOLS

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "h5s5t5a5p5l5e5_default_staples.py"


def test_new_user_gets_default_staples(client, login):
    """모든 사용자 필수품(사용자 결정 2026-09-17) — 로그인만 해도 72개가 분류별로 생긴다."""
    login()
    rows = client.get("/api/staples").get_json()
    assert {(r["name"], r["category"]) for r in rows} == set(DEFAULT_STAPLES)
    assert len(rows) == len(DEFAULT_STAPLES) == 72


def test_seasoning_category_staples_default_to_out_of_stock_not_deducted():
    # 조미료 분류 필수품은 요리 시 기본 "차감 안 함"(스펙 14절): staples.py CATEGORY_ORDER가 조미료를 아는지만 확인
    from app.staples import CATEGORY_ORDER

    assert "조미료" in CATEGORY_ORDER
    seasoning_names = {name for name, category in DEFAULT_STAPLES if category == "조미료"}
    assert len(seasoning_names) == 40


def test_migration_defaults_match_app_defaults():
    # 마이그레이션에 고정해 둔 값이 app.defaults와 같은지(위 storage_locations·item_rules 마이그레이션 테스트와 같은 패턴).
    # 앞으로 기본 필수품을 바꾸면 이 테스트가 실패한다 — 그때는 이 마이그레이션을 고치지 않고 새 마이그레이션을 추가한다.
    spec = importlib.util.spec_from_file_location("default_staples_migration", MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.DEFAULT_STAPLES == DEFAULT_STAPLES


def test_default_staple_names_unique():
    names = [name for name, _ in DEFAULT_STAPLES]
    assert len(names) == len(set(names))


TOOLS_MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "h6t6o6o6l6s6_default_tools.py"


def test_new_user_gets_default_tools(client, login):
    """모든 사용자 주방 도구(사용자 결정 2026-09-19) — 로그인만 해도 13개가 분류별로 생긴다."""
    login()
    rows = client.get("/api/tools").get_json()
    assert {(r["name"], r["category"]) for r in rows} == {(name, category) for name, category, _ in DEFAULT_TOOLS}
    assert len(rows) == len(DEFAULT_TOOLS) == 13


def test_default_tools_are_not_due_right_after_signup(client, login):
    # 가입 직후 `점검할 때` 뱃지가 하나도 뜨면 안 된다 — 없는 도구의 점검 알림을 막으려고 주기를 비워 뒀고,
    # 주기가 있는 프라이팬도 bought_on·last_checked_on이 비어 기준일이 만든 날이라 6개월 뒤에야 뜬다.
    login()
    rows = client.get("/api/tools").get_json()
    assert [r["name"] for r in rows if r["is_due"]] == []
    assert [r["name"] for r in rows if r["check_every_months"]] == ["프라이팬"]


def test_default_tool_categories_are_known():
    from app.tools import CATEGORIES

    assert {category for _, category, _ in DEFAULT_TOOLS} <= set(CATEGORIES)


def test_tools_migration_defaults_match_app_defaults():
    # 필수품과 같은 패턴 — 기본 도구를 바꾸면 이 테스트가 실패한다. 그때는 이 마이그레이션을 고치지 않고 새 마이그레이션을 추가한다.
    spec = importlib.util.spec_from_file_location("default_tools_migration", TOOLS_MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.DEFAULT_TOOLS == DEFAULT_TOOLS


def test_default_tool_names_unique():
    names = [name for name, _, _ in DEFAULT_TOOLS]
    assert len(names) == len(set(names))


RULES_MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "h7r7u7l7e7s7_more_mfds_rules.py"


def test_processed_milk_and_lactic_drink_rules(client, login):
    """식약처 1차 공개분 나머지 둘(가공유 24일·유산균음료 26일, 2026-09-19) — 실제로 적는 이름에 붙였다."""
    login()
    rules = {r["keyword"]: (r["warn_days"], r["danger_days"]) for r in client.get("/api/item-rules").get_json()}
    for name in ("딸기우유", "초코우유", "바나나우유"):
        assert rules[name] == (16, 19)  # 24일의 80% 내림 = 19, 그 3일 전 = 16
    assert rules["야쿠르트"] == (17, 20)  # 26일의 80% 내림 = 20


def test_plain_milk_still_has_no_rule():
    # 우유는 소비기한 표시제가 2031년 적용이라 참고값이 없다 — 규칙을 만들지 않는다(포장 날짜 입력 안내).
    assert "우유" not in {keyword for keyword, _, _, _ in DEFAULT_RULES}


FRESH_MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "h8f8i8s8h8_fresh_food_rules.py"


def _migration(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contiguous_index(rules, block):
    """block이 rules 안에 순서 그대로 이어져 있는 시작 위치(없으면 -1)."""
    for i in range(len(rules) - len(block) + 1):
        if rules[i : i + len(block)] == block:
            return i
    return -1


@pytest.mark.parametrize(
    ("name", "path_name"),
    [("more_mfds_rules_migration", "RULES"), ("fresh_food_rules_migration", "FRESH")],
)
def test_rules_migrations_match_app_defaults(name, path_name):
    # 각 마이그레이션이 넣은 줄이 app.defaults에 순서 그대로 남아 있는지. 기본값을 바꾸면 여기서 실패한다 —
    # 그때는 배포된 마이그레이션을 고치는 게 아니라 새 마이그레이션을 추가한다.
    path = {"RULES": RULES_MIGRATION_PATH, "FRESH": FRESH_MIGRATION_PATH}[path_name]
    assert _contiguous_index(DEFAULT_RULES, _migration(name, path).NEW_RULES) >= 0


# --- 신선 수산물·김치 규칙 (사용자 결정 2026-09-20) ---


def test_short_seafood_keywords_do_not_catch_seasonings_or_snacks():
    """한 글자·두 글자 키워드는 그 낱말로 끝날 때만 맞는다(matching.keyword_in) — 굴소스·새우깡이 상한 것으로 보이면 안 된다."""
    from app.ingredients import matching_rule

    class R:
        def __init__(self, i, keyword, warn, danger):
            self.id, self.keyword, self.warn_days, self.danger_days = i, keyword, warn, danger

    rules = [R(i, k, w, d) for i, (k, w, d, _) in enumerate(DEFAULT_RULES)]
    assert matching_rule("굴", rules) == (4, 5)
    assert matching_rule("생굴", rules) == (4, 5)
    assert matching_rule("굴소스", rules) is None
    assert matching_rule("새우", rules) == (2, 3)
    assert matching_rule("새우깡", rules) is None
    assert matching_rule("배추김치", rules) == (75, 90)
    assert matching_rule("김치찌개", rules) is None


def test_frozen_seafood_has_no_rule_warning():
    """냉동은 품목 규칙을 쓰지 않는다(ingredient_status) — 얼려 둔 생선에 `상했을 수 있어요`가 뜨면 안 된다."""
    from datetime import timedelta

    from app.ingredients import ingredient_status, seoul_today

    today = seoul_today()
    bought = today - timedelta(days=5)
    assert ingredient_status(bought, None, today, kind="fridge", rule=(1, 2)) == "danger"
    assert ingredient_status(bought, None, today, kind="freezer", rule=(1, 2)) == "ok"  # 냉동 60일 기준


def test_kimchi_rule_replaces_the_seven_day_fridge_default():
    """규칙이 없으면 김치가 냉장 `오래됨` 7일에 걸린다 — 3개월 규칙이 그걸 고친다."""
    from datetime import timedelta

    from app.ingredients import ingredient_status, seoul_today

    today = seoul_today()
    bought = today - timedelta(days=30)
    assert ingredient_status(bought, None, today, kind="fridge", rule=None) == "old"
    assert ingredient_status(bought, None, today, kind="fridge", rule=(75, 90)) == "ok"


def test_fresh_rule_sources_are_labelled_agencies():
    # 화면이 출처 이름을 꼬리표로 보여 준다(RulesSheet.tsx SOURCE_LABEL) — 기관을 섞어 적으면 출처를 잘못 밝히게 된다.
    by_keyword = {keyword: source for keyword, _, _, source in DEFAULT_RULES}
    assert {by_keyword[k] for k in ("생선", "오징어", "새우", "조개", "가리비", "굴")} == {"nfqs"}
    assert by_keyword["김치"] == "rda"
    assert by_keyword["두부"] == "mfds"
