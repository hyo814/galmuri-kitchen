import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from flask_migrate import downgrade, upgrade

from app import create_app, database_url
from app.models import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")

MIGRATE_DATABASE_URL = os.environ.get("TEST_MIGRATE_DATABASE_URL")


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Alembic env.py의 fileConfig가 기존 로거(app 등)를 꺼 버려 다른 테스트의 caplog를 망가뜨리지 않도록 막는다
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    if MIGRATE_DATABASE_URL:
        uri = database_url(MIGRATE_DATABASE_URL)
    else:
        uri = f"sqlite:///{tmp_path / 'migrate.sqlite3'}"
    flask_app = create_app({"TESTING": True, "SECRET_KEY": "t", "SQLALCHEMY_DATABASE_URI": uri})
    if MIGRATE_DATABASE_URL:
        # Postgres DB is shared across the whole run — drop everything
        # (including alembic_version) before each test starts from base.
        with flask_app.app_context():
            db.drop_all()
            with db.engine.begin() as conn:
                conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    yield flask_app
    # Dispose the Postgres engine explicitly so connections don't leak
    # across tests (SQLite is unaffected — it's a fresh file per test).
    with flask_app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_location_migration_moves_existing_ingredients_to_fridge(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="69204259dd5d")
        with db.engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, provider, provider_id, nickname, created_at) "
                    "VALUES (1, 'test', '1', 'u', '2026-09-01 00:00:00')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO ingredients (user_id, name, quantity, unit, purchased_on, created_at) "
                    "VALUES (1, '우유', 1, '개', '2026-09-10', '2026-09-10 00:00:00')"
                )
            )

        upgrade(directory=MIGRATIONS, revision="a1b1c1d1e1f1")

        with db.engine.connect() as conn:
            locations = conn.execute(
                sa.text("SELECT name, kind FROM storage_locations WHERE user_id = 1 ORDER BY sort_order")
            ).all()
            moved_to = conn.execute(
                sa.text("SELECT l.name FROM ingredients i JOIN storage_locations l ON l.id = i.location_id")
            ).scalar_one()
        assert [tuple(r) for r in locations] == [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]
        assert moved_to == "냉장실"

        downgrade(directory=MIGRATIONS, revision="69204259dd5d")


def test_item_rules_migration_seeds_existing_users(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a2b2c2d2e2f2")
        with db.engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, provider, provider_id, nickname, created_at) "
                    "VALUES (1, 'test', '1', 'u', '2026-09-01 00:00:00')"
                )
            )

        upgrade(directory=MIGRATIONS, revision="a3b3c3d3e3f3")

        with db.engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT keyword, warn_days, danger_days FROM item_rules WHERE user_id = 1")
            ).all()
        assert len(rows) == 10
        assert ("계란", 25, 30) in [tuple(r) for r in rows]


def test_ai_calls_migration_adds_and_removes_table_and_indexes(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a4b4c4d4e4f4")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert "ai_calls" not in tables

        upgrade(directory=MIGRATIONS, revision="a5b5c5d5e5f5")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            tables = set(inspector.get_table_names())
            index_names = {ix["name"] for ix in inspector.get_indexes("ai_calls")}
        assert "ai_calls" in tables
        assert {"ix_ai_calls_created_at", "ix_ai_calls_user_id"} <= index_names

        downgrade(directory=MIGRATIONS, revision="a4b4c4d4e4f4")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert "ai_calls" not in tables


def test_recipes_migration_adds_and_removes_tables(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a5b5c5d5e5f5")
        upgrade(directory=MIGRATIONS, revision="a6b6c6d6e6f6")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            tables = set(inspector.get_table_names())
            recipe_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("recipes")}
            public_uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("public_recipes")}
        assert {"recipes", "public_recipes"} <= tables
        assert recipe_fks == {"users": "CASCADE", "public_recipes": "SET NULL"}
        assert ("rcp_seq",) in public_uniques

        downgrade(directory=MIGRATIONS, revision="a5b5c5d5e5f5")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert not {"recipes", "public_recipes"} & tables


def test_ai_call_tokens_migration_adds_and_removes_columns(app):
    token_columns = {"model", "input_tokens", "output_tokens"}
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a7b7c7d7e7f7")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("ai_calls")}
        assert token_columns <= columns

        downgrade(directory=MIGRATIONS, revision="a6b6c6d6e6f6")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("ai_calls")}
        assert not token_columns & columns


def test_upgrade_to_head_and_back_to_base(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert {
            "users",
            "ingredients",
            "storage_locations",
            "staples",
            "item_rules",
            "kitchen_tools",
            "ai_calls",
            "public_recipes",
            "recipes",
        } <= tables
        downgrade(directory=MIGRATIONS, revision="base")
