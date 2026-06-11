# Example Failure Responses

## /filter_code failure — data-domain-script not found

Copilot response:

---

OneTrust automation failed.

Failed API: /filter_code

Failed step:
extract_data_domain_script

Message: data-domain-script attribute not found in modal text

Current URL:
https://uat-de.onetrust.com/cookies/scan-results/abc123

Screenshot:
backend/screenshots/extract_data_domain_script_20260611_143022.png

Likely reason:
Production scripts modal opened but script text was not available/readable to Playwright

Next action:
Check screenshot — verify Production scripts modal is open and contains the script block

---

Raw debug block from response:
```json
{
  "status": "failed",
  "message": "data-domain-script attribute not found in modal text",
  "failed_step": "extract_data_domain_script",
  "debug": {
    "step": "extract_data_domain_script",
    "current_url": "https://uat-de.onetrust.com/cookies/scan-results/...",
    "page_title": "Cookie Consent | OneTrust",
    "visible_markers": ["Production scripts", "Use on your production website", "Copy scripts"],
    "modal_text_preview": "<script src=\"https://cdn.cookielaw.org/scripttemplates/otSDKStub.js\" type=\"text/javascript\" charset=\"UTF-8\" ",
    "possible_reason": "Production scripts modal opened but script text was not available/readable to Playwright",
    "next_action": "Check screenshot — verify Production scripts modal is open and contains the script block",
    "screenshot": "backend/screenshots/extract_data_domain_script_20260611_143022.png"
  }
}
```

---

## /add_app failure — step failed

Copilot response:

---

OneTrust automation failed.

Failed API: /add_app

Failed step:
select_experience_kit

Message: Experience kit 'US- Geolocation Category test' not found on page

Current URL:
https://uat-de.onetrust.com/cookies/new-user-wizard

Screenshot:
backend/screenshots/select_experience_kit_20260611_150301.png

Likely reason:
Kit name selector did not match any visible card. Kit may have been renamed or page is still loading.

Next action:
Check screenshot for visible kit names. If kit name changed, update ONETRUST_KIT_NAME in idea.md.

---

## /auth/login SSO issue

Copilot response:

---

OneTrust login requires SSO completion.

The browser window is open. Please:
1. Complete PingID / SSO authentication manually in the opened browser
2. Wait until you are redirected to the OneTrust dashboard
3. Come back and ask: "Retry OneTrust automation for https://www.hiomtest.com"

---

## /filter_code — website not found

```json
{
  "status": "website not found",
  "message": "Website row not found. Run /add_app first or wait for OneTrust table refresh.",
  "input_url": "https://www.hiomtest.com",
  "normalized_domain": "hiomtest.com"
}
```

Copilot response: "The website row was not found in the OneTrust Websites table. Either run `/add_app` first, or if it was just added, wait 30 seconds and retry `/filter_code`."
