"""Starter Lambda agent for the Infiapp demo app."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from generated.dynamodb import SampleMessagesItem, put_sample_messages, query_sample_messages_by_message_id_range_page
from response import json_response

APP_NAME = "infiapp"
DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 50


def _parse_limit(value: object) -> int:
    if isinstance(value, int):
        limit = value
    elif isinstance(value, str) and value.isdecimal():
        limit = int(value)
    else:
        limit = DEFAULT_PAGE_LIMIT
    return max(1, min(limit, MAX_PAGE_LIMIT))


def _parse_next_message_id(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _format_message(item: SampleMessagesItem) -> dict[str, str]:
    return {
        "messageId": item["message_id"],
        "createdAt": item["created_at"],
        "message": item["message"],
    }


def _store_message(message: str) -> SampleMessagesItem:
    created_at = datetime.now(timezone.utc).isoformat()
    item: SampleMessagesItem = {
        "app_name": APP_NAME,
        "message_id": f"{created_at}#{uuid.uuid4()}",
        "created_at": created_at,
        "message": message,
    }
    put_sample_messages(item)
    return item


def _list_messages(limit: int, next_message_id: str | None) -> dict[str, Any]:
    exclusive_start_key = {"app_name": APP_NAME, "message_id": next_message_id} if next_message_id else None
    page = query_sample_messages_by_message_id_range_page(
        APP_NAME,
        exclusive_start_key=exclusive_start_key,
        scan_index_forward=False,
        consistent_read=True,
        limit=limit,
    )
    next_key = page["next_key"]
    next_returned_message_id = next_key.get("message_id") if isinstance(next_key, dict) else None
    return {
        "messages": [_format_message(item) for item in page["items"]],
        "nextMessageId": next_returned_message_id if isinstance(next_returned_message_id, str) else None,
    }


def lambda_handler(event: dict[str, Any] | None, context: object | None = None) -> dict[str, Any]:
    """Store or list sample messages."""
    _ = context
    payload = event or {}
    action = str(payload.get("action", "store_message"))

    if action == "list_messages":
        page = _list_messages(_parse_limit(payload.get("limit")), _parse_next_message_id(payload.get("nextMessageId")))
        return json_response(
            200,
            {
                **page,
            },
        )

    if action != "store_message":
        return json_response(400, {"error": f"unsupported action: {action}"})

    message = str(payload.get("message", "")).strip()
    if not message:
        return json_response(400, {"error": "message is required"})

    item = _store_message(message)
    body = {
        "message": "message stored",
        "item": _format_message(item),
        "stored": True,
    }
    return json_response(200, body)
