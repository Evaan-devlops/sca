# GitHub Copilot Instructions — OneTrust Automation

## OneTrust Cookie Consent automation

When the user asks any of the following, use the skill at `.github/skills/onetrust-cookie-consent-automation/SKILL.md`:

- Add a website to OneTrust
- Run OneTrust Cookie Consent automation
- Extract data-domain-script from OneTrust
- Get production script for a URL
- Process a URL through login, add_app, filter_code

**Do not rewrite Playwright browser automation code** unless the user explicitly asks to fix an implementation bug.

Use the existing local backend APIs in this order:

1. `GET http://127.0.0.1:8000/health`
2. `POST http://127.0.0.1:8000/auth/login`
3. `POST http://127.0.0.1:8000/add_app`
4. `POST http://127.0.0.1:8000/filter_code`

Streaming variants (`/add_app/stream`, `/filter_code/stream`) are preferred when available.

Full orchestration instructions, response formats, and security rules are in:

```
.github/skills/onetrust-cookie-consent-automation/SKILL.md
```
