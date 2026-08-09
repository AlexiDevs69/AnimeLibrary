"""Add profile social features and verified watch tracking.

Revision ID: 20260809_0007
Revises: 20260721_0006
Create Date: 2026-08-09
"""

import sqlalchemy as sa

from alembic import op

revision = "20260809_0007"
down_revision = "20260721_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("profile_tags", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column("video_sources", sa.Column("label", sa.String(length=80), nullable=True))
    op.execute(
        "UPDATE video_sources SET label = CASE "
        "WHEN source_type = 'anilibria_hls' THEN 'AniLiberty' "
        "WHEN source_type = 'official_youtube' THEN 'YouTube Official' "
        "ELSE NULL END WHERE label IS NULL"
    )
    op.add_column("watch_rooms", sa.Column("source_id", sa.Uuid(), nullable=True))

    op.add_column("watch_progress", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column(
        "watch_progress", sa.Column("heartbeat_session_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "watch_progress",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "watch_progress",
        sa.Column("heartbeat_position", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "watch_progress",
        sa.Column("heartbeat_playing", sa.Boolean(), server_default="false", nullable=False),
    )

    op.create_table(
        "watch_episode_stats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("watched_seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("max_position", sa.Float(), server_default="0", nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("first_watched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "anime_id",
            "episode_number",
            name="uq_watch_episode_stat_user_anime_episode",
        ),
    )
    op.create_index("ix_watch_episode_stats_user_id", "watch_episode_stats", ["user_id"])
    op.create_index("ix_watch_episode_stats_anime_id", "watch_episode_stats", ["anime_id"])

    op.create_table(
        "profile_wall_posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_user_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.String(length=600), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["profile_wall_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_profile_wall_posts_profile_user_id",
        "profile_wall_posts",
        ["profile_user_id"],
    )
    op.create_index("ix_profile_wall_posts_author_id", "profile_wall_posts", ["author_id"])
    op.create_index("ix_profile_wall_posts_parent_id", "profile_wall_posts", ["parent_id"])
    op.create_index("ix_profile_wall_posts_created_at", "profile_wall_posts", ["created_at"])


def downgrade() -> None:
    op.drop_table("profile_wall_posts")
    op.drop_table("watch_episode_stats")
    op.drop_column("watch_progress", "heartbeat_playing")
    op.drop_column("watch_progress", "heartbeat_position")
    op.drop_column("watch_progress", "heartbeat_at")
    op.drop_column("watch_progress", "heartbeat_session_id")
    op.drop_column("watch_progress", "duration_seconds")
    op.drop_column("watch_rooms", "source_id")
    op.drop_column("video_sources", "label")
    op.drop_column("users", "profile_tags")
