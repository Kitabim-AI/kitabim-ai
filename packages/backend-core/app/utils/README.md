# Utilities (`app/utils`)

## Overview
Provides shared utility functions, concurrency controls, text processing, structured logging, distributed locking, rate limiting, circuit breakers, and privacy helpers.

## Interface
- `[text.py:normalize_uyghur_chars]` — Normalizes Arabic/Uyghur character variants and removes invisible control characters.
- `[text.py:clean_uyghur_text]` — Strips noise, isolated headers, and page numbers from extracted OCR text.
- `[text.py:is_toc_page]` / `[text.py:parse_toc_entries]` — Detects table-of-contents pages and parses title/page number mappings.
- `[text.py:is_degenerate_ocr_output]` — Detects repetitive or pathological text loops in OCR outputs.
- `[circuit_breaker.py:CircuitBreaker]` — Async circuit breaker protecting external service calls (e.g. Gemini API) with Redis-coordinated state.
- `[circuit_breaker.py:CircuitBreakerOpen]` — Exception raised when operations are attempted while a circuit breaker is in an open state.
- `[redis_lock.py:RedisLock]` — Distributed Redis lock ensuring single-process execution for critical operations.
- `[redis_lock.py:MultiPageLock]` — Multi-key distributed lock context manager locking batches of page records concurrently.
- `[rate_limiter.py:RedisRateLimiter]` — Sliding-window rate limiter backing API throttling and quota controls.
- `[lru_cache.py:LocalLRUCache]` — Thread-safe in-memory cache with configurable maximum capacity and time-to-live expiration.
- `[observability.py:configure_logging]` — Configures structured JSON logging with request tracing.
- `[observability.py:track_request_id]` — Async context manager propagating request trace identifiers.
- `[observability.py:patch_arq_enqueue_job]` — Monkey-patches ARQ job dispatch to pass distributed trace context to worker queues.
- `[security.py:hash_ip_address]` — Hashes client IP addresses with SHA-256 for privacy-preserving rate limit tracking.
- `[markdown.py:normalize_markdown]` / `[markdown.py:strip_markdown]` — Markdown formatting normalization and plain-text stripping.
- `[categories.py:normalize_category]` / `[categories.py:normalize_categories]` — Canonicalizes category labels across books.
- `[citation_fixer.py:fix_malformed_citations]` — Fixes bracket formatting anomalies in generated RAG citations.
- `[errors.py:record_book_error]` — Records book processing pipeline failures to database and error logs.

## Invariants
- `[security.py:hash_ip_address]` — Anonymizes IP addresses deterministically using SHA-256 without persisting raw IP strings.
- `[circuit_breaker.py:CircuitBreaker]` — Trips to `OPEN` state upon reaching `failure_threshold` within sliding window; rejects calls until `recovery_timeout` elapses.
- `[text.py:is_degenerate_ocr_output]` — Flags OCR strings when repetitive n-gram frequency exceeds acceptable linguistic variance.

## Side Effects
- Acquires, refreshes, and releases distributed lock keys in Redis via `RedisLock`.
- Increments sliding-window request timestamps and counters in Redis.
- Configures process-wide Python `logging` handlers and formatting.

## Verification
- Run: `pytest packages/backend-core/tests`
