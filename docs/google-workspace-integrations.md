# Google Workspace integration path

This app treats Google Calendar as the appointment source of truth and Gmail as
the patient communication source. The first implementation is deliberately
read-first and approval-gated.

## Safety rules

- Calendar writes are disabled until we explicitly add a user-approved write
  workflow.
- Gmail scans can create or refresh patient request records, linked in-app
  action records, and draft text, but they must not send email, label threads,
  archive messages, or create Gmail drafts automatically.
- Gmail sending is available only through the explicit `approve_and_send_gmail`
  action. Gmail draft creation remains a future explicit approval action.
- OAuth refresh tokens must not be stored in DynamoDB. Store token material in a
  secret store, and keep only metadata such as account email, scopes, sync
  tokens, and secret IDs in DynamoDB.

## Current repo shape

- `clinic_integrations` stores Google connection metadata, required scopes, and
  sync cursors.
- `clinic_schedule` stores a local cache of Google Calendar events, including
  external calendar/event IDs.
- `clinic_patient_requests` is the main durable entity for Gmail-derived
  patient requests. It is keyed by `practice_id + patient_request_id`.
- `clinic_actions` stores child approval/audit records linked by
  `patient_request_id`; action IDs are separate so one request can support
  multiple future actions.
- `clinic_practice_members` stores app login members for a practice. Patients
  remain separate and are identified by `patient_id`.
- The Next.js server passes the signed-in email as `actorEmail` with a
  short-lived HMAC signature. The Lambda verifies the signature before deriving
  `practice_id`, so the browser never chooses the practice boundary.
- `list_integrations` reports connection status and safety modes.
- Auth.js owns Google sign-in, OAuth state handling, and authorization-code
  exchange in the Next.js server.
- `connect_google_workspace` stores Auth.js-verified token material in AWS
  Secrets Manager and records connection metadata in `clinic_integrations`.
- `sync_google_calendar` refreshes the OAuth token, reads Google Calendar
  events for the next sync window, and refreshes the local schedule cache.
- `scan_gmail_inbox` refreshes the OAuth token, reads recent Gmail metadata and
  snippets matching clinic keywords, and upserts patient requests plus in-app
  action drafts. It does not delete durable open requests that are absent from a
  later scan. For scheduling requests such as meet-and-greet or initial
  consultation messages, draft replies include availability windows from the
  local Google Calendar cache, filtered by patient preferences in the email such
  as weekdays, next week, morning/afternoon, or after/before time constraints.
- Unknown senders are filtered conservatively. Automated, newsletter, and
  marketing-style messages are ignored unless they look like direct clinic or
  patient scheduling messages.
- `approve_and_send_gmail` sends the edited reply into the source Gmail thread
  only after the doctor clicks the send-specific approval button. It records the
  sent Gmail message id on the action for audit.

## Google scopes

Use the narrowest scopes we can:

- Google Calendar: `https://www.googleapis.com/auth/calendar.events.readonly`
- Gmail read: `https://www.googleapis.com/auth/gmail.readonly`
- Gmail send after approval: `https://www.googleapis.com/auth/gmail.compose`

`gmail.compose` can create drafts and send messages, so code paths using it must
be approval-gated.

Official docs:

- Gmail scopes: https://developers.google.com/workspace/gmail/api/auth/scopes
- Gmail draft creation: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create
- Gmail draft send: https://developers.google.com/gmail/api/reference/rest/v1/users.drafts/send
- Calendar scopes: https://developers.google.com/workspace/calendar/api/auth
- Calendar event list/sync: https://developers.google.com/calendar/api/v3/reference/events/list

## Next implementation steps

1. Add a patient matching/review workflow for unknown Gmail senders.
2. Add calendar-slot holds after an explicit approval step.
3. Add an explicit `create_gmail_draft` action if we want doctor-approved Gmail
   drafts before direct sending.
