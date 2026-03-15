# Auto-Correction System for Spell Check

## Overview

The auto-correction system allows administrators to define correction rules for commonly misspelled words and automatically apply those corrections across all books. This significantly reduces manual editing workload for systematic OCR errors or repeated spelling mistakes.

## Architecture

### Components

1. **Database Layer** (`030_spell_check_auto_corrections.sql`)
   - `spell_check_corrections` table: Stores correction rules
   - `auto_corrected_at` column in `page_spell_issues`: Tracks when issues were auto-corrected
   - System configs for enabling/disabling the feature

2. **Data Model** ([packages/backend-core/app/db/models.py](../packages/backend-core/app/db/models.py))
   - `SpellCheckCorrection`: SQLAlchemy model for correction rules
   - Updated `PageSpellIssue` with `auto_corrected_at` timestamp

3. **Service Layer** ([packages/backend-core/app/services/auto_correct_service.py](../packages/backend-core/app/services/auto_correct_service.py))
   - `get_correction_rules()`: Fetch active correction rules
   - `apply_auto_corrections_to_page()`: Apply corrections to a single page
   - `find_pages_with_auto_correctable_issues()`: Find eligible pages
   - `get_auto_correction_stats()`: Statistics about corrections

4. **API Endpoints** ([services/backend/api/endpoints/spell_check_corrections.py](../services/backend/api/endpoints/spell_check_corrections.py))
   - `GET /api/spell-check-corrections` - List all correction rules
   - `GET /api/spell-check-corrections/stats` - Get correction statistics
   - `GET /api/spell-check-corrections/{word}` - Get specific rule
   - `POST /api/spell-check-corrections` - Create/update correction rule
   - `PATCH /api/spell-check-corrections/{word}` - Update rule
   - `DELETE /api/spell-check-corrections/{word}` - Delete rule
   - `POST /api/spell-check-corrections/apply` - Manually trigger corrections

5. **Background Job** ([services/worker/jobs/auto_correct_job.py](../services/worker/jobs/auto_correct_job.py))
   - Processes batches of pages with auto-correctable issues
   - Applies corrections in parallel (up to 10 concurrent pages)
   - Tracks success/failure metrics
   - Logs corrections for audit trail

6. **Scanner** ([services/worker/scanners/auto_correct_scanner.py](../services/worker/scanners/auto_correct_scanner.py))
   - Runs every 5 minutes
   - Finds pages with open spell issues matching correction rules
   - Dispatches auto-correction jobs to the worker

## How It Works

### Setup Phase

1. Admin creates correction rules via API:
   ```json
   POST /api/spell-check-corrections
   {
     "misspelled_word": "تەبىئەت",
     "corrected_word": "تەبىئەت",
     "auto_apply": true,
     "description": "Common OCR error in nature/natural"
   }
   ```

2. Enable auto-correction in system configs:
   ```sql
   UPDATE system_configs
   SET value = 'true'
   WHERE key = 'auto_correct_enabled';
   ```

### Automatic Processing

1. **Spell Check Scanner** runs every 1 minute:
   - Detects misspelled words on pages
   - Creates entries in `page_spell_issues` with `status='open'`

2. **Auto-Correction Scanner** runs every 5 minutes:
   - Queries for pages with open issues matching correction rules
   - Batches pages (default: 50 per job)
   - Dispatches `auto_correct_job` to worker queue

3. **Auto-Correction Job** executes:
   - Fetches correction rules once for entire batch
   - Processes pages in parallel (10 concurrent)
   - For each page:
     - Finds open issues matching correction rules
     - Applies corrections to page text (reverse order to preserve offsets)
     - Marks issues as `corrected` with `auto_corrected_at` timestamp
     - Sets page `is_indexed=False` to trigger re-embedding
     - Invalidates word index for the book
   - Logs metrics and pipeline events

### Manual Triggering

Admins can manually trigger auto-corrections:

```bash
POST /api/spell-check-corrections/apply
```

This immediately queues pages for processing without waiting for the scanner.

## Database Schema

### spell_check_corrections

| Column | Type | Description |
|--------|------|-------------|
| misspelled_word | TEXT (PK) | The word to find and replace |
| corrected_word | TEXT | The replacement word |
| auto_apply | BOOLEAN | Whether to automatically apply this rule |
| description | TEXT | Optional notes about the correction |
| created_at | TIMESTAMPTZ | When the rule was created |
| updated_at | TIMESTAMPTZ | When the rule was last modified |
| created_by | INTEGER (FK) | User who created the rule |

### page_spell_issues (updated)

Added column:
- `auto_corrected_at`: TIMESTAMPTZ - When the issue was auto-corrected (NULL if not auto-corrected)

## Configuration

### System Configs

| Key | Default | Description |
|-----|---------|-------------|
| `auto_correct_enabled` | `false` | Enable/disable auto-correction feature |
| `auto_correct_batch_size` | `50` | Max pages to process per job |

### Worker Schedule

- **Scanner**: Runs every 5 minutes
- **Job Concurrency**: Up to 10 pages processed in parallel per job

## API Examples

### List Correction Rules

```bash
GET /api/spell-check-corrections
Authorization: Bearer <admin_token>
```

Response:
```json
[
  {
    "misspelled_word": "تەبىئەت",
    "corrected_word": "تەبىئەت",
    "auto_apply": true,
    "description": "Common OCR error",
    "created_at": "2026-03-15T10:00:00Z",
    "updated_at": "2026-03-15T10:00:00Z",
    "created_by": 1
  }
]
```

### Get Statistics

```bash
GET /api/spell-check-corrections/stats
Authorization: Bearer <admin_token>
```

Response:
```json
{
  "total_rules": 15,
  "active_rules": 10,
  "total_auto_corrected": 1250,
  "pending_corrections": 42
}
```

### Create Correction Rule

```bash
POST /api/spell-check-corrections
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "misspelled_word": "كىتاب",
  "corrected_word": "كىتاب",
  "auto_apply": true,
  "description": "Book spelling variant"
}
```

### Update Correction Rule

```bash
PATCH /api/spell-check-corrections/كىتاب
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "auto_apply": false
}
```

### Delete Correction Rule

```bash
DELETE /api/spell-check-corrections/كىتاب
Authorization: Bearer <admin_token>
```

## Migration

To enable the auto-correction system:

1. Run the database migration:
   ```bash
   psql -h localhost -U postgres -d kitabim_ai \
     -f packages/backend-core/migrations/030_spell_check_auto_corrections.sql
   ```

2. Restart backend and worker services to load new code

3. Enable the feature:
   ```sql
   UPDATE system_configs
   SET value = 'true'
   WHERE key = 'auto_correct_enabled';
   ```

4. Add correction rules via API

## Monitoring

### Logs

The auto-correction job logs detailed metrics:

```
INFO auto-correction job started page_count=50
INFO loaded correction rules rule_count=10
DEBUG applied auto-correction page_id=12345 original="تەبىئەت" corrected="تەبىئەت"
INFO auto-corrections applied to page page_id=12345 corrections_count=3
INFO auto-correction job completed succeeded=48 failed=2 total_corrections=156
```

### Pipeline Events

Each auto-correction creates a pipeline event:

- `auto_correct_succeeded`: Correction applied successfully
- `auto_correct_failed`: Correction failed with error details

Query events:
```sql
SELECT * FROM pipeline_events
WHERE event_type LIKE 'auto_correct_%'
ORDER BY created_at DESC
LIMIT 100;
```

## Safety Features

1. **Constraint Checks**:
   - Corrected word must be different from misspelled word
   - Words cannot be empty

2. **Manual Override**:
   - `auto_apply` flag allows rules to be defined but not auto-applied
   - Admins can selectively enable rules

3. **Audit Trail**:
   - `auto_corrected_at` timestamp tracks when corrections were applied
   - Pipeline events log all corrections
   - `created_by` tracks who created each rule

4. **Re-indexing**:
   - Pages are marked for re-embedding after correction
   - Word index is invalidated to ensure search accuracy

## Performance Considerations

1. **Batching**: Pages are processed in configurable batches (default: 50)
2. **Parallel Processing**: Up to 10 pages processed concurrently per job
3. **Shared Cache**: Correction rules fetched once per job, not per page
4. **Efficient Queries**: Uses CTEs and indexed lookups to find eligible pages
5. **Offset Preservation**: Corrections applied in reverse order to maintain char offsets

## Future Enhancements

1. **Rule Groups**: Organize corrections by category (OCR errors, spelling variants, etc.)
2. **Confidence Scores**: Track how often each rule is applied successfully
3. **Batch Import**: Upload CSV of correction rules
4. **Regex Support**: Allow pattern-based corrections
5. **Review Queue**: Human review before auto-applying new rules
6. **A/B Testing**: Compare auto-corrected vs manual corrections
