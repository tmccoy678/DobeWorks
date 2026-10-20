#!/usr/bin/env python3
"""Validate the bounded Phase 2 Generation 2 documentation correction."""

from __future__ import annotations

import argparse
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
DEGS_TIMEOUT_SECONDS = 5
GENERATION_1_COMMIT = "f45ae80c64a0aa8c723a5a58b4fbc7073682d349"
GENERATION_1_MANIFEST_SHA256 = (
    "9ed515ac90cc100bae3d3a3baa674d6c2a200f5e18b3da4d7b4daaf979ac8d77"
)
DEAS_DEFINITION_COMMIT = "ca8efcefe6568a7a64b5b6d930031dff0131efec"
DEAS_MANIFEST_SHA256 = (
    "3f40080f3cd725db8906385abb6f7db79fadef5a231cf6bc9206b2fa43863c88"
)
GENERATION_2_TASK_ID = "DEGS-T1-DW-HWSW-P2-GENERATION-2-20260902"
PACKAGE_PREFIX = (
    "contexts/operational-system/docs/program/v1/qualification/phase-2"
)
VALIDATOR_RELATIVE = f"{PACKAGE_PREFIX}/validation/validate_phase2.py"
ENGINEERING_GATE_RELATIVE = "governance/bin/engineering-gate.py"
ENGINEERING_GATE_SHA256 = (
    "44c33ba743851d7befe11ebf93f2f4d9021b126f951a4587562adfca21f65c1e"
)
REVIEW_EVIDENCE_PATH = (
    ".scratch/dobeworks-deas-v1-generation-2/review/final-review-index.md"
)
SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[1]
SCRIPT_REPOSITORY_ROOT = SCRIPT_PATH.parents[8]
EVIDENCE_SCHEMA_START = "<!-- DEAS-EVIDENCE-SCHEMA:START -->"
EVIDENCE_SCHEMA_END = "<!-- DEAS-EVIDENCE-SCHEMA:END -->"
MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  ([^\s].*)$")
DISCREPANCY_REFERENCES = re.compile(
    r"(?:NONE|\x60P2-G2-DISC-\d{3}\x60(?:, \x60P2-G2-DISC-\d{3}\x60)*)"
)

PACKAGE_FILES = frozenset(
    {
        "qualification-plan.md",
        "source-register.md",
        "evidence/current-mac-baseline.md",
        "evidence/seagate-device-volume.md",
        "evidence/worker-candidate.md",
        "evidence/observer-surface.md",
        "discrepancies-and-unknowns.md",
        "evidence/command-log.md",
        "validation/validate_phase2.py",
        "validation/validation-report.md",
        "degs/phase2-task.json",
        "handoff.md",
        "evidence-sha256.txt",
        "generation-history.md",
        "generation-2-sha256.txt",
        "degs/phase2-generation-2-task.json",
    }
)
EVIDENCE_MANIFEST_ARTIFACTS = PACKAGE_FILES - {
    "evidence-sha256.txt",
    "generation-2-sha256.txt",
}
GENERATION_2_ARTIFACTS = (
    "contexts/operational-system/docs/program/v1/phase-2-entry-criteria.md",
    f"{PACKAGE_PREFIX}/degs/phase2-generation-2-task.json",
    f"{PACKAGE_PREFIX}/evidence-sha256.txt",
    f"{PACKAGE_PREFIX}/evidence/current-mac-baseline.md",
    f"{PACKAGE_PREFIX}/evidence/observer-surface.md",
    f"{PACKAGE_PREFIX}/evidence/seagate-device-volume.md",
    f"{PACKAGE_PREFIX}/evidence/worker-candidate.md",
    f"{PACKAGE_PREFIX}/generation-history.md",
    f"{PACKAGE_PREFIX}/handoff.md",
    f"{PACKAGE_PREFIX}/qualification-plan.md",
    f"{PACKAGE_PREFIX}/source-register.md",
    f"{PACKAGE_PREFIX}/validation/validate_phase2.py",
    f"{PACKAGE_PREFIX}/validation/validation-report.md",
    "contexts/operational-system/docs/program/v1/traceability-matrix.md",
)
GENERATION_2_MANIFEST = f"{PACKAGE_PREFIX}/generation-2-sha256.txt"
C4_PATHS = frozenset((*GENERATION_2_ARTIFACTS, GENERATION_2_MANIFEST))
PHASE2_REPORT_COMMAND = (
    f"python3 {PACKAGE_PREFIX}/validation/validate_phase2.py "
    "--repository-root . --generation 2 --json"
)
DEAS_REPORT_COMMAND = (
    "python3 docs/standards/deas/v1/validation/validate_deas.py conformance "
    f"--generation 2 --identity-manifest {GENERATION_2_MANIFEST} "
    '--identity-manifest-sha256 "$DEAS_GENERATION_2_MANIFEST_SHA256" '
    "--json --repository-root ."
)

GENERATION_1_UNCHANGED = {
    "discrepancies-and-unknowns.md": (
        "f218d8b2441fee8b47f212ebeaf3a66cdc840e2dc055d58724dfe20bd88071fb"
    ),
    "evidence/command-log.md": (
        "affe2c741e04b776c4f57e226ee352689bcd57426fdbdfd29c9425f55bfa8324"
    ),
    "degs/phase2-task.json": (
        "6377c8a5f3d057e74b931f871d5f4e5434c1d2762a7e878f09e616939824e97b"
    ),
}
EVIDENCE_EXPECTATIONS = {
    f"{PACKAGE_PREFIX}/evidence/current-mac-baseline.md": (
        "9478faa83b6367d8737325fb1136c2d9c90eabf42d64c52a715c0a533ca87eca",
        "OBSERVED_WITH_UNRESOLVED_DISCREPANCY",
    ),
    f"{PACKAGE_PREFIX}/evidence/seagate-device-volume.md": (
        "0be85cc8856ea610cad9239b8d163be0b4049e768bb170f852eb7b7909b76514",
        "OBSERVED_WITH_UNKNOWNS",
    ),
    f"{PACKAGE_PREFIX}/evidence/observer-surface.md": (
        "9b772d85cf7b0124cfd7a6fd931e0b882866a52475d10c52fc652a348a8b0cdc",
        "EXECUTABLE_PRESENCE_ONLY",
    ),
    f"{PACKAGE_PREFIX}/evidence/worker-candidate.md": (
        "92b246de1e5e8c5c7b1ecd2fc4f88290ea77265ae89c9d4dde0c7e09503b79ac",
        "BLOCKED_PENDING_EVIDENCE",
    ),
}
EVIDENCE_GAP_EXPECTATIONS = {
    relative: {
        "**Evidence owner:**": (
            "UNKNOWN; contemporaneous evidence does not name the owner "
            "accountable for record integrity."
        )
    }
    for relative in EVIDENCE_EXPECTATIONS
}
EVIDENCE_GAP_EXPECTATIONS[
    f"{PACKAGE_PREFIX}/evidence/observer-surface.md"
].update(
    {
        "**Start time:**": "NOT RECORDED",
        "**End time:**": "NOT RECORDED",
    }
)


class ValidationError(Exception):
    """A deterministic input, execution, or repository-boundary failure."""

    def __init__(
        self,
        message: str,
        *,
        path: str = VALIDATOR_RELATIVE,
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


class Phase2ArgumentParser(argparse.ArgumentParser):
    """Convert parser failures into the structured validator error seam."""

    def error(self, message: str) -> None:
        raise ValidationError(
            f"invalid arguments: {message}",
            path="command-line",
            rule_id="DEAS-PRE-007",
        )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def bounded_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"missing or non-regular required file: {label}")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValidationError(f"cannot inspect required file: {label}") from error
    if size > MAX_TEXT_BYTES:
        raise ValidationError(f"input exceeds {MAX_TEXT_BYTES} bytes: {label}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValidationError(f"cannot read required file: {label}") from error


def bounded_text(path: Path, label: str) -> str:
    try:
        return bounded_bytes(path, label).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"required file is not UTF-8: {label}") from error


def rooted_path(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ValidationError(f"absolute artifact path is prohibited: {relative}")
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValidationError(f"artifact path escapes its root: {relative}")
    return path


def rooted_bytes(root: Path, relative: str) -> bytes:
    return bounded_bytes(rooted_path(root, relative), relative)


def rooted_text(root: Path, relative: str) -> str:
    return bounded_text(rooted_path(root, relative), relative)


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
                used = sum(len(item) for item in buffers.values())
                capacity = MAX_TEXT_BYTES - used
                chunk = os.read(key.fileobj.fileno(), min(65536, capacity + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                elif len(chunk) > capacity:
                    terminate_process_group(process)
                    raise ValidationError(f"{label} output limit exceeded")
                else:
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


def run_bounded(
    command: list[str],
    cwd: Path,
    label: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[bytes]:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        raise ValidationError(f"{label} execution failed") from error
    stdout, stderr = collect_bounded_output(process, label, timeout_seconds)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def parse_manifest(
    root: Path,
    relative: str,
    expected_paths: frozenset[str],
) -> dict[str, str]:
    text = rooted_text(root, relative)
    entries: dict[str, str] = {}
    ordered: list[str] = []
    for line in text.splitlines():
        match = MANIFEST_LINE.fullmatch(line)
        if match is None:
            raise ValidationError(f"manifest contains a malformed line: {relative}")
        digest, artifact = match.groups()
        if artifact in entries:
            raise ValidationError(f"manifest contains a duplicate path: {relative}")
        entries[artifact] = digest
        ordered.append(artifact)
    if ordered != sorted(ordered) or frozenset(ordered) != expected_paths:
        raise ValidationError(f"manifest path set or order differs: {relative}")
    return entries


def verify_manifest_entries(root: Path, entries: dict[str, str], label: str) -> None:
    for relative, expected in entries.items():
        actual = sha256_bytes(rooted_bytes(root, relative))
        if actual != expected:
            raise ValidationError(f"{label} hash mismatch: {relative}")


def verify_package_file_set() -> None:
    paths = tuple(PACKAGE_ROOT.rglob("*"))
    symlinks = [path for path in paths if path.is_symlink()]
    if symlinks:
        raise ValidationError("Phase 2 package contains a symbolic link")
    actual = frozenset(
        str(path.relative_to(PACKAGE_ROOT)) for path in paths if path.is_file()
    )
    if actual != PACKAGE_FILES:
        missing = sorted(PACKAGE_FILES - actual)
        extra = sorted(actual - PACKAGE_FILES)
        raise ValidationError(f"Phase 2 package file set differs: {missing=}, {extra=}")


def verify_manifests(repository_root: Path) -> None:
    evidence_entries = parse_manifest(
        PACKAGE_ROOT,
        "evidence-sha256.txt",
        EVIDENCE_MANIFEST_ARTIFACTS,
    )
    verify_manifest_entries(PACKAGE_ROOT, evidence_entries, "evidence manifest")
    generation_entries = parse_manifest(
        repository_root,
        GENERATION_2_MANIFEST,
        frozenset(GENERATION_2_ARTIFACTS),
    )
    verify_manifest_entries(repository_root, generation_entries, "Generation 2 manifest")


def load_json(root: Path, relative: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(rooted_text(root, relative))
    except json.JSONDecodeError as error:
        raise ValidationError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} root is not an object")
    return value


def load_evidence_labels(repository_root: Path) -> tuple[str, ...]:
    standard = rooted_text(repository_root, "docs/standards/deas/v1/standard.md")
    try:
        schema = standard.split(EVIDENCE_SCHEMA_START, 1)[1].split(
            EVIDENCE_SCHEMA_END,
            1,
        )[0]
    except IndexError as error:
        raise ValidationError("canonical evidence schema markers are missing") from error
    labels = tuple(
        line.split("`")[1] for line in schema.splitlines() if " | `**" in line
    )
    if len(labels) != 23 or len(set(labels)) != 23:
        raise ValidationError("canonical evidence schema field set differs")
    return labels


def evidence_values(record: str, label: str) -> list[str]:
    pattern = re.compile(
        rf"^- {re.escape(label)}[ \t]+(.+)$",
        re.MULTILINE,
    )
    return [match.group(1).strip() for match in pattern.finditer(record)]


def evidence_contract_complete(record: str, labels: tuple[str, ...]) -> bool:
    return all(
        len(values := evidence_values(record, label)) == 1 and bool(values[0])
        for label in labels
    )


def verify_evidence_gap_fields(record: str, relative: str) -> None:
    expected_fields = EVIDENCE_GAP_EXPECTATIONS[relative]
    for label, expected in expected_fields.items():
        if evidence_values(record, label) != [expected]:
            raise ValidationError(
                f"source-limited evidence field differs: {label}",
                path=relative,
                rule_id="DEAS-EVIDENCE-001",
            )


def read_generation_1_blob(repository_root: Path, relative: str) -> bytes:
    result = run_bounded(
        ["git", "-C", str(repository_root), "show", f"{GENERATION_1_COMMIT}:{relative}"],
        repository_root,
        "Generation 1 Git",
        GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise ValidationError(f"Generation 1 artifact is unavailable: {relative}")
    if result.stderr:
        raise ValidationError("Generation 1 Git emitted diagnostics")
    return result.stdout


def ordered_line_subsequence(original: bytes, corrected: bytes) -> bool:
    corrected_lines = iter(corrected.splitlines(keepends=True))
    return all(
        any(candidate == line for candidate in corrected_lines)
        for line in original.splitlines(keepends=True)
    )


def verify_original_observations(
    repository_root: Path,
    labels: tuple[str, ...],
) -> None:
    for relative, (expected_hash, expected_status) in EVIDENCE_EXPECTATIONS.items():
        original = read_generation_1_blob(repository_root, relative)
        corrected = rooted_bytes(repository_root, relative)
        if sha256_bytes(original) != expected_hash:
            raise ValidationError(f"Generation 1 evidence identity differs: {relative}")
        if not ordered_line_subsequence(original, corrected):
            raise ValidationError(f"original observation lines differ: {relative}")
        try:
            text = corrected.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(
                f"corrected evidence is not UTF-8: {relative}"
            ) from error
        if not evidence_contract_complete(text, labels):
            raise ValidationError(f"evidence contract is incomplete: {relative}")
        if evidence_values(text, "**Status:**") != [expected_status]:
            raise ValidationError(f"evidence status differs: {relative}")
        verify_evidence_gap_fields(text, relative)
        roles = re.findall(
            rb"^- \*\*Role Disposition:\*\*[ \t]+(.+)$",
            corrected,
            re.MULTILINE,
        )
        if roles != [b"not assigned"]:
            raise ValidationError(f"Role Disposition differs: {relative}")


def verify_unchanged_generation_1(repository_root: Path) -> None:
    for relative, expected_hash in GENERATION_1_UNCHANGED.items():
        repository_relative = f"{PACKAGE_PREFIX}/{relative}"
        original = read_generation_1_blob(repository_root, repository_relative)
        current = rooted_bytes(PACKAGE_ROOT, relative)
        if sha256_bytes(original) != expected_hash or current != original:
            raise ValidationError(f"unchanged Generation 1 artifact differs: {relative}")


def verify_phase_history(repository_root: Path) -> None:
    plan = rooted_text(PACKAGE_ROOT, "qualification-plan.md")
    trace = rooted_text(
        repository_root,
        "contexts/operational-system/docs/program/v1/traceability-matrix.md",
    )
    entry = rooted_text(
        repository_root,
        "contexts/operational-system/docs/program/v1/phase-2-entry-criteria.md",
    )
    if evidence_values(plan, "**Evidence collection:**") != ["`COMPLETE`"]:
        raise ValidationError("Phase 2 evidence collection state differs")
    if "Reserved only; no evidence yet" in trace or any(
        "EV-P2-" in line and "PLANNED" in line for line in trace.splitlines()
    ):
        raise ValidationError("Phase 2 traceability still reserves produced evidence")
    required_trace = (
        "degs/phase2-generation-2-task.json",
        "generation-2-sha256.txt",
        "validation/validation-report.md",
        "discrepancies-and-unknowns.md",
    )
    if any(marker not in trace for marker in required_trace):
        raise ValidationError("Phase 2 traceability lacks the Generation 2 basis")
    entry_markers = (
        "Historical entry disposition",
        "Historical entry sufficiency: `NOT ESTABLISHED`",
        "separate AgentOps delegation evidence is `NOT RECORDED`",
        "absence of delegation is not claimed",
    )
    if "- [ ]" in entry or any(marker not in entry for marker in entry_markers):
        raise ValidationError("Phase 2 historical entry disposition is incomplete")


def record_status_is(value: object, status: str) -> bool:
    return isinstance(value, dict) and value.get("status") == status


def verify_generation_2_task(repository_root: Path) -> None:
    relative = f"{PACKAGE_PREFIX}/degs/phase2-generation-2-task.json"
    task = load_json(repository_root, relative, "Generation 2 DEGS task")
    requirements = (
        task.get("task_id") == GENERATION_2_TASK_ID,
        task.get("status") == "READY_FOR_EXECUTION",
        task.get("risk_tier") == "TIER_1",
        task.get("authority_lane") == "TAYLOR_AI_WORKBENCH",
        task.get("unresolved_items") == [],
        task.get("warnings") == [],
        record_status_is(task.get("validation"), "PASS"),
        record_status_is(task.get("post_action_validation"), "PENDING"),
        record_status_is(task.get("handoff"), "PASS"),
        record_status_is(task.get("independent_review"), "PENDING"),
    )
    affected = task.get("affected_files")
    approval = task.get("human_approval")
    scope = task.get("scope")
    review = task.get("independent_review")
    if not all(requirements):
        raise ValidationError("Generation 2 task is incomplete or inconsistent")
    if not (
        isinstance(affected, list)
        and len(affected) == len(C4_PATHS)
        and len(set(affected)) == len(affected)
        and frozenset(affected) == C4_PATHS
    ):
        raise ValidationError("Generation 2 task path set differs")
    if not (
        isinstance(approval, dict)
        and approval.get("required") is True
        and approval.get("status") == "APPROVED"
        and approval.get("approver") == "Taylor"
    ):
        raise ValidationError("Generation 2 human approval evidence differs")
    if not (
        isinstance(scope, dict)
        and scope.get("description")
        == "The exact 15-path C4 package correction; Git delivery is external."
        and isinstance(review, dict)
        and review.get("evidence_path") == REVIEW_EVIDENCE_PATH
    ):
        raise ValidationError("Generation 2 package and delivery lifecycle differ")


def verify_generation_2_report(
    repository_root: Path,
    labels: tuple[str, ...],
) -> None:
    relative = f"{PACKAGE_PREFIX}/validation/validation-report.md"
    report = rooted_text(repository_root, relative)
    statuses = evidence_values(report, "**Status:**")
    procedures = evidence_values(report, "**Procedure or command identity:**")
    identities = evidence_values(report, "**Cryptographic identities:**")
    discrepancies = evidence_values(report, "**Discrepancy references:**")
    complete = evidence_contract_complete(report, labels)
    commands = (
        "## Exact validation commands" in report
        and PHASE2_REPORT_COMMAND in report
        and DEAS_REPORT_COMMAND in report
    )
    if not (
        complete
        and statuses == ["PACKAGE_PASS_READY_FOR_GIT_DELIVERY"]
        and procedures == ["See Exact validation commands below."]
        and len(identities) == 1
        and GENERATION_2_MANIFEST in identities[0]
        and GENERATION_2_TASK_ID in report
        and commands
    ):
        raise ValidationError("Generation 2 validation report is incomplete")
    if not (
        len(discrepancies) == 1
        and DISCREPANCY_REFERENCES.fullmatch(discrepancies[0]) is not None
    ):
        raise ValidationError("Generation 2 report discrepancy evidence differs")


def find_engineering_gate(repository_root: Path) -> Path:
    for root in (repository_root, *repository_root.parents):
        candidate = root / ENGINEERING_GATE_RELATIVE
        if candidate.is_file():
            verify_engineering_gate_identity(candidate)
            return candidate
    raise ValidationError("canonical DEGS gate is unavailable")


def verify_engineering_gate_identity(gate: Path) -> None:
    actual = sha256_bytes(bounded_bytes(gate, ENGINEERING_GATE_RELATIVE))
    if actual != ENGINEERING_GATE_SHA256:
        raise ValidationError(
            "canonical DEGS gate identity differs",
            path=ENGINEERING_GATE_RELATIVE,
            rule_id="DEAS-PRE-003",
        )


def verify_degs_result(
    result: subprocess.CompletedProcess[bytes],
    action: str,
) -> None:
    if result.stderr or result.returncode != 0:
        raise ValidationError(f"Generation 2 DEGS {action} is not silent PASS")
    payload = parse_external_json(
        result.stdout, f"Generation 2 DEGS {action} output is invalid"
    )
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
        and bool(payload["evidence_paths"])
        and all(isinstance(item, str) for item in payload["evidence_paths"])
    )
    if not valid:
        raise ValidationError(f"Generation 2 DEGS {action} schema differs")


def verify_generation_2_degs(repository_root: Path) -> None:
    gate = find_engineering_gate(repository_root)
    task = repository_root / f"{PACKAGE_PREFIX}/degs/phase2-generation-2-task.json"
    for action in ("validate", "evaluate"):
        result = run_bounded(
            [sys.executable, str(gate), action, str(task), "--json"],
            gate.parents[2],
            f"Generation 2 DEGS {action}",
            DEGS_TIMEOUT_SECONDS,
        )
        verify_degs_result(result, action)
        verify_engineering_gate_identity(gate)


def verify_generation_records(repository_root: Path) -> None:
    history = rooted_text(PACKAGE_ROOT, "generation-history.md")
    source = rooted_text(PACKAGE_ROOT, "source-register.md")
    handoff = rooted_text(PACKAGE_ROOT, "handoff.md")
    required_history = (
        GENERATION_1_COMMIT,
        GENERATION_1_MANIFEST_SHA256,
        GENERATION_2_TASK_ID,
        DEAS_DEFINITION_COMMIT,
        DEAS_MANIFEST_SHA256,
        "generation-2-sha256.txt",
        "EXPECTED_NONCONFORMING",
        "FIRST_CONFORMING_CANDIDATE",
    )
    if any(marker not in history for marker in required_history):
        raise ValidationError("Generation history is incomplete")
    required_source = (
        GENERATION_1_COMMIT,
        GENERATION_2_TASK_ID,
        DEAS_DEFINITION_COMMIT,
        DEAS_MANIFEST_SHA256,
        "generation-2-sha256.txt",
        "documentation correction",
    )
    if any(marker not in source for marker in required_source):
        raise ValidationError("Generation 2 source register is incomplete")
    if not (
        "READY_FOR_GIT_DELIVERY" in handoff
        and "Merge: NOT_AUTHORIZED" in handoff
        and GENERATION_2_TASK_ID in handoff
    ):
        raise ValidationError("Generation 2 handoff state differs")


def verify_privacy_boundary() -> None:
    texts: list[str] = []
    total = 0
    for relative in sorted(PACKAGE_FILES):
        if not relative.endswith((".md", ".json")):
            continue
        value = rooted_text(PACKAGE_ROOT, relative)
        total += len(value.encode("utf-8"))
        if total > MAX_TEXT_BYTES:
            raise ValidationError("combined privacy-inspection input is oversize")
        texts.append(value)
    combined = "\n".join(texts)
    patterns = {
        "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
        "OpenAI-like secret": r"\bsk-[A-Za-z0-9_-]{20,}\b",
        "absolute user path": r"/Users/[^/\s]+",
        "absolute volume path": r"/Volumes/[^\s]+",
        "raw disk identifier": r"\bdisk\d+(?:s\d+)?\b",
        "UUID": r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
        "email address": r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b",
        "MAC address": r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, combined, re.IGNORECASE):
            raise ValidationError(f"prohibited or secret-like material: {label}")
    if "QUALIFIED_FOR_BOUNDED_ROLE" in combined or "QUALIFIED_OUT" in combined:
        raise ValidationError("a forbidden Role Disposition is present")


def validate_generation_2(repository_root: Path) -> None:
    verify_package_file_set()
    verify_manifests(repository_root)
    verify_unchanged_generation_1(repository_root)
    labels = load_evidence_labels(repository_root)
    verify_phase_history(repository_root)
    verify_original_observations(repository_root, labels)
    verify_generation_2_task(repository_root)
    verify_generation_2_report(repository_root, labels)
    verify_generation_records(repository_root)
    verify_privacy_boundary()
    verify_generation_2_degs(repository_root)


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = Phase2ArgumentParser(
        description="Validate Phase 2 Generation 2 through its public seam."
    )
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--generation", required=True, type=int, choices=(2,))
    parser.add_argument("--json", required=True, action="store_true")
    return parser.parse_args(arguments)


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
        "generation": 2,
        "schema_version": 2,
    }


def main() -> int:
    raw_arguments = sys.argv[1:]
    json_requested = "--json" in raw_arguments
    try:
        arguments = parse_arguments(raw_arguments)
        repository_root = arguments.repository_root.resolve()
        if not repository_root.is_dir() or repository_root != SCRIPT_REPOSITORY_ROOT:
            raise ValidationError(
                "repository root differs",
                path=".",
                rule_id="DEAS-PRE-006",
            )
        validate_generation_2(repository_root)
    except (OSError, UnicodeError, ValidationError) as caught:
        error = caught if isinstance(caught, ValidationError) else ValidationError(str(caught))
        if json_requested:
            print(json.dumps(error_payload(error), sort_keys=True))
        else:
            print(f"PHASE2_VALIDATION_ERROR: {error}", file=sys.stderr)
        return 2
    payload = {
        "decision": "PASS",
        "generation": 2,
        "identity_verified": True,
        "original_observations_preserved": True,
        "phase2_degs_decision": "PASS",
        "role_disposition": "NONE",
        "schema_version": 2,
        "validation_report_decision": "PASS",
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
