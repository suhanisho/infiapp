"""Generated DynamoDB helpers. Run `python -m repo_tools codegen` to refresh."""

from __future__ import annotations

from typing import Any

SAMPLE_MESSAGES_TABLE: dict[str, Any] = {
    "attributes": {
        "app_name": 'String',
        "created_at": 'String',
        "message": 'String',
        "message_id": 'String',
    },
    "owner_agent": 'sample_agent',
    "partition_key": {
        "name": 'app_name',
        "type": 'String',
    },
    "sort_key": {
        "name": 'message_id',
        "type": 'String',
    },
    "table_name": 'sample_messages',
}

TABLES: dict[str, dict[str, Any]] = {
    "sample_messages": SAMPLE_MESSAGES_TABLE,
}
