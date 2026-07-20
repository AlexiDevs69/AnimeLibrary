from __future__ import annotations

import re
import secrets
import string
import unicodedata
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Anime, Episode, RoomMember, User, VideoSource, WatchRoom
from app.schemas import AnimeOut, RoomCreate, RoomOut


INVITE_ALPHABET = string.ascii_uppercase + string.digits
MANAGED_SOURCE_TYPES = ("licensed_hls", "licensed_mp4", "official_youtube", "embed_iframe")
SOURCE_PRIORITY = {
    "licensed_hls": 0,
    "licensed_mp4": 1,
    "official_youtube": 2,
    "embed_iframe": 3,
}
NON_EPISODE_WORDS = (
    "trailer",
    "teaser",
    "preview",
    "promo",
    "promotional",
    "clip",
    "music video",
)


class SourceUnavailableError(LookupError):
    pass


def youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    candidate: str | None = None
    if hostname == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif hostname in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            parts = parsed.path.strip("/").split("/")
            candidate = parts[1] if len(parts) > 1 else None
    if candidate and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        return candidate
    return None


def streaming_episode_number(title: str) -> int | None:
    lowered = " ".join(title.lower().split())
    if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in NON_EPISODE_WORDS):
        return None
    patterns = (
        r"(?:episode|ep\.?|епізод|серія|серия)\s*#?0*(\d{1,4})\b",
        r"^\s*0*(\d{1,4})(?:\s*[-.:]|\s*$)",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            number = int(match.group(1))
            return number if number > 0 else None
    return None


def official_youtube_episodes(item: dict[str, Any]) -> list[tuple[int, str, str | None]]:
    episodes: list[tuple[int, str, str | None]] = []
    seen: set[tuple[int, str]] = set()
    for stream in item.get("streamingEpisodes") or []:
        title = str(stream.get("title") or "").strip()
        video_id = youtube_video_id(str(stream.get("url") or ""))
        number = streaming_episode_number(title)
        if video_id is None or number is None or (number, video_id) in seen:
            continue
        seen.add((number, video_id))
        thumbnail = str(stream.get("thumbnail") or "").strip() or None
        episodes.append((number, video_id, thumbnail))
    return episodes


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

    await db.flush()

    for anime, item in zip(ordered, items, strict=True):
        youtube_episodes = official_youtube_episodes(item)
        if not youtube_episodes:
            continue
        numbers = [number for number, _, _ in youtube_episodes]
        episode_result = await db.execute(
            select(Episode).where(
                Episode.anime_id == anime.id,
                Episode.number.in_(numbers),
            )
        )
        episodes_by_number = {episode.number: episode for episode in episode_result.scalars()}
        prepared_sources: list[tuple[Episode, str]] = []
        for number, video_id, thumbnail in youtube_episodes:
            episode = episodes_by_number.get(number)
            if episode is None:
                episode = Episode(
                    anime_id=anime.id,
                    number=number,
                    duration=anime.episode_duration,
                    thumbnail_url=thumbnail,
                )
                db.add(episode)
                episodes_by_number[number] = episode
            elif thumbnail and not episode.thumbnail_url:
                episode.thumbnail_url = thumbnail
            prepared_sources.append((episode, video_id))

        await db.flush()
        episode_ids = [episode.id for episode, _ in prepared_sources]
        source_result = await db.execute(
            select(VideoSource.episode_id, VideoSource.source_reference).where(
                VideoSource.episode_id.in_(episode_ids),
                VideoSource.source_type == "official_youtube",
            )
        )
        existing_sources = set(source_result.tuples())
        for episode, video_id in prepared_sources:
            if (episode.id, video_id) not in existing_sources:
                db.add(
                    VideoSource(
                        episode_id=episode.id,
                        source_type="official_youtube",
                        source_reference=video_id,
                        language=None,
                        region=None,
                        is_active=True,
                    )
                )

    await db.commit()
    return ordered


async def get_anime_detail(db: AsyncSession, anime_id: uuid.UUID) -> Anime | None:
    result = await db.execute(
        select(Anime)
        .options(selectinload(Anime.episodes).selectinload(Episode.sources))
        .where(Anime.id == anime_id)
    )
    anime = result.scalar_one_or_none()
    if anime is not None:
        anime.episodes.sort(key=lambda episode: episode.number)
    return anime


async def resolve_video_source(
    db: AsyncSession,
    *,
    anime_id: uuid.UUID,
    episode_number: int,
    source_id: uuid.UUID | None,
    source_type: str,
) -> VideoSource | None:
    query = (
        select(VideoSource)
        .join(Episode, Episode.id == VideoSource.episode_id)
        .where(
            Episode.anime_id == anime_id,
            Episode.number == episode_number,
            VideoSource.is_active.is_(True),
            VideoSource.source_type.in_(MANAGED_SOURCE_TYPES),
        )
    )
    if source_id is not None:
        query = query.where(VideoSource.id == source_id)
    elif source_type in MANAGED_SOURCE_TYPES:
        query = query.where(VideoSource.source_type == source_type)
    query = query.order_by(
        case(
            (VideoSource.source_type == "licensed_hls", 0),
            (VideoSource.source_type == "licensed_mp4", 1),
            (VideoSource.source_type == "official_youtube", 2),
            (VideoSource.source_type == "embed_iframe", 3),
            else_=9,
        ),
        VideoSource.created_at.asc(),
    ).limit(1)
    
    source = (await db.execute(query)).scalar_one_or_none()
    
    # Автогенерація джерела Kodik, якщо в базі немає інших файлів
    if source is None and (source_type == "auto" or source_type == "embed_iframe"):
        anime = await db.get(Anime, anime_id)
        if anime:
            ep_res = await db.execute(
                select(Episode).where(Episode.anime_id == anime_id, Episode.number == episode_number)
            )
            episode = ep_res.scalar_one_or_none()
            if episode:
                kodik_url = f"https://kodik.info/serial/{anime.anilist_id}/iframe?episode={episode_number}"
                return VideoSource(
                    id=uuid.uuid4(),
                    episode_id=episode.id,
                    source_type="embed_iframe",
                    source_reference=kodik_url,
                    is_active=True,
                )
    return source


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

    resolved_source: VideoSource | None = None
    if data.source_type != "local_file":
        if data.anime_id is None:
            raise SourceUnavailableError("Спочатку виберіть аніме та серію")
        resolved_source = await resolve_video_source(
            db,
            anime_id=data.anime_id,
            episode_number=data.episode_number,
            source_id=data.source_id,
            source_type=data.source_type,
        )
        if resolved_source is None:
            raise SourceUnavailableError("Для цієї серії ще немає повного відео")

    host = User(display_name=data.host_name, is_guest=True)
    db.add(host)
    await db.flush()

    room = WatchRoom(
        invite_code=await unique_invite_code(db),
        host_id=host.id,
        anime_id=data.anime_id,
        episode_number=data.episode_number,
        source_type=resolved_source.source_type if resolved_source else "local_file",
        source_reference=(
            resolved_source.source_reference if resolved_source else data.source_reference
        ),
        file_hash=data.file_hash if resolved_source is None else None,
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
