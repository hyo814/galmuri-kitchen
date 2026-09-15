"""food_log_photos (먹은 기록 사진, 4b-3 Task 3)

Revision ID: g3f3l3p3h3o3
Revises: g2f2o2o2d2l2
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "g3f3l3p3h3o3"
down_revision = "g2f2o2o2d2l2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "food_log_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("log_id", sa.Integer(), nullable=False),
        sa.Column("photo_key", sa.String(length=200), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["log_id"], ["food_logs.id"], name=op.f("fk_food_log_photos_log_id_food_logs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_log_photos")),
        sa.UniqueConstraint("photo_key", name=op.f("uq_food_log_photos_photo_key")),
    )
    op.create_index(op.f("ix_food_log_photos_log_id"), "food_log_photos", ["log_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_food_log_photos_log_id"), table_name="food_log_photos")
    op.drop_table("food_log_photos")
