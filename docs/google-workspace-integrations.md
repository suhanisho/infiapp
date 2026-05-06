# Google Workspace integration path

This app treats Google Calendar as the appointment source of truth and Gmail as
the patient communication source. The first implementation is deliberately
read-first and approval-gated.

## Safety rules

- Calendar writes are disabled until we explicitly add a user-approved write
  workflow.
- Gmail scans can create or refresh in-app action records and draft text, but
  they must not send email, label threads, archive messages, or create Gmail
  drafts automatically.
- Gmail draft creation and Gmail sending are separate future actions. Each must
  require an explicit approval event and preserve an audit trail.
- OAuth refresh tokens must not be stored in DynamoDB. Store token material in a
  secret store, and keep only metadata such as account email, scopes, sync
  tokens, and secret IDs in DynamoDB.

## Current repo shape

- `clinic_integrations` stores Google connection metadata, required scopes, and
  sync cursors.
- `clinic_schedule` stores a local cache of Google Calendar events, including
  external calendar/event IDs.
- `clinic_actions` stores Gmail-derived action records, draft text, approval
  state, and Gmail thread/message/draft IDs.
- `list_integrations` reports connection status and safety modes.
- Auth.js owns Google sign-in, OAuth state handling, and authorization-code
  exchange in the Next.js server.
- `connect_google_workspace` stores Auth.js-verified token material in AWS
  Secrets Manager and records connection metadata in `clinic_integrations`.
- `sync_google_calendar` refreshes the OAuth token, reads Google Calendar
  events for the next sync window, and refreshes the local schedule cache.
- `scan_gmail_inbox` refreshes the OAuth token, reads recent Gmail metadata and
  snippets matching clinic keywords, and prepares in-app action drafts. For
  scheduling requests such as meet-and-greet or initial consultation messages,
  draft replies include available slots from the local Google Calendar cache.

## Google scopes

Use the narrowest scopes we can:

- Google Calendar: `https://www.googleapis.com/auth/calendar.events.readonly`
- Gmail read: `https://www.googleapis.com/auth/gmail.readonly`
- Gmail draft/send path: `https://www.googleapis.com/auth/gmail.compose`

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
3. Add explicit, separate approval actions for `create_gmail_draft` and
   `send_gmail_draft` when we are ready to move beyond in-app drafts.
