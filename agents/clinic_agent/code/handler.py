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
import urllib.error
import urllib.request
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
    ClinicEmailMessagesItem,
    ClinicIntegrationsItem,
    ClinicPatientRequestsItem,
    ClinicPatientsItem,
    ClinicPracticeMembersItem,
    ClinicScheduleItem,
    ClinicSettingsItem,
    delete_clinic_schedule,
    get_clinic_actions,
    get_clinic_email_messages,
    get_clinic_integrations,
    get_clinic_patient_requests,
    get_clinic_patients,
    put_clinic_actions,
    put_clinic_email_messages,
    put_clinic_integrations,
    put_clinic_patient_requests,
    put_clinic_patients,
    put_clinic_practice_members,
    put_clinic_schedule,
    put_clinic_settings,
    query_clinic_actions,
    query_clinic_email_messages,
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
GMAIL_SCAN_QUERY = "in:inbox newer_than:30d -category:promotions -category:social"
GMAIL_SCAN_MAX_MESSAGES = 25
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_CLINIC_LLM_MODEL = "gpt-5.4-nano"
CLINIC_LLM_TIMEOUT_SECONDS = 20
CLINIC_LLM_MAX_EMAIL_CHARS = 5000
DEFAULT_SLOT_SUGGESTIONS = 3
SLOT_SEARCH_DAYS = 14
SLOT_STEP_MINUTES = 30
MIN_BOOKING_NOTICE_HOURS = 2
ACTOR_ASSERTION_TTL_SECONDS = 300
REPLY_REVIEW_ACTION_KIND = "review_reply"
CONFIRM_BOOKING_ACTION_KIND = "confirm_booking"
REVIEW_THREAD_REPLY_ACTION_KIND = "review_thread_reply"
AWAITING_PATIENT_SLOT_SELECTION_STATUS = "awaiting_patient_slot_selection"
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
LLM_REQUEST_TYPES = {
    "appointment_request",
    "appointment_booking_selection",
    "reschedule_cancellation",
    "follow_up",
    "urgent_clinical_concern",
    "routine_clinical_question",
    "test_report_result_query",
    "prescription_admin_request",
    "billing_payment",
    "general_logistics",
    "general_patient_question",
    "non_patient",
}
LLM_URGENCY_LEVELS = {"routine", "soon", "urgent"}
LLM_RISK_LEVELS = {"low", "medium", "high"}
LLM_EMOTIONAL_TONES = {"neutral", "anxious_or_frustrated"}
LLM_ACTION_PRIORITIES = {"urgent", "clinical", "action", "admin", "new", "info"}


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


class LlmClinicReview(TypedDict):
    is_patient_relevant: bool
    request_type: str
    urgency_level: str
    risk_level: str
    requires_doctor_review: bool
    suggested_next_action: str
    patient_emotional_tone: str
    triage_confidence: Decimal
    triage_reason: str
    action_priority: str
    should_offer_availability: bool
    draft_message: str
    ignored_reason: str
    model: str


class LlmClinicReviewOutcome(TypedDict):
    review: LlmClinicReview | None
    status: str
    model: str
    error: str


class LlmDailyBriefingOutcome(TypedDict):
    briefing: str
    status: str
    model: str
    error: str


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


class GmailMessageContext(TypedDict):
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
        "gestation_age": "28+4",
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
        "gestation_age": "12+1",
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
        "gestation_age": "20+6",
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
        "gestation_age": "",
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
        "gestation_age": "",
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
        "gestation_age": "",
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


def _patient_lookup_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def _patient_gestation_age(item: ClinicPatientsItem | None) -> str | None:
    if item is None:
        return None
    value = item.get("gestation_age", "")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _gestation_age_from_text(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""

    compact_match = re.search(r"\b(?P<weeks>[1-4]?\d)\s*(?:\+|w\s*)\s*(?P<days>[0-6])\s*d?\b", normalized, re.I)
    if compact_match:
        weeks = int(compact_match.group("weeks"))
        days = int(compact_match.group("days"))
        if 4 <= weeks <= 45:
            return f"{weeks}+{days}"

    contextual_pattern = re.compile(
        r"\b(?P<weeks>[1-4]?\d)\s*(?:weeks?|wks?|w)"
        r"(?:\s*(?:and)?\s*(?P<days>[0-6])\s*(?:days?|d))?"
        r"\b",
        re.I,
    )
    for match in contextual_pattern.finditer(normalized):
        weeks = int(match.group("weeks"))
        if weeks < 4 or weeks > 45:
            continue
        window = normalized[max(0, match.start() - 40) : min(len(normalized), match.end() + 40)].lower()
        if not any(marker in window for marker in ("pregnan", "gestation", "gestational", "antenatal")):
            continue
        days = int(match.group("days") or 0)
        return f"{weeks}+{days}" if days else f"{weeks} weeks"

    return ""


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
        "gestationAge": _patient_gestation_age(item),
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


def _patient_for_schedule_item(
    item: ClinicScheduleItem,
    patients_by_id: dict[str, ClinicPatientsItem],
    patients_by_name: dict[str, ClinicPatientsItem],
) -> ClinicPatientsItem | None:
    patient_id = item["patient_id"].strip()
    if patient_id and patient_id in patients_by_id:
        return patients_by_id[patient_id]

    schedule_name = _patient_lookup_name(item["patient_name"])
    if not schedule_name:
        return None
    exact_match = patients_by_name.get(schedule_name)
    if exact_match is not None:
        return exact_match
    for patient_name, patient in sorted(patients_by_name.items(), key=lambda entry: len(entry[0]), reverse=True):
        if patient_name and schedule_name.startswith(f"{patient_name} "):
            return patient
    return None


def _schedule_event_dto(
    item: ClinicScheduleItem,
    patients_by_id: dict[str, ClinicPatientsItem] | None = None,
    patients_by_name: dict[str, ClinicPatientsItem] | None = None,
) -> dict[str, Any]:
    matched_patient = _patient_for_schedule_item(item, patients_by_id or {}, patients_by_name or {})
    return {
        "eventId": item["event_id"],
        "appointmentType": item["appointment_type"],
        "endTime": item["end_time"],
        "externalCalendarId": _optional_text(item["external_calendar_id"]),
        "externalEventId": _optional_text(item["external_event_id"]),
        "gestationAge": _patient_gestation_age(matched_patient),
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


def _patient_request_update_after_gmail_send(
    *,
    patient_request: ClinicPatientRequestsItem,
    action: ClinicActionsItem,
    approved_by: str,
    final_text: str,
    sent_reply: SentGmailReply,
    now: str,
) -> ClinicPatientRequestsItem:
    metadata = action.get("metadata", {})
    action_kind = str(metadata.get("action_kind", ""))
    has_proposed_windows = bool(patient_request.get("proposed_windows"))
    if action_kind == REPLY_REVIEW_ACTION_KIND and has_proposed_windows:
        return cast(
            ClinicPatientRequestsItem,
            {
                **patient_request,
                "status": AWAITING_PATIENT_SLOT_SELECTION_STATUS,
                "approved_at": now,
                "approved_by": approved_by,
                "completed_at": "",
                "completion_note": "Doctor sent proposed availability; waiting for the patient to choose an exact time.",
                "final_message": final_text,
                "request_constraints": {
                    **patient_request["request_constraints"],
                    "last_sent_gmail_message_id": sent_reply["sent_message_id"],
                    "conversation_stage": "awaiting_patient_slot_selection",
                },
                "updated_at": now,
            },
        )
    return cast(
        ClinicPatientRequestsItem,
        {
            **patient_request,
            "status": "completed",
            "approved_at": now,
            "approved_by": approved_by,
            "completed_at": now,
            "completion_note": GMAIL_SEND_COMPLETION_NOTE,
            "final_message": final_text,
            "request_constraints": {
                **patient_request["request_constraints"],
                "last_sent_gmail_message_id": sent_reply["sent_message_id"],
            },
            "updated_at": now,
        },
    )


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
            _patient_request_update_after_gmail_send(
                patient_request=patient_request,
                action=item,
                approved_by=approved_by,
                final_text=final_text,
                sent_reply=sent_reply,
                now=now,
            )
        )
        put_clinic_email_messages(
            _sent_message_record_item(
                gmail_message_id=sent_reply["sent_message_id"],
                gmail_thread_id=item["source_thread_id"],
                patient_request_id=patient_request_id,
                patient_id=item["patient_id"],
                recipient=sent_reply["recipient"],
                subject=item["source_summary"],
                body=final_text,
                processed_at=now,
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
                    "request_constraints": {
                        **patient_request["request_constraints"],
                        "last_sent_gmail_message_id": sent_reply["sent_message_id"],
                        "external_calendar_event_id": calendar_event_id,
                        "conversation_stage": "booked",
                    },
                    "updated_at": now,
                },
            )
        )
        put_clinic_email_messages(
            _sent_message_record_item(
                gmail_message_id=sent_reply["sent_message_id"],
                gmail_thread_id=item["source_thread_id"],
                patient_request_id=item["patient_request_id"],
                patient_id=item["patient_id"],
                recipient=sent_reply["recipient"],
                subject=item["source_summary"],
                body=final_text,
                processed_at=now,
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
    patient_items = _list_patient_items()
    patients_by_id = {item["patient_id"]: item for item in patient_items if item["patient_id"]}
    patients_by_name = {_patient_lookup_name(item["name"]): item for item in patient_items if item["name"].strip()}
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
        cast(list[dict[str, Any]], days_by_date[day_key]["events"]).append(
            _schedule_event_dto(item, patients_by_id, patients_by_name)
        )

    return {"days": [days_by_date[key] for key in sorted(days_by_date)]}


def _action_metadata_string(item: ClinicActionsItem, key: str) -> str:
    metadata = item.get("metadata", {})
    value = metadata.get(key) if isinstance(metadata, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _action_needs_doctor_review(item: ClinicActionsItem) -> bool:
    metadata = item.get("metadata", {})
    requires_review = metadata.get("requires_doctor_review") if isinstance(metadata, dict) else False
    return (
        requires_review is True
        or _action_metadata_string(item, "risk_level") == "high"
        or _action_metadata_string(item, "urgency_level") == "urgent"
        or item["priority"] in {"urgent", "clinical"}
    )


def _action_attention_rank(item: ClinicActionsItem) -> int:
    if _action_metadata_string(item, "urgency_level") == "urgent" or item["priority"] == "urgent":
        return 0
    if _action_needs_doctor_review(item):
        return 1
    if item["priority"] == "action":
        return 2
    if item["priority"] == "new":
        return 3
    return 4


def _daily_schedule_context(schedule: dict[str, Any], today: date) -> tuple[list[dict[str, Any]], bool]:
    days = schedule.get("days", [])
    if not isinstance(days, list):
        return [], False
    today_key = today.isoformat()
    selected_day = next(
        (
            day
            for day in days
            if isinstance(day, dict) and (day.get("dayDate") == today_key or day.get("dayLabel") == f"{today:%A} {today.day} {today:%b}")
        ),
        None,
    )
    if selected_day is None and days and isinstance(days[0], dict):
        selected_day = days[0]
    if selected_day is None:
        return [], False
    events = selected_day.get("events", [])
    if not isinstance(events, list):
        return [], True
    return [cast(dict[str, Any], event) for event in events if isinstance(event, dict) and event.get("status") != "open"], True


def _daily_attention_summary(open_actions: list[ClinicActionsItem]) -> str:
    urgent = len([item for item in open_actions if _action_attention_rank(item) == 0])
    clinical = len([item for item in open_actions if _action_needs_doctor_review(item)])
    if urgent > 0:
        return f"{urgent} urgent item{'s' if urgent != 1 else ''} should be reviewed first."
    if clinical > 0:
        return f"{clinical} clinical review item{'s' if clinical != 1 else ''} need your attention."
    if open_actions:
        return f"{len(open_actions)} open action{'s' if len(open_actions) != 1 else ''} ready for review."
    return "No open actions waiting for review."


def _daily_briefing_fallback(
    open_actions: list[ClinicActionsItem],
    schedule_events: list[dict[str, Any]],
    *,
    schedule_loaded: bool,
) -> str:
    if not schedule_events:
        appointment_copy = "No appointments are on the calendar today." if schedule_loaded else "Calendar context has not been read yet."
    elif len(schedule_events) == 1:
        appointment_copy = f"One appointment is on the calendar at {schedule_events[0].get('startTime', '')}."
    else:
        appointment_copy = f"{len(schedule_events)} appointments are on the calendar; next at {schedule_events[0].get('startTime', '')}."
    return f"{appointment_copy} {_daily_attention_summary(open_actions)}"


def _daily_briefing_action_payload(item: ClinicActionsItem) -> dict[str, Any]:
    return {
        "patient_name": item["patient_name"],
        "action_type": item["action_type"],
        "priority": item["priority"],
        "time_label": item["time_label"],
        "source_summary": item["source_summary"],
        "urgency_level": _action_metadata_string(item, "urgency_level") or "routine",
        "risk_level": _action_metadata_string(item, "risk_level") or "low",
        "requires_doctor_review": _action_needs_doctor_review(item),
        "suggested_next_action": _action_metadata_string(item, "suggested_next_action"),
    }


def _daily_briefing_schedule_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_time": str(event.get("startTime", "")),
        "end_time": str(event.get("endTime", "")),
        "patient_name": str(event.get("patientName", "")),
        "gestation_age": str(event.get("gestationAge", "") or ""),
        "appointment_type": str(event.get("appointmentType", "")),
        "status": str(event.get("status", "")),
    }


def _daily_briefing() -> dict[str, Any]:
    now = datetime.now(_clinic_timezone())
    action_items = sorted(
        [item for item in _list_action_items() if item["status"] != "completed"],
        key=lambda item: (_action_attention_rank(item), item["created_at"]),
    )
    schedule_events, schedule_loaded = _daily_schedule_context(_list_schedule(), now.date())
    fallback = _daily_briefing_fallback(action_items, schedule_events, schedule_loaded=schedule_loaded)
    metrics = {
        "appointmentCount": len(schedule_events),
        "openActionCount": len(action_items),
        "urgentActionCount": len([item for item in action_items if _action_attention_rank(item) == 0]),
        "clinicalReviewCount": len([item for item in action_items if _action_needs_doctor_review(item)]),
        "scheduleLoaded": 1 if schedule_loaded else 0,
    }
    llm_outcome = _llm_daily_briefing(
        today=now.date(),
        fallback=fallback,
        schedule_events=schedule_events,
        open_actions=action_items,
        metrics=metrics,
    )
    used_llm = llm_outcome["status"] == "used" and bool(llm_outcome["briefing"].strip())
    return {
        "briefing": llm_outcome["briefing"] if used_llm else fallback,
        "dayDate": now.date().isoformat(),
        "generatedAt": now.isoformat(),
        "llmError": _optional_text(llm_outcome["error"]),
        "llmModel": llm_outcome["model"],
        "llmStatus": llm_outcome["status"],
        "metrics": metrics,
        "practiceId": _practice_id(),
        "source": "llm" if used_llm else "fallback",
    }


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


def _gmail_visible_reply_text(value: str) -> str:
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
    return _truncate("\n".join(visible_lines).strip(), 4000)


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


def _normalized_message_signature(sender_email: str, subject: str, message_text: str) -> str:
    normalized_subject = re.sub(r"^(re|fw|fwd):\s*", "", subject.strip().lower())
    normalized_text = re.sub(r"\s+", " ", message_text.strip().lower())
    material = f"{sender_email.strip().lower()}\n{normalized_subject}\n{normalized_text[:2000]}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _gmail_message_context(message: dict[str, Any]) -> GmailMessageContext | None:
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        return None

    headers = _gmail_headers(message)
    snippet = html.unescape(str(message.get("snippet") or ""))
    message_text = _gmail_message_text(message) or snippet
    sender_name, sender_email = parseaddr(headers.get("from", ""))
    normalized_sender_email = sender_email.strip().lower()
    subject = headers.get("subject", "").strip()
    received_at = _gmail_message_datetime(message, headers)
    localized = received_at.astimezone(_clinic_timezone())
    thread_id = message.get("threadId")
    summary = _truncate(subject or message_text or snippet or "New Gmail message", 120)
    source_excerpt = _truncate(f"From: {headers.get('from', '')}\nSubject: {subject}\n\n{message_text}".strip(), 1200)
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
        "message_signature": _normalized_message_signature(normalized_sender_email, subject, message_text),
    }


def _list_email_message_items() -> list[ClinicEmailMessagesItem]:
    return query_clinic_email_messages(_practice_id(), scan_index_forward=True, consistent_read=True)


def _patient_lookup_by_email() -> dict[str, ClinicPatientsItem]:
    return {item["email"].strip().lower(): item for item in _list_patient_items() if item["email"].strip()}


def _patient_item_from_request(item: ClinicPatientRequestsItem) -> ClinicPatientsItem:
    name = item["patient_name"].strip() or item["patient_email"].strip() or "Unknown patient"
    note_source = item["source_summary"].strip() or item["request_type"].replace("_", " ")
    gestation_age = _gestation_age_from_text(
        " ".join([item["source_subject"], item["source_summary"], item["source_excerpt"]])
    )
    return {
        "clinic_id": _clinic_id(),
        "patient_id": item["patient_id"],
        "name": name,
        "email": item["patient_email"].strip().lower(),
        "gestation_age": gestation_age,
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
        gestation_age = _gestation_age_from_text(
            " ".join([item["source_subject"], item["source_summary"], item["source_excerpt"]])
        )
        if gestation_age and _patient_gestation_age(existing) is None:
            put_clinic_patients(cast(ClinicPatientsItem, {**existing, "gestation_age": gestation_age}))
        return
    put_clinic_patients(_patient_item_from_request(item))


def _message_record_item(
    context: GmailMessageContext,
    *,
    patient_request_id: str,
    patient_id: str,
    classification: str,
    processed_at: str,
    direction: str = "inbound",
    to_email: str = "",
) -> ClinicEmailMessagesItem:
    return {
        "practice_id": _practice_id(),
        "gmail_message_id": context["gmail_message_id"],
        "gmail_thread_id": context["gmail_thread_id"],
        "message_id_header": context["message_id_header"],
        "in_reply_to": context["in_reply_to"],
        "references": context["references"],
        "message_signature": context["message_signature"],
        "patient_request_id": patient_request_id,
        "patient_id": patient_id,
        "direction": direction,
        "from_email": context["sender_email"],
        "from_name": context["sender_name"],
        "to_email": to_email,
        "subject": context["subject"],
        "body_excerpt": _truncate(context["message_text"], 1200),
        "classification": classification,
        "source_provider": "gmail",
        "received_at": context["received_at"].astimezone(timezone.utc).isoformat(),
        "processed_at": processed_at,
    }


def _sent_message_record_item(
    *,
    gmail_message_id: str,
    gmail_thread_id: str,
    patient_request_id: str,
    patient_id: str,
    recipient: str,
    subject: str,
    body: str,
    processed_at: str,
) -> ClinicEmailMessagesItem:
    context: GmailMessageContext = {
        "gmail_message_id": gmail_message_id,
        "gmail_thread_id": gmail_thread_id,
        "message_id_header": "",
        "in_reply_to": "",
        "references": "",
        "sender_name": "Dr. Shalini's Clinic",
        "sender_email": "",
        "subject": subject,
        "snippet": body,
        "message_text": body,
        "source_excerpt": body,
        "summary": _truncate(subject or body or "Sent Gmail reply", 120),
        "received_at": datetime.now(timezone.utc),
        "time_label": datetime.now(_clinic_timezone()).strftime("%I:%M %p").lstrip("0"),
        "message_signature": _normalized_message_signature(recipient, subject, body),
    }
    return _message_record_item(
        context,
        patient_request_id=patient_request_id,
        patient_id=patient_id,
        classification="approved_reply_sent",
        processed_at=processed_at,
        direction="outbound",
        to_email=recipient,
    )


def _parse_sort_datetime(value: object) -> datetime:
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _prefer_conversation_request(
    current: ClinicPatientRequestsItem | None,
    candidate: ClinicPatientRequestsItem,
) -> ClinicPatientRequestsItem:
    if current is None:
        return candidate
    current_completed = current["status"] in COMPLETED_STATUSES
    candidate_completed = candidate["status"] in COMPLETED_STATUSES
    if current_completed and not candidate_completed:
        return candidate
    if candidate_completed and not current_completed:
        return current
    current_time = _parse_sort_datetime(current.get("updated_at") or current.get("created_at"))
    candidate_time = _parse_sort_datetime(candidate.get("updated_at") or candidate.get("created_at"))
    return candidate if candidate_time >= current_time else current


def _request_indexes(
    requests: list[ClinicPatientRequestsItem],
) -> tuple[dict[str, ClinicPatientRequestsItem], dict[str, ClinicPatientRequestsItem], dict[str, ClinicPatientRequestsItem]]:
    by_id: dict[str, ClinicPatientRequestsItem] = {}
    by_thread: dict[str, ClinicPatientRequestsItem] = {}
    by_source_message: dict[str, ClinicPatientRequestsItem] = {}
    for request in requests:
        by_id[request["patient_request_id"]] = request
        thread_id = request["source_thread_id"].strip()
        if thread_id:
            by_thread[thread_id] = _prefer_conversation_request(by_thread.get(thread_id), request)
        source_message_id = request["source_message_id"].strip()
        if source_message_id:
            by_source_message[source_message_id] = request
    return by_id, by_thread, by_source_message


def _should_reprocess_legacy_message(
    message_record: ClinicEmailMessagesItem,
    requests_by_id: dict[str, ClinicPatientRequestsItem],
) -> bool:
    classification = message_record["classification"]
    if classification not in {"new_request", "thread_reply"}:
        return False
    request = requests_by_id.get(message_record["patient_request_id"])
    if request is None:
        return False
    return request["status"] not in COMPLETED_STATUSES


def _message_indexes(
    messages: list[ClinicEmailMessagesItem],
) -> tuple[dict[str, ClinicEmailMessagesItem], dict[str, ClinicEmailMessagesItem], dict[str, ClinicEmailMessagesItem]]:
    by_gmail_id: dict[str, ClinicEmailMessagesItem] = {}
    by_header_id: dict[str, ClinicEmailMessagesItem] = {}
    by_signature: dict[str, ClinicEmailMessagesItem] = {}
    for message in messages:
        by_gmail_id[message["gmail_message_id"]] = message
        if message["message_id_header"]:
            by_header_id[message["message_id_header"]] = message
        if message["message_signature"]:
            by_signature[message["message_signature"]] = message
    return by_gmail_id, by_header_id, by_signature


def _awaiting_slot_request_for_sender_reply(
    context: GmailMessageContext,
    patient_requests: list[ClinicPatientRequestsItem],
) -> ClinicPatientRequestsItem | None:
    sender_email = context["sender_email"].strip().lower()
    if not sender_email:
        return None
    reply_text = f"{context['subject']} {_gmail_visible_reply_text(context['message_text']) or context['message_text']}"
    matches: list[ClinicPatientRequestsItem] = []
    for request in patient_requests:
        if request["status"] != AWAITING_PATIENT_SLOT_SELECTION_STATUS:
            continue
        if request["patient_email"].strip().lower() != sender_email:
            continue
        if not request["proposed_windows"]:
            continue
        duration_minutes = int(request["duration_minutes"] or 30)
        candidate = _booking_candidate_from_proposed_windows_reply(
            reply_text,
            request["proposed_windows"],
            request["appointment_type"],
            duration_minutes,
        )
        if candidate is not None:
            matches.append(request)
    if len(matches) != 1:
        return None
    return matches[0]


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_scheduling_intent(text: str) -> bool:
    lowered = text.lower()
    if _contains_any(lowered, BOOKING_PHRASES):
        return True
    if _contains_any(
        lowered,
        (
            "appointment",
            "consultation",
            "reschedule",
            "cancel",
            "meet & greet",
            "meet and greet",
            "slot",
            "availability",
            "available",
        ),
    ):
        return True
    return re.search(
        r"\b(?:book|schedule|arrange|reschedule|cancel|move)\b",
        lowered,
    ) is not None


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


def _is_obvious_non_patient_message(*, headers: dict[str, str], snippet: str) -> bool:
    sender_email = parseaddr(headers.get("from", ""))[1].lower()
    sender_text = headers.get("from", "").lower()
    subject = headers.get("subject", "")
    combined_text = f"{subject} {snippet}".lower()
    return (
        _contains_any(sender_email, NON_PATIENT_SENDER_MARKERS)
        or _contains_any(sender_text, NON_PATIENT_SENDER_MARKERS)
        or _contains_any(combined_text, NON_PATIENT_TEXT_MARKERS)
    )


def _clinic_llm_model() -> str:
    return os.environ.get("CLINIC_LLM_MODEL", DEFAULT_CLINIC_LLM_MODEL).strip() or DEFAULT_CLINIC_LLM_MODEL


def _clinic_llm_enabled() -> bool:
    enabled_value = os.environ.get("CLINIC_LLM_ENABLED", "true").strip().lower()
    if enabled_value in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _truncate_for_llm(value: str, *, limit: int = CLINIC_LLM_MAX_EMAIL_CHARS) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}\n\n[Message truncated for triage.]"


def _clinic_llm_response_schema() -> dict[str, Any]:
    return {
        "name": "clinic_gmail_review",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_patient_relevant": {"type": "boolean"},
                "request_type": {
                    "type": "string",
                    "enum": sorted(LLM_REQUEST_TYPES),
                },
                "urgency_level": {
                    "type": "string",
                    "enum": sorted(LLM_URGENCY_LEVELS),
                },
                "risk_level": {
                    "type": "string",
                    "enum": sorted(LLM_RISK_LEVELS),
                },
                "requires_doctor_review": {"type": "boolean"},
                "suggested_next_action": {"type": "string"},
                "patient_emotional_tone": {
                    "type": "string",
                    "enum": sorted(LLM_EMOTIONAL_TONES),
                },
                "triage_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "triage_reason": {"type": "string"},
                "action_priority": {
                    "type": "string",
                    "enum": sorted(LLM_ACTION_PRIORITIES),
                },
                "should_offer_availability": {"type": "boolean"},
                "draft_message": {"type": "string"},
                "ignored_reason": {"type": "string"},
            },
            "required": [
                "is_patient_relevant",
                "request_type",
                "urgency_level",
                "risk_level",
                "requires_doctor_review",
                "suggested_next_action",
                "patient_emotional_tone",
                "triage_confidence",
                "triage_reason",
                "action_priority",
                "should_offer_availability",
                "draft_message",
                "ignored_reason",
            ],
        },
    }


def _clinic_llm_system_prompt() -> str:
    return (
        "You are an inbox triage assistant for a private medical clinic. "
        "Return only JSON that matches the provided schema.\n\n"
        "Your job has three parts: decide whether the Gmail message is relevant "
        "to a patient or prospective patient workflow, classify the request, and "
        "write a warm draft reply for the doctor to review.\n\n"
        "Patient-relevant messages include messages from patients, prospective "
        "patients, carers, referrers, or clinic partners about appointments, "
        "symptoms, test results, prescriptions, fees, clinic logistics, or follow-up. "
        "Irrelevant messages include marketing, newsletters, automated account "
        "alerts, password resets, delivery notices, generic promotions, and "
        "anything unrelated to the medical practice. For irrelevant messages, set "
        "is_patient_relevant=false, request_type=non_patient, draft_message='', and "
        "explain briefly in ignored_reason.\n\n"
        "Request types must be one of: appointment_request, "
        "appointment_booking_selection, reschedule_cancellation, follow_up, "
        "urgent_clinical_concern, routine_clinical_question, "
        "test_report_result_query, prescription_admin_request, billing_payment, "
        "general_logistics, general_patient_question, non_patient.\n\n"
        "Safety rules: do not diagnose, reassure clinically, or give treatment "
        "advice. For clinical questions, acknowledge the message and say Dr. "
        "Shalini will review it. Do not invent appointment times. Use only the "
        "calendar_availability_windows supplied in the user payload. If no windows "
        "are supplied, do not propose any time. If booking_candidate.available is "
        "true, you may write the reply as a booking confirmation, but remember no "
        "email is sent and no calendar event is created until the doctor explicitly "
        "approves in the app. Keep drafts concise, personal to the patient's "
        "message, and in British English. Sign as Dr. Shalini's Clinic."
    )


def _safe_llm_decimal(value: Any, fallback: Decimal) -> Decimal:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    numeric = max(0.0, min(1.0, numeric))
    return cast(Decimal, _dynamodb_decimal(f"{numeric:.2f}"))


def _validated_llm_review(raw_review: Any, *, model: str, fallback: TriageResult) -> LlmClinicReview | None:
    if not isinstance(raw_review, dict):
        return None
    request_type = str(raw_review.get("request_type", fallback["request_type"])).strip()
    if request_type not in LLM_REQUEST_TYPES:
        request_type = fallback["request_type"]
    urgency_level = str(raw_review.get("urgency_level", fallback["urgency_level"])).strip()
    if urgency_level not in LLM_URGENCY_LEVELS:
        urgency_level = fallback["urgency_level"]
    risk_level = str(raw_review.get("risk_level", fallback["risk_level"])).strip()
    if risk_level not in LLM_RISK_LEVELS:
        risk_level = fallback["risk_level"]
    emotional_tone = str(raw_review.get("patient_emotional_tone", fallback["patient_emotional_tone"])).strip()
    if emotional_tone not in LLM_EMOTIONAL_TONES:
        emotional_tone = fallback["patient_emotional_tone"]
    action_priority = str(raw_review.get("action_priority", fallback["action_priority"])).strip()
    if action_priority not in LLM_ACTION_PRIORITIES:
        action_priority = fallback["action_priority"]
    if risk_level == "high":
        urgency_level = "urgent"
        action_priority = "urgent"

    is_patient_relevant = bool(raw_review.get("is_patient_relevant"))
    should_offer_availability = bool(raw_review.get("should_offer_availability"))
    if request_type == "non_patient":
        is_patient_relevant = False
        should_offer_availability = False
    if risk_level == "high":
        should_offer_availability = False

    suggested_next_action = str(raw_review.get("suggested_next_action", "")).strip()
    triage_reason = str(raw_review.get("triage_reason", "")).strip()
    draft_message = str(raw_review.get("draft_message", "")).strip()
    ignored_reason = str(raw_review.get("ignored_reason", "")).strip()
    if is_patient_relevant and not suggested_next_action:
        suggested_next_action = fallback["suggested_next_action"]
    if is_patient_relevant and not triage_reason:
        triage_reason = fallback["triage_reason"]

    return {
        "is_patient_relevant": is_patient_relevant,
        "request_type": request_type,
        "urgency_level": urgency_level,
        "risk_level": risk_level,
        "requires_doctor_review": bool(raw_review.get("requires_doctor_review", fallback["requires_doctor_review"])),
        "suggested_next_action": suggested_next_action,
        "patient_emotional_tone": emotional_tone,
        "triage_confidence": _safe_llm_decimal(raw_review.get("triage_confidence"), fallback["triage_confidence"]),
        "triage_reason": triage_reason,
        "action_priority": action_priority,
        "should_offer_availability": should_offer_availability,
        "draft_message": draft_message,
        "ignored_reason": ignored_reason,
        "model": model,
    }


def _openai_chat_completion_json(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    request = urllib.request.Request(
        os.environ.get("OPENAI_CHAT_COMPLETIONS_URL", OPENAI_CHAT_COMPLETIONS_URL),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=CLINIC_LLM_TIMEOUT_SECONDS) as response:
        response_body = response.read().decode("utf-8")
    parsed_response = json.loads(response_body)
    content = parsed_response["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", part.get("content", ""))) if isinstance(part, dict) else str(part)
            for part in content
        )
    if not isinstance(content, str):
        raise ValueError("OpenAI response content was not text.")
    return cast(dict[str, Any], json.loads(content))


def _daily_briefing_llm_response_schema() -> dict[str, Any]:
    return {
        "name": "clinic_daily_briefing",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "briefing": {"type": "string"},
            },
            "required": ["briefing"],
        },
    }


def _daily_briefing_system_prompt() -> str:
    return (
        "You write the Today Briefing card for Dr. Shalini's private clinic. "
        "Return only JSON matching the provided schema.\n\n"
        "Write one or two calm, doctor-facing sentences, no more than 60 words. "
        "Use British English. Prioritise urgent or clinical review items, then "
        "summarise today's appointments. Mention patient gestation only when it "
        "is supplied in the payload. Do not invent patients, diagnoses, clinical "
        "advice, appointment times, or completed work. Do not mention implementation "
        "details or the word JSON. Remember that emails and calendar updates only "
        "happen after explicit doctor approval."
    )


def _llm_daily_briefing(
    *,
    today: date,
    fallback: str,
    schedule_events: list[dict[str, Any]],
    open_actions: list[ClinicActionsItem],
    metrics: dict[str, int],
) -> LlmDailyBriefingOutcome:
    model = _clinic_llm_model()
    if not _clinic_llm_enabled():
        return {"briefing": "", "status": "disabled", "model": model, "error": ""}

    user_payload = {
        "clinic": "Dr. Shalini's Clinic",
        "day_date": today.isoformat(),
        "metrics": metrics,
        "schedule_events": [_daily_briefing_schedule_payload(event) for event in schedule_events[:10]],
        "schedule_loaded": bool(metrics.get("scheduleLoaded", 0)),
        "open_actions": [_daily_briefing_action_payload(item) for item in open_actions[:8]],
        "deterministic_fallback": fallback,
        "no_external_action_without_doctor_approval": True,
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _daily_briefing_system_prompt()},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": _daily_briefing_llm_response_schema(),
        },
        "max_completion_tokens": 350,
    }
    try:
        raw_briefing = _openai_chat_completion_json(payload)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return {"briefing": "", "status": "error", "model": model, "error": str(exc)[:240]}

    briefing = str(raw_briefing.get("briefing", "")).strip()
    if not briefing:
        return {"briefing": "", "status": "invalid", "model": model, "error": "LLM briefing was empty."}
    return {"briefing": _truncate(briefing, 500), "status": "used", "model": model, "error": ""}


def _llm_review_gmail_message(
    *,
    context: GmailMessageContext,
    patient_name: str,
    patient_email: str,
    request_text: str,
    fallback_triage: TriageResult,
    appointment_kind: str,
    duration_minutes: int,
    constraints: SlotConstraints,
    calendar_availability_windows: list[str],
    booking_candidate: BookingCandidate | None,
    existing_request: ClinicPatientRequestsItem | None,
) -> LlmClinicReviewOutcome:
    model = _clinic_llm_model()
    if not _clinic_llm_enabled():
        return {"review": None, "status": "disabled", "model": model, "error": ""}

    booking_candidate_payload: dict[str, Any] | None = None
    if booking_candidate is not None:
        booking_candidate_payload = {
            "label": booking_candidate["label"],
            "available": booking_candidate["available"],
            "reason": booking_candidate["reason"],
            "start_at": booking_candidate["start_at"].isoformat(),
            "end_at": booking_candidate["end_at"].isoformat(),
        }
    existing_request_payload: dict[str, Any] | None = None
    if existing_request is not None:
        existing_request_payload = {
            "patient_request_id": existing_request["patient_request_id"],
            "status": existing_request["status"],
            "request_type": existing_request["request_type"],
            "source_summary": existing_request["source_summary"],
            "previous_proposed_windows": existing_request["proposed_windows"],
        }

    user_payload = {
        "clinic": "Dr. Shalini's Clinic",
        "patient": {
            "name": patient_name,
            "email": patient_email,
            "matched_existing_request": existing_request is not None,
        },
        "gmail_message": {
            "from": context["sender_name"],
            "subject": context["subject"],
            "snippet": context["snippet"],
            "received_at": context["received_at"].isoformat(),
            "body": _truncate_for_llm(context["message_text"]),
        },
        "deterministic_context": {
            "fallback_request_type": fallback_triage["request_type"],
            "fallback_risk_level": fallback_triage["risk_level"],
            "appointment_kind": appointment_kind,
            "duration_minutes": duration_minutes,
            "constraint_summary": constraints["constraint_summary"],
            "calendar_availability_windows": calendar_availability_windows,
            "booking_candidate": booking_candidate_payload,
            "existing_request": existing_request_payload,
            "no_external_action_without_doctor_approval": True,
        },
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _clinic_llm_system_prompt()},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": _clinic_llm_response_schema(),
        },
        "max_completion_tokens": 1200,
    }
    try:
        raw_review = _openai_chat_completion_json(payload)
        review = _validated_llm_review(raw_review, model=model, fallback=fallback_triage)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return {"review": None, "status": "error", "model": model, "error": str(exc)[:240]}
    if review is None:
        return {"review": None, "status": "invalid", "model": model, "error": "LLM response did not match the expected shape."}
    return {"review": review, "status": "used", "model": model, "error": ""}


def _triage_from_llm_review(review: LlmClinicReview, fallback: TriageResult) -> TriageResult:
    if not review["is_patient_relevant"]:
        return fallback
    return {
        "request_type": review["request_type"],
        "urgency_level": review["urgency_level"],
        "risk_level": review["risk_level"],
        "requires_doctor_review": review["requires_doctor_review"],
        "suggested_next_action": review["suggested_next_action"],
        "patient_emotional_tone": review["patient_emotional_tone"],
        "triage_confidence": review["triage_confidence"],
        "triage_reason": review["triage_reason"],
        "action_priority": review["action_priority"],
    }


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
    has_scheduling_intent = _has_scheduling_intent(lowered)

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
            "requires_doctor_review": not has_scheduling_intent,
            "suggested_next_action": (
                "Review proposed availability windows and approve the reply text."
                if has_scheduling_intent
                else "Review the patient's follow-up question before any reply is sent."
            ),
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.80"),
            "triage_reason": (
                "Message appears to ask for follow-up scheduling."
                if has_scheduling_intent
                else "Message appears to ask about follow-up or next steps, but does not clearly request scheduling."
            ),
            "action_priority": "new" if has_scheduling_intent else "clinical",
        }
    if not has_scheduling_intent:
        return {
            "request_type": "general_patient_question",
            "urgency_level": "routine",
            "risk_level": "medium" if matched_patient else "low",
            "requires_doctor_review": True,
            "suggested_next_action": "Review the patient's question and approve a contextual response.",
            "patient_emotional_tone": emotional_tone,
            "triage_confidence": _dynamodb_decimal("0.74") if matched_patient else _dynamodb_decimal("0.64"),
            "triage_reason": "Message looks patient-related but does not clearly ask to book, reschedule, or choose an appointment slot.",
            "action_priority": "clinical" if matched_patient else "admin",
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


def _append_time_mention(
    mentions: list[TimeMention],
    seen_mentions: set[tuple[int, int, time]],
    *,
    start: int,
    end: int,
    raw_hour: str,
    raw_minute: str = "00",
    suffix: str = "",
) -> None:
    try:
        minute = int(raw_minute)
    except ValueError:
        return
    if minute < 0 or minute > 59:
        return
    parsed = _text_hour_to_time(raw_hour, suffix)
    if parsed is None:
        return
    value = parsed.replace(minute=minute)
    key = (start, end, value)
    if key in seen_mentions:
        return
    mentions.append({"value": value, "start": start, "end": end})
    seen_mentions.add(key)


def _booking_reply_time_mentions_with_spans(text: str) -> list[TimeMention]:
    normalized = _normalized_clock_text(text)
    mentions = _time_mentions_with_spans(normalized)
    seen_mentions = {(mention["start"], mention["end"], mention["value"]) for mention in mentions}

    for match in re.finditer(r"\b(?:at\s+)?(\d{1,2})[:.](\d{2})\b(?!\s*(?:am|pm)\b)", normalized, flags=re.IGNORECASE):
        _append_time_mention(
            mentions,
            seen_mentions,
            start=match.start(),
            end=match.end(),
            raw_hour=match.group(1),
            raw_minute=match.group(2),
        )

    bare_hour_pattern = re.compile(
        r"\b(?:at|for|around|about|take|book|do|prefer|preferred)\s+(\d{1,2})\b(?!\s*(?:[:.]\d|\d))|"
        r"\b(\d{1,2})\b(?!\s*(?:[:.]\d|\d))\s*"
        r"(?:works|suits|is fine|is ok|is okay|would work|would be good|please)\b",
        flags=re.IGNORECASE,
    )
    for match in bare_hour_pattern.finditer(normalized):
        raw_hour = match.group(1) or match.group(2) or ""
        if not raw_hour:
            continue
        try:
            hour = int(raw_hour)
        except ValueError:
            continue
        if hour < 1 or hour > 12:
            continue
        _append_time_mention(
            mentions,
            seen_mentions,
            start=match.start(),
            end=match.end(),
            raw_hour=raw_hour,
        )

    return sorted(mentions, key=lambda mention: mention["start"])


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
    time_mentions = _booking_reply_time_mentions_with_spans(normalized)
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
    visible_reply = _gmail_visible_reply_text(text)
    start_at = _booking_start_from_text(visible_reply) if visible_reply else _booking_start_from_text(text)
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


def _slot_label_window(label: str) -> tuple[datetime, datetime] | None:
    match = re.search(
        r"\b[A-Za-z]+\s+(\d{1,2})\s+([A-Za-z]{3,}),\s+(?:between\s+)?"
        r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s+(?:and|-)\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)",
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
    start_time = _text_hour_to_time(match.group(3), match.group(5))
    end_time = _text_hour_to_time(match.group(6), match.group(8))
    if start_time is None or end_time is None:
        return None
    start_time = start_time.replace(minute=int(match.group(4) or "00"))
    end_time = end_time.replace(minute=int(match.group(7) or "00"))
    start_at = datetime.combine(slot_date, start_time, tzinfo=_clinic_timezone())
    end_at = datetime.combine(slot_date, end_time, tzinfo=_clinic_timezone())
    if end_at <= start_at:
        return None
    return start_at, end_at


def _booking_candidate_from_proposed_windows_reply(
    text: str,
    proposed_windows: list[Any],
    appointment_kind: str,
    duration_minutes: int,
) -> BookingCandidate | None:
    normalized = _normalized_clock_text(_gmail_visible_reply_text(text) or text)
    time_mentions = _booking_reply_time_mentions_with_spans(normalized)
    if not time_mentions:
        return None

    window_candidates = [
        window
        for window in (_slot_label_window(str(label)) for label in proposed_windows)
        if window is not None
    ]
    if not window_candidates:
        return None

    scored_candidates: list[tuple[int, datetime]] = []
    duration_delta = timedelta(minutes=duration_minutes)
    for time_mention in time_mentions:
        score = _booking_time_score(normalized, time_mention)
        if score < 1:
            continue
        for window_start, window_end in window_candidates:
            candidate_start = datetime.combine(window_start.date(), time_mention["value"], tzinfo=_clinic_timezone())
            candidate_end = candidate_start + duration_delta
            if candidate_start < window_start or candidate_end > window_end:
                continue
            scored_candidates.append((score, candidate_start))

    if not scored_candidates:
        return None
    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    top_score = scored_candidates[0][0]
    top_candidates = [candidate for score, candidate in scored_candidates if score == top_score]
    unique_candidates = sorted(set(top_candidates))
    if len(unique_candidates) != 1:
        return None

    start_at = unique_candidates[0]
    end_at = start_at + duration_delta
    available, reason = _local_booking_slot_is_available(start_at, end_at)
    return {
        "start_at": start_at,
        "end_at": end_at,
        "label": _booking_label(start_at, end_at, appointment_kind, duration_minutes),
        "available": available,
        "reason": reason,
    }


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
    if triage and triage["request_type"] in {
        "routine_clinical_question",
        "test_report_result_query",
        "prescription_admin_request",
        "general_patient_question",
    }:
        context_note = _reply_summary_note(summary)
        if triage["request_type"] == "test_report_result_query":
            next_sentence = "Dr. Shalini will review the result context before we reply in detail."
        elif triage["request_type"] == "prescription_admin_request":
            next_sentence = "Dr. Shalini will review the request and we will come back with the appropriate next step."
        else:
            next_sentence = "Dr. Shalini will review your question and we will come back to you shortly."
        return (
            f"Dear {first_name},\n\n"
            f"Thank you for your message.{context_note}\n\n"
            f"{next_sentence}\n\n"
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


def _should_offer_availability_windows(
    *,
    triage: TriageResult,
    request_text: str,
    existing_request: ClinicPatientRequestsItem | None,
    booking_candidate: BookingCandidate | None,
    llm_should_offer_availability: bool | None = None,
) -> bool:
    if existing_request is not None:
        return False
    if triage["risk_level"] == "high":
        return False
    if booking_candidate is not None and booking_candidate["available"]:
        return False
    if triage["request_type"] not in {"appointment_request", "reschedule_cancellation", "follow_up"}:
        return False
    if llm_should_offer_availability is not None:
        return llm_should_offer_availability
    return _has_scheduling_intent(request_text)


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


def _action_kind_for_request(item: ClinicPatientRequestsItem) -> str:
    request_constraints = item["request_constraints"]
    conversation_stage = str(request_constraints.get("conversation_stage", "new_request"))
    if conversation_stage == "patient_selected_slot":
        return CONFIRM_BOOKING_ACTION_KIND
    if conversation_stage == "thread_reply":
        return REVIEW_THREAD_REPLY_ACTION_KIND
    return REPLY_REVIEW_ACTION_KIND


def _action_id_for_request(item: ClinicPatientRequestsItem, action_kind: str) -> str:
    if action_kind == REPLY_REVIEW_ACTION_KIND:
        return _request_action_id(item["patient_request_id"], action_kind)
    source_message_id = item["source_message_id"].strip()
    action_fragment = f"{action_kind}-{source_message_id}" if source_message_id else action_kind
    return _request_action_id(item["patient_request_id"], action_fragment)


def _patient_request_to_action_item(item: ClinicPatientRequestsItem) -> ClinicActionsItem:
    action_kind = _action_kind_for_request(item)
    request_constraints = item["request_constraints"]
    return {
        "clinic_id": _clinic_id(),
        "action_id": _action_id_for_request(item, action_kind),
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
    existing_request: ClinicPatientRequestsItem | None = None,
) -> ClinicPatientRequestsItem | None:
    context = _gmail_message_context(message)
    if context is None:
        return None

    headers = _gmail_headers(message)
    relevance_text = f"{context['snippet']} {context['message_text']}"
    if existing_request is None and _is_obvious_non_patient_message(headers=headers, snippet=relevance_text):
        return None
    rule_clinic_relevant = _is_clinic_message(
        headers=headers,
        snippet=relevance_text,
        patient_by_email=patient_by_email,
    )
    if existing_request is None and not rule_clinic_relevant and not _clinic_llm_enabled():
        return None

    normalized_sender_email = context["sender_email"]
    matched_patient = patient_by_email.get(normalized_sender_email) if normalized_sender_email else None
    if existing_request is not None:
        patient_name = existing_request["patient_name"] or (
            matched_patient["name"] if matched_patient else _patient_display_name(context["sender_name"], normalized_sender_email)
        )
        patient_id = existing_request["patient_id"] or (
            matched_patient["patient_id"] if matched_patient else (_patient_id_for_email(normalized_sender_email) if normalized_sender_email else "")
        )
        patient_email = existing_request["patient_email"] or normalized_sender_email
    else:
        patient_name = matched_patient["name"] if matched_patient else _patient_display_name(context["sender_name"], normalized_sender_email)
        patient_id = matched_patient["patient_id"] if matched_patient else (_patient_id_for_email(normalized_sender_email) if normalized_sender_email else "")
        patient_email = normalized_sender_email

    subject = context["subject"]
    summary = context["summary"]
    visible_message_text = _gmail_visible_reply_text(context["message_text"]) or context["message_text"]
    request_text = f"{subject} {visible_message_text}"
    intent, _ = _infer_gmail_action_type(request_text)
    triage = _triage_gmail_request(request_text, matched_patient=matched_patient is not None)
    detected_appointment_kind, detected_duration_minutes = _request_appointment_details(request_text)
    if existing_request is not None:
        appointment_kind = existing_request["appointment_type"] or detected_appointment_kind
        raw_duration = existing_request["duration_minutes"] or detected_duration_minutes
        duration_minutes = int(raw_duration)
    else:
        appointment_kind = detected_appointment_kind
        duration_minutes = detected_duration_minutes
    constraints = _slot_constraints_from_text(request_text, appointment_kind=appointment_kind)
    booking_candidate = (
        None
        if triage["risk_level"] == "high"
        else _booking_candidate_from_text(request_text, appointment_kind, duration_minutes)
    )
    if existing_request is not None and booking_candidate is None and triage["risk_level"] != "high":
        booking_candidate = _booking_candidate_from_proposed_windows_reply(
            request_text,
            existing_request["proposed_windows"],
            appointment_kind,
            duration_minutes,
        )
    conversation_stage = "new_request"
    if existing_request is not None:
        conversation_stage = "patient_selected_slot" if booking_candidate is not None else "thread_reply"
        if booking_candidate is not None:
            triage = {
                **triage,
                "request_type": "appointment_booking_selection",
                "urgency_level": "soon",
                "risk_level": "low",
                "requires_doctor_review": False,
                "suggested_next_action": "Review the selected slot, then book the appointment and send the confirmation.",
                "triage_confidence": _dynamodb_decimal("0.92"),
                "triage_reason": "Patient replied in an existing request thread with a specific appointment time.",
                "action_priority": "action",
            }

    candidate_slot_labels = (
        _filter_slot_labels_by_constraints(
            _suggest_free_slot_labels(
                appointment_kind=appointment_kind,
                duration_minutes=duration_minutes,
                constraints=constraints,
            ),
            constraints,
        )
        if _clinic_llm_enabled()
        and existing_request is None
        and not (booking_candidate is not None and booking_candidate["available"])
        and triage["risk_level"] != "high"
        else []
    )
    llm_outcome = _llm_review_gmail_message(
        context=context,
        patient_name=patient_name,
        patient_email=patient_email,
        request_text=request_text,
        fallback_triage=triage,
        appointment_kind=appointment_kind,
        duration_minutes=duration_minutes,
        constraints=constraints,
        calendar_availability_windows=candidate_slot_labels,
        booking_candidate=booking_candidate,
        existing_request=existing_request,
    )
    llm_review = llm_outcome["review"]
    if existing_request is None:
        if llm_review is not None:
            if not llm_review["is_patient_relevant"]:
                return None
        elif not rule_clinic_relevant:
            return None
    if llm_review is not None and llm_review["is_patient_relevant"]:
        triage = _triage_from_llm_review(llm_review, triage)
    if existing_request is not None and booking_candidate is not None:
        triage = {
            **triage,
            "request_type": "appointment_booking_selection",
            "urgency_level": "soon",
            "risk_level": "low",
            "requires_doctor_review": False,
            "suggested_next_action": "Review the selected slot, then book the appointment and send the confirmation.",
            "triage_confidence": _dynamodb_decimal("0.92"),
            "triage_reason": "Patient replied in an existing request thread with a specific appointment time.",
            "action_priority": "action",
        }

    llm_should_offer_availability = (
        llm_review["should_offer_availability"] if llm_review is not None and llm_review["is_patient_relevant"] else None
    )
    should_offer_availability = _should_offer_availability_windows(
        triage=triage,
        request_text=request_text,
        existing_request=existing_request,
        booking_candidate=booking_candidate,
        llm_should_offer_availability=llm_should_offer_availability,
    )
    slot_labels = (
        candidate_slot_labels
        if should_offer_availability and candidate_slot_labels
        else (
            _suggest_free_slot_labels(
                appointment_kind=appointment_kind,
                duration_minutes=duration_minutes,
                constraints=constraints,
            )
            if should_offer_availability
            else []
        )
    )
    slot_labels = _filter_slot_labels_by_constraints(slot_labels, constraints)
    llm_draft_message = (
        llm_review["draft_message"].strip()
        if llm_review is not None and llm_review["is_patient_relevant"] and llm_review["draft_message"].strip()
        else ""
    )
    if llm_draft_message and llm_review is not None and llm_review["should_offer_availability"] and not slot_labels:
        llm_draft_message = ""
    if llm_draft_message:
        draft_message = llm_draft_message
    else:
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
    patient_request_id = (
        existing_request["patient_request_id"]
        if existing_request is not None
        else (
            f"gmail-thread-{_safe_external_fragment(context['gmail_thread_id'])}"
            if context["gmail_thread_id"]
            else f"gmail-{_safe_external_fragment(context['gmail_message_id'])}"
        )
    )
    llm_request_metadata = {
        "llm_review_status": llm_outcome["status"],
        "llm_model": llm_outcome["model"],
        "llm_error": llm_outcome["error"],
        "llm_patient_relevant": llm_review["is_patient_relevant"] if llm_review is not None else False,
        "llm_should_offer_availability": (
            llm_review["should_offer_availability"] if llm_review is not None else False
        ),
        "llm_draft_used": bool(llm_draft_message),
        "llm_ignored_reason": llm_review["ignored_reason"] if llm_review is not None else "",
    }

    return {
        "practice_id": _practice_id(),
        "patient_request_id": patient_request_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "patient_email": patient_email,
        "time_label": context["time_label"],
        "source_summary": summary,
        "source_excerpt": context["source_excerpt"],
        "source_subject": subject,
        "draft_message": draft_message,
        "appointment_type": appointment_kind,
        "duration_minutes": duration_minutes,
        "intent": intent,
        "patient_emotional_tone": triage["patient_emotional_tone"],
        "proposed_windows": slot_labels,
        "request_constraints": {
            **_slot_constraints_record(constraints),
            "conversation_stage": conversation_stage,
            "latest_gmail_message_id": context["gmail_message_id"],
            "message_signature": context["message_signature"],
            "previous_patient_request_status": existing_request["status"] if existing_request is not None else "",
            "previous_proposed_windows": existing_request["proposed_windows"] if existing_request is not None else [],
            **llm_request_metadata,
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
        "source_thread_id": context["gmail_thread_id"],
        "source_message_id": context["gmail_message_id"],
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "",
        "created_at": context["received_at"].astimezone(timezone.utc).isoformat(),
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
    conversation_stage = str(incoming["request_constraints"].get("conversation_stage", "new_request"))
    is_thread_continuation = conversation_stage in {"thread_reply", "patient_selected_slot"}
    existing_status = existing_data.get("status")
    if (
        not is_thread_continuation
        and isinstance(existing_status, str)
        and existing_status
        and existing_status != "needs_approval"
    ):
        merged["status"] = existing_status
    if not is_thread_continuation:
        for key in ("approved_at", "approved_by", "completed_at", "completion_note", "final_message"):
            if existing_data.get(key):
                merged_data[key] = existing_data[key]
    if is_thread_continuation and not incoming["proposed_windows"] and existing_data.get("proposed_windows"):
        merged["proposed_windows"] = cast(list[Any], existing_data["proposed_windows"])
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
        email_messages = _list_email_message_items()
        messages_by_id, messages_by_header_id, messages_by_signature = _message_indexes(email_messages)
        patient_requests = _list_patient_request_items()
        requests_by_id, requests_by_thread, requests_by_source_message = _request_indexes(patient_requests)
        synced_at = _now()
        request_items_by_id: dict[str, ClinicPatientRequestsItem] = {}
        message_records: list[ClinicEmailMessagesItem] = []

        message_pairs = [
            (context, message)
            for message in messages
            for context in [_gmail_message_context(message)]
            if context is not None
        ]
        message_contexts = [context for context, _ in message_pairs]
        messages_by_context_id = {context["gmail_message_id"]: message for context, message in message_pairs}

        for context in sorted(message_contexts, key=lambda item: item["received_at"]):
            existing_message_record = messages_by_id.get(context["gmail_message_id"])
            if existing_message_record is not None and not _should_reprocess_legacy_message(
                existing_message_record,
                requests_by_id,
            ):
                continue

            duplicate_record = (
                messages_by_header_id.get(context["message_id_header"]) if context["message_id_header"] else None
            ) or messages_by_signature.get(context["message_signature"])
            if duplicate_record is not None and duplicate_record["gmail_message_id"] != context["gmail_message_id"]:
                duplicate_item = _message_record_item(
                    context,
                    patient_request_id=duplicate_record["patient_request_id"],
                    patient_id=duplicate_record["patient_id"],
                    classification="duplicate",
                    processed_at=synced_at,
                )
                message_records.append(duplicate_item)
                messages_by_id[duplicate_item["gmail_message_id"]] = duplicate_item
                if duplicate_item["message_id_header"]:
                    messages_by_header_id[duplicate_item["message_id_header"]] = duplicate_item
                if duplicate_item["message_signature"]:
                    messages_by_signature[duplicate_item["message_signature"]] = duplicate_item
                continue

            message = messages_by_context_id.get(context["gmail_message_id"])
            if message is None:
                continue
            existing_request = (
                requests_by_thread.get(context["gmail_thread_id"])
                if context["gmail_thread_id"]
                else requests_by_source_message.get(context["gmail_message_id"])
            )
            if existing_request is None:
                existing_request = _awaiting_slot_request_for_sender_reply(context, patient_requests)
            if existing_request is not None:
                existing_updated_at = _parse_sort_datetime(existing_request.get("updated_at"))
                if (
                    context["gmail_message_id"] == existing_request["source_message_id"]
                    or context["received_at"] <= existing_updated_at
                ):
                    historical_item = _message_record_item(
                        context,
                        patient_request_id=existing_request["patient_request_id"],
                        patient_id=existing_request["patient_id"],
                        classification="historical_request_message",
                        processed_at=synced_at,
                    )
                    message_records.append(historical_item)
                    messages_by_id[historical_item["gmail_message_id"]] = historical_item
                    if historical_item["message_id_header"]:
                        messages_by_header_id[historical_item["message_id_header"]] = historical_item
                    if historical_item["message_signature"]:
                        messages_by_signature[historical_item["message_signature"]] = historical_item
                    continue
            item = _gmail_message_to_patient_request_item(
                message,
                patient_by_email=patient_by_email,
                synced_at=synced_at,
                existing_request=existing_request,
            )
            if item is None:
                continue
            request_items_by_id[item["patient_request_id"]] = item
            requests_by_id[item["patient_request_id"]] = item
            if item["source_thread_id"]:
                requests_by_thread[item["source_thread_id"]] = item
            if item["source_message_id"]:
                requests_by_source_message[item["source_message_id"]] = item

            message_record = _message_record_item(
                context,
                patient_request_id=item["patient_request_id"],
                patient_id=item["patient_id"],
                classification=item["request_type"],
                processed_at=synced_at,
            )
            message_records.append(message_record)
            messages_by_id[message_record["gmail_message_id"]] = message_record
            if message_record["message_id_header"]:
                messages_by_header_id[message_record["message_id_header"]] = message_record
            if message_record["message_signature"]:
                messages_by_signature[message_record["message_signature"]] = message_record

        sorted_requests = sorted(request_items_by_id.values(), key=lambda item: item["created_at"], reverse=True)
        sorted_actions = _upsert_gmail_request_candidates(sorted_requests)
        for message_record in message_records:
            if get_clinic_email_messages(_practice_id(), message_record["gmail_message_id"]) is None:
                put_clinic_email_messages(message_record)
        _mark_integration_success("gmail", synced_at)
        return {
            "status": "synced",
            "sourceOfTruth": "gmail",
            "writeMode": "read_inbox_prepare_in_app_drafts",
            "externalWrites": 0,
            "messagesScanned": len(messages),
            "proposedActions": len(sorted_actions),
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
    if action == "get_daily_briefing":
        return json_response(200, _daily_briefing())
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
