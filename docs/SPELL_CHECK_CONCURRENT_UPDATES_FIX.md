# Spell Check Concurrent Updates Fix

## Problem

The `index_book_words` function was timing out in production with these errors:

**First error (timeout):**
```
asyncpg.exceptions.QueryCanceledError: canceling statement due to statement timeout
```

**Second error (transaction abort):**
```
asyncpg.exceptions.InFailedSQLTransactionError: current transaction is aborted, commands ignored until end of transaction block
```

The timeout was occurring on the `ON CONFLICT ... DO UPDATE` query that updates word occurrence counts in the `book_word_index` table.

### Root Cause

When multiple workers process pages from the same book simultaneously, they all try to update the same `(book_id, word_id)` rows in `book_word_index`. This causes:

1. **Lock contention**: PostgreSQL row-level locks block concurrent updates
2. **Timeout escalation**: Workers wait for locks, eventually hitting the statement timeout
3. **Transaction abort**: When a timeout occurs, PostgreSQL aborts the entire transaction
4. **Cascading failure**: Spell check job fails even though only the word indexing timed out

## Solution

Implemented a **savepoint-based approach** to isolate the word indexing from the rest of the spell check:

### 1. Smaller Batches

Reduced batch size from 500 to 100 words to minimize lock duration:

```python
BATCH_SIZE = 100  # Smaller = less time holding locks
```

### 2. Nested Transaction (Savepoint)

Wrap word indexing in a savepoint so failures don't abort the entire transaction:

```python
index_succeeded = False
try:
    # Create a savepoint before the potentially failing operation
    async with session.begin_nested():
        await index_book_words(session, page.book_id, word_freq)
        index_succeeded = True
except Exception as e:
    # Savepoint automatically rolled back on exception
    # Log the error but don't fail the entire spell check
    logger.warning(f"Failed to index words for book {page.book_id}: {repr(e)}")
```

### 3. Graceful Degradation

If word indexing fails, we skip the `unique_to_book` check (which depends on the word index) but still complete the spell check with OCR corrections:

```python
if index_succeeded:
    unique_to_book = await find_words_unique_to_book(session, page.book_id, no_ocr_unknown, cache=cache)
else:
    # Skip unique_to_book check if indexing failed
    unique_to_book = set()
```

## Benefits

1. **No spell check failures**: Word indexing timeouts no longer fail the entire job
2. **Graceful degradation**: Spell check still reports OCR corrections even if indexing fails
3. **Transaction isolation**: Savepoints prevent transaction abort from propagating
4. **Reduced lock contention**: Smaller batches hold locks for less time

## Trade-offs

- **Incomplete word index**: If indexing fails, the book_word_index may be incomplete
- **Fewer issues reported**: Pages processed when indexing fails won't report "unique to book" issues
- **Eventual consistency**: Word index will be updated on retry or next spell check run

## How Savepoints Work

PostgreSQL savepoints create a "checkpoint" in a transaction:
- `BEGIN NESTED` creates a savepoint
- If an error occurs, only changes since the savepoint are rolled back
- The outer transaction can continue normally
- This prevents `InFailedSQLTransactionError` from aborting the entire transaction

## Testing

To verify the fix works:

1. Monitor logs for `InFailedSQLTransactionError` - should disappear
2. Check for WARNING logs about failed word indexing - these are expected under high load
3. Verify spell check jobs complete successfully even when word indexing times out
4. Confirm OCR corrections are still being reported

## Files Changed

- [`packages/backend-core/app/services/spell_check_service.py:292-351`](../packages/backend-core/app/services/spell_check_service.py#L292-L351): Updated `index_book_words` to use smaller batches
- [`packages/backend-core/app/services/spell_check_service.py:553-576`](../packages/backend-core/app/services/spell_check_service.py#L553-L576): Wrapped word indexing in savepoint with graceful degradation
