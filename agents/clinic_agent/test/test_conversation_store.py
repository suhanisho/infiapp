"""Tests for conversation summaries and immutable draft revisions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parents[1]
AGENTS_DIR = AGENT_DIR.parents[0]
sys.path.insert(0, str(AGENTS_DIR / "shared_utils"))
sys.path.insert(0, str(AGENT_DIR / "code"))

from clinic_features import conversation_store
from generated.dynamodb import ClinicEmailMessagesItem, ClinicPatientRequestsItem


def patient_request(*, source_message_id: str, draft_message: str = "Draft response") -> ClinicPatientRequestsItem:
    return {
        "practice_id": "practice-doctor",
        "patient_request_id": "gmail-thread-thread-1",
        "patient_id": "patient-1",
        "patient_name": "Sarah Jones",
        "patient_email": "sarah@example.com",
        "time_label": "10:00 AM",
        "source_summary": "Appointment request",
        "source_excerpt": "Could I come next Tuesday?",
        "source_subject": "Appointment request",
        "draft_message": draft_message,
        "appointment_type": "Initial Consultation",
        "duration_minutes": 45,
        "intent": "review_booking",
        "patient_emotional_tone": "neutral",
        "proposed_windows": ["Tuesday 4 August at 2:30 PM"],
        "request_constraints": {
            "llm_review_status": "used",
            "llm_model": "test-model",
        },
        "request_type": "appointment_request",
        "requires_doctor_review": False,
        "risk_level": "low",
        "suggested_next_action": "Review the draft.",
        "triage_category": "appointment_request",
        "triage_confidence": 0.9,
        "triage_reason": "Scheduling request.",
        "urgency_level": "routine",
        "status": "needs_approval",
        "final_message": "",
        "source_provider": "gmail",
        "source_thread_id": "thread-1",
        "source_message_id": source_message_id,
        "approved_at": "",
        "approved_by": "",
        "completed_at": "",
        "completion_note": "",
        "created_at": "2026-08-01T09:00:00+00:00",
        "updated_at": "2026-08-01T09:00:01+00:00",
    }


def email_message(
    *,
    message_id: str,
    received_at: str,
    thread_id: str = "thread-1",
    direction: str = "inbound",
) -> ClinicEmailMessagesItem:
    return {
        "practice_id": "practice-doctor",
        "gmail_message_id": message_id,
        "gmail_thread_id": thread_id,
        "message_id_header": f"<{message_id}@example.com>",
        "in_reply_to": "",
        "references": "",
        "message_signature": f"signature-{message_id}",
        "patient_request_id": "gmail-thread-thread-1",
        "patient_id": "patient-1",
        "direction": direction,
        "from_email": "sarah@example.com" if direction == "inbound" else "",
        "from_name": "Sarah Jones" if direction == "inbound" else "Dr. Shalini's Clinic",
        "to_email": "" if direction == "inbound" else "sarah@example.com",
        "subject": "Appointment request",
        "body_excerpt": "Could I come next Tuesday?" if direction == "inbound" else "Tuesday at 2:30 PM is available.",
        "classification": "appointment_request" if direction == "inbound" else "approved_reply_sent",
        "source_provider": "gmail",
        "received_at": received_at,
        "processed_at": received_at,
    }


class ConversationStoreTest(unittest.TestCase):
    def test_initial_message_creates_conversation_and_draft_revision(self) -> None:
        request = patient_request(source_message_id="message-1")
        message = email_message(message_id="message-1", received_at="2026-08-01T09:00:00+00:00")

        with (
            patch.object(conversation_store, "get_clinic_conversations", return_value=None),
            patch.object(conversation_store, "put_clinic_draft_revisions_if_absent", return_value=True) as put_draft,
            patch.object(conversation_store, "put_clinic_conversations_if_newer", return_value=True) as put_conversation,
        ):
            result = conversation_store.persist_conversation_message(request=request, message=message)

        self.assertEqual(result["conversation"]["conversation_id"], "gmail-thread-thread-1")
        self.assertEqual(result["conversation"]["latest_message_id"], "message-1")
        self.assertTrue(result["conversation_updated"])
        self.assertTrue(result["draft_revision_created"])
        self.assertIsNotNone(result["draft_revision"])
        draft = cast(Any, result["draft_revision"])
        self.assertEqual(draft["source_message_id"], "message-1")
        self.assertEqual(draft["draft_body"], "Draft response")
        self.assertEqual(draft["availability_windows"], ["Tuesday 4 August at 2:30 PM"])
        put_draft.assert_called_once()
        put_conversation.assert_called_once()

    def test_follow_up_updates_same_conversation_and_creates_new_revision(self) -> None:
        initial_request = patient_request(source_message_id="message-1")
        initial_message = email_message(message_id="message-1", received_at="2026-08-01T09:00:00+00:00")
        with (
            patch.object(conversation_store, "get_clinic_conversations", return_value=None),
            patch.object(conversation_store, "put_clinic_draft_revisions_if_absent", return_value=True),
            patch.object(conversation_store, "put_clinic_conversations_if_newer", return_value=True),
        ):
            initial = conversation_store.persist_conversation_message(
                request=initial_request,
                message=initial_message,
            )

        follow_up_request = patient_request(source_message_id="message-2", draft_message="Tuesday at 2:30 PM works.")
        follow_up_message = email_message(message_id="message-2", received_at="2026-08-01T10:00:00+00:00")
        with (
            patch.object(
                conversation_store,
                "get_clinic_conversations",
                return_value=initial["conversation"],
            ),
            patch.object(conversation_store, "put_clinic_draft_revisions_if_absent", return_value=True),
            patch.object(conversation_store, "put_clinic_conversations_if_newer", return_value=True),
        ):
            follow_up = conversation_store.persist_conversation_message(
                request=follow_up_request,
                message=follow_up_message,
            )

        self.assertEqual(
            initial["conversation"]["conversation_id"],
            follow_up["conversation"]["conversation_id"],
        )
        self.assertEqual(follow_up["conversation"]["latest_message_id"], "message-2")
        self.assertEqual(follow_up["conversation"]["created_at"], initial["conversation"]["created_at"])
        initial_draft = cast(Any, initial["draft_revision"])
        follow_up_draft = cast(Any, follow_up["draft_revision"])
        self.assertNotEqual(initial_draft["draft_revision_id"], follow_up_draft["draft_revision_id"])
        self.assertEqual(follow_up_draft["source_message_id"], "message-2")

    def test_reprocessing_same_message_does_not_replace_revision_or_latest_summary(self) -> None:
        request = patient_request(source_message_id="message-1")
        message = email_message(message_id="message-1", received_at="2026-08-01T09:00:00+00:00")
        existing_conversation = cast(
            Any,
            {
                "practice_id": "practice-doctor",
                "conversation_id": "gmail-thread-thread-1",
                "source_provider": "gmail",
                "source_thread_id": "thread-1",
                "patient_id": "patient-1",
                "patient_name": "Sarah Jones",
                "patient_email": "sarah@example.com",
                "subject": "Appointment request",
                "latest_message_id": "message-1",
                "latest_message_excerpt": "Could I come next Tuesday?",
                "latest_message_at": "2026-08-01T09:00:00+00:00",
                "latest_message_sort_key": "2026-08-01T09:00:00+00:00#message-1",
                "latest_message_direction": "inbound",
                "latest_classification": "appointment_request",
                "latest_draft_revision_id": "existing-revision",
                "status": "needs_approval",
                "requires_doctor_review": False,
                "created_at": "2026-08-01T09:00:00+00:00",
                "updated_at": "2026-08-01T09:00:00+00:00",
            },
        )
        with (
            patch.object(
                conversation_store,
                "get_clinic_conversations",
                return_value=existing_conversation,
            ),
            patch.object(conversation_store, "put_clinic_draft_revisions_if_absent", return_value=False),
            patch.object(conversation_store, "put_clinic_conversations_if_newer", return_value=False),
        ):
            result = conversation_store.persist_conversation_message(request=request, message=message)

        self.assertFalse(result["draft_revision_created"])
        self.assertFalse(result["conversation_updated"])

    def test_new_gmail_thread_creates_a_different_conversation(self) -> None:
        first = email_message(
            message_id="message-1",
            thread_id="thread-1",
            received_at="2026-08-01T09:00:00+00:00",
        )
        second = email_message(
            message_id="message-2",
            thread_id="thread-2",
            received_at="2026-08-01T10:00:00+00:00",
        )

        self.assertNotEqual(
            conversation_store.conversation_id_for_message(first),
            conversation_store.conversation_id_for_message(second),
        )

    def test_outbound_message_preserves_latest_draft_without_creating_revision(self) -> None:
        request = patient_request(source_message_id="message-1")
        message = email_message(
            message_id="sent-message-1",
            received_at="2026-08-01T11:00:00+00:00",
            direction="outbound",
        )
        existing_conversation = cast(
            Any,
            {
                "practice_id": "practice-doctor",
                "conversation_id": "gmail-thread-thread-1",
                "source_provider": "gmail",
                "source_thread_id": "thread-1",
                "patient_id": "patient-1",
                "patient_name": "Sarah Jones",
                "patient_email": "sarah@example.com",
                "subject": "Appointment request",
                "latest_message_id": "message-1",
                "latest_message_excerpt": "Could I come next Tuesday?",
                "latest_message_at": "2026-08-01T09:00:00+00:00",
                "latest_message_sort_key": "2026-08-01T09:00:00+00:00#message-1",
                "latest_message_direction": "inbound",
                "latest_classification": "appointment_request",
                "latest_draft_revision_id": "draft-revision-1",
                "status": "needs_approval",
                "requires_doctor_review": False,
                "created_at": "2026-08-01T09:00:00+00:00",
                "updated_at": "2026-08-01T09:00:00+00:00",
            },
        )
        with (
            patch.object(
                conversation_store,
                "get_clinic_conversations",
                return_value=existing_conversation,
            ),
            patch.object(conversation_store, "put_clinic_draft_revisions_if_absent") as put_draft,
            patch.object(conversation_store, "put_clinic_conversations_if_newer", return_value=True),
        ):
            result = conversation_store.persist_conversation_message(
                request=request,
                message=message,
                create_draft_revision=False,
            )

        self.assertIsNone(result["draft_revision"])
        self.assertFalse(result["draft_revision_created"])
        self.assertEqual(result["conversation"]["latest_draft_revision_id"], "draft-revision-1")
        self.assertEqual(result["conversation"]["latest_message_direction"], "outbound")
        put_draft.assert_not_called()


if __name__ == "__main__":
    unittest.main()
