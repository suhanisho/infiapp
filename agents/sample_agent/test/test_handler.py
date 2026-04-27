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
        response = lambda_handler({"action": "store_message", "message": "sample note"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["action"], "store_message")
        self.assertEqual(body["message"], "message stored")
        self.assertEqual(body["item"]["message"], "sample note")
        self.assertEqual(body["agent"], "sample_agent")
        self.assertFalse(body["stored"])

    def test_lambda_handler_accepts_function_url_body(self) -> None:
        response = lambda_handler({"body": json.dumps({"action": "store_message", "message": "from body"})})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["item"]["message"], "from body")

    def test_lambda_handler_lists_messages_shape(self) -> None:
        response = lambda_handler({"action": "list_messages", "limit": 5})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["action"], "list_messages")
        self.assertEqual(body["messages"], [])
        self.assertIsNone(body["nextKey"])

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
