"""recipes

Revision ID: a6b6c6d6e6f6
Revises: a5b5c5d5e5f5
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a6b6c6d6e6f6"
down_revision = "a5b5c5d5e5f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "public_recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rcp_seq", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=True),
        sa.Column("method", sa.String(length=30), nullable=True),
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("ingredients_text", sa.Text(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("ingredient_keys", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("is_sample", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_public_recipes")),
        sa.UniqueConstraint("rcp_seq", name=op.f("uq_public_recipes_rcp_seq")),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("public_recipe_id", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["public_recipe_id"],
            ["public_recipes.id"],
            name=op.f("fk_recipes_public_recipe_id_public_recipes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_recipes_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.UniqueConstraint("user_id", "public_recipe_id", name=op.f("uq_recipes_user_id")),
    )
    op.create_index(op.f("ix_recipes_user_id"), "recipes", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_recipes_user_id"), table_name="recipes")
    op.drop_table("recipes")
    op.drop_table("public_recipes")
