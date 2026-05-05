"""Google Workspace integration boundary.

This module defines the scopes and safety contract for Google integrations.
Live OAuth and Google API calls should be implemented behind this boundary so
agents can keep tests focused on read/write intent.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GOOGLE_OPENID_SCOPE = "openid"
GOOGLE_EMAIL_SCOPE = "email"


class CalendarSyncPreview(TypedDict):
    source_of_truth: str
    write_mode: str
    external_writes: int
    events_read: int
    appointments_cached: int
    status: str
    message: str


class GmailScanPreview(TypedDict):
    source_of_truth: str
    write_mode: str
    external_writes: int
    messages_scanned: int
    proposed_actions: int
    status: str
    message: str


class GoogleWorkspaceClient(Protocol):
    """Protocol for the future live Google client."""

    def preview_calendar_sync(self) -> CalendarSyncPreview:
        """Read calendar data and describe local cache changes."""

    def preview_gmail_scan(self) -> GmailScanPreview:
        """Read Gmail messages and describe proposed action records."""


def required_google_scopes() -> dict[str, list[str]]:
    return {
        "google_calendar": [GOOGLE_CALENDAR_READONLY_SCOPE],
        "gmail": [GMAIL_READONLY_SCOPE],
        "oauth_identity": [GOOGLE_OPENID_SCOPE, GOOGLE_EMAIL_SCOPE],
        "future_gmail_send": [GMAIL_COMPOSE_SCOPE],
    }
