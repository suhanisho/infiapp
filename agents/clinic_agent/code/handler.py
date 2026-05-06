"""Clinic assistant Lambda agent.

The MVP is deliberately human-in-the-loop: this agent records proposals,
approvals, and completions, but it does not send email or update calendars.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, TypedDict, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from generated.dynamodb import (
    ClinicActionsItem,
    ClinicIntegrationsItem,
    ClinicPatientsItem,
    ClinicScheduleItem,
    ClinicSettingsItem,
    delete_clinic_actions,
    delete_clinic_schedule,
    get_clinic_actions,
    get_clinic_integrations,
    put_clinic_actions,
    put_clinic_integrations,
    put_clinic_patients,
    put_clinic_schedule,
    put_clinic_settings,
    query_clinic_actions,
    query_clinic_integrations,
    query_clinic_patients,
    query_clinic_schedule,
    query_clinic_settings,
)
from google_workspace import GoogleWorkspaceError, GoogleWorkspaceHttpClient, refresh_google_access_token, required_google_scopes
from response import json_response

CLINIC_ID = "shalini-clinic"
SEED_UPDATED_AT = "2026-05-02T00:00:00+00:00"
COMPLETION_NOTE = "Doctor approved and stored this action. No external email or calendar action was taken by the MVP."
DEFAULT_CLINIC_TIMEZONE = "Europe/London"
CALENDAR_SYNC_DAYS = 14
GMAIL_SCAN_QUERY = (
    "in:inbox newer_than:30d "
    "(appointment OR booking OR book OR consultation OR referral OR meet OR greet OR intro OR reschedule OR cancel OR follow-up)"
)
GMAIL_SCAN_MAX_MESSAGES = 10
DEFAULT_SLOT_SUGGESTIONS = 3
SLOT_SEARCH_DAYS = 14
SLOT_STEP_MINUTES = 30
MIN_BOOKING_NOTICE_HOURS = 2
WEEKDAY_ALIASES = {
    0: ("monday", "mondays", "mon"),
    1: ("tuesday", "tuesdays", "tue", "tues"),
    2: ("wednesday", "wednesdays", "wed"),
    3: ("thursday", "thursdays", "thu", "thur", "thurs"),
    4: ("friday", "fridays", "fri"),
    5: ("saturday", "saturdays", "sat"),
    6: ("sunday", "sundays", "sun"),
}
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
DIRECT_PATIENT_REQUEST_PATTERN = re.compile(
    r"\b(i|i'm|i’d|i'd|my|me|could|can|would|please|available|prefer|need|want)\b",
    flags=re.IGNORECASE,
)


class SlotConstraints(TypedDict):
    preferred_weekdays: set[int]
    earliest_date: date | None
    latest_date: date | None
    daily_start: time | None
    daily_end: time | None
    notes: list[str]

SEED_ACTIONS: list[ClinicActionsItem] = [
    {
        "clinic_id": CLINIC_ID,
        "action_id": "act_001",
        "action_type": "enquiry",
        "priority": "new",
        "status": "needs_approval",
        "patient_id": "p10",
        "patient_name": "Rachel Davies",
        "time_label": "9:41 AM",
        "source_summary": "New patient referred by GP, wants initial consultation",
        "source_message": "Hi, I was referred by Dr. Patel at the Angel Medical Centre. I'd like to book an initial consultation at your earliest convenience. I'm flexible on days but prefer afternoons if possible. Thank you, Rachel",
        "draft_message": "Dear Rachel,\n\nThank you for getting in touch, and welcome. I have the following afternoon slots available:\n\n- Wednesday 30 Apr at 2:00 PM\n- Friday 2 May at 3:15 PM\n- Monday 5 May at 2:30 PM\n\nInitial consultations are 45 minutes. Please let me know which works best and I will confirm your booking.\n\nWarm regards,\nDr. Shalini's Clinic",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
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
        "time_label": "8:15 AM",
        "source_summary": "Wants to move Friday appointment to next week",
        "source_message": "Hi, I'm afraid something has come up and I won't be able to make my Friday appointment. Could we reschedule to sometime next week? Monday or Tuesday would be ideal. Thanks, Fatima",
        "draft_message": "Dear Fatima,\n\nOf course, no problem at all. I can offer the following options for next week:\n\n- Monday 5 May at 11:00 AM\n- Tuesday 6 May at 10:30 AM\n- Tuesday 6 May at 3:00 PM\n\nPlease let me know your preference.\n\nBest wishes,\nDr. Shalini's Clinic",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
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
        "time_label": "7:30 AM",
        "source_summary": "NHS clinic confirmed for Wednesday",
        "source_message": "Wednesday 30 Apr, 8:30 AM - 1:00 PM\nSt Mary's Hospital, Praed Street\n4 patients scheduled",
        "draft_message": "",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
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
        "time_label": "Auto",
        "source_summary": "Follow-up due - last seen 4 weeks ago",
        "source_message": "",
        "draft_message": "Dear Priya,\n\nI hope you are well. It has been about four weeks since your last visit and I would like to schedule a follow-up to review your progress. I have availability on:\n\n- Friday 2 May at 10:00 AM\n- Monday 5 May at 9:30 AM\n\nPlease let me know if either works, or suggest a time that suits you better.\n\nBest wishes,\nDr. Shalini's Clinic",
        "external_draft_id": "",
        "external_sent_message_id": "",
        "final_message": "",
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
        "write_mode": "read_only_source_of_truth",
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
        "write_mode": "read_inbox_prepare_in_app_drafts",
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
        "patientId": _optional_text(item["patient_id"]),
        "patientName": _optional_text(item["patient_name"]),
        "priority": item["priority"],
        "sourceMessage": _optional_text(item["source_message"]),
        "sourceMessageId": _optional_text(item["source_message_id"]),
        "sourceProvider": item["source_provider"],
        "sourceSummary": item["source_summary"],
        "sourceThreadId": _optional_text(item["source_thread_id"]),
        "status": item["status"],
        "timeLabel": item["time_label"],
        "updatedAt": item["updated_at"],
    }


def _patient_dto(item: ClinicPatientsItem) -> dict[str, Any]:
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
    items = query_clinic_actions(CLINIC_ID, scan_index_forward=True, consistent_read=True)
    if items:
        return items
    gmail_integration = get_clinic_integrations(CLINIC_ID, "gmail")
    if gmail_integration and gmail_integration["last_sync_at"]:
        return []
    for item in SEED_ACTIONS:
        put_clinic_actions(item)
    return list(SEED_ACTIONS)


def _list_patient_items() -> list[ClinicPatientsItem]:
    items = query_clinic_patients(CLINIC_ID, scan_index_forward=True, consistent_read=True)
    if items:
        return items
    for item in SEED_PATIENTS:
        put_clinic_patients(item)
    return list(SEED_PATIENTS)


def _list_schedule_items() -> list[ClinicScheduleItem]:
    items = query_clinic_schedule(CLINIC_ID, scan_index_forward=True, consistent_read=True)
    if items:
        return items
    calendar_integration = get_clinic_integrations(CLINIC_ID, "google_calendar")
    if calendar_integration and calendar_integration["last_sync_at"]:
        return []
    for item in SEED_SCHEDULE:
        put_clinic_schedule(item)
    return list(SEED_SCHEDULE)


def _list_setting_items() -> list[ClinicSettingsItem]:
    items = query_clinic_settings(CLINIC_ID, scan_index_forward=True, consistent_read=True)
    if items:
        return items
    for item in SEED_SETTINGS:
        put_clinic_settings(item)
    return list(SEED_SETTINGS)


def _list_integration_items() -> list[ClinicIntegrationsItem]:
    items = query_clinic_integrations(CLINIC_ID, scan_index_forward=True, consistent_read=True)
    if items:
        return items
    for item in SEED_INTEGRATIONS:
        put_clinic_integrations(item)
    return list(SEED_INTEGRATIONS)


def _list_actions(include_completed: bool) -> dict[str, Any]:
    items = sorted(_list_action_items(), key=lambda item: item["created_at"], reverse=True)
    if not include_completed:
        items = [item for item in items if item["status"] != "completed"]
    return {"actions": [_action_dto(item) for item in items]}


def _find_action(action_id: str) -> ClinicActionsItem | None:
    item = get_clinic_actions(CLINIC_ID, action_id)
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
    return {
        "action": _action_dto(updated),
        "message": "approval stored; no external action was taken",
    }


def _list_patients() -> dict[str, Any]:
    items = sorted(_list_patient_items(), key=lambda item: item["name"])
    return {"patients": [_patient_dto(item) for item in items]}


def _list_schedule() -> dict[str, Any]:
    items = sorted(_list_schedule_items(), key=lambda item: (item["sort_order"], item["start_time"]))
    days_by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        day_key = item["day_key"]
        if day_key not in days_by_key:
            days_by_key[day_key] = {
                "dayKey": day_key,
                "dayLabel": item["day_label"],
                "dayType": item["day_type"],
                "events": [],
            }
        cast(list[dict[str, Any]], days_by_key[day_key]["events"]).append(_schedule_event_dto(item))
    return {"days": list(days_by_key.values())}


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
            "calendarWrites": "disabled",
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

    token_secret_prefix = os.environ.get("GOOGLE_TOKEN_SECRET_PREFIX", f"{CLINIC_ID}/clinic_agent/google").strip()
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
        "clinic_id": CLINIC_ID,
        "integration_id": integration_id,
        "provider": provider,
        "status": "connected",
        "account_email": account_email,
        "calendar_id": "primary" if integration_id == "google_calendar" else "",
        "calendar_sync_token": "",
        "gmail_history_id": "",
        "required_scopes": scopes,
        "write_mode": "read_only_source_of_truth"
        if integration_id == "google_calendar"
        else "read_inbox_prepare_in_app_drafts",
        "token_secret_id": token_secret_id,
        "last_sync_at": "",
        "last_error": "",
        "connected_at": now,
        "updated_at": now,
    }


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
    return {
        "message": "Google account connected through Auth.js. Tokens were stored in the configured secret store.",
        "integrations": [_integration_dto(calendar_integration), _integration_dto(gmail_integration)],
    }


def _google_oauth_config() -> tuple[str, str]:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth client ID and secret are required for live Google reads.")
    return client_id, client_secret


def _connected_google_integration(integration_id: str) -> ClinicIntegrationsItem:
    integration = get_clinic_integrations(CLINIC_ID, integration_id)
    if integration is None:
        _list_integration_items()
        integration = get_clinic_integrations(CLINIC_ID, integration_id)
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
    integration = get_clinic_integrations(CLINIC_ID, integration_id)
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
    integration = get_clinic_integrations(CLINIC_ID, integration_id)
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
        "clinic_id": CLINIC_ID,
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
    for existing in query_clinic_schedule(CLINIC_ID, scan_index_forward=True, consistent_read=True):
        if existing["source_provider"] == "google_calendar":
            delete_clinic_schedule(CLINIC_ID, existing["event_id"])
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
    has_scheduling_intent = _contains_any(combined_text, SCHEDULING_INTENT_TERMS) or _contains_any(
        combined_text,
        BOOKING_PHRASES,
    )
    has_direct_request = DIRECT_PATIENT_REQUEST_PATTERN.search(combined_text) is not None

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
        "daily_start": None,
        "daily_end": None,
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


def _slot_constraints_from_text(text: str) -> SlotConstraints:
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
) -> str:
    first_name = patient_name.split()[0] if patient_name and patient_name != "Unknown sender" else "there"
    request_focus = _request_focus_phrase(request_text, appointment_kind)
    summary_note = _reply_summary_note(summary)
    if slot_labels:
        formatted_slots = "\n".join(f"- {slot}" for slot in slot_labels)
        return (
            f"Dear {first_name},\n\n"
            f"Thank you for your message about {request_focus}.{summary_note} "
            "I have checked Dr. Shalini's calendar and these windows currently look available:\n\n"
            f"{formatted_slots}\n\n"
            "Please let me know what exact time within one of these windows works best, "
            "and Dr. Shalini will confirm the appointment.\n\n"
            "Warm regards,\n"
            "Dr. Shalini's Clinic"
        )

    return (
        f"Dear {first_name},\n\n"
        "Thank you for your message. I have noted your request"
        f"{': ' + summary if summary else ''}.\n\n"
        "Dr. Shalini will review this and we will come back to you shortly.\n\n"
        "Warm regards,\n"
        "Dr. Shalini's Clinic"
    )


def _gmail_message_to_action_item(
    message: dict[str, Any],
    *,
    patient_by_email: dict[str, ClinicPatientsItem],
    synced_at: str,
) -> ClinicActionsItem | None:
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id:
        return None
    headers = _gmail_headers(message)
    snippet = html.unescape(str(message.get("snippet") or ""))
    if not _is_clinic_message(headers=headers, snippet=snippet, patient_by_email=patient_by_email):
        return None

    sender_name, sender_email = parseaddr(headers.get("from", ""))
    matched_patient = patient_by_email.get(sender_email.lower()) if sender_email else None
    patient_name = matched_patient["name"] if matched_patient else sender_name or sender_email or "Unknown sender"
    patient_id = matched_patient["patient_id"] if matched_patient else ""
    subject = headers.get("subject", "").strip()
    summary = _truncate(subject or snippet or "New Gmail message", 120)
    source_message = _truncate(f"From: {headers.get('from', '')}\nSubject: {subject}\n\n{snippet}".strip(), 1200)
    request_text = f"{subject} {snippet}"
    action_type, priority = _infer_gmail_action_type(request_text)
    appointment_kind, duration_minutes = _request_appointment_details(request_text)
    constraints = _slot_constraints_from_text(request_text)
    slot_labels = _suggest_free_slot_labels(
        appointment_kind=appointment_kind,
        duration_minutes=duration_minutes,
        constraints=constraints,
    )
    created_at = _gmail_message_datetime(message, headers)
    thread_id = message.get("threadId")
    localized = created_at.astimezone(_clinic_timezone())

    return {
        "clinic_id": CLINIC_ID,
        "action_id": f"gmail-{_safe_external_fragment(message_id)}",
        "action_type": action_type,
        "priority": priority,
        "status": "needs_approval",
        "patient_id": patient_id,
        "patient_name": patient_name,
        "time_label": localized.strftime("%I:%M %p").lstrip("0"),
        "source_summary": summary,
        "source_message": source_message,
        "draft_message": _draft_reply_for_message(
            patient_name,
            summary,
            appointment_kind=appointment_kind,
            slot_labels=slot_labels,
            request_text=request_text,
        ),
        "external_draft_id": "",
        "external_sent_message_id": "",
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


def _replace_open_gmail_action_candidates(items: list[ClinicActionsItem]) -> None:
    for existing in query_clinic_actions(CLINIC_ID, scan_index_forward=True, consistent_read=True):
        if existing["source_provider"] == "gmail" and existing["status"] != "completed":
            delete_clinic_actions(CLINIC_ID, existing["action_id"])
    for item in items:
        put_clinic_actions(item)


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
        action_items: list[ClinicActionsItem] = []
        for message in messages:
            item = _gmail_message_to_action_item(message, patient_by_email=patient_by_email, synced_at=synced_at)
            if item is None:
                continue
            existing = get_clinic_actions(CLINIC_ID, item["action_id"])
            if existing and existing["status"] == "completed":
                continue
            action_items.append(item)

        _replace_open_gmail_action_candidates(action_items)
        _mark_integration_success("gmail", synced_at)
        sorted_actions = sorted(action_items, key=lambda item: item["created_at"], reverse=True)
        return {
            "status": "synced",
            "sourceOfTruth": "gmail",
            "writeMode": "read_inbox_prepare_in_app_drafts",
            "externalWrites": 0,
            "messagesScanned": len(messages),
            "proposedActions": len(action_items),
            "message": "Gmail read completed. In-app action drafts were prepared; no email was sent or drafted in Gmail.",
            "actions": [_action_dto(item) for item in sorted_actions],
        }
    except (GoogleWorkspaceError, RuntimeError) as exc:
        _mark_integration_failure("gmail", str(exc))
        raise RuntimeError(str(exc)) from exc


def lambda_handler(event: dict[str, Any] | None, context: object | None = None) -> dict[str, Any]:
    """Route clinic app actions."""
    _ = context
    payload = event or {}
    action = str(payload.get("action", "list_actions"))

    if action == "list_actions":
        return json_response(200, _list_actions(bool(payload.get("includeCompleted", False))))
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
