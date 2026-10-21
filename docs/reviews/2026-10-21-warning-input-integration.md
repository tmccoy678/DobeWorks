# DobeWorks v3.0 warning-input integration verification

DobeWorks now selects the sibling `DEGS-v3.0` gate by default. An explicit `--degs-root` still selects another checkout. The shared adapter preserves DEGS's derived unresolved count and numbered, sanitized issues. Every active warning or unresolved item blocks readiness; closure requires agreeing `NONE` / `RESOLVED` / `true` fields and a nonblank recorded evidence reference. Conflicting resolution fields fail validation.

The final frontend suite passed **10 tests**, including three cases using the actual sibling DEGS CLI: an active item blocks, conflicting closure fails, and recorded closure permits otherwise-valid readiness. The other seven frontend checks also passed. This run used the final DEGS candidate containing the warning, numeric-input, and Unicode corrections; the frontend suite directly exercises the warning contract, while the DEGS core tests cover the other counterexamples.

One earlier actual current-pair integration run returned exit `0`, empty stderr, fresh Observer `PASS`, stale Observer `BLOCKED`, and unaccepted Worker `BLOCKED`. That single run preceded the final Unicode correction. Its start and end timestamps were **NOT RECORDED**, and its temporary artifacts were removed after checking the output. It is a separate observation from the final suite below.

## Evidence record

- **Evidence ID:** DOBEWORKS-V3-WARNING-INPUT-INTEGRATION-2026-10-21
- **Requirement/fault IDs:** DEGS review findings 1 and 2; DWI-V3-PAIR-001 (default public v3 pairing); DEAS-PRE-003, DEAS-PRE-005, DEAS-PRE-007, DEAS-PRE-010.
- **Claim under test:** The public v3 frontend selects the v3 gate by default and preserves blocked, invalid, and resolved warning decisions through its existing adapter.
- **Acceptance method:** CLI integration tests and existing frontend unit tests, with exact input hashes checked before and after execution.
- **Exact source/configuration/role/device-safe identity/environment/target:** DobeWorks base `92d49f1c3f7505605e276322ba06bc2b19983d73`; DEGS base `30c93fa6bb05bad56504d8b666ea407491be7720` plus candidate-file SHA-256 values in the evidence JSON; Python 3.9.6 on Darwin arm64; sibling `DEGS-v3.0`; Strict profile with Python, Document, Evidence, Validator, AI-Assisted, and Git overlays.
- **Procedure or command identity:** `python3 -B -m unittest discover -s interface -p 'test_*.py' -v` from the DobeWorks repository root, with a 120-second subprocess timeout.
- **Start time:** 2026-10-21T03:09:15.888964+00:00
- **End time:** 2026-10-21T03:09:16.181795+00:00
- **Clock-quality basis:** Local host UTC wall clock and monotonic elapsed time; independent clock synchronization was not measured.
- **Expected result:** Exit `0`; 10 tests executed; zero failures, errors, or skips; unchanged candidate hashes.
- **Actual result:** Exit `0`; 10 tests executed; zero failures, errors, or skips; `Ran 10 tests in 0.231s` and `OK` in unittest's standard stderr report; empty stdout; all captured hashes unchanged. Exact stdout and stderr are retained in the evidence JSON.
- **Status:** PASS for this recorded frontend test execution; publication and final delivery identity checks remain outside this record.
- **Discrepancy references:** NONE for the final frontend suite.
- **Artifact paths:** [Sorted correction manifest](2026-10-21-warning-input-integration-sha256.txt); [2026-10-21-warning-input-integration-evidence.json](2026-10-21-warning-input-integration-evidence.json); [interface implementation](../../interface/command_center.py); [frontend tests](../../interface/test_command_center.py); [warning integration tests](../../interface/test_degs_warning_contract.py); [interface guide](../../interface/README.md).
- **Cryptographic identities:** Evidence JSON SHA-256 `3b0b4d2b6ef92832c39970c9e6593e60efe5b16f190342444ab01c9bb6b47c55`; before/after SHA-256 values for all four changed interface files and the directly used DEGS gate, schema, and Tier 0 fixture are in that JSON. Base commits identify unchanged tracked inputs.
- **Evidence owner:** Taylor, repository owner; capture prepared by the Codex integration agent.
- **Human/physical action owner:** NOT APPLICABLE to these local synthetic tests.
- **Confidentiality classification:** PUBLIC; public source, synthetic records, and local test execution metadata.
- **Recoverability classification:** Reversible source and documentation changes on a short-lived branch; prior committed bytes retained in Git.
- **Limitations:** The three new warning cases invoke the actual gate; other frontend cases retain their existing mocks. The suite does not authenticate closure evidence or directly reproduce the numeric and Unicode counterexamples. An explicitly selected older gate retains its own behavior.
- **Unsupported inferences:** Clinical safety, legal authorization, production qualification, and overall DEAS conformance remain unmeasured by this test run.
- **Current freshness:** Exact candidate bytes captured during the stated final run; later code or schema changes require renewed verification.
- **Supersession:** Supplements the preserved historical DEGS core review; does not edit or replace it.
