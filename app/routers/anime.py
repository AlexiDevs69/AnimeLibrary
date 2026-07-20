import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.anilist import AniListError, fetch_anime
from app.database import get_db
from app.schemas import AnimeDetailOut, AnimeOut


router = APIRouter(prefix="/api/anime", tags=["anime"])


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
    return AnimeDetailOut.model_validate(anime)

