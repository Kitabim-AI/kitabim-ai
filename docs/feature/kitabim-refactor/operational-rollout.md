# Operational Rollout Runbook — `kitabim-ocr-redo`

This runbook covers the end-to-end operational rollout for the [`kitabim-ocr-redo`](file:///Users/Omarjan/Projects/kitabim-ai/docs/feature/kitabim-refactor/kitabim-ocr-redo.md) architecture across local OCR queues, production deployment, corpus re-OCR backfill, structure/chunking migration, and rollback procedures.

---

## 1. Overview of Rollout Phases

| Phase | Scope | What Happens |
| :--- | :--- | :--- |
| **Phase 0** | Local `kitabim-ocr` Queue | Finish (or safely restart) the local `clients/kitabim-ocr` web app so new books use `surya-2.5-v2`. |
| **Phase 1** | Production Deployment & DB Migrations | Deploy backend/worker/frontend via `./deploy/gcp/scripts/deploy.sh` and apply SQL migrations `101`–`103`. |
| **Phase 2** | Headless Corpus Re-OCR Backfill | Run `python main.py backfill` locally on older PDF books (`ocr_version IS NULL`) with backlog throttling. |
| **Phase 3** | Remaining Structure & Chunking Backfill | Run `scripts/trigger_remaining_structure_backfill.py` for any legacy PDFs not re-OCR'd in Phase 2. |
| **Rollback** | Per-Book Snapshot Restore or Schema Rollback | Restore any individual book's pre-backfill OCR from its `.jsonl.gz` backup or roll back migrations `103` → `101`. |

---

## 2. Phase 0 — Local `kitabim-ocr` Queue Cutover

If you have books actively running or queued in your local `clients/kitabim-ocr` web UI (`python main.py app`):

1. **No session data is lost on restart:** All session state in `$KITABIM_WORK_DIR` (`~/kitabim-ocr-work`) is backward-compatible (`PageState` defaults `detected_page_number=None`, `skipped=False`, `ended_with_hyphen=False`).
2. **When to restart `python main.py app`:**
   - Wait for the currently OCR-ing book to finish its page loop (or stop and restart `python main.py app` between books).
   - Once restarted, every newly OCR'd book automatically runs **Engine v2 (`surya-2.5-v2`)**:
     - Preserves `#` / `##` headings on `<p>`-wrapped `Title` and `SectionHeader` blocks.
     - Captures printed `detectedPageNumber` sidecars from `PageFooter`/`PageHeader` before stripping.
     - Joins cross-page hyphenated Uyghur words at the end of the book pass.
     - Uploads with `ocr_version="surya-2.5-v2"`, immediately triggering `structure` → `chunking` → `embedding` on the server.
3. **GPU Lock Protection:** Both `python main.py app` and `python main.py backfill` share an exclusive file lock at `$KITABIM_WORK_DIR/.surya_gpu.lock`, preventing two Surya predictors from loading on your Mac GPU at the same time.

---

## 3. Phase 1 — Production Environment & Deployment

### 3.1 Verify Environment Variables
Ensure the updated chunking parameters are set in both `.env` (local) and `deploy/gcp/.env` (production):

```ini
CHUNK_SIZE=1500
CHUNK_OVERLAP=200
CHUNK_MIN_SIZE=350
```

### 3.2 Apply Database Migrations (`101`–`103`)
- **Local Dev:** Already applied automatically by `./deploy/local/rebuild-and-restart.sh all`.
- **Production (Cloud SQL):** Apply migrations `101`, `102`, and `103` in order against the production PostgreSQL database before or during deployment:
  1. `packages/backend-core/migrations/101_add_book_structure_and_section_chunking.sql`
     - Creates `book_sections`, adds `structure_milestone` and `ocr_version` to `books`, `detected_page_number` and `content_page_number_manual` to `pages`, and `end_page_number`, `section_id`, `text_hash` to `chunks`.
     - Automatically stamps `ocr_version = 'surya-2.5-v2'` on `surya_local` PDFs uploaded on or after `2026-11-08T00:00:00Z`.
     - Sets `structure_milestone = 'complete'` on all books that have already finished OCR (`ocr_milestone = 'complete'`) so **zero** books automatically re-chunk on deploy, while books still in OCR remain `'idle'`. Existing books (`surya-2.5-v2` PDFs, non-PDFs, and remaining legacy PDFs) are triggered in controlled batches via `scripts/trigger_remaining_structure_backfill.py` or `replace-ocr`.
  2. `packages/backend-core/migrations/102_drop_llm_spell_check_and_history_staging.sql`
     - Drops retired `batch_llm_spell_check_jobs`, `history_dictionary_staging`, `batch_history_extraction_jobs`, and `pages.llm_spell_check_*` columns.
  3. `packages/backend-core/migrations/103_strip_hypothetical_queries_from_book_summaries.sql`
     - Strips Section 6 (`تىپىك سوئاللار`) and renumbers Section 7 (`ئاچقۇچلۇق سۆزلەر`) to `6.` in `book_summaries.summary` in-place without invalidating existing summary embeddings.

### 3.3 Deploy Application Images to Production
From the repository root, run the standard production deploy script:

```bash
./deploy/gcp/scripts/deploy.sh <IMAGE_TAG>
```

Verify post-deploy health:
- Check backend health: `curl -fsS https://kitabim.ai/api/health` (or `http://localhost:30800/health` locally).
- Open **Admin Panel → Books** and verify the new **Structure** milestone column is visible and existing books remain searchable.

---

## 4. Phase 2 — Headless Corpus Re-OCR Backfill (`clients/kitabim-ocr`)

Once Phase 1 is deployed and your local `python main.py app` queue is idle (or between batches), use the headless `backfill` CLI in `clients/kitabim-ocr` to re-OCR older PDF books (`ocr_version IS NULL`) with Surya 2.5 v2.

### 4.1 Step 1: One-Time OAuth Login (Saves `refresh_token`)
Authenticate once in your browser to save both `access_token` and the 7-day `refresh_token` to `~/.config/kitabim-ocr-client/token.json` (`0600` permissions):

```bash
cd clients/kitabim-ocr
.venv/bin/python main.py login
```

*(To target a specific backend URL instead of `KITABIM_BASE_URL` in `clients/kitabim-ocr/.env`, pass `--base-url https://kitabim.ai/api`.)*

### 4.2 Step 2: Dry-Run Candidate Discovery
Inspect which books the server reports as backfill candidates (`file_type='pdf'`, `status != 'error'`, and `ocr_version != 'surya-2.5-v2'`) without downloading or modifying anything:

```bash
cd clients/kitabim-ocr
.venv/bin/python main.py backfill --dry-run
```

### 4.3 Step 3: Canary Backfill on a Single Book
Test the full download → Surya 2.5 v2 OCR → cross-page dehyphenation → gzipped `replace-ocr` → worker `structure` → `chunking` → `embedding` flow on a single book first:

```bash
cd clients/kitabim-ocr
.venv/bin/python main.py backfill --book-id <BOOK_ID>
```

What happens automatically during `replace-ocr`:
1. The backend snapshots the book's existing `pages` rows to `$GCS_DATA_BUCKET/backups/ocr/{book_id}/{timestamp}.jsonl.gz` and records the URI in `books.gcs_ocr_backup_uri`.
2. Pages with `updated_by IS NOT NULL` (human-edited in Admin/Spell-Check) and skipped pages (`page 1` cover and existing formatted pipe-table ToC pages with `>= 2` rows) **keep their existing text** while still storing `detectedPageNumber` if captured.
3. The book's `structure_milestone` is reset to `idle`, and the worker runs `BookStructureService` → `ChunkingService` (carrying over unchanged chunk vectors via `text_hash`) → `BatchEmbeddingService`.

### 4.4 Step 4: Batch Backfill with Server Backlog Throttling
Run the backfill in batches (e.g., 5–20 books at a time, or unlimited overnight). The CLI automatically polls `activePipelineBookCount` and pauses (`30s` intervals) whenever the server has `>= --max-server-backlog` books actively running `structure`, `chunking`, or `embedding`:

```bash
cd clients/kitabim-ocr
.venv/bin/python main.py backfill --limit 10 --max-server-backlog 3
```

- **Resumable:** Every completed book is stamped with `ocr_version = 'surya-2.5-v2'` on the server, so re-running `python main.py backfill` automatically picks up where it left off.
- **Audit Log:** Every processed book appends a JSON line to `$KITABIM_WORK_DIR/backfill_audit.jsonl` (or a custom path via `--audit-log`) recording `book_id`, `title`, `ocrd_pages`, `skipped_pages`, `failed_pages`, `dehyphenated_pairs`, `pages_updated`, `backup_uri`, and `elapsed_s`.

---

## 5. Phase 3 — Trigger Structure & Section-Chunking on `surya-2.5-v2`, Non-PDF, and Remaining Books

Because Migration `101` leaves all already-OCR'd books at `structure_milestone = 'complete'` on deploy, use [`scripts/trigger_remaining_structure_backfill.py`](file:///Users/Omarjan/Projects/kitabim-ai/scripts/trigger_remaining_structure_backfill.py) to trigger `BookStructureService` + section-stream chunking in controlled batches:

### 5.1 Trigger `surya-2.5-v2` PDFs and non-PDF books (`--skip-legacy-pdf`)
Can be run immediately after deploy while legacy PDFs await Phase 2 re-OCR:
```bash
# 1. Preview matching surya-2.5-v2 and non-PDF books without book_sections
./venv/bin/python scripts/trigger_remaining_structure_backfill.py --skip-legacy-pdf --limit 50 --dry-run

# 2. Reset up to 50 books at a time to structure_milestone = 'idle'
./venv/bin/python scripts/trigger_remaining_structure_backfill.py --skip-legacy-pdf --limit 50
```

### 5.2 Trigger any remaining books without `book_sections` (after Phase 2 re-OCR)
```bash
# 1. Preview any remaining completed books that still have no book_sections rows
./venv/bin/python scripts/trigger_remaining_structure_backfill.py --limit 50 --dry-run

# 2. Reset up to 50 books at a time to structure_milestone = 'idle'
./venv/bin/python scripts/trigger_remaining_structure_backfill.py --limit 50
```

You can also trigger structure extraction and re-chunking on any individual book at any time from:
- **Admin UI:** Books table → Action Menu (`⋯`) → **Re-extract Structure** (`قۇرۇلمىنى قايتا ئايرىش`).
- **API:** `POST /api/books/{book_id}/reprocess/structure`.

---

## 6. Rollback & Recovery Procedures

### 6.1 Restore a Single Book's Pre-Backfill OCR (`restore_book_ocr_backup.py`)
If a backfilled book has an OCR regression and you want to revert its pages to the pre-backfill snapshot stored in `books.gcs_ocr_backup_uri`:

```bash
# 1. Dry-run to inspect the snapshot and page count
./venv/bin/python scripts/restore_book_ocr_backup.py --book-id <BOOK_ID> --dry-run

# 2. Restore pages from books.gcs_ocr_backup_uri and re-trigger structure/chunking
./venv/bin/python scripts/restore_book_ocr_backup.py --book-id <BOOK_ID>
```

*(You can also pass an explicit `--backup-uri gs://.../backups/ocr/<book_id>/<ts>.jsonl.gz` if needed.)*

### 6.2 Full Database Schema Rollback (`103` → `101`)
If you ever need to roll back the database schema changes in reverse order:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 < packages/backend-core/migrations/103_rollback_strip_hypothetical_queries_from_book_summaries.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 < packages/backend-core/migrations/102_rollback_drop_llm_spell_check_and_history_staging.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 < packages/backend-core/migrations/101_rollback_add_book_structure_and_section_chunking.sql
```

---

## 7. Post-Migration Code & Data Cleanup Checklist

Once the corpus backfill (Phases 2 & 3) is complete and verified in production, the following migration-only scaffolding can be removed in a follow-up cleanup PR:

1. **Standalone `clients/kitabim-ocr` Backfill Scaffolding:**
   - Delete [`clients/kitabim-ocr/backfill.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/backfill.py) and [`clients/kitabim-ocr/tests/test_backfill.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/tests/test_backfill.py).
   - Remove the `backfill` subcommand (`cmd_backfill`) from [`clients/kitabim-ocr/main.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/main.py).
   - Remove `get_backfill_candidates` / `list_backfill_candidates` and `replace_book_ocr` from [`clients/kitabim-ocr/kitabim_client/api.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/kitabim_client/api.py).
2. **Backend Backfill & Snapshot Replacement Endpoints:**
   - Remove `GET /api/books/backfill-candidates` and `POST /api/books/{book_id}/replace-ocr` from [`services/backend/api/endpoints/books_router.py`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/api/endpoints/books_router.py) and delete [`services/backend/tests/api/endpoints/books_replace_ocr_test.py`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/tests/api/endpoints/books_replace_ocr_test.py).
   - Remove `BackfillCandidateItem`, `BackfillCandidatesResponse`, `ReplaceOcrPageItem`, `ReplaceOcrRequest`, and `ReplaceOcrResponse` from [`packages/backend-core/app/models/schemas.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/models/schemas.py) and regenerate `packages/shared/src/api-types.ts`.
3. **One-Time Migration Scripts & GCS Backups:**
   - Delete [`scripts/trigger_remaining_structure_backfill.py`](file:///Users/Omarjan/Projects/kitabim-ai/scripts/trigger_remaining_structure_backfill.py) and [`scripts/restore_book_ocr_backup.py`](file:///Users/Omarjan/Projects/kitabim-ai/scripts/restore_book_ocr_backup.py) (and remove their entries from [`scripts/README.md`](file:///Users/Omarjan/Projects/kitabim-ai/scripts/README.md)).
   - Delete `$GCS_DATA_BUCKET/backups/ocr/` snapshots once you are satisfied with the re-OCR quality.
4. **Database Columns (`books` table):**
   - Drop `books.ocr_backfill_at` and `books.gcs_ocr_backup_uri` (and optionally `books.ocr_version`) via a small cleanup migration and remove them from [`packages/backend-core/app/db/models.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/db/models.py).
5. **Legacy Fallback Paths (Optional):**
   - Once every book has `book_sections` populated, remove the legacy regex fallback (`_fallback_toc_page_scan`) in [`packages/backend-core/app/rag/toc_lookup_service.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/rag/toc_lookup_service.py).
