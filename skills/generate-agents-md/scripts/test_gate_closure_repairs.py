from __future__ import annotations

import hashlib
import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_delivery_gate import execute_gate
from delivery_gate_planner import compute_command_fingerprints
import test_validate_delivery_contract as contract_support
import test_validate_frontend_evidence as frontend_support


class GateClosureRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = contract_support.DeliveryContractValidatorTests('test_valid_contract_passes')
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def run_gate(self, output='docs/new-output.txt', receipt='docs/new-receipt.json'):
        return execute_gate(self.fixture.path, 'targeted_tests', project_root=self.root,
                            output_path=output, receipt_path=receipt, run_id='repair-test')

    def test_gate_cannot_overwrite_contract_or_existing_receipt(self):
        before = self.fixture.path.read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.run_gate(output='docs/delivery-contract.json')
        self.assertEqual(before, self.fixture.path.read_bytes())
        receipt = self.root / 'docs/existing.json'
        receipt.write_text('existing evidence')
        with self.assertRaises((ValueError, OSError)):
            self.run_gate(receipt='docs/existing.json')
        self.assertEqual('existing evidence', receipt.read_text())
        self.assertFalse((self.root / 'docs/new-output.txt').exists())

    def test_zero_tests_must_not_create_passing_receipt(self):
        self.assertNotEqual(0, self.run_gate())
        receipt = json.loads((self.root / 'docs/new-receipt.json').read_text())
        self.assertEqual('fail', receipt['verdict'])

    def test_concurrent_runs_cannot_share_output_pair(self):
        (self.root / 'test_success.py').write_text(
            'import unittest\nclass TestSuccess(unittest.TestCase):\n'
            '    def test_success(self): self.assertEqual(2, 1 + 1)\n')
        def attempt():
            try:
                return self.run_gate()
            except (ValueError, OSError):
                return 'collision'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual([0, 'collision'], results)

    def test_script_content_changes_command_fingerprint(self):
        script = self.root / 'gate.py'
        script.write_text('print("checks")\n')
        path = self.root / 'docs/project-commands.json'
        manifest = json.loads(path.read_text())
        manifest['commands'][0]['argv'] = ['python3', 'gate.py']
        path.write_text(json.dumps(manifest))
        contract = json.loads(self.fixture.path.read_text())
        before = compute_command_fingerprints(contract, self.root)
        script.write_text('raise RuntimeError("broken runner")\n')
        after = compute_command_fingerprints(contract, self.root)
        self.assertNotEqual(before, after)

    def test_failed_tests_preserve_output_and_fail_receipt(self):
        (self.root / 'test_failure.py').write_text(
            'import unittest\nclass TestFailure(unittest.TestCase):\n'
            '    def test_failure(self): self.fail("expected failure")\n')
        self.assertNotEqual(0, self.run_gate())
        self.assertIn('expected failure', (self.root / 'docs/new-output.txt').read_text())
        receipt = json.loads((self.root / 'docs/new-receipt.json').read_text())
        self.assertEqual('fail', receipt['verdict'])
        self.assertNotEqual(0, receipt['exit_code'])

    def test_interrupted_run_cannot_leave_passing_receipt_or_be_overwritten(self):
        with patch('execute_delivery_gate.subprocess.run', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_gate()
        self.assertEqual(b'', (self.root / 'docs/new-receipt.json').read_bytes())
        with self.assertRaises((ValueError, OSError)):
            self.run_gate()

    def test_repeated_run_preserves_bytes_and_fresh_paths_allow_retry(self):
        self.run_gate()  # Empty discovery produces a failed, immutable attempt.
        receipt = (self.root / 'docs/new-receipt.json').read_bytes()
        with self.assertRaises((ValueError, OSError)):
            self.run_gate()
        self.assertEqual(receipt, (self.root / 'docs/new-receipt.json').read_bytes())
        self.assertNotEqual(0, self.run_gate('docs/retry.txt', 'docs/retry.json'))

    def test_zero_test_output_is_rejected_by_contract_validator(self):
        data = json.loads(self.fixture.path.read_text())
        ref = data['gate_receipts']['targeted_tests']
        path = self.root / ref['path']
        receipt = json.loads(path.read_text())
        output = self.root / receipt['output_path']
        output.write_text('Ran 0 tests in 0.000s\n\nOK\n')
        receipt['output_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
        path.write_text(json.dumps(receipt))
        ref.update(self.fixture.ref(ref['path']))
        self.fixture.path.write_text(json.dumps(data))
        self.assertIn('gate-test-result-not-pass', self.fixture.codes())


class CypressPendingRepairTests(unittest.TestCase):
    def test_pending_acceptance_fails_complete_frontend_validation(self):
        fixture = frontend_support.FrontendEvidenceValidatorTests()
        fixture.setUp()
        try:
            fixture._use_cypress_command()
            passed, pending = {'fullTitle': 'works'}, {'fullTitle': 'acceptance skipped'}
            fixture.report.write_text(json.dumps({
                'stats': {'tests': 2, 'passes': 1, 'pending': 1, 'failures': 0},
                'tests': [passed, pending], 'pending': [pending], 'passes': [passed], 'failures': [],
            }))
            data = fixture._evidence()
            data['e2e'].update(framework='Cypress', passed=1,
                command_argv_sha256=hashlib.sha256(b'npx\0cypress\0run').hexdigest(),
                report_sha256=hashlib.sha256(fixture.report.read_bytes()).hexdigest())
            fixture.path.write_text(json.dumps(data))
            self.assertIn('e2e-report-mismatch', fixture.codes())
        finally:
            fixture.tearDown()
