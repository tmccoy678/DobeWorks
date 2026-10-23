# DobeWorks

![DobeWorks and DEGS shared terminal interface](docs/figures/DobeWorks_UI.jpg)

DobeWorks provides a bounded Worker and a read-only Observer. The shared terminal interface runs both alongside [DEGS](https://github.com/tmccoy678/DEGS), the engineering evidence gate.

## Start here

Install Git and Python 3.9 or later, then run these commands from a directory where you keep projects:

```sh
git clone https://github.com/tmccoy678/DobeWorks.git
git clone https://github.com/tmccoy678/DEGS.git
cd DobeWorks
python3 -B interface/command_center.py menu
```

No Python packages, model account, or API key are required. On macOS, `zsh DobeWorks.command` opens the same menu with the screenshot's Terminal settings. Keep the two folders beside each other, or use `--degs-root /path/to/DEGS` before `menu`.

Choose **01** for the paired demonstration, **07** to check both cores, or **00** to close. The examples use synthetic records: a fresh Observer record passes, a stale record blocks, and Worker output stays staged until separately accepted. Local run evidence is saved under `interface/Runs/`.

[Interface guide and command reference](interface/README.md) · [Worker and Observer details](contexts/operational-system/software/phase4/README.md)

## Initial release

This release contains the implemented synthetic Worker and Observer cores, the shared interface, examples, tests, and supporting documentation. Its Git tag is `initial-release-final`. Internal policy, phase, correction-generation, and benchmark numbers keep their existing meanings.

The Sashiko/Live-SWE executor is proposed follow-up work. The current examples do not operate a device, grant execution authority, or qualify a production system. Source archives are available with the release; the shared interface requires Git clones with an `origin` remote.

## Evidence and documentation

- [Core verification and correction record](docs/reviews/2026-10-20-boundary-fixes.md) and [paired warning-contract verification](docs/reviews/2026-10-21-warning-input-integration.md)
- [Benchmark method, results, and reproduction](benchmarks/benchmark.md)
- [Illustrated system guide](docs/figures/README.md)
- [Engineering assurance standard](docs/standards/deas/v1/standard.md), [citations](CITATIONS.md), and [historical package tests](docs/historical-package-tests.md)

## From Taylor

I will briefly introduce Dobeworks and DEGS. First, DobeWorks and DEGS were originally intended for personal-use after I became quite obsessed with LLM hallucinations and developing a way to perform auditable context transfer between windows for Codex and OpenAI models in August, 2026.

I am aware that it is impossible to eliminate errors. It follows then that DobeWorks and DEGS do not try to fix errors; and one strength of the systems is their ability to prevent errors from moving forward into the next ticket or part of the work.

For a time, I used DobeWorks and DEGS in front of every message entering my regular Codex terminal. As I made the governance more exacting, ordinary work became buried under gate preparation. I created a separate external clean Workbench lane to regain balance. That history explains why a Tier 2 record with required human approval marked `REJECTED` was once allowed to return `PASS`, but it was not a truthful gate result and has been corrected in DEGS. A proper Doberman is resolute, quiet, and poised in the house; it does not need to splash in a river to prove that it is moving. DobeWorks should remain an umbrella over AI while applying governance in proportion to the work.

### Historical screenshots

| September 8: recognizing the governance burden | October 22: documenting the installed external Workbench menu |
|---|---|
| [![A preserved terminal conversation says routine trash handling had begun to feel like a launch sequence.](docs/figures/history/2026-09-08-governance-overhead.png)](docs/figures/history/2026-09-08-governance-overhead.png) | [![The Taylor AI Workbench menu displays C Clean Path Codex alongside the existing Codex route.](docs/figures/history/2026-10-22-workbench-clean-path.png)](docs/figures/history/2026-10-22-workbench-clean-path.png) |

The September image is a surviving contemporaneous screenshot from the discussion that led to the external Clean Path. The October image documents the currently installed Workbench launcher after it was opened solely for this record; its capture date is not a usage date. See [Governance balance and external Clean Path history](docs/history/clean-path-balance.md) for provenance and interpretation.

DobeWorks and DEGS are my personal engineering system for methodological systems, software, research infrastructure, and special projects.

If you would like to discuss DobeWorks and/or DEGS privately, please email me at: tmccoy678@gmail.com.

Thank you,

Taylor

Except for material identified in [third-party notices](THIRD_PARTY_NOTICES.md) and under its own license, DobeWorks is available under [Apache License 2.0](LICENSE). Use [issues](https://github.com/tmccoy678/DobeWorks/issues) for non-sensitive questions and [SECURITY.md](SECURITY.md) for vulnerability reporting.
