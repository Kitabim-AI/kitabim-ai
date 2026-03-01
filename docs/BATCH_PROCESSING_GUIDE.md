# Batch Processing System Guide

## Overview

The Kitabim AI batch processing system uses Google Gemini's Batch API to process OCR and embeddings at **50% cost savings** compared to real-time API calls. This guide covers architecture, usage, monitoring, and troubleshooting.

---

## Table of Contents

1. [Architecture](#architecture)
2. [How It Works](#how-it-works)
3. [Admin API Endpoints](#admin-api-endpoints)
4. [Monitoring & Observability](#monitoring--observability)
5. [Troubleshooting](#troubleshooting)
6. [Cost Tracking](#cost-tracking)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Batch Processing Flow                     │
└─────────────────────────────────────────────────────────────┘

1. Submission Phase (Hourly Cron)
   ┌──────────────┐
   │ Collect      │──┐
   │ Pending Work │  │
   └──────────────┘  │
                     ▼
   ┌──────────────────────────┐
   │ Generate JSONL           │
   │ Upload to File API       │
   │ Submit to Batch API      │
   └──────────────────────────┘
                     │
                     ▼
   ┌──────────────────────────┐
   │ Store Job in Database    │
   │ - batch_jobs            │
   │ - batch_requests        │
   └──────────────────────────┘

2. Processing Phase (Gemini Backend)
   ┌──────────────┐
   │ Gemini       │
   │ Processes    │──▶ (Takes 0-24 hours)
   │ Batch        │
   └──────────────┘

3. Polling Phase (Configurable interval, default 10 min)
   ┌──────────────────────────┐
   │ Cron runs every minute   │
   │ Early-exit if interval   │
   │ hasn't passed            │
   └──────────────────────────┘
                     │
                     ▼
   ┌──────────────┐
   │ Check Job    │
   │ Status       │
   └──────────────┘
                     │
                     ▼
   ┌──────────────────────────┐
   │ If SUCCEEDED:            │
   │ - Download Results       │
   │ - Parse JSONL Output     │
   │ - Update Pages/Chunks    │
   │ - Cleanup Files          │
   └──────────────────────────┘

4. Finalization Phase (Same interval as polling)
   ┌──────────────┐
   │ Update Page  │
   │ Statuses     │──▶ chunked → indexed
   └──────────────┘
                     │
                     ▼
   ┌──────────────────────────┐
   │ Update Book Statuses     │
   └──────────────────────────┘
```

### Database Schema

#### `batch_jobs` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `job_type` | String | "ocr" or "embedding" |
| `remote_job_id` | String | Gemini API job ID |
| `status` | String | created, submitted, completed, failed |
| `request_count` | Integer | Number of requests in batch |
| `input_file_uri` | String | File API file name (for cleanup) |
| `output_file_uri` | String | Output file URI |
| `created_at` | DateTime | Job creation time |
| `completed_at` | DateTime | Job completion time |
| `error_message` | Text | Error details if failed |

#### `batch_requests` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `batch_job_id` | UUID | Foreign key to batch_jobs |
| `book_id` | String | Book being processed |
| `page_number` | Integer | Page number |
| `request_id` | String | Custom ID in JSONL (e.g., "ocr_book123_5") |
| `status` | String | pending, completed |

---

## How It Works

### Page Status Flow

```
pending
  │
  ├─▶ [Batch Submission] ─▶ ocr_processing
  │                              │
  │                              ├─▶ [OCR Complete] ─▶ ocr_done
  │                                                       │
  │                                                       ├─▶ [Chunking] ─▶ chunked
  │                                                                            │
  │                                                                            ├─▶ [Embedding] ─▶ indexed
  └─▶ error
```

### OCR Batch Processing

**Trigger**: Hourly cron job (`gemini_batch_submission_cron`)

**Steps**:
1. Collect up to 1000 pages with `status = 'pending'`
2. Generate JSONL with OCR requests:
   ```json
   {
     "custom_id": "ocr_book123_5",
     "request": {
       "contents": [{
         "parts": [
           {"file_data": {"mime_type": "application/pdf", "file_uri": "gs://..."}},
           {"text": "Extract and OCR all text from page 5..."}
         ]
       }]
     }
   }
   ```
3. Upload JSONL to Gemini File API
4. Submit batch job
5. Mark pages as `ocr_processing`
6. Store job in database

**Result Processing** (polling cron):
- Download output JSONL when job completes
- Parse results and extract OCR text
- Update page records:
  - `text` = extracted text
  - `status` = "ocr_done"

### Embedding Batch Processing

**Trigger**: Hourly cron job (after OCR chunking)

**Steps**:
1. Run chunking on `ocr_done` pages → creates chunks with `embedding = NULL`
2. Collect up to 2000 chunks where `embedding IS NULL`
3. Generate JSONL with embedding requests:
   ```json
   {
     "custom_id": "embed_chunk_uuid",
     "request": {
       "content": {
         "parts": [{"text": "chunk text here"}]
       }
     }
   }
   ```
4. Submit embedding batch job
5. Store job in database

**Result Processing**:
- Download output when job completes
- Parse embedding vectors
- Update chunk records with embedding vectors

### Finalization

**Trigger**: Every 10 minutes (in polling cron)

**Logic**:
1. Find pages with `status = 'chunked'`
2. Check if all chunks for that page have embeddings
3. If yes → mark page as `indexed`
4. Update book status based on page completion

---

## Admin API Endpoints

All endpoints require **admin authentication**.

Base URL: `/api/admin`

### List Batch Jobs

```http
GET /api/admin/batch-jobs/
```

**Query Parameters**:
- `status` (optional): Filter by status (created, submitted, completed, failed)
- `job_type` (optional): Filter by type (ocr, embedding)
- `limit` (default: 50): Number of results
- `offset` (default: 0): Pagination offset

**Response**:
```json
[
  {
    "id": "uuid",
    "jobType": "ocr",
    "remoteJobId": "batches/...",
    "status": "submitted",
    "requestCount": 1000,
    "createdAt": "2026-02-22T10:00:00Z",
    "completedAt": null,
    "errorMessage": null
  }
]
```

### Get Batch Job Statistics

```http
GET /api/admin/batch-jobs/stats
```

**Response**:
```json
{
  "totalJobs": 45,
  "jobsByStatus": [
    {"status": "completed", "count": 30},
    {"status": "submitted", "count": 5},
    {"status": "failed", "count": 10}
  ],
  "jobsByType": [
    {"jobType": "ocr", "count": 25},
    {"jobType": "embedding", "count": 20}
  ],
  "totalRequestsProcessed": 50000,
  "activeJobsCount": 5
}
```

### Get Job Details

```http
GET /api/admin/batch-jobs/{jobId}
```

**Response**:
```json
{
  "id": "uuid",
  "jobType": "embedding",
  "remoteJobId": "batches/abc123",
  "status": "completed",
  "requestCount": 2000,
  "inputFileUri": "files/xyz789",
  "outputFileUri": "files/output-456",
  "createdAt": "2026-02-22T09:00:00Z",
  "updatedAt": "2026-02-22T10:30:00Z",
  "completedAt": "2026-02-22T10:30:00Z",
  "errorMessage": null
}
```

### Manually Submit OCR Batch

```http
POST /api/admin/batch-jobs/submit-ocr
```

**Query Parameters**:
- `limit` (default: 1000): Max pages to include

**Response**:
```json
{
  "success": true,
  "jobId": "uuid",
  "message": "OCR batch job submitted successfully"
}
```

### Manually Submit Embedding Batch

```http
POST /api/admin/batch-jobs/submit-embedding
```

**Query Parameters**:
- `limit` (default: 2000): Max chunks to include

**Response**:
```json
{
  "success": true,
  "jobId": "uuid",
  "message": "Embedding batch job submitted successfully"
}
```

### Cancel Batch Job

```http
POST /api/admin/batch-jobs/{jobId}/cancel
```

**Response**:
```json
{
  "success": true,
  "message": "Batch job cancelled"
}
```

**Note**: Can only cancel jobs with status `created` or `submitted`.

### Manually Poll Jobs

```http
POST /api/admin/batch-jobs/poll
```

Triggers immediate polling of active batch jobs, bypassing the interval check.

**Use Cases**:
- Force immediate check after submitting a batch
- Debug stuck jobs
- Testing batch completion workflow

**Response**:
```json
{
  "success": true,
  "message": "Batch jobs polled successfully"
}
```

**Note**: This bypasses the `batch_polling_interval_minutes` check and always runs.

### Manually Finalize Pages

```http
POST /api/admin/batch-jobs/finalize
```

Triggers page status finalization (chunked → indexed).

**Response**:
```json
{
  "success": true,
  "message": "Pages finalized successfully"
}
```

---

## Monitoring & Observability

### Key Metrics to Track

1. **Batch Job Success Rate**
   ```sql
   SELECT
     status,
     COUNT(*) as count,
     ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
   FROM batch_jobs
   GROUP BY status;
   ```

2. **Average Turnaround Time**
   ```sql
   SELECT
     job_type,
     AVG(EXTRACT(EPOCH FROM (completed_at - created_at)) / 3600) as avg_hours
   FROM batch_jobs
   WHERE status = 'completed'
   GROUP BY job_type;
   ```

3. **Pending Work Queue Depth**
   ```sql
   -- Pending OCR pages
   SELECT COUNT(*) FROM pages WHERE status = 'pending';

   -- Chunks needing embeddings
   SELECT COUNT(*) FROM chunks WHERE embedding IS NULL;
   ```

4. **Failed Jobs**
   ```sql
   SELECT
     id,
     job_type,
     remote_job_id,
     error_message,
     created_at
   FROM batch_jobs
   WHERE status = 'failed'
   ORDER BY created_at DESC
   LIMIT 10;
   ```

5. **Polling Configuration**
   ```sql
   -- Check current polling settings
   SELECT
     key,
     value,
     CASE
       WHEN key = 'batch_last_polled_at' THEN
         to_timestamp(value::float)::text
       ELSE value
     END as readable_value
   FROM system_configs
   WHERE key IN ('batch_polling_interval_minutes', 'batch_last_polled_at')
   ORDER BY key;
   ```

### Log Monitoring

Key log messages to monitor:

```bash
# Batch submission
kubectl logs -n kitabim -l app=worker | grep "Batch Job submitted"

# Batch completion
kubectl logs -n kitabim -l app=worker | grep "Batch job results processed successfully"

# Model mismatch warnings
kubectl logs -n kitabim -l app=worker | grep "Model mismatch found"

# Errors
kubectl logs -n kitabim -l app=worker | grep "ERROR.*batch"
```

---

## Troubleshooting

### Problem: Polling Not Running

**Symptoms**: Jobs stuck in "submitted", `batch_last_polled_at` not updating

**Diagnosis**:
```bash
# Check polling configuration
psql $DATABASE_URL -c "
  SELECT
    key,
    value,
    CASE
      WHEN key = 'batch_last_polled_at' THEN
        to_timestamp(value::float)::text
      ELSE value
    END as readable
  FROM system_configs
  WHERE key LIKE 'batch_%';
"

# Check worker logs
kubectl logs -n kitabim -l app=worker --since=15m | grep -i "polling\|batch"
```

**Common Causes**:
1. **Cron not scheduled**: Check `worker.py` has `gemini_batch_polling_cron` in cron_jobs
2. **Early-exit always triggering**: Interval too long or `batch_last_polled_at` incorrectly set
3. **Worker not running**: `kubectl get pods -n kitabim -l app=worker`
4. **Exception in polling function**: Check worker logs for tracebacks

**Solutions**:
```bash
# Force immediate poll (bypasses early-exit)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:30800/api/admin/batch-jobs/poll

# Reset last polled time to force next cron to run
psql $DATABASE_URL -c "
  UPDATE system_configs
  SET value = '0'
  WHERE key = 'batch_last_polled_at';
"

# Set more frequent polling temporarily
psql $DATABASE_URL -c "
  UPDATE system_configs
  SET value = '1'
  WHERE key = 'batch_polling_interval_minutes';
"
```

---

### Problem: Jobs Stuck in "submitted" Status

**Symptoms**: Jobs created but never complete (polling IS running)

**Diagnosis**:
```bash
# Check active jobs
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:30800/api/admin/batch-jobs/?status=submitted

# Verify polling is actually running (not early-exiting)
kubectl logs -n kitabim -l app=worker --since=30m | grep "Batch polling cron finished"
```

**Solutions**:
1. Check Gemini API status
2. Manually poll: `POST /api/admin/batch-jobs/poll`
3. Check worker logs for errors during polling
4. Verify network connectivity to Gemini API
5. Check if jobs are actually processing on Gemini side (may take 24 hours)

### Problem: Pages Not Moving from "chunked" to "indexed"

**Symptoms**: Pages stuck at `chunked` status

**Diagnosis**:
```sql
-- Find pages stuck at chunked
SELECT
  p.book_id,
  p.page_number,
  COUNT(c.id) as total_chunks,
  COUNT(c.embedding) as embedded_chunks
FROM pages p
LEFT JOIN chunks c ON p.book_id = c.book_id AND p.page_number = c.page_number
WHERE p.status = 'chunked'
GROUP BY p.book_id, p.page_number
HAVING COUNT(c.id) > COUNT(c.embedding);
```

**Solutions**:
1. Manually trigger finalization: `POST /api/admin/batch-jobs/finalize`
2. Submit embedding batch: `POST /api/admin/batch-jobs/submit-embedding`
3. Check if chunks were created properly

### Problem: Model Mismatch Errors

**Symptoms**: Jobs cancelled with "Model mismatch" error

**Cause**: `.env` model changed while jobs were running

**Solutions**:
1. This is expected behavior - old jobs are cancelled to prevent using wrong model
2. Pages are automatically returned to `pending` status
3. Next batch submission will use correct model
4. No manual intervention needed

### Problem: High Failure Rate

**Diagnosis**:
```bash
# Get failed job details
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:30800/api/admin/batch-jobs/?status=failed&limit=20"
```

**Common Causes**:
1. **API quota exceeded**: Check Gemini API quota
2. **Invalid file URIs**: Verify GCS URIs are accessible
3. **Malformed JSONL**: Check input file format
4. **Network timeouts**: Check worker network connectivity

**Solutions**:
- Review `error_message` in failed jobs
- Check worker logs for stack traces
- Verify Gemini API credentials
- Check GCS permissions

---

## Cost Tracking

### Calculate Cost Savings

**Real-time API Costs** (Gemini 2.0 Flash):
- Text generation: $0.000300 per 1K input tokens
- Embeddings: $0.00003 per 1K input tokens

**Batch API Costs** (50% discount):
- Text generation: $0.000150 per 1K input tokens
- Embeddings: $0.000015 per 1K input tokens

### Example Calculation

For a 100-page book:
- **OCR**: 100 pages × 500 tokens avg = 50K tokens
  - Real-time: 50K × $0.000300 / 1K = **$0.015**
  - Batch: 50K × $0.000150 / 1K = **$0.0075**

- **Embeddings**: 200 chunks × 200 tokens avg = 40K tokens
  - Real-time: 40K × $0.00003 / 1K = **$0.0012**
  - Batch: 40K × $0.000015 / 1K = **$0.0006**

**Total per book**:
- Real-time: $0.0162
- Batch: $0.0081
- **Savings: $0.0081 (50%)**

**At scale** (1000 books/month):
- Batch saves: **$8.10/month**

**At scale** (10,000 books/month):
- Batch saves: **$81/month** or **~$970/year**

### Query Actual Usage

```sql
-- Count requests processed
SELECT
  job_type,
  SUM(request_count) as total_requests,
  COUNT(*) as job_count
FROM batch_jobs
WHERE status = 'completed'
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY job_type;
```

---

## Configuration

### Environment Variables

Required in `.env`:

```bash
# Gemini API
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL_NAME=gemini-2.0-flash-exp
GEMINI_EMBEDDING_MODEL=text-embedding-004

# GCS Storage (for PDF access)
GCS_BUCKET_NAME=your-bucket
GOOGLE_CLOUD_PROJECT=your-project
```

### Cron Job Schedule

Configured in [`app/worker.py`](../packages/backend-core/app/worker.py):

```python
cron_jobs = [
    # Batch Submission: Every hour
    cron(gemini_batch_submission_cron, minute=0),

    # Batch Polling: Every 1 minute with dynamic early-exit
    # Actual interval controlled by system_configs table
    cron(gemini_batch_polling_cron)
]
```

**Dynamic Polling Interval**: The polling cron runs every minute but implements an early-exit pattern based on configurable intervals stored in the `system_configs` table. This allows changing the polling frequency without redeploying the worker.

**System Config Values**:
- `batch_polling_interval_minutes` (default: 10) - Minutes between actual polling attempts
- `batch_last_polled_at` (auto-updated) - Unix timestamp of last poll

**How It Works**:
```python
# Cron runs every minute, but early-exits if interval hasn't passed
async def gemini_batch_polling_cron(ctx):
    # Check interval from system_configs
    interval_minutes = await config_repo.get_value("batch_polling_interval_minutes", "10")
    last_polled = await config_repo.get_value("batch_last_polled_at", "0")

    if elapsed_minutes < interval_minutes:
        return  # Early exit, interval not reached

    # Update timestamp and proceed with polling
    await config_repo.set_value("batch_last_polled_at", str(current_time))
    await batch_service.poll_and_process_jobs()
```

**Adjust Polling Interval** (no deployment needed):
```sql
-- Change polling interval to 5 minutes
INSERT INTO system_configs (key, value, description)
VALUES ('batch_polling_interval_minutes', '5', 'Minutes between batch job polling attempts')
ON CONFLICT (key) DO UPDATE SET value = '5';

-- Change polling interval to 30 minutes
UPDATE system_configs
SET value = '30'
WHERE key = 'batch_polling_interval_minutes';
```

### Batch Limits

Adjust in batch service calls:

```python
# In queue.py
await batch_service.submit_ocr_batch(limit=1000)  # Max OCR pages per batch
await batch_service.submit_embedding_batch(limit=2000)  # Max chunks per batch
```

---

## Early-Exit Pattern for Polling

The batch polling system uses an **early-exit pattern** to allow dynamic configuration without worker restarts:

### How It Works

1. **Cron runs frequently** (every minute) with minimal overhead
2. **Early-exit check** happens immediately:
   ```python
   if elapsed_time < configured_interval:
       return  # Exit immediately, no work done
   ```
3. **Only when interval passes** does actual polling occur

### Benefits

✅ **Zero-downtime configuration** - Change polling interval without restart
✅ **Consistent timing** - No drift from cron schedule variations
✅ **Easy debugging** - Manually trigger with `POST /poll` endpoint
✅ **Resource efficient** - Early exits are extremely cheap

### Configuration Options

| Interval | Use Case | Pros | Cons |
|----------|----------|------|------|
| 1 minute | Testing, debugging | Fastest feedback | High API call volume |
| 5 minutes | Production (fast) | Quick turnaround | Moderate API calls |
| 10 minutes | **Default production** | Balanced | Good for most cases |
| 30 minutes | Low-priority batches | Minimal overhead | Slower feedback |
| 60 minutes | Overnight batches | Lowest cost | Very slow feedback |

### Monitoring Early Exits

```bash
# Worker logs show early exits (no output if exiting early)
kubectl logs -n kitabim -l app=worker --since=5m | grep "Batch polling cron"

# If you see this log, polling actually ran:
# {"message": "Batch polling cron finished"}

# If you don't see it, the cron early-exited
```

---

## Best Practices

1. **Monitor Queue Depth**: Keep pending queues under 10,000 items
2. **Review Failed Jobs Weekly**: Check for patterns in failures
3. **Use Admin Endpoints Sparingly**: Let cron jobs handle normal flow
4. **Don't Cancel Jobs Unnecessarily**: Gemini charges for partial processing
5. **Archive Old Jobs**: Clean up completed jobs older than 90 days
6. **Adjust Polling Interval Dynamically**: Use system_configs instead of hardcoding
7. **Use Manual Poll for Debugging**: Bypass interval check with `/poll` endpoint

---

## Testing

Run batch processing tests:

```bash
# All batch tests
pytest packages/backend-core/tests/test_batch*.py -v

# Specific test suites
pytest packages/backend-core/tests/test_batch_client.py -v
pytest packages/backend-core/tests/test_batch_repositories.py -v
pytest packages/backend-core/tests/test_batch_service.py -v
```

---

## Related Documentation

- [Gemini Batch API Implementation Plan](./gemini_batch_api_implementation_plan.md)
- [Book Processing Flow](./book_processing_diagram.md)
- [Database Cleanup Analysis](../DATABASE_CLEANUP_ANALYSIS.md)

---

**Last Updated**: 2026-02-22
