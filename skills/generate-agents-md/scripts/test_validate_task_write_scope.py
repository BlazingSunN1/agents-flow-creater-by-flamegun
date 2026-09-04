from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import validate_task_write_scope as write_scope


SCRIPT = Path(__file__).resolve().parent / "validate_task_write_scope.py"


class TaskWriteScopeTests(unittest.TestCase):
    def run_validator(
        self, *arguments: str, home: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if home is not None:
            environment["HOME"] = str(home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    @staticmethod
    def write_ownership(root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "AGENTS.md").write_text(
            "# Project rules\n\n"
            "## Module Agent Ownership and Dispatcher\n\n"
            "| Module | Stable scope | Owned project-relative paths | Long-term maintenance Agent title |\n"
            "| --- | --- | --- | --- |\n"
            "| m01 | feature | `src/m01/`, `tests/m01/` | M01 Maintainer |\n"
            "| m02 | other | `src/m02/` | M02 Maintainer |\n",
            encoding="utf-8",
        )

    def project_arguments(self, root: Path, protected: Path | None = None) -> list[str]:
        arguments = [
            "--role", "project-agent",
            "--project-root", str(root),
            "--module-key", "m01",
            "--ownership-file", "AGENTS.md",
        ]
        if protected is not None:
            arguments.extend(("--protected-root", str(protected)))
        return arguments

    def test_project_target_inside_project_root_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            self.write_ownership(project)
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(project / "src" / "m01" / "feature.py"),
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_module_key_is_case_insensitive_like_ownership_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            self.write_ownership(project)
            arguments = self.project_arguments(project)
            arguments[arguments.index("m01")] = "M01"
            result = self.run_validator(
                *arguments,
                "--target", str(project / "src" / "m01" / "feature.py"),
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_uppercase_module_key_reports_cross_module_target_precisely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            self.write_ownership(project)
            arguments = self.project_arguments(project)
            arguments[arguments.index("m01")] = "M01"
            result = self.run_validator(
                *arguments,
                "--target", str(project / "src" / "m02" / "feature.py"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("module-ownership-mismatch", result.stderr)
        self.assertNotIn("module-owner-not-registered", result.stderr)

    def test_project_target_outside_project_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            self.write_ownership(project)
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(base / "outside.txt"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside-project-root", result.stderr)

    def test_project_target_in_protected_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            protected = base / "plugins"
            self.write_ownership(project)
            protected.mkdir()
            result = self.run_validator(
                *self.project_arguments(project, protected),
                "--target", str(protected / "skill" / "SKILL.md"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("protected-root", result.stderr)

    def test_existing_symlink_escape_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            outside = base / "outside"
            self.write_ownership(project)
            outside.mkdir()
            (project / "escape").symlink_to(outside, target_is_directory=True)
            result = self.run_validator(
                *self.project_arguments(project, base / "plugins"),
                "--target", str(project / "escape" / "changed.txt"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside-project-root", result.stderr)

    def test_project_root_cannot_be_a_protected_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            protected = base / "plugins"
            project = protected / "plugin-source"
            self.write_ownership(project)
            result = self.run_validator(
                *self.project_arguments(project, protected),
                "--target", str(project / "SKILL.md"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("project-root-is-protected", result.stderr)

    def test_maintainer_requires_explicit_current_user_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            maintenance = Path(temporary) / "plugin-source"
            maintenance.mkdir()
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--target", str(maintenance / "SKILL.md"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing-explicit-user-authorization", result.stderr)

    def test_maintainer_exact_root_with_authorization_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            protected = base / "plugins"
            maintenance = protected / "plugin-source"
            maintenance.mkdir(parents=True)
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--protected-root", str(protected),
                "--target", str(maintenance / "SKILL.md"),
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_maintainer_directory_target_cannot_hide_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            maintenance = base / "plugin-source"
            outside = base / "outside"
            maintenance.mkdir()
            outside.mkdir()
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            (maintenance / "escape").symlink_to(outside, target_is_directory=True)
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--target", str(maintenance),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("maintenance-directory-target-contains-symlink", result.stderr)

    def test_maintainer_directory_scan_error_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            maintenance = Path(temporary) / "plugin-source"
            maintenance.mkdir()
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            args = write_scope.build_parser().parse_args([
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--target", str(maintenance),
            ])
            with patch.object(
                write_scope,
                "_directory_target_risks",
                return_value=(None, None, maintenance / "locked"),
            ):
                findings, _warnings = write_scope.validate(args)

        self.assertIn(
            "maintenance-directory-target-scan-failed",
            {finding.code for finding in findings},
        )

    def test_maintainer_directory_without_symlinks_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            maintenance = Path(temporary) / "plugin-source"
            maintenance.mkdir()
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            (maintenance / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--target", str(maintenance),
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_maintainer_cannot_write_a_sibling_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            protected = base / "plugins"
            maintenance = protected / "plugin-source"
            sibling = protected / "other-plugin"
            maintenance.mkdir(parents=True)
            sibling.mkdir()
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--protected-root", str(protected),
                "--target", str(sibling / "SKILL.md"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside-maintenance-root", result.stderr)

    def test_maintainer_root_must_be_a_skill_or_plugin_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            maintenance = Path(temporary) / "broad-root"
            maintenance.mkdir()
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--target", str(maintenance / "arbitrary.txt"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid-maintenance-source-root", result.stderr)

    def test_maintainer_rejects_derived_install_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            derived = Path(temporary) / "installed-skills"
            maintenance = derived / "example-skill"
            maintenance.mkdir(parents=True)
            (maintenance / "SKILL.md").write_text("# test\n", encoding="utf-8")
            result = self.run_validator(
                "--role", "skill-maintainer",
                "--maintenance-root", str(maintenance),
                "--explicit-user-authorization",
                "--authorization-source", "current-user-request",
                "--derived-root", str(derived),
                "--target", str(maintenance / "SKILL.md"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("maintenance-root-is-derived", result.stderr)

    def test_filesystem_root_cannot_be_declared_as_project(self) -> None:
        result = self.run_validator(
            "--role", "project-agent",
            "--project-root", "/",
            "--module-key", "m01",
            "--ownership-file", "AGENTS.md",
            "--target", "/private/etc/hosts",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsafe-project-root", result.stderr)

    def test_project_target_must_belong_to_declared_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            self.write_ownership(project)
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", "src/m02/foreign.py",
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("module-ownership-mismatch", result.stderr)

    def test_project_requires_canonical_ownership_file_and_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            self.write_ownership(project)
            missing_module = self.run_validator(
                "--role", "project-agent",
                "--project-root", str(project),
                "--ownership-file", "AGENTS.md",
                "--target", "src/m01/file.py",
            )
            alternate_file = self.run_validator(
                *self.project_arguments(project),
                "--ownership-file", "OTHER.md",
                "--target", "src/m01/file.py",
            )
        self.assertNotEqual(0, missing_module.returncode)
        self.assertIn("--module-key", missing_module.stderr)
        self.assertNotEqual(0, alternate_file.returncode)
        self.assertIn("ownership-file-not-canonical", alternate_file.stderr)

    def test_disable_default_protection_switch_is_not_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            self.write_ownership(project)
            result = self.run_validator(
                *self.project_arguments(project),
                "--no-default-protected-roots",
                "--target", "src/m01/file.py",
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_ordinary_project_under_plugins_parent_is_not_overblocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            project = home / "plugins" / "ordinary-project"
            self.write_ownership(project)
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", "src/m01/file.py",
                home=home,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_plugin_source_cannot_masquerade_as_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "plugin-source"
            self.write_ownership(project)
            (project / ".codex-plugin").mkdir()
            (project / ".codex-plugin/plugin.json").write_text("{}", encoding="utf-8")
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", "src/m01/file.py",
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("project-root-is-skill-source", result.stderr)

    def test_nested_plugin_source_outside_conventional_roots_is_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "src"
            plugin = project / "global-plugin"
            project.mkdir(parents=True)
            (project / "AGENTS.md").write_text(
                "# Project rules\n\n"
                "## Module Agent Ownership and Dispatcher\n\n"
                "| Module | Stable scope | Owned project-relative paths | Long-term maintenance Agent title |\n"
                "| --- | --- | --- | --- |\n"
                "| m01 | feature | `global-plugin/` | M01 Maintainer |\n",
                encoding="utf-8",
            )
            (plugin / ".codex-plugin").mkdir(parents=True)
            (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(plugin / "skills" / "example" / "SKILL.md"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("project-target-is-skill-source", result.stderr)

    def test_symlinked_source_marker_cannot_hide_nested_plugin_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            plugin = project / "src" / "m01" / "plugin"
            self.write_ownership(project)
            (plugin / ".codex-plugin").mkdir(parents=True)
            (plugin / ".codex-plugin" / "plugin.json").symlink_to(
                project / "missing-plugin-manifest.json"
            )
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(plugin / "skills" / "example" / "helper.py"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("project-target-is-skill-source", result.stderr)

    def test_parent_directory_target_cannot_cover_nested_plugin_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            plugin = project / "src" / "m01" / "nested-plugin"
            self.write_ownership(project)
            (plugin / ".codex-plugin").mkdir(parents=True)
            (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(project / "src" / "m01"),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("project-target-contains-skill-source", result.stderr)

    def test_parent_directory_target_cannot_hide_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            outside = base / "outside"
            self.write_ownership(project)
            outside.mkdir()
            owned = project / "src" / "m01"
            owned.mkdir(parents=True, exist_ok=True)
            (owned / "external-link").symlink_to(outside, target_is_directory=True)
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(owned),
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("project-directory-target-contains-symlink", result.stderr)

    def test_owned_directory_without_protected_descendants_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            self.write_ownership(project)
            owned = project / "src" / "m01"
            owned.mkdir(parents=True, exist_ok=True)
            (owned / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = self.run_validator(
                *self.project_arguments(project),
                "--target", str(owned),
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_directory_scan_error_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "owned"
            target.mkdir()

            def failed_walk(*_args: object, **kwargs: object):
                onerror = kwargs["onerror"]
                assert callable(onerror)
                onerror(PermissionError(13, "permission denied", str(target / "locked")))
                return iter(())

            with patch.object(write_scope.os, "walk", side_effect=failed_walk):
                source, symlink, scan_error = write_scope._directory_target_risks(target)

        self.assertIsNone(source)
        self.assertIsNone(symlink)
        self.assertEqual(target / "locked", scan_error)

    def test_project_agent_cannot_create_a_new_skill_source_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            self.write_ownership(project)
            targets = (
                project / "src" / "m01" / "new-skill" / "SKILL.md",
                project / "src" / "m01" / "new-skill-case-alias" / "skill.md",
                project / "src" / "m01" / "new-plugin" / ".codex-plugin" / "plugin.json",
                project / "src" / "m01" / "new-plugin-case-alias" / ".CODEX-PLUGIN" / "PLUGIN.JSON",
            )
            for target in targets:
                with self.subTest(target=target):
                    result = self.run_validator(
                        *self.project_arguments(project),
                        "--target", str(target),
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("project-target-is-skill-source", result.stderr)


if __name__ == "__main__":
    unittest.main()
