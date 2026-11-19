# 0002 — Default Gemini model: gemini-3.5-flash-lite

Date: 2026-11-19 · Status: accepted · Lab: 31

## Context

`/chat` got no token within the 30 s timeout. A latency probe (a one-off script, one prompt, 90 s cap per run) gave:

| Model | Mode / thinking | First token | Result |
|---|---|---|---|
| gemini-flash-latest | stream | — | 404 not found |
| gemini-2.5-flash-lite | stream | — | 404, "no longer available to new users" |
| gemini-3.8-flash | stream / non-stream / REST (httpx) / `thinking_budget=0` | — | no response in 90 s |
| gemini-3.8-flash | `thinking_level=MINIMAL` | — | 400, level not supported |
| gemini-3.8-flash | `thinking_level=LOW` | 45 s | works, but above our 30 s timeout |
| gemini-3.5-flash-lite | default | **3.4 s** | works |

The raw REST call hangs the same way as the SDK, so the cause is not our code, the SDK, streaming or thinking.
Model access depends on the Google account (project), not on a single key.

## Decision

Default `GEMINI_MODEL` to `gemini-3.5-flash-lite`. The model stays configurable in `.env`.

## Consequences

- Fast first token on the free tier; the 30 s timeout is no longer hit.
- Verified with one run per configuration — it shows what works now, not how stable it is.
- `ListModels` is not proof of access (it listed `gemini-2.5-flash-lite`, which returned 404): check a model with a real call.
- Model availability can change per account and over time; if `/chat` hangs again, re-run a probe before changing code.
