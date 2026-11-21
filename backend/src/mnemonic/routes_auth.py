"""Account endpoints: register, login, me, delete me."""

import asyncio
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm

from mnemonic.auth import (
    DUMMY_HASH,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from mnemonic.config import Settings, get_settings
from mnemonic.openapi import R401, R422, R429
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
    summary="Register",
    description="Create an account. The password is stored only as an argon2id hash.",
    responses={
        403: {"description": "Wrong or missing registration code"},
        409: {"description": "Email already registered"},
        422: R422,
        429: R429,
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
    summary="Log in",
    description="OAuth2 password form: `username` is the email. Returns a Bearer token (24 h).",
    responses={401: {"description": "Wrong email or password"}, 422: R422, 429: R429},
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


@router.get(
    "/me",
    response_model=UserOut,
    summary="Who am I",
    description="The account the Bearer token belongs to.",
    responses={401: R401},
)
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user


@router.delete(
    "/me",
    status_code=204,
    summary="Delete my account",
    description="Permanently deletes the account with all its sessions, messages, documents and "
    "chunks. The token stops working at once.",
    responses={401: R401},
)
async def delete_me(
    user: Annotated[User, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]
) -> Response:
    await asyncio.to_thread(store.delete_user, user.id)  # the rest goes by ON DELETE CASCADE
    return Response(status_code=204)
