"""Google Workspace integration boundary.

This module defines the scopes and safety contract for Google integrations.
Live OAuth and Google API calls should be implemented behind this boundary so
agents can keep tests focused on read/write intent.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, TypedDict

GOOGLE_CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GOOGLE_OPENID_SCOPE = "openid"
GOOGLE_EMAIL_SCOPE = "email"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

JsonObject = dict[str, Any]
QueryParams = Mapping[str, object] | Sequence[tuple[str, object]]


class GoogleWorkspaceError(RuntimeError):
    """Raised when Google refuses or cannot complete a read-only request."""


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


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
) -> JsonObject:
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        detail = raw_error
        try:
            parsed = json.loads(raw_error)
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    detail = str(error["message"])
                elif isinstance(parsed.get("error_description"), str):
                    detail = str(parsed["error_description"])
                elif isinstance(parsed.get("error"), str):
                    detail = str(parsed["error"])
        except json.JSONDecodeError:
            pass
        raise GoogleWorkspaceError(f"Google API request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GoogleWorkspaceError(f"Google API request failed: {exc.reason}") from exc

    if not raw_body:
        return {}
    parsed = json.loads(raw_body)
    if not isinstance(parsed, dict):
        raise GoogleWorkspaceError("Google API returned an unexpected response.")
    return parsed


def _url_with_params(url: str, params: QueryParams) -> str:
    encoded = urllib.parse.urlencode(params, doseq=True)
    return f"{url}?{encoded}" if encoded else url


def refresh_google_access_token(
    *,
    token_response: Mapping[str, Any],
    client_id: str,
    client_secret: str,
) -> JsonObject:
    refresh_token = token_response.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleWorkspaceError("Google refresh token is missing. Reconnect Google with consent.")
    if not client_id or not client_secret:
        raise GoogleWorkspaceError("Google OAuth client ID and secret are required for live sync.")

    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    refreshed = _json_request(
        GOOGLE_TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=payload,
    )
    access_token = refreshed.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise GoogleWorkspaceError("Google did not return an access token.")

    expires_in = refreshed.get("expires_in")
    if isinstance(expires_in, (int, float)):
        refreshed["expires_at"] = int(time.time() + int(expires_in))
    refreshed["refresh_token"] = refresh_token
    return refreshed


class GoogleWorkspaceHttpClient:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def _get(self, url: str, params: QueryParams) -> JsonObject:
        return _json_request(
            _url_with_params(url, params),
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

    def list_calendar_events(
        self,
        *,
        calendar_id: str,
        time_min: str,
        time_max: str,
        max_results: int = 50,
    ) -> list[JsonObject]:
        url = GOOGLE_CALENDAR_EVENTS_URL.format(calendar_id=urllib.parse.quote(calendar_id, safe=""))
        data = self._get(
            url,
            {
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max_results,
            },
        )
        items = data.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    def list_gmail_message_metadata(self, *, query: str, max_results: int = 10) -> list[JsonObject]:
        listing = self._get(
            GMAIL_MESSAGES_URL,
            {
                "q": query,
                "maxResults": max_results,
                "includeSpamTrash": "false",
            },
        )
        message_refs = listing.get("messages", [])
        messages: list[JsonObject] = []
        iterable_message_refs = message_refs if isinstance(message_refs, list) else []
        for message_ref in iterable_message_refs:
            if not isinstance(message_ref, dict):
                continue
            message_id = message_ref.get("id")
            if not isinstance(message_id, str) or not message_id:
                continue
            messages.append(self.get_gmail_message_full(message_id))
        return messages

    def get_gmail_message_metadata(self, message_id: str) -> JsonObject:
        url = f"{GMAIL_MESSAGES_URL}/{urllib.parse.quote(message_id, safe='')}"
        return self._get(
            url,
            [
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Reply-To"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Date"),
            ],
        )

    def get_gmail_message_full(self, message_id: str) -> JsonObject:
        url = f"{GMAIL_MESSAGES_URL}/{urllib.parse.quote(message_id, safe='')}"
        return self._get(url, {"format": "full"})


def required_google_scopes() -> dict[str, list[str]]:
    return {
        "google_calendar": [GOOGLE_CALENDAR_READONLY_SCOPE],
        "gmail": [GMAIL_READONLY_SCOPE],
        "oauth_identity": [GOOGLE_OPENID_SCOPE, GOOGLE_EMAIL_SCOPE],
        "future_gmail_send": [GMAIL_COMPOSE_SCOPE],
    }
