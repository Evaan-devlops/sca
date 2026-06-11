---
name: onetrust-cookie-consent-automation
description: Use this skill when the user wants to automate the authorized OneTrust Cookie Consent sandbox workflow using the local FastAPI backend. This includes SSO login, adding a website, confirming the default experience kit, opening the created website, and extracting the OneTrust production data-domain-script from /auth/login, /add_app, and /filter_code.
---

## 1. Purpose

This skill orchestrates three existing local FastAPI tools to complete the OneTrust Cookie Consent automation workflow end-to-end. It does **not** implement browser automation itself — the Playwright logic lives entirely in the running backend.

The backend must already be running at `http://127.0.0.1:8000`.

## 2. When to use this skill

Use this skill when the user asks any of the following:

- "Add website to OneTrust"
- "Create OneTrust Cookie Consent website"
- "Get OneTrust data-domain-script"
- "Fetch production script from OneTrust"
- "Run OneTrust automation for a URL"
- "Process URL through login, add_app, filter_code"
- "Use OneTrust automation for `<url>`"
- "Extract data-domain-script for `<url>`"

## 3. When NOT to use this skill

Do not use this skill for:

- Unrelated web scraping or data extraction
- Bypassing SSO, MFA, PingID, GlobalProtect, or any corporate security control
- Editing or rewriting Playwright browser automation code (unless the user explicitly asks to fix an implementation bug)
- Extracting cookies, tokens, auth headers, or session secrets
- Any automated login that is not authorized OneTrust sandbox access

## 4. Required backend

The backend must be running locally at:

```
http://127.0.0.1:8000
```

Required endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Confirm backend is alive |
| POST | `/auth/login` | SSO login via persistent browser session |
| POST | `/add_app` | Add website + confirm experience kit (11 steps) |
| POST | `/filter_code` | Find website row, verify scan, extract data-domain-script (12 steps) |

Streaming variants (preferred if available):

| Method | Path |
|--------|------|
| POST | `/add_app/stream` |
| POST | `/filter_code/stream` |

If streaming endpoints are available, prefer them so step progress is visible in real time. Fall back to normal endpoints if streaming is not supported or fails.

## 5. Required input

The user must provide a complete URL including protocol, for example:

```
https://www.example.com
http://www.example.com
```

If the user provides only a domain (e.g. `example.com`) without a protocol, ask the user whether to use `https://example.com` before proceeding.

## 6. Main orchestration flow

### Step 1 — Check backend health

```
GET http://127.0.0.1:8000/health
```

If the backend is not running or returns an error, stop and tell the user:

> "The backend is not running. Start it first:
> ```
> cd /path/to/project/backend
> source ../.venv/bin/activate   # Mac/Linux
> # OR: ..\.venv\Scripts\Activate.ps1  (Windows)
> python -m uvicorn app.main:app --reload
> ```
> Then try again."

### Step 2 — Login

```
POST http://127.0.0.1:8000/auth/login
Body: {}
```

Handle response `status`:

| Status | Action |
|--------|--------|
| `"logged in"` | Continue to Step 3 |
| `"SSO issue"` | Stop. Tell user: "SSO did not complete. A browser window should be open — complete the PingID/SSO login manually, then call this again." |
| `"configuration error"` | Stop. Show `message` and `debug.next_action` from response. |
| `"error"` / any other | Stop. Show `failed_step`, `message`, `debug.next_action`, `screenshot` path. |

### Step 3 — Add website

```
POST http://127.0.0.1:8000/add_app
Body: {"url": "<user_url>"}
```

Or streaming:
```
POST http://127.0.0.1:8000/add_app/stream
Body: {"url": "<user_url>"}
```

Expected success: `status = "website configuration confirmed"`

If failed: do **not** proceed to Step 4. Return `failed_step`, `steps`, `current_url`, `screenshot`, `debug.next_action` to the user.

### Step 4 — Extract data-domain-script

```
POST http://127.0.0.1:8000/filter_code
Body: {"url": "<same_user_url>"}
```

Or streaming:
```
POST http://127.0.0.1:8000/filter_code/stream
Body: {"url": "<same_user_url>"}
```

Expected success: `status = "data_domain_script extracted"`

Return: `data_domain_script`, `matched_display_url`, `scan_status`, `script_snippet`, and steps summary.

If failed: return `failed_step`, `message`, `current_url`, `screenshot`, `debug.possible_reason`, `debug.next_action`.

## 7. Success response format

When all four steps complete successfully, respond with:

```
OneTrust automation completed.

Website: <input_url>

Matched website:
<matched_display_url>

Scan status:
<scan_status>

data-domain-script:
<data_domain_script>

Production script snippet:
<script_snippet>

Completed steps:
- /auth/login — completed
- /add_app — website configuration confirmed
- /filter_code — data_domain_script extracted
```

## 8. Failure response format

When any step fails, respond with:

```
OneTrust automation failed.

Failed API: <api_name>

Failed step:
<failed_step>

Message: <message>

Current URL:
<current_url>

Screenshot:
<screenshot_path>

Likely reason:
<debug.possible_reason>

Next action:
<debug.next_action>
```

Then ask the user: "Do you want to share the screenshot or the full JSON response for further diagnosis?"

## 9. Security rules

- **Never** bypass SSO, MFA, PingID, GlobalProtect, CAPTCHA, or any corporate security control
- **Never** store, log, or display passwords, cookies, session tokens, or auth headers
- **Never** scrape full page HTML or include it in responses
- **Never** use screenshot/OCR/image-based automation or pixel coordinates
- Only use authorized OneTrust sandbox access — this backend is not for production OneTrust environments
- Sensitive fields (`screenshot`) contain only a local file path — never the file contents

## 10. Implementation rule

When using this skill, Copilot must:

- Call the existing backend APIs — do **not** rewrite or reproduce Playwright automation logic
- Use the three tools in order: `/auth/login` → `/add_app` → `/filter_code`
- Only modify backend Python code if the user explicitly asks to fix an implementation bug
- Treat the backend as a black box; the skill's job is orchestration and response presentation only
