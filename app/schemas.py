from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SourceType = Literal["local_file", "youtube", "licensed_hls"]


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


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    title: str | None
    thumbnail_url: str | None
    duration: int | None


class AnimeDetailOut(AnimeOut):
    episodes: list[EpisodeOut]


class RoomCreate(BaseModel):
    host_name: str = Field(min_length=2, max_length=40)
    anime_id: uuid.UUID | None = None
    episode_number: int = Field(default=1, ge=1)
    source_type: SourceType = "local_file"
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

