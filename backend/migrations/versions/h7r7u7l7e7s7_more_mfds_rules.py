"""가공유·유산균음료 소비기한 규칙 추가 (식약처 1차 공개분 나머지, 사용자 결정 2026-09-19)

Revision ID: h7r7u7l7e7s7
Revises: h6t6o6o6l6s6
Create Date: 2026-09-19

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "h7r7u7l7e7s7"
down_revision = "h6t6o6o6l6s6"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본값을 고정한다. app/defaults.py DEFAULT_RULES에 이번에 더한 줄과 같다.
# 가공유 24일·유산균음료 26일(식약처 참고값)을 구입일 기준 80%(내림)에서 빨강, 그 3일 전부터 노랑으로.
NEW_RULES = [
    ("딸기우유", 16, 19, "mfds"),
    ("초코우유", 16, 19, "mfds"),
    ("바나나우유", 16, 19, "mfds"),
    ("야쿠르트", 17, 20, "mfds"),
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
