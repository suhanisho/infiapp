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
    def test_lambda_handler_returns_demo_message(self) -> None:
        response = lambda_handler({"button": "clicked"})

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["message"], "lambda was called")
        self.assertEqual(body["agent"], "hello_agent")
        self.assertEqual(body["table"], "infiloop_hello_calls")

    def test_local_call_uses_handler(self) -> None:
        self.assertEqual(local_call()["message"], "lambda was called")


if __name__ == "__main__":
    unittest.main()

