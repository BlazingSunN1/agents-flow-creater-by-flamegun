from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_validate_traceability as trace_test_support
from test_validate_agents_md import ROOT_TEMPLATE, error_codes
from validate_agents_md import REQUIRED_MACHINE_POLICY
from validate_traceability import validate_traceability


class AdversarialPropertyTests(unittest.TestCase):
    def test_every_machine_policy_value_fails_when_weakened(self) -> None:
        for key, expected in REQUIRED_MACHINE_POLICY.items():
            with self.subTest(key=key):
                weakened = ROOT_TEMPLATE.replace(f"{key}: {expected}", f"{key}: optional")
                self.assertIn(
                    "invalid-machine-policy",
                    error_codes(weakened, mode="public-template", scope="root"),
                )

    def test_seeded_malformed_trace_rows_never_disappear(self) -> None:
        fixture = trace_test_support.TraceabilityValidatorTests()
        fixture.setUp()
        try:
            original = fixture.matrix.read_text(encoding="utf-8")
            marker = "\n## Independent Gate Evidence"
            randomizer = random.Random(20260814)
            for index in range(50):
                cell_count = randomizer.choice(tuple(range(1, 9)) + tuple(range(10, 15)))
                row = "| " + " | ".join(f"fuzz-{index}-{cell}" for cell in range(cell_count)) + " |"
                fixture.matrix.write_text(original.replace(marker, f"\n{row}{marker}"), encoding="utf-8")
                codes = {
                    issue.code
                    for issue in validate_traceability(fixture.matrix, project_root=fixture.root)
                }
                self.assertIn("malformed-table-row", codes)
        finally:
            fixture.tearDown()

    def test_path_escape_variants_are_rejected(self) -> None:
        fixture = trace_test_support.TraceabilityValidatorTests()
        fixture.setUp()
        try:
            original = fixture.matrix.read_text(encoding="utf-8")
            for unsafe in ("../outside.md", "../../etc/passwd", "/tmp/outside.md"):
                with self.subTest(path=unsafe):
                    fixture.matrix.write_text(original.replace("features/list.md", unsafe), encoding="utf-8")
                    codes = {
                        issue.code
                        for issue in validate_traceability(fixture.matrix, project_root=fixture.root)
                    }
                    self.assertIn("unsafe-trace-artifact-path", codes)
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
