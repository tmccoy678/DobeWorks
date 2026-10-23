#!/usr/bin/env python3
"""Governed live-worker controller with an atomic staged handback seam."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENVELOPE_SCHEMA = "dobeworks.governed-live-job/v1"
SCRIPT_SCHEMA = "dobeworks.scripted-agent/v1"
HAND_BACK_SCHEMA = "dobeworks.governed-live-handback/v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
JOB_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CONTROL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_CONTROL_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 50_000
MAX_JSON_NUMBER_DIGITS = 4_300
MAX_TREE_FILES = 10_000
MAX_TREE_ENTRIES = 20_000
MAX_TREE_BYTES = 536_870_912
MAX_IDENTITY_FILE_BYTES = 67_108_864
FIXED_STAGES = ("inspect", "execute_check", "review")
DEGS_FILES = (
    ("gate_relative_path", "gate_sha256"),
    ("task_relative_path", "task_sha256"),
    ("review_relative_path", "review_sha256"),
    ("sashiko_relative_path", "sashiko_sha256"),
    ("sashiko_provenance_relative_path", "sashiko_provenance_sha256"),
)


class LiveWorkerError(Exception):
    """A bounded rejection surfaced through the public command seam."""

    def __init__(self, state: str, message: str) -> None:
        super().__init__(message)
        self.state = state
        self.message = message


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LiveWorkerError("REJECTED_INPUT", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _bounded_integer(token: str) -> int:
    if sum(character.isdigit() for character in token) > MAX_JSON_NUMBER_DIGITS:
        raise ValueError("JSON integer exceeds the digit bound")
    return int(token)


def _bounded_float(token: str) -> float:
    if sum(character.isdigit() for character in token) > MAX_JSON_NUMBER_DIGITS:
        raise ValueError("JSON decimal exceeds the digit bound")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("JSON decimal is outside the finite float range")
    return value


def _validate_json_tree(value: Any, state: str) -> Any:
    stack, nodes = [(value, 0)], 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise LiveWorkerError(state, "JSON structure exceeds its bound")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return value


def _parse_json(raw: bytes, label: str, state: str) -> Any:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate,
            parse_constant=_reject_constant,
            parse_int=_bounded_integer,
            parse_float=_bounded_float,
        )
    except LiveWorkerError as error:
        raise LiveWorkerError(state, f"invalid {label}: {error.message}") from error
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise LiveWorkerError(state, f"invalid {label}: {error}") from error
    return _validate_json_tree(value, state)


def load_json(path: Path, maximum: int = MAX_CONTROL_BYTES) -> Any:
    """Load one bounded regular JSON file with duplicate-key rejection."""
    try:
        if path.is_symlink() or not path.is_file():
            raise LiveWorkerError("REJECTED_PATH", f"not a regular file: {path}")
        raw = path.read_bytes()
    except OSError as error:
        raise LiveWorkerError("REJECTED_PATH", f"cannot read {path}: {error}") from error
    if len(raw) > maximum:
        raise LiveWorkerError("REJECTED_INPUT_LIMIT", f"input exceeds {maximum} bytes")
    return _parse_json(raw, "JSON input", "REJECTED_INPUT")


def write_json(path: Path, value: Any) -> None:
    """Write one deterministic JSON artifact."""
    try:
        encoded = (
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        path.write_bytes(encoded)
    except (OSError, TypeError, ValueError) as error:
        raise LiveWorkerError("FAILED_HAND_BACK", f"cannot write {path.name}: {error}") from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        if path.stat().st_size > MAX_IDENTITY_FILE_BYTES:
            raise LiveWorkerError("REJECTED_INPUT_LIMIT", f"identity file exceeds bound: {path}")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1_048_576), b""):
                digest.update(block)
    except OSError as error:
        raise LiveWorkerError("REJECTED_PATH", f"cannot hash file: {path}") from error
    return digest.hexdigest()


def _tree_files(root: Path) -> list[tuple[Path, Path]]:
    if root.is_symlink() or not root.is_dir():
        raise LiveWorkerError("REJECTED_PATH", f"not a regular source directory: {root}")
    files: list[tuple[Path, Path]] = []
    pending = [Path()]
    entry_count = 0
    total_bytes = 0
    try:
        while pending:
            directory_relative = pending.pop()
            directory = root / directory_relative
            if directory.is_symlink() or not directory.is_dir():
                raise LiveWorkerError(
                    "REJECTED_PATH",
                    f"source directory changed during inspection: {directory_relative}",
                )
            with os.scandir(directory) as entries:
                for entry in entries:
                    entry_count += 1
                    if entry_count > MAX_TREE_ENTRIES:
                        raise LiveWorkerError(
                            "REJECTED_INPUT_LIMIT",
                            "source tree exceeds the entry-count bound",
                        )
                    relative = directory_relative / entry.name
                    if ".git" in relative.parts:
                        continue
                    if entry.is_symlink():
                        raise LiveWorkerError(
                            "REJECTED_PATH", f"symlink is prohibited: {relative}"
                        )
                    if entry.is_file(follow_symlinks=False):
                        if len(files) >= MAX_TREE_FILES:
                            raise LiveWorkerError(
                                "REJECTED_INPUT_LIMIT",
                                "source tree exceeds the file-count bound",
                            )
                        total_bytes += entry.stat(follow_symlinks=False).st_size
                        if total_bytes > MAX_TREE_BYTES:
                            raise LiveWorkerError(
                                "REJECTED_INPUT_LIMIT",
                                "source tree exceeds the byte bound",
                            )
                        files.append((relative, Path(entry.path)))
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(relative)
                    else:
                        raise LiveWorkerError(
                            "REJECTED_PATH", f"unsupported source entry: {relative}"
                        )
    except LiveWorkerError:
        raise
    except OSError as error:
        raise LiveWorkerError(
            "REJECTED_PATH", "source tree changed during inspection"
        ) from error
    files.sort(key=lambda item: item[0])
    return files


def tree_sha256(root: Path) -> str:
    """Hash relative path identities and file bytes, excluding Git metadata."""
    digest = hashlib.sha256()
    for relative, path in _tree_files(root):
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must be an object")
    keys = set(value)
    if keys != expected:
        raise LiveWorkerError("REJECTED_INPUT", f"{label} fields differ: {sorted(keys ^ expected)}")
    return value


def _nonblank(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must be a nonblank string")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must be lowercase SHA-256")
    return value


def _control_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or CONTROL_ID_PATTERN.fullmatch(value) is None:
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must be a path-safe control ID")
    return value


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must be {minimum} through {maximum}")
    return value


def _relative_path(value: Any, label: str) -> str:
    text = _nonblank(value, label)
    path = Path(text)
    if path.is_absolute() or text != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise LiveWorkerError("REJECTED_PATH", f"{label} must be a normalized relative path")
    if len(text.encode("utf-8")) > 4096 or len(path.parts) > 128:
        raise LiveWorkerError("REJECTED_PATH", f"{label} exceeds the path bound")
    if any(len(part.encode("utf-8")) > 255 for part in path.parts):
        raise LiveWorkerError("REJECTED_PATH", f"{label} has an oversized component")
    return text


def _parse_time(value: Any, label: str) -> datetime:
    text = _nonblank(value, label)
    if not text.endswith("Z"):
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must use UTC Z notation")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise LiveWorkerError("REJECTED_INPUT", f"invalid {label}") from error
    if parsed.tzinfo != timezone.utc:
        raise LiveWorkerError("REJECTED_INPUT", f"{label} must be UTC")
    return parsed


def validate_envelope(value: Any, now_text: str) -> dict[str, Any]:
    """Validate the closed version-one job contract and its finite bounds."""
    expected = {"schema_version", "job_id", "objective", "issued_at", "expires_at", "source_tree_sha256", "agent_adapter", "degs", "dispatch_authority", "permissions", "checks", "limits"}
    envelope = _exact_keys(value, expected, "envelope")
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise LiveWorkerError("REJECTED_INPUT", "unsupported envelope schema")
    if not isinstance(envelope["job_id"], str) or JOB_ID_PATTERN.fullmatch(envelope["job_id"]) is None:
        raise LiveWorkerError("REJECTED_INPUT", "invalid job_id")
    _nonblank(envelope["objective"], "objective")
    issued = _parse_time(envelope["issued_at"], "issued_at")
    expires = _parse_time(envelope["expires_at"], "expires_at")
    now = _parse_time(now_text, "now")
    if not issued <= now <= expires or expires <= issued:
        raise LiveWorkerError("REJECTED_TIME", "job is not active at the supplied time")
    _sha256(envelope["source_tree_sha256"], "source_tree_sha256")
    _validate_agent_adapter(envelope["agent_adapter"])
    _validate_degs(envelope["degs"])
    _validate_authority(envelope["dispatch_authority"])
    _validate_permissions(envelope["permissions"])
    _validate_checks(envelope["checks"])
    _validate_limits(envelope["limits"])
    if set(envelope["checks"]) != set(envelope["permissions"]["check_ids"]):
        raise LiveWorkerError("REJECTED_INPUT", "checks must exactly match permissions.check_ids")
    return envelope


def _validate_agent_adapter(value: Any) -> None:
    adapter = _exact_keys(value, {"kind", "configuration_sha256"}, "agent_adapter")
    if adapter["kind"] not in {"SCRIPTED", "PROCESS"}:
        raise LiveWorkerError("REJECTED_ADAPTER", "unsupported agent adapter kind")
    _sha256(adapter["configuration_sha256"], "agent_adapter.configuration_sha256")


def _validate_degs(value: Any) -> None:
    expected = {field for pair in DEGS_FILES for field in pair}
    degs = _exact_keys(value, expected, "degs")
    for path_field, digest_field in DEGS_FILES:
        _relative_path(degs[path_field], f"degs.{path_field}")
        _sha256(degs[digest_field], f"degs.{digest_field}")


def _validate_authority(value: Any) -> None:
    authority = _exact_keys(value, {"authorized", "authorized_by", "scope"}, "dispatch_authority")
    if authority["authorized"] is not True:
        raise LiveWorkerError("REJECTED_AUTHORITY", "dispatch authority is not recorded")
    _nonblank(authority["authorized_by"], "dispatch_authority.authorized_by")
    _nonblank(authority["scope"], "dispatch_authority.scope")


def _validate_permissions(value: Any) -> None:
    permissions = _exact_keys(value, {"mutation", "allowed_paths", "check_ids"}, "permissions")
    if not isinstance(permissions["mutation"], bool):
        raise LiveWorkerError("REJECTED_INPUT", "permissions.mutation must be Boolean")
    if not isinstance(permissions["allowed_paths"], list) or not permissions["allowed_paths"]:
        raise LiveWorkerError("REJECTED_INPUT", "permissions.allowed_paths must be nonempty")
    for index, path in enumerate(permissions["allowed_paths"]):
        _relative_path(path, f"permissions.allowed_paths[{index}]")
    if len(set(permissions["allowed_paths"])) != len(permissions["allowed_paths"]):
        raise LiveWorkerError("REJECTED_INPUT", "permissions.allowed_paths must be unique")
    if not isinstance(permissions["check_ids"], list):
        raise LiveWorkerError("REJECTED_INPUT", "permissions.check_ids must be an array")
    for check_id in permissions["check_ids"]:
        _control_id(check_id, "permissions.check_ids item")
    if len(set(permissions["check_ids"])) != len(permissions["check_ids"]):
        raise LiveWorkerError("REJECTED_INPUT", "permissions.check_ids must be unique")


def _validate_checks(value: Any) -> None:
    if not isinstance(value, dict):
        raise LiveWorkerError("REJECTED_INPUT", "checks must be an object")
    for check_id, definition in value.items():
        _control_id(check_id, "check id")
        check = _exact_keys(definition, {"argv", "timeout_seconds"}, f"checks.{check_id}")
        if not isinstance(check["argv"], list) or not check["argv"]:
            raise LiveWorkerError("REJECTED_INPUT", f"checks.{check_id}.argv must be nonempty")
        for argument in check["argv"]:
            _nonblank(argument, f"checks.{check_id}.argv item")
        _integer(check["timeout_seconds"], 1, 30, f"checks.{check_id}.timeout_seconds")


def _validate_limits(value: Any) -> None:
    limits = _exact_keys(value, {"max_actions_per_stage", "timeout_seconds", "max_file_bytes", "max_output_bytes"}, "limits")
    _integer(limits["max_actions_per_stage"], 1, 32, "limits.max_actions_per_stage")
    _integer(limits["timeout_seconds"], 1, 30, "limits.timeout_seconds")
    _integer(limits["max_file_bytes"], 1, 1_048_576, "limits.max_file_bytes")
    _integer(limits["max_output_bytes"], 1024, 4_194_304, "limits.max_output_bytes")


def _beneath(root: Path, relative_text: str) -> Path:
    relative = Path(_relative_path(relative_text, "operation path"))
    candidate = root.joinpath(relative)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise LiveWorkerError("REJECTED_PATH", f"unavailable operation path: {relative}") from error
    if resolved_root not in resolved.parents and resolved != resolved_root:
        raise LiveWorkerError("REJECTED_PATH", f"operation path escapes candidate: {relative}")
    if candidate.is_symlink() or not resolved.is_file():
        raise LiveWorkerError("REJECTED_PATH", f"operation path is not a regular file: {relative}")
    return resolved


def _verify_allowed_path(relative: str, permissions: dict[str, Any]) -> None:
    if relative not in permissions["allowed_paths"]:
        raise LiveWorkerError("REJECTED_OPERATION", f"path is not allowed: {relative}")


def validate_script(value: Any, maximum_actions: int) -> dict[str, list[dict[str, Any]]]:
    script = _exact_keys(value, {"schema_version", "stages"}, "agent script")
    if script["schema_version"] != SCRIPT_SCHEMA:
        raise LiveWorkerError("REJECTED_ADAPTER", "unsupported agent script schema")
    stages = script["stages"]
    if not isinstance(stages, dict):
        raise LiveWorkerError("REJECTED_ADAPTER", "agent script stages must be an object")
    if set(stages) != set(FIXED_STAGES):
        raise LiveWorkerError("REJECTED_STAGE", "agent script cannot add, omit, or reorder controller stages")
    for stage in FIXED_STAGES:
        actions = stages[stage]
        if not isinstance(actions, list) or not 1 <= len(actions) <= maximum_actions:
            raise LiveWorkerError("REJECTED_ADAPTER", f"invalid action count for {stage}")
        if not all(isinstance(action, dict) for action in actions):
            raise LiveWorkerError("REJECTED_ADAPTER", f"actions for {stage} must be objects")
    return stages


def _validate_process_config(value: Any, envelope: dict[str, Any]) -> dict[str, Any]:
    expected = {"schema_version", "argv", "timeout_seconds", "network", "environment_keys", "identity_files"}
    config = _exact_keys(value, expected, "process agent configuration")
    if config["schema_version"] != "dobeworks.process-agent/v1":
        raise LiveWorkerError("REJECTED_ADAPTER", "unsupported process agent schema")
    if not isinstance(config["argv"], list) or not 1 <= len(config["argv"]) <= 32:
        raise LiveWorkerError("REJECTED_ADAPTER", "process argv must contain 1 through 32 strings")
    for argument in config["argv"]:
        if not isinstance(argument, str) or not argument or len(argument) > 4096:
            raise LiveWorkerError("REJECTED_ADAPTER", "process argv contains an invalid argument")
    timeout = _integer(config["timeout_seconds"], 1, 30, "process timeout_seconds")
    if timeout > envelope["limits"]["timeout_seconds"]:
        raise LiveWorkerError("REJECTED_ADAPTER", "process timeout exceeds the envelope")
    if config["network"] not in {"ALLOWED", "DENIED"}:
        raise LiveWorkerError("REJECTED_ADAPTER", "process network must be ALLOWED or DENIED")
    _validate_environment_keys(config["environment_keys"])
    _validate_identity_files(config["identity_files"], config["argv"])
    return config


def _validate_environment_keys(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 16:
        raise LiveWorkerError("REJECTED_ADAPTER", "environment_keys must contain at most 16 names")
    prohibited = {"HOME", "PATH", "PYTHONPATH", "SHELL", "PWD", "OLDPWD"}
    for key in value:
        if not isinstance(key, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key) is None:
            raise LiveWorkerError("REJECTED_ADAPTER", "invalid environment key")
        if key in prohibited or key.startswith(("DYLD_", "LD_")):
            raise LiveWorkerError("REJECTED_ADAPTER", f"prohibited environment key: {key}")
    if len(set(value)) != len(value):
        raise LiveWorkerError("REJECTED_ADAPTER", "environment_keys must be unique")


def _trusted_system_path(path: Path) -> bool:
    roots = ("/System", "/usr", "/bin", "/sbin", "/Applications", "/Library")
    text = str(path)
    return any(text == root or text.startswith(root + "/") for root in roots)


def _validate_identity_files(value: Any, argv: list[str]) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise LiveWorkerError("REJECTED_ADAPTER", "identity_files must contain 1 through 32 records")
    identities: set[str] = set()
    for index, item in enumerate(value):
        record = _exact_keys(item, {"path", "sha256"}, f"identity_files[{index}]")
        path = Path(_nonblank(record["path"], f"identity_files[{index}].path"))
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise LiveWorkerError("REJECTED_ADAPTER", "identity file must be an absolute regular file")
        if sha256_file(path) != _sha256(record["sha256"], f"identity_files[{index}].sha256"):
            raise LiveWorkerError("REJECTED_IDENTITY", f"process identity mismatch: {path}")
        identities.add(str(path.resolve()))
    for argument in argv:
        path = Path(argument)
        if path.is_absolute() and path.is_file() and not _trusted_system_path(path.resolve()):
            if str(path.resolve()) not in identities:
                raise LiveWorkerError("REJECTED_IDENTITY", f"unbound process file: {path}")


class ScriptedAdapter:
    kind = "SCRIPTED"

    def __init__(self, stages: dict[str, list[dict[str, Any]]]) -> None:
        self.stages = stages

    def next_action(self, stage: str, index: int, _request: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.stages[stage][index]
        except IndexError as error:
            raise LiveWorkerError("REJECTED_STAGE", f"stage {stage} exhausted before finish") from error

    def confirm_finish(self, stage: str, next_index: int) -> None:
        if next_index != len(self.stages[stage]):
            raise LiveWorkerError("REJECTED_STAGE", f"action follows finish in {stage}")


class ProcessAdapter:
    kind = "PROCESS"

    def __init__(self, config: dict[str, Any], envelope: dict[str, Any], denied_roots: list[Path]) -> None:
        self.config = config
        self.envelope = envelope
        self.denied_roots = denied_roots

    def next_action(self, _stage: str, _index: int, request: dict[str, Any]) -> dict[str, Any]:
        return _run_process_agent(self.config, self.envelope, self.denied_roots, request)

    def confirm_finish(self, _stage: str, _next_index: int) -> None:
        return


def _load_adapter(envelope: dict[str, Any], adapter_path: Path, source: Path, staging: Path, degs: Path):
    if sha256_file(adapter_path) != envelope["agent_adapter"]["configuration_sha256"]:
        raise LiveWorkerError("REJECTED_IDENTITY", "agent configuration identity mismatch")
    value = load_json(adapter_path)
    if envelope["agent_adapter"]["kind"] == "SCRIPTED":
        stages = validate_script(value, envelope["limits"]["max_actions_per_stage"])
        return ScriptedAdapter(stages)
    config = _validate_process_config(value, envelope)
    return ProcessAdapter(config, envelope, [source, staging, degs])


def _verify_degs_files(envelope: dict[str, Any], degs_root: Path) -> dict[str, Path]:
    config = envelope["degs"]
    verified: dict[str, Path] = {}
    for path_field, digest_field in DEGS_FILES:
        path = _beneath(degs_root, config[path_field])
        if sha256_file(path) != config[digest_field]:
            raise LiveWorkerError("REJECTED_IDENTITY", f"DEGS identity mismatch: {path_field}")
        verified[path_field] = path
    return verified


def _terminate_process_group(process_id: int) -> None:
    try:
        os.killpg(process_id, signal.SIGKILL)
    except ProcessLookupError:
        return


def _wait_process_group(
    process: subprocess.Popen,
    timeout: int,
    timeout_state: str,
    label: str,
) -> int:
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _terminate_process_group(process.pid)
        process.wait()
        raise LiveWorkerError(timeout_state, f"{label} exceeded its timeout") from error
    _terminate_process_group(process.pid)
    return returncode


def _run_json_process(argv: list[str], cwd: Path, timeout: int, maximum_output: int, label: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dobeworks-degs-") as temporary:
        root = Path(temporary)
        stdout_path, stderr_path = root / "stdout", root / "stderr"
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    env=_process_environment([]),
                    preexec_fn=lambda: _child_limits(maximum_output),
                )
                returncode = _wait_process_group(process, timeout, "FAILED_DEGS", label)
            stdout_bytes, stderr_bytes = stdout_path.read_bytes(), stderr_path.read_bytes()
        except (OSError, subprocess.SubprocessError) as error:
            raise LiveWorkerError("FAILED_DEGS", f"{label} invocation failed: {error}") from error
    if len(stdout_bytes) + len(stderr_bytes) > maximum_output:
        raise LiveWorkerError("FAILED_DEGS", f"{label} output exceeded the envelope bound")
    if returncode == 0 and stderr_bytes:
        raise LiveWorkerError("FAILED_DEGS", f"{label} wrote unexpected standard error")
    payload = _parse_json(stdout_bytes, f"{label} JSON result", "FAILED_DEGS")
    if returncode != 0:
        raise LiveWorkerError("BLOCKED_DEGS", f"{label} returned non-success")
    if not isinstance(payload, dict):
        raise LiveWorkerError("FAILED_DEGS", f"{label} result must be an object")
    return payload


def _run_degs(envelope: dict[str, Any], degs_root: Path, files: dict[str, Path]) -> dict[str, Any]:
    payload = _run_json_process(
        [sys.executable, "-I", "-B", str(files["gate_relative_path"]), "evaluate", str(files["task_relative_path"]), "--json"],
        degs_root,
        envelope["limits"]["timeout_seconds"],
        envelope["limits"]["max_output_bytes"],
        "DEGS gate",
    )
    warning = payload.get("warning_state", {}) if isinstance(payload, dict) else {}
    if payload.get("decision") != "PASS":
        raise LiveWorkerError("BLOCKED_DEGS", "DEGS readiness did not pass")
    if warning.get("unresolved_count") != 0 or warning.get("resolved") is not True:
        raise LiveWorkerError("BLOCKED_DEGS", "DEGS reports unresolved warnings")
    return payload


def _run_review_state(envelope: dict[str, Any], degs_root: Path, files: dict[str, Path], partial: Path, review_finish: dict[str, Any]) -> dict[str, Any]:
    request = {
        "schema_version": "degs.sashiko-review-request/v1",
        "stage_outputs": [
            {
                "stage": "review",
                "concerns": review_finish["concerns"],
                "dismissed_concerns": review_finish["dismissed_concerns"],
            }
        ],
    }
    request_path = partial / "review-request.json"
    write_json(request_path, request)
    payload = _run_json_process(
        [sys.executable, "-I", "-B", str(files["review_relative_path"]), "build", str(request_path), "--json"],
        degs_root,
        envelope["limits"]["timeout_seconds"],
        envelope["limits"]["max_output_bytes"],
        "DEGS review-state adapter",
    )
    required = {
        "schema_version",
        "sashiko_source_commit",
        "report_basis",
        "agent_reported_concern_status",
        "all_concerns",
        "all_dismissed_concerns",
        "deduplicated_concerns",
        "deduplicated_dismissed_concerns",
        "conflict_resolved_concerns",
        "findings",
    }
    result = _exact_keys(payload, required, "DEGS review-state result")
    scalar_fields = {
        "schema_version",
        "sashiko_source_commit",
        "report_basis",
        "agent_reported_concern_status",
    }
    for field in required - scalar_fields:
        if not isinstance(result[field], list):
            raise LiveWorkerError("FAILED_DEGS", f"DEGS review field is not an array: {field}")
    provenance = load_json(files["sashiko_provenance_relative_path"])
    source_commit = provenance.get("commit") if isinstance(provenance, dict) else None
    expected_status = "UNRESOLVED_REPORTED" if result["all_concerns"] else "NONE_REPORTED"
    if (
        result["schema_version"] != "degs.sashiko-review-state/v1"
        or result["sashiko_source_commit"] != source_commit
        or result["report_basis"] != "AGENT_SUPPLIED_REVIEW_VALUES"
        or result["agent_reported_concern_status"] != expected_status
    ):
        raise LiveWorkerError("FAILED_DEGS", "DEGS review-state result is inconsistent")
    return result


def _copy_candidate(source: Path, destination: Path) -> None:
    _tree_files(source)
    try:
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
    except OSError as error:
        raise LiveWorkerError("FAILED_CANDIDATE", f"cannot create candidate: {error}") from error


def _event(events: list[dict[str, Any]], event: str, stage: str, now_text: str, **fields: Any) -> None:
    record = {"event": event, "stage": stage, "observed_at": now_text}
    record.update(fields)
    events.append(record)


class HandoffJournal:
    """Append a compact live view of proposals, enforcement, and authority."""

    def __init__(self, path: Path, job_id: str, observed_at: str) -> None:
        self.path = path
        self.job_id = job_id
        self.observed_at = observed_at
        self.sequence = 0

    def emit(
        self,
        event: str,
        stage: str,
        actor: str,
        authority: str,
        details: dict[str, Any],
    ) -> None:
        self.sequence += 1
        record = {
            "schema_version": "dobeworks.handoff-event/v1",
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "job_id": self.job_id,
            "event": event,
            "stage": stage,
            "actor": actor,
            "authority": authority,
            "details": details,
        }
        try:
            encoded = (
                json.dumps(record, allow_nan=False, sort_keys=True) + "\n"
            ).encode("utf-8")
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, TypeError, ValueError) as error:
            raise LiveWorkerError(
                "FAILED_HAND_BACK",
                f"cannot append handoff event: {error}",
            ) from error


def _read_operation(action: dict[str, Any], candidate: Path, envelope: dict[str, Any]) -> dict[str, Any]:
    action = _exact_keys(action, {"operation", "path"}, "read_file operation")
    relative = _relative_path(action["path"], "read_file.path")
    _verify_allowed_path(relative, envelope["permissions"])
    path = _beneath(candidate, relative)
    size = path.stat().st_size
    if size > envelope["limits"]["max_file_bytes"]:
        raise LiveWorkerError("REJECTED_INPUT_LIMIT", f"file exceeds bound: {relative}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LiveWorkerError("REJECTED_INPUT", f"file is not readable UTF-8 text: {relative}") from error
    return {"operation": "read_file", "path": relative, "bytes": size, "sha256": sha256_file(path), "content": content}


def _replace_operation(action: dict[str, Any], candidate: Path, envelope: dict[str, Any]) -> dict[str, Any]:
    expected = {"operation", "path", "expected_sha256", "old", "new", "expected_occurrences"}
    action = _exact_keys(action, expected, "replace_text operation")
    if envelope["permissions"]["mutation"] is not True:
        raise LiveWorkerError("REJECTED_OPERATION", "mutation is not authorized")
    relative = _relative_path(action["path"], "replace_text.path")
    _verify_allowed_path(relative, envelope["permissions"])
    path = _beneath(candidate, relative)
    if sha256_file(path) != _sha256(action["expected_sha256"], "replace_text.expected_sha256"):
        raise LiveWorkerError("REJECTED_IDENTITY", f"candidate identity changed: {relative}")
    if not isinstance(action["old"], str) or not action["old"]:
        raise LiveWorkerError("REJECTED_INPUT", "replace_text.old must be a nonempty string")
    if not isinstance(action["new"], str):
        raise LiveWorkerError("REJECTED_INPUT", "replace_text.new must be a string")
    count = _integer(action["expected_occurrences"], 1, 100, "replace_text.expected_occurrences")
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LiveWorkerError("REJECTED_INPUT", f"cannot read text file: {relative}") from error
    if original.count(action["old"]) != count:
        raise LiveWorkerError("REJECTED_IDENTITY", f"replacement occurrence mismatch: {relative}")
    updated = original.replace(action["old"], action["new"])
    encoded = updated.encode("utf-8")
    if len(encoded) > envelope["limits"]["max_file_bytes"]:
        raise LiveWorkerError("REJECTED_INPUT_LIMIT", f"replacement exceeds file bound: {relative}")
    _atomic_replace(path, encoded)
    return {"operation": "replace_text", "path": relative, "before_sha256": action["expected_sha256"], "after_sha256": sha256_file(path), "occurrences": count}


def _atomic_replace(path: Path, encoded: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".dobeworks-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    except OSError as error:
        raise LiveWorkerError("FAILED_MUTATION", f"atomic replacement failed: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _seatbelt_quote(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace('"', '\\"')


def _sandbox_profile(output_root: Path, candidate: Path) -> str:
    output = _seatbelt_quote(output_root)
    protected = " ".join(
        f'(subpath "{_seatbelt_quote(root)}")'
        for root in (Path("/Users"), Path("/Volumes"), Path.home())
    )
    candidate_path = _seatbelt_quote(candidate)
    return (
        '(version 1)\n'
        '(deny default)\n'
        '(allow process*)\n'
        '(allow file-read*)\n'
        f'(deny file-read* {protected})\n'
        f'(allow file-read* (subpath "{candidate_path}"))\n'
        f'(allow file-write* (subpath "{output}"))\n'
        '(deny network*)\n'
        '(allow sysctl-read)\n'
    )


def _adapter_sandbox_profile(
    output_root: Path,
    denied_roots: list[Path],
    network: str,
) -> str:
    protected_roots = [*denied_roots, Path("/Users"), Path("/Volumes")]
    denied = " ".join(
        f'(subpath "{_seatbelt_quote(root)}")' for root in protected_roots
    )
    network_rule = "(allow network*)" if network == "ALLOWED" else "(deny network*)"
    return (
        '(version 1)\n'
        '(deny default)\n'
        '(allow process*)\n'
        '(allow file-read*)\n'
        f'(deny file-read* {denied})\n'
        f'(allow file-write* (subpath "{_seatbelt_quote(output_root)}"))\n'
        f'{network_rule}\n'
        '(allow sysctl-read)\n'
    )


def _child_limits(maximum_output: int) -> None:
    os.setsid()
    resource.setrlimit(resource.RLIMIT_FSIZE, (maximum_output, maximum_output))


def _process_environment(keys: list[str]) -> dict[str, str]:
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
    }
    for key in keys:
        if key not in os.environ:
            raise LiveWorkerError("REJECTED_ADAPTER", f"required environment key is unavailable: {key}")
        environment[key] = os.environ[key]
    return environment


def _stage_identity_files(config: dict[str, Any], root: Path) -> tuple[list[str], list[Path]]:
    identity_root = root / "identity"
    identity_root.mkdir()
    replacements: dict[str, str] = {}
    staged: list[Path] = []
    for index, record in enumerate(config["identity_files"]):
        source = Path(record["path"])
        destination = identity_root / f"{index:02d}-{source.name}"
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o500)
        if sha256_file(destination) != record["sha256"]:
            raise LiveWorkerError("REJECTED_IDENTITY", "staged process identity mismatch")
        replacements[str(source.resolve())] = str(destination)
        staged.append(destination)
    argv = []
    for argument in config["argv"]:
        candidate = Path(argument)
        resolved = str(candidate.resolve()) if candidate.is_absolute() and candidate.exists() else argument
        argv.append(replacements.get(resolved, argument))
    return argv, staged


def _run_process_agent(config: dict[str, Any], envelope: dict[str, Any], denied_roots: list[Path], request: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = (
            json.dumps(request, allow_nan=False, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise LiveWorkerError("FAILED_ADAPTER", "agent request is not finite JSON") from error
    maximum = envelope["limits"]["max_output_bytes"]
    if len(encoded) > maximum:
        raise LiveWorkerError("REJECTED_INPUT_LIMIT", "agent request exceeds the output bound")
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise LiveWorkerError("BLOCKED_PLATFORM", "macOS sandbox-exec is required for process adapters")
    with tempfile.TemporaryDirectory(prefix="dobeworks-agent-") as temporary:
        root = Path(temporary)
        request_path, stdout_path, stderr_path = root / "request.json", root / "stdout", root / "stderr"
        request_path.write_bytes(encoded)
        agent_argv, _staged_identity = _stage_identity_files(config, root)
        profile = _adapter_sandbox_profile(
            root,
            denied_roots,
            config["network"],
        )
        command = [str(sandbox), "-p", profile, "--", *agent_argv]
        try:
            with request_path.open("rb") as stdin, stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    command,
                    cwd=root,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    env=_process_environment(config["environment_keys"]),
                    preexec_fn=lambda: _child_limits(maximum),
                )
                returncode = _wait_process_group(
                    process,
                    config["timeout_seconds"],
                    "FAILED_ADAPTER_TIMEOUT",
                    "agent process",
                )
            stdout_bytes, stderr_bytes = stdout_path.read_bytes(), stderr_path.read_bytes()
        except (OSError, subprocess.SubprocessError) as error:
            raise LiveWorkerError("FAILED_ADAPTER", f"agent process failed: {error}") from error
    if len(stdout_bytes) + len(stderr_bytes) > maximum:
        raise LiveWorkerError("FAILED_ADAPTER_OUTPUT_LIMIT", "agent process output exceeded its bound")
    if returncode != 0:
        raise LiveWorkerError("FAILED_ADAPTER", f"agent process returned exit {returncode}")
    if stderr_bytes:
        raise LiveWorkerError("FAILED_ADAPTER", "agent process wrote unexpected standard error")
    action = _parse_json(stdout_bytes, "agent process JSON action", "FAILED_ADAPTER")
    if not isinstance(action, dict):
        raise LiveWorkerError("FAILED_ADAPTER", "agent process action must be an object")
    return action


def _bounded_check(argv: list[str], candidate: Path, output_root: Path, timeout: int, maximum_output: int) -> dict[str, Any]:
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file():
        raise LiveWorkerError("BLOCKED_PLATFORM", "macOS sandbox-exec is required for live checks")
    output_root.mkdir(parents=True, exist_ok=False)
    stdout_path = output_root / "stdout"
    stderr_path = output_root / "stderr"
    command = [str(sandbox), "-p", _sandbox_profile(output_root, candidate), "--", *argv]
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=candidate,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                env=_process_environment([]),
                preexec_fn=lambda: _child_limits(maximum_output),
            )
            returncode = _wait_process_group(
                process,
                timeout,
                "FAILED_CHECK_TIMEOUT",
                "check",
            )
        stdout_bytes = stdout_path.read_bytes()
        stderr_bytes = stderr_path.read_bytes()
    except (OSError, subprocess.SubprocessError) as error:
        raise LiveWorkerError("FAILED_CHECK", f"check invocation failed: {error}") from error
    if len(stdout_bytes) + len(stderr_bytes) > maximum_output:
        raise LiveWorkerError("FAILED_CHECK_OUTPUT_LIMIT", "check output exceeded its bound")
    return {
        "returncode": returncode,
        "stdout_bytes": len(stdout_bytes),
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_bytes": len(stderr_bytes),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "sandbox": "darwin-seatbelt-v1",
        "network": "DENIED",
    }


def _check_operation(action: dict[str, Any], candidate: Path, envelope: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    action = _exact_keys(action, {"operation", "check_id"}, "run_check operation")
    check_id = _control_id(action["check_id"], "run_check.check_id")
    if check_id not in envelope["permissions"]["check_ids"]:
        raise LiveWorkerError("REJECTED_OPERATION", f"check is not authorized: {check_id}")
    definition = envelope["checks"][check_id]
    before = tree_sha256(candidate)
    result = _bounded_check(
        definition["argv"],
        candidate,
        artifact_root / ".process" / check_id,
        definition["timeout_seconds"],
        envelope["limits"]["max_output_bytes"],
    )
    if tree_sha256(candidate) != before:
        raise LiveWorkerError("REJECTED_SIDE_EFFECT", f"check mutated the candidate: {check_id}")
    result.update({"operation": "run_check", "check_id": check_id, "argv": definition["argv"]})
    checks_root = artifact_root / "checks"
    checks_root.mkdir(exist_ok=True)
    write_json(checks_root / f"{check_id}.json", result)
    if result["returncode"] != 0:
        raise LiveWorkerError("FAILED_CHECK", f"required check failed: {check_id}")
    if result["stderr_bytes"] != 0:
        raise LiveWorkerError("FAILED_CHECK", f"successful check wrote diagnostics: {check_id}")
    return result


def _finish_operation(action: dict[str, Any], stage: str) -> dict[str, Any]:
    expected = {"operation", "summary"}
    if stage == "review":
        expected.update({"concerns", "dismissed_concerns"})
    action = _exact_keys(action, expected, f"{stage} finish_stage operation")
    result: dict[str, Any] = {"operation": "finish_stage", "summary": _nonblank(action["summary"], "summary")}
    if stage == "review":
        for field in ("concerns", "dismissed_concerns"):
            if not isinstance(action[field], list):
                raise LiveWorkerError("REJECTED_ADAPTER", f"review {field} must be an array")
            result[field] = action[field]
    return result


def _allowed_operations(stage: str, envelope: dict[str, Any]) -> list[str]:
    operations = ["read_file", "finish_stage"]
    if stage == "execute_check":
        if envelope["permissions"]["mutation"]:
            operations.append("replace_text")
        if envelope["permissions"]["check_ids"]:
            operations.append("run_check")
    return operations


def _agent_request(stage: str, history: list[dict[str, Any]], candidate: Path, envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "dobeworks.agent-turn/v1",
        "objective": envelope["objective"],
        "stage": stage,
        "allowed_operations": _allowed_operations(stage, envelope),
        "allowed_paths": envelope["permissions"]["allowed_paths"],
        "check_ids": envelope["permissions"]["check_ids"],
        "candidate_tree_sha256": tree_sha256(candidate),
        "history": history,
    }


def _evidence_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "content"}


def _proposal_view(action: dict[str, Any]) -> dict[str, Any]:
    operation = action.get("operation")
    visible_operation = (
        operation
        if isinstance(operation, str) and CONTROL_ID_PATTERN.fullmatch(operation)
        else "UNRECOGNIZED"
    )
    view: dict[str, Any] = {"operation": visible_operation}
    if "path" in action:
        try:
            view["path"] = _relative_path(action["path"], "proposal path")
        except LiveWorkerError:
            view["path"] = "REDACTED_INVALID_PATH"
    if "check_id" in action:
        try:
            view["check_id"] = _control_id(action["check_id"], "proposal check ID")
        except LiveWorkerError:
            view["check_id"] = "REDACTED_INVALID_ID"
    occurrences = action.get("expected_occurrences")
    if isinstance(occurrences, int) and not isinstance(occurrences, bool):
        view["expected_occurrences"] = occurrences
    if action.get("operation") == "finish_stage":
        concerns = action.get("concerns", [])
        dismissed = action.get("dismissed_concerns", [])
        view["reported_concern_count"] = len(concerns) if isinstance(concerns, list) else "INVALID_TYPE"
        view["reported_dismissed_concern_count"] = len(dismissed) if isinstance(dismissed, list) else "INVALID_TYPE"
    return view


def _result_view(result: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "operation",
        "path",
        "check_id",
        "bytes",
        "sha256",
        "before_sha256",
        "after_sha256",
        "occurrences",
        "returncode",
        "stdout_bytes",
        "stdout_sha256",
        "stderr_bytes",
        "stderr_sha256",
        "sandbox",
        "network",
    }
    view = {key: value for key, value in result.items() if key in allowed}
    if result.get("operation") == "finish_stage":
        view["reported_concern_count"] = len(result.get("concerns", []))
        view["reported_dismissed_concern_count"] = len(
            result.get("dismissed_concerns", [])
        )
    return view


def _perform_operation(
    stage: str,
    action: dict[str, Any],
    candidate: Path,
    envelope: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    operation = action.get("operation")
    if operation == "read_file":
        return _read_operation(action, candidate, envelope)
    if operation == "replace_text" and stage == "execute_check":
        return _replace_operation(action, candidate, envelope)
    if operation == "run_check" and stage == "execute_check":
        return _check_operation(action, candidate, envelope, artifact_root)
    if operation == "finish_stage":
        return _finish_operation(action, stage)
    raise LiveWorkerError(
        "REJECTED_OPERATION",
        f"operation {operation!r} is unavailable in {stage}",
    )


def _run_agent_action(
    stage: str,
    index: int,
    action: dict[str, Any],
    candidate: Path,
    envelope: dict[str, Any],
    artifact_root: Path,
    events: list[dict[str, Any]],
    journal: HandoffJournal,
    now_text: str,
) -> dict[str, Any]:
    journal.emit(
        "operation_proposed",
        stage,
        "AGENT_ADAPTER",
        "PROPOSAL_ONLY",
        {"action_index": index, **_proposal_view(action)},
    )
    try:
        result = _perform_operation(
            stage,
            action,
            candidate,
            envelope,
            artifact_root,
        )
    except LiveWorkerError as error:
        journal.emit(
            "operation_rejected",
            stage,
            "DOBEWORKS_CONTROLLER",
            "DETERMINISTIC_ENFORCEMENT",
            {
                "action_index": index,
                "operation": _proposal_view(action)["operation"],
                "state": error.state,
            },
        )
        raise
    _event(
        events,
        "operation_completed",
        stage,
        now_text,
        action_index=index,
        result=_evidence_result(result),
    )
    journal.emit(
        "operation_completed",
        stage,
        "DOBEWORKS_CONTROLLER",
        "DETERMINISTIC_ENFORCEMENT",
        {"action_index": index, **_result_view(result)},
    )
    return result


def _next_agent_action(
    adapter,
    stage: str,
    index: int,
    request: dict[str, Any],
    journal: HandoffJournal,
) -> dict[str, Any]:
    try:
        return adapter.next_action(stage, index, request)
    except LiveWorkerError as error:
        journal.emit(
            "adapter_failed",
            stage,
            "AGENT_ADAPTER",
            "PROPOSAL_ONLY",
            {"action_index": index, "state": error.state},
        )
        raise


def _run_stage(
    stage: str,
    adapter,
    candidate: Path,
    envelope: dict[str, Any],
    artifact_root: Path,
    events: list[dict[str, Any]],
    journal: HandoffJournal,
    now_text: str,
) -> dict[str, Any]:
    _event(events, "stage_started", stage, now_text)
    journal.emit(
        "stage_started",
        stage,
        "DOBEWORKS_CONTROLLER",
        "DETERMINISTIC_ENFORCEMENT",
        {"candidate_tree_sha256": tree_sha256(candidate)},
    )
    finish: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []
    maximum = envelope["limits"]["max_actions_per_stage"]
    for index in range(maximum):
        request = _agent_request(stage, history, candidate, envelope)
        action = _next_agent_action(adapter, stage, index, request, journal)
        result = _run_agent_action(
            stage,
            index,
            action,
            candidate,
            envelope,
            artifact_root,
            events,
            journal,
            now_text,
        )
        if result.get("operation") == "finish_stage":
            finish = result
        history.append({"action": action, "observation": result})
        if finish is not None:
            adapter.confirm_finish(stage, index + 1)
            break
    if finish is None:
        raise LiveWorkerError("REJECTED_STAGE", f"stage {stage} did not finish")
    _event(events, "stage_completed", stage, now_text, summary=finish["summary"])
    journal.emit(
        "stage_completed",
        stage,
        "DOBEWORKS_CONTROLLER",
        "DETERMINISTIC_ENFORCEMENT",
        {"candidate_tree_sha256": tree_sha256(candidate)},
    )
    return finish


def _require_all_checks(events: list[dict[str, Any]], envelope: dict[str, Any]) -> None:
    executed = {
        event["result"]["check_id"]
        for event in events
        if event["event"] == "operation_completed"
        and event["result"].get("operation") == "run_check"
    }
    missing = set(envelope["permissions"]["check_ids"]) - executed
    if missing:
        raise LiveWorkerError("FAILED_CHECK", f"required checks were not run: {sorted(missing)}")


def _artifact_manifest(partial: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(partial.rglob("*")):
        if path.is_file():
            records.append({"path": path.relative_to(partial).as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return records


def _prepare_paths(source: Path, staging_root: Path, job_id: str) -> tuple[Path, Path]:
    if staging_root.is_symlink() or not staging_root.is_dir():
        raise LiveWorkerError("REJECTED_PATH", "staging root must be an existing regular directory")
    _tree_files(source)
    destination = staging_root / job_id
    partial = staging_root / f".partial-{job_id}"
    if destination.exists() or destination.is_symlink() or partial.exists() or partial.is_symlink():
        raise LiveWorkerError("REJECTED_DESTINATION", "job destination already exists")
    return partial, destination


def _create_candidate(source: Path, partial: Path, source_identity: str) -> Path:
    try:
        partial.mkdir()
    except OSError as error:
        raise LiveWorkerError("FAILED_HAND_BACK", f"cannot create partial handback: {error}") from error
    candidate = partial / "candidate"
    _copy_candidate(source, candidate)
    if tree_sha256(source) != source_identity or tree_sha256(candidate) != source_identity:
        raise LiveWorkerError(
            "REJECTED_IDENTITY",
            "source or candidate identity changed while copying",
        )
    return candidate


def _start_journal(
    partial: Path,
    envelope: dict[str, Any],
    degs_result: dict[str, Any],
    now_text: str,
) -> HandoffJournal:
    journal = HandoffJournal(
        partial / "handoffs.jsonl",
        envelope["job_id"],
        now_text,
    )
    journal.emit(
        "preflight_admitted",
        "preflight",
        "DOBEWORKS_CONTROLLER",
        "DETERMINISTIC_ENFORCEMENT",
        {
            "degs_preflight_readiness": degs_result["decision"],
            "candidate_state": "DISPOSABLE",
        },
    )
    return journal


def _run_fixed_stages(
    adapter,
    candidate: Path,
    envelope: dict[str, Any],
    partial: Path,
    journal: HandoffJournal,
    now_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for stage in ("inspect", "execute_check"):
        _run_stage(
            stage,
            adapter,
            candidate,
            envelope,
            partial,
            events,
            journal,
            now_text,
        )
    _require_all_checks(events, envelope)
    frozen_candidate_sha256 = tree_sha256(candidate)
    review_finish = _run_stage(
        "review",
        adapter,
        candidate,
        envelope,
        partial,
        events,
        journal,
        now_text,
    )
    if tree_sha256(candidate) != frozen_candidate_sha256:
        raise LiveWorkerError("REJECTED_SIDE_EFFECT", "review changed the frozen candidate")
    return events, review_finish


def _observer_record(
    envelope: dict[str, Any],
    degs_result: dict[str, Any],
    concern_status: str,
    now_text: str,
) -> dict[str, Any]:
    return {
        "schema_version": "dobeworks.live-observer/v1",
        "job_id": envelope["job_id"],
        "observed_at": now_text,
        "evidence_status": "CURRENT",
        "missing_artifacts": [],
        "degs_preflight_readiness": degs_result["decision"],
        "agent_reported_concern_status": concern_status,
        "candidate_state": "COMPLETED_UNACCEPTED",
        "promotion": "NOT_PERFORMED",
    }


def _handback_record(
    envelope: dict[str, Any],
    source_identity: str,
    candidate: Path,
    partial: Path,
    degs_result: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": HAND_BACK_SCHEMA,
        "job_id": envelope["job_id"],
        "state": "COMPLETED_UNACCEPTED",
        "promotion": "NOT_PERFORMED",
        "retry": "PROHIBITED_AUTOMATIC",
        "attempts": 1,
        "source_tree_sha256": source_identity,
        "candidate_tree_sha256": tree_sha256(candidate),
        "agent_adapter_kind": envelope["agent_adapter"]["kind"],
        "agent_configuration_sha256": envelope["agent_adapter"]["configuration_sha256"],
        "degs_preflight_readiness": degs_result["decision"],
        "agent_reported_concern_status": review["agent_reported_concern_status"],
        "sashiko_source_commit": review["sashiko_source_commit"],
        "handoff_timeline_sha256": sha256_file(partial / "handoffs.jsonl"),
        "artifact_manifest_sha256": sha256_file(partial / "artifact-manifest.json"),
    }


def _write_job_artifacts(
    partial: Path,
    candidate: Path,
    envelope: dict[str, Any],
    source_identity: str,
    degs_result: dict[str, Any],
    review: dict[str, Any],
    events: list[dict[str, Any]],
    journal: HandoffJournal,
    now_text: str,
) -> None:
    concern_status = review["agent_reported_concern_status"]
    _event(events, "stage_started", "report", now_text)
    _event(events, "stage_completed", "report", now_text, summary="Staged unaccepted handback.")
    write_json(partial / "degs-result.json", degs_result)
    write_json(partial / "review.json", review)
    write_json(partial / "events.json", events)
    write_json(
        partial / "observer.json",
        _observer_record(envelope, degs_result, concern_status, now_text),
    )
    journal.emit(
        "human_acceptance_required",
        "report",
        "DOBEWORKS_CONTROLLER",
        "HUMAN_ONLY",
        {
            "candidate_state": "COMPLETED_UNACCEPTED",
            "promotion": "NOT_PERFORMED",
            "agent_reported_concern_status": concern_status,
        },
    )
    write_json(partial / "artifact-manifest.json", _artifact_manifest(partial))
    write_json(
        partial / "handback.json",
        _handback_record(
            envelope,
            source_identity,
            candidate,
            partial,
            degs_result,
            review,
        ),
    )


def execute_job(
    envelope_path: Path,
    source: Path,
    staging_root: Path,
    degs_root: Path,
    adapter_path: Path,
    adapter_kind: str,
    now_text: str,
) -> dict[str, Any]:
    """Execute one bounded job and atomically stage its unaccepted handback."""
    envelope = validate_envelope(load_json(envelope_path), now_text)
    source_identity = tree_sha256(source)
    if source_identity != envelope["source_tree_sha256"]:
        raise LiveWorkerError("REJECTED_IDENTITY", "source tree identity mismatch")
    if adapter_kind != envelope["agent_adapter"]["kind"]:
        raise LiveWorkerError("REJECTED_ADAPTER", "CLI adapter kind differs from the envelope")
    adapter = _load_adapter(envelope, adapter_path, source, staging_root, degs_root)
    degs_files = _verify_degs_files(envelope, degs_root)
    degs_result = _run_degs(envelope, degs_root, degs_files)
    partial, destination = _prepare_paths(source, staging_root, envelope["job_id"])
    candidate = _create_candidate(source, partial, source_identity)
    journal = _start_journal(partial, envelope, degs_result, now_text)
    events, review_finish = _run_fixed_stages(
        adapter,
        candidate,
        envelope,
        partial,
        journal,
        now_text,
    )
    review = _run_review_state(envelope, degs_root, degs_files, partial, review_finish)
    journal.emit(
        "review_report_aggregated",
        "review",
        "DEGS_REVIEW_ADAPTER",
        "AGGREGATION_ONLY",
        {"agent_reported_concern_status": review["agent_reported_concern_status"]},
    )
    _write_job_artifacts(
        partial,
        candidate,
        envelope,
        source_identity,
        degs_result,
        review,
        events,
        journal,
        now_text,
    )
    try:
        partial.rename(destination)
    except OSError as error:
        raise LiveWorkerError("FAILED_HAND_BACK", f"cannot finalize handback: {error}") from error
    return {"job_id": envelope["job_id"], "state": "COMPLETED_UNACCEPTED", "promotion": "NOT_PERFORMED", "handback_path": str(destination / "handback.json")}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one governed live-worker job")
    for name in ("envelope", "source-repo", "staging-root", "degs-root"):
        run.add_argument(f"--{name}", required=True)
    adapter = run.add_mutually_exclusive_group(required=True)
    adapter.add_argument("--agent-script")
    adapter.add_argument("--agent-process")
    run.add_argument("--now", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.agent_script:
        adapter_path, adapter_kind = Path(args.agent_script), "SCRIPTED"
    else:
        adapter_path, adapter_kind = Path(args.agent_process), "PROCESS"
    try:
        result = execute_job(
            Path(args.envelope),
            Path(args.source_repo),
            Path(args.staging_root),
            Path(args.degs_root),
            adapter_path,
            adapter_kind,
            args.now,
        )
    except LiveWorkerError as error:
        print(json.dumps({"state": error.state, "error": error.message}, sort_keys=True))
        return 2
    except Exception as error:
        print(json.dumps({"state": "FAILED_INTERNAL", "error": str(error)}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
