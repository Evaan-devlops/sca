# Tests Progress — OneTrust Automation Backend

> **Tests sub-agent memory.**
> Tests are skipped in v1 per user decision (2026-06-08).
> This file is initialized per SPL structure for future use.

---

## Tests Current State

**Last updated:** 2026-06-08

```
TESTS-APP: onetrust-automation — tests layer
TESTS-STACK: pytest (backend) | DB: None

COVERAGE SNAPSHOT:
  (no tests yet — v1 skips tests per user decision)

TESTS DONE:
  (none)

ACTIVE: skipped — will be added in a future version
NEXT: add tests when user requests

TEST RULES:
  Unit tests    → mock only Playwright browser at the boundary
  Coverage      → 80% target on all new code when tests are added
  Per test case → one behavior, clear name, arrange/act/assert
```

---

## Resume Point

**Active task:** none — tests skipped in v1
**Blockers:** none

---

## Test File Map

```
tests/
  (empty — tests not yet added)
```

---

## Untested Areas

- [ ] `backend/app/features/browser/service.py` — BrowserManager lifecycle
- [ ] `backend/app/features/auth/service.py` — login_onetrust, SSO wait, modal handling
- [ ] `backend/app/features/websites/service.py` — click_add_website, ensure_websites_page

---

## Tests Dev Log

<!-- Add entries here after testing milestones. -->
