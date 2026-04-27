"""Starter Lambda agent for the Infiapp demo app."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from generated.dynamodb import SAMPLE_MESSAGES_TABLE
from response import json_response


def _payload_from_event(event: dict[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}

    body = event.get("body")
    if isinstance(body, str) and body:
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            parsed_body = {}
        if isinstance(parsed_body, dict):
            return parsed_body

    if isinstance(body, dict):
        return body

    return event


def _store_message(message: str) -> bool:
    if not os.environ.get("AWS_EXECUTION_ENV"):
        return False

    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        return False

    created_at = datetime.now(timezone.utc).isoformat()
    table_name = SAMPLE_MESSAGES_TABLE["table_name"]
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    table.put_item(
        Item={
            "app_name": "infiapp",
            "message_id": f"{created_at}#{uuid.uuid4()}",
            "created_at": created_at,
            "message": message,
        }
    )
    return True


def lambda_handler(event: dict[str, Any] | None, context: object | None = None) -> dict[str, Any]:
    """Store a user message and echo the latest message back."""
    _ = context
    payload = _payload_from_event(event)
    message = str(payload.get("message", "")).strip()
    if not message:
        return json_response(400, {"error": "message is required", "agent": "sample_agent"})

    stored = _store_message(message)
    body = {
        "message": f"lambda was called: {message}",
        "lastMessage": message,
        "agent": "sample_agent",
        "mocked": False,
        "stored": stored,
        "table": SAMPLE_MESSAGES_TABLE["table_name"],
    }
    return json_response(200, body)


def local_call(message: str = "sample message from local") -> dict[str, Any]:
    """Convenience function used by local tooling and tests."""
    response = lambda_handler({"source": "local", "message": message})
    return json.loads(response["body"])
