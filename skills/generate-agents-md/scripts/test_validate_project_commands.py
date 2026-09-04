from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_project_commands import REQUIRED_COMMANDS, validate_project_commands


SKILL_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_TEMPLATE = SKILL_ROOT / "assets" / "project-commands.template.json"


class ProjectCommandValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "commands.txt").write_text("unittest\npython3 -m unittest\npython3 -m playwright test\n", encoding="utf-8")
        self.path = self.root / "commands.json"
        self.path.write_text(json.dumps(self._manifest()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _manifest(self) -> dict[str, object]:
        commands = [
            {
                "id": command_id,
                "argv": ["python3", "-m", "unittest"],
                "source": "commands.txt",
                "source_selector": "unittest",
                "source_command": "python3 -m unittest",
                "working_directory": ".",
                "applicability": "required",
            }
            for command_id in sorted(REQUIRED_COMMANDS)
        ]
        for command_id in ("frontend_evidence", "frontend_e2e"):
            commands.append({
                "id": command_id,
                "argv": ["python3", "-m", "unittest"],
                "source": "commands.txt",
                "source_selector": "unittest",
                "source_command": "python3 -m unittest",
                "working_directory": ".",
                "applicability": "N/A: no frontend",
            })
        return {
            "schema_version": 1,
            "frontend_applicable": False,
            "frontend_preview_url": "N/A: no frontend",
            "frontend_preview_root": "N/A: no frontend",
            "frontend_entry_artifact": "N/A: no frontend",
            "commands": commands,
        }

    def codes(self) -> set[str]:
        return {item.code for item in validate_project_commands(self.path, project_root=self.root)}

    def test_public_template_structure_passes(self) -> None:
        self.assertEqual([], validate_project_commands(PUBLIC_TEMPLATE, project_root=SKILL_ROOT, template=True))

    def test_write_scope_command_is_required_and_not_constant_success(self) -> None:
        self.assertIn("task_write_scope", REQUIRED_COMMANDS)
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        command = next(item for item in data["commands"] if item["id"] == "task_write_scope")
        self.assertEqual("scripts/validate_task_write_scope.py", command["source"])
        self.assertIn("--module-key", command["argv"])
        self.assertIn("--target", command["argv"])
        command["argv"] = ["true"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_project_commands(
            self.path, project_root=self.root, template=True,
        )}
        self.assertIn("unsafe-command", codes)

    def test_template_mode_rejects_nested_unsafe_command(self) -> None:
        data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
        data["commands"][0]["argv"] = ["sh", "-c", "exit 0"]
        data["commands"][0]["unknown_failure_state"] = "P1 unresolved"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        codes = {item.code for item in validate_project_commands(self.path, project_root=self.root, template=True)}
        self.assertTrue({"unsafe-command", "invalid-command-fields"} <= codes)

    def test_template_frontend_entry_rejects_non_http_and_escaping_paths(self) -> None:
        cases = (
            ("frontend_preview_url", "file:///tmp/index.html"),
            ("frontend_preview_root", "../outside"),
            ("frontend_entry_artifact", "."),
        )
        for field, value in cases:
            with self.subTest(field=field):
                data = json.loads(PUBLIC_TEMPLATE.read_text(encoding="utf-8"))
                data[field] = value
                self.path.write_text(json.dumps(data), encoding="utf-8")
                codes = {item.code for item in validate_project_commands(self.path, project_root=self.root, template=True)}
                self.assertIn("invalid-frontend-entry", codes)

    def test_valid_manifest_passes(self) -> None:
        self.assertEqual(set(), self.codes())

    def test_boolean_schema_version_is_rejected(self) -> None:
        data = self._manifest()
        data["schema_version"] = True
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-schema-version", self.codes())

    def test_duplicate_or_unknown_command_fields_fail_closed(self) -> None:
        raw = json.dumps(self._manifest()).replace(
            '"argv": ["python3", "-m", "unittest"]',
            '"argv": ["sh", "-c", "exit 0"], "argv": ["python3", "-m", "unittest"]',
            1,
        )
        self.path.write_text(raw, encoding="utf-8")
        self.assertIn("invalid-command-manifest", self.codes())
        data = self._manifest()
        data["commands"][0]["unknown_failure_state"] = "P1 unresolved"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-command-fields", self.codes())

    def test_command_provenance_fields_must_be_strings(self) -> None:
        data = self._manifest()
        data["commands"][0]["working_directory"] = 123
        data["commands"][0]["source"] = 456
        data["commands"][0]["source_selector"] = 789
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-command-field-types", self.codes())

    def test_constant_success_and_shell_wrapper_fail(self) -> None:
        data = self._manifest()
        data["commands"][0]["argv"] = ["true"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unsafe-command", self.codes())

    def test_source_must_declare_selector(self) -> None:
        data = self._manifest()
        data["commands"][0]["source_selector"] = "missing-selector"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("undeclared-command", self.codes())

    def test_inline_constant_success_cannot_masquerade_as_declared_command(self) -> None:
        data = self._manifest()
        data["commands"][0]["argv"] = ["python3", "-c", "pass"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue({"unsafe-command", "command-declaration-mismatch"} & self.codes())

    def test_combined_inline_code_argument_is_rejected(self) -> None:
        command = "python3 -cpass"
        data = self._manifest()
        data["commands"][0]["argv"] = ["python3", "-cpass"]
        data["commands"][0]["source_command"] = command
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + command + "\n",
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unsafe-command", self.codes())

    def test_env_cannot_indirectly_launch_shell_or_swallow_failure(self) -> None:
        command = "env false"
        data = self._manifest()
        data["commands"][0]["argv"] = ["env", "false"]
        data["commands"][0]["source_command"] = command
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + command + "\n",
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unsafe-command", self.codes())

    def test_wrapper_cannot_indirectly_launch_shell_pipeline(self) -> None:
        command = "nice bash -lc false"
        data = self._manifest()
        data["commands"][0]["argv"] = ["nice", "bash", "-lc", "false"]
        data["commands"][0]["source_command"] = command
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + command + "\n",
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unsafe-command", self.codes())

    def test_single_pipe_shell_syntax_is_rejected(self) -> None:
        command = "nice false '|' true"
        data = self._manifest()
        data["commands"][0]["argv"] = ["nice", "false", "|", "true"]
        data["commands"][0]["source_command"] = command
        (self.root / "commands.txt").write_text(
            (self.root / "commands.txt").read_text(encoding="utf-8") + command + "\n",
            encoding="utf-8",
        )
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("unsafe-command", self.codes())

    def test_argv_must_equal_complete_declared_command(self) -> None:
        data = self._manifest()
        data["commands"][0]["argv"] = ["python3", "-m", "compileall"]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("command-declaration-mismatch", self.codes())

    def test_frontend_requires_e2e_command(self) -> None:
        data = self._manifest()
        data["frontend_applicable"] = True
        data.update({
            "frontend_preview_url": "http://127.0.0.1:4173/index.html",
            "frontend_preview_root": ".",
            "frontend_entry_artifact": "index.html",
        })
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("missing-frontend-command", self.codes())

    def test_frontend_entry_artifact_must_be_a_file(self) -> None:
        (self.root / "entry-dir").mkdir()
        data = self._manifest()
        data["frontend_applicable"] = True
        data.update({
            "frontend_preview_url": "http://127.0.0.1:4173/entry-dir",
            "frontend_preview_root": ".",
            "frontend_entry_artifact": "entry-dir",
        })
        for command in data["commands"]:
            if command["id"] in {"frontend_evidence", "frontend_e2e"}:
                command["applicability"] = "required"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("invalid-frontend-entry-artifact", self.codes())


if __name__ == "__main__":
    unittest.main()
