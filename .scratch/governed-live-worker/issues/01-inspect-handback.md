# Inspect-only staged handback

Status: resolved

## Acceptance

Through the command-line seam, a valid read-only envelope and deterministic
Adapter script produce an atomic `COMPLETED_UNACCEPTED` handback. The exact
source tree remains unchanged. The DEGS gate identity and result, ordered stage
events, candidate identity, observer record, and `NOT_PERFORMED` promotion
state are inspectable in the staged output.

## Failure state

Invalid identity, authority, path, gate result, Adapter operation, stage
transition, or output leaves no completed destination and returns a structured
non-success result.

## Comments

- 2026-10-23: Public seam confirmed by Taylor. Baselines: DobeWorks 84 passing;
  DEGS 103 passing and one expected interpreter-specific skip.
- 2026-10-23: Implemented and verified through the public CLI. The final
  package run passed 33 live-worker/handoff cases, 84 existing core cases, and
  12 existing interface cases. The companion DEGS suite passed 109 cases with
  its one expected Python 3.9 skip. The deterministic PROCESS Adapter demo
  produced 17 contiguous handoff records and stopped at the human-acceptance
  boundary with promotion `NOT_PERFORMED`.
- 2026-10-23: Independent review proved that process-group termination alone
  did not contain a child that called `setsid()`. Adapter, check, and DEGS
  invocations now deny `process-fork` under Seatbelt, with three adversarial
  regressions that attempt the exact fork-and-session escape.
