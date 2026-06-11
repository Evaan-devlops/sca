# Implementation Report — OneTrust Automation Backend

Generated: 2026-06-08

---

## 1. Summary of Implemented Changes

The FastAPI + Playwright backend for authorized OneTrust sandbox automation was built in five milestones:

- **M1–M3**: Core scaffold, login endpoint, initial `/add_app` (click-only stub)
- **M4**: Structural cleanup — consolidated all features under `features/onetrust/`; removed dead code
- **M5** (current): Enhanced `/add_app` to complete the full Add Website wizard (7 sequential steps); added `mapper.py` service; added `GET /mapper/default` and `POST /mapper/resolve` endpoints

---

## 2. Final Folder Tree

```
scrapper/
  backend/
    app/
      __init__.py
      main.py                          FastAPI app, lifespan, /health
      core/
        __init__.py
        config.py                      pydantic-settings (all env vars)
        errors.py                      AppError + 3 exception handlers
      features/
        __init__.py
        onetrust/
          __init__.py
          auth.py                      login_onetrust, is_logged_in, SSO wait, modal handling
          browser.py                   BrowserManager singleton (persistent Chromium)
          mapper.py                    DEFAULT_EXPERIENCE_KIT, get_experience_kit_for_url
          router.py                    All routes: /auth/login, /add_app, /mapper/*
          schemas.py                   All Pydantic models
          websites.py                  add_app_flow (7-step wizard)
    screenshots/
      .gitkeep                         Error screenshots land here (gitignored)
    .env.example
    requirements.txt
```

---

## 3. APIs

### `GET /health`
```json
{ "status": "ok", "browser_ready": false }
```

### `POST /auth/login`
Request: `{}`

Success:
```json
{
  "status": "logged in",
  "message": "OneTrust login completed and sandbox page reached",
  "current_url": "https://uat-de.onetrust.com/cookies/websites",
  "handled_modals": ["scheduled maintenance"]
}
```

SSO timeout:
```json
{
  "status": "SSO issue",
  "message": "SSO did not complete within timeout. Please complete SSO manually in the opened browser, then retry.",
  "current_url": "https://pingidentity.pfizer.com/..."
}
```

### `POST /add_app`
See Section 4.

### `GET /mapper/default`
```json
{
  "default_experience_kit": "US- Geolocation Category test",
  "mode": "default_for_all_urls"
}
```

### `POST /mapper/resolve`
Request: `{ "url": "https://www.example.com" }`
```json
{
  "url": "https://www.example.com",
  "experience_kit": "US- Geolocation Category test",
  "mode": "default_for_all_urls"
}
```

---

## 4. `/add_app` Request & Response Examples

### Request
```json
{ "url": "https://www.pfizerguidesources.com" }
```

### Success response
```json
{
  "status": "new user wizard selection done",
  "message": "Website URL added and default experience kit selected.",
  "input_url": "https://www.pfizerguidesources.com",
  "selected_kit": "US- Geolocation Category test",
  "current_url": "https://uat-de.onetrust.com/cookies/...",
  "screenshot": null,
  "steps": [
    { "step": "confirm_login",               "status": "completed" },
    { "step": "open_websites_page",           "status": "completed" },
    { "step": "click_add_website",            "status": "completed" },
    { "step": "fill_website_url",             "status": "completed", "value": "https://www.pfizerguidesources.com" },
    { "step": "continue_to_banner_setup",     "status": "completed" },
    { "step": "select_experience_kit",        "status": "completed", "selected_kit": "US- Geolocation Category test" },
    { "step": "click_next_after_kit_selection", "status": "completed" }
  ]
}
```

### Not logged in
```json
{
  "status": "not logged in",
  "message": "Please call /auth/login first or complete SSO in the opened browser.",
  "input_url": "https://www.pfizerguidesources.com",
  "current_url": "https://uat-de.onetrust.com/auth/login",
  "steps": [
    { "step": "confirm_login", "status": "failed", "message": "Not logged in" }
  ]
}
```

### Step failure (example: kit not found)
```json
{
  "status": "failed",
  "message": "Step 'select_experience_kit' failed: ...",
  "input_url": "https://www.pfizerguidesources.com",
  "selected_kit": "US- Geolocation Category test",
  "current_url": "https://uat-de.onetrust.com/cookies/...",
  "screenshot": "screenshots/select_experience_kit_20260608_152500.png",
  "steps": [
    { "step": "confirm_login",           "status": "completed" },
    { "step": "open_websites_page",      "status": "completed" },
    { "step": "click_add_website",       "status": "completed" },
    { "step": "fill_website_url",        "status": "completed", "value": "https://www.pfizerguidesources.com" },
    { "step": "continue_to_banner_setup","status": "completed" },
    { "step": "select_experience_kit",   "status": "failed", "message": "Experience kit card not found" }
  ]
}
```

---

## 5. Files Changed

| File | Change |
|------|--------|
| `backend/app/features/onetrust/mapper.py` | **Created** — default kit constant + resolver function |
| `backend/app/features/onetrust/schemas.py` | **Updated** — added `StepResult`, `MapperDefaultResponse`, `MapperResolveRequest`, `MapperResolveResponse`; updated `AddAppResponse` |
| `backend/app/features/onetrust/websites.py` | **Rewritten** — replaced `click_add_website` with `add_app_flow` (7 steps) |
| `backend/app/features/onetrust/router.py` | **Updated** — `/add_app` now calls `add_app_flow`; added `/mapper/default` + `/mapper/resolve` |

---

## 6. Default Experience Kit Mapping

Defined in `backend/app/features/onetrust/mapper.py`:

```python
DEFAULT_EXPERIENCE_KIT = "US- Geolocation Category test"

def get_experience_kit_for_url(url: str) -> str:
    return DEFAULT_EXPERIENCE_KIT
```

All URLs currently map to this single default. The function signature is designed so domain-specific logic can be added later without changing callers.

---

## 7. Login Check Before `/add_app`

`add_app_flow` in `websites.py` calls `is_logged_in(page)` as Step 1 before any navigation:

```python
if not await is_logged_in(page):
    steps.append({"step": "confirm_login", "status": "failed", "message": "Not logged in"})
    return { "status": "not logged in", ... }
```

`is_logged_in` checks:
- URL contains any of: `onetrust.com/home`, `/welcome`, `/cookies`, `/privacy`, `/assessments`
- OR page body contains: `"Sandbox Environment"`, `"My apps"`, `"Cookie Consent"`

---

## 8. Selectors Used

### Add website button (Step 3)
```python
page.get_by_role("button", name=re.compile(r"Add website", re.I))
# fallback:
page.get_by_text("Add website", exact=False)
# fallback:
page.locator("button:has-text('Add website')")
```

### URL input (Step 4)
```python
page.get_by_label(re.compile(r"URL", re.I))
# fallback:
page.locator("input[placeholder*='example.com' i]")
# fallback:
page.locator("input[type='url']")
```

### Continue to banner setup button (Step 5)
```python
page.get_by_role("button", name=re.compile(r"Continue to banner setup", re.I))
# fallback:
page.locator("button:has-text('Continue to banner setup')")
```

### US- Geolocation Category test card (Step 6)
```python
page.get_by_text(re.compile(r"US.{0,3}Geolocation Category test", re.I))
# fallback (scroll into view, then click):
await kit_locator.first.scroll_into_view_if_needed(timeout=5000)
# fallback (search box):
search_box = page.get_by_role("searchbox")
await search_box.fill("US- Geolocation Category test")
# then click the matching card
```

### Next button (Step 7)
```python
page.get_by_role("button", name=re.compile(r"^Next$", re.I))
# fallback:
page.locator("button:has-text('Next')")
```

---

## 9. Error-Handling Behavior

Each step in `add_app_flow` is wrapped in `try/except`:
- On failure: logs the error with step name + current URL
- Appends `{"step": NAME, "status": "failed", "message": str(exc)}` to `steps`
- Returns immediately with `status: "failed"` + all partial steps completed so far
- Does **not** continue to remaining steps after a failure

The outer `except Exception` pattern ensures no raw Python exceptions escape to the API response. All errors are converted to JSON with a `"status": "failed"` shape.

---

## 10. Screenshot-on-Error Behavior

On any step failure, `browser_manager.screenshot_on_error(step_name)` is called:
- Saves a timestamped PNG to `backend/screenshots/` (e.g. `select_experience_kit_20260608_152500.png`)
- The path is returned in the API response as the `screenshot` field
- Screenshots are **for debugging only** — not used as automation input
- `screenshots/*.png/jpg/jpeg/webp` are gitignored

---

## 11. How to Run

```bash
cd backend
cp .env.example .env        # fill ONETRUST_EMAIL
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Required `.env` values:
```
ONETRUST_BASE_URL=https://uat-de.onetrust.com
ONETRUST_LOGIN_URL=https://uat-de.onetrust.com/auth/login
ONETRUST_EMAIL=your.email@pfizer.com
PLAYWRIGHT_HEADLESS=false
```

Typical flow:
1. `POST /auth/login` — opens browser, fills email, waits for SSO (complete manually if needed)
2. `POST /add_app {"url": "https://www.pfizerguidesources.com"}` — runs the full wizard

---

## 12. Assumptions and Limitations

| Item | Detail |
|------|--------|
| Kit selection | Matched with `re.compile(r"US\s*-?\s*Geolocation Category test", re.I)` — tolerates `"US-"`, `"US -"`, `"US - "` spacing variants |
| Wizard stops after Step 7 | After clicking Next on the experience kit page, the flow stops and returns. No further pages are automated in this phase. |
| URL field detection | Three fallback selectors used; if none match, the step fails with a screenshot |
| Continue button enabled | `wait_for(state="enabled", timeout=15000)` — raises `RuntimeError` with clear message if button doesn't enable |
| SSO passthrough | SSO/PingID/GlobalProtect/MFA are never bypassed. If SSO requires manual action, `/auth/login` returns `"SSO issue"` and the browser stays open for manual completion |
| Persistent profile | Session is stored in `PLAYWRIGHT_USER_DATA_DIR` (default: `.playwright/onetrust-profile`). Delete this folder to force a fresh login |
| Single browser tab | The automation reuses one persistent page across all API calls |

---

## 13. Manual Test Results

Not yet tested against the live OneTrust sandbox — testing requires VPN + Pfizer SSO passthrough on the user's machine. All code verified with `ruff check` + `mypy` (zero errors, 13 source files).

---

## 14. Hardening Pass (M6) — 2026-06-08

Changes made before live testing:

### What changed

| Fix | File | Detail |
|-----|------|--------|
| Mutable default | `schemas.py` | `steps: list[StepResult] = []` → `Field(default_factory=list)` |
| URL validation | `schemas.py` | `@field_validator("url")` on `AddAppRequest` — rejects non-http(s) with 422 |
| Continue button state | `websites.py` Step 4 | `wait_for("visible")` → `wait_for("enabled", timeout=15000)` + explicit RuntimeError |
| Kit regex | `websites.py` Step 6 | `US.{0,3}` → `US\s*-?\s*` (tolerates hyphen spacing variants) |
| Next button state | `websites.py` Step 6 | `wait_for("visible")` → `wait_for("enabled", timeout=10000)` + explicit RuntimeError |
| Post-nav login check | `websites.py` Step 2 | After goto, checks URL for SSO indicators; returns `"not logged in"` if redirected |

### .gitignore confirmed

All required patterns present:
```
.venv/              ✓
__pycache__/        ✓
.mypy_cache/        ✓
.ruff_cache/        ✓
.pytest_cache/      ✓
.env                ✓
.playwright/        ✓
backend/screenshots/*.png   ✓
backend/screenshots/*.jpg   ✓
backend/screenshots/*.jpeg  ✓
backend/screenshots/*.webp  ✓
```

### Verification

- `ruff check app/` — All checks passed
- `mypy app/ --ignore-missing-imports` — Success: no issues found in 13 source files

### Live test status

Not yet tested — hardening pass complete and ready for first live run.

---

## 15. Portability Pass (M7) — 2026-06-08

### Critical runtime fix

`locator.wait_for(state="enabled")` is **not a valid Playwright state** — valid values are `"attached"`, `"detached"`, `"visible"`, `"hidden"`. This would raise `ValueError` at runtime on Steps 4 and 6.

**Fixed in `websites.py`** using the correct Playwright assertion API:
```python
from playwright.async_api import expect

# Step 4 — Continue to banner setup
await expect(continue_btn.first).to_be_enabled(timeout=15000)

# Step 6 — Next button after kit selection
await expect(next_btn.first).to_be_enabled(timeout=10000)
```

### Other changes

| Fix | File | Detail |
|-----|------|--------|
| `expect` import | `websites.py` | Added `from playwright.async_api import Page, expect` |
| MapperResolveRequest validator | `schemas.py` | Added same `@field_validator("url")` as `AddAppRequest` |
| `backend/.gitignore` | Created | Backend-scoped gitignore for portability |
| `backend/README.md` | Created | Windows setup + run instructions |

### Packaging verification

`backend_onetrust.zip` created at repo root. Contents:

```
backend/.env.example          ✓
backend/.gitignore             ✓
backend/IMPLEMENTATION_REPORT.md  ✓
backend/README.md              ✓
backend/app/__init__.py        ✓
backend/app/core/...           ✓
backend/app/features/onetrust/ ✓
backend/app/main.py            ✓
backend/requirements.txt       ✓
backend/screenshots/.gitkeep   ✓
```

Excluded from zip:
- `__pycache__/` ✓
- `.mypy_cache/` ✓
- `.ruff_cache/` ✓
- `.pytest_cache/` ✓
- `.venv/` ✓
- `.playwright/` ✓
- `.env` ✓
- `screenshots/*.png/jpg/jpeg/webp` ✓
- SPL orchestration files (`agents.md`, `progress.md`) ✓

### Local checks (M7)

```
python -m compileall app/  — OK (no syntax errors)
ruff check app/            — All checks passed
mypy app/ --ignore-missing-imports — Success: no issues found in 13 source files
```

---

## 16. M8 — Debug Responses + Email Prefill + Extended /add_app (Steps 8–13)

Generated: 2026-06-08

### APIs Updated

- `POST /auth/login` — now returns `failed_step`, `steps[]`, and `debug` object on failure/SSO issue
- `POST /add_app` — extended from 7 to 13 steps; final status is `"website url scan_status completed"`; adds `scan_status`, `matched_display_url`, `debug` to response

### New Schema: DebugInfo

All optional fields. Never includes passwords, cookies, auth tokens, or full HTML.

Fields: `step`, `current_url`, `page_title`, `timestamp`, `screenshot`, `browser_headless`, `user_data_dir`, `possible_reason`, `next_action`, `visible_markers`, `exception_type`, `exception_message`

### Email Prefill Logic (`/auth/login`)

Step `fill_email_or_confirm_prefilled_email`:
1. Read current value of email input
2. If empty → fill from `ONETRUST_EMAIL` (`email_action: "filled_from_env"`)
3. If matches env email (case-insensitive) → keep (`email_action: "kept_existing"`)
4. If different → clear and fill (`email_action: "replaced_existing"`)
Email is masked in debug/log output (`s*****@pfizer.com` format).

### /add_app — Full 13-Step Flow

| Step | Name | Action |
|------|------|--------|
| 1 | `confirm_login` | Check `is_logged_in()` |
| 2 | `open_websites_page` | Navigate to `/cookies/websites` |
| 3 | `click_add_website` | Click Add website button |
| 4 | `fill_website_url` | Fill URL field |
| 5 | `continue_to_banner_setup` | Click Continue button |
| 6 | `select_experience_kit` | Click kit card (scroll/search fallback) |
| 7 | `click_next_after_kit_selection` | Click Next |
| 8 | `wait_review_configurations_page` | Wait for "Review configurations" heading |
| 9 | `click_accept_all_preview` | Click Accept All (main page → frames; skips if Confirm already enabled) |
| 10 | `click_confirm` | Wait until Confirm enabled, then click |
| 11 | `wait_return_to_websites_page` | Wait for `/cookies/websites` URL |
| 12 | `find_website_row` | Normalize URL, search table, return matched row text |
| 13 | `wait_scan_status_completed` | Poll every 5s up to `ONETRUST_SCAN_TIMEOUT_MS` |

### URL Normalization (Step 12)

Input `https://www.pfizerguidesources.com` → search with `www.pfizerguidesources.com`.
Also tries `pfizerguidesources.com` (without www) if first not found.

### Scan Status Polling (Step 13)

- Poll interval: 5 seconds
- Timeout: `ONETRUST_SCAN_TIMEOUT_MS` (default 300000 ms / 5 minutes)
- Terminates on: "Completed" (success), "Failed"/"Error" in row text (scan failed), or timeout (failed)
- Attempts to click refresh button if available between polls

### New Env Variable

`ONETRUST_SCAN_TIMEOUT_MS=300000` — configurable scan wait timeout

### Files Changed

| File | Change |
|------|--------|
| `backend/app/features/onetrust/schemas.py` | Added `DebugInfo`; added fields to `LoginResponse`, `AddAppResponse`, `StepResult` |
| `backend/app/features/onetrust/auth.py` | Renamed `fill_email_and_next` → `fill_email_or_confirm_prefilled_email`; added prefill logic, debug helpers, step tracking |
| `backend/app/features/onetrust/websites.py` | Added URL normalize helpers, `_build_debug`, steps 8–13 |
| `backend/app/core/config.py` | Added `scan_timeout_ms: int = 300000` |
| `backend/.env.example` | Added `ONETRUST_SCAN_TIMEOUT_MS=300000` |

### Verification

```
python -m compileall app/  — OK (no syntax errors)
ruff check app/            — All checks passed
mypy app/ --ignore-missing-imports — Success: no issues found in 13 source files
```

---

## 17. M9 - Mac Runtime Setup Fix

Generated: 2026-06-08

### Changes

- Fixed pydantic-settings v2 env handling in `backend/app/core/config.py`.
- Added `SettingsConfigDict(extra="ignore")` so extra `.env` keys do not crash startup.
- Added `onetrust_scan_timeout_ms` config field and kept env variable `ONETRUST_SCAN_TIMEOUT_MS`.
- `ONETRUST_EMAIL` no longer crashes the app at import time.
- `/auth/login` returns a clean configuration error JSON response if `ONETRUST_EMAIL` is missing.
- Confirmed no `locator.wait_for(state="enabled")` or `wait_for("enabled")` usage remains.
- Added Mac setup and VS Code interpreter instructions to `backend/README.md`.
- Added `backend/check_setup.py`.
- Confirmed `backend/.env.example` has the expected runtime keys.
- Confirmed `backend/requirements.txt` includes the required setup/runtime packages.

### Commands run and results

| Command | Result |
|---------|--------|
| `python -m pip install --upgrade pip` | Passed; pip upgraded to 26.1.2 in the existing backend venv |
| `pip install -r requirements.txt` | Passed; requirements satisfied |
| `python -m playwright install chromium` | Timed out twice while checking/installing Chromium in this Windows environment |
| `python check_setup.py` | Passed; `SETUP OK` |
| `python -m compileall app` | Passed |
| `ruff check app/` | Passed |
| `mypy app/` | Passed |
| `python -m uvicorn app.main:app --reload` | Direct long-running command timed out; controlled uvicorn startup on `127.0.0.1:8010` passed and was stopped |

---

## 18. M10 - Cross-platform Mac/Windows VS Code Setup

Generated: 2026-06-09

### Changes

- README now has separate Mac and Windows setup flows from the repo root.
- `.vscode/settings.json` added without a hardcoded interpreter path.
- No hardcoded Windows runtime paths remain in source files.
- Runtime Playwright paths use `pathlib.Path`; the user data dir resolves via `Path(settings.playwright_user_data_dir).resolve()`.
- Screenshots directory is created with `mkdir(parents=True, exist_ok=True)`.
- Root `.gitignore` updated for Mac/Windows artifacts, Python caches, Playwright output, env files, and debug screenshots.
- Cache/generated files removed from the working package while keeping `backend/screenshots/.gitkeep`.

### Commands run and results

| Command | Result |
|---------|--------|
| `rg -n -F -e "\\Scripts\\" -e "Activate.ps1" -e "C:\\" -e "copy .env.example .env" -e "/Users/" -e "Users\\" .` | Matches expected setup documentation only |
| `python check_setup.py` | Failed in this Windows workspace: `No module named 'playwright'` in the available system Python |
| `python -m compileall app` | Passed |
| `ruff check app/` | Passed |
| `mypy app/ --ignore-missing-imports` | Passed |
| `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010` | Failed before startup: `No module named 'playwright'` in the available system Python |

### Remaining issue

The current Windows workspace does not have a project virtual environment or Playwright installed for the available system Python, so `check_setup.py` and uvicorn startup cannot complete here until dependencies are installed.

---

## 19. M10 — Websites Page SPA Readiness Fix

Generated: 2026-06-09

### Problem

`/add_app` Step 3 (`click_add_website`) was failing with "Could not find or click the 'Add website' button" because the OneTrust Websites SPA renders the `<h1>Websites</h1>` heading immediately but loads the table and action buttons asynchronously. Step 2 (`open_websites_page`) was completing as soon as `"text=Websites"` matched — before the button was visible.

### Root cause

`ensure_websites_page` waited only for `"text=Websites"` (15s). The "Add website" button appears 5–30s later once the SPA finishes hydrating. `click_add_website_button` then fired against a page still showing a spinner.

### Changes

**`backend/app/features/onetrust/websites.py`**

- Added `Locator` to `playwright.async_api` imports.
- Removed `ensure_websites_page(page) -> None` and `click_add_website_button(page) -> bool`.
- Added `_find_add_website_button(page) -> Locator | None` — 6-selector cascade (role, exact text, `:has-text`, data-testid, class, `<a>` fallback).
- Added `collect_visible_markers(page) -> list[str]` — probes 9 page markers for debug output.
- Added `wait_for_websites_page_ready(page) -> None`:
  - Navigate to `/cookies/websites` if not already there.
  - Wait for heading (`text=Websites`, 15s).
  - Try `networkidle` non-blocking (5s).
  - Poll 60s (every 5s) calling `_find_add_website_button`; return on first hit.
  - One reload, then 30s retry poll.
  - Raise `RuntimeError` after 90s total.
- Step 2 (`open_websites_page`): calls `wait_for_websites_page_ready` instead of `ensure_websites_page`; failure response now includes `debug` with `collect_visible_markers` output.
- Step 3 (`click_add_website`): calls `_find_add_website_button` + `expect().to_be_visible()` + `expect().to_be_enabled()` + `scroll_into_view_if_needed()` before clicking.

### Commands run and results

| Command | Result |
|---------|--------|
| `ruff check app\features\onetrust\websites.py` | All checks passed |
| `mypy app\features\onetrust\websites.py --ignore-missing-imports` | Success: no issues found |

---

## 20. M12 — Split Add App and Filter Code Extraction

Generated: 2026-06-10

### Reason for split

`/add_app` was failing at `find_website_row` because OneTrust returns to the Websites list immediately after Confirm but the table rows load asynchronously. Splitting the flow into two independent APIs eliminates the race condition and gives the caller control over when to fetch the script.

### `/add_app` changes (11 steps)

- Removed Steps 12 (`find_website_row`) and 13 (`wait_scan_status_completed`).
- New success status: `"website configuration confirmed"`.
- New `next_action` field in response guides caller to `/filter_code`.
- `AddAppResponse` no longer contains `scan_status` or `matched_display_url`; gains `next_action: dict | None`.

### New `/filter_code` API (12 steps)

| Step | Name | Action |
|------|------|--------|
| 1 | `confirm_login` | Check session |
| 2 | `open_websites_page` | Navigate to `/cookies/websites` |
| 3 | `wait_websites_table_loaded` | Poll for table controls (not just heading) |
| 4 | `filter_website` | Search by root domain keyword |
| 5 | `find_website_row` | Find row; poll up to `ONETRUST_WEBSITE_TABLE_TIMEOUT_MS` |
| 6 | `verify_scan_completed` | Poll row for "Completed" status |
| 7 | `open_website_details` | Click URL link in row |
| 8 | `wait_website_details_page` | Wait for details page + Publish button |
| 9 | `open_actions_menu` | Click three-dot button near Publish |
| 10 | `click_copy_production_scripts` | Click menu item |
| 11 | `wait_production_scripts_modal` | Wait for modal with `data-domain-script` |
| 12 | `extract_data_domain_script` | Regex-extract value |

### URL normalization

- `http://www.hitestom.com` → variants: `www.hitestom.com`, `hitestom.com`, `http://www.hitestom.com`, `https://www.hitestom.com`
- Search keyword: root domain only (e.g. `hitestom`)

### Table loading wait

`wait_websites_table_loaded` checks for: "Website URL", "Scan status", search input, "Add website" button, `[role='row']`, "No records found". Polls every 3s up to `ONETRUST_WEBSITE_TABLE_TIMEOUT_MS`.

### Three-dot menu selection

Selects the button near Publish/Publish test. If multiple `More` buttons exist, uses `bounding_box()` Y-coordinate comparison to pick the topmost one.

### New env var

`ONETRUST_WEBSITE_TABLE_TIMEOUT_MS=120000` — max ms for table load + row search + scan polling.

### New files

- `backend/app/features/onetrust/filter_code.py` — `filter_code_flow`, `wait_websites_table_loaded`, helpers

### Files changed

- `backend/app/features/onetrust/websites.py` — removed steps 12-13; new success response
- `backend/app/features/onetrust/schemas.py` — `AddAppResponse` updated; `FilterCodeRequest` + `FilterCodeResponse` added
- `backend/app/features/onetrust/router.py` — `POST /filter_code` registered
- `backend/app/core/config.py` — `onetrust_website_table_timeout_ms` field added
- `backend/.env.example` — `ONETRUST_WEBSITE_TABLE_TIMEOUT_MS=120000` added

### Commands run and results

| Command | Result |
|---------|--------|
| `ruff check app\` | All checks passed |
| `mypy app\ --ignore-missing-imports` | Success: no issues found in 14 source files |

---

## 21. M13 — Filter Code Wait/Extraction Fix

Generated: 2026-06-11

### Problems fixed

| # | Problem | Root cause |
|---|---------|------------|
| 1 | `verify_scan_completed` passed before Pending became Completed | Checked whole page for "Completed" instead of specific matched row only |
| 2 | `wait_website_details_page` completed too early | Used a single `wait_for_selector("text=Website details")` which matched before Publish button, domain, Completed chip, and actions menu were all present |
| 3 | `open_actions_menu` could pick wrong three-dot button | Two More menus on details page (top-right near Publish; lower near Scan now); code didn't guarantee picking top-right |
| 4 | `wait_production_scripts_modal` completed before `data-domain-script` rendered | Checked for structural modal markers but not that modal text actually contained the script attribute |
| 5 | `extract_data_domain_script` failure response was not diagnostic | Only returned generic `debug` — missing `modal_text_preview`, `failed_step`, `next_action` fields useful for pasting to ChatGPT |

### Fixes

#### 1. Row-specific scan status polling (`verify_scan_completed`)

- Added `_find_row_for_variants(page, variants)` helper — re-locates the specific matched row and returns its text.
- `verify_scan_completed` now uses `_find_row_for_variants` exclusively; never scans the whole page.
- Timeout changed from `table_timeout_ms` → `settings.onetrust_scan_timeout_ms` (default 300000ms).
- Emits structured log lines: `"verify_scan_completed started"`, `"current scan status: Pending"`, `"waiting 5 seconds"`, `"current scan status: Completed"`.
- On each poll: re-applies search filter, tries refresh button, re-finds row.
- Timeout response includes `scan_status: <last_status>` field.

#### 2. Full website details readiness wait (`wait_website_details_ready`)

New `wait_website_details_ready(page: Page, domain: str) -> None` helper. Polls up to 60s for **all** of:
1. URL matches `/cookies/scan-results/`
2. `"Website details"` text visible
3. Domain text visible (e.g. `www.hiomtest.com`)
4. `"Completed"` chip/text visible
5. `"Publish"` or `"Publish test"` button visible
6. Top-right actions menu button visible (aria-label contains More/Options/Actions)
7. No spinner/loading overlay

Step 8 (`wait_website_details_page`) now calls `wait_website_details_ready(page, normalized_domain)`.

#### 3. Top-right actions menu selection (`click_top_right_actions_menu`)

New `click_top_right_actions_menu(page: Page) -> None` helper:
- Checks candidates: `button[name~=More]`, `More options`, `aria-label*=More/Options/Actions`
- For each visible candidate, reads bounding box; picks the one with **smallest `y` coordinate** (topmost = closest to Publish buttons)
- After clicking, waits for `"Copy production scripts"` text (timeout 10s); raises `RuntimeError` with screenshot path if not found

Step 9 (`open_actions_menu`) now calls `click_top_right_actions_menu(page)`.

#### 4. Modal text collection from DOM descendants (`get_production_modal_text`)

New `get_production_modal_text(page: Page) -> str` helper:
- Locates `[role='dialog']` first; falls back to nearest ancestor of `"Production scripts"` text, then `[class*='modal']`, then `body`
- Collects from: `modal.inner_text()`, all `textarea` elements (input_value + inner_text), all `pre` elements, all `code` elements, parent/grandparent of elements containing `otSDKStub.js`
- Normalises whitespace (collapses spaces/tabs, trims 3+ newlines to 2)
- Does NOT collect full page HTML — modal/dialog subtree only

#### 5. Modal waits until script text is present (`wait_production_scripts_modal`)

Step 11 now polls up to 30s (6 × 5s iterations), checking **all 6 conditions** per iteration:
1. `"Production scripts"` heading
2. `"Use on your production website"` text
3. `"Copy scripts"` button
4. `"Close"` button
5. Modal text contains `otSDKStub.js`
6. Modal text contains `data-domain-script`

Uses `get_production_modal_text(page)` to check conditions 5 and 6.

#### 6. Robust extraction with fallback regex (`extract_data_domain_script`)

Step 12:
- Primary regex: `data-domain-script=["']([^"']+)["']` on raw modal text
- Fallback regex: same pattern on whitespace-normalised modal text (handles broken line-wraps)
- `script_snippet` set to the specific line containing `otSDKStub.js`
- Failure response includes all required diagnostic fields:
  - `screenshot`, `current_url`, `page_title`, `visible_markers`
  - `modal_text_preview` (first 1000 chars)
  - `failed_step`, `next_action`, `possible_reason`

### Files changed

| File | Change |
|------|--------|
| `backend/app/features/onetrust/filter_code.py` | Rewrote Steps 6, 8, 9, 11, 12; added helpers `_find_row_for_variants`, `wait_website_details_ready`, `click_top_right_actions_menu`, `get_production_modal_text` |
| `backend/backend/progress.md` | Updated to M13 state (was stale at M5) |

### Verification

| Command | Result |
|---------|--------|
| `python -m compileall app` | OK — no syntax errors |
| `python -m ruff check app/` | All checks passed |
| `python -m mypy app/ --ignore-missing-imports` | Success: no issues found in 14 source files |

---

## 22. M13 — Streaming APIs

Generated: 2026-06-11

### New Endpoints

| Endpoint | Method | Content-Type | Description |
|----------|--------|--------------|-------------|
| `POST /add_app/stream` | POST | `application/x-ndjson` | NDJSON stream of all 11 add_app steps |
| `POST /filter_code/stream` | POST | `application/x-ndjson` | NDJSON stream of all 12 filter_code steps |

### Stream Event Format

Each line is a JSON object terminated by `\n`:

```
{"event":"started","api":"add_app","input_url":"http://www.example.com"}
{"event":"step_started","step":"confirm_login"}
{"event":"step_completed","step":"confirm_login"}
{"event":"step_started","step":"open_websites_page"}
{"event":"step_completed","step":"open_websites_page"}
...
{"event":"finished","status":"website configuration confirmed","result":{...}}
```

On step failure:
```
{"event":"step_failed","step":"fill_website_url","message":"...","debug":{...}}
{"event":"finished","status":"failed","result":{...}}
```

On unhandled exception:
```
{"event":"error","message":"..."}
```

### Security

`debug` objects in `step_failed` events contain only: `possible_reason`, `next_action`, `exception_type`. No cookies, auth headers, SSO tokens, or full page HTML are streamed.

### Implementation Pattern

**`emit` callback** — `add_app_flow` and `filter_code_flow` accept an optional `emit: Callable[[dict], Awaitable[None]] | None = None` parameter. When `None` (default), all existing callers continue to work unchanged.

**`_ndjson_stream` helper** in `router.py` — creates an `asyncio.Queue`, passes an `emit` closure that puts events onto the queue, runs the flow function as an `asyncio.Task`, and drains the queue line by line until the `None` sentinel is received.

**`StreamingResponse`** is used instead of a regular JSON response; `response_model=` is intentionally omitted (incompatible with `StreamingResponse`).

### Files Changed

| File | Change |
|------|--------|
| `backend/app/features/onetrust/websites.py` | `add_app_flow` signature → `(url, emit=None)`; emit calls added at all 11 steps |
| `backend/app/features/onetrust/filter_code.py` | `filter_code_flow` signature → `(url, emit=None)`; emit calls added at all 12 steps |
| `backend/app/features/onetrust/router.py` | Added `asyncio`, `json`, `StreamingResponse`, `AsyncGenerator` imports; added `_ndjson_stream()` helper; added `POST /add_app/stream` and `POST /filter_code/stream` routes |

### Verification

| Command | Result |
|---------|--------|
| `python -m compileall app` | OK — no syntax errors |
| `python -m ruff check app/` | All checks passed |
| `python -m mypy app/ --ignore-missing-imports` | Success: no issues found in 14 source files |

---

## 23. M14 — GitHub Copilot Skill Packaging

Generated: 2026-06-11

### Skill name

`onetrust-cookie-consent-automation`

### Skill folder

```
.github/skills/onetrust-cookie-consent-automation/
```

### Files created

| File | Purpose |
|------|---------|
| `.github/skills/onetrust-cookie-consent-automation/SKILL.md` | Copilot orchestration guide — 10 sections: purpose, when to use, backend requirements, 4-step flow, success/failure formats, security rules, implementation rule |
| `.github/skills/onetrust-cookie-consent-automation/README.md` | User-facing guide: Copilot Chat usage, prerequisites, troubleshooting |
| `.github/skills/onetrust-cookie-consent-automation/examples/user-request.md` | Example Copilot Chat prompts and `idea.md` request formats |
| `.github/skills/onetrust-cookie-consent-automation/examples/success-response.md` | Sample success output with `data_domain_script`, `script_snippet`, completed steps |
| `.github/skills/onetrust-cookie-consent-automation/examples/failure-response.md` | Sample failure outputs for extract failure, SSO issue, website not found |
| `.github/skills/onetrust-cookie-consent-automation/examples/python-client-reference.py` | Reference Python client (documentation only) |
| `.github/copilot-instructions.md` | Project-level trigger instruction for Copilot |

### How Copilot detects when to use the skill

The `SKILL.md` frontmatter `description:` explicitly names `/auth/login`, `/add_app`, `/filter_code`. `.github/copilot-instructions.md` adds a project-level trigger. Copilot matches on: OneTrust automation, add website, data-domain-script, production script.

### Three backend tools used

| Step | API | Purpose |
|------|-----|---------|
| 1 | `GET /health` | Confirm backend is alive |
| 2 | `POST /auth/login` | Open browser session, complete SSO passthrough |
| 3 | `POST /add_app` | Add website + confirm experience kit (11 steps) |
| 4 | `POST /filter_code` | Find row, verify scan, extract `data-domain-script` (12 steps) |

Streaming variants preferred when available.

### Example user prompt

```
Use OneTrust automation for https://www.hiomtest.com and give me the production data-domain-script.
```

### Security restrictions

Never bypass SSO/MFA/PingID/CAPTCHA. Never expose cookies, tokens, auth headers. No full page HTML. No OCR/screenshot/pixel automation. Authorized sandbox access only.

### Backend changes

None — all existing Python files unchanged.

### Verification

| Item | Result |
|------|--------|
| `python -m compileall app` | OK — no backend Python changes |
| `.github/` files created | 7 new files confirmed |
| `backend/README.md` updated | "Using GitHub Copilot Skill" section + streaming endpoints in table |
