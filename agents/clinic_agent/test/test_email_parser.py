"""Characterization tests for deterministic Gmail message parsing."""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

AGENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_DIR / "code"))

from clinic_features.email_parser import normalized_message_signature, parse_gmail_message, visible_reply_text


def encoded_body(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


class EmailParserTest(unittest.TestCase):
    def test_normalizes_initial_patient_email(self) -> None:
        message = {
            "id": "gmail-message-1",
            "threadId": "gmail-thread-1",
            "internalDate": "1785834000000",
            "snippet": "Could I come in next Tuesday afternoon?",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "Sarah Jones <SARAH@example.com>"},
                    {"name": "Subject", "value": "Appointment request"},
                    {"name": "Message-ID", "value": "<message-1@example.com>"},
                ],
                "body": {"data": encoded_body("Could I come in next Tuesday afternoon?")},
            },
        }

        parsed = parse_gmail_message(message, clinic_timezone=ZoneInfo("Europe/London"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["gmail_message_id"], "gmail-message-1")
        self.assertEqual(parsed["gmail_thread_id"], "gmail-thread-1")
        self.assertEqual(parsed["sender_name"], "Sarah Jones")
        self.assertEqual(parsed["sender_email"], "sarah@example.com")
        self.assertEqual(parsed["message_text"], "Could I come in next Tuesday afternoon?")
        self.assertEqual(parsed["message_id_header"], "<message-1@example.com>")

    def test_follow_up_is_a_distinct_message_in_the_same_thread(self) -> None:
        initial = {
            "id": "gmail-message-1",
            "threadId": "gmail-thread-1",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sarah Jones <sarah@example.com>"},
                    {"name": "Subject", "value": "Appointment request"},
                ]
            },
            "snippet": "Could I come in next Tuesday afternoon?",
        }
        follow_up = {
            "id": "gmail-message-2",
            "threadId": "gmail-thread-1",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "Sarah Jones <sarah@example.com>"},
                    {"name": "Subject", "value": "Re: Appointment request"},
                    {"name": "In-Reply-To", "value": "<clinic-reply@example.com>"},
                ],
                "body": {
                    "data": encoded_body(
                        "2:30 PM would be perfect.\n\n"
                        "On Monday, Dr. Shalini's Clinic wrote:\n"
                        "> We have 2:30 PM or 4:00 PM available."
                    )
                },
            },
        }

        parsed_initial = parse_gmail_message(initial, clinic_timezone=ZoneInfo("Europe/London"))
        parsed_follow_up = parse_gmail_message(follow_up, clinic_timezone=ZoneInfo("Europe/London"))

        self.assertIsNotNone(parsed_initial)
        self.assertIsNotNone(parsed_follow_up)
        assert parsed_initial is not None and parsed_follow_up is not None
        self.assertNotEqual(parsed_initial["gmail_message_id"], parsed_follow_up["gmail_message_id"])
        self.assertEqual(parsed_initial["gmail_thread_id"], parsed_follow_up["gmail_thread_id"])
        self.assertEqual(visible_reply_text(parsed_follow_up["message_text"]), "2:30 PM would be perfect.")
        self.assertEqual(parsed_follow_up["in_reply_to"], "<clinic-reply@example.com>")

    def test_equivalent_messages_have_a_stable_signature(self) -> None:
        initial_signature = normalized_message_signature(
            "Sarah@Example.com",
            "Appointment request",
            "Tuesday afternoon works for me.",
        )
        equivalent_signature = normalized_message_signature(
            "sarah@example.com",
            "Re: Appointment request",
            "  tuesday   afternoon works for me.  ",
        )

        self.assertEqual(initial_signature, equivalent_signature)

    def test_message_without_gmail_id_is_rejected(self) -> None:
        parsed = parse_gmail_message(
            {"threadId": "gmail-thread-1", "snippet": "Missing id"},
            clinic_timezone=ZoneInfo("Europe/London"),
        )

        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
