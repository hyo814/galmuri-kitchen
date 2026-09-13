"""staples

Revision ID: a2b2c2d2e2f2
Revises: a1b1c1d1e1f1
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a2b2c2d2e2f2"
down_revision = "a1b1c1d1e1f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "staples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_staples_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staples")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_staples_user_id")),
    )
    with op.batch_alter_table("staples") as batch_op:
        batch_op.create_index(batch_op.f("ix_staples_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("staples") as batch_op:
        batch_op.drop_index(batch_op.f("ix_staples_user_id"))
    op.drop_table("staples")
