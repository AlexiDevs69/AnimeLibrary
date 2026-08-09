from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Anime, Episode, VideoSource
from app.schemas import VideoSourceAdminOut, VideoSourceCreate

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    if not settings.admin_api_key or not secrets.compare_digest(
        x_admin_key, settings.admin_api_key
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")


@router.post(
    "/video-sources",
    response_model=VideoSourceAdminOut,
    dependencies=[Depends(require_admin_key)],
)
async def save_licensed_video_source(
    payload: VideoSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> VideoSourceAdminOut:
    if not payload.confirmed_licensed:
        raise HTTPException(
            status_code=422,
            detail="Потрібно підтвердити право на вбудовування відео",
        )
    anime = await db.scalar(select(Anime).where(Anime.anilist_id == payload.anilist_id))
    if anime is None:
        raise HTTPException(status_code=404, detail="Спочатку відкрийте аніме в каталозі")

    episode = await db.scalar(
        select(Episode).where(
            Episode.anime_id == anime.id,
            Episode.number == payload.episode_number,
        )
    )
    if episode is None:
        episode = Episode(
            anime_id=anime.id,
            number=payload.episode_number,
            title=payload.episode_title,
            duration=payload.duration or anime.episode_duration,
        )
        db.add(episode)
        await db.flush()

    source = await db.scalar(
        select(VideoSource).where(
            VideoSource.episode_id == episode.id,
            VideoSource.source_type == payload.source_type,
            VideoSource.label == payload.label,
        )
    )
    if source is None:
        source = VideoSource(
            episode_id=episode.id,
            source_type=payload.source_type,
            source_reference=payload.source_url,
            label=payload.label,
            language=payload.language,
            region=payload.region,
            is_active=True,
        )
        db.add(source)
    else:
        source.source_reference = payload.source_url
        source.language = payload.language
        source.region = payload.region
        source.is_active = True
    await db.commit()
    await db.refresh(source)
    return VideoSourceAdminOut(
        id=source.id,
        episode_id=source.episode_id,
        source_type=payload.source_type,
        source_reference=source.source_reference,
        label=source.label,
        language=source.language,
        region=source.region,
        is_active=source.is_active,
    )
