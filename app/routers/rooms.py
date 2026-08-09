import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import current_user, optional_user
from app.database import get_db
from app.models import (
    Friendship,
    RoomInvitation,
    RoomMember,
    User,
    VideoSource,
    WatchRoom,
)
from app.realtime import connections, room_state_cache
from app.schemas import (
    RoomCreate,
    RoomEpisodeChangeIn,
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

    # Older catalog rooms could be created with source_type=local_file even
    # though no file was ever selected. In that case the UI only shows the
    # upload/drop zone and the managed player never gets a source.
    #
    # Repair only this exact broken state. Real local-file rooms already have
    # a file_hash or source_reference and are left untouched.
    needs_managed_source = (
        room.anime_id is not None
        and room.source_type == "local_file"
        and room.source_reference is None
        and room.file_hash is None
    )

    if needs_managed_source:
        try:
            if room.anime is not None:
                # Refresh AniLibriya sources when their cache is stale/missing.
                await crud.sync_anilibria_sources(db, room.anime)

            resolved = await crud.resolve_room_source(
                db,
                anime_id=room.anime_id,
                episode_number=room.episode_number,
                source_id=None,
                source_type="auto",
            )

            if resolved is not None:
                room.source_type, room.source_reference, room.source_id = resolved
                room.file_hash = None
                room.current_time = 0
                room.is_paused = True
                room.playback_rate = 1
                room.state_version += 1
                room.updated_at = datetime.now(timezone.utc)
                await db.commit()

                room = await crud.get_room(db, invite_code)
                if room is None:
                    raise HTTPException(status_code=404, detail="Кімнату не знайдено")
        except Exception:
            # Provider outages must not make an existing room inaccessible.
            await db.rollback()

    return crud.room_to_schema(room)


@router.patch("/{invite_code}/episode", response_model=RoomOut)
async def change_room_episode(
    invite_code: str,
    payload: RoomEpisodeChangeIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomOut:
    room = await db.scalar(
        select(WatchRoom)
        .where(WatchRoom.invite_code == invite_code.upper())
        .with_for_update()
    )
    if room is None or room.host_id != user.id:
        raise HTTPException(status_code=404, detail="Перегляд не знайдено")
    if room.anime_id is None:
        raise HTTPException(status_code=409, detail="Спочатку виберіть аніме")
    if payload.episode_number == room.episode_number:
        current = await crud.get_room(db, room.invite_code)
        if current is None:
            raise HTTPException(status_code=404, detail="Перегляд не знайдено")
        return crud.room_to_schema(current)

    if room.source_type == "local_file":
        room.source_id = None
        room.source_reference = None
        room.file_hash = None
    else:
        preferred_id = room.source_id if room.source_type == "kodik_embed" else None
        preferred_label = None
        if room.source_id is not None and room.source_type != "kodik_embed":
            current_source = await db.get(VideoSource, room.source_id)
            preferred_label = current_source.label if current_source is not None else None
        resolved = await crud.resolve_room_source(
            db,
            anime_id=room.anime_id,
            episode_number=payload.episode_number,
            source_id=preferred_id,
            source_type=room.source_type,
            source_label=preferred_label,
        )
        if resolved is None:
            resolved = await crud.resolve_room_source(
                db,
                anime_id=room.anime_id,
                episode_number=payload.episode_number,
                source_id=None,
                source_type="auto",
            )
        if resolved is None:
            raise HTTPException(
                status_code=409,
                detail="Для наступної серії ще немає доступного відео",
            )
        room.source_type, room.source_reference, room.source_id = resolved
        room.file_hash = None

    room.episode_number = payload.episode_number
    room.current_time = 0
    room.is_paused = True
    room.playback_rate = 1
    room.state_version += 1
    room.updated_at = datetime.now(timezone.utc)
    await db.commit()

    message = {
        "type": "episode_changed",
        "room_code": room.invite_code,
        "episode_number": room.episode_number,
        "current_time": 0,
        "is_paused": True,
        "playback_rate": 1,
        "state_version": room.state_version,
        "server_time": room.updated_at.isoformat(),
    }
    await room_state_cache.save(room.invite_code, message)
    await connections.broadcast(room.invite_code, message)
    current = await crud.get_room(db, room.invite_code)
    if current is None:
        raise HTTPException(status_code=404, detail="Перегляд не знайдено")
    return crud.room_to_schema(current)


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
