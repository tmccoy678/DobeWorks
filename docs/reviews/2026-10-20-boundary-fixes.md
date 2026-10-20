# Boundary fixes and verification — October 20, 2026

This correction closes the reproduced input-read, cancellation-deadline, output-depth, and external-result parsing defects in the public synthetic cores and current validator implementations. Its predecessor is commit `10b4ad94dddb7ed64dbb3dd88c77dc8dd67a2d36`.

The changes were written manually after failing regression tests. [Raw evidence](2026-10-20-boundary-fixes-evidence.json) preserves exact commands, times, exits, stdout/stderr, source hashes, and the intermediate validator failure. The sorted [correction manifest](2026-10-20-boundary-fixes-sha256.txt) identifies the changed artifacts. Git delivery and review identities are recorded separately from this immutable package.

## Repairs

| Review finding | Corrected behavior | Regression evidence |
| --- | --- | --- |
| D1 — check-to-open replacement and growth | Shared `bounded_input.py` traverses from a pinned root descriptor, refuses descendant symlinks, checks the opened regular file, and consumes at most the configured limit plus one byte. Short reads cannot hide trailing data; opened descriptors are closed on rejection and success. | Worker/Observer tests grow or replace input at the open boundary, replace an ancestor, exercise short reads and descriptor failures, and retain valid controls. |
| D2 — cancellation preservation outside deadline | Cancellation-race candidate preservation remains inside the active envelope deadline. Expiry returns `FAILED_TIMEOUT`. | A one-second envelope interrupts deliberately slow candidate preservation and records the failure. |
| D3 — interpreter-dependent deep-result rejection | Candidate depth and node counts are explicitly bounded before encoding. A serialization placeholder remains failure evidence and cannot become a handback. | Deep candidates reject consistently on both tested Python versions; a placeholder digest cannot yield success. |
| X1 — ambiguous external gate results | Both current validators reject duplicate JSON keys, invalid UTF-8, nonfinite/overflow numbers, and excessive depth before inspecting exact PASS fields. Compound Phase 2 results also require exact scalar types. | Exact PASS controls remain accepted; contradictory decisions, nested duplicates, malformed values, Boolean/number aliases, and float/integer aliases reject. |

The benchmark harness now identifies the shared input helper as a measured source dependency and rejects helper drift during measurement. The corpus, selection manifest, denominator, and native controls remain unchanged.

## Recorded verification

Host: macOS 27.0.1, build 26A434, Apple silicon arm64. Python 3.14.7 ran in a temporary virtual environment without pip or system site packages; Python 3.9.6 used the system interpreter. Test processes used temporary HOME/TMPDIR and a restricted environment. No dependencies were installed.

| Suite | Python 3.14.7 | Python 3.9.6 |
| --- | ---: | ---: |
| Worker and Observer | 84 passed | 84 passed |
| DEAS, final validator implementation | 39 passed | 39 passed |
| Phase 3 historical-package inputs | 19 passed | 19 passed |
| Benchmark harness tests | 7 passed | 7 passed |
| Phase 4 historical-package tests | 32 skipped | 32 skipped |

All listed final available suites exited 0. The 32 Phase 4 cases require the undistributed external specification through `DOBEWORKS_PHASE4_SPEC`; they are excluded from passing counts.

The [fresh Observer benchmark](../../benchmarks/results/apple-silicon-v3.json) matched 318/318 out-of-contract inputs, with both native controls passing, exit 0, and empty stderr. This is application rejection evidence at the Observer CLI.

The first integrated validation run included a four-failure compound scalar-type regression. The raw record retains that observation. Independent review identified the type-alias gap; the manual correction was followed by complete 39-test DEAS reruns passing on both interpreters. The evidence file names the accepted and superseded record indices explicitly.

Independent source reviews covered the runtime and cross-system boundaries. The X1 implementation's initial author was not its sole reviewer; separate reviewers examined the parser and the later exact-type correction. Source functions changed by this correction satisfy the applicable 60-line bound.

## Historical and operational boundaries

Historical manifests, externally pinned gate hashes, and original observations are preserved. Current validator changes supersede their executable implementations; they do not rewrite or qualify a frozen historical package. The historical validators still require their older external DEGS identity. These sibling public repositories are not a demonstrated current operational integration.

Worker success remains `COMPLETED_UNACCEPTED`, with promotion unperformed and automatic retry prohibited. Observer returns records or retention decisions without dispatch, remediation, or deletion. Descriptor confinement does not create an immutable snapshot of concurrently changing file contents. POSIX descriptor facilities and the main-thread timer remain required for the tested bounded paths; arbitrary injected Python adapters are not sandboxed.

## Evidence record

- **Evidence ID:** DOBEWORKS-BOUNDARY-FIXES-20261020
- **Requirement/fault IDs:** D1, D2, D3, X1; DEAS-PRE-002, DEAS-PRE-007
- **Claim under test:** The corrected component boundaries reject the reproduced malformed or out-of-bound cases while retaining the documented synthetic success paths.
- **Acceptance method:** Regression-first public API/CLI tests, existing suites, pinned public-data benchmark, source inspection, and independent review.
- **Exact source/configuration/role/device-safe identity/environment/target:** Base commit above; final source identities and environment in the raw evidence; changed-artifact identities in the correction manifest.
- **Procedure or command identity:** Exact command arrays in the raw evidence; documented unittest discovery and benchmark commands.
- **Start time:** 2026-10-20T20:58:52.006529+00:00
- **End time:** 2026-10-20T21:03:29.415163+00:00
- **Clock-quality basis:** Host wall-clock UTC timestamps; independent synchronization not verified.
- **Expected result:** Reproduced defects reject; valid controls pass; all available applicable suites pass; historical Phase 4 cases skip without their external specification.
- **Actual result:** 84 core, 39 DEAS, 19 Phase 3, and 7 benchmark tests passed on each interpreter; 32 Phase 4 cases skipped on each; 318/318 benchmark inputs and both controls passed.
- **Status:** PASS for the stated component checks.
- **Discrepancy references:** Reproduced D1, D2, D3, and X1 corrected; unavailable historical Phase 4 specification remains an explicit scope limit.
- **Artifact paths:** docs/reviews/2026-10-20-boundary-fixes-evidence.json; docs/reviews/2026-10-20-boundary-fixes-sha256.txt; benchmarks/results/apple-silicon-v3.json.
- **Cryptographic identities:** Sorted correction manifest and raw evidence source_sha256 map; historical identities remain unchanged.
- **Evidence owner:** Taylor; Codex prepared this correction and verification record.
- **Human/physical action owner:** Taylor; no physical or live-system action performed.
- **Confidentiality classification:** Public source, public benchmark corpus, and synthetic test data.
- **Recoverability classification:** Original Git history and exact baseline backups retained; revert the bounded correction to restore its predecessor.
- **Limitations:** Synthetic component checks on one host; 32 undistributed-specification tests skipped; historical external gate compatibility unchanged.
- **Unsupported inferences:** Operational integration, device support, installation, qualification, authorization, promotion, or production readiness.
- **Current freshness:** Fixed observation for the identified source bytes; rerun affected checks after relevant source or configuration changes.
- **Supersession:** Current-source claims use this record; earlier benchmark and historical-package observations remain attributable and unchanged.

DEAS Strict applies with Python, Document, Evidence, Validator, AI-Assisted, and Git overlays. Taylor authorized corrections to the existing public repositories, selecting their public remotes for this task. The bounded objective is the reviewed defects and their tests, directly affected documentation, and evidence. Publication of corrected source does not activate or qualify the Operational System.
