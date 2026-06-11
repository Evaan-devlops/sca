# Progress — OneTrust Automation Backend

> **Orchestrator memory.** Read `Current State` at the start of every session — not source files.
> Update after every feature milestone.

---

## Current State

> Post-compact restore block. Read this after `/compact` or at any new session start.
> Update after every milestone. Keep under 40 lines.

**Last updated:** 2026-06-11 | **Milestones since /compact:** 10

```
APP: onetrust-automation — FastAPI backend automating authorized OneTrust sandbox workflows via Playwright
STACK: FastAPI + Playwright (backend/) | DB: None | AI: None | Auth: SSO passthrough (no API auth)
PORTS: BE=http://localhost:8000 | prefix: none (bare paths)

FEATURES DONE:
  scaffold (GET /health) — BE ✓
  auth (POST /auth/login) — BE ✓
  websites (POST /add_app) — 11-step wizard (stops at wait_return_to_websites_page) ✓
  mapper (GET /mapper/default, POST /mapper/resolve) — BE ✓
  M8 debug responses + email prefill — BE ✓
  M9 Mac/cross-platform compatibility — config extra="ignore", venv paths ✓
  M10 Websites page SPA readiness — wait_for_websites_page_ready ✓
  M11 Split /add_app + new /filter_code — POST /filter_code 12-step data-domain-script extraction ✓
  M12 Filter code reliability + streaming APIs:
    - verify_scan_completed: row-specific scan-status polling (5s interval, ONETRUST_SCAN_TIMEOUT_MS)
    - wait_website_details_ready: blocks until domain/Completed/Publish/menu all visible
    - click_top_right_actions_menu: picks topmost three-dot button (min y-coordinate)
    - get_production_modal_text: collects from textarea/pre/code/otSDKStub parent
    - wait_production_scripts_modal: polls until data-domain-script present in modal DOM
    - extract_data_domain_script failure: rich debug (screenshot, modal_text_preview, visible_markers)
    - POST /add_app/stream: NDJSON step events via asyncio.Queue + background task
    - POST /filter_code/stream: same pattern ✓

ACTIVE: COMPLETE — M12 done. Run: source .venv/bin/activate && cd backend && uvicorn app.main:app --reload

NEXT: none

KEY DECISIONS:
  bare API paths (no /api/v1/) — per idea.md |
  features/onetrust/ flat module (M4 restructure) |
  tests skipped — per user decision |
  no DB — email from .env only |
  pydantic-settings validation_alias for all fields + extra="ignore" — per M9 spec |
  development is LOCAL ONLY — no git automation |
  streaming uses asyncio.Queue + background task — decouples Playwright I/O from HTTP streaming
GAPS: none
MILESTONES SINCE /compact: 10
```

---

## API Contracts

| Method | Path | Request | Response | Auth | Status |
|--------|------|---------|----------|------|--------|
| GET | `/health` | — | `{status: str, browser_ready: bool}` | No | Task 1 |
| POST | `/auth/login` | `{}` | `{status, message, current_url?, handled_modals?, screenshot?, failed_step?, steps[]?, debug?}` | No | Task 2 |
| POST | `/add_app` | `{url: str}` | `{status, message, input_url?, selected_kit?, current_url?, screenshot?, steps[], next_action?, debug?}` | No | Task 5 |
| POST | `/filter_code` | `{url: str}` | `{status, message, input_url, normalized_domain?, matched_display_url?, scan_status?, data_domain_script?, script_snippet?, current_url?, screenshot?, steps[], debug?}` | No | Task 11 |
| POST | `/add_app/stream` | `{url: str}` | NDJSON stream of step events (`application/x-ndjson`) | No | Task 13 |
| POST | `/filter_code/stream` | `{url: str}` | NDJSON stream of step events (`application/x-ndjson`) | No | Task 13 |
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

POST /filter_code ──▶  backend/app/features/onetrust/router.py
                           └──▶ features/onetrust/filter_code.py (filter_code_flow — 12 steps,
                                                                   wait_websites_table_loaded,
                                                                   _url_variants, _normalize_domain)
                           └──▶ features/onetrust/browser.py (BrowserManager singleton)
                           └──▶ features/onetrust/auth.py (is_logged_in check)

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
| `ONETRUST_SCAN_TIMEOUT_MS` | BE | (Unused after M11 — /add_app no longer polls scan) | No (default: 300000) |
| `ONETRUST_WEBSITE_TABLE_TIMEOUT_MS` | BE | Max ms for table load + row search + scan poll in /filter_code | No (default: 120000) |

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
- 2026-06-09 — M10 complete: SPA readiness fix — wait_for_websites_page_ready (90s poll + reload retry), _find_add_website_button (6-selector cascade), collect_visible_markers; Step 2/3 updated; ruff ✓, mypy ✓
- 2026-06-10 — M11 complete: /add_app cut to 11 steps (status: "website configuration confirmed" + next_action); POST /filter_code added (12-step flow, filter_code.py); ONETRUST_WEBSITE_TABLE_TIMEOUT_MS config; ruff ✓, mypy ✓ (14 files)
