# Dr. Shalini Clinic App Handoff

Last updated: 2026-05-09

This document captures the key design decisions and session context needed to
continue work on the Dr. Shalini clinic app.

For a fuller system overview, see `docs/high-level-design.md`.

## Product goal

Build a doctor-facing assistant for Dr. Shalini's clinic. Google Calendar is the
source of truth for appointments. Gmail is the source of patient communication.
The app reads both, prepares patient requests, triage, and draft replies, and
keeps the doctor in control of any completed action.
Gmail messages are now treated as events inside an ongoing patient request, so a
patient reply in the same thread should update the existing request rather than
starting a duplicate one.

## Current branch and deployment

- Fork: `https://github.com/suhanisho/infiapp`
- Upstream: `https://github.com/infiloop2/infiapp`
- Working branch: `build-clinic-mvp`
- Production app: `https://shalini-clinic-webui.vercel.app`
- Vercel project: `shalini-clinic-webui`
- Deploy workflow: `.github/workflows/deploy.yml`
- Deploys are manual `workflow_dispatch` runs against `build-clinic-mvp`.
- Latest production code commit before this change set: `9fb45f5` - Add
  approval-gated Gmail sending.
- Latest successful deploy run:
  `https://github.com/suhanisho/infiapp/actions/runs/25564898598`

## Safety contract

This is the most important product rule:

- No email is sent without explicit user approval.
- No Gmail draft is created without explicit user approval.
- No calendar event is created, updated, deleted, or blocked without explicit
  user approval.
- `Approve and store` only stores completion/audit state. `Approve & send
  Gmail` is the explicit send path and records the Gmail sent message id.
- `Approve, send & book` is the explicit Calendar booking path. It only appears
  when the patient request contains an exact date/time, verifies the slot
  against Google Calendar, creates the event, sends the edited Gmail
  confirmation, and records the Calendar event id plus Gmail sent id.
- Completed actions are stored in `clinic_actions` for future validation/audit.
- The durable product entity is now `patient_request_id` under a per-login
  `practice_id`; `clinic_actions` stores child workflow/audit actions that link
  back to a patient request. This allows one request to have multiple future
  actions such as reply review, Gmail draft creation, sending, booking, or
  document follow-up.
- Processed Gmail messages are stored in `clinic_email_messages` for
  idempotency, duplicate detection, thread continuity, and future audit.
- Patients are identified by `patient_id`. People who log into the app are
  practice members; patients remain separate patient records.
- Google OAuth refresh/access token material is stored in AWS Secrets Manager,
  not in DynamoDB or Auth.js tables.

## Auth and integrations

- Auth uses Auth.js/NextAuth v4.
- Google sign-in and Google Workspace connection use the same Google OAuth app,
  but the OAuth app is not "per user"; any allowed account signs in through the
  same client ID/secret.
- Allowed sign-in emails are controlled by `CLINIC_ALLOWED_EMAILS`, unless
  `CLINIC_ALLOW_SELF_ONBOARDING=true` is set for controlled self-onboarding.
- The Next.js server passes the signed-in email to the Lambda as `actorEmail`
  with a short-lived HMAC signature. The Lambda verifies that assertion before
  deriving a deterministic `practice_id` from the email. The browser does not
  choose the practice boundary.
- Practice members are recorded in `clinic_practice_members` when Google is
  connected.
- Auth.js uses JWT sessions. There is no Auth.js database adapter because we do
  not want Google token material stored in normal auth tables.
- The Auth.js sign-in callback calls `connect_google_workspace`, which stores
  token material in Secrets Manager and safe metadata in `clinic_integrations`.
- Current scopes:
  - `openid`
  - `email`
  - `https://www.googleapis.com/auth/calendar.events.readonly`
  - `https://www.googleapis.com/auth/calendar.events`
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/gmail.compose`
- Existing users may need to click `Reconnect Google` after compose or Calendar
  write scopes are added; otherwise approve-and-send or approve-send-and-book
  will ask them to reconnect before sending or booking.

## Backend shape

Main Lambda:

- `agents/clinic_agent/code/handler.py`

Shared Google client:

- `agents/shared_utils/google_workspace.py`

DynamoDB specs:

- `dynamodb/clinic_agent/clinic_actions.json`
- `dynamodb/clinic_agent/clinic_email_messages.json`
- `dynamodb/clinic_agent/clinic_patient_requests.json`
- `dynamodb/clinic_agent/clinic_practice_members.json`
- `dynamodb/clinic_agent/clinic_schedule.json`
- `dynamodb/clinic_agent/clinic_integrations.json`
- `dynamodb/clinic_agent/clinic_patients.json`
- `dynamodb/clinic_agent/clinic_settings.json`

Generated bindings:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

Run `python3.11 -m repo_tools codegen` after editing agent specs or DynamoDB
specs.

## Current data flows

Google Calendar:

- User manually clicks `Read Calendar`.
- `sync_google_calendar` refreshes OAuth using the stored refresh token.
- It reads Google Calendar events for the next 14 days.
- It maps events into `clinic_schedule`.
- It returns a rolling 14-day read-only schedule, including empty days, so the
  Schedule tab can show a complete week and the following week.
- It does not write to Google Calendar during sync.
- Calendar writes exist only through `approve_send_and_book_calendar`, which is
  triggered by the doctor clicking `Approve, send & book` on a specific action.

Gmail:

- User manually clicks `Scan Gmail`.
- `scan_gmail_inbox` refreshes OAuth using the stored refresh token.
- It lists recent inbox messages, then fetches full read-only message content
  for candidate messages so triage and drafts can use the patient's original
  wording instead of snippets alone.
- It checks `clinic_email_messages` before drafting. Already-seen Gmail message
  ids, repeated RFC message ids, and repeated normalized patient message
  signatures are skipped or recorded as duplicates.
- It resolves Gmail `threadId` against existing patient requests before
  drafting. Replies in an existing thread reuse the existing
  `patient_request_id`.
- It filters out obvious non-patient messages, including newsletters, no-reply
  senders, promos, password resets, and marketing-style emails.
- It stores the main request in `clinic_patient_requests` using
  `practice_id + patient_request_id`.
- It adds intelligent triage fields to each patient request: request type,
  urgency, risk level, doctor-review requirement, suggested next action,
  patient emotional tone, confidence, and reason.
- It extracts and persists `request_constraints`, including patient-stated
  timing preferences and clinical context anchors such as scan/test/procedure
  dates and times.
- Urgent clinical concern language is routed to doctor review and gets an
  escalation-style in-app draft instead of calendar availability windows.
- It upserts linked in-app action records in `clinic_actions` so the current
  Rounds and approval/audit flow continue to work. Scans do not delete durable
  open patient requests that fall out of the current Gmail result set.
- If a patient reply in an existing thread contains an exact selected slot, the
  app creates a new `confirm_booking` child action on the same
  `patient_request_id`; this is what powers `Approve, send & book`.
- If the patient only writes a time such as `4.30pm works`, the scanner tries to
  resolve it against the request's previously proposed windows and only proceeds
  when there is one clear match.
- Historical source messages from already-known Gmail threads are recorded in
  `clinic_email_messages` but skipped for request updates, so they do not erase
  proposed windows before newer replies are processed.
- The app should only propose Calendar availability when the message clearly has
  scheduling intent. Result questions, prescription/admin requests, symptom
  questions, and general next-step questions should get contextual review drafts
  instead of generic meeting-slot replies.
- It does not send email, label/archive messages, or create Gmail drafts.

Approval:

- User expands a request/action card, edits the draft text, then clicks
  `Approve and store`.
- `approve_action` marks the action completed and stores final text/audit
  metadata. If the action links to a `patient_request_id`, the patient request
  is marked completed with the same final text and approval metadata.
- It does not send the final text anywhere.
- For Gmail-sourced actions, the doctor can instead click `Approve & send
  Gmail`. This calls `approve_and_send_gmail`, sends the edited message through
  Gmail, and records the Gmail sent message id on the action. If the sent reply
  contains proposed availability windows, the linked request moves to
  `awaiting_patient_slot_selection` instead of `completed`.
- For Gmail-sourced scheduling replies with an exact patient-selected slot, the
  doctor can click `Approve, send & book`. This calls
  `approve_send_and_book_calendar`, verifies the slot against live Google
  Calendar, creates a Calendar event with no attendee/invite emails, sends the
  edited Gmail confirmation, and marks the linked patient request complete.

## Scheduling design decisions

- Calendar is treated as busy/free context, not as something the app mutates.
- The app should offer availability windows, not overly granular slot menus.
  Prefer wording like:
  - `Monday 11 May, between 9:00 AM and 12:00 PM`
  - `Tuesday 12 May, between 1:00 PM and 2:30 PM`
- The patient can choose an exact time inside a proposed window.
- Meet & Greet is currently treated as a 15-minute appointment.
- Initial Consultation is currently treated as 45 minutes.
- Follow-up is currently treated as 20 minutes.
- Slot suggestions respect:
  - Doctor availability rules from `clinic_settings`
  - Lunch break preference
  - Buffer between appointments
  - Existing busy calendar events
  - Patient-stated constraints from the email, such as weekdays, next week,
    morning/afternoon/evening/lunchtime, after/before, and between time ranges.
  - Context anchors such as a scan/test/procedure date and time. If a patient
    asks for a follow-up after a scan at 3:00 PM, the app treats the earliest
    appointment time as 90 minutes later on the same day rather than simply
    moving to the next day.
- Contextual scheduling constraints are stored on the patient request metadata
  so future request-linked workflows can reuse the same interpretation.
- Exact patient-selected booking slots are stored on request/action metadata as
  `booking_candidate_*` fields, including start/end time, label, availability
  flag, and any unavailable reason. The booking button is shown only when an
  exact slot is available.
- Google Calendar supports appointment schedule booking pages, so a future mode
  could share a booking link instead of proposing windows. Keep this optional
  until we are comfortable with quality and patient experience.

## Frontend shape

Main app:

- `webUI/app/clinic-app.tsx`
- `webUI/app/styles.css`

Important UI decisions:

- The app is mobile-first and doctor-facing, not a marketing page.
- The first tab is `Rounds`. It now follows the warm cream, high-readability
  visual theme from `weave_clinic_rounds_light_theme.html`, because dark mode
  was too tiring for the intended doctor audience.
- Key visual decisions: cream background (`#F7F3E8`), dark teal accents
  (`#0F6E56` / `#1D9E75`), larger default type, stronger text weights, solid
  status-pill fills, white briefing/action cards for contrast against the cream
  page, rounded phone canvas, 1px card borders, and a dark navy serif `S` block
  as the brand anchor.
- Quiet zero-review states are hidden in the Rounds briefing so doctors do not
  learn to ignore that metric area.
- `Rounds` is the daily cockpit: greeting, date, briefing, schedule overview,
  and open actions that need attention.
- New empty practices see a first-run setup screen for Google connection,
  Calendar read, and Gmail scan. It disappears once synced workspace data
  exists or the user opens the empty workspace.
- `Schedule` shows 7 days by default with previous/next week controls, while
  remaining read-only.
- Settings drawer has Google controls:
  - `Reconnect Google`
  - `Read Calendar`
  - `Scan Gmail`
- Request cards expand to show source email, triage, patient context, and an
  editable draft reply.
- The `Patients` tab shows linked request history. Gmail scan now creates a
  deterministic `patient_id` and a patient record for new clinic-relevant
  senders, then links requests/actions back to that patient.
- Draft reply text is editable before `Approve and store`.
- The bottom nav has:
  - `Rounds`
  - `Schedule`
  - `Patients`

## Production environment

GitHub Actions secrets currently expected:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `VERCEL_TOKEN`
- `VERCEL_TEAM_ID`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `NEXTAUTH_SECRET`
- Optional: `CLINIC_AGENT_INTERNAL_SECRET`; if omitted, the app uses
  `NEXTAUTH_SECRET` for the internal signed actor assertion.

GitHub Actions variables currently expected:

- `NEXTAUTH_URL=https://shalini-clinic-webui.vercel.app`
- `CLINIC_ALLOWED_EMAILS=...`
- Optional: `CLINIC_ALLOW_SELF_ONBOARDING=true`
- Optional: `CLINIC_DEMO_SEED_DATA=true` to show demo patients/actions for a
  practice. New real practice IDs do not receive demo patient data by default.
- Optional: `GOOGLE_TOKEN_SECRET_PREFIX` as a root prefix; the Lambda appends
  `practice_id/clinic_agent/google`. If omitted, the root prefix defaults to
  `shalini-clinic`.

The deploy script syncs relevant env vars to Vercel and Lambda.

## Validation commands

Run these before committing meaningful backend/frontend changes:

```sh
python3.11 -m repo_tools validate-agents
python3.11 -m repo_tools validate-db
python3.11 -m repo_tools codegen-check
python3.11 -m repo_tools test-agents
python3.11 -m repo_tools typecheck-agents
npm --prefix webUI run build
```

Known local quirk: `npm --prefix webUI run build` may rewrite
`webUI/next-env.d.ts` from `.next/dev/types/routes.d.ts` to
`.next/types/routes.d.ts`. We have been restoring that generated reference
before commits to avoid unrelated churn.

## Recent commits of interest

- `d7728b3` - Respect patient context in appointment drafts
- `e781051` - Redesign clinic rounds experience
- `edb32a8` - Add inbox triage and daily cockpit
- `6834ea9` - Fix Gmail scan production errors
- `8a7f55d` - Fix Google reconnect for practice workspaces
- `1dff88b` - Add patient request workflow model
- `0368378` - Document clinic app handoff decisions

## Suggested next steps

1. Add a preview/audit panel showing why an email was included or ignored and
   which patient constraints were extracted.
2. Add patient matching/review for unknown senders before completing durable
   patient-linked requests.
3. Improve email triage with a real LLM/classifier step while preserving
   deterministic safety guardrails.
4. Consider a configurable Google Calendar appointment schedule booking link.
5. Consider an XL type-size setting for doctors who prefer 18px body text.
6. Later, add explicit approval-gated actions for:
   - creating a Gmail draft
   - holding or booking a calendar slot
