# Governed live worker

Status: confirmed for implementation by Taylor on 2026-10-23.

## Objective

Assemble the existing DobeWorks Worker/Observer boundaries, DEGS readiness
gate, and Sashiko-derived review-state operations into one provider-neutral
live-worker path. An agent may propose bounded operations inside a fixed
workflow. It may not choose its authority, workflow, stage, mutation surface,
or Promotion Event.

## Public seam

The public interface is a versioned live Job Envelope submitted through the
DobeWorks command-line interface. Inputs are an immutable envelope, a source
repository, a DEGS checkout, an agent Adapter, and an existing staging root.
The Module operates on a disposable candidate and returns an atomic staged
handback whose terminal success state is `COMPLETED_UNACCEPTED`.

## Fixed workflow

1. Inspect with read/search operations only.
2. Execute and check with envelope-authorized structured edits and checks.
3. Review the frozen candidate without mutation.
4. Aggregate and stage-stamp the agent-supplied review values without silently
   dropping a reported concern or claiming semantic completeness.
5. Report an auditable, unaccepted handback for separate human review.

The report step belongs to the controller. The Adapter cannot jump stages,
expand tools, approve unknowns, or promote output. Version one preserves every
reported concern but cannot determine whether the Adapter omitted a concern or
soundly dismissed one; semantic reconciliation, deduplication, and finding
verification remain future work.

The command invocation is the external authorization boundary. The envelope's
`dispatch_authority` field records the supplied basis but is not a signature.
The caller-selected DEGS checkout and Adapter are executable trust inputs whose
hashes establish exact byte identity, not trustworthiness.

## Observability seam

The controller writes `dobeworks.handoff-event/v1` JSON Lines as each proposal
and decision occurs. Records distinguish agent proposal, controller
enforcement, DEGS aggregation, and human-only acceptance authority. They omit
file contents, credentials, agent summary prose, and private reasoning. A
direct two-lane viewer consumes this event stream without parsing terminal
text. Invalid path-like proposal values are redacted, Adapter failure is a
terminal visible event, and contiguous sequence numbers—not the repeated
evaluation timestamp—establish event order.

## Selected assurance

- Profile: DEAS Strict.
- Overlays: Python, Document, Evidence, Validator, AI-Assisted, and Git.
- First vertical slice: a deterministic inspect-only Adapter run.
- First postcondition: source bytes are unchanged; staged candidate and
  evidence are identity-bound; promotion is `NOT_PERFORMED`.
- Initial negative cases: stage jump, unapproved operation, unresolved concern
  represented as clean, and self-promotion.
- Process boundary cases: direct source read and unrelated home-file read are
  denied; agent identity bytes are hash-bound and staged before execution; a
  process-group or session escape cannot occur because Adapter, check, and DEGS
  subprocesses execute under a Seatbelt profile that denies `process-fork`.
- Parser boundary cases: malformed, deeply nested, non-finite, duplicate, and
  diagnostic-bearing structured subprocess results fail closed, and DEGS
  output is capped while it is produced rather than after in-memory capture.
- Paid or external model execution is excluded until deterministic tests pass
  and a separate model budget is authorized.
