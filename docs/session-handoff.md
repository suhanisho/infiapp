# Dr. Shalini Clinic App Handoff

Last updated: 2026-05-07

This document captures the key design decisions and session context needed to
continue work on the Dr. Shalini clinic app.

For a fuller system overview, see `docs/high-level-design.md`.

## Product goal

Build a doctor-facing assistant for Dr. Shalini's clinic. Google Calendar is the
source of truth for appointments. Gmail is the source of patient communication.
The app reads both, prepares patient requests and draft replies, and keeps the
doctor in control of any completed action.

## Current branch and deployment

- Fork: `https://github.com/suhanisho/infiapp`
- Upstream: `https://github.com/infiloop2/infiapp`
- Working branch: `build-clinic-mvp`
- Production app: `https://shalini-clinic-webui.vercel.app`
- Vercel project: `shalini-clinic-webui`
- Deploy workflow: `.github/workflows/deploy.yml`
- Deploys are manual `workflow_dispatch` runs against `build-clinic-mvp`.

## Safety contract

This is the most important product rule:

- No email is sent without explicit user approval.
- No Gmail draft is created without explicit user approval.
- No calendar event is created, updated, deleted, or blocked without explicit
  user approval.
- Current MVP approvals only store completion/audit state in the backend. They
  do not perform external side effects.
- Completed actions are stored in `clinic_actions` for future validation/audit.
- The durable product entity is now `patient_request_id` under a per-login
  `practice_id`; `clinic_actions` stores child workflow/audit actions that link
  back to a patient request. This allows one request to have multiple future
  actions such as reply review, Gmail draft creation, sending, booking, or
  document follow-up.
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
  - `https://www.googleapis.com/auth/gmail.readonly`
- Future send/draft scope would be `https://www.googleapis.com/auth/gmail.compose`,
  but do not add it until send/draft actions are separately approval-gated.

## Backend shape

Main Lambda:

- `agents/clinic_agent/code/handler.py`

Shared Google client:

- `agents/shared_utils/google_workspace.py`

DynamoDB specs:

- `dynamodb/clinic_agent/clinic_actions.json`
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
- It does not write to Google Calendar.

Gmail:

- User manually clicks `Scan Gmail`.
- `scan_gmail_inbox` refreshes OAuth using the stored refresh token.
- It reads recent Gmail message metadata/snippets matching clinic-oriented query
  terms.
- It filters out obvious non-patient messages, including newsletters, no-reply
  senders, promos, password resets, and marketing-style emails.
- It stores the main request in `clinic_patient_requests` using
  `practice_id + patient_request_id`.
- It adds intelligent triage fields to each patient request: request type,
  urgency, risk level, doctor-review requirement, suggested next action,
  patient emotional tone, confidence, and reason.
- Urgent clinical concern language is routed to doctor review and gets an
  escalation-style in-app draft instead of calendar availability windows.
- It upserts linked in-app action records in `clinic_actions` so the current
  Daily Cockpit and approval/audit flow continue to work. Scans do not delete
  durable open patient requests that fall out of the current Gmail result set.
- It does not send email, label/archive messages, or create Gmail drafts.

Approval:

- User expands a request/action card, edits the draft text, then clicks
  `Approve and store`.
- `approve_action` marks the action completed and stores final text/audit
  metadata. If the action links to a `patient_request_id`, the patient request
  is marked completed with the same final text and approval metadata.
- It does not send the final text anywhere.

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
- Google Calendar supports appointment schedule booking pages, so a future mode
  could share a booking link instead of proposing windows. Keep this optional
  until we are comfortable with quality and patient experience.

## Frontend shape

Main app:

- `webUI/app/clinic-app.tsx`
- `webUI/app/styles.css`

Important UI decisions:

- The app is mobile-first and doctor-facing, not a marketing page.
- Settings drawer has Google controls:
  - `Reconnect Google`
  - `Read Calendar`
  - `Scan Gmail`
- Request cards expand to show source email and editable draft reply.
- The first tab is the Daily Cockpit. It shows:
  - summary overview of the day
  - open actions that need attention, prioritised by triage
- Draft reply text is editable before `Approve and store`.
- The bottom nav has:
  - `Cockpit`
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

- `39261d2` - Read Google Calendar and Gmail into clinic app
- `7fe0a1a` - Suggest calendar slots in Gmail drafts
- `1c8b06c` - Respect patient preferences in slot suggestions
- `082e4af` - Offer availability windows and filter inbox noise
- Current working changes after that add `practice_id` scoping,
  `clinic_patient_requests` as the main request entity, child action IDs,
  signed actor assertions, and practice member records.

## Suggested next steps

1. Improve email triage with a real LLM/classifier step so the app can better
   distinguish patient messages from unrelated inbox noise.
2. Add patient matching/review for unknown senders before completing durable
   patient-linked requests.
3. Add a preview/audit panel showing why an email was included or ignored.
4. Consider a configurable Google Calendar appointment schedule booking link.
5. Later, add explicit approval-gated actions for:
   - creating a Gmail draft
   - sending a Gmail draft
   - holding or booking a calendar slot
