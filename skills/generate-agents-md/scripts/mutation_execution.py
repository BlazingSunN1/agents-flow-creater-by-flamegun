"""Bounded mutation test execution; infrastructure errors never kill a mutant."""
import subprocess
import sys
from pathlib import Path


def run_target(root: Path, target: str) -> str:
    worker = Path(__file__).with_name('mutation_test_runner.py')
    try:
        result = subprocess.run([sys.executable, '-B', str(worker), target], cwd=root,
            text=True, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return 'invalid'
    for code, outcome in ((0, 'pass'), (1, 'fail')):
        if result.returncode == code and result.stdout.strip() == f'MUTATION_TEST_RESULT={outcome}':
            return outcome
    return 'invalid'
