"""Add compact Kodik release cache and MAL mapping.

Revision ID: 20260720_0002
Revises: 20260720_0001
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_0002"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("anime", sa.Column("mal_id", sa.Integer(), nullable=True))
    op.add_column(
        "anime",
        sa.Column("kodik_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_anime_mal_id", "anime", ["mal_id"])

    op.create_table(
        "kodik_releases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=300), nullable=False),
        sa.Column("provider_id", sa.String(length=200), nullable=False),
        sa.Column("player_link", sa.String(length=2000), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("season_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("episodes_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("translation_id", sa.Integer(), nullable=True),
        sa.Column("translation_title", sa.String(length=200), nullable=True),
        sa.Column("translation_type", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "anime_id",
            "provider_key",
            name="uq_kodik_release_anime_key",
        ),
    )
    op.create_index("ix_kodik_releases_anime_id", "kodik_releases", ["anime_id"])


def downgrade() -> None:
    op.drop_table("kodik_releases")
    op.drop_index("ix_anime_mal_id", table_name="anime")
    op.drop_column("anime", "kodik_synced_at")
    op.drop_column("anime", "mal_id")
