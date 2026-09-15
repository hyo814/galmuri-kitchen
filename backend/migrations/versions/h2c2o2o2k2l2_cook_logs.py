"""cook_logs·cook_log_items (요리 일기, 5단계 Task 4)

Revision ID: h2c2o2o2k2l2
Revises: h1p1r1i1c1e1
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "h2c2o2o2k2l2"
down_revision = "h1p1r1i1c1e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cook_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("food_log_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("cooked_on", sa.Date(), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("memo", sa.String(length=500), nullable=True),
        sa.Column("photo_key", sa.String(length=200), nullable=True),
        sa.Column("photo_size", sa.Integer(), nullable=True),
        sa.Column("eat_out_price", sa.Integer(), nullable=True),
        sa.Column("eat_out_source", sa.String(length=10), nullable=True),
        sa.Column("ingredient_cost", sa.Integer(), nullable=False),
        sa.Column("saved", sa.Integer(), nullable=True),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_cook_logs_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], name=op.f("fk_cook_logs_recipe_id_recipes"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["food_log_id"], ["food_logs.id"], name=op.f("fk_cook_logs_food_log_id_food_logs"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cook_logs")),
        sa.UniqueConstraint("photo_key", name=op.f("uq_cook_logs_photo_key")),
    )
    op.create_index(op.f("ix_cook_logs_recipe_id"), "cook_logs", ["recipe_id"], unique=False)
    op.create_index(op.f("ix_cook_logs_food_log_id"), "cook_logs", ["food_log_id"], unique=False)
    op.create_index("ix_cook_logs_user_id_cooked_on", "cook_logs", ["user_id", "cooked_on"], unique=False)
    op.create_table(
        "cook_log_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cook_log_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=True),
        sa.Column("removal_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("amount_text", sa.String(length=30), nullable=True),
        sa.Column("used", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=10), nullable=True),
        sa.Column("quantity_before", sa.Float(), nullable=True),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("purchased_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("price_quantity", sa.Float(), nullable=True),
        sa.Column("cost", sa.Integer(), nullable=True),
        sa.Column("excluded", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["cook_log_id"], ["cook_logs.id"], name=op.f("fk_cook_log_items_cook_log_id_cook_logs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], name=op.f("fk_cook_log_items_ingredient_id_ingredients"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["removal_id"], ["ingredient_removals.id"], name=op.f("fk_cook_log_items_removal_id_ingredient_removals"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cook_log_items")),
    )
    op.create_index(op.f("ix_cook_log_items_cook_log_id"), "cook_log_items", ["cook_log_id"], unique=False)
    op.create_index(op.f("ix_cook_log_items_ingredient_id"), "cook_log_items", ["ingredient_id"], unique=False)
    op.create_index(op.f("ix_cook_log_items_removal_id"), "cook_log_items", ["removal_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_cook_log_items_removal_id"), table_name="cook_log_items")
    op.drop_index(op.f("ix_cook_log_items_ingredient_id"), table_name="cook_log_items")
    op.drop_index(op.f("ix_cook_log_items_cook_log_id"), table_name="cook_log_items")
    op.drop_table("cook_log_items")
    op.drop_index("ix_cook_logs_user_id_cooked_on", table_name="cook_logs")
    op.drop_index(op.f("ix_cook_logs_food_log_id"), table_name="cook_logs")
    op.drop_index(op.f("ix_cook_logs_recipe_id"), table_name="cook_logs")
    op.drop_table("cook_logs")
