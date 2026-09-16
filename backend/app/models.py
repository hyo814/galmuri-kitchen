import sqlite3
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite has foreign keys OFF by default, so ondelete="CASCADE" (and
    # phase 4's SET NULL) would silently do nothing here while Postgres
    # enforces them in production.
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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


class StorageLocation(db.Model):
    __tablename__ = "storage_locations"
    __table_args__ = (db.UniqueConstraint("user_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # fridge | freezer | room
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Ingredient(db.Model):
    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_locations.id"), nullable=False, index=True)
    location = db.relationship("StorageLocation")
    name = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(10), nullable=False, default="개")
    purchased_on = db.Column(db.Date)  # None: 구입일 모름("기억 안 나요")
    expires_on = db.Column(db.Date)
    price = db.Column(db.Integer)
    price_quantity = db.Column(db.Float)  # 가격을 넣거나 바꾸거나 단위를 바꾼 순간의 수량(재료비 비율 분모, 29절 결정 10). 가격 없으면 NULL
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class IngredientRemoval(db.Model):
    """재료를 지울 때 고른 이유(스펙 27절, 리포트의 버린 재료 수). 이유를 안 고르면 행을 만들지 않는다."""

    __tablename__ = "ingredient_removals"
    __table_args__ = (db.Index("ix_ingredient_removals_user_id_created_at", "user_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)  # 지운 재료 이름(재료 행은 지워지므로 복사)
    reason = db.Column(db.String(10), nullable=False)  # eaten | discarded
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Staple(db.Model):
    __tablename__ = "staples"
    __table_args__ = (db.UniqueConstraint("user_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(10), nullable=False, default="기타")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ItemRule(db.Model):
    __tablename__ = "item_rules"
    __table_args__ = (db.UniqueConstraint("user_id", "keyword"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword = db.Column(db.String(20), nullable=False)
    warn_days = db.Column(db.Integer, nullable=False)
    danger_days = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(10), nullable=False, default="user")  # mfds | user
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class KitchenTool(db.Model):
    __tablename__ = "kitchen_tools"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(30), nullable=False)
    category = db.Column(db.String(10), nullable=False, default="조리도구")
    bought_on = db.Column(db.Date)
    check_every_months = db.Column(db.Integer)
    last_checked_on = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ShoppingItem(db.Model):
    """장보기 항목(스펙 16절). stocked_at이 있으면 재고에 넣은 것(산 것, 7일 보이고 지운다)."""

    __tablename__ = "shopping_items"
    # 기기에서 만든 id로 다시 보내도 하나만 생긴다. client_id가 NULL인 행끼리는 겹쳐도 된다.
    __table_args__ = (db.UniqueConstraint("user_id", "client_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = db.Column(db.String(36))
    name = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=1)
    unit = db.Column(db.String(10), nullable=False, default="개")
    planned_on = db.Column(db.Date)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_locations.id", ondelete="SET NULL"), index=True)
    location = db.relationship("StorageLocation")
    source = db.Column(db.String(10), nullable=False, default="manual")  # manual | recipe | staple | urgent | meal_plan | memo
    source_label = db.Column(db.String(60))  # 태그용(레시피 이름 등)
    household = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())  # 생활용품: 재고에 넣지 않고 산 것으로만
    done_at = db.Column(db.DateTime(timezone=True))
    done_changed_at = db.Column(db.DateTime(timezone=True))  # 체크·해제를 마지막으로 바꾼 기기 시각(스펙 19절)
    stocked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ShoppingNote(db.Model):
    """장보기 메모(스펙 19절). updated_at은 기기가 보낸 저장 시각(edited_at)이라 다시 보내도 같다."""

    __tablename__ = "shopping_notes"
    __table_args__ = (db.UniqueConstraint("user_id", "client_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = db.Column(db.String(36))
    place = db.Column(db.String(30))
    body = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    photos = db.relationship("ShoppingNotePhoto", order_by="ShoppingNotePhoto.id", cascade="all, delete-orphan", passive_deletes=True)


class ShoppingNotePhoto(db.Model):
    """메모 사진. 파일은 storage(photo_key)에 있고, 행이 지워져도 DB가 파일을 지우지 않으므로 지우는 곳에서 storage.delete."""

    __tablename__ = "shopping_note_photos"
    __table_args__ = (db.UniqueConstraint("note_id", "client_id"),)

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.Integer, db.ForeignKey("shopping_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = db.Column(db.String(36))
    photo_key = db.Column(db.String(200), nullable=False, unique=True)
    size = db.Column(db.Integer, nullable=False)  # 바이트, 사용자별 저장 공간 상한용
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class AiCall(db.Model):
    __tablename__ = "ai_calls"

    id = db.Column(db.Integer, primary_key=True)
    # 사용자를 지워도(체험 계정 정리 등) 원가·전체 예산 계산을 위해 기록은 남긴다(user_id만 비운다)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())  # 체험 계정 호출(전체 체험 AI 예산, ai.demo_ai_budget_spent)
    kind = db.Column(db.String(20), nullable=False)  # fridge | receipt | order | memo | recipe | link | recipe_photo | meal | eat_out(사 먹으면 얼마 추정, 29절 결정 11) | nutrition(영양 추정, 토큰 있음) | link_fetch·channel_add·video_refresh·shop_link(외부 요청 기록)·export(데이터 내보내기)·food_fetch(식품영양성분 DB 요청), 모두 모델·토큰 없음
    # 원가 계산용. 단가는 모델마다 달라 모델 이름을 같이 남긴다. 응답을 못 받은 호출(오류·타임아웃)은 비어 있다.
    model = db.Column(db.String(60))
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class PublicRecipe(db.Model):
    """식약처 COOKRCP01 레시피(또는 키가 없을 때 넣는 예시 레시피). 사용자 소유가 아니다."""

    __tablename__ = "public_recipes"

    id = db.Column(db.Integer, primary_key=True)
    rcp_seq = db.Column(db.String(20), nullable=False, unique=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30))  # RCP_PAT2 (반찬, 국&찌개 …)
    method = db.Column(db.String(30))  # RCP_WAY2 (끓이기, 볶기 …)
    kcal = db.Column(db.Float)  # INFO_ENG
    servings = db.Column(db.Integer, nullable=False, default=2)
    ingredients_text = db.Column(db.Text, nullable=False, default="")  # RCP_PARTS_DTLS 원문
    ingredients = db.Column(db.JSON, nullable=False, default=list)  # [{name, amount}]
    ingredient_keys = db.Column(db.JSON, nullable=False, default=list)  # ingredients와 같은 순서의 매칭용 이름
    steps = db.Column(db.JSON, nullable=False, default=list)  # [str]
    image_url = db.Column(db.String(500))
    is_sample = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Recipe(db.Model):
    __tablename__ = "recipes"
    # 같은 공공 레시피를 두 번 저장하지 않는다(동시에 눌러도). public_recipe_id가 NULL인 행끼리는 겹쳐도 된다.
    __table_args__ = (db.UniqueConstraint("user_id", "public_recipe_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(60), nullable=False)
    servings = db.Column(db.Integer, nullable=False, default=2)
    ingredients = db.Column(db.JSON, nullable=False, default=list)  # [{name, amount}]
    steps = db.Column(db.JSON, nullable=False, default=list)  # [str]
    source = db.Column(db.String(20), nullable=False, default="mine")  # mine | public | ai | youtube | instagram | blog | text
    source_url = db.Column(db.String(500))
    public_recipe_id = db.Column(db.Integer, db.ForeignKey("public_recipes.id", ondelete="SET NULL"))
    image_url = db.Column(db.String(500))
    eat_out_price = db.Column(db.Integer)  # 사 먹으면 얼마(1인분, 원, 29절 결정 11)
    eat_out_source = db.Column(db.String(10))  # user | ai | sample
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class MealPlan(db.Model):
    """식단(스펙 20절, 4b-1). 칸은 slots 관계로."""

    __tablename__ = "meal_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(30), nullable=False)
    start_on = db.Column(db.Date, nullable=False)
    days = db.Column(db.Integer, nullable=False)  # 1~31
    default_servings = db.Column(db.Integer, nullable=False, default=1)  # 1~20 (23절 D5)
    goal_kcal = db.Column(db.Integer)  # 하루 목표, 500~5000
    goal_note = db.Column(db.String(100))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    slots = db.relationship(
        "MealSlot", order_by="(MealSlot.date, MealSlot.id)", cascade="all, delete-orphan", passive_deletes=True
    )


class MealSlot(db.Model):
    """식단 칸(끼니 하나). recipe_id가 있으면 레시피 칸, 레시피를 지우면(SET NULL) 제목만 남은 직접 쓰기 칸처럼 된다."""

    __tablename__ = "meal_slots"
    __table_args__ = (db.UniqueConstraint("plan_id", "date", "meal"),)

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    meal = db.Column(db.String(10), nullable=False)  # breakfast | lunch | dinner | snack
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="SET NULL"), index=True)
    title = db.Column(db.String(60), nullable=False)
    servings = db.Column(db.Integer, nullable=False, default=1)  # 1~20
    est_kcal = db.Column(db.Integer)  # 1인분 추정치, AI 초안으로 채운 칸만
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    recipe = db.relationship("Recipe")


class BodyProfile(db.Model):
    """하루 칼로리 목표 계산용 몸 정보(스펙 21절). 건강 정보라 본인만 보고, 계정을 지우면 함께 지운다. 목표 kcal은 화면이 계산한다."""

    __tablename__ = "body_profiles"
    __table_args__ = (db.UniqueConstraint("user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sex = db.Column(db.String(6), nullable=False)  # female | male
    birth_year = db.Column(db.Integer, nullable=False)
    height_cm = db.Column(db.Float, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    activity = db.Column(db.String(12), nullable=False)  # sedentary | light | moderate | active | very_active
    goal = db.Column(db.String(10), nullable=False)  # maintain | lose | gain
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Seasoning(db.Model):
    """사용자 "내 비율"(스펙 22절). 기본 양념은 화면 데이터 파일(frontend/src/data/seasoningPresets.ts)에 있다."""

    __tablename__ = "seasonings"
    __table_args__ = (db.UniqueConstraint("user_id", "name"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(30), nullable=False)
    basis = db.Column(db.String(20), nullable=False)  # main_weight | servings | yield
    basis_amount = db.Column(db.Float, nullable=False)
    basis_unit = db.Column(db.String(10), nullable=False)  # g | 인분 | 컵 | ml
    main_ingredient = db.Column(db.String(50))  # main_weight일 때만
    items = db.Column(db.JSON, nullable=False, default=list)  # [{name, amount, unit}], 순서 = 표시 순서
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class YoutubeChannel(db.Model):
    """요리 채널(스펙 17절). 여러 사용자가 같이 쓰는 캐시라 사용자 소유가 아니다. 기본 채널은 is_default."""

    __tablename__ = "youtube_channels"

    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.String(30), nullable=False, unique=True)  # UC…
    title = db.Column(db.String(100), nullable=False, default="")
    thumbnail_url = db.Column(db.String(500))
    uploads_playlist_id = db.Column(db.String(40))
    video_count = db.Column(db.Integer)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    fetched_at = db.Column(db.DateTime(timezone=True))  # 마지막으로 새로 받은 때(실패 포함). NULL이면 아직 안 받음
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class UserChannel(db.Model):
    """hidden=false 행은 내가 추가한 채널, hidden=true 행은 숨긴 기본 채널."""

    __tablename__ = "user_channels"
    __table_args__ = (db.UniqueConstraint("user_id", "channel_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("youtube_channels.id", ondelete="CASCADE"), nullable=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class FoodNutrient(db.Model):
    """식품 한 행의 100g(100ml)당 영양. 사용자 소유가 아닌 공유 캐시(스펙 21절).
    source: api(공공데이터포털) | sample(키 없는 개발 모드) | ai('추정으로 두기' AI 추정, food_code 'ai:<재료 키>')."""

    __tablename__ = "food_nutrients"

    id = db.Column(db.Integer, primary_key=True)
    food_code = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    name_key = db.Column(db.String(60), nullable=False, index=True)  # foods.food_name_key(name)
    group_name = db.Column(db.String(20), nullable=False, default="")  # 음식 | 가공식품 | 원재료성 | 추정
    kcal = db.Column(db.Float, nullable=False)
    carbs_g = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    fat_g = db.Column(db.Float)
    sugars_g = db.Column(db.Float)
    sodium_mg = db.Column(db.Float)
    serving_g = db.Column(db.Float)  # 식품중량(1인분 g, 음식 행에만 있음, 없으면 NULL). foods.FIELDS["serving"]
    source = db.Column(db.String(10), nullable=False)
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class FoodSearch(db.Model):
    """이 이름으로 식품 DB를 찾아봤다는 기록(결과 행은 food_nutrients). 30일 지나면 다시 찾는다(결정 11)."""

    __tablename__ = "food_searches"

    id = db.Column(db.Integer, primary_key=True)
    query_key = db.Column(db.String(60), nullable=False, unique=True)  # normalize(검색어)
    total = db.Column(db.Integer, nullable=False, default=0)  # API totalCount
    searched_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class FoodMatch(db.Model):
    """재료 이름 → 고른 식품(사용자별 기억, 결정 B). food_code가 NULL이면 '추정으로 두기'. unit_grams는 사용자가 고친 한 단위 무게 {"모": 300}."""

    __tablename__ = "food_matches"
    __table_args__ = (db.UniqueConstraint("user_id", "ingredient_key"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_key = db.Column(db.String(60), nullable=False)
    food_code = db.Column(db.String(80))
    unit_grams = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class UnitWeightEstimate(db.Model):
    """재료 한 단위 무게 추정(모든 사용자가 함께 쓴다, 결정 7). 사용자가 고친 값은 food_matches.unit_grams."""

    __tablename__ = "unit_weight_estimates"
    __table_args__ = (db.UniqueConstraint("name_key", "unit"),)

    id = db.Column(db.Integer, primary_key=True)
    name_key = db.Column(db.String(60), nullable=False)
    unit = db.Column(db.String(10), nullable=False)
    grams = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(10), nullable=False)  # ai | sample
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class YoutubeVideo(db.Model):
    """채널 최근 영상 캐시. 새로 받을 때 채널 영상을 통째로 바꾸고, 30일 넘게 새로 받지 못한 행은 지운다(유튜브 약관)."""

    __tablename__ = "youtube_videos"
    __table_args__ = (db.Index("ix_youtube_videos_published_at_id", "published_at", "id"),)  # 최신순 커서 페이지

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(20), nullable=False, unique=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("youtube_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, default="")
    thumbnail_url = db.Column(db.String(500))
    duration_seconds = db.Column(db.Integer)
    description = db.Column(db.String(500))
    published_at = db.Column(db.DateTime(timezone=True), nullable=False)
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class FoodLog(db.Model):
    """먹은 기록 한 줄(스펙 21·24절). 영양 칸은 저장할 때 계산한 스냅숏 — 레시피를 고쳐도 지난 기록은 그대로(결정 2).
    title이 NULL이면 사진만 먼저 남긴 '사진 기록'. meal_slot_id는 식단 칸 '먹었어요'(칸 하나에 기록 하나)."""

    __tablename__ = "food_logs"
    __table_args__ = (
        db.UniqueConstraint("meal_slot_id"),
        db.Index("ix_food_logs_user_id_eaten_on", "user_id", "eaten_on"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    eaten_on = db.Column(db.Date, nullable=False)
    meal = db.Column(db.String(10), nullable=False)  # breakfast | lunch | dinner | snack
    source = db.Column(db.String(10), nullable=False, default="manual")  # manual | meal_plan | cook_log(5단계)
    title = db.Column(db.String(60))
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="SET NULL"), index=True)
    meal_slot_id = db.Column(db.Integer, db.ForeignKey("meal_slots.id", ondelete="SET NULL"))
    food_code = db.Column(db.String(80))  # food_nutrients.food_code — 공유 캐시라 FK 아님
    servings = db.Column(db.Float)
    grams = db.Column(db.Integer)
    place = db.Column(db.String(4))  # home | out
    rating = db.Column(db.Integer)
    memo = db.Column(db.String(200))
    kcal = db.Column(db.Integer)
    carbs_g = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    fat_g = db.Column(db.Float)
    sugars_g = db.Column(db.Float)
    sodium_mg = db.Column(db.Integer)
    # 레시피 계산에서 값이 빠진 영양소 → 재료 이름 {"sodium_mg": ["된장"]}, 없으면 NULL(None을 JSON null이 아니라 SQL NULL로)
    nutrition_incomplete = db.Column(db.JSON(none_as_null=True))
    approx = db.Column(db.Boolean, nullable=False, default=False)
    nutrition_pending = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    recipe = db.relationship("Recipe")
    meal_slot = db.relationship("MealSlot", backref=db.backref("food_log", uselist=False))
    photos = db.relationship("FoodLogPhoto", order_by="FoodLogPhoto.id", cascade="all, delete-orphan", passive_deletes=True)


class FoodLogPhoto(db.Model):
    """먹은 기록 사진(기록당 4장, 결정 9). 파일은 storage(photo_key). 행이 지워져도 DB가 파일을 지우지 않으므로 지우는 곳에서 storage.delete."""

    __tablename__ = "food_log_photos"

    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey("food_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_key = db.Column(db.String(200), nullable=False, unique=True)
    size = db.Column(db.Integer, nullable=False)  # 바이트, 사용자별 저장 공간 상한용
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class CookLog(db.Model):
    """요리 일기 한 건(스펙 4·29절). 돈 칸은 저장할 때 계산한 값 — 레시피·재고를 고쳐도 지난 일기는 그대로(결정 13·14)."""

    __tablename__ = "cook_logs"
    __table_args__ = (db.Index("ix_cook_logs_user_id_cooked_on", "user_id", "cooked_on"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="SET NULL"), index=True)
    food_log_id = db.Column(db.Integer, db.ForeignKey("food_logs.id", ondelete="SET NULL"), index=True)  # 먹은 기록을 지울 때 SET NULL이 cook_logs 전체를 훑지 않게(개정 1 T4⑤)
    title = db.Column(db.String(60), nullable=False)
    cooked_on = db.Column(db.Date, nullable=False)
    servings = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Integer)
    memo = db.Column(db.String(500))
    photo_key = db.Column(db.String(200), unique=True)
    photo_size = db.Column(db.Integer)
    eat_out_price = db.Column(db.Integer)  # 1인분(원)
    eat_out_source = db.Column(db.String(10))  # user | ai | sample
    ingredient_cost = db.Column(db.Integer, nullable=False, default=0)
    saved = db.Column(db.Integer)  # None = 계산 못 함(결정 14)
    excluded_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    recipe = db.relationship("Recipe")
    food_log = db.relationship("FoodLog")
    items = db.relationship("CookLogItem", order_by="CookLogItem.id", cascade="all, delete-orphan", passive_deletes=True)


class CookLogItem(db.Model):
    """요리에 쓴 재료 한 줄. 재고에서 뺀 줄은 되돌리기용 스냅숏(결정 7·8), 재고에 없던 레시피 재료는 이름·양만(가격 모름)."""

    __tablename__ = "cook_log_items"

    id = db.Column(db.Integer, primary_key=True)
    cook_log_id = db.Column(db.Integer, db.ForeignKey("cook_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id", ondelete="SET NULL"), index=True)  # 남은 재료만(지운 재료는 처음부터 NULL)
    removal_id = db.Column(db.Integer, db.ForeignKey("ingredient_removals.id", ondelete="SET NULL"), index=True)  # 다 먹었어요 기록을 지울 때 SET NULL이 전체를 훑지 않게
    name = db.Column(db.String(50), nullable=False)
    amount_text = db.Column(db.String(30))  # 재고에 없던 재료의 레시피 양
    used = db.Column(db.Float)  # 뺀 양(재고 단위)
    unit = db.Column(db.String(10))
    quantity_before = db.Column(db.Float)
    removed = db.Column(db.Boolean, nullable=False, default=False)
    location_id = db.Column(db.Integer)  # 스냅숏(FK 아님 — 위치가 지워져도 되돌리기가 기본 위치로)
    purchased_on = db.Column(db.Date)
    expires_on = db.Column(db.Date)
    price = db.Column(db.Integer)
    price_quantity = db.Column(db.Float)
    cost = db.Column(db.Integer)
    excluded = db.Column(db.String(10))  # seasoning | no_price | None

    ingredient = db.relationship("Ingredient")
    removal = db.relationship("IngredientRemoval")
