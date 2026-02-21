# Status Naming Refactor

The current `completed` status is ambiguous: on a **Page** it means OCR succeeded; on a **Book** it means OCR succeeded but indexing failed — a partial failure that sounds like success. Additionally, jobs are marked `failed` when a book ends as `completed`, which is misleading since OCR ran fine.

## Why this is clean to split

The worker in `pdf_service.py` already has two clearly separate phases in the same function:

```
Phase 1 (L280–404): OCR loop  → page: pending → ocr_processing → ocr_done / error
Phase 2 (L411–end): Embed loop → page: ocr_done → indexing → indexed (is_indexed=True)
```

This means we can set distinct statuses at exact points with zero restructuring of the pipeline.

## Rename Summary

| Old value / name | New value / name | Where |
|---|---|---|
| book status `"processing"` | `"ocr_processing"` | DB + all code |
| book status `"completed"` | `"ocr_done"` | DB + all code |
| *(new)* book status | `"indexing"` | Set when Phase 2 (embed) starts |
| page status `"processing"` | `"ocr_processing"` | DB + all code |
| page status `"completed"` | `"ocr_done"` | DB + all code |
| `completed_count` (DB column) | `ocr_done_count` | `books` table |
| `completed_count` (Python field) | `ocr_done_count` | Pydantic, repos, endpoints |
| `completedCount` (TS field) | `ocrDoneCount` | Frontend types, components |
| `admin.stats.completed` (i18n) | `admin.stats.ocrDone` | `en.json`, `ug.json` |
| Job `"failed"` when book=`ocr_done` | Job `"succeeded"` with note | Job status logic |

> [!IMPORTANT]
> `completed_count` on the `books` DB table is a **denormalized cache column** — renaming it requires an `ALTER TABLE` plus updating every place that writes/reads it. This is the riskiest part.

> [!NOTE]
> `"completed"` in log message strings (e.g. `"OCR completed for page"`, `"Embedding batch completed"`) does **not** need changing — those are human-readable text, not status values.

---

## Proposed Changes by File

### Database

**Migration SQL** (run once against live DB):
```sql
-- Rename status values in data
UPDATE books SET status = 'ocr_processing' WHERE status = 'processing';
UPDATE books SET status = 'ocr_done'       WHERE status = 'completed';
UPDATE pages SET status = 'ocr_processing' WHERE status = 'processing';
UPDATE pages SET status = 'ocr_done'       WHERE status = 'completed';

-- Rename denormalized cache column
ALTER TABLE books RENAME COLUMN completed_count TO ocr_done_count;

-- Update page status check constraint
ALTER TABLE pages DROP CONSTRAINT pages_status_check;
ALTER TABLE pages ADD CONSTRAINT pages_status_check
  CHECK (status IN ('pending', 'ocr_processing', 'ocr_done', 'indexing', 'indexed', 'error'));
```

---

### Backend Python

#### [MODIFY] [models.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/db/models.py)
- Line 83: column `completed_count` → `ocr_done_count`
- Line 171: constraint `'pending', 'processing', 'completed', 'error'` → `'pending', 'ocr_processing', 'ocr_done', 'indexing', 'error'`

  > Note: we add `'indexing'` as a valid page status (set at Phase 2 start), and keep no `'processing'` since it splits into `'ocr_processing'`.

#### [MODIFY] [schemas.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/models/schemas.py)
- Line 75: field `completed_count: int` → `ocr_done_count: int`

#### [MODIFY] [pdf_service.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/pdf_service.py)

**Phase 0 — book init (L231–235):**
- `status="processing"` → `"ocr_processing"`

**Phase 1 — OCR loop (L280–404):**
- L260, L269, L304: `Page.status != "completed"` / `== "completed"` → `"ocr_done"`
- L308: `update_status(..., "processing")` (per-page, before OCR) → `"ocr_processing"`
- L371: `status="completed" if success else "error"` → `"ocr_done" if success else "error"`

**Phase 2 — Embedding loop (L411–end):**
- L415: query filter `Page.status == "completed"` → `"ocr_done"`
- **NEW (before embed loop starts):** set book status → `"indexing"`, commit
- **NEW (per page, before embed call):** set page status → `"indexing"`
- **NEW (per page, after embed success):** set page status → `"indexed"` (replaces bare `is_indexed=True`)

**Final status (L558–564):**
- `completed_count` variable → `ocr_done_count` (+ all references on L559, L561, L572)
- `count_by_book(book_id, status="completed")` → `status="ocr_done"`
- `final_status = "completed"` → `"ocr_done"`
- L598–601: when `final_status == "ocr_done"`, mark job **`"succeeded"`** with note `"OCR complete, indexing incomplete"`

#### [MODIFY] [books.py (endpoint)](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/api/endpoints/books.py)
- L268, L272: variable `group_completed` → `group_ocr_done`; key `"completed"` → `"ocr_done"`
- L294, L332, L415, L420, L650: key `"completed_count"` → `"ocr_done_count"`; `.get("completed", 0)` → `.get("ocr_done", 0)`
- L675–685: variable `completed` → `ocr_done`; dict key `"completed"` → `"ocr_done"`
- L1070, L1076: SQL string `status = 'completed'` → `'ocr_done'`
- L1150: `status = 'completed'` (page update) → `'ocr_done'`
- L1198: `r.get("status", "completed")` → `"ocr_done"`
- L1298: column name string `"completed_count"` → `"ocr_done_count"`

#### [MODIFY] [books.py (repository)](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/db/repositories/books.py)
- L122: key `"completed_count"` → `"ocr_done_count"`; `.get("completed", 0)` → `.get("ocr_done", 0)`

#### [MODIFY] [spell_check_service.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/spell_check_service.py)
- L76: `page_rec.status != "completed"` → `"ocr_done"`
- L121: `status = 'completed'` → `'ocr_done'`

#### [MODIFY] [discovery_service.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/discovery_service.py)
- L169: `"status": "completed"` → `"ocr_done"`

#### [MODIFY] [main.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/main.py)
- L81: `Page.status == 'completed'` → `'ocr_done'`

#### [MODIFY] [maintenance.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/maintenance.py)
- L86: `existing_job.status in ("completed", "failed")` → only `("failed",)` (job `"completed"` was never a real terminal state anyway — this was a latent bug)

---

### Frontend TypeScript

#### [MODIFY] [useBookActions.ts](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/hooks/useBookActions.ts)
- L232, L239, L310: `status: 'completed'` → `'ocr_done'`

#### [MODIFY] [ProgressBar.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/admin/ProgressBar.tsx)
- L9: `p.status === 'completed'` → `'ocr_done'`; `book.completedCount` → `book.ocrDoneCount`

#### [MODIFY] [AdminView.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/admin/AdminView.tsx)
- L262: `book.completedCount` → `book.ocrDoneCount`; `p.status === 'completed'` → `'ocr_done'`

#### [MODIFY] [StatsPanel.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/admin/StatsPanel.tsx)
- L31: add `ocr_processing:`, `ocr_done:`, `indexing:` entries to `STATUS_STYLES`
- L54: add `case 'ocr_processing':`, `case 'ocr_done':`, `case 'indexing':` to `StatusIcon`
- L177: `completed: t('admin.stats.ocrDone')` → `ocr_done: t('admin.stats.ocrDone')` in `bookStatusLabel`; add `ocr_processing: t('admin.stats.bookOcrProcessing')`, `indexing: t('admin.stats.bookIndexing')`
- L184: `completed:` → `ocr_done:` in `pageStatusLabel`; add `ocr_processing: t('admin.stats.pageOcrProcessing')`, `indexing: t('admin.stats.pageIndexing')`
- L320: `.filter(({ status }) => status !== 'completed')` → `!== 'ocr_done'` (pages section still hides the top-row indexed card)

#### [MODIFY] Test files
- `useBookActions.test.tsx` L26, L156, L157: `status: 'completed'` → `'ocr_done'`
- `ReaderView.test.tsx` L18, L19, L248: same
- `App.test.tsx` L87: same
- `AdminView.test.tsx` L15, L16, L32: same

---

### Frontend i18n

#### [MODIFY] [en.json](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/locales/en.json)
| Old key | New key | Value |
|---|---|---|
| `admin.stats.completed` | `admin.stats.ocrDone` | `"OCR Done (not indexed)"` |
| `admin.stats.bookProcessing` | `admin.stats.bookOcrProcessing` | `"OCR Processing"` |
| `admin.stats.pageProcessing` | `admin.stats.pageOcrProcessing` | `"OCR Processing"` |
| *(new)* | `admin.stats.bookIndexing` | `"Indexing"` |
| *(new)* | `admin.stats.pageIndexing` | `"Indexing"` |

> `common.completed` (line 101) stays — it's generic UI text, not a status label.

#### [MODIFY] [ug.json](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/locales/ug.json)
Same key renames with Uyghur translations.

---

## Verification Plan

### Automated
```bash
# After migration: verify zero completed rows remain
psql -c "SELECT COUNT(*) FROM books WHERE status='completed';"   -- expect 0
psql -c "SELECT COUNT(*) FROM pages WHERE status='completed';"   -- expect 0
# Verify ocr_done rows exist
psql -c "SELECT status, COUNT(*) FROM books GROUP BY status;"
psql -c "SELECT status, COUNT(*) FROM pages GROUP BY status;"
```

### Manual
- Upload a new test book → watch it go through `pending → processing → ocr_done` or `ready`
- Stats page shows the new label "OCR Done" / "ئىندېكىسلەنمىگەن كىتاب" with correct counts
- A book finishing as `ocr_done` now shows job as `succeeded` (not `failed`)
- Progress bars and page counts in Admin view still calculate correctly
