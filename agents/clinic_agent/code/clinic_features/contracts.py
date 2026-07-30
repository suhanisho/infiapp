"""Domain contracts shared by the clinic agent's feature modules."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class NormalizedEmail(TypedDict):
    """A Gmail message after deterministic metadata and body normalization."""

    gmail_message_id: str
    gmail_thread_id: str
    message_id_header: str
    in_reply_to: str
    references: str
    sender_name: str
    sender_email: str
    subject: str
    snippet: str
    message_text: str
    source_excerpt: str
    summary: str
    received_at: datetime
    time_label: str
    message_signature: str


class RequestedSlotConstraints(TypedDict):
    """Serializable date and time preferences extracted from a patient email."""

    date_from: str | None
    date_to: str | None
    preferred_periods: list[str]
    explicit_datetimes: list[str]
    timezone: str
    needs_clarification: bool


class AvailableWindow(TypedDict):
    """A backend-verified Calendar window that may be offered to a patient."""

    slot_id: str
    start_at: str
    end_at: str
    display_text: str


class EmailAnalysis(TypedDict):
    """Structured understanding produced for one immutable inbound email."""

    classification: str
    confidence: float
    requires_human_review: bool
    constraints: RequestedSlotConstraints


class DraftResponse(TypedDict):
    """An AI-written response linked to verified availability facts."""

    body: str
    referenced_slot_ids: list[str]
