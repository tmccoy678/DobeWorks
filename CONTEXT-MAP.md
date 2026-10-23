# DobeWorks Context Map

## Contexts

- [DobeWorks](CONTEXT.md) — owns the complete name, personal-project scope, public-source boundary, identity, mark, and provenance language.
- [Operational System](contexts/operational-system/CONTEXT.md) — owns hardware/software mission, roles, data and recovery classes, requirements, configuration, evidence, operations, maintenance, and retirement.

## Relationships

- **Operational System → DobeWorks**: The Operational System belongs to DobeWorks and inherits its source-publication and identity boundaries without redefining the name or identity.
- **Operational System ↔ Taylor AI Workbench and Command Center**: Historical program records refer to external supervised implementation and routing interfaces; this repository does not include or redefine them.
- **Operational System → DEGS**: The Operational System supplies task records and evidence to the external [DEGS repository](https://github.com/tmccoy678/DEGS-v2.1); it does not copy DEGS policy or treat a gate result as execution authority.
- **Governed live worker → Operational System and DEGS**: The experimental live-worker Module belongs to the Operational System. It invokes exact-identity DEGS gate and review-adapter files without importing DEGS policy or converting readiness into candidate acceptance.

## Decision placement

- Cross-context and repository-shape decisions live under `docs/adr/`.
- Decisions owned only by the Operational System live under `contexts/operational-system/docs/adr/` when the first such decision is recorded.
- The context map and each context glossary contain vocabulary and ownership only; program requirements and implementation details live outside the glossaries.
