"""shopping items

Revision ID: b4b4c4d4e4f4
Revises: b3b3c3d3e3f3
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "b4b4c4d4e4f4"
down_revision = "b3b3c3d3e3f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=10), nullable=False),
        sa.Column("planned_on", sa.Date(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("source_label", sa.String(length=60), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"], ["storage_locations.id"], name=op.f("fk_shopping_items_location_id_storage_locations"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_shopping_items_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_items")),
        sa.UniqueConstraint("user_id", "client_id", name=op.f("uq_shopping_items_user_id")),
    )
    op.create_index(op.f("ix_shopping_items_location_id"), "shopping_items", ["location_id"], unique=False)
    op.create_index(op.f("ix_shopping_items_user_id"), "shopping_items", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_shopping_items_user_id"), table_name="shopping_items")
    op.drop_index(op.f("ix_shopping_items_location_id"), table_name="shopping_items")
    op.drop_table("shopping_items")
