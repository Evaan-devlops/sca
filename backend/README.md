# OneTrust Automation Backend

FastAPI + Playwright backend that automates authorized OneTrust sandbox workflows.

## Setup (Mac)

```bash
cd <project-root>          # e.g. ~/scrapper or wherever you cloned the repo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
cd backend
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
code .env                  # fill in ONETRUST_EMAIL
python check_setup.py
python -m uvicorn app.main:app --reload
```

### VS Code Interpreter (Mac)

Cmd + Shift + P → Python: Select Interpreter → select the `.venv` interpreter inside your project root:

```text
<project-root>/.venv/bin/python
```

## Setup (Windows)

```powershell
cd C:\Users\91997\scrapper
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
cd backend
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
code .env
python check_setup.py
python -m uvicorn app.main:app --reload
```

### VS Code Interpreter (Windows)

Ctrl + Shift + P -> Python: Select Interpreter ->

```text
<repo>\.venv\Scripts\python.exe
```

## Environment

After copying `.env.example`, edit `backend/.env` and fill in your values:

```env
ONETRUST_BASE_URL=https://uat-de.onetrust.com
ONETRUST_LOGIN_URL=https://uat-de.onetrust.com/auth/login
ONETRUST_EMAIL=your.email@pfizer.com
PLAYWRIGHT_HEADLESS=false
PLAYWRIGHT_USER_DATA_DIR=.playwright/onetrust-profile
PLAYWRIGHT_TIMEOUT_MS=90000
ONETRUST_SCAN_TIMEOUT_MS=300000
```

## Run

```bash
cd backend
python -m uvicorn app.main:app --reload
```

API available at `http://localhost:8000`

## Usage

**1. Login (required first)**
```
POST http://localhost:8000/auth/login
{}
```
A browser window opens. Complete SSO/PingID if prompted. Returns `"status": "logged in"` on success.

**2. Add website**
```
POST http://localhost:8000/add_app
{"url": "https://www.pfizerguidesources.com"}
```
Runs the full 13-step Add Website wizard through to scan status Completed.

**3. Check mapper**
```
GET http://localhost:8000/mapper/default
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Browser ready status |
| POST | `/auth/login` | Login to OneTrust via SSO |
| POST | `/add_app` | Run Add Website wizard (11 steps) |
| POST | `/add_app/stream` | Same as above, NDJSON step stream |
| POST | `/filter_code` | Find website, verify scan, extract data-domain-script |
| POST | `/filter_code/stream` | Same as above, NDJSON step stream |
| GET | `/mapper/default` | Default experience kit |
| POST | `/mapper/resolve` | Resolve URL to experience kit |

## Using GitHub Copilot Skill

The preferred way to consume this backend is via the included GitHub Copilot Chat skill — no CLI scripts needed.

**1. Start the backend:**

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

**2. Open GitHub Copilot Chat in VS Code.**

**3. Ask Copilot:**
```
Use OneTrust automation for https://www.example.com and give me the data-domain-script.
```

**4. Copilot uses the skill** at `.github/skills/onetrust-cookie-consent-automation/SKILL.md` and calls:
- `POST /auth/login`
- `POST /add_app`
- `POST /filter_code`

**5. If SSO appears** — complete PingID/SSO manually in the opened browser, then ask Copilot to continue or retry `/auth/login`.

See `.github/skills/onetrust-cookie-consent-automation/README.md` for full usage and troubleshooting.

## Notes

- Browser runs in **headed mode** by default — required for SSO passthrough
- Persistent profile stored in `PLAYWRIGHT_USER_DATA_DIR` — delete to force fresh login
- Screenshots saved to `screenshots/` on step failure (for debugging only)
- SSO/MFA/PingID are never bypassed — complete manually in the opened browser if prompted
