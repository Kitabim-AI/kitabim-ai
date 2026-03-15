# Kitabim.ai Project Information

## Project Conventions

### Documentation
- **Location:** All documentation files MUST be created in the `/docs` folder
- **Format:** Markdown (.md)
- **Index:** See `/docs/README.md` for complete documentation index
- **Types:**
  - Architecture docs (e.g., `SYSTEM_DESIGN.md`, `WORKER_DESIGN.md`)
  - Operations guides (e.g., `VM_MONITORING.md`)
  - Optimization guides (e.g., `PIPELINE_OPTIMIZATIONS.md`)
  - Feature docs (e.g., `book-summary-rag.md`)
  - Migration guides (e.g., `MIGRATION_015_*.md`)
  - API specs (e.g., `openapi.json`)
- **Standards:**
  - Include "Last Updated" date
  - Add status indicator (✅ Current, ⚠️ Outdated, 🚧 Draft)
  - Use Table of Contents for docs >500 lines
  - Include examples for technical guides
- **Test Files:** Place in `/tests/fixtures/` NOT in `/docs/`

### Code Organization
- **Backend Core:** `/packages/backend-core/` - Shared Python code
- **Services:**
  - `/services/backend/` - FastAPI REST API
  - `/services/worker/` - ARQ background workers
- **Frontend:** `/apps/frontend/` - React/Vite SPA
- **Migrations:** `/packages/backend-core/migrations/` - SQL migration scripts

### Database
- **Primary:** PostgreSQL (production: kitabim-ai)
- **Cache/Queue:** Redis
- **Migrations:** Numbered SQL files (e.g., `021_description.sql`)
- **Always verify schema before writing migrations:**
  ```bash
  psql -d kitabim-ai -c "\d table_name"
  ```

### Performance & Safety
- **Zero-risk changes:** Configuration-only optimizations (env vars, batch sizes)
- **High-risk changes:** Schema changes, concurrent job increases, multiple workers
- **Always prioritize:** Data integrity > Speed

### Environment Files
- **Local:** `.env` (root level)
- **Production:** `deploy/gcp/.env`
- **Never commit:** Keep `.env` files in `.gitignore`

## Recent Optimizations (2026-03-14)

### Safe Pipeline Speed Improvements
Applied three zero-risk optimizations for ~2x pipeline speedup:

1. **MAX_PARALLEL_PAGES:** 6→8 (local), 4→8 (production)
2. **EMBED_BATCH_SIZE:** 20→50
3. **scanner_book_limit:** 10→20 (via migration 021)

**Impact:** 300-page book processing: ~30min → ~15min

See: `/docs/PIPELINE_OPTIMIZATIONS.md` for full details.

## Architecture Notes

### Worker Pipeline Stages
1. **GCS Discovery** → Finds new PDFs in GCS bucket
2. **OCR** → Gemini Vision extracts text from PDF pages
3. **Chunking** → Splits text into semantic chunks
4. **Embedding** → Generates 768-dim vectors via Gemini
5. **Word Index** → Builds searchable word index
6. **Spell Check** → Optional spell checking
7. **Summary** → AI-generated book summaries

### Safety Mechanisms
- **Database:** `SELECT FOR UPDATE SKIP LOCKED` prevents race conditions
- **Jobs:** ARQ queue with Redis backing
- **Retries:** Configurable retry counts with exponential backoff
- **Circuit Breaker:** LLM failures trigger graceful degradation

## API Optimization Patterns

### Caching Strategy
- **Books List:** 30min (guests), 10min (authenticated), skip (admins)
- **Individual Books:** Until status changes to 'ready'
- **RAG Search:** Per query hash
- **Categories:** Long TTL (infrequent changes)

### Query Optimization
- **includeStats param:** Only load pipeline stats when needed (admin view)
- **Indexes:** Composite indexes on (title, author, upload_date)
- **Batch operations:** Use `get_batch_stats()` instead of N+1 queries

---

*Last Updated: 2026-03-14*
