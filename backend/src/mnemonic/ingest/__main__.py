"""Ingest the FastAPI docs: clone -> chunk -> embed -> upsert into Postgres.

Run from backend/:  uv run python -m mnemonic.ingest
"""

import subprocess
import sys
from pathlib import Path

from mnemonic.config import get_settings
from mnemonic.ingest import db
from mnemonic.ingest.chunker import Chunk, chunk_markdown
from mnemonic.ingest.embedder import embed_documents, get_tokenizer

REPO_URL = "https://github.com/fastapi/fastapi.git"
DATA_DIR = Path("data")  # git-ignored; relative to backend/
REPO_DIR = DATA_DIR / "fastapi"
DOCS_DIR = REPO_DIR / "docs" / "en" / "docs"  # English docs only
BATCH = 64


def clone_docs() -> None:
    if REPO_DIR.exists():
        print(f"Using existing clone: {REPO_DIR}")
        return
    DATA_DIR.mkdir(exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)], check=True)


def collect_chunks() -> list[Chunk]:
    tokenizer = get_tokenizer()
    chunks: list[Chunk] = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        rel = path.relative_to(DOCS_DIR).as_posix()
        chunks += chunk_markdown(path.read_text(encoding="utf-8"), rel, tokenizer)
    return chunks


def main() -> int:
    clone_docs()
    chunks = collect_chunks()
    print(f"Chunked into {len(chunks)} chunks")

    with db.connect(get_settings().database_url) as conn:
        db.init_schema(conn)
        known = db.existing_hashes(conn)
        # Embedding is the slow part: only embed chunks that are not stored yet.
        new = [c for c in chunks if db.content_hash(c) not in known]
        print(f"{len(new)} new, {len(chunks) - len(new)} already stored")

        inserted = 0
        for i in range(0, len(new), BATCH):
            batch = new[i : i + BATCH]
            inserted += db.upsert_chunks(conn, batch, embed_documents(c.content for c in batch))
            print(f"  {min(i + BATCH, len(new))}/{len(new)}", end="\r")
        print(f"\nInserted {inserted}. Total rows: {db.count(conn)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
