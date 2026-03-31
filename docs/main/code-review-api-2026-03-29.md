# API Code Review — 2026-03-29

**Branch:** main
**Verdict:** Request changes

---

## Issues

### `services/backend/api/endpoints/auth.py`

- **[blocking]** Lines 636, 648 — XSS in OAuth HTML responses. `message` is interpolated directly into the HTML body (`<div class="message">{message}</div>`) and into a JS string literal (`error: "{message}"`). The `message` value can include the OAuth provider's raw `?error=` query parameter (line 175). Escape with `html.escape(message)` before interpolating into HTML/JS.

- **[suggestion]** Lines 174, 188, 196, 200, 202, 235, 240 — `logger.info(f"...")` / `logger.error(f"...")` used instead of `log_json(logger, level, "msg", key=value)`. This breaks structured JSON logging. Replace all f-string logger calls in this file with `log_json`.

- **[suggestion]** Line 240 — `client_ip` is logged raw (`from {client_ip}`) before being passed to `update_user_login`. The IP is hashed in the service layer, but the log itself emits the raw IP. Use `hash_ip_if_present(client_ip)` or omit it from the log.

---

### `services/backend/api/endpoints/books.py`

- **[blocking]** Line 890 — `GET /stats` is unreachable. `@router.get("/{book_id}")` is registered at line 750 and matches before `@router.get("/stats")` at line 890. Any request to `/api/books/stats` hits `get_book` with `book_id="stats"` and returns 404. Move `get_book_stats` above the `/{book_id}` route.

- **[blocking]** Line 308 — `BookDB.visibility is None` is a Python identity check, always `False` at parse time. No SQL `IS NULL` clause is generated. Books with `NULL` visibility are excluded from all guest queries. Replace with `BookDB.visibility.is_(None)` (already used correctly in the `groupByWork` count at line 355).

- **[blocking]** Lines 1228, 1284, 1621, 1892, 1983 — Cache invalidation uses bare key `f"book:{book_id}"` but `get_book` caches with scoped keys like `book:{book_id}:public` and `book:{book_id}:staff` (via `get_book_cache_key`). After reprocess, update, or delete operations, stale data remains in cache indefinitely. Use `cache_service.delete_pattern(f"book:{book_id}:*")` at every invalidation site.

- **[blocking]** Lines 524, 529, 856 — `cache_service.set()` is called with dicts containing Python `datetime` objects (from ORM models and `model_dump()` without `mode='json'`). `cache_service._serialize_value` calls `model_dump()` (not `model_dump(mode='json')`), leaving `datetime` objects unconverted. `json.dumps()` then raises `TypeError`, which is caught silently — the cache never actually stores book data. Fix: use `model_dump(mode='json')` in `_serialize_value` inside `cache_service.py` (or at each call site).

- **[blocking]** Lines 103, 376, 409, 427, 475, 646, 712, 1198, 1256, 1312, 1326, 1371, 1409, 1464, 1528, 1539, 1581, 1586, 1598, 1660, 1677 — `session.execute()`, `session.add()`, and `session.flush()` are called directly in endpoint functions, bypassing the repository layer. Per the architecture rules, all DB access must go through repository methods. This is a pervasive violation; the most critical cases (reprocess endpoints, update_page_text, bulk_reset) should be moved to service or repository methods.

- **[suggestion]** Line 175 — `HTTPException(detail="Invalid image file")` is a hardcoded English string. Use `t("errors.invalid_image_file")`.

- **[suggestion]** Line 880 — `HTTPException(detail="Book not found")` is hardcoded English. Use `t("errors.book_not_found")`.

- **[suggestion]** Line 1506 — `HTTPException(detail="system_config 'gemini_embedding_model' is not set")` is hardcoded. Add an i18n key or at minimum use a constant.

- **[suggestion]** Line 2081 — `HTTPException(detail=str(exc))` on download failure leaks raw exception internals (file paths, storage errors) to the client. Use a generic i18n error.

- **[suggestion]** Lines 940, 947 — `logger.info(f"DEBUG: ...")` left in `get_book_content`. These log potentially large content lengths on every call. Remove or demote to `DEBUG` level with `log_json`.

- **[suggestion]** Lines 1596, 1959, 1964, 1968, 1972, 2011, 2080 — f-string logger calls. Replace with `log_json`.

- **[suggestion]** Line 744 — `ttl=30` hardcoded in `suggest_books`. Add `cache_ttl_suggestions` to `Settings` in `core/config.py`.

- **[suggestion]** Line 1791 — `PagesRepository(session)` result is discarded immediately. Dead code; remove.

- **[suggestion]** Lines 898–912 — `get_book_stats` issues four sequential `COUNT` queries (one per status). Replace with a single `SELECT status, COUNT(*) FROM books GROUP BY status` query.

- **[suggestion]** Lines 218, 422–424 — `sortBy` regex pattern and `sort_map` are out of sync. Pattern allows `"date"`, `"created_at"`, `"updated_at"` but `sort_map` has none of them. `"lastUpdated"` is in `sort_map` but not in the regex. Values like `sortBy=date` silently fall back to `upload_date` instead of being rejected. Align the regex pattern with `sort_map` keys.

---

### `services/backend/api/endpoints/contact.py`

- **[suggestion]** Line 21 — `POST /contact/submit` is a public unauthenticated endpoint with no rate limiting. Add `@limiter.limit("5/minute")`.

- **[suggestion]** Line 48 — `limit: int = 100` has no upper bound. Add `Query(100, ge=1, le=500)`.

---

### `services/backend/api/endpoints/stats.py`

- **[blocking]** Lines 63, 67, 93, 97, 108, 114, 138, 141 — `session.execute()` called directly in endpoint, bypassing repository layer. Move to `StatsRepository` or use existing `BooksRepository`/`PagesRepository` methods.

---

### `services/backend/api/endpoints/dictionary.py`

- **[blocking]** Lines 53, 58, 62, 90, 101, 119, 136 — All DB access is done with raw `session.execute()` and `session.add()` directly in endpoint functions. Move to a `DictionaryRepository`.

---

### `services/backend/api/endpoints/spell_check.py`

- **[blocking]** Lines 107, 135, 194, 206, 251, 265, 296, 307, 335, 349, 357, 359, 362, 400, 422, 460, 488, 495 — Same issue: all DB operations bypass the repository layer.

---

### `packages/backend-core/app/services/cache_service.py`

- **[blocking]** Lines 72, 94 — `model_dump()` is used without `mode='json'` in both `set()` and `_serialize_value()`. Pydantic models with `datetime`, `UUID`, or `Enum` fields will not serialize to JSON. Change to `model_dump(mode='json')` in both places.

---

## Summary

There are six blocking issues that need to be resolved before merging: an XSS vulnerability in the OAuth callback HTML, two correctness bugs (unreachable `/stats` route and broken NULL visibility check), broken cache serialization that silently drops all book caching, stale cache keys after mutations, and pervasive direct `session.execute()` calls in endpoint files that violate the repository pattern. The architecture violation is widespread across `books.py`, `spell_check.py`, `stats.py`, and `dictionary.py`. The remaining suggestions are quality issues (f-string logging, hardcoded strings, missing rate limit) that should be addressed but are not blocking correctness.
