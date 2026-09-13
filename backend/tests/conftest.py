import os

import pytest

from app import create_app, database_url
from app.defaults import seed_user_defaults
from app.models import User, db

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")

TEST_CONFIG = {
    "TESTING": True,
    "SECRET_KEY": "test",
    "SQLALCHEMY_DATABASE_URI": database_url(TEST_DATABASE_URL),
    "DEV_MODE": True,
    "SESSION_COOKIE_SECURE": False,
    "ANTHROPIC_API_KEY": None,  # 셸에 키가 있어도 테스트는 예시 모드로 시작한다
}


@pytest.fixture
def make_app():
    apps = []

    def _make(**overrides):
        app = create_app({**TEST_CONFIG, **overrides})
        with app.app_context():
            # Postgres DB is shared across the whole run (unlike sqlite://,
            # a fresh in-memory DB per app) — reset it so tests stay isolated.
            if not TEST_DATABASE_URL.startswith("sqlite"):
                db.drop_all()
            db.create_all()
        apps.append(app)
        return app

    yield _make

    # Postgres connections aren't closed by garbage collection alone; dispose
    # each app's engine explicitly so the pool doesn't leak across tests.
    for app in apps:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def app(make_app):
    # No app_context held here: Flask must push/pop a fresh request+app context
    # (and therefore a fresh db.session) per test-client request, the same as
    # in production. Holding one open here would make Flask reuse it for every
    # request the test makes, silently masking routes that forget to commit().
    return make_app()


@pytest.fixture
def raw_client(app):
    return app.test_client()


@pytest.fixture
def client(app):
    c = app.test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    return c


@pytest.fixture
def login(client, app):
    def _login(provider_id="1"):
        with app.app_context():
            user = User(provider="test", provider_id=provider_id, nickname=f"user{provider_id}")
            db.session.add(user)
            db.session.commit()
            seed_user_defaults(user.id)
            db.session.commit()
            user_id = user.id
        with client.session_transaction() as s:
            s["user_id"] = user_id
        return user

    return _login
