# Progress — OneTrust Automation Backend

> **Orchestrator memory.** Read `Current State` at the start of every session — not source files.
> Update after every feature milestone.

---

## Current State

> Post-compact restore block. Read this after `/compact` or at any new session start.
> Update after every milestone. Keep under 40 lines.

**Last updated:** 2026-06-08 | **Milestones since /compact:** 7

```
APP: onetrust-automation — FastAPI backend automating authorized OneTrust sandbox workflows via Playwright
STACK: FastAPI + Playwright (backend/) | DB: None | AI: None | Auth: SSO passthrough (no API auth)
PORTS: BE=http://localhost:8000 | prefix: none (bare paths)

FEATURES DONE:
  scaffold (GET /health) — BE ✓
  auth (POST /auth/login) — BE ✓
  websites (POST /add_app) — full 13-step wizard ✓
  mapper (GET /mapper/default, POST /mapper/resolve) — BE ✓
  M8 debug responses + email prefill + scan polling — BE ✓

ACTIVE: COMPLETE — M8 done. Run: cd backend && uvicorn app.main:app --reload

NEXT: none

KEY DECISIONS:
  bare API paths (no /api/v1/) — per idea.md |
  features/onetrust/ flat module (M4 restructure) |
  tests skipped — per user decision |
  no DB — email from .env only |
  /add_app full 13-step wizard including scan polling — per M8 spec
GAPS: none
MILESTONES SINCE /compact: 7
```

---

## API Contracts

| Method | Path | Request | Response | Auth | Status |
|--------|------|---------|----------|------|--------|
| GET | `/health` | — | `{status: str, browser_ready: bool}` | No | Task 1 |
| POST | `/auth/login` | `{}` | `{status, message, current_url?, handled_modals?, screenshot?, failed_step?, steps[]?, debug?}` | No | Task 2 |
| POST | `/add_app` | `{url: str}` | `{status, message, input_url?, selected_kit?, current_url?, screenshot?, steps[], scan_status?, matched_display_url?, debug?}` | No | Task 5 |
| GET | `/mapper/default` | — | `{default_experience_kit, mode}` | No | Task 5 |
| POST | `/mapper/resolve` | `{url: str}` | `{url, experience_kit, mode}` | No | Task 5 |

**`/auth/login` status values:** `"logged in"` / `"SSO issue"` / `"error"`
**`/add_app` status values:** `"website url scan_status completed"` / `"not logged in"` / `"failed"` / `"scan failed"`
**Standard error shape (unhandled):** `{detail: str}`

---

## Decision Log

| Decision | Rationale | Date | Layers affected |
|----------|-----------|------|-----------------|
| Bare API paths — no version prefix | idea.md specifies `/auth/login`, `/add_app` | 2026-06-08 | BE |
| SPL `features/<feature>/` structure | User instruction: use SPL practices | 2026-06-08 | BE |
| Tests skipped in v1 | User decision — to be added later | 2026-06-08 | Tests |
| No database | Email from `.env` only in this version | 2026-06-08 | BE |
| Persistent Playwright context | SSO session must survive across API calls | 2026-06-08 | BE |
| Headed mode default | PingID may require visible browser interaction | 2026-06-08 | BE |

---

## Module Map

```
POST /auth/login  ──▶  backend/app/features/onetrust/router.py
                           └──▶ features/onetrust/auth.py (login_onetrust, fill_email_or_confirm_prefilled_email,
                                                            wait_for_sso_completion, handle_post_login_modals,
                                                            is_logged_in, _build_debug, _mask_email)
                           └──▶ features/onetrust/browser.py (BrowserManager singleton)

POST /add_app     ──▶  backend/app/features/onetrust/router.py
                           └──▶ features/onetrust/websites.py (add_app_flow — 13-step wizard,
                                                                ensure_websites_page,
                                                                click_add_website_button,
                                                                _build_debug, _normalize_url_for_search,
                                                                _domain_variants)
                           └──▶ features/onetrust/browser.py (BrowserManager singleton)
                           └──▶ features/onetrust/auth.py (is_logged_in check)
                           └──▶ features/onetrust/mapper.py (get_experience_kit_for_url)

GET/POST /mapper/* ──▶  backend/app/features/onetrust/router.py
                           └──▶ features/onetrust/mapper.py (DEFAULT_EXPERIENCE_KIT, get_experience_kit_for_url)

GET  /health      ──▶  backend/app/main.py (inline handler)
                           └──▶ features/onetrust/browser.py (browser_manager.is_ready)
```

---

## Env Registry

| Variable | Scope | Description | Required |
|----------|-------|-------------|----------|
| `ONETRUST_BASE_URL` | BE | OneTrust instance base URL | Yes |
| `ONETRUST_LOGIN_URL` | BE | Full login page URL | Yes |
| `ONETRUST_EMAIL` | BE | Email to fill on login page | Yes (at request time) |
| `PLAYWRIGHT_HEADLESS` | BE | `false` = headed, `true` = headless | No (default: false) |
| `PLAYWRIGHT_USER_DATA_DIR` | BE | Path to persistent Chromium profile | No (default: `.playwright/onetrust-profile`) |
| `PLAYWRIGHT_TIMEOUT_MS` | BE | SSO wait timeout in milliseconds | No (default: 90000) |
| `DEBUG` | BE | Show full tracebacks in error responses | No (default: false) |
| `ONETRUST_SCAN_TIMEOUT_MS` | BE | Max milliseconds to poll for scan completion | No (default: 300000) |

---

## Pattern Index

| Pattern | Rule | get_symbol command |
|---------|------|--------------------|
| Route handler | Thin: validate → call service → return | `get_symbol backend/app/features/auth/router.py auth_login` |
| Service function | Business logic, catches Playwright errors, raises AppError | `get_symbol backend/app/features/auth/service.py login_onetrust` |
| Settings access | `from app.core.config import settings` — nowhere else | `get_symbol backend/app/core/config.py Settings` |
| BrowserManager | Singleton, persistent Chromium context | `get_symbol backend/app/features/browser/service.py BrowserManager` |
| Error shape | `raise AppError(status_code, msg)` in services → `{detail: str}` | `get_symbol backend/app/core/errors.py AppError` |

---

## Development Log

<!-- Add entries here after each completed feature. Keep last 3 only. -->
- 2026-06-08 — Task 2 complete: POST /auth/login — auth feature fully implemented (is_logged_in, fill_email_and_next, wait_for_sso_completion, handle_post_login_modals, login_onetrust), ruff ✓, mypy ✓
- 2026-06-08 — Task 3 complete: POST /add_app — websites feature fully implemented (ensure_websites_page, click_add_website_button, click_add_website), ruff ✓, mypy ✓, route registered ✓. v1 complete.
- 2026-06-08 — M8 complete: debug responses + email prefill + /add_app extended to 13 steps with scan polling; DebugInfo schema added; scan_timeout_ms config added; ruff ✓, mypy ✓, compileall ✓
