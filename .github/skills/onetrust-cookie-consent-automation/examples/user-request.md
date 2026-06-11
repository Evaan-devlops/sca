# Example User Requests

## Copilot Chat prompts

These prompts will trigger the `onetrust-cookie-consent-automation` skill automatically.

**Direct URL request:**
```
Use OneTrust automation for https://www.hiomtest.com and give me the production data-domain-script.
```

**Casual phrasing:**
```
Add https://www.example.com to OneTrust and get the script code.
```

**Batch-style:**
```
Add https://www.pfizerguidesources.com to OneTrust Cookie Consent sandbox and extract data-domain-script.
```

**From idea.md:**
```
Read idea.md and run the OneTrust automation for the URL mentioned there.
```

---

## idea.md request format

You can also write requests directly in `idea.md` and say `process idea.md`:

```
OneTrust task:
URL: https://www.hiomtest.com
Goal: Add website in OneTrust sandbox and extract production data-domain-script.
```

Or more concisely:

```
Run OneTrust automation for https://www.hiomtest.com — return data-domain-script.
```

---

## What Copilot will do

1. Check `GET /health` — confirm backend is alive
2. Call `POST /auth/login` — open browser session, complete SSO
3. Call `POST /add_app {"url": "..."}` — run 11-step Add Website wizard
4. Call `POST /filter_code {"url": "..."}` — find row, verify scan, extract `data-domain-script`
5. Return the result in chat
