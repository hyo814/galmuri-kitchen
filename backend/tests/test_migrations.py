from pathlib import Path

import sqlalchemy as sa
from flask_migrate import downgrade, upgrade

from app import create_app
from app.models import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


def migration_app(tmp_path, monkeypatch):
    # Alembic env.py의 fileConfig가 기존 로거(app 등)를 꺼 버려 다른 테스트의 caplog를 망가뜨리지 않도록 막는다
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    return create_app(
        {"TESTING": True, "SECRET_KEY": "t", "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'migrate.sqlite3'}"}
    )


def test_location_migration_moves_existing_ingredients_to_fridge(tmp_path, monkeypatch):
    app = migration_app(tmp_path, monkeypatch)
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
