"""food_logs (먹은 기록, 4b-3 Task 2)

Revision ID: g2f2o2o2d2l2
Revises: g1s1e1r1v1n1
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "g2f2o2o2d2l2"
down_revision = "g1s1e1r1v1n1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "food_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("eaten_on", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=True),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("meal_slot_id", sa.Integer(), nullable=True),
        sa.Column("food_code", sa.String(length=80), nullable=True),
        sa.Column("servings", sa.Float(), nullable=True),
        sa.Column("grams", sa.Integer(), nullable=True),
        sa.Column("place", sa.String(length=4), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("memo", sa.String(length=200), nullable=True),
        sa.Column("kcal", sa.Integer(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("sugars_g", sa.Float(), nullable=True),
        sa.Column("sodium_mg", sa.Integer(), nullable=True),
        sa.Column("approx", sa.Boolean(), nullable=False),
        sa.Column("nutrition_pending", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_food_logs_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name=op.f("fk_food_logs_recipe_id_recipes"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["meal_slot_id"], ["meal_slots.id"], name=op.f("fk_food_logs_meal_slot_id_meal_slots"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_logs")),
        sa.UniqueConstraint("meal_slot_id", name=op.f("uq_food_logs_meal_slot_id")),
    )
    op.create_index(op.f("ix_food_logs_recipe_id"), "food_logs", ["recipe_id"], unique=False)
    op.create_index("ix_food_logs_user_id_eaten_on", "food_logs", ["user_id", "eaten_on"], unique=False)


def downgrade():
    op.drop_index("ix_food_logs_user_id_eaten_on", table_name="food_logs")
    op.drop_index(op.f("ix_food_logs_recipe_id"), table_name="food_logs")
    op.drop_table("food_logs")
