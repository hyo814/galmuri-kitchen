"""체험하기 계정(심사·둘러보기용). DEMO_LOGIN=1일 때만 켜진다(DEV_MODE와 무관, 운영에서도 켤 수 있다).
누를 때마다 예시 재고가 든 새 사용자를 만들고, 24시간 지나면 `flask purge-demo-users`(와 체험하기 요청 때 조금씩)로 지운다.
사용자 데이터는 모두 users.id에 ON DELETE CASCADE로 묶여 있어 users 행만 지우면 된다. 메모 사진 파일만 커밋 뒤 storage.delete로 따로 지운다."""

import hashlib
import hmac
import ipaddress
import json
import secrets
import zlib
from datetime import timedelta

import click
from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy import text

from . import storage
from .auth import login_user, user_json
from .defaults import seed_user_defaults
from .ingredients import seoul_today
from .models import (
    Ingredient,
    MealPlan,
    MealSlot,
    Recipe,
    Seasoning,
    ShoppingItem,
    ShoppingNote,
    ShoppingNotePhoto,
    Staple,
    StorageLocation,
    User,
    db,
    utcnow,
)
from .public_recipes import SAMPLE_FILE

bp = Blueprint("demo", __name__, cli_group=None)  # 명령은 `flask purge-demo-users`

PROVIDER = "demo"
NICKNAME = "체험 사용자"
TTL = timedelta(hours=24)
MAX_ACTIVE = 5000  # 체험 계정 전체 상한. 차면 가장 오래된 계정부터 지우고(재활용) 새로 만든다
PURGE_BATCH = 50  # 체험하기 요청 한 번에 함께 지우는 만료·재활용 계정 수 상한

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
DEFAULT_RECIPE_LABEL = "두부조림"  # 이름이 든 예시 레시피가 없을 때 쓰는 출처 태그(스펙 16절)
# 장보기 예시(시안 docs/design/shopping-4/ShoppingList.dc.html). (이름, 수량, 단위, 며칠 뒤(None=날짜 미정), source, 체크됨, 생활용품)
SHOPPING_ITEMS = [
    ("두부", 1, "모", 0, "recipe", False, False),
    ("대파", 1, "단", 0, "urgent", True, False),
    ("청양고추", 1, "봉", 0, "recipe", False, False),
    ("계란", 30, "구", 3, "staple", False, False),
    ("우유", 1, "L", 3, "manual", True, False),
    ("수세미", 1, "개", 3, "manual", False, True),
    ("간장", 1, "병", None, "staple", False, False),  # STAPLES 중 재고에 없는 필수품 → 필수품 배너와 일치
]
STOCKED_SHOPPING_ITEM = ("양파", 1, "망")  # 어제 재고에 넣어 '산 것' 접힘이 보이게
SHOPPING_MEMO = {"place": "이마트 성수점", "body": "세일 수요일까지\n계란은 30구로\n두부 2+1 행사 확인"}
MEAL_PLAN_DAYS = 7
MEAL_PLAN_SERVINGS = 2
_ORDINALS = ["첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째"]
# (오늘부터 며칠 뒤, 끼니, RECIPE_SAMPLES 인덱스(None=직접 쓰기), 직접 쓸 때 제목)
MEAL_PLAN_SLOTS = [
    (0, "dinner", 0, None),  # 오늘 저녁: 된장찌개(SAMPLE-01)
    (1, "lunch", 1, None),  # 내일 점심: 김치찌개(SAMPLE-02)
    (1, "breakfast", None, "토스트"),  # 내일 아침: 직접 쓰기(레시피 없음)
    (2, "dinner", 0, None),  # 모레 저녁: 된장찌개 재사용
]


def default_plan_name(start, days):
    """식단 기본 이름(스펙 20절). frontend/src/meals/plan.ts의 defaultPlanName과 같은 규칙 — 둘 다 고치기."""
    if days >= 28:
        return f"{start.month}월 식단"
    first_offset = start.replace(day=1).weekday()  # 월=0(파이썬 date.weekday()가 JS의 (getDay()+6)%7과 같다)
    index = (start.day - 1 + first_offset) // 7
    return f"{start.month}월 {_ORDINALS[index]} 주"


def ip_key(ip):
    """IP를 그대로 저장하지 않는다: SECRET_KEY에서 따로 뽑은 키로 서명한 해시 앞 16자. provider_id 앞에 붙여 IP별 횟수를 센다.
    IPv6는 한 사람이 /64 대역을 통째로 받으므로 /64로 묶는다."""
    try:
        address = ipaddress.ip_address(ip or "")
        ip = str(ipaddress.ip_network(f"{address}/64", strict=False)) if address.version == 6 else str(address)
    except ValueError:
        ip = ip or ""
    key = current_app.config["SECRET_KEY"].encode() + b"|demo-ip"
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()[:16]


def seed_demo_data(user_id):
    """새 사용자 기본값 + 예시 재고·필수품·레시피 2개·양념 비율 1개·장보기(살 것 7개·산 것 1개·메모 1개). commit은 호출 측에서."""
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
    recipes = [samples[seq] for seq in RECIPE_SAMPLES]
    recipe_rows = []  # 식단 칸이 붙일 실제 Recipe 행(recipes는 원본 샘플 dict라 여기 따로 둔다)
    for item in recipes:
        recipe_rows.append(
            Recipe(
                user_id=user_id,
                title=item["title"],
                servings=item["servings"],
                ingredients=item["ingredients"],
                steps=item["steps"],
                source="mine",
            )
        )
    db.session.add_all(recipe_rows)
    db.session.add(Seasoning(user_id=user_id, **SEASONING))

    def recipe_label(name):
        return next((r["title"] for r in recipes if any(ing["name"] == name for ing in r["ingredients"])), DEFAULT_RECIPE_LABEL)

    now = utcnow()
    for name, quantity, unit, days, source, checked, household in SHOPPING_ITEMS:
        db.session.add(
            ShoppingItem(
                user_id=user_id,
                name=name,
                quantity=quantity,
                unit=unit,
                planned_on=None if days is None else today + timedelta(days=days),
                location_id=None if household else locations["fridge"],
                source=source,
                source_label=recipe_label(name) if source == "recipe" else None,
                household=household,
                done_at=now if checked else None,
                done_changed_at=now if checked else None,
            )
        )
    stocked_name, stocked_quantity, stocked_unit = STOCKED_SHOPPING_ITEM
    stocked_at = now - timedelta(days=1)
    db.session.add(
        ShoppingItem(
            user_id=user_id,
            name=stocked_name,
            quantity=stocked_quantity,
            unit=stocked_unit,
            location_id=locations["fridge"],
            source="manual",
            done_at=stocked_at,
            done_changed_at=stocked_at,
            stocked_at=stocked_at,
        )
    )
    db.session.add(ShoppingNote(user_id=user_id, **SHOPPING_MEMO))

    plan = MealPlan(
        user_id=user_id,
        name=default_plan_name(today, MEAL_PLAN_DAYS),
        start_on=today,
        days=MEAL_PLAN_DAYS,
        default_servings=MEAL_PLAN_SERVINGS,
    )
    for days_ahead, meal, recipe_index, free_title in MEAL_PLAN_SLOTS:
        recipe = recipe_rows[recipe_index] if recipe_index is not None else None
        plan.slots.append(
            MealSlot(
                date=today + timedelta(days=days_ahead),
                meal=meal,
                recipe=recipe,
                title=recipe.title if recipe else free_title,
                servings=MEAL_PLAN_SERVINGS,
            )
        )
    db.session.add(plan)


def delete_demo_users(query, limit=None):
    """query(User.id를 고른 체험 계정, 지울 순서대로)의 앞 limit개를 지운다(데이터는 CASCADE, AI 호출 기록은 남음).
    (지운 수, 메모 사진 키)를 돌려준다. commit은 호출 측에서, 사진 파일은 커밋 뒤 storage.delete(키)로(DB가 파일을 지우지 않는다)."""
    ids = [user_id for (user_id,) in (query.limit(limit) if limit else query)]
    keys = []
    if ids:
        photos = db.session.query(ShoppingNotePhoto.photo_key).join(ShoppingNote).filter(ShoppingNote.user_id.in_(ids))
        keys = [key for (key,) in photos]
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
    return len(ids), keys


def purge_expired(limit=None):
    """24시간 지난 체험 계정을 지운다. (지운 수, 메모 사진 키)를 돌려준다."""
    query = db.session.query(User.id).filter(User.provider == PROVIDER, User.created_at < utcnow() - TTL).order_by(User.id)
    return delete_demo_users(query, limit)


@bp.post("/api/demo-login")
def demo_login():
    if not current_app.config["DEMO_LOGIN"]:
        abort(404)
    if db.session.get_bind().dialect.name == "postgresql":
        # 동시에 눌러도 IP 한도·전체 상한을 함께 넘지 않게 체험 계정 만들기를 한 줄로 세운다(커밋 때 풀린다).
        db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": zlib.crc32(b"demo-login") & 0x7FFFFFFF})
    _, keys = purge_expired(PURGE_BATCH)
    now = utcnow()
    key = ip_key(request.remote_addr)
    demo_users = User.query.filter(User.provider == PROVIDER)
    mine = demo_users.filter(User.provider_id.startswith(f"{key}."))
    if (
        mine.filter(User.created_at >= now - timedelta(hours=1)).count() >= current_app.config["DEMO_IP_HOURLY_LIMIT"]
        or mine.filter(User.created_at >= now - TTL).count() >= current_app.config["DEMO_IP_DAILY_LIMIT"]  # 체험 계정이 24시간 살아 있어 그대로 센다
    ):
        db.session.commit()  # 지운 만료 계정은 남긴다
        storage.delete(keys)
        abort(429, "체험하기를 너무 많이 눌렀어요. 잠시 후 다시 시도해주세요.")
    over = demo_users.count() - MAX_ACTIVE + 1
    if over > 0:
        # 가득 차도 심사하는 분이 막히지 않게 가장 오래된 체험 계정부터 지운다. 한 번에 PURGE_BATCH개까지만 지우고, 그래도 차 있으면 거절한다(상한 유지).
        oldest = db.session.query(User.id).filter(User.provider == PROVIDER).order_by(User.created_at, User.id)
        removed, recycled = delete_demo_users(oldest, min(over, PURGE_BATCH))
        keys += recycled
        if removed < over:
            db.session.commit()
            storage.delete(keys)
            abort(503, "지금은 체험하는 분이 많아요. 잠시 후 다시 시도해주세요.")
    user = User(provider=PROVIDER, provider_id=f"{key}.{secrets.token_hex(16)}", nickname=NICKNAME, created_at=now)
    db.session.add(user)
    db.session.flush()
    seed_demo_data(user.id)
    db.session.commit()
    storage.delete(keys)  # 커밋 뒤에 — 커밋이 실패하면 파일은 남아 있어야 한다
    login_user(user)
    return user_json(user)


@bp.cli.command("purge-demo-users")
def purge_demo_users():
    """24시간 지난 체험 계정과 그 데이터를 지운다. Render Cron Job으로 한 시간마다 돌린다(docs/deploy.md)."""
    removed, keys = purge_expired()
    db.session.commit()
    storage.delete(keys)
    click.echo(f"체험 계정 {removed}개를 지웠어요.")
