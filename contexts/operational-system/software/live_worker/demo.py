#!/usr/bin/env python3
"""Run a synthetic governed process-Adapter demonstration and render it."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parent
REPOSITORY = BASE.parents[3]
CONTROLLER = BASE / "governed_live_worker.py"
VIEWER = BASE / "handoff_view.py"
REFERENCE_AGENT = BASE / "examples" / "reference_process_agent.py"

sys.path.insert(0, str(BASE))
from governed_live_worker import sha256_file, tree_sha256, write_json  # noqa: E402


def _degs_paths(root: Path) -> dict[str, Path]:
    paths = {
        "gate": root / "bin" / "engineering-gate.py",
        "task": root / "fixtures" / "tier0-readonly-pass.json",
        "review": root / "bin" / "review-state.py",
        "sashiko": root / "sashiko_derived" / "__init__.py",
        "provenance": root / "provenance" / "sashiko-source.json",
    }
    for path in paths.values():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required DEGS file is unavailable: {path}")
    return paths


def _build_envelope(
    job_id: str,
    source: Path,
    config: Path,
    paths: dict[str, Path],
    now: datetime,
) -> dict:
    return {
        "schema_version": "dobeworks.governed-live-job/v1",
        "job_id": job_id,
        "objective": "Inspect one synthetic file through the governed process seam.",
        "issued_at": (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "source_tree_sha256": tree_sha256(source),
        "agent_adapter": {
            "kind": "PROCESS",
            "configuration_sha256": sha256_file(config),
        },
        "degs": _degs_identity(paths),
        "dispatch_authority": {
            "authorized": True,
            "authorized_by": "local-demo-launcher",
            "scope": "Synthetic read-only reference demonstration.",
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


def _degs_identity(paths: dict[str, Path]) -> dict:
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


def _prepare_run(runs_root: Path, degs_root: Path) -> tuple[Path, Path, Path, str]:
    now = datetime.now(timezone.utc)
    job_id = "reference-" + now.strftime("%Y%m%d-%H%M%S-%f")
    run_root = runs_root / job_id
    source, staging = run_root / "source", run_root / "staging"
    source.mkdir(parents=True)
    staging.mkdir()
    (source / "README.txt").write_text(
        "Synthetic input for the governed live-worker reference run.\n",
        encoding="utf-8",
    )
    config = run_root / "process-agent.json"
    write_json(
        config,
        {
            "schema_version": "dobeworks.process-agent/v1",
            "argv": [sys.executable, "-B", str(REFERENCE_AGENT)],
            "timeout_seconds": 5,
            "network": "DENIED",
            "environment_keys": [],
            "identity_files": [
                {"path": str(REFERENCE_AGENT), "sha256": sha256_file(REFERENCE_AGENT)}
            ],
        },
    )
    envelope = run_root / "job-envelope.json"
    paths = _degs_paths(degs_root)
    write_json(envelope, _build_envelope(job_id, source, config, paths, now))
    now_text = now.isoformat().replace("+00:00", "Z")
    return envelope, config, staging, now_text


def _run_demo(args: argparse.Namespace) -> int:
    degs_root = args.degs_root.resolve()
    envelope, config, staging, now_text = _prepare_run(
        args.runs_root.resolve(),
        degs_root,
    )
    command = [
        sys.executable,
        "-B",
        str(CONTROLLER),
        "run",
        "--envelope",
        str(envelope),
        "--source-repo",
        str(envelope.parent / "source"),
        "--staging-root",
        str(staging),
        "--degs-root",
        str(degs_root),
        "--agent-process",
        str(config),
        "--now",
        now_text,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if completed.returncode != 0 or completed.stderr:
        print(completed.stderr or completed.stdout, file=sys.stderr, end="")
        return 2
    result = json.loads(completed.stdout)
    handback = Path(result["handback_path"])
    view = subprocess.run(
        [sys.executable, "-B", str(VIEWER), str(handback.parent / "handoffs.jsonl")],
        check=False,
    )
    print(f"\nHandback: {handback}")
    return 0 if view.returncode == 0 else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--degs-root",
        type=Path,
        default=REPOSITORY.parent / "DEGS",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=REPOSITORY / "interface" / "Runs" / "governed-live-worker",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run_demo(args)
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print(f"demo failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
