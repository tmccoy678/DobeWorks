#!/usr/bin/env python3
"""Render the append-only DobeWorks handoff stream as two readable lanes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterator


SCHEMA = "dobeworks.handoff-event/v1"
LANE_WIDTH = 46


class HandoffViewError(Exception):
    pass


def _wait_for_stream(path: Path, follow: bool, interval: float, idle_timeout: float) -> None:
    deadline = time.monotonic() + idle_timeout
    while not path.exists() and follow and time.monotonic() < deadline:
        time.sleep(interval)
    if path.is_symlink() or not path.is_file():
        raise HandoffViewError("handoff stream must be a regular file")


def _read_lines(
    path: Path,
    follow: bool,
    interval: float,
    idle_timeout: float,
) -> Iterator[str]:
    _wait_for_stream(path, follow, interval, idle_timeout)
    deadline = time.monotonic() + idle_timeout
    with path.open("r", encoding="utf-8") as stream:
        while True:
            line = stream.readline()
            if line:
                deadline = time.monotonic() + idle_timeout
                yield line
                continue
            if not follow:
                return
            if time.monotonic() >= deadline:
                raise HandoffViewError("handoff stream exceeded its idle timeout")
            time.sleep(interval)


def _validate_event(value: Any, expected_sequence: int) -> dict[str, Any]:
    fields = {
        "schema_version",
        "sequence",
        "observed_at",
        "job_id",
        "event",
        "stage",
        "actor",
        "authority",
        "details",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise HandoffViewError("handoff event fields differ from version one")
    if value["schema_version"] != SCHEMA:
        raise HandoffViewError("unsupported handoff event schema")
    if value["sequence"] != expected_sequence:
        raise HandoffViewError("handoff sequence is not contiguous")
    if not isinstance(value["details"], dict):
        raise HandoffViewError("handoff details must be an object")
    for field in ("observed_at", "job_id", "event", "stage", "actor", "authority"):
        if not isinstance(value[field], str) or not value[field]:
            raise HandoffViewError(f"invalid handoff field: {field}")
    return value


def _operation_text(prefix: str, details: dict[str, Any]) -> str:
    parts = [prefix, str(details.get("operation", "unknown"))]
    if "path" in details:
        parts.append(str(details["path"]))
    if "check_id" in details:
        parts.append(str(details["check_id"]))
    if "state" in details:
        parts.append(str(details["state"]))
    return " ".join(parts)


def event_text(event: dict[str, Any]) -> str:
    name, stage, details = event["event"], event["stage"], event["details"]
    if name == "preflight_admitted":
        return f"PREFLIGHT {details.get('degs_preflight_readiness')}"
    if name == "stage_started":
        return f"START {stage.upper()}"
    if name == "stage_completed":
        return f"HANDOFF {stage.upper()} COMPLETE"
    if name == "operation_proposed":
        return _operation_text("PROPOSE", details)
    if name == "operation_completed":
        return _operation_text("ALLOW", details)
    if name == "operation_rejected":
        return _operation_text("REJECT", details)
    if name == "adapter_failed":
        return f"ADAPTER FAILED {details.get('state')}"
    if name == "review_report_aggregated":
        return f"REVIEW {details.get('agent_reported_concern_status')}"
    if name == "human_acceptance_required":
        return "HUMAN ACCEPTANCE REQUIRED"
    return f"{name.upper()} [{stage}]"


def render_row(event: dict[str, Any]) -> str:
    text = event_text(event)[:LANE_WIDTH]
    if event["actor"] == "AGENT_ADAPTER":
        left, right = text, ""
    else:
        left, right = "", text
    return f"{event['sequence']:04d}  {left:<{LANE_WIDTH}} | {right}"


def run(path: Path, follow: bool, interval: float, idle_timeout: float) -> None:
    print(f"{'SEQ':<6}{'AGENT / PROPOSAL':<{LANE_WIDTH + 1}} | CONTROLLER / EVIDENCE")
    print(f"{'-' * 4:<6}{'-' * LANE_WIDTH} | {'-' * LANE_WIDTH}")
    expected = 1
    for raw in _read_lines(path, follow, interval, idle_timeout):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise HandoffViewError(f"invalid handoff JSON: {error}") from error
        event = _validate_event(value, expected)
        print(render_row(event), flush=True)
        expected += 1
        if follow and event["event"] in {
            "adapter_failed",
            "human_acceptance_required",
            "operation_rejected",
        }:
            return


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stream", type=Path)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--idle-timeout", type=float, default=60.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 0.02 <= args.interval <= 5.0:
        print("interval must be between 0.02 and 5.0 seconds", file=sys.stderr)
        return 2
    if not 1.0 <= args.idle_timeout <= 3600.0:
        print("idle timeout must be between 1 and 3600 seconds", file=sys.stderr)
        return 2
    try:
        run(args.stream, args.follow, args.interval, args.idle_timeout)
    except (HandoffViewError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
