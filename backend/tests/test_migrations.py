import os
from datetime import date
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


def test_body_profiles_migration_adds_and_removes_table(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="f1b1o1d1y1p1")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            columns = {c["name"] for c in inspector.get_columns("body_profiles")}
            fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("body_profiles")}
            uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("body_profiles")}
        assert columns == {
            "id", "user_id", "sex", "birth_year", "height_cm", "weight_kg", "activity", "goal", "updated_at",
        }
        assert fks == {"users": "CASCADE"}
        assert ("user_id",) in uniques

        downgrade(directory=MIGRATIONS, revision="e1p1u1r1c1h1")
        with db.engine.connect() as conn:
            tables = set(sa.inspect(conn).get_table_names())
        assert "body_profiles" not in tables


def test_food_tables_migration_adds_and_removes_tables(app):
    tables = {"food_nutrients", "food_searches", "food_matches", "unit_weight_estimates"}
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="f1b1o1d1y1p1")
        upgrade(directory=MIGRATIONS, revision="f2f2o2o2d2s2")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            assert tables <= set(inspector.get_table_names())
            nutrient_columns = {c["name"] for c in inspector.get_columns("food_nutrients")}
            search_columns = {c["name"] for c in inspector.get_columns("food_searches")}
            match_columns = {c["name"] for c in inspector.get_columns("food_matches")}
            estimate_columns = {c["name"] for c in inspector.get_columns("unit_weight_estimates")}
            match_fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("food_matches")}
            uniques = {
                table: {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)} for table in tables
            }
            index_names = {ix["name"] for table in tables for ix in inspector.get_indexes(table)}
        assert nutrient_columns == {
            "id", "food_code", "name", "name_key", "group_name", "kcal", "carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg", "source", "fetched_at",
        }
        assert search_columns == {"id", "query_key", "total", "searched_at"}
        assert match_columns == {"id", "user_id", "ingredient_key", "food_code", "unit_grams", "updated_at"}
        assert estimate_columns == {"id", "name_key", "unit", "grams", "source", "created_at"}
        assert match_fks == {"users": "CASCADE"}
        assert ("food_code",) in uniques["food_nutrients"]
        assert ("query_key",) in uniques["food_searches"]
        assert ("user_id", "ingredient_key") in uniques["food_matches"]
        assert ("name_key", "unit") in uniques["unit_weight_estimates"]
        assert {"ix_food_nutrients_name_key", "ix_food_matches_user_id"} <= index_names

        downgrade(directory=MIGRATIONS, revision="f1b1o1d1y1p1")
        with db.engine.connect() as conn:
            assert not tables & set(sa.inspect(conn).get_table_names())


def test_food_serving_grams_migration(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="f2f2o2o2d2s2")
        with db.engine.begin() as conn:
            conn.execute(sa.text(
                "INSERT INTO food_searches (id, query_key, total, searched_at) VALUES (1, '두부', 1, '2026-09-15 00:00:00+00:00')"
            ))

        upgrade(directory=MIGRATIONS, revision="g1s1e1r1v1n1")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("food_nutrients")}
            searched_at = conn.execute(sa.text("SELECT searched_at FROM food_searches WHERE id = 1")).scalar_one()
        assert "serving_g" in columns
        assert str(searched_at).startswith("2000-01-01")

        downgrade(directory=MIGRATIONS, revision="f2f2o2o2d2s2")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("food_nutrients")}
        assert "serving_g" not in columns


def test_food_logs_migration_adds_and_removes_table(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="g2f2o2o2d2l2")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            columns = {c["name"] for c in inspector.get_columns("food_logs")}
            fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("food_logs")}
            uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("food_logs")}
            index_names = {ix["name"] for ix in inspector.get_indexes("food_logs")}
        assert columns == {
            "id", "user_id", "eaten_on", "meal", "source", "title", "recipe_id", "meal_slot_id", "food_code", "servings", "grams",
            "place", "rating", "memo", "kcal", "carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg", "approx",
            "nutrition_pending", "created_at", "updated_at",
        }
        assert fks == {"users": "CASCADE", "recipes": "SET NULL", "meal_slots": "SET NULL"}
        assert ("meal_slot_id",) in uniques
        assert {"ix_food_logs_recipe_id", "ix_food_logs_user_id_eaten_on"} <= index_names

        downgrade(directory=MIGRATIONS, revision="g1s1e1r1v1n1")
        with db.engine.connect() as conn:
            assert "food_logs" not in set(sa.inspect(conn).get_table_names())


def test_food_log_photos_migration_adds_and_removes_table(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="g3f3l3p3h3o3")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            columns = {c["name"] for c in inspector.get_columns("food_log_photos")}
            fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys("food_log_photos")}
            uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("food_log_photos")}
            index_names = {ix["name"] for ix in inspector.get_indexes("food_log_photos")}
        assert columns == {"id", "log_id", "photo_key", "size", "created_at"}
        assert fks == {"food_logs": "CASCADE"}
        assert ("photo_key",) in uniques
        assert "ix_food_log_photos_log_id" in index_names

        downgrade(directory=MIGRATIONS, revision="g2f2o2o2d2l2")
        with db.engine.connect() as conn:
            assert "food_log_photos" not in set(sa.inspect(conn).get_table_names())


def test_ingredients_purchased_on_nullable_migration(app):
    def purchased_on_nullable(conn):
        return {c["name"]: c for c in sa.inspect(conn).get_columns("ingredients")}["purchased_on"]["nullable"]

    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="d1m1e1a1l1s1")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'test', '1', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO storage_locations (id, user_id, name, kind, sort_order, created_at) VALUES (1, 1, '냉장실', 'fridge', 0, CURRENT_TIMESTAMP)"))
            conn.execute(sa.text(
                "INSERT INTO ingredients (id, user_id, location_id, name, quantity, unit, purchased_on, created_at) "
                "VALUES (1, 1, 1, '우유', 1, '개', '2026-09-01', '2026-09-10 20:00:00+00:00')"
            ))

        upgrade(directory=MIGRATIONS, revision="e1p1u1r1c1h1")
        with db.engine.begin() as conn:
            assert purchased_on_nullable(conn) is True
            assert conn.execute(sa.text("SELECT purchased_on FROM ingredients WHERE id = 1")).scalar_one() in (date(2026, 9, 1), "2026-09-01")
            conn.execute(sa.text(
                "INSERT INTO ingredients (id, user_id, location_id, name, quantity, unit, purchased_on, created_at) "
                "VALUES (2, 1, 1, '두부', 1, '모', NULL, '2026-09-10 20:00:00+00:00')"
            ))

        downgrade(directory=MIGRATIONS, revision="d1m1e1a1l1s1")
        with db.engine.connect() as conn:
            assert purchased_on_nullable(conn) is False
            rows = conn.execute(sa.text("SELECT id, purchased_on FROM ingredients ORDER BY id")).all()
        # 모르던 구입일은 넣은 날(서울 날짜)로 채운다: UTC 9/10 20시 = 서울 9/11
        assert [(i, str(d)) for i, d in rows] == [(1, "2026-09-01"), (2, "2026-09-11")]


def test_price_basis_migration(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="g3f3l3p3h3o3")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'test', '1', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO storage_locations (id, user_id, name, kind, sort_order, created_at) VALUES (1, 1, '냉장실', 'fridge', 0, CURRENT_TIMESTAMP)"))
            conn.execute(sa.text(
                "INSERT INTO ingredients (id, user_id, location_id, name, quantity, unit, price, created_at) "
                "VALUES (1, 1, 1, '깐마늘', 300, 'g', 4980, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text(
                "INSERT INTO ingredients (id, user_id, location_id, name, quantity, unit, price, created_at) "
                "VALUES (2, 1, 1, '대파', 2, '대', NULL, CURRENT_TIMESTAMP)"
            ))

        upgrade(directory=MIGRATIONS, revision="h1p1r1i1c1e1")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("recipes")}
            rows = conn.execute(sa.text("SELECT id, price_quantity FROM ingredients ORDER BY id")).all()
        assert {"eat_out_price", "eat_out_source"} <= columns
        assert [(i, pq) for i, pq in rows] == [(1, 300.0), (2, None)]

        downgrade(directory=MIGRATIONS, revision="g3f3l3p3h3o3")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("ingredients")}
            recipe_columns = {c["name"] for c in sa.inspect(conn).get_columns("recipes")}
        assert "price_quantity" not in columns
        assert not {"eat_out_price", "eat_out_source"} & recipe_columns


def test_cook_logs_migration_adds_and_removes_tables(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="h2c2o2o2k2l2")
        with db.engine.connect() as conn:
            inspector = sa.inspect(conn)
            columns = {t: {c["name"] for c in inspector.get_columns(t)} for t in ("cook_logs", "cook_log_items")}
            fks = {t: {fk["referred_table"]: fk["options"].get("ondelete") for fk in inspector.get_foreign_keys(t)} for t in columns}
            uniques = {tuple(u["column_names"]) for u in inspector.get_unique_constraints("cook_logs")}
            index_names = {ix["name"] for t in columns for ix in inspector.get_indexes(t)}
        assert columns["cook_logs"] == {
            "id", "user_id", "recipe_id", "food_log_id", "title", "cooked_on", "servings", "rating", "memo", "photo_key", "photo_size",
            "eat_out_price", "eat_out_source", "ingredient_cost", "saved", "excluded_count", "created_at", "updated_at",
        }
        assert columns["cook_log_items"] == {
            "id", "cook_log_id", "ingredient_id", "removal_id", "name", "amount_text", "used", "unit", "quantity_before", "removed",
            "location_id", "purchased_on", "expires_on", "price", "price_quantity", "cost", "excluded",
        }
        assert fks == {
            "cook_logs": {"users": "CASCADE", "recipes": "SET NULL", "food_logs": "SET NULL"},
            "cook_log_items": {"cook_logs": "CASCADE", "ingredients": "SET NULL", "ingredient_removals": "SET NULL"},
        }
        assert ("photo_key",) in uniques
        assert {
            "ix_cook_logs_recipe_id", "ix_cook_logs_food_log_id", "ix_cook_logs_user_id_cooked_on",
            "ix_cook_log_items_cook_log_id", "ix_cook_log_items_ingredient_id", "ix_cook_log_items_removal_id",
        } <= index_names

        downgrade(directory=MIGRATIONS, revision="h1p1r1i1c1e1")
        with db.engine.connect() as conn:
            assert not {"cook_logs", "cook_log_items"} & set(sa.inspect(conn).get_table_names())


def test_food_log_nutrition_incomplete_migration(app):
    """칸만 더하고 뺀다 — SQLite에서 food_logs를 다시 만들면(batch) 외래 키 CASCADE로 기록 사진이 지워지고 요리 일기 연결이 끊긴다."""

    def linked():
        with db.engine.connect() as conn:
            return (
                conn.execute(sa.text("SELECT COUNT(*) FROM food_log_photos WHERE log_id = 1")).scalar_one(),
                conn.execute(sa.text("SELECT food_log_id FROM cook_logs WHERE id = 1")).scalar_one(),
            )

    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="h2c2o2o2k2l2")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'test', '1', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text(
                "INSERT INTO food_logs (id, user_id, eaten_on, meal, source, title, kcal, sodium_mg, approx, nutrition_pending, created_at, updated_at) "
                "VALUES (1, 1, '2026-09-14', 'dinner', 'manual', '된장찌개', 165, 7, TRUE, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text(
                "INSERT INTO food_log_photos (id, log_id, photo_key, size, created_at) VALUES (1, 1, 'foodlog/1/a.jpg', 10, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text(
                "INSERT INTO cook_logs (id, user_id, food_log_id, title, cooked_on, servings, ingredient_cost, excluded_count, created_at, updated_at) "
                "VALUES (1, 1, 1, '된장찌개', '2026-09-14', 2, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))

        upgrade(directory=MIGRATIONS, revision="h3i3n3c3m3p3")
        with db.engine.connect() as conn:
            columns = {c["name"] for c in sa.inspect(conn).get_columns("food_logs")}
            kept = conn.execute(sa.text("SELECT nutrition_incomplete FROM food_logs")).scalar_one()
        assert "nutrition_incomplete" in columns
        assert kept is None  # 지난 스냅숏은 어떤 값이 빠졌는지 알 수 없어 비워 둔다
        assert linked() == (1, 1)

        downgrade(directory=MIGRATIONS, revision="h2c2o2o2k2l2")
        with db.engine.connect() as conn:
            assert "nutrition_incomplete" not in {c["name"] for c in sa.inspect(conn).get_columns("food_logs")}
            assert "ix_food_logs_user_id_eaten_on" in {ix["name"] for ix in sa.inspect(conn).get_indexes("food_logs")}
        assert linked() == (1, 1)

        upgrade(directory=MIGRATIONS, revision="h3i3n3c3m3p3")
        assert linked() == (1, 1)


def test_cook_log_manual_migration(app):
    """칸만 더하고 뺀다 — SQLite에서 cook_logs를 다시 만들면(batch) 외래 키 CASCADE로 쓴 재료 줄이 지워진다."""

    def items():
        with db.engine.connect() as conn:
            return conn.execute(sa.text("SELECT COUNT(*) FROM cook_log_items WHERE cook_log_id = 1")).scalar_one()

    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="h3i3n3c3m3p3")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'test', '1', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text(
                "INSERT INTO cook_logs (id, user_id, title, cooked_on, servings, ingredient_cost, excluded_count, created_at, updated_at) "
                "VALUES (1, 1, '김치찌개', '2026-09-14', 2, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            conn.execute(sa.text("INSERT INTO cook_log_items (id, cook_log_id, name, removed) VALUES (1, 1, '김치', FALSE)"))

        upgrade(directory=MIGRATIONS, revision="h4d4i4a4r4y4")
        with db.engine.begin() as conn:
            # 칸을 빼고 넣어도 false(server_default) — 지난 일기는 모두 레시피로 남긴 것
            conn.execute(sa.text(
                "INSERT INTO cook_logs (id, user_id, title, cooked_on, servings, ingredient_cost, excluded_count, created_at, updated_at) "
                "VALUES (2, 1, '된장찌개', '2026-09-15', 1, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))
            manual = conn.execute(sa.text("SELECT id, manual FROM cook_logs ORDER BY id")).all()
        assert [(i, bool(m)) for i, m in manual] == [(1, False), (2, False)]
        assert items() == 1

        downgrade(directory=MIGRATIONS, revision="h3i3n3c3m3p3")
        with db.engine.connect() as conn:
            assert "manual" not in {c["name"] for c in sa.inspect(conn).get_columns("cook_logs")}
            assert "ix_cook_logs_user_id_cooked_on" in {ix["name"] for ix in sa.inspect(conn).get_indexes("cook_logs")}
        assert items() == 1

        upgrade(directory=MIGRATIONS, revision="h4d4i4a4r4y4")
        assert items() == 1


def test_default_staples_migration_backfills_and_is_idempotent(app):
    """모든 사용자 필수품(사용자 결정 2026-09-17). 기존 사용자는 빠진 것만 채우고, 이미 만든 이름은 그대로 둔다(다시 돌려도 안전).
    had_stock("가졌던 것만 배너에"): 전부터 있던 행은 true, 새로 채운 행은 지금 재고와 맞으면 true 아니면 false."""
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="h4d4i4a4r4y4")
        with db.engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO users (id, provider, provider_id, nickname, created_at) VALUES (1, 'test', '1', 'u', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO storage_locations (id, user_id, name, kind, sort_order, created_at) VALUES (1, 1, '냉장실', 'fridge', 0, CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO ingredients (user_id, location_id, name, quantity, unit, created_at) VALUES (1, 1, '양파', 1, '개', CURRENT_TIMESTAMP)"))
            # 이미 만들어 둔 필수품 하나(기본값과 이름이 같음 — 백필이 건너뛰어야 함)와, 사용자가 직접 만든 필수품 하나(그대로 남아야 함)
            conn.execute(sa.text("INSERT INTO staples (user_id, name, category, created_at) VALUES (1, '대파', '야채', CURRENT_TIMESTAMP)"))
            conn.execute(sa.text("INSERT INTO staples (user_id, name, category, created_at) VALUES (1, '내가 만든 소스', '조미료', CURRENT_TIMESTAMP)"))

        upgrade(directory=MIGRATIONS, revision="h5s5t5a5p5l5e5")
        with db.engine.connect() as conn:
            rows = {n: bool(h) for n, h in conn.execute(sa.text("SELECT name, had_stock FROM staples WHERE user_id = 1")).all()}
        from app.defaults import DEFAULT_STAPLES

        names = set(rows)
        assert names == {name for name, _ in DEFAULT_STAPLES} | {"내가 만든 소스"}
        with db.engine.connect() as conn:
            assert conn.execute(sa.text("SELECT COUNT(*) FROM staples WHERE user_id = 1 AND name = '대파'")).scalar_one() == 1
        # 전부터 있던 행(사용자가 직접 만든 것)은 had_stock true
        assert rows["대파"] is True
        assert rows["내가 만든 소스"] is True
        # 새로 채운 기본 행: 지금 재고(양파)와 맞으면 true, 아니면(소금) false
        assert rows["양파"] is True
        assert rows["소금"] is False

        downgrade(directory=MIGRATIONS, revision="h4d4i4a4r4y4")
        with db.engine.connect() as conn:
            count_after_downgrade = conn.execute(sa.text("SELECT COUNT(*) FROM staples WHERE user_id = 1")).scalar_one()
            assert "had_stock" not in {c["name"] for c in sa.inspect(conn).get_columns("staples")}
        assert count_after_downgrade == len(names)  # downgrade는 행을 지우지 않는다(사용자 데이터 보존) — 칸만 없앤다

        # 다시 올려도(백필을 두 번 돌려도) 늘지 않는다
        upgrade(directory=MIGRATIONS, revision="h5s5t5a5p5l5e5")
        with db.engine.connect() as conn:
            count_after_rerun = conn.execute(sa.text("SELECT COUNT(*) FROM staples WHERE user_id = 1")).scalar_one()
        assert count_after_rerun == len(names)


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
