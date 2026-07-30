# Agent Development Notes

This repo contains Nora, the doctor-facing clinic assistant for Dr. Shalini.
Read this file first in a fresh Codex session, then read the fuller docs in
`docs/`.

## Current Project Context

- Repository: `https://github.com/suhanisho/nora`
- Legacy source: `https://github.com/suhanisho/infiapp/tree/build-clinic-mvp`
- Upstream: `https://github.com/infiloop2/infiapp`
- Default branch: `main`
- Production app: `https://shalini-clinic-webui.vercel.app`
- Manual deploy workflow: `.github/workflows/deploy.yml`
- Main product docs:
  - `docs/session-handoff.md`
  - `docs/high-level-design.md`
  - `docs/google-workspace-integrations.md`
  - `../clinic_assistant_product_spec.md`

## Product Rules

The most important product rule is explicit approval before external action.

- No email is sent without explicit doctor approval.
- No Gmail draft is created without explicit doctor approval.
- No Google Calendar event is created, updated, deleted, held, or blocked
  without explicit doctor approval.
- The legacy `approve_action` backend path is audit-only and does not call Gmail
  or Calendar, but it is no longer exposed as a Review-card button.
- `Approve & send` is the send-only path. It sends the edited reply
  through Gmail after an explicit confirmation, then records the Gmail sent
  message id for audit. If the reply proposes availability windows, the linked
  request should wait in `awaiting_patient_slot_selection`.
- `Approve, send & book` is the explicit Calendar booking path. It verifies an
  exact patient-selected slot against Google Calendar, creates the event, sends
  the edited Gmail confirmation, and records both external IDs for audit.
- Google Calendar remains the source of truth for appointments. Calendar writes
  must only happen through explicit approval actions.
- Gmail is the source of patient communication. Gmail scans may read messages,
  create patient requests, and prepare in-app draft replies, but they must not
  send, label, archive, or delete messages.

## Current Architecture

- Auth uses Auth.js/NextAuth v4 with JWT sessions.
- Google sign-in and Google Workspace connection use the same Google OAuth app.
- Google token material is stored in AWS Secrets Manager, not DynamoDB or
  Auth.js tables.
- The Next.js server passes the signed-in email as `actorEmail` with a
  short-lived HMAC assertion. The Lambda verifies this before deriving
  `practice_id`; the browser must not choose the tenant boundary.
- `practice_id` is unique per login user for now.
- App login users are practice members, not patients.
- Patients are identified by `patient_id`.
- Current patient identity resolution is email-based:
  - parse sender email from Gmail
  - trim and lowercase it
  - match against existing `clinic_patients.email`
  - if no match, create deterministic `patient_email_<hash>` from that email
- The current identity layer does not merge Gmail aliases, multiple email
  addresses, phone numbers, names, DOBs, or family-member senders.
- `patient_request_id` is the durable workflow entity for an inbound patient
  request.
- `clinic_actions` stores child actions linked to `patient_request_id`, so one
  patient request can later support multiple actions.
- Gmail messages are events inside a request. Use Gmail `threadId` and
  `clinic_email_messages` to avoid duplicate requests and to attach patient
  replies to the existing `patient_request_id`.
- `clinic_email_messages` records processed inbound/outbound Gmail messages for
  idempotency, duplicate detection, thread continuity, and audit.
- Gmail patient relevance, request classification, and natural draft wording can
  be LLM-assisted when `OPENAI_API_KEY` is present. The deterministic rules are
  still the fallback, and all external actions remain approval-gated.

## Google Integration Rules

Current OAuth scopes:

- `openid`
- `email`
- `https://www.googleapis.com/auth/calendar.events.readonly`
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.compose`

Important: existing users may need to click `Reconnect Google` after scope
changes. If Gmail send or Calendar booking fails because a Google permission is
missing, ask the user to reconnect Google.

Gmail sending must:

- only happen through `approve_and_send_gmail` or
  `approve_send_and_book_calendar`
- only work for Gmail-sourced actions
- send the edited final message, not an unreviewed draft
- reply in the source Gmail thread when source thread/message ids are present
- record `external_sent_message_id`
- mark the linked patient request completed when relevant, but leave slot
  proposals waiting for patient selection

Calendar writes must:

- only happen through `approve_send_and_book_calendar` for now
- verify the exact slot against live Google Calendar immediately before booking
- create events with `sendUpdates=none`; patient communication stays in Gmail
- record the external Calendar event id for audit
- stay covered by tests whenever a new Calendar mutation path is added

## LLM Rules

- The current LLM boundary is limited to Gmail relevance, classification, and
  draft wording.
- The LLM must not invent appointment times. Calendar windows come from backend
  slot generation only.
- The LLM must not imply an email was sent or a Calendar event was created
  before explicit doctor approval.
- Keep deterministic code responsible for Gmail/thread de-duplication,
  `patient_id` creation, date/time parsing, slot generation, booking-candidate
  extraction, Gmail send, and Calendar writes.
- Runtime env:
  - `OPENAI_API_KEY` enables the path.
  - `CLINIC_LLM_ENABLED=false` disables it.
  - `CLINIC_LLM_MODEL` overrides the default model.

## Frontend Direction

- The first tab is `Rounds`, the daily cockpit.
- The app uses a warm light theme for readability:
  - cream background
  - white attention surfaces
  - dark teal accents
  - larger, medium-weight text
- Do not reintroduce dark theme as the default.
- Keep the UI doctor-facing and operational, not a marketing page.
- The doctor should be able to review, edit, approve, and understand why an
  action exists.
- Gmail actions should expose `Approve & send` or `Approve, send & book`; do not
  reintroduce an `Approve and store` button in the Review UI.

## Repo Conventions

- Read `README.md` and the README files inside `agents/`, `webUI/`,
  `repo_tools/`, and `dynamodb/` when working in those areas.
- Never push directly to `main`.
- Create a focused branch and pull request for changes to `main`.
- Be careful with generated files. Edit specs first, then run codegen.
- Do not edit generated files by hand unless fixing the generator itself.
- Python dependencies are pinned in root `pyproject.toml`. Agent specs list
  package names in `required_dependencies`; validation fails if a listed package
  is not pinned.

## Common Commands

Use `.venv/bin/python` when the repo venv is available. In this workspace,
`python3.11` has also been used successfully.

Run after changing agent specs or DynamoDB specs:

```sh
python3.11 -m repo_tools codegen
```

Useful validation commands:

```sh
python3.11 -m repo_tools validate-agents
python3.11 -m repo_tools validate-db
python3.11 -m repo_tools codegen-check
python3.11 -m repo_tools test-agents
python3.11 -m repo_tools typecheck-agents
npm --prefix webUI run build
```

For visible frontend workflows, try:

```sh
npm --prefix webUI run test:e2e
```

Local Playwright can be blocked by the macOS sandbox in this environment. If it
cannot launch Chromium, say so clearly and rely on build/type/backend checks.

`npm --prefix webUI run build` may change `webUI/next-env.d.ts` between
`.next/types/routes.d.ts` and `.next/dev/types/routes.d.ts`. If that is the
only change from the build, restore it before committing.

## Deploy Flow

Deploys are manual GitHub Actions runs against `main`.
Before the first deploy from the renamed repository, recreate the GitHub
Actions secrets and variables listed in `docs/session-handoff.md`. GitHub does
not copy them when code moves to a new repository.

```sh
git push origin <feature-branch>
gh workflow run deploy.yml --repo suhanisho/nora --ref main
gh run list --repo suhanisho/nora --workflow deploy.yml --branch main --limit 3
```

Watch the run to completion and then health-check production:

```sh
gh run watch <run-id> --repo suhanisho/nora --exit-status
curl -I -L https://shalini-clinic-webui.vercel.app/
```

## Change Conventions

- Agents: update `agents/<agent>/spec.json`, `code/handler.py`, tests under
  `test/`, and owned DynamoDB specs when needed.
- DynamoDB: keep partition and sort key names and types stable unless a real
  migration plan exists.
- WebUI: update `webUI/app/clinic-app.tsx`, route handlers under
  `webUI/app/api/clinic/`, and mock behavior under `webUI/src/lib/mocks/`.
- Generated bindings live under `webUI/src/lib/generated/` and
  `agents/shared_utils/generated/`.
- Docs should stay current when the safety model, data model, OAuth scopes, or
  deploy state changes.
