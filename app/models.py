from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(40))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    username: Mapped[str | None] = mapped_column(String(24), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(500))
    friend_code: Mapped[str | None] = mapped_column(String(12), unique=True, index=True)
    bio: Mapped[str | None] = mapped_column(String(300))
    banner_url: Mapped[str | None] = mapped_column(String(1000))
    is_profile_private: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    hosted_rooms: Mapped[list[WatchRoom]] = relationship(back_populates="host")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship()


class ProfileImage(Base):
    __tablename__ = "profile_images"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_profile_image_user_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10), index=True)
    mime_type: Mapped[str] = mapped_column(
        String(50), default="image/webp", server_default="image/webp"
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship()


class Anime(Base):
    __tablename__ = "anime"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    anilist_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    mal_id: Mapped[int | None] = mapped_column(Integer, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    title_romaji: Mapped[str] = mapped_column(String(300))
    title_english: Mapped[str | None] = mapped_column(String(300))
    title_native: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    poster_url: Mapped[str | None] = mapped_column(String(1000))
    banner_url: Mapped[str | None] = mapped_column(String(1000))
    cover_color: Mapped[str | None] = mapped_column(String(20))
    year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(40), index=True)
    episodes_count: Mapped[int | None] = mapped_column(Integer)
    episode_duration: Mapped[int | None] = mapped_column(Integer)
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    average_score: Mapped[int | None] = mapped_column(Integer)
    anilist_url: Mapped[str | None] = mapped_column(String(1000))
    anilibria_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kodik_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    episodes: Mapped[list[Episode]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    kodik_releases: Mapped[list[KodikRelease]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("anime_id", "number", name="uq_episode_anime_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    anime_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anime.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(500))
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    air_date: Mapped[date | None] = mapped_column(Date)
    duration: Mapped[int | None] = mapped_column(Integer)

    anime: Mapped[Anime] = relationship(back_populates="episodes")
    sources: Mapped[list[VideoSource]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )


class VideoSource(Base):
    __tablename__ = "video_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_reference: Mapped[str] = mapped_column(String(2000))
    region: Mapped[str | None] = mapped_column(String(10))
    language: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    episode: Mapped[Episode] = relationship(back_populates="sources")


class KodikRelease(Base):
    __tablename__ = "kodik_releases"
    __table_args__ = (
        UniqueConstraint("anime_id", "provider_key", name="uq_kodik_release_anime_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    anime_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anime.id", ondelete="CASCADE"), index=True
    )
    provider_key: Mapped[str] = mapped_column(String(300))
    provider_id: Mapped[str] = mapped_column(String(200))
    player_link: Mapped[str] = mapped_column(String(2000))
    content_type: Mapped[str] = mapped_column(String(32))
    season_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    episodes_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    translation_id: Mapped[int | None] = mapped_column(Integer)
    translation_title: Mapped[str | None] = mapped_column(String(200))
    translation_type: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    anime: Mapped[Anime] = relationship(back_populates="kodik_releases")


class WatchRoom(Base):
    __tablename__ = "watch_rooms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    invite_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    host_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    anime_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anime.id", ondelete="SET NULL"), index=True
    )
    episode_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source_type: Mapped[str] = mapped_column(String(32), default="local_file")
    source_reference: Mapped[str | None] = mapped_column(String(2000))
    file_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    current_time: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    is_paused: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    playback_rate: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    state_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    allow_members_control: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    host: Mapped[User] = relationship(back_populates="hosted_rooms")
    anime: Mapped[Anime | None] = relationship()
    members: Mapped[list[RoomMember]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_room_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_rooms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    room: Mapped[WatchRoom] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_one_id", "user_two_id", name="uq_friendship_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_one_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    user_two_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(12), default="pending", server_default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RoomInvitation(Base):
    __tablename__ = "room_invitations"
    __table_args__ = (
        UniqueConstraint("room_id", "recipient_id", name="uq_room_invitation_recipient"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_rooms.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(12), default="pending", server_default="pending", index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    room: Mapped[WatchRoom] = relationship()
    sender: Mapped[User] = relationship(foreign_keys=[sender_id])
    recipient: Mapped[User] = relationship(foreign_keys=[recipient_id])


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (UniqueConstraint("user_id", "anime_id", name="uq_progress_user_anime"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    anime_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anime.id", ondelete="CASCADE"), index=True
    )
    episode_number: Mapped[int] = mapped_column(Integer, default=1)
    current_time: Mapped[float] = mapped_column(Float, default=0.0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AnimeLibraryEntry(Base):
    __tablename__ = "anime_library_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "anime_id", name="uq_library_user_anime"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    anime_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anime.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="planned", server_default="planned", index=True
    )
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    rating: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    anime: Mapped[Anime] = relationship()


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_rooms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "anime_id", name="uq_favorite_user_anime"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    anime_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anime.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


Index("ix_rooms_public_created", WatchRoom.is_public, WatchRoom.created_at)
