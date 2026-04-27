"""Generated DynamoDB helpers. Run `npm run codegen` to refresh."""

from __future__ import annotations

from typing import Any

SAMPLE_MESSAGES_TABLE: dict[str, Any] = {
    "attributes": {
        "app_name": 'S',
        "created_at": 'S',
        "message": 'S',
        "message_id": 'S',
    },
    "owner_agent": 'sample_agent',
    "partition_key": {
        "name": 'app_name',
        "type": 'S',
    },
    "sort_key": {
        "name": 'message_id',
        "type": 'S',
    },
    "table_name": 'sample_messages',
}

TABLES: dict[str, dict[str, Any]] = {
    "sample_messages": SAMPLE_MESSAGES_TABLE,
}
