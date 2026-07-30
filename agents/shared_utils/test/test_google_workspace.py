"""Tests for bounded Google Workspace pagination."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SHARED_UTILS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED_UTILS_DIR))

from google_workspace import GMAIL_MESSAGES_URL, GMAIL_THREADS_URL, GoogleWorkspaceHttpClient


class GoogleWorkspaceHttpClientTest(unittest.TestCase):
    def test_gmail_page_returns_messages_and_continuation_token(self) -> None:
        client = GoogleWorkspaceHttpClient("access-token")
        with patch.object(
            client,
            "_get",
            side_effect=[
                {
                    "messages": [{"id": "message-1"}, {"id": "message-2"}],
                    "nextPageToken": "next-page",
                    "resultSizeEstimate": 12,
                },
                {"id": "message-1", "threadId": "thread-1"},
                {"id": "message-2", "threadId": "thread-2"},
            ],
        ) as get:
            page = client.list_gmail_message_page(
                query="in:inbox newer_than:30d",
                max_results=2,
                page_token="current-page",
            )

        self.assertEqual([message["id"] for message in page["messages"]], ["message-1", "message-2"])
        self.assertEqual(page["next_page_token"], "next-page")
        self.assertEqual(page["result_size_estimate"], 12)
        listing_url, listing_params = get.call_args_list[0].args
        self.assertEqual(listing_url, GMAIL_MESSAGES_URL)
        self.assertEqual(listing_params["pageToken"], "current-page")
        self.assertEqual(listing_params["maxResults"], 2)

    def test_legacy_list_method_returns_first_page_messages(self) -> None:
        client = GoogleWorkspaceHttpClient("access-token")
        with patch.object(
            client,
            "list_gmail_message_page",
            return_value={
                "messages": [{"id": "message-1"}],
                "next_page_token": "ignored-next-page",
                "result_size_estimate": 2,
            },
        ):
            messages = client.list_gmail_message_metadata(query="in:inbox", max_results=1)

        self.assertEqual(messages, [{"id": "message-1"}])

    def test_gmail_thread_page_returns_inbox_messages_in_thread_payload(self) -> None:
        client = GoogleWorkspaceHttpClient("access-token")
        with patch.object(
            client,
            "_get",
            side_effect=[
                {
                    "threads": [{"id": "thread-1"}],
                    "nextPageToken": "next-thread-page",
                    "resultSizeEstimate": 4,
                },
                {
                    "id": "thread-1",
                    "messages": [
                        {"id": "message-1", "threadId": "thread-1", "labelIds": ["INBOX"]},
                        {"id": "sent-1", "threadId": "thread-1", "labelIds": ["SENT"]},
                        {"id": "message-2", "threadId": "thread-1", "labelIds": ["INBOX"]},
                    ],
                },
            ],
        ) as get:
            page = client.list_gmail_thread_page(
                query="in:inbox newer_than:30d",
                max_results=1,
                page_token="current-thread-page",
            )

        self.assertEqual([message["id"] for message in page["messages"]], ["message-1", "message-2"])
        self.assertEqual(page["next_page_token"], "next-thread-page")
        self.assertEqual(page["result_size_estimate"], 8)
        listing_url, listing_params = get.call_args_list[0].args
        self.assertEqual(listing_url, GMAIL_THREADS_URL)
        self.assertEqual(listing_params["pageToken"], "current-thread-page")
        self.assertEqual(get.call_args_list[1].args[0], f"{GMAIL_THREADS_URL}/thread-1")


if __name__ == "__main__":
    unittest.main()
