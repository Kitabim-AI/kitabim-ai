# Pipeline Statistics Caching Fix

## Problem
Pipeline statistics were being cached for 10 minutes on the admin management page, but the statistics change every few seconds during book processing. This caused stale data to be displayed despite the frontend polling every 5 seconds for updates.

## Solution: Dual-Track Caching Strategy

### Approach
We implemented a dual-track caching system that separates **stable metadata** from **rapidly-changing statistics**:

1. **Metadata Cache** (20 minutes TTL)
   - Book list (title, author, volume, categories, etc.)
   - Total counts
   - Pagination info
   - These rarely change, so longer caching is safe

2. **Fresh Stats** (no caching)
   - Pipeline progress counts (OCR, chunking, embedding, etc.)
   - Active/failed page counts
   - Summary status
   - Always fetched from database on every request

### How It Works

#### First Request (Cache Miss)
```
Admin visits page with includeStats=true
  ↓
No metadata cache exists
  ↓
Query database for books + stats
  ↓
Cache metadata-only version (no stats)
  ↓
Return full result with stats
```

#### Subsequent Requests (Cache Hit)
```
Admin polls every 5 seconds
  ↓
Metadata cache HIT
  ↓
Load cached books, counts from Redis
  ↓
Query ONLY fresh stats from PostgreSQL (fast!)
  ↓
Merge cached metadata + fresh stats
  ↓
Return combined result with real-time stats
```

### Performance Impact

**Before:**
- Cached response: ~0ms (but STALE data - could be 10 min old)
- Cache miss: ~200-500ms (full query + stats)

**After:**
- Metadata hit + stats query: ~5-10ms (with new index)
- Cache miss: ~200-500ms (same as before)
- **Stats are ALWAYS accurate and real-time**

### Database Optimization

Added composite index to speed up stats aggregation:

```sql
CREATE INDEX idx_pages_book_milestones
ON pages (
    book_id,
    ocr_milestone,
    chunking_milestone,
    embedding_milestone,
    word_index_milestone,
    spell_check_milestone
);
```

This allows PostgreSQL to use index-only scans for the `COUNT(CASE...)` queries in `get_batch_stats()`.

## Implementation Details

### Files Modified

1. **[services/backend/api/endpoints/books.py](../services/backend/api/endpoints/books.py)**
   - Lines 143-185: Dual-track cache lookup logic
   - Lines 188-209: Early return with cached metadata + fresh stats
   - Lines 386-417: Dual-track cache storage logic

2. **[packages/backend-core/migrations/024_add_stats_composite_index.sql](../packages/backend-core/migrations/024_add_stats_composite_index.sql)** (new)
   - Composite index for stats query optimization

### Key Code Changes

**Cache Key Generation:**
```python
# Separate cache keys for metadata vs. full results
cache_params_no_stats = {**cache_params_base, "includeStats": False}
metadata_cache_key = KEY_BOOKS_LIST.format(hash=md5(cache_params_no_stats))
```

**Metadata Reuse:**
```python
if cached_metadata and includeStats:
    cached_books = [Book.model_validate(b) for b in cached_metadata["books"]]
    batch_stats = await repo.get_batch_stats(book_ids)  # Fresh stats only!
    # Merge and return immediately
```

**Selective Caching:**
```python
if includeStats:
    # Cache metadata-only (no stats)
    await cache_service.set(metadata_cache_key, metadata_result, ttl=1200)
    # Do NOT cache full stats result
else:
    # Normal caching for non-admin views
    await cache_service.set(cache_key, result, ttl=600)
```

## Testing

### Manual Testing Steps

1. **Verify fresh stats on admin page:**
   ```bash
   # Upload a book and watch the pipeline progress
   # Stats should update every 5 seconds without stale data
   ```

2. **Check cache behavior:**
   ```bash
   # First request should cache metadata
   redis-cli KEYS "books:list:*"

   # Verify metadata cache TTL is 20 min (1200s)
   redis-cli TTL "books:list:<hash>"
   ```

3. **Performance validation:**
   ```bash
   # Monitor query performance
   kubectl logs -n kitabim deployment/backend | grep "get_batch_stats"
   ```

### Expected Behavior

- ✅ Admin page shows real-time pipeline progress
- ✅ Stats update every 5 seconds without delay
- ✅ Book list doesn't re-query on every poll
- ✅ Cache hit ratio remains high for metadata
- ✅ Stats query completes in <10ms

## Rollout

### Migration Steps

1. **Apply database migration:**
   ```bash
   # The index will be created automatically on next deployment
   kubectl exec -it deployment/backend -- python -m alembic upgrade head
   ```

2. **Clear existing caches (optional):**
   ```bash
   # If you want immediate effect, clear old cached results
   kubectl exec -it deployment/redis -- redis-cli FLUSHPATTERN "books:list:*"
   ```

3. **Monitor performance:**
   ```bash
   # Watch for slow query logs
   kubectl logs -n kitabim -f deployment/backend | grep -i "slow"
   ```

## Rollback Plan

If issues occur:

1. **Revert code changes:**
   ```bash
   git revert <commit-hash>
   ```

2. **Drop index (if causing problems):**
   ```sql
   DROP INDEX IF EXISTS idx_pages_book_milestones;
   ```

3. **Restart backend to clear in-memory state:**
   ```bash
   kubectl rollout restart deployment/backend
   ```

## Future Improvements

1. **WebSocket-based real-time updates** instead of polling
2. **Server-Sent Events (SSE)** for push-based stats
3. **GraphQL subscriptions** for reactive data
4. **Materialized view** with trigger-based updates (if stats query becomes bottleneck)

## References

- Original issue: Stale statistics on admin management page
- Related: Frontend polling in [useBooks.ts:33-59](../apps/frontend/src/hooks/useBooks.ts#L33-L59)
- Stats query: [books.py:232-296](../packages/backend-core/app/db/repositories/books.py#L232-L296)
