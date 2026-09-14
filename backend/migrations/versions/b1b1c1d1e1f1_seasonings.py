"""seasonings

Revision ID: b1b1c1d1e1f1
Revises: a8b8c8d8e8f8
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "b1b1c1d1e1f1"
down_revision = "a8b8c8d8e8f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "seasonings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("basis", sa.String(length=20), nullable=False),
        sa.Column("basis_amount", sa.Float(), nullable=False),
        sa.Column("basis_unit", sa.String(length=10), nullable=False),
        sa.Column("main_ingredient", sa.String(length=50), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_seasonings_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasonings")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_seasonings_user_id")),
    )
    op.create_index(op.f("ix_seasonings_user_id"), "seasonings", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_seasonings_user_id"), table_name="seasonings")
    op.drop_table("seasonings")
