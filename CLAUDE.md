# Kitabim AI — Claude Instructions

## Skills

This project has a set of skills in `.claude/skills/`. Invoke the right one before starting any work. The skills carry full codebase conventions, patterns, and checklists — do not repeat what is already in the skill.

### When to invoke which skill

| Task | Invoke |
|------|--------|
| Designing a new API endpoint, schema, or DB model | `/api-designer` |
| Implementing backend features day-to-day (migrations, services, repos, jobs) | `/api-developer` |
| Writing backend tests (repos, services, endpoints) | `/api-unit-tester` |
| Reviewing backend/worker code changes | `/api-code-review` |
| Designing a new worker job or scanner | `/worker-designer` |
| Implementing worker jobs, scanners, pipeline wiring | `/worker-developer` |
| Writing worker/scanner tests | `/worker-unit-tester` |
| Reviewing worker code changes | `/worker-code-review` |
| Designing or implementing React UI components | `/ui-designer` |
| Implementing frontend hooks, services, routing | `/ui-developer` |
| Writing frontend component/hook tests | `/ui-unit-tester` |
| Reviewing frontend code changes | `/ui-code-review` |
| Designing database schemas, migrations, query patterns | `/database-designer` |
| Designing infrastructure, GCP resources, CI/CD | `/infra-designer` |
| Implementing shell scripts, Docker, Nginx, GitHub Actions | `/infra-developer` |
| Auditing or implementing security controls | `/app-security` |
| Writing or editing LLM prompts (OCR, RAG, summary) | `/prompt-engineer` |
| Designing a new feature end-to-end across services | `/system-architect` |

### Rules
- **Always invoke the relevant skill first** before writing or reviewing any code.
- A task may require multiple skills (e.g. `/api-designer` + `/database-designer` for a new feature with a new table).
- Skills are self-contained — they carry the patterns, conventions, and checklists. Trust them.

---

## Project Layout (quick reference)

| Location | Contents |
|----------|----------|
| `services/backend/` | FastAPI API server |
| `services/worker/` | arq background worker |
| `apps/frontend/` | React/Vite SPA |
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
