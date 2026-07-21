from __future__ import annotations

import uuid
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import (
    clear_session_cookie,
    create_session,
    current_user,
    hash_password,
    optional_user,
    revoke_request_session,
    set_session_cookie,
    verify_password,
)
from app.database import get_db
from app.models import (
    Anime,
    AnimeLibraryEntry,
    Friendship,
    ProfileImage,
    RoomInvitation,
    RoomMember,
    User,
    WatchRoom,
    WatchProgress,
)
from app.profile_images import MAX_UPLOAD_BYTES, ProfileImageError, process_profile_image
from app.schemas import (
    AccountOut,
    AnimeOut,
    FriendEntryOut,
    FriendRequestCreate,
    FriendRequestOut,
    FriendsDashboardOut,
    FriendUserOut,
    LibraryEntryIn,
    LoginIn,
    ProfileAnimeOut,
    ProfileOut,
    ProfileStatsOut,
    ProfileUpdateIn,
    ProgressIn,
    PublicAccountOut,
    RegisterIn,
    RoomInvitationOut,
)


router = APIRouter(tags=["profiles"])
FRIEND_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


async def unique_friend_code(db: AsyncSession) -> str:
    for _ in range(20):
        token = "".join(secrets.choice(FRIEND_CODE_ALPHABET) for _ in range(8))
        code = f"AL-{token[:4]}-{token[4:]}"
        if await db.scalar(select(User.id).where(User.friend_code == code)) is None:
            return code
    raise RuntimeError("Не вдалося створити код акаунта")


def account_out(user: User) -> AccountOut:
    return AccountOut(
        id=user.id,
        username=user.username or "",
        email=user.email or "",
        friend_code=user.friend_code or "",
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        banner_url=user.banner_url,
        bio=user.bio,
        is_profile_private=user.is_profile_private,
        created_at=user.created_at,
    )


@router.post("/api/auth/register", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    existing = await db.scalar(
        select(User.id).where(
            or_(
                func.lower(User.username) == payload.username,
                func.lower(User.email) == payload.email,
            )
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Логін або email уже зайнятий")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        friend_code=await unique_friend_code(db),
        display_name=payload.display_name,
        is_guest=False,
    )
    db.add(user)
    try:
        await db.flush()
        token = await create_session(db, user)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Логін або email уже зайнятий") from exc
    set_session_cookie(response, token)
    return account_out(user)


@router.post("/api/auth/login", response_model=AccountOut)
async def login(
    payload: LoginIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    login_value = payload.login.strip().lower()
    result = await db.execute(
        select(User).where(
            User.is_guest.is_(False),
            or_(
                func.lower(User.username) == login_value,
                func.lower(User.email) == login_value,
            ),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")
    token = await create_session(db, user)
    set_session_cookie(response, token)
    return account_out(user)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await revoke_request_session(request, db)
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/api/auth/me", response_model=AccountOut)
async def me(user: User = Depends(current_user)) -> AccountOut:
    return account_out(user)


@router.patch("/api/profiles/me", response_model=AccountOut)
async def update_profile(
    payload: ProfileUpdateIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    user.display_name = payload.display_name
    user.bio = payload.bio
    user.avatar_url = payload.avatar_url
    user.banner_url = payload.banner_url
    user.is_profile_private = payload.is_profile_private
    await db.commit()
    return account_out(user)


@router.post("/api/profiles/me/images/{kind}", response_model=AccountOut)
async def upload_profile_image(
    kind: str,
    image: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountOut:
    if kind not in {"avatar", "banner"}:
        raise HTTPException(status_code=404, detail="Невідомий тип зображення")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Підтримуються лише PNG, JPEG та WebP")

    payload = await image.read(MAX_UPLOAD_BYTES + 1)
    await image.close()
    try:
        processed = process_profile_image(payload, kind)  # type: ignore[arg-type]
    except ProfileImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    old_result = await db.execute(
        select(ProfileImage).where(
            ProfileImage.user_id == user.id,
            ProfileImage.kind == kind,
        )
    )
    old_image = old_result.scalar_one_or_none()
    if old_image is not None:
        await db.delete(old_image)
        await db.flush()

    stored = ProfileImage(
        user_id=user.id,
        kind=kind,
        mime_type=processed.mime_type,
        content=processed.content,
        width=processed.width,
        height=processed.height,
    )
    db.add(stored)
    await db.flush()
    media_url = f"/api/media/profile/{stored.id}"
    if kind == "avatar":
        user.avatar_url = media_url
    else:
        user.banner_url = media_url
    await db.commit()
    return account_out(user)


@router.get("/api/media/profile/{image_id}", include_in_schema=False)
async def profile_image(
    image_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    stored = await db.get(ProfileImage, image_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Зображення не знайдено")
    etag = f'"{stored.id}"'
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=stored.content, media_type=stored.mime_type, headers=headers)


def friend_pair(first: uuid.UUID, second: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return tuple(sorted((first, second), key=str))  # type: ignore[return-value]


def friend_user(user: User, online_ids: set[uuid.UUID]) -> FriendUserOut:
    return FriendUserOut(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        friend_code=user.friend_code or "",
        is_online=user.id in online_ids,
    )


@router.get("/api/friends", response_model=FriendsDashboardOut)
async def friends_dashboard(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendsDashboardOut:
    friendship_result = await db.execute(
        select(Friendship)
        .where(
            or_(
                Friendship.user_one_id == user.id,
                Friendship.user_two_id == user.id,
            )
        )
        .order_by(Friendship.updated_at.desc())
    )
    relationships = list(friendship_result.scalars())
    other_ids = {
        item.user_two_id if item.user_one_id == user.id else item.user_one_id
        for item in relationships
    }
    users_by_id: dict[uuid.UUID, User] = {}
    if other_ids:
        users_result = await db.execute(select(User).where(User.id.in_(other_ids)))
        users_by_id = {item.id: item for item in users_result.scalars()}
        online_result = await db.execute(
            select(RoomMember.user_id)
            .where(
                RoomMember.user_id.in_(other_ids),
                RoomMember.is_connected.is_(True),
            )
            .distinct()
        )
        online_ids = set(online_result.scalars())
    else:
        online_ids = set()

    friends: list[FriendEntryOut] = []
    incoming: list[FriendRequestOut] = []
    outgoing: list[FriendRequestOut] = []
    for relationship in relationships:
        other_id = (
            relationship.user_two_id
            if relationship.user_one_id == user.id
            else relationship.user_one_id
        )
        other = users_by_id.get(other_id)
        if other is None or other.is_guest:
            continue
        entry = FriendEntryOut(
            friendship_id=relationship.id,
            user=friend_user(other, online_ids),
            created_at=relationship.created_at,
        )
        if relationship.status == "accepted":
            friends.append(entry)
        elif relationship.status == "pending":
            request = FriendRequestOut(
                **entry.model_dump(),
                direction="outgoing" if relationship.requested_by_id == user.id else "incoming",
            )
            (outgoing if request.direction == "outgoing" else incoming).append(request)

    invitation_result = await db.execute(
        select(RoomInvitation)
        .options(
            selectinload(RoomInvitation.room).selectinload(WatchRoom.anime),
            selectinload(RoomInvitation.sender),
        )
        .where(
            RoomInvitation.recipient_id == user.id,
            RoomInvitation.status == "pending",
            RoomInvitation.expires_at > datetime.now(timezone.utc),
        )
        .order_by(RoomInvitation.created_at.desc())
    )
    invitations = list(invitation_result.scalars())
    invitation_senders = {item.sender_id for item in invitations}
    invitation_online = set(online_ids)
    if invitation_senders - other_ids:
        online_result = await db.execute(
            select(RoomMember.user_id)
            .where(
                RoomMember.user_id.in_(invitation_senders),
                RoomMember.is_connected.is_(True),
            )
            .distinct()
        )
        invitation_online.update(online_result.scalars())

    return FriendsDashboardOut(
        my_code=user.friend_code or "",
        friends=friends,
        incoming=incoming,
        outgoing=outgoing,
        room_invitations=[
            RoomInvitationOut(
                id=item.id,
                invite_code=item.room.invite_code,
                anime=AnimeOut.model_validate(item.room.anime) if item.room.anime else None,
                episode_number=item.room.episode_number,
                sender=friend_user(item.sender, invitation_online),
                created_at=item.created_at,
                expires_at=item.expires_at,
            )
            for item in invitations
        ],
    )


@router.post("/api/friends/requests", status_code=status.HTTP_204_NO_CONTENT)
async def send_friend_request(
    payload: FriendRequestCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    target = await db.scalar(
        select(User).where(
            User.friend_code == payload.code,
            User.is_guest.is_(False),
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Акаунт із таким кодом не знайдено")
    if target.id == user.id:
        raise HTTPException(status_code=409, detail="Не можна додати самого себе")
    user_one_id, user_two_id = friend_pair(user.id, target.id)
    relationship = await db.scalar(
        select(Friendship).where(
            Friendship.user_one_id == user_one_id,
            Friendship.user_two_id == user_two_id,
        )
    )
    if relationship is not None and relationship.status == "accepted":
        raise HTTPException(status_code=409, detail="Ви вже друзі")
    if relationship is not None and relationship.status == "pending":
        raise HTTPException(status_code=409, detail="Заявка вже існує")
    if relationship is None:
        relationship = Friendship(
            user_one_id=user_one_id,
            user_two_id=user_two_id,
            requested_by_id=user.id,
        )
        db.add(relationship)
    else:
        relationship.requested_by_id = user.id
        relationship.status = "pending"
        relationship.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Заявка вже існує") from exc


@router.post(
    "/api/friends/requests/{friendship_id}/accept",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def accept_friend_request(
    friendship_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    relationship = await db.get(Friendship, friendship_id)
    if (
        relationship is None
        or user.id not in {relationship.user_one_id, relationship.user_two_id}
        or relationship.status != "pending"
        or relationship.requested_by_id == user.id
    ):
        raise HTTPException(status_code=404, detail="Вхідну заявку не знайдено")
    relationship.status = "accepted"
    relationship.updated_at = datetime.now(timezone.utc)
    await db.commit()


@router.delete(
    "/api/friends/requests/{friendship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_friend_request(
    friendship_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    relationship = await db.get(Friendship, friendship_id)
    if (
        relationship is None
        or user.id not in {relationship.user_one_id, relationship.user_two_id}
        or relationship.status != "pending"
    ):
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    await db.delete(relationship)
    await db.commit()


@router.delete("/api/friends/{friend_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend(
    friend_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    user_one_id, user_two_id = friend_pair(user.id, friend_id)
    relationship = await db.scalar(
        select(Friendship).where(
            Friendship.user_one_id == user_one_id,
            Friendship.user_two_id == user_two_id,
            Friendship.status == "accepted",
        )
    )
    if relationship is None:
        raise HTTPException(status_code=404, detail="Друга не знайдено")
    await db.delete(relationship)
    await db.commit()


async def build_profile(
    db: AsyncSession,
    profile_user: User,
    viewer: User | None,
) -> ProfileOut:
    is_owner = viewer is not None and viewer.id == profile_user.id
    public_user = PublicAccountOut(
        id=profile_user.id,
        username=profile_user.username or "",
        display_name=profile_user.display_name,
        avatar_url=profile_user.avatar_url,
        banner_url=profile_user.banner_url,
        bio=profile_user.bio,
        is_profile_private=profile_user.is_profile_private,
        created_at=profile_user.created_at,
    )
    if profile_user.is_profile_private and not is_owner:
        return ProfileOut(
            user=public_user,
            is_owner=False,
            entries=[],
            recent=[],
            stats=ProfileStatsOut(
                library_count=0,
                completed_count=0,
                favorite_count=0,
                episodes_watched=0,
                minutes_watched=0,
            ),
        )

    entry_result = await db.execute(
        select(AnimeLibraryEntry)
        .options(selectinload(AnimeLibraryEntry.anime))
        .where(AnimeLibraryEntry.user_id == profile_user.id)
        .order_by(AnimeLibraryEntry.updated_at.desc())
    )
    library_entries = list(entry_result.scalars())
    progress_result = await db.execute(
        select(WatchProgress).where(WatchProgress.user_id == profile_user.id)
    )
    progress_by_anime = {item.anime_id: item for item in progress_result.scalars()}

    entries: list[ProfileAnimeOut] = []
    episodes_watched = 0
    minutes_watched = 0
    for entry in library_entries:
        progress = progress_by_anime.get(entry.anime_id)
        if progress is not None:
            finished_before = max(0, progress.episode_number - 1)
            episodes_watched += finished_before + int(progress.completed)
            duration = entry.anime.episode_duration or 24
            minutes_watched += finished_before * duration + int(progress.current_time // 60)
        entries.append(
            ProfileAnimeOut(
                anime=AnimeOut.model_validate(entry.anime),
                status=entry.status,  # type: ignore[arg-type]
                is_favorite=entry.is_favorite,
                is_pinned=entry.is_pinned,
                rating=entry.rating,
                created_at=entry.created_at,
                updated_at=max(entry.updated_at, progress.updated_at) if progress else entry.updated_at,
                episode_number=progress.episode_number if progress else None,
                current_time=progress.current_time if progress else None,
                progress_completed=progress.completed if progress else False,
            )
        )

    entries.sort(key=lambda item: item.updated_at, reverse=True)
    return ProfileOut(
        user=public_user,
        is_owner=is_owner,
        entries=entries,
        recent=[item for item in entries if item.episode_number is not None][:8],
        stats=ProfileStatsOut(
            library_count=len(entries),
            completed_count=sum(item.status == "completed" for item in entries),
            favorite_count=sum(item.is_favorite for item in entries),
            episodes_watched=episodes_watched,
            minutes_watched=minutes_watched,
        ),
    )


@router.get("/api/profiles/me", response_model=ProfileOut)
async def my_profile(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    return await build_profile(db, user, user)


@router.get("/api/profiles/{username}", response_model=ProfileOut)
async def public_profile(
    username: str,
    viewer: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    result = await db.execute(
        select(User).where(
            func.lower(User.username) == username.strip().lower(),
            User.is_guest.is_(False),
        )
    )
    profile_user = result.scalar_one_or_none()
    if profile_user is None:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    return await build_profile(db, profile_user, viewer)


@router.put("/api/library/{anime_id}", response_model=ProfileAnimeOut)
async def save_library_entry(
    anime_id: uuid.UUID,
    payload: LibraryEntryIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileAnimeOut:
    anime = await db.get(Anime, anime_id)
    if anime is None:
        raise HTTPException(status_code=404, detail="Аніме не знайдено")
    result = await db.execute(
        select(AnimeLibraryEntry).where(
            AnimeLibraryEntry.user_id == user.id,
            AnimeLibraryEntry.anime_id == anime_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = AnimeLibraryEntry(user_id=user.id, anime_id=anime_id)
        db.add(entry)
    if payload.is_pinned and not entry.is_pinned:
        pins = await db.scalar(
            select(func.count(AnimeLibraryEntry.id)).where(
                AnimeLibraryEntry.user_id == user.id,
                AnimeLibraryEntry.is_pinned.is_(True),
            )
        )
        if (pins or 0) >= 6:
            raise HTTPException(status_code=409, detail="Можна закріпити не більше 6 аніме")
    entry.status = payload.status
    entry.is_favorite = payload.is_favorite
    entry.is_pinned = payload.is_pinned
    entry.rating = payload.rating
    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return ProfileAnimeOut(
        anime=AnimeOut.model_validate(anime),
        status=payload.status,
        is_favorite=entry.is_favorite,
        is_pinned=entry.is_pinned,
        rating=entry.rating,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.delete("/api/library/{anime_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_library_entry(
    anime_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        delete(AnimeLibraryEntry).where(
            AnimeLibraryEntry.user_id == user.id,
            AnimeLibraryEntry.anime_id == anime_id,
        )
    )
    await db.commit()


@router.post("/api/progress", status_code=status.HTTP_204_NO_CONTENT)
async def save_progress(
    payload: ProgressIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    anime = await db.get(Anime, payload.anime_id)
    if anime is None:
        raise HTTPException(status_code=404, detail="Аніме не знайдено")
    progress_result = await db.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user.id,
            WatchProgress.anime_id == payload.anime_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    if progress is None:
        progress = WatchProgress(user_id=user.id, anime_id=payload.anime_id)
        db.add(progress)
    progress.episode_number = payload.episode_number
    progress.current_time = payload.current_time
    progress.completed = payload.completed
    progress.updated_at = datetime.now(timezone.utc)

    entry_result = await db.execute(
        select(AnimeLibraryEntry).where(
            AnimeLibraryEntry.user_id == user.id,
            AnimeLibraryEntry.anime_id == payload.anime_id,
        )
    )
    entry = entry_result.scalar_one_or_none()
    if entry is None:
        entry = AnimeLibraryEntry(
            user_id=user.id,
            anime_id=payload.anime_id,
            status="watching",
        )
        db.add(entry)
    elif entry.status == "planned":
        entry.status = "watching"
    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()
