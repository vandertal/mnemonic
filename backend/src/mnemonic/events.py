"""Product events: what happened, never what was said.

`emit` is the only way the app writes an event. It never raises: a broken metrics table must not
break signup, chat or search. Props are a small fixed set of booleans plus the `channel` word of
a non-web client; question text, emails and document names must never be put in them.
"""

import asyncio
import logging
from typing import Literal
from uuid import UUID

from mnemonic.store import Store

logger = logging.getLogger(__name__)

SIGNUP = "signup"
QUESTION_ANSWERED = "question_answered"  # THE main-action metric
CARDS_MADE = "cards_made"
SEARCH = "search"

EVENT_NAMES = (SIGNUP, QUESTION_ANSWERED, CARDS_MADE, SEARCH)


async def emit(
    store: Store,
    name: str,
    user_id: UUID | None,
    channel: Literal["telegram"] | None = None,
    **props: bool,
) -> None:
    """`channel` is set by the non-web clients only; an event without it counts as "web"."""
    if channel:
        props = {**props, "channel": channel}  # a fixed word, never user text
    try:
        await asyncio.to_thread(store.log_event, name, user_id, props)
    except Exception:
        logger.exception("could not write the %r event", name)
