from __future__ import annotations

import sys
import tempfile
import unittest
import ast
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_code_structure import validate_scripts


class CodeStructureTests(unittest.TestCase):
    def test_current_skill_structure_passes(self) -> None:
        self.assertEqual([], validate_scripts())

    def test_long_function_and_cycle_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text("import b\n\ndef oversized():\n" + "    x = 1\n" * 51, encoding="utf-8")
            (root / "b.py").write_text("import a\n", encoding="utf-8")
            codes = {issue.code for issue in validate_scripts(root)}
        self.assertEqual({"function-too-long", "circular-import"}, codes)

    def test_delivery_bundle_orchestrator_stays_within_function_limit(self) -> None:
        source = (SCRIPT_DIR / "validate_delivery_bundle.py").read_text(encoding="utf-8")
        function = next(
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "_validate_delivery_bundle_impl"
        )
        self.assertLessEqual((function.end_lineno or function.lineno) - function.lineno + 1, 50)


if __name__ == "__main__":
    unittest.main()
