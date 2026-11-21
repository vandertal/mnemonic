"""Passwords (argon2id) and access tokens (JWT HS256)."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from mnemonic.config import Settings, get_settings
from mnemonic.store import Store, User, get_store

ALGORITHM = "HS256"

# recommended() = argon2id with safe defaults. The salt is random per hash and stored inside it.
password_hash = PasswordHash.recommended()
# Verified when the email is unknown, so "no such user" costs the same time as "wrong password".
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, settings: Settings) -> dict:
    """Verify signature and expiry. `algorithms` is explicit: the token's own header must never
    choose the algorithm (the classic `alg: none` / key-confusion attacks)."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )


def invalid_token() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
) -> User:
    """The user behind the Bearer token. Every failure gives the same 401."""
    if token is None:
        raise invalid_token()
    try:
        user_id = UUID(decode_token(token, settings)["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise invalid_token() from None
    user = await asyncio.to_thread(store.get_user, user_id)
    if user is None:  # a valid token of a deleted account
        raise invalid_token()
    return user
