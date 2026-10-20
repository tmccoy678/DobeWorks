# Benchmark correction and validation scope

The first benchmark observation remains unchanged in [apple-silicon.json](../benchmarks/results/apple-silicon.json). The historical harness correction is recorded in [apple-silicon-v2.json](../benchmarks/results/apple-silicon-v2.json); [comparison](../benchmarks/results/measurement-comparison.json) records both run hashes and every changed case. Corpus pins, input bytes, labels, and denominators are unchanged. [Historical test output](../benchmarks/results/validation-v2.json) retains commands, timestamps, exits, and diagnostics. The [October boundary-fix record](reviews/2026-10-20-boundary-fixes.md) identifies the newer runtime and validator implementations separately.

Both harnesses now preserve partial timeout diagnostics and actual script invocation arguments. The Observer stale control requires literal STALE freshness. Negative tests inject a real delayed process, contradictory freshness, broken candidates, and changed corpus/selection bytes. They failed for the intended reasons before the fixes and pass afterward. Python 3.9 cannot report original interpreter argv; the report records that limitation, the executable, effective interpreter flags, working directory, and exact script arguments.

## Observer and historical package checks

**Historical test-fixture correction:** package samples were changed to come from pinned commits, while the validator CLIs remained under test. That recorded run passed 150 tests: DEAS 29, Phase 3 19, Phase 4 32, and Worker/Observer 70. Its Phase 4 run used the required external specification. The four failures described below are retained as the earlier observation, not the result of the corrected setup. See [historical package test scope](historical-package-tests.md) and [fixture-correction evidence](historical-package-test-results.json).

The Observer source and fixtures were unchanged by that harness correction. Its 318 public out-of-contract inputs produced controlled unusable outcomes; both native controls passed. This is application rejection evidence, not JSON parser conformance or whole-system assurance. Its recorded Worker/Observer and benchmark results concern the source generation identified in those records.

The earlier 149-test run had 145 passes and four failures: DEAS 27/28, Phase 3 18/19, Phase 4 package validation 30/32, Worker/Observer 70/70. These reproduced at the approved base 793ed01. The DEAS manifest expected an older README identity; Phase 3 likewise expected its frozen Operational System README. Phase 4's positive package tests asserted an exact diff against their historical baseline, but the supplied draft base already contained documentation paths outside that package. That benchmark commit added more paths outside the historical package; it could not qualify as that exact package either.

The earlier draft report describes its earlier observation and is retained; its 148/149 summary does not describe current main or these changes. Historical assertions need their original complete package tree and specified external identities. Current runtime tests and the new benchmark use current draft source. Passing either set cannot substitute for the other. No historical manifest has been rehashed to hide drift.

The historical 792-line Phase 2 validator refers to an externally pinned DEGS identity. It contains no copy of the defective comparator. Its historical hash remains unchanged. The October correction supersedes the current validator implementation's external-result parser; it does not rewrite the frozen Phase 2 package. A future current-system integration package must explicitly bind the corrected DEGS source and generate new evidence.

## Remaining work

The user approved correction of staged system v1 and v2. The verified working pair is now published as DobeWorks-v2.1 and DEGS-v2.1 development snapshots. A separate pre-Generation-2 staged v1 pair has not been identified. A component directory named v1 does not establish that system version. Apply the same behavioral regression and a minimal backport after its exact repository or commit is identified.

The public source snapshot does not claim that a complete bundled DobeWorks product exists. Historical plans for integrated Trash Pickup, Treasure Pickup, and FigureMe remain future composition work. The standalone [Trash and Treasure Pickup pair](https://github.com/tmccoy678/TrashTreasurePickup) is independently available. Nothing here qualifies the synthetic system for production.
