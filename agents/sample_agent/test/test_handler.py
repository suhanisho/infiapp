"""Tests for sample_agent."""

from __future__ import annotations

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


def load_handler_module() -> ModuleType:
    module_path = AGENT_DIR / "code" / "handler.py"
    spec = spec_from_file_location("sample_agent_handler", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handler_module = load_handler_module()
lambda_handler = cast(
    Callable[..., dict[str, Any]],
    getattr(handler_module, "lambda_handler"),
)


class SampleAgentTest(unittest.TestCase):
    def test_lambda_handler_stores_message_shape(self) -> None:
        with patch.object(handler_module, "put_sample_messages") as put_item:
            response = lambda_handler({"action": "store_message", "message": "sample note"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertNotIn("action", body)
        self.assertEqual(body["message"], "message stored")
        self.assertEqual(body["item"]["message"], "sample note")
        self.assertNotIn("agent", body)
        self.assertNotIn("mocked", body)
        self.assertTrue(body["stored"])
        put_item.assert_called_once()

    def test_lambda_handler_lists_messages_shape(self) -> None:
        page = {
            "items": [
                {
                    "app_name": "infiapp",
                    "message_id": "message-1",
                    "created_at": "2026-04-27T00:00:00+00:00",
                    "message": "latest",
                }
            ],
            "next_key": {"app_name": "infiapp", "message_id": "message-1"},
        }
        with patch.object(handler_module, "query_sample_messages_by_message_id_range_page", return_value=page) as query:
            response = lambda_handler(
                {
                    "action": "list_messages",
                    "limit": 5,
                    "nextKey": {"app_name": "infiapp", "message_id": "message-0"},
                }
            )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertNotIn("action", body)
        self.assertEqual(body["messages"][0]["message"], "latest")
        self.assertEqual(body["nextKey"], {"app_name": "infiapp", "message_id": "message-1"})
        query.assert_called_once_with(
            "infiapp",
            exclusive_start_key={"app_name": "infiapp", "message_id": "message-0"},
            scan_index_forward=False,
            consistent_read=True,
            limit=5,
        )

    def test_lambda_handler_requires_message(self) -> None:
        response = lambda_handler({"action": "store_message"})

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "message is required")

    def test_lambda_handler_rejects_unknown_action(self) -> None:
        response = lambda_handler({"action": "wat"})

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "unsupported action: wat")


if __name__ == "__main__":
    unittest.main()
