# DobeWorks v2.1

![DobeWorks command center running the current DobeWorks and DEGS cores](docs/figures/dobeworks-degs-command-center.png)

I built DobeWorks and DEGS for myself after I became obsessed with AI hallucination capture and immutable context transfer between windows. I believe that the resulting DobeWorks and DEGS that I was using on my MacPro are rigorous and true reflections of the diligence in the references of the work that they were built from.

DobeWorks and DEGS are my private personal engineering system and identity for methodological systems, software, research infrastructure, and special projects. It is not currently a public company identity, service, or commercial offering.

If you would like to discuss DobeWorks or DEGS privately, please email me at: tmccoy678@gmail.com.

Thank you,

Taylor

DobeWorks is a public development snapshot of a personal engineering system. This repository contains two runnable, standard-library Python demonstrations:

- **Observer Core** turns a bounded synthetic snapshot into a minimized status record and makes stale or unavailable evidence explicit.
- **Worker Core** validates a bounded synthetic job and stages its result without accepting or promoting it.

The examples use synthetic fixtures. They do not inspect a device, install a service, grant authority, or qualify a production system.

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

## Tests

The ordinary public tests use only the checkout and Python standard library:

```sh
python3 -B -m unittest discover \
  -s contexts/operational-system/software/phase4 -p 'test_*_core.py' -v
python3 -B -m unittest discover -s benchmarks -p 'test_*.py' -v
```

The current suite contains 70 Worker/Observer tests and six benchmark tests. The benchmark exercises 318 public JSON inputs plus two native controls. These results cover the included synthetic behaviors; they do not prove security, correctness, device support, or production readiness.

Historical package-validator tests are separate. They use pinned Git history, and the Phase 4 set also needs the original external specification through `DOBEWORKS_PHASE4_SPEC`. A normal source archive does not contain that historical artifact. See [historical package tests](docs/historical-package-tests.md).

## Documentation

- [Illustrated system guide](docs/figures/README.md)
- [Benchmark method and results](benchmarks/benchmark.md)
- [DobeWorks Engineering Assurance Standard](docs/standards/deas/v1/standard.md)
- [Citations and source credit](CITATIONS.md)
- [Companion DEGS repository](https://github.com/tmccoy678/DEGS-v2.1)

This is a development snapshot without a versioned release or universal platform-support claim. It was recorded on Apple silicon with macOS 26.6.2 and Python 3.9.6; the standard-library examples are intended to be portable, while other environments remain unverified.

Except for material identified in [third-party notices](THIRD_PARTY_NOTICES.md) and under its own license, this repository is available under the [Apache License 2.0](LICENSE). Use [issues](https://github.com/tmccoy678/DobeWorks-v2.1/issues) for non-sensitive questions and [SECURITY.md](SECURITY.md) for vulnerability reporting.
