# AGENTS.md — Frontend

## Service Purpose
React/Vite frontend that consumes the backend API. No secrets in the browser.

## Run (Dev)
```bash
npm install
npm run dev
```

## Notes
- Vite dev server proxies `/api` to the backend.
- Do not add AI keys or other secrets to client code.
- Local dev uses Docker Desktop Kubernetes (see `k8s/local`).

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in the root `docs/` folder.
