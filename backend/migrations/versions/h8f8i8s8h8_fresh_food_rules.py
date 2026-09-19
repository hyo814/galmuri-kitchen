"""신선 수산물·김치 소비기한 규칙 (수품원·농진청, 사용자 결정 2026-09-20)

Revision ID: h8f8i8s8h8
Revises: h7r7u7l7e7s7
Create Date: 2026-09-20

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "h8f8i8s8h8"
down_revision = "h7r7u7l7e7s7"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본값을 고정한다. app/defaults.py DEFAULT_RULES에 이번에 더한 줄과 같다.
# 출처: nfqs 국립수산물품질관리원(신선 수산물 보관 요령), rda 농촌진흥청(김장 김치).
# 조사 근거는 docs/superpowers/fresh-food-shelf-life.md.
NEW_RULES = [
    ("생선", 1, 2, "nfqs"),
    ("오징어", 1, 2, "nfqs"),
    ("새우", 2, 3, "nfqs"),
    ("조개", 2, 3, "nfqs"),
    ("가리비", 2, 3, "nfqs"),
    ("굴", 4, 5, "nfqs"),
    ("김치", 75, 90, "rda"),
]


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    existing = {
        (user_id, keyword) for user_id, keyword in conn.execute(sa.text("SELECT user_id, keyword FROM item_rules")).all()
    }

    # 기존 사용자에게 빠진 규칙만 채운다(같은 키워드를 직접 만들어 뒀으면 그 값을 그대로 둔다 — 다시 돌려도 안전).
    rows = [
        {"user_id": user_id, "keyword": keyword, "warn_days": warn, "danger_days": danger, "source": source,
         "created_at": now}
        for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all()
        for keyword, warn, danger, source in NEW_RULES
        if (user_id, keyword) not in existing
    ]
    if rows:
        insert_missing = sa.text(
            "INSERT INTO item_rules (user_id, keyword, warn_days, danger_days, source, created_at) "
            "VALUES (:user_id, :keyword, :warn_days, :danger_days, :source, :created_at)"
        ).bindparams(sa.bindparam("created_at", type_=sa.DateTime(timezone=True)))
        conn.execute(insert_missing, rows)


def downgrade():
    # 규칙 행은 사용자가 고쳤을 수 있어 지우지 않는다(사용자 데이터 보존). 칸 변경도 없다.
    pass
