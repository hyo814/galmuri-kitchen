"""food_nutrients.serving_g (음식 1인분 무게, 4b-3 Task 1)

Revision ID: g1s1e1r1v1n1
Revises: f2f2o2o2d2s2
Create Date: 2026-09-15

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "g1s1e1r1v1n1"
down_revision = "f2f2o2o2d2s2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("food_nutrients") as b:
        b.add_column(sa.Column("serving_g", sa.Float(), nullable=True))
    # 이미 캐시된 행은 serving_g가 없으므로 다음 찾기 때 다시 받도록 검색 기록을 되돌린다(결정 4)
    op.execute(sa.text("UPDATE food_searches SET searched_at = :old").bindparams(old=datetime(2000, 1, 1, tzinfo=timezone.utc)))


def downgrade():
    with op.batch_alter_table("food_nutrients") as b:
        b.drop_column("serving_g")
