"""ai calls

Revision ID: a5b5c5d5e5f5
Revises: a4b4c4d4e4f4
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a5b5c5d5e5f5"
down_revision = "a4b4c4d4e4f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_ai_calls_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_calls")),
    )
    op.create_index(op.f("ix_ai_calls_created_at"), "ai_calls", ["created_at"], unique=False)
    op.create_index(op.f("ix_ai_calls_user_id"), "ai_calls", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_ai_calls_user_id"), table_name="ai_calls")
    op.drop_index(op.f("ix_ai_calls_created_at"), table_name="ai_calls")
    op.drop_table("ai_calls")
