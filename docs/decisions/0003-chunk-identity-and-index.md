# 0003 — Chunk identity (content_hash) and HNSW index

Date: 2026-11-19 · Status: accepted · Lab: 31

## Context

Ingest must be re-runnable without duplicates, and re-embedding 2200 chunks is slow.
Search must use cosine similarity.

## Decision

- `content_hash = sha256(file_path + "\0" + content)`, `UNIQUE`. Insert uses `ON CONFLICT DO NOTHING`;
  ingest also skips embedding chunks whose hash is already stored.
  The path is part of the hash so identical boilerplate in two files is stored twice (each can be cited).
- Index: HNSW with `vector_cosine_ops` (matches the `<=>` operator; no training step, unlike IVFFlat).
- Heading is not part of the hash: changing only heading cleaning needs a `TRUNCATE` + re-ingest.

## Consequences

- Re-run = 0 inserts, nearly instant. Changed text = new row.
- Chunks whose text was edited upstream leave stale rows behind (no delete pass); fine for a static corpus,
  to revisit with per-user uploads (M7).
- Identical chunks inside one file collapse into one row (1 of 2203 chunks on the first run).
