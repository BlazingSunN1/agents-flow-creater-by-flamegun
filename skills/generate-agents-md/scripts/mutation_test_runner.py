"""Run one mutation target with distinct test-failure and invalid-run outcomes."""
import contextlib
import sys
import unittest
from pathlib import Path


def main() -> int:
    # This worker may live outside the copied candidate; never import its source instead.
    own_directory = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != own_directory]
    sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'scripts')]
    try:
        with contextlib.redirect_stdout(sys.stderr):
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromName(sys.argv[1])
            if loader.errors or suite.countTestCases() == 0:
                return 2
            result = unittest.TextTestRunner().run(suite)
        if result.testsRun - len(result.skipped) == 0:
            return 2
    except (Exception, SystemExit) as error:
        print(f'MUTATION_TEST_RESULT=invalid {type(error).__name__}')
        return 2
    outcome = 'pass' if result.wasSuccessful() else 'fail'
    print(f'MUTATION_TEST_RESULT={outcome}')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
