"""shopping items household flag

Revision ID: c2h2o2u2s2e2
Revises: c1d1e1m1o1a1
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "c2h2o2u2s2e2"
down_revision = "c1d1e1m1o1a1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shopping_items") as batch_op:
        batch_op.add_column(sa.Column("household", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("shopping_items") as batch_op:
        batch_op.drop_column("household")
