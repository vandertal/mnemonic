# Lab 22 — M3 task for Claude Code (autonomous): make it yours + close

The developer PRE-APPROVED this plan. Do NOT wait for "ok": print a 5-line plan, then execute. Stop only if blocked by a missing secret/irreversible decision.
Read first: CLAUDE.md, docs/labs/lab-22.md, brief `../Programming-Practice-Projects/labs/lab-22-spa-frontend.md` (sections: Deployment checklist, What to put in your README, Reflection), then only files you touch.
Rules: small Conventional commits, no AI attribution, English code/docs, UI strings via i18n (uk + en).

## "Make it yours" (decided, do not ask)
- Aesthetic: Linear-style minimal, indigo accent, dark/light, Inter.
- Signature feature: **verifiable answers** — inline citation chips + source cards that open the exact chunk. Make sure it is polished and mentioned in README.

## Tasks
1. Performance/Lighthouse mobile >= 90: lazy-load routes (React.lazy + Suspense with skeleton), lazy-load markdown/dialog code if heavy, preload Inter weights used, no layout shift on first paint, `lang` attribute follows i18n, `<meta name=theme-color>` per theme, descriptive `<title>` per route.
2. Accessibility: labels/aria for icon-only buttons, focus-visible rings, dialog focus trap (Radix already), contrast AA on muted text in both themes, `prefers-reduced-motion` respected.
3. Deployment checklist items: favicon (own SVG, not Vite default), OpenGraph + Twitter meta (title, description, image `public/og.png` 1200x630 generated as simple SVG->PNG or a static brand card), 404 page exists, no `alert()` (grep), no console errors on fresh load, `.env` git-ignored, SPA fallback (`public/_redirects` with `/* /index.html 200`), API URL only from env.
4. UX polish pass in ONE sweep: consistent spacing/radius, hover/active states, empty/error states in every page, skeleton shapes match content, mobile 375px check of every page by reading the layout classes (no horizontal overflow).
5. Cmd/Ctrl+K command palette (cmdk, approved dep): New chat, go to Chat/Documents/Flashcards/Settings, toggle theme, switch language, sign out. i18n.
6. frontend/README.md per the brief's 10-point list, adapted: live URL placeholder `TODO_LIVE_URL` (developer fills), tech stack with versions from package.json, mermaid architecture diagram (browser -> Cloudflare Pages SPA -> Render FastAPI -> Neon), run locally + `.env.example`, deploy steps, side quests done (i18n, Cmd+K, optimistic delete, offline banner), known limitations (access code in localStorage = XSS-readable, same class of risk as JWT in localStorage; no real accounts until lab 21; SSE parser has no unit tests yet -> lab 21 CI; owner_id is not auth), "recording: TODO developer".
7. docs/labs/lab-22.md: fill the **Reflection** answers (7 questions) as DRAFTS grounded in the real code (auth flow = access code + X-API-Key + 401 handling in api/client.ts; storage; network tab walk-through of upload/chat; offline behaviour; two tabs; 500 mid-submit; hardest bug = the .env/CORS/old-deploy chain). Mark them "draft: developer must rewrite in own words". Update status block.
8. Run tsc, oxlint, `vite build`; report bundle size per chunk (top 5).
9. Report <= 20 lines. List explicitly what the DEVELOPER must still do (Lighthouse run, phone check, 60s recording, fill TODO_LIVE_URL, tag). Then 3-7 bullets "what & why" (code splitting, CSS-variable theming, a11y choices, cmdk).
