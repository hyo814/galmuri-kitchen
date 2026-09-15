"""food_nutrients·food_searches·food_matches·unit_weight_estimates (식품영양성분 DB 캐시, 4b-2)

Revision ID: f2f2o2o2d2s2
Revises: f1b1o1d1y1p1
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "f2f2o2o2d2s2"
down_revision = "f1b1o1d1y1p1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "food_nutrients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("food_code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_key", sa.String(length=60), nullable=False),
        sa.Column("group_name", sa.String(length=20), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=False),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("sugars_g", sa.Float(), nullable=True),
        sa.Column("sodium_mg", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_nutrients")),
        sa.UniqueConstraint("food_code", name=op.f("uq_food_nutrients_food_code")),
    )
    op.create_index(op.f("ix_food_nutrients_name_key"), "food_nutrients", ["name_key"])

    op.create_table(
        "food_searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query_key", sa.String(length=60), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_searches")),
        sa.UniqueConstraint("query_key", name=op.f("uq_food_searches_query_key")),
    )

    op.create_table(
        "food_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_key", sa.String(length=60), nullable=False),
        sa.Column("food_code", sa.String(length=80), nullable=True),
        sa.Column("unit_grams", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_food_matches_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_matches")),
        sa.UniqueConstraint("user_id", "ingredient_key", name=op.f("uq_food_matches_user_id")),
    )
    op.create_index(op.f("ix_food_matches_user_id"), "food_matches", ["user_id"])

    op.create_table(
        "unit_weight_estimates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name_key", sa.String(length=60), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_weight_estimates")),
        sa.UniqueConstraint("name_key", "unit", name=op.f("uq_unit_weight_estimates_name_key")),
    )


def downgrade():
    op.drop_table("unit_weight_estimates")
    op.drop_index(op.f("ix_food_matches_user_id"), table_name="food_matches")
    op.drop_table("food_matches")
    op.drop_table("food_searches")
    op.drop_index(op.f("ix_food_nutrients_name_key"), table_name="food_nutrients")
    op.drop_table("food_nutrients")
