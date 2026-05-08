"""Small response helpers shared by Lambda agents."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def _json_default(value: object) -> int | float:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Return an API Gateway/Lambda Function URL compatible JSON response."""
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
        },
        "body": json.dumps(body, default=_json_default, separators=(",", ":")),
    }
