Copilot command mappings

This repository supports a simple Copilot CLI mapping for processing Intercom tickets.

Command:
- `process ticket <ticket-number>`

Behavior:
- The Copilot CLI should call the backend endpoint `POST /intercom/process_ticket/stream` with JSON body `{"ticket": "<ticket-number>"}`.
- The endpoint streams NDJSON events describing the steps: open Intercom, click SSO, search ticket, open conversation, extract URL, start OneTrust add_app_flow.

Example:
```bash
curl -X POST http://localhost:8000/intercom/process_ticket/stream \
  -H "Content-Type: application/json" \
  -d '{"ticket":"112670879"}'
```

Notes for Copilot:
- Use the streaming endpoint to show progress to the user.
- If the flow requires manual SSO approval, surface a message to the user explaining that manual approval is required and how to continue.
