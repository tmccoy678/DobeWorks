"""Regression tests for untrusted external governance-result parsing."""

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[5]
DEAS = Path(__file__).with_name("validate_deas.py")
PHASE2 = ROOT / (
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "validation/validate_phase2.py"
)
PASS = {
    "applicable_rule_ids": ["DEGS-REQ-001"],
    "authority_lane": "TAYLOR_AI_WORKBENCH",
    "decision": "PASS",
    "evidence_paths": ["evidence.md"],
    "risk_tier": "TIER_1",
    "unmet_requirements": [],
    "warnings": [],
}
PHASE2_PASS = {
    "decision": "PASS",
    "generation": 2,
    "identity_verified": True,
    "original_observations_preserved": True,
    "phase2_degs_decision": "PASS",
    "role_disposition": "NONE",
    "schema_version": 2,
    "validation_report_decision": "PASS",
}


def load_validator(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExternalGateResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deas = load_validator("external_result_deas", DEAS)
        phase2 = load_validator("external_result_phase2", PHASE2)
        cls.validators = (
            (deas, deas.verify_degs_pass_output),
            (phase2, phase2.verify_degs_result),
        )

    def assert_rejected(self, raw):
        for module, verify in self.validators:
            for action in ("validate", "evaluate"):
                with self.subTest(validator=module.__name__, action=action):
                    result = subprocess.CompletedProcess([], 0, raw, b"")
                    with self.assertRaisesRegex(
                        module.ValidationError, "not valid JSON|output is invalid"
                    ):
                        verify(result, action)

    def test_exact_pass_remains_accepted(self):
        raw = json.dumps(PASS).encode("utf-8")
        for module, verify in self.validators:
            for action in ("validate", "evaluate"):
                with self.subTest(validator=module.__name__, action=action):
                    result = subprocess.CompletedProcess([], 0, raw, b"")
                    self.assertIsNone(verify(result, action))

    def test_contradictory_duplicate_decisions_are_rejected(self):
        raw = json.dumps(PASS).replace(
            '"decision": "PASS"', '"decision": "BLOCKED", "decision": "PASS"'
        ).encode("utf-8")
        self.assert_rejected(raw)

    def test_nested_duplicates_are_invalid_json(self):
        raw = json.dumps(PASS).replace(
            '"warnings": []',
            '"warnings": [{"status": "BLOCKED", "status": "PASS"}]',
        ).encode("utf-8")
        self.assert_rejected(raw)

    def test_nonfinite_values_are_invalid_json(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(token=token):
                raw = json.dumps(PASS).replace(
                    '"warnings": []', '"warnings": [' + token + ']'
                ).encode("utf-8")
                self.assert_rejected(raw)

    def test_invalid_utf8_is_a_validation_error(self):
        self.assert_rejected(json.dumps(PASS).encode("utf-8") + b"\xff")

    def test_other_json_encodings_are_not_utf8(self):
        self.assert_rejected(json.dumps(PASS).encode("utf-16"))

    def test_excessive_nesting_is_a_validation_error(self):
        for depth in (65, 2000):
            with self.subTest(depth=depth):
                self.assert_rejected(b"[" * depth + b"0" + b"]" * depth)

    def test_compound_phase2_result_accepts_exact_pass(self):
        deas = self.validators[0][0]
        result = subprocess.CompletedProcess(
            [], 0, json.dumps(PHASE2_PASS).encode("utf-8"), b""
        )
        with patch.object(deas, "run_bounded_subprocess", return_value=result), \
                patch.object(deas, "verify_generation_2_task"), \
                patch.object(deas, "verify_generation_2_report"), \
                patch.object(deas, "verify_original_observations"), \
                patch.object(deas, "verify_generation_2_degs"), \
                patch.object(deas, "validate_definition_content"):
            outcome = deas.verify_phase2_validator_result(ROOT)
        self.assertTrue(outcome["phase2_compound_validation_verified"])

    def test_compound_phase2_result_rejects_duplicate_stop_decision(self):
        deas = self.validators[0][0]
        raw = json.dumps(PHASE2_PASS).replace(
            '"decision": "PASS"', '"decision": "BLOCKED", "decision": "PASS"'
        ).encode("utf-8")
        result = subprocess.CompletedProcess([], 0, raw, b"")
        with patch.object(deas, "run_bounded_subprocess", return_value=result), \
                patch.object(deas, "verify_generation_2_task"), \
                patch.object(deas, "verify_generation_2_report"), \
                patch.object(deas, "verify_original_observations"), \
                patch.object(deas, "verify_generation_2_degs"), \
                patch.object(deas, "validate_definition_content"):
            with self.assertRaises(deas.ValidationError):
                deas.verify_phase2_validator_result(ROOT)

    def test_compound_phase2_result_rejects_wrong_scalar_types(self):
        deas = self.validators[0][0]
        for field, value in (
            ("identity_verified", 1), ("original_observations_preserved", 1),
            ("generation", 2.0), ("schema_version", 2.0),
        ):
            with self.subTest(field=field, value=value):
                payload = dict(PHASE2_PASS, **{field: value})
                result = subprocess.CompletedProcess([], 0, json.dumps(payload).encode("utf-8"), b"")
                with patch.object(deas, "run_bounded_subprocess", return_value=result), \
                        patch.object(deas, "verify_generation_2_task"), \
                        patch.object(deas, "verify_generation_2_report"), \
                        patch.object(deas, "verify_original_observations"), \
                        patch.object(deas, "verify_generation_2_degs"), \
                        patch.object(deas, "validate_definition_content"):
                    with self.assertRaises(deas.ValidationError):
                        deas.verify_phase2_validator_result(ROOT)


if __name__ == "__main__":
    unittest.main()
