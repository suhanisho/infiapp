"""Clinic assistant Lambda agent.

The app is deliberately human-in-the-loop: this agent records proposals,
approvals, and completions. External actions such as Gmail sending only happen
through explicit action-specific approval paths.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from decimal import Decimal
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from email.utils import formatdate
from typing import Any, TypedDict, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from generated.dynamodb import (
    ClinicActionsItem,
    ClinicIntegrationsItem,
    ClinicPatientRequestsItem,
    ClinicPatientsItem,
    ClinicPracticeMembersItem,
    ClinicScheduleItem,
    ClinicSettingsItem,
    delete_clinic_schedule,
    get_clinic_actions,
    get_clinic_integrations,
    get_clinic_patient_requests,
    get_clinic_patients,
    put_clinic_actions,
    put_clinic_integrations,
    put_clinic_patient_requests,
    put_clinic_patients,
    put_clinic_practice_members,
    put_clinic_schedule,
    put_clinic_settings,
    query_clinic_actions,
    query_clinic_integrations,
    query_clinic_patient_requests,
    query_clinic_patients,
    query_clinic_schedule,
    query_clinic_settings,
)
from google_workspace import GoogleWorkspaceError, GoogleWorkspaceHttpClient, refresh_google_access_token, required_google_scopes
from response import json_response

LEGACY_CLINIC_ID = "shalini-clinic"
CLINIC_ID = LEGACY_CLINIC_ID
_CURRENT_PRACTICE_ID: ContextVar[str] = ContextVar("clinic_agent_practice_id", default=LEGACY_CLINIC_ID)
SEED_UPDATED_AT = "2026-05-02T00:00:00+00:00"
COMPLETION_NOTE = "Doctor approved and stored this action. No external email or calendar action was taken by the MVP."
GMAIL_SEND_COMPLETION_NOTE = "Doctor explicitly approved and Gmail sent this message."
GMAIL_SEND_AND_BOOK_COMPLETION_NOTE = (
    "Doctor explicitly approved, Gmail sent this message, and Google Calendar was updated."
)
DEFAULT_CLINIC_TIMEZONE = "Europe/London"
CALENDAR_SYNC_DAYS = 14
GMAIL_SCAN_QUERY = (
    "in:inbox newer_than:30d "
    "(appointment OR booking OR book OR consultation OR referral OR meet OR greet OR intro OR reschedule OR cancel "
    "OR follow-up OR pregnant OR pregnancy OR bleeding OR pain OR movement OR result OR report OR prescription "
    "OR invoice OR payment OR form OR directions)"
)
GMAIL_SCAN_MAX_MESSAGES = 10
DEFAULT_SLOT_SUGGESTIONS = 3
SLOT_SEARCH_DAYS = 14
SLOT_STEP_MINUTES = 30
MIN_BOOKING_NOTICE_HOURS = 2
ACTOR_ASSERTION_TTL_SECONDS = 300
REPLY_REVIEW_ACTION_KIND = "review_reply"
COMPLETED_STATUSES = {"completed"}
WEEKDAY_ALIASES = {
    0: ("monday", "mondays", "mon"),
    1: ("tuesday", "tuesdays", "tue", "tues"),
    2: ("wednesday", "wednesdays", "wed"),
    3: ("thursday", "thursdays", "thu", "thur", "thurs"),
    4: ("friday", "fridays", "fri"),
    5: ("saturday", "saturdays", "sat"),
    6: ("sunday", "sundays", "sun"),
}
MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
CONTEXT_ANCHOR_TERMS = (
    "scan",
    "ultrasound",
    "blood test",
    "test",
    "procedure",
    "mri",
    "ct",
    "x-ray",
    "xray",
)
ANCHOR_FOLLOW_UP_TERMS = ("after", "afterward", "afterwards", "following", "post", "once")
ANCHOR_START_ONLY_BUFFER_MINUTES = 90
CLINIC_MESSAGE_KEYWORDS = (
    "appointment",
    "booking",
    "book",
    "consultation",
    "referral",
    "meet",
    "greet",
    "intro",
    "reschedule",
    "cancel",
    "follow-up",
    "follow up",
    "clinic",
    "patient",
)
NON_PATIENT_SENDER_MARKERS = (
    "no-reply",
    "noreply",
    "newsletter",
    "marketing",
    "updates",
    "notifications",
    "donotreply",
    "do-not-reply",
)
NON_PATIENT_TEXT_MARKERS = (
    "unsubscribe",
    "sale ends",
    "limited time offer",
    "webinar",
    "digest",
    "newsletter",
    "terms of service",
    "privacy policy",
    "verify your account",
    "password reset",
    "delivery update",
)
MEDICAL_PRACTICE_TERMS = (
    "shalini",
    "clinic",
    "doctor",
    "dr ",
    "gp",
    "referral",
    "patient",
    "medical",
    "health",
    "prescription",
    "scan",
    "ultrasound",
    "gynaecology",
    "gynecology",
    "hormone",
    "fertility",
    "pregnancy",
    "pcos",
    "endometriosis",
    "menopause",
    "pelvic",
    "bleeding",
    "pain",
)
SCHEDULING_INTENT_TERMS = (
    "appointment",
    "consultation",
    "reschedule",
    "cancel",
    "follow-up",
    "follow up",
    "meet & greet",
    "meet and greet",
    "referral",
)
BOOKING_PHRASES = (
    "book an appointment",
    "book a consultation",
    "book a meet",
    "arrange an appointment",
    "arrange a consultation",
    "schedule an appointment",
)
URGENT_CLINICAL_TERMS = (
    "reduced fetal movement",
    "no fetal movement",
    "heavy bleeding",
    "severe bleeding",
    "severe pain",
    "unbearable pain",
    "chest pain",
    "shortness of breath",
    "fainting",
    "dizzy and faint",
    "high fever",
    "fever",
    "ectopic",
    "miscarriage",
    "waters broke",
    "water broke",
    "contractions",
)
ROUTINE_CLINICAL_TERMS = (
    "symptom",
    "symptoms",
    "pain",
    "bleeding",
    "cramps",
    "cramping",
    "discharge",
    "pregnant",
    "pregnancy",
    "period",
    "hormone",
    "fertility",
    "pcos",
    "endometriosis",
    "menopause",
)
RESULT_QUERY_TERMS = (
    "result",
    "results",
    "report",
    "scan report",
    "blood test",
    "test",
)
PRESCRIPTION_ADMIN_TERMS = (
    "prescription",
    "repeat prescription",
    "medication",
    "medicine",
    "sick note",
    "letter",
    "form",
    "referral letter",
)
BILLING_TERMS = (
    "invoice",
    "payment",
    "billing",
    "receipt",
    "insurance",
    "claim",
    "fee",
)
LOGISTICS_TERMS = (
    "directions",
    "address",
    "parking",
    "where are you",
    "location",
    "zoom",
    "teams link",
)
ANXIOUS_TONE_TERMS = (
    "worried",
    "anxious",
    "concerned",
    "scared",
    "frustrated",
    "upset",
    "urgent",
    "asap",
)
FOLLOW_UP_TERMS = ("follow-up", "follow up", "review", "next steps")
BOOKING_SELECTION_TERMS = (
    "can do",
    "could do",
    "works",
    "work for me",
    "suits",
    "prefer",
    "preferred",
    "available",
    "free",
    "slot",
    "appointment",
    "consultation",
    "meet",
    "see dr",
    "see doctor",
    "see the doctor",
)
DIRECT_PATIENT_REQUEST_PATTERN = re.compile(
    r"\b(i|i'm|i’d|i'd|my|me|could|can|would|please|available|prefer|need|want)\b",
    flags=re.IGNORECASE,
)


class SlotConstraints(TypedDict):
    preferred_weekdays: set[int]
    earliest_date: date | None
    latest_date: date | None
    earliest_at: datetime | None
    daily_start: time | None
    daily_end: time | None
    anchor_event: str
    anchor_at: datetime | None
    constraint_summary: str
    notes: list[str]


class TriageResult(TypedDict):
    request_type: str
    urgency_level: str
    risk_level: str
    requires_doctor_review: bool
    suggested_next_action: str
    patient_emotional_tone: str
    triage_confidence: Decimal
    triage_reason: str
    action_priority: str


class DateMention(TypedDict):
    value: date
    start: int
    end: int


class TimeMention(TypedDict):
    value: time
    start: int
    end: int


class BookingCandidate(TypedDict):
    start_at: datetime
    end_at: datetime
    label: str
    available: bool
    reason: str


class SentGmailReply(TypedDict):
    sent_message_id: str
    recipient: str


def _practice_id() -> str:
    return _CURRENT_PRACTICE_ID.get()


def _clinic_id() -> str:
    return _practice_id()


def _actor_email_from_payload(payload: dict[str, Any]) -> str:
    for key in ("actorEmail", "accountEmail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def _internal_agent_secret() -> str:
    return (
        os.environ.get("CLINIC_AGENT_INTERNAL_SECRET", "").strip()
        or os.environ.get("NEXTAUTH_SECRET", "").strip()
        or os.environ.get("AUTH_SECRET", "").strip()
    )


def _signed_actor_message(actor_email: str, issued_at: str) -> str:
    return f"{actor_email}:{issued_at}"


def _verify_actor_assertion(payload: dict[str, Any]) -> str:
    actor_email = _actor_email_from_payload(payload)
    if not actor_email:
        return ""

    secret = _internal_agent_secret()
    if not secret:
        raise RuntimeError("Trusted actor assertion secret is not configured.")

    issued_at = str(payload.get("actorIssuedAt", "")).strip()
    signature = str(payload.get("actorSignature", "")).strip()
    if not issued_at or not signature:
        raise RuntimeError("Trusted actor assertion is required.")

    try:
        issued_at_seconds = int(issued_at)
    except ValueError as exc:
        raise RuntimeError("Trusted actor assertion timestamp is invalid.") from exc

    now_seconds = int(datetime.now(timezone.utc).timestamp())
    if abs(now_seconds - issued_at_seconds) > ACTOR_ASSERTION_TTL_SECONDS:
        raise RuntimeError("Trusted actor assertion has expired.")

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        _signed_actor_message(actor_email, issued_at).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise RuntimeError("Trusted actor assertion signature is invalid.")
    return actor_email


def _practice_id_for_actor(actor_email: str) -> str:
    normalized = actor_email.strip().lower()
    if not normalized:
        return LEGACY_CLINIC_ID
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"practice_{digest}"


def _with_current_practice(item: Any) -> dict[str, Any]:
    return {**item, "clinic_id": _clinic_id()}


def _demo_seed_enabled() -> bool:
    configured = os.environ.get("CLINIC_DEMO_SEED_DATA", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return _practice_id() == LEGACY_CLINIC_ID


def _practice_member_id(actor_email: str) -> str:
    return f"member_{hashlib.sha256(actor_email.strip().lower().encode('utf-8')).hexdigest()[:20]}"


def _request_action_id(patient_request_id: str, action_kind: str) -> str:
    return f"{patient_request_id}#action#{_safe_external_fragment(action_kind)}"

SEED_ACTIONS: list[ClinicActionsItem] = [
    {
        "clinic_id": CLINIC_ID,
        "action_id": "act_001",
        "action_type": "enquiry",
        "priority": "new",
        "status": "needs_approval",
        "patient_id": "p10",
        "patient_name": "Rachel Davies",
        "patient_request_id": "seed-request-rachel-davies",
        "time_label": "9:41 AM",
        "source_summary": "New patient referred by GP, wants initial consultation",
        "source_message": "Hi, I was referred by Dr. Patel at the Angel Medical Centre. I'd like to book an initial consultation at your earliest convenience. I'm flexible on days but prefer afternoons if possible. Thank you, Rachel",
        "draft_message": "Dear Rachel,\n\nThank you for getting in touch, and welcome. I have the following afternoon slots available:\n\n- Wednesday 30 Apr at 2:00 PM\n- Friday 2 May at 3:15 PM\n- Monday 5 May at 2:30 PM\n\nInitial consultations are 45 minutes. Please let me know which works best and I will confirm your booking.\n\nWarm regards,\nDr. Shalini's Clinic",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
        "metadata": {},
        "source_provider": "gmail",
        "source_thread_id": "gmail-thread-rachel-davies",
        "source_message_id": "gmail-message-rachel-davies",
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "",
        "created_at": "2026-05-02T08:41:00+00:00",
        "updated_at": "2026-05-02T08:41:00+00:00",
    },
    {
        "clinic_id": CLINIC_ID,
        "action_id": "act_002",
        "action_type": "reschedule",
        "priority": "action",
        "status": "needs_approval",
        "patient_id": "p8",
        "patient_name": "Fatima Ali",
        "patient_request_id": "seed-request-fatima-ali",
        "time_label": "8:15 AM",
        "source_summary": "Wants to move Friday appointment to next week",
        "source_message": "Hi, I'm afraid something has come up and I won't be able to make my Friday appointment. Could we reschedule to sometime next week? Monday or Tuesday would be ideal. Thanks, Fatima",
        "draft_message": "Dear Fatima,\n\nOf course, no problem at all. I can offer the following options for next week:\n\n- Monday 5 May at 11:00 AM\n- Tuesday 6 May at 10:30 AM\n- Tuesday 6 May at 3:00 PM\n\nPlease let me know your preference.\n\nBest wishes,\nDr. Shalini's Clinic",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
        "metadata": {},
        "source_provider": "gmail",
        "source_thread_id": "gmail-thread-fatima-ali",
        "source_message_id": "gmail-message-fatima-ali",
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "",
        "created_at": "2026-05-02T07:15:00+00:00",
        "updated_at": "2026-05-02T07:15:00+00:00",
    },
    {
        "clinic_id": CLINIC_ID,
        "action_id": "act_003",
        "action_type": "nhs",
        "priority": "info",
        "status": "proposed",
        "patient_id": "",
        "patient_name": "",
        "patient_request_id": "seed-request-nhs-clinic",
        "time_label": "7:30 AM",
        "source_summary": "NHS clinic confirmed for Wednesday",
        "source_message": "Wednesday 30 Apr, 8:30 AM - 1:00 PM\nSt Mary's Hospital, Praed Street\n4 patients scheduled",
        "draft_message": "",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
        "metadata": {},
        "source_provider": "google_calendar",
        "source_thread_id": "",
        "source_message_id": "",
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "Calendar write intentionally deferred from MVP.",
        "created_at": "2026-05-02T06:30:00+00:00",
        "updated_at": "2026-05-02T06:30:00+00:00",
    },
    {
        "clinic_id": CLINIC_ID,
        "action_id": "act_004",
        "action_type": "reminder",
        "priority": "info",
        "status": "needs_approval",
        "patient_id": "p9",
        "patient_name": "Priya Sharma",
        "patient_request_id": "seed-request-priya-sharma",
        "time_label": "Auto",
        "source_summary": "Follow-up due - last seen 4 weeks ago",
        "source_message": "",
        "draft_message": "Dear Priya,\n\nI hope you are well. It has been about four weeks since your last visit and I would like to schedule a follow-up to review your progress. I have availability on:\n\n- Friday 2 May at 10:00 AM\n- Monday 5 May at 9:30 AM\n\nPlease let me know if either works, or suggest a time that suits you better.\n\nBest wishes,\nDr. Shalini's Clinic",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
        "metadata": {},
        "source_provider": "gmail",
        "source_thread_id": "gmail-thread-priya-sharma",
        "source_message_id": "",
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "",
        "created_at": "2026-05-02T06:00:00+00:00",
        "updated_at": "2026-05-02T06:00:00+00:00",
    },
]

SEED_PATIENTS: list[ClinicPatientsItem] = [
    {
        "clinic_id": CLINIC_ID,
        "patient_id": "p1",
        "name": "Emma Richardson",
        "email": "emma.r@gmail.com",
        "phone": "07412 345 678",
        "last_visit": "28 Apr 2026",
        "next_appt": "-",
        "visits": 4,
        "status": "active",
        "notes": "Reviewing hormone panel results. TSH slightly elevated - may need dose adjustment. Prefers morning slots.",
    },
    {
        "clinic_id": CLINIC_ID,
        "patient_id": "p2",
        "name": "Lucy Chen",
        "email": "lucy.chen@outlook.com",
        "phone": "07891 234 567",
        "last_visit": "28 Apr 2026",
        "next_appt": "-",
        "visits": 1,
        "status": "new",
        "notes": "Referred by Dr. Patel at Angel Medical Centre. Irregular cycles and pelvic discomfort. GP referral letter on file.",
    },
    {
        "clinic_id": CLINIC_ID,
        "patient_id": "p3",
        "name": "Sarah Mitchell",
        "email": "s.mitchell@yahoo.com",
        "phone": "07723 456 789",
        "last_visit": "28 Apr 2026",
        "next_appt": "-",
        "visits": 3,
        "status": "active",
        "notes": "Follow-up on ultrasound. Small ovarian cyst detected - likely functional. Monitoring plan discussed.",
    },
    {
        "clinic_id": CLINIC_ID,
        "patient_id": "p8",
        "name": "Fatima Ali",
        "email": "fatima.ali@gmail.com",
        "phone": "07978 901 234",
        "last_visit": "4 Apr 2026",
        "next_appt": "Fri 2 May, 11:00 AM",
        "visits": 3,
        "status": "active",
        "notes": "Endometriosis management. Hormonal treatment - review symptom diary. May discuss surgical referral.",
    },
    {
        "clinic_id": CLINIC_ID,
        "patient_id": "p9",
        "name": "Priya Sharma",
        "email": "priya.sharma@gmail.com",
        "phone": "07089 012 345",
        "last_visit": "31 Mar 2026",
        "next_appt": "-",
        "visits": 6,
        "status": "overdue",
        "notes": "Long-term patient. PCOS management with metformin. Follow-up overdue - 4 weeks since last visit.",
    },
    {
        "clinic_id": CLINIC_ID,
        "patient_id": "p10",
        "name": "Rachel Davies",
        "email": "rachel.d@gmail.com",
        "phone": "07190 123 456",
        "last_visit": "-",
        "next_appt": "Pending",
        "visits": 0,
        "status": "new",
        "notes": "New enquiry via email. Referred by Dr. Patel, Angel Medical Centre. Prefers afternoon appointments.",
    },
]

SEED_SCHEDULE: list[ClinicScheduleItem] = [
    {
        "clinic_id": CLINIC_ID,
        "event_id": "2026-04-28-0900",
        "day_key": "Mon 28",
        "day_label": "Monday 28 Apr",
        "day_type": "private",
        "start_time": "09:00",
        "end_time": "09:45",
        "start_at": "2026-04-28T09:00:00+01:00",
        "end_at": "2026-04-28T09:45:00+01:00",
        "external_calendar_id": "primary",
        "external_etag": "",
        "external_event_id": "gcal-2026-04-28-0900",
        "last_synced_at": SEED_UPDATED_AT,
        "patient_id": "p1",
        "patient_name": "Emma Richardson",
        "source_provider": "google_calendar",
        "appointment_type": "Follow-up",
        "status": "completed",
        "sort_order": 1,
    },
    {
        "clinic_id": CLINIC_ID,
        "event_id": "2026-04-28-1330",
        "day_key": "Mon 28",
        "day_label": "Monday 28 Apr",
        "day_type": "private",
        "start_time": "13:30",
        "end_time": "14:00",
        "start_at": "2026-04-28T13:30:00+01:00",
        "end_at": "2026-04-28T14:00:00+01:00",
        "external_calendar_id": "primary",
        "external_etag": "",
        "external_event_id": "gcal-2026-04-28-1330",
        "last_synced_at": SEED_UPDATED_AT,
        "patient_id": "p3",
        "patient_name": "Sarah Mitchell",
        "source_provider": "google_calendar",
        "appointment_type": "Follow-up",
        "status": "in_progress",
        "sort_order": 2,
    },
    {
        "clinic_id": CLINIC_ID,
        "event_id": "2026-04-30-0830",
        "day_key": "Wed 30",
        "day_label": "Wednesday 30 Apr",
        "day_type": "nhs",
        "start_time": "08:30",
        "end_time": "13:00",
        "start_at": "2026-04-30T08:30:00+01:00",
        "end_at": "2026-04-30T13:00:00+01:00",
        "external_calendar_id": "primary",
        "external_etag": "",
        "external_event_id": "gcal-2026-04-30-0830",
        "last_synced_at": SEED_UPDATED_AT,
        "patient_id": "",
        "patient_name": "NHS Clinic - St Mary's",
        "source_provider": "google_calendar",
        "appointment_type": "NHS Duty",
        "status": "nhs",
        "sort_order": 3,
    },
    {
        "clinic_id": CLINIC_ID,
        "event_id": "2026-04-30-1400",
        "day_key": "Wed 30",
        "day_label": "Wednesday 30 Apr",
        "day_type": "nhs",
        "start_time": "14:00",
        "end_time": "14:45",
        "start_at": "2026-04-30T14:00:00+01:00",
        "end_at": "2026-04-30T14:45:00+01:00",
        "external_calendar_id": "primary",
        "external_etag": "",
        "external_event_id": "gcal-2026-04-30-1400",
        "last_synced_at": SEED_UPDATED_AT,
        "patient_id": "",
        "patient_name": "Available",
        "source_provider": "google_calendar",
        "appointment_type": "Open slot",
        "status": "open",
        "sort_order": 4,
    },
    {
        "clinic_id": CLINIC_ID,
        "event_id": "2026-05-02-1000",
        "day_key": "Fri 2",
        "day_label": "Friday 2 May",
        "day_type": "private",
        "start_time": "10:00",
        "end_time": "10:45",
        "start_at": "2026-05-02T10:00:00+01:00",
        "end_at": "2026-05-02T10:45:00+01:00",
        "external_calendar_id": "primary",
        "external_etag": "",
        "external_event_id": "gcal-2026-05-02-1000",
        "last_synced_at": SEED_UPDATED_AT,
        "patient_id": "",
        "patient_name": "Available",
        "source_provider": "google_calendar",
        "appointment_type": "Open slot",
        "status": "open",
        "sort_order": 5,
    },
    {
        "clinic_id": CLINIC_ID,
        "event_id": "2026-05-02-1100",
        "day_key": "Fri 2",
        "day_label": "Friday 2 May",
        "day_type": "private",
        "start_time": "11:00",
        "end_time": "11:30",
        "start_at": "2026-05-02T11:00:00+01:00",
        "end_at": "2026-05-02T11:30:00+01:00",
        "external_calendar_id": "primary",
        "external_etag": "",
        "external_event_id": "gcal-2026-05-02-1100",
        "last_synced_at": SEED_UPDATED_AT,
        "patient_id": "p8",
        "patient_name": "Fatima Ali",
        "source_provider": "google_calendar",
        "appointment_type": "Follow-up",
        "status": "upcoming",
        "sort_order": 6,
    },
]

SEED_SETTINGS: list[ClinicSettingsItem] = [
    {
        "clinic_id": CLINIC_ID,
        "setting_id": "availability_rules",
        "updated_at": SEED_UPDATED_AT,
        "data": {
            "items": [
                {"day": "Monday", "enabled": True, "hours": "9:00 AM - 5:00 PM", "type": "Private"},
                {"day": "Tuesday", "enabled": True, "hours": "9:00 AM - 5:00 PM", "type": "Private"},
                {"day": "Wednesday", "enabled": True, "hours": "8:30 AM - 5:00 PM", "type": "NHS + Private"},
                {"day": "Thursday", "enabled": True, "hours": "9:00 AM - 5:00 PM", "type": "NHS"},
                {"day": "Friday", "enabled": True, "hours": "9:00 AM - 4:30 PM", "type": "Private"},
            ]
        },
    },
    {
        "clinic_id": CLINIC_ID,
        "setting_id": "appointment_types",
        "updated_at": SEED_UPDATED_AT,
        "data": {
            "items": [
                {"name": "Initial Consultation", "duration": "45 min", "color": "#3b82f6"},
                {"name": "Follow-up", "duration": "20 min", "color": "#10b981"},
                {"name": "Scan / Procedure", "duration": "30 min", "color": "#8b5cf6"},
            ]
        },
    },
    {
        "clinic_id": CLINIC_ID,
        "setting_id": "preferences",
        "updated_at": SEED_UPDATED_AT,
        "data": {
            "items": [
                {"label": "Buffer between appointments", "value": "15 min"},
                {"label": "Lunch break", "value": "1:00 - 1:30 PM"},
                {"label": "Max patients per day", "value": "8"},
                {"label": "Auto-send confirmations", "value": "Off"},
            ]
        },
    },
]

GOOGLE_SCOPES = required_google_scopes()
GOOGLE_TOKEN_SECRET_DEFAULT_ROOT_PREFIX = "shalini-clinic"
SEED_INTEGRATIONS: list[ClinicIntegrationsItem] = [
    {
        "clinic_id": CLINIC_ID,
        "integration_id": "google_calendar",
        "provider": "google_calendar",
        "status": "ready_to_connect",
        "account_email": "",
        "calendar_id": "primary",
        "calendar_sync_token": "",
        "gmail_history_id": "",
        "required_scopes": GOOGLE_SCOPES["google_calendar"],
        "write_mode": "read_source_book_after_approval",
        "token_secret_id": "",
        "last_sync_at": "",
        "last_error": "",
        "connected_at": "",
        "updated_at": SEED_UPDATED_AT,
    },
    {
        "clinic_id": CLINIC_ID,
        "integration_id": "gmail",
        "provider": "gmail",
        "status": "ready_to_connect",
        "account_email": "",
        "calendar_id": "",
        "calendar_sync_token": "",
        "gmail_history_id": "",
        "required_scopes": GOOGLE_SCOPES["gmail"],
        "write_mode": "read_inbox_send_after_approval",
        "token_secret_id": "",
        "last_sync_at": "",
        "last_error": "",
        "connected_at": "",
        "updated_at": SEED_UPDATED_AT,
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clinic_timezone() -> timezone | ZoneInfo:
    zone_name = os.environ.get("CLINIC_TIMEZONE", DEFAULT_CLINIC_TIMEZONE).strip() or DEFAULT_CLINIC_TIMEZONE
    try:
        return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _dynamodb_decimal(value: str) -> Any:
    return Decimal(value)


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 1)].rstrip()}..."


def _safe_external_fragment(value: str) -> str:
    fragment = re.sub(r"[^A-Za-z0-9_.:@=-]+", "-", value).strip("-")
    if fragment:
        return fragment[:120]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _patient_id_for_email(email: str) -> str:
    normalized = email.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"patient_email_{digest}"


def _patient_display_name(sender_name: str, sender_email: str) -> str:
    cleaned = sender_name.strip().strip('"')
    if cleaned and "@" not in cleaned:
        return cleaned
    local_part = sender_email.split("@", 1)[0] if sender_email else ""
    local_name = re.sub(r"[._+-]+", " ", local_part).strip()
    return local_name.title() if local_name else sender_email or "Unknown patient"


def _action_dto(item: ClinicActionsItem) -> dict[str, Any]:
    return {
        "actionId": item["action_id"],
        "actionType": item["action_type"],
        "approvedAt": _optional_text(item["approved_at"]),
        "approvedBy": _optional_text(item["approved_by"]),
        "completedAt": _optional_text(item["completed_at"]),
        "completionNote": _optional_text(item["completion_note"]),
        "createdAt": item["created_at"],
        "draftMessage": _optional_text(item["draft_message"]),
        "externalDraftId": _optional_text(item["external_draft_id"]),
        "externalSentMessageId": _optional_text(item["external_sent_message_id"]),
        "finalMessage": _optional_text(item["final_message"]),
        "metadata": item.get("metadata", {}),
        "patientId": _optional_text(item["patient_id"]),
        "patientName": _optional_text(item["patient_name"]),
        "patientRequestId": _optional_text(item.get("patient_request_id", "")),
        "priority": item["priority"],
        "practiceId": item["clinic_id"],
        "sourceMessage": _optional_text(item["source_message"]),
        "sourceMessageId": _optional_text(item["source_message_id"]),
        "sourceProvider": item["source_provider"],
        "sourceSummary": item["source_summary"],
        "sourceThreadId": _optional_text(item["source_thread_id"]),
        "status": item["status"],
        "timeLabel": item["time_label"],
        "updatedAt": item["updated_at"],
    }


def _patient_request_dto(item: ClinicPatientRequestsItem) -> dict[str, Any]:
    return {
        "appointmentType": item["appointment_type"],
        "approvedAt": _optional_text(item["approved_at"]),
        "approvedBy": _optional_text(item["approved_by"]),
        "completedAt": _optional_text(item["completed_at"]),
        "completionNote": _optional_text(item["completion_note"]),
        "createdAt": item["created_at"],
        "draftMessage": _optional_text(item["draft_message"]),
        "durationMinutes": item["duration_minutes"],
        "finalMessage": _optional_text(item["final_message"]),
        "intent": item["intent"],
        "patientEmail": _optional_text(item["patient_email"]),
        "patientEmotionalTone": str(item.get("patient_emotional_tone", "neutral")),
        "patientId": _optional_text(item["patient_id"]),
        "patientName": _optional_text(item["patient_name"]),
        "patientRequestId": item["patient_request_id"],
        "practiceId": item["practice_id"],
        "proposedWindows": item["proposed_windows"],
        "requestConstraints": item["request_constraints"],
        "requestType": str(item.get("request_type", item["intent"])),
        "requiresDoctorReview": bool(item.get("requires_doctor_review", False)),
        "riskLevel": str(item.get("risk_level", "low")),
        "sourceExcerpt": _optional_text(item["source_excerpt"]),
        "sourceMessageId": _optional_text(item["source_message_id"]),
        "sourceProvider": item["source_provider"],
        "sourceSubject": _optional_text(item["source_subject"]),
        "sourceSummary": item["source_summary"],
        "sourceThreadId": _optional_text(item["source_thread_id"]),
        "status": item["status"],
        "suggestedNextAction": str(item.get("suggested_next_action", "Review this request before responding.")),
        "timeLabel": item["time_label"],
        "triageConfidence": float(item["triage_confidence"]),
        "triageCategory": str(item.get("triage_category", item.get("request_type", item["intent"]))),
        "triageReason": item["triage_reason"],
        "urgencyLevel": str(item.get("urgency_level", "routine")),
        "updatedAt": item["updated_at"],
    }


def _patient_timeline_item(item: ClinicPatientRequestsItem) -> dict[str, Any]:
    return {
        "timelineId": f"request-{item['patient_request_id']}",
        "kind": "patient_request",
        "patientRequestId": item["patient_request_id"],
        "actionId": "",
        "title": item["source_summary"],
        "description": item["triage_reason"] or item["source_excerpt"] or item["suggested_next_action"],
        "status": item["status"],
        "requestType": item["request_type"],
        "sourceProvider": item["source_provider"],
        "sourceMessageId": _optional_text(item["source_message_id"]),
        "createdAt": item["created_at"],
        "updatedAt": item["updated_at"],
        "timeLabel": item["time_label"],
    }


def _patient_dto(item: ClinicPatientsItem, timeline: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    timeline_items = timeline or []
    open_request_count = len([entry for entry in timeline_items if entry["status"] not in COMPLETED_STATUSES])
    return {
        "patientId": item["patient_id"],
        "name": item["name"],
        "email": item["email"],
        "phone": item["phone"],
        "lastVisit": item["last_visit"],
        "nextAppt": item["next_appt"],
        "visits": item["visits"],
        "status": item["status"],
        "notes": item["notes"],
        "requestCount": len(timeline_items),
        "openRequestCount": open_request_count,
        "lastRequestAt": _optional_text(timeline_items[0]["createdAt"]) if timeline_items else None,
        "timeline": timeline_items,
    }


def _schedule_event_dto(item: ClinicScheduleItem) -> dict[str, Any]:
    return {
        "eventId": item["event_id"],
        "appointmentType": item["appointment_type"],
        "endTime": item["end_time"],
        "externalCalendarId": _optional_text(item["external_calendar_id"]),
        "externalEventId": _optional_text(item["external_event_id"]),
        "lastSyncedAt": _optional_text(item["last_synced_at"]),
        "patientId": _optional_text(item["patient_id"]),
        "patientName": item["patient_name"],
        "sourceProvider": item["source_provider"],
        "startTime": item["start_time"],
        "status": item["status"],
    }


def _integration_dto(item: ClinicIntegrationsItem) -> dict[str, Any]:
    scopes = item["required_scopes"]
    return {
        "integrationId": item["integration_id"],
        "provider": item["provider"],
        "status": item["status"],
        "accountEmail": _optional_text(item["account_email"]),
        "calendarId": _optional_text(item["calendar_id"]),
        "lastSyncAt": _optional_text(item["last_sync_at"]),
        "lastError": _optional_text(item["last_error"]),
        "requiredScopes": [str(scope) for scope in scopes],
        "writeMode": item["write_mode"],
        "connectedAt": _optional_text(item["connected_at"]),
    }


def _list_action_items() -> list[ClinicActionsItem]:
    items = query_clinic_actions(_clinic_id(), scan_index_forward=True, consistent_read=True)
    if items:
        return items
    gmail_integration = get_clinic_integrations(_clinic_id(), "gmail")
    if gmail_integration and gmail_integration["last_sync_at"]:
        return []
    if not _demo_seed_enabled():
        return []
    for item in SEED_ACTIONS:
        put_clinic_actions(cast(ClinicActionsItem, _with_current_practice(item)))
    return [cast(ClinicActionsItem, _with_current_practice(item)) for item in SEED_ACTIONS]


def _list_patient_request_items() -> list[ClinicPatientRequestsItem]:
    return query_clinic_patient_requests(_practice_id(), scan_index_forward=True, consistent_read=True)


def _list_patient_items() -> list[ClinicPatientsItem]:
    items = query_clinic_patients(_clinic_id(), scan_index_forward=True, consistent_read=True)
    if items:
        return items
    if not _demo_seed_enabled():
        return []
    for item in SEED_PATIENTS:
        put_clinic_patients(cast(ClinicPatientsItem, _with_current_practice(item)))
    return [cast(ClinicPatientsItem, _with_current_practice(item)) for item in SEED_PATIENTS]


def _list_schedule_items() -> list[ClinicScheduleItem]:
    items = query_clinic_schedule(_clinic_id(), scan_index_forward=True, consistent_read=True)
    if items:
        return items
    calendar_integration = get_clinic_integrations(_clinic_id(), "google_calendar")
    if calendar_integration and calendar_integration["last_sync_at"]:
        return []
    if not _demo_seed_enabled():
        return []
    for item in SEED_SCHEDULE:
        put_clinic_schedule(cast(ClinicScheduleItem, _with_current_practice(item)))
    return [cast(ClinicScheduleItem, _with_current_practice(item)) for item in SEED_SCHEDULE]


def _list_setting_items() -> list[ClinicSettingsItem]:
    items = query_clinic_settings(_clinic_id(), scan_index_forward=True, consistent_read=True)
    if items:
        return items
    for item in SEED_SETTINGS:
        put_clinic_settings(cast(ClinicSettingsItem, _with_current_practice(item)))
    return [cast(ClinicSettingsItem, _with_current_practice(item)) for item in SEED_SETTINGS]


def _list_integration_items() -> list[ClinicIntegrationsItem]:
    items = query_clinic_integrations(_clinic_id(), scan_index_forward=True, consistent_read=True)
    if items:
        return items
    for item in SEED_INTEGRATIONS:
        put_clinic_integrations(cast(ClinicIntegrationsItem, _with_current_practice(item)))
    return [cast(ClinicIntegrationsItem, _with_current_practice(item)) for item in SEED_INTEGRATIONS]


def _list_actions(include_completed: bool) -> dict[str, Any]:
    items = sorted(_list_action_items(), key=lambda item: item["created_at"], reverse=True)
    if not include_completed:
        items = [item for item in items if item["status"] != "completed"]
    return {"actions": [_action_dto(item) for item in items], "practiceId": _practice_id()}


def _list_patient_requests(include_completed: bool) -> dict[str, Any]:
    items = sorted(_list_patient_request_items(), key=lambda item: item["created_at"], reverse=True)
    if not include_completed:
        items = [item for item in items if item["status"] != "completed"]
    return {"patientRequests": [_patient_request_dto(item) for item in items], "practiceId": _practice_id()}


def _find_action(action_id: str) -> ClinicActionsItem | None:
    item = get_clinic_actions(_clinic_id(), action_id)
    if item is not None:
        return item
    for seed_item in _list_action_items():
        if seed_item["action_id"] == action_id:
            return seed_item
    return None


def _approve_action(action_id: str, approved_by: str, final_message: str | None) -> dict[str, Any]:
    item = _find_action(action_id)
    if item is None:
        return {"error": f"action not found: {action_id}"}

    now = _now()
    final_text = (final_message or item["draft_message"] or item["source_summary"]).strip()
    updated = cast(
        ClinicActionsItem,
        {
            **item,
            "status": "completed",
            "approved_at": now,
            "approved_by": approved_by,
            "completed_at": now,
            "completion_note": COMPLETION_NOTE,
            "final_message": final_text,
            "updated_at": now,
        },
    )
    put_clinic_actions(updated)
    patient_request_id = item.get("patient_request_id", "")
    if patient_request_id:
        patient_request = get_clinic_patient_requests(_practice_id(), patient_request_id)
        if patient_request is not None:
            put_clinic_patient_requests(
                cast(
                    ClinicPatientRequestsItem,
                    {
                        **patient_request,
                        "status": "completed",
                        "approved_at": now,
                        "approved_by": approved_by,
                        "completed_at": now,
                        "completion_note": COMPLETION_NOTE,
                        "final_message": final_text,
                        "updated_at": now,
                    },
                )
            )
    return {
        "action": _action_dto(updated),
        "message": "approval stored; no external action was taken",
    }


def _integration_has_scopes(integration: ClinicIntegrationsItem, required_scopes: list[str]) -> bool:
    granted = {str(scope) for scope in integration["required_scopes"]}
    return all(scope in granted for scope in required_scopes)


def _reply_subject(subject: str) -> str:
    cleaned = subject.strip()
    if not cleaned:
        return "Re: Your message to Dr. Shalini's Clinic"
    if cleaned.lower().startswith("re:"):
        return cleaned
    return f"Re: {cleaned}"


def _gmail_reply_recipient(
    *,
    action: ClinicActionsItem,
    patient_request: ClinicPatientRequestsItem | None,
    headers: dict[str, str],
) -> str:
    candidate = headers.get("reply-to") or headers.get("from") or ""
    _, email_address = parseaddr(candidate)
    if email_address:
        return email_address.strip()
    if patient_request and patient_request["patient_email"]:
        return patient_request["patient_email"].strip()
    return ""


def _gmail_raw_reply(
    *,
    account_email: str,
    recipient: str,
    subject: str,
    body: str,
    original_message_id: str,
    original_references: str,
) -> str:
    message = EmailMessage()
    message["From"] = account_email
    message["To"] = recipient
    message["Subject"] = _reply_subject(subject)
    message["Date"] = formatdate(localtime=True)
    if original_message_id:
        message["In-Reply-To"] = original_message_id
        message["References"] = f"{original_references} {original_message_id}".strip()
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def _gmail_source_headers(client: GoogleWorkspaceHttpClient, action: ClinicActionsItem) -> dict[str, str]:
    source_message_id = action["source_message_id"]
    if not source_message_id:
        return {}
    return _gmail_headers(client.get_gmail_message_metadata(source_message_id))


def _send_gmail_reply_for_action(
    *,
    item: ClinicActionsItem,
    patient_request: ClinicPatientRequestsItem | None,
    final_text: str,
) -> SentGmailReply:
    integration, client = _google_client_for_integration("gmail")
    required_send_scopes = GOOGLE_SCOPES["gmail"]
    if not _integration_has_scopes(integration, required_send_scopes):
        raise RuntimeError("Reconnect Google to grant Gmail send permission before sending.")

    headers = _gmail_source_headers(client, item)
    recipient = _gmail_reply_recipient(action=item, patient_request=patient_request, headers=headers)
    if not recipient:
        raise RuntimeError("Could not determine a patient email address for this Gmail reply.")

    subject = headers.get("subject", "")
    if not subject and patient_request is not None:
        subject = patient_request["source_subject"]
    raw_reply = _gmail_raw_reply(
        account_email=integration["account_email"],
        recipient=recipient,
        subject=subject or item["source_summary"],
        body=final_text,
        original_message_id=headers.get("message-id", ""),
        original_references=headers.get("references", ""),
    )
    send_response = client.send_gmail_message(raw_message=raw_reply, thread_id=item["source_thread_id"] or None)
    sent_message_id = send_response.get("id")
    if not isinstance(sent_message_id, str) or not sent_message_id:
        raise RuntimeError("Gmail did not return a sent message id.")
    return {"sent_message_id": sent_message_id, "recipient": recipient}


def _approve_and_send_gmail(action_id: str, approved_by: str, final_message: str | None) -> dict[str, Any]:
    item = _find_action(action_id)
    if item is None:
        return {"error": f"action not found: {action_id}"}
    if item["source_provider"] != "gmail":
        return {"error": "only Gmail-sourced actions can be sent by Gmail"}
    if item["status"] == "completed":
        return {"error": "action is already completed"}
    if item["external_sent_message_id"]:
        return {"error": "this action already has a Gmail sent message id"}

    final_text = (final_message or item["draft_message"] or item["source_summary"]).strip()
    if not final_text:
        return {"error": "finalMessage is required before sending"}

    patient_request_id = item.get("patient_request_id", "")
    patient_request = (
        get_clinic_patient_requests(_practice_id(), patient_request_id)
        if patient_request_id
        else None
    )

    sent_reply = _send_gmail_reply_for_action(item=item, patient_request=patient_request, final_text=final_text)

    now = _now()
    updated_metadata = {
        **item.get("metadata", {}),
        "external_action": "gmail_send",
        "sent_to": sent_reply["recipient"],
    }
    updated = cast(
        ClinicActionsItem,
        {
            **item,
            "status": "completed",
            "approved_at": now,
            "approved_by": approved_by,
            "completed_at": now,
            "completion_note": GMAIL_SEND_COMPLETION_NOTE,
            "external_sent_message_id": sent_reply["sent_message_id"],
            "final_message": final_text,
            "metadata": updated_metadata,
            "updated_at": now,
        },
    )
    put_clinic_actions(updated)
    if patient_request is not None:
        put_clinic_patient_requests(
            cast(
                ClinicPatientRequestsItem,
                {
                    **patient_request,
                    "status": "completed",
                    "approved_at": now,
                    "approved_by": approved_by,
                    "completed_at": now,
                    "completion_note": GMAIL_SEND_COMPLETION_NOTE,
                    "final_message": final_text,
                    "updated_at": now,
                },
            )
        )
    return {
        "action": _action_dto(updated),
        "externalWrites": 1,
        "message": "email sent via Gmail after explicit approval",
    }


def _patient_request_for_action(item: ClinicActionsItem) -> ClinicPatientRequestsItem | None:
    patient_request_id = item.get("patient_request_id", "")
    return get_clinic_patient_requests(_practice_id(), patient_request_id) if patient_request_id else None


def _booking_candidate_for_action(
    item: ClinicActionsItem,
    patient_request: ClinicPatientRequestsItem | None,
) -> BookingCandidate | None:
    metadata = item.get("metadata", {})
    start_value = metadata.get("booking_candidate_start_at")
    duration_value = metadata.get("booking_candidate_duration_minutes")
    appointment_kind = str(metadata.get("appointment_type") or item["action_type"] or "Appointment")
    duration_minutes = int(duration_value) if isinstance(duration_value, (int, float)) and duration_value > 0 else 0
    if patient_request is not None:
        appointment_kind = patient_request["appointment_type"] or appointment_kind
        duration_minutes = int(patient_request["duration_minutes"])
    if duration_minutes <= 0:
        duration_minutes = 30

    if isinstance(start_value, str) and start_value:
        start_at = _parse_datetime(start_value)
        if start_at is not None:
            end_value = metadata.get("booking_candidate_end_at")
            end_at = _parse_datetime(end_value) if isinstance(end_value, str) else None
            if end_at is None or end_at <= start_at:
                end_at = start_at + timedelta(minutes=duration_minutes)
            available, reason = _local_booking_slot_is_available(start_at, end_at)
            return {
                "start_at": start_at,
                "end_at": end_at,
                "label": _booking_label(start_at, end_at, appointment_kind, duration_minutes),
                "available": available,
                "reason": reason,
            }

    source_text = " ".join(
        part
        for part in (
            item.get("source_summary", ""),
            item.get("source_message", ""),
            patient_request["source_excerpt"] if patient_request is not None else "",
        )
        if part
    )
    return _booking_candidate_from_text(source_text, appointment_kind, duration_minutes)


def _clinic_timezone_name() -> str:
    zone_name = os.environ.get("CLINIC_TIMEZONE", DEFAULT_CLINIC_TIMEZONE).strip() or DEFAULT_CLINIC_TIMEZONE
    try:
        ZoneInfo(zone_name)
        return zone_name
    except ZoneInfoNotFoundError:
        return "UTC"


def _calendar_event_summary(
    *,
    patient_name: str,
    appointment_type: str,
) -> str:
    normalized_patient = patient_name.strip() or "Patient"
    normalized_type = appointment_type.strip() or "Appointment"
    return f"{normalized_type} - {normalized_patient}"


def _calendar_event_payload(
    *,
    action: ClinicActionsItem,
    patient_request: ClinicPatientRequestsItem | None,
    candidate: BookingCandidate,
) -> dict[str, Any]:
    appointment_type = (
        patient_request["appointment_type"]
        if patient_request is not None and patient_request["appointment_type"]
        else str(action.get("metadata", {}).get("appointment_type") or action["action_type"] or "Appointment")
    )
    patient_name = action["patient_name"] or (patient_request["patient_name"] if patient_request is not None else "")
    patient_email = patient_request["patient_email"] if patient_request is not None else ""
    description_lines = [
        "Booked by the clinic assistant after explicit doctor approval.",
        f"Patient request ID: {action.get('patient_request_id', '')}",
    ]
    if patient_email:
        description_lines.append(f"Patient email: {patient_email}")
    if action["source_message_id"]:
        description_lines.append(f"Source Gmail message ID: {action['source_message_id']}")
    return {
        "summary": _calendar_event_summary(patient_name=patient_name, appointment_type=appointment_type),
        "description": "\n".join(description_lines),
        "start": {
            "dateTime": candidate["start_at"].isoformat(),
            "timeZone": _clinic_timezone_name(),
        },
        "end": {
            "dateTime": candidate["end_at"].isoformat(),
            "timeZone": _clinic_timezone_name(),
        },
        "reminders": {"useDefault": True},
    }


def _schedule_item_for_booked_event(
    *,
    event: dict[str, Any],
    calendar_id: str,
    action: ClinicActionsItem,
    patient_request: ClinicPatientRequestsItem | None,
    candidate: BookingCandidate,
    synced_at: str,
) -> ClinicScheduleItem:
    external_event_id = event.get("id")
    external_event_id = external_event_id if isinstance(external_event_id, str) and external_event_id else candidate["start_at"].isoformat()
    raw_etag = event.get("etag")
    appointment_type = (
        patient_request["appointment_type"]
        if patient_request is not None and patient_request["appointment_type"]
        else str(action.get("metadata", {}).get("appointment_type") or action["action_type"] or "Appointment")
    )
    patient_name = action["patient_name"] or (patient_request["patient_name"] if patient_request is not None else "Patient")
    return {
        "clinic_id": _clinic_id(),
        "event_id": f"gcal-{_safe_external_fragment(external_event_id)}",
        "day_key": f"{candidate['start_at']:%a} {candidate['start_at'].day}",
        "day_label": f"{candidate['start_at']:%A} {candidate['start_at'].day} {candidate['start_at']:%b}",
        "day_type": "private",
        "start_time": candidate["start_at"].strftime("%H:%M"),
        "end_time": candidate["end_at"].strftime("%H:%M"),
        "start_at": candidate["start_at"].isoformat(),
        "end_at": candidate["end_at"].isoformat(),
        "external_calendar_id": calendar_id,
        "external_etag": raw_etag if isinstance(raw_etag, str) else "",
        "external_event_id": external_event_id,
        "last_synced_at": synced_at,
        "patient_id": action["patient_id"],
        "patient_name": patient_name,
        "source_provider": "google_calendar",
        "appointment_type": appointment_type,
        "status": "upcoming",
        "sort_order": int(candidate["start_at"].strftime("%H%M")),
    }


def _book_google_calendar_event_for_action(
    *,
    item: ClinicActionsItem,
    patient_request: ClinicPatientRequestsItem | None,
    candidate: BookingCandidate,
) -> tuple[str, int]:
    metadata = item.get("metadata", {})
    existing_event_id = metadata.get("external_calendar_event_id")
    if isinstance(existing_event_id, str) and existing_event_id:
        return existing_event_id, 0

    calendar_integration, calendar_client = _google_client_for_integration("google_calendar")
    required_calendar_scopes = GOOGLE_SCOPES["google_calendar"]
    if not _integration_has_scopes(calendar_integration, required_calendar_scopes):
        raise RuntimeError("Reconnect Google to grant Calendar booking permission before booking.")

    local_available, local_reason = _local_booking_slot_is_available(candidate["start_at"], candidate["end_at"])
    if not local_available:
        raise RuntimeError(local_reason or "The proposed slot is not available.")

    calendar_id = calendar_integration["calendar_id"] or "primary"
    google_available, google_reason = _google_calendar_slot_is_available(
        client=calendar_client,
        calendar_id=calendar_id,
        start_at=candidate["start_at"],
        end_at=candidate["end_at"],
    )
    if not google_available:
        raise RuntimeError(google_reason or "Google Calendar shows that slot as unavailable.")

    event = calendar_client.create_calendar_event(
        calendar_id=calendar_id,
        event=_calendar_event_payload(action=item, patient_request=patient_request, candidate=candidate),
        send_updates="none",
    )
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise RuntimeError("Google Calendar did not return a calendar event id.")

    synced_at = _now()
    put_clinic_schedule(
        _schedule_item_for_booked_event(
            event=event,
            calendar_id=calendar_id,
            action=item,
            patient_request=patient_request,
            candidate=candidate,
            synced_at=synced_at,
        )
    )
    return event_id, 1


def _approve_send_and_book_calendar(action_id: str, approved_by: str, final_message: str | None) -> dict[str, Any]:
    item = _find_action(action_id)
    if item is None:
        return {"error": f"action not found: {action_id}"}
    if item["source_provider"] != "gmail":
        return {"error": "only Gmail-sourced actions can book and send a confirmation"}
    if item["status"] == "completed":
        return {"error": "action is already completed"}
    if item["external_sent_message_id"]:
        return {"error": "this action already has a Gmail sent message id"}

    final_text = (final_message or item["draft_message"] or item["source_summary"]).strip()
    if not final_text:
        return {"error": "finalMessage is required before sending"}

    patient_request = _patient_request_for_action(item)
    candidate = _booking_candidate_for_action(item, patient_request)
    if candidate is None:
        return {"error": "No exact appointment date and time was found in the patient request."}
    if not candidate["available"]:
        return {"error": candidate["reason"] or "The proposed slot is not available."}

    calendar_event_id, calendar_writes = _book_google_calendar_event_for_action(
        item=item,
        patient_request=patient_request,
        candidate=candidate,
    )
    interim_metadata = {
        **item.get("metadata", {}),
        "booking_candidate_start_at": candidate["start_at"].isoformat(),
        "booking_candidate_end_at": candidate["end_at"].isoformat(),
        "booking_candidate_label": candidate["label"],
        "booking_candidate_available": True,
        "external_calendar_event_id": calendar_event_id,
    }
    item = cast(ClinicActionsItem, {**item, "metadata": interim_metadata, "updated_at": _now()})
    put_clinic_actions(item)

    sent_reply = _send_gmail_reply_for_action(item=item, patient_request=patient_request, final_text=final_text)
    now = _now()
    updated_metadata = {
        **interim_metadata,
        "external_action": "gmail_send_calendar_book",
        "sent_to": sent_reply["recipient"],
    }
    updated = cast(
        ClinicActionsItem,
        {
            **item,
            "status": "completed",
            "approved_at": now,
            "approved_by": approved_by,
            "completed_at": now,
            "completion_note": GMAIL_SEND_AND_BOOK_COMPLETION_NOTE,
            "external_sent_message_id": sent_reply["sent_message_id"],
            "final_message": final_text,
            "metadata": updated_metadata,
            "updated_at": now,
        },
    )
    put_clinic_actions(updated)
    if patient_request is not None:
        put_clinic_patient_requests(
            cast(
                ClinicPatientRequestsItem,
                {
                    **patient_request,
                    "status": "completed",
                    "approved_at": now,
                    "approved_by": approved_by,
                    "completed_at": now,
                    "completion_note": GMAIL_SEND_AND_BOOK_COMPLETION_NOTE,
                    "final_message": final_text,
                    "updated_at": now,
                },
            )
        )
    return {
        "action": _action_dto(updated),
        "calendarEventId": calendar_event_id,
        "externalWrites": calendar_writes + 1,
        "message": "appointment booked in Google Calendar and Gmail confirmation sent after explicit approval",
    }


def _list_patients() -> dict[str, Any]:
    items = sorted(_list_patient_items(), key=lambda item: item["name"])
    requests_by_patient_id: dict[str, list[dict[str, Any]]] = {}
    for request in sorted(_list_patient_request_items(), key=lambda item: item["created_at"], reverse=True):
        patient_id = request["patient_id"]
        if not patient_id:
            continue
        requests_by_patient_id.setdefault(patient_id, []).append(_patient_timeline_item(request))
    return {
        "patients": [_patient_dto(item, requests_by_patient_id.get(item["patient_id"], [])) for item in items]
    }


def _schedule_day_date(item: ClinicScheduleItem) -> date | None:
    if item["start_at"]:
        try:
            parsed = datetime.fromisoformat(item["start_at"].replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed.astimezone(_clinic_timezone()).date() if parsed.tzinfo else parsed.date()
    return _parse_schedule_day_label(item["day_label"])


def _schedule_day_shell(day_date: date) -> dict[str, Any]:
    return {
        "dayDate": day_date.isoformat(),
        "dayKey": f"{day_date:%a} {day_date.day}",
        "dayLabel": f"{day_date:%A} {day_date.day} {day_date:%b}",
        "dayType": "private",
        "events": [],
    }


def _list_schedule() -> dict[str, Any]:
    items = sorted(_list_schedule_items(), key=lambda item: (item["start_at"], item["sort_order"], item["start_time"]))
    today = datetime.now(_clinic_timezone()).date()
    window_end = today + timedelta(days=CALENDAR_SYNC_DAYS)
    days_by_date = {
        (today + timedelta(days=offset)).isoformat(): _schedule_day_shell(today + timedelta(days=offset))
        for offset in range(CALENDAR_SYNC_DAYS)
    }

    for item in items:
        item_date = _schedule_day_date(item)
        if item_date is None or item_date < today or item_date >= window_end:
            continue
        day_key = item_date.isoformat()
        if day_key not in days_by_date:
            days_by_date[day_key] = _schedule_day_shell(item_date)
        if item["day_type"] == "nhs":
            days_by_date[day_key]["dayType"] = "nhs"
        cast(list[dict[str, Any]], days_by_date[day_key]["events"]).append(_schedule_event_dto(item))

    return {"days": [days_by_date[key] for key in sorted(days_by_date)]}


def _setting_items(setting_id: str, settings: dict[str, ClinicSettingsItem]) -> list[dict[str, Any]]:
    setting = settings.get(setting_id)
    if setting is None:
        return []
    data = setting["data"]
    if not isinstance(data, dict):
        return []
    items = data.get("items", [])
    return cast(list[dict[str, Any]], items) if isinstance(items, list) else []


def _list_settings() -> dict[str, Any]:
    settings = {item["setting_id"]: item for item in _list_setting_items()}
    return {
        "availabilityRules": _setting_items("availability_rules", settings),
        "appointmentTypes": _setting_items("appointment_types", settings),
        "preferences": _setting_items("preferences", settings),
    }


def _list_integrations() -> dict[str, Any]:
    return {
        "integrations": [_integration_dto(item) for item in _list_integration_items()],
        "safety": {
            "calendarWrites": "requires_explicit_approval",
            "gmailSends": "requires_explicit_approval",
            "tokenStorage": "external_secret_store",
        },
    }


def _decode_google_email(id_token: object) -> str:
    if not isinstance(id_token, str) or id_token.count(".") < 2:
        return ""
    payload = id_token.split(".")[1]
    padded = payload + ("=" * (-len(payload) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        claims = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return ""
    email = claims.get("email") if isinstance(claims, dict) else None
    return email if isinstance(email, str) else ""


def _safe_secret_fragment(value: str) -> str:
    fragment = re.sub(r"[^A-Za-z0-9/_+=.@-]+", "-", value).strip("-")
    return fragment or "unknown-account"


def _store_google_token_secret(account_email: str, token_response: dict[str, Any]) -> str:
    refresh_token = token_response.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RuntimeError("Google did not return a refresh token. Reconnect with consent to enable offline sync.")

    import boto3

    configured_prefix = os.environ.get(
        "GOOGLE_TOKEN_SECRET_PREFIX",
        GOOGLE_TOKEN_SECRET_DEFAULT_ROOT_PREFIX,
    ).strip().strip("/")
    token_secret_prefix = (
        f"{configured_prefix}/{_practice_id()}/clinic_agent/google"
        if configured_prefix
        else f"{_practice_id()}/clinic_agent/google"
    )
    secret_id = f"{token_secret_prefix}/{_safe_secret_fragment(account_email)}"
    secret_payload = json.dumps(
        {
            "provider": "google",
            "account_email": account_email,
            "token_response": token_response,
            "stored_at": _now(),
        },
        sort_keys=True,
    )
    client = boto3.client("secretsmanager")
    try:
        client.create_secret(Name=secret_id, SecretString=secret_payload)
    except client.exceptions.ResourceExistsException:
        client.put_secret_value(SecretId=secret_id, SecretString=secret_payload)
    return secret_id


def _connected_integration(
    *,
    integration_id: str,
    provider: str,
    account_email: str,
    token_secret_id: str,
    scopes: list[str],
    now: str,
) -> ClinicIntegrationsItem:
    return {
        "clinic_id": _clinic_id(),
        "integration_id": integration_id,
        "provider": provider,
        "status": "connected",
        "account_email": account_email,
        "calendar_id": "primary" if integration_id == "google_calendar" else "",
        "calendar_sync_token": "",
        "gmail_history_id": "",
        "required_scopes": scopes,
        "write_mode": "read_source_book_after_approval"
        if integration_id == "google_calendar"
        else "read_inbox_send_after_approval",
        "token_secret_id": token_secret_id,
        "last_sync_at": "",
        "last_error": "",
        "connected_at": now,
        "updated_at": now,
    }


def _record_practice_member(account_email: str, now: str) -> None:
    normalized_email = account_email.strip().lower()
    if not normalized_email:
        return
    member = cast(
        ClinicPracticeMembersItem,
        {
            "practice_id": _practice_id(),
            "member_email": normalized_email,
            "member_id": _practice_member_id(normalized_email),
            "display_name": account_email,
            "role": "owner",
            "status": "active",
            "auth_provider": "google",
            "last_login_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )
    put_clinic_practice_members(member)


def _connect_google_workspace(account_email: str, token_response: dict[str, Any]) -> dict[str, Any]:
    if not account_email:
        account_email = _decode_google_email(token_response.get("id_token"))
    if not account_email:
        account_email = "connected-google-account"
    token_secret_id = _store_google_token_secret(account_email, token_response)
    now = _now()
    calendar_integration = _connected_integration(
        integration_id="google_calendar",
        provider="google_calendar",
        account_email=account_email,
        token_secret_id=token_secret_id,
        scopes=GOOGLE_SCOPES["google_calendar"],
        now=now,
    )
    gmail_integration = _connected_integration(
        integration_id="gmail",
        provider="gmail",
        account_email=account_email,
        token_secret_id=token_secret_id,
        scopes=GOOGLE_SCOPES["gmail"],
        now=now,
    )
    put_clinic_integrations(calendar_integration)
    put_clinic_integrations(gmail_integration)
    _record_practice_member(account_email, now)
    return {
        "message": "Google account connected through Auth.js. Tokens were stored in the configured secret store.",
        "practiceId": _practice_id(),
        "integrations": [_integration_dto(calendar_integration), _integration_dto(gmail_integration)],
    }


def _google_oauth_config() -> tuple[str, str]:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth client ID and secret are required for live Google reads.")
    return client_id, client_secret


def _connected_google_integration(integration_id: str) -> ClinicIntegrationsItem:
    integration = get_clinic_integrations(_clinic_id(), integration_id)
    if integration is None:
        _list_integration_items()
        integration = get_clinic_integrations(_clinic_id(), integration_id)
    if integration is None or not integration["token_secret_id"]:
        raise RuntimeError("Connect Google before reading Calendar or Gmail.")
    return integration


def _load_google_token_payload(secret_id: str) -> dict[str, Any]:
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    secret_string = response.get("SecretString")
    if not isinstance(secret_string, str) or not secret_string:
        raise RuntimeError("Stored Google token secret is empty.")
    parsed = json.loads(secret_string)
    if not isinstance(parsed, dict):
        raise RuntimeError("Stored Google token secret has an unexpected format.")
    return parsed


def _store_google_token_payload(secret_id: str, payload: dict[str, Any]) -> None:
    import boto3

    client = boto3.client("secretsmanager")
    client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(payload, sort_keys=True))


def _google_client_for_integration(integration_id: str) -> tuple[ClinicIntegrationsItem, GoogleWorkspaceHttpClient]:
    integration = _connected_google_integration(integration_id)
    token_payload = _load_google_token_payload(integration["token_secret_id"])
    token_response = token_payload.get("token_response")
    if not isinstance(token_response, dict):
        raise RuntimeError("Stored Google token payload is missing token_response.")

    client_id, client_secret = _google_oauth_config()
    refreshed = refresh_google_access_token(
        token_response=token_response,
        client_id=client_id,
        client_secret=client_secret,
    )
    merged_token_response = {**token_response, **refreshed}
    token_payload["token_response"] = merged_token_response
    token_payload["refreshed_at"] = _now()
    _store_google_token_payload(integration["token_secret_id"], token_payload)

    access_token = merged_token_response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Google access token is missing after refresh.")
    return integration, GoogleWorkspaceHttpClient(access_token)


def _mark_integration_success(integration_id: str, synced_at: str) -> None:
    integration = get_clinic_integrations(_clinic_id(), integration_id)
    if integration is None:
        return
    updated = cast(
        ClinicIntegrationsItem,
        {
            **integration,
            "status": "connected",
            "last_sync_at": synced_at,
            "last_error": "",
            "updated_at": synced_at,
        },
    )
    put_clinic_integrations(updated)


def _mark_integration_failure(integration_id: str, message: str) -> None:
    integration = get_clinic_integrations(_clinic_id(), integration_id)
    if integration is None:
        return
    now = _now()
    updated = cast(
        ClinicIntegrationsItem,
        {
            **integration,
            "status": "error",
            "last_error": _truncate(message, 300),
            "updated_at": now,
        },
    )
    put_clinic_integrations(updated)


def _calendar_sync_window() -> tuple[str, str]:
    zone = _clinic_timezone()
    today = datetime.now(zone).date()
    start = datetime.combine(today, time.min, tzinfo=zone)
    end = start + timedelta(days=CALENDAR_SYNC_DAYS)
    return start.isoformat(), end.isoformat()


def _calendar_edge_datetime(edge: object, fallback: datetime) -> tuple[datetime, str, bool]:
    zone = _clinic_timezone()
    if not isinstance(edge, dict):
        return fallback, "", False

    date_time = edge.get("dateTime")
    if isinstance(date_time, str) and date_time:
        parsed = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
        localized = parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)
        return localized, localized.strftime("%H:%M"), False

    date_value = edge.get("date")
    if isinstance(date_value, str) and date_value:
        parsed_date = date.fromisoformat(date_value)
        localized = datetime.combine(parsed_date, time.min, tzinfo=zone)
        return localized, "All day", True

    return fallback, "", False


def _calendar_event_text(event: dict[str, Any]) -> str:
    parts = []
    for key in ("summary", "description", "location"):
        value = event.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    return " ".join(parts).lower()


def _calendar_appointment_type(event_text: str) -> str:
    if "available" in event_text or "open slot" in event_text or "free" in event_text:
        return "Open slot"
    if "nhs" in event_text:
        return "NHS Duty"
    if "initial" in event_text or "consultation" in event_text:
        return "Initial Consultation"
    if "follow" in event_text or "review" in event_text:
        return "Follow-up"
    if "scan" in event_text or "procedure" in event_text:
        return "Scan / Procedure"
    return "Appointment"


def _calendar_status(event_text: str, start_at: datetime, end_at: datetime, all_day: bool) -> str:
    now = datetime.now(_clinic_timezone())
    if "available" in event_text or "open slot" in event_text or "free" in event_text:
        return "open"
    if "nhs" in event_text:
        return "nhs"
    if all_day:
        return "upcoming" if start_at.date() >= now.date() else "completed"
    if end_at < now:
        return "completed"
    if start_at <= now <= end_at:
        return "in_progress"
    return "upcoming"


def _calendar_event_to_schedule_item(
    event: dict[str, Any],
    *,
    calendar_id: str,
    sort_order: int,
    synced_at: str,
) -> ClinicScheduleItem:
    fallback = datetime.now(_clinic_timezone())
    start_at, start_label, all_day = _calendar_edge_datetime(event.get("start"), fallback)
    end_at, end_label, _ = _calendar_edge_datetime(event.get("end"), start_at)
    raw_external_id = event.get("id")
    external_event_id = raw_external_id if isinstance(raw_external_id, str) and raw_external_id else start_at.isoformat()
    event_text = _calendar_event_text(event)
    raw_summary = event.get("summary")
    summary = _truncate(raw_summary, 120) if isinstance(raw_summary, str) and raw_summary else "Busy"
    raw_etag = event.get("etag")
    return {
        "clinic_id": _clinic_id(),
        "event_id": f"gcal-{_safe_external_fragment(external_event_id)}",
        "day_key": f"{start_at:%a} {start_at.day}",
        "day_label": f"{start_at:%A} {start_at.day} {start_at:%b}",
        "day_type": "nhs" if "nhs" in event_text else "private",
        "start_time": start_label or "All day",
        "end_time": end_label or ("All day" if all_day else start_label),
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "external_calendar_id": calendar_id,
        "external_etag": raw_etag if isinstance(raw_etag, str) else "",
        "external_event_id": external_event_id,
        "last_synced_at": synced_at,
        "patient_id": "",
        "patient_name": summary,
        "source_provider": "google_calendar",
        "appointment_type": _calendar_appointment_type(event_text),
        "status": _calendar_status(event_text, start_at, end_at, all_day),
        "sort_order": sort_order,
    }


def _replace_google_schedule_cache(items: list[ClinicScheduleItem]) -> None:
    for existing in query_clinic_schedule(_clinic_id(), scan_index_forward=True, consistent_read=True):
        if existing["source_provider"] == "google_calendar":
            delete_clinic_schedule(_clinic_id(), existing["event_id"])
    for item in items:
        put_clinic_schedule(item)


def _gmail_headers(message: dict[str, Any]) -> dict[str, str]:
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


def _decode_gmail_body_data(value: object) -> str:
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


def _gmail_payload_text_parts(payload: object) -> tuple[list[str], list[str]]:
    if not isinstance(payload, dict):
        return [], []

    plain_parts: list[str] = []
    html_parts: list[str] = []
    mime_type = str(payload.get("mimeType", "")).lower()
    body = payload.get("body")
    body_data = body.get("data") if isinstance(body, dict) else None
    decoded = _decode_gmail_body_data(body_data)
    if decoded:
        if "html" in mime_type:
            html_parts.append(_html_to_text(decoded))
        else:
            plain_parts.append(decoded)

    raw_parts = payload.get("parts")
    if isinstance(raw_parts, list):
        for part in raw_parts:
            nested_plain, nested_html = _gmail_payload_text_parts(part)
            plain_parts.extend(nested_plain)
            html_parts.extend(nested_html)

    return plain_parts, html_parts


def _gmail_message_text(message: dict[str, Any]) -> str:
    plain_parts, html_parts = _gmail_payload_text_parts(message.get("payload"))
    body_text = "\n".join(part for part in [*plain_parts, *html_parts] if part.strip())
    if body_text.strip():
        return _truncate(body_text, 4000)
    return _truncate(html.unescape(str(message.get("snippet") or "")), 4000)


def _gmail_message_datetime(message: dict[str, Any], headers: dict[str, str]) -> datetime:
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


def _patient_lookup_by_email() -> dict[str, ClinicPatientsItem]:
    return {item["email"].strip().lower(): item for item in _list_patient_items() if item["email"].strip()}


def _patient_item_from_request(item: ClinicPatientRequestsItem) -> ClinicPatientsItem:
    name = item["patient_name"].strip() or item["patient_email"].strip() or "Unknown patient"
    note_source = item["source_summary"].strip() or item["request_type"].replace("_", " ")
    return {
        "clinic_id": _clinic_id(),
        "patient_id": item["patient_id"],
        "name": name,
        "email": item["patient_email"].strip().lower(),
        "phone": "",
        "last_visit": "-",
        "next_appt": "Pending request",
        "visits": 0,
        "status": "new",
        "notes": f"Created from Gmail request. Latest request: {note_source}",
    }


def _ensure_patient_for_request(item: ClinicPatientRequestsItem) -> None:
    if not item["patient_id"] or not item["patient_email"]:
        return
    existing = get_clinic_patients(_clinic_id(), item["patient_id"])
    if existing is not None:
        return
    put_clinic_patients(_patient_item_from_request(item))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_clinic_message(
    *,
    headers: dict[str, str],
    snippet: str,
    patient_by_email: dict[str, ClinicPatientsItem],
) -> bool:
    sender_email = parseaddr(headers.get("from", ""))[1].lower()
    sender_text = headers.get("from", "").lower()
    subject = headers.get("subject", "")
    combined_text = f"{subject} {snippet}".lower()
    if _contains_any(sender_email, NON_PATIENT_SENDER_MARKERS) or _contains_any(
        sender_text,
        NON_PATIENT_SENDER_MARKERS,
    ):
        return False
    if _contains_any(combined_text, NON_PATIENT_TEXT_MARKERS):
        return False

    if sender_email and sender_email in patient_by_email:
        return True

    has_medical_context = _contains_any(combined_text, MEDICAL_PRACTICE_TERMS)
    has_urgent_clinical_context = _contains_any(combined_text, URGENT_CLINICAL_TERMS)
    has_scheduling_intent = _contains_any(combined_text, SCHEDULING_INTENT_TERMS) or _contains_any(
        combined_text,
        BOOKING_PHRASES,
    )
    has_direct_request = DIRECT_PATIENT_REQUEST_PATTERN.search(combined_text) is not None

    if has_urgent_clinical_context and has_direct_request:
        return True
    if has_medical_context and (has_scheduling_intent or has_direct_request):
        return True
    if has_scheduling_intent and has_direct_request:
        return True
    return False


def _infer_gmail_action_type(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if "reschedule" in lowered or "cancel" in lowered or "move" in lowered:
        return "reschedule", "action"
    if "follow-up" in lowered or "follow up" in lowered or "review" in lowered:
        return "reminder", "info"
    if "referral" in lowered or "consultation" in lowered or "appointment" in lowered or "book" in lowered:
        return "enquiry", "new"
    return "enquiry", "new"


def _triage_gmail_request(text: str, *, matched_patient: bool) -> TriageResult:
    lowered = text.lower()
    emotional_tone = "anxious_or_frustrated" if _contains_any(lowered, ANXIOUS_TONE_TERMS) else "neutral"

    if _contains_any(lowered, URGENT_CLINICAL_TERMS):
        return {
            "request_type": "urgent_clinical_concern",
            "urgency_level": "urgent",
            "risk_level": "high",
            "requires_doctor_review": True,
            "suggested_next_action": "Review urgently and follow the clinic escalation protocol before any reply is sent.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.88") if matched_patient else _dynamodb_decimal("0.76"),
            "triage_reason": "Message includes wording associated with potentially urgent OB-GYN symptoms.",
            "action_priority": "urgent",
        }
    if "reschedule" in lowered or "cancel" in lowered or "move" in lowered:
        return {
            "request_type": "reschedule_cancellation",
            "urgency_level": "soon",
            "risk_level": "low",
            "requires_doctor_review": False,
            "suggested_next_action": "Review the draft and confirm the scheduling next step with the patient.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.86"),
            "triage_reason": "Message is about changing an existing appointment.",
            "action_priority": "action",
        }
    if _contains_any(lowered, RESULT_QUERY_TERMS):
        return {
            "request_type": "test_report_result_query",
            "urgency_level": "soon",
            "risk_level": "medium",
            "requires_doctor_review": True,
            "suggested_next_action": "Doctor should review the result context before the clinic replies.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.82"),
            "triage_reason": "Message appears to ask about a test, scan, report, or result.",
            "action_priority": "clinical",
        }
    if _contains_any(lowered, PRESCRIPTION_ADMIN_TERMS):
        return {
            "request_type": "prescription_admin_request",
            "urgency_level": "routine",
            "risk_level": "medium",
            "requires_doctor_review": True,
            "suggested_next_action": "Check the request details and approve the appropriate clinic response.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.80"),
            "triage_reason": "Message appears to request a prescription, letter, form, or referral document.",
            "action_priority": "clinical",
        }
    if _contains_any(lowered, ROUTINE_CLINICAL_TERMS):
        return {
            "request_type": "routine_clinical_question",
            "urgency_level": "soon",
            "risk_level": "medium",
            "requires_doctor_review": True,
            "suggested_next_action": "Doctor should review the clinical context before any reply is sent.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.78") if matched_patient else _dynamodb_decimal("0.68"),
            "triage_reason": "Message contains clinical terms but does not match the urgent escalation list.",
            "action_priority": "clinical",
        }
    if _contains_any(lowered, BILLING_TERMS):
        return {
            "request_type": "billing_payment",
            "urgency_level": "routine",
            "risk_level": "low",
            "requires_doctor_review": False,
            "suggested_next_action": "Review the admin draft or route to billing support.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.84"),
            "triage_reason": "Message appears to be about billing, payment, insurance, or receipts.",
            "action_priority": "admin",
        }
    if _contains_any(lowered, LOGISTICS_TERMS):
        return {
            "request_type": "general_logistics",
            "urgency_level": "routine",
            "risk_level": "low",
            "requires_doctor_review": False,
            "suggested_next_action": "Review the logistics draft before any patient reply is created or sent.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.82"),
            "triage_reason": "Message appears to be about clinic logistics.",
            "action_priority": "admin",
        }
    if _contains_any(lowered, FOLLOW_UP_TERMS):
        return {
            "request_type": "follow_up",
            "urgency_level": "routine",
            "risk_level": "low",
            "requires_doctor_review": False,
            "suggested_next_action": "Review the follow-up draft and decide the next admin step.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.80"),
            "triage_reason": "Message appears to ask about follow-up or next steps.",
            "action_priority": "info",
        }
    return {
        "request_type": "appointment_request",
        "urgency_level": "routine",
        "risk_level": "low",
        "requires_doctor_review": False,
        "suggested_next_action": "Review proposed availability windows and approve the reply text.",
        "patient_emotional_tone": emotional_tone,
        "triage_confidence": _dynamodb_decimal("0.90") if matched_patient else _dynamodb_decimal("0.72"),
        "triage_reason": "Message matched patient scheduling language in Gmail metadata.",
        "action_priority": "new",
    }


def _parse_time_value(value: str) -> time | None:
    normalized = value.strip()
    if not normalized or normalized.lower() == "all day":
        return None
    for pattern in ("%H:%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(normalized.upper(), pattern).time()
        except ValueError:
            continue
    return None


def _ampm_suffix(value: str) -> str:
    match = re.search(r"\b(am|pm)\b", value, flags=re.IGNORECASE)
    return f" {match.group(1).upper()}" if match else ""


def _parse_hours_range(hours: str) -> tuple[time, time] | None:
    parts = re.split(r"\s+-\s+", hours.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    start_text = parts[0]
    end_text = parts[1]
    if not _ampm_suffix(start_text) and _ampm_suffix(end_text):
        start_text = f"{start_text}{_ampm_suffix(end_text)}"
    start = _parse_time_value(start_text)
    end = _parse_time_value(end_text)
    if start is None or end is None or end <= start:
        return None
    return start, end


def _weekday_availability() -> dict[int, tuple[time, time]]:
    settings = {item["setting_id"]: item for item in _list_setting_items()}
    rules = _setting_items("availability_rules", settings)
    availability: dict[int, tuple[time, time]] = {}
    for rule in rules:
        day = str(rule.get("day", "")).strip().lower()
        enabled = bool(rule.get("enabled", False))
        rule_type = str(rule.get("type", "")).strip().lower()
        hours = str(rule.get("hours", "")).strip()
        parsed_hours = _parse_hours_range(hours)
        if not enabled or parsed_hours is None or rule_type == "nhs":
            continue
        weekday = next((index for index, aliases in WEEKDAY_ALIASES.items() if day in aliases), None)
        if weekday is not None:
            availability[weekday] = parsed_hours

    if availability:
        return availability
    default_start, default_end = time(9, 0), time(17, 0)
    return {weekday: (default_start, default_end) for weekday in range(5)}


def _preference_items() -> list[dict[str, Any]]:
    settings = {item["setting_id"]: item for item in _list_setting_items()}
    return _setting_items("preferences", settings)


def _clinic_buffer_minutes() -> int:
    for preference in _preference_items():
        label = str(preference.get("label", "")).strip().lower()
        value = str(preference.get("value", "")).strip()
        if "buffer" not in label:
            continue
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return 0


def _clinic_lunch_window() -> tuple[time, time] | None:
    for preference in _preference_items():
        label = str(preference.get("label", "")).strip().lower()
        value = str(preference.get("value", "")).strip()
        if "lunch" not in label:
            continue
        return _parse_hours_range(value)
    return None


def _request_appointment_details(text: str) -> tuple[str, int]:
    lowered = text.lower()
    if "meet & greet" in lowered or "meet and greet" in lowered or "intro" in lowered or "introductory" in lowered:
        return "Meet & Greet", 15
    if "follow-up" in lowered or "follow up" in lowered or "review" in lowered:
        return "Follow-up", 20
    if (
        any(anchor in lowered for anchor in ("scan", "ultrasound", "test", "procedure"))
        and any(term in lowered for term in ANCHOR_FOLLOW_UP_TERMS)
        and any(term in lowered for term in ("appointment", "consultation", "see dr", "see the doctor"))
    ):
        return "Follow-up", 20
    if "scan" in lowered or "procedure" in lowered:
        return "Scan / Procedure", 30
    if "consultation" in lowered or "referral" in lowered or "appointment" in lowered or "book" in lowered:
        return "Initial Consultation", 45
    return "Appointment", 30


def _empty_slot_constraints() -> SlotConstraints:
    return {
        "preferred_weekdays": set(),
        "earliest_date": None,
        "latest_date": None,
        "earliest_at": None,
        "daily_start": None,
        "daily_end": None,
        "anchor_event": "",
        "anchor_at": None,
        "constraint_summary": "",
        "notes": [],
    }


def _merge_daily_start(current: time | None, candidate: time) -> time:
    return max(current, candidate) if current is not None else candidate


def _merge_daily_end(current: time | None, candidate: time) -> time:
    return min(current, candidate) if current is not None else candidate


def _text_hour_to_time(raw_hour: str, suffix: str) -> time | None:
    try:
        hour = int(raw_hour)
    except ValueError:
        return None
    if hour < 1 or hour > 12:
        return None
    normalized_suffix = suffix.strip().lower()
    if normalized_suffix == "pm" and hour != 12:
        hour += 12
    elif normalized_suffix == "am" and hour == 12:
        hour = 0
    elif not normalized_suffix and 1 <= hour <= 7:
        hour += 12
    return time(hour, 0)


def _weekday_mentions(text: str) -> set[int]:
    weekdays: set[int] = set()
    for weekday, aliases in WEEKDAY_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases):
            weekdays.add(weekday)
    if "weekend" in text:
        weekdays.update({5, 6})
    if "weekday" in text:
        weekdays.update({0, 1, 2, 3, 4})
    return weekdays


def _human_date(value: date) -> str:
    return f"{value:%A} {value.day} {value:%b}"


def _human_time(value: time) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _month_number(raw_month: str) -> int | None:
    return MONTH_ALIASES.get(raw_month.strip().lower().rstrip("."))


def _future_date_for_day_month(day: int, month: int, today: date) -> date | None:
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today - timedelta(days=30):
        try:
            return date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def _future_date_for_day(day: int, today: date) -> date | None:
    try:
        candidate = date(today.year, today.month, day)
    except ValueError:
        return None
    if candidate < today:
        month = today.month + 1
        year = today.year
        if month > 12:
            month = 1
            year += 1
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
    return candidate


def _date_mentions_with_spans(text: str, today: date) -> list[DateMention]:
    mentions: list[DateMention] = []
    day_month_pattern = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_PATTERN})\b")
    month_day_pattern = re.compile(rf"\b({MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
    bare_day_pattern = re.compile(r"\b(?:on|for|scheduled for|the)\s+(\d{1,2})(?:st|nd|rd|th)?\b")

    for match in day_month_pattern.finditer(text):
        month = _month_number(match.group(2))
        if month is None:
            continue
        candidate = _future_date_for_day_month(int(match.group(1)), month, today)
        if candidate is not None:
            mentions.append({"value": candidate, "start": match.start(), "end": match.end()})

    for match in month_day_pattern.finditer(text):
        month = _month_number(match.group(1))
        if month is None:
            continue
        candidate = _future_date_for_day_month(int(match.group(2)), month, today)
        if candidate is not None:
            mentions.append({"value": candidate, "start": match.start(), "end": match.end()})

    if not mentions:
        for match in bare_day_pattern.finditer(text):
            candidate = _future_date_for_day(int(match.group(1)), today)
            if candidate is not None:
                mentions.append({"value": candidate, "start": match.start(), "end": match.end()})

    return mentions


def _date_mentions(text: str, today: date) -> list[date]:
    return [mention["value"] for mention in _date_mentions_with_spans(text, today)]


def _normalized_clock_text(text: str) -> str:
    return re.sub(r"\b(\d{1,2})\.(\d{2})(\s*(?:am|pm)\b)", r"\1:\2\3", text, flags=re.IGNORECASE)


def _time_mentions_with_spans(text: str) -> list[TimeMention]:
    normalized = _normalized_clock_text(text)
    mentions: list[TimeMention] = []
    for match in re.finditer(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", normalized):
        raw_hour = match.group(1)
        raw_minute = match.group(2) or "00"
        parsed = _text_hour_to_time(raw_hour, match.group(3))
        if parsed is not None:
            mentions.append({"value": parsed.replace(minute=int(raw_minute)), "start": match.start(), "end": match.end()})

    for match in re.finditer(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", normalized):
        mentions.append({"value": time(int(match.group(1)), int(match.group(2))), "start": match.start(), "end": match.end()})

    return mentions


def _clock_mentions(text: str) -> list[time]:
    return [mention["value"] for mention in _time_mentions_with_spans(text)]


def _anchor_label(raw_anchor: str) -> str:
    if raw_anchor in {"xray", "x-ray"}:
        return "x-ray"
    return raw_anchor


def _text_implies_anchor_follow_up(text: str, anchor_window: str) -> bool:
    if any(term in anchor_window for term in ANCHOR_FOLLOW_UP_TERMS):
        return True
    return any(re.search(rf"\b{term}\b.{0,100}\b(?:scan|ultrasound|test|procedure|mri|ct|x-?ray)\b", text) for term in ANCHOR_FOLLOW_UP_TERMS)


def _apply_context_anchor_constraints(constraints: SlotConstraints, text: str, today: date, zone: tzinfo) -> None:
    for raw_anchor in CONTEXT_ANCHOR_TERMS:
        anchor_pattern = re.compile(rf"\b{re.escape(raw_anchor)}\b")
        for match in anchor_pattern.finditer(text):
            window_start = max(0, match.start() - 90)
            window_end = min(len(text), match.end() + 120)
            window = text[window_start:window_end]
            if not _text_implies_anchor_follow_up(text, window):
                continue

            date_candidates = _date_mentions(window, today)
            if not date_candidates:
                continue
            anchor_date = date_candidates[0]
            time_candidates = _clock_mentions(window)
            anchor_event = _anchor_label(raw_anchor)
            constraints["anchor_event"] = anchor_event

            if time_candidates:
                anchor_at = datetime.combine(anchor_date, time_candidates[0], tzinfo=zone)
                earliest_at = anchor_at + timedelta(minutes=ANCHOR_START_ONLY_BUFFER_MINUTES)
                constraints["anchor_at"] = anchor_at
                constraints["earliest_at"] = earliest_at
                constraints["earliest_date"] = anchor_date
                constraints["constraint_summary"] = (
                    f"after your {anchor_event} on {_human_date(anchor_date)} at {_human_time(time_candidates[0])}"
                )
                constraints["notes"].append(f"after {anchor_event}")
                return

            earliest_date = anchor_date + timedelta(days=1)
            constraints["anchor_at"] = datetime.combine(anchor_date, time.min, tzinfo=zone)
            constraints["earliest_date"] = earliest_date
            constraints["constraint_summary"] = f"after your {anchor_event} on {_human_date(anchor_date)}"
            constraints["notes"].append(f"after {anchor_event}")
            return


def _slot_constraints_from_text(text: str, appointment_kind: str = "") -> SlotConstraints:
    lowered = text.lower()
    zone = _clinic_timezone()
    today = datetime.now(zone).date()
    constraints = _empty_slot_constraints()
    constraints["preferred_weekdays"] = _weekday_mentions(lowered)

    if "tomorrow" in lowered:
        target_date = today + timedelta(days=1)
        constraints["earliest_date"] = target_date
        constraints["latest_date"] = target_date
    elif "next week" in lowered:
        start_of_next_week = today + timedelta(days=(7 - today.weekday()))
        constraints["earliest_date"] = start_of_next_week
        constraints["latest_date"] = start_of_next_week + timedelta(days=6)
        constraints["notes"].append("next week")
    elif "this week" in lowered:
        constraints["earliest_date"] = today
        constraints["latest_date"] = today + timedelta(days=(6 - today.weekday()))

    if appointment_kind != "Scan / Procedure":
        _apply_context_anchor_constraints(constraints, lowered, today, zone)

    if "morning" in lowered:
        constraints["daily_start"] = _merge_daily_start(constraints["daily_start"], time(9, 0))
        constraints["daily_end"] = _merge_daily_end(constraints["daily_end"], time(12, 0))
        constraints["notes"].append("morning")
    if "afternoon" in lowered:
        constraints["daily_start"] = _merge_daily_start(constraints["daily_start"], time(12, 0))
        constraints["daily_end"] = _merge_daily_end(constraints["daily_end"], time(17, 0))
        constraints["notes"].append("afternoon")
    if "evening" in lowered:
        constraints["daily_start"] = _merge_daily_start(constraints["daily_start"], time(17, 0))
        constraints["daily_end"] = _merge_daily_end(constraints["daily_end"], time(20, 0))
        constraints["notes"].append("evening")
    if "lunchtime" in lowered or "lunch time" in lowered:
        constraints["daily_start"] = _merge_daily_start(constraints["daily_start"], time(12, 0))
        constraints["daily_end"] = _merge_daily_end(constraints["daily_end"], time(14, 0))
        constraints["notes"].append("lunchtime")

    between_match = re.search(r"\bbetween\s+(\d{1,2})(?:\s*(am|pm))?\s+(?:and|to|-)\s+(\d{1,2})(?:\s*(am|pm))?", lowered)
    if between_match:
        start_suffix = between_match.group(2) or between_match.group(4) or ""
        end_suffix = between_match.group(4) or between_match.group(2) or ""
        start_time = _text_hour_to_time(between_match.group(1), start_suffix)
        end_time = _text_hour_to_time(between_match.group(3), end_suffix)
        if start_time is not None and end_time is not None and end_time > start_time:
            constraints["daily_start"] = _merge_daily_start(constraints["daily_start"], start_time)
            constraints["daily_end"] = _merge_daily_end(constraints["daily_end"], end_time)

    for after_match in re.finditer(r"\bafter\s+(\d{1,2})(?:\s*(am|pm))?", lowered):
        start_time = _text_hour_to_time(after_match.group(1), after_match.group(2) or "")
        if start_time is not None:
            constraints["daily_start"] = _merge_daily_start(constraints["daily_start"], start_time)

    for before_match in re.finditer(r"\bbefore\s+(noon|midday|(\d{1,2})(?:\s*(am|pm))?)", lowered):
        if before_match.group(1) in {"noon", "midday"}:
            end_time = time(12, 0)
        else:
            end_time = _text_hour_to_time(before_match.group(2) or "", before_match.group(3) or "")
        if end_time is not None:
            constraints["daily_end"] = _merge_daily_end(constraints["daily_end"], end_time)

    return constraints


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    zone = _clinic_timezone()
    return parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)


def _parse_schedule_day_label(value: str) -> date | None:
    match = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,})\b", value)
    if match is None:
        return None
    day_and_month = f"{match.group(1)} {match.group(2)}"
    current_year = datetime.now(_clinic_timezone()).year
    for pattern in ("%d %b %Y", "%d %B %Y"):
        try:
            candidate = datetime.strptime(f"{day_and_month} {current_year}", pattern).date()
        except ValueError:
            continue
        if candidate < datetime.now(_clinic_timezone()).date() - timedelta(days=30):
            return date(candidate.year + 1, candidate.month, candidate.day)
        return candidate
    return None


def _schedule_item_window(item: ClinicScheduleItem) -> tuple[datetime, datetime] | None:
    start_at = _parse_datetime(item.get("start_at"))
    end_at = _parse_datetime(item.get("end_at"))
    if start_at is not None and end_at is not None and end_at > start_at:
        return start_at, end_at

    schedule_date = _parse_schedule_day_label(item["day_label"])
    start_time = _parse_time_value(item["start_time"])
    end_time = _parse_time_value(item["end_time"])
    if schedule_date is not None and start_time is not None and end_time is not None and end_time > start_time:
        zone = _clinic_timezone()
        return (
            datetime.combine(schedule_date, start_time, tzinfo=zone),
            datetime.combine(schedule_date, end_time, tzinfo=zone),
        )
    return None


def _busy_schedule_windows() -> list[tuple[datetime, datetime]]:
    busy_windows: list[tuple[datetime, datetime]] = []
    for item in _list_schedule_items():
        if item["status"] == "open" or item["appointment_type"].lower() == "open slot":
            continue
        window = _schedule_item_window(item)
        if window is not None:
            busy_windows.append(window)
    return sorted(busy_windows, key=lambda window: window[0])


def _future_date_for_weekday(weekday: int, today: date) -> date:
    days_ahead = (weekday - today.weekday()) % 7
    return today + timedelta(days=days_ahead)


def _window_text(text: str, start: int, end: int, radius: int = 90) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _nearest_date_for_time(
    *,
    date_mentions: list[DateMention],
    time_mention: TimeMention,
    text: str,
    today: date,
) -> date | None:
    close_dates = [
        mention
        for mention in date_mentions
        if abs(mention["start"] - time_mention["start"]) <= 140 or abs(mention["end"] - time_mention["end"]) <= 140
    ]
    if close_dates:
        return min(close_dates, key=lambda mention: abs(mention["start"] - time_mention["start"]))["value"]
    if len(date_mentions) == 1:
        return date_mentions[0]["value"]

    nearby = _window_text(text, time_mention["start"], time_mention["end"], radius=100)
    nearby_weekdays = _weekday_mentions(nearby.lower())
    if len(nearby_weekdays) == 1:
        return _future_date_for_weekday(next(iter(nearby_weekdays)), today)

    all_weekdays = _weekday_mentions(text.lower())
    if len(all_weekdays) == 1:
        return _future_date_for_weekday(next(iter(all_weekdays)), today)
    return None


def _booking_time_score(text: str, time_mention: TimeMention) -> int:
    lowered = text.lower()
    nearby = _window_text(lowered, time_mention["start"], time_mention["end"], radius=90)
    before = lowered[max(0, time_mention["start"] - 55) : time_mention["start"]]
    before_sentence = re.split(r"[.!?\n]", before)[-1]
    score = 0
    if _contains_any(nearby, BOOKING_SELECTION_TERMS):
        score += 4
    if re.search(r"\b(?:can|could|would|please|happy|prefer|preferred|works|suits|available)\b", nearby):
        score += 2
    if _contains_any(nearby, SCHEDULING_INTENT_TERMS):
        score += 2
    anchor_index = max((before_sentence.rfind(term) for term in CONTEXT_ANCHOR_TERMS), default=-1)
    booking_index = max((before_sentence.rfind(term) for term in BOOKING_SELECTION_TERMS), default=-1)
    if anchor_index >= 0 and booking_index < anchor_index:
        score -= 10
    return score


def _booking_start_from_text(text: str) -> datetime | None:
    normalized = _normalized_clock_text(text)
    zone = _clinic_timezone()
    today = datetime.now(zone).date()
    date_mentions = _date_mentions_with_spans(normalized.lower(), today)
    time_mentions = _time_mentions_with_spans(normalized)
    scored_candidates: list[tuple[int, datetime]] = []

    for time_mention in time_mentions:
        candidate_date = _nearest_date_for_time(
            date_mentions=date_mentions,
            time_mention=time_mention,
            text=normalized,
            today=today,
        )
        if candidate_date is None:
            continue
        candidate_start = datetime.combine(candidate_date, time_mention["value"], tzinfo=zone)
        if candidate_start < datetime.now(zone) - timedelta(days=1):
            continue
        score = _booking_time_score(normalized, time_mention)
        if len(date_mentions) == 1:
            score += 1
        if candidate_date in [mention["value"] for mention in date_mentions]:
            score += 1
        scored_candidates.append((score, candidate_start))

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    top_score, top_start = scored_candidates[0]
    if top_score < 1:
        return None
    top_candidates = [candidate for score, candidate in scored_candidates if score == top_score]
    if len(set(top_candidates)) > 1:
        return None
    return top_start


def _overlaps(start_at: datetime, end_at: datetime, other_start_at: datetime, other_end_at: datetime) -> bool:
    return start_at < other_end_at and end_at > other_start_at


def _booking_candidate_from_text(text: str, appointment_kind: str, duration_minutes: int) -> BookingCandidate | None:
    start_at = _booking_start_from_text(text)
    if start_at is None:
        return None
    end_at = start_at + timedelta(minutes=duration_minutes)
    available, reason = _local_booking_slot_is_available(start_at, end_at)
    return {
        "start_at": start_at,
        "end_at": end_at,
        "label": _booking_label(start_at, end_at, appointment_kind, duration_minutes),
        "available": available,
        "reason": reason,
    }


def _booking_label(start_at: datetime, end_at: datetime, appointment_kind: str, duration_minutes: int) -> str:
    return (
        f"{start_at:%A} {start_at.day} {start_at:%b} at {_human_time(start_at.time())} - "
        f"{_human_time(end_at.time())} ({duration_minutes}-minute {appointment_kind})"
    )


def _local_booking_slot_is_available(start_at: datetime, end_at: datetime) -> tuple[bool, str]:
    zone = _clinic_timezone()
    now = datetime.now(zone)
    localized_start = start_at.astimezone(zone)
    localized_end = end_at.astimezone(zone)
    if localized_end <= localized_start:
        return False, "The proposed appointment end time is before the start time."
    if localized_start < now + timedelta(hours=MIN_BOOKING_NOTICE_HOURS):
        return False, "The proposed slot is too soon to book safely."
    if localized_start.date() != localized_end.date():
        return False, "The proposed slot crosses clinic days."

    buffer_delta = timedelta(minutes=_clinic_buffer_minutes())
    for busy_start, busy_end in _busy_schedule_windows():
        buffered_start = busy_start - buffer_delta
        buffered_end = busy_end + buffer_delta
        if _overlaps(localized_start, localized_end, buffered_start, buffered_end):
            return False, "The proposed slot overlaps an appointment already in the local schedule cache."
    return True, ""


def _google_calendar_slot_is_available(
    *,
    client: GoogleWorkspaceHttpClient,
    calendar_id: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[bool, str]:
    events = client.list_calendar_events(
        calendar_id=calendar_id,
        time_min=start_at.isoformat(),
        time_max=end_at.isoformat(),
        max_results=10,
    )
    fallback = datetime.now(_clinic_timezone())
    for event in events:
        if event.get("status") == "cancelled":
            continue
        event_text = _calendar_event_text(event)
        if _calendar_appointment_type(event_text) == "Open slot":
            continue
        event_start, _, _ = _calendar_edge_datetime(event.get("start"), fallback)
        event_end, _, _ = _calendar_edge_datetime(event.get("end"), event_start)
        if _overlaps(start_at, end_at, event_start, event_end):
            summary = event.get("summary")
            event_label = summary if isinstance(summary, str) and summary else "another calendar event"
            return False, f"Google Calendar already has {event_label} during that time."
    return True, ""


def _round_up_to_step(value: datetime, step_minutes: int) -> datetime:
    minute = ((value.minute + step_minutes - 1) // step_minutes) * step_minutes
    rounded = value.replace(second=0, microsecond=0)
    if minute >= 60:
        return rounded.replace(minute=0) + timedelta(hours=1)
    return rounded.replace(minute=minute)


def _slot_label(start_at: datetime, end_at: datetime, appointment_kind: str, duration_minutes: int) -> str:
    start_time = start_at.strftime("%I:%M %p").lstrip("0")
    end_time = end_at.strftime("%I:%M %p").lstrip("0")
    return (
        f"{start_at:%A} {start_at.day} {start_at:%b}, between {start_time} and {end_time} "
        f"({duration_minutes}-minute {appointment_kind})"
    )


def _slot_label_start_at(label: str) -> datetime | None:
    match = re.search(
        r"\b[A-Za-z]+\s+(\d{1,2})\s+([A-Za-z]{3,}),\s+(?:between\s+)?(\d{1,2})(?::(\d{2}))?\s*(AM|PM)",
        label,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    month = _month_number(match.group(2))
    if month is None:
        return None
    today = datetime.now(_clinic_timezone()).date()
    slot_date = _future_date_for_day_month(int(match.group(1)), month, today)
    if slot_date is None:
        return None
    slot_time = _text_hour_to_time(match.group(3), match.group(5))
    if slot_time is None:
        return None
    slot_time = slot_time.replace(minute=int(match.group(4) or "00"))
    return datetime.combine(slot_date, slot_time, tzinfo=_clinic_timezone())


def _filter_slot_labels_by_constraints(slot_labels: list[str], constraints: SlotConstraints) -> list[str]:
    if constraints["earliest_at"] is None and constraints["earliest_date"] is None:
        return slot_labels

    filtered: list[str] = []
    for label in slot_labels:
        slot_start = _slot_label_start_at(label)
        if slot_start is None:
            continue
        if constraints["earliest_at"] is not None and slot_start < constraints["earliest_at"]:
            continue
        if constraints["earliest_date"] is not None and slot_start.date() < constraints["earliest_date"]:
            continue
        filtered.append(label)
    return filtered


def _suggest_free_slot_labels(
    *,
    appointment_kind: str,
    duration_minutes: int,
    constraints: SlotConstraints | None = None,
    limit: int = DEFAULT_SLOT_SUGGESTIONS,
) -> list[str]:
    zone = _clinic_timezone()
    now = datetime.now(zone)
    earliest_start = _round_up_to_step(now + timedelta(hours=MIN_BOOKING_NOTICE_HOURS), SLOT_STEP_MINUTES)
    active_constraints = constraints or _empty_slot_constraints()
    availability = _weekday_availability()
    buffer_delta = timedelta(minutes=_clinic_buffer_minutes())
    lunch_window = _clinic_lunch_window()
    busy_windows = _busy_schedule_windows()
    slots: list[str] = []

    for day_offset in range(SLOT_SEARCH_DAYS):
        current_day = (now + timedelta(days=day_offset)).date()
        if active_constraints["earliest_at"] is not None and current_day < active_constraints["earliest_at"].date():
            continue
        if active_constraints["earliest_date"] is not None and current_day < active_constraints["earliest_date"]:
            continue
        if active_constraints["latest_date"] is not None and current_day > active_constraints["latest_date"]:
            continue
        if (
            active_constraints["preferred_weekdays"]
            and current_day.weekday() not in active_constraints["preferred_weekdays"]
        ):
            continue

        hours = availability.get(current_day.weekday())
        if hours is None:
            continue

        start_time = hours[0]
        end_time = hours[1]
        if active_constraints["daily_start"] is not None:
            start_time = max(start_time, active_constraints["daily_start"])
        if active_constraints["daily_end"] is not None:
            end_time = min(end_time, active_constraints["daily_end"])
        if end_time <= start_time:
            continue

        day_start = datetime.combine(current_day, start_time, tzinfo=zone)
        day_end = datetime.combine(current_day, end_time, tzinfo=zone)
        cursor = max(day_start, earliest_start) if current_day == earliest_start.date() else day_start
        if active_constraints["earliest_at"] is not None and current_day == active_constraints["earliest_at"].date():
            cursor = max(cursor, active_constraints["earliest_at"])
        cursor = _round_up_to_step(cursor, SLOT_STEP_MINUTES)
        day_busy_windows = [
            (max(start_at - buffer_delta, day_start), min(end_at + buffer_delta, day_end))
            for start_at, end_at in busy_windows
            if start_at - buffer_delta < day_end and end_at + buffer_delta > day_start
        ]
        if lunch_window is not None:
            lunch_start = datetime.combine(current_day, lunch_window[0], tzinfo=zone)
            lunch_end = datetime.combine(current_day, lunch_window[1], tzinfo=zone)
            if lunch_start < day_end and lunch_end > day_start:
                day_busy_windows.append((max(lunch_start, day_start), min(lunch_end, day_end)))
        day_busy_windows.sort(key=lambda window: window[0])

        for busy_start, busy_end in [*day_busy_windows, (day_end, day_end)]:
            if cursor + timedelta(minutes=duration_minutes) <= busy_start:
                slots.append(_slot_label(cursor, busy_start, appointment_kind, duration_minutes))
                if len(slots) >= limit:
                    return slots
            if busy_end > cursor:
                cursor = _round_up_to_step(busy_end, SLOT_STEP_MINUTES)

    return slots


def _request_focus_phrase(text: str, appointment_kind: str) -> str:
    lowered = text.lower()
    if "reschedule" in lowered or "move" in lowered:
        return "rescheduling your appointment"
    if "cancel" in lowered:
        return "changing your appointment"
    if appointment_kind == "Meet & Greet":
        return "arranging a meet and greet"
    if appointment_kind == "Initial Consultation":
        if "referral" in lowered or "gp" in lowered:
            return "arranging an initial consultation following your referral"
        return "arranging an initial consultation"
    if appointment_kind == "Follow-up":
        return "booking a follow-up appointment"
    return "booking an appointment"


def _reply_summary_note(summary: str) -> str:
    normalized = summary.strip().lower()
    if not normalized or normalized in {"appointment request", "meet & greet request", "new gmail message"}:
        return ""
    return f" I have noted: {summary}."


def _draft_reply_for_message(
    patient_name: str,
    summary: str,
    *,
    appointment_kind: str,
    slot_labels: list[str],
    request_text: str = "",
    booking_candidate: BookingCandidate | None = None,
    constraints: SlotConstraints | None = None,
    triage: TriageResult | None = None,
) -> str:
    first_name = patient_name.split()[0] if patient_name and patient_name != "Unknown sender" else "there"
    if triage and triage["request_type"] == "urgent_clinical_concern":
        return (
            f"Dear {first_name},\n\n"
            "Thank you for letting us know. I have flagged your message for urgent review by Dr. Shalini and the clinic team.\n\n"
            "If you feel unwell, symptoms are worsening, or you are worried this cannot wait, please follow the clinic's urgent care guidance or seek urgent medical help now.\n\n"
            "Warm regards,\n"
            "Dr. Shalini's Clinic"
        )

    request_focus = _request_focus_phrase(request_text, appointment_kind)
    summary_note = _reply_summary_note(summary)
    if booking_candidate is not None and booking_candidate["available"]:
        return (
            f"Dear {first_name},\n\n"
            f"Thank you for confirming. I can confirm your appointment with Dr. Shalini is booked for "
            f"{booking_candidate['label']}.{summary_note}\n\n"
            "Warm regards,\n"
            "Dr. Shalini's Clinic"
        )

    constraint_summary = constraints["constraint_summary"] if constraints else ""
    if constraint_summary:
        intro = (
            f"Thank you for your message. I understand you would like help with {request_focus} "
            f"{constraint_summary}.{summary_note} "
        )
    else:
        intro = f"Thank you for your message about {request_focus}.{summary_note} "
    if slot_labels:
        formatted_slots = "\n".join(f"- {slot}" for slot in slot_labels)
        return (
            f"Dear {first_name},\n\n"
            f"{intro}"
            "I have checked Dr. Shalini's calendar with that context in mind, and these windows currently look available:\n\n"
            f"{formatted_slots}\n\n"
            "Please let me know what exact time within one of these windows works best, "
            "and Dr. Shalini will confirm the appointment.\n\n"
            "Warm regards,\n"
            "Dr. Shalini's Clinic"
        )

    return (
        f"Dear {first_name},\n\n"
        f"{intro.strip()}\n\n"
        "Dr. Shalini will review this and we will come back to you shortly.\n\n"
        "Warm regards,\n"
        "Dr. Shalini's Clinic"
    )


def _slot_constraints_record(constraints: SlotConstraints) -> dict[str, Any]:
    return {
        "preferred_weekdays": [WEEKDAY_ALIASES[weekday][0] for weekday in sorted(constraints["preferred_weekdays"])],
        "earliest_date": constraints["earliest_date"].isoformat() if constraints["earliest_date"] is not None else "",
        "latest_date": constraints["latest_date"].isoformat() if constraints["latest_date"] is not None else "",
        "earliest_appointment_at": constraints["earliest_at"].isoformat() if constraints["earliest_at"] is not None else "",
        "daily_start": constraints["daily_start"].strftime("%H:%M") if constraints["daily_start"] is not None else "",
        "daily_end": constraints["daily_end"].strftime("%H:%M") if constraints["daily_end"] is not None else "",
        "anchor_event": constraints["anchor_event"],
        "anchor_at": constraints["anchor_at"].isoformat() if constraints["anchor_at"] is not None else "",
        "constraint_summary": constraints["constraint_summary"],
        "notes": list(constraints["notes"]),
    }


def _action_priority_for_intent(intent: str) -> str:
    if intent == "reschedule":
        return "action"
    if intent == "reminder":
        return "info"
    return "new"


def _action_priority_for_request(item: ClinicPatientRequestsItem) -> str:
    if item["urgency_level"] == "urgent" or item["risk_level"] == "high":
        return "urgent"
    if item["requires_doctor_review"]:
        return "clinical"
    if item["request_type"] in {"reschedule_cancellation"}:
        return "action"
    if item["request_type"] in {"billing_payment", "general_logistics"}:
        return "admin"
    return _action_priority_for_intent(item["intent"])


def _patient_request_to_action_item(item: ClinicPatientRequestsItem) -> ClinicActionsItem:
    action_kind = REPLY_REVIEW_ACTION_KIND
    request_constraints = item["request_constraints"]
    return {
        "clinic_id": _clinic_id(),
        "action_id": _request_action_id(item["patient_request_id"], action_kind),
        "action_type": item["request_type"],
        "priority": _action_priority_for_request(item),
        "status": item["status"],
        "patient_id": item["patient_id"],
        "patient_name": item["patient_name"],
        "patient_request_id": item["patient_request_id"],
        "time_label": item["time_label"],
        "source_summary": item["source_summary"],
        "source_message": item["source_excerpt"],
        "draft_message": item["draft_message"],
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": item["final_message"],
        "metadata": {
            "action_kind": action_kind,
            "appointment_type": item["appointment_type"],
            "booking_candidate_available": request_constraints.get("booking_candidate_available", False),
            "booking_candidate_duration_minutes": item["duration_minutes"],
            "booking_candidate_end_at": str(request_constraints.get("booking_candidate_end_at", "")),
            "booking_candidate_label": str(request_constraints.get("booking_candidate_label", "")),
            "booking_candidate_start_at": str(request_constraints.get("booking_candidate_start_at", "")),
            "booking_candidate_unavailable_reason": str(request_constraints.get("booking_candidate_unavailable_reason", "")),
            "patient_emotional_tone": item["patient_emotional_tone"],
            "patient_request_id": item["patient_request_id"],
            "request_constraints": request_constraints,
            "request_type": item["request_type"],
            "constraint_summary": str(request_constraints.get("constraint_summary", "")),
            "requires_doctor_review": item["requires_doctor_review"],
            "risk_level": item["risk_level"],
            "suggested_next_action": item["suggested_next_action"],
            "triage_category": item["triage_category"],
            "triage_confidence": str(item["triage_confidence"]),
            "triage_reason": item["triage_reason"],
            "urgency_level": item["urgency_level"],
        },
        "source_provider": item["source_provider"],
        "source_thread_id": item["source_thread_id"],
        "source_message_id": item["source_message_id"],
        "approved_at": item["approved_at"],
        "approved_by": item["approved_by"],
        "completed_at": item["completed_at"],
        "completion_note": item["completion_note"],
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


def _gmail_message_to_patient_request_item(
    message: dict[str, Any],
    *,
    patient_by_email: dict[str, ClinicPatientsItem],
    synced_at: str,
) -> ClinicPatientRequestsItem | None:
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        return None
    headers = _gmail_headers(message)
    snippet = html.unescape(str(message.get("snippet") or ""))
    message_text = _gmail_message_text(message) or snippet
    if not _is_clinic_message(headers=headers, snippet=f"{snippet} {message_text}", patient_by_email=patient_by_email):
        return None

    sender_name, sender_email = parseaddr(headers.get("from", ""))
    normalized_sender_email = sender_email.strip().lower()
    matched_patient = patient_by_email.get(normalized_sender_email) if normalized_sender_email else None
    patient_name = matched_patient["name"] if matched_patient else _patient_display_name(sender_name, sender_email)
    patient_id = matched_patient["patient_id"] if matched_patient else (_patient_id_for_email(normalized_sender_email) if normalized_sender_email else "")
    subject = headers.get("subject", "").strip()
    summary = _truncate(subject or message_text or snippet or "New Gmail message", 120)
    source_message = _truncate(f"From: {headers.get('from', '')}\nSubject: {subject}\n\n{message_text}".strip(), 1200)
    request_text = f"{subject} {message_text}"
    intent, _ = _infer_gmail_action_type(request_text)
    triage = _triage_gmail_request(request_text, matched_patient=matched_patient is not None)
    appointment_kind, duration_minutes = _request_appointment_details(request_text)
    constraints = _slot_constraints_from_text(request_text, appointment_kind=appointment_kind)
    booking_candidate = (
        None
        if triage["risk_level"] == "high"
        else _booking_candidate_from_text(request_text, appointment_kind, duration_minutes)
    )
    slot_labels = (
        []
        if triage["risk_level"] == "high" or (booking_candidate is not None and booking_candidate["available"])
        else _suggest_free_slot_labels(
            appointment_kind=appointment_kind,
            duration_minutes=duration_minutes,
            constraints=constraints,
        )
    )
    slot_labels = _filter_slot_labels_by_constraints(slot_labels, constraints)
    created_at = _gmail_message_datetime(message, headers)
    thread_id = message.get("threadId")
    localized = created_at.astimezone(_clinic_timezone())
    patient_request_id = f"gmail-{_safe_external_fragment(message_id)}"
    draft_message = _draft_reply_for_message(
        patient_name,
        summary,
        appointment_kind=appointment_kind,
        slot_labels=slot_labels,
        request_text=request_text,
        booking_candidate=booking_candidate,
        constraints=constraints,
        triage=triage,
    )

    return {
        "practice_id": _practice_id(),
        "patient_request_id": patient_request_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "patient_email": normalized_sender_email,
        "time_label": localized.strftime("%I:%M %p").lstrip("0"),
        "source_summary": summary,
        "source_excerpt": source_message,
        "source_subject": subject,
        "draft_message": draft_message,
        "appointment_type": appointment_kind,
        "duration_minutes": duration_minutes,
        "intent": intent,
        "patient_emotional_tone": triage["patient_emotional_tone"],
        "proposed_windows": slot_labels,
        "request_constraints": {
            **_slot_constraints_record(constraints),
            **(
                {
                    "booking_candidate_start_at": booking_candidate["start_at"].isoformat(),
                    "booking_candidate_end_at": booking_candidate["end_at"].isoformat(),
                    "booking_candidate_label": booking_candidate["label"],
                    "booking_candidate_available": booking_candidate["available"],
                    "booking_candidate_unavailable_reason": booking_candidate["reason"],
                }
                if booking_candidate is not None
                else {}
            ),
        },
        "request_type": triage["request_type"],
        "requires_doctor_review": triage["requires_doctor_review"],
        "risk_level": triage["risk_level"],
        "suggested_next_action": triage["suggested_next_action"],
        "triage_category": triage["request_type"],
        "triage_confidence": _dynamodb_decimal(str(triage["triage_confidence"])),
        "triage_reason": triage["triage_reason"],
        "urgency_level": triage["urgency_level"],
        "status": "needs_approval",
        "final_message": "",
        "source_provider": "gmail",
        "source_thread_id": thread_id if isinstance(thread_id, str) else "",
        "source_message_id": message_id,
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "",
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "updated_at": synced_at,
    }


def _merge_patient_request_candidate(
    existing: ClinicPatientRequestsItem | None,
    incoming: ClinicPatientRequestsItem,
) -> ClinicPatientRequestsItem:
    if existing is None:
        return incoming
    existing_data = cast(dict[str, Any], existing)
    merged_data: dict[str, Any] = {**existing_data, **incoming}
    merged = cast(ClinicPatientRequestsItem, merged_data)
    merged["created_at"] = str(existing_data.get("created_at", incoming["created_at"]))
    existing_status = existing_data.get("status")
    if isinstance(existing_status, str) and existing_status and existing_status != "needs_approval":
        merged["status"] = existing_status
    for key in ("approved_at", "approved_by", "completed_at", "completion_note", "final_message"):
        if existing_data.get(key):
            merged_data[key] = existing_data[key]
    return merged


def _merge_action_candidate(existing: ClinicActionsItem | None, incoming: ClinicActionsItem) -> ClinicActionsItem:
    if existing is None:
        return incoming
    existing_data = cast(dict[str, Any], existing)
    merged_data: dict[str, Any] = {**existing_data, **incoming}
    existing_metadata = existing_data.get("metadata", {})
    incoming_metadata = incoming["metadata"]
    if isinstance(existing_metadata, dict):
        preserved_external_metadata = {
            str(key): value
            for key, value in existing_metadata.items()
            if str(key).startswith("external_") or key == "sent_to"
        }
        if preserved_external_metadata:
            merged_data["metadata"] = {**incoming_metadata, **preserved_external_metadata}
    merged = cast(ClinicActionsItem, merged_data)
    merged["created_at"] = str(existing_data.get("created_at", incoming["created_at"]))
    existing_status = existing_data.get("status")
    if isinstance(existing_status, str) and existing_status and existing_status != "needs_approval":
        merged["status"] = existing_status
    for key in ("approved_at", "approved_by", "completed_at", "completion_note", "final_message"):
        if existing_data.get(key):
            merged_data[key] = existing_data[key]
    return merged


def _upsert_gmail_request_candidates(items: list[ClinicPatientRequestsItem]) -> list[ClinicActionsItem]:
    action_items: list[ClinicActionsItem] = []
    for item in items:
        existing_request = get_clinic_patient_requests(_practice_id(), item["patient_request_id"])
        request_item = _merge_patient_request_candidate(existing_request, item)
        _ensure_patient_for_request(request_item)
        put_clinic_patient_requests(request_item)

        action_item = _patient_request_to_action_item(request_item)
        existing_action = get_clinic_actions(_clinic_id(), action_item["action_id"])
        merged_action = _merge_action_candidate(existing_action, action_item)
        put_clinic_actions(merged_action)
        action_items.append(merged_action)
    return action_items


def _sync_google_calendar() -> dict[str, Any]:
    try:
        integration, client = _google_client_for_integration("google_calendar")
        calendar_id = integration["calendar_id"] or "primary"
        time_min, time_max = _calendar_sync_window()
        events = [
            event
            for event in client.list_calendar_events(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
                max_results=50,
            )
            if event.get("status") != "cancelled"
        ]
        synced_at = _now()
        schedule_items = [
            _calendar_event_to_schedule_item(event, calendar_id=calendar_id, sort_order=index + 1, synced_at=synced_at)
            for index, event in enumerate(events)
        ]
        _replace_google_schedule_cache(schedule_items)
        _mark_integration_success("google_calendar", synced_at)
        schedule = _list_schedule()
        return {
            "status": "synced",
            "sourceOfTruth": "google_calendar",
            "writeMode": "read_only_cache",
            "externalWrites": 0,
            "eventsRead": len(events),
            "appointmentsCached": len(schedule_items),
            "message": "Calendar read completed. The local schedule cache was refreshed; Google Calendar was not changed.",
            **schedule,
        }
    except (GoogleWorkspaceError, RuntimeError) as exc:
        _mark_integration_failure("google_calendar", str(exc))
        raise RuntimeError(str(exc)) from exc


def _scan_gmail_inbox() -> dict[str, Any]:
    try:
        _, client = _google_client_for_integration("gmail")
        messages = client.list_gmail_message_metadata(query=GMAIL_SCAN_QUERY, max_results=GMAIL_SCAN_MAX_MESSAGES)
        patient_by_email = _patient_lookup_by_email()
        synced_at = _now()
        request_items: list[ClinicPatientRequestsItem] = []
        for message in messages:
            item = _gmail_message_to_patient_request_item(
                message,
                patient_by_email=patient_by_email,
                synced_at=synced_at,
            )
            if item is None:
                continue
            existing_request = get_clinic_patient_requests(_practice_id(), item["patient_request_id"])
            action_id = _request_action_id(item["patient_request_id"], REPLY_REVIEW_ACTION_KIND)
            existing_action = get_clinic_actions(_clinic_id(), action_id)
            if (existing_request and existing_request["status"] in COMPLETED_STATUSES) or (
                existing_action and existing_action["status"] in COMPLETED_STATUSES
            ):
                continue
            request_items.append(item)

        sorted_requests = sorted(request_items, key=lambda item: item["created_at"], reverse=True)
        sorted_actions = _upsert_gmail_request_candidates(sorted_requests)
        _mark_integration_success("gmail", synced_at)
        return {
            "status": "synced",
            "sourceOfTruth": "gmail",
            "writeMode": "read_inbox_prepare_in_app_drafts",
            "externalWrites": 0,
            "messagesScanned": len(messages),
            "proposedActions": len(request_items),
            "practiceId": _practice_id(),
            "message": "Gmail read completed. Patient requests and in-app drafts were prepared; no email was sent or drafted in Gmail.",
            "actions": [_action_dto(item) for item in sorted_actions],
            "patientRequests": [_patient_request_dto(item) for item in sorted_requests],
        }
    except (GoogleWorkspaceError, RuntimeError) as exc:
        _mark_integration_failure("gmail", str(exc))
        raise RuntimeError(str(exc)) from exc


def _handle_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "list_actions"))

    if action == "list_actions":
        return json_response(200, _list_actions(bool(payload.get("includeCompleted", False))))
    if action == "list_patient_requests":
        return json_response(200, _list_patient_requests(bool(payload.get("includeCompleted", False))))
    if action == "approve_action":
        action_id = str(payload.get("actionId", "")).strip()
        if not action_id:
            return json_response(400, {"error": "actionId is required"})
        response = _approve_action(
            action_id,
            str(payload.get("approvedBy") or "Dr. Shalini").strip() or "Dr. Shalini",
            str(payload["finalMessage"]).strip() if isinstance(payload.get("finalMessage"), str) else None,
        )
        if "error" in response:
            return json_response(404, response)
        return json_response(200, response)
    if action == "approve_and_send_gmail":
        action_id = str(payload.get("actionId", "")).strip()
        if not action_id:
            return json_response(400, {"error": "actionId is required"})
        try:
            response = _approve_and_send_gmail(
                action_id,
                str(payload.get("approvedBy") or "Dr. Shalini").strip() or "Dr. Shalini",
                str(payload["finalMessage"]).strip() if isinstance(payload.get("finalMessage"), str) else None,
            )
        except (GoogleWorkspaceError, RuntimeError) as exc:
            return json_response(400, {"error": str(exc)})
        if "error" in response:
            return json_response(400, response)
        return json_response(200, response)
    if action == "approve_send_and_book_calendar":
        action_id = str(payload.get("actionId", "")).strip()
        if not action_id:
            return json_response(400, {"error": "actionId is required"})
        try:
            response = _approve_send_and_book_calendar(
                action_id,
                str(payload.get("approvedBy") or "Dr. Shalini").strip() or "Dr. Shalini",
                str(payload["finalMessage"]).strip() if isinstance(payload.get("finalMessage"), str) else None,
            )
        except (GoogleWorkspaceError, RuntimeError) as exc:
            return json_response(400, {"error": str(exc)})
        if "error" in response:
            return json_response(400, response)
        return json_response(200, response)
    if action == "list_patients":
        return json_response(200, _list_patients())
    if action == "list_schedule":
        return json_response(200, _list_schedule())
    if action == "list_settings":
        return json_response(200, _list_settings())
    if action == "list_integrations":
        return json_response(200, _list_integrations())
    if action == "connect_google_workspace":
        account_email = str(payload.get("accountEmail", "")).strip()
        token_response = payload.get("tokenResponse")
        if not isinstance(token_response, dict):
            return json_response(400, {"error": "tokenResponse is required"})
        try:
            return json_response(200, _connect_google_workspace(account_email, cast(dict[str, Any], token_response)))
        except RuntimeError as exc:
            return json_response(400, {"error": str(exc)})
    if action == "sync_google_calendar":
        try:
            return json_response(200, _sync_google_calendar())
        except RuntimeError as exc:
            return json_response(400, {"error": str(exc)})
    if action == "scan_gmail_inbox":
        try:
            return json_response(200, _scan_gmail_inbox())
        except RuntimeError as exc:
            return json_response(400, {"error": str(exc)})

    return json_response(400, {"error": f"unsupported action: {action}"})


def lambda_handler(event: dict[str, Any] | None, context: object | None = None) -> dict[str, Any]:
    """Route clinic app actions."""
    _ = context
    payload = event or {}
    try:
        actor_email = _verify_actor_assertion(payload)
    except RuntimeError as exc:
        return json_response(401, {"error": str(exc)})
    practice_id = _practice_id_for_actor(actor_email)
    token = _CURRENT_PRACTICE_ID.set(practice_id)
    try:
        return _handle_payload(payload)
    finally:
        _CURRENT_PRACTICE_ID.reset(token)
