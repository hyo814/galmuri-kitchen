"""ai calls keep history (user_id SET NULL, demo flag)

Revision ID: c1d1e1m1o1a1
Revises: b5b5c5d5e5f5
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "c1d1e1m1o1a1"
down_revision = "b5b5c5d5e5f5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_calls") as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_ai_calls_user_id_users"), type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key(batch_op.f("fk_ai_calls_user_id_users"), "users", ["user_id"], ["id"], ondelete="SET NULL")
        batch_op.add_column(sa.Column("demo", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.execute("DELETE FROM ai_calls WHERE user_id IS NULL")  # 되돌리면 지워진 사용자의 기록은 남길 수 없다
    with op.batch_alter_table("ai_calls") as batch_op:
        batch_op.drop_column("demo")
        batch_op.drop_constraint(batch_op.f("fk_ai_calls_user_id_users"), type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(batch_op.f("fk_ai_calls_user_id_users"), "users", ["user_id"], ["id"], ondelete="CASCADE")
