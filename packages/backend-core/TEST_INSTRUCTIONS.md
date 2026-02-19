# 🧪 Testing the Watchdog Fix

## What We're Testing

**Problem Before:** Watchdog re-enqueued pending books every 15 minutes, even if they were already being processed → infinite loop ♾️

**Fix:** Watchdog now checks job status and skips books that are already queued/processing ✅

## Test Setup

- **Worker Concurrency:** 2 jobs (max_jobs=2) - keeps queue visible
- **Test Duration:** 20 minutes (covers 2 watchdog cycles)
- **What to Watch:** Watchdog logs showing SKIP behavior

---

## Step-by-Step Test

### 1. Check Current State

```bash
cd /Users/Omarjan/Projects/kitabim-ai/packages/backend-core
python3 diagnose_books.py
```

**Expected:** ~30 pending books

### 2. Start Worker with Monitoring

Open **TWO terminals**:

**Terminal 1:** Run the worker
```bash
cd /Users/Omarjan/Projects/kitabim-ai/packages/backend-core
arq app.worker.WorkerSettings
```

**Terminal 2:** Monitor watchdog activity
```bash
cd /Users/Omarjan/Projects/kitabim-ai/packages/backend-core
./monitor_watchdog.sh
```

### 3. Observe Cycle 1 (Startup - t=0)

**Expected logs:**
```
⚠️ Watchdog: Found 30 stale books. Checking job status...
🔄 Book XXX: Job skipped 45m ago. Circuit breaker likely recovered. Will re-enqueue.
🚑 Rescuing book XXX...
✅ Book XXX successfully re-queued.
📊 Watchdog summary: 30 books re-queued, 0 skipped
```

**What this means:** All 30 books enqueued (expected - they have old jobs)

### 4. Wait and Observe Job Processing

You'll see jobs being processed 2 at a time:
```
→ process_pdf_job(book_id='XXX')
  PDF missing locally, downloading from storage
  File downloaded from GCS
  File uploaded to GCS
← process_pdf_job ●
```

### 5. Observe Cycle 2 (t=15 minutes)

**Expected logs (THE PROOF!):**
```
⚠️ Watchdog: Found 30 stale books. Checking job status...
⏸️  Skipping book XXX: Job recently created (2.3m ago) with status 'in_progress'
⏸️  Skipping book YYY: Job recently created (3.1m ago) with status 'queued'
📊 Watchdog summary: 0 books re-queued, 30 skipped (waiting for existing job to complete)
```

**What this means:** 🎉 **FIX WORKING!** Watchdog is NOT re-enqueueing!

---

## ✅ Success Criteria

| Metric | Before Fix | After Fix | Status |
|--------|-----------|-----------|---------|
| Cycle 1 enqueued | 30 | 30 | ✅ Expected |
| Cycle 2 enqueued | 30 ❌ | 0 ✅ | **TEST THIS** |
| Cycle 2 skipped | 0 | 30 | **PROOF!** |

---

## 🐛 Troubleshooting

**If Cycle 2 still enqueues books:**
- Check the maintenance.py file has the fix
- Verify jobs have status 'queued' or 'in_progress'
- Check job age is < 5 minutes

**If no pending books found:**
- Jobs completed (good!)
- Run `python3 diagnose_books.py` to confirm

**If circuit breaker triggers again:**
- Check Gemini API key/quota
- Review error logs for API failures

---

## 📊 After Test - Analysis

Run diagnostics after 20 minutes:

```bash
python3 diagnose_books.py
python3 inspect_jobs.py
```

**Expected:**
- Pending books: decreasing (being processed)
- Jobs with status 'succeeded': increasing
- No infinite re-enqueueing in logs ✅
