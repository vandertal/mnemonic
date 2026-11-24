"""Dev-only: call the real model the way make_flashcards does (one call, prints the raw failure)."""

import asyncio
import logging

from mnemonic.config import get_settings
from mnemonic.llm.base import Usage
from mnemonic.llm.factory import build_provider
from mnemonic.rag import build_flashcard_messages
from mnemonic.schemas import FlashcardSet
from mnemonic.store import Chunk

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    s = get_settings()
    p = build_provider(s)
    chunks = [Chunk(1, "tutorial/cors.md", "CORS", "Use CORSMiddleware to allow origins.")]
    msgs = build_flashcard_messages("Use CORSMiddleware [1].", chunks)
    usage = Usage()
    try:
        r = await p.generate_json(msgs, FlashcardSet, usage)
        print("OK", r)
    except Exception as e:
        print("FAIL", type(e).__name__, getattr(e, "code", None), str(e)[:800])
    print(usage)


asyncio.run(main())
