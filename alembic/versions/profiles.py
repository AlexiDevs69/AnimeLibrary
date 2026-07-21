"""Add registered profiles, sessions, and anime libraries.

Revision ID: 20260721_0004
Revises: 20260721_0003
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_0004"
down_revision = "20260721_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=24), nullable=True))
    op.add_column("users", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(length=300), nullable=True))
    op.add_column("users", sa.Column("banner_url", sa.String(length=1000), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "is_profile_private",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "anime_library_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("anime_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("is_favorite", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 10)", name="ck_library_rating"),
        sa.ForeignKeyConstraint(["anime_id"], ["anime.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "anime_id", name="uq_library_user_anime"),
    )
    op.create_index(
        "ix_anime_library_entries_user_id", "anime_library_entries", ["user_id"]
    )
    op.create_index(
        "ix_anime_library_entries_anime_id", "anime_library_entries", ["anime_id"]
    )
    op.create_index(
        "ix_anime_library_entries_status", "anime_library_entries", ["status"]
    )


def downgrade() -> None:
    op.drop_table("anime_library_entries")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "is_profile_private")
    op.drop_column("users", "banner_url")
    op.drop_column("users", "bio")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
    op.drop_column("users", "username")
