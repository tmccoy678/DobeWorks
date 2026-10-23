---
status: accepted
---

# Add a governed live-worker seam and direct handoff stream

Taylor approved a public seam in which a versioned Job Envelope enters
DobeWorks, an Adapter proposes bounded operations against a disposable
candidate, and the controller returns an atomic `COMPLETED_UNACCEPTED`
handback. DobeWorks owns workflow and enforcement; DEGS supplies preflight
readiness and deterministic review-value aggregation; human acceptance remains
separate.

The live-worker path emits `dobeworks.handoff-event/v1` JSON Lines while work is
in progress. Agent proposals, deterministic controller decisions, DEGS
aggregation, and the human-only acceptance boundary have distinct actor and
authority labels. A two-lane terminal viewer consumes these records directly.
Visual interfaces may change without changing or reverse-engineering the
execution protocol.

## Consequences

- Provider-specific agents remain replaceable behind one process protocol.
- The command invocation is the external authorization boundary. The envelope
  records that authority, but version one does not authenticate it with a
  signature.
- An agent cannot acquire direct project access merely because it runs locally;
  project operations remain controller-mediated.
- Adapter, check, and DEGS invocations are single-process Seatbelt jobs:
  `process-exec` is allowed and `process-fork` is denied. Each invocation also
  owns a fresh process group that is terminated at the end of the bounded turn.
- A DEGS preflight `PASS`, an agent report of `NONE_REPORTED`, a staged
  candidate, and human acceptance remain different states.
- Observability is part of the first implementation rather than a later log
  parser, and the visible stream omits file contents and private reasoning.
- Adapter failure and controller rejection are terminal visible events; invalid
  path-like proposal values are redacted before they enter the stream.
- Version one stops with reported unresolved concerns. It does not claim
  semantic completeness or import Sashiko's full review workflow.
- External model execution, broader isolation evidence, promotion, deployment,
  and release require separate work and authority.
