# DobeWorks v3.0

![DobeWorks command center running the current DobeWorks and DEGS cores](docs/figures/dobeworks-degs-command-center.png)

This repository contains two runnable, standard-library Python demonstrations:

- **Observer Core** turns a bounded synthetic snapshot into a minimized status record and makes stale or unavailable evidence explicit.
- **Worker Core** validates a bounded synthetic job and stages its result without accepting or promoting it.

The examples use synthetic fixtures. They do not inspect a device, install a service, grant authority, or qualify a production system.

I will briefly introduce Dobeworks and DEGS. First, DobeWorks and DEGS were originally intended for personal-use after I became quite obsessed with LLM hallucinations and developing a way to perform auditable context transfer between windows for Codex and OpenAI models in August, 2026. 

I am aware that it is impossible to eliminate errors. It follows then that DobeWorks and DEGS do not try to fix errors; and one strength of the systems is their ability to prevent errors from moving forward into the next ticket or part of the work. 

DobeWorks and DEGS are my personal engineering system for methodological systems, software, research infrastructure, and special projects.

If you would like to discuss DobeWorks and/or DEGS privately, please email me at: tmccoy678@gmail.com.

Thank you,

Taylor

## Quick start

Python 3.9 or later is required. No package installation is needed.

```sh
git clone https://github.com/tmccoy678/DobeWorks-v2.1.git
cd DobeWorks-v2.1
```

Run the Observer against the included fresh fixture:

```sh
python3 -B contexts/operational-system/software/phase4/observer_core.py \
  --snapshot contexts/operational-system/software/phase4/fixtures/observer-snapshot.json \
  --policy contexts/operational-system/software/phase4/fixtures/observer-policy.json \
  --allowed-input-root contexts/operational-system/software/phase4/fixtures \
  --now 2026-09-06T00:01:00Z
```

The result has `status: VALIDATED` and `freshness: FRESH`. Change `--now` to `2026-09-07T00:01:00Z` to see stale evidence become `TELEMETRY_UNAVAILABLE` with unknown signals.

Run one Worker job in a disposable directory:

```sh
demo_stage=$(mktemp -d)
python3 -B contexts/operational-system/software/phase4/worker_core.py \
  --envelope contexts/operational-system/software/phase4/fixtures/job-envelope.json \
  --input contexts/operational-system/software/phase4/fixtures/input-records.json \
  --staging-root "$demo_stage" \
  --allowed-input-root contexts/operational-system/software/phase4/fixtures \
  --configuration-sha256 ba0e803fc49b7a78989a44c9c9beb9789e37980b7ce92654a89d3f364460873d \
  --now 2026-09-06T00:01:00Z
```

The expected state is `COMPLETED_UNACCEPTED`. Inspect the staged files, then remove the disposable directory when finished. The [software-core guide](contexts/operational-system/software/phase4/README.md) explains the checks and limits.

## Shared interface

The optional [shared terminal interface](interface/README.md) brings DobeWorks and DEGS into one menu with the blue display, quoted voices, and result screens shown above. From this checkout, place the DEGS clone alongside it and launch:

```sh
git clone https://github.com/tmccoy678/DEGS-v2.1.git ../DEGS-v2.1
python3 -B interface/command_center.py menu
```

On macOS, run `zsh DobeWorks.command` for the Courier window settings; the [setup guide](interface/README.md) also explains Finder double-click setup and `--degs-root` for an existing DEGS checkout. The interface calls the existing core CLIs and writes local evidence under ignored `interface/Runs/`. Its integration result checks the synthetic adapter mapping; it grants no acceptance, promotion, or execution authority.

## Tests

The ordinary public tests use only the checkout and Python standard library:

```sh
python3 -B -m unittest discover \
  -s contexts/operational-system/software/phase4 -p 'test_*_core.py' -v
python3 -B -m unittest discover -s benchmarks -p 'test_*.py' -v
```

The shared interface has a separate focused suite: `python3 -B -m unittest discover -s interface -p 'test_*.py' -v`.

The current suite contains 84 Worker/Observer tests and seven benchmark tests. The [recorded v3 Observer benchmark](benchmarks/results/apple-silicon-v3.json) records passing outcomes for 318 public JSON inputs and two native controls. It predates the [decoder refinement and its verification](https://github.com/tmccoy678/DobeWorks-v2.1/pull/8), which preserves the active Python integer limit and returns structured errors for decoding failures. The [boundary-fix and verification record](docs/reviews/2026-10-20-boundary-fixes.md) gives the earlier correction scope, commands, and test evidence. These results cover the included synthetic behaviors; they do not prove security, correctness, device support, or production readiness.

Historical package-validator tests are separate. They use pinned Git history, and the Phase 4 set also needs the original external specification through `DOBEWORKS_PHASE4_SPEC`. A normal source archive does not contain that historical artifact. See [historical package tests](docs/historical-package-tests.md).

## Documentation

- [Illustrated system guide](docs/figures/README.md)
- [Benchmark method and results](benchmarks/benchmark.md)
- [DobeWorks Engineering Assurance Standard](docs/standards/deas/v1/standard.md)
- [Citations and source credit](CITATIONS.md)
- [Companion DEGS repository](https://github.com/tmccoy678/DEGS-v2.1)

This is a development snapshot without a versioned release or universal platform-support claim. Current tests were verified on arm64 macOS 27.0.1 with Python 3.9.6 and 3.14.7; the recorded v3 benchmark uses Python 3.14.7. Earlier results retain their historical source identities and environments. Other environments remain unverified.

Except for material identified in [third-party notices](THIRD_PARTY_NOTICES.md) and under its own license, this repository is available under the [Apache License 2.0](LICENSE). Use [issues](https://github.com/tmccoy678/DobeWorks-v2.1/issues) for non-sensitive questions and [SECURITY.md](SECURITY.md) for vulnerability reporting.
