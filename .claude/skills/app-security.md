# Application Security Skill — Kitabim AI

You are auditing, designing, or implementing security controls for the kitabim-ai application. This skill covers authentication, authorisation, secrets management, data privacy, transport security, and incident response. Every decision must be grounded in the actual implementation — check the code before declaring something safe or broken.

---

## Security Architecture Overview

```
Internet → Nginx (TLS 1.2/1.3) → FastAPI middleware stack → Route handler
                                        │
              ┌─────────────────────────┼──────────────────────────────┐
              ▼                         ▼                              ▼
   block_noisy_requests         enforce_app_id              add_security_headers
   (crawler/scanner paths)  (X-Kitabim-App-Id header)   (CSP, HSTS, X-Frame etc.)
              │                         │                              │
              └─────────────────────────▼──────────────────────────────┘
                                   CORS check
                                        │
                                   Route handler
                                        │
                              Auth dependency (JWT)
                                        │
                             Role check (RBAC)
```

---

## Authentication System

### JWT Token Lifecycle

| Token | Expiry | Storage | Purpose |
|-------|--------|---------|---------|
| Access token | 60 min (configurable) | Memory / `Authorization: Bearer` header | API authentication |
| Refresh token | 7 days (configurable) | `refresh_tokens` DB table (by `jti`) | Issue new access tokens |

**Access token payload** (`jwt_handler.py`):
```json
{
  "sub": "<user_id>",
  "email": "user@example.com",
  "role": "reader|editor|admin",
  "display_name": "...",
  "jti": "<uuid4>",
  "type": "access",
  "iat": <timestamp>,
  "exp": <timestamp>
}
```

**Security properties:**
- Algorithm: `HS256` — symmetric, `JWT_SECRET_KEY` must never leave the server
- `JWT_SECRET_KEY` validated at startup (`validate_jwt_secret()`): minimum 32 chars; app refuses to start if missing or too short
- Access tokens are **stateless** — validated by signature only; no DB lookup per request
- Refresh tokens are **stateful** — stored in `refresh_tokens` table; invalidated on logout by deleting the row by `jti`
- Token type is validated on decode (`expected_type="access"` or `"refresh"`) — prevents access tokens being used as refresh tokens and vice versa

### Auth Dependencies

```python
# services/backend/auth/dependencies.py

# Use one of these on every endpoint — never bypass:
require_admin   = require_role(UserRole.ADMIN)
require_editor  = require_role(UserRole.ADMIN, UserRole.EDITOR)
require_reader  = require_role(UserRole.ADMIN, UserRole.EDITOR, UserRole.READER)

# For endpoints where guests are explicitly supported:
user = Depends(get_current_user_optional)  # returns None for guests

# For endpoints that require any authenticated user:
user = Depends(get_current_user)           # raises 401 if not authenticated
```

**User caching**: after JWT validation, the user record is cached in Redis for `cache_ttl_user_profile` (300 s default). Cache key: `KEY_USER.format(user_id=user_id)`. **Important**: if a user's role or `is_active` status changes, the cache must be invalidated immediately — otherwise the old state persists for up to 5 minutes.

**Disable a user**: set `is_active=False` in the DB. The cache check (`if not user.is_active: raise 401`) will catch this on the next cache miss. To force immediate logout, also delete all their `refresh_tokens` rows and flush the user cache key.

### Role Hierarchy

```
ADMIN   → can do everything
EDITOR  → can manage content (books, dictionary, spell-check, auto-correct)
READER  → can read books and use chat
(guest) → public endpoints only
```

**Admin auto-promotion**: emails in `ADMIN_EMAILS` env var are automatically promoted to `ADMIN` role on OAuth login (`is_admin_email()` in `oauth_providers.py`). Keep this list current — a stale entry grants admin to the wrong person.

---

## OAuth Authentication

### CSRF Protection

OAuth state is encoded as a signed JWT (10-minute expiry) containing:
- `nonce` — random 32-byte value for replay prevention
- `redirect_uri` — the post-login destination
- `provider` — which OAuth provider initiated the flow
- `code_verifier` — PKCE verifier (Twitter/X only)

The state JWT is signed with `JWT_SECRET_KEY`. An attacker cannot forge a valid state without the key.

**When adding a new OAuth provider:**
1. Use `OAuthState` — never a plain random string passed as query param
2. Validate `state` on the callback before exchanging the code
3. Add the production callback URI to `GOOGLE_REDIRECT_URI` / equivalent in `.env` before deploying
4. Add client ID/secret to `.env` (never hardcode)

### postMessage Security

OAuth popups communicate results back to the opener via `window.postMessage`. The target origin must be the specific app domain — never `"*"`. This is enforced in the callback HTML page rendered by the backend. Do not change `targetOrigin` to `"*"` even during debugging.

---

## Middleware Security Stack

All middleware lives in `services/backend/main.py`. Order matters — they execute top-to-bottom.

### 1. `block_noisy_requests`
Rejects requests to known scanner/crawler paths (`/api/v1/`, `/api/v2/`, `/api/s3/`, `/api/uploads/`, etc.) with `404` before they reach any handler. Add new blocked prefixes to `settings.security_block_path_prefixes` — not hardcoded in the middleware.

### 2. `enforce_app_id`
All non-`GET`/`OPTIONS` requests must include `X-Kitabim-App-Id: <SECURITY_APP_ID>`. The `SECURITY_APP_ID` is rotated on every production deploy (`openssl rand -hex 16`), acting as a lightweight bot filter. It is **not** a security boundary on its own — authenticated endpoints still require a valid JWT.

### 3. CORS
Origins are whitelisted via `CORS_ORIGINS` (comma-separated in `.env`). Never set to `*` in production. `allow_credentials=True` is required for the `Authorization` header to be sent cross-origin.

**Adding a new allowed origin:**
```bash
# In deploy/gcp/.env:
CORS_ORIGINS=https://kitabim.ai,https://www.kitabim.ai,https://new-origin.example.com
```

### 4. `add_security_headers`
Adds to every response:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Frame-Options` | `DENY` | Clickjacking |
| `X-Content-Type-Options` | `nosniff` | MIME sniffing |
| `Strict-Transport-Security` | `max-age=31536000` (prod only) | HTTPS enforcement |
| `Content-Security-Policy` | strict allowlist | XSS, resource injection |
| `Permissions-Policy` | camera/mic/geo/interest-cohort off | Privacy |

**HSTS is production-only** — controlled by `settings.environment == "production"`. Never enable HSTS in local dev (it will break HTTP access).

### 5. Rate Limiting (`slowapi`)
Applied per-endpoint. Current limits are defined per route. When adding a new endpoint that could be abused (login, OTP, password reset, expensive LLM call):
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/my-endpoint")
@limiter.limit("10/minute")
async def my_endpoint(request: Request, ...):
    ...
```

**IP detection**: `ProxyHeadersMiddleware` trusts `X-Forwarded-For` from `127.0.0.1` (Nginx) only. Do not add other trusted proxies without understanding the implications for IP spoofing.

---

## Data Privacy & PII

### IP Address Hashing
All IP addresses must be hashed before storage using `hash_ip_address()` from `app.utils.security`:

```python
from app.utils.security import hash_ip_if_present

hashed_ip = hash_ip_if_present(request.client.host)
# Stores first 16 hex chars of SHA-256(ip + IP_SALT)
# One-way: cannot recover original IP
```

`IP_SALT` must be set in production (32+ chars). Without it, hashes are predictable (empty salt). **Never store raw IPs** in any DB table, log, or metric.

### What Must Never Be Logged

| Data | Reason |
|------|--------|
| Raw IP addresses | GDPR / privacy |
| JWT tokens (full string) | Token theft |
| OAuth access/ID tokens | Account takeover |
| `JWT_SECRET_KEY` | Signs all tokens |
| `IP_SALT` | Breaks IP anonymisation |
| `GEMINI_API_KEY` | API billing abuse |
| OAuth client secrets | Account hijacking |
| Passwords or hashes | N/A (OAuth only, no passwords) |
| Full request bodies | May contain PII |

**Logging rule**: use `log_json(logger, level, "message", user_id=..., book_id=...)` — structured fields only. Never interpolate sensitive values into message strings.

### GCS File Access
- **PDFs** (`data` bucket): private — accessed via service account key on the VM. Never generate public URLs for PDFs.
- **Covers** (`media` bucket): partially public — served via `/api/covers/{book_id}.jpg` endpoint which controls access. The Nginx config allows caching of cover images.
- **Signed URLs**: use GCS signed URLs for temporary client-side access if needed — never expose the service account key or bucket credentials to the frontend.

---

## Input Validation & Injection Prevention

### SQL Injection
All DB access goes through SQLAlchemy ORM with bound parameters. Raw SQL is used only in migration files (no user input). **Never** use string interpolation in SQLAlchemy queries:
```python
# WRONG — SQL injection risk:
await session.execute(text(f"SELECT * FROM books WHERE id = '{book_id}'"))

# RIGHT — bound parameter:
await session.execute(select(Book).where(Book.id == book_id))
# Or with text():
await session.execute(text("SELECT * FROM books WHERE id = :id"), {"id": book_id})
```

### File Upload Validation
When adding file upload endpoints:
- Validate MIME type from the file content (not just the extension or `Content-Type` header)
- Validate file size against `settings.max_upload_size_mb` before reading into memory
- Never execute uploaded file content
- Store in GCS under a UUID path — never use the original filename

### LLM Prompt Injection
User-supplied text flows into LLM prompts (RAG queries, OCR corrections). Guard against prompt injection:
- The RAG prompt wraps user input in `Question: {question}` — the context and instructions blocks are server-controlled
- Do not inject raw user text into the `{instructions}` or `{context}` blocks
- Treat LLM output as untrusted content — strip/escape before rendering in HTML

---

## Secrets Management

### Required Secrets and Minimum Requirements

| Secret | Min length | Generation command | Rotation period |
|--------|-----------|-------------------|-----------------|
| `JWT_SECRET_KEY` | 64 chars | `openssl rand -hex 32` | 90 days |
| `IP_SALT` | 32 chars | `openssl rand -hex 16` | 90 days |
| `SECURITY_APP_ID` | 16 chars | `openssl rand -hex 8` | Every deploy (auto) |
| GCS service account key | N/A (JSON) | GCP IAM console | On compromise |
| `GEMINI_API_KEY` | N/A | Google AI Studio | On compromise |
| OAuth secrets | N/A | Provider console | On compromise |

### Secret Rotation Procedure

**Rotating `JWT_SECRET_KEY`** (invalidates all active sessions):
1. Generate: `openssl rand -hex 32`
2. Update `deploy/gcp/.env` on the VM: `cp .env .env.backup && nano .env`
3. Delete all rows from `refresh_tokens` table (all sessions expire)
4. Restart backend: `docker compose restart backend`
5. Users will need to log in again

**Rotating `IP_SALT`** (breaks existing hashed-IP lookups):
1. Generate: `openssl rand -hex 16`
2. Update `.env`
3. **Note**: existing `rag_evaluations` and audit records with hashed IPs will no longer correlate with new hashes — acceptable tradeoff for security

**Revoking a single user session**:
```sql
-- Invalidate all refresh tokens for a user
DELETE FROM refresh_tokens WHERE user_id = '<user_id>';
-- Also flush their Redis user cache key
```

**Disabling a user immediately**:
```sql
UPDATE users SET is_active = false WHERE id = '<user_id>';
DELETE FROM refresh_tokens WHERE user_id = '<user_id>';
-- Then flush Redis cache key: KEY_USER.format(user_id=<user_id>)
```

---

## Dependency & Supply Chain Security

### Python dependencies
```bash
# Audit for known vulnerabilities
pip install pip-audit
pip-audit -r services/backend/requirements.txt
pip-audit -r packages/backend-core/requirements.txt
```

### npm dependencies (frontend)
```bash
cd apps/frontend
npm audit
npm audit fix   # only for non-breaking fixes
```

### Docker base images
- Use pinned versions (`nginx:1.27-alpine`, `python:3.12-slim`) — never `latest`
- Rebuild images regularly to pull OS security patches
- Run `docker scout cves` or `trivy image` on built images before deployment

### When adding a new Python dependency
- Check the package on PyPI for recent activity and maintainer reputation
- Avoid packages with known CVEs at the version you're pinning
- Pin to a specific version in `requirements.txt` — no unpinned ranges

---

## Security Checklist for New Endpoints

Before merging any new API endpoint:

- [ ] Auth dependency applied — `require_admin`, `require_editor`, `require_reader`, or `get_current_user_optional` with explicit justification for guest access
- [ ] No ownership bypass — verify the requesting user owns or has rights to the resource
- [ ] Rate limit applied if the endpoint is expensive or abuse-prone
- [ ] Input validated with Pydantic — no raw dict access from request body
- [ ] No raw SQL with user input — always bound parameters
- [ ] File uploads validate MIME type and size
- [ ] No secrets, tokens, or PII in response body or logs
- [ ] IP addresses hashed before storage (`hash_ip_if_present()`)
- [ ] Error messages use `t("errors.key")` — no internal details exposed to client
- [ ] `enforce_app_id` not bypassed (GET requests are exempt — verify the endpoint method)

---

## Incident Response

### Suspected token compromise
1. Rotate `JWT_SECRET_KEY` (invalidates all tokens globally)
2. Clear `refresh_tokens` table
3. Restart backend
4. Review logs for the compromised token's `jti` (JWT ID) — trace what it accessed

### Suspected OAuth client secret compromise
1. Revoke the secret in the provider console (Google/Facebook/Twitter)
2. Generate a new secret
3. Update `deploy/gcp/.env`
4. Restart backend
5. Users re-authenticate on next login (access tokens still valid until expiry — rotate `JWT_SECRET_KEY` too if immediate invalidation is needed)

### Suspected GCS service account key compromise
1. Disable the key in GCP IAM console immediately
2. Generate a new key
3. Copy to `/etc/gcs/key.json` on the VM
4. Restart backend and worker (they read the key on startup)
5. Review GCS access logs for unauthorised reads/writes

### Suspected DB credential compromise
1. Change the Cloud SQL user password via GCP console
2. Update `DATABASE_URL` in `deploy/gcp/.env`
3. Restart backend and worker
4. Review Cloud SQL audit logs

### API key abuse (Gemini)
1. Revoke key in Google AI Studio
2. Generate new key
3. Update `deploy/gcp/.env` → `GEMINI_API_KEY`
4. Restart backend and worker
5. Check circuit breaker status — it may be open from the abuse: `GET /api/admin/circuit-breakers`

---

## Known Security Decisions (from Audit History)

These are documented security choices — not bugs:

| Decision | Rationale |
|----------|-----------|
| `HS256` (symmetric) instead of `RS256` (asymmetric) | Single backend service; no need to distribute public keys |
| Access tokens stateless (no server-side revocation per-token) | Performance; 60-min expiry limits exposure window |
| `IP_SALT` falls back to empty string in dev | Avoids local dev breakage; prod always requires a set salt |
| `SECURITY_APP_ID` rotated every deploy | Reduces automated scraping; not a crypto boundary |
| Covers partially public (no signed URL) | Covers are non-sensitive thumbnails; complexity not justified |
| OAuth state via JWT (not server-side session) | Stateless; avoids Redis dependency for auth flow |
