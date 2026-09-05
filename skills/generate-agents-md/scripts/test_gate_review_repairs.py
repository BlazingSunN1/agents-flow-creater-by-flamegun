import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_validate_delivery_contract as support
from delivery_gate_planner import (
    _command_entrypoints, build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
)
from execute_delivery_gate import execute_gate
from validate_delivery_contract import validate_delivery_contract
from validate_project_commands import validate_project_commands


class GateReviewRepairTests(unittest.TestCase):
    def setUp(self):
        self.f = support.DeliveryContractValidatorTests('test_valid_contract_passes')
        self.f.setUp()
        self.root = self.f.root
        self.addCleanup(self.f.tearDown)

    def configure(self, command_id, argv, **extra):
        path = self.root / 'docs/project-commands.json'
        manifest = json.loads(path.read_text())
        entry = next(c for c in manifest['commands'] if c['id'] == command_id)
        text = shlex.join(argv)
        entry.update(argv=argv, source='docs/command.txt', source_selector=text, source_command=text, **extra)
        (self.root / entry['source']).write_text(text)
        path.write_text(json.dumps(manifest))
        self.assertEqual([], validate_project_commands(path, project_root=self.root))
        data = self.f.contract()
        data['change']['risk_level'] = 'high-risk'
        data['gate_plan'] = build_gate_plan(data['change'], stage=data['stage'],
            impact_fingerprint=compute_impact_fingerprint(data, self.root),
            command_fingerprints=compute_command_fingerprints(data, self.root))
        self.f._write_gate_receipts(data)
        self.f.path.write_text(json.dumps(data))
        return data

    def execute(self, command_id):
        rc = execute_gate(self.f.path, command_id, project_root=self.root,
            output_path='docs/run.log', receipt_path='docs/run.json', run_id='review-regression')
        data = json.loads(self.f.path.read_text())
        data['gate_receipts'][command_id] = self.f.ref('docs/run.json')
        self.f.path.write_text(json.dumps(data))
        return rc

    def _assert_buffered_unittest_passes(self, flags):
        (self.root / 'runner.py').write_text('import unittest\n'
            'class T(unittest.TestCase):\n'
            '    def test_ok(self):\n        print("business result: 2")\n'
            '        self.assertEqual(2, 1 + 1)\n'
            'unittest.main()\n')
        self.configure('targeted_tests', ['python3', 'runner.py', *flags])
        self.assertEqual(0, self.execute('targeted_tests'))
        output = (self.root / 'docs/run.log').read_text()
        self.assertIn('OK\nbusiness result: 2\n', output)
        self.assertEqual([], validate_delivery_contract(self.f.path, project_root=self.root))

    def test_buffered_unittest_stdout_default_passes(self):
        self._assert_buffered_unittest_passes([])

    def test_buffered_unittest_stdout_quiet_passes(self):
        self._assert_buffered_unittest_passes(['-q'])

    def test_buffered_unittest_stdout_verbose_passes(self):
        self._assert_buffered_unittest_passes(['-v'])

    def _assert_receipt_cleanup_fails(self, cleanup, *, replacement=False):
        (self.root / 'runner.py').write_text('import unittest, shutil\nfrom pathlib import Path\n'
            'class T(unittest.TestCase):\n'
            f'    def setUp(self):\n        {cleanup}\n'
            '    def test_ok(self): self.assertEqual(2, 1 + 1)\n'
            'unittest.main()\n')
        self.configure('targeted_tests', ['python3', 'runner.py'])
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('execute_delivery_gate.py')),
            str(self.f.path), 'targeted_tests', '--project-root', str(self.root),
            '--output-path', 'logs/run.log', '--receipt-path', 'artifacts/run.json',
            '--run-id', 'cleanup-regression'], capture_output=True, text=True, check=False)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn('ERROR gate-execution', result.stdout)
        self.assertIn('Ran 1 test', (self.root / 'logs/run.log').read_text())
        receipt = self.root / 'artifacts/run.json'
        if replacement:
            self.assertEqual('{}', receipt.read_text())
        else:
            self.assertFalse(receipt.exists())

    def test_json_cleanup_cannot_silently_lose_receipt(self):
        self._assert_receipt_cleanup_fails('[p.unlink() for p in Path("artifacts").glob("*.json")]')

    def test_clean_build_cannot_silently_lose_receipt(self):
        self._assert_receipt_cleanup_fails('shutil.rmtree("artifacts")')

    def test_recreated_report_path_is_not_overwritten_or_accepted(self):
        self._assert_receipt_cleanup_fails('Path("artifacts/run.json").unlink(); '
            'Path("artifacts/run.json").write_text("{}")', replacement=True)

    def test_wrapped_zero_test_full_gate_fails_runner_and_validator(self):
        (self.root / 'runner.py').write_text('import subprocess, sys\n'
            'sys.exit(subprocess.call([sys.executable, "-m", "unittest"]))\n')
        self.configure('full_test_or_build', ['python3', 'runner.py'])
        self.assertNotEqual(0, self.execute('full_test_or_build'))
        receipt_path = self.root / 'docs/run.json'
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual('fail', receipt['verdict'])
        receipt['verdict'] = 'pass'  # Validator must independently reject the zero-test report.
        receipt_path.write_text(json.dumps(receipt))
        data = json.loads(self.f.path.read_text())
        data['gate_receipts']['full_test_or_build'] = self.f.ref('docs/run.json')
        self.f.path.write_text(json.dumps(data))
        self.assertIn('gate-test-result-not-pass', self.f.codes())

    def test_explicit_build_passes_without_test_report(self):
        (self.root / 'build.py').write_text('print("build complete")\n')
        self.configure('full_test_or_build', ['python3', 'build.py', 'pytest'], result_kind='build')
        self.assertEqual(0, self.execute('full_test_or_build'))
        self.assertEqual([], validate_delivery_contract(self.f.path, project_root=self.root))

    def test_build_label_cannot_exempt_a_known_test_invocation(self):
        path = self.root / 'docs/project-commands.json'
        data = json.loads(path.read_text())
        next(c for c in data['commands'] if c['id'] == 'full_test_or_build')['result_kind'] = 'build'
        path.write_text(json.dumps(data))
        self.assertIn('invalid-command-result-kind',
                      {issue.code for issue in validate_project_commands(path, project_root=self.root)})

    def test_build_wrapper_cannot_hide_zero_test_report(self):
        (self.root / 'runner.py').write_text('import subprocess, sys\n'
            'sys.exit(subprocess.call([sys.executable, "-m", "unittest"]))\n')
        self.configure('full_test_or_build', ['python3', 'runner.py'], result_kind='build')
        self.assertNotEqual(0, self.execute('full_test_or_build'))
        self.assertIn('gate-test-result-not-pass', self.f.codes())

    def test_generated_output_does_not_invalidate_gate(self):
        (self.root / 'runner.py').write_text('import sys, unittest\nfrom pathlib import Path\n'
            'Path(sys.argv.pop()).write_text("report")\n'
            'class T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n'
            'unittest.main()\n')
        data = self.configure('targeted_tests', ['python3', 'runner.py', 'docs/report.txt'])
        before = compute_command_fingerprints(data, self.root)
        self.assertEqual(0, self.execute('targeted_tests'))
        self.assertEqual(before, compute_command_fingerprints(data, self.root))
        self.assertEqual([], validate_delivery_contract(self.f.path, project_root=self.root))
        (self.root / 'docs/report.txt').write_text('report changed')
        self.assertEqual(before, compute_command_fingerprints(data, self.root))

    def test_real_unittest_with_browser_argument_passes_runner_and_contract(self):
        (self.root / 'runner.py').write_text('import sys, unittest\n'
            'class T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n'
            'unittest.main(argv=[sys.argv[0]])\n')
        self.configure('targeted_tests', ['python3', 'runner.py', '--adapter', 'playwright'])
        self.assertEqual(0, self.execute('targeted_tests'))
        self.assertEqual([], validate_delivery_contract(self.f.path, project_root=self.root))

    def test_result_kind_cannot_disable_other_test_gates_or_use_unknown_value(self):
        path = self.root / 'docs/project-commands.json'
        original = json.loads(path.read_text())
        for command_id, kind in [('targeted_tests', 'build'), ('full_test_or_build', 'anything'),
                                 ('full_test_or_build', None)]:
            data = json.loads(json.dumps(original))
            next(c for c in data['commands'] if c['id'] == command_id)['result_kind'] = kind
            path.write_text(json.dumps(data))
            self.assertTrue(validate_project_commands(path, project_root=self.root))

    def test_entrypoint_detection_stops_before_output_arguments(self):
        for argv in (['python3', '-B', 'runner.py', '--output', 'report.py'],
                     ['python3', '-W', 'ignore', 'runner.py', '-m', 'report'],
                     ['python3', '--', 'runner.py', 'report.py']):
            self.assertEqual([self.root / 'python3', self.root / 'runner.py'],
                             _command_entrypoints(argv, self.root))
        self.assertEqual([self.root / 'python3', self.root / 'pkg/cli.py',
                          self.root / 'pkg/cli/__main__.py'],
                         _command_entrypoints(['python3', '-m', 'pkg.cli', 'report.py'], self.root))
