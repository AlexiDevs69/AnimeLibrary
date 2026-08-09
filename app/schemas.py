from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal[
    "auto",
    "local_file",
    "licensed_hls",
    "licensed_mp4",
    "official_youtube",
    "anilibria_hls",
    "kodik_embed",
]
ManagedSourceType = Literal[
    "licensed_hls",
    "licensed_mp4",
    "official_youtube",
    "anilibria_hls",
    "kodik_embed",
]
AdminSourceType = Literal["licensed_hls", "licensed_mp4"]


class AnimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    anilist_id: int
    slug: str
    title_romaji: str
    title_english: str | None
    title_native: str | None
    description: str | None
    poster_url: str | None
    banner_url: str | None
    cover_color: str | None
    year: int | None
    status: str | None
    episodes_count: int | None
    episode_duration: int | None
    genres: list[str]
    average_score: int | None


class VideoSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: ManagedSourceType
    region: str | None
    language: str | None
    label: str | None = None


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    title: str | None
    thumbnail_url: str | None
    duration: int | None
    sources: list[VideoSourceOut] = Field(default_factory=list)


class AnimeDetailOut(AnimeOut):
    episodes: list[EpisodeOut]


class RoomCreate(BaseModel):
    host_name: str = Field(min_length=2, max_length=40)
    anime_id: uuid.UUID | None = None
    episode_number: int = Field(default=1, ge=1)
    source_type: SourceType = "auto"
    source_id: uuid.UUID | None = None
    source_reference: str | None = Field(default=None, max_length=2000)
    file_hash: str | None = Field(default=None, min_length=8, max_length=128)
    is_public: bool = False
    allow_members_control: bool = True

    @field_validator("host_name")
    @classmethod
    def clean_host_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Ім'я має містити щонайменше 2 символи")
        return cleaned

    @field_validator("source_reference", "file_hash")
    @classmethod
    def empty_string_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class RoomOut(BaseModel):
    id: uuid.UUID
    invite_code: str
    host_id: uuid.UUID
    host_name: str
    anime: AnimeOut | None
    episode_number: int
    source_type: str
    source_id: uuid.UUID | None = None
    source_reference: str | None
    file_hash: str | None
    current_time: float
    is_paused: bool
    playback_rate: float
    state_version: int
    is_public: bool
    allow_members_control: bool
    created_at: datetime


class RoomJoin(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)


class RoomJoinOut(BaseModel):
    user_id: uuid.UUID
    room: RoomOut


class RoomEpisodeChangeIn(BaseModel):
    episode_number: int = Field(ge=1, le=10000)


class VideoSourceCreate(BaseModel):
    anilist_id: int = Field(gt=0)
    episode_number: int = Field(ge=1)
    source_type: AdminSourceType
    label: str = Field(min_length=2, max_length=80)
    source_url: str = Field(min_length=12, max_length=2000)
    language: str = Field(default="ja", min_length=2, max_length=20)
    region: str | None = Field(default=None, min_length=2, max_length=10)
    episode_title: str | None = Field(default=None, max_length=500)
    duration: int | None = Field(default=None, ge=10, le=600)
    confirmed_licensed: bool

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        cleaned = value.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Потрібне звичайне HTTPS-посилання без логіна й пароля")
        return cleaned

    @field_validator("language", "region")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        return " ".join(value.split())


class VideoSourceAdminOut(VideoSourceOut):
    episode_id: uuid.UUID
    source_reference: str
    is_active: bool


LibraryStatus = Literal["watching", "planned", "completed", "on_hold", "dropped"]
ProfileTag = Literal[
    "night_owl",
    "early_bird",
    "binge_watcher",
    "daily_watcher",
    "weekend_watcher",
    "completionist",
    "rewatcher",
    "slow_watcher",
    "ua_dub",
    "original_voice",
    "subtitles",
    "dub_fan",
    "manga_reader",
    "light_novel_reader",
    "seasonal_only",
    "movie_fan",
    "classic_fan",
    "new_gen_fan",
    "action_fan",
    "romance_fan",
    "fantasy_fan",
    "horror_fan",
    "comedy_fan",
    "drama_fan",
    "mystery_fan",
    "slice_of_life_fan",
    "season_hunter",
    "social_watcher",
    "solo_watcher",
    "collector",
    "critic",
    "reviewer",
    "list_maker",
    "spoiler_free",
    "soundtrack_hunter",
    "opening_never_skip",
    "hidden_gem_hunter",
]


def clean_username(value: str) -> str:
    cleaned = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,24}", cleaned):
        raise ValueError("Логін: 3–24 латинські літери, цифри або _")
    return cleaned


def clean_email(value: str) -> str:
    cleaned = value.strip().lower()
    if len(cleaned) > 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+",
        cleaned,
    ):
        raise ValueError("Введіть коректну email-адресу")
    return cleaned


def clean_image_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if re.fullmatch(r"/api/media/profile/[0-9a-fA-F-]{36}", cleaned):
        return cleaned
    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Зображення повинно мати звичайне HTTPS-посилання")
    return cleaned


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=40)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return clean_username(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Ім'я має містити щонайменше 2 символи")
        return cleaned


class LoginIn(BaseModel):
    login: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    friend_code: str
    display_name: str
    avatar_url: str | None
    banner_url: str | None
    bio: str | None
    profile_tags: list[ProfileTag] = Field(default_factory=list)
    is_profile_private: bool
    created_at: datetime


class ProfileUpdateIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)
    bio: str | None = Field(default=None, max_length=300)
    avatar_url: str | None = Field(default=None, max_length=1000)
    banner_url: str | None = Field(default=None, max_length=1000)
    profile_tags: list[ProfileTag] = Field(default_factory=list, max_length=6)
    is_profile_private: bool = False

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Ім'я має містити щонайменше 2 символи")
        return cleaned

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value and value.strip() else None

    @field_validator("avatar_url", "banner_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        return clean_image_url(value)

    @field_validator("profile_tags")
    @classmethod
    def unique_profile_tags(cls, values: list[ProfileTag]) -> list[ProfileTag]:
        return list(dict.fromkeys(values))[:6]


class LibraryEntryIn(BaseModel):
    status: LibraryStatus = "planned"
    is_favorite: bool = False
    is_pinned: bool = False
    rating: int | None = Field(default=None, ge=1, le=10)


class ProgressIn(BaseModel):
    anime_id: uuid.UUID
    episode_number: int = Field(ge=1, le=10000)
    current_time: float = Field(default=0, ge=0, le=100000)
    completed: bool = False


class WatchHeartbeatIn(BaseModel):
    session_id: uuid.UUID
    anime_id: uuid.UUID
    episode_number: int = Field(ge=1, le=10000)
    position: float = Field(ge=0, le=100000)
    duration: float | None = Field(default=None, ge=30, le=100000)
    playing: bool = False
    visible: bool = True
    playback_rate: float = Field(default=1.0, ge=0.25, le=2.0)
    ended: bool = False


class ProfileLevelOut(BaseModel):
    level: int
    xp: int
    current_level_xp: int
    next_level_xp: int
    progress: float
    rank_key: str
    rank_level: int
    next_rank_key: str | None
    next_rank_level: int | None
    rank_progress: float


class ProfileRankTierOut(BaseModel):
    key: str
    min_level: int
    unlocked: bool
    current: bool


class ProfileStreakOut(BaseModel):
    current_days: int
    longest_days: int
    today_seconds: int
    daily_goal_seconds: int
    daily_goal_progress: float


class ProfileAchievementOut(BaseModel):
    key: str
    category: str
    unit: Literal["seconds", "count", "days"]
    current: int
    target: int
    unlocked: bool


class WatchHeartbeatOut(BaseModel):
    credited_seconds: int
    total_watch_seconds: int
    episode_completed: bool
    level: ProfileLevelOut


class ProfileAnimeOut(BaseModel):
    anime: AnimeOut
    status: LibraryStatus
    is_favorite: bool
    is_pinned: bool
    rating: int | None
    created_at: datetime
    updated_at: datetime
    episode_number: int | None = None
    current_time: float | None = None
    progress_completed: bool = False
    watched_seconds: int = 0


class ProfileStatsOut(BaseModel):
    library_count: int
    completed_count: int
    favorite_count: int
    episodes_watched: int
    minutes_watched: int


class PublicAccountOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None
    banner_url: str | None
    bio: str | None
    profile_tags: list[ProfileTag] = Field(default_factory=list)
    is_profile_private: bool
    created_at: datetime


class FriendUserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None
    friend_code: str
    is_online: bool = False


class FriendEntryOut(BaseModel):
    friendship_id: uuid.UUID
    user: FriendUserOut
    created_at: datetime


class FriendRequestOut(FriendEntryOut):
    direction: Literal["incoming", "outgoing"]


class RoomInvitationOut(BaseModel):
    id: uuid.UUID
    invite_code: str
    anime: AnimeOut | None
    episode_number: int
    sender: FriendUserOut
    created_at: datetime
    expires_at: datetime


class FriendsDashboardOut(BaseModel):
    my_code: str
    friends: list[FriendEntryOut]
    incoming: list[FriendRequestOut]
    outgoing: list[FriendRequestOut]
    room_invitations: list[RoomInvitationOut]


class FriendRequestCreate(BaseModel):
    code: str = Field(min_length=8, max_length=20)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        cleaned = value.strip().upper().replace(" ", "")
        if not re.fullmatch(r"AL-[A-Z0-9]{4}-[A-Z0-9]{4}", cleaned):
            raise ValueError("Код має формат AL-XXXX-XXXX")
        return cleaned


class RoomInvitationCreate(BaseModel):
    friend_id: uuid.UUID


class RoomInvitationAcceptOut(BaseModel):
    invite_code: str


class WallAuthorOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None


class WallPostOut(BaseModel):
    id: uuid.UUID
    author: WallAuthorOut
    parent_id: uuid.UUID | None
    content: str
    created_at: datetime
    can_delete: bool = False


class WallPostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    parent_id: uuid.UUID | None = None

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = "\n".join(line.rstrip() for line in value.strip().splitlines())
        if not cleaned:
            raise ValueError("Коментар не може бути порожнім")
        return cleaned


class ProfileOut(BaseModel):
    user: PublicAccountOut
    is_owner: bool
    entries: list[ProfileAnimeOut]
    recent: list[ProfileAnimeOut]
    stats: ProfileStatsOut
    level: ProfileLevelOut
    rank_tiers: list[ProfileRankTierOut] = Field(default_factory=list)
    streak: ProfileStreakOut
    achievements: list[ProfileAchievementOut] = Field(default_factory=list)
    wall: list[WallPostOut] = Field(default_factory=list)
    wall_count: int = 0
    can_post_wall: bool = False
