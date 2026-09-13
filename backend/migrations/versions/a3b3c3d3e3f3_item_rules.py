"""item rules

Revision ID: a3b3c3d3e3f3
Revises: a2b2c2d2e2f2
Create Date: 2026-09-13

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "a3b3c3d3e3f3"
down_revision = "a2b2c2d2e2f2"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본 규칙을 숫자로 고정한다 (app/defaults.py DEFAULT_RULES와 같은 값)
DEFAULT_RULES = [
    ("달걀", 25, 30, "user"),
    ("계란", 25, 30, "user"),
    ("두부", 15, 18, "mfds"),
    ("요거트", 22, 25, "mfds"),
    ("요구르트", 22, 25, "mfds"),
    ("주스", 25, 28, "mfds"),
    ("빵", 21, 24, "mfds"),
    ("어묵", 30, 33, "mfds"),
    ("소시지", 41, 44, "mfds"),
    ("햄", 42, 45, "mfds"),
]


def upgrade():
    op.create_table(
        "item_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=20), nullable=False),
        sa.Column("warn_days", sa.Integer(), nullable=False),
        sa.Column("danger_days", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_item_rules_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_rules")),
        sa.UniqueConstraint("user_id", "keyword", name=op.f("uq_item_rules_user_id")),
    )
    with op.batch_alter_table("item_rules") as batch_op:
        batch_op.create_index(batch_op.f("ix_item_rules_user_id"), ["user_id"], unique=False)

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    insert_rule = sa.text(
        "INSERT INTO item_rules (user_id, keyword, warn_days, danger_days, source, created_at) "
        "VALUES (:user_id, :keyword, :warn_days, :danger_days, :source, :created_at)"
    ).bindparams(sa.bindparam("created_at", type_=sa.DateTime(timezone=True)))
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all():
        for keyword, warn_days, danger_days, source in DEFAULT_RULES:
            conn.execute(
                insert_rule,
                {
                    "user_id": user_id,
                    "keyword": keyword,
                    "warn_days": warn_days,
                    "danger_days": danger_days,
                    "source": source,
                    "created_at": now,
                },
            )


def downgrade():
    with op.batch_alter_table("item_rules") as batch_op:
        batch_op.drop_index(batch_op.f("ix_item_rules_user_id"))
    op.drop_table("item_rules")
