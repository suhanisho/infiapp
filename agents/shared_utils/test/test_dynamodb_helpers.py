"""Tests for generated DynamoDB table helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

SHARED_UTILS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED_UTILS_DIR))

from generated.dynamodb import (  # noqa: E402
    SampleMessagesItem,
    delete_sample_messages,
    get_sample_messages,
    put_sample_messages,
    query_sample_messages_by_message_id_range,
    query_sample_messages_by_message_id_range_page,
    query_sample_messages_item,
)


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.last_query_args: dict[str, Any] = {}

    def put_item(self, Item: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        self.items[(Item["app_name"], Item["message_id"])] = dict(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        item = self.items.get((Key["app_name"], Key["message_id"]))
        return {"Item": dict(item)} if item else {}

    def delete_item(self, Key: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        self.items.pop((Key["app_name"], Key["message_id"]), None)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.last_query_args = kwargs
        response: dict[str, Any] = {"Items": list(self.items.values())}
        if kwargs.get("Limit") == 1:
            response["LastEvaluatedKey"] = {
                "app_name": "infiapp",
                "message_id": "message-1",
            }
        return response


class FakeDynamoDBResource:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def Table(self, table_name: str) -> FakeTable:  # noqa: N802
        return self.tables.setdefault(table_name, FakeTable())


class GeneratedDynamoDBHelpersTest(unittest.TestCase):
    def test_put_get_delete_sample_messages(self) -> None:
        dynamodb = FakeDynamoDBResource()
        item: SampleMessagesItem = {
            "app_name": "infiapp",
            "message_id": "message-1",
            "created_at": "2026-04-27T00:00:00+00:00",
            "message": "hello",
        }

        put_sample_messages(item, dynamodb_resource=dynamodb)

        loaded_item = get_sample_messages("infiapp", "message-1", dynamodb_resource=dynamodb)
        self.assertEqual(loaded_item["message"] if loaded_item else None, "hello")
        queried_item = query_sample_messages_item("infiapp", "message-1", dynamodb_resource=dynamodb)
        self.assertEqual(queried_item["message"] if queried_item else None, "hello")

        delete_sample_messages("infiapp", "message-1", dynamodb_resource=dynamodb)
        self.assertIsNone(get_sample_messages("infiapp", "message-1", dynamodb_resource=dynamodb))

    def test_query_sample_messages_by_message_id_range_passes_query_options(self) -> None:
        dynamodb = FakeDynamoDBResource()
        put_sample_messages(
            {
                "app_name": "infiapp",
                "message_id": "message-1",
                "created_at": "2026-04-27T00:00:00+00:00",
                "message": "latest",
            },
            dynamodb_resource=dynamodb,
        )

        items = query_sample_messages_by_message_id_range(
            "infiapp",
            start_message_id="message-0",
            end_message_id="message-9",
            dynamodb_resource=dynamodb,
            scan_index_forward=False,
            consistent_read=True,
            limit=1,
        )

        table = dynamodb.Table("sample_messages")
        self.assertEqual(items[0]["message"], "latest")
        self.assertFalse(table.last_query_args["ScanIndexForward"])
        self.assertTrue(table.last_query_args["ConsistentRead"])
        self.assertEqual(table.last_query_args["Limit"], 1)

    def test_query_sample_messages_by_message_id_range_page_returns_next_key(self) -> None:
        dynamodb = FakeDynamoDBResource()
        put_sample_messages(
            {
                "app_name": "infiapp",
                "message_id": "message-1",
                "created_at": "2026-04-27T00:00:00+00:00",
                "message": "latest",
            },
            dynamodb_resource=dynamodb,
        )

        page = query_sample_messages_by_message_id_range_page(
            "infiapp",
            exclusive_start_key={"app_name": "infiapp", "message_id": "message-0"},
            dynamodb_resource=dynamodb,
            limit=1,
        )

        table = dynamodb.Table("sample_messages")
        self.assertEqual(page["items"][0]["message"], "latest")
        self.assertEqual(page["next_key"], {"app_name": "infiapp", "message_id": "message-1"})
        self.assertEqual(
            table.last_query_args["ExclusiveStartKey"],
            {"app_name": "infiapp", "message_id": "message-0"},
        )


if __name__ == "__main__":
    unittest.main()
