"""The real Telegram API client: aiogram's `Bot`, behind the small `TelegramApi` interface.

This is the only module that imports aiogram, and it is imported only when a bot token is set, so
the app (and every test) runs without the library being exercised. We use aiogram for what it is
good at: typed Bot API calls, one pooled HTTP session, and flood-control errors as exceptions. We
do NOT use its Dispatcher/FSM: conversation state lives in Postgres, and the webhook route
parses the update itself.
"""

from collections.abc import Sequence

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from mnemonic.telegram_bot import Button

# Only these update types are delivered: less traffic, less to defend.
ALLOWED_UPDATES = ["message", "callback_query"]


class AiogramApi:
    def __init__(self, token: str) -> None:
        # HTML is the default for every message; the bot always escapes what it sends.
        self._bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    async def send_message(
        self, chat_id: int, html_text: str, buttons: Sequence[Button] = ()
    ) -> None:
        markup = (
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=b.text, callback_data=b.data)] for b in buttons
                ]
            )
            if buttons
            else None
        )
        await self._bot.send_message(chat_id, html_text, reply_markup=markup)

    async def send_typing(self, chat_id: int) -> None:
        await self._bot.send_chat_action(chat_id, ChatAction.TYPING)

    async def answer_callback(self, callback_id: str) -> None:
        await self._bot.answer_callback_query(callback_id)

    async def set_webhook(self, url: str, secret: str) -> None:
        await self._bot.set_webhook(url, secret_token=secret, allowed_updates=ALLOWED_UPDATES)

    async def close(self) -> None:
        await self._bot.session.close()
