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
