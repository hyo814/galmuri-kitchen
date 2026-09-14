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
    purchased_on = db.Column(db.Date, nullable=False)
    expires_on = db.Column(db.Date)
    price = db.Column(db.Integer)
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
    done_at = db.Column(db.DateTime(timezone=True))
    done_changed_at = db.Column(db.DateTime(timezone=True))  # 체크·해제를 마지막으로 바꾼 기기 시각(스펙 19절)
    stocked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class AiCall(db.Model):
    __tablename__ = "ai_calls"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)  # fridge | receipt | order | memo | recipe | link | link_fetch·channel_add·video_refresh(외부 요청 기록)·export(데이터 내보내기), 모두 모델·토큰 없음
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
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
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
