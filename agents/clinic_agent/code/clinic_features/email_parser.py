"""Deterministic Gmail message normalization.

This module deliberately has no database, model, or Google API dependencies.
It converts an already-fetched Gmail API message into a stable internal
contract for downstream classification and conversation processing.
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
from datetime import datetime, timezone, tzinfo
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from .contracts import NormalizedEmail

MAX_MESSAGE_TEXT_CHARS = 4000
MAX_SUMMARY_CHARS = 120
MAX_SOURCE_EXCERPT_CHARS = 1200
MAX_SIGNATURE_TEXT_CHARS = 2000


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def gmail_headers(message: dict[str, Any]) -> dict[str, str]:
    """Return case-insensitive Gmail headers keyed by lowercase name."""

    payload = message.get("payload")
    raw_headers = payload.get("headers") if isinstance(payload, dict) else None
    headers: dict[str, str] = {}
    if not isinstance(raw_headers, list):
        return headers
    for raw_header in raw_headers:
        if not isinstance(raw_header, dict):
            continue
        name = raw_header.get("name")
        value = raw_header.get("value")
        if isinstance(name, str) and isinstance(value, str):
            headers[name.lower()] = value
    return headers


def _decode_body_data(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        padded = value + ("=" * (-len(value) % 4))
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _html_to_text(value: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return html.unescape(without_tags)


def _payload_text_parts(payload: object) -> tuple[list[str], list[str]]:
    if not isinstance(payload, dict):
        return [], []

    plain_parts: list[str] = []
    html_parts: list[str] = []
    mime_type = str(payload.get("mimeType", "")).lower()
    body = payload.get("body")
    body_data = body.get("data") if isinstance(body, dict) else None
    decoded = _decode_body_data(body_data)
    if decoded:
        if "html" in mime_type:
            html_parts.append(_html_to_text(decoded))
        else:
            plain_parts.append(decoded)

    raw_parts = payload.get("parts")
    if isinstance(raw_parts, list):
        for part in raw_parts:
            nested_plain, nested_html = _payload_text_parts(part)
            plain_parts.extend(nested_plain)
            html_parts.extend(nested_html)

    return plain_parts, html_parts


def _message_text(message: dict[str, Any]) -> str:
    plain_parts, html_parts = _payload_text_parts(message.get("payload"))
    body_text = "\n".join(part for part in [*plain_parts, *html_parts] if part.strip())
    if body_text.strip():
        return _truncate(body_text, MAX_MESSAGE_TEXT_CHARS)
    return _truncate(html.unescape(str(message.get("snippet") or "")), MAX_MESSAGE_TEXT_CHARS)


def visible_reply_text(value: str) -> str:
    """Remove common quoted-thread markers from the latest visible reply."""

    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = re.split(
        r"(?im)\n\s*(?:on .+?wrote:|from:\s+.+|sent:\s+.+|to:\s+.+|subject:\s+.+|[-]+original message[-]+)",
        text,
        maxsplit=1,
    )[0]
    visible_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if re.match(r"(?i)^on .+ wrote:$", stripped):
            break
        if stripped.startswith(">"):
            break
        if visible_lines and re.match(r"(?i)^(from|sent|to|subject):\s+", stripped):
            break
        visible_lines.append(line)
    return _truncate("\n".join(visible_lines).strip(), MAX_MESSAGE_TEXT_CHARS)


def _message_datetime(message: dict[str, Any], headers: dict[str, str]) -> datetime:
    raw_internal_date = message.get("internalDate")
    if isinstance(raw_internal_date, str) and raw_internal_date.isdigit():
        return datetime.fromtimestamp(int(raw_internal_date) / 1000, tz=timezone.utc)
    raw_date = headers.get("date", "")
    if raw_date:
        try:
            parsed = parsedate_to_datetime(raw_date)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def normalized_message_signature(sender_email: str, subject: str, message_text: str) -> str:
    """Build a stable duplicate-detection signature for equivalent messages."""

    normalized_subject = re.sub(r"^(re|fw|fwd):\s*", "", subject.strip().lower())
    normalized_text = re.sub(r"\s+", " ", message_text.strip().lower())
    material = (
        f"{sender_email.strip().lower()}\n"
        f"{normalized_subject}\n"
        f"{normalized_text[:MAX_SIGNATURE_TEXT_CHARS]}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def parse_gmail_message(message: dict[str, Any], *, clinic_timezone: tzinfo) -> NormalizedEmail | None:
    """Normalize one Gmail API message without classifying or persisting it."""

    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        return None

    headers = gmail_headers(message)
    snippet = html.unescape(str(message.get("snippet") or ""))
    message_text = _message_text(message) or snippet
    sender_name, sender_email = parseaddr(headers.get("from", ""))
    normalized_sender_email = sender_email.strip().lower()
    subject = headers.get("subject", "").strip()
    received_at = _message_datetime(message, headers)
    localized = received_at.astimezone(clinic_timezone)
    thread_id = message.get("threadId")
    summary = _truncate(subject or message_text or snippet or "New Gmail message", MAX_SUMMARY_CHARS)
    source_excerpt = _truncate(
        f"From: {headers.get('from', '')}\nSubject: {subject}\n\n{message_text}".strip(),
        MAX_SOURCE_EXCERPT_CHARS,
    )
    return {
        "gmail_message_id": message_id,
        "gmail_thread_id": thread_id if isinstance(thread_id, str) else "",
        "message_id_header": headers.get("message-id", "").strip(),
        "in_reply_to": headers.get("in-reply-to", "").strip(),
        "references": headers.get("references", "").strip(),
        "sender_name": sender_name,
        "sender_email": normalized_sender_email,
        "subject": subject,
        "snippet": snippet,
        "message_text": message_text,
        "source_excerpt": source_excerpt,
        "summary": summary,
        "received_at": received_at,
        "time_label": localized.strftime("%I:%M %p").lstrip("0"),
        "message_signature": normalized_message_signature(normalized_sender_email, subject, message_text),
    }
