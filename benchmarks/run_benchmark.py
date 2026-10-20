#!/usr/bin/env python3
"""Measure Observer application rejection on the pinned JSONTestSuite corpus."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PHASE = ROOT / 'contexts/operational-system/software/phase4'
CANDIDATE = PHASE / 'observer_core.py'
MANIFEST_SHA256 = '9e56f3f2d87fe307a8bbbdfe27256a327a930322075d1dae5c456464b8203ccd'
TIMEOUT_SECONDS = 5
FRESH = '2026-09-06T00:01:00Z'
STALE = '2026-09-07T00:01:00Z'
SIGNALS = {'backup_restore_age_days': 4, 'bounded_resource_percent': 42,
           'configuration_generation': 'phase4-synthetic-config-v1', 'job_state': 'IDLE',
           'role_freshness': 'CURRENT', 'storage_presence': 'PRESENT'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_manifest():
    if digest(HERE / 'manifest.json') != MANIFEST_SHA256:
        raise ValueError('manifest SHA-256 mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_text())
    actual = {p.name: digest(p) for p in (HERE / 'data').iterdir() if p.is_file()}
    if actual != manifest['files']:
        raise ValueError('corpus file inventory or SHA-256 mismatch')
    files = sorted((HERE / 'data').glob('*.json'))
    if len(files) != 318 or any(b'dobeworks.observer-snapshot.v1' in p.read_bytes() for p in files):
        raise ValueError('corpus no longer matches the out-of-contract inventory')
    return manifest, files


def invoke(snapshot, directory, now):
    command = [sys.executable, '-B', str(CANDIDATE), '--snapshot', str(snapshot),
               '--policy', str(directory / 'policy.json'), '--allowed-input-root',
               str(directory), '--now', now]
    try:
        result = subprocess.run(command, capture_output=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        return {'execution': 'timeout', 'exit_code': None,
                'stdout': (error.stdout or b'').decode('utf-8', errors='replace'),
                'stderr': (error.stderr or b'').decode('utf-8', errors='replace')}
    record = {'execution': 'error', 'exit_code': result.returncode,
              'stdout': result.stdout.decode('utf-8', errors='replace'),
              'stderr': result.stderr.decode('utf-8', errors='replace')}
    if result.stderr:
        return record
    try:
        parsed = json.loads(result.stdout)
        if not isinstance(parsed, dict):
            return record
    except (ValueError, UnicodeError):
        return record
    record.update(execution='completed', result=parsed)
    return record


def record_shape(value):
    keys = {'decision_map', 'freshness', 'limitations', 'observed_at', 'provenance',
            'role_id', 'schema_version', 'self_health', 'signals', 'status'}
    return (set(value) == keys and value['schema_version'] == 'dobeworks.observer-record.v1'
            and isinstance(value['self_health'], dict)
            and isinstance(value['signals'], dict) and set(value['signals']) == set(SIGNALS))


def unavailable(record, status, reason):
    value = record.get('result', {})
    return (record['execution'] == 'completed' and record['exit_code'] == 0
            and record_shape(value) and value['status'] == status
            and value['self_health'].get('failure_status') == reason
            and all(v == 'UNKNOWN' for v in value['signals'].values()))


def rejected(record):
    value = record.get('result', {})
    error = (record['execution'] == 'completed' and record['exit_code'] == 2
             and set(value) == {'code', 'message', 'status'} and value['status'] == 'ERROR'
             and isinstance(value['code'], str) and bool(value['code'])
             and isinstance(value['message'], str))
    return error or unavailable(record, 'UNKNOWN', 'SCHEMA_INCOMPATIBLE')


def controls(directory):
    snapshot = directory / 'control.json'
    shutil.copyfile(PHASE / 'fixtures/observer-snapshot.json', snapshot)
    fresh, stale = invoke(snapshot, directory, FRESH), invoke(snapshot, directory, STALE)
    value = fresh.get('result', {})
    fresh['passed'] = (fresh['execution'] == 'completed' and fresh['exit_code'] == 0
                       and record_shape(value) and value['status'] == 'VALIDATED'
                       and value['freshness'] == 'FRESH' and value['signals'] == SIGNALS
                       and value['self_health'].get('failure_status') == 'NONE')
    stale['passed'] = (unavailable(stale, 'TELEMETRY_UNAVAILABLE', 'STALE_DATA')
                       and stale['result']['freshness'] == 'STALE')
    return {'fresh': fresh, 'stale': stale}


def measure(files):
    cases = []
    with tempfile.TemporaryDirectory(prefix='dw-public-benchmark-') as temporary:
        directory = Path(temporary)
        shutil.copyfile(PHASE / 'fixtures/observer-policy.json', directory / 'policy.json')
        native = controls(directory)
        for source in files:
            snapshot = directory / 'input.json'
            shutil.copyfile(source, snapshot)
            if digest(snapshot) != digest(source):
                raise ValueError('raw input copy digest mismatch')
            result = invoke(snapshot, directory, FRESH)
            result.update(id=source.name, stratum=source.name[0], sha256=digest(source),
                          passed=rejected(result))
            cases.append(result)
    return cases, native


def report_run(manifest, files):
    started = datetime.now(timezone.utc).isoformat()
    inputs = [CANDIDATE, PHASE / 'bounded_input.py', PHASE / 'fixtures/observer-snapshot.json',
              PHASE / 'fixtures/observer-policy.json']
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    cases, native = measure(files)
    if hashes != {str(p.relative_to(ROOT)): digest(p) for p in inputs}:
        raise ValueError('candidate or native inputs changed during measurement')
    return {'benchmark': 'dobeworks-observer-rejection-v1', 'started_at': started,
            'ended_at': datetime.now(timezone.utc).isoformat(),
            'python': platform.python_version(), 'macos': platform.mac_ver()[0],
            'architecture': platform.machine(), 'timeout_seconds_per_case': TIMEOUT_SECONDS,
            'invocation': {'executable': sys.executable, 'argv': sys.argv[:],
                           'working_directory': str(Path.cwd()),
                           'dont_write_bytecode': sys.dont_write_bytecode,
                           'interpreter_flags': str(sys.flags),
                           'original_argv': getattr(sys, 'orig_argv', None),
                           'note': 'argv records script arguments exactly; original interpreter argv is unavailable on Python 3.9'},
            'source_sha256': hashes, 'harness_sha256': digest(Path(__file__)),
            'manifest_sha256': digest(HERE / 'manifest.json'), 'upstream_commit': manifest['commit'],
            'selected': len(cases), 'strata': dict(Counter(c['stratum'] for c in cases)),
            'controls': native, 'controls_passed': all(c['passed'] for c in native.values()),
            'passed': sum(c['passed'] for c in cases), 'failed': sum(not c['passed'] for c in cases),
            'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest, files = checked_manifest()
        report = report_run(manifest, files)
        checked_manifest()
        output = args.output.resolve()
        if ROOT in output.parents and HERE / 'results' not in output.parents:
            raise ValueError('repository output must be inside benchmarks/results')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n')
        print(json.dumps({k: report[k] for k in ('selected', 'passed', 'failed', 'controls_passed')}))
        return int(report['failed'] != 0 or not report['controls_passed'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'ERROR', 'message': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
