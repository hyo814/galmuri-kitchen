"""체험하기 계정(심사·둘러보기용). DEMO_LOGIN=1일 때만 켜진다(DEV_MODE와 무관, 운영에서도 켤 수 있다).
누를 때마다 예시 재고가 든 새 사용자를 만들고, 24시간 지나면 `flask purge-demo-users`(와 체험하기 요청 때 조금씩)로 지운다.
사용자 데이터는 모두 users.id에 ON DELETE CASCADE로 묶여 있어 users 행만 지우면 된다."""

import hashlib
import hmac
import json
import secrets
import zlib
from datetime import timedelta

import click
from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy import text

from .auth import login_user, user_json
from .defaults import seed_user_defaults
from .ingredients import seoul_today
from .models import Ingredient, Recipe, Seasoning, Staple, StorageLocation, User, db, utcnow
from .public_recipes import SAMPLE_FILE

bp = Blueprint("demo", __name__, cli_group=None)  # 명령은 `flask purge-demo-users`

PROVIDER = "demo"
NICKNAME = "체험 사용자"
TTL = timedelta(hours=24)
IP_HOURLY_LIMIT = 10  # 같은 IP에서 1시간에 만들 수 있는 체험 계정 수
MAX_ACTIVE = 500  # 지워지기 전(24시간 안) 체험 계정 전체 상한
PURGE_BATCH = 50  # 체험하기 요청 한 번에 함께 지우는 만료 계정 수

# (이름, 수량, 단위, 위치 종류, 며칠 전 구입, 유통기한까지 남은 날 또는 None)
INGREDIENTS = [
    ("두부", 1, "모", "fridge", 3, 1),
    ("대파", 1, "단", "fridge", 5, 2),
    ("달걀", 8, "개", "fridge", 4, None),
    ("우유", 1, "L", "fridge", 2, 6),
    ("애호박", 1, "개", "fridge", 2, None),
    ("김치", 1, "kg", "fridge", 10, None),
    ("돼지고기 앞다리살", 600, "g", "freezer", 12, None),
    ("냉동 만두", 1, "봉지", "freezer", 30, None),
    ("양파", 3, "개", "room", 6, None),
    ("감자", 4, "개", "room", 7, None),
]
STAPLES = [("간장", "조미료"), ("대파", "야채"), ("달걀", "기타")]  # 간장은 재고에 없어 '떨어졌어요'로 보인다
RECIPE_SAMPLES = ("SAMPLE-01", "SAMPLE-02")  # 된장찌개, 김치찌개
SEASONING = {
    "name": "우리집 제육볶음 양념",
    "basis": "main_weight",
    "basis_amount": 600,
    "basis_unit": "g",
    "main_ingredient": "돼지고기",
    "items": [
        {"name": "고추장", "amount": 2, "unit": "큰술"},
        {"name": "고춧가루", "amount": 1, "unit": "큰술"},
        {"name": "간장", "amount": 1, "unit": "큰술"},
        {"name": "설탕", "amount": 0.5, "unit": "큰술"},
        {"name": "다진 마늘", "amount": 1, "unit": "큰술"},
    ],
}


def ip_key(ip):
    """IP를 그대로 저장하지 않는다: SECRET_KEY로 서명한 해시 앞 16자. provider_id 앞에 붙여 IP별 횟수를 센다."""
    return hmac.new(current_app.config["SECRET_KEY"].encode(), (ip or "").encode(), hashlib.sha256).hexdigest()[:16]


def seed_demo_data(user_id):
    """새 사용자 기본값 + 예시 재고·필수품·레시피 2개·양념 비율 1개. commit은 호출 측에서."""
    seed_user_defaults(user_id)
    db.session.flush()
    locations = {loc.kind: loc.id for loc in StorageLocation.query.filter_by(user_id=user_id)}
    today = seoul_today()
    for name, quantity, unit, kind, bought_ago, expires_in in INGREDIENTS:
        db.session.add(
            Ingredient(
                user_id=user_id,
                location_id=locations[kind],
                name=name,
                quantity=quantity,
                unit=unit,
                purchased_on=today - timedelta(days=bought_ago),
                expires_on=None if expires_in is None else today + timedelta(days=expires_in),
            )
        )
    for name, category in STAPLES:
        db.session.add(Staple(user_id=user_id, name=name, category=category))
    samples = {item["rcp_seq"]: item for item in json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))}
    for seq in RECIPE_SAMPLES:
        item = samples[seq]
        db.session.add(
            Recipe(
                user_id=user_id,
                title=item["title"],
                servings=item["servings"],
                ingredients=item["ingredients"],
                steps=item["steps"],
                source="mine",
            )
        )
    db.session.add(Seasoning(user_id=user_id, **SEASONING))


def purge_expired(limit=None):
    """24시간 지난 체험 계정을 지운다(데이터는 CASCADE). 지운 수를 돌려준다. commit은 호출 측에서."""
    query = db.session.query(User.id).filter(User.provider == PROVIDER, User.created_at < utcnow() - TTL).order_by(User.id)
    ids = [user_id for (user_id,) in (query.limit(limit) if limit else query)]
    if ids:
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
    return len(ids)


@bp.post("/api/demo-login")
def demo_login():
    if not current_app.config["DEMO_LOGIN"]:
        abort(404)
    if db.session.get_bind().dialect.name == "postgresql":
        # 동시에 눌러도 IP 한도·전체 상한을 함께 넘지 않게 체험 계정 만들기를 한 줄로 세운다(커밋 때 풀린다).
        db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": zlib.crc32(b"demo-login") & 0x7FFFFFFF})
    purge_expired(PURGE_BATCH)
    now = utcnow()
    key = ip_key(request.remote_addr)
    demo_users = User.query.filter(User.provider == PROVIDER)
    if demo_users.filter(User.provider_id.startswith(f"{key}."), User.created_at >= now - timedelta(hours=1)).count() >= IP_HOURLY_LIMIT:
        db.session.commit()  # 지운 만료 계정은 남긴다
        abort(429, "체험하기를 너무 많이 눌렀어요. 잠시 후 다시 시도해주세요.")
    if demo_users.filter(User.created_at >= now - TTL).count() >= MAX_ACTIVE:
        db.session.commit()
        abort(503, "지금은 체험하는 분이 많아요. 잠시 후 다시 시도해주세요.")
    user = User(provider=PROVIDER, provider_id=f"{key}.{secrets.token_hex(16)}", nickname=NICKNAME, created_at=now)
    db.session.add(user)
    db.session.flush()
    seed_demo_data(user.id)
    db.session.commit()
    login_user(user)
    return user_json(user)


@bp.cli.command("purge-demo-users")
def purge_demo_users():
    """24시간 지난 체험 계정과 그 데이터를 지운다. Render Cron Job으로 한 시간마다 돌린다(docs/deploy.md)."""
    removed = purge_expired()
    db.session.commit()
    click.echo(f"체험 계정 {removed}개를 지웠어요.")
