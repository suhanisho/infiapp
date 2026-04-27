"""Starter Lambda agent for the Infiloop demo app."""

from __future__ import annotations

import json
from typing import Any

from generated.dynamodb import INFILOOP_HELLO_CALLS_TABLE
from response import json_response


def lambda_handler(event: dict[str, Any] | None, context: object | None = None) -> dict[str, Any]:
    """Return a stable response for the starter backend call."""
    _ = context
    body = {
        "message": "lambda was called",
        "agent": "hello_agent",
        "mocked": False,
        "table": INFILOOP_HELLO_CALLS_TABLE["table_name"],
        "received": event or {},
    }
    return json_response(200, body)


def local_call() -> dict[str, Any]:
    """Convenience function used by local tooling and tests."""
    response = lambda_handler({"source": "local"})
    return json.loads(response["body"])
