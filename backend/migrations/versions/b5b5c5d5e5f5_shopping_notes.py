"""shopping notes and photos

Revision ID: b5b5c5d5e5f5
Revises: b4b4c4d4e4f4
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "b5b5c5d5e5f5"
down_revision = "b4b4c4d4e4f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shopping_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=True),
        sa.Column("place", sa.String(length=30), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_shopping_notes_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_notes")),
        sa.UniqueConstraint("user_id", "client_id", name=op.f("uq_shopping_notes_user_id")),
    )
    op.create_index(op.f("ix_shopping_notes_user_id"), "shopping_notes", ["user_id"], unique=False)
    op.create_table(
        "shopping_note_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=True),
        sa.Column("photo_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"], ["shopping_notes.id"], name=op.f("fk_shopping_note_photos_note_id_shopping_notes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_note_photos")),
        sa.UniqueConstraint("note_id", "client_id", name=op.f("uq_shopping_note_photos_note_id")),
        sa.UniqueConstraint("photo_key", name=op.f("uq_shopping_note_photos_photo_key")),
    )
    op.create_index(op.f("ix_shopping_note_photos_note_id"), "shopping_note_photos", ["note_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_shopping_note_photos_note_id"), table_name="shopping_note_photos")
    op.drop_table("shopping_note_photos")
    op.drop_index(op.f("ix_shopping_notes_user_id"), table_name="shopping_notes")
    op.drop_table("shopping_notes")
