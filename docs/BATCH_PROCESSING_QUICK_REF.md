# Batch Processing Quick Reference

Quick reference for common batch processing operations and debugging.

---

## Common Operations

### Check System Status

```bash
# View active batch jobs
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/?status=submitted"

# Get statistics
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/stats"

# Check current polling interval
psql $DATABASE_URL -c "SELECT * FROM system_configs WHERE key = 'batch_polling_interval_minutes';"

# Check last poll time
psql $DATABASE_URL -c "SELECT key, value, to_timestamp(value::float) as last_polled FROM system_configs WHERE key = 'batch_last_polled_at';"

# Check worker logs
kubectl logs -n kitabim -l app=worker --tail=50 | grep batch
```

### Force Batch Submission

```bash
# Submit OCR batch manually
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/submit-ocr?limit=500"

# Submit embedding batch manually
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/submit-embedding?limit=1000"
```

### Trigger Processing

```bash
# Poll active jobs immediately (bypasses interval check)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/poll"

# Finalize indexed pages
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/finalize"

# Change polling interval (no restart needed)
psql $DATABASE_URL -c "
  INSERT INTO system_configs (key, value, description)
  VALUES ('batch_polling_interval_minutes', '5', 'Minutes between batch job polling')
  ON CONFLICT (key) DO UPDATE SET value = '5';
"
```

### Cancel Stuck Job

```bash
# Cancel a specific job
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/{JOB_ID}/cancel"
```

---

## SQL Queries

### Check Queue Depths

```sql
-- Pending OCR pages
SELECT COUNT(*) as pending_ocr FROM pages WHERE status = 'pending';

-- Pages in OCR processing
SELECT COUNT(*) as ocr_processing FROM pages WHERE status = 'ocr_processing';

-- Chunks needing embeddings
SELECT COUNT(*) as need_embeddings FROM chunks WHERE embedding IS NULL;

-- Pages ready for chunking
SELECT COUNT(*) as ready_for_chunking FROM pages WHERE status = 'ocr_done';
```

### Find Stuck Items

```sql
-- Pages stuck in ocr_processing for > 48 hours
SELECT book_id, page_number, status, last_updated
FROM pages
WHERE status = 'ocr_processing'
  AND last_updated < NOW() - INTERVAL '48 hours'
ORDER BY last_updated DESC;

-- Books with mixed page statuses
SELECT
  b.id,
  b.title,
  b.status,
  COUNT(DISTINCT p.status) as distinct_statuses,
  string_agg(DISTINCT p.status, ', ') as page_statuses
FROM books b
JOIN pages p ON b.id = p.book_id
GROUP BY b.id, b.title, b.status
HAVING COUNT(DISTINCT p.status) > 1;
```

### Recent Batch Jobs

```sql
-- Last 10 batch jobs
SELECT
  id,
  job_type,
  status,
  request_count,
  created_at,
  completed_at,
  EXTRACT(EPOCH FROM (completed_at - created_at))/3600 as hours_to_complete
FROM batch_jobs
ORDER BY created_at DESC
LIMIT 10;

-- Failed jobs in last 24 hours
SELECT
  id,
  job_type,
  remote_job_id,
  error_message,
  created_at
FROM batch_jobs
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

---

## Troubleshooting Flowchart

```
┌─────────────────────────────────┐
│ Is batch processing working?    │
└────────────┬────────────────────┘
             │
             ├─ YES ──▶ Monitor normally
             │
             └─ NO
                 │
                 ▼
┌───────────────────────────────────────┐
│ Are there pending pages/chunks?       │
└────────────┬──────────────────────────┘
             │
             ├─ NO ──▶ System is idle (OK)
             │
             └─ YES
                 │
                 ▼
┌───────────────────────────────────────┐
│ Are batch jobs being created hourly?  │
└────────────┬──────────────────────────┘
             │
             ├─ NO ──▶ Check worker cron jobs
             │         kubectl logs -l app=worker
             │
             └─ YES
                 │
                 ▼
┌───────────────────────────────────────┐
│ Is polling cron running?              │
│ Check: batch_last_polled_at updates   │
└────────────┬──────────────────────────┘
             │
             ├─ NO ──▶ Check early-exit interval
             │         Set interval to 1 min
             │         Reset last_polled_at to 0
             │
             └─ YES
                 │
                 ▼
┌───────────────────────────────────────┐
│ Are jobs completing?                  │
└────────────┬──────────────────────────┘
             │
             ├─ NO ──▶ Check job status in Gemini
             │         Look for error_message
             │         May take up to 24 hours
             │
             └─ YES
                 │
                 ▼
┌───────────────────────────────────────┐
│ Are pages being updated?              │
└────────────┬──────────────────────────┘
             │
             ├─ NO ──▶ Check result processing
             │         Manual: POST /poll
             │
             └─ YES ──▶ Check finalization
                        Manual: POST /finalize
```

---

## Emergency Procedures

### Reset Stuck Pages

```sql
-- CAUTION: This returns stuck pages to pending status
-- Only use if you're sure they're truly stuck

BEGIN;

-- Reset pages stuck in ocr_processing for > 72 hours
UPDATE pages
SET status = 'pending', updated_by = 'manual_reset'
WHERE status = 'ocr_processing'
  AND last_updated < NOW() - INTERVAL '72 hours';

-- Verify before committing
SELECT * FROM pages WHERE updated_by = 'manual_reset';

-- If OK:
COMMIT;
-- If not OK:
ROLLBACK;
```

### Clean Up Failed Jobs

```sql
-- Delete old failed jobs (keeps last 30 days)
DELETE FROM batch_jobs
WHERE status = 'failed'
  AND created_at < NOW() - INTERVAL '30 days';
```

### Retry Failed Pages

```sql
-- Find books with error pages
SELECT
  book_id,
  COUNT(*) as error_pages
FROM pages
WHERE status = 'error'
GROUP BY book_id
ORDER BY error_pages DESC;

-- Reset error pages to retry OCR
UPDATE pages
SET status = 'pending',
    error = NULL,
    updated_by = 'manual_retry'
WHERE book_id = 'YOUR_BOOK_ID'
  AND status = 'error';
```

---

## Performance Tuning

### Adjust Batch Sizes

Edit `packages/backend-core/app/queue.py`:

```python
# Larger batches = fewer API calls but longer processing
await batch_service.submit_ocr_batch(limit=2000)  # Default: 1000

# Smaller batches = faster feedback but more overhead
await batch_service.submit_embedding_batch(limit=1000)  # Default: 2000
```

### Adjust Polling Frequency

**No deployment needed** - polling interval is controlled via `system_configs` table:

```sql
-- More frequent polling (5 minutes) = faster results but more API calls
UPDATE system_configs
SET value = '5'
WHERE key = 'batch_polling_interval_minutes';

-- Less frequent polling (30 minutes) = lower overhead
UPDATE system_configs
SET value = '30'
WHERE key = 'batch_polling_interval_minutes';

-- Verify current setting
SELECT * FROM system_configs WHERE key = 'batch_polling_interval_minutes';
```

**How it works**:
- Cron runs every minute but implements early-exit pattern
- Checks `batch_polling_interval_minutes` from system_configs
- Only proceeds if enough time has elapsed since `batch_last_polled_at`
- No worker restart needed when changing interval

### Optimize Submission Frequency

**Requires deployment** - submission frequency is hardcoded in worker cron schedule:

Edit `packages/backend-core/app/worker.py`:

```python
# More frequent submission = lower latency
cron(gemini_batch_submission_cron, minute={0, 30})  # Every 30 min

# Less frequent = larger batches
cron(gemini_batch_submission_cron, minute=0, hour={0, 6, 12, 18})  # Every 6 hours
```

Then redeploy:
```bash
./rebuild-and-restart.sh worker
```

---

## Monitoring Checklist

Daily:
- [ ] Check failed jobs count
- [ ] Verify queue depths are reasonable
- [ ] Check for stuck pages (> 48 hours in processing)
- [ ] Verify polling interval is appropriate for current load

Weekly:
- [ ] Review average turnaround times
- [ ] Check success rate by job type
- [ ] Review error messages for patterns
- [ ] Clean up old completed jobs
- [ ] Verify `batch_last_polled_at` is updating correctly

Monthly:
- [ ] Calculate actual cost savings
- [ ] Review and optimize batch sizes
- [ ] Archive old batch job records
- [ ] Evaluate if polling interval should be adjusted
- [ ] Review system_configs for stale values

---

## Key Files

| File | Purpose |
|------|---------|
| `app/services/batch_service.py` | Main batch orchestration logic |
| `app/services/gemini_batch_client.py` | Direct Gemini API client |
| `app/db/repositories/batch_jobs.py` | Database operations for batch jobs |
| `app/api/endpoints/batch_jobs.py` | Admin API endpoints |
| `app/queue.py` | Cron job definitions |
| `app/worker.py` | Worker configuration |

---

## Useful kubectl Commands

```bash
# Watch worker logs in real-time
kubectl logs -n kitabim -l app=worker -f | grep batch

# Check worker pod status
kubectl get pods -n kitabim -l app=worker

# Restart worker to apply config changes
kubectl rollout restart deployment/worker -n kitabim

# Check cron job execution
kubectl logs -n kitabim -l app=worker --since=1h | grep "Batch submission cron"
kubectl logs -n kitabim -l app=worker --since=1h | grep "Batch polling cron"
```

---

## Contact

For issues not covered here, check:
- Full documentation: [`BATCH_PROCESSING_GUIDE.md`](./BATCH_PROCESSING_GUIDE.md)
- Implementation plan: [`gemini_batch_api_implementation_plan.md`](./gemini_batch_api_implementation_plan.md)
