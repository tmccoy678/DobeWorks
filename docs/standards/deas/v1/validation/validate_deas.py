#!/usr/bin/env python3
"""Deterministic definition and conformance checks for DEAS v1.0."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path


MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_EXTERNAL_JSON_DEPTH = 64
GIT_TIMEOUT_SECONDS = 2
PHASE2_TIMEOUT_SECONDS = 2
DEGS_TIMEOUT_SECONDS = 5
GENERATION_2_TASK_ID = "DEGS-T1-DW-HWSW-P2-GENERATION-2-20260902"
DEFINITION_CORRECTION_TASK_ID = (
    "DEGS-T1-DW-ENGINEERING-ASSURANCE-V1-CORRECT-20260905"
)
EXTERNAL_GATES = ("G7", "G8", "G9")
VALIDATOR_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
TRACE_PATH = "contexts/operational-system/docs/program/v1/traceability-matrix.md"
ENTRY_PATH = "contexts/operational-system/docs/program/v1/phase-2-entry-criteria.md"
PLAN_PATH = (
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "qualification-plan.md"
)
EVIDENCE_PATHS = (
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "evidence/current-mac-baseline.md",
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "evidence/seagate-device-volume.md",
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "evidence/observer-surface.md",
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "evidence/worker-candidate.md",
)
PHASE2_VALIDATOR_PATH = (
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "validation/validate_phase2.py"
)
DEAS_VALIDATOR_PATH = "docs/standards/deas/v1/validation/validate_deas.py"
ENGINEERING_GATE_RELATIVE = "governance/bin/engineering-gate.py"
ENGINEERING_GATE_SHA256 = (
    "44c33ba743851d7befe11ebf93f2f4d9021b126f951a4587562adfca21f65c1e"
)
GENERATION_2_TASK_PATH = (
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "degs/phase2-generation-2-task.json"
)
GENERATION_2_REPORT_PATH = (
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "validation/validation-report.md"
)
GENERATION_2_IDENTITY_ARTIFACTS = (
    "contexts/operational-system/docs/program/v1/phase-2-entry-criteria.md",
    GENERATION_2_TASK_PATH,
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "evidence-sha256.txt",
    *EVIDENCE_PATHS,
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "generation-history.md",
    PLAN_PATH,
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "source-register.md",
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "handoff.md",
    PHASE2_VALIDATOR_PATH,
    GENERATION_2_REPORT_PATH,
    TRACE_PATH,
)
DEAS_ROOT = Path("docs/standards/deas/v1")
MANIFEST_PATH = DEAS_ROOT / "deas-v1-sha256.txt"
GENERATION_2_MANIFEST_PATH = Path(
    "contexts/operational-system/docs/program/v1/qualification/phase-2/"
    "generation-2-sha256.txt"
)
PHASE2_REPORT_COMMAND = (
    f"python3 {PHASE2_VALIDATOR_PATH} --repository-root . --generation 2 --json"
)
DEAS_REPORT_COMMAND = (
    "python3 docs/standards/deas/v1/validation/validate_deas.py conformance "
    f"--generation 2 --identity-manifest {GENERATION_2_MANIFEST_PATH} "
    '--identity-manifest-sha256 "$DEAS_GENERATION_2_MANIFEST_SHA256" '
    "--json --repository-root ."
)
EVIDENCE_SCHEMA_START = "<!-- DEAS-EVIDENCE-SCHEMA:START -->"
EVIDENCE_SCHEMA_END = "<!-- DEAS-EVIDENCE-SCHEMA:END -->"
EVIDENCE_SCHEMA_FIELD_COUNT = 23
DEFINITION_ARTIFACTS = (
    "AGENTS.md",
    "README.md",
    "docs/adr/0014-adopt-deas-v1.md",
    "docs/standards/deas/v1/degs/definition-task.json",
    "docs/standards/deas/v1/enforcement-matrix.md",
    "docs/standards/deas/v1/handoff.md",
    "docs/standards/deas/v1/phase2-generation-2-plan.md",
    "docs/standards/deas/v1/source-register.md",
    "docs/standards/deas/v1/standard.md",
    "docs/standards/deas/v1/validation/generation-1-expected-findings.json",
    "docs/standards/deas/v1/validation/test_validate_deas.py",
    "docs/standards/deas/v1/validation/validate_deas.py",
    "docs/standards/deas/v1/validation/validation-report.md",
)
DEFINITION_CORRECTION_PATHS = frozenset(
    {
        "docs/standards/deas/v1/degs/definition-task.json",
        "docs/standards/deas/v1/deas-v1-sha256.txt",
        "docs/standards/deas/v1/enforcement-matrix.md",
        "docs/standards/deas/v1/handoff.md",
        "docs/standards/deas/v1/phase2-generation-2-plan.md",
        "docs/standards/deas/v1/source-register.md",
        "docs/standards/deas/v1/standard.md",
        "docs/standards/deas/v1/validation/test_validate_deas.py",
        "docs/standards/deas/v1/validation/validate_deas.py",
        "docs/standards/deas/v1/validation/validation-report.md",
    }
)
PROFILE_MARKERS = ("### Core", "### Strict", "### Exploratory")
OVERLAY_MARKERS = (
    "### Python overlay",
    "### Document overlay",
    "### Evidence overlay",
    "### Validator overlay",
    "### AI-Assisted overlay",
    "### Git overlay",
)
INVARIANT_MARKERS = tuple(f"### DEAS-PRE-{number:03d}" for number in range(1, 11))
MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  ([^\s].*)$")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
DISCREPANCY_REFERENCES = re.compile(
    r"(?:NONE|`P2-G2-DISC-\d{3}`(?:, `P2-G2-DISC-\d{3}`)*)"
)


class ValidationError(Exception):
    """A deterministic input, execution, or repository-boundary failure."""

    def __init__(
        self,
        message: str,
        *,
        path: str = DEAS_VALIDATOR_PATH,
        rule_id: str = "DEAS-PRE-007",
    ) -> None:
        super().__init__(message)
        self.path = path
        self.rule_id = rule_id


def parse_external_json(raw: bytes, message: str) -> object:
    """Decode one unambiguous, finite, bounded-depth UTF-8 result."""
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def reject_constant(token):
        raise ValueError("nonfinite JSON constant")

    try:
        if not isinstance(raw, bytes):
            raise ValueError("external result must be UTF-8 bytes")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        pending = [(payload, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > MAX_EXTERNAL_JSON_DEPTH:
                raise ValueError("external JSON nesting exceeds limit")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("nonfinite JSON number")
            if isinstance(value, (dict, list)):
                children = value.values() if isinstance(value, dict) else value
                pending.extend((item, depth + 1) for item in children)
        return payload
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValidationError(message) from error


class DeasArgumentParser(argparse.ArgumentParser):
    """Convert parser failures into the validator's structured error seam."""

    def error(self, message: str) -> None:
        raise ValidationError(
            f"invalid arguments: {message}",
            path="command-line",
            rule_id="DEAS-PRE-007",
        )


def read_bounded_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"missing or non-regular required file: {label}")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValidationError(f"input exceeds {MAX_TEXT_BYTES} bytes: {label}")
    return path.read_bytes()


def read_bounded_text(path: Path, label: str) -> str:
    return read_bounded_bytes(path, label).decode("utf-8")


def read_repository_text(repository_root: Path, relative: str) -> str:
    path = (repository_root / relative).resolve()
    if path != repository_root and repository_root not in path.parents:
        raise ValidationError(f"path escapes repository root: {relative}")
    return read_bounded_text(path, relative)


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def collect_bounded_output(
    process: subprocess.Popen[bytes],
    label: str,
    timeout_seconds: int,
) -> tuple[bytes, bytes]:
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    deadline = time.monotonic() + timeout_seconds
    try:
        for name, stream in streams.items():
            if stream is not None:
                selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            events = selector.select(max(0, remaining))
            if remaining <= 0 or not events:
                terminate_process_group(process)
                raise ValidationError(f"{label} read timed out")
            for key, _ in events:
                capacity = MAX_TEXT_BYTES - sum(len(item) for item in buffers.values())
                chunk = os.read(key.fileobj.fileno(), min(65536, capacity + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if len(chunk) > capacity:
                    terminate_process_group(process)
                    raise ValidationError(f"{label} output limit exceeded")
                buffers[key.data].extend(chunk)
        process.wait(timeout=max(0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as error:
        terminate_process_group(process)
        raise ValidationError(f"{label} read timed out") from error
    finally:
        selector.close()
        for stream in streams.values():
            if stream is not None:
                stream.close()
    return bytes(buffers["stdout"]), bytes(buffers["stderr"])


def run_bounded_subprocess(
    command: list[str],
    cwd: Path,
    label: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout, stderr = collect_bounded_output(process, label, timeout_seconds)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def finding(rule_id: str, path: str, message: str) -> dict[str, str]:
    return {"message": message, "path": path, "rule_id": rule_id}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(repository_root: Path, relative: str) -> object:
    text = read_repository_text(repository_root, relative)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValidationError(f"invalid JSON in {relative}: {error}") from error


def load_local_expected_findings() -> dict[str, object]:
    path = Path(__file__).with_name("generation-1-expected-findings.json")
    try:
        value = json.loads(read_bounded_text(path, "local expected findings"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid local expected findings: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError("local expected findings must be a JSON object")
    return value


def load_evidence_contract_labels() -> tuple[str, ...]:
    standard_path = Path(__file__).resolve().parents[1] / "standard.md"
    text = read_bounded_text(standard_path, "canonical DEAS standard")
    if text.count(EVIDENCE_SCHEMA_START) != 1 or text.count(EVIDENCE_SCHEMA_END) != 1:
        raise ValidationError("canonical evidence schema markers differ")
    section = text.split(EVIDENCE_SCHEMA_START, 1)[1].split(
        EVIDENCE_SCHEMA_END,
        1,
    )[0]
    labels = tuple(re.findall(r"^\| [0-9]+ \| `([^`]+)` \|", section, re.MULTILINE))
    if len(labels) != EVIDENCE_SCHEMA_FIELD_COUNT or len(set(labels)) != len(labels):
        raise ValidationError("canonical evidence schema fields differ")
    return labels


def evidence_contract_complete(record: str, labels: tuple[str, ...]) -> bool:
    for label in labels:
        values = evidence_field_values(record, label)
        if len(values) != 1 or not values[0].strip():
            return False
    return True


def evidence_field_values(record: str, label: str) -> list[str]:
    pattern = re.compile(
        rf"^- {re.escape(label)}(?:[ \t]+(.*))?$",
        re.MULTILINE,
    )
    return pattern.findall(record)


def evidence_collection_is_complete(plan: str) -> bool:
    states = re.findall(
        r"^- \*\*Evidence collection:\*\*[ \t]+`([^`]+)`[ \t]*$",
        plan,
        re.MULTILINE,
    )
    if len(states) != 1:
        raise ValidationError("evidence collection state is missing or duplicated")
    if states[0] != "COMPLETE":
        raise ValidationError("evidence collection state is not COMPLETE")
    return True


def validate_generation_1_record(expected: dict[str, object]) -> dict[str, str]:
    baseline = expected.get("baseline")
    if not isinstance(baseline, dict):
        raise ValidationError("Generation 1 baseline record is missing")
    commit = baseline.get("commit")
    manifest_hash = baseline.get("manifest_sha256")
    artifacts = baseline.get("artifacts")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValidationError("Generation 1 commit identity is invalid")
    if not isinstance(artifacts, dict) or len(artifacts) != 28:
        raise ValidationError("Generation 1 artifact set is not exactly 28 paths")
    if any(
        not isinstance(path, str)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for path, digest in artifacts.items()
    ):
        raise ValidationError("Generation 1 artifact identity is invalid")
    manifest = "".join(
        f"{artifacts[path]}  {path}\n" for path in sorted(artifacts)
    ).encode()
    if hashlib.sha256(manifest).hexdigest() != manifest_hash:
        raise ValidationError("Generation 1 manifest identity is invalid")
    return artifacts


def verify_generation_1_identity(
    repository_root: Path,
    expected: dict[str, object],
) -> None:
    artifacts = validate_generation_1_record(expected)
    for relative, expected_hash in sorted(artifacts.items()):
        path = (repository_root / relative).resolve()
        read_repository_text(repository_root, relative)
        if sha256_file(path) != expected_hash:
            raise ValidationError(f"Generation 1 identity mismatch: {relative}")


def verify_generation_1_commit(
    repository_root: Path,
    expected: dict[str, object],
) -> None:
    artifacts = validate_generation_1_record(expected)
    baseline = expected["baseline"]
    commit = baseline["commit"]
    for relative, expected_hash in sorted(artifacts.items()):
        content = read_generation_1_blob(repository_root, commit, relative)
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValidationError(f"Generation 1 commit mismatch: {relative}")


def read_generation_1_blob(
    repository_root: Path,
    commit: str,
    relative: str,
) -> bytes:
    result = run_bounded_subprocess(
        ["git", "-C", str(repository_root), "show", f"{commit}:{relative}"],
        repository_root,
        "Generation 1 Git",
        GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise ValidationError(f"Generation 1 commit path missing: {relative}")
    if result.stderr:
        raise ValidationError("Generation 1 Git emitted diagnostics")
    return result.stdout


def verify_artifact_manifest(repository_root: Path) -> None:
    manifest = read_repository_text(repository_root, str(MANIFEST_PATH))
    entries: dict[str, str] = {}
    ordered_paths: list[str] = []
    for line in manifest.splitlines():
        match = MANIFEST_LINE.fullmatch(line)
        if not match:
            raise ValidationError("invalid artifact manifest line")
        expected_hash, relative = match.groups()
        if relative in entries:
            raise ValidationError(f"duplicate artifact manifest path: {relative}")
        entries[relative] = expected_hash
        ordered_paths.append(relative)
    if tuple(ordered_paths) != tuple(sorted(DEFINITION_ARTIFACTS)):
        raise ValidationError("artifact manifest path set or order differs")
    for relative in ordered_paths:
        path = (repository_root / relative).resolve()
        read_repository_text(repository_root, relative)
        if sha256_file(path) != entries[relative]:
            raise ValidationError(f"artifact manifest mismatch: {relative}")


def verify_markdown_links(repository_root: Path) -> None:
    for relative in DEFINITION_ARTIFACTS:
        if not relative.endswith(".md"):
            continue
        source = (repository_root / relative).resolve()
        text = read_repository_text(repository_root, relative)
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            target_path = target.split("#", 1)[0]
            resolved = (source.parent / target_path).resolve()
            if repository_root not in resolved.parents and resolved != repository_root:
                raise ValidationError(f"link escapes repository root: {relative}")
            if not resolved.exists():
                raise ValidationError(f"unresolved link in {relative}: {target}")


def verify_strict_python_functions(
    repository_root: Path,
    include_phase2: bool = False,
) -> None:
    python_paths = [
        DEAS_ROOT / "validation/validate_deas.py",
        DEAS_ROOT / "validation/test_validate_deas.py",
    ]
    if include_phase2:
        python_paths.append(
            Path(
                "contexts/operational-system/docs/program/v1/qualification/"
                "phase-2/validation/validate_phase2.py"
            )
        )
    for relative_path in python_paths:
        relative = str(relative_path)
        source = read_repository_text(repository_root, relative)
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as error:
            raise ValidationError(f"Python syntax error in {relative}: {error}") from error
        functions = (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        for function in functions:
            body = lines[function.lineno - 1 : function.end_lineno]
            logical = sum(
                bool(line.strip()) and not line.lstrip().startswith("#")
                for line in body
            )
            if logical > 60:
                raise ValidationError(
                    f"Strict function limit exceeded: {relative}:{function.name}={logical}"
                )


def verify_identity_manifest(
    repository_root: Path,
    manifest_path: Path,
    expected_manifest_hash: str,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_hash):
        raise ValidationError("identity manifest SHA-256 is invalid")
    resolved = (repository_root / manifest_path).resolve()
    if resolved != repository_root and repository_root not in resolved.parents:
        raise ValidationError("identity manifest escapes repository root")
    expected_path = (repository_root / GENERATION_2_MANIFEST_PATH).resolve()
    if resolved != expected_path:
        raise ValidationError("Generation 2 identity manifest path differs")
    relative_manifest = str(resolved.relative_to(repository_root))
    text = read_repository_text(repository_root, relative_manifest)
    if sha256_file(resolved) != expected_manifest_hash:
        raise ValidationError("identity manifest SHA-256 mismatch")
    entries: dict[str, str] = {}
    paths: list[str] = []
    for line in text.splitlines():
        match = MANIFEST_LINE.fullmatch(line)
        if not match:
            raise ValidationError("invalid identity manifest line")
        digest, relative = match.groups()
        if relative in entries:
            raise ValidationError(f"duplicate identity path: {relative}")
        entries[relative] = digest
        paths.append(relative)
    if not paths or paths != sorted(paths):
        raise ValidationError("identity manifest must be nonempty and sorted")
    if tuple(paths) != tuple(sorted(GENERATION_2_IDENTITY_ARTIFACTS)):
        raise ValidationError("Generation 2 identity manifest path set differs")
    for relative, expected_hash in entries.items():
        path = (repository_root / relative).resolve()
        read_repository_text(repository_root, relative)
        if sha256_file(path) != expected_hash:
            raise ValidationError(f"identity mismatch: {relative}")


def verify_phase2_validator_result(
    repository_root: Path,
) -> dict[str, object]:
    validator_path = repository_root / PHASE2_VALIDATOR_PATH
    result = run_bounded_subprocess(
        [
            sys.executable,
            str(validator_path),
            "--repository-root",
            str(repository_root),
            "--generation",
            "2",
            "--json",
        ],
        repository_root,
        "Phase 2 validator",
        PHASE2_TIMEOUT_SECONDS,
    )
    if result.stderr:
        raise ValidationError("Phase 2 validator emitted diagnostics")
    if result.returncode != 0:
        raise ValidationError("Phase 2 validator compound result is not PASS")
    payload = parse_external_json(
        result.stdout, "Phase 2 validator result is not valid JSON"
    )
    expected = {
        "decision": "PASS",
        "generation": 2,
        "identity_verified": True,
        "original_observations_preserved": True,
        "phase2_degs_decision": "PASS",
        "role_disposition": "NONE",
        "schema_version": 2,
        "validation_report_decision": "PASS",
    }
    # Python equality aliases booleans and numbers; external fields keep exact types.
    if payload != expected or any(
        type(payload[key]) is not type(value) for key, value in expected.items()
    ):
        raise ValidationError("Phase 2 validator compound result is not PASS")
    verify_generation_2_task(repository_root)
    verify_generation_2_report(repository_root)
    verify_original_observations(repository_root)
    verify_generation_2_degs(repository_root)
    validate_definition_content(repository_root)
    return {
        "deas_definition_verified": True,
        "original_observations_preserved": True,
        "phase2_compound_validation_verified": True,
        "phase2_degs_verified": True,
        "role_disposition": "NONE",
        "validation_report_verified": True,
    }


def record_has_status(value: object, status: str) -> bool:
    return isinstance(value, dict) and value.get("status") == status


def verify_generation_2_task(repository_root: Path) -> None:
    task = load_json(repository_root, GENERATION_2_TASK_PATH)
    if not isinstance(task, dict):
        raise ValidationError("Generation 2 task is incomplete or inconsistent")
    required = (
        task.get("task_id") == GENERATION_2_TASK_ID,
        task.get("status") == "READY_FOR_EXECUTION",
        task.get("risk_tier") == "TIER_1",
        task.get("authority_lane") == "TAYLOR_AI_WORKBENCH",
        task.get("unresolved_items") == [],
        record_has_status(task.get("validation"), "PASS"),
        record_has_status(task.get("post_action_validation"), "PENDING"),
        record_has_status(task.get("handoff"), "PASS"),
        record_has_status(task.get("independent_review"), "PENDING"),
    )
    if not all(required):
        raise ValidationError("Generation 2 task is incomplete or inconsistent")


def verify_generation_2_report(
    repository_root: Path,
) -> None:
    report = read_repository_text(repository_root, GENERATION_2_REPORT_PATH)
    labels = load_evidence_contract_labels()
    status = evidence_field_values(report, "**Status:**")
    identities = evidence_field_values(report, "**Cryptographic identities:**")
    procedures = evidence_field_values(report, "**Procedure or command identity:**")
    discrepancies = evidence_field_values(report, "**Discrepancy references:**")
    if not (
        evidence_contract_complete(report, labels)
        and status == ["PACKAGE_PASS_READY_FOR_GIT_DELIVERY"]
        and len(identities) == 1
        and str(GENERATION_2_MANIFEST_PATH) in identities[0]
        and GENERATION_2_TASK_ID in report
    ):
        raise ValidationError("Generation 2 validation report is incomplete")
    if not (
        procedures == ["See Exact validation commands below."]
        and "## Exact validation commands" in report
        and PHASE2_REPORT_COMMAND in report
        and DEAS_REPORT_COMMAND in report
    ):
        raise ValidationError("Generation 2 report command evidence differs")
    if not (
        len(discrepancies) == 1
        and DISCREPANCY_REFERENCES.fullmatch(discrepancies[0]) is not None
    ):
        raise ValidationError("Generation 2 report discrepancy evidence differs")


def ordered_line_subsequence(original: bytes, corrected: bytes) -> bool:
    corrected_lines = iter(corrected.splitlines(keepends=True))
    return all(
        any(candidate == line for candidate in corrected_lines)
        for line in original.splitlines(keepends=True)
    )


def verify_original_observations(repository_root: Path) -> None:
    expected = load_local_expected_findings()
    artifacts = validate_generation_1_record(expected)
    commit = expected["baseline"]["commit"]
    for relative in EVIDENCE_PATHS:
        original = read_generation_1_blob(
            VALIDATOR_REPOSITORY_ROOT,
            commit,
            relative,
        )
        if hashlib.sha256(original).hexdigest() != artifacts[relative]:
            raise ValidationError(f"Generation 1 commit mismatch: {relative}")
        corrected_path = (repository_root / relative).resolve()
        corrected = read_bounded_bytes(corrected_path, relative)
        role_values = re.findall(
            rb"^- \*\*Role Disposition:\*\*[ \t]+(.+)$",
            corrected,
            re.MULTILINE,
        )
        if not ordered_line_subsequence(original, corrected):
            raise ValidationError(f"Generation 2 original observations differ: {relative}")
        if role_values != [b"not assigned"]:
            raise ValidationError(f"Generation 2 Role Disposition differs: {relative}")


def verify_engineering_gate_identity(gate: Path) -> None:
    digest = hashlib.sha256(
        read_bounded_bytes(gate, ENGINEERING_GATE_RELATIVE)
    ).hexdigest()
    if digest != ENGINEERING_GATE_SHA256:
        raise ValidationError(
            "canonical DEGS gate identity differs",
            path=ENGINEERING_GATE_RELATIVE,
            rule_id="DEAS-PRE-003",
        )


def find_engineering_gate(repository_root: Path) -> Path:
    for root in (repository_root, *repository_root.parents):
        candidate = root / ENGINEERING_GATE_RELATIVE
        if candidate.is_file():
            verify_engineering_gate_identity(candidate)
            return candidate
    raise ValidationError("Generation 2 DEGS gate is unavailable")


def verify_degs_pass_output(
    result: subprocess.CompletedProcess[bytes],
    action: str,
) -> None:
    label = f"Generation 2 DEGS {action}"
    if result.stderr:
        raise ValidationError(f"{label} emitted diagnostics")
    if result.returncode != 0:
        raise ValidationError(f"{label} is not PASS")
    payload = parse_external_json(result.stdout, f"{label} result is not valid JSON")
    expected_fields = {
        "applicable_rule_ids",
        "authority_lane",
        "decision",
        "evidence_paths",
        "risk_tier",
        "unmet_requirements",
        "warnings",
    }
    valid = (
        isinstance(payload, dict)
        and set(payload) == expected_fields
        and payload.get("decision") == "PASS"
        and payload.get("risk_tier") == "TIER_1"
        and payload.get("authority_lane") == "TAYLOR_AI_WORKBENCH"
        and payload.get("unmet_requirements") == []
        and payload.get("warnings") == []
        and isinstance(payload.get("applicable_rule_ids"), list)
        and bool(payload["applicable_rule_ids"])
        and all(isinstance(item, str) for item in payload["applicable_rule_ids"])
        and isinstance(payload.get("evidence_paths"), list)
        and all(isinstance(item, str) for item in payload["evidence_paths"])
    )
    if not valid:
        raise ValidationError(f"{label} is not PASS")


def verify_generation_2_degs(repository_root: Path) -> None:
    gate = find_engineering_gate(repository_root)
    task_path = (repository_root / GENERATION_2_TASK_PATH).resolve()
    for action in ("validate", "evaluate"):
        result = run_bounded_subprocess(
            [sys.executable, str(gate), action, str(task_path), "--json"],
            gate.parents[2],
            f"Generation 2 DEGS {action}",
            DEGS_TIMEOUT_SECONDS,
        )
        verify_degs_pass_output(result, action)
        verify_engineering_gate_identity(gate)


def generation_1_findings_from_commit(
    repository_root: Path,
    expected: dict[str, object],
) -> list[dict[str, str]]:
    commit = expected["baseline"]["commit"]

    def historical_text(relative: str) -> str:
        content = read_generation_1_blob(repository_root, commit, relative)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(
                f"Generation 1 commit path is not UTF-8: {relative}"
            ) from error

    records = {path: historical_text(path) for path in EVIDENCE_PATHS}
    return semantic_findings(
        historical_text(PLAN_PATH),
        historical_text(TRACE_PATH),
        historical_text(ENTRY_PATH),
        records,
    )


def verify_definition_package_lifecycle(
    repository_root: Path,
    task: object,
) -> str:
    if not (
        isinstance(task, dict)
        and task.get("task_id") == DEFINITION_CORRECTION_TASK_ID
        and task.get("status") == "READY_FOR_EXECUTION"
    ):
        raise ValidationError("definition package is not READY_FOR_EXECUTION")
    if not record_has_status(task.get("post_action_validation"), "PENDING"):
        raise ValidationError("definition Git delivery is not PENDING")
    if not record_has_status(task.get("independent_review"), "PENDING"):
        raise ValidationError("definition independent review is not PENDING")
    report = read_repository_text(
        repository_root,
        str(DEAS_ROOT / "validation/validation-report.md"),
    )
    report_status = evidence_field_values(report, "**Status:**")
    if report_status != ["PACKAGE_PASS_READY_FOR_GIT_DELIVERY"]:
        raise ValidationError("definition report lifecycle status differs")
    handoff = read_repository_text(repository_root, str(DEAS_ROOT / "handoff.md"))
    if "- State: READY_FOR_GIT_DELIVERY" not in handoff.splitlines():
        raise ValidationError("definition handoff lifecycle status differs")
    return report


def validate_definition_content(repository_root: Path) -> dict[str, object]:
    standard = read_repository_text(repository_root, str(DEAS_ROOT / "standard.md"))
    for marker in PROFILE_MARKERS + OVERLAY_MARKERS + INVARIANT_MARKERS:
        if standard.count(marker) != 1:
            raise ValidationError(f"definition marker count differs: {marker}")
    load_evidence_contract_labels()
    expected = load_json(
        repository_root,
        str(DEAS_ROOT / "validation/generation-1-expected-findings.json"),
    )
    if not isinstance(expected, dict):
        raise ValidationError("expected findings must be a JSON object")
    verify_generation_1_commit(repository_root, expected)
    actual_findings = generation_1_findings_from_commit(repository_root, expected)
    findings_match = (
        expected.get("expected_decision") == "FAIL"
        and expected.get("generation") == 1
        and expected.get("findings") == actual_findings
    )
    if not findings_match:
        raise ValidationError("Generation 1 findings differ from frozen expectation")
    task = load_json(repository_root, str(DEAS_ROOT / "degs/definition-task.json"))
    report = verify_definition_package_lifecycle(repository_root, task)
    affected_files = task.get("affected_files")
    expected_affected = DEFINITION_CORRECTION_PATHS
    if (
        not isinstance(affected_files, list)
        or len(affected_files) != len(expected_affected)
        or set(affected_files) != expected_affected
    ):
        raise ValidationError("definition task affected-file count differs")
    if not evidence_contract_complete(report, load_evidence_contract_labels()):
        raise ValidationError("validation report evidence contract is incomplete")
    if "- Result: PACKAGE_PASS" not in report.splitlines():
        raise ValidationError("validation report is not package PASS")
    verify_markdown_links(repository_root)
    verify_strict_python_functions(repository_root)
    verify_artifact_manifest(repository_root)
    return {
        "artifact_manifest_verified": True,
        "decision": "PASS",
        "decision_scope": "PACKAGE",
        "external_gates_pending": list(EXTERNAL_GATES),
        "generation_1_decision": "FAIL",
        "generation_1_findings_match": findings_match,
        "overlay_count": len(OVERLAY_MARKERS),
        "preventive_invariant_count": len(INVARIANT_MARKERS),
        "profile_count": len(PROFILE_MARKERS),
        "schema_version": 1,
    }


def semantic_findings(
    plan: str,
    trace: str,
    entry: str,
    records: dict[str, str],
) -> list[dict[str, str]]:
    collection_complete = evidence_collection_is_complete(plan)
    evidence_labels = load_evidence_contract_labels()
    findings: list[dict[str, str]] = []

    trace_lines = trace.splitlines()
    trace_is_stale = "Reserved only; no evidence yet" in trace or any(
        "EV-P2-" in line and "PLANNED" in line for line in trace_lines
    )
    if collection_complete and trace_is_stale:
        findings.append(
            finding(
                "DEAS-TRACE-001",
                TRACE_PATH,
                "Completed Phase 2 evidence is still represented as planned or reserved.",
            )
        )

    if collection_complete and "- [ ]" in entry:
        findings.append(
            finding(
                "DEAS-PHASE-001",
                ENTRY_PATH,
                "Phase 2 entry prerequisites remain unchecked although evidence collection is complete.",
            )
        )

    for path in EVIDENCE_PATHS:
        record = records[path]
        if not evidence_contract_complete(record, evidence_labels):
            findings.append(
                finding(
                    "DEAS-EVIDENCE-001",
                    path,
                    "Consequential evidence record omits one or more required contract fields.",
                )
            )
    return findings


def generation_findings(repository_root: Path) -> list[dict[str, str]]:
    records = {
        path: read_repository_text(repository_root, path)
        for path in EVIDENCE_PATHS
    }
    return semantic_findings(
        read_repository_text(repository_root, PLAN_PATH),
        read_repository_text(repository_root, TRACE_PATH),
        read_repository_text(repository_root, ENTRY_PATH),
        records,
    )


def run_conformance(arguments: argparse.Namespace) -> int:
    repository_root = arguments.repository_root.resolve()
    if not repository_root.is_dir():
        raise ValidationError(
            "repository root is not a directory",
            path=".",
            rule_id="DEAS-PRE-006",
        )
    identity_verified = False
    if arguments.generation == 1:
        if arguments.identity_manifest or arguments.identity_manifest_sha256:
            raise ValidationError("Generation 1 identity is fixed by the baseline record")
        verify_generation_1_identity(
            repository_root,
            load_local_expected_findings(),
        )
        identity_verified = True
    if arguments.generation == 2:
        if not arguments.identity_manifest or not arguments.identity_manifest_sha256:
            raise ValidationError(
                "Generation 2 requires an identity manifest and its SHA-256"
            )
        verify_identity_manifest(
            repository_root,
            arguments.identity_manifest,
            arguments.identity_manifest_sha256,
        )
        verify_strict_python_functions(repository_root, include_phase2=True)
        identity_verified = True
    findings = generation_findings(repository_root)
    compound_result: dict[str, object] = {}
    if arguments.generation == 2 and not findings:
        compound_result = verify_phase2_validator_result(repository_root)
    payload = {
        "decision": "FAIL" if findings else "PASS",
        "finding_count": len(findings),
        "findings": findings,
        "generation": arguments.generation,
        "identity_verified": identity_verified,
        "schema_version": 1,
    }
    payload.update(compound_result)
    if arguments.generation == 2 and not findings:
        payload["decision_scope"] = "PACKAGE"
        payload["external_gates_pending"] = list(EXTERNAL_GATES)
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        label = "PACKAGE_VALIDATION" if arguments.generation == 2 else "CONFORMANCE"
        print(f"DEAS_GENERATION_{arguments.generation}_{label}: {payload['decision']}")
        for item in findings:
            print(f"- {item['rule_id']} {item['path']}: {item['message']}")
    return 1 if findings else 0


def run_definition(arguments: argparse.Namespace) -> int:
    repository_root = arguments.repository_root.resolve()
    if not repository_root.is_dir():
        raise ValidationError(
            "repository root is not a directory",
            path=".",
            rule_id="DEAS-PRE-006",
        )
    payload = validate_definition_content(repository_root)
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("DEAS_DEFINITION_VALIDATION: PASS")
        print(f"profiles={payload['profile_count']}")
        print(f"overlays={payload['overlay_count']}")
        print(f"preventive_invariants={payload['preventive_invariant_count']}")
        print("generation_1=EXPECTED_NONCONFORMING")
        print("artifact_manifest=VERIFIED")
    return 0


def run_evidence_record(arguments: argparse.Namespace) -> int:
    repository_root = arguments.repository_root.resolve()
    if not repository_root.is_dir():
        raise ValidationError(
            "repository root is not a directory",
            path=".",
            rule_id="DEAS-PRE-006",
        )
    relative = str(arguments.record)
    record = read_repository_text(repository_root, relative)
    is_complete = evidence_contract_complete(
        record,
        load_evidence_contract_labels(),
    )
    findings = [] if is_complete else [
        finding(
            "DEAS-EVIDENCE-001",
            relative,
            "Consequential evidence record omits, duplicates, or leaves blank a required contract field.",
        )
    ]
    payload = {
        "decision": "PASS" if is_complete else "FAIL",
        "finding_count": len(findings),
        "findings": findings,
        "schema_version": 1,
    }
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"DEAS_EVIDENCE_RECORD: {payload['decision']}")
    return 0 if is_complete else 1


def build_parser() -> argparse.ArgumentParser:
    parser = DeasArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    conformance = commands.add_parser("conformance")
    conformance.add_argument("--generation", type=int, choices=(1, 2), required=True)
    conformance.add_argument("--json", action="store_true")
    conformance.add_argument("--identity-manifest", type=Path)
    conformance.add_argument("--identity-manifest-sha256")
    conformance.add_argument("--repository-root", type=Path, required=True)
    conformance.set_defaults(handler=run_conformance)
    definition = commands.add_parser("definition")
    definition.add_argument("--json", action="store_true")
    definition.add_argument("--repository-root", type=Path, required=True)
    definition.set_defaults(handler=run_definition)
    evidence = commands.add_parser("evidence-record")
    evidence.add_argument("--record", type=Path, required=True)
    evidence.add_argument("--json", action="store_true")
    evidence.add_argument("--repository-root", type=Path, required=True)
    evidence.set_defaults(handler=run_evidence_record)
    return parser


def error_payload(error: ValidationError) -> dict[str, object]:
    return {
        "decision": "ERROR",
        "finding_count": 1,
        "findings": [
            {
                "message": str(error),
                "path": error.path,
                "rule_id": error.rule_id,
            }
        ],
        "schema_version": 1,
    }


def main() -> int:
    raw_arguments = sys.argv[1:]
    json_requested = "--json" in raw_arguments
    try:
        arguments = build_parser().parse_args(raw_arguments)
        return arguments.handler(arguments)
    except (OSError, UnicodeError, ValidationError) as caught:
        error = caught if isinstance(caught, ValidationError) else ValidationError(str(caught))
        if json_requested:
            print(json.dumps(error_payload(error), indent=2, sort_keys=True))
        else:
            print(f"DEAS_VALIDATION_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
