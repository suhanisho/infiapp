"""Persistence boundary for conversation summaries and immutable draft revisions."""

from __future__ import annotations

import hashlib
import re
from typing import TypedDict

from generated.dynamodb import (
    ClinicConversationsItem,
    ClinicDraftRevisionsItem,
    ClinicEmailMessagesItem,
    ClinicPatientRequestsItem,
    get_clinic_conversations,
    put_clinic_conversations_if_newer,
    put_clinic_draft_revisions_if_absent,
)


class ConversationPersistenceResult(TypedDict):
    """Outcome of projecting one immutable email into conversation storage."""

    conversation: ClinicConversationsItem
    conversation_updated: bool
    draft_revision: ClinicDraftRevisionsItem | None
    draft_revision_created: bool


def _safe_fragment(value: str) -> str:
    fragment = re.sub(r"[^A-Za-z0-9_.:@=-]+", "-", value).strip("-")
    if fragment:
        return fragment[:120]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def conversation_id_for_message(message: ClinicEmailMessagesItem) -> str:
    """Use the Gmail thread as the stable conversation boundary."""

    thread_id = message["gmail_thread_id"].strip()
    if thread_id:
        return f"gmail-thread-{_safe_fragment(thread_id)}"
    return f"gmail-message-{_safe_fragment(message['gmail_message_id'])}"


def _message_sort_key(message: ClinicEmailMessagesItem) -> str:
    return f"{message['received_at']}#{_safe_fragment(message['gmail_message_id'])}"


def _draft_revision_id(message: ClinicEmailMessagesItem) -> str:
    return f"{_message_sort_key(message)}#v1"


def _metadata_text(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""


def _draft_revision_item(
    *,
    request: ClinicPatientRequestsItem,
    message: ClinicEmailMessagesItem,
    conversation_id: str,
) -> ClinicDraftRevisionsItem | None:
    draft_body = request["draft_message"].strip()
    if not draft_body:
        return None

    constraints = dict(request["request_constraints"])
    return {
        "practice_conversation_id": f"{request['practice_id']}#{conversation_id}",
        "draft_revision_id": _draft_revision_id(message),
        "practice_id": request["practice_id"],
        "conversation_id": conversation_id,
        "source_message_id": message["gmail_message_id"],
        "classification": message["classification"],
        "request_constraints": constraints,
        "availability_windows": list(request["proposed_windows"]),
        "referenced_slot_ids": [],
        "draft_body": draft_body,
        "llm_status": _metadata_text(constraints, "llm_review_status"),
        "llm_model": _metadata_text(constraints, "llm_model"),
        "status": "proposed",
        "created_at": message["received_at"],
    }


def persist_conversation_message(
    *,
    request: ClinicPatientRequestsItem,
    message: ClinicEmailMessagesItem,
    create_draft_revision: bool = True,
) -> ConversationPersistenceResult:
    """Project one email into a latest-conversation row and optional draft revision."""

    conversation_id = conversation_id_for_message(message)
    existing = get_clinic_conversations(request["practice_id"], conversation_id)
    draft_revision = (
        _draft_revision_item(request=request, message=message, conversation_id=conversation_id)
        if create_draft_revision
        else None
    )
    draft_revision_created = (
        put_clinic_draft_revisions_if_absent(draft_revision)
        if draft_revision is not None
        else False
    )
    latest_draft_revision_id = (
        draft_revision["draft_revision_id"]
        if draft_revision is not None
        else (existing["latest_draft_revision_id"] if existing is not None else "")
    )
    created_at = existing["created_at"] if existing is not None else message["received_at"]
    conversation: ClinicConversationsItem = {
        "practice_id": request["practice_id"],
        "conversation_id": conversation_id,
        "source_provider": message["source_provider"],
        "source_thread_id": message["gmail_thread_id"],
        "patient_id": request["patient_id"],
        "patient_name": request["patient_name"],
        "patient_email": request["patient_email"],
        "patient_request_id": request["patient_request_id"],
        "subject": message["subject"],
        "latest_message_id": message["gmail_message_id"],
        "latest_message_excerpt": message["body_excerpt"],
        "latest_message_at": message["received_at"],
        "latest_message_sort_key": _message_sort_key(message),
        "latest_message_direction": message["direction"],
        "latest_classification": message["classification"],
        "latest_draft_revision_id": latest_draft_revision_id,
        "status": request["status"],
        "requires_doctor_review": request["requires_doctor_review"],
        "created_at": created_at,
        "updated_at": message["processed_at"],
    }
    conversation_updated = put_clinic_conversations_if_newer(
        conversation,
        ordering_attribute="latest_message_sort_key",
    )
    return {
        "conversation": conversation,
        "conversation_updated": conversation_updated,
        "draft_revision": draft_revision,
        "draft_revision_created": draft_revision_created,
    }
