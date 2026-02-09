# Authentication & Authorization Design — Kitabim.AI

## 1) Overview

This document outlines the design for implementing authentication (AuthN) and authorization (AuthZ) in Kitabim.AI. The system will support:

- **Google OAuth 2.0** for user sign-up/sign-in (extensible to other providers later)
- **JWT-based token authentication** for API access
- **Role-Based Access Control (RBAC)** with three user roles

## 2) User Roles & Permissions

| Role | Description | Permissions |
|------|-------------|-------------|
| **System Admin** | Full system control | Manage users & roles, delete books, all Editor permissions |
| **Editor** | Content management | Upload books, run pipelines, modify/edit pages, view all books |
| **Reader** | Read-only access | View ready books, use RAG chat |
| **Guest** | Unauthenticated user | View public ready books only (no chat access) |

### Permission Matrix

| Action | Guest | Reader | Editor | Admin |
|--------|-------|--------|--------|-------|
| View ready books | ✅ | ✅ | ✅ | ✅ |
| View book details | ✅ | ✅ | ✅ | ✅ |
| Use RAG chat (per-book) | ❌ | ✅ | ✅ | ✅ |
| Use Global chat | ❌ | ✅ | ✅ | ✅ |
| Upload books | ❌ | ❌ | ✅ | ✅ |
| Start/retry OCR | ❌ | ❌ | ✅ | ✅ |
| Edit page content | ❌ | ❌ | ✅ | ✅ |
| Reprocess books | ❌ | ❌ | ✅ | ✅ |
| Apply spell corrections | ❌ | ❌ | ✅ | ✅ |
| Update book metadata | ❌ | ❌ | ✅ | ✅ |
| Upload covers | ❌ | ❌ | ✅ | ✅ |
| Delete books | ❌ | ❌ | ❌ | ✅ |
| Manage users | ❌ | ❌ | ❌ | ✅ |
| Change user roles | ❌ | ❌ | ❌ | ✅ |

**Guest scope**: Guests can only access books with `visibility=public` (or `is_public=true`) **and** `status=ready`. All other books require authenticated roles.

## 3) Architecture

### High-Level Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Google
    participant MongoDB

    User->>Frontend: Click "Sign in with Google"
    Frontend->>Backend: GET /api/auth/google/login
    Backend->>Frontend: Redirect URL to Google
    Frontend->>Google: Redirect to Google OAuth
    User->>Google: Authenticate & Consent
    Google->>Backend: Callback with auth code
    Backend->>Google: Exchange code for tokens
    Google->>Backend: Access token + ID token
    Backend->>MongoDB: Create/Update user record
    Backend->>Frontend: Set refresh token cookie; return short HTML to postMessage access token (no tokens in URL)
    Frontend->>Backend: API requests with Bearer access token
    Backend->>Backend: Validate JWT, check permissions
    Backend->>Frontend: Protected response
```

### Component Structure

```
/packages/backend-core/app
  /auth                         # NEW: Auth module
    ├── __init__.py
    ├── dependencies.py         # FastAPI dependencies (get_current_user, require_role)
    ├── jwt_handler.py          # JWT creation/validation
    ├── oauth_providers.py      # Google OAuth (extensible)
    └── permissions.py          # Role-based permission checks
  /api/endpoints
    └── auth.py                 # NEW: Auth endpoints
  /models
    └── user.py                 # NEW: User schemas
  /db
    └── mongodb.py              # Add users collection + indexes
```

## 4) Data Model

### Users Collection

```python
class User(BaseModel):
    id: str                           # UUID
    email: str                        # Unique, from OAuth provider
    display_name: str                 # From OAuth or user-set
    avatar_url: Optional[str]         # Profile picture URL
    role: UserRole                    # admin | editor | reader
    provider: str                     # "google" (extensible)
    provider_id: str                  # Google user ID
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime]
    is_active: bool = True            # For soft-disable

class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    READER = "reader"
```

### Account Linking Policy (MVP)

- **No automatic linking by email.** If a user signs in with a different provider and the email matches an existing account, reject with a clear message (e.g., “Account exists with another provider”).
- **Future**: add an explicit account-linking flow (user-initiated + re-auth).

### Book Visibility (Guest Access)

Add a field on books to enforce public access for guests:

```python
class Book(BaseModel):
    # ...
    status: str              # e.g., "ready"
    visibility: str          # "public" | "private" (or is_public: bool)
```

Guests may only see books where `status="ready"` and `visibility="public"`. Consider an index on `(status, visibility)` to support efficient filtering.

### MongoDB Indexes

```python
# In mongodb.py _ensure_indexes()
users = self.db.users
await safe_create_index(users, [("email", 1)], unique=True)
await safe_create_index(users, [("provider", 1), ("provider_id", 1)], unique=True)
await safe_create_index(users, [("role", 1)])
```

### Refresh Tokens Collection (Optional Enhancement)

```python
class RefreshToken(BaseModel):
    id: str
    user_id: str
    jti: str                  # Unique token ID (for rotation)
    token_hash: str           # Hashed token for security
    expires_at: datetime
    created_at: datetime
    revoked: bool = False
    device_info: Optional[str]
```

**Refresh token lifecycle (MVP recommendation):**

- Store **hashed** refresh tokens (and `jti`) in DB; set a TTL index on `expires_at`.
- Rotate on every refresh: issue a new refresh token and revoke the previous `jti`.
- On logout, revoke the current refresh token (and optionally all active tokens for the user).

## 5) JWT Token Design

### Access Token Structure

```json
{
  "sub": "user_id_uuid",
  "email": "user@example.com",
  "role": "editor",
  "display_name": "User Name",
  "jti": "token_uuid",
  "iat": 1707000000,
  "exp": 1707003600,
  "type": "access"
}
```

### Token Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Access Token Expiry | 1 hour | Short-lived for security |
| Refresh Token Expiry | 7 days | Longer for user convenience |
| Algorithm | HS256 | Simple, fast; upgrade to RS256 for multi-service |
| Secret Key | From env `JWT_SECRET_KEY` | Secure random 256-bit key |

### Configuration Additions (config.py)

```python
# Auth Settings
jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
jwt_access_token_expire_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
jwt_refresh_token_expire_days: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Google OAuth
google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

# Auth behavior
default_user_role: str = os.getenv("DEFAULT_USER_ROLE", "reader")
```

## 6) API Endpoints

### Auth Routes (`/api/auth`)

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET | `/auth/google/login` | ❌ | Initiate Google OAuth flow |
| GET | `/auth/google/callback` | ❌ | OAuth callback, issues JWT |
| POST | `/auth/logout` | ✅ | Invalidate refresh token |
| POST | `/auth/refresh` | ❌ (refresh token) | Refresh access token |
| GET | `/auth/me` | ✅ | Get current user profile |

### User Management Routes (`/api/users`) - Admin Only

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET | `/users` | ✅ Admin | List all users |
| GET | `/users/{id}` | ✅ Admin | Get user details |
| PATCH | `/users/{id}/role` | ✅ Admin | Change user role |
| PATCH | `/users/{id}/status` | ✅ Admin | Enable/disable user |
| DELETE | `/users/{id}` | ✅ Admin | Delete user account |

### Protected Existing Routes

Update these routes with appropriate authorization:

| Endpoint Group | Required Role | Notes |
|----------------|---------------|-------|
| `GET /api/books` (ready books) | Guest | Public access to ready books |
| `GET /api/books/{id}` | Guest | View book details |
| `POST /api/books/upload` | Editor | Upload new books |
| `POST /api/books/{id}/start-ocr` | Editor | Start OCR processing |
| `PATCH /api/books/{id}/pages/{num}` | Editor | Edit page content |
| `POST /api/books/{id}/reprocess` | Editor | Reprocess book |
| `DELETE /api/books/{id}` | Admin | Delete book |
| `POST /api/chat` | Reader+ | RAG chat (requires authentication) |
| `POST /api/chat/global` | Reader+ | Global chat (requires authentication) |

## 7) Implementation Details

### FastAPI Dependencies

```python
# auth/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[User]:
    """Returns user if valid token; returns None only when no token is provided."""
    if not credentials:
        return None
    try:
        payload = decode_jwt(credentials.credentials)
        user = await get_user_by_id(payload["sub"])
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive user"
            )
        return user
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Requires authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user

def require_role(*allowed_roles: UserRole):
    """Dependency factory for role-based access control."""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return user
    return role_checker

# Convenience dependencies
require_admin = require_role(UserRole.ADMIN)
require_editor = require_role(UserRole.ADMIN, UserRole.EDITOR)
require_reader = require_role(UserRole.ADMIN, UserRole.EDITOR, UserRole.READER)
```

### JWT Handler

```python
# auth/jwt_handler.py

from datetime import datetime, timedelta
from jose import jwt, JWTError
from app.core.config import settings

def create_access_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role.value,
        "display_name": user.display_name,
        "type": "access",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def create_refresh_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "type": "refresh",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def decode_jwt(token: str) -> dict:
    """Decode and validate JWT. Raises JWTError on failure."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
```

### Google OAuth Provider

**State/nonce handling and ID token validation (required):**

- Generate a cryptographically random `state` and `nonce` per login attempt.
- Store them server-side (or in a signed, httpOnly cookie) and validate on callback.
- Validate the **ID token** signature and claims (`iss`, `aud`, `exp`, `nonce`). Consider checking `email_verified` for Google accounts.

```python
# auth/oauth_providers.py

import httpx
from app.core.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

def get_google_auth_url(state: str, nonce: str) -> str:
    """Generate Google OAuth authorization URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "nonce": nonce,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri,
        })
        response.raise_for_status()
        return response.json()

async def get_google_user_info(access_token: str) -> dict:
    """Fetch user profile from Google."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()
```

## 8) Frontend Integration

### Auth State Management

```typescript
// hooks/useAuth.ts

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface User {
  id: string;
  email: string;
  displayName: string;
  avatarUrl?: string;
  role: 'admin' | 'editor' | 'reader';
}

// Store tokens securely (MVP)
const TOKEN_KEY = 'kitabim_access_token';
const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token);
const getToken = () => localStorage.getItem(TOKEN_KEY);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);
```

**Login flow (MVP recommendation):**

- Open Google login in a popup.
- The backend callback sets an httpOnly refresh token cookie and returns a short HTML page that `postMessage`s the **access token** to the opener (no tokens in URLs).
- The frontend stores the access token in localStorage and fetches `/auth/me`.

### API Client Updates

```typescript
// services/apiClient.ts

const apiClient = {
  async request(url: string, options: RequestInit = {}) {
    const token = getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers,
    };
    
    const response = await fetch(url, { ...options, headers });
    
    // Handle 401 - token expired
    if (response.status === 401) {
      // Try refresh token flow
      const refreshed = await this.refreshToken();
      if (refreshed) {
        return this.request(url, options); // Retry
      }
      // Clear auth state, redirect to login
      clearToken();
      window.location.href = '/';
    }
    
    return response;
  },
  
  async refreshToken(): Promise<boolean> {
    // Implement refresh token logic
  }
};
```

### UI Components

```typescript
// components/auth/LoginButton.tsx
// components/auth/UserMenu.tsx (avatar + dropdown with role, logout)
// components/auth/ProtectedRoute.tsx (wrapper for role-based routes)
```

## 9) Security Considerations

### Token Storage

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| `localStorage` | Simple, persists | XSS vulnerable | OK for MVP |
| `httpOnly cookie` | XSS resistant | CSRF needed | Better for prod |
| In-memory + refresh | Most secure | Complex | Future enhancement |

**MVP Approach**: Use `localStorage` for access token with short expiry (1 hour). Implement CSRF protection if moving to cookies.

### Additional Security Measures

1. **Rate Limiting**: Apply to auth endpoints (e.g., 5 login attempts/minute)
2. **HTTPS Only**: Enforce in production
3. **Token Revocation**: Store revoked refresh tokens until expiry
4. **Audit Logging**: Log authentication events
5. **State Parameter**: Prevent CSRF in OAuth flow
6. **XSS Protections (required if using localStorage)**: Strict CSP (no inline scripts), sanitize/escape user input, and avoid `dangerouslySetInnerHTML` in React unless explicitly sanitized.
7. **Fail-fast on secrets**: Abort startup if `JWT_SECRET_KEY` is missing or too short.

## 10) Configuration (Kubernetes)

### secret.yaml additions

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: kitabim-secrets
  namespace: kitabim
type: Opaque
stringData:
  GEMINI_API_KEY: "your-gemini-key"
  JWT_SECRET_KEY: "your-256-bit-random-secret"
  GOOGLE_CLIENT_ID: "your-google-client-id"
  GOOGLE_CLIENT_SECRET: "your-google-client-secret"
```

### configmap.yaml additions

```yaml
data:
  # ... existing config ...
  JWT_ALGORITHM: HS256
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES: "60"
  JWT_REFRESH_TOKEN_EXPIRE_DAYS: "7"
  GOOGLE_REDIRECT_URI: "http://localhost:8000/api/auth/google/callback"
  DEFAULT_USER_ROLE: "reader"
```

## 11) Implementation Phases

### Phase 1: Core Auth Infrastructure (MVP) ✅ COMPLETED
1. ✅ Create auth module structure
2. ✅ Implement JWT handler with token validation
3. ✅ Add User model and MongoDB collection with indexes
4. ✅ Implement FastAPI security dependencies (get_current_user, require_role)
5. ✅ Create `/auth/me` endpoint for testing

### Phase 2: Google OAuth ✅ COMPLETED
1. ✅ Implement Google OAuth provider (popup-based flow)
2. ✅ Create login/callback endpoints with CSRF protection
3. ✅ Handle user creation/update on OAuth callback (admin role for configured emails)
4. ✅ Frontend login button, UserMenu, and AuthProvider context
5. ✅ Token refresh mechanism and httpOnly cookie for refresh tokens

### Phase 3: Protected Routes ✅ COMPLETED
1. ✅ Add auth dependencies to all book management endpoints
2. ✅ Implement guest visibility filter (public + ready books only)
3. ✅ Add role-based authorization:
   - Reader+: Chat functionality
   - Editor+: Upload, OCR, edit, reindex, spell check
   - Admin only: Delete books
4. ✅ Update frontend API calls with authFetch wrapper
5. ✅ Add 403 error handling with user-friendly messages

### Phase 4: User Management (Admin) ✅ COMPLETED
1. ✅ Create admin user management endpoints (`/api/users`)
2. ✅ Add UserManagementPanel with tabbed AdminTabs interface
3. ✅ Implement role change functionality (with self-edit protection)
4. ✅ Implement enable/disable user accounts

### Phase 5: Enhancements (Future)
1. 🔲 Refresh token rotation for enhanced security
2. ✅ Token revocation on logout (implemented)
3. Rate limiting
4. Audit logging
5. Additional OAuth providers (if needed)

## 12) Testing Strategy

### Unit Tests
- JWT creation/validation
- Permission checking
- OAuth URL generation

### Integration Tests
- Full OAuth flow (mocked Google)
- Protected endpoint access
- Role-based authorization

### E2E Tests
- Login flow
- Token refresh
- Permission-gated UI elements

## 13) Dependencies to Add

### Python (requirements.txt)
```
python-jose[cryptography]>=3.3.0   # JWT handling
httpx>=0.25.0                       # Already present, for OAuth requests
```

### Environment Variables Summary
```bash
# Required
JWT_SECRET_KEY=            # 256-bit random secret
GOOGLE_CLIENT_ID=          # From Google Cloud Console
GOOGLE_CLIENT_SECRET=      # From Google Cloud Console
GOOGLE_REDIRECT_URI=       # OAuth callback URL

# Optional
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
DEFAULT_USER_ROLE=reader
```

## 14) Design Decisions (Finalized)

| Question | Decision | Details |
|----------|----------|---------|
| **First Admin Bootstrap** | `ADMIN_EMAILS` env var | Users signing up with emails in this comma-separated list are auto-promoted to admin |
| **Default Book Visibility** | `private` by default | Editors must explicitly set `visibility=public` to make books accessible to guests |
| **Multi-device Logout** | Single device only | Logout revokes only the current refresh token, not all sessions |
| **Existing Books Migration** | All become `public` | Maintains current behavior; migration sets `visibility=public` on all existing books |
| **Session Management** | Stateless JWT only | No server-side session tracking for MVP; refresh token tracking provides sufficient control |

## 15) Future Considerations

1. **Email Verification**: Required for non-OAuth registration (if added later)
2. **Granular Permissions**: Category/book-level access control
3. **"Log out everywhere"**: User-initiated revocation of all sessions
4. **Additional OAuth Providers**: Apple, Microsoft, etc.

---

**Implementation Ready**: Design approved. Proceeding with Phase 1.
