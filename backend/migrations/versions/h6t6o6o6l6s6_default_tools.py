"""default kitchen tools (모든 사용자 주방 도구, 사용자 결정 2026-09-19)

Revision ID: h6t6o6o6l6s6
Revises: h5s5t5a5p5l5e5
Create Date: 2026-09-19

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "h6t6o6o6l6s6"
down_revision = "h5s5t5a5p5l5e5"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본값을 고정한다(앱 코드가 바뀌어도 이 마이그레이션의 결과는 같아야 함). app/defaults.py DEFAULT_TOOLS와 같다.
DEFAULT_TOOLS = [
    ("프라이팬", "조리기구", 6), ("냄비", "조리기구", None), ("전기밥솥", "조리기구", None),
    ("식칼", "칼·도마", None), ("도마", "칼·도마", None), ("주방 가위", "칼·도마", None),
    ("국자", "조리도구", None), ("뒤집개", "조리도구", None), ("집게", "조리도구", None),
    ("밥주걱", "조리도구", None),
    ("수세미", "기타", None), ("행주", "기타", None), ("고무장갑", "기타", None),
]


def upgrade():
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    existing = {
        (user_id, name) for user_id, name in conn.execute(sa.text("SELECT user_id, name FROM kitchen_tools")).all()
    }

    # 기존 사용자에게 빠진 기본 도구만 채운다(이미 같은 이름을 만들어 뒀으면 건너뜀 — 다시 돌려도 안전).
    # bought_on·last_checked_on은 비워 둔다: 점검 기준일이 만든 날이 되어(app/tools.py check_base)
    # 프라이팬의 6개월 점검도 시드 직후에는 `점검할 때`로 뜨지 않는다.
    rows = [
        {"user_id": user_id, "name": name, "category": category, "check_every_months": months, "created_at": now}
        for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all()
        for name, category, months in DEFAULT_TOOLS
        if (user_id, name) not in existing
    ]
    if rows:
        insert_missing = sa.text(
            "INSERT INTO kitchen_tools (user_id, name, category, check_every_months, created_at) "
            "VALUES (:user_id, :name, :category, :check_every_months, :created_at)"
        ).bindparams(sa.bindparam("created_at", type_=sa.DateTime(timezone=True)))
        conn.execute(insert_missing, rows)  # 한 번에 묶어 보낸다 — executemany


def downgrade():
    # 도구 행은 사용자가 만들었든 이 마이그레이션이 만들었든 지우지 않는다(사용자 데이터 보존).
    # 칸 변경이 없어 되돌릴 것도 없다.
    pass
