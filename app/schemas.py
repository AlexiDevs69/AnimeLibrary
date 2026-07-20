from __future__ import annotations

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
]
ManagedSourceType = Literal["licensed_hls", "licensed_mp4", "official_youtube"]
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


class VideoSourceCreate(BaseModel):
    anilist_id: int = Field(gt=0)
    episode_number: int = Field(ge=1)
    source_type: AdminSourceType
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


class VideoSourceAdminOut(VideoSourceOut):
    episode_id: uuid.UUID
    source_reference: str
    is_active: bool
