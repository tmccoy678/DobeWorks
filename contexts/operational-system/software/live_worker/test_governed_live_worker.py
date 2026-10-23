#!/usr/bin/env python3
"""Public-seam tests for the governed live-worker Module."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import governed_live_worker as worker  # noqa: E402

CLI = BASE / "governed_live_worker.py"
NOW = "2026-10-23T12:00:00Z"
GATE_DOUBLE = (
    "import json\n"
    "print(json.dumps({'decision':'PASS','warning_state':"
    "{'unresolved_count':0,'status':'RESOLVED','resolved':True}}))\n"
)
REVIEW_DOUBLE = (
    "import json,sys\n"
    "request=json.load(open(sys.argv[2], encoding='utf-8'))\n"
    "concerns=[]\n"
    "dismissed=[]\n"
    "for output in request['stage_outputs']:\n"
    "  for item in output['concerns']:\n"
    "    value=dict(item); value['stage']=output['stage']; concerns.append(value)\n"
    "  for item in output['dismissed_concerns']:\n"
    "    value=dict(item); value['stage']=output['stage']; dismissed.append(value)\n"
    "print(json.dumps({'schema_version':'degs.sashiko-review-state/v1',"
    "'sashiko_source_commit':'39f6ce95c797bb40023247916a8b16d0f4aaf0da',"
    "'report_basis':'AGENT_SUPPLIED_REVIEW_VALUES',"
    "'agent_reported_concern_status':"
    "'UNRESOLVED_REPORTED' if concerns else 'NONE_REPORTED',"
    "'all_concerns':concerns,'all_dismissed_concerns':dismissed,"
    "'deduplicated_concerns':[],'deduplicated_dismissed_concerns':[],"
    "'conflict_resolved_concerns':[],'findings':[]}))\n"
)


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_degs_double(root: Path) -> dict[str, Path]:
    paths = {
        "task": root / "fixtures" / "task.json",
        "gate": root / "bin" / "engineering-gate.py",
        "review": root / "bin" / "review-state.py",
        "sashiko": root / "sashiko_derived" / "__init__.py",
        "provenance": root / "provenance" / "sashiko-source.json",
    }
    for directory in ("fixtures", "bin", "sashiko_derived", "provenance"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    write_json(paths["task"], {"schema_version": 1, "risk_tier": "TIER_0"})
    paths["gate"].write_text(GATE_DOUBLE, encoding="utf-8")
    paths["review"].write_text(REVIEW_DOUBLE, encoding="utf-8")
    paths["sashiko"].write_text("# bounded test double\n", encoding="utf-8")
    write_json(
        paths["provenance"],
        {
            "repository": "https://github.com/sashiko-dev/sashiko",
            "commit": "39f6ce95c797bb40023247916a8b16d0f4aaf0da",
        },
    )
    return paths


def base_degs_identity(paths: dict[str, Path]) -> dict[str, str]:
    return {
        "gate_relative_path": "bin/engineering-gate.py",
        "gate_sha256": sha256_file(paths["gate"]),
        "task_relative_path": "fixtures/task.json",
        "task_sha256": sha256_file(paths["task"]),
        "review_relative_path": "bin/review-state.py",
        "review_sha256": sha256_file(paths["review"]),
        "sashiko_relative_path": "sashiko_derived/__init__.py",
        "sashiko_sha256": sha256_file(paths["sashiko"]),
        "sashiko_provenance_relative_path": "provenance/sashiko-source.json",
        "sashiko_provenance_sha256": sha256_file(paths["provenance"]),
    }


def base_envelope(source: Path, paths: dict[str, Path]) -> dict:
    return {
        "schema_version": "dobeworks.governed-live-job/v1",
        "job_id": "job-inspect-001",
        "objective": "Inspect the bounded source without changing it.",
        "issued_at": "2026-10-23T11:55:00Z",
        "expires_at": "2026-10-23T12:05:00Z",
        "source_tree_sha256": tree_sha256(source),
        "degs": base_degs_identity(paths),
        "dispatch_authority": {
            "authorized": True,
            "authorized_by": "Taylor",
            "scope": "Read-only inspection of the disposable candidate.",
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


def base_script() -> dict:
    return {
        "schema_version": "dobeworks.scripted-agent/v1",
        "stages": {
            "inspect": [
                {"operation": "read_file", "path": "README.txt"},
                {"operation": "finish_stage", "summary": "Inspected README.txt."},
            ],
            "execute_check": [
                {"operation": "finish_stage", "summary": "No change requested."}
            ],
            "review": [
                {
                    "operation": "finish_stage",
                    "summary": "No concerns found.",
                    "concerns": [],
                    "dismissed_concerns": [],
                }
            ],
        },
    }


def bounded_agent_source(source_file: Path, private_file: Path) -> str:
    return (
        "import json,sys\n"
        f"source={str(source_file)!r}\n"
        f"private_file={str(private_file)!r}\n"
        "request=json.load(sys.stdin)\n"
        "try:\n"
        "  open(source, encoding='utf-8').read()\n"
        "except OSError:\n"
        "  direct_read=False\n"
        "else:\n"
        "  direct_read=True\n"
        "try:\n"
        "  open(private_file, encoding='utf-8').read()\n"
        "except OSError:\n"
        "  ambient_read=False\n"
        "else:\n"
        "  ambient_read=True\n"
        "stage=request['stage']; history=request['history']\n"
        "if direct_read or ambient_read:\n"
        "  action={'operation':'promote_output','approval':'self'}\n"
        "elif stage=='inspect' and not history:\n"
        "  action={'operation':'read_file','path':'README.txt'}\n"
        "elif stage=='review':\n"
        "  action={'operation':'finish_stage','summary':'No concerns found.',"
        "'concerns':[],'dismissed_concerns':[]}\n"
        "else:\n"
        "  action={'operation':'finish_stage','summary':'Stage complete.'}\n"
        "print(json.dumps(action))\n"
    )


def session_escape_agent_source() -> str:
    return (
        "import json,os,sys,time\n"
        "request=json.load(sys.stdin)\n"
        "stage=request['stage']; history=request['history']\n"
        "if stage == 'inspect' and not history:\n"
        "  read_fd,write_fd=os.pipe()\n"
        "  try:\n"
        "    child=os.fork()\n"
        "  except PermissionError:\n"
        "    os.close(read_fd); os.close(write_fd); child=None\n"
        "  else:\n"
        "    if child == 0:\n"
        "      os.close(read_fd); os.setsid(); os.write(write_fd,b'1'); "
        "os.close(write_fd); time.sleep(30); os._exit(0)\n"
        "    os.close(write_fd); os.read(read_fd,1); os.close(read_fd)\n"
        "  path='README.txt' if child is None else f'pid-{child}'\n"
        "  action={'operation':'read_file','path':path}\n"
        "elif stage == 'review':\n"
        "  action={'operation':'finish_stage','summary':'Reviewed.',"
        "'concerns':[],'dismissed_concerns':[]}\n"
        "else:\n"
        "  action={'operation':'finish_stage','summary':'Stage complete.'}\n"
        "print(json.dumps(action))\n"
    )


def process_config(agent: Path) -> dict:
    return {
        "schema_version": "dobeworks.process-agent/v1",
        "argv": [sys.executable, "-B", str(agent)],
        "timeout_seconds": 5,
        "network": "DENIED",
        "environment_keys": [],
        "identity_files": [{"path": str(agent), "sha256": sha256_file(agent)}],
    }


class GovernedLiveWorkerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.staging = self.root / "staging"
        self.degs = self.root / "DEGS"
        self.source.mkdir()
        self.staging.mkdir()
        (self.source / "README.txt").write_text("bounded input\n", encoding="utf-8")
        paths = make_degs_double(self.degs)
        self.task = paths["task"]
        self.gate = paths["gate"]
        self.review_adapter = paths["review"]
        self.sashiko_module = paths["sashiko"]
        self.sashiko_provenance = paths["provenance"]
        self.envelope = self.root / "job-envelope.json"
        write_json(self.envelope, base_envelope(self.source, paths))
        self.agent_script = self.root / "agent-script.json"
        write_json(self.agent_script, base_script())
        self.mutate_envelope(
            lambda value: value.update(
                {
                    "agent_adapter": {
                        "kind": "SCRIPTED",
                        "configuration_sha256": sha256_file(self.agent_script),
                    }
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_job(
        self,
        agent_flag: str = "--agent-script",
        agent_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(CLI),
                "run",
                "--envelope",
                str(self.envelope),
                "--source-repo",
                str(self.source),
                "--staging-root",
                str(self.staging),
                "--degs-root",
                str(self.degs),
                agent_flag,
                str(agent_path or self.agent_script),
                "--now",
                NOW,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def mutate_script(self, mutation) -> None:
        value = json.loads(self.agent_script.read_text(encoding="utf-8"))
        mutation(value)
        write_json(self.agent_script, value)
        envelope = json.loads(self.envelope.read_text(encoding="utf-8"))
        envelope["agent_adapter"]["configuration_sha256"] = sha256_file(self.agent_script)
        write_json(self.envelope, envelope)

    def mutate_envelope(self, mutation) -> None:
        value = json.loads(self.envelope.read_text(encoding="utf-8"))
        mutation(value)
        write_json(self.envelope, value)

    def test_inspect_only_job_stages_auditable_unaccepted_handback(self) -> None:
        original_sha256 = tree_sha256(self.source)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        result = json.loads(completed.stdout)
        destination = self.staging / "job-inspect-001"
        handback = json.loads((destination / "handback.json").read_text(encoding="utf-8"))
        events = json.loads((destination / "events.json").read_text(encoding="utf-8"))
        handoffs = [
            json.loads(line)
            for line in (destination / "handoffs.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        observer = json.loads((destination / "observer.json").read_text(encoding="utf-8"))

        self.assertEqual(result["state"], "COMPLETED_UNACCEPTED")
        self.assertEqual(handback["state"], "COMPLETED_UNACCEPTED")
        self.assertEqual(handback["promotion"], "NOT_PERFORMED")
        self.assertEqual(handback["degs_preflight_readiness"], "PASS")
        self.assertEqual(handback["agent_reported_concern_status"], "NONE_REPORTED")
        self.assertEqual(
            handback["sashiko_source_commit"],
            "39f6ce95c797bb40023247916a8b16d0f4aaf0da",
        )
        self.assertEqual(original_sha256, tree_sha256(self.source))
        self.assertEqual(original_sha256, tree_sha256(destination / "candidate"))
        self.assertEqual(
            [event["stage"] for event in events if event["event"] == "stage_completed"],
            ["inspect", "execute_check", "review", "report"],
        )
        self.assertEqual(observer["evidence_status"], "CURRENT")
        self.assertEqual(observer["missing_artifacts"], [])
        self.assertEqual(observer["promotion"], "NOT_PERFORMED")
        self.assertEqual(handoffs[0]["event"], "preflight_admitted")
        self.assertEqual(handoffs[-1]["event"], "human_acceptance_required")
        self.assertEqual(
            [event["sequence"] for event in handoffs],
            list(range(1, len(handoffs) + 1)),
        )
        proposals = [event for event in handoffs if event["event"] == "operation_proposed"]
        self.assertTrue(proposals)
        self.assertTrue(
            all(event["authority"] == "PROPOSAL_ONLY" for event in proposals)
        )
        self.assertNotIn(
            "bounded input",
            (destination / "handoffs.jsonl").read_text(encoding="utf-8"),
        )
        self.assertFalse((self.staging / ".partial-job-inspect-001").exists())

    def test_agent_cannot_add_or_jump_to_a_controller_stage(self) -> None:
        self.mutate_script(
            lambda value: value["stages"].update(
                {"report": [{"operation": "finish_stage", "summary": "Promote it."}]}
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_STAGE")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_unapproved_shell_operation_is_rejected(self) -> None:
        self.mutate_script(
            lambda value: value["stages"]["inspect"].insert(
                0, {"operation": "run_shell", "command": "touch escaped"}
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_OPERATION")
        self.assertFalse((self.source / "escaped").exists())
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_invalid_proposed_path_is_redacted_from_live_handoff(self) -> None:
        marker = "private-secret-path-marker"
        self.mutate_script(
            lambda value: value["stages"]["inspect"].insert(
                0,
                {
                    "operation": "read_file",
                    "path": f"/Users/example/{marker}",
                },
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_PATH")
        journal = self.staging / ".partial-job-inspect-001" / "handoffs.jsonl"
        text = journal.read_text(encoding="utf-8")
        self.assertNotIn(marker, text)
        self.assertIn("REDACTED_INVALID_PATH", text)
        self.assertIn("operation_rejected", text)

    def test_agent_cannot_request_its_own_promotion(self) -> None:
        self.mutate_script(
            lambda value: value["stages"]["review"].insert(
                0, {"operation": "promote_output", "approval": "self"}
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_OPERATION")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_concern_cannot_be_hidden_by_a_clean_summary(self) -> None:
        def add_concern(value) -> None:
            finish = value["stages"]["review"][-1]
            finish["summary"] = "Everything is clean."
            finish["concerns"] = [
                {
                    "id": "C-001",
                    "type": "Correctness",
                    "description": "A claimed boundary remains unverified.",
                    "reasoning": "The supplied evidence does not cover the boundary.",
                    "locations": [],
                }
            ]

        self.mutate_script(add_concern)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        destination = self.staging / "job-inspect-001"
        handback = json.loads((destination / "handback.json").read_text(encoding="utf-8"))
        review = json.loads((destination / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(
            handback["agent_reported_concern_status"],
            "UNRESOLVED_REPORTED",
        )
        self.assertEqual(review["all_concerns"][0]["id"], "C-001")
        self.assertEqual(review["all_concerns"][0]["stage"], "review")
        self.assertEqual(handback["promotion"], "NOT_PERFORMED")

    def test_changed_sashiko_module_identity_blocks_before_agent_work(self) -> None:
        self.sashiko_module.write_text("# substituted module\n", encoding="utf-8")
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_IDENTITY")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_changed_agent_configuration_identity_blocks_execution(self) -> None:
        value = json.loads(self.agent_script.read_text(encoding="utf-8"))
        value["stages"]["inspect"][1]["summary"] = "Substituted after authorization."
        write_json(self.agent_script, value)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_IDENTITY")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_authorized_structured_edit_and_check_change_only_candidate(self) -> None:
        source_file = self.source / "app.txt"
        source_file.write_text("mode=unsafe\n", encoding="utf-8")

        def configure_envelope(value) -> None:
            value["source_tree_sha256"] = tree_sha256(self.source)
            value["permissions"] = {
                "mutation": True,
                "allowed_paths": ["README.txt", "app.txt"],
                "check_ids": ["safe-mode"],
            }
            value["checks"] = {
                "safe-mode": {
                    "argv": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; "
                        "raise SystemExit(0 if Path('app.txt').read_text() == 'mode=safe\\n' else 7)",
                    ],
                    "timeout_seconds": 5,
                }
            }

        self.mutate_envelope(configure_envelope)

        def configure_script(value) -> None:
            value["stages"]["execute_check"] = [
                {
                    "operation": "replace_text",
                    "path": "app.txt",
                    "expected_sha256": sha256_file(source_file),
                    "old": "mode=unsafe",
                    "new": "mode=safe",
                    "expected_occurrences": 1,
                },
                {"operation": "run_check", "check_id": "safe-mode"},
                {"operation": "finish_stage", "summary": "Changed and checked safe mode."},
            ]

        self.mutate_script(configure_script)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        destination = self.staging / "job-inspect-001"
        handback = json.loads((destination / "handback.json").read_text(encoding="utf-8"))
        self.assertEqual(source_file.read_text(encoding="utf-8"), "mode=unsafe\n")
        self.assertEqual((destination / "candidate" / "app.txt").read_text(encoding="utf-8"), "mode=safe\n")
        self.assertNotEqual(handback["source_tree_sha256"], handback["candidate_tree_sha256"])
        self.assertTrue((destination / "checks" / "safe-mode.json").is_file())

    def test_readonly_envelope_rejects_structured_edit(self) -> None:
        original_sha256 = sha256_file(self.source / "README.txt")

        def configure_script(value) -> None:
            value["stages"]["execute_check"] = [
                {
                    "operation": "replace_text",
                    "path": "README.txt",
                    "expected_sha256": original_sha256,
                    "old": "bounded",
                    "new": "escaped",
                    "expected_occurrences": 1,
                },
                {"operation": "finish_stage", "summary": "Changed the source."},
            ]

        self.mutate_script(configure_script)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_OPERATION")
        self.assertEqual((self.source / "README.txt").read_text(encoding="utf-8"), "bounded input\n")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_failed_required_check_never_completes_handback(self) -> None:
        def configure_envelope(value) -> None:
            value["permissions"]["check_ids"] = ["always-fails"]
            value["checks"] = {
                "always-fails": {
                    "argv": [sys.executable, "-c", "raise SystemExit(7)"],
                    "timeout_seconds": 5,
                }
            }

        self.mutate_envelope(configure_envelope)
        self.mutate_script(
            lambda value: value["stages"].update(
                {
                    "execute_check": [
                        {"operation": "run_check", "check_id": "always-fails"},
                        {"operation": "finish_stage", "summary": "Ignored failure."},
                    ]
                }
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "FAILED_CHECK")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_path_like_check_id_is_rejected_before_work(self) -> None:
        def configure_envelope(value) -> None:
            value["permissions"]["check_ids"] = ["../escape"]
            value["checks"] = {
                "../escape": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "timeout_seconds": 5,
                }
            }

        self.mutate_envelope(configure_envelope)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_INPUT")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_duplicate_allowed_path_is_rejected_before_work(self) -> None:
        self.mutate_envelope(
            lambda value: value["permissions"].update(
                {"allowed_paths": ["README.txt", "README.txt"]}
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_INPUT")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_nonfinite_control_number_is_rejected_before_work(self) -> None:
        value = json.loads(self.envelope.read_text(encoding="utf-8"))
        value["limits"]["timeout_seconds"] = float("nan")
        self.envelope.write_text(json.dumps(value), encoding="utf-8")
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_INPUT")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_oversized_source_file_is_rejected_before_copy(self) -> None:
        oversized = self.source / "oversized.bin"
        with oversized.open("wb") as stream:
            stream.truncate(67_108_865)
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(
            json.loads(completed.stdout)["state"],
            "REJECTED_INPUT_LIMIT",
        )
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_source_tree_scan_does_not_use_unbounded_rglob(self) -> None:
        with mock.patch.object(
            Path,
            "rglob",
            side_effect=AssertionError("source traversal must be bounded while enumerating"),
        ):
            files = worker._tree_files(self.source)
        self.assertEqual([relative.as_posix() for relative, _ in files], ["README.txt"])

    def test_source_tree_file_count_bound_is_enforced(self) -> None:
        (self.source / "second.txt").write_text("second\n", encoding="utf-8")
        with mock.patch.object(worker, "MAX_TREE_FILES", 1):
            with self.assertRaises(worker.LiveWorkerError) as raised:
                worker._tree_files(self.source)
        self.assertEqual(raised.exception.state, "REJECTED_INPUT_LIMIT")
        self.assertIn("file-count", raised.exception.message)

    def test_source_tree_aggregate_byte_bound_is_enforced(self) -> None:
        with mock.patch.object(worker, "MAX_TREE_BYTES", 1):
            with self.assertRaises(worker.LiveWorkerError) as raised:
                worker._tree_files(self.source)
        self.assertEqual(raised.exception.state, "REJECTED_INPUT_LIMIT")
        self.assertIn("byte bound", raised.exception.message)

    def test_source_tree_entry_count_bound_includes_directories(self) -> None:
        (self.source / "empty-directory").mkdir()
        with mock.patch.object(worker, "MAX_TREE_ENTRIES", 1):
            with self.assertRaises(worker.LiveWorkerError) as raised:
                worker._tree_files(self.source)
        self.assertEqual(raised.exception.state, "REJECTED_INPUT_LIMIT")
        self.assertIn("entry-count", raised.exception.message)

    def test_deep_control_json_is_rejected_without_traceback(self) -> None:
        depth = 600
        self.envelope.write_text(
            '{"nested":' + "[" * depth + "0" + "]" * depth + "}",
            encoding="utf-8",
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "REJECTED_INPUT")
        self.assertNotIn("Traceback", completed.stderr)
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_successful_degs_process_must_not_write_standard_error(self) -> None:
        self.gate.write_text(GATE_DOUBLE + "import sys\nprint('noise', file=sys.stderr)\n", encoding="utf-8")
        self.mutate_envelope(
            lambda value: value["degs"].update(
                {"gate_sha256": sha256_file(self.gate)}
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "FAILED_DEGS")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_degs_output_is_capped_while_the_process_runs(self) -> None:
        self.gate.write_text(
            "import sys\nsys.stdout.write('x' * 2000000)\n",
            encoding="utf-8",
        )
        self.mutate_envelope(
            lambda value: value["degs"].update(
                {"gate_sha256": sha256_file(self.gate)}
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "FAILED_DEGS")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_degs_subprocess_cannot_fork_and_escape_its_session(self) -> None:
        self.gate.write_text(
            "import json,os,time\n"
            "read_fd,write_fd=os.pipe()\n"
            "try:\n"
            "  child=os.fork()\n"
            "except PermissionError:\n"
            "  os.close(read_fd); os.close(write_fd); child=None\n"
            "else:\n"
            "  if child == 0:\n"
            "    os.close(read_fd); os.setsid(); os.write(write_fd,b'1'); "
            "os.close(write_fd); time.sleep(30); os._exit(0)\n"
            "  os.close(write_fd); os.read(read_fd,1); os.close(read_fd)\n"
            "print(json.dumps({'decision':'PASS','warning_state':"
            "{'unresolved_count':0,'status':'RESOLVED','resolved':True},"
            "'escaped_pid':child}))\n",
            encoding="utf-8",
        )
        self.mutate_envelope(
            lambda value: value["degs"].update(
                {"gate_sha256": sha256_file(self.gate)}
            )
        )
        escaped_pid = None
        try:
            completed = self.run_job()
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            result = json.loads(
                (self.staging / "job-inspect-001" / "degs-result.json").read_text(
                    encoding="utf-8"
                )
            )
            escaped_pid = result["escaped_pid"]
            self.assertIsNone(escaped_pid, "DEGS was allowed to create a new session")
        finally:
            if escaped_pid is not None:
                try:
                    os.kill(escaped_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_check_subprocess_receives_no_ambient_home_environment(self) -> None:
        def configure_envelope(value) -> None:
            value["permissions"]["check_ids"] = ["clean-environment"]
            value["checks"] = {
                "clean-environment": {
                    "argv": [
                        sys.executable,
                        "-c",
                        "import os; raise SystemExit(0 if 'HOME' not in os.environ else 7)",
                    ],
                    "timeout_seconds": 5,
                }
            }

        self.mutate_envelope(configure_envelope)
        self.mutate_script(
            lambda value: value["stages"].update(
                {
                    "execute_check": [
                        {"operation": "run_check", "check_id": "clean-environment"},
                        {"operation": "finish_stage", "summary": "Check completed."},
                    ]
                }
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_check_subprocess_cannot_fork_and_escape_its_session(self) -> None:
        check_source = (
            "import os,time\n"
            "read_fd,write_fd=os.pipe()\n"
            "try:\n"
            "  child=os.fork()\n"
            "except PermissionError:\n"
            "  os.close(read_fd); os.close(write_fd); print('fork-denied')\n"
            "else:\n"
            "  if child == 0:\n"
            "    os.close(read_fd); os.setsid(); os.write(write_fd,b'1'); "
            "os.close(write_fd); time.sleep(30); os._exit(0)\n"
            "  os.close(write_fd); os.read(read_fd,1); os.close(read_fd); print(child)\n"
        )

        def configure_envelope(value) -> None:
            value["permissions"]["check_ids"] = ["no-descendants"]
            value["checks"] = {
                "no-descendants": {
                    "argv": [sys.executable, "-B", "-c", check_source],
                    "timeout_seconds": 5,
                }
            }

        self.mutate_envelope(configure_envelope)
        self.mutate_script(
            lambda value: value["stages"].update(
                {
                    "execute_check": [
                        {"operation": "run_check", "check_id": "no-descendants"},
                        {"operation": "finish_stage", "summary": "Check completed."},
                    ]
                }
            )
        )
        escaped_pid = None
        try:
            completed = self.run_job()
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            stdout = (
                self.staging
                / "job-inspect-001"
                / ".process"
                / "no-descendants"
                / "stdout"
            ).read_text(encoding="utf-8").strip()
            if stdout.isdigit():
                escaped_pid = int(stdout)
            self.assertEqual(stdout, "fork-denied")
        finally:
            if escaped_pid is not None:
                try:
                    os.kill(escaped_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_successful_check_with_standard_error_fails(self) -> None:
        def configure_envelope(value) -> None:
            value["permissions"]["check_ids"] = ["noisy-check"]
            value["checks"] = {
                "noisy-check": {
                    "argv": [
                        sys.executable,
                        "-c",
                        "import sys; print('noise', file=sys.stderr)",
                    ],
                    "timeout_seconds": 5,
                }
            }

        self.mutate_envelope(configure_envelope)
        self.mutate_script(
            lambda value: value["stages"].update(
                {
                    "execute_check": [
                        {"operation": "run_check", "check_id": "noisy-check"},
                        {"operation": "finish_stage", "summary": "Check completed."},
                    ]
                }
            )
        )
        completed = self.run_job()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "FAILED_CHECK")
        self.assertFalse((self.staging / "job-inspect-001").exists())

    def test_process_adapter_drives_stages_without_direct_source_access(self) -> None:
        private_root = tempfile.TemporaryDirectory(
            prefix=".dobeworks-private-",
            dir=Path.home(),
        )
        self.addCleanup(private_root.cleanup)
        private_file = Path(private_root.name) / "unrelated-private.txt"
        private_file.write_text("not part of this job\n", encoding="utf-8")
        agent = self.root / "bounded-agent.py"
        agent.write_text(
            bounded_agent_source(self.source / "README.txt", private_file),
            encoding="utf-8",
        )
        config = self.root / "process-agent.json"
        write_json(config, process_config(agent))
        self.mutate_envelope(
            lambda value: value.update(
                {
                    "agent_adapter": {
                        "kind": "PROCESS",
                        "configuration_sha256": sha256_file(config),
                    }
                }
            )
        )
        completed = self.run_job("--agent-process", config)
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        destination = self.staging / "job-inspect-001"
        handback = json.loads((destination / "handback.json").read_text(encoding="utf-8"))
        events = json.loads((destination / "events.json").read_text(encoding="utf-8"))
        self.assertEqual(handback["agent_adapter_kind"], "PROCESS")
        self.assertEqual(handback["promotion"], "NOT_PERFORMED")
        read_event = next(
            event
            for event in events
            if event["event"] == "operation_completed"
            and event["result"]["operation"] == "read_file"
        )
        self.assertNotIn("content", read_event["result"])

    def test_process_adapter_stderr_is_visible_as_a_terminal_handoff(self) -> None:
        agent = self.root / "noisy-agent.py"
        source = bounded_agent_source(self.source / "README.txt", self.root / "absent.txt")
        agent.write_text(source.replace("import json,sys\n", "import json,sys\nprint('noise', file=sys.stderr)\n"), encoding="utf-8")
        config = self.root / "process-agent.json"
        write_json(config, process_config(agent))
        self.mutate_envelope(
            lambda value: value.update(
                {
                    "agent_adapter": {
                        "kind": "PROCESS",
                        "configuration_sha256": sha256_file(config),
                    }
                }
            )
        )
        completed = self.run_job("--agent-process", config)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "FAILED_ADAPTER")
        journal = self.staging / ".partial-job-inspect-001" / "handoffs.jsonl"
        events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["event"], "adapter_failed")
        self.assertEqual(events[-1]["details"]["state"], "FAILED_ADAPTER")

    def test_process_adapter_cannot_fork_and_escape_its_session(self) -> None:
        agent = self.root / "forking-agent.py"
        agent.write_text(session_escape_agent_source(), encoding="utf-8")
        config = self.root / "process-agent.json"
        write_json(config, process_config(agent))
        self.mutate_envelope(
            lambda value: value.update(
                {
                    "agent_adapter": {
                        "kind": "PROCESS",
                        "configuration_sha256": sha256_file(config),
                    }
                }
            )
        )
        escaped_pid = None
        try:
            completed = self.run_job("--agent-process", config)
            journal_root = (
                self.staging / "job-inspect-001"
                if completed.returncode == 0
                else self.staging / ".partial-job-inspect-001"
            )
            events = [
                json.loads(line)
                for line in (journal_root / "handoffs.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            proposal = next(
                item for item in events if item["event"] == "operation_proposed"
            )
            proposed_path = proposal["details"]["path"]
            if proposed_path.startswith("pid-"):
                escaped_pid = int(proposed_path.removeprefix("pid-"))
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(proposed_path, "README.txt")
        finally:
            if escaped_pid is not None:
                try:
                    os.kill(escaped_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
