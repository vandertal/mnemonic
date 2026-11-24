"""Owner-only numbers: GET /admin/stats. Hidden from the OpenAPI docs."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from mnemonic.auth import get_current_user
from mnemonic.config import Settings, admin_email_set, get_settings
from mnemonic.store import Store, User, get_store

router = APIRouter(prefix="/admin", include_in_schema=False)


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """401 without a valid token (from get_current_user); 404 for everyone not in ADMIN_EMAILS,
    so the route does not even reveal that it exists."""
    if user.email.lower() not in admin_email_set(settings):
        raise HTTPException(status_code=404, detail="Not Found")
    return user


@router.get("/stats")
async def stats(
    _: Annotated[User, Depends(require_admin)], store: Annotated[Store, Depends(get_store)]
) -> dict:
    return await asyncio.to_thread(store.event_stats)
