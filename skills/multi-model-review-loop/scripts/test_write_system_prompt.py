from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from spawn_external_agent import SYSTEM_PROMPTS


class WriteSystemPromptTests(unittest.TestCase):
    def test_writes_exact_reviewed_prompt_once(self) -> None:
        root = Path(tempfile.mkdtemp(
            prefix="codex-external-loop.", dir="/tmp",
        ))
        output = root / "deepseek-system.txt"
        script = Path(__file__).with_name("write_system_prompt.py")

        completed = subprocess.run(
            [sys.executable, str(script), "deepseek", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(SYSTEM_PROMPTS["deepseek"] + "\n", output.read_text())
        repeated = subprocess.run(
            [sys.executable, str(script), "deepseek", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, repeated.returncode)


if __name__ == "__main__":
    unittest.main()
