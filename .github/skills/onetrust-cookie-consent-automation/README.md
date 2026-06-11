# OneTrust Cookie Consent Automation Skill

This GitHub Copilot Chat skill orchestrates the local FastAPI + Playwright backend to automate the OneTrust Cookie Consent sandbox workflow end-to-end.

## What it does

Given a URL, Copilot will call three backend APIs in sequence:

1. `POST /auth/login` — open the OneTrust browser session and complete SSO
2. `POST /add_app` — add the website and confirm the default experience kit (11 steps)
3. `POST /filter_code` — find the website row, verify scan completion, and extract the `data-domain-script`

You do **not** need to run any CLI commands or scripts manually. Copilot handles the orchestration.

## Prerequisites

1. **Backend running:**

   Mac/Linux:
   ```bash
   cd /path/to/project/backend
   source ../.venv/bin/activate
   python -m uvicorn app.main:app --reload
   ```

   Windows:
   ```powershell
   cd C:\path\to\project\backend
   ..\.venv\Scripts\Activate.ps1
   python -m uvicorn app.main:app --reload
   ```

2. **`backend/.env` configured** — `ONETRUST_EMAIL` must be set.

3. **Headed browser mode** — `PLAYWRIGHT_HEADLESS=false` (default). Required for SSO passthrough.

4. **SSO ready** — if PingID/SSO prompts appear in the opened browser, complete them manually before asking Copilot to continue.

## Usage from GitHub Copilot Chat

Open Copilot Chat in VS Code and type any of these:

**Example 1:**
```
Use OneTrust automation for https://www.hiomtest.com and return the data-domain-script.
```

**Example 2:**
```
Add https://www.example.com to OneTrust and get the production script code.
```

**Example 3:**
```
Read idea.md and run the OneTrust automation for the URL mentioned there.
```

Copilot will automatically select the `onetrust-cookie-consent-automation` skill and call the three APIs in the correct order.

## Expected output

On success, Copilot returns:

- `data-domain-script` value (e.g. `019eb61a-8e3d-7bfe-a3fd-731b31d7bb95`)
- Matched website URL as it appears in OneTrust
- Scan status (should be `Completed`)
- Full `<script>` snippet ready to paste into your site
- Summary of completed steps

## Troubleshooting

| Problem | What to do |
|---------|-----------|
| Backend not running | Start `uvicorn` (see Prerequisites above) |
| SSO issue | A browser window is open — complete PingID/SSO manually, then ask Copilot to retry `/auth/login` |
| `add_app` failed | Check `failed_step` and `debug.next_action` in the response; check `screenshots/` folder |
| `filter_code` failed | Website row may not have appeared yet — wait a moment and retry `/filter_code` |
| Scan status pending | The OneTrust scan is still running — retry `/filter_code` after a few minutes |
| `data-domain-script` not found | Check the `modal_text_preview` in the debug response and share with the team |

## Skill location

```
.github/skills/onetrust-cookie-consent-automation/SKILL.md
```
