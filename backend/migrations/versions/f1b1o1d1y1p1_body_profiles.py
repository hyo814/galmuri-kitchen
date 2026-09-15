"""body profiles (하루 칼로리 목표용 몸 정보, 21절)

Revision ID: f1b1o1d1y1p1
Revises: e1p1u1r1c1h1
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "f1b1o1d1y1p1"
down_revision = "e1p1u1r1c1h1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "body_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sex", sa.String(length=6), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("activity", sa.String(length=12), nullable=False),
        sa.Column("goal", sa.String(length=10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_body_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_body_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_body_profiles_user_id")),
    )


def downgrade():
    op.drop_table("body_profiles")
