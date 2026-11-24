"""The Telegram client: a second front end for the same backend (docs/decisions/0007).

Everything here is plain Python over a tiny `TelegramApi` interface, so it is tested with a fake
and never touches the network. The real `TelegramApi` (aiogram's Bot) lives in telegram_api.py.

What it does NOT do: it has no RAG of its own. A question goes through `answering.start_answer`
and `/cards` through `answering.make_flashcards`, the same functions `POST /chat` and
`POST /flashcards` call, so retrieval, citations, the "I don't know" gate, the service-wide LLM
budget, `llm_calls` and events behave exactly as on the web.

Privacy rule: the text of a question is never logged and never put in an event.
"""

import asyncio
import contextlib
import html
import logging
import math
import re
import secrets
import traceback
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from mnemonic import events as metrics
from mnemonic.answering import NON_ENGLISH, collect_answer, make_flashcards, start_answer
from mnemonic.auth import hash_password
from mnemonic.config import Settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm import errors as llm_errors
from mnemonic.llm.base import LLMProvider
from mnemonic.retrieval import Retriever
from mnemonic.schemas import ChatRequest
from mnemonic.store import Store, User

logger = logging.getLogger(__name__)

MAX_MESSAGE = 4096  # Telegram's limit for one message (after entity parsing)
MAX_QUESTION = 2000  # the same limit as the web (ChatRequest.message)
MAX_CARDS = 5
TYPING_EVERY_SECONDS = 4.0  # the "typing…" status fades after ~5 s
WEBHOOK_TIMEOUT_SECONDS = 15.0

# The same three questions as the web onboarding (frontend i18n `chat.suggestions`): the knowledge
# base and the embedder are English, so the examples are English in every language.
EXAMPLES = (
    "How do I enable CORS in FastAPI?",
    "How do I define a request body with a Pydantic model?",
    "How do I run a background task after returning a response?",
)
EXAMPLE_PREFIX = "ex:"

WELCOME = (
    "Hi! I'm Mnemonic, a study assistant: ask a question and I answer from the knowledge base "
    "(the FastAPI docs) with sources, or honestly say I don't know.\n"
    "After an answer, send /cards to get flashcards. Tap an example to start:"
)
HELP = (
    "Send a question as plain text. I answer with sources, or say it's not in the materials.\n"
    "/cards: flashcards for my last answer\n"
    "/new: start a fresh chat (I forget this conversation)\n"
    "/help: this message"
)
NEW_CHAT = "Started a new chat. Ask your first question."
NO_CARDS = "Ask a question first. Then /cards turns my sourced answer into flashcards."
NO_CARDS_REFUSED = "My last answer had no sources, so there is nothing to make cards from."
TEXT_ONLY = "I only understand text questions for now. Please type your question."
# Same wording style as the web failure table (docs/labs/lab-34-failures.md).
TOO_LONG = f"That is too long. Questions can have up to {MAX_QUESTION} characters."
INVALID = "I could not read that. Please send your question as plain text."
BUSY = "The service is busy right now. Try again in a minute."
ERR_MODEL = "The model couldn't finish the answer. Please try again."
ERR_CARDS = "The model couldn't make flashcards. Please try again."
ERR_GENERIC = "Something went wrong. Please try again."
NON_ENGLISH_HINT = "Ask in English: the knowledge base is in English."


@dataclass(frozen=True)
class Button:
    text: str
    data: str  # callback_data, at most 64 bytes


class TelegramApi(Protocol):
    """The four calls the bot needs from Telegram, and nothing else."""

    async def send_message(
        self, chat_id: int, html_text: str, buttons: Sequence[Button] = ()
    ) -> None: ...

    async def send_typing(self, chat_id: int) -> None: ...

    async def answer_callback(self, callback_id: str) -> None: ...

    async def set_webhook(self, url: str, secret: str) -> None: ...

    async def close(self) -> None: ...


# ---------- incoming updates ----------


@dataclass(frozen=True)
class Incoming:
    """The part of a Telegram update the bot looks at."""

    telegram_id: int
    chat_id: int
    text: str | None = None  # None: not a text message (photo, sticker, voice, ...)
    callback_id: str | None = None
    callback_data: str | None = None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _private_chat(message: object, sender_id: int) -> int | None:
    """The chat id of a one-to-one chat with `sender_id`, else None. Groups are ignored on
    purpose: one shared chat must not become one person's account."""
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return None
    chat_id = _int(chat.get("id"))
    return chat_id if chat_id == sender_id else None


def parse_update(raw: object) -> Incoming | None:
    """A message or a button press from a person in a private chat; anything else is None."""
    if not isinstance(raw, dict):
        return None
    callback = raw.get("callback_query")
    if isinstance(callback, dict):
        sender = callback.get("from")
        sender_id = _int(sender.get("id")) if isinstance(sender, dict) else None
        callback_id = callback.get("id")
        data = callback.get("data")
        if sender_id is None or sender.get("is_bot") or not isinstance(callback_id, str):
            return None
        chat_id = _private_chat(callback.get("message"), sender_id)
        if chat_id is None or not isinstance(data, str):
            return None
        return Incoming(sender_id, chat_id, callback_id=callback_id, callback_data=data)
    message = raw.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from")
    sender_id = _int(sender.get("id")) if isinstance(sender, dict) else None
    if sender_id is None or sender.get("is_bot"):
        return None
    chat_id = _private_chat(message, sender_id)
    if chat_id is None:
        return None
    text = message.get("text")
    return Incoming(sender_id, chat_id, text=text if isinstance(text, str) else None)


class UpdateDedupe:
    """Remembers the last `size` update ids. Telegram resends an update until it gets a 200, so
    one slow answer must not be answered (and paid for) twice. In memory: one process, and the
    memory is lost on restart, which at worst repeats one answer."""

    def __init__(self, size: int = 1000) -> None:
        self._size = size
        self._seen: OrderedDict[int, None] = OrderedDict()

    def is_duplicate(self, update_id: int) -> bool:
        if update_id in self._seen:
            self._seen.move_to_end(update_id)
            return True
        self._seen[update_id] = None
        while len(self._seen) > self._size:
            self._seen.popitem(last=False)
        return False


# ---------- rendering (parse_mode=HTML) ----------


def esc(text: str) -> str:
    """Telegram's HTML mode needs only these three escaped. ALWAYS applied to model output and to
    anything that came from a user or a document: an unescaped `<` is a rejected message at best."""
    return html.escape(text, quote=False)


def _escaped_len(text: str) -> int:
    return len(esc(text))


def _hard_split(line: str, limit: int) -> list[str]:
    """Cut a single over-long line into pieces by characters (never inside an HTML entity: the
    escaping happens after the cut, we only measure the escaped length)."""
    out: list[str] = []
    current, size = [], 0
    for ch in line:
        width = _escaped_len(ch)
        if size + width > limit:
            out.append("".join(current))
            current, size = [], 0
        current.append(ch)
        size += width
    if current:
        out.append("".join(current))
    return out


def _fit_paragraph(paragraph: str, limit: int) -> list[str]:
    if _escaped_len(paragraph) <= limit:
        return [paragraph]
    out: list[str] = []
    current = ""
    for line in paragraph.split("\n"):
        for part in [line] if _escaped_len(line) <= limit else _hard_split(line, limit):
            candidate = f"{current}\n{part}" if current else part
            if _escaped_len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    out.append(current)
                current = part
    if current:
        out.append(current)
    return out


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Cut RAW text into pieces whose escaped length is at most `limit`. Prefers a paragraph
    boundary (blank line), then a line, then, only for a monster line, a character."""
    pieces: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        for part in _fit_paragraph(paragraph, limit):
            candidate = f"{current}\n\n{part}" if current else part
            if _escaped_len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = part
    if current:
        pieces.append(current)
    return pieces or [""]


_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")
_CODE = re.compile(r"`([^`\n]+)`")


def to_html(piece: str) -> str:
    """Escape a piece of the model's markdown and keep the two things that matter in an answer:
    `code` and **bold**. Everything else stays literal text. If the tags would push the message
    over the limit, the plain escaped text is sent instead."""
    escaped = esc(piece)
    parts = _CODE.split(escaped)  # [text, code, text, code, ...]; code spans get no bold inside
    out = []
    for i, part in enumerate(parts):
        out.append(f"<code>{part}</code>" if i % 2 else _BOLD.sub(r"<b>\1</b>", part))
    formatted = "".join(out)
    return formatted if len(formatted) <= MAX_MESSAGE else escaped


_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def renumber_citations(text: str, sources: Sequence[dict]) -> str:
    """The model cites chunk ids ([42]); the reader should see 1, 2, 3 matching the Sources list.
    Same rule as the web app: an id that is not among the sources is dropped from the brackets."""
    if not sources:
        return text
    position = {s.get("id"): i + 1 for i, s in enumerate(sources)}

    def swap(match: re.Match) -> str:
        numbers = [
            position[n] for n in (int(x) for x in match.group(1).split(",")) if n in position
        ]
        return f"[{', '.join(map(str, numbers))}]" if numbers else match.group(0)

    return _CITATION.sub(swap, text)


def sources_block(sources: Sequence[dict]) -> str:
    lines = []
    for i, s in enumerate(sources, 1):
        heading, path = str(s.get("heading") or ""), str(s.get("file_path") or "")
        label = f"{heading} — {path}" if heading and path else heading or path
        lines.append(f"[{i}] {esc(label)}")
    return "<b>Sources</b>\n" + "\n".join(lines)


def render_answer(text: str, sources: Sequence[dict]) -> list[str]:
    """The answer as HTML messages: renumbered citations, then a "Sources" list when the answer
    has any. A refusal has no sources and is sent as the server wrote it."""
    pieces = split_message(renumber_citations(text.strip(), sources))
    messages = [to_html(p) for p in pieces]
    if sources:
        block = sources_block(sources)
        if len(messages[-1]) + 2 + len(block) <= MAX_MESSAGE:
            messages[-1] += "\n\n" + block
        else:
            messages.append(block)
    return messages


def render_cards(cards: Sequence) -> list[str]:
    """Up to MAX_CARDS cards as "Q / A" pairs, grouped into messages under the limit."""
    blocks = [
        f"<b>{i}. Q:</b> {esc(c.question)}\n<b>A:</b> {esc(c.answer)}"
        for i, c in enumerate(cards[:MAX_CARDS], 1)
    ]
    messages: list[str] = []
    for block in blocks:
        if messages and len(messages[-1]) + 2 + len(block) <= MAX_MESSAGE:
            messages[-1] += "\n\n" + block
        else:
            messages.append(block[:MAX_MESSAGE])
    return messages


def friendly_error(error: HTTPException, *, cards: bool = False) -> str:
    """One calm sentence per failure, in the web's wording style. Never echoes user input."""
    if error.status_code == 429:
        return BUSY
    if error.status_code == 422:
        return NO_CARDS_REFUSED
    if error.status_code in (502, 503):
        # The server's sentence names the cause (quota, overload, invalid output); it is a fixed
        # text, never user input. The unclassified one is replaced by the generic wording.
        return model_error(str(error.detail), cards=cards)
    return ERR_GENERIC


def model_error(server_message: str, *, cards: bool = False) -> str:
    """A specific sentence for a classified failure, the generic one for "other"."""
    known = {m for k, m in llm_errors.MESSAGES.items() if k != llm_errors.OTHER}
    if server_message in known:
        return server_message
    return ERR_CARDS if cards else ERR_MODEL


def log_failure(error: BaseException) -> None:
    """Log what failed and where, not what it said: exception messages can carry user text."""
    frames = "".join(traceback.format_tb(error.__traceback__))
    logger.error("telegram update failed: %s\n%s", type(error).__name__, frames)


def command_of(text: str) -> str | None:
    """ "/cards@MnemonicBot extra" -> "cards"; plain text -> None."""
    if not text.startswith("/"):
        return None
    return text.split(maxsplit=1)[0][1:].split("@")[0].lower()


# ---------- the bot ----------


class TelegramBot:
    def __init__(
        self,
        api: TelegramApi,
        store: Store,
        provider: LLMProvider,
        retriever: Retriever,
        settings: Settings,
        global_limiter: SlidingWindowLimiter,
        user_limiter: SlidingWindowLimiter,
    ) -> None:
        self.api = api
        self.store = store
        self.provider = provider
        self.retriever = retriever
        self.settings = settings
        self.global_limiter = global_limiter
        self.user_limiter = user_limiter

    async def handle_update(self, raw: object) -> None:
        """Never raises: a failure is logged and the person gets one calm sentence."""
        incoming = parse_update(raw)
        if incoming is None:
            return
        try:
            await self._handle(incoming)
        except Exception as error:
            log_failure(error)
            await self._say(incoming.chat_id, ERR_GENERIC)

    async def _say(self, chat_id: int, html_text: str, buttons: Sequence[Button] = ()) -> None:
        try:
            await self.api.send_message(chat_id, html_text, buttons)
        except Exception as error:  # Telegram down, bot blocked by the user, flood control, ...
            log_failure(error)

    async def _handle(self, inc: Incoming) -> None:
        if inc.callback_id:
            with contextlib.suppress(Exception):  # stops the button's spinner; not critical
                await self.api.answer_callback(inc.callback_id)
        user = await self._user(inc.telegram_id)
        if inc.callback_data is not None:
            question = example_question(inc.callback_data)
            if question:
                await self._ask(user, inc.chat_id, inc.telegram_id, question)
            return
        if inc.text is None:
            await self._say(inc.chat_id, TEXT_ONLY)
            return
        match command_of(inc.text):
            case None:
                await self._ask(user, inc.chat_id, inc.telegram_id, inc.text)
            case "start":
                buttons = [Button(q, f"{EXAMPLE_PREFIX}{i}") for i, q in enumerate(EXAMPLES)]
                await self._say(inc.chat_id, esc(WELCOME), buttons)
            case "new":
                await asyncio.to_thread(self.store.create_session, user.id)
                await self._say(inc.chat_id, esc(NEW_CHAT))
            case "cards":
                await self._cards(user, inc.chat_id, inc.telegram_id)
            case _:  # /help and any command we do not know
                await self._say(inc.chat_id, esc(HELP))

    async def _user(self, telegram_id: int) -> User:
        """The Mnemonic user of this Telegram id; the first message creates one (a normal account
        that cannot log in on the web: its password is a hash of a secret nobody has seen)."""
        user = await asyncio.to_thread(self.store.find_telegram_user, telegram_id)
        if user is not None:
            return user
        hashed = await asyncio.to_thread(hash_password, secrets.token_urlsafe(48))
        user, created = await asyncio.to_thread(
            self.store.get_or_create_telegram_user, telegram_id, hashed
        )
        if created:  # two first messages at once: only the one that really created emits
            await metrics.emit(self.store, metrics.SIGNUP, user.id, "telegram")
        return user

    async def _current_session(self, user: User, create: bool) -> UUID | None:
        """One chat per person: the most recently used one; /new makes a fresh one."""
        sessions, _ = await asyncio.to_thread(self.store.list_sessions, user.id, 1, 0)
        if sessions:
            return sessions[0].id
        if not create:
            return None
        return (await asyncio.to_thread(self.store.create_session, user.id)).id

    def _throttled(self, telegram_id: int) -> str | None:
        """Per-person limit (the web limits per IP, but every Telegram request comes from
        Telegram's servers, so the IP says nothing). A sentence if the person must wait."""
        wait = self.user_limiter.acquire(str(telegram_id))
        if wait is None:
            return None
        return f"You're sending messages too fast. Try again in {math.ceil(wait)} s."

    async def _typing(self, chat_id: int) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self.api.send_typing(chat_id)
            await asyncio.sleep(TYPING_EVERY_SECONDS)

    @contextlib.asynccontextmanager
    async def _typing_while(self, chat_id: int):
        task = asyncio.create_task(self._typing(chat_id))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _ask(self, user: User, chat_id: int, telegram_id: int, text: str) -> None:
        try:  # the web's own rules: 1-2000 characters, no NUL, valid Unicode
            ChatRequest(session_id=uuid4(), message=text)
        except ValidationError:  # its message contains the input: never log or echo it
            await self._say(chat_id, esc(TOO_LONG if len(text) > MAX_QUESTION else INVALID))
            return
        if (slow := self._throttled(telegram_id)) is not None:
            await self._say(chat_id, esc(slow))
            return
        session_id = await self._current_session(user, create=True)
        async with self._typing_while(chat_id):
            try:
                stream = await start_answer(
                    provider=self.provider,
                    settings=self.settings,
                    retriever=self.retriever,
                    store=self.store,
                    global_limiter=self.global_limiter,
                    user_id=user.id,
                    session_id=session_id,
                    message=text,
                    channel="telegram",
                )
                answer = await collect_answer(stream)
            except HTTPException as error:
                await self._say(chat_id, esc(friendly_error(error)))
                return
        if answer.refusal_reason == NON_ENGLISH:
            await self._say(chat_id, esc(NON_ENGLISH_HINT))
            return
        if answer.error or not answer.text.strip():
            await self._say(chat_id, esc(model_error(answer.error or "")))
            return
        for message in render_answer(answer.text, answer.sources):
            await self._say(chat_id, message)

    async def _cards(self, user: User, chat_id: int, telegram_id: int) -> None:
        session_id = await self._current_session(user, create=False)
        stored = (
            await asyncio.to_thread(self.store.get_messages, user.id, session_id)
            if session_id
            else None
        )
        last = next((m for m in reversed(stored or []) if m.role == "assistant"), None)
        if last is None:
            await self._say(chat_id, esc(NO_CARDS))
            return
        if not last.sources:  # the last answer was a refusal: nothing to learn from
            await self._say(chat_id, esc(NO_CARDS_REFUSED))
            return
        if (slow := self._throttled(telegram_id)) is not None:
            await self._say(chat_id, esc(slow))
            return
        async with self._typing_while(chat_id):
            try:
                cards = await make_flashcards(
                    provider=self.provider,
                    settings=self.settings,
                    store=self.store,
                    global_limiter=self.global_limiter,
                    user_id=user.id,
                    session_id=session_id,
                    message_id=last.id,
                    channel="telegram",
                )
            except HTTPException as error:
                await self._say(chat_id, esc(friendly_error(error, cards=True)))
                return
        for message in render_cards(cards.cards):
            await self._say(chat_id, message)


def example_question(callback_data: str) -> str | None:
    """The example behind an "ex:N" button, or None for anything else (data comes from the client:
    never trusted beyond an index into our own fixed list)."""
    if not callback_data.startswith(EXAMPLE_PREFIX):
        return None
    index = callback_data[len(EXAMPLE_PREFIX) :]
    if not index.isdigit() or int(index) >= len(EXAMPLES):
        return None
    return EXAMPLES[int(index)]


async def run_update(bot: TelegramBot, raw: object) -> None:
    """The background task behind the webhook: an exception here must never reach the server."""
    try:
        await bot.handle_update(raw)
    except Exception as error:
        log_failure(error)


async def register_webhook(settings: Settings, api: TelegramApi) -> None:
    """Tell Telegram where to send updates. Best effort: a failure is logged, the app runs on
    (the webhook can be set again by restarting). Neither the token nor the URL (it contains the
    secret) is ever logged."""
    if not (settings.public_url and settings.telegram_webhook_secret):
        logger.warning("Telegram bot: PUBLIC_URL or TELEGRAM_WEBHOOK_SECRET is not set; no webhook")
        return
    url = f"{settings.public_url.rstrip('/')}/telegram/webhook/{settings.telegram_webhook_secret}"
    try:
        await asyncio.wait_for(
            api.set_webhook(url, settings.telegram_webhook_secret), WEBHOOK_TIMEOUT_SECONDS
        )
        logger.info("Telegram webhook registered")
    except Exception as error:
        logger.error("Telegram webhook registration failed: %s", type(error).__name__)
