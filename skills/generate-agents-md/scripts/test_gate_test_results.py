import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_test_results import test_result_passes
from test_gate_output_support import passing_output


class GateTestResultsTests(unittest.TestCase):
    def test_unittest_status_is_bound_to_summary_not_final_stdout_line(self):
        argv = ['python3', '-m', 'unittest']
        good = passing_output(argv)
        self.assertTrue(test_result_passes('targeted_tests', argv,
            (good + 'business result: 2\n').encode()))
        for report in (good.replace('1 test', '0 tests'),
                       good.replace('OK', 'OK (skipped=1)'),
                       good.replace('OK', 'OK (expected failures=1)'),
                       good.replace('OK', 'FAILED (failures=1)'),
                       good.replace('OK', 'FAILED (unexpected successes=1)'),
                       good.replace('\n\nOK', '\n\n'), good + good,
                       good + good.replace('OK', 'FAILED (errors=1)')):
            with self.subTest(report=report):
                self.assertFalse(test_result_passes('targeted_tests', argv,
                    (report + 'business result: 2\nOK\n').encode()))

    def test_unittest_report_requires_nonzero_all_passed(self):
        argv = ['python3', '-m', 'unittest']
        good = passing_output(argv)
        self.assertTrue(test_result_passes('targeted_tests', argv, good.encode()))
        for text in (good.replace('1 test', '0 tests'), good.replace('OK', 'OK (skipped=1)'),
                     good.replace('OK', 'FAILED (failures=1)'), good + good, 'passed targeted_tests'):
            with self.subTest(text=text):
                self.assertFalse(test_result_passes('targeted_tests', argv, text.encode()))

    def test_build_without_test_framework_does_not_require_test_counts(self):
        self.assertTrue(test_result_passes('full_test_or_build', ['npm', 'run', 'build'],
                                         b'build complete', result_kind='build'))
        self.assertFalse(test_result_passes('full_test_or_build', ['python3', '-m', 'unittest'], b'OK'))

    def test_browser_names_in_script_arguments_do_not_change_report_type(self):
        report = passing_output(['python3', '-m', 'unittest']).encode()
        for adapter in ('playwright', 'cypress'):
            with self.subTest(adapter=adapter):
                argv = ['python3', '-B', 'runner.py', '--adapter', adapter]
                self.assertTrue(test_result_passes('targeted_tests', argv, report))

    def test_browser_entrypoints_accept_only_their_own_native_reports(self):
        reports = {
            'playwright': passing_output(['playwright']).encode(),
            'cypress': json.dumps({'stats': {'passes': 1, 'failures': 0, 'pending': 0, 'tests': 1},
                'tests': [{'title': 'ok'}], 'passes': [{'title': 'ok'}],
                'failures': [], 'pending': []}).encode(),
        }
        unittest_report = passing_output(['python3', '-m', 'unittest']).encode()
        for framework in reports:
            entrypoints = ([framework], [f'/project/node_modules/.bin/{framework}'],
                           [f'./node_modules/.bin/{framework}'], ['npx', framework])
            if framework == 'playwright':
                entrypoints += (['python3', '-B', '-m', 'playwright'],)
            for entry in entrypoints:
                with self.subTest(entry=entry):
                    argv = [*entry, 'test' if framework == 'playwright' else 'run']
                    self.assertTrue(test_result_passes('frontend_e2e', argv, reports[framework]))
                    other = 'cypress' if framework == 'playwright' else 'playwright'
                    self.assertFalse(test_result_passes('frontend_e2e', argv, reports[other]))
                    self.assertFalse(test_result_passes('frontend_e2e', argv, unittest_report))

    def test_playwright_native_report_is_accepted_and_wrong_framework_rejected(self):
        argv = ['npx', 'playwright', 'test', '--reporter=json']
        report = passing_output(argv).encode()
        self.assertTrue(test_result_passes('frontend_e2e', argv, report))
        self.assertFalse(test_result_passes('frontend_e2e', ['npx', 'cypress', 'run'], report))
        self.assertFalse(test_result_passes('frontend_e2e', argv, passing_output([]).encode()))

    def test_missing_unknown_or_malformed_reports_do_not_pass(self):
        for payload in (b'', b'OK', b'{}', b'\xff', b'{"stats":true}', b'{"passed":1}'):
            self.assertFalse(test_result_passes('targeted_tests', ['custom-test-runner'], payload))

    def test_native_cypress_report_is_accepted_but_pending_is_not(self):
        passed, pending = {'title': 'passed'}, {'title': 'pending'}
        report = {'stats': {'passes': 1, 'failures': 0, 'pending': 0, 'tests': 1},
                  'tests': [passed], 'passes': [passed], 'failures': [], 'pending': []}
        argv = ['npx', 'cypress', 'run']
        self.assertTrue(test_result_passes('frontend_e2e', argv, json.dumps(report).encode()))
        report['pending'] = [pending]
        report['tests'].append(pending)
        report['stats'].update(pending=1, tests=2)
        self.assertFalse(test_result_passes('frontend_e2e', argv, json.dumps(report).encode()))
