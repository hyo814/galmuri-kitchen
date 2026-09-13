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
    from .ingredients import bp as ingredients_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ingredients_bp)

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
