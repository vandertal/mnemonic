"""The Telegram webhook: POST /telegram/webhook/{secret}. Hidden from the OpenAPI docs.

Telegram calls this URL for every message sent to the bot. Two secrets must match: the one in the
path and the `X-Telegram-Bot-Api-Secret-Token` header Telegram adds because we passed the same
value to setWebhook. Anything else gets a 404, so the route does not reveal itself. The answer is
200 at once and the work runs in a background task: an LLM call takes seconds, and Telegram
resends an update it did not get a 200 for.
"""

import hmac
import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from mnemonic.answering import get_provider, get_retriever
from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm.base import LLMProvider
from mnemonic.retrieval import Retriever
from mnemonic.security import get_global_limiter, get_telegram_limiter
from mnemonic.store import Store, get_store
from mnemonic.telegram_bot import TelegramApi, TelegramBot, UpdateDedupe, run_update

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

SECRET_HEADER = "x-telegram-bot-api-secret-token"


@lru_cache
def get_telegram_api() -> TelegramApi | None:
    """The real client, or None when no token is set (the feature is off)."""
    token = get_settings().telegram_bot_token
    if not token:
        return None
    from mnemonic.telegram_api import AiogramApi  # imported only when the feature is on

    return AiogramApi(token)


@lru_cache
def get_update_dedupe() -> UpdateDedupe:
    return UpdateDedupe()


def get_telegram_bot(
    settings: Annotated[Settings, Depends(get_settings)],
    api: Annotated[TelegramApi | None, Depends(get_telegram_api)],
    store: Annotated[Store, Depends(get_store)],
    provider: Annotated[LLMProvider, Depends(get_provider)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    global_limiter: Annotated[SlidingWindowLimiter, Depends(get_global_limiter)],
    user_limiter: Annotated[SlidingWindowLimiter, Depends(get_telegram_limiter)],
) -> TelegramBot | None:
    if api is None:
        return None
    return TelegramBot(api, store, provider, retriever, settings, global_limiter, user_limiter)


def secrets_match(path_secret: str, header_secret: str, expected: str) -> bool:
    """Both comparisons always run (no early exit), each in constant time."""
    if not expected:
        return False
    in_path = hmac.compare_digest(path_secret.encode(), expected.encode())
    in_header = hmac.compare_digest(header_secret.encode(), expected.encode())
    return in_path and in_header


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    bot: Annotated[TelegramBot | None, Depends(get_telegram_bot)],
    dedupe: Annotated[UpdateDedupe, Depends(get_update_dedupe)],
) -> dict:
    header = request.headers.get(SECRET_HEADER, "")
    if bot is None or not secrets_match(secret, header, settings.telegram_webhook_secret):
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        update = await request.json()
    except ValueError:
        return {"ok": True}  # not JSON: nothing to do, and a retry would not help
    update_id = update.get("update_id") if isinstance(update, dict) else None
    if isinstance(update_id, int) and dedupe.is_duplicate(update_id):
        return {"ok": True}  # Telegram resent an update we are already answering
    background.add_task(run_update, bot, update)
    return {"ok": True}
