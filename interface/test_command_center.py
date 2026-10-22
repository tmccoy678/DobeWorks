"""Focused regressions for the shared frontend's result boundaries."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import command_center as ui


class InterfaceTests(unittest.TestCase):
    def test_default_gate_uses_plain_name_with_explicit_checkout_override(self):
        default = ui.parse_args(["degs", "tier2-complete-pass.json"])
        self.assertEqual(default.degs_root, ui.ROOT.parent / "DEGS")
        custom = Path("custom-degs-checkout")
        selected = ui.parse_args(["--degs-root", str(custom), "degs", "tier2-complete-pass.json"])
        self.assertEqual(selected.degs_root, custom)

    def integration(self, stale=None, worker=None):
        snapshot = json.loads((ui.PHASE4 / "fixtures/observer-snapshot.json").read_text())
        fresh = {"schema_version": "dobeworks.observer-record.v1", "role_id": snapshot["role_id"],
                 "status": "VALIDATED", "freshness": "FRESH",
                 "signals": {item["name"]: item["value"] for item in snapshot["signals"]}}
        if stale is None:
            stale = dict(fresh, status="TELEMETRY_UNAVAILABLE", freshness="STALE",
                         signals={name: "UNKNOWN" for name in fresh["signals"]})
        if worker is None:
            worker = {"state": "COMPLETED_UNACCEPTED", "promotion": "NOT_PERFORMED"}
        decisions = [
            {"validate_exit": 0, "validate_decision": "PASS", "evaluate_exit": code, "evaluate_decision": decision}
            for code, decision in [(0, "PASS"), (2, "BLOCKED"), (2, "BLOCKED")]
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(ui, "new_run", return_value=root), \
                 patch.object(ui, "run_observer", side_effect=[fresh, stale]), \
                 patch.object(ui, "run_worker", return_value=(worker, root / "handback.json")), \
                 patch.object(ui, "observer_task", return_value={}), \
                 patch.object(ui, "worker_task", return_value={}), \
                 patch.object(ui, "run_degs_task", side_effect=decisions), \
                 patch.object(ui, "source_identity", return_value={}), \
                 contextlib.redirect_stdout(io.StringIO()):
                return ui.run_integration()

    def test_integration_requires_actual_source_states(self):
        self.assertEqual(self.integration(), 0)
        for stale in [
            {},
            {"status": "ERROR", "freshness": "UNKNOWN"},
            {"status": "TELEMETRY_UNAVAILABLE", "freshness": "FRESH"},
        ]:
            with self.subTest(stale=stale):
                self.assertEqual(self.integration(stale=stale), 1)
        for worker in [
            {"state": "COMPLETED_UNACCEPTED", "promotion": "PERFORMED"},
            {"state": "FAILED", "promotion": "NOT_PERFORMED"},
        ]:
            with self.subTest(worker=worker):
                self.assertEqual(self.integration(worker=worker), 1)

    def test_verification_requires_executed_tests(self):
        outputs = [
            ("Ran 2 tests in 0.01s\n\nOK\n", 0),
            ("Ran 0 tests in 0.00s\n\nOK\n", 1),
            ("Ran 2 tests in 0.00s\n\nOK (skipped=2)\n", 1),
            ("No unittest summary\n", 1),
        ]
        for output, expected in outputs:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as directory:
                process = subprocess.CompletedProcess([], 0, "", output)
                with patch.object(ui, "new_run", return_value=Path(directory)), \
                     patch.object(ui, "source_identity", return_value={}), \
                     patch.object(ui.subprocess, "run", return_value=process), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ui.verify_cores(), expected)

    def test_degs_demo_requires_expected_decision(self):
        for exit_code, decision, expected in [(0, "PASS", 0), (2, "BLOCKED", 1), (4, "FAIL", 1)]:
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "fixtures").mkdir()
                (root / "fixtures/tier2-complete-pass.json").write_text('{"task_id":"DEMO"}')
                with patch.object(ui, "DEGS", root), \
                     patch.object(ui, "new_run", return_value=root), \
                     patch.object(ui, "run_json", return_value=(exit_code, {"decision": decision})), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ui.show_degs_fixture("tier2-complete-pass.json"), expected)

    def test_voice_bank_contains_only_verified_outputs_for_three_voices(self):
        entries = json.loads(ui.VOICE_BANK.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 6)
        speakers = {"ELIZA", "COLOSSUS", "COLOSSUS + GUARDIAN"}
        self.assertEqual({item["speaker"] for item in entries}, speakers)
        self.assertEqual(
            {speaker: sum(item["speaker"] == speaker for item in entries)
             for speaker in speakers},
            {"ELIZA": 2, "COLOSSUS": 2, "COLOSSUS + GUARDIAN": 2},
        )
        for item in entries:
            self.assertEqual(item["verification"], "primary-source-verified")
            self.assertTrue(item["source"])
            self.assertTrue(item["locator"])
            self.assertRegex(item["source_sha256"], r"^[0-9a-f]{64}$")
            self.assertNotEqual(item.get("origin"), "Original workbench line")
        with patch.object(ui, "choose_workbench_voice", return_value=("COLOSSUS", "TEST LINE.", "· COLOSSUS")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            ui.print_header()
        self.assertIn("“TEST LINE.”", output.getvalue())
        self.assertIn("· COLOSSUS", output.getvalue())

    def test_voice_bank_rejects_missing_primary_source_provenance(self):
        entries = [
            {
                "speaker": speaker,
                "text": f"VERIFIED LINE {index}.",
                "attribution": f"· {speaker}",
                "verification": "primary-source-verified",
                "source": "Primary source",
                "locator": "Exact locator",
                "source_sha256": "0" * 64,
            }
            for speaker in ("ELIZA", "COLOSSUS", "COLOSSUS + GUARDIAN")
            for index in (1, 2)
        ]
        del entries[0]["locator"]
        with tempfile.TemporaryDirectory() as directory:
            bank = Path(directory) / "voices.json"
            bank.write_text(json.dumps(entries), encoding="utf-8")
            with patch.object(ui, "VOICE_BANK", bank), self.assertRaises(RuntimeError):
                ui.load_workbench_voices()

    def test_voice_bank_rejects_invalid_source_hash(self):
        entries = [
            {
                "speaker": speaker,
                "text": f"VERIFIED LINE {index}.",
                "attribution": f"· {speaker}",
                "verification": "primary-source-verified",
                "source": "Primary source",
                "locator": "Exact locator",
                "source_sha256": "not-a-sha256",
            }
            for speaker in ("ELIZA", "COLOSSUS", "COLOSSUS + GUARDIAN")
            for index in (1, 2)
        ]
        with tempfile.TemporaryDirectory() as directory:
            bank = Path(directory) / "voices.json"
            bank.write_text(json.dumps(entries), encoding="utf-8")
            with patch.object(ui, "VOICE_BANK", bank), self.assertRaises(RuntimeError):
                ui.load_workbench_voices()

    def test_subprocess_rejects_malformed_output_and_stderr(self):
        import sys
        for code, rejected in [
            ('print("{}")', False),
            ('print("[]")', True),
            ('print("not JSON")', True),
            ('print(\'{"decision":"BLOCKED","decision":"PASS"}\')', True),
            ('print(\'{"value":NaN}\')', True),
            ('print(\'{"value":1e999}\')', True),
            ('import sys; print("{}"); print("diagnostic", file=sys.stderr)', True),
        ]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                arguments = ([sys.executable, "-c", code], Path(directory), "child", (0,))
                if rejected:
                    with self.assertRaises(RuntimeError):
                        ui.run_json(*arguments)
                else:
                    self.assertEqual(ui.run_json(*arguments), (0, {}))

    def test_evidence_omits_credentials_and_unperformed_pass_claims(self):
        for remote in [
            "https://user:FAKE_CREDENTIAL@github.com/owner/repo.git?token=FAKE_QUERY#private",
            "ssh://FAKE_CREDENTIAL@github.com/owner/repo.git",
            "git+ssh://FAKE_CREDENTIAL@github.com/owner/repo.git",
            "helper::ssh://FAKE_CREDENTIAL@github.com/owner/repo.git",
        ]:
            responses = [subprocess.CompletedProcess([], 0, value, "")
                         for value in ["abc123\n", "", remote + "\n"]]
            with self.subTest(remote=remote), patch.object(ui.subprocess, "run", side_effect=responses):
                recorded = ui.git_identity(Path("unused"))["remote"]
                self.assertNotIn("FAKE_", recorded)
                self.assertNotIn("private", recorded)
        adapted = ui.replace_evidence_paths({"tests": [{"status": "PASS", "evidence_path": "fixture"}]}, "handback")
        self.assertEqual(adapted["tests"][0]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
