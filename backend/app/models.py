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
