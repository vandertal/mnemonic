"""Account endpoints: register, login, me."""

import asyncio
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from mnemonic.auth import (
    DUMMY_HASH,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from mnemonic.config import Settings, get_settings
from mnemonic.schemas import RegisterRequest, TokenOut, UserOut
from mnemonic.security import limit_auth_per_ip
from mnemonic.store import EmailTaken, Store, User, get_store

router = APIRouter(prefix="/auth", tags=["auth"])


def normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post(
    "/register",
    status_code=201,
    response_model=UserOut,
    dependencies=[Depends(limit_auth_per_ip)],
    responses={
        403: {"description": "Wrong or missing registration code"},
        409: {"description": "Email already registered"},
    },
)
async def register(
    body: RegisterRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
) -> User:
    """Create an account. The password is stored only as an argon2id hash."""
    if settings.registration_code and not (
        body.registration_code is not None
        and secrets.compare_digest(
            body.registration_code.encode(), settings.registration_code.encode()
        )
    ):
        raise HTTPException(status_code=403, detail="Invalid registration code")
    # argon2 is CPU-bound (~50 ms): a worker thread keeps the event loop free for other requests.
    hashed = await asyncio.to_thread(hash_password, body.password)
    try:
        return await asyncio.to_thread(store.create_user, normalize_email(body.email), hashed)
    except EmailTaken:
        raise HTTPException(status_code=409, detail="Email already registered") from None


@router.post(
    "/login",
    response_model=TokenOut,
    dependencies=[Depends(limit_auth_per_ip)],
    responses={401: {"description": "Wrong email or password"}},
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
) -> TokenOut:
    """Exchange email (form field `username`) and password for a Bearer token."""
    found = await asyncio.to_thread(store.get_user_by_email, normalize_email(form.username))
    user, stored_hash = found if found else (None, DUMMY_HASH)
    # Always verify, even for an unknown email, so both failures look and take the same.
    ok = await asyncio.to_thread(verify_password, form.password, stored_hash)
    if user is None or not ok:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=UserOut, responses={401: {"description": "Invalid token"}})
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    """The account the Bearer token belongs to."""
    return user
