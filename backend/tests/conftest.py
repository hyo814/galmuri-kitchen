import os
import socket

import anthropic
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
    "CLAUDE_MODEL": "claude-sonnet-5",  # 셸의 CLAUDE_MODEL이 ai_calls.model 확인을 흔들지 않게 고정한다
    "FOODSAFETY_API_KEY": None,  # 셸에 키가 있어도 동기화 테스트는 키 없음으로 시작한다
    "YOUTUBE_API_KEY": None,
}


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """테스트는 네트워크를 부르지 않는다. 가짜를 깜빡하면 조용히 밖으로 나가지 않고 여기서 실패한다.
    requests·httpx(anthropic)는 IP 주소로 연결할 때도 getaddrinfo를 거친다. 로컬 PostgreSQL 테스트 DB(psycopg)만 허용한다."""
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host, *args, **kwargs):
        if host not in ("localhost", "127.0.0.1", "::1"):
            raise AssertionError("테스트에서 네트워크를 부르면 안 돼요")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)


@pytest.fixture
def fake_anthropic(monkeypatch):
    """anthropic.Anthropic을 가짜로 바꾸고, 받은 인자를 calls에 모은다."""

    def _fake(response=None, error=None):
        calls = {}

        class FakeClient:
            def __init__(self, **kwargs):
                calls["client"] = kwargs
                self.messages = self

            def parse(self, **kwargs):
                calls["parse"] = kwargs
                if error is not None:
                    raise error
                return response

        monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
        return calls

    return _fake


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
