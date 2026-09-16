"""food_logs.nutrition_incomplete (값이 빠진 영양소 표시, 스펙 21절 결정 14 개정 2)

Revision ID: h3i3n3c3m3p3
Revises: h2c2o2o2k2l2
Create Date: 2026-09-16

"""
import sqlalchemy as sa
from alembic import op

revision = "h3i3n3c3m3p3"
down_revision = "h2c2o2o2k2l2"
branch_labels = None
depends_on = None


# recreate="never": SQLite에서 food_logs를 다시 만들면(batch 기본) 표를 지울 때 외래 키 CASCADE가 돌아
# 기록 사진(food_log_photos)이 지워지고 요리 일기 연결(cook_logs.food_log_id)이 끊긴다. 칸 더하기·빼기는 ALTER TABLE로 된다(SQLite 3.35+).


def upgrade():
    # 지난 스냅숏은 어떤 값이 빠졌는지 알 수 없어 NULL로 둔다(다시 계산하면 스냅숏 값이 바뀌므로 채우지 않는다)
    with op.batch_alter_table("food_logs", recreate="never") as b:
        b.add_column(sa.Column("nutrition_incomplete", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("food_logs", recreate="never") as b:
        b.drop_column("nutrition_incomplete")
