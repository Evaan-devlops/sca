# Example Success Response

When all three APIs complete successfully, Copilot responds:

---

OneTrust automation completed.

Website: https://www.hiomtest.com

Matched website:
www.hiomtest.com

Scan status:
Completed

data-domain-script:
019eb61a-8e3d-7bfe-a3fd-731b31d7bb95

Production script snippet:
```html
<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"
        data-document-language="true"
        type="text/javascript"
        charset="UTF-8"
        data-domain-script="019eb61a-8e3d-7bfe-a3fd-731b31d7bb95">
</script>
```

Completed steps:
- /auth/login — logged in
- /add_app — website configuration confirmed (11 steps)
- /filter_code — data_domain_script extracted (12 steps)

---

## Raw `/filter_code` response shape

```json
{
  "status": "data_domain_script extracted",
  "message": "Production script data-domain-script was extracted successfully.",
  "input_url": "https://www.hiomtest.com",
  "normalized_domain": "hiomtest.com",
  "matched_display_url": "www.hiomtest.com",
  "scan_status": "Completed",
  "data_domain_script": "019eb61a-8e3d-7bfe-a3fd-731b31d7bb95",
  "script_snippet": "<script src=\"https://cdn.cookielaw.org/...\" data-domain-script=\"019eb61a-...\">",
  "current_url": "https://uat-de.onetrust.com/cookies/scan-results/...",
  "screenshot": null,
  "steps": [
    {"step": "confirm_login", "status": "completed"},
    {"step": "open_websites_page", "status": "completed"},
    {"step": "wait_websites_table_loaded", "status": "completed"},
    {"step": "filter_website", "status": "completed"},
    {"step": "find_website_row", "status": "completed"},
    {"step": "verify_scan_completed", "status": "completed"},
    {"step": "open_website_details", "status": "completed"},
    {"step": "wait_website_details_page", "status": "completed"},
    {"step": "open_actions_menu", "status": "completed"},
    {"step": "click_copy_production_scripts", "status": "completed"},
    {"step": "wait_production_scripts_modal", "status": "completed"},
    {"step": "extract_data_domain_script", "status": "completed"}
  ],
  "debug": {
    "step": "extract_data_domain_script",
    "possible_reason": null,
    "next_action": "Ready for next automation phase",
    "visible_markers": ["Production scripts", "data-domain-script", "Copy scripts"]
  }
}
```
