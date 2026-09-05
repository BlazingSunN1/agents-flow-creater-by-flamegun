from __future__ import annotations

import re
from pathlib import Path

from frontend_report_validation import _native_report_counts
from strict_json import loads as strict_json_loads


TEST_COMMANDS = {'targeted_tests', 'frontend_e2e', 'mobile_frontend_e2e', 'native_mobile_tests'}


def _test_framework(argv: object) -> str | None:
    if not isinstance(argv, list) or not argv or not all(isinstance(token, str) for token in argv):
        return None
    frameworks = {'unittest', 'pytest', 'py.test', 'playwright', 'cypress'}
    executable = Path(argv[0]).name.lower().removesuffix('.exe')
    if executable in frameworks:
        return executable
    if not executable.startswith('python') and executable not in {'npx', 'npx.cmd'}:
        return None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == '-m' and executable.startswith('python'):
            module = argv[index + 1].split('.')[0] if index + 1 < len(argv) else None
            return module if module in frameworks else None
        if token in {'-c', '--', '-'} or token.startswith('-c'):
            return None
        if not token.startswith('-'):
            return token if executable in {'npx', 'npx.cmd'} and token in frameworks else None
        index += 2 if token in {'-W', '-X', '--check-hash-based-pycs'} else 1
    return None


def invokes_test_framework(argv: object) -> bool:
    return _test_framework(argv) is not None


def _looks_like_test_report(payload: bytes) -> bool:
    text = payload.decode('utf-8', errors='replace')
    if re.search(r'^Ran \d+ tests? in ', text, re.MULTILINE):
        return True
    try:
        report = strict_json_loads(text)
    except ValueError:
        return False
    if not isinstance(report, dict) or not isinstance(report.get('stats'), dict):
        return False
    return ({'config', 'suites'} <= report.keys()
            or {'tests', 'passes', 'failures', 'pending'} <= report.keys()
            or ('results' in report and {'passes', 'failures'} <= report['stats'].keys()))


def test_result_passes(command_id: str, argv: object, payload: bytes, *, result_kind: str = 'tests') -> bool:
    """Require executed passing tests, using existing native reports only."""
    is_test = command_id in TEST_COMMANDS or (
        command_id == 'full_test_or_build' and (
            result_kind != 'build' or invokes_test_framework(argv) or _looks_like_test_report(payload))
    )
    if not is_test:
        return True
    try:
        text = payload.decode('utf-8').strip()
    except UnicodeError:
        return False
    invoked_framework = _test_framework(argv)
    browser_framework = invoked_framework if invoked_framework in {'playwright', 'cypress'} else None
    # unittest's native summary: exactly one run, positive count, no skip/fail.
    runs = list(re.finditer(r'^Ran (\d+) tests? in [0-9.]+s$', text, re.MULTILINE))
    if runs and browser_framework is None:
        # Buffered stdout can follow stderr's summary; bind OK to that summary.
        return (len(runs) == 1 and int(runs[0].group(1)) > 0
                and re.match(r'\n\nOK(?:\n|$)', text[runs[0].end():]) is not None)
    try:
        report = strict_json_loads(text)
    except ValueError:
        return False
    for framework in ('Playwright', 'Cypress'):
        if browser_framework is not None and framework.lower() != browser_framework:
            continue
        observed = _native_report_counts(report, framework)
        if observed is not None and observed[0] > 0 and observed[1] == 0:
            return True
    return False
