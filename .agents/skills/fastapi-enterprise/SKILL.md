---
name: fastapi-enterprise
description: >-
  Enterprise FastAPI architecture patterns, async routes, Pydantic v2 validation,
  multi-tenant database isolation, SQLAlchemy 2.0 SQLite WAL lifecycles, and pytest testing.
---

# Enterprise FastAPI & Python Standards

Use this skill when developing, refactoring, or testing FastAPI backend services, database migrations, security middleware, and authentication within the hybrid monolith.

---

## 1. Hybrid Monolith Architecture Rules

1. **Colocated Server-Rendered UI & API**:
   * API endpoints reside under `/api/...` and return structured JSON.
   * Browser workspace routes reside under root paths (`/dashboard`, `/profile`, `/settings`) and return `TemplateResponse` with pre-rendered Jinja2 HTML.
   * Never introduce Node.js, Webpack, Vite, or npm build steps. The frontend must remain pure, zero-build vanilla async JavaScript with CDN Tailwind CSS.

2. **Lifespan Management**:
   Always manage background workers, schedulers, and connection pools using the `lifespan` async context manager:
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # Startup
       start_scheduler()
       yield
       # Shutdown
       stop_scheduler()
   ```

---

## 2. Multi-Tenant Database Patterns (SQLAlchemy 2.0 & SQLite WAL)

1. **WAL & Concurrency Pragmas**:
   Every SQLite connection must enforce Write-Ahead Logging (WAL), foreign key constraints, and a 30-second busy timeout to avoid `sqlite3.OperationalError: database is locked`:
   ```python
   @event.listens_for(engine, "connect")
   def set_sqlite_pragma(dbapi_connection, connection_record):
       cursor = dbapi_connection.cursor()
       cursor.execute("PRAGMA journal_mode=WAL;")
       cursor.execute("PRAGMA foreign_keys=ON;")
       cursor.execute("PRAGMA busy_timeout=30000;")
       cursor.close()
   ```

2. **Tenant Isolation by Default**:
   * All user-owned models (`CandidateProfile`, `AnswerBank`, `UserJobApplication`) must declare a foreign key to `users.id` with `ondelete="CASCADE"`.
   * Queries must filter by `user_id == current_user.id` or explicitly handle guest fallbacks.

3. **Session Dependency Injection**:
   Always inject database sessions with `Depends(get_db)` to ensure cleanup via `finally: db.close()`.

---

## 3. Pydantic v2 Schemas & Data Validation

1. **Email & Type Strictness**:
   Use `EmailStr` from `pydantic` (with `email-validator` installed).
2. **Settings Management**:
   Inherit from `pydantic_settings.BaseSettings` with `SettingsConfigDict(env_file=..., extra="ignore")`.
3. **Password Policies**:
   Enforce minimum length ($\ge 8$ chars) in the Pydantic schema or endpoint validator before invoking bcrypt hashing.

---

## 4. Security & Authentication Architecture

1. **Bcrypt Salted Hashes**:
   Store only `bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()`. Never store plaintext passwords.
2. **Cryptographic JWTs**:
   Sign access tokens with HS256 and store them strictly in `HttpOnly`, `SameSite="lax"` cookies to eliminate XSS token exfiltration.
3. **PKCE for OAuth 2.0**:
   When redirecting to Google OAuth, persist `flow.code_verifier` in an HttpOnly cookie and restore it during the token exchange callback.

---

## 5. Automated Testing Guidelines (Pytest)

1. Always use `starlette.testclient.TestClient`.
2. Clean up test users and temporary rows inside `try...finally` blocks.
3. Mock external LLM and ATS API calls using `respx` or `unittest.mock`.
