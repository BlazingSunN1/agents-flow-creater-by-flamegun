import json
import hashlib
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_validate_delivery_contract as support
import test_validate_context_manifest as context_support
from delivery_gate_planner import (
    GatePlanError, _command_entrypoints, build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
)
from validate_context_manifest import _parse_metadata, _validate_fingerprints, _cache_key
from delivery_contract_bundle_validation import _change_issues
from validate_swimlane_evidence import _validate_diagrams
from execute_delivery_gate import execute_gate
from gate_test_results import test_result_passes
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

    def test_cypress_pending_and_total_stats_must_match_executed_results(self):
        for stats, valid in [({'passes': 1, 'failures': 0}, True),
                             ({'passes': 1, 'failures': 0, 'pending': 0, 'tests': 1}, True),
                             ({'passes': 1, 'failures': 0, 'pending': 1, 'tests': 2}, False),
                             ({'passes': 1, 'failures': 0, 'tests': 2}, False),
                             ({'passes': 1, 'failures': 0, 'pending': '0'}, False)]:
            with self.subTest(stats=stats):
                payload = json.dumps({'stats': stats, 'results': [{'title': 'works', 'state': 'passed'}]})
                self.assertEqual(valid, test_result_passes('targeted_tests', ['python3', 'adapter.py'], payload.encode()))

    def test_cypress_inconsistent_adapter_fails_runner_and_validator(self):
        report = {'stats': {'passes': 1, 'failures': 0, 'pending': 1, 'tests': 2},
                  'results': [{'title': 'works', 'state': 'passed'}]}
        (self.root / 'adapter.py').write_text(f'print({json.dumps(report)!r})\n')
        self.configure('targeted_tests', ['python3', 'adapter.py'])
        self.assertNotEqual(0, self.execute('targeted_tests'))
        self.assertIn('gate-test-result-not-pass', self.f.codes())

    def test_stage_transition_reuses_business_receipts_but_rechecks_stage_semantics(self):
        for risk in ('standard', 'high-risk'):
            with self.subTest(risk=risk):
                data = self.f.contract()
                data['change']['risk_level'] = risk
                old_impact = compute_impact_fingerprint(data, self.root)
                old = build_gate_plan(data['change'], stage=data['stage'], impact_fingerprint=old_impact)
                data['stage'], data['status'] = 'completion', 'completed'
                data['change']['delivery_phase'] = 'completed'
                new_impact = compute_impact_fingerprint(data, self.root)
                new = build_gate_plan(data['change'], stage=data['stage'], impact_fingerprint=new_impact)
                self.assertEqual(old_impact, new_impact)
                for command in ('real_entry_acceptance', 'targeted_tests', 'code_standards', 'automated_review'):
                    self.assertEqual(old['gate_input_fingerprints'][command], new['gate_input_fingerprints'][command])
                for command in ('traceability', 'multi_agent_evidence'):
                    self.assertNotEqual(old['gate_input_fingerprints'][command], new['gate_input_fingerprints'][command])
                self.assertIn('delivery_bundle', new['aggregate_command_ids'])
                if risk == 'high-risk':
                    self.assertNotIn('BLACK_BOX', old['independent_roles'])
                    self.assertIn('BLACK_BOX', new['independent_roles'])

    def test_deleted_file_and_rename_are_bound_to_contract(self):
        data = self.f.contract()
        (self.root / 'src/module.py').unlink()
        data['change']['deleted_files'] = ['src/module.py']
        for renamed in (False, True):
            with self.subTest(renamed=renamed):
                if renamed:
                    (self.root / 'src/new.py').write_text('renamed')
                    data['change']['changed_files'].append('src/new.py')
                impact = compute_impact_fingerprint(data, self.root)
                data['gate_plan'] = build_gate_plan(data['change'], stage=data['stage'], impact_fingerprint=impact,
                    command_fingerprints=compute_command_fingerprints(data, self.root))
                self.f._write_gate_receipts(data)
                self.f.path.write_text(json.dumps(data))
                self.assertEqual([], validate_delivery_contract(self.f.path, project_root=self.root))
        (self.root / 'src/module.py').write_text('restored')
        self.assertTrue(validate_delivery_contract(self.f.path, project_root=self.root))
        with self.assertRaises(GatePlanError):
            compute_impact_fingerprint(data, self.root)

    def test_deleted_files_context_fingerprint_and_module_ownership(self):
        fixture = context_support.ContextManifestValidatorTests('test_valid_manifest_passes')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        metadata, _ = _parse_metadata(fixture.path.read_text())
        (fixture.root / 'src/module.py').unlink()
        metadata['Deleted files'] = 'src/module.py'
        metadata['Code fingerprint'] = hashlib.sha256(b'src/module.py\0deleted').hexdigest()
        metadata['Evidence cache key'] = _cache_key(metadata)
        issues = []
        _validate_fingerprints(metadata, fixture.root.resolve(), issues)
        self.assertEqual([], issues)
        metadata['Modules'] = 'module, other'
        metadata['Module changed files'] = 'module=src/module.py;other=src/module.py'
        issues = []
        _validate_fingerprints(metadata, fixture.root.resolve(), issues)
        self.assertIn('ambiguous-module-changed-file', {i.code for i in issues})

    def test_bundle_deleted_files_must_match_context(self):
        context = {'Requirement IDs': 'REQ-001', 'Modules': 'module', 'Changed files': 'src/module.py',
                   'Configuration files': '', 'Input files': '', 'Deleted files': 'src/module.py',
                   'Direct dependency boundaries': 'direct callers and tests'}
        trace = {'Risk level': 'standard', 'Risk reason': 'observable behavior changed',
                 'Change surfaces': 'behavior-change'}
        data = self.f.contract()
        self.assertTrue(_change_issues(data, trace, context, {'frontend_applicable': False}, self.f.path))
        data['change']['deleted_files'] = ['src/module.py']
        self.assertEqual([], _change_issues(data, trace, context, {'frontend_applicable': False}, self.f.path))

    def test_deleted_paths_reject_missing_declarations_aliases_duplicates_and_live_inputs(self):
        data = self.f.contract()
        (self.root / 'src/module.py').unlink()
        for paths in (None, ['src/module.py', 'src/module.py'], ['src/../src/module.py'],
                      ['./src/module.py'], ['src//module.py'], ['/tmp/missing'], ['src/other.py']):
            with self.subTest(paths=paths):
                if paths is None:
                    data['change'].pop('deleted_files', None)
                else:
                    data['change']['deleted_files'] = paths
                with self.assertRaises(GatePlanError):
                    compute_impact_fingerprint(data, self.root)
        data['change']['deleted_files'] = ['src/module.py']
        for field in ('configuration_files', 'input_files'):
            data['change'][field] = ['src/module.py']
            with self.assertRaises(GatePlanError):
                compute_impact_fingerprint(data, self.root)
            data['change'][field] = []
        (self.root / 'alias').symlink_to(self.root / 'src', target_is_directory=True)
        data['change'].update(changed_files=['alias/module.py'], deleted_files=['alias/module.py'])
        with self.assertRaises(GatePlanError):
            compute_impact_fingerprint(data, self.root)
        (self.root / 'src/link.py').symlink_to(self.root / 'missing.py')
        data['change'].update(changed_files=['src/link.py'], deleted_files=['src/link.py'])
        with self.assertRaises(GatePlanError):
            compute_impact_fingerprint(data, self.root)

    def test_deleted_configuration_and_rename_new_side_content_invalidate(self):
        data = self.f.contract()
        data['change'].update(changed_files=['settings.json', 'src/module.py'], deleted_files=['settings.json'])
        before = compute_impact_fingerprint(data, self.root)
        (self.root / 'src/module.py').write_text('new side changed')
        self.assertNotEqual(before, compute_impact_fingerprint(data, self.root))
        (self.root / 'settings.json').write_text('{}')
        with self.assertRaises(GatePlanError):
            compute_impact_fingerprint(data, self.root)

    def test_deleted_root_and_malformed_live_lists_fail_as_plan_errors(self):
        data = self.f.contract()
        data['change'].update(changed_files=['.'], deleted_files=['.'])
        with self.assertRaises(GatePlanError):
            compute_impact_fingerprint(data, self.root)
        for field in ('changed_files', 'configuration_files', 'input_files'):
            with self.subTest(field=field):
                data = self.f.contract()
                data['change'][field] = None
                with self.assertRaises(GatePlanError):
                    compute_impact_fingerprint(data, self.root)

    def test_swimlane_code_evidence_keeps_deleted_workset_identity(self):
        from test_validate_swimlane_evidence import HTML
        (self.root / 'src/module.py').unlink()
        diagrams = []
        for module in ('system', 'module'):
            (self.root / f'docs/{module}.html').write_text(HTML)
            diagrams.append({'module': module, 'path': f'docs/{module}.html',
                             'sha256': self.f.ref(f'docs/{module}.html')['sha256'],
                             'code_evidence': ['src/module.py']})
        context = {'Changed files': 'src/module.py', 'Deleted files': 'src/module.py',
                   'Module changed files': 'module=src/module.py'}
        issues = []
        _validate_diagrams(diagrams, {'module'}, context, self.root, issues)
        self.assertEqual([], issues)
        (self.root / 'src/module.py').write_text('restored')
        issues = []
        _validate_diagrams(diagrams, {'module'}, context, self.root, issues)
        self.assertTrue(issues)

    def test_agent_context_and_inputs_preserve_explicit_deletion(self):
        from validate_multi_agent_evidence import _agent_context, _allowed_role_inputs
        from multi_agent_input_validation import _valid_input_artifacts
        (self.root / 'src/module.py').unlink()
        path = self.root / 'docs/deletion-context.md'
        path.write_text('- Changed files: src/module.py\n- Deleted files: src/module.py\n')
        issues = []
        context, identities = _agent_context(path, self.root, issues)
        self.assertEqual([], issues)
        self.assertEqual(set(), identities)
        self.assertIn('src/module.py', _allowed_role_inputs({}, context)['CHANGE_REVIEW'])
        artifacts = [{'path': 'src/module.py', 'state': 'deleted'}]
        self.assertTrue(_valid_input_artifacts(artifacts, {'src/module.py'}, self.root,
                                              deleted_paths={'src/module.py'}))
        self.assertFalse(_valid_input_artifacts(artifacts, {'src/module.py'}, self.root))
        for invalid in ([{**artifacts[0], 'sha256': '0' * 64}], artifacts * 2,
                        [{'path': [], 'state': 'deleted'}], [],
                        [{'path': 'src/module.py', 'state': 'missing'}]):
            self.assertFalse(_valid_input_artifacts(invalid, {'src/module.py'}, self.root,
                                                   deleted_paths={'src/module.py'}))
        (self.root / 'src/module.py').write_text('restored')
        self.assertFalse(_valid_input_artifacts(artifacts, {'src/module.py'}, self.root,
                                               deleted_paths={'src/module.py'}))
        issues = []
        _agent_context(path, self.root, issues)
        self.assertTrue(issues)

    def test_deleted_trace_code_requires_explicit_context(self):
        from test_validate_traceability import TraceabilityValidatorTests
        from validate_traceability import validate_traceability
        f = TraceabilityValidatorTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        (f.root / 'src/module.py').unlink()
        context = f.root / 'deleted-context.md'
        context.write_text('- Changed files: src/module.py\n- Deleted files: src/module.py\n')
        self.assertTrue(validate_traceability(f.matrix, project_root=f.root))
        self.assertEqual([], validate_traceability(f.matrix, project_root=f.root, context_path=context))
        original = f.matrix.read_text()
        for old, new in (('[MOD-001](src/module.py)', '[MOD-001](src/)'),
                         ('[MOD-001](src/module.py)', '[MOD-001](src/missing.py)'),
                         ('[UT-001](tests/unit.md)', '[UT-001](src/module.py)')):
            f.matrix.write_text(original.replace(old, new))
            self.assertTrue(validate_traceability(f.matrix, project_root=f.root, context_path=context))
        f.matrix.write_text(original)
        (f.root / 'src/module.py').write_text('restored')
        self.assertTrue(validate_traceability(f.matrix, project_root=f.root, context_path=context))

    def test_review_alias_check_accepts_only_declared_absence(self):
        from delivery_record_validation import _aliases_changed_file
        (self.root / 'src/module.py').unlink()
        evidence = self.root / 'docs/review.txt'
        evidence.write_text('review')
        self.assertTrue(_aliases_changed_file(evidence, 'src/module.py', self.root))
        self.assertFalse(_aliases_changed_file(evidence, 'src/module.py', self.root,
                                               deleted_files={'src/module.py'}))
        import os
        os.link(evidence, self.root / 'src/module.py')
        self.assertTrue(_aliases_changed_file(evidence, 'src/module.py', self.root))
        self.assertTrue(_aliases_changed_file(evidence, 'src/module.py', self.root,
                                              deleted_files={'src/module.py'}))

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
