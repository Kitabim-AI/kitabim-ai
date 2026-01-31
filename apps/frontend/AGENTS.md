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
- Local dev uses Docker Desktop Kubernetes (see `infra/k8s/docker-desktop`).
