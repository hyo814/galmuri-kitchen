from functools import wraps

import requests
from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, abort, current_app, g, jsonify, redirect, session, url_for

from .ai import scan_mode
from .defaults import seed_user_defaults
from .models import User, db

bp = Blueprint("auth", __name__)

PROVIDERS = {
    "kakao": {
        "authorize_url": "https://kauth.kakao.com/oauth/authorize",
        "access_token_url": "https://kauth.kakao.com/oauth/token",
        "api_base_url": "https://kapi.kakao.com/",
        "client_kwargs": {"token_endpoint_auth_method": "client_secret_post"},
    },
    "naver": {
        "authorize_url": "https://nid.naver.com/oauth2.0/authorize",
        "access_token_url": "https://nid.naver.com/oauth2.0/token",
        "api_base_url": "https://openapi.naver.com/",
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


def login_user(user):
    session.clear()
    session["user_id"] = user.id
    session["pid"] = user.provider_id  # 지운 사용자 id가 다시 쓰여도(SQLite) 옛 세션이 새 사용자로 이어지지 않게
    session.permanent = True


def current_user():
    """세션의 사용자. 없거나 지운 사용자 id가 다시 쓰였으면(pid 다름) None."""
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    return user if user is not None and session.get("pid") == user.provider_id else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if g.user is None:
            abort(401, "로그인이 필요해요.")
        return view(*args, **kwargs)

    return wrapper


def abort_if_id_too_big(obj_id):
    """DB의 int 컬럼 범위 밖 → 조회 없이 바로 404 (500 방지). URL <int:>는 음수를 받지 않는다."""
    if obj_id > 2**31 - 1:
        abort(404, "찾을 수 없어요.")


def get_owned_or_404(model, obj_id):
    abort_if_id_too_big(obj_id)
    obj = db.session.get(model, obj_id)
    if obj is None or obj.user_id != g.user.id:
        abort(404, "찾을 수 없어요.")
    return obj


DEMO_AI_DAILY_LIMIT = 3  # 체험 계정(demo.py)의 사진 인식·AI 레시피(링크 가져오기 포함) 하루 한도


def ai_daily_limit(user, key):
    """AI_DAILY_SCAN_LIMIT·AI_DAILY_RECIPE_LIMIT 설정값. 체험 계정은 DEMO_AI_DAILY_LIMIT보다 크지 않게."""
    limit = current_app.config[key]
    return min(limit, DEMO_AI_DAILY_LIMIT) if user.provider == "demo" else limit


def user_json(user):
    """/api/me와 개발용 로그인이 같은 모양을 돌려준다. scan은 사진으로 추가·AI 레시피 입구 표시용(같은 키로 판단한다).
    ponytail: 이름이 scan이라 헷갈리면 ai로 바꾼다. videos는 영상 칸 표시용."""
    from .videos import video_mode  # videos.py가 auth.login_required를 쓰므로 여기서 불러온다
    return jsonify(
        id=user.id,
        nickname=user.nickname,
        provider=user.provider,  # 더보기 계정 묶음의 '카카오로 로그인했어요' 표시용 (스펙 27절). demo는 체험 계정
        scan=scan_mode(user),
        scan_limit=ai_daily_limit(user, "AI_DAILY_SCAN_LIMIT"),
        recipe_limit=ai_daily_limit(user, "AI_DAILY_RECIPE_LIMIT"),
        videos=video_mode(user),
        # 제휴 링크를 쓸 수 있는 쇼핑몰만 true(스펙 16절). 쿠팡은 서버가 키로 딥링크를 만든다(coupang.py) — 키·트래킹 코드는 넘기지 않는다.
        # 체험 계정은 서버가 늘 일반 링크로 보내므로 광고 표시도 없다
        shop_affiliates=(
            {"coupang": True}
            if current_app.config["COUPANG_ACCESS_KEY"] and current_app.config["COUPANG_SECRET_KEY"] and user.provider != "demo"
            else {}
        ),
    )


def upsert_user(provider, provider_id, nickname):
    user = User.query.filter_by(provider=provider, provider_id=provider_id).first()
    if user is None:
        user = User(provider=provider, provider_id=provider_id)
        db.session.add(user)
        db.session.flush()
        seed_user_defaults(user.id)
    user.nickname = (nickname or "사용자")[:50]
    db.session.commit()
    return user


@bp.get("/api/auth-options")
def auth_options():
    registry = current_app.extensions["recipe_oauth"]
    return jsonify(
        providers=[name for name in PROVIDERS if registry.create_client(name)],
        dev_login=current_app.config["DEV_MODE"],
        demo_login=current_app.config["DEMO_LOGIN"],
    )


@bp.post("/api/dev-login")
def dev_login():
    if not current_app.config["DEV_MODE"]:
        abort(404)
    user = upsert_user("dev", "dev", "개발자")
    login_user(user)
    return user_json(user)


@bp.get("/api/me")
@login_required
def me():
    return user_json(g.user)


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


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
        elif provider == "naver":
            info = client.get("v1/nid/me", token=token).json().get("response") or {}
            provider_id, nickname = info.get("id"), info.get("nickname")
        else:
            info = client.get("v2/user/me", token=token).json()
            provider_id, nickname = info.get("id"), (info.get("properties") or {}).get("nickname")
    except (OAuthError, requests.RequestException, ValueError) as e:
        current_app.logger.warning("oauth %s callback failed: %r", provider, e)
        return redirect("/?login_error=1")
    if not provider_id:
        current_app.logger.warning("oauth %s callback failed: missing provider_id", provider)
        return redirect("/?login_error=1")
    login_user(upsert_user(provider, str(provider_id), nickname))
    return redirect("/")
