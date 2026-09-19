import importlib.util
from pathlib import Path

from app.defaults import DEFAULT_STAPLES, DEFAULT_TOOLS

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
