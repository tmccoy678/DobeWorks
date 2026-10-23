#!/usr/bin/env python3
"""Tests for the direct handoff-stream viewer."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parent
CLI = BASE / "handoff_view.py"


def event(sequence: int, name: str, actor: str, details: dict) -> dict:
    return {
        "schema_version": "dobeworks.handoff-event/v1",
        "sequence": sequence,
        "observed_at": "2026-10-23T12:00:00Z",
        "job_id": "view-001",
        "event": name,
        "stage": "inspect",
        "actor": actor,
        "authority": "PROPOSAL_ONLY" if actor == "AGENT_ADAPTER" else "DETERMINISTIC_ENFORCEMENT",
        "details": details,
    }


class HandoffViewTests(unittest.TestCase):
    def run_view(self, events: list[dict]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            stream = Path(temporary) / "handoffs.jsonl"
            stream.write_text(
                "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
                encoding="utf-8",
            )
            return subprocess.run(
                [sys.executable, "-B", str(CLI), str(stream)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

    def test_renders_agent_and_controller_in_parallel_lanes(self) -> None:
        completed = self.run_view(
            [
                event(
                    1,
                    "operation_proposed",
                    "AGENT_ADAPTER",
                    {"operation": "read_file", "path": "README.txt"},
                ),
                event(
                    2,
                    "operation_completed",
                    "DOBEWORKS_CONTROLLER",
                    {"operation": "read_file", "path": "README.txt"},
                ),
            ]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("AGENT / PROPOSAL", completed.stdout)
        self.assertIn("CONTROLLER / EVIDENCE", completed.stdout)
        self.assertIn("PROPOSE read_file README.txt", completed.stdout)
        self.assertIn("| ALLOW read_file README.txt", completed.stdout)

    def test_noncontiguous_sequence_fails_closed(self) -> None:
        completed = self.run_view(
            [event(2, "stage_started", "DOBEWORKS_CONTROLLER", {})]
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("not contiguous", completed.stderr)

    def test_adapter_failure_is_rendered_in_the_agent_lane(self) -> None:
        completed = self.run_view(
            [
                event(
                    1,
                    "adapter_failed",
                    "AGENT_ADAPTER",
                    {"action_index": 0, "state": "FAILED_ADAPTER"},
                )
            ]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ADAPTER FAILED FAILED_ADAPTER", completed.stdout)


if __name__ == "__main__":
    unittest.main()
