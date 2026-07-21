"""Add account friend codes, friendships, and watch invitations.

Revision ID: 20260721_0006
Revises: 20260721_0005
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_0006"
down_revision = "20260721_0005"
branch_labels = None
depends_on = None


def _friend_code(user_id: object, used: set[str]) -> str:
    raw = str(user_id).replace("-", "").upper()
    for offset in range(0, max(1, len(raw) - 7)):
        token = (raw[offset : offset + 8] + raw)[:8]
        code = f"AL-{token[:4]}-{token[4:]}"
        if code not in used:
            used.add(code)
            return code
    raise RuntimeError("Could not create a unique friend code")


def upgrade() -> None:
    op.add_column("users", sa.Column("friend_code", sa.String(length=12), nullable=True))
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("is_guest", sa.Boolean()),
        sa.column("friend_code", sa.String(length=12)),
    )
    if not op.get_context().as_sql:
        connection = op.get_bind()
        rows = connection.execute(
            sa.select(users.c.id).where(users.c.is_guest.is_(False))
        ).all()
        used: set[str] = set()
        for (user_id,) in rows:
            connection.execute(
                users.update()
                .where(users.c.id == user_id)
                .values(friend_code=_friend_code(user_id, used))
            )
    op.create_index("ix_users_friend_code", "users", ["friend_code"], unique=True)

    op.create_table(
        "friendships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_one_id", sa.Uuid(), nullable=False),
        sa.Column("user_two_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_one_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_two_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_one_id", "user_two_id", name="uq_friendship_pair"),
    )
    op.create_index("ix_friendships_user_one_id", "friendships", ["user_one_id"])
    op.create_index("ix_friendships_user_two_id", "friendships", ["user_two_id"])
    op.create_index("ix_friendships_requested_by_id", "friendships", ["requested_by_id"])
    op.create_index("ix_friendships_status", "friendships", ["status"])

    op.create_table(
        "room_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["watch_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "recipient_id", name="uq_room_invitation_recipient"),
    )
    op.create_index("ix_room_invitations_room_id", "room_invitations", ["room_id"])
    op.create_index("ix_room_invitations_sender_id", "room_invitations", ["sender_id"])
    op.create_index("ix_room_invitations_recipient_id", "room_invitations", ["recipient_id"])
    op.create_index("ix_room_invitations_status", "room_invitations", ["status"])
    op.create_index("ix_room_invitations_expires_at", "room_invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_table("room_invitations")
    op.drop_table("friendships")
    op.drop_index("ix_users_friend_code", table_name="users")
    op.drop_column("users", "friend_code")
