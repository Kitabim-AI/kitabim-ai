# Security Audit Report

**Project:** Kitabim AI
**Date:** 2026-03-22
**Scope:** Full codebase — backend, frontend, worker, infrastructure, configuration

---

## Summary

| Severity | Count | Fixed |
|----------|-------|-------|
| Critical | 1 | 1 |
| High | 5 | 5 |
| Medium | 5 | 5 |
| Low | 3 | 2 |
| **Total** | **16** | **13** |

---

## Critical

### SEC-001 — Secrets Exposed in `.env` File ✅ RESOLVED

**File:** `.env`
**Severity:** Critical
**Status:** Fixed 2026-03-22 — All secrets rotated. `.env` confirmed never committed to git history and is gitignored.

The `.env` file contains live production secrets. If this file has ever been committed to git, the secrets are in the repository history and must be considered compromised.

**Exposed secrets:**
- `GEMINI_API_KEY`
- `JWT_SECRET_KEY`
- `IP_SALT`
- `SECURITY_APP_ID`
- `DATABASE_URL` (exposes internal database address)

**Fix:**
1. Rotate all secrets immediately (GCP console, JWT generator, etc.)
2. Ensure `.env` is listed in `.gitignore`
3. If the file was ever committed: purge it from git history (`git filter-repo` or BFG)
4. Use only `.env.template` (with placeholder values) in version control
5. For production: store secrets in Google Cloud Secret Manager, not flat files

---

## High

### SEC-002 — OAuth `postMessage` Uses Wildcard Origin ✅ RESOLVED

**File:** `services/backend/api/endpoints/auth.py` (lines 480, 494, 640)
**Severity:** High
**Status:** Fixed 2026-03-22 — Success path now uses `openerOrigin` (already captured); error path loops through `allowedOrigins` from `settings.cors_origins`. No more wildcard `'*'`.

During OAuth callback, the access token is sent to the opener window using `'*'` as the `targetOrigin`. Any page opened in the same browser context can intercept the token.

```python
# Current — unsafe
window.opener.postMessage({ type: 'OAUTH_SUCCESS', accessToken: accessToken }, '*')

# Fix — restrict to known origin
window.opener.postMessage({ type: 'OAUTH_SUCCESS', accessToken: accessToken }, 'https://kitabim.ai')
```

**Fix:** Replace `'*'` with the specific frontend origin (read from `CORS_ORIGINS` config).

---

### SEC-003 — Access Token Stored in `localStorage` ✅ RESOLVED

**File:** `apps/frontend/src/services/authService.ts` (lines 25, 32, 39, 532)
**Severity:** High
**Status:** Fixed 2026-03-22 — Token now lives in a module-level memory variable only. Session recovery on page load uses: (1) URL param for mobile redirect flow, (2) `sessionStorage` one-time read for popup redirect fallback (cleared immediately), (3) silent refresh via httpOnly cookie. Backend fallback changed from `localStorage` to `sessionStorage`.

The JWT access token is persisted in `localStorage`, which is accessible to any JavaScript running on the page. A single XSS vulnerability would allow full token theft.

The refresh token is correctly stored in an `httpOnly` cookie. The access token should follow the same pattern or be kept in memory only.

**Fix:**
- Store the access token in module-level memory (a JS variable), not `localStorage`
- On page reload, use the httpOnly refresh token to silently re-issue an access token
- Remove the `localStorage.setItem('kitabim_access_token', ...)` fallback in the OAuth callback

---

### SEC-004 — Security Headers Inverted: Missing in Production ✅ RESOLVED

**File:** `services/backend/main.py` (lines 118–132)
**Severity:** High
**Status:** Fixed 2026-03-22 — `X-Frame-Options` and `X-Content-Type-Options` now set unconditionally. HSTS added for production environments.

The middleware sets `X-Frame-Options` and `X-Content-Type-Options` only when the environment is **not** production. This is the opposite of what is needed.

```python
# Current — inverted, headers missing in production
if settings.environment != "production":
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"

# Fix — always set these headers
response.headers["X-Frame-Options"] = "DENY"
response.headers["X-Content-Type-Options"] = "nosniff"
if settings.environment == "production":
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

---

### SEC-005 — No Rate Limiting on File Upload and Reprocess Endpoints

**File:** `services/backend/api/endpoints/books.py`
**Severity:** Low *(downgraded from High)*

`POST /api/books/upload` requires editor role. All `/reprocess/*` endpoints require admin role. User base with these permissions is small and trusted. Rate limiting would be defense-in-depth only. Accepted risk — revisit if the editor/admin user base grows.

---

### SEC-006 — GCS Proxy Passes Raw Query Parameters ✅ RESOLVED

**File:** `services/backend/main.py` (lines 303–304)
**Severity:** High
**Status:** Fixed 2026-03-22 — Only the whitelisted `v` (cache-bust) param is forwarded. All other query params are dropped.

The static file proxy appends user-supplied query parameters directly to GCS URLs without validation.

```python
# Current — user controls what gets appended to the GCS URL
if request.query_params:
    url += f"?{request.query_params}"
```

**Fix:** Whitelist only known parameters:
```python
allowed_params = {k: v for k, v in request.query_params.items() if k in ("v",)}
if allowed_params:
    url += f"?{urlencode(allowed_params)}"
```

---

### SEC-007 — Overly Permissive Content Security Policy ✅ RESOLVED

**File:** `services/backend/main.py` (lines 136–145)
**Severity:** High
**Status:** Fixed 2026-03-22 — `unsafe-eval` removed from backend CSP (API responses). CSP added to `apps/frontend/nginx.conf` (was entirely absent) with `unsafe-inline` removed from `script-src` (Vite builds don't need it) and `worker-src blob:` added for pdf.js. `unsafe-eval` kept only in Nginx CSP where pdf.js requires it.

The CSP includes both `'unsafe-inline'` and `'unsafe-eval'` in `script-src`. This substantially weakens XSS protection — any injected script will execute.

**Fix:** Use nonce-based CSP to allow legitimate inline scripts without the blanket `unsafe-inline`:
```python
nonce = secrets.token_urlsafe(16)
csp = f"script-src 'self' 'nonce-{nonce}' https://accounts.google.com; ..."
response.headers["Content-Security-Policy"] = csp
```
Evaluate whether `'unsafe-eval'` is truly required (pdf.js may need it; React/Vite do not in production builds).

---

### SEC-008 — `APP_CLIENT_ID` Hardcoded in Frontend Bundle

**File:** `apps/frontend/src/config.ts` (line 7)
**Severity:** Informational *(downgraded from High)*

`APP_CLIENT_ID` is intentionally used as a lightweight bot filter only, not as a security control. Access control is enforced via JWT authentication. The ID is not secret by design — it is expected to be visible in the bundle. No fix required.

---

## Medium

### SEC-009 — JWT Access Token Expiry Defaults to 24 Hours ✅ RESOLVED

**File:** `packages/backend-core/app/core/config.py` (line 103)
**Severity:** Medium

```python
jwt_access_token_expire_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
```

A 24-hour window means a stolen token is valid for a full day. Industry standard is 15–60 minutes, relying on the refresh token for session continuity.

**Fix:** Change the default to `"60"`.

---

### SEC-010 — MD5 Used for Book ID Generation ✅ RESOLVED

**File:** `services/backend/api/endpoints/books.py` (line 1065)
**Severity:** Medium

```python
book_id = hashlib.md5(f"{file.filename}{datetime.now(timezone.utc)}".encode()).hexdigest()[:12]
```

MD5 is cryptographically broken. The ID also incorporates user-controlled input (`file.filename`), reducing entropy.

**Fix:**
```python
import secrets
book_id = secrets.token_hex(6)  # 12 hex characters, cryptographically random
```

---

### SEC-011 — `LOG_LEVEL` Defaults to `DEBUG` ✅ RESOLVED

**File:** `packages/backend-core/app/core/config.py`
**Severity:** Medium

Debug logging in production exposes SQL queries, internal state, stack traces, and other sensitive details to anyone with log access.

**Fix:** Change the default from `"DEBUG"` to `"WARNING"` and set `LOG_LEVEL=INFO` explicitly in non-production environments via `.env`.

---

### SEC-012 — No Length Validation on Query Parameters ✅ RESOLVED

**File:** `services/backend/api/endpoints/books.py` (lines 212–223)
**Severity:** Medium

`q`, `category`, and `sortBy` query parameters accept arbitrary-length strings with no validation. This risks log flooding and potential processing overhead.

**Fix:**
```python
q: Optional[str] = Query(None, max_length=500)
category: Optional[str] = Query(None, max_length=100)
sortBy: str = Query("title", pattern="^(title|author|date|created_at)$")
```

---

### SEC-013 — User Email Logged in Plaintext ✅ RESOLVED

**File:** `services/backend/api/endpoints/auth.py` (line 202)
**Severity:** Medium

```python
logger.info(f"User info retrieved for {provider}: {user_info.email}")
```

Email addresses are PII. Logging them exposes user data to anyone with access to the log system.

**Fix:**
```python
logger.info(f"User authenticated via {provider}")
```

---

## Low

### SEC-014 — Redis Exposed on Host Port in Local Dev

**File:** `docker-compose.yml` (line 11)
**Severity:** Low

Redis is exposed on `0.0.0.0:6379` with no authentication in local development. Any process on the machine can read/write the cache and job queue.

**Note:** The production GCP compose correctly places Redis on an internal Docker network only. This is a local-dev-only issue.

**Fix:** Not critical for local dev, but consider binding to `127.0.0.1:6379` to limit exposure.

---

### SEC-015 — No Database Query Timeout ✅ RESOLVED

**File:** `packages/backend-core/app/core/config.py`
**Severity:** Low

No query timeout is configured. A slow or runaway query can hold a connection pool slot indefinitely, degrading availability.

**Fix:**
```python
db_query_timeout: int = int(os.getenv("DB_QUERY_TIMEOUT", "30"))
```
Pass to the SQLAlchemy engine via `connect_args={"command_timeout": settings.db_query_timeout}`.

---

### SEC-016 — IP Address Detection Bypassed by Proxy ✅ RESOLVED

**File:** `services/backend/main.py` (lines 216, 233, 269)
**Severity:** Low

`request.client.host` returns the proxy's IP in production (behind Nginx), not the real client IP. Rate limiting and IP-based throttling are ineffective.

**Fix:** Configure FastAPI to trust the `X-Forwarded-For` header from the Nginx proxy:
```python
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1"])
```

---

## Immediate Action Plan

| # | Action | Effort | Owner |
|---|--------|--------|-------|
| 1 | ~~Rotate `GEMINI_API_KEY`, `JWT_SECRET_KEY`, `IP_SALT`, `SECURITY_APP_ID`~~ ✅ | 30 min | DevOps |
| 2 | ~~Add `.env` to `.gitignore`, purge from git history if committed~~ ✅ | 1 hr | DevOps |
| 3 | Fix `postMessage` wildcard origin (SEC-002) | 5 min | Backend |
| 4 | Fix inverted security header logic (SEC-004) | 5 min | Backend |
| 5 | Add rate limiting to upload/reprocess (SEC-005) | 15 min | Backend |
| 6 | Fix GCS query param passthrough (SEC-006) | 10 min | Backend |
| 7 | Lower JWT expiry default to 60 min (SEC-009) | 2 min | Backend |
| 8 | Replace MD5 with `secrets.token_hex` (SEC-010) | 2 min | Backend |
| 9 | Migrate access token from localStorage to memory (SEC-003) | 2–4 hrs | Frontend |
| 10 | Switch default log level to WARNING (SEC-011) | 2 min | Backend |
