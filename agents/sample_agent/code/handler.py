"""Starter Lambda agent for the Infiapp demo app."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, NamedTuple

from generated.dynamodb import SampleMessagesItem, put_sample_messages, query_sample_messages_by_message_id_range_page
from response import json_response

APP_NAME = "infiapp"
DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 50


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


class StoreResult(NamedTuple):
    stored: bool
    item: SampleMessagesItem


def _parse_limit(value: object) -> int:
    if isinstance(value, int):
        limit = value
    elif isinstance(value, str) and value.isdecimal():
        limit = int(value)
    else:
        limit = DEFAULT_PAGE_LIMIT
    return max(1, min(limit, MAX_PAGE_LIMIT))


def _parse_next_key(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return None


def _format_message(item: SampleMessagesItem) -> dict[str, str]:
    return {
        "messageId": item["message_id"],
        "createdAt": item["created_at"],
        "message": item["message"],
    }


def _store_message(message: str) -> StoreResult:
    created_at = datetime.now(timezone.utc).isoformat()
    item: SampleMessagesItem = {
        "app_name": APP_NAME,
        "message_id": f"{created_at}#{uuid.uuid4()}",
        "created_at": created_at,
        "message": message,
    }
    if not os.environ.get("AWS_EXECUTION_ENV"):
        return StoreResult(False, item)

    put_sample_messages(item)
    return StoreResult(True, item)


def _list_messages(limit: int, next_key: dict[str, Any] | None) -> dict[str, Any]:
    if not os.environ.get("AWS_EXECUTION_ENV"):
        return {"messages": [], "nextKey": None}

    page = query_sample_messages_by_message_id_range_page(
        APP_NAME,
        exclusive_start_key=next_key,
        scan_index_forward=False,
        consistent_read=True,
        limit=limit,
    )
    return {
        "messages": [_format_message(item) for item in page["items"]],
        "nextKey": page["next_key"],
    }


def lambda_handler(event: dict[str, Any] | None, context: object | None = None) -> dict[str, Any]:
    """Store or list sample messages."""
    _ = context
    payload = _payload_from_event(event)
    action = str(payload.get("action", "store_message"))

    if action == "list_messages":
        page = _list_messages(_parse_limit(payload.get("limit")), _parse_next_key(payload.get("nextKey")))
        return json_response(
            200,
            {
                "action": "list_messages",
                **page,
            },
        )

    if action != "store_message":
        return json_response(400, {"error": f"unsupported action: {action}"})

    message = str(payload.get("message", "")).strip()
    if not message:
        return json_response(400, {"error": "message is required"})

    store_result = _store_message(message)
    body = {
        "action": "store_message",
        "message": "message stored",
        "item": _format_message(store_result.item),
        "stored": store_result.stored,
    }
    return json_response(200, body)
