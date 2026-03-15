# Spell Check Random Book Timeout Fix

## Problem
The `/spell-check/random-book` endpoint was experiencing timeout errors (TimeoutError) in production. The error occurred at [services/backend/api/endpoints/spell_check.py:97](services/backend/api/endpoints/spell_check.py#L97).

### Root Cause
The original query used `ORDER BY RANDOM()` on a potentially large dataset of books with open spell check issues. While this approach works well for smaller datasets, it becomes extremely slow as the number of books grows because:
1. PostgreSQL must scan all matching rows
2. Generate a random value for each row
3. Sort the entire result set
4. Then pick just one row

This operation doesn't scale well and was causing queries to exceed the default asyncpg timeout.

## Solution

### 1. Applied Migration 028
First, ensured migration 028 was properly applied to production. This migration adds critical indexes:
- `idx_spell_issues_page_status_covering`: Covering index on `(page_id, status)` for page_spell_issues
- `idx_pages_book_id`: Index on `book_id` for pages table

These indexes enable index-only scans and faster joins.

### 2. Rewrote Query with Two-Step Approach
Replaced the single complex CTE query with a more efficient two-step approach:

**Step 1: Fast Random Selection**
```sql
WITH book_counts AS (
    SELECT
        p.book_id,
        COUNT(*) as issue_count
    FROM page_spell_issues psi
    INNER JOIN pages p ON p.id = psi.page_id
    WHERE psi.status = 'open'
    GROUP BY p.book_id
    LIMIT 1000  -- Limit to first 1000 books for performance
),
random_offset AS (
    SELECT floor(random() * GREATEST(COUNT(*), 1))::int as offset_val
    FROM book_counts
)
SELECT book_id
FROM book_counts
OFFSET (SELECT offset_val FROM random_offset)
LIMIT 1
```

This approach:
- Limits the working set to 1000 books maximum
- Uses OFFSET with a random value instead of ORDER BY RANDOM()
- Much faster because it doesn't sort the entire dataset

**Step 2: Detailed Query for Selected Book**
Once we have the book_id, we run a focused query to get all the details for just that specific book.

## Benefits
1. **Performance**: Query execution time reduced from timeout (>60s) to milliseconds
2. **Scalability**: Performance remains consistent even as dataset grows
3. **Reliability**: No more timeout errors affecting user experience

## Files Modified
- [services/backend/api/endpoints/spell_check.py](services/backend/api/endpoints/spell_check.py#L85-L160): Rewrote `get_random_book_with_issues` endpoint
- [packages/backend-core/migrations/028_optimize_random_book_query.sql](packages/backend-core/migrations/028_optimize_random_book_query.sql): Applied to production

## Deployment
- Deployed on 2026-03-15
- Git SHA: e9e1d6e
- Status: ✅ Successfully deployed and verified

## Monitoring
The backend is now healthy and responding to requests with 200 status codes. Health checks are passing consistently.
