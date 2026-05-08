"""Tests for clinic_agent."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
from importlib.util import module_from_spec, spec_from_file_location
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parents[1]
AGENTS_DIR = AGENT_DIR.parents[0]
sys.path.insert(0, str(AGENTS_DIR / "shared_utils"))
sys.path.insert(0, str(AGENT_DIR / "code"))


def load_handler_module() -> ModuleType:
    module_path = AGENT_DIR / "code" / "handler.py"
    spec = spec_from_file_location("clinic_agent_handler", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handler_module = load_handler_module()
lambda_handler = cast(
    Callable[..., dict[str, Any]],
    getattr(handler_module, "lambda_handler"),
)


class FakeGoogleClient:
    def list_calendar_events(
        self,
        *,
        calendar_id: str,
        time_min: str,
        time_max: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        _ = (calendar_id, time_min, time_max, max_results)
        return [
            {
                "id": "calendar-event-1",
                "summary": "Follow-up with Emma Richardson",
                "etag": "etag-1",
                "start": {"dateTime": "2026-05-06T09:00:00+01:00"},
                "end": {"dateTime": "2026-05-06T09:30:00+01:00"},
                "status": "confirmed",
            }
        ]

    def list_gmail_message_metadata(self, *, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        _ = (query, max_results)
        return [
            {
                "id": "gmail-message-live-1",
                "threadId": "gmail-thread-live-1",
                "internalDate": "1778067600000",
                "snippet": "Could I book an appointment with Dr Shalini next week?",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Rachel Davies <rachel.d@gmail.com>"},
                        {"name": "Subject", "value": "Appointment request"},
                    ]
                },
            }
        ]


def fake_id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{payload}.signature"


def trusted_actor_fields(email: str, secret: str = "test-internal-secret") -> dict[str, str]:
    normalized = email.strip().lower()
    issued_at = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{normalized}:{issued_at}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "actorEmail": normalized,
        "actorIssuedAt": issued_at,
        "actorSignature": signature,
    }


class ClinicAgentTest(unittest.TestCase):
    def test_lists_seed_actions_when_table_is_empty(self) -> None:
        with (
            patch.object(handler_module, "query_clinic_actions", return_value=[]),
            patch.object(handler_module, "get_clinic_integrations", return_value=None),
            patch.object(handler_module, "put_clinic_actions") as put_action,
        ):
            response = lambda_handler({"action": "list_actions", "includeCompleted": True})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertGreaterEqual(len(body["actions"]), 4)
        self.assertEqual(body["actions"][0]["status"], "needs_approval")
        put_action.assert_called()

    def test_actor_email_derives_practice_scope(self) -> None:
        expected_practice_id = handler_module._practice_id_for_actor("doctor@example.com")
        with (
            patch.dict(handler_module.os.environ, {"CLINIC_AGENT_INTERNAL_SECRET": "test-internal-secret"}),
            patch.object(handler_module, "query_clinic_actions", return_value=[]) as query_actions,
            patch.object(handler_module, "get_clinic_integrations", return_value={"last_sync_at": "2026-05-07"}),
        ):
            response = lambda_handler(
                {
                    "action": "list_actions",
                    **trusted_actor_fields("doctor@example.com"),
                    "includeCompleted": True,
                }
            )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["practiceId"], expected_practice_id)
        query_actions.assert_called_once_with(expected_practice_id, scan_index_forward=True, consistent_read=True)

    def test_actor_email_requires_trusted_assertion(self) -> None:
        response = lambda_handler(
            {
                "action": "list_actions",
                "actorEmail": "doctor@example.com",
                "includeCompleted": True,
            }
        )

        self.assertEqual(response["statusCode"], 401)
        body = json.loads(response["body"])
        self.assertIn("Trusted actor assertion", body["error"])

    def test_approval_records_completion_without_external_side_effects(self) -> None:
        seed_action = handler_module.SEED_ACTIONS[0]
        with (
            patch.object(handler_module, "get_clinic_actions", return_value=seed_action),
            patch.object(handler_module, "get_clinic_patient_requests", return_value=None),
            patch.object(handler_module, "put_clinic_actions") as put_action,
        ):
            response = lambda_handler(
                {
                    "action": "approve_action",
                    "actionId": seed_action["action_id"],
                    "approvedBy": "Dr. Shalini",
                    "finalMessage": "Approved text",
                }
            )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["action"]["status"], "completed")
        self.assertEqual(body["action"]["finalMessage"], "Approved text")
        self.assertIn("no external action", body["message"])
        saved_item = put_action.call_args.args[0]
        self.assertEqual(saved_item["status"], "completed")
        self.assertIn("No external email or calendar action", saved_item["completion_note"])

    def test_approval_requires_action_id(self) -> None:
        response = lambda_handler({"action": "approve_action"})

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "actionId is required")

    def test_unknown_action_is_rejected(self) -> None:
        response = lambda_handler({"action": "send_email"})

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "unsupported action: send_email")

    def test_calendar_sync_path_is_read_only(self) -> None:
        with (
            patch.object(
                handler_module,
                "_google_client_for_integration",
                return_value=({**handler_module.SEED_INTEGRATIONS[0], "token_secret_id": "secret"}, FakeGoogleClient()),
            ),
            patch.object(handler_module, "_replace_google_schedule_cache") as replace_cache,
            patch.object(handler_module, "_mark_integration_success") as mark_success,
            patch.object(
                handler_module,
                "_list_schedule",
                return_value={
                    "days": [
                        {
                            "dayKey": "Wed 6",
                            "dayLabel": "Wednesday 6 May",
                            "dayType": "private",
                            "events": [],
                        }
                    ]
                },
            ),
        ):
            response = lambda_handler({"action": "sync_google_calendar"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["sourceOfTruth"], "google_calendar")
        self.assertEqual(body["writeMode"], "read_only_cache")
        self.assertEqual(body["externalWrites"], 0)
        self.assertEqual(body["eventsRead"], 1)
        replace_cache.assert_called_once()
        mark_success.assert_called_once()

    def test_list_schedule_returns_two_week_day_window(self) -> None:
        zone = handler_module._clinic_timezone()
        today = datetime.now(zone).date()
        appointment_date = today + timedelta(days=2)
        start_at = datetime.combine(appointment_date, time(10, 0), tzinfo=zone)
        end_at = datetime.combine(appointment_date, time(10, 30), tzinfo=zone)
        schedule_item = {
            "clinic_id": handler_module.LEGACY_CLINIC_ID,
            "event_id": "future-event-1",
            "day_key": f"{appointment_date:%a} {appointment_date.day}",
            "day_label": f"{appointment_date:%A} {appointment_date.day} {appointment_date:%b}",
            "day_type": "private",
            "start_time": "10:00",
            "end_time": "10:30",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "external_calendar_id": "primary",
            "external_etag": "etag-1",
            "external_event_id": "external-1",
            "last_synced_at": "2026-05-08T10:00:00+01:00",
            "patient_id": "patient-1",
            "patient_name": "Future Patient",
            "source_provider": "google_calendar",
            "appointment_type": "Follow-up",
            "status": "upcoming",
            "sort_order": 1,
        }
        with patch.object(handler_module, "query_clinic_schedule", return_value=[schedule_item]):
            body = handler_module._list_schedule()

        self.assertEqual(len(body["days"]), handler_module.CALENDAR_SYNC_DAYS)
        self.assertEqual(body["days"][0]["dayDate"], today.isoformat())
        self.assertEqual(body["days"][2]["dayDate"], appointment_date.isoformat())
        self.assertEqual(body["days"][2]["events"][0]["patientName"], "Future Patient")

    def test_gmail_scan_path_only_prepares_in_app_drafts(self) -> None:
        with (
            patch.object(
                handler_module,
                "_google_client_for_integration",
                return_value=({**handler_module.SEED_INTEGRATIONS[1], "token_secret_id": "secret"}, FakeGoogleClient()),
            ),
            patch.object(handler_module, "_patient_lookup_by_email", return_value={}),
            patch.object(
                handler_module,
                "_suggest_free_slot_labels",
                return_value=["Monday 11 May, 9:00 AM - 9:45 AM (Initial Consultation)"],
            ),
            patch.object(handler_module, "get_clinic_patient_requests", return_value=None),
            patch.object(handler_module, "get_clinic_actions", return_value=None),
            patch.object(handler_module, "_upsert_gmail_request_candidates", side_effect=lambda items: [handler_module._patient_request_to_action_item(item) for item in items]) as upsert_requests,
            patch.object(handler_module, "_mark_integration_success") as mark_success,
        ):
            response = lambda_handler({"action": "scan_gmail_inbox"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["sourceOfTruth"], "gmail")
        self.assertEqual(body["writeMode"], "read_inbox_prepare_in_app_drafts")
        self.assertEqual(body["externalWrites"], 0)
        self.assertEqual(body["messagesScanned"], 1)
        self.assertEqual(body["proposedActions"], 1)
        self.assertIn("no email was sent", body["message"])
        self.assertIn("Monday 11 May", body["actions"][0]["draftMessage"])
        self.assertEqual(body["actions"][0]["patientRequestId"], "gmail-gmail-message-live-1")
        self.assertNotEqual(body["actions"][0]["actionId"], body["actions"][0]["patientRequestId"])
        self.assertEqual(body["actions"][0]["metadata"]["request_type"], "appointment_request")
        self.assertEqual(body["actions"][0]["metadata"]["urgency_level"], "routine")
        self.assertEqual(body["patientRequests"][0]["patientRequestId"], "gmail-gmail-message-live-1")
        self.assertEqual(body["patientRequests"][0]["requestType"], "appointment_request")
        self.assertFalse(body["patientRequests"][0]["requiresDoctorReview"])
        upsert_requests.assert_called_once()
        mark_success.assert_called_once()

    def test_request_action_id_is_distinct_from_patient_request_id(self) -> None:
        with patch.object(handler_module, "_suggest_free_slot_labels", return_value=[]):
            request_item = handler_module._gmail_message_to_patient_request_item(
                FakeGoogleClient().list_gmail_message_metadata(query="", max_results=1)[0],
                patient_by_email={},
                synced_at="2026-05-07T00:00:00+00:00",
            )
        self.assertIsNotNone(request_item)
        request_item = cast(Any, request_item)
        action_item = handler_module._patient_request_to_action_item(request_item)

        self.assertEqual(action_item["patient_request_id"], request_item["patient_request_id"])
        self.assertNotEqual(action_item["action_id"], request_item["patient_request_id"])
        self.assertEqual(action_item["metadata"]["action_kind"], handler_module.REPLY_REVIEW_ACTION_KIND)
        self.assertEqual(action_item["action_type"], "appointment_request")
        self.assertEqual(action_item["metadata"]["risk_level"], "low")
        self.assertIsInstance(request_item["triage_confidence"], Decimal)
        self.assertEqual(handler_module._patient_request_dto(request_item)["triageConfidence"], 0.72)
        json.dumps(handler_module._patient_request_dto(request_item))

    def test_new_gmail_sender_gets_patient_id_and_record(self) -> None:
        with patch.object(handler_module, "_suggest_free_slot_labels", return_value=[]):
            request_item = handler_module._gmail_message_to_patient_request_item(
                FakeGoogleClient().list_gmail_message_metadata(query="", max_results=1)[0],
                patient_by_email={},
                synced_at="2026-05-07T00:00:00+00:00",
            )
        self.assertIsNotNone(request_item)
        request_item = cast(Any, request_item)

        with (
            patch.object(handler_module, "get_clinic_patient_requests", return_value=None),
            patch.object(handler_module, "get_clinic_actions", return_value=None),
            patch.object(handler_module, "get_clinic_patients", return_value=None),
            patch.object(handler_module, "put_clinic_patients") as put_patient,
            patch.object(handler_module, "put_clinic_patient_requests"),
            patch.object(handler_module, "put_clinic_actions") as put_action,
        ):
            actions = handler_module._upsert_gmail_request_candidates([request_item])

        self.assertTrue(request_item["patient_id"].startswith("patient_email_"))
        self.assertEqual(request_item["patient_email"], "rachel.d@gmail.com")
        patient_item = put_patient.call_args.args[0]
        self.assertEqual(patient_item["patient_id"], request_item["patient_id"])
        self.assertEqual(patient_item["email"], "rachel.d@gmail.com")
        self.assertEqual(patient_item["status"], "new")
        self.assertEqual(actions[0]["patient_id"], request_item["patient_id"])
        self.assertEqual(put_action.call_args.args[0]["patient_id"], request_item["patient_id"])

    def test_list_patients_includes_request_timeline(self) -> None:
        with patch.object(handler_module, "_suggest_free_slot_labels", return_value=[]):
            request_item = handler_module._gmail_message_to_patient_request_item(
                FakeGoogleClient().list_gmail_message_metadata(query="", max_results=1)[0],
                patient_by_email={},
                synced_at="2026-05-07T00:00:00+00:00",
            )
        self.assertIsNotNone(request_item)
        request_item = cast(Any, request_item)
        patient_item = handler_module._patient_item_from_request(request_item)

        with (
            patch.object(handler_module, "query_clinic_patients", return_value=[patient_item]),
            patch.object(handler_module, "query_clinic_patient_requests", return_value=[request_item]),
        ):
            body = handler_module._list_patients()

        patient = body["patients"][0]
        self.assertEqual(patient["requestCount"], 1)
        self.assertEqual(patient["openRequestCount"], 1)
        self.assertEqual(patient["timeline"][0]["patientRequestId"], request_item["patient_request_id"])
        self.assertEqual(patient["timeline"][0]["requestType"], "appointment_request")

    def test_urgent_clinical_message_is_triaged_for_doctor_review(self) -> None:
        message = {
            "id": "gmail-message-urgent-1",
            "threadId": "gmail-thread-urgent-1",
            "internalDate": "1778067600000",
            "snippet": "I am 28 weeks pregnant and have had reduced fetal movement since last night.",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Aisha Khan <aisha@example.com>"},
                    {"name": "Subject", "value": "Worried about movement"},
                ]
            },
        }

        with patch.object(handler_module, "_suggest_free_slot_labels", return_value=["Monday 11 May, 9:00 AM"]):
            request_item = handler_module._gmail_message_to_patient_request_item(
                message,
                patient_by_email={},
                synced_at="2026-05-07T00:00:00+00:00",
            )

        self.assertIsNotNone(request_item)
        request_item = cast(Any, request_item)
        action_item = handler_module._patient_request_to_action_item(request_item)
        dto = handler_module._patient_request_dto(request_item)

        self.assertEqual(request_item["request_type"], "urgent_clinical_concern")
        self.assertEqual(request_item["urgency_level"], "urgent")
        self.assertEqual(request_item["risk_level"], "high")
        self.assertTrue(request_item["requires_doctor_review"])
        self.assertEqual(request_item["proposed_windows"], [])
        self.assertIn("urgent review", request_item["draft_message"])
        self.assertEqual(action_item["priority"], "urgent")
        self.assertEqual(dto["requestType"], "urgent_clinical_concern")

    def test_patient_request_merge_preserves_existing_state(self) -> None:
        with patch.object(handler_module, "_suggest_free_slot_labels", return_value=[]):
            incoming = handler_module._gmail_message_to_patient_request_item(
                FakeGoogleClient().list_gmail_message_metadata(query="", max_results=1)[0],
                patient_by_email={},
                synced_at="2026-05-07T00:00:00+00:00",
            )
        self.assertIsNotNone(incoming)
        incoming = cast(Any, incoming)
        existing = cast(
            dict[str, Any],
            {
                **incoming,
                "created_at": "2026-05-01T00:00:00+00:00",
                "triage_reason": "Manually reviewed by the doctor.",
                "manual_note": "Keep this note.",
            },
        )

        merged = cast(
            dict[str, Any],
            handler_module._merge_patient_request_candidate(cast(Any, existing), incoming),
        )

        self.assertEqual(merged["created_at"], "2026-05-01T00:00:00+00:00")
        self.assertEqual(merged["manual_note"], "Keep this note.")

    def test_meet_and_greet_draft_uses_short_calendar_slots(self) -> None:
        appointment_kind, duration_minutes = handler_module._request_appointment_details(
            "Can I book a meet & greet with Dr. Shalini?"
        )
        draft = handler_module._draft_reply_for_message(
            "Rachel Davies",
            "Meet & Greet request",
            appointment_kind=appointment_kind,
            slot_labels=["Monday 11 May, 9:00 AM - 9:15 AM (Meet & Greet)"],
        )

        self.assertEqual(appointment_kind, "Meet & Greet")
        self.assertEqual(duration_minutes, 15)
        self.assertIn("Monday 11 May", draft)
        self.assertIn("what exact time within one of these windows", draft)

    def test_patient_text_constraints_capture_weekdays_and_time_window(self) -> None:
        constraints = handler_module._slot_constraints_from_text(
            "Monday or Tuesday afternoons next week would be ideal."
        )

        self.assertEqual(constraints["preferred_weekdays"], {0, 1})
        self.assertEqual(constraints["daily_start"], time(12, 0))
        self.assertEqual(constraints["daily_end"], time(17, 0))
        self.assertIsNotNone(constraints["earliest_date"])
        self.assertIsNotNone(constraints["latest_date"])

    def test_scan_anchor_constraints_capture_same_day_after_time(self) -> None:
        appointment_kind, duration_minutes = handler_module._request_appointment_details(
            "Could I book an appointment after my scan on 15th May at 3pm?"
        )
        constraints = handler_module._slot_constraints_from_text(
            "Could I book an appointment after my scan on 15th May at 3pm?",
            appointment_kind=appointment_kind,
        )

        self.assertEqual(appointment_kind, "Follow-up")
        self.assertEqual(duration_minutes, 20)
        self.assertIsNotNone(constraints["earliest_at"])
        earliest_at = constraints["earliest_at"]
        self.assertEqual(earliest_at.month, 5)
        self.assertEqual(earliest_at.day, 15)
        self.assertEqual(earliest_at.hour, 16)
        self.assertEqual(earliest_at.minute, 30)
        self.assertEqual(constraints["earliest_date"], earliest_at.date())
        self.assertIn("after your scan", constraints["constraint_summary"])

    def test_non_patient_marketing_email_is_ignored(self) -> None:
        headers = {
            "from": "Newsletter <newsletter@example.com>",
            "subject": "Book your product demo appointment",
        }

        self.assertFalse(
            handler_module._is_clinic_message(
                headers=headers,
                snippet="Limited time offer. Unsubscribe here.",
                patient_by_email={},
            )
        )

    def test_slot_suggestions_respect_patient_constraints(self) -> None:
        zone = handler_module._clinic_timezone()
        target_date = datetime.now(zone).date() + timedelta(days=3)
        constraints = handler_module._empty_slot_constraints()
        constraints["preferred_weekdays"] = {target_date.weekday()}
        constraints["earliest_date"] = target_date
        constraints["latest_date"] = target_date
        constraints["daily_start"] = time(14, 0)
        constraints["daily_end"] = time(17, 0)

        with (
            patch.object(handler_module, "_weekday_availability", return_value={target_date.weekday(): (time(9, 0), time(17, 0))}),
            patch.object(handler_module, "_clinic_buffer_minutes", return_value=0),
            patch.object(handler_module, "_clinic_lunch_window", return_value=None),
            patch.object(handler_module, "_busy_schedule_windows", return_value=[]),
        ):
            slots = handler_module._suggest_free_slot_labels(
                appointment_kind="Meet & Greet",
                duration_minutes=15,
                constraints=constraints,
                limit=2,
            )

        expected_day = f"{target_date:%A} {target_date.day} {target_date:%b}"
        self.assertEqual(len(slots), 1)
        self.assertTrue(all(expected_day in slot for slot in slots))
        self.assertIn("between 2:00 PM and 5:00 PM", slots[0])

    def test_slot_suggestions_respect_anchor_earliest_datetime(self) -> None:
        zone = handler_module._clinic_timezone()
        target_date = datetime.now(zone).date() + timedelta(days=3)
        earliest_at = datetime.combine(target_date, time(15, 30), tzinfo=zone)
        constraints = handler_module._empty_slot_constraints()
        constraints["earliest_date"] = target_date
        constraints["earliest_at"] = earliest_at

        with (
            patch.object(
                handler_module,
                "_weekday_availability",
                return_value={target_date.weekday(): (time(9, 0), time(17, 0))},
            ),
            patch.object(handler_module, "_clinic_buffer_minutes", return_value=0),
            patch.object(handler_module, "_clinic_lunch_window", return_value=None),
            patch.object(handler_module, "_busy_schedule_windows", return_value=[]),
        ):
            slots = handler_module._suggest_free_slot_labels(
                appointment_kind="Follow-up",
                duration_minutes=20,
                constraints=constraints,
                limit=1,
            )

        expected_day = f"{target_date:%A} {target_date.day} {target_date:%b}"
        self.assertEqual(len(slots), 1)
        self.assertIn(expected_day, slots[0])
        self.assertIn("between 3:30 PM and 5:00 PM", slots[0])

    def test_gmail_full_body_context_anchors_follow_up_slots(self) -> None:
        zone = handler_module._clinic_timezone()
        scan_date = datetime.now(zone).date() + timedelta(days=8)
        body = (
            f"Hello, could I book a follow-up with Dr Shalini after my scan on "
            f"{scan_date.day} {scan_date:%b} at 3pm?"
        )
        encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8").rstrip("=")
        message = {
            "id": "gmail-message-scan-anchor",
            "threadId": "gmail-thread-scan-anchor",
            "internalDate": "1778067600000",
            "snippet": "Hello, could I book a follow-up?",
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": encoded_body},
                "headers": [
                    {"name": "From", "value": "Nina Shah <nina@example.com>"},
                    {"name": "Subject", "value": "Follow-up appointment"},
                ],
            },
        }
        captured_constraints: dict[str, Any] = {}

        def fake_slot_suggestions(**kwargs: Any) -> list[str]:
            captured_constraints.update(kwargs["constraints"])
            return [
                f"{scan_date:%A} {scan_date.day} {scan_date:%b}, between 4:30 PM and 5:30 PM "
                "(20-minute Follow-up)"
            ]

        with patch.object(handler_module, "_suggest_free_slot_labels", side_effect=fake_slot_suggestions):
            request_item = handler_module._gmail_message_to_patient_request_item(
                message,
                patient_by_email={},
                synced_at="2026-05-07T00:00:00+00:00",
            )

        self.assertIsNotNone(request_item)
        request_item = cast(Any, request_item)
        self.assertEqual(captured_constraints["earliest_at"].hour, 16)
        self.assertEqual(captured_constraints["earliest_at"].minute, 30)
        self.assertIn("after your scan", request_item["request_constraints"]["constraint_summary"])
        self.assertIn("after your scan", request_item["draft_message"])
        self.assertIn("4:30 PM", request_item["draft_message"])

    def test_connect_google_workspace_stores_metadata_without_returning_tokens(self) -> None:
        token_response = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
            "id_token": fake_id_token("doctor@example.com"),
        }
        with (
            patch.dict(handler_module.os.environ, {"CLINIC_AGENT_INTERNAL_SECRET": "test-internal-secret"}),
            patch.object(handler_module, "_store_google_token_secret", return_value="secret/google/doctor") as store,
            patch.object(handler_module, "put_clinic_integrations") as put_integration,
            patch.object(handler_module, "put_clinic_practice_members") as put_member,
        ):
            response = lambda_handler(
                {
                    "action": "connect_google_workspace",
                    "accountEmail": "doctor@example.com",
                    **trusted_actor_fields("doctor@example.com"),
                    "tokenResponse": token_response,
                }
            )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertNotIn("refresh-token", json.dumps(body))
        self.assertNotIn("gmail.compose", json.dumps(body))
        self.assertEqual(body["integrations"][0]["accountEmail"], "doctor@example.com")
        self.assertEqual(body["integrations"][0]["status"], "connected")
        store.assert_called_once()
        self.assertEqual(put_integration.call_count, 2)
        put_member.assert_called_once()


if __name__ == "__main__":
    unittest.main()
