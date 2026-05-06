"""Tests for clinic_agent."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, time, timedelta
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

    def test_approval_records_completion_without_external_side_effects(self) -> None:
        seed_action = handler_module.SEED_ACTIONS[0]
        with (
            patch.object(handler_module, "get_clinic_actions", return_value=seed_action),
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
            patch.object(handler_module, "get_clinic_actions", return_value=None),
            patch.object(handler_module, "_replace_open_gmail_action_candidates") as replace_actions,
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
        replace_actions.assert_called_once()
        mark_success.assert_called_once()

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

    def test_connect_google_workspace_stores_metadata_without_returning_tokens(self) -> None:
        token_response = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
            "id_token": fake_id_token("doctor@example.com"),
        }
        with (
            patch.object(handler_module, "_store_google_token_secret", return_value="secret/google/doctor") as store,
            patch.object(handler_module, "put_clinic_integrations") as put_integration,
        ):
            response = lambda_handler(
                {
                    "action": "connect_google_workspace",
                    "accountEmail": "doctor@example.com",
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


if __name__ == "__main__":
    unittest.main()
