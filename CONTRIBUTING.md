# Contributing

Mnemonic is a solo university project, but small fixes and issues are welcome.

## Setup

Needs Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 22, and a Postgres with pgvector (a free Neon branch works).
Step by step: [README, Quickstart](README.md#quickstart-from-a-fresh-clone). Secrets go only in `.env` files (git-ignored);
copy `backend/.env.example` and `frontend/.env.example`. `LLM_PROVIDER=fake` needs no API key.

## Run the tests

```powershell
# backend
cd backend
uv run ruff check . ; uv run ruff format --check .
uv run pytest                                # unit tests; integration tests skip themselves
$env:TEST_DATABASE_URL = "postgresql://..."  # a THROWAWAY database: these tests wipe it
uv run pytest -m integration

# frontend
cd frontend
npx tsc -b ; npx oxlint ; npm run test ; npm run build
```

CI runs all of this on every push and pull request to `main`.

## Commit style

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
Small commits, one idea each. Never commit secrets, `.env` files, model weights or large data files.

## Pull request flow

1. Branch from `main` (`git switch -c fix-something`).
2. Add or update tests for new logic; run `ruff` and the tests above.
3. Open a pull request against `main` and describe what changed and why. CI must be green: Render deploys `main` only after the checks pass.
4. Do not add a new dependency or service without discussing it in the PR first.

Decisions worth knowing before a bigger change are in [docs/decisions/](docs/decisions/).
