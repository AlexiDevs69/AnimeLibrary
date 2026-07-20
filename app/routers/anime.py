import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.anilibria import AniLibriaError
from app.anilist import AniListError, fetch_anime
from app.database import get_db
from app.kodik import KodikError
from app.schemas import AnimeDetailOut, AnimeOut, EpisodeOut, VideoSourceOut


router = APIRouter(prefix="/api/anime", tags=["anime"])
logger = logging.getLogger(__name__)


@router.get("/search", response_model=list[AnimeOut])
async def search_anime(
    q: str | None = Query(default=None, min_length=2, max_length=100),
    page: int = Query(default=1, ge=1, le=100),
    limit: int = Query(default=24, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[AnimeOut]:
    try:
        items = await fetch_anime(q, page=page, per_page=limit)
    except AniListError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    anime = await crud.cache_anime_batch(db, items)
    return [AnimeOut.model_validate(item) for item in anime]


@router.get("/{anime_id}", response_model=AnimeDetailOut)
async def anime_detail(
    anime_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AnimeDetailOut:
    anime = await crud.get_anime_detail(db, anime_id)
    if anime is None:
        raise HTTPException(status_code=404, detail="Аніме не знайдено")
    changed = False
    try:
        changed = await crud.sync_anilibria_sources(db, anime)
    except AniLibriaError as exc:
        # The catalog remains usable even when the optional video provider is down.
        logger.warning("AniLibria sync failed for anime %s: %s", anime_id, exc)
    try:
        changed = await crud.sync_kodik_releases(db, anime) or changed
    except KodikError as exc:
        # Kodik is an optional fallback; a provider outage must not break AniList
        # metadata or already cached video sources.
        logger.warning("Kodik sync failed for anime %s: %s", anime_id, exc)
    if changed:
        anime = await crud.get_anime_detail(db, anime_id)
        if anime is None:
            raise HTTPException(status_code=404, detail="Аніме не знайдено")

    base = AnimeOut.model_validate(anime)
    episodes = [
        EpisodeOut(
            id=episode.id,
            number=episode.number,
            title=episode.title,
            thumbnail_url=episode.thumbnail_url,
            duration=episode.duration,
            sources=sorted(
                [
                    VideoSourceOut(
                        id=source.id,
                        source_type=source.source_type,
                        region=source.region,
                        language=source.language,
                        label="AniLibria" if source.source_type == "anilibria_hls" else None,
                    )
                    for source in episode.sources
                    if source.is_active and source.source_type in crud.MANAGED_SOURCE_TYPES
                ]
                + [
                    VideoSourceOut(
                        id=release.id,
                        source_type="kodik_embed",
                        region=None,
                        language=None,
                        label=release.translation_title or "Kodik",
                    )
                    for release in anime.kodik_releases
                    if release.is_active and episode.number <= release.episodes_count
                ],
                key=lambda item: crud.SOURCE_PRIORITY.get(item.source_type, 9),
            ),
        )
        for episode in anime.episodes
    ]
    return AnimeDetailOut(**base.model_dump(), episodes=episodes)
