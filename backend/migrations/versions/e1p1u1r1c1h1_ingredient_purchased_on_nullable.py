"""ingredients.purchased_on nullable (구입일 기억 안 나요)

Revision ID: e1p1u1r1c1h1
Revises: d1m1e1a1l1s1
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "e1p1u1r1c1h1"
down_revision = "d1m1e1a1l1s1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.alter_column("purchased_on", existing_type=sa.Date(), nullable=True)


def downgrade():
    # 되돌리면 모르던 구입일은 넣은 날(서울 날짜)로 채운다
    if op.get_bind().dialect.name == "postgresql":
        op.execute("UPDATE ingredients SET purchased_on = (created_at AT TIME ZONE 'Asia/Seoul')::date WHERE purchased_on IS NULL")
    else:
        op.execute("UPDATE ingredients SET purchased_on = date(created_at, '+9 hours') WHERE purchased_on IS NULL")
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.alter_column("purchased_on", existing_type=sa.Date(), nullable=False)
