"""우리 집 비법 (cooking_tips, 사용자 결정 2026-09-20)

Revision ID: h9t9i9p9s9
Revises: h8f8i8s8h8
Create Date: 2026-09-20

"""
import sqlalchemy as sa
from alembic import op

revision = "h9t9i9p9s9"
down_revision = "h8f8i8s8h8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cooking_tips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_cooking_tips_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cooking_tips")),
    )
    with op.batch_alter_table("cooking_tips") as batch_op:
        batch_op.create_index(batch_op.f("ix_cooking_tips_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("cooking_tips") as batch_op:
        batch_op.drop_index(batch_op.f("ix_cooking_tips_user_id"))
    op.drop_table("cooking_tips")
