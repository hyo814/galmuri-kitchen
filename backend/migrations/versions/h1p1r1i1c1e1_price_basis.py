"""ingredients.price_quantity, recipes.eat_out_price·eat_out_source (5단계 Task 1)

Revision ID: h1p1r1i1c1e1
Revises: g3f3l3p3h3o3
Create Date: 2026-09-15

"""
import sqlalchemy as sa
from alembic import op

revision = "h1p1r1i1c1e1"
down_revision = "g3f3l3p3h3o3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.add_column(sa.Column("price_quantity", sa.Float(), nullable=True))
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("eat_out_price", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("eat_out_source", sa.String(length=10), nullable=True))
    op.execute(sa.text("UPDATE ingredients SET price_quantity = quantity WHERE price IS NOT NULL"))


def downgrade():
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("eat_out_source")
        batch_op.drop_column("eat_out_price")
    with op.batch_alter_table("ingredients") as batch_op:
        batch_op.drop_column("price_quantity")
