"""Clinic assistant Lambda agent.

The MVP is deliberately human-in-the-loop: this agent records proposals,
approvals, and completions, but it does not send email or update calendars.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, cast

from generated.dynamodb import (
    ClinicActionsItem,
    ClinicIntegrationsItem,
    ClinicPatientsItem,
    ClinicScheduleItem,
    ClinicSettingsItem,
    get_clinic_actions,
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
from google_workspace import required_google_scopes
from response import json_response

CLINIC_ID = "shalini-clinic"
SEED_UPDATED_AT = "2026-05-02T00:00:00+00:00"
COMPLETION_NOTE = "Doctor approved and stored this action. No external email or calendar action was taken by the MVP."

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


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


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


def _sync_google_calendar() -> dict[str, Any]:
    schedule = _list_schedule()
    event_count = sum(len(day["events"]) for day in schedule["days"])
    return {
        "status": "preview",
        "sourceOfTruth": "google_calendar",
        "writeMode": "read_only_cache",
        "externalWrites": 0,
        "eventsRead": event_count,
        "appointmentsCached": event_count,
        "message": "Calendar sync path is read-only: appointments are read from Google Calendar and cached locally.",
        **schedule,
    }


def _scan_gmail_inbox() -> dict[str, Any]:
    gmail_actions = [item for item in _list_action_items() if item["source_provider"] == "gmail"]
    return {
        "status": "preview",
        "sourceOfTruth": "gmail",
        "writeMode": "read_inbox_prepare_in_app_drafts",
        "externalWrites": 0,
        "messagesScanned": len(gmail_actions),
        "proposedActions": len(gmail_actions),
        "message": "Gmail scan path is read-only: messages become proposed action records and in-app drafts only.",
        "actions": [_action_dto(item) for item in gmail_actions],
    }


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
        return json_response(200, _sync_google_calendar())
    if action == "scan_gmail_inbox":
        return json_response(200, _scan_gmail_inbox())

    return json_response(400, {"error": f"unsupported action: {action}"})
