"""meal plans

Revision ID: d1m1e1a1l1s1
Revises: c2h2o2u2s2e2
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "d1m1e1a1l1s1"
down_revision = "c2h2o2u2s2e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meal_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("default_servings", sa.Integer(), nullable=False),
        sa.Column("goal_kcal", sa.Integer(), nullable=True),
        sa.Column("goal_note", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_meal_plans_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_plans")),
    )
    op.create_index(op.f("ix_meal_plans_user_id"), "meal_plans", ["user_id"], unique=False)

    op.create_table(
        "meal_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(length=10), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("est_kcal", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["meal_plans.id"], name=op.f("fk_meal_slots_plan_id_meal_plans"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name=op.f("fk_meal_slots_recipe_id_recipes"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_slots")),
        sa.UniqueConstraint("plan_id", "date", "meal", name=op.f("uq_meal_slots_plan_id")),
    )
    op.create_index(op.f("ix_meal_slots_plan_id"), "meal_slots", ["plan_id"], unique=False)
    op.create_index(op.f("ix_meal_slots_recipe_id"), "meal_slots", ["recipe_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_meal_slots_recipe_id"), table_name="meal_slots")
    op.drop_index(op.f("ix_meal_slots_plan_id"), table_name="meal_slots")
    op.drop_table("meal_slots")
    op.drop_index(op.f("ix_meal_plans_user_id"), table_name="meal_plans")
    op.drop_table("meal_plans")
