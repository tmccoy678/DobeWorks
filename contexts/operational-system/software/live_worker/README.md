# Governed live worker

The governed live worker lets an external agent propose bounded operations while
DobeWorks owns the workflow, permissions, execution, evidence, and final state.
Every successful run ends as `COMPLETED_UNACCEPTED`; neither the agent nor DEGS
can promote its candidate.

This is an experimental integration path in the current tree. It is separate
from the synthetic Phase 4 Worker Core and does not qualify a production
system.

## Try the process handoff

With DobeWorks and DEGS cloned beside each other, run:

```sh
python3 -B contexts/operational-system/software/live_worker/demo.py
```

The no-key reference Adapter chooses each next operation through the real
process protocol. DobeWorks performs the operations and then prints the direct
two-lane handoff view. This is a deterministic protocol demonstration, not a
live-model claim. Its local artifacts are written beneath the ignored
`interface/Runs/governed-live-worker/` directory.

## What happens

1. DobeWorks validates a closed, versioned Job Envelope and exact source,
   Adapter, DEGS gate, task-record, review-adapter, Sashiko-port, and provenance
   identities.
2. DEGS evaluates preflight readiness. A pass admits the bounded job; it is not
   candidate acceptance.
3. DobeWorks copies the source into a disposable candidate and runs the fixed
   `inspect`, `execute_check`, and `review` stages.
4. The Adapter proposes one operation at a time. DobeWorks validates and
   performs only controller-listed operations.
5. The DEGS review-state adapter stage-stamps and preserves agent-supplied
   concern values without making a semantic completeness claim.
6. DobeWorks atomically stages the candidate and evidence for human review.

| Actor | Can do | Cannot do |
| --- | --- | --- |
| Agent Adapter | Propose listed reads, structured replacements, checks, and stage completion | Change stages, permissions, paths, checks, authority, or promotion state |
| DobeWorks controller | Validate identities, execute allowed operations, enforce bounds, record handoffs | Accept the candidate or infer that an omitted concern is absent |
| DEGS gate | Decide whether recorded preflight evidence satisfies its policy | Execute work or accept the resulting candidate |
| DEGS review adapter | Preserve and stage-stamp supplied concerns and dismissals | Perform semantic review, deduplication, conflict resolution, or verification |
| Human reviewer | Inspect and separately accept or reject the staged candidate | Inherit acceptance from a gate or successful process exit |

## Adapter modes

`SCRIPTED` consumes a deterministic three-stage JSON script. It exists for
tests, demonstrations, and reproducible failure cases.

`PROCESS` invokes a hash-bound external program once per requested action. Each
invocation receives one `dobeworks.agent-turn/v1` JSON object on standard input
and must return one JSON operation on standard output. The turn contains the
objective, current stage, permitted operations, relative paths, check IDs,
candidate hash, and prior controller-mediated observations. It does not contain
an absolute source path.

On macOS, process invocations run through Seatbelt with bounded time and output.
Network access and environment-variable names are explicit in the hash-bound
Adapter configuration. Original Adapter files are verified, copied into a
temporary execution directory, and invoked from those copies. Reads beneath
`/Users`, `/Volumes`, the source, the staging root, and the DEGS checkout are
denied; the controller mediates project reads. The process can still read
runtime material elsewhere on the host, so this is not a host-wide
confidentiality proof or a substitute for a dedicated VM.
After each turn, DobeWorks terminates the Adapter's complete process group so a
forked descendant cannot outlive the bounded invocation.

DEGS commands run under isolated Python flags with a fixed `PATH` and `LANG`;
ambient environment variables are not inherited. Their exact source bytes are
verified before execution. The CLI caller selects `--degs-root`, so that path
is an executable trust input: a matching hash establishes identity, not
trustworthiness. Likewise, `dispatch_authority` records the supplied authority
basis but is not a digital signature. Invoking the command with those inputs is
the external authorization boundary in version one.

## Operations

- `read_file`: bounded UTF-8 read of one envelope-listed relative path.
- `replace_text`: exact hash- and occurrence-bound replacement in the
  disposable candidate; available only when mutation is authorized.
- `run_check`: one path-safe, envelope-listed command under a no-network macOS
  sandbox. The command receives only a fixed `PATH` and `LANG`, can read its
  candidate but not `/Users` or `/Volumes`, may not mutate the candidate, and
  cannot leave a descendant process running after the check.
- `finish_stage`: returns the agent's stage summary. Review completion also
  returns reported concerns and dismissed concerns.

There is no general shell operation. Every stage has a maximum action count,
and every process and check has an explicit timeout and output cap.
Version one also caps a source tree during enumeration at 20,000 total entries,
10,000 files, and 512 MiB, with no single identity-hashed file larger than
64 MiB; file hashes are streamed in one-MiB blocks.

## Watching the handoffs

`handoffs.jsonl` is written and flushed as the run proceeds. It is the stable
version-one observability seam, not a transcript: it contains proposal type,
controller disposition, hashes, check results, stage transitions, and authority
labels, but no file contents, credentials, private model reasoning, or agent
summary prose. Invalid path-like proposal values are redacted before append,
and an Adapter failure becomes a terminal `adapter_failed` record. Sequence
numbers establish event order; `observed_at` is the envelope evaluation time,
not a per-event high-resolution clock.

Render an existing stream:

```sh
python3 -B contexts/operational-system/software/live_worker/handoff_view.py \
  /path/to/staging/job-id/handoffs.jsonl
```

Follow an active partial handback until rejection, human handoff, or the bounded
idle timeout:

```sh
python3 -B contexts/operational-system/software/live_worker/handoff_view.py \
  /path/to/staging/.partial-job-id/handoffs.jsonl --follow
```

The viewer places agent proposals in the left lane and DobeWorks/DEGS actions
in the right lane. Other interfaces can consume the same
`dobeworks.handoff-event/v1` records without parsing terminal text.

## Handback artifacts

- `candidate/`: disposable result; never accepted automatically.
- `handoffs.jsonl`: append-only live proposal/enforcement view.
- `events.json`: detailed controller event snapshot.
- `checks/`: structured results for required checks.
- `degs-result.json`: preflight readiness result.
- `review-request.json` and `review.json`: agent-supplied review values and the
  deterministic aggregation result.
- `observer.json`: current artifact-presence and authority state.
- `artifact-manifest.json`: hashes of artifacts produced before the handback.
- `handback.json`: terminal `COMPLETED_UNACCEPTED` record and identities.

The handback uses separate fields for `degs_preflight_readiness` and
`agent_reported_concern_status`. `NONE_REPORTED` means only that the Adapter
supplied no unresolved concern; it does not mean the candidate is clean.

## Tests

Run the public-seam tests against a sibling DEGS checkout:

```sh
DOBEWORKS_DEGS_ROOT=../DEGS python3 -B -m unittest discover \
  -s contexts/operational-system/software/live_worker -p 'test_*.py' -v
```

The suite exercises success, direct-source and ambient-home read denial,
identity substitution, unapproved operations, stage jumps, self-promotion,
read-only mutation, failed checks, preserved concerns, malformed and non-finite
JSON, diagnostic-bearing successful subprocesses, redacted invalid proposals,
the actual DEGS review adapter, and malformed handoff streams. It runs no paid
model call.

## Current limits

- The process sandbox and command-check sandbox require macOS
  `/usr/bin/sandbox-exec`.
- Version one supports exact text replacement, not arbitrary patches.
- The controller detects source or candidate identity drift around copying, but
  it does not claim an operating-system snapshot against a change-and-revert
  race.
- Source-tree limits are fixed version-one controller bounds rather than
  per-envelope settings.
- The review adapter preserves supplied values; semantic investigation,
  autonomous reconciliation, deduplication, conflict resolution, and finding
  verification are not implemented.
- No provider-specific live-model Adapter or paid external-model evidence is
  included yet.
- Exact hashes establish byte identity, not the trustworthiness of an
  operator-selected DEGS checkout, Adapter, or Job Envelope.
- Human acceptance, Git commit, push, merge, release, deployment, and retry are
  separate actions outside this command.
