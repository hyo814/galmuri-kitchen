# 1단계(기반) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인한 사용자가 폰(갤럭시 S22 Ultra)에서 냉장고 재료를 수기로 등록·수정·삭제하고 임박 재료를 한눈에 보며, 같은 코드가 Render에 배포 가능한 상태.

**Architecture:** Flask 단일 앱이 `/api/*`, `/auth/*`, React 빌드 결과를 같은 오리진에서 서빙한다. 로컬에서는 Vite 개발 서버(0.0.0.0:5173)가 `/api`·`/auth`를 Flask(127.0.0.1:5000)로 프록시해 폰에서 같은 와이파이로 접속한다. OAuth는 사설 IP를 리다이렉트 URI로 쓸 수 없어 `DEV_MODE=1`에서만 개발용 로그인을 연다.

**Tech Stack:** Python 3.14, Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, Authlib 1.8.0, pytest 9.1.1 / Node 24, Vite 8, React 19, TypeScript

**Spec:** `docs/superpowers/specs/2026-09-13-recipe-ai-design.md`

## Global Constraints

- 모든 사용자 소유 데이터 조회는 `g.user.id`로 한정, 남의 리소스는 404 `{"error": "찾을 수 없어요."}`.
- API 오류 형식은 항상 `{"error": "<한국어 메시지>"}` + 상태 코드.
- `/api/*` 상태 변경 요청(POST/PUT/PATCH/DELETE)은 `X-Requested-With: fetch` 헤더 필수, 없으면 400 `{"error": "잘못된 요청이에요."}`.
- 세션 쿠키: HttpOnly, SameSite=Lax, `DEV_MODE=1`이 아니면 Secure.
- `DEV_MODE=1`이면서 `RENDER` 환경변수가 있으면 앱 시작 거부.
- 임박 규칙: `expires_on - today <= 3일`이면 `urgent`, 유통기한 없고 `today - purchased_on >= 7일`이면 `old`, 그 외 `ok`. today는 Asia/Seoul 기준.
- 재료 검증: name 1~50자, quantity 유한수 > 0, unit 최대 10자(기본 `개`), 날짜 ISO `YYYY-MM-DD`, purchased_on 필수.
- 모바일 우선, 터치 타깃 44px 이상, 입력 글자 16px 이상.
- 모든 명령은 저장소 루트(`/Users/limhyojin/PycharmProjects/ recipe-ai` — **경로 앞에 공백 있음, 항상 따옴표로 감쌀 것**) 기준.

## 파일 구조

```
.gitignore                      (수정) instance/, .env 등
dev.sh                          로컬 실행: Flask + Vite, 폰 접속 URL 출력
Dockerfile, .dockerignore       운영 이미지
docs/deploy.md                  OAuth 앱 등록·Render 배포 절차
backend/
  requirements.txt, pytest.ini, .env.example
  app/__init__.py               create_app, 설정, CSRF 헤더 검사, JSON 오류, SPA 서빙
  app/models.py                 db, User, Ingredient
  app/auth.py                   세션 로그인, login_required, get_owned_or_404, upsert_user, 개발용/OAuth 로그인
  app/ingredients.py            임박 판정, 재료 검증, 재료 CRUD API
  migrations/                   Flask-Migrate 자동 생성
  tests/conftest.py, test_auth.py, test_ingredients.py, test_oauth.py, test_spa.py
frontend/
  package.json, tsconfig.json, vite.config.ts, index.html
  public/manifest.webmanifest, icon-192.png, icon-512.png
  src/main.tsx, App.tsx, api.ts, styles.css
  src/pages/Login.tsx, Fridge.tsx
  src/components/IngredientForm.tsx
```

1단계는 화면이 하나(냉장고)라 라우터와 하단 탭은 넣지 않는다. 3단계(추천·레시피)에서 추가한다.

---

### Task 1: 백엔드 뼈대 + 세션 + 개발용 로그인

**Files:**
- Create: `backend/requirements.txt`, `backend/pytest.ini`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/models.py`, `backend/app/auth.py`
- Create: `backend/tests/conftest.py`, `backend/tests/test_auth.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces:
  - `app.create_app(test_config: dict | None = None) -> Flask`
  - `app.database_url(url: str) -> str`
  - `app.models.db: SQLAlchemy`, `app.models.User(id, provider, provider_id, nickname, created_at)`, `app.models.utcnow()`
  - `app.auth.bp` (Blueprint `"auth"`), `login_user(user)`, `login_required(view)` (성공 시 `g.user` 설정), `get_owned_or_404(model, obj_id)`, `upsert_user(provider: str, provider_id: str, nickname: str | None) -> User`
  - API: `GET /api/auth-options` → `{providers: [], dev_login: bool}`, `POST /api/dev-login` → `{id, nickname}`, `GET /api/me` → `{id, nickname}`, `POST /api/logout` → `{ok: true}`
  - 테스트 픽스처: `make_app(**overrides)`, `app`, `client`(fetch 헤더 자동), `raw_client`(헤더 없음), `login(provider_id="1") -> User`

- [ ] **Step 1: 가상환경과 의존성**

`backend/requirements.txt`:
```
Flask==3.1.3
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.1.0
Authlib==1.8.0
requests==2.34.2
python-dotenv==1.2.3
tzdata==2026.4
gunicorn==26.2.0
psycopg[binary]==3.3.5
pytest==9.1.1
```

`backend/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

`backend/.env.example`:
```
# 로컬 개발: 개발용 로그인 켜기 + 세션 쿠키 Secure 끄기. 운영에서는 절대 넣지 말 것.
DEV_MODE=1
# SECRET_KEY=운영에서는 긴 랜덤 문자열
# DATABASE_URL=비우면 backend/instance/dev.sqlite3
```

`.gitignore` 끝에 추가:
```
instance/
```

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && cp .env.example .env
```
Expected: 오류 없이 종료.

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/conftest.py`:
```python
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
```

`backend/tests/test_auth.py`:
```python
import pytest

from app import database_url
from app.auth import upsert_user
from app.models import User


def test_me_requires_login(client):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.get_json() == {"error": "로그인이 필요해요."}


def test_dev_login_then_me(client):
    assert client.post("/api/dev-login").status_code == 200
    assert client.get("/api/me").get_json()["nickname"] == "개발자"


def test_dev_login_reuses_same_user(client):
    first = client.post("/api/dev-login").get_json()["id"]
    second = client.post("/api/dev-login").get_json()["id"]
    assert first == second
    assert User.query.count() == 1


def test_dev_login_hidden_without_dev_mode(make_app):
    c = make_app(DEV_MODE=False).test_client()
    c.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    assert c.post("/api/dev-login").status_code == 404
    assert c.get("/api/auth-options").get_json() == {"providers": [], "dev_login": False}


def test_logout_clears_session(client):
    client.post("/api/dev-login")
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_mutation_without_fetch_header_rejected(raw_client):
    res = raw_client.post("/api/dev-login")
    assert res.status_code == 400
    assert res.get_json() == {"error": "잘못된 요청이에요."}


def test_unknown_api_route_is_json_404(client):
    res = client.get("/api/nope")
    assert res.status_code == 404
    assert res.get_json() == {"error": "찾을 수 없어요."}


def test_upsert_user_updates_nickname(app):
    first = upsert_user("kakao", "1", "옛이름")
    second = upsert_user("kakao", "1", "새이름")
    assert first.id == second.id
    assert second.nickname == "새이름"
    assert upsert_user("kakao", "2", None).nickname == "사용자"


def test_database_url_normalizes_render_postgres():
    assert database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert database_url("sqlite:///dev.sqlite3") == "sqlite:///dev.sqlite3"


def test_secret_key_required(make_app):
    with pytest.raises(RuntimeError):
        make_app(SECRET_KEY=None)


def test_dev_mode_refused_on_render(make_app, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError):
        make_app()
```

- [ ] **Step 3: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: 수집 오류 `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 4: 구현**

`backend/app/models.py`:
```python
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (db.UniqueConstraint("provider", "provider_id"),)

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20), nullable=False)
    provider_id = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(50), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
```

`backend/app/auth.py`:
```python
from functools import wraps

from flask import Blueprint, abort, current_app, g, jsonify, session

from .models import User, db

bp = Blueprint("auth", __name__)


def login_user(user):
    session.clear()
    session["user_id"] = user.id
    session.permanent = True


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id else None
        if g.user is None:
            abort(401, "로그인이 필요해요.")
        return view(*args, **kwargs)

    return wrapper


def get_owned_or_404(model, obj_id):
    obj = db.session.get(model, obj_id)
    if obj is None or obj.user_id != g.user.id:
        abort(404, "찾을 수 없어요.")
    return obj


def upsert_user(provider, provider_id, nickname):
    user = User.query.filter_by(provider=provider, provider_id=provider_id).first()
    if user is None:
        user = User(provider=provider, provider_id=provider_id)
        db.session.add(user)
    user.nickname = (nickname or "사용자")[:50]
    db.session.commit()
    return user


@bp.get("/api/auth-options")
def auth_options():
    return jsonify(providers=[], dev_login=current_app.config["DEV_MODE"])


@bp.post("/api/dev-login")
def dev_login():
    if not current_app.config["DEV_MODE"]:
        abort(404)
    user = upsert_user("dev", "dev", "개발자")
    login_user(user)
    return jsonify(id=user.id, nickname=user.nickname)


@bp.get("/api/me")
@login_required
def me():
    return jsonify(id=g.user.id, nickname=g.user.nickname)


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)
```

`backend/app/__init__.py`:
```python
import os
import re

from flask import Flask, jsonify, request
from flask_migrate import Migrate
from werkzeug.exceptions import HTTPException

from .models import db

DEFAULT_MESSAGES = {
    400: "잘못된 요청이에요.",
    401: "로그인이 필요해요.",
    404: "찾을 수 없어요.",
    405: "허용되지 않는 요청이에요.",
    413: "파일이 너무 커요. 10MB 이하로 올려 주세요.",
}


def database_url(url):
    # Render는 postgres:// 를 주지만 SQLAlchemy + psycopg 3 는 postgresql+psycopg:// 가 필요
    return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


def create_app(test_config=None):
    dev = os.environ.get("DEV_MODE") == "1"
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or ("dev" if dev else None),
        SQLALCHEMY_DATABASE_URI=database_url(os.environ.get("DATABASE_URL", "sqlite:///dev.sqlite3")),
        DEV_MODE=dev,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not dev,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY 환경변수가 필요합니다.")
    if app.config["DEV_MODE"] and os.environ.get("RENDER"):
        raise RuntimeError("운영(Render)에서는 DEV_MODE를 켤 수 없습니다.")

    db.init_app(app)
    Migrate(app, db, render_as_batch=True)

    from .auth import bp as auth_bp

    app.register_blueprint(auth_bp)

    @app.before_request
    def require_fetch_header():
        # CSRF 방어: SameSite=Lax 쿠키 + 크로스사이트 폼이 붙일 수 없는 커스텀 헤더
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and request.path.startswith("/api/")
            and request.headers.get("X-Requested-With") != "fetch"
        ):
            return jsonify(error=DEFAULT_MESSAGES[400]), 400

    @app.errorhandler(HTTPException)
    def http_error(e):
        if not request.path.startswith("/api/"):
            return e
        custom = e.description != type(e).description
        message = e.description if custom else DEFAULT_MESSAGES.get(e.code, "문제가 생겼어요.")
        return jsonify(error=message), e.code

    return app
```

- [ ] **Step 5: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: `11 passed`

- [ ] **Step 6: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add .gitignore backend && git commit -m "feat: Flask 뼈대, 세션, 개발용 로그인"
```

---

### Task 2: 냉장고 재료 API + 첫 마이그레이션

**Files:**
- Modify: `backend/app/models.py` (Ingredient 추가)
- Create: `backend/app/ingredients.py`, `backend/tests/test_ingredients.py`
- Modify: `backend/app/__init__.py` (블루프린트 등록)
- Create: `backend/migrations/` (자동 생성)

**Interfaces:**
- Consumes: `login_required`, `get_owned_or_404`, `db`, `utcnow`, 픽스처 `client`, `login`
- Produces:
  - `app.models.Ingredient(id, user_id, name, quantity, unit, purchased_on, expires_on, created_at)`
  - `app.ingredients.seoul_today() -> date`, `ingredient_status(purchased_on: date, expires_on: date | None, today: date) -> "urgent" | "old" | "ok"`
  - API `GET /api/ingredients` → 임박순 배열, `POST /api/ingredients` → 201, `PATCH /api/ingredients/<id>`, `DELETE /api/ingredients/<id>` → 204
  - 재료 JSON: `{id, name, quantity, unit, purchased_on, expires_on, status, days_left, days_since_purchase}` (`days_left`는 유통기한 없으면 null)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_ingredients.py`:
```python
from datetime import date, timedelta

import pytest

from app.ingredients import ingredient_status, seoul_today

TODAY = date(2026, 9, 13)


@pytest.mark.parametrize(
    "purchased, expires, expected",
    [
        (TODAY, TODAY + timedelta(days=3), "urgent"),
        (TODAY, TODAY + timedelta(days=4), "ok"),
        (TODAY, TODAY - timedelta(days=1), "urgent"),
        (TODAY - timedelta(days=30), TODAY + timedelta(days=10), "ok"),
        (TODAY - timedelta(days=7), None, "old"),
        (TODAY - timedelta(days=6), None, "ok"),
    ],
)
def test_ingredient_status(purchased, expires, expected):
    assert ingredient_status(purchased, expires, TODAY) == expected


def create(client, **fields):
    body = {"name": "우유", "quantity": 1, "unit": "개", "purchased_on": seoul_today().isoformat(), **fields}
    return client.post("/api/ingredients", json=body)


def test_requires_login(client):
    assert client.get("/api/ingredients").status_code == 401


def test_create_and_list_sorted_by_urgency(client, login):
    login()
    today = seoul_today()
    create(client, name="계란")
    create(client, name="두부", purchased_on=(today - timedelta(days=30)).isoformat())
    res = create(client, name="우유", expires_on=today.isoformat())
    assert res.status_code == 201
    assert res.get_json()["status"] == "urgent"

    items = client.get("/api/ingredients").get_json()
    assert [(i["name"], i["status"]) for i in items] == [("우유", "urgent"), ("두부", "old"), ("계란", "ok")]
    assert items[0]["days_left"] == 0
    assert items[1]["days_since_purchase"] == 30
    assert items[2]["days_left"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "가" * 51},
        {"quantity": 0},
        {"quantity": "많이"},
        {"purchased_on": "2026-13-01"},
        {"purchased_on": None},
        {"expires_on": "내일"},
    ],
)
def test_create_validation(client, login, fields):
    login()
    res = create(client, **fields)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_update_partial_and_clear_expiry(client, login):
    login()
    item = create(client, expires_on="2030-01-01").get_json()
    res = client.patch(f"/api/ingredients/{item['id']}", json={"quantity": 2.5, "expires_on": None})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["name"], body["quantity"], body["expires_on"]) == ("우유", 2.5, None)


def test_delete(client, login):
    login()
    item = create(client).get_json()
    assert client.delete(f"/api/ingredients/{item['id']}").status_code == 204
    assert client.get("/api/ingredients").get_json() == []


def test_other_users_ingredient_is_hidden(client, login):
    login("owner")
    item = create(client).get_json()
    login("intruder")
    assert client.get("/api/ingredients").get_json() == []
    assert client.patch(f"/api/ingredients/{item['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/ingredients/{item['id']}").status_code == 404
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q tests/test_ingredients.py`
Expected: `ModuleNotFoundError: No module named 'app.ingredients'`

- [ ] **Step 3: 구현**

`backend/app/models.py` 끝에 추가:
```python


class Ingredient(db.Model):
    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(10), nullable=False, default="개")
    purchased_on = db.Column(db.Date, nullable=False)
    expires_on = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
```

`backend/app/ingredients.py`:
```python
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, g, jsonify, request

from .auth import get_owned_or_404, login_required
from .models import Ingredient, db

bp = Blueprint("ingredients", __name__, url_prefix="/api/ingredients")

URGENT_DAYS = 3  # 유통기한까지 3일 이내(지난 것 포함)면 임박
OLD_DAYS = 7  # 유통기한이 없으면 구입 7일째부터 오래됨
STATUS_RANK = {"urgent": 0, "old": 1, "ok": 2}
SEOUL = ZoneInfo("Asia/Seoul")


def seoul_today():
    return datetime.now(SEOUL).date()


def ingredient_status(purchased_on, expires_on, today):
    if expires_on is not None:
        return "urgent" if (expires_on - today).days <= URGENT_DAYS else "ok"
    return "old" if (today - purchased_on).days >= OLD_DAYS else "ok"


def to_json(item, today):
    return {
        "id": item.id,
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "purchased_on": item.purchased_on.isoformat(),
        "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        "status": ingredient_status(item.purchased_on, item.expires_on, today),
        "days_left": (item.expires_on - today).days if item.expires_on else None,
        "days_since_purchase": (today - item.purchased_on).days,
    }


def _date(value, label):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(400, f"{label}은 YYYY-MM-DD 형식으로 입력해 주세요.")


def parse_fields(data, creating):
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    fields = {}
    if creating or "name" in data:
        name = str(data.get("name") or "").strip()
        if not 1 <= len(name) <= 50:
            abort(400, "이름은 1~50자로 입력해 주세요.")
        fields["name"] = name
    if creating or "quantity" in data:
        try:
            quantity = float(data.get("quantity", 1))
        except (TypeError, ValueError):
            abort(400, "수량은 숫자로 입력해 주세요.")
        if not (math.isfinite(quantity) and quantity > 0):
            abort(400, "수량은 0보다 커야 해요.")
        fields["quantity"] = quantity
    if creating or "unit" in data:
        fields["unit"] = str(data.get("unit") or "").strip()[:10] or "개"
    if creating or "purchased_on" in data:
        fields["purchased_on"] = _date(data.get("purchased_on"), "구입일")
    if "expires_on" in data:
        value = data["expires_on"]
        fields["expires_on"] = _date(value, "유통기한") if value else None
    return fields


@bp.get("")
@login_required
def list_ingredients():
    today = seoul_today()
    items = Ingredient.query.filter_by(user_id=g.user.id).all()
    items.sort(
        key=lambda i: (
            STATUS_RANK[ingredient_status(i.purchased_on, i.expires_on, today)],
            i.expires_on or date.max,
            i.purchased_on,
            i.id,
        )
    )
    return jsonify([to_json(i, today) for i in items])


@bp.post("")
@login_required
def create_ingredient():
    item = Ingredient(user_id=g.user.id, **parse_fields(request.get_json(silent=True), creating=True))
    db.session.add(item)
    db.session.commit()
    return jsonify(to_json(item, seoul_today())), 201


@bp.patch("/<int:item_id>")
@login_required
def update_ingredient(item_id):
    item = get_owned_or_404(Ingredient, item_id)
    for key, value in parse_fields(request.get_json(silent=True), creating=False).items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify(to_json(item, seoul_today()))


@bp.delete("/<int:item_id>")
@login_required
def delete_ingredient(item_id):
    db.session.delete(get_owned_or_404(Ingredient, item_id))
    db.session.commit()
    return "", 204
```

`backend/app/__init__.py`에서 블루프린트 등록 부분을 다음으로 교체:
```python
    from .auth import bp as auth_bp
    from .ingredients import bp as ingredients_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ingredients_bp)
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: `29 passed`

- [ ] **Step 5: 마이그레이션 생성·적용**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/flask --app app db init && .venv/bin/flask --app app db migrate -m "users and ingredients" && .venv/bin/flask --app app db upgrade
```
Expected: `migrations/versions/xxxx_users_and_ingredients.py` 생성, 그 안에 `op.create_table('users'`와 `op.create_table('ingredients'`가 있음. `instance/dev.sqlite3` 생성.

- [ ] **Step 6: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "feat: 냉장고 재료 CRUD API와 임박 판정"
```

---

### Task 3: 프론트엔드 — 로그인 + 냉장고 화면 + PWA

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`
- Create: `frontend/public/manifest.webmanifest`, `frontend/public/icon-192.png`, `frontend/public/icon-512.png`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/styles.css`, `frontend/src/pages/Login.tsx`, `frontend/src/pages/Fridge.tsx`, `frontend/src/components/IngredientForm.tsx`

**Interfaces:**
- Consumes: Task 1·2의 API (`/api/auth-options`, `/api/dev-login`, `/api/me`, `/api/logout`, `/api/ingredients*`), 로그인 실패 시 `/?login_error=1` 리다이렉트(Task 5)
- Produces:
  - `api<T>(path: string, options?: { method?: string; body?: unknown }): Promise<T>` — 항상 `X-Requested-With: fetch`, 실패 시 `ApiError(status, message)` throw
  - 타입 `User`, `AuthOptions`, `Status`, `IngredientInput`, `Ingredient` (`src/api.ts`)

- [ ] **Step 1: 프로젝트 파일과 의존성**

`frontend/package.json`:
```json
{
  "name": "recipe-ai-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview"
  }
}
```

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm install react react-dom && npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom
```
Expected: `package.json`에 dependencies/devDependencies 추가, `package-lock.json` 생성.

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "types": ["vite/client"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`frontend/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": backend, "/auth": backend } },
});
```

`frontend/index.html`:
```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="theme-color" content="#2f7d4f" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="icon" href="/icon-192.png" />
    <title>냉장고 레시피</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: PWA manifest와 아이콘**

`frontend/public/manifest.webmanifest`:
```json
{
  "name": "냉장고 레시피",
  "short_name": "냉장고레시피",
  "lang": "ko",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#faf7f2",
  "theme_color": "#2f7d4f",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
```

아이콘은 한 번만 생성해서 커밋한다(생성 스크립트는 남기지 않음). 초록 배경에 흰 그릇과 김 세 줄기.

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && python3 - <<'EOF'
import struct, zlib

def png(size, path):
    green, cream = (0x2F, 0x7D, 0x4F), (0xFA, 0xF7, 0xF2)
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            u, v = x / size, y / size
            bowl = v >= 0.52 and (u - 0.5) ** 2 + (v - 0.52) ** 2 <= 0.28 ** 2
            rim = 0.20 <= u <= 0.80 and 0.49 <= v <= 0.53
            steam = any((u - cx) ** 2 + (v - 0.38) ** 2 <= 0.035 ** 2 for cx in (0.40, 0.50, 0.60))
            row += bytes(cream if bowl or rim or steam else green)
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))

png(192, "public/icon-192.png")
png(512, "public/icon-512.png")
EOF
file public/icon-192.png public/icon-512.png
```
Expected: `PNG image data, 192 x 192, 8-bit/color RGB` / `512 x 512`

- [ ] **Step 3: API 클라이언트와 진입점**

`frontend/src/api.ts`:
```ts
export type Status = "urgent" | "old" | "ok";

export interface User {
  id: number;
  nickname: string;
}

export interface AuthOptions {
  providers: string[];
  dev_login: boolean;
}

export interface IngredientInput {
  name: string;
  quantity: number;
  unit: string;
  purchased_on: string;
  expires_on: string | null;
}

export interface Ingredient extends IngredientInput {
  id: number;
  status: Status;
  days_left: number | null;
  days_since_purchase: number;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const hasBody = options.body !== undefined;
  const res = await fetch(path, {
    method: options.method ?? "GET",
    headers: { "X-Requested-With": "fetch", ...(hasBody ? { "Content-Type": "application/json" } : {}) },
    body: hasBody ? JSON.stringify(options.body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error ?? "문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
  return data as T;
}

/** 기기 로컬 날짜 YYYY-MM-DD (toISOString은 UTC라 새벽에 하루 밀림) */
export const localToday = () => new Date().toLocaleDateString("sv-SE");
```

`frontend/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api, type User } from "./api";
import Fridge from "./pages/Fridge";
import Login from "./pages/Login";

export default function App() {
  // undefined: 확인 중, null: 비로그인
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api<User>("/api/me").then(setUser, () => setUser(null));
  }, []);

  if (user === undefined) return <p className="center muted">불러오는 중…</p>;
  if (user === null) return <Login onLogin={setUser} />;
  return <Fridge onLogout={() => setUser(null)} />;
}
```

- [ ] **Step 4: 로그인 화면**

`frontend/src/pages/Login.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api, type AuthOptions, type User } from "../api";

export default function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [error, setError] = useState(
    new URLSearchParams(location.search).has("login_error") ? "로그인에 실패했어요. 다시 시도해 주세요." : "",
  );

  useEffect(() => {
    api<AuthOptions>("/api/auth-options").then(setOptions, (e: Error) => setError(e.message));
  }, []);

  const devLogin = async () => {
    try {
      onLogin(await api<User>("/api/dev-login", { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <main className="login">
      <h1>냉장고 레시피</h1>
      <p className="muted">냉장고 속 재료로 오늘 뭐 해 먹을지 정해요.</p>
      {options?.providers.includes("kakao") && (
        <a className="btn kakao" href="/auth/login/kakao">
          카카오 로그인
        </a>
      )}
      {options?.providers.includes("google") && (
        <a className="btn google" href="/auth/login/google">
          Google로 계속하기
        </a>
      )}
      {options?.dev_login && (
        <button className="btn ghost" onClick={devLogin}>
          개발용 로그인
        </button>
      )}
      {options && options.providers.length === 0 && !options.dev_login && (
        <p className="muted">아직 로그인 방법이 설정되지 않았어요.</p>
      )}
      {error && <p className="error">{error}</p>}
    </main>
  );
}
```

- [ ] **Step 5: 재료 입력 시트**

`frontend/src/components/IngredientForm.tsx`:
```tsx
import { useEffect, useRef, useState, type FormEvent } from "react";
import { localToday, type Ingredient, type IngredientInput } from "../api";

interface Props {
  initial: Ingredient | null;
  onSubmit: (input: IngredientInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

const UNITS = ["개", "g", "kg", "ml", "L", "팩", "봉", "병", "모"];

export default function IngredientForm({ initial, onSubmit, onDelete, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(initial?.name ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? "개");
  const [purchasedOn, setPurchasedOn] = useState(initial?.purchased_on ?? localToday());
  const [expiresOn, setExpiresOn] = useState(initial?.expires_on ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal(); // StrictMode 이중 실행 대비
  }, []);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(() =>
      onSubmit({
        name: name.trim(),
        quantity: Number(quantity),
        unit: unit.trim() || "개",
        purchased_on: purchasedOn,
        expires_on: expiresOn || null,
      }),
    );
  };

  return (
    <dialog ref={ref} className="sheet" onClose={onClose} aria-labelledby="ingredient-form-title">
      <form onSubmit={submit}>
        <h2 id="ingredient-form-title">{initial ? "재료 수정" : "재료 추가"}</h2>
        <label className="field">
          이름
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={50} placeholder="예: 대파" />
        </label>
        <div className="row">
          <label className="field">
            수량
            <input
              type="number"
              inputMode="decimal"
              min="0.1"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
          </label>
          <label className="field">
            단위
            <input list="units" value={unit} onChange={(e) => setUnit(e.target.value)} maxLength={10} />
            <datalist id="units">
              {UNITS.map((u) => (
                <option key={u} value={u} />
              ))}
            </datalist>
          </label>
        </div>
        <div className="row">
          <label className="field">
            구입일
            <input type="date" value={purchasedOn} onChange={(e) => setPurchasedOn(e.target.value)} required />
          </label>
          <label className="field">
            유통기한 (선택)
            <input type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
          </label>
        </div>
        <button className="btn primary" disabled={busy}>
          {busy ? "저장 중…" : "저장"}
        </button>
        {onDelete && (
          <button type="button" className="btn danger" disabled={busy} onClick={() => run(onDelete)}>
            삭제
          </button>
        )}
        <button type="button" className="btn ghost" onClick={onClose}>
          취소
        </button>
      </form>
    </dialog>
  );
}
```

- [ ] **Step 6: 냉장고 화면**

`frontend/src/pages/Fridge.tsx`:
```tsx
import { useEffect, useState } from "react";
import { api, ApiError, type Ingredient, type IngredientInput } from "../api";
import IngredientForm from "../components/IngredientForm";

function badge(item: Ingredient): string | null {
  const d = item.days_left;
  if (d !== null) return d > 0 ? `D-${d}` : d === 0 ? "D-day" : `${-d}일 지남`;
  if (item.status === "old") return `구입 ${item.days_since_purchase}일째`;
  return null;
}

const formatQuantity = (q: number) => (Number.isInteger(q) ? String(q) : q.toFixed(1));

export default function Fridge({ onLogout }: { onLogout: () => void }) {
  const [items, setItems] = useState<Ingredient[] | null>(null);
  const [editing, setEditing] = useState<Ingredient | "new" | null>(null);
  const [error, setError] = useState("");

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) onLogout();
    else setError((e as Error).message);
  };

  const load = () => api<Ingredient[]>("/api/ingredients").then(setItems, fail);

  useEffect(() => {
    load();
  }, []);

  const save = async (input: IngredientInput) => {
    try {
      if (editing === "new") await api("/api/ingredients", { method: "POST", body: input });
      else if (editing) await api(`/api/ingredients/${editing.id}`, { method: "PATCH", body: input });
      setEditing(null);
      setError("");
      await load();
    } catch (e) {
      fail(e);
    }
  };

  const remove = async () => {
    if (!editing || editing === "new" || !confirm(`${editing.name}을(를) 삭제할까요?`)) return;
    try {
      await api(`/api/ingredients/${editing.id}`, { method: "DELETE" });
      setEditing(null);
      await load();
    } catch (e) {
      fail(e);
    }
  };

  const logout = async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    onLogout();
  };

  return (
    <div className="page">
      <header className="topbar">
        <h1>내 냉장고</h1>
        <button className="link" onClick={logout}>
          로그아웃
        </button>
      </header>

      {error && (
        <p className="error" role="alert" onClick={() => setError("")}>
          {error}
        </p>
      )}

      {items === null ? (
        <p className="center muted">불러오는 중…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          <p>냉장고가 비어 있어요.</p>
          <p className="muted">아래 버튼으로 재료를 추가해 보세요.</p>
        </div>
      ) : (
        <ul className="list">
          {items.map((item) => {
            const label = badge(item);
            return (
              <li key={item.id}>
                <button className="item" onClick={() => setEditing(item)}>
                  <span className="item-name">{item.name}</span>
                  <span className="item-meta">
                    {formatQuantity(item.quantity)}
                    {item.unit} · {item.purchased_on} 구입
                  </span>
                  {label && <span className={`badge ${item.status}`}>{label}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <button className="btn primary fab" onClick={() => setEditing("new")}>
        + 재료 추가
      </button>

      {editing && (
        <IngredientForm
          initial={editing === "new" ? null : editing}
          onSubmit={save}
          onDelete={editing === "new" ? undefined : remove}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 7: 스타일**

`frontend/src/styles.css`:
```css
:root {
  --bg: #faf7f2;
  --surface: #ffffff;
  --text: #2a2622;
  --muted: #7a726a;
  --line: #ebe5dc;
  --accent: #2f7d4f;
  --accent-text: #ffffff;
  --urgent: #c2410c;
  --urgent-bg: #ffedd5;
  --old: #a16207;
  --old-bg: #fef3c7;
  --radius: 14px;
  color-scheme: light dark;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #171512;
    --surface: #221f1b;
    --text: #f2ede6;
    --muted: #a39a90;
    --line: #332e28;
    --accent: #4fae76;
    --accent-text: #0f1a13;
    --urgent: #fb923c;
    --urgent-bg: #3a2014;
    --old: #fbbf24;
    --old-bg: #3a2e10;
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif;
  -webkit-tap-highlight-color: transparent;
}

button,
input {
  font: inherit;
  color: inherit;
}

.page {
  max-width: 520px;
  margin: 0 auto;
  padding: 0 16px calc(96px + env(safe-area-inset-bottom));
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 0 12px;
}

.topbar h1 {
  margin: 0;
  font-size: 1.5rem;
}

.link {
  min-height: 44px;
  padding: 0 4px;
  border: 0;
  background: none;
  color: var(--muted);
  cursor: pointer;
}

.muted {
  color: var(--muted);
}

.center {
  padding: 48px 16px;
  text-align: center;
}

.error {
  margin: 0 0 12px;
  padding: 12px 14px;
  border-radius: var(--radius);
  background: var(--urgent-bg);
  color: var(--urgent);
}

.empty {
  padding: 64px 16px;
  text-align: center;
}

.empty p {
  margin: 4px 0;
}

.list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: grid;
  grid-template-columns: 1fr auto;
  column-gap: 12px;
  width: 100%;
  min-height: 64px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
}

.item-name {
  font-weight: 600;
}

.item-meta {
  grid-row: 2;
  color: var(--muted);
  font-size: 0.875rem;
}

.badge {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--line);
  color: var(--muted);
  font-size: 0.8125rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.badge.urgent {
  background: var(--urgent-bg);
  color: var(--urgent);
}

.badge.old {
  background: var(--old-bg);
  color: var(--old);
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 52px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.6;
}

.btn:focus-visible,
.item:focus-visible,
.link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.btn.primary {
  background: var(--accent);
  color: var(--accent-text);
}

.btn.ghost {
  border-color: var(--line);
  background: transparent;
}

.btn.danger {
  background: transparent;
  color: var(--urgent);
}

.btn.kakao {
  background: #fee500;
  color: #191600;
}

.btn.google {
  border-color: #dadce0;
  background: #ffffff;
  color: #1f1f1f;
}

.fab {
  position: fixed;
  bottom: calc(20px + env(safe-area-inset-bottom));
  left: 50%;
  width: min(488px, calc(100% - 32px));
  transform: translateX(-50%);
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.15);
}

.login {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  max-width: 400px;
  min-height: 100dvh;
  margin: 0 auto;
  padding: 24px 16px;
}

.login h1 {
  margin: 0;
  font-size: 2rem;
}

.login > p.muted {
  margin: 0 0 24px;
}

.sheet {
  width: 100%;
  max-width: 520px;
  max-height: 90dvh;
  margin: auto auto 0;
  padding: 0;
  border: 0;
  border-radius: 20px 20px 0 0;
  background: var(--surface);
  color: var(--text);
}

.sheet::backdrop {
  background: rgb(0 0 0 / 0.4);
}

.sheet form {
  display: grid;
  gap: 14px;
  padding: 20px 16px calc(20px + env(safe-area-inset-bottom));
}

.sheet h2 {
  margin: 0;
  font-size: 1.25rem;
}

.field {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 0.875rem;
}

.field input {
  width: 100%;
  min-height: 48px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg);
  color: var(--text);
  font-size: 1rem;
}

.field input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
```

- [ ] **Step 8: 타입 검사·빌드 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build`
Expected: `tsc` 오류 없음, `dist/index.html`, `dist/assets/*.js`, `dist/manifest.webmanifest`, `dist/icon-512.png` 생성

- [ ] **Step 9: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add frontend && git commit -m "feat: 로그인과 냉장고 화면, PWA manifest"
```

---

### Task 4: 폰에서 보기 (dev.sh + 실기기 확인)

**Files:**
- Create: `dev.sh`

**Interfaces:**
- Consumes: `backend/.venv`, `backend/.env`(DEV_MODE=1), `frontend/node_modules`, Vite 프록시 설정
- Produces: `./dev.sh` → Flask 127.0.0.1:5000 + Vite 0.0.0.0:5173, 폰 접속 URL 출력

- [ ] **Step 1: 실행 스크립트 작성**

`dev.sh`:
```bash
#!/usr/bin/env bash
# 로컬 개발: Flask(127.0.0.1:5000) + Vite(0.0.0.0:5173). 폰은 같은 와이파이에서 접속.
set -euo pipefail
cd "$(dirname "$0")"

(cd backend && .venv/bin/flask --app app db upgrade && exec .venv/bin/flask --app app run --port 5000 --debug) &
trap 'kill 0' EXIT

IP=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || echo localhost)
echo ""
echo "📱 폰(같은 와이파이)에서 열기: http://$IP:5173"
echo ""
cd frontend && npm run dev -- --host 0.0.0.0
```

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && chmod +x dev.sh`

- [ ] **Step 2: 프록시를 통한 동작 확인**

Run(백그라운드): `cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && ./dev.sh`

그 다음:
```bash
IP=$(ipconfig getifaddr en0)
curl -s "http://$IP:5173/" | grep -o '<title>.*</title>'
curl -s -c /tmp/rc.txt -X POST -H 'X-Requested-With: fetch' "http://$IP:5173/api/dev-login"
curl -s -b /tmp/rc.txt -X POST -H 'X-Requested-With: fetch' -H 'Content-Type: application/json' \
  -d '{"name":"우유","quantity":1,"unit":"개","purchased_on":"2026-09-10","expires_on":"2026-09-14"}' "http://$IP:5173/api/ingredients"
curl -s -b /tmp/rc.txt "http://$IP:5173/api/ingredients"
```
Expected: `<title>냉장고 레시피</title>`, `{"id":1,"nickname":"개발자"}`, 생성된 우유 JSON(`"status":"urgent"`), 목록에 우유 1건. 확인 후 테스트 데이터 삭제: `curl -s -b /tmp/rc.txt -X DELETE -H 'X-Requested-With: fetch' "http://$IP:5173/api/ingredients/1"`

- [ ] **Step 3: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add dev.sh && git commit -m "chore: 폰 확인용 로컬 실행 스크립트"
```

- [ ] **Step 4: 🔶 체크포인트 — 사용자가 폰으로 확인**

`dev.sh`를 켜 둔 채로 사용자에게 안내한다:
1. 갤럭시 S22 Ultra를 맥과 **같은 와이파이**에 연결
2. Chrome에서 `http://<맥 IP>:5173` 열기 (맥에서 "node가 들어오는 연결을 허용할까요?" 방화벽 창이 뜨면 허용)
3. `개발용 로그인` → `+ 재료 추가` → 저장 → 항목 탭해 수정/삭제, 유통기한을 오늘로 넣어 빨간 `D-day` 배지 확인
4. (선택) Chrome 메뉴 → `홈 화면에 추가`. HTTP라 앱 모드 대신 바로가기로 추가됨. 앱 모드는 Task 6 배포(HTTPS) 이후.

사용자 피드백을 반영한 뒤 Task 5로 진행한다.

---

### Task 5: 카카오 / 구글 로그인

**Files:**
- Modify: `backend/app/auth.py`, `backend/app/__init__.py`, `backend/.env.example`
- Create: `backend/tests/test_oauth.py`

**Interfaces:**
- Consumes: `login_user`, `upsert_user`, `make_app`, `app` 픽스처
- Produces:
  - `app.auth.PROVIDERS: dict[str, dict]` (`"kakao"`, `"google"`), `init_oauth(app)` — 설정된 provider만 등록, `app.extensions["recipe_oauth"]`에 OAuth 레지스트리 저장
  - `GET /auth/login/<provider>` → 302 provider 인증 페이지 (미설정 provider 404)
  - `GET /auth/callback/<provider>` → 성공 시 302 `/`, 실패 시 302 `/?login_error=1`
  - `GET /api/auth-options`의 `providers`가 설정된 provider 목록

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_oauth.py`:
```python
import pytest
from authlib.integrations.base_client import OAuthError

from app.models import User


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


@pytest.fixture
def oauth_app(make_app):
    app = make_app(
        KAKAO_CLIENT_ID="kid",
        KAKAO_CLIENT_SECRET="ksecret",
        GOOGLE_CLIENT_ID="gid",
        GOOGLE_CLIENT_SECRET="gsecret",
    )
    with app.app_context():
        yield app


def oauth_client(app, name):
    return app.extensions["recipe_oauth"].create_client(name)


def test_auth_options_lists_configured_providers(oauth_app):
    assert oauth_app.test_client().get("/api/auth-options").get_json()["providers"] == ["kakao", "google"]


def test_unconfigured_provider_is_404(client):
    assert client.get("/auth/login/kakao").status_code == 404
    assert client.get("/auth/login/naver").status_code == 404


def test_kakao_login_redirects_to_kakao(oauth_app):
    res = oauth_app.test_client().get("/auth/login/kakao")
    assert res.status_code == 302
    assert res.location.startswith("https://kauth.kakao.com/oauth/authorize")
    assert "client_id=kid" in res.location


def test_kakao_callback_logs_in(oauth_app, monkeypatch):
    kakao = oauth_client(oauth_app, "kakao")
    monkeypatch.setattr(kakao, "authorize_access_token", lambda: {"access_token": "t"})
    monkeypatch.setattr(
        kakao, "get", lambda url, token: FakeResponse({"id": 42, "properties": {"nickname": "냉장고왕"}})
    )
    c = oauth_app.test_client()
    res = c.get("/auth/callback/kakao")
    assert res.status_code == 302
    assert res.location == "/"
    assert c.get("/api/me").get_json()["nickname"] == "냉장고왕"
    assert User.query.filter_by(provider="kakao", provider_id="42").count() == 1


def test_google_callback_logs_in(oauth_app, monkeypatch):
    google = oauth_client(oauth_app, "google")
    monkeypatch.setattr(google, "authorize_access_token", lambda: {"userinfo": {"sub": "g-1", "name": "구글사용자"}})
    c = oauth_app.test_client()
    assert c.get("/auth/callback/google").location == "/"
    assert c.get("/api/me").get_json()["nickname"] == "구글사용자"


def test_callback_error_redirects_with_flag(oauth_app, monkeypatch):
    kakao = oauth_client(oauth_app, "kakao")

    def denied():
        raise OAuthError(error="access_denied")

    monkeypatch.setattr(kakao, "authorize_access_token", denied)
    res = oauth_app.test_client().get("/auth/callback/kakao")
    assert res.location == "/?login_error=1"
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q tests/test_oauth.py`
Expected: FAIL (`KeyError: 'recipe_oauth'`, 404 등)

- [ ] **Step 3: 구현**

`backend/app/auth.py` 상단 import를 다음으로 교체:
```python
from functools import wraps

import requests
from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, abort, current_app, g, jsonify, redirect, session, url_for

from .models import User, db

bp = Blueprint("auth", __name__)

PROVIDERS = {
    "kakao": {
        "authorize_url": "https://kauth.kakao.com/oauth/authorize",
        "access_token_url": "https://kauth.kakao.com/oauth/token",
        "api_base_url": "https://kapi.kakao.com/",
        "client_kwargs": {"token_endpoint_auth_method": "client_secret_post"},
    },
    "google": {
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        "client_kwargs": {"scope": "openid profile"},
    },
}


def init_oauth(app):
    oauth = OAuth(app)
    for name, settings in PROVIDERS.items():
        client_id = app.config.get(f"{name.upper()}_CLIENT_ID")
        if client_id:
            oauth.register(
                name,
                client_id=client_id,
                client_secret=app.config.get(f"{name.upper()}_CLIENT_SECRET"),
                **settings,
            )
    app.extensions["recipe_oauth"] = oauth


def oauth_client(provider):
    client = current_app.extensions["recipe_oauth"].create_client(provider) if provider in PROVIDERS else None
    if client is None:
        abort(404)
    return client
```

`backend/app/auth.py`의 `auth_options`를 교체:
```python
@bp.get("/api/auth-options")
def auth_options():
    registry = current_app.extensions["recipe_oauth"]
    return jsonify(
        providers=[name for name in PROVIDERS if registry.create_client(name)],
        dev_login=current_app.config["DEV_MODE"],
    )
```

`backend/app/auth.py` 끝에 추가:
```python


@bp.get("/auth/login/<provider>")
def oauth_login(provider):
    client = oauth_client(provider)
    return client.authorize_redirect(url_for("auth.oauth_callback", provider=provider, _external=True))


@bp.get("/auth/callback/<provider>")
def oauth_callback(provider):
    client = oauth_client(provider)
    try:
        token = client.authorize_access_token()
        if provider == "google":
            info = token.get("userinfo") or {}
            provider_id, nickname = info.get("sub"), info.get("name")
        else:
            info = client.get("v2/user/me", token=token).json()
            provider_id, nickname = info.get("id"), (info.get("properties") or {}).get("nickname")
    except (OAuthError, requests.RequestException, ValueError):
        return redirect("/?login_error=1")
    if not provider_id:
        return redirect("/?login_error=1")
    login_user(upsert_user(provider, str(provider_id), nickname))
    return redirect("/")
```

`backend/app/__init__.py`:
- import에 추가: `from werkzeug.middleware.proxy_fix import ProxyFix`
- `app.config.from_mapping(...)` 인자에 추가:
```python
        KAKAO_CLIENT_ID=os.environ.get("KAKAO_CLIENT_ID"),
        KAKAO_CLIENT_SECRET=os.environ.get("KAKAO_CLIENT_SECRET"),
        GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID"),
        GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET"),
```
- `db.init_app(app)` 바로 위에 추가:
```python
    # Render 프록시 뒤에서 OAuth 콜백 URL이 https://<도메인> 으로 만들어지도록
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
```
- 블루프린트 import를 교체:
```python
    from .auth import bp as auth_bp
    from .auth import init_oauth
    from .ingredients import bp as ingredients_bp

    init_oauth(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ingredients_bp)
```

`backend/.env.example` 끝에 추가:
```
# 소셜 로그인 (docs/deploy.md 참고). 비워 두면 해당 버튼이 숨겨짐
# KAKAO_CLIENT_ID=REST API 키
# KAKAO_CLIENT_SECRET=
# GOOGLE_CLIENT_ID=
# GOOGLE_CLIENT_SECRET=
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: `35 passed`

- [ ] **Step 5: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend && git commit -m "feat: 카카오/구글 소셜 로그인"
```

---

### Task 6: 운영 서빙 + Dockerfile + 배포 문서

**Files:**
- Modify: `backend/app/__init__.py` (SPA 서빙)
- Create: `backend/tests/test_spa.py`, `Dockerfile`, `.dockerignore`, `docs/deploy.md`

**Interfaces:**
- Consumes: `make_app`, `frontend/dist`(Task 3 빌드 결과)
- Produces: 설정 `FRONTEND_DIST`(기본 `<repo>/frontend/dist`), `GET /<path>` → 파일이 있으면 그 파일, 없으면 `index.html`, `/api/*`는 JSON 404

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_spa.py`:
```python
def test_serves_spa_and_assets(make_app, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    c = make_app(FRONTEND_DIST=str(tmp_path)).test_client()

    assert b"root" in c.get("/").data
    assert b"root" in c.get("/some/client/route").data
    assert c.get("/assets/app.js").data == b"console.log(1)"

    res = c.get("/api/nope")
    assert res.status_code == 404
    assert res.get_json() == {"error": "찾을 수 없어요."}
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q tests/test_spa.py`
Expected: FAIL (`/` 404)

- [ ] **Step 3: 구현**

`backend/app/__init__.py`:
- import 교체: `from flask import Flask, abort, jsonify, request, send_from_directory`
- `DEFAULT_MESSAGES` 위에 추가:
```python
DEFAULT_FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
```
- `app.config.from_mapping(...)` 인자에 추가: `FRONTEND_DIST=os.environ.get("FRONTEND_DIST", DEFAULT_FRONTEND_DIST),`
- `return app` 바로 위에 추가:
```python
    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path):
        if path.startswith("api/"):
            abort(404)
        dist = app.config["FRONTEND_DIST"]
        if path and os.path.isfile(os.path.join(dist, path)):
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")
```

- [ ] **Step 4: 통과 확인**

Run: `cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && .venv/bin/pytest -q`
Expected: `36 passed`

- [ ] **Step 5: 운영 방식으로 로컬 실행 확인 (gunicorn + 빌드 결과)**

Run:
```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/frontend" && npm run build
cd "/Users/limhyojin/PycharmProjects/ recipe-ai/backend" && SECRET_KEY=local-check .venv/bin/gunicorn -b 127.0.0.1:8000 "app:create_app()" &
curl -s http://127.0.0.1:8000/ | grep -o '<title>.*</title>'
curl -s http://127.0.0.1:8000/api/me
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/manifest.webmanifest
kill %1
```
Expected: `<title>냉장고 레시피</title>`, `{"error":"로그인이 필요해요."}`, `200`

- [ ] **Step 6: Dockerfile**

`Dockerfile`:
```dockerfile
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /srv/frontend/dist
ENV FRONTEND_DIST=/srv/frontend/dist
CMD flask --app app db upgrade && exec gunicorn -w 2 -b 0.0.0.0:${PORT:-8000} "app:create_app()"
```

`.dockerignore`:
```
**/node_modules
**/.venv
**/__pycache__
backend/instance
backend/.env
frontend/dist
.git
.idea
.omc
```

로컬에 Docker가 없으므로 이미지 빌드는 Render 첫 배포에서 검증한다.

- [ ] **Step 7: 배포 문서**

`docs/deploy.md`:
```markdown
# 배포 가이드 (Render + 카카오/구글 로그인)

## 1. GitHub에 올리기
1. GitHub에서 **비공개** 저장소 생성
2. `git remote add origin <주소> && git push -u origin main`

## 2. Render 데이터베이스
1. https://dashboard.render.com → New → **PostgreSQL**
2. Region: **Singapore**(한국과 가장 가까움)
3. 생성 후 **Internal Database URL** 복사

## 3. Render 웹 서비스
1. New → **Web Service** → GitHub 저장소 선택
2. Language: **Docker**, Region: DB와 같은 Singapore
3. Environment Variables:
   | 키 | 값 |
   |---|---|
   | `SECRET_KEY` | Generate 버튼으로 생성 |
   | `DATABASE_URL` | 2번에서 복사한 Internal Database URL |
   | `KAKAO_CLIENT_ID` / `KAKAO_CLIENT_SECRET` | 4번에서 발급 |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | 5번에서 발급 |
   `DEV_MODE`는 **절대 넣지 않는다**(넣으면 앱이 시작을 거부함).
4. 배포가 끝나면 주소 확인: `https://<서비스명>.onrender.com` (아래에서 `<도메인>`)

## 4. 카카오 로그인
1. https://developers.kakao.com → 내 애플리케이션 → 애플리케이션 추가
2. 앱 키의 **REST API 키** → `KAKAO_CLIENT_ID`
3. 플랫폼 → Web → 사이트 도메인에 `https://<도메인>` 등록
4. 카카오 로그인 → 활성화 ON → Redirect URI에 `https://<도메인>/auth/callback/kakao` 등록
5. 동의항목 → **닉네임** 설정
6. 보안 → Client Secret 코드 생성, 활성화 → `KAKAO_CLIENT_SECRET`

## 5. 구글 로그인
1. https://console.cloud.google.com → 프로젝트 생성
2. OAuth 동의 화면(외부) 구성
3. 사용자 인증 정보 → OAuth 클라이언트 ID → 웹 애플리케이션
4. 승인된 리디렉션 URI: `https://<도메인>/auth/callback/google`
5. 클라이언트 ID/보안 비밀 → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
6. 동의 화면을 "프로덕션 게시"하기 전까지는 테스트 사용자로 등록한 계정만 로그인 가능

환경변수를 바꾼 뒤에는 Render에서 Manual Deploy → Deploy latest commit.

## 6. 폰에 앱처럼 설치 (갤럭시)
1. Chrome에서 `https://<도메인>` 열기
2. 메뉴(⋮) → **홈 화면에 추가** → 설치
3. 홈 화면 아이콘으로 열면 주소창 없이 앱처럼 실행

## 참고
- Render 무료 웹 서비스는 15분 동안 요청이 없으면 잠들어 첫 접속이 30초가량 느리다.
- Render 무료 PostgreSQL은 생성 30일 후 만료된다. 실제로 쓸 때는 유료 플랜으로 전환한다.
```

- [ ] **Step 8: 커밋**

```bash
cd "/Users/limhyojin/PycharmProjects/ recipe-ai" && git add backend Dockerfile .dockerignore docs/deploy.md && git commit -m "feat: 운영 SPA 서빙, Dockerfile, 배포 문서"
```

---

## 1단계 완료 기준

- `backend/.venv/bin/pytest -q` → 36 passed
- `frontend`에서 `npm run build` 성공
- 사용자가 폰에서 개발용 로그인 → 재료 추가/수정/삭제 → 임박 배지 확인(Task 4 체크포인트)
- 배포는 사용자가 GitHub 저장소·Render·카카오/구글 계정을 준비하면 `docs/deploy.md`대로 진행
