import pytest

from app import create_app
from app.models import User, db

TEST_CONFIG = {
    "TESTING": True,
    "SECRET_KEY": "test",
    "SQLALCHEMY_DATABASE_URI": "sqlite://",
    "DEV_MODE": True,
    "SESSION_COOKIE_SECURE": False,
}


@pytest.fixture
def make_app():
    def _make(**overrides):
        app = create_app({**TEST_CONFIG, **overrides})
        with app.app_context():
            db.create_all()
        return app

    return _make


@pytest.fixture
def app(make_app):
    app = make_app()
    with app.app_context():
        yield app


@pytest.fixture
def raw_client(app):
    return app.test_client()


@pytest.fixture
def client(app):
    c = app.test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    return c


@pytest.fixture
def login(client):
    def _login(provider_id="1"):
        user = User(provider="test", provider_id=provider_id, nickname=f"user{provider_id}")
        db.session.add(user)
        db.session.commit()
        with client.session_transaction() as s:
            s["user_id"] = user.id
        return user

    return _login
