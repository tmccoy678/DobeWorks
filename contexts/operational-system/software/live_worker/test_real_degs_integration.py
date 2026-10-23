#!/usr/bin/env python3
"""Optional cross-repository test using an actual DEGS checkout."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BASE = Path(__file__).resolve().parent
CLI = BASE / "governed_live_worker.py"
NOW = "2026-10-23T12:00:00Z"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts or not path.is_file():
            continue
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def actual_degs_paths(degs: Path) -> dict[str, Path]:
    return {
        "gate": degs / "bin" / "engineering-gate.py",
        "task": degs / "fixtures" / "tier0-readonly-pass.json",
        "review": degs / "bin" / "review-state.py",
        "sashiko": degs / "sashiko_derived" / "__init__.py",
        "provenance": degs / "provenance" / "sashiko-source.json",
    }


def integration_script() -> dict:
    return {
        "schema_version": "dobeworks.scripted-agent/v1",
        "stages": {
            "inspect": [
                {"operation": "read_file", "path": "README.txt"},
                {"operation": "finish_stage", "summary": "Inspected source."},
            ],
            "execute_check": [
                {"operation": "finish_stage", "summary": "No mutation requested."}
            ],
            "review": [
                {
                    "operation": "finish_stage",
                    "summary": "No concern found.",
                    "concerns": [],
                    "dismissed_concerns": [],
                }
            ],
        },
    }


def degs_identity(paths: dict[str, Path]) -> dict[str, str]:
    return {
        "gate_relative_path": "bin/engineering-gate.py",
        "gate_sha256": sha256_file(paths["gate"]),
        "task_relative_path": "fixtures/tier0-readonly-pass.json",
        "task_sha256": sha256_file(paths["task"]),
        "review_relative_path": "bin/review-state.py",
        "review_sha256": sha256_file(paths["review"]),
        "sashiko_relative_path": "sashiko_derived/__init__.py",
        "sashiko_sha256": sha256_file(paths["sashiko"]),
        "sashiko_provenance_relative_path": "provenance/sashiko-source.json",
        "sashiko_provenance_sha256": sha256_file(paths["provenance"]),
    }


def integration_envelope(source: Path, script: Path, paths: dict[str, Path]) -> dict:
    return {
        "schema_version": "dobeworks.governed-live-job/v1",
        "job_id": "actual-degs-001",
        "objective": "Exercise the actual DEGS gate and Sashiko adapter.",
        "issued_at": "2026-10-23T11:55:00Z",
        "expires_at": "2026-10-23T12:05:00Z",
        "source_tree_sha256": tree_sha256(source),
        "agent_adapter": {
            "kind": "SCRIPTED",
            "configuration_sha256": sha256_file(script),
        },
        "degs": degs_identity(paths),
        "dispatch_authority": {
            "authorized": True,
            "authorized_by": "Taylor",
            "scope": "Bounded cross-repository test.",
        },
        "permissions": {
            "mutation": False,
            "allowed_paths": ["README.txt"],
            "check_ids": [],
        },
        "checks": {},
        "limits": {
            "max_actions_per_stage": 8,
            "timeout_seconds": 10,
            "max_file_bytes": 65536,
            "max_output_bytes": 1048576,
        },
    }


def run_integration(
    envelope: Path,
    source: Path,
    staging: Path,
    degs: Path,
    script: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "run",
            "--envelope",
            str(envelope),
            "--source-repo",
            str(source),
            "--staging-root",
            str(staging),
            "--degs-root",
            str(degs),
            "--agent-script",
            str(script),
            "--now",
            NOW,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@unittest.skipUnless(os.environ.get("DOBEWORKS_DEGS_ROOT"), "set DOBEWORKS_DEGS_ROOT for cross-repository evidence")
class RealDegsIntegrationTests(unittest.TestCase):
    def test_actual_gate_and_sashiko_adapter_complete_none_reported_handback(self) -> None:
        degs = Path(os.environ["DOBEWORKS_DEGS_ROOT"]).resolve()
        paths = actual_degs_paths(degs)
        for path in paths.values():
            self.assertTrue(path.is_file(), path)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, staging = root / "source", root / "staging"
            source.mkdir()
            staging.mkdir()
            (source / "README.txt").write_text("actual DEGS integration\n", encoding="utf-8")
            script = root / "agent-script.json"
            write_json(script, integration_script())
            envelope = root / "envelope.json"
            write_json(envelope, integration_envelope(source, script, paths))
            completed = run_integration(envelope, source, staging, degs, script)
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            handback = json.loads(
                (staging / "actual-degs-001" / "handback.json").read_text(encoding="utf-8")
            )
            self.assertEqual(handback["degs_preflight_readiness"], "PASS")
            self.assertEqual(
                handback["agent_reported_concern_status"],
                "NONE_REPORTED",
            )
            self.assertEqual(
                handback["sashiko_source_commit"],
                "39f6ce95c797bb40023247916a8b16d0f4aaf0da",
            )
            self.assertEqual(handback["promotion"], "NOT_PERFORMED")


if __name__ == "__main__":
    unittest.main()
