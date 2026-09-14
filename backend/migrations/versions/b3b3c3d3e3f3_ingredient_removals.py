"""ingredient removals

Revision ID: b3b3c3d3e3f3
Revises: b2b2c2d2e2f2
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "b3b3c3d3e3f3"
down_revision = "b2b2c2d2e2f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingredient_removals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_ingredient_removals_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredient_removals")),
    )
    op.create_index(op.f("ix_ingredient_removals_user_id"), "ingredient_removals", ["user_id"], unique=False)
    op.create_index("ix_ingredient_removals_user_id_created_at", "ingredient_removals", ["user_id", "created_at"], unique=False)


def downgrade():
    op.drop_index("ix_ingredient_removals_user_id_created_at", table_name="ingredient_removals")
    op.drop_index(op.f("ix_ingredient_removals_user_id"), table_name="ingredient_removals")
    op.drop_table("ingredient_removals")
