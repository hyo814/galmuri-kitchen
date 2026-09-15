import os
import re

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_migrate import Migrate
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .models import db

DEFAULT_FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
DEFAULT_UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))

DEFAULT_MESSAGES = {
    400: "잘못된 요청이에요.",
    401: "로그인이 필요해요.",
    404: "찾을 수 없어요.",
    405: "허용되지 않는 요청이에요.",
    413: "파일이 너무 커요. 10MB 이하로 올려주세요.",
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
        KAKAO_CLIENT_ID=os.environ.get("KAKAO_CLIENT_ID"),
        KAKAO_CLIENT_SECRET=os.environ.get("KAKAO_CLIENT_SECRET"),
        NAVER_CLIENT_ID=os.environ.get("NAVER_CLIENT_ID"),
        NAVER_CLIENT_SECRET=os.environ.get("NAVER_CLIENT_SECRET"),
        GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID"),
        GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET"),
        FRONTEND_DIST=os.environ.get("FRONTEND_DIST", DEFAULT_FRONTEND_DIST),
        ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY") or None,
        CLAUDE_MODEL=os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5",
        AI_DAILY_SCAN_LIMIT=int(os.environ.get("AI_DAILY_SCAN_LIMIT") or 20),
        AI_SCAN_BURST_LIMIT=int(os.environ.get("AI_SCAN_BURST_LIMIT") or 3),
        AI_DAILY_RECIPE_LIMIT=int(os.environ.get("AI_DAILY_RECIPE_LIMIT") or 20),
        FOODSAFETY_API_KEY=os.environ.get("FOODSAFETY_API_KEY") or None,
        FOOD_NUTRITION_API_KEY=os.environ.get("FOOD_NUTRITION_API_KEY") or None,
        YOUTUBE_API_KEY=os.environ.get("YOUTUBE_API_KEY") or None,
        UPLOAD_DIR=DEFAULT_UPLOAD_DIR,  # R2가 없을 때 개발용 사진 폴더(스펙 3절, gitignore)
        R2_ACCOUNT_ID=os.environ.get("R2_ACCOUNT_ID") or None,
        R2_ACCESS_KEY_ID=os.environ.get("R2_ACCESS_KEY_ID") or None,
        R2_SECRET_ACCESS_KEY=os.environ.get("R2_SECRET_ACCESS_KEY") or None,
        R2_BUCKET=os.environ.get("R2_BUCKET") or None,
        COUPANG_PARTNERS_ID=os.environ.get("COUPANG_PARTNERS_ID") or None,  # 파트너스 트래킹 코드(AF…). 참고용 — 링크는 아래 두 키로 만든다
        COUPANG_ACCESS_KEY=os.environ.get("COUPANG_ACCESS_KEY") or None,  # 파트너스 API 키. 둘 다 있어야 쿠팡 제휴 링크·광고 표시(coupang.py)
        COUPANG_SECRET_KEY=os.environ.get("COUPANG_SECRET_KEY") or None,
        DEMO_LOGIN=os.environ.get("DEMO_LOGIN") == "1",  # 로그인 화면 '로그인 없이 체험하기'(demo.py)
        DEMO_IP_HOURLY_LIMIT=int(os.environ.get("DEMO_IP_HOURLY_LIMIT") or 30),  # 같은 IP(IPv6는 /64)에서 1시간에 만들 수 있는 체험 계정 수. 사무실·행사장처럼 한 주소를 여럿이 쓰면 넉넉히
        DEMO_IP_DAILY_LIMIT=int(os.environ.get("DEMO_IP_DAILY_LIMIT") or 100),  # 같은 IP에서 24시간에 만들 수 있는 체험 계정 수
        DEMO_AI_GLOBAL_DAILY=int(os.environ.get("DEMO_AI_GLOBAL_DAILY") or 300),  # 체험 계정 전체 AI 호출 24시간 예산, 넘으면 예시 결과
        DEMO_NUTRITION_GLOBAL_DAILY=int(os.environ.get("DEMO_NUTRITION_GLOBAL_DAILY") or 30),  # 체험 계정 전체 영양 추정 하루(서울) 횟수, 넘으면 AI 추정 없이 계산
        TRUSTED_PROXY_HOPS=int(os.environ.get("TRUSTED_PROXY_HOPS") or 1),  # X-Forwarded-For를 붙이는 앞단 프록시 수(docs/deploy.md 5-3)
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY 환경변수가 필요합니다.")
    if app.config["DEV_MODE"] and os.environ.get("RENDER"):
        raise RuntimeError("운영(Render)에서는 DEV_MODE를 켤 수 없습니다.")

    # Render 프록시 뒤에서 OAuth 콜백 URL이 https://<도메인> 으로 만들어지도록.
    # x_for: 체험 계정 IP별 한도(demo.py)가 프록시 주소가 아니라 접속한 사람 주소를 보게 한다(TRUSTED_PROXY_HOPS, 기본 1)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config["TRUSTED_PROXY_HOPS"], x_proto=1, x_host=1)

    db.init_app(app)
    Migrate(app, db, render_as_batch=True)

    from .auth import bp as auth_bp
    from .auth import init_oauth
    from .body import bp as body_bp
    from .cooklog import bp as cooklog_bp
    from .coupang import bp as coupang_bp
    from .demo import bp as demo_bp
    from .export import bp as export_bp
    from .food_logs import bp as food_logs_bp
    from .foods import bp as foods_bp
    from .ingredients import bp as ingredients_bp
    from .item_rules import bp as item_rules_bp
    from .locations import bp as locations_bp
    from .meals import bp as meals_bp
    from .nutrition import bp as nutrition_bp
    from .photos import bp as photos_bp
    from .public_recipes import bp as public_recipes_bp
    from .recipe_ai import bp as recipe_ai_bp
    from .recipes import bp as recipes_bp
    from .scan import bp as scan_bp
    from .seasonings import bp as seasonings_bp
    from .shopping import bp as shopping_bp
    from .staples import bp as staples_bp
    from .tools import bp as tools_bp
    from .videos import bp as videos_bp

    init_oauth(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(body_bp)
    app.register_blueprint(cooklog_bp)
    app.register_blueprint(coupang_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(food_logs_bp)
    app.register_blueprint(foods_bp)
    app.register_blueprint(ingredients_bp)
    app.register_blueprint(item_rules_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(meals_bp)
    app.register_blueprint(nutrition_bp)
    app.register_blueprint(photos_bp)
    app.register_blueprint(public_recipes_bp)
    app.register_blueprint(recipe_ai_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(seasonings_bp)
    app.register_blueprint(shopping_bp)
    app.register_blueprint(staples_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(videos_bp)

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

    @app.errorhandler(RecursionError)
    def recursion_error(e):
        # 지나치게 깊은 JSON(예: 중첩 배열)을 파싱할 때 C 확장이 없는 환경 등에서 발생할 수 있다.
        return jsonify(error=DEFAULT_MESSAGES[400]), 400

    @app.route("/api/<path:_>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_not_found(_):
        abort(404)

    # 서비스워커/매니페스트는 캐시 없이 매번 받아야 업데이트가 바로 반영된다.
    NO_CACHE_FILES = {"sw.js": "text/javascript", "manifest.webmanifest": "application/manifest+json"}

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path):
        dist = app.config["FRONTEND_DIST"]
        if path in NO_CACHE_FILES and os.path.isfile(os.path.join(dist, path)):
            res = send_from_directory(dist, path, mimetype=NO_CACHE_FILES[path])
            res.headers["Cache-Control"] = "no-cache"
            return res
        if path and os.path.isfile(os.path.join(dist, path)):
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    return app
