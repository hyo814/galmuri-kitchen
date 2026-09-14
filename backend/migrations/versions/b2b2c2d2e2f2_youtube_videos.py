"""youtube channels and videos

Revision ID: b2b2c2d2e2f2
Revises: b1b1c1d1e1f1
Create Date: 2026-09-14

"""
import sqlalchemy as sa
from alembic import op

revision = "b2b2c2d2e2f2"
down_revision = "b1b1c1d1e1f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "youtube_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("uploads_playlist_id", sa.String(length=40), nullable=True),
        sa.Column("video_count", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_youtube_channels")),
        sa.UniqueConstraint("channel_id", name=op.f("uq_youtube_channels_channel_id")),
    )
    op.create_table(
        "user_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["youtube_channels.id"], name=op.f("fk_user_channels_channel_id_youtube_channels"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_channels_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_channels")),
        sa.UniqueConstraint("user_id", "channel_id", name=op.f("uq_user_channels_user_id")),
    )
    op.create_index(op.f("ix_user_channels_user_id"), "user_channels", ["user_id"], unique=False)
    op.create_table(
        "youtube_videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.String(length=20), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["youtube_channels.id"], name=op.f("fk_youtube_videos_channel_id_youtube_channels"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_youtube_videos")),
        sa.UniqueConstraint("video_id", name=op.f("uq_youtube_videos_video_id")),
    )
    op.create_index(op.f("ix_youtube_videos_channel_id"), "youtube_videos", ["channel_id"], unique=False)
    op.create_index(op.f("ix_youtube_videos_fetched_at"), "youtube_videos", ["fetched_at"], unique=False)
    op.create_index("ix_youtube_videos_published_at_id", "youtube_videos", ["published_at", "id"], unique=False)


def downgrade():
    op.drop_index("ix_youtube_videos_published_at_id", table_name="youtube_videos")
    op.drop_index(op.f("ix_youtube_videos_fetched_at"), table_name="youtube_videos")
    op.drop_index(op.f("ix_youtube_videos_channel_id"), table_name="youtube_videos")
    op.drop_table("youtube_videos")
    op.drop_index(op.f("ix_user_channels_user_id"), table_name="user_channels")
    op.drop_table("user_channels")
    op.drop_table("youtube_channels")
