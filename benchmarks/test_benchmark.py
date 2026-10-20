"""Command-level tests of the Observer public-data benchmark."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class BenchmarkTests(unittest.TestCase):
    def test_full_corpus_and_native_controls_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            run = subprocess.run([sys.executable, '-B', str(HERE / 'run_benchmark.py'),
                                  '--output', str(output)], capture_output=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report['invocation']['argv'],
                             [str(HERE / 'run_benchmark.py'), '--output', str(output)])
            self.assertEqual(report['invocation']['working_directory'], str(Path.cwd()))
            self.assertEqual(report['invocation']['executable'], sys.executable)
            self.assertTrue(report['invocation']['dont_write_bytecode'])
            self.assertEqual(report['selected'], 318)
            self.assertEqual(report['strata'], {'n': 188, 'y': 95, 'i': 35})
            self.assertEqual(report['passed'], 318)
            self.assertEqual(report['failed'], 0)
            self.assertTrue(report['controls_passed'])
            self.assertEqual(len(report['cases']), 318)
            self.assertEqual(set(report['controls']), {'fresh', 'stale'})
            helper = HERE.parent / 'contexts/operational-system/software/phase4/bounded_input.py'
            self.assertEqual(report['source_sha256'][str(helper.relative_to(HERE.parent))],
                             hashlib.sha256(helper.read_bytes()).hexdigest())


    def test_corpus_drift_is_an_input_error_without_a_score(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(HERE, root / 'benchmarks')
            source = next((root / 'benchmarks/data').glob('*.json'))
            source.write_bytes(source.read_bytes() + b' ')
            output = root / 'benchmarks/results/report.json'
            run = subprocess.run([sys.executable, '-B', str(root / 'benchmarks/run_benchmark.py'),
                                  '--output', str(output)], capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertIn(b'SHA-256 mismatch', run.stderr)
            self.assertFalse(output.exists())

    def test_selection_manifest_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(HERE, root / 'benchmarks')
            manifest = root / 'benchmarks/manifest.json'
            manifest.write_text(manifest.read_text() + ' ')
            run = subprocess.run([sys.executable, '-B', str(root / 'benchmarks/run_benchmark.py'),
                                  '--output', str(root / 'report.json')], capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertIn(b'manifest SHA-256 mismatch', run.stderr)

    def test_input_helper_drift_during_measurement_invalidates_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(HERE, root / 'benchmarks')
            phase = root / 'contexts/operational-system/software/phase4'
            original = HERE.parent / 'contexts/operational-system/software/phase4'
            shutil.copytree(original, phase)
            candidate = phase / 'observer_core.py'
            source = candidate.read_text()
            tree = ast.parse(source)
            insertion = max((node.end_lineno for node in tree.body
                             if isinstance(node, ast.ImportFrom) and node.module == '__future__'), default=0)
            lines = source.splitlines(keepends=True)
            probe = ("import atexit as _ae, pathlib as _p\n"
                     "_h = _p.Path(__file__).with_name('bounded_input.py')\n"
                     "_ae.register(_h.write_bytes, _h.read_bytes() + b'\\n')\n")
            candidate.write_text(''.join(lines[:insertion]) + probe + ''.join(lines[insertion:]))
            output = root / 'report.json'
            run = subprocess.run([sys.executable, '-B', str(root / 'benchmarks/run_benchmark.py'),
                                  '--output', str(output)], capture_output=True, timeout=120)
            self.assertEqual(run.returncode, 2)
            self.assertIn(b'candidate or native inputs changed during measurement', run.stderr)
            self.assertFalse(output.exists())

    def test_degenerate_and_broken_candidates_cannot_earn_success(self):
        candidates = [("import json\nprint(json.dumps({'status':'ERROR','code':'ALWAYS_REJECT','message':'test control'}))\nraise SystemExit(2)\n", 318, 0, False), ("print('not JSON')\n", 0, 318, False)]
        for source, passed, failed, controls_passed in candidates:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(HERE, root / 'benchmarks')
                candidate = root / 'contexts/operational-system/software/phase4/observer_core.py'
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(source)
                shutil.copyfile(HERE.parent / 'contexts/operational-system/software/phase4/bounded_input.py',
                                candidate.parent / 'bounded_input.py')
                shutil.copytree(HERE.parent / 'contexts/operational-system/software/phase4/fixtures', candidate.parent / 'fixtures')
                output = root / 'benchmarks/results/report.json'
                run = subprocess.run([sys.executable, '-B', str(root / 'benchmarks/run_benchmark.py'),
                                      '--output', str(output)], capture_output=True, timeout=120)
                self.assertEqual(run.returncode, 1, run.stderr)
                report = json.loads(output.read_text())
                self.assertEqual(report['passed'], passed)
                self.assertEqual(report['failed'], failed)
                self.assertEqual(report['controls_passed'], controls_passed)

    def test_one_timeout_remains_a_failed_case_in_the_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(HERE, root / 'benchmarks')
            candidate = root / 'contexts/operational-system/software/phase4/observer_core.py'
            candidate.parent.mkdir(parents=True, exist_ok=True)
            original = HERE.parent / 'contexts/operational-system/software/phase4/observer_core.py'
            source = original.read_text()
            tree = ast.parse(source)
            insertion = max((node.end_lineno for node in tree.body
                             if isinstance(node, ast.ImportFrom) and node.module == '__future__'), default=0)
            lines = source.splitlines(keepends=True)
            probe = ("import pathlib, time, sys\n"
                     "_counter = pathlib.Path(__file__).with_name('test-process-count')\n"
                     "_count = int(_counter.read_text()) if _counter.exists() else 0\n"
                     "_counter.write_text(str(_count + 1))\n"
                     "if _count == 2:\n"
                     "    print('partial stdout', flush=True)\n"
                     "    print('partial stderr', file=sys.stderr, flush=True)\n"
                     "    time.sleep(6)\n")
            candidate.write_text(''.join(lines[:insertion]) + probe + ''.join(lines[insertion:]))
            shutil.copyfile(original.with_name('bounded_input.py'), candidate.parent / 'bounded_input.py')
            shutil.copytree(original.parent / 'fixtures', candidate.parent / 'fixtures')
            output = root / 'benchmarks/results/report.json'
            run = subprocess.run([sys.executable, '-B', str(root / 'benchmarks/run_benchmark.py'),
                                  '--output', str(output)], capture_output=True, timeout=120)
            self.assertEqual(run.returncode, 1, run.stderr)
            report = json.loads(output.read_text())
            timed_out = [c for c in report['cases'] if c['execution'] == 'timeout']
            self.assertEqual(len(timed_out), 1)
            self.assertFalse(timed_out[0]['passed'])
            self.assertEqual(timed_out[0]['stdout'], 'partial stdout\n')
            self.assertEqual(timed_out[0]['stderr'], 'partial stderr\n')
            self.assertEqual(report['passed'] + report['failed'], report['selected'])
            self.assertTrue(report['controls_passed'])

    def test_contradictory_stale_freshness_invalidates_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(HERE, root / 'benchmarks')
            original = HERE.parent / 'contexts/operational-system/software/phase4/observer_core.py'
            candidate = root / original.relative_to(HERE.parent)
            candidate.parent.mkdir(parents=True)
            shutil.copyfile(original.with_name('bounded_input.py'), candidate.parent / 'bounded_input.py')
            # Wrap the real CLI and change only the reported stale freshness.
            candidate.write_text(
                "import json, subprocess, sys\n"
                f"result = subprocess.run([sys.executable, '-B', {str(original)!r}] + sys.argv[1:], capture_output=True)\n"
                "value = json.loads(result.stdout)\n"
                "if value.get('freshness') == 'STALE': value['freshness'] = 'FRESH'\n"
                "print(json.dumps(value))\n"
                "sys.stderr.buffer.write(result.stderr)\n"
                "raise SystemExit(result.returncode)\n")
            shutil.copytree(original.parent / 'fixtures', candidate.parent / 'fixtures')
            output = root / 'benchmarks/results/report.json'
            run = subprocess.run([sys.executable, '-B', str(root / 'benchmarks/run_benchmark.py'),
                                  '--output', str(output)], capture_output=True, timeout=120)
            report = json.loads(output.read_text())
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(report['passed'], 318)
            self.assertTrue(report['controls']['fresh']['passed'])
            self.assertEqual(report['controls']['stale']['result']['freshness'], 'FRESH')
            self.assertFalse(report['controls']['stale']['passed'])
            self.assertFalse(report['controls_passed'])

if __name__ == '__main__':
    unittest.main()
