"""The Telegram client: webhook security, dedupe, identity, commands, rendering, failures.

Nothing here calls Telegram: the bot talks to a `FakeApi` that records what it was asked to send.
"""

import asyncio
import html
import json
import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mnemonic import routes_telegram
from mnemonic.auth import verify_password
from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm import errors as llm_errors
from mnemonic.llm import retry
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.rag import REFUSAL
from mnemonic.routes_telegram import get_telegram_api, get_update_dedupe
from mnemonic.security import get_telegram_limiter
from mnemonic.store import Chunk
from mnemonic.telegram_bot import (
    BUSY,
    ERR_CARDS,
    ERR_GENERIC,
    ERR_MODEL,
    EXAMPLES,
    INVALID,
    MAX_MESSAGE,
    NEW_CHAT,
    NO_CARDS,
    NO_CARDS_REFUSED,
    NON_ENGLISH_HINT,
    TEXT_ONLY,
    TOO_LONG,
    Button,
    TelegramBot,
    UpdateDedupe,
    command_of,
    esc,
    parse_update,
    register_webhook,
    render_cards,
    renumber_citations,
    run_update,
    split_message,
    to_html,
)

from .fakes import FakeRetriever, MemoryStore, RecordingProvider, make_hit

SECRET = "s3cret-" + "x" * 30
TOKEN = "123456:TEST-TOKEN-never-logged"
ALICE = 1001  # a telegram id
BOB = 1002
UPDATE_IDS = iter(range(1, 10**9))


class FakeApi:
    """Records every call; `fail_send` makes Telegram "refuse" messages (bot blocked, flood...)."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str, list[Button]]] = []
        self.typing: list[int] = []
        self.callbacks: list[str] = []
        self.webhooks: list[tuple[str, str]] = []
        self.closed = False
        self.fail_send = False
        self.fail_webhook = False

    async def send_message(self, chat_id, html_text, buttons=()):
        if self.fail_send:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, html_text, list(buttons)))

    async def send_typing(self, chat_id):
        self.typing.append(chat_id)

    async def answer_callback(self, callback_id):
        self.callbacks.append(callback_id)

    async def set_webhook(self, url, secret):
        if self.fail_webhook:
            raise RuntimeError(f"cannot reach telegram with {TOKEN}")
        self.webhooks.append((url, secret))

    async def close(self):
        self.closed = True

    @property
    def texts(self) -> list[str]:
        return [t for _, t, _ in self.sent]


def message(text: str | None = "hello", user: int = ALICE, chat_type: str = "private", **extra):
    msg = {"message_id": 1, "from": {"id": user, "is_bot": False}, "chat": {"id": user}}
    msg["chat"]["type"] = chat_type
    if text is not None:
        msg["text"] = text
    msg.update(extra)
    return {"update_id": next(UPDATE_IDS), "message": msg}


def press(data: str, user: int = ALICE) -> dict:
    return {
        "update_id": next(UPDATE_IDS),
        "callback_query": {
            "id": "cb-1",
            "from": {"id": user, "is_bot": False},
            "message": {"message_id": 5, "chat": {"id": user, "type": "private"}},
            "data": data,
        },
    }


@pytest.fixture
def store():
    s = MemoryStore()
    s.chunks[1] = Chunk(1, "tutorial/cors.md", "CORS", "Use CORSMiddleware.")
    return s


@pytest.fixture
def api():
    return FakeApi()


def make_bot(store, api, *, answer="Use CORSMiddleware [1].", hits=None, provider=None, **limits):
    retriever = FakeRetriever([make_hit(1)] if hits is None else hits)
    provider = provider or RecordingProvider(answer)
    bot = TelegramBot(
        api,
        store,
        provider,
        retriever,
        Settings(_env_file=None, similarity_threshold=0.5),
        limits.get("global_limiter") or SlidingWindowLimiter(1000),
        limits.get("user_limiter") or SlidingWindowLimiter(1000),
    )
    bot.retriever_fake, bot.provider_fake = retriever, provider  # for assertions
    return bot


def user_of(store: MemoryStore, telegram_id: int = ALICE):
    return store.find_telegram_user(telegram_id)


def event_names(store, channel="telegram") -> list[str]:
    return [n for n, _, p, _ in store.events if p.get("channel") == channel]


# ---------- parsing ----------


def test_parse_update_reads_a_private_text_message():
    inc = parse_update(message("hi"))
    assert (inc.telegram_id, inc.chat_id, inc.text) == (ALICE, ALICE, "hi")


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        {"update_id": 1, "edited_message": {}},
        message("hi", chat_type="group"),  # groups are ignored
        message("hi", chat_type="supergroup"),
        {
            "message": {
                "from": {"id": ALICE, "is_bot": True},
                "chat": {"id": ALICE, "type": "private"},
            }
        },
        {"message": {"from": {"id": True}, "chat": {"id": 1, "type": "private"}}},
        {"message": {"from": {"id": ALICE}, "chat": {"id": BOB, "type": "private"}}},  # mismatch
    ],
)
def test_parse_update_ignores_everything_else(raw):
    assert parse_update(raw) is None


def test_a_photo_is_a_message_without_text():
    inc = parse_update(message(None, photo=[{"file_id": "x"}]))
    assert inc is not None and inc.text is None


def test_command_of():
    assert command_of("/cards") == "cards"
    assert command_of("/Cards@MnemonicBot please") == "cards"
    assert command_of("how do I /cards") is None


# ---------- webhook security ----------


@pytest.fixture
def hook(store, api):
    """A TestClient wired to the fake store and fake Telegram API, with the feature on."""
    settings = Settings(
        _env_file=None,
        telegram_bot_token=TOKEN,
        telegram_webhook_secret=SECRET,
        similarity_threshold=0.5,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_telegram_api] = lambda: api
    app.dependency_overrides[get_provider] = lambda: RecordingProvider("Use CORSMiddleware [1].")
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([make_hit(1)])
    app.dependency_overrides[get_telegram_limiter] = lambda: SlidingWindowLimiter(1000)
    dedupe = UpdateDedupe()
    app.dependency_overrides[get_update_dedupe] = lambda: dedupe
    with TestClient(app) as client:
        yield client


def post(client, update, secret=SECRET, header=SECRET):
    headers = {} if header is None else {"X-Telegram-Bot-Api-Secret-Token": header}
    return client.post(f"/telegram/webhook/{secret}", json=update, headers=headers)


def test_the_webhook_answers_200_and_the_bot_replies(hook, api):
    r = post(hook, message("How do I enable CORS?"))
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert any("CORSMiddleware" in t for t in api.texts)  # the background task ran


@pytest.mark.parametrize(
    ("secret", "header"),
    [
        ("wrong", SECRET),  # bad path secret
        (SECRET, "wrong"),  # bad header
        (SECRET, None),  # header missing
        ("wrong", None),
        (SECRET, SECRET + "x"),
        (SECRET[:-1], SECRET),
    ],
)
def test_a_wrong_secret_in_the_path_or_the_header_is_a_404(hook, api, secret, header):
    r = post(hook, message("hi"), secret=secret, header=header)
    assert r.status_code == 404
    assert api.sent == []  # nothing was processed


def test_both_secrets_are_compared_with_compare_digest_without_short_circuit(hook, monkeypatch):
    calls = []
    real = routes_telegram.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(routes_telegram.hmac, "compare_digest", spy)
    assert post(hook, message("hi"), secret="wrong", header="wrong").status_code == 404
    assert len(calls) == 2  # the header is compared even though the path already failed


def test_without_a_token_the_route_does_not_exist(store):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        assert post(client, message("hi")).status_code == 404


def test_the_secret_must_be_configured(store, api):
    settings = Settings(_env_file=None, telegram_bot_token=TOKEN)  # token but no secret
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_telegram_api] = lambda: api
    with TestClient(app) as client:
        assert post(client, message("hi"), secret="", header="").status_code in (404, 405)
        assert post(client, message("hi"), secret="x", header="x").status_code == 404


def test_the_webhook_is_not_in_the_public_docs(hook):
    assert "/telegram" not in json.dumps(hook.get("/openapi.json").json())


def test_a_body_that_is_not_json_is_ignored_with_200(hook, api):
    r = hook.post(
        f"/telegram/webhook/{SECRET}",
        content=b"not json",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert r.status_code == 200
    assert api.sent == []


# ---------- dedupe ----------


def test_the_same_update_id_is_answered_once(hook, api):
    update = message("How do I enable CORS?")
    assert post(hook, update).status_code == 200
    assert post(hook, update).status_code == 200  # Telegram retried
    assert sum("CORSMiddleware" in t for t in api.texts) == 1


def test_dedupe_remembers_a_bounded_number_of_ids():
    d = UpdateDedupe(size=3)
    assert [d.is_duplicate(i) for i in (1, 2, 3)] == [False, False, False]
    assert d.is_duplicate(2) is True
    assert d.is_duplicate(4) is False  # evicts the oldest: 1 (2 was just refreshed)
    assert d.is_duplicate(1) is False  # 1 was forgotten, so it counts as new again (evicts 3)
    assert d.is_duplicate(2) is True  # the refreshed one survived
    assert d.is_duplicate(3) is False  # 3 was forgotten
    assert len(d._seen) == 3


def test_a_default_dedupe_keeps_about_a_thousand():
    d = UpdateDedupe()
    for i in range(1500):
        d.is_duplicate(i)
    assert len(d._seen) == 1000


# ---------- background safety ----------


def test_a_crash_in_the_background_task_does_not_crash_the_app(hook, store, api, caplog):
    question = "my secret " + "question"  # built at runtime: a traceback prints source lines

    def boom(*a, **k):
        raise RuntimeError("database is gone: " + question)

    store.find_telegram_user = boom
    with caplog.at_level(logging.ERROR):
        r = post(hook, message("my secret question"))
    assert r.status_code == 200
    assert api.texts == [esc(ERR_GENERIC)]  # one calm sentence for the person
    assert "my secret question" not in caplog.text  # the exception message is not logged
    assert "RuntimeError" in caplog.text  # but its type is
    assert hook.get("/health").status_code == 200  # the app is fine


def test_run_update_never_raises(store, api):
    class Broken:
        async def handle_update(self, raw):
            raise ValueError("x")

    asyncio.run(run_update(Broken(), {}))


def test_a_failing_send_is_swallowed(store, api):
    api.fail_send = True
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("How do I enable CORS?")))  # no exception


# ---------- identity ----------


def test_first_message_creates_a_normal_user_that_cannot_log_in(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("How do I enable CORS?")))
    user = user_of(store)
    assert user.email == f"tg-{ALICE}@telegram.invalid"
    _, stored_hash = store.get_user_by_email(user.email)
    assert stored_hash.startswith("$argon2")  # a real hash: a login attempt fails cleanly
    assert verify_password("anything", stored_hash) is False
    assert event_names(store).count("signup") == 1
    assert ("signup", user.id, {"channel": "telegram"}) in [
        (n, u, p) for n, u, p, _ in store.events
    ]


def test_logging_in_on_the_web_as_a_telegram_user_is_a_plain_401(store, api):
    asyncio.run(make_bot(store, api).handle_update(message("hi")))
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        r = client.post(
            "/auth/login",
            data={"username": f"tg-{ALICE}@telegram.invalid", "password": "guess"},
        )
    assert r.status_code == 401


def test_the_second_message_reuses_the_user_and_does_not_sign_up_again(store, api):
    bot = make_bot(store, api)
    for _ in range(3):
        asyncio.run(bot.handle_update(message("How do I enable CORS?")))
    assert len(store.telegram) == 1
    assert event_names(store).count("signup") == 1


def test_many_first_messages_at_once_make_one_user(store, api):
    bot = make_bot(store, api)

    async def burst():
        await asyncio.gather(*(bot.handle_update(message("/help")) for _ in range(8)))

    asyncio.run(burst())
    assert len(store.telegram) == 1
    assert len(store.users) == 1
    assert event_names(store).count("signup") == 1


def test_two_people_get_two_users(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("/help", user=ALICE)))
    asyncio.run(bot.handle_update(message("/help", user=BOB)))
    assert user_of(store, ALICE).id != user_of(store, BOB).id


def test_deleting_the_user_removes_the_telegram_link(store, api):
    asyncio.run(make_bot(store, api).handle_update(message("/help")))
    store.delete_user(user_of(store).id)
    assert store.find_telegram_user(ALICE) is None


# ---------- /start, /help, buttons ----------


def test_start_sends_a_two_line_welcome_and_the_three_web_examples_as_buttons(store, api):
    asyncio.run(make_bot(store, api).handle_update(message("/start")))
    chat, text, buttons = api.sent[0]
    assert chat == ALICE
    assert len(text.splitlines()) == 2
    assert [b.text for b in buttons] == list(EXAMPLES)
    assert [b.data for b in buttons] == ["ex:0", "ex:1", "ex:2"]
    assert all(len(b.data.encode()) <= 64 for b in buttons)


def test_examples_are_the_same_as_the_web_onboarding():
    en = json.loads(
        (__import__("pathlib").Path(__file__).parents[2] / "frontend/src/i18n/en.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(EXAMPLES) == en["chat"]["suggestions"]


def test_help_and_unknown_commands_show_the_help(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("/help")))
    asyncio.run(bot.handle_update(message("/frobnicate")))
    assert "/cards" in api.texts[0] and "/new" in api.texts[0]
    assert api.texts[0] == api.texts[1]
    assert bot.provider_fake.calls == []  # commands cost no LLM call


def test_pressing_an_example_button_asks_that_question(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(press("ex:1")))
    assert api.callbacks == ["cb-1"]  # the button's spinner is stopped
    assert bot.retriever_fake.questions == [EXAMPLES[1]]
    assert any("CORSMiddleware" in t for t in api.texts)


@pytest.mark.parametrize("data", ["ex:9", "ex:-1", "ex:x", "other", "", "ex:" + "9" * 50])
def test_a_forged_button_payload_is_ignored(store, api, data):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(press(data)))
    assert bot.retriever_fake.questions == []
    assert api.sent == []


# ---------- questions ----------


def test_a_question_gets_an_answer_with_renumbered_citations_and_a_sources_list(store, api):
    bot = make_bot(store, api, answer="Use it [7].", hits=[make_hit(7)])
    asyncio.run(bot.handle_update(message("How do I enable CORS?")))
    (text,) = api.texts
    assert text.startswith("Use it [1].")  # chunk id 7 is shown as [1], like the web
    assert "<b>Sources</b>\n[1] Heading 7 — tutorial/page-7.md" in text
    assert api.typing  # the "typing…" status was shown while waiting


def test_the_question_reaches_the_shared_rag_with_the_telegram_users_id(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("How do I enable CORS?")))
    assert bot.retriever_fake.questions == ["How do I enable CORS?"]
    assert bot.retriever_fake.owners == [user_of(store).id]


def test_a_refusal_is_sent_as_is_without_sources(store, api):
    bot = make_bot(store, api, hits=[make_hit(1, similarity=0.1)])
    asyncio.run(bot.handle_update(message("What is the weather?")))
    assert api.texts == [esc(REFUSAL)]
    assert bot.provider_fake.calls == []  # no LLM call for "I don't know"


def test_the_bot_keeps_one_chat_and_the_model_sees_the_earlier_turns(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("first question")))
    asyncio.run(bot.handle_update(message("second question")))
    sessions, total = store.list_sessions(user_of(store).id, 10, 0)
    assert total == 1
    second_call = bot.provider_fake.calls[1]
    assert "first question" in [m.content for m in second_call]


def test_new_starts_a_fresh_chat_with_no_memory(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("first question")))
    asyncio.run(bot.handle_update(message("/new")))
    assert api.texts[-1] == esc(NEW_CHAT)
    asyncio.run(bot.handle_update(message("second question")))
    _, total = store.list_sessions(user_of(store).id, 10, 0)
    assert total == 2
    assert "first question" not in [m.content for m in bot.provider_fake.calls[1]]


def test_non_text_messages_get_a_short_text_only_reply(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message(None, photo=[{"file_id": "x"}])))
    assert api.texts == [esc(TEXT_ONLY)]
    assert bot.retriever_fake.questions == []


def test_group_chats_and_bots_are_ignored(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("hi", chat_type="group")))
    assert api.sent == [] and store.users == {}


def test_an_over_long_question_is_a_readable_message_and_is_not_echoed(store, api):
    bot = make_bot(store, api)
    long_text = "secret " * 400  # 2800 characters
    asyncio.run(bot.handle_update(message(long_text)))
    assert api.texts == [esc(TOO_LONG)]
    assert "2000" in api.texts[0]
    assert bot.retriever_fake.questions == []
    assert "secret" not in api.texts[0]


def test_exactly_2000_characters_is_accepted(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("a" * 2000)))
    assert len(bot.retriever_fake.questions) == 1


def test_text_postgres_cannot_store_is_a_readable_message(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("bad \x00 text")))
    assert api.texts == [esc(INVALID)]
    assert bot.retriever_fake.questions == []


# ---------- rendering ----------


def test_model_output_is_always_html_escaped(store, api):
    nasty = "<script>alert(1)</script> & <b>x</b> **bold** and `a<b`"
    bot = make_bot(store, api, answer=nasty + " [1]")
    asyncio.run(bot.handle_update(message("q")))
    (text,) = api.texts
    assert "<script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;b&gt;x&lt;/b&gt;" in text
    assert "<b>bold</b>" in text  # only OUR formatting tags survive
    assert "<code>a&lt;b</code>" in text


def test_source_names_are_escaped_too(store, api):
    hit = make_hit(1)
    hit = type(hit)(id=1, similarity=0.9, file_path="a<b>.md", heading="H & <i>", content="c")
    bot = make_bot(store, api, hits=[hit])
    asyncio.run(bot.handle_update(message("q")))
    assert "H &amp; &lt;i&gt; — a&lt;b&gt;.md" in api.texts[0]


def test_bold_is_not_applied_inside_code():
    assert to_html("`**x**`") == "<code>**x**</code>"
    assert to_html("**a** `b`") == "<b>a</b> <code>b</code>"


def test_formatting_that_would_overflow_falls_back_to_plain_text():
    text = "`x` " * 1200  # 4800 chars raw, much more with tags
    pieces = split_message(text)
    for piece in pieces:
        assert len(to_html(piece)) <= MAX_MESSAGE


def test_short_text_is_one_piece():
    assert split_message("hello\n\nworld") == ["hello\n\nworld"]


def test_a_long_text_is_split_on_paragraph_boundaries():
    paragraphs = [f"{i}" * 1500 for i in range(1, 6)]  # 1500 chars each
    pieces = split_message("\n\n".join(paragraphs))
    assert len(pieces) == 3  # 2 + 2 + 1 paragraphs: never a paragraph cut in half
    assert pieces[0] == "\n\n".join(paragraphs[:2])
    assert all(len(esc(p)) <= MAX_MESSAGE for p in pieces)


def test_pieces_count_the_escaped_length_and_never_cut_an_entity():
    text = "&" * 5000  # each & becomes "&amp;" (5 characters)
    pieces = split_message(text)
    assert all(len(esc(p)) <= MAX_MESSAGE for p in pieces)
    assert "".join(pieces) == text  # nothing lost, nothing duplicated
    assert all(html.unescape(esc(p)) == p for p in pieces)


def test_an_over_long_line_without_blank_lines_is_still_split():
    text = "word " * 2000
    pieces = split_message(text)
    assert len(pieces) >= 3 and all(len(esc(p)) <= MAX_MESSAGE for p in pieces)


def test_a_long_answer_is_sent_as_several_messages_with_sources_at_the_end(store, api):
    answer = "\n\n".join(f"Paragraph {i}: " + "x" * 1800 + " [1]" for i in range(4))
    bot = make_bot(store, api, answer=answer)
    asyncio.run(bot.handle_update(message("q")))
    assert len(api.texts) >= 2
    assert all(len(t) <= MAX_MESSAGE for t in api.texts)
    assert "<b>Sources</b>" in api.texts[-1]
    assert not any("<b>Sources</b>" in t for t in api.texts[:-1])


def test_renumber_drops_ids_that_are_not_sources():
    sources = [{"id": 42}, {"id": 7}]
    assert renumber_citations("a [7] b [42, 7] c [99] d [42, 99]", sources) == (
        "a [2] b [1, 2] c [99] d [1]"
    )
    assert renumber_citations("a [7]", []) == "a [7]"


# ---------- /cards ----------


def cards_provider(n=5):
    cards = [
        {"question": f"Q{i} <x>?", "answer": f"A{i} & more.", "source_chunk_id": 1}
        for i in range(1, n + 1)
    ]
    return FakeProvider(json_responses=[json.dumps({"cards": cards})])


def test_cards_for_the_last_answer_are_sent_as_q_and_a_pairs(store, api):
    provider = cards_provider(5)

    class Both(RecordingProvider):  # streams the answer AND makes the cards
        generate_json = provider.generate_json

    bot = make_bot(store, api, provider=Both("Use CORSMiddleware [1]."))
    asyncio.run(bot.handle_update(message("How do I enable CORS?")))
    api.sent.clear()
    asyncio.run(bot.handle_update(message("/cards")))
    text = "\n\n".join(api.texts)
    assert text.count("Q:") == 5 and text.count("A:") == 5
    assert "<b>1. Q:</b> Q1 &lt;x&gt;?\n<b>A:</b> A1 &amp; more." in text  # escaped
    assert event_names(store) == ["signup", "question_answered", "cards_made"]


def test_render_cards_sends_at_most_five():
    class C:
        def __init__(self, n):
            self.question, self.answer = f"Q{n}", f"A{n}"

    text = " ".join(render_cards([C(n) for n in range(8)]))
    assert text.count("Q:") == 5


def test_cards_before_any_question(store, api):
    asyncio.run(make_bot(store, api).handle_update(message("/cards")))
    assert api.texts == [esc(NO_CARDS)]


def test_cards_after_new_chat_have_nothing_to_use(store, api):
    bot = make_bot(store, api)
    asyncio.run(bot.handle_update(message("q")))
    asyncio.run(bot.handle_update(message("/new")))
    asyncio.run(bot.handle_update(message("/cards")))
    assert api.texts[-1] == esc(NO_CARDS)


def test_cards_after_a_refusal_say_there_is_nothing_to_learn(store, api):
    bot = make_bot(store, api, hits=[make_hit(1, similarity=0.1)])
    asyncio.run(bot.handle_update(message("What is the weather?")))
    asyncio.run(bot.handle_update(message("/cards")))
    assert api.texts[-1] == esc(NO_CARDS_REFUSED)
    assert "cards_made" not in event_names(store)


def test_a_model_failure_while_making_cards_is_a_friendly_sentence(store, api):
    class Both(RecordingProvider):
        async def generate_json(self, messages, schema, usage=None):
            raise RuntimeError("provider down: my private question")

    bot = make_bot(store, api, provider=Both("ok [1]"))
    asyncio.run(bot.handle_update(message("q")))
    asyncio.run(bot.handle_update(message("/cards")))
    assert api.texts[-1] == esc(ERR_CARDS)


def test_a_quota_failure_says_so_in_the_bot(store, api, monkeypatch):
    class Quota(Exception):
        code = 429

    class Both(RecordingProvider):
        async def generate_json(self, messages, schema, usage=None):
            raise Quota()

    async def instant(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry, "_sleep", instant)  # no real backoff between the 429 retries
    bot = make_bot(store, api, provider=Both("ok [1]"))
    asyncio.run(bot.handle_update(message("q")))
    asyncio.run(bot.handle_update(message("/cards")))
    assert "quota" in api.texts[-1]


def test_a_russian_question_gets_the_english_hint_and_no_llm_call(store, api):
    provider = RecordingProvider("never")
    bot = make_bot(store, api, provider=provider)
    asyncio.run(bot.handle_update(message("Как работает Depends?")))
    assert api.texts[-1] == esc(NON_ENGLISH_HINT)
    assert provider.calls == []
    assert store.llm_calls == []
    refused = [p for n, _, p, _ in store.events if n == "question_answered"]
    assert refused[-1]["refused"] is True and refused[-1]["reason"] == "non_english"


# ---------- limits and errors ----------


def test_a_per_person_rate_limit_stops_a_flood_without_calling_the_llm(store, api):
    bot = make_bot(store, api, user_limiter=SlidingWindowLimiter(1))
    asyncio.run(bot.handle_update(message("first")))
    asyncio.run(bot.handle_update(message("second")))
    assert "too fast" in api.texts[-1] and "Try again in" in api.texts[-1]
    assert len(bot.provider_fake.calls) == 1


def test_the_limit_is_per_person(store, api):
    bot = make_bot(store, api, user_limiter=SlidingWindowLimiter(1))
    asyncio.run(bot.handle_update(message("first", user=ALICE)))
    asyncio.run(bot.handle_update(message("first", user=BOB)))
    assert len(bot.provider_fake.calls) == 2


def test_an_exhausted_service_budget_is_a_friendly_busy_message(store, api):
    budget = SlidingWindowLimiter(1)
    budget.acquire("global")  # somebody else used the only slot
    bot = make_bot(store, api, global_limiter=budget)
    asyncio.run(bot.handle_update(message("How do I enable CORS?")))
    assert api.texts == [esc(BUSY)]
    assert bot.provider_fake.calls == []


def test_a_provider_error_is_a_friendly_sentence_and_not_logged_with_the_question(
    store, api, caplog
):
    class Broken(RecordingProvider):
        async def stream(self, messages, usage=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    bot = make_bot(store, api, provider=Broken())
    with caplog.at_level(logging.INFO):
        asyncio.run(bot.handle_update(message("my very private question")))
    assert api.texts == [esc(ERR_MODEL)]
    assert "my very private question" not in caplog.text
    assert "my very private question" not in api.texts[0]


def test_a_timeout_is_a_friendly_sentence(store, api, monkeypatch):
    async def instant(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry, "_sleep", instant)

    class Hanging(RecordingProvider):
        async def stream(self, messages, usage=None):
            await asyncio.sleep(60)
            yield "never"

    bot = make_bot(store, api, provider=Hanging())
    bot.settings = Settings(_env_file=None, similarity_threshold=0.5, llm_timeout_seconds=0.05)
    asyncio.run(bot.handle_update(message("q")))
    assert api.texts == [esc(llm_errors.MESSAGES["timeout"])]


# ---------- events ----------


def test_events_carry_the_channel_and_never_the_question_text(store, api, caplog):
    secret = "my very private question about CORS"
    bot = make_bot(store, api)
    with caplog.at_level(logging.DEBUG):
        asyncio.run(bot.handle_update(message(secret)))
    answered = [(u, p) for n, u, p, _ in store.events if n == "question_answered"]
    assert answered == [
        (user_of(store).id, {"channel": "telegram", "cited": True, "refused": False})
    ]
    assert secret not in repr(store.events)
    assert secret not in caplog.text


def test_a_broken_events_table_does_not_break_the_bot(store, api):
    store.fail_events = True
    asyncio.run(make_bot(store, api).handle_update(message("How do I enable CORS?")))
    assert any("CORSMiddleware" in t for t in api.texts)


def test_admin_stats_split_web_and_telegram(store, api):
    store.log_event("question_answered", UUID(int=1), {"cited": True, "refused": False})
    asyncio.run(make_bot(store, api).handle_update(message("q")))
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, admin_emails="owner@example.com"
    )
    app.dependency_overrides[get_store] = lambda: store
    from .fakes import login

    with TestClient(app, headers=login(store, "owner@example.com")) as client:
        body = client.get("/admin/stats").json()
    assert body["by_channel"]["web"]["question_answered"] == 1
    assert body["by_channel"]["telegram"]["question_answered"] == 1
    assert body["by_channel"]["telegram"]["signup"] == 1
    assert body["by_channel"]["telegram"]["users"] == 1
    assert body["totals"]["question_answered"] == 2  # the old totals still add up


# ---------- webhook registration ----------


def settings_with(**kw):
    base = dict(
        telegram_bot_token=TOKEN,
        telegram_webhook_secret=SECRET,
        public_url="https://m.example.com/",
    )
    return Settings(_env_file=None, **{**base, **kw})


def test_register_webhook_sends_the_url_and_the_secret_token():
    api = FakeApi()
    asyncio.run(register_webhook(settings_with(), api))
    assert api.webhooks == [(f"https://m.example.com/telegram/webhook/{SECRET}", SECRET)]


def test_register_webhook_failure_is_logged_without_token_or_url(caplog):
    api = FakeApi()
    api.fail_webhook = True
    with caplog.at_level(logging.DEBUG):
        asyncio.run(register_webhook(settings_with(), api))  # does not raise
    assert "failed" in caplog.text
    assert TOKEN not in caplog.text and SECRET not in caplog.text


def test_register_webhook_success_does_not_log_the_secret_url(caplog):
    with caplog.at_level(logging.DEBUG):
        asyncio.run(register_webhook(settings_with(), FakeApi()))
    assert SECRET not in caplog.text and TOKEN not in caplog.text


@pytest.mark.parametrize("missing", ["public_url", "telegram_webhook_secret"])
def test_register_webhook_needs_the_public_url_and_the_secret(missing):
    api = FakeApi()
    asyncio.run(register_webhook(settings_with(**{missing: ""}), api))
    assert api.webhooks == []


def test_the_app_registers_the_webhook_at_startup_and_closes_the_client(store):
    api = FakeApi()
    app.dependency_overrides[get_settings] = lambda: settings_with()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_telegram_api] = lambda: api
    with TestClient(app):
        pass
    assert len(api.webhooks) == 1 and api.closed


def test_the_app_runs_without_any_telegram_settings(store):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_a_failing_webhook_registration_does_not_stop_the_app(store):
    api = FakeApi()
    api.fail_webhook = True
    app.dependency_overrides[get_settings] = lambda: settings_with()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_telegram_api] = lambda: api
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
