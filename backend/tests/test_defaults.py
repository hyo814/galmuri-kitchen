import importlib.util
from pathlib import Path

from app.defaults import DEFAULT_STAPLES

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
