"""ingredient price

Revision ID: a8b8c8d8e8f8
Revises: a7b7c7d7e7f7
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "a8b8c8d8e8f8"
down_revision = "a7b7c7d7e7f7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.add_column(sa.Column("price", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.drop_column("price")
