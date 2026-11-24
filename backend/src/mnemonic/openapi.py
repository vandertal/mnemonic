"""OpenAPI text shared by the routers: tag descriptions and reusable error responses."""

DESCRIPTION = """
An AI study assistant: ask questions about a knowledge base or your own files, get answers
with citations (or an honest "I don't know"), and turn answers into flashcards.

**How to try it:** `POST /auth/register`, then press **Authorize** and log in with the same
email and password. Every endpoint except `/auth/*`, `/health` and `/` needs the Bearer token
and only ever sees the rows of that account.
"""

TAGS = [
    {"name": "auth", "description": "Accounts: register, log in, who am I, delete my account."},
    {
        "name": "sessions",
        "description": "Chat sessions of the caller: create, list (paginated), rename, delete, "
        "read the messages.",
    },
    {"name": "chat", "description": "Ask a question inside a session; the answer streams (SSE)."},
    {"name": "flashcards", "description": "Flashcards from a saved answer and its sources."},
    {"name": "documents", "description": "The caller's uploaded files (.md, .txt, .pdf)."},
    {
        "name": "search",
        "description": "Keyword search (own BM25 index) over the knowledge base and the caller's "
        "own documents, with highlighted snippets and a per-term score explanation.",
    },
    {"name": "chunks", "description": "The text behind a citation."},
    {"name": "system", "description": "Liveness and the demo page."},
]

R401 = {"description": "Missing, invalid or expired Bearer token"}
R404 = {"description": "Not found (or it belongs to someone else: the two look the same)"}
R409 = {"description": "Conflict"}
R422 = {"description": "Validation error"}
R429 = {"description": "Too many requests; see the Retry-After header"}
