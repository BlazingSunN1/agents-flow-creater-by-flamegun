from __future__ import annotations

import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
