from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from update_project_record import MISSING_SHA, update_record
import update_project_record


SCRIPT = Path(__file__).resolve().parent / "update_project_record.py"


class AtomicProjectRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_and_compare_and_swap_update(self) -> None:
        first_sha = update_record(Path("docs/progress.md"), project_root=self.root, content=b"first", expected_sha256=MISSING_SHA)
        self.assertEqual(hashlib.sha256(b"first").hexdigest(), first_sha)
        second_sha = update_record(Path("docs/progress.md"), project_root=self.root, content=b"second", expected_sha256=first_sha)
        self.assertEqual(hashlib.sha256(b"second").hexdigest(), second_sha)
        self.assertEqual(b"second", (self.root / "docs/progress.md").read_bytes())

    def test_stale_writer_is_rejected_without_overwrite(self) -> None:
        update_record(Path("progress.md"), project_root=self.root, content=b"current", expected_sha256=MISSING_SHA)
        with self.assertRaisesRegex(RuntimeError, "stale-write"):
            update_record(Path("progress.md"), project_root=self.root, content=b"stale", expected_sha256="0" * 64)
        self.assertEqual(b"current", (self.root / "progress.md").read_bytes())

    def test_two_concurrent_writers_cannot_both_commit(self) -> None:
        target = self.root / "progress.md"
        target.write_bytes(b"base")
        expected = hashlib.sha256(b"base").hexdigest()
        inputs = []
        processes = []
        for index in range(2):
            source = self.root / f"input-{index}.txt"
            source.write_text(f"writer-{index}", encoding="utf-8")
            inputs.append(source)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "progress.md",
                        "--project-root",
                        str(self.root),
                        "--content-file",
                        str(source),
                        "--expected-sha256",
                        expected,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        return_codes = [process.communicate(timeout=10)[0] and process.returncode for process in processes]
        self.assertEqual([0, 1], sorted(return_codes))
        self.assertIn(target.read_text(encoding="utf-8"), {"writer-0", "writer-1"})

    def test_target_cannot_escape_project_root(self) -> None:
        with self.assertRaises(ValueError):
            update_record(Path("../outside.md"), project_root=self.root, content=b"bad", expected_sha256=MISSING_SHA)

    def test_symlinked_parent_cannot_redirect_write_outside_project(self) -> None:
        outside = Path(tempfile.mkdtemp())
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises((ValueError, OSError)):
                update_record(Path("linked/progress.md"), project_root=self.root, content=b"bad", expected_sha256=MISSING_SHA)
            self.assertFalse((outside / "progress.md").exists())
        finally:
            outside.rmdir()

    def test_project_root_swap_cannot_redirect_write_outside_project(self) -> None:
        project = self.root / "project"
        outside = self.root / "outside"
        moved = self.root / "project-original"
        project.mkdir()
        outside.mkdir()
        (outside / "progress.md").write_bytes(b"outside")
        original_resolve = update_project_record._resolve_target

        def swap_root(target: Path, root: Path) -> Path:
            resolved = original_resolve(target, root)
            project.rename(moved)
            project.symlink_to(outside, target_is_directory=True)
            return resolved

        with mock.patch.object(update_project_record, "_resolve_target", side_effect=swap_root):
            with self.assertRaises((OSError, RuntimeError)):
                update_record(Path("progress.md"), project_root=project, content=b"bad", expected_sha256=hashlib.sha256(b"outside").hexdigest())
        self.assertEqual(b"outside", (outside / "progress.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
