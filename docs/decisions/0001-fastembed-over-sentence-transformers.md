# 0001 — fastembed instead of sentence-transformers for local embeddings

Date: 2026-11-19 · Status: accepted · Lab: 31

## Context

RAG needs embeddings twice: once at ingest (all chunks) and on every question (at runtime, on the server).
We want local embeddings (free, no extra API limits). `sentence-transformers` depends on PyTorch
(~1 GB+ install, several hundred MB RAM). The backend runs on Render's free tier with 512 MB RAM.

## Decision

Use **fastembed** (ONNX Runtime, no PyTorch) with `BAAI/bge-small-en-v1.5` (384 dimensions).

## Consequences

- Small install and memory footprint — fits the free tier.
- Same kind of models as sentence-transformers, so retrieval quality is comparable.
- Fewer models available than in sentence-transformers; fine-tuning embeddings would need a different tool.
- Changing the model later means re-running ingest (vector size and space change).
