from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_tools.check_deployed_state import ResourceCheck, format_resource_summary, write_action_summary


class DeployedStateSummaryTests(unittest.TestCase):
    def test_format_resource_summary_lists_resources_and_discrepancies(self) -> None:
        summary = format_resource_summary(
            [
                ResourceCheck("DynamoDB table", "sample_messages", found=True),
                ResourceCheck(
                    "Lambda function",
                    "sample_agent",
                    found=True,
                    discrepancies=["sample_agent: Timeout is 60, expected 30"],
                ),
                ResourceCheck(
                    "Vercel production env var",
                    "AWS_ROLE_ARN",
                    found=False,
                    discrepancies=["Vercel production env var missing: AWS_ROLE_ARN"],
                ),
            ],
            [
                "sample_agent: Timeout is 60, expected 30",
                "Vercel production env var missing: AWS_ROLE_ARN",
            ],
        )

        self.assertIn("# Deployed State Verification", summary)
        self.assertIn("- Resources checked: 3", summary)
        self.assertIn("- OK: 1", summary)
        self.assertIn("- Discrepancies: 1", summary)
        self.assertIn("- Missing: 1", summary)
        self.assertIn("| DynamoDB table | `sample_messages` | OK | Matches repo definition |", summary)
        self.assertIn("| Lambda function | `sample_agent` | Discrepancy |", summary)
        self.assertIn("| Vercel production env var | `AWS_ROLE_ARN` | Missing |", summary)
        self.assertIn("## Discrepancies", summary)

    def test_write_action_summary_writes_markdown_to_requested_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "summary.md"

            write_action_summary(
                [ResourceCheck("IAM role", "vercel-invoke", found=True)],
                [],
                str(summary_path),
            )

            self.assertIn("`vercel-invoke`", summary_path.read_text())


if __name__ == "__main__":
    unittest.main()
