# Backend Progress — OneTrust Automation Backend

> **Backend sub-agent memory.** Read this at the start of every backend task.
> Do NOT read source files to orient — this file has everything you need.
> Open a source file only when you are about to edit it, or when a test fails unexpectedly.
> Update after every backend milestone.

---

## Backend Current State

**Last updated:** 2026-06-08

```
BE-APP: onetrust-automation — backend layer
BE-STACK: FastAPI + Playwright | DB: None | ORM: None | AI: None
BE-URL: http://localhost:8000 | prefix: none (bare paths)

BE-MODULES DONE:
  [scaffold]  → main.py, core/config.py, core/errors.py
  [onetrust]  → features/onetrust/browser.py, auth.py, mapper.py,
                websites.py, schemas.py, router.py

BE-ACTIVE: COMPLETE — all 5 tasks done

BE-NEXT: none — M5 full wizard complete

BE-ENV:
  ONETRUST_BASE_URL       = https://uat-de.onetrust.com  (required)
  ONETRUST_LOGIN_URL      = https://uat-de.onetrust.com/auth/login  (required)
  ONETRUST_EMAIL          = (required at request time)
  PLAYWRIGHT_HEADLESS     = false  (default)
  PLAYWRIGHT_USER_DATA_DIR = .playwright/onetrust-profile  (default)
  PLAYWRIGHT_TIMEOUT_MS   = 90000  (default)
  DEBUG                   = false  (default)

BE-CONTRACTS EXPOSED (source of truth in root progress.md):
  GET  /health       → {status: str, browser_ready: bool}
  POST /auth/login   {} → {status, message, current_url?, handled_modals?, screenshot?}
  POST /add_app      {url: str} → {status, message, input_url?, current_url?, screenshot?}

BE-PATTERNS:
  Routes     → thin handlers, delegate to services
  Services   → business logic + Playwright calls, catch errors, raise AppError
  Schemas    → Pydantic at every route boundary
  Errors     → {detail: str} — raise AppError(status_code, msg) in services
  Config     → backend/app/core/config.py only, no os.environ elsewhere
  Browser    → BrowserManager singleton in features/browser/service.py
```

---

## Resume Point

**Active task:** COMPLETE — all tasks done
**Last file written:** backend/app/features/websites/router.py

**Done within this task (Task 1 — COMPLETE):**
- [x] `backend/requirements.txt`
- [x] `backend/.env.example`
- [x] `backend/app/__init__.py`
- [x] `backend/app/main.py`
- [x] `backend/app/core/__init__.py`
- [x] `backend/app/core/config.py`
- [x] `backend/app/core/logging.py`
- [x] `backend/app/core/errors.py`
- [x] `backend/app/api/__init__.py`
- [x] `backend/app/api/router.py`
- [x] `backend/app/features/__init__.py`
- [x] `backend/app/features/browser/__init__.py`
- [x] `backend/app/features/browser/service.py`
- [x] `backend/screenshots/.gitkeep`

**Done within this task (Task 2 — COMPLETE):**
- [x] `backend/app/features/auth/__init__.py`
- [x] `backend/app/features/auth/schemas.py`  — LoginResponse
- [x] `backend/app/features/auth/service.py`  — login_onetrust(), fill_email_and_next(), wait_for_sso_completion(), handle_post_login_modals(), is_logged_in()
- [x] `backend/app/features/auth/router.py`   — POST /auth/login
- [x] Register auth router in `backend/app/api/router.py`

**Done within this task (Task 3 — COMPLETE):**
- [x] `backend/app/features/websites/__init__.py`
- [x] `backend/app/features/websites/schemas.py`  — AddAppRequest, AddAppResponse
- [x] `backend/app/features/websites/service.py`  — click_add_website(), ensure_websites_page(), click_add_website_button()
- [x] `backend/app/features/websites/router.py`   — POST /add_app
- [x] Register websites router in `backend/app/api/router.py`

**Blockers:** none

---

## File Map

```
backend/
  app/
    main.py                            — FastAPI app, lifespan, exception handlers, /health
    core/
      config.py                        — Settings(BaseSettings): all env vars; settings singleton
      logging.py                       — configure_logging(), shared logger
      errors.py                        — AppError, validation_error_handler,
                                         app_error_handler, global_exception_handler
    api/
      router.py                        — includes onetrust router (no prefix)
    features/
      onetrust/
        __init__.py                    — empty
        browser.py                     — BrowserManager: start(), get_page(), close(),
                                         screenshot_on_error(), is_ready; browser_manager singleton
        auth.py                        — login_onetrust(), fill_email_and_next(),
                                         wait_for_sso_completion(), handle_post_login_modals(),
                                         is_logged_in()
        websites.py                    — click_add_website(), ensure_websites_page(),
                                         click_add_website_button()
        schemas.py                     — LoginResponse, AddAppRequest, AddAppResponse
        router.py                      — POST /auth/login, POST /add_app
  screenshots/                         — error screenshots (gitignored)
  .env.example
  requirements.txt
```

---

## Backend Pattern Index

| Pattern | Rule | get_symbol command |
|---------|------|--------------------|
| Route handler | Thin: validate → call service → return | `get_symbol backend/app/features/onetrust/router.py auth_login` |
| Service | Business logic, catch Playwright errors, raise AppError | `get_symbol backend/app/features/onetrust/auth.py login_onetrust` |
| Settings access | `from app.core.config import settings` — only in app/ | `get_symbol backend/app/core/config.py Settings` |
| BrowserManager | Singleton, persistent Chromium, reusable page | `get_symbol backend/app/features/onetrust/browser.py BrowserManager` |
| Error shape | `raise AppError(status_code, msg)` → `{detail: str}` | `get_symbol backend/app/core/errors.py AppError` |
| Screenshot | `await browser_manager.screenshot_on_error(name)` → path str | `get_symbol backend/app/features/onetrust/browser.py screenshot_on_error` |

---

## DB Schema

None — no database in this version.

---

## Backend Dev Log

<!-- Add entries here after each completed backend milestone. Keep last 3 only. -->
- 2026-06-08 — Task 3 complete: POST /add_app implemented (websites schemas, service, router), ruff ✓, mypy ✓ (19 source files), import smoke-test ✓, route registered ✓
- 2026-06-08 — Task 5 complete: full 7-step /add_app wizard + mapper.py + /mapper/default + /mapper/resolve, IMPLEMENTATION_REPORT.md created, ruff ✓, mypy ✓ (13 source files)
- 2026-06-08 — Task 6 complete: pre-live hardening — Field default_factory, URL validator, enabled-state waits, kit regex, post-nav SSO check, report updated, ruff ✓, mypy ✓
