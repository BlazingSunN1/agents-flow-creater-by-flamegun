from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trace_workset_binding import binding_issue_codes, module_requirement_ids


class TraceWorksetBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in ("src/a.py", "src/b.py"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(relative, encoding="utf-8")
        self.trace = """## Traceability

| Requirement | Flow | Feature | UI/UX | Unit tests | Acceptance cases | Code module | Black-box result | Status |
|---|---|---|---|---|---|---|---|---|
| [REQ-001](requirements/a.md) | [FLOW-001](flows/a.html) | [FEAT-001](features/a.md) | N/A: internal | [UT-001](tests/a.py) | [AT-001](tests/a.md) | [MOD-001](src/a.py) | [BB-001](evidence/a.md) | pending |
| [REQ-002](requirements/b.md) | [FLOW-002](flows/b.html) | [FEAT-002](features/b.md) | N/A: internal | [UT-002](tests/b.py) | [AT-002](tests/b.md) | [MOD-002](src/b.py) | [BB-002](evidence/b.md) | pending |
"""

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_selected_requirement_must_cover_current_changed_files(self) -> None:
        context = {
            "Requirement IDs": "REQ-001",
            "Changed files": "src/b.py",
            "Modules": "b",
            "Module changed files": "b=src/b.py",
        }
        self.assertIn("bundle-requirement-code-mismatch", binding_issue_codes(self.trace, context, self.root))

    def test_module_records_receive_only_owned_requirement_ids(self) -> None:
        context = {
            "Requirement IDs": "REQ-001, REQ-002",
            "Changed files": "src/a.py, src/b.py",
            "Modules": "a, b",
            "Module changed files": "a=src/a.py; b=src/b.py",
        }
        self.assertEqual({"a": "REQ-001", "b": "REQ-002"}, module_requirement_ids(self.trace, context, self.root))

    def test_multi_requirement_row_only_attributes_selected_ids(self) -> None:
        trace = self.trace.replace(
            "[REQ-001](requirements/a.md)",
            "[REQ-001](requirements/a.md), [REQ-002](requirements/b.md)",
            1,
        ).replace(
            "| [REQ-002](requirements/b.md) | [FLOW-002]", "| [REQ-003](requirements/b.md) | [FLOW-002]",
        )
        context = {
            "Requirement IDs": "REQ-001",
            "Changed files": "src/a.py",
            "Modules": "a",
            "Module changed files": "a=src/a.py",
        }
        self.assertEqual({"a": "REQ-001"}, module_requirement_ids(trace, context, self.root))
