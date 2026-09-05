import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_mutation_checks as mutations
from mutation_execution import run_target


class MutationExecutionTests(unittest.TestCase):
    def test_registered_mutation_targets_exist(self):
        for target in sorted({mutant.test for mutant in mutations.MUTANTS}):
            with self.subTest(target=target):
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromName(target)
                self.assertEqual([], loader.errors)
                self.assertGreater(suite.countTestCases(), 0)

    def test_hard_deny_mutant_is_killed_by_an_executed_test(self):
        mutant = next(item for item in mutations.MUTANTS
                      if item.name == 'hard-deny-writer-actor-priority-disabled')
        output = io.StringIO()
        with patch.object(mutations, 'MUTANTS', (mutant,)), contextlib.redirect_stdout(output):
            result = mutations.main()
        self.assertEqual(0, result, output.getvalue())
        self.assertIn(f'KILLED {mutant.name}', output.getvalue())
        self.assertIn('mutation_survivors=0 mutants=1 valid=true', output.getvalue())

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/__init__.py').touch()
        (self.root / 'scripts/value.py').write_text('VALUE = 1\n')
        (self.root / 'scripts/test_value.py').write_text('import unittest\n'
            'from scripts.value import VALUE\nclass T(unittest.TestCase):\n'
            '    def test_value(self): self.assertEqual(1, VALUE)\n')

    def test_release_publish_mutant_is_killed_by_an_executed_test(self):
        mutant = next(item for item in mutations.MUTANTS
                      if item.name == 'release-publish-verdict-action-ontology-disabled')
        output = io.StringIO()
        with patch.object(mutations, 'MUTANTS', (mutant,)), contextlib.redirect_stdout(output):
            result = mutations.main()
        self.assertEqual(0, result, output.getvalue())
        self.assertIn(f'KILLED {mutant.name}', output.getvalue())

    def run_mutant(self, *, target='scripts.test_value', replacement='VALUE = 2\n'):
        mutant = mutations.Mutant('small-fixture', 'scripts/value.py', 'VALUE = 1\n', replacement, target)
        output = io.StringIO()
        with patch.object(mutations, 'SKILL_ROOT', self.root), patch.object(mutations, 'MUTANTS', (mutant,)):
            with contextlib.redirect_stdout(output):
                result = mutations.main()
        return result, output.getvalue()

    def test_missing_target_is_invalid_not_killed(self):
        result, output = self.run_mutant(target='scripts.does_not_exist')
        self.assertNotEqual(0, result)
        self.assertNotIn('KILLED', output)

    def test_mutated_import_error_is_invalid_not_killed(self):
        result, output = self.run_mutant(replacement='raise ImportError("broken import")\n')
        self.assertNotEqual(0, result)
        self.assertNotIn('KILLED', output)

    def test_mutated_syntax_error_is_invalid_not_killed(self):
        result, output = self.run_mutant(replacement='VALUE = (\n')
        self.assertNotEqual(0, result)
        self.assertNotIn('KILLED', output)

    def test_failing_baseline_is_invalid_not_killed(self):
        (self.root / 'scripts/test_value.py').write_text('import unittest\n'
            'class T(unittest.TestCase):\n    def test_fail(self): self.fail("baseline fails")\n')
        result, output = self.run_mutant()
        self.assertNotEqual(0, result)
        self.assertNotIn('KILLED', output)

    def test_assertion_kills_mutant(self):
        result, output = self.run_mutant()
        self.assertEqual(0, result)
        self.assertIn('KILLED small-fixture', output)

    def test_zero_tests_and_survivor_never_pass(self):
        result, _ = self.run_mutant(replacement='VALUE = 1  # survives\n')
        self.assertNotEqual(0, result)
        result, _ = self.run_mutant(target='scripts.value')
        self.assertNotEqual(0, result)

    def test_timeout_is_invalid(self):
        with patch('mutation_execution.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 60)):
            self.assertEqual('invalid', run_target(self.root, 'scripts.test_value'))

    def test_noisy_test_output_does_not_invalidate_real_test_failure(self):
        path = self.root / 'scripts/test_value.py'
        path.write_text(path.read_text().replace('self.assertEqual', 'print("diagnostic"); self.assertEqual'))
        result, output = self.run_mutant()
        self.assertEqual(0, result)
        self.assertIn('KILLED', output)

    def test_all_skipped_baseline_is_invalid(self):
        path = self.root / 'scripts/test_value.py'
        path.write_text(path.read_text().replace('class T', '@unittest.skip("unavailable")\nclass T'))
        result, output = self.run_mutant()
        self.assertNotEqual(0, result)
        self.assertNotIn('KILLED', output)
