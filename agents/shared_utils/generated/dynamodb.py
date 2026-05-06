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
    patient_id: str
    patient_name: str
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


class ClinicIntegrationsItem(TypedDict):
    """Typed representation of a row in the clinic_integrations table."""

    account_email: str
    calendar_id: str
    calendar_sync_token: str
    clinic_id: str
    connected_at: str
    gmail_history_id: str
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


class ClinicPatientsItem(TypedDict):
    """Typed representation of a row in the clinic_patients table."""

    clinic_id: str
    email: str
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
        "patient_id": "String",
        "patient_name": "String",
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

CLINIC_INTEGRATIONS_TABLE: dict[str, Any] = {
    "attributes": {
        "account_email": "String",
        "calendar_id": "String",
        "calendar_sync_token": "String",
        "clinic_id": "String",
        "connected_at": "String",
        "gmail_history_id": "String",
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

CLINIC_PATIENTS_TABLE: dict[str, Any] = {
    "attributes": {
        "clinic_id": "String",
        "email": "String",
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
    "clinic_integrations": CLINIC_INTEGRATIONS_TABLE,
    "clinic_patients": CLINIC_PATIENTS_TABLE,
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



def put_clinic_integrations(
    item: ClinicIntegrationsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_INTEGRATIONS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


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



def put_clinic_patients(
    item: ClinicPatientsItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_PATIENTS_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


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



def put_clinic_schedule(
    item: ClinicScheduleItem,
    *,
    dynamodb_resource: Any | None = None,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _table(CLINIC_SCHEDULE_TABLE, dynamodb_resource).put_item(Item=dict(item)),
    )


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
