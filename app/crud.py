from __future__ import annotations

import re
import secrets
import string
import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Anime, Episode, RoomMember, User, WatchRoom
from app.schemas import AnimeOut, RoomCreate, RoomOut


INVITE_ALPHABET = string.ascii_uppercase + string.digits


def make_slug(title: str, anilist_id: int) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return f"{base or 'anime'}-{anilist_id}"


def anime_payload(item: dict[str, Any]) -> dict[str, Any]:
    titles = item.get("title") or {}
    cover = item.get("coverImage") or {}
    romaji = titles.get("romaji") or titles.get("english") or f"Anime {item['id']}"
    return {
        "anilist_id": item["id"],
        "slug": make_slug(romaji, item["id"]),
        "title_romaji": romaji,
        "title_english": titles.get("english"),
        "title_native": titles.get("native"),
        "description": item.get("description"),
        "poster_url": cover.get("extraLarge") or cover.get("large"),
        "banner_url": item.get("bannerImage"),
        "cover_color": cover.get("color"),
        "year": item.get("seasonYear"),
        "status": item.get("status"),
        "episodes_count": item.get("episodes"),
        "episode_duration": item.get("duration"),
        "genres": item.get("genres") or [],
        "average_score": item.get("averageScore"),
        "anilist_url": item.get("siteUrl"),
    }


async def cache_anime_batch(
    db: AsyncSession, items: list[dict[str, Any]]
) -> list[Anime]:
    if not items:
        return []

    ids = [item["id"] for item in items]
    result = await db.execute(select(Anime).where(Anime.anilist_id.in_(ids)))
    existing = {anime.anilist_id: anime for anime in result.scalars()}
    ordered: list[Anime] = []

    for item in items:
        values = anime_payload(item)
        anime = existing.get(item["id"])
        if anime is None:
            anime = Anime(**values)
            db.add(anime)
            existing[item["id"]] = anime
        else:
            for field, value in values.items():
                setattr(anime, field, value)
        ordered.append(anime)

    await db.flush()

    for anime in ordered:
        count = anime.episodes_count
        if not count or count > 2000:
            continue
        episode_result = await db.execute(
            select(Episode.number).where(Episode.anime_id == anime.id)
        )
        existing_numbers = set(episode_result.scalars())
        for number in range(1, count + 1):
            if number not in existing_numbers:
                db.add(
                    Episode(
                        anime_id=anime.id,
                        number=number,
                        duration=anime.episode_duration,
                    )
                )

    await db.commit()
    return ordered


async def get_anime_detail(db: AsyncSession, anime_id: uuid.UUID) -> Anime | None:
    result = await db.execute(
        select(Anime)
        .options(selectinload(Anime.episodes))
        .where(Anime.id == anime_id)
    )
    anime = result.scalar_one_or_none()
    if anime is not None:
        anime.episodes.sort(key=lambda episode: episode.number)
    return anime


async def unique_invite_code(db: AsyncSession, length: int = 8) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(length))
        exists = await db.scalar(select(WatchRoom.id).where(WatchRoom.invite_code == code))
        if exists is None:
            return code
    raise RuntimeError("Не вдалося створити унікальний код кімнати")


async def create_room(db: AsyncSession, data: RoomCreate) -> tuple[WatchRoom, User]:
    if data.anime_id is not None:
        anime = await db.get(Anime, data.anime_id)
        if anime is None:
            raise LookupError("Аніме не знайдено")

    host = User(display_name=data.host_name, is_guest=True)
    db.add(host)
    await db.flush()

    room = WatchRoom(
        invite_code=await unique_invite_code(db),
        host_id=host.id,
        anime_id=data.anime_id,
        episode_number=data.episode_number,
        source_type=data.source_type,
        source_reference=data.source_reference,
        file_hash=data.file_hash,
        is_public=data.is_public,
        allow_members_control=data.allow_members_control,
    )
    db.add(room)
    await db.flush()
    db.add(RoomMember(room_id=room.id, user_id=host.id, is_connected=False))
    await db.commit()
    return await get_room(db, room.invite_code), host  # type: ignore[return-value]


async def get_room(db: AsyncSession, invite_code: str) -> WatchRoom | None:
    result = await db.execute(
        select(WatchRoom)
        .options(selectinload(WatchRoom.host), selectinload(WatchRoom.anime))
        .where(WatchRoom.invite_code == invite_code.upper())
    )
    return result.scalar_one_or_none()


def room_to_schema(room: WatchRoom) -> RoomOut:
    return RoomOut(
        id=room.id,
        invite_code=room.invite_code,
        host_id=room.host_id,
        host_name=room.host.display_name,
        anime=AnimeOut.model_validate(room.anime) if room.anime else None,
        episode_number=room.episode_number,
        source_type=room.source_type,
        source_reference=room.source_reference,
        file_hash=room.file_hash,
        current_time=room.current_time,
        is_paused=room.is_paused,
        playback_rate=room.playback_rate,
        state_version=room.state_version,
        is_public=room.is_public,
        allow_members_control=room.allow_members_control,
        created_at=room.created_at,
    )
