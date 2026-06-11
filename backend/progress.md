# Backend Progress — OneTrust Automation Backend

> **Backend sub-agent memory.** Read this at the start of every backend task.
> Do NOT read source files to orient — this file has everything you need.
> Open a source file only when you are about to edit it, or when a test fails unexpectedly.
> Update after every backend milestone.

---

## Backend Current State

**Last updated:** 2026-06-11

```
BE-APP: onetrust-automation — backend layer
BE-STACK: FastAPI + Playwright | DB: None | ORM: None | AI: None
BE-URL: http://localhost:8000 | prefix: none (bare paths)

BE-MODULES DONE:
  [scaffold]   → main.py, core/config.py, core/errors.py, core/logging.py
  [onetrust]   → features/onetrust/browser.py, auth.py, mapper.py,
                 websites.py, filter_code.py, schemas.py, router.py

BE-ACTIVE: M13 complete — streaming endpoints added

BE-NEXT: none

BE-ENV:
  ONETRUST_BASE_URL                = https://uat-de.onetrust.com  (required)
  ONETRUST_LOGIN_URL               = https://uat-de.onetrust.com/auth/login  (required)
  ONETRUST_EMAIL                   = (required at request time)
  PLAYWRIGHT_HEADLESS              = false  (default)
  PLAYWRIGHT_USER_DATA_DIR         = .playwright/onetrust-profile  (default)
  PLAYWRIGHT_TIMEOUT_MS            = 90000  (default)
  ONETRUST_SCAN_TIMEOUT_MS         = 300000  (default 5 min — for verify_scan_completed polling)
  ONETRUST_WEBSITE_TABLE_TIMEOUT_MS = 120000  (default 2 min — for table load + row search)
  ONETRUST_DEBUG                   = false  (default)

BE-CONTRACTS EXPOSED (source of truth in root progress.md):
  GET  /health               → {status: str, browser_ready: bool}
  POST /auth/login           {} → {status, message, current_url?, handled_modals?, screenshot?, steps?, debug?}
  POST /add_app              {url: str} → {status, message, input_url?, current_url?, screenshot?, steps?, debug?, next_action?}
  POST /add_app/stream       {url: str} → NDJSON stream (application/x-ndjson)
                               events: started | step_started | step_completed | step_failed | finished | error
  POST /filter_code          {url: str} → {status, message, input_url?, normalized_domain?, matched_display_url?,
                                           scan_status?, data_domain_script?, script_snippet?, current_url?,
                                           screenshot?, steps?, debug?}
  POST /filter_code/stream   {url: str} → NDJSON stream (application/x-ndjson)
                               events: started | step_started | step_completed | step_failed | finished | error
  GET  /mapper/default       → {default_experience_kit: str, mode: str}
  POST /mapper/resolve       {url: str} → {url, experience_kit, mode}

BE-PATTERNS:
  Routes     → thin handlers, delegate to services
  Services   → business logic + Playwright calls, catch errors, raise AppError
  Schemas    → Pydantic at every route boundary
  Errors     → {detail: str} — raise AppError(status_code, msg) in services
  Config     → backend/app/core/config.py only, no os.environ elsewhere
  Browser    → BrowserManager singleton in features/onetrust/browser.py
```

---

## Resume Point

**Active task:** M13 complete — streaming endpoints added
**Last file written:** backend/app/features/onetrust/router.py

**Done within M13 (streaming):**
- [x] `add_app_flow(url, emit=None)` — optional emit callback added, all 11 steps emit start/complete/failed
- [x] `filter_code_flow(url, emit=None)` — optional emit callback added, all 12 steps emit start/complete/failed
- [x] `_ndjson_stream()` async generator in router.py — asyncio.Queue + background task pattern
- [x] `POST /add_app/stream` — NDJSON streaming endpoint, media_type=application/x-ndjson
- [x] `POST /filter_code/stream` — NDJSON streaming endpoint, media_type=application/x-ndjson
- [x] Existing routes unchanged — no regression
- [x] debug objects in step_failed events omit cookies/auth/html (only reason/action/exc_type)

**Blockers:** none

---

## File Map

```
backend/
  app/
    main.py                            — FastAPI app, lifespan, exception handlers, /health
    core/
      config.py                        — Settings(BaseSettings): all env vars; settings singleton
                                         Fields: onetrust_base_url, onetrust_login_url, onetrust_email,
                                         playwright_headless, playwright_user_data_dir, playwright_timeout_ms,
                                         onetrust_scan_timeout_ms (300000), onetrust_website_table_timeout_ms (120000),
                                         debug
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
        auth.py                        — login_onetrust(), fill_email_or_confirm_prefilled_email(),
                                         wait_for_sso_completion(), handle_post_login_modals(),
                                         is_logged_in()
        websites.py                    — add_app_flow(url, emit=None) — 11 steps, optional emit callback
                                         confirm_login→open_websites_page→click_add_website→
                                         fill_website_url→continue_to_banner_setup→select_experience_kit→
                                         click_next_after_kit_selection→wait_review_configurations_page→
                                         click_accept_all_preview→click_confirm→wait_return_to_websites_page
        filter_code.py                 — filter_code_flow(url, emit=None) — 12 steps, optional emit callback
                                         confirm_login→open_websites_page→wait_websites_table_loaded→
                                         filter_website→find_website_row→verify_scan_completed→
                                         open_website_details→wait_website_details_page→open_actions_menu→
                                         click_copy_production_scripts→wait_production_scripts_modal→
                                         extract_data_domain_script
                                         Helpers: wait_website_details_ready, click_top_right_actions_menu,
                                         get_production_modal_text, _find_row_for_variants
        mapper.py                      — DEFAULT_EXPERIENCE_KIT, get_experience_kit_for_url()
        schemas.py                     — LoginResponse, AddAppRequest, AddAppResponse,
                                         FilterCodeRequest, FilterCodeResponse, StepResult, DebugInfo,
                                         MapperDefaultResponse, MapperResolveRequest, MapperResolveResponse
        router.py                      — POST /auth/login, POST /add_app, POST /add_app/stream,
                                         POST /filter_code, POST /filter_code/stream,
                                         GET /mapper/default, POST /mapper/resolve
                                         _ndjson_stream() async generator helper
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
- 2026-06-11 — M13 complete: /filter_code reliability fixes — row-specific scan polling, wait_website_details_ready, click_top_right_actions_menu, get_production_modal_text, modal wait-until-data-domain, rich failure debug, ruff ✓, mypy ✓ compileall ✓
- 2026-06-11 — M13 streaming: POST /add_app/stream + POST /filter_code/stream — NDJSON streaming via asyncio.Queue + emit callback pattern; existing routes unchanged; ruff ✓, mypy ✓, compileall ✓
