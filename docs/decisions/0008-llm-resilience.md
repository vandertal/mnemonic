# 0008 — LLM resilience: classify, retry once, tell the user which failure it was

Date: 2026-11-24 · Status: accepted · Lab: 34 (fix 1)

## Context

Live testing showed two kinds of failure on the free Gemini tier:

1. **Flashcards failed every time.** Not flakiness: a bug. `FlashcardSet` carries `examples` for the OpenAPI docs;
   the SDK converts a Pydantic model into its own strict `Schema` and rejects the key before any request is sent. The
   route turned that into a 502 for everyone. Found by one real call from a script (`scripts/repro_cards.py`).
2. **Answers sometimes died mid-stream** (429 quota, 503 overload) and worked on a retry. The old retry only covered
   the time before the first token, because after that a repeat would duplicate text.

## Decision

- **Classify every provider failure** (`llm/errors.py`): `quota` (429), `overloaded` (5xx), `blocked` (safety),
  `timeout`, `invalid_output`, `other`. The class is written to `llm_calls.error_class` (migration `0006`), counted per
  class for 7 days in `GET /admin/stats` (`llm_errors_by_class`) and mapped to a short user message on the web (uk/en)
  and in the bot. The server's SSE `error` event is now `{kind, message}`.
- **Retry the whole stream once** when it fails after text was already sent. Before the retry the server emits a
  `reset` event: the client discards the partial text and the server drops it from the saved answer, so nothing is
  shown or stored twice. Not retried: a `blocked` answer (the same prompt is refused again) and a failure when the
  service-wide budget is spent. Exactly one retry (`STREAM_ATTEMPTS = 2`): more would hide a real outage and burn the
  free quota (5 requests/min).
- **Every attempt is a real call**: it spends one slot of `GLOBAL_RPM` and writes its own `llm_calls` row, so cost and
  error stats stay honest.
- **Flashcards**: `502` = the model answered with unusable output; `503` = the provider is unavailable (the sentence
  says quota, overload, timeout or declined). The provider sends a cleaned JSON schema (`response_json_schema`).
- **Non-English questions** are refused before retrieval (`language.py`: words counted by script, code and
  identifier-like words ignored). No embedding, no LLM call, reason `non_english`.

## Consequences

- A flaky provider is mostly invisible to the user; a real outage is visible in the stats and in the message.
- A retry after text was sent makes the answer start over (the user sees it clear and restart).
- The English hint covers only non-Latin scripts; German or Polish questions are still just "I don't know".
- Cost: a failing question can cost two calls instead of one.
