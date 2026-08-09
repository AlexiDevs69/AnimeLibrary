"""Add daily watch statistics for streaks and goals.

Revision ID: 20260809_0008
Revises: 20260809_0007
Create Date: 2026-08-09
"""

import sqlalchemy as sa

from alembic import op

revision = "20260809_0008"
down_revision = "20260809_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_daily_stats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("watch_date", sa.Date(), nullable=False),
        sa.Column("watched_seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "watch_date",
            name="uq_watch_daily_stat_user_date",
        ),
    )
    op.create_index("ix_watch_daily_stats_user_id", "watch_daily_stats", ["user_id"])
    op.create_index(
        "ix_watch_daily_stats_watch_date",
        "watch_daily_stats",
        ["watch_date"],
    )


def downgrade() -> None:
    op.drop_table("watch_daily_stats")
