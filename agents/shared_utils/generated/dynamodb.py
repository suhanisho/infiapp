"""Generated DynamoDB helpers. Run `python -m repo_tools codegen` to refresh."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_DYNAMODB_RESOURCE: Any | None = None


def _get_dynamodb_resource(dynamodb_resource: Any | None = None) -> Any:
    if dynamodb_resource is not None:
        return dynamodb_resource

    global _DYNAMODB_RESOURCE
    if _DYNAMODB_RESOURCE is None:
        import boto3

        _DYNAMODB_RESOURCE = boto3.resource("dynamodb")
    return _DYNAMODB_RESOURCE


def _table(table_definition: Mapping[str, Any], dynamodb_resource: Any | None = None) -> Any:
    return _get_dynamodb_resource(dynamodb_resource).Table(str(table_definition["table_name"]))


def _build_key(
    table_definition: Mapping[str, Any],
    partition_key_value: Any,
    sort_key_value: Any | None = None,
) -> dict[str, Any]:
    partition_key = table_definition["partition_key"]
    key = {str(partition_key["name"]): partition_key_value}
    sort_key = table_definition.get("sort_key")
    if sort_key:
        if sort_key_value is None:
            raise ValueError(f"{table_definition['table_name']} requires a sort key value.")
        key[str(sort_key["name"])] = sort_key_value
    elif sort_key_value is not None:
        raise ValueError(f"{table_definition['table_name']} does not have a sort key.")
    return key

SAMPLE_MESSAGES_TABLE: dict[str, Any] = {
    "attributes": {
        "app_name": "String",
        "created_at": "String",
        "message": "String",
        "message_id": "String",
    },
    "partition_key": {
        "name": "app_name",
        "type": "String",
    },
    "sort_key": {
        "name": "message_id",
        "type": "String",
    },
    "table_name": "sample_messages",
}

TABLES: dict[str, dict[str, Any]] = {
    "sample_messages": SAMPLE_MESSAGES_TABLE,
}


def put_sample_messages(
    item: Mapping[str, Any],
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return _table(SAMPLE_MESSAGES_TABLE, dynamodb_resource).put_item(Item=dict(item))


def get_sample_messages(
    app_name: Any,
    message_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any] | None:
    response = _table(
        SAMPLE_MESSAGES_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            SAMPLE_MESSAGES_TABLE,
            app_name,
            message_id,
        )
    )
    item = response.get("Item")
    return dict(item) if isinstance(item, dict) else None


def delete_sample_messages(
    app_name: Any,
    message_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return _table(SAMPLE_MESSAGES_TABLE, dynamodb_resource).delete_item(
        Key=_build_key(
            SAMPLE_MESSAGES_TABLE,
            app_name,
            message_id,
        )
    )


def query_sample_messages(
    app_name: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from boto3.dynamodb.conditions import Key

    query_args: dict[str, Any] = {
        "KeyConditionExpression": Key("app_name").eq(app_name),
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(SAMPLE_MESSAGES_TABLE, dynamodb_resource).query(**query_args)
    return [dict(item) for item in response.get("Items", [])]
