"""Tests for shared Lambda response helpers."""

from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

SHARED_UTILS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED_UTILS_DIR))

from response import json_response  # noqa: E402


class JsonResponseTest(unittest.TestCase):
    def test_json_response_serializes_dynamodb_decimals(self) -> None:
        response = json_response(
            200,
            {
                "whole": Decimal("4"),
                "fractional": Decimal("0.72"),
                "nested": {"visits": Decimal("0")},
            },
        )

        body = json.loads(response["body"])
        self.assertEqual(body["whole"], 4)
        self.assertEqual(body["fractional"], 0.72)
        self.assertEqual(body["nested"]["visits"], 0)


if __name__ == "__main__":
    unittest.main()
