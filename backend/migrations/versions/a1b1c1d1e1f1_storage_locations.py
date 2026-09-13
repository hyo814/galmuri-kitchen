"""storage locations

Revision ID: a1b1c1d1e1f1
Revises: 69204259dd5d
Create Date: 2026-09-13

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "a1b1c1d1e1f1"
down_revision = "69204259dd5d"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본값을 고정한다(앱 코드가 바뀌어도 이 마이그레이션의 결과는 같아야 함)
DEFAULT_LOCATIONS = [("냉장실", "fridge"), ("냉동실", "freezer"), ("실온", "room")]


def upgrade():
    op.create_table(
        "storage_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_storage_locations_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_storage_locations")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_storage_locations_user_id")),
    )
    with op.batch_alter_table("storage_locations") as batch_op:
        batch_op.create_index(batch_op.f("ix_storage_locations_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.add_column(sa.Column("location_id", sa.Integer(), nullable=True))

    # 기존 사용자에게 기본 위치를 만들고, 기존 재료는 모두 냉장실로 옮긴다
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all():
        for order, (name, kind) in enumerate(DEFAULT_LOCATIONS):
            conn.execute(
                sa.text(
                    "INSERT INTO storage_locations (user_id, name, kind, sort_order, created_at) "
                    "VALUES (:user_id, :name, :kind, :sort_order, :created_at)"
                ),
                {"user_id": user_id, "name": name, "kind": kind, "sort_order": order, "created_at": now},
            )
        fridge_id = conn.execute(
            sa.text(
                "SELECT id FROM storage_locations WHERE user_id = :user_id AND kind = 'fridge' "
                "ORDER BY sort_order LIMIT 1"
            ),
            {"user_id": user_id},
        ).scalar()
        conn.execute(
            sa.text("UPDATE ingredients SET location_id = :location_id WHERE user_id = :user_id"),
            {"location_id": fridge_id, "user_id": user_id},
        )

    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.alter_column("location_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f("ix_ingredients_location_id"), ["location_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_ingredients_location_id_storage_locations"), "storage_locations", ["location_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_ingredients_location_id_storage_locations"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_ingredients_location_id"))
        batch_op.drop_column("location_id")
    with op.batch_alter_table("storage_locations") as batch_op:
        batch_op.drop_index(batch_op.f("ix_storage_locations_user_id"))
    op.drop_table("storage_locations")
