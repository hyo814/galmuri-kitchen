"""default staples (모든 사용자 필수품, 사용자 결정 2026-09-17)

Revision ID: h5s5t5a5p5l5e5
Revises: h4d4i4a4r4y4
Create Date: 2026-09-17

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "h5s5t5a5p5l5e5"
down_revision = "h4d4i4a4r4y4"
branch_labels = None
depends_on = None

# 마이그레이션 시점의 기본값을 고정한다(앱 코드가 바뀌어도 이 마이그레이션의 결과는 같아야 함). app/defaults.py DEFAULT_STAPLES와 같다.
DEFAULT_STAPLES = [
    ("대파", "야채"), ("양파", "야채"), ("마늘", "야채"), ("생강", "야채"), ("감자", "야채"),
    ("당근", "야채"), ("고추", "야채"), ("바질", "야채"), ("파슬리", "야채"),
    ("멸치 액젓", "조미료"), ("굴소스", "조미료"), ("케찹", "조미료"), ("돈까스소스", "조미료"),
    ("참소스", "조미료"), ("마요네즈", "조미료"), ("머스타드소스", "조미료"), ("식용유", "조미료"),
    ("참기름", "조미료"), ("들기름", "조미료"), ("고추가루", "조미료"), ("고추장", "조미료"),
    ("된장", "조미료"), ("맛술", "조미료"), ("진간장", "조미료"), ("비빔장", "조미료"),
    ("짜장 소스", "조미료"), ("불닭 소스", "조미료"), ("국간장", "조미료"), ("양조간장", "조미료"),
    ("식초", "조미료"), ("발사믹 식초", "조미료"), ("설탕", "조미료"), ("소금", "조미료"),
    ("후추", "조미료"), ("깨소금", "조미료"), ("토마토 파스타 소스", "조미료"), ("크림 파스타 소스", "조미료"),
    ("스위트 칠리 소스", "조미료"), ("춘장", "조미료"), ("카레가루", "조미료"), ("돼지 갈비 양념 소스", "조미료"),
    ("불고기 양념 소스", "조미료"), ("쌈장", "조미료"), ("올리브유", "조미료"), ("밀가루", "조미료"),
    ("튀김가루", "조미료"), ("감자전분가루", "조미료"), ("부침가루", "조미료"), ("매실청", "조미료"),
    ("달걀", "기타"), ("버터", "기타"), ("파스타면", "기타"), ("뿌리는 치즈", "기타"),
    ("기본 치즈", "기타"), ("휘핑 크림", "기타"), ("연유", "기타"), ("우유", "기타"),
    ("돼지고기", "기타"), ("소고기", "기타"), ("닭고기", "기타"), ("생선 종류", "기타"),
    ("조개", "기타"), ("오징어", "기타"), ("새우", "기타"), ("꽃게", "기타"),
    ("옥수수콘", "기타"), ("떡", "기타"), ("어묵", "기타"), ("김치", "기타"),
    ("라면", "기타"), ("다시팩", "기타"), ("식빵", "기타"),
]


def upgrade():
    # had_stock: 재고에서 실제로 본 적 있음("가졌던 것만 배너에" — 사용자 결정 2026-09-17).
    with op.batch_alter_table("staples", recreate="never") as b:
        b.add_column(sa.Column("had_stock", sa.Boolean(), nullable=False, server_default=sa.false()))

    conn = op.get_bind()
    # 이 마이그레이션 전부터 있던 필수품은 모두 사용자가 직접 만든 것이라 "가졌던 적 있음"으로 본다
    conn.execute(sa.text("UPDATE staples SET had_stock = TRUE"))

    # 이름 매칭은 앱의 실제 규칙(필수품 전용 방향 규칙 포함)을 그대로 써야 해서, 다른 마이그레이션처럼
    # 값을 얼려 두는 대신 app.matching을 그대로 불러온다(순수 함수라 부작용 없음).
    from app.matching import staple_matches

    now = datetime.now(timezone.utc)
    ingredients_by_user = {}
    for user_id, name in conn.execute(sa.text("SELECT user_id, name FROM ingredients")).all():
        ingredients_by_user.setdefault(user_id, []).append(name)
    existing = {(user_id, name) for user_id, name in conn.execute(sa.text("SELECT user_id, name FROM staples")).all()}

    # 기존 사용자에게 빠진 기본 필수품만 채운다(이미 같은 이름을 만들어 뒀으면 건너뜀 — 다시 돌려도 안전).
    # had_stock은 지금 재고에 맞는 이름이 있으면 true(있는 걸 곧장 떨어짐으로 잘못 보여주지 않으려는 게 아니라,
    # 배너가 "가졌던 것"만 보이게 하려면 지금 있는 것도 "가졌던 것"으로 시작해야 하기 때문 — 나중에 재고에서 빠지면 그때 떨어짐).
    rows = [
        {
            "user_id": user_id,
            "name": name,
            "category": category,
            "had_stock": any(staple_matches(name, stock_name) for stock_name in ingredients_by_user.get(user_id, [])),
            "created_at": now,
        }
        for (user_id,) in conn.execute(sa.text("SELECT id FROM users")).all()
        for name, category in DEFAULT_STAPLES
        if (user_id, name) not in existing
    ]
    if rows:
        insert_missing = sa.text(
            "INSERT INTO staples (user_id, name, category, had_stock, created_at) "
            "VALUES (:user_id, :name, :category, :had_stock, :created_at)"
        ).bindparams(sa.bindparam("created_at", type_=sa.DateTime(timezone=True)))
        conn.execute(insert_missing, rows)  # 한 번에 묶어 보낸다(리뷰, 2026-09-18) — executemany


def downgrade():
    # 필수품 행은 사용자가 만들었든 이 마이그레이션이 만들었든 지우지 않는다(사용자 데이터 보존) — 칸만 없앤다.
    with op.batch_alter_table("staples", recreate="never") as b:
        b.drop_column("had_stock")
