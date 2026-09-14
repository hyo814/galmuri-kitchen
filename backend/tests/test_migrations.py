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


def test_ingredient_price_migration_adds_and_removes_column(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a8b8c8d8e8f8")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("ingredients")}
        assert "price" in columns

        downgrade(directory=MIGRATIONS, revision="a7b7c7d7e7f7")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("ingredients")}
        assert "price" not in columns


def test_seasonings_migration_adds_and_removes_table(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="b1b1c1d1e1f1")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("seasonings")}
            uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("seasonings")}
            index_names = {ix["name"] for ix in inspector.get_indexes("seasonings")}
        assert fks == {"users": "CASCADE"}
        assert ("user_id", "name") in uniques
        assert "ix_seasonings_user_id" in index_names

        downgrade(directory=MIGRATIONS, revision="a8b8c8d8e8f8")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert "seasonings" not in tables


def test_youtube_videos_migration_adds_and_removes_tables(app):
    tables = {"youtube_channels", "user_channels", "youtube_videos"}
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="b2b2c2d2e2f2")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            assert tables <= set(inspector.get_table_names())
            uniques = {
                table: {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)} for table in tables
            }
            user_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("user_channels")}
            video_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("youtube_videos")}
            video_indexes = {ix["name"] for ix in inspector.get_indexes("youtube_videos")}
        assert ("channel_id",) in uniques["youtube_channels"]
        assert ("user_id", "channel_id") in uniques["user_channels"]
        assert ("video_id",) in uniques["youtube_videos"]
        assert user_fks == {"users": "CASCADE", "youtube_channels": "CASCADE"}
        assert video_fks == {"youtube_channels": "CASCADE"}
        assert {"ix_youtube_videos_channel_id", "ix_youtube_videos_fetched_at", "ix_youtube_videos_published_at_id"} <= video_indexes

        downgrade(directory=MIGRATIONS, revision="b1b1c1d1e1f1")
        with db.engine.connect() as conn:
            assert not tables & set(sa.inspect(conn).get_table_names())


def test_ingredient_removals_migration_adds_and_removes_table(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="b3b3c3d3e3f3")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("ingredient_removals")}
            indexes = {ix["name"]: ix["column_names"] for ix in inspector.get_indexes("ingredient_removals")}
        assert fks == {"users": "CASCADE"}
        assert indexes["ix_ingredient_removals_user_id"] == ["user_id"]
        assert indexes["ix_ingredient_removals_user_id_created_at"] == ["user_id", "created_at"]

        downgrade(directory=MIGRATIONS, revision="b2b2c2d2e2f2")
        with db.engine.connect() as conn:
            assert "ingredient_removals" not in sa.inspect(conn).get_table_names()


def test_shopping_items_migration_adds_and_removes_table(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="b4b4c4d4e4f4")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            columns = {c["name"] for c in inspector.get_columns("shopping_items")}
            fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("shopping_items")}
            uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("shopping_items")}
            index_names = {ix["name"] for ix in inspector.get_indexes("shopping_items")}
        assert columns == {
            "id", "user_id", "client_id", "name", "quantity", "unit", "planned_on", "location_id", "source",
            "source_label", "done_at", "done_changed_at", "stocked_at", "created_at",
        }
        assert fks == {"users": "CASCADE", "storage_locations": "SET NULL"}
        assert ("user_id", "client_id") in uniques
        assert {"ix_shopping_items_user_id", "ix_shopping_items_location_id"} <= index_names

        downgrade(directory=MIGRATIONS, revision="b3b3c3d3e3f3")
        with db.engine.connect() as conn:
            assert "shopping_items" not in sa.inspect(conn).get_table_names()


def test_shopping_notes_migration_adds_and_removes_tables(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="b5b5c5d5e5f5")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            note_columns = {c["name"] for c in inspector.get_columns("shopping_notes")}
            photo_columns = {c["name"] for c in inspector.get_columns("shopping_note_photos")}
            note_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("shopping_notes")}
            photo_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("shopping_note_photos")}
            note_uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("shopping_notes")}
            photo_uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("shopping_note_photos")}
            indexes = {ix["name"] for ix in inspector.get_indexes("shopping_notes") + inspector.get_indexes("shopping_note_photos")}
        assert note_columns == {"id", "user_id", "client_id", "place", "body", "created_at", "updated_at"}
        assert photo_columns == {"id", "note_id", "client_id", "photo_key", "size", "created_at"}
        assert note_fks == {"users": "CASCADE"}
        assert photo_fks == {"shopping_notes": "CASCADE"}
        assert ("user_id", "client_id") in note_uniques
        assert {("note_id", "client_id"), ("photo_key",)} <= photo_uniques
        assert {"ix_shopping_notes_user_id", "ix_shopping_note_photos_note_id"} <= indexes

        downgrade(directory=MIGRATIONS, revision="b4b4c4d4e4f4")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert not {"shopping_notes", "shopping_note_photos"} & tables


def test_ai_calls_keep_history_migration(app):
    def ai_calls_shape(conn):
        inspector = sa.inspect(conn)
        columns = {c["name"]: c for c in inspector.get_columns("ai_calls")}
        fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("ai_calls")}
        index_names = {ix["name"] for ix in inspector.get_indexes("ai_calls")}
        return columns, fks, index_names

    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="b5b5c5d5e5f5")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'demo', 'x', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO ai_calls (user_id, kind, created_at) VALUES (1, 'recipe', CURRENT_TIMESTAMP)"))

        upgrade(directory=MIGRATIONS, revision="c1d1e1m1o1a1")
        with db.engine.connect() as conn:
            columns, fks, index_names = ai_calls_shape(conn)
        assert columns["user_id"]["nullable"] is True
        assert columns["demo"]["nullable"] is False
        assert fks == {"users": "SET NULL"}
        assert {"ix_ai_calls_created_at", "ix_ai_calls_user_id"} <= index_names
        with db.engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.execute(sa.text("PRAGMA foreign_keys=ON"))
            conn.execute(sa.text("DELETE FROM users"))
            assert conn.execute(sa.text("SELECT user_id, demo FROM ai_calls")).all() == [(None, False)]

        downgrade(directory=MIGRATIONS, revision="b5b5c5d5e5f5")
        with db.engine.connect() as conn:
            columns, fks, _ = ai_calls_shape(conn)
            assert conn.execute(sa.text("SELECT COUNT(*) FROM ai_calls")).scalar() == 0
        assert "demo" not in columns and columns["user_id"]["nullable"] is False
        assert fks == {"users": "CASCADE"}


def test_shopping_items_household_migration(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="c1d1e1m1o1a1")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'test', '1', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO shopping_items (user_id, name, quantity, unit, source, created_at) VALUES (1, '휴지', 1, '개', 'manual', CURRENT_TIMESTAMP)"))

        upgrade(directory=MIGRATIONS, revision="c2h2o2u2s2e2")
        with db.engine.connect() as conn:
            columns = {c["name"]: c for c in sa.inspect(conn).get_columns("shopping_items")}
            assert conn.execute(sa.text("SELECT household FROM shopping_items")).scalar_one() in (False, 0)  # 이미 있던 항목은 식품으로
        assert columns["household"]["nullable"] is False

        downgrade(directory=MIGRATIONS, revision="c1d1e1m1o1a1")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("shopping_items")}
            assert conn.execute(sa.text("SELECT COUNT(*) FROM shopping_items")).scalar() == 1
        assert "household" not in columns


def test_meal_plans_migration_adds_and_removes_tables(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="d1m1e1a1l1s1")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            plan_columns = {c["name"] for c in inspector.get_columns("meal_plans")}
            slot_columns = {c["name"] for c in inspector.get_columns("meal_slots")}
            plan_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("meal_plans")}
            slot_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("meal_slots")}
            slot_uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("meal_slots")}
            index_names = {ix["name"] for ix in inspector.get_indexes("meal_plans") + inspector.get_indexes("meal_slots")}
        assert plan_columns == {
            "id", "user_id", "name", "start_on", "days", "default_servings", "goal_kcal", "goal_note", "created_at", "updated_at",
        }
        assert slot_columns == {
            "id", "plan_id", "date", "meal", "recipe_id", "title", "servings", "est_kcal", "created_at",
        }
        assert plan_fks == {"users": "CASCADE"}
        assert slot_fks == {"meal_plans": "CASCADE", "recipes": "SET NULL"}
        assert ("plan_id", "date", "meal") in slot_uniques
        assert {"ix_meal_plans_user_id", "ix_meal_slots_plan_id", "ix_meal_slots_recipe_id"} <= index_names

        downgrade(directory=MIGRATIONS, revision="c2h2o2u2s2e2")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert not {"meal_plans", "meal_slots"} & tables


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
            "seasonings",
            "youtube_channels",
            "user_channels",
            "youtube_videos",
            "ingredient_removals",
            "shopping_items",
            "shopping_notes",
            "shopping_note_photos",
            "meal_plans",
            "meal_slots",
        } <= tables
        downgrade(directory=MIGRATIONS, revision="base")
