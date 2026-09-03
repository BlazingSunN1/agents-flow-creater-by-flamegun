from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_plugin_distribution import PLUGIN_ROOT, validate_distribution


class PluginDistributionTests(unittest.TestCase):
    def test_default_plugin_root_contains_manifest(self) -> None:
        self.assertTrue((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").is_file())

    def _source(self, root: Path) -> Path:
        source = root / "source"
        (source / ".codex-plugin").mkdir(parents=True)
        (source / "skills" / "generate-agents-md").mkdir(parents=True)
        (source / "skills" / "native-gpt-review-loop").mkdir(parents=True)
        (source / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "demo", "version": "1.0+codex.test", "skills": "./skills/"}),
            encoding="utf-8",
        )
        for name in ("generate-agents-md", "native-gpt-review-loop"):
            (source / "skills" / name / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: test\n---\n", encoding="utf-8",
            )
        return source

    def test_matching_cache_and_direct_duplicate_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            installed = root / "installed"
            direct = root / "direct"
            shutil.copytree(source, installed)
            shutil.copytree(source / "skills" / "generate-agents-md", direct / "generate-agents-md")
            self.assertEqual([], validate_distribution(source, installed, direct))

    def test_stale_cache_and_direct_duplicate_fail_with_precise_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            installed = root / "installed"
            direct = root / "direct"
            shutil.copytree(source, installed)
            shutil.copytree(source / "skills" / "generate-agents-md", direct / "generate-agents-md")
            (installed / "skills" / "generate-agents-md" / "SKILL.md").write_text("stale", encoding="utf-8")
            (direct / "generate-agents-md" / "SKILL.md").write_text("stale", encoding="utf-8")
            codes = {issue.code for issue in validate_distribution(source, installed, direct)}
            self.assertIn("installed-content-mismatch", codes)
            self.assertIn("direct-skill-mismatch", codes)

    def test_required_direct_skill_missing_fails_without_forcing_plugin_only_users(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            installed = root / "installed"
            direct = root / "direct"
            shutil.copytree(source, installed)
            shutil.copytree(source / "skills" / "generate-agents-md", direct / "generate-agents-md")
            optional_codes = {issue.code for issue in validate_distribution(source, installed, direct)}
            required_codes = {
                issue.code for issue in validate_distribution(
                    source, installed, direct, require_direct_skills=True,
                )
            }
            self.assertNotIn("missing-direct-skill", optional_codes)
            self.assertIn("missing-direct-skill", required_codes)

    def test_invalid_source_manifest_keeps_json_cli_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            (source / ".codex-plugin").mkdir(parents=True)
            (source / ".codex-plugin" / "plugin.json").write_text("{broken", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "validate_plugin_distribution.py"),
                    "--source-plugin-root", str(source), "--json",
                ],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(1, result.returncode)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertEqual("invalid-plugin-manifest", payload["issues"][0]["code"])
            self.assertNotIn("Traceback", result.stderr)

    def test_manifest_requires_nonempty_string_name_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            installed = root / "installed"
            direct = root / "direct"
            shutil.copytree(source, installed)
            for candidate in (source, installed):
                manifest = candidate / ".codex-plugin" / "plugin.json"
                manifest.write_text(json.dumps({"skills": "./skills/"}), encoding="utf-8")
            codes = {issue.code for issue in validate_distribution(source, installed, direct)}
            self.assertIn("invalid-plugin-manifest", codes)

    def test_package_symlink_is_rejected_even_when_bytes_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            installed = root / "installed"
            direct = root / "direct"
            target = root / "external-skill.md"
            target.write_text("external", encoding="utf-8")
            source_skill = source / "skills" / "generate-agents-md" / "SKILL.md"
            source_skill.unlink()
            source_skill.symlink_to(target)
            shutil.copytree(source, installed, symlinks=False)
            codes = {issue.code for issue in validate_distribution(source, installed, direct)}
            self.assertIn("package-symlink", codes)

    def test_cli_does_not_resolve_away_symlinked_plugin_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._source(root)
            installed = root / "installed-real"
            installed_link = root / "installed-link"
            shutil.copytree(source, installed)
            installed_link.symlink_to(installed, target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT_DIR / "validate_plugin_distribution.py"),
                    "--source-plugin-root", str(source),
                    "--installed-plugin-root", str(installed_link), "--json",
                ],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(1, result.returncode)
            codes = {issue["code"] for issue in json.loads(result.stdout)["issues"]}
            self.assertIn("package-symlink", codes)


if __name__ == "__main__":
    unittest.main()
