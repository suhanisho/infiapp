"""Tests for generated DynamoDB table helpers."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

SHARED_UTILS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED_UTILS_DIR))


class FakeKey:
    def __init__(self, name: str) -> None:
        self.name = name

    def eq(self, value: object) -> "FakeKey":
        _ = value
        return self

    def between(self, start: object, end: object) -> "FakeKey":
        _ = start, end
        return self

    def gte(self, value: object) -> "FakeKey":
        _ = value
        return self

    def lte(self, value: object) -> "FakeKey":
        _ = value
        return self

    def __and__(self, other: object) -> "FakeKey":
        _ = other
        return self


fake_boto3 = types.ModuleType("boto3")
fake_dynamodb = types.ModuleType("boto3.dynamodb")
fake_conditions = types.ModuleType("boto3.dynamodb.conditions")
setattr(fake_conditions, "Key", FakeKey)
setattr(fake_dynamodb, "conditions", fake_conditions)
setattr(fake_boto3, "dynamodb", fake_dynamodb)
sys.modules.setdefault("boto3", fake_boto3)
sys.modules.setdefault("boto3.dynamodb", fake_dynamodb)
sys.modules.setdefault("boto3.dynamodb.conditions", fake_conditions)

from generated.dynamodb import (  # noqa: E402
    ClinicActionsItem,
    delete_clinic_actions,
    get_clinic_actions,
    put_clinic_actions,
    query_clinic_actions_by_action_id_range,
    query_clinic_actions_by_action_id_range_page,
    query_clinic_actions_item,
)


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.last_query_args: dict[str, Any] = {}

    def put_item(self, Item: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        self.items[(Item["clinic_id"], Item["action_id"])] = dict(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        item = self.items.get((Key["clinic_id"], Key["action_id"]))
        return {"Item": dict(item)} if item else {}

    def delete_item(self, Key: dict[str, Any]) -> dict[str, Any]:  # noqa: N803
        self.items.pop((Key["clinic_id"], Key["action_id"]), None)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.last_query_args = kwargs
        response: dict[str, Any] = {"Items": list(self.items.values())}
        if kwargs.get("Limit") == 1:
            response["LastEvaluatedKey"] = {
                "clinic_id": "shalini-clinic",
                "action_id": "act_001",
            }
        return response


class FakeDynamoDBResource:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def Table(self, table_name: str) -> FakeTable:  # noqa: N802
        return self.tables.setdefault(table_name, FakeTable())


class GeneratedDynamoDBHelpersTest(unittest.TestCase):
    def test_put_get_delete_clinic_actions(self) -> None:
        dynamodb = FakeDynamoDBResource()
        item: ClinicActionsItem = {
            "clinic_id": "shalini-clinic",
            "action_id": "act_001",
            "action_type": "enquiry",
            "approved_at": "",
            "approved_by": "",
            "completed_at": "",
            "completion_note": "",
            "created_at": "2026-04-27T00:00:00+00:00",
            "draft_message": "hello",
            "external_draft_id": "",
            "external_sent_message_id": "",
            "final_message": "",
            "metadata": {},
            "patient_id": "p10",
            "patient_name": "Rachel Davies",
            "patient_request_id": "seed-request-rachel-davies",
            "priority": "new",
            "source_message": "source",
            "source_message_id": "gmail-message-1",
            "source_provider": "gmail",
            "source_summary": "summary",
            "source_thread_id": "gmail-thread-1",
            "status": "needs_approval",
            "time_label": "9:41 AM",
            "updated_at": "2026-04-27T00:00:00+00:00",
        }

        put_clinic_actions(item, dynamodb_resource=dynamodb)

        loaded_item = get_clinic_actions("shalini-clinic", "act_001", dynamodb_resource=dynamodb)
        self.assertEqual(loaded_item["draft_message"] if loaded_item else None, "hello")
        queried_item = query_clinic_actions_item("shalini-clinic", "act_001", dynamodb_resource=dynamodb)
        self.assertEqual(queried_item["draft_message"] if queried_item else None, "hello")

        delete_clinic_actions("shalini-clinic", "act_001", dynamodb_resource=dynamodb)
        self.assertIsNone(get_clinic_actions("shalini-clinic", "act_001", dynamodb_resource=dynamodb))

    def test_query_clinic_actions_by_action_id_range_passes_query_options(self) -> None:
        dynamodb = FakeDynamoDBResource()
        put_clinic_actions(
            {
                "clinic_id": "shalini-clinic",
                "action_id": "act_001",
                "action_type": "enquiry",
                "approved_at": "",
                "approved_by": "",
                "completed_at": "",
                "completion_note": "",
                "created_at": "2026-04-27T00:00:00+00:00",
                "draft_message": "latest",
                "external_draft_id": "",
                "external_sent_message_id": "",
                "final_message": "",
                "metadata": {},
                "patient_id": "p10",
                "patient_name": "Rachel Davies",
                "patient_request_id": "seed-request-rachel-davies",
                "priority": "new",
                "source_message": "source",
                "source_message_id": "gmail-message-1",
                "source_provider": "gmail",
                "source_summary": "summary",
                "source_thread_id": "gmail-thread-1",
                "status": "needs_approval",
                "time_label": "9:41 AM",
                "updated_at": "2026-04-27T00:00:00+00:00",
            },
            dynamodb_resource=dynamodb,
        )

        items = query_clinic_actions_by_action_id_range(
            "shalini-clinic",
            start_action_id="act_000",
            end_action_id="act_999",
            dynamodb_resource=dynamodb,
            scan_index_forward=False,
            consistent_read=True,
            limit=1,
        )

        table = dynamodb.Table("clinic_actions")
        self.assertEqual(items[0]["draft_message"], "latest")
        self.assertFalse(table.last_query_args["ScanIndexForward"])
        self.assertTrue(table.last_query_args["ConsistentRead"])
        self.assertEqual(table.last_query_args["Limit"], 1)

    def test_query_clinic_actions_by_action_id_range_page_returns_next_key(self) -> None:
        dynamodb = FakeDynamoDBResource()
        put_clinic_actions(
            {
                "clinic_id": "shalini-clinic",
                "action_id": "act_001",
                "action_type": "enquiry",
                "approved_at": "",
                "approved_by": "",
                "completed_at": "",
                "completion_note": "",
                "created_at": "2026-04-27T00:00:00+00:00",
                "draft_message": "latest",
                "external_draft_id": "",
                "external_sent_message_id": "",
                "final_message": "",
                "metadata": {},
                "patient_id": "p10",
                "patient_name": "Rachel Davies",
                "patient_request_id": "seed-request-rachel-davies",
                "priority": "new",
                "source_message": "source",
                "source_message_id": "gmail-message-1",
                "source_provider": "gmail",
                "source_summary": "summary",
                "source_thread_id": "gmail-thread-1",
                "status": "needs_approval",
                "time_label": "9:41 AM",
                "updated_at": "2026-04-27T00:00:00+00:00",
            },
            dynamodb_resource=dynamodb,
        )

        page = query_clinic_actions_by_action_id_range_page(
            "shalini-clinic",
            exclusive_start_key={"clinic_id": "shalini-clinic", "action_id": "act_000"},
            dynamodb_resource=dynamodb,
            limit=1,
        )

        table = dynamodb.Table("clinic_actions")
        self.assertEqual(page["items"][0]["draft_message"], "latest")
        self.assertEqual(page["next_key"], {"clinic_id": "shalini-clinic", "action_id": "act_001"})
        self.assertEqual(
            table.last_query_args["ExclusiveStartKey"],
            {"clinic_id": "shalini-clinic", "action_id": "act_000"},
        )


if __name__ == "__main__":
    unittest.main()
