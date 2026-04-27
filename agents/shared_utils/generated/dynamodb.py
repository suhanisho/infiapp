"""Generated DynamoDB helpers. Run `npm run codegen` to refresh."""

from __future__ import annotations

from typing import Any

INFILOOP_HELLO_CALLS_TABLE: dict[str, Any] = {
    "attributes": {
        "agent_name": 'S',
        "call_id": 'S',
        "created_at": 'S',
        "message": 'S',
    },
    "owner_agent": 'hello_agent',
    "partition_key": {
        "name": 'agent_name',
        "type": 'S',
    },
    "sort_key": {
        "name": 'call_id',
        "type": 'S',
    },
    "table_name": 'infiloop_hello_calls',
}

INFILOOP_USER_MESSAGES_TABLE: dict[str, Any] = {
    "attributes": {
        "app_name": 'S',
        "created_at": 'S',
        "message": 'S',
        "message_id": 'S',
    },
    "owner_agent": 'hello_agent',
    "partition_key": {
        "name": 'app_name',
        "type": 'S',
    },
    "sort_key": {
        "name": 'message_id',
        "type": 'S',
    },
    "table_name": 'infiloop_user_messages',
}

TABLES: dict[str, dict[str, Any]] = {
    "infiloop_hello_calls": INFILOOP_HELLO_CALLS_TABLE,
    "infiloop_user_messages": INFILOOP_USER_MESSAGES_TABLE,
}
