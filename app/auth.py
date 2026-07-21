from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AuthSession, User


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return "$".join(
        ("scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P), salt.hex(), digest.hex())
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.session_duration_days),
        )
    )
    await db.commit()
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_duration_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def user_from_request(request: Request, db: AsyncSession) -> User | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    result = await db.execute(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == token_digest(token),
            AuthSession.expires_at > datetime.now(timezone.utc),
            User.is_guest.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    return await user_from_request(request, db)


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Потрібно увійти в профіль",
        )
    return user


async def revoke_request_session(request: Request, db: AsyncSession) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await db.execute(
            delete(AuthSession).where(AuthSession.token_hash == token_digest(token))
        )
        await db.commit()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    await db.commit()
