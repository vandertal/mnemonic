# Mnemonic — frontend

React + TypeScript + Vite + Tailwind SPA.

```powershell
cd frontend
npm install
cp .env.example .env        # VITE_API_URL = backend address
npm run dev                 # http://localhost:5173
npm run build ; npm run lint
```

## Commands

- `npm run dev` — prints the effective API URL first (`predev`) and warns loudly if it is missing or local.
- `npm run smoke` — checks the backend from the SPA's point of view: CORS preflight, wrong key → 401, right key → 200, `GET /documents`.
  Needs `SMOKE_KEY` (the access code; never printed), optional `SMOKE_ORIGIN` (default `http://localhost:5173`):
  `$env:SMOKE_KEY = "<code>" ; npm run smoke`
- `npm run build` · `npm run lint`

Backend must allow this origin: `CORS_ORIGINS` in `backend/.env` (default `http://localhost:5173`).

## Layout

- `src/styles/tokens.css` — design tokens (CSS variables, light + `.dark`); the only place with colours.
- `src/api/` — `client.ts` (X-API-Key, typed errors), `sse.ts` (stream parser), `chat.ts`.
- `src/i18n/{uk,en}.json` — all UI strings; use `t('key')`, never literals.
- `src/features/chat/` — streaming chat, source cards, markdown.

## Deploy (Cloudflare Pages)

1. Push the repo to GitHub.
2. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** → pick the repo.
3. Build settings: root directory `frontend`, build command `npm run build`, output directory `dist`.
4. Environment variables (production): `VITE_API_URL` = your Render URL (no trailing slash), `NODE_VERSION` = `22`.
5. **Save and Deploy**. Copy the URL (`https://<name>.pages.dev`).
6. Render → backend service → Environment → `CORS_ORIGINS` = that URL → save (redeploys).
7. Open the URL, enter the access code, ask a question.

`VITE_*` variables are baked in at build time: change one → redeploy the frontend.
