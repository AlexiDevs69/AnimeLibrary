from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import optional_user
from app.database import get_db
from app.models import User
from app.schemas import RoomCreate, RoomJoinOut, RoomOut


router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=RoomJoinOut, status_code=status.HTTP_201_CREATED)
async def create_watch_room(
    payload: RoomCreate,
    db: AsyncSession = Depends(get_db),
    account: User | None = Depends(optional_user),
) -> RoomJoinOut:
    try:
        room, host = await crud.create_room(db, payload, account=account)
    except crud.SourceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RoomJoinOut(user_id=host.id, room=crud.room_to_schema(room))


@router.get("/{invite_code}", response_model=RoomOut)
async def room_detail(
    invite_code: str,
    db: AsyncSession = Depends(get_db),
) -> RoomOut:
    room = await crud.get_room(db, invite_code)
    if room is None:
        raise HTTPException(status_code=404, detail="Кімнату не знайдено")
    return crud.room_to_schema(room)
