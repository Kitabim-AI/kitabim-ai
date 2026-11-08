# Kitabim AI — Claude Instructions

## Project Layout (quick reference)

| Location | Contents |
|----------|----------|
| `services/backend/` | FastAPI API server |
| `services/worker/` | arq background worker |
| `apps/frontend/` | React/Vite SPA |
| `clients/kitabim-ocr/` | Standalone local OCR client (currently Surya OCR) — not part of the deployed product, not containerized, talks to the backend only over its public API |
| `packages/backend-core/` | Shared Python code (models, services, repos, config) |
| `packages/backend-core/migrations/` | SQL migration files |
| `deploy/local/` | Local dev rebuild scripts |
| `deploy/gcp/` | Production Docker Compose + deploy scripts |
| `scripts/` | Operational / maintenance scripts |
| `docs/` | All project documentation |

**Local dev rebuild:** `./deploy/local/rebuild-and-restart.sh [backend|worker|frontend|all]`
**Frontend:** http://localhost:30080 | **Backend:** http://localhost:30800

---

## Non-negotiable rules (apply regardless of skill)

- No `print()` — use `log_json(logger, level, "message", key=value)`
- No `os.environ.get()` in application code — use `settings.*` from `core/config.py`
- No hardcoded user-visible strings — use `t("errors.key")` from `app.core.i18n`
- No raw SQL with user input — always SQLAlchemy bound parameters
- No session shared across pages in a worker job — new `async with async_session_factory()` per page
- Migration file first, ORM model second, repository third, endpoint last
- All new API endpoints need an auth dependency — never skip it
