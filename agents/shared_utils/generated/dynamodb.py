"""Generated DynamoDB helpers. Run `python -m repo_tools codegen` to refresh."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict, cast

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


class ClinicActionsItem(TypedDict):
    """Typed representation of a row in the clinic_actions table."""

    action_id: str
    action_type: str
    approved_at: str
    approved_by: str
    clinic_id: str
    completed_at: str
    completion_note: str
    created_at: str
    draft_message: str
    external_draft_id: str
    external_sent_message_id: str
    final_message: str
    metadata: dict[str, Any]
    patient_id: str
    patient_name: str
    patient_request_id: str
    priority: str
    source_message: str
    source_message_id: str
    source_provider: str
    source_summary: str
    source_thread_id: str
    status: str
    time_label: str
    updated_at: str


class ClinicActionsPage(TypedDict):
    """Paginated query result for the clinic_actions table."""

    items: list[ClinicActionsItem]
    next_key: dict[str, Any] | None


class ClinicConversationsItem(TypedDict):
    """Typed representation of a row in the clinic_conversations table."""

    conversation_id: str
    created_at: str
    latest_classification: str
    latest_draft_revision_id: str
    latest_message_at: str
    latest_message_direction: str
    latest_message_excerpt: str
    latest_message_id: str
    latest_message_sort_key: str
    patient_email: str
    patient_id: str
    patient_name: str
    patient_request_id: str
    practice_id: str
    requires_doctor_review: bool
    source_provider: str
    source_thread_id: str
    status: str
    subject: str
    updated_at: str


class ClinicConversationsPage(TypedDict):
    """Paginated query result for the clinic_conversations table."""

    items: list[ClinicConversationsItem]
    next_key: dict[str, Any] | None


class ClinicDraftRevisionsItem(TypedDict):
    """Typed representation of a row in the clinic_draft_revisions table."""

    availability_windows: list[Any]
    classification: str
    conversation_id: str
    created_at: str
    draft_body: str
    draft_revision_id: str
    llm_model: str
    llm_status: str
    practice_conversation_id: str
    practice_id: str
    referenced_slot_ids: list[Any]
    request_constraints: dict[str, Any]
    source_message_id: str
    status: str


class ClinicDraftRevisionsPage(TypedDict):
    """Paginated query result for the clinic_draft_revisions table."""

    items: list[ClinicDraftRevisionsItem]
    next_key: dict[str, Any] | None


class ClinicEmailMessagesItem(TypedDict):
    """Typed representation of a row in the clinic_email_messages table."""

    body_excerpt: str
    classification: str
    direction: str
    from_email: str
    from_name: str
    gmail_message_id: str
    gmail_thread_id: str
    in_reply_to: str
    message_id_header: str
    message_signature: str
    patient_id: str
    patient_request_id: str
    practice_id: str
    processed_at: str
    received_at: str
    references: str
    source_provider: str
    subject: str
    to_email: str


class ClinicEmailMessagesPage(TypedDict):
    """Paginated query result for the clinic_email_messages table."""

    items: list[ClinicEmailMessagesItem]
    next_key: dict[str, Any] | None


class ClinicIntegrationsItem(TypedDict):
    """Typed representation of a row in the clinic_integrations table."""

    account_email: str
    calendar_id: str
    calendar_sync_token: str
    clinic_id: str
    connected_at: str
    gmail_history_id: str
    gmail_import_estimated_total: int | float
    gmail_import_page_token: str
    gmail_import_processed_count: int | float
    gmail_import_started_at: str
    gmail_import_status: str
    integration_id: str
    last_error: str
    last_sync_at: str
    provider: str
    required_scopes: list[Any]
    status: str
    token_secret_id: str
    updated_at: str
    write_mode: str


class ClinicIntegrationsPage(TypedDict):
    """Paginated query result for the clinic_integrations table."""

    items: list[ClinicIntegrationsItem]
    next_key: dict[str, Any] | None


class ClinicPatientRequestsItem(TypedDict):
    """Typed representation of a row in the clinic_patient_requests table."""

    appointment_type: str
    approved_at: str
    approved_by: str
    completed_at: str
    completion_note: str
    created_at: str
    draft_message: str
    duration_minutes: int | float
    final_message: str
    intent: str
    patient_email: str
    patient_emotional_tone: str
    patient_id: str
    patient_name: str
    patient_request_id: str
    practice_id: str
    proposed_windows: list[Any]
    request_constraints: dict[str, Any]
    request_type: str
    requires_doctor_review: bool
    risk_level: str
    source_excerpt: str
    source_message_id: str
    source_provider: str
    source_subject: str
    source_summary: str
    source_thread_id: str
    status: str
    suggested_next_action: str
    time_label: str
    triage_category: str
    triage_confidence: int | float
    triage_reason: str
    updated_at: str
    urgency_level: str


class ClinicPatientRequestsPage(TypedDict):
    """Paginated query result for the clinic_patient_requests table."""

    items: list[ClinicPatientRequestsItem]
    next_key: dict[str, Any] | None


class ClinicPatientsItem(TypedDict):
    """Typed representation of a row in the clinic_patients table."""

    clinic_id: str
    email: str
    gestation_age: str
    last_visit: str
    name: str
    next_appt: str
    notes: str
    patient_id: str
    phone: str
    status: str
    visits: int | float


class ClinicPatientsPage(TypedDict):
    """Paginated query result for the clinic_patients table."""

    items: list[ClinicPatientsItem]
    next_key: dict[str, Any] | None


class ClinicPracticeMembersItem(TypedDict):
    """Typed representation of a row in the clinic_practice_members table."""

    auth_provider: str
    created_at: str
    display_name: str
    last_login_at: str
    member_email: str
    member_id: str
    practice_id: str
    role: str
    status: str
    updated_at: str


class ClinicPracticeMembersPage(TypedDict):
    """Paginated query result for the clinic_practice_members table."""

    items: list[ClinicPracticeMembersItem]
    next_key: dict[str, Any] | None


class ClinicScheduleItem(TypedDict):
    """Typed representation of a row in the clinic_schedule table."""

    appointment_type: str
    clinic_id: str
    day_key: str
    day_label: str
    day_type: str
    end_at: str
    end_time: str
    event_id: str
    external_calendar_id: str
    external_etag: str
    external_event_id: str
    last_synced_at: str
    patient_id: str
    patient_name: str
    sort_order: int | float
    source_provider: str
    start_at: str
    start_time: str
    status: str


class ClinicSchedulePage(TypedDict):
    """Paginated query result for the clinic_schedule table."""

    items: list[ClinicScheduleItem]
    next_key: dict[str, Any] | None


class ClinicSettingsItem(TypedDict):
    """Typed representation of a row in the clinic_settings table."""

    clinic_id: str
    data: dict[str, Any]
    setting_id: str
    updated_at: str


class ClinicSettingsPage(TypedDict):
    """Paginated query result for the clinic_settings table."""

    items: list[ClinicSettingsItem]
    next_key: dict[str, Any] | None

CLINIC_ACTIONS_TABLE: dict[str, Any] = {
    "attributes": {
        "action_id": "String",
        "action_type": "String",
        "approved_at": "String",
        "approved_by": "String",
        "clinic_id": "String",
        "completed_at": "String",
        "completion_note": "String",
        "created_at": "String",
        "draft_message": "String",
        "external_draft_id": "String",
        "external_sent_message_id": "String",
        "final_message": "String",
        "metadata": "Map",
        "patient_id": "String",
        "patient_name": "String",
        "patient_request_id": "String",
        "priority": "String",
        "source_message": "String",
        "source_message_id": "String",
        "source_provider": "String",
        "source_summary": "String",
        "source_thread_id": "String",
        "status": "String",
        "time_label": "String",
        "updated_at": "String",
    },
    "partition_key": {
        "name": "clinic_id",
        "type": "String",
    },
    "sort_key": {
        "name": "action_id",
        "type": "String",
    },
    "table_name": "clinic_actions",
}

CLINIC_CONVERSATIONS_TABLE: dict[str, Any] = {
    "attributes": {
        "conversation_id": "String",
        "created_at": "String",
        "latest_classification": "String",
        "latest_draft_revision_id": "String",
        "latest_message_at": "String",
        "latest_message_direction": "String",
        "latest_message_excerpt": "String",
        "latest_message_id": "String",
        "latest_message_sort_key": "String",
        "patient_email": "String",
        "patient_id": "String",
        "patient_name": "String",
        "patient_request_id": "String",
        "practice_id": "String",
        "requires_doctor_review": "Boolean",
        "source_provider": "String",
        "source_thread_id": "String",
        "status": "String",
        "subject": "String",
        "updated_at": "String",
    },
    "partition_key": {
        "name": "practice_id",
        "type": "String",
    },
    "sort_key": {
        "name": "conversation_id",
        "type": "String",
    },
    "table_name": "clinic_conversations",
}

CLINIC_DRAFT_REVISIONS_TABLE: dict[str, Any] = {
    "attributes": {
        "availability_windows": "List",
        "classification": "String",
        "conversation_id": "String",
        "created_at": "String",
        "draft_body": "String",
        "draft_revision_id": "String",
        "llm_model": "String",
        "llm_status": "String",
        "practice_conversation_id": "String",
        "practice_id": "String",
        "referenced_slot_ids": "List",
        "request_constraints": "Map",
        "source_message_id": "String",
        "status": "String",
    },
    "partition_key": {
        "name": "practice_conversation_id",
        "type": "String",
    },
    "sort_key": {
        "name": "draft_revision_id",
        "type": "String",
    },
    "table_name": "clinic_draft_revisions",
}

CLINIC_EMAIL_MESSAGES_TABLE: dict[str, Any] = {
    "attributes": {
        "body_excerpt": "String",
        "classification": "String",
        "direction": "String",
        "from_email": "String",
        "from_name": "String",
        "gmail_message_id": "String",
        "gmail_thread_id": "String",
        "in_reply_to": "String",
        "message_id_header": "String",
        "message_signature": "String",
        "patient_id": "String",
        "patient_request_id": "String",
        "practice_id": "String",
        "processed_at": "String",
        "received_at": "String",
        "references": "String",
        "source_provider": "String",
        "subject": "String",
        "to_email": "String",
    },
    "partition_key": {
        "name": "practice_id",
        "type": "String",
    },
    "sort_key": {
        "name": "gmail_message_id",
        "type": "String",
    },
    "table_name": "clinic_email_messages",
}

CLINIC_INTEGRATIONS_TABLE: dict[str, Any] = {
    "attributes": {
        "account_email": "String",
        "calendar_id": "String",
        "calendar_sync_token": "String",
        "clinic_id": "String",
        "connected_at": "String",
        "gmail_history_id": "String",
        "gmail_import_estimated_total": "Number",
        "gmail_import_page_token": "String",
        "gmail_import_processed_count": "Number",
        "gmail_import_started_at": "String",
        "gmail_import_status": "String",
        "integration_id": "String",
        "last_error": "String",
        "last_sync_at": "String",
        "provider": "String",
        "required_scopes": "List",
        "status": "String",
        "token_secret_id": "String",
        "updated_at": "String",
        "write_mode": "String",
    },
    "partition_key": {
        "name": "clinic_id",
        "type": "String",
    },
    "sort_key": {
        "name": "integration_id",
        "type": "String",
    },
    "table_name": "clinic_integrations",
}

CLINIC_PATIENT_REQUESTS_TABLE: dict[str, Any] = {
    "attributes": {
        "appointment_type": "String",
        "approved_at": "String",
        "approved_by": "String",
        "completed_at": "String",
        "completion_note": "String",
        "created_at": "String",
        "draft_message": "String",
        "duration_minutes": "Number",
        "final_message": "String",
        "intent": "String",
        "patient_email": "String",
        "patient_emotional_tone": "String",
        "patient_id": "String",
        "patient_name": "String",
        "patient_request_id": "String",
        "practice_id": "String",
        "proposed_windows": "List",
        "request_constraints": "Map",
        "request_type": "String",
        "requires_doctor_review": "Boolean",
        "risk_level": "String",
        "source_excerpt": "String",
        "source_message_id": "String",
        "source_provider": "String",
        "source_subject": "String",
        "source_summary": "String",
        "source_thread_id": "String",
        "status": "String",
        "suggested_next_action": "String",
        "time_label": "String",
        "triage_category": "String",
        "triage_confidence": "Number",
        "triage_reason": "String",
        "updated_at": "String",
        "urgency_level": "String",
    },
    "partition_key": {
        "name": "practice_id",
        "type": "String",
    },
    "sort_key": {
        "name": "patient_request_id",
        "type": "String",
    },
    "table_name": "clinic_patient_requests",
}

CLINIC_PATIENTS_TABLE: dict[str, Any] = {
    "attributes": {
        "clinic_id": "String",
        "email": "String",
        "gestation_age": "String",
        "last_visit": "String",
        "name": "String",
        "next_appt": "String",
        "notes": "String",
        "patient_id": "String",
        "phone": "String",
        "status": "String",
        "visits": "Number",
    },
    "partition_key": {
        "name": "clinic_id",
        "type": "String",
    },
    "sort_key": {
        "name": "patient_id",
        "type": "String",
    },
    "table_name": "clinic_patients",
}

CLINIC_PRACTICE_MEMBERS_TABLE: dict[str, Any] = {
    "attributes": {
        "auth_provider": "String",
        "created_at": "String",
        "display_name": "String",
        "last_login_at": "String",
        "member_email": "String",
        "member_id": "String",
        "practice_id": "String",
        "role": "String",
        "status": "String",
        "updated_at": "String",
    },
    "partition_key": {
        "name": "practice_id",
        "type": "String",
    },
    "sort_key": {
        "name": "member_email",
        "type": "String",
    },
    "table_name": "clinic_practice_members",
}

CLINIC_SCHEDULE_TABLE: dict[str, Any] = {
    "attributes": {
        "appointment_type": "String",
        "clinic_id": "String",
        "day_key": "String",
        "day_label": "String",
        "day_type": "String",
        "end_at": "String",
        "end_time": "String",
        "event_id": "String",
        "external_calendar_id": "String",
        "external_etag": "String",
        "external_event_id": "String",
        "last_synced_at": "String",
        "patient_id": "String",
        "patient_name": "String",
        "sort_order": "Number",
        "source_provider": "String",
        "start_at": "String",
        "start_time": "String",
        "status": "String",
    },
    "partition_key": {
        "name": "clinic_id",
        "type": "String",
    },
    "sort_key": {
        "name": "event_id",
        "type": "String",
    },
    "table_name": "clinic_schedule",
}

CLINIC_SETTINGS_TABLE: dict[str, Any] = {
    "attributes": {
        "clinic_id": "String",
        "data": "Map",
        "setting_id": "String",
        "updated_at": "String",
    },
    "partition_key": {
        "name": "clinic_id",
        "type": "String",
    },
    "sort_key": {
        "name": "setting_id",
        "type": "String",
    },
    "table_name": "clinic_settings",
}

TABLES: dict[str, dict[str, Any]] = {
    "clinic_actions": CLINIC_ACTIONS_TABLE,
    "clinic_conversations": CLINIC_CONVERSATIONS_TABLE,
    "clinic_draft_revisions": CLINIC_DRAFT_REVISIONS_TABLE,
    "clinic_email_messages": CLINIC_EMAIL_MESSAGES_TABLE,
    "clinic_integrations": CLINIC_INTEGRATIONS_TABLE,
    "clinic_patient_requests": CLINIC_PATIENT_REQUESTS_TABLE,
    "clinic_patients": CLINIC_PATIENTS_TABLE,
    "clinic_practice_members": CLINIC_PRACTICE_MEMBERS_TABLE,
    "clinic_schedule": CLINIC_SCHEDULE_TABLE,
    "clinic_settings": CLINIC_SETTINGS_TABLE,
}


def put_clinic_actions(
    item: ClinicActionsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_ACTIONS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_actions_if_absent(
    item: ClinicActionsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "clinic_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "action_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_ACTIONS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_actions_if_newer(
    item: ClinicActionsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_actions item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_ACTIONS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_actions(
    clinic_id: Any,
    action_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicActionsItem | None:
    response = _table(
        CLINIC_ACTIONS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_ACTIONS_TABLE,
            clinic_id,
            action_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicActionsItem, item) if isinstance(item, dict) else None


def query_clinic_actions_item(
    clinic_id: Any,
    action_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicActionsItem | None:
    return get_clinic_actions(
        clinic_id,
        action_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_actions(
    clinic_id: Any,
    action_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_ACTIONS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_ACTIONS_TABLE,
                clinic_id,
                action_id,
            )
        ),
    )


def query_clinic_actions_by_action_id_range_page(
    clinic_id: Any,
    *,
    start_action_id: Any | None = None,
    end_action_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicActionsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("clinic_id").eq(clinic_id)
    if start_action_id is not None and end_action_id is not None:
        key_condition = key_condition & Key("action_id").between(start_action_id, end_action_id)
    elif start_action_id is not None:
        key_condition = key_condition & Key("action_id").gte(start_action_id)
    elif end_action_id is not None:
        key_condition = key_condition & Key("action_id").lte(end_action_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_ACTIONS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicActionsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_actions_by_action_id_range(
    clinic_id: Any,
    *,
    start_action_id: Any | None = None,
    end_action_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicActionsItem]:
    return query_clinic_actions_by_action_id_range_page(
        clinic_id,
        start_action_id=start_action_id,
        end_action_id=end_action_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_actions(
    clinic_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicActionsItem]:
    return query_clinic_actions_by_action_id_range(
        clinic_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_conversations(
    item: ClinicConversationsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_CONVERSATIONS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_conversations_if_absent(
    item: ClinicConversationsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "practice_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "conversation_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_CONVERSATIONS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_conversations_if_newer(
    item: ClinicConversationsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_conversations item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_CONVERSATIONS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_conversations(
    practice_id: Any,
    conversation_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicConversationsItem | None:
    response = _table(
        CLINIC_CONVERSATIONS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_CONVERSATIONS_TABLE,
            practice_id,
            conversation_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicConversationsItem, item) if isinstance(item, dict) else None


def query_clinic_conversations_item(
    practice_id: Any,
    conversation_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicConversationsItem | None:
    return get_clinic_conversations(
        practice_id,
        conversation_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_conversations(
    practice_id: Any,
    conversation_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_CONVERSATIONS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_CONVERSATIONS_TABLE,
                practice_id,
                conversation_id,
            )
        ),
    )


def query_clinic_conversations_by_conversation_id_range_page(
    practice_id: Any,
    *,
    start_conversation_id: Any | None = None,
    end_conversation_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicConversationsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("practice_id").eq(practice_id)
    if start_conversation_id is not None and end_conversation_id is not None:
        key_condition = key_condition & Key("conversation_id").between(start_conversation_id, end_conversation_id)
    elif start_conversation_id is not None:
        key_condition = key_condition & Key("conversation_id").gte(start_conversation_id)
    elif end_conversation_id is not None:
        key_condition = key_condition & Key("conversation_id").lte(end_conversation_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_CONVERSATIONS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicConversationsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_conversations_by_conversation_id_range(
    practice_id: Any,
    *,
    start_conversation_id: Any | None = None,
    end_conversation_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicConversationsItem]:
    return query_clinic_conversations_by_conversation_id_range_page(
        practice_id,
        start_conversation_id=start_conversation_id,
        end_conversation_id=end_conversation_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_conversations(
    practice_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicConversationsItem]:
    return query_clinic_conversations_by_conversation_id_range(
        practice_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_draft_revisions(
    item: ClinicDraftRevisionsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_DRAFT_REVISIONS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_draft_revisions_if_absent(
    item: ClinicDraftRevisionsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "practice_conversation_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "draft_revision_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_DRAFT_REVISIONS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_draft_revisions_if_newer(
    item: ClinicDraftRevisionsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_draft_revisions item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_DRAFT_REVISIONS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_draft_revisions(
    practice_conversation_id: Any,
    draft_revision_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicDraftRevisionsItem | None:
    response = _table(
        CLINIC_DRAFT_REVISIONS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_DRAFT_REVISIONS_TABLE,
            practice_conversation_id,
            draft_revision_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicDraftRevisionsItem, item) if isinstance(item, dict) else None


def query_clinic_draft_revisions_item(
    practice_conversation_id: Any,
    draft_revision_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicDraftRevisionsItem | None:
    return get_clinic_draft_revisions(
        practice_conversation_id,
        draft_revision_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_draft_revisions(
    practice_conversation_id: Any,
    draft_revision_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_DRAFT_REVISIONS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_DRAFT_REVISIONS_TABLE,
                practice_conversation_id,
                draft_revision_id,
            )
        ),
    )


def query_clinic_draft_revisions_by_draft_revision_id_range_page(
    practice_conversation_id: Any,
    *,
    start_draft_revision_id: Any | None = None,
    end_draft_revision_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicDraftRevisionsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("practice_conversation_id").eq(practice_conversation_id)
    if start_draft_revision_id is not None and end_draft_revision_id is not None:
        key_condition = key_condition & Key("draft_revision_id").between(start_draft_revision_id, end_draft_revision_id)
    elif start_draft_revision_id is not None:
        key_condition = key_condition & Key("draft_revision_id").gte(start_draft_revision_id)
    elif end_draft_revision_id is not None:
        key_condition = key_condition & Key("draft_revision_id").lte(end_draft_revision_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_DRAFT_REVISIONS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicDraftRevisionsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_draft_revisions_by_draft_revision_id_range(
    practice_conversation_id: Any,
    *,
    start_draft_revision_id: Any | None = None,
    end_draft_revision_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicDraftRevisionsItem]:
    return query_clinic_draft_revisions_by_draft_revision_id_range_page(
        practice_conversation_id,
        start_draft_revision_id=start_draft_revision_id,
        end_draft_revision_id=end_draft_revision_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_draft_revisions(
    practice_conversation_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicDraftRevisionsItem]:
    return query_clinic_draft_revisions_by_draft_revision_id_range(
        practice_conversation_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_email_messages(
    item: ClinicEmailMessagesItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_EMAIL_MESSAGES_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_email_messages_if_absent(
    item: ClinicEmailMessagesItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "practice_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "gmail_message_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_EMAIL_MESSAGES_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_email_messages_if_newer(
    item: ClinicEmailMessagesItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_email_messages item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_EMAIL_MESSAGES_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_email_messages(
    practice_id: Any,
    gmail_message_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicEmailMessagesItem | None:
    response = _table(
        CLINIC_EMAIL_MESSAGES_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_EMAIL_MESSAGES_TABLE,
            practice_id,
            gmail_message_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicEmailMessagesItem, item) if isinstance(item, dict) else None


def query_clinic_email_messages_item(
    practice_id: Any,
    gmail_message_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicEmailMessagesItem | None:
    return get_clinic_email_messages(
        practice_id,
        gmail_message_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_email_messages(
    practice_id: Any,
    gmail_message_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_EMAIL_MESSAGES_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_EMAIL_MESSAGES_TABLE,
                practice_id,
                gmail_message_id,
            )
        ),
    )


def query_clinic_email_messages_by_gmail_message_id_range_page(
    practice_id: Any,
    *,
    start_gmail_message_id: Any | None = None,
    end_gmail_message_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicEmailMessagesPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("practice_id").eq(practice_id)
    if start_gmail_message_id is not None and end_gmail_message_id is not None:
        key_condition = key_condition & Key("gmail_message_id").between(start_gmail_message_id, end_gmail_message_id)
    elif start_gmail_message_id is not None:
        key_condition = key_condition & Key("gmail_message_id").gte(start_gmail_message_id)
    elif end_gmail_message_id is not None:
        key_condition = key_condition & Key("gmail_message_id").lte(end_gmail_message_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_EMAIL_MESSAGES_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicEmailMessagesItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_email_messages_by_gmail_message_id_range(
    practice_id: Any,
    *,
    start_gmail_message_id: Any | None = None,
    end_gmail_message_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicEmailMessagesItem]:
    return query_clinic_email_messages_by_gmail_message_id_range_page(
        practice_id,
        start_gmail_message_id=start_gmail_message_id,
        end_gmail_message_id=end_gmail_message_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_email_messages(
    practice_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicEmailMessagesItem]:
    return query_clinic_email_messages_by_gmail_message_id_range(
        practice_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_integrations(
    item: ClinicIntegrationsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_INTEGRATIONS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_integrations_if_absent(
    item: ClinicIntegrationsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "clinic_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "integration_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_INTEGRATIONS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_integrations_if_newer(
    item: ClinicIntegrationsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_integrations item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_INTEGRATIONS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_integrations(
    clinic_id: Any,
    integration_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicIntegrationsItem | None:
    response = _table(
        CLINIC_INTEGRATIONS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_INTEGRATIONS_TABLE,
            clinic_id,
            integration_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicIntegrationsItem, item) if isinstance(item, dict) else None


def query_clinic_integrations_item(
    clinic_id: Any,
    integration_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicIntegrationsItem | None:
    return get_clinic_integrations(
        clinic_id,
        integration_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_integrations(
    clinic_id: Any,
    integration_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_INTEGRATIONS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_INTEGRATIONS_TABLE,
                clinic_id,
                integration_id,
            )
        ),
    )


def query_clinic_integrations_by_integration_id_range_page(
    clinic_id: Any,
    *,
    start_integration_id: Any | None = None,
    end_integration_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicIntegrationsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("clinic_id").eq(clinic_id)
    if start_integration_id is not None and end_integration_id is not None:
        key_condition = key_condition & Key("integration_id").between(start_integration_id, end_integration_id)
    elif start_integration_id is not None:
        key_condition = key_condition & Key("integration_id").gte(start_integration_id)
    elif end_integration_id is not None:
        key_condition = key_condition & Key("integration_id").lte(end_integration_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_INTEGRATIONS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicIntegrationsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_integrations_by_integration_id_range(
    clinic_id: Any,
    *,
    start_integration_id: Any | None = None,
    end_integration_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicIntegrationsItem]:
    return query_clinic_integrations_by_integration_id_range_page(
        clinic_id,
        start_integration_id=start_integration_id,
        end_integration_id=end_integration_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_integrations(
    clinic_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicIntegrationsItem]:
    return query_clinic_integrations_by_integration_id_range(
        clinic_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_patient_requests(
    item: ClinicPatientRequestsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PATIENT_REQUESTS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_patient_requests_if_absent(
    item: ClinicPatientRequestsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "practice_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "patient_request_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_PATIENT_REQUESTS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_patient_requests_if_newer(
    item: ClinicPatientRequestsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_patient_requests item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_PATIENT_REQUESTS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_patient_requests(
    practice_id: Any,
    patient_request_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicPatientRequestsItem | None:
    response = _table(
        CLINIC_PATIENT_REQUESTS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_PATIENT_REQUESTS_TABLE,
            practice_id,
            patient_request_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicPatientRequestsItem, item) if isinstance(item, dict) else None


def query_clinic_patient_requests_item(
    practice_id: Any,
    patient_request_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicPatientRequestsItem | None:
    return get_clinic_patient_requests(
        practice_id,
        patient_request_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_patient_requests(
    practice_id: Any,
    patient_request_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PATIENT_REQUESTS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_PATIENT_REQUESTS_TABLE,
                practice_id,
                patient_request_id,
            )
        ),
    )


def query_clinic_patient_requests_by_patient_request_id_range_page(
    practice_id: Any,
    *,
    start_patient_request_id: Any | None = None,
    end_patient_request_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicPatientRequestsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("practice_id").eq(practice_id)
    if start_patient_request_id is not None and end_patient_request_id is not None:
        key_condition = key_condition & Key("patient_request_id").between(start_patient_request_id, end_patient_request_id)
    elif start_patient_request_id is not None:
        key_condition = key_condition & Key("patient_request_id").gte(start_patient_request_id)
    elif end_patient_request_id is not None:
        key_condition = key_condition & Key("patient_request_id").lte(end_patient_request_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_PATIENT_REQUESTS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicPatientRequestsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_patient_requests_by_patient_request_id_range(
    practice_id: Any,
    *,
    start_patient_request_id: Any | None = None,
    end_patient_request_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicPatientRequestsItem]:
    return query_clinic_patient_requests_by_patient_request_id_range_page(
        practice_id,
        start_patient_request_id=start_patient_request_id,
        end_patient_request_id=end_patient_request_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_patient_requests(
    practice_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicPatientRequestsItem]:
    return query_clinic_patient_requests_by_patient_request_id_range(
        practice_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_patients(
    item: ClinicPatientsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PATIENTS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_patients_if_absent(
    item: ClinicPatientsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "clinic_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "patient_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_PATIENTS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_patients_if_newer(
    item: ClinicPatientsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_patients item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_PATIENTS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_patients(
    clinic_id: Any,
    patient_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicPatientsItem | None:
    response = _table(
        CLINIC_PATIENTS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_PATIENTS_TABLE,
            clinic_id,
            patient_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicPatientsItem, item) if isinstance(item, dict) else None


def query_clinic_patients_item(
    clinic_id: Any,
    patient_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicPatientsItem | None:
    return get_clinic_patients(
        clinic_id,
        patient_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_patients(
    clinic_id: Any,
    patient_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PATIENTS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_PATIENTS_TABLE,
                clinic_id,
                patient_id,
            )
        ),
    )


def query_clinic_patients_by_patient_id_range_page(
    clinic_id: Any,
    *,
    start_patient_id: Any | None = None,
    end_patient_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicPatientsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("clinic_id").eq(clinic_id)
    if start_patient_id is not None and end_patient_id is not None:
        key_condition = key_condition & Key("patient_id").between(start_patient_id, end_patient_id)
    elif start_patient_id is not None:
        key_condition = key_condition & Key("patient_id").gte(start_patient_id)
    elif end_patient_id is not None:
        key_condition = key_condition & Key("patient_id").lte(end_patient_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_PATIENTS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicPatientsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_patients_by_patient_id_range(
    clinic_id: Any,
    *,
    start_patient_id: Any | None = None,
    end_patient_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicPatientsItem]:
    return query_clinic_patients_by_patient_id_range_page(
        clinic_id,
        start_patient_id=start_patient_id,
        end_patient_id=end_patient_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_patients(
    clinic_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicPatientsItem]:
    return query_clinic_patients_by_patient_id_range(
        clinic_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_practice_members(
    item: ClinicPracticeMembersItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PRACTICE_MEMBERS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_practice_members_if_absent(
    item: ClinicPracticeMembersItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "practice_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "member_email"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_PRACTICE_MEMBERS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_practice_members_if_newer(
    item: ClinicPracticeMembersItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_practice_members item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_PRACTICE_MEMBERS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_practice_members(
    practice_id: Any,
    member_email: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicPracticeMembersItem | None:
    response = _table(
        CLINIC_PRACTICE_MEMBERS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_PRACTICE_MEMBERS_TABLE,
            practice_id,
            member_email,
        )
    )
    item = response.get("Item")
    return cast(ClinicPracticeMembersItem, item) if isinstance(item, dict) else None


def query_clinic_practice_members_item(
    practice_id: Any,
    member_email: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicPracticeMembersItem | None:
    return get_clinic_practice_members(
        practice_id,
        member_email,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_practice_members(
    practice_id: Any,
    member_email: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PRACTICE_MEMBERS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_PRACTICE_MEMBERS_TABLE,
                practice_id,
                member_email,
            )
        ),
    )


def query_clinic_practice_members_by_member_email_range_page(
    practice_id: Any,
    *,
    start_member_email: Any | None = None,
    end_member_email: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicPracticeMembersPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("practice_id").eq(practice_id)
    if start_member_email is not None and end_member_email is not None:
        key_condition = key_condition & Key("member_email").between(start_member_email, end_member_email)
    elif start_member_email is not None:
        key_condition = key_condition & Key("member_email").gte(start_member_email)
    elif end_member_email is not None:
        key_condition = key_condition & Key("member_email").lte(end_member_email)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_PRACTICE_MEMBERS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicPracticeMembersItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_practice_members_by_member_email_range(
    practice_id: Any,
    *,
    start_member_email: Any | None = None,
    end_member_email: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicPracticeMembersItem]:
    return query_clinic_practice_members_by_member_email_range_page(
        practice_id,
        start_member_email=start_member_email,
        end_member_email=end_member_email,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_practice_members(
    practice_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicPracticeMembersItem]:
    return query_clinic_practice_members_by_member_email_range(
        practice_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_schedule(
    item: ClinicScheduleItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_SCHEDULE_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_schedule_if_absent(
    item: ClinicScheduleItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "clinic_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "event_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_SCHEDULE_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_schedule_if_newer(
    item: ClinicScheduleItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_schedule item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_SCHEDULE_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_schedule(
    clinic_id: Any,
    event_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicScheduleItem | None:
    response = _table(
        CLINIC_SCHEDULE_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_SCHEDULE_TABLE,
            clinic_id,
            event_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicScheduleItem, item) if isinstance(item, dict) else None


def query_clinic_schedule_item(
    clinic_id: Any,
    event_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicScheduleItem | None:
    return get_clinic_schedule(
        clinic_id,
        event_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_schedule(
    clinic_id: Any,
    event_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_SCHEDULE_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_SCHEDULE_TABLE,
                clinic_id,
                event_id,
            )
        ),
    )


def query_clinic_schedule_by_event_id_range_page(
    clinic_id: Any,
    *,
    start_event_id: Any | None = None,
    end_event_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicSchedulePage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("clinic_id").eq(clinic_id)
    if start_event_id is not None and end_event_id is not None:
        key_condition = key_condition & Key("event_id").between(start_event_id, end_event_id)
    elif start_event_id is not None:
        key_condition = key_condition & Key("event_id").gte(start_event_id)
    elif end_event_id is not None:
        key_condition = key_condition & Key("event_id").lte(end_event_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_SCHEDULE_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicScheduleItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_schedule_by_event_id_range(
    clinic_id: Any,
    *,
    start_event_id: Any | None = None,
    end_event_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicScheduleItem]:
    return query_clinic_schedule_by_event_id_range_page(
        clinic_id,
        start_event_id=start_event_id,
        end_event_id=end_event_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_schedule(
    clinic_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicScheduleItem]:
    return query_clinic_schedule_by_event_id_range(
        clinic_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )



def put_clinic_settings(
    item: ClinicSettingsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_SETTINGS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


def put_clinic_settings_if_absent(
    item: ClinicSettingsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> bool:
    expression_attribute_names = {"#partition_key": "clinic_id"}
    condition_expression = "attribute_not_exists(#partition_key)"
    expression_attribute_names["#sort_key"] = "setting_id"
    condition_expression += " AND attribute_not_exists(#sort_key)"
    try:
        _table(CLINIC_SETTINGS_TABLE, dynamodb_resource).put_item(
            Item=dict(item),
            ConditionExpression=condition_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_clinic_settings_if_newer(
    item: ClinicSettingsItem,
    *,
    ordering_attribute: str,
    dynamodb_resource: Any | None = None,
) -> bool:
    item_dict = dict(item)
    if ordering_attribute not in item_dict:
        raise ValueError(f"clinic_settings item does not contain {ordering_attribute}.")
    try:
        _table(CLINIC_SETTINGS_TABLE, dynamodb_resource).put_item(
            Item=item_dict,
            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",
            ExpressionAttributeNames={"#ordering": ordering_attribute},
            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},
        )
    except Exception as exc:
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, dict) else None
        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_clinic_settings(
    clinic_id: Any,
    setting_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicSettingsItem | None:
    response = _table(
        CLINIC_SETTINGS_TABLE,
        dynamodb_resource,
    ).get_item(
        Key=_build_key(
            CLINIC_SETTINGS_TABLE,
            clinic_id,
            setting_id,
        )
    )
    item = response.get("Item")
    return cast(ClinicSettingsItem, item) if isinstance(item, dict) else None


def query_clinic_settings_item(
    clinic_id: Any,
    setting_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> ClinicSettingsItem | None:
    return get_clinic_settings(
        clinic_id,
        setting_id,
        dynamodb_resource=dynamodb_resource,
    )


def delete_clinic_settings(
    clinic_id: Any,
    setting_id: Any,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_SETTINGS_TABLE, dynamodb_resource).delete_item(
            Key=_build_key(
                CLINIC_SETTINGS_TABLE,
                clinic_id,
                setting_id,
            )
        ),
    )


def query_clinic_settings_by_setting_id_range_page(
    clinic_id: Any,
    *,
    start_setting_id: Any | None = None,
    end_setting_id: Any | None = None,
    exclusive_start_key: Mapping[str, Any] | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> ClinicSettingsPage:
    from boto3.dynamodb.conditions import Key

    key_condition = Key("clinic_id").eq(clinic_id)
    if start_setting_id is not None and end_setting_id is not None:
        key_condition = key_condition & Key("setting_id").between(start_setting_id, end_setting_id)
    elif start_setting_id is not None:
        key_condition = key_condition & Key("setting_id").gte(start_setting_id)
    elif end_setting_id is not None:
        key_condition = key_condition & Key("setting_id").lte(end_setting_id)
    query_args: dict[str, Any] = {
        "KeyConditionExpression": key_condition,
        "ScanIndexForward": scan_index_forward,
        "ConsistentRead": consistent_read,
    }
    if exclusive_start_key is not None:
        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)
    if limit is not None:
        query_args["Limit"] = limit
    response = _table(CLINIC_SETTINGS_TABLE, dynamodb_resource).query(**query_args)
    next_key = response.get("LastEvaluatedKey")
    return {
        "items": [cast(ClinicSettingsItem, item) for item in response.get("Items", [])],
        "next_key": dict(next_key) if isinstance(next_key, dict) else None,
    }


def query_clinic_settings_by_setting_id_range(
    clinic_id: Any,
    *,
    start_setting_id: Any | None = None,
    end_setting_id: Any | None = None,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicSettingsItem]:
    return query_clinic_settings_by_setting_id_range_page(
        clinic_id,
        start_setting_id=start_setting_id,
        end_setting_id=end_setting_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )["items"]


def query_clinic_settings(
    clinic_id: Any,
    *,
    dynamodb_resource: Any | None = None,
    scan_index_forward: bool = True,
    consistent_read: bool = False,
    limit: int | None = None,
) -> list[ClinicSettingsItem]:
    return query_clinic_settings_by_setting_id_range(
        clinic_id,
        dynamodb_resource=dynamodb_resource,
        scan_index_forward=scan_index_forward,
        consistent_read=consistent_read,
        limit=limit,
    )
