"""Initial anime watch-party schema.

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=40), nullable=False),
        sa.Column("avatar_url", sa.String(length=1000), nullable=True),
        sa.Column("is_guest", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "anime",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anilist_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("title_romaji", sa.String(length=300), nullable=False),
        sa.Column("title_english", sa.String(length=300), nullable=True),
        sa.Column("title_native", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("poster_url", sa.String(length=1000), nullable=True),
        sa.Column("banner_url", sa.String(length=1000), nullable=True),
        sa.Column("cover_color", sa.String(length=20), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("episodes_count", sa.Integer(), nullable=True),
        sa.Column("episode_duration", sa.Integer(), nullable=True),
        sa.Column("genres", sa.JSON(), nullable=False),
        sa.Column("average_score", sa.Integer(), nullable=True),
        sa.Column("anilist_url", sa.String(length=1000), nullable=True),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anilist_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_anime_anilist_id", "anime", ["anilist_id"])
    op.create_index("ix_anime_slug", "anime", ["slug"])
    op.create_index("ix_anime_status", "anime", ["status"])

    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=True),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anime_id", "number", name="uq_episode_anime_number"),
    )
    op.create_index("ix_episodes_anime_id", "episodes", ["anime_id"])

    op.create_table(
        "video_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=False),
        sa.Column("region", sa.String(length=10), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_sources_episode_id", "video_sources", ["episode_id"])
    op.create_index("ix_video_sources_source_type", "video_sources", ["source_type"])

    op.create_table(
        "watch_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invite_code", sa.String(length=12), nullable=False),
        sa.Column("host_id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=True),
        sa.Column("episode_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=2000), nullable=True),
        sa.Column("file_hash", sa.String(length=128), nullable=True),
        sa.Column("current_time", sa.Float(), server_default="0", nullable=False),
        sa.Column("is_paused", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("playback_rate", sa.Float(), server_default="1", nullable=False),
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("allow_members_control", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["host_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_index("ix_watch_rooms_invite_code", "watch_rooms", ["invite_code"])
    op.create_index("ix_watch_rooms_host_id", "watch_rooms", ["host_id"])
    op.create_index("ix_watch_rooms_anime_id", "watch_rooms", ["anime_id"])
    op.create_index("ix_watch_rooms_file_hash", "watch_rooms", ["file_hash"])
    op.create_index("ix_rooms_public_created", "watch_rooms", ["is_public", "created_at"])

    op.create_table(
        "room_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("is_connected", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["watch_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_room_member"),
    )
    op.create_index("ix_room_members_room_id", "room_members", ["room_id"])
    op.create_index("ix_room_members_user_id", "room_members", ["user_id"])

    op.create_table(
        "watch_progress",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("current_time", sa.Float(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "anime_id", name="uq_progress_user_anime"),
    )
    op.create_index("ix_watch_progress_user_id", "watch_progress", ["user_id"])
    op.create_index("ix_watch_progress_anime_id", "watch_progress", ["anime_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["watch_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_room_id", "chat_messages", ["room_id"])
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])

    op.create_table(
        "favorites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "anime_id", name="uq_favorite_user_anime"),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_index("ix_favorites_anime_id", "favorites", ["anime_id"])


def downgrade() -> None:
    op.drop_table("favorites")
    op.drop_table("chat_messages")
    op.drop_table("watch_progress")
    op.drop_table("room_members")
    op.drop_table("watch_rooms")
    op.drop_table("video_sources")
    op.drop_table("episodes")
    op.drop_table("anime")
    op.drop_table("users")
