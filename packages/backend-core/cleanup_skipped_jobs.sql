-- Clean up old skipped jobs caused by circuit breaker
-- These jobs are >1 day old and will never complete
-- Deleting them allows the watchdog to create fresh jobs

BEGIN;

-- Show what we're about to delete
SELECT
    job_key,
    status,
    created_at,
    last_error
FROM jobs
WHERE status = 'skipped'
  AND created_at < NOW() - INTERVAL '1 day'
ORDER BY created_at;

-- Delete old skipped jobs
-- The watchdog will create new jobs for these books on the next run
DELETE FROM jobs
WHERE status = 'skipped'
  AND created_at < NOW() - INTERVAL '1 day';

-- Show summary
SELECT
    'Deleted' as action,
    COUNT(*) as count
FROM jobs
WHERE FALSE; -- This query shows 0 because we already deleted them above

COMMIT;

-- Verify: Check remaining jobs by status
SELECT status, COUNT(*) as count
FROM jobs
GROUP BY status
ORDER BY status;
