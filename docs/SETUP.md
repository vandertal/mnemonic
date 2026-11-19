# Setup — what is installed and how to remove it

Machine: Windows 11. Everything below was installed with **winget** (user scope, no admin) on 2026-11-19.

Update everything once a month (winget does not auto-update):

```powershell
winget upgrade --all
```

## Tools

| Tool | Version at install | Why | Remove |
|---|---|---|---|
| Git | 2.56.1 | Version control | Settings → Apps, or `winget uninstall Git.Git` |
| GitHub CLI (`gh`) | 2.105.0 | Login, repo creation, CI status from the terminal | `winget uninstall GitHub.cli` |
| uv | 0.13.9 | Python versions, virtual envs, dependencies | `winget uninstall astral-sh.uv` (+ delete `%APPDATA%\uv`) |
| VS Code | 1.146.0 | Editor | `winget uninstall Microsoft.VisualStudioCode` |
| Node.js LTS | 26.13.1 | Frontend build (lab 22) | `winget uninstall OpenJS.NodeJS.LTS` |
| Claude Code | 2.1.318 | AI coding assistant in the repo | `winget uninstall Anthropic.ClaudeCode` |
| PowerShell 7 (`pwsh`) | 7.7.0 | Modern shell (`&&`, UTF-8 by default); default profile in Windows Terminal | `winget uninstall Microsoft.PowerShell` (+ reset the default profile in Windows Terminal) |

VS Code extensions: `ms-python.python`, `charliermarsh.ruff`, `anthropic.claude-code`.

## Where project files live

- Python packages: `backend/.venv/` — delete the folder to remove them. Global cache: `uv cache clean`.
- Node packages: `frontend/node_modules/` — delete the folder to remove them.
- Secrets: `backend/.env` (never committed).

## Git configuration (global)

- `user.name` = Vladislav, `user.email` = GitHub noreply address
- `init.defaultBranch` = main, `core.autocrlf` = true
- `core.longpaths` = true — allows paths longer than 260 chars on Windows (deep `node_modules/`)
- GitHub auth via `gh auth login` (HTTPS)

## Accounts

| Service | Used for | Status |
|---|---|---|
| GitHub | Code, CI | ✅ |
| Claude Pro | Claude Code | ✅ |
| LLM API provider (Gemini) | RAG answers (lab 31) — free tier, billing not connected | ⏳ lab 31 |
| Neon | Postgres + pgvector | ⏳ lab 31 |
| Render | Backend hosting | ⏳ lab 31 |
| Vercel / Netlify | Frontend hosting | ⏳ lab 22 |

## Planned, not installed yet

- Docker Desktop — from lab 21 if needed.
- Ollama — optional, local LLM on the RTX 5070.
- PyTorch with CUDA — lab 33, installed inside the project via `uv`.
