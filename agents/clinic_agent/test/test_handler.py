"""Tests for clinic_agent."""

from __future__ import annotations

import base64
from collections.abc import Callable
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


def fake_id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{payload}.signature"


class ClinicAgentTest(unittest.TestCase):
    def test_lists_seed_actions_when_table_is_empty(self) -> None:
        with (
            patch.object(handler_module, "query_clinic_actions", return_value=[]),
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
        with patch.object(handler_module, "query_clinic_schedule", return_value=handler_module.SEED_SCHEDULE):
            response = lambda_handler({"action": "sync_google_calendar"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["sourceOfTruth"], "google_calendar")
        self.assertEqual(body["writeMode"], "read_only_cache")
        self.assertEqual(body["externalWrites"], 0)
        self.assertGreater(body["eventsRead"], 0)

    def test_gmail_scan_path_only_prepares_in_app_drafts(self) -> None:
        with patch.object(handler_module, "query_clinic_actions", return_value=handler_module.SEED_ACTIONS):
            response = lambda_handler({"action": "scan_gmail_inbox"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["sourceOfTruth"], "gmail")
        self.assertEqual(body["writeMode"], "read_inbox_prepare_in_app_drafts")
        self.assertEqual(body["externalWrites"], 0)
        self.assertGreater(body["proposedActions"], 0)

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
