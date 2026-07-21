from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.auth import token_digest
from app.config import settings
from app.models import AuthSession, ChatMessage, RoomMember, User, WatchRoom
from app.realtime import connections, room_state_cache


router = APIRouter(tags=["realtime"])
CONTROL_EVENTS = {"play", "pause", "seek", "rate"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_payload(room: WatchRoom, event_type: str = "state") -> dict[str, Any]:
    return {
        "type": event_type,
        "room_code": room.invite_code,
        "episode_number": room.episode_number,
        "current_time": room.current_time,
        "is_paused": room.is_paused,
        "playback_rate": room.playback_rate,
        "state_version": room.state_version,
        "server_time": now_iso(),
    }


async def resolve_member(
    room: WatchRoom,
    display_name: str,
    user_id: uuid.UUID | None,
    account: User | None,
) -> User:
    async with AsyncSessionLocal() as db:
        user = account
        if user is None and user_id:
            candidate = await db.get(User, user_id)
            user = candidate if candidate is not None and candidate.is_guest else None
        if user is None:
            user = User(display_name=display_name, is_guest=True)
            db.add(user)
            await db.flush()

        result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room.id,
                RoomMember.user_id == user.id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = RoomMember(room_id=room.id, user_id=user.id)
            db.add(membership)
        membership.is_connected = True
        await db.commit()
        return user


async def websocket_account(websocket: WebSocket) -> User | None:
    token = websocket.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    async with AsyncSessionLocal() as db:
        return await db.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == token_digest(token),
                AuthSession.expires_at > datetime.now(timezone.utc),
                User.is_guest.is_(False),
            )
        )


async def mark_disconnected(room_id: uuid.UUID, user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is not None:
            membership.is_connected = False
            await db.commit()


@router.websocket("/ws/rooms/{invite_code}")
async def room_socket(
    websocket: WebSocket,
    invite_code: str,
    name: str = Query(min_length=2, max_length=40),
    user_id: uuid.UUID | None = Query(default=None),
) -> None:
    room_code = invite_code.upper()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WatchRoom).where(WatchRoom.invite_code == room_code)
        )
        room = result.scalar_one_or_none()

    if room is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found")
        return

    clean_name = " ".join(name.split())
    account = await websocket_account(websocket)
    member = await resolve_member(room, clean_name, user_id, account)
    await connections.connect(room_code, websocket)
    online_count = connections.count(room_code)

    cached_state = await room_state_cache.get(room_code)
    await websocket.send_json(
        {
            "type": "connected",
            "user_id": str(member.id),
            "display_name": member.display_name,
            "online_count": online_count,
            "state": cached_state or state_payload(room),
        }
    )
    await connections.broadcast(
        room_code,
        {
            "type": "member_joined",
            "user_id": str(member.id),
            "display_name": member.display_name,
            "online_count": online_count,
            "server_time": now_iso(),
        },
    )

    try:
        while True:
            message = await websocket.receive_json()
            event_type = message.get("type")

            if event_type == "ping":
                await websocket.send_json({"type": "pong", "server_time": now_iso()})
                continue

            if event_type == "chat":
                content = str(message.get("content", "")).strip()[:2000]
                if not content:
                    continue
                async with AsyncSessionLocal() as db:
                    db.add(
                        ChatMessage(
                            room_id=room.id,
                            user_id=member.id,
                            content=content,
                        )
                    )
                    await db.commit()
                await connections.broadcast(
                    room_code,
                    {
                        "type": "chat",
                        "user_id": str(member.id),
                        "display_name": member.display_name,
                        "content": content,
                        "server_time": now_iso(),
                    },
                )
                continue

            if event_type == "source":
                file_hash = str(message.get("file_hash", "")).strip()[:128]
                file_name = str(message.get("file_name", "")).strip()[:500]
                if len(file_hash) < 8:
                    await websocket.send_json(
                        {"type": "error", "message": "Не вдалося перевірити файл"}
                    )
                    continue
                async with AsyncSessionLocal() as db:
                    current_room = await db.get(WatchRoom, room.id)
                    if current_room is None:
                        break
                    if current_room.file_hash and current_room.file_hash != file_hash:
                        await websocket.send_json(
                            {
                                "type": "source_mismatch",
                                "message": "У кімнаті вибрано іншу версію серії",
                                "expected_hash": current_room.file_hash,
                            }
                        )
                        continue
                    if current_room.file_hash is None:
                        current_room.file_hash = file_hash
                        current_room.source_reference = file_name or None
                        await db.commit()
                await connections.broadcast(
                    room_code,
                    {
                        "type": "source_ready",
                        "file_hash": file_hash,
                        "file_name": file_name,
                        "user_id": str(member.id),
                        "server_time": now_iso(),
                    },
                )
                continue

            if event_type not in CONTROL_EVENTS:
                await websocket.send_json(
                    {"type": "error", "message": "Невідомий тип події"}
                )
                continue

            async with AsyncSessionLocal() as db:
                current_room = await db.get(WatchRoom, room.id)
                if current_room is None:
                    break
                if not current_room.allow_members_control and member.id != current_room.host_id:
                    await websocket.send_json(
                        {"type": "error", "message": "Керувати плеєром може лише хост"}
                    )
                    continue

                try:
                    current_time = max(0.0, float(message.get("current_time", 0.0)))
                    playback_rate = min(
                        2.0,
                        max(0.25, float(message.get("playback_rate", current_room.playback_rate))),
                    )
                except (TypeError, ValueError):
                    await websocket.send_json(
                        {"type": "error", "message": "Некоректний стан плеєра"}
                    )
                    continue

                current_room.current_time = current_time
                current_room.playback_rate = playback_rate
                if event_type == "play":
                    current_room.is_paused = False
                elif event_type == "pause":
                    current_room.is_paused = True
                current_room.state_version += 1
                current_room.updated_at = datetime.now(timezone.utc)
                await db.commit()
                payload = state_payload(current_room, event_type)
                payload["actor_id"] = str(member.id)

            await room_state_cache.save(room_code, payload)
            await connections.broadcast(room_code, payload)
    except WebSocketDisconnect:
        pass
    finally:
        connections.disconnect(room_code, websocket)
        await mark_disconnected(room.id, member.id)
        online_count = connections.count(room_code)
        await connections.broadcast(
            room_code,
            {
                "type": "member_left",
                "user_id": str(member.id),
                "display_name": member.display_name,
                "online_count": online_count,
                "server_time": now_iso(),
            },
        )
