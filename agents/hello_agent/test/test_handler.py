"""Tests for hello_agent."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
AGENTS_DIR = AGENT_DIR.parents[0]
sys.path.insert(0, str(AGENT_DIR / "code"))
sys.path.insert(0, str(AGENTS_DIR / "shared_utils"))

from handler import lambda_handler, local_call  # noqa: E402


class HelloAgentTest(unittest.TestCase):
    def test_lambda_handler_stores_and_echoes_message_shape(self) -> None:
        response = lambda_handler({"button": "clicked", "message": "hello there"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["message"], "lambda was called: hello there")
        self.assertEqual(body["lastMessage"], "hello there")
        self.assertEqual(body["agent"], "hello_agent")
        self.assertEqual(body["table"], "infiloop_user_messages")
        self.assertFalse(body["stored"])

    def test_lambda_handler_accepts_function_url_body(self) -> None:
        response = lambda_handler({"body": json.dumps({"message": "from body"})})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["lastMessage"], "from body")

    def test_lambda_handler_requires_message(self) -> None:
        response = lambda_handler({"button": "clicked"})

        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "message is required")

    def test_local_call_uses_handler(self) -> None:
        self.assertEqual(local_call("local echo")["lastMessage"], "local echo")


if __name__ == "__main__":
    unittest.main()
