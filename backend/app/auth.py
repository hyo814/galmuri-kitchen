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
    if obj_id > 2**31 - 1:  # DB의 int 컬럼 범위 밖 → 조회 없이 바로 404 (500 방지)
        abort(404, "찾을 수 없어요.")
    obj = db.session.get(model, obj_id)
    if obj is None or obj.user_id != g.user.id:
        abort(404, "찾을 수 없어요.")
    return obj


def user_json(user):
    """/api/me와 개발용 로그인이 같은 모양을 돌려준다. scan은 사진으로 추가·AI 레시피 입구 표시용(같은 키로 판단한다).
    ponytail: 이름이 scan이라 헷갈리면 ai로 바꾼다. videos는 영상 칸 표시용."""
    from .videos import video_mode  # videos.py가 auth.login_required를 쓰므로 여기서 불러온다
    return jsonify(
        id=user.id,
        nickname=user.nickname,
        scan=scan_mode(),
        scan_limit=current_app.config["AI_DAILY_SCAN_LIMIT"],
        recipe_limit=current_app.config["AI_DAILY_RECIPE_LIMIT"],
        videos=video_mode(),
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
