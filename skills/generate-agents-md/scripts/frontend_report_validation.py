from __future__ import annotations

from collections import Counter


def _native_report_counts(report: object, framework: str) -> tuple[object, object] | None:
    if not isinstance(report, dict):
        return None
    stats = report.get("stats")
    if not isinstance(stats, dict):
        return None
    if (framework == "Playwright" and isinstance(report.get("config"), dict)
            and isinstance(report.get("suites"), list) and report.get("errors") == []):
        expected, unexpected = stats.get("expected"), stats.get("unexpected")
        observed = _playwright_report_counts(report["suites"])
        if (isinstance(expected, int) and isinstance(unexpected, int)
                and expected + unexpected > 0 and observed == (expected, unexpected)
                and stats.get("flaky", 0) == 0 and stats.get("skipped", 0) == 0):
            return expected, unexpected
    if framework == "Cypress" and isinstance(report.get("results"), list):
        passes, failures = stats.get("passes"), stats.get("failures")
        observed = _cypress_results_counts(report["results"])
        if isinstance(passes, int) and isinstance(failures, int) and passes > 0 and observed == (passes, failures):
            return passes, failures
    if framework == "Cypress" and all(isinstance(report.get(key), list) for key in ("tests", "pending", "failures", "passes")):
        passes, failures = stats.get("passes"), stats.get("failures")
        observed = _mocha_report_counts(report, stats)
        if isinstance(passes, int) and isinstance(failures, int) and passes > 0 and observed == (passes, failures):
            return passes, failures
    return None


def _cypress_results_counts(results: list[object]) -> tuple[int, int] | None:
    counts = [0, 0]
    for result in results:
        if not isinstance(result, dict):
            return None
        tests = result.get("tests")
        candidates = tests if isinstance(tests, list) and tests else [result]
        for test in candidates:
            if not isinstance(test, dict) or not _cypress_test_identity(test):
                return None
            state = _cypress_test_state(test)
            if state == "passed":
                counts[0] += 1
            elif state == "failed":
                counts[1] += 1
            else:
                return None
    return tuple(counts) if sum(counts) > 0 else None


def _cypress_test_identity(test: dict[str, object]) -> bool:
    title = test.get("title", test.get("fullTitle"))
    if isinstance(title, str):
        return bool(title.strip())
    return isinstance(title, list) and bool(title) and all(isinstance(item, str) and item.strip() for item in title)


def _cypress_test_state(test: dict[str, object]) -> object:
    state = test.get("state")
    if state in {"passed", "failed"}:
        return state
    attempts = test.get("attempts")
    if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict):
        return attempts[-1].get("state")
    return None


def _mocha_report_counts(report: dict[str, object], stats: dict[str, object]) -> tuple[int, int] | None:
    test_ids = _mocha_test_ids(report["tests"])
    pass_ids = _mocha_test_ids(report["passes"])
    failure_ids = _mocha_test_ids(report["failures"])
    pending_ids = _mocha_test_ids(report["pending"])
    if any(items is None for items in (test_ids, pass_ids, failure_ids, pending_ids)):
        return None
    if not test_ids or Counter(test_ids) != Counter(pass_ids + failure_ids + pending_ids):
        return None
    passes, failures = stats.get("passes"), stats.get("failures")
    total, pending = stats.get("tests"), stats.get("pending")
    if (len(pass_ids) != passes or len(failure_ids) != failures
            or (isinstance(total, int) and len(test_ids) != total)
            or (isinstance(pending, int) and len(pending_ids) != pending)):
        return None
    return len(pass_ids), len(failure_ids)


def _mocha_test_ids(items: object) -> list[str] | None:
    if not isinstance(items, list):
        return None
    identities: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        identity = item.get("fullTitle", item.get("title"))
        if not isinstance(identity, str) or not identity.strip():
            return None
        identities.append(identity.strip())
    return identities


def _playwright_report_counts(suites: list[object]) -> tuple[int, int] | None:
    expected_count = 0
    unexpected_count = 0
    for suite in suites:
        if not isinstance(suite, dict):
            return None
        specs = suite.get("specs", [])
        if isinstance(specs, list):
            for spec in specs:
                if not isinstance(spec, dict):
                    return None
                tests = spec.get("tests", []) if isinstance(spec, dict) else []
                identity = spec.get("title", spec.get("file"))
                if (not isinstance(identity, str) or not identity.strip()
                        or not isinstance(tests, list) or not tests):
                    return None
                for test in tests:
                    results = test.get("results") if isinstance(test, dict) else None
                    if (not isinstance(results, list) or len(results) != 1
                            or not isinstance(results[0], dict)
                            or results[0].get("status") not in {"passed", "failed", "timedOut", "interrupted"}):
                        return None
                    expected_status = test.get("expectedStatus", "passed")
                    actual_status = results[0].get("status")
                    if actual_status in {"passed", "failed"} and actual_status == expected_status:
                        expected_count += 1
                    else:
                        unexpected_count += 1
        children = suite.get("suites", [])
        if isinstance(children, list):
            child_counts = _playwright_report_counts(children)
            if child_counts is None:
                return None
            expected_count += child_counts[0]
            unexpected_count += child_counts[1]
    return expected_count, unexpected_count
