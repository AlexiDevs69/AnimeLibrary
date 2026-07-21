import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import current_user, optional_user
from app.database import get_db
from app.models import Friendship, RoomInvitation, RoomMember, User, WatchRoom
from app.schemas import (
    RoomCreate,
    RoomInvitationAcceptOut,
    RoomInvitationCreate,
    RoomJoinOut,
    RoomOut,
)


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


@router.post(
    "/{invite_code}/invites",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def invite_friend_to_room(
    invite_code: str,
    payload: RoomInvitationCreate,
    account: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    room = await db.scalar(
        select(WatchRoom).where(WatchRoom.invite_code == invite_code.upper())
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Перегляд не знайдено")
    membership = await db.scalar(
        select(RoomMember.id).where(
            RoomMember.room_id == room.id,
            RoomMember.user_id == account.id,
        )
    )
    if membership is None and room.host_id != account.id:
        raise HTTPException(status_code=403, detail="Ви не є учасником цього перегляду")
    friend = await db.get(User, payload.friend_id)
    if friend is None or friend.is_guest:
        raise HTTPException(status_code=404, detail="Друга не знайдено")
    pair = sorted((account.id, friend.id), key=str)
    relationship = await db.scalar(
        select(Friendship.id).where(
            Friendship.user_one_id == pair[0],
            Friendship.user_two_id == pair[1],
            Friendship.status == "accepted",
        )
    )
    if relationship is None:
        raise HTTPException(status_code=403, detail="Запрошувати можна лише друзів")
    invitation = await db.scalar(
        select(RoomInvitation).where(
            RoomInvitation.room_id == room.id,
            RoomInvitation.recipient_id == friend.id,
        )
    )
    now = datetime.now(timezone.utc)
    if invitation is None:
        invitation = RoomInvitation(
            room_id=room.id,
            sender_id=account.id,
            recipient_id=friend.id,
            expires_at=now + timedelta(hours=24),
        )
        db.add(invitation)
    else:
        invitation.sender_id = account.id
        invitation.status = "pending"
        invitation.expires_at = now + timedelta(hours=24)
        invitation.updated_at = now
    await db.commit()


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=RoomInvitationAcceptOut,
)
async def accept_room_invitation(
    invitation_id: uuid.UUID,
    account: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomInvitationAcceptOut:
    invitation = await db.get(RoomInvitation, invitation_id)
    now = datetime.now(timezone.utc)
    expires_at = invitation.expires_at if invitation is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        invitation is None
        or invitation.recipient_id != account.id
        or invitation.status != "pending"
        or expires_at is None
        or expires_at <= now
    ):
        raise HTTPException(status_code=404, detail="Запрошення не знайдено або прострочене")
    room = await db.get(WatchRoom, invitation.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Перегляд уже недоступний")
    invitation.status = "accepted"
    invitation.updated_at = now
    await db.commit()
    return RoomInvitationAcceptOut(invite_code=room.invite_code)


@router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def decline_room_invitation(
    invitation_id: uuid.UUID,
    account: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    invitation = await db.get(RoomInvitation, invitation_id)
    if invitation is None or invitation.recipient_id != account.id:
        raise HTTPException(status_code=404, detail="Запрошення не знайдено")
    await db.delete(invitation)
    await db.commit()
