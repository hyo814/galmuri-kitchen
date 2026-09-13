"""kitchen tools

Revision ID: a4b4c4d4e4f4
Revises: a3b3c3d3e3f3
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a4b4c4d4e4f4"
down_revision = "a3b3c3d3e3f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kitchen_tools",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("bought_on", sa.Date(), nullable=True),
        sa.Column("check_every_months", sa.Integer(), nullable=True),
        sa.Column("last_checked_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_kitchen_tools_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kitchen_tools")),
    )
    op.create_index(op.f("ix_kitchen_tools_user_id"), "kitchen_tools", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_kitchen_tools_user_id"), table_name="kitchen_tools")
    op.drop_table("kitchen_tools")
