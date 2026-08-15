from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_cli_smoke import CLI_SCRIPTS, run_cli_smoke


class CliSmokeTests(unittest.TestCase):
    def test_every_declared_cli_starts(self) -> None:
        self.assertIn("validate_traceability.py", CLI_SCRIPTS)
        self.assertEqual([], run_cli_smoke())


if __name__ == "__main__":
    unittest.main()
