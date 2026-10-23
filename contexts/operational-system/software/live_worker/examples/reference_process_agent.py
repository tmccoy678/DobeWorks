#!/usr/bin/env python3
"""Deterministic reference client for the process-Adapter protocol."""

from __future__ import annotations

import json
import sys


def choose_action(request: dict) -> dict:
    stage = request["stage"]
    history = request["history"]
    if stage == "inspect" and not history:
        return {"operation": "read_file", "path": "README.txt"}
    if stage == "review":
        return {
            "operation": "finish_stage",
            "summary": "Reference Adapter completed review.",
            "concerns": [],
            "dismissed_concerns": [],
        }
    return {
        "operation": "finish_stage",
        "summary": "Reference Adapter completed the bounded stage.",
    }


def main() -> int:
    try:
        request = json.load(sys.stdin)
        action = choose_action(request)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(action, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
