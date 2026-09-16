"""cook_logs.manual (레시피 없이 쓴 요리 일기, 스펙 29절 추가 2026-09-16)

Revision ID: h4d4i4a4r4y4
Revises: h3i3n3c3m3p3
Create Date: 2026-09-16

"""
import sqlalchemy as sa
from alembic import op

revision = "h4d4i4a4r4y4"
down_revision = "h3i3n3c3m3p3"
branch_labels = None
depends_on = None


# recreate="never": SQLite에서 cook_logs를 다시 만들면(batch 기본) 표를 지울 때 외래 키 CASCADE로
# 쓴 재료 줄(cook_log_items)이 지워진다. 칸 더하기·빼기는 ALTER TABLE로 된다(SQLite 3.35+).


def upgrade():
    # 지난 일기는 모두 레시피로 남긴 것이라 false(레시피를 지운 일기도 false — 직접 쓴 일기와 구별)
    with op.batch_alter_table("cook_logs", recreate="never") as b:
        b.add_column(sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("cook_logs", recreate="never") as b:
        b.drop_column("manual")
