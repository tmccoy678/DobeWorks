"""Run the shared adapter against the actual DEGS warning gate."""

import json
import os
from pathlib import Path
import tempfile
import unittest

import command_center as ui


class DegsWarningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get("DOBEWORKS_DEGS_ROOT")
        cls.degs_root = Path(selected).expanduser().resolve() if selected else ui.ROOT.parent / "DEGS"
        if not (cls.degs_root / "bin" / "engineering-gate.py").is_file():
            if selected:
                raise RuntimeError("DOBEWORKS_DEGS_ROOT must identify a DEGS checkout")
            raise unittest.SkipTest("DEGS sibling unavailable; set DOBEWORKS_DEGS_ROOT")

    def evaluate(self, task):
        previous_root = ui.DEGS
        try:
            ui.DEGS = self.degs_root
            with tempfile.TemporaryDirectory() as directory:
                return ui.run_degs_task(task, Path(directory), "warning-contract")
        finally:
            ui.DEGS = previous_root

    def test_unresolved_item_blocks_tier0_through_shared_adapter(self):
        task = json.loads((self.degs_root / "fixtures" / "tier0-readonly-pass.json").read_text(encoding="utf-8"))
        task["unresolved_items"] = [{"severity": "CRITICAL", "status": "UNRESOLVED", "resolved": False}]
        result = self.evaluate(task)
        self.assertEqual((result["evaluate_exit"], result["evaluate_decision"]), (2, "BLOCKED"))
        self.assertEqual(result["evaluate"]["warning_state"], {
            "unresolved_count": 1, "severity": "CRITICAL", "status": "UNRESOLVED", "resolved": False,
        })
        issues = result["evaluate"]["warnings"]
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0]["number"], issues[0]["field"]), (1, "unresolved_items[0]"))

    def test_contradictory_resolution_cannot_pass_through_shared_adapter(self):
        task = json.loads((self.degs_root / "fixtures" / "tier0-readonly-pass.json").read_text(encoding="utf-8"))
        task["warnings"] = [{"severity": "CRITICAL", "status": "RESOLVED", "resolved": False}]
        result = self.evaluate(task)
        self.assertEqual((result["validate_exit"], result["validate_decision"]), (4, "FAIL"))
        self.assertEqual((result["evaluate_exit"], result["evaluate_decision"]), (4, "FAIL"))

    def test_recorded_closure_preserves_clean_readiness_through_shared_adapter(self):
        task = json.loads((self.degs_root / "fixtures" / "tier0-readonly-pass.json").read_text(encoding="utf-8"))
        task["warnings"] = [{
            "severity": "NONE", "status": "RESOLVED", "resolved": True,
            "evidence_path": "synthetic-closure-record.md",
        }]
        result = self.evaluate(task)
        self.assertEqual((result["validate_exit"], result["validate_decision"]), (0, "PASS"))
        self.assertEqual((result["evaluate_exit"], result["evaluate_decision"]), (0, "PASS"))
        self.assertEqual(result["evaluate"]["warning_state"], {
            "unresolved_count": 0, "severity": "NONE", "status": "RESOLVED", "resolved": True,
        })
        self.assertEqual(result["evaluate"]["warnings"], [])


if __name__ == "__main__":
    unittest.main()
