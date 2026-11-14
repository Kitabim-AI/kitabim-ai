# Kitabim Client SDK

## Overview
HTTP client SDK and OAuth2 authentication handlers used by the Kitabim OCR desktop client to authenticate with the remote Kitabim API, search books, download source PDFs, and upload OCR results and page corrections.

## Interface
- `[auth.py:AuthError]`: Exception raised when local OAuth callback, headless auth, or browser login times out or is cancelled.
- `[auth.py:get_valid_token]`: Reads valid JWT access token from disk cache, refreshes via `refresh_access_token` when `< 5` minutes remain, or initiates browser OAuth login flow (raising `AuthError` if `headless=True`).
- `[auth.py:refresh_access_token]`: Calls `POST /auth/refresh` with JSON `{"refresh_token": ...}` and saves the renewed `access_token` (`0600`).
- `[auth.py:login_and_save]`: Runs interactive loopback OAuth login and writes `{access_token, refresh_token}` (`0600`).
- `[auth.py:_login]`: Starts local ephemeral HTTP server on `127.0.0.1`, launches system web browser, and intercepts OAuth callback.
- `[api.py:KitabimAPIError]`: Exception raised for non-2xx responses from Kitabim API.
- `[api.py:KitabimClient]`: Client for interacting with Kitabim backend API.
  - `[api.py:KitabimClient.push_new_book]`: Uploads PDF and page OCR payload (`detectedPageNumber`, `ocr_version`) to `/books/upload-ocrd`.
  - `[api.py:KitabimClient.push_page_correction]`: Updates corrected text and TOC flags via `/books/{book_id}/pages/{page_number}/update` and `/toc`.
  - `[api.py:KitabimClient.download_book_pdf]`: Obtains a download ticket from `POST /books/{book_id}/download-ticket` and streams the PDF without forwarding `Authorization` headers to GCS.
  - `[api.py:KitabimClient.get_backfill_candidates]`: Lists un-backfilled PDF books and server indexing backlog from `GET /books/backfill-candidates`.
  - `[api.py:KitabimClient.replace_book_ocr]`: Sends gzip-compressed bulk OCR replacement payload to `POST /books/{book_id}/replace-ocr`.
  - `[api.py:KitabimClient.list_books]`: Lists books with query filters and pagination.
  - `[api.py:KitabimClient.get_book_pages]`: Retrieves full list of pages for a book across pagination batches.
  - `[api.py:KitabimClient.get_book]`: Fetches metadata for an individual book ID.
  - `[api.py:KitabimClient.book_exists]`: Checks book existence by inspecting HTTP status codes.

## Invariants
- `[auth.py:get_valid_token]`: Cached access token is reused if its decoded `exp` claim exceeds `time.time() + 300` seconds; otherwise `refresh_access_token` is attempted before browser fallback.
- `[api.py:KitabimClient._headers]`: Outbound requests require an authenticated Bearer token and append `X-Kitabim-App-Id` when `SECURITY_APP_ID` is present.

## Side Effects
- `[auth.py:_login]`: Spawns a background HTTP daemon thread listening on an ephemeral localhost port and launches default web browser.
- `[auth.py:get_valid_token]`: Writes authenticated token JSON to local disk (`~/.config/kitabim-ocr-client/token.json`).
- `[api.py:KitabimClient]`: Issues outbound HTTP requests (GET, POST) to remote Kitabim API and writes downloaded PDF files to disk.

## Verification
- Run: `pytest clients/kitabim-ocr/tests`
