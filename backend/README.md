# OneTrust Automation Backend

FastAPI + Playwright backend that automates authorized OneTrust sandbox workflows.

## Setup (Windows)

```powershell
cd C:\Users\91997\scrapper\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
code .env
python -m uvicorn app.main:app --reload
```

## Setup (Mac)

```bash
cd /Users/sinhas43/scrapper
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
cd backend
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
code .env
python -m uvicorn app.main:app --reload
```

In VS Code, select this interpreter:

```text
/Users/sinhas43/scrapper/.venv/bin/python
```

Edit `backend/.env` and fill in your values:

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
Runs the full 7-step Add Website wizard and returns step-by-step results.

**3. Check mapper**
```
GET http://localhost:8000/mapper/default
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Browser ready status |
| POST | `/auth/login` | Login to OneTrust via SSO |
| POST | `/add_app` | Run Add Website wizard |
| GET | `/mapper/default` | Default experience kit |
| POST | `/mapper/resolve` | Resolve URL to experience kit |

## Notes

- Browser runs in **headed mode** by default — required for SSO passthrough
- Persistent profile stored in `PLAYWRIGHT_USER_DATA_DIR` — delete to force fresh login
- Screenshots saved to `screenshots/` on step failure (for debugging only)
- SSO/MFA/PingID are never bypassed — complete manually in the opened browser if prompted
