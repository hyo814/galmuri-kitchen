"""ai call tokens

Revision ID: a7b7c7d7e7f7
Revises: a6b6c6d6e6f6
Create Date: 2026-09-13

"""
import sqlalchemy as sa
from alembic import op

revision = "a7b7c7d7e7f7"
down_revision = "a6b6c6d6e6f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_calls") as batch_op:
        batch_op.add_column(sa.Column("model", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("ai_calls") as batch_op:
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("model")
