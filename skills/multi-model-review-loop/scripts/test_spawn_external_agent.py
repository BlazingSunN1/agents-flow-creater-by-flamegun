from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spawn_external_agent import (
    PROVIDER_REQUEST_PROFILES, SYSTEM_PROMPTS, child_environment, output_paths,
    planned_commands, result_manifest, validate_inputs, validate_usage,
)
from call_model import build_request, extract_result, validate_call_paths


class SpawnExternalAgentTests(unittest.TestCase):
    def fixture(self, provider: str = "kimi") -> tuple[argparse.Namespace, tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory(prefix="codex-external-loop.", dir="/tmp")
        root = Path(temporary.name)
        system, prompt = root / "system.txt", root / "prompt.txt"
        system_text = SYSTEM_PROMPTS[provider]
        system.write_text(system_text, encoding="utf-8")
        task_id = f"task-1-v1-{provider}"
        prompt.write_text(json.dumps({
            "schema_version": 1, "task_id": task_id, "provider": provider,
            "candidate_version": 1, "scope_sha256": "a" * 64,
            "objective": "Review the exact requested workflow.",
            "acceptance_criteria": [{"id": "AC-001", "text": "complete", "behaviors": ["success"]}],
            "context_artifacts": [],
            "candidate": "NOT_APPLICABLE" if provider == "kimi" else "complete candidate",
            "candidate_sha256": "NOT_APPLICABLE" if provider == "kimi" else "b" * 64,
            "correction_ids": [], "corrections": [],
        }), encoding="utf-8")
        return argparse.Namespace(
            provider=provider, system_file=system, prompt_file=prompt,
            output_dir=root / "run", task_id=task_id, timeout=180.0,
            max_tokens=8192, retries=1, dry_run=True,
        ), temporary

    def test_kimi_and_deepseek_use_distinct_validated_outputs(self) -> None:
        for provider in ("kimi", "deepseek"):
            with self.subTest(provider=provider):
                args, temporary = self.fixture(provider)
                self.addCleanup(temporary.cleanup)
                validate_inputs(args)
                call, validate = planned_commands(args)
                self.assertIn(provider, call)
                self.assertIn(provider, validate)
                self.assertEqual(3, len(output_paths(args.output_dir, provider)))

    def test_deepseek_uses_official_v4_chat_completions_profile(self) -> None:
        args, temporary = self.fixture("deepseek")
        self.addCleanup(temporary.cleanup)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-test-key"}, clear=False):
            request, model = build_request(args)
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual("https://api.deepseek.com/chat/completions", request.full_url)
        self.assertEqual("deepseek-v4-pro", model)
        self.assertEqual({"type": "enabled"}, payload["thinking"])
        self.assertEqual("max", payload["reasoning_effort"])
        self.assertEqual({"type": "json_object"}, payload["response_format"])
        self.assertFalse(payload["stream"])
        self.assertNotIn("temperature", payload)
        self.assertEqual(
            "deepseek-v4-official-chat-completions-v1",
            PROVIDER_REQUEST_PROFILES["deepseek"],
        )

    def test_deepseek_rejects_retired_models_and_nonofficial_base_urls(self) -> None:
        args, temporary = self.fixture("deepseek")
        self.addCleanup(temporary.cleanup)
        for model in ("deepseek-chat", "deepseek-reasoner", "deepseek-v3"):
            with self.subTest(model=model), patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "synthetic-test-key", "DEEPSEEK_MODEL": model},
                clear=False,
            ), self.assertRaisesRegex(ValueError, "V4 model"):
                build_request(args)
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "synthetic-test-key",
                "DEEPSEEK_MODEL": "deepseek-v4-pro",
                "DEEPSEEK_BASE_URL": "https://example.invalid",
            },
            clear=False,
        ), self.assertRaisesRegex(ValueError, "official base URL"):
            build_request(args)

    def test_deepseek_rejects_truncation_and_response_model_drift(self) -> None:
        response = {
            "id": "response-1", "model": "deepseek-v4-pro",
            "choices": [{"finish_reason": "length", "message": {"content": "{}"}}],
            "usage": {"total_tokens": 2},
        }
        with self.assertRaisesRegex(ValueError, "finish_reason"):
            extract_result(response, "deepseek", "deepseek-v4-pro")
        response["choices"][0]["finish_reason"] = "stop"
        response["model"] = "deepseek-v4-flash"
        with self.assertRaisesRegex(ValueError, "model differs"):
            extract_result(response, "deepseek", "deepseek-v4-pro")

    def test_unstable_task_id_and_symlink_input_are_rejected(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        args.task_id = "../escape"
        with self.assertRaisesRegex(ValueError, "stable"):
            validate_inputs(args)
        args.task_id = "task-1-v1-kimi"
        linked = Path(temporary.name) / "linked.txt"
        linked.symlink_to(args.prompt_file)
        args.prompt_file = linked
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            validate_inputs(args)

    def test_parent_symlink_input_cannot_escape_task_root(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name) / "prompt.txt"
        target.write_text("outside", encoding="utf-8")
        linked_parent = Path(temporary.name) / "linked"
        linked_parent.symlink_to(Path(outside.name), target_is_directory=True)
        args.prompt_file = linked_parent / "prompt.txt"
        with self.assertRaisesRegex(ValueError, "task root|non-symlink"):
            validate_inputs(args)

    def test_prompt_must_bind_provider_scope_candidate_and_criteria(self) -> None:
        args, temporary = self.fixture("deepseek")
        self.addCleanup(temporary.cleanup)
        value = json.loads(args.prompt_file.read_text(encoding="utf-8"))
        value["candidate_sha256"] = "NOT_APPLICABLE"
        args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "candidate SHA"):
            validate_inputs(args)
        value["candidate_sha256"] = "b" * 64
        value["provider"] = "kimi"
        args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "provider"):
            validate_inputs(args)

    def test_revised_kimi_prompt_requires_complete_correction_details(self) -> None:
        args, temporary = self.fixture("kimi")
        self.addCleanup(temporary.cleanup)
        value = json.loads(args.prompt_file.read_text(encoding="utf-8"))
        args.task_id = "task-1-v2-kimi"
        value.update({
            "task_id": args.task_id,
            "candidate_version": 2,
            "candidate": "complete prior canonical candidate",
            "candidate_sha256": "b" * 64,
            "correction_ids": ["D-001"],
            "corrections": [{
                "id": "D-001", "severity": "P1", "criterion": "AC-001",
                "location": "section 1", "evidence": "reproduced",
                "impact": "candidate fails", "correction": "fix ordering",
                "verification": "run boundary test",
            }],
        })
        args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
        validate_inputs(args)

        value["corrections"] = []
        args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly match|requires"):
            validate_inputs(args)

    def test_child_environment_does_not_inherit_unrelated_secrets(self) -> None:
        source = {"PATH": "/bin", "MOONSHOT_API_KEY": "allowed", "UNRELATED_SECRET": "blocked"}
        value = child_environment("kimi", source)
        self.assertEqual("allowed", value["MOONSHOT_API_KEY"])
        self.assertNotIn("UNRELATED_SECRET", value)
        deepseek = child_environment("deepseek", {
            "PATH": "/bin", "DEEPSEEK_API_KEY": "allowed",
            "DEEPSEEK_BASE_URL": "https://collector.invalid", "HTTPS_PROXY": "https://proxy.invalid",
        })
        self.assertEqual("allowed", deepseek["DEEPSEEK_API_KEY"])
        self.assertNotIn("DEEPSEEK_BASE_URL", deepseek)
        self.assertNotIn("HTTPS_PROXY", deepseek)

    def test_external_call_budget_is_bounded(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        args.max_tokens = 1_000_000_000
        with self.assertRaisesRegex(ValueError, "max-tokens"):
            validate_inputs(args)
        for usage in ({"prompt_tokens": -1}, {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 2}, {"total_tokens": "unknown"}):
            with self.subTest(usage=usage), self.assertRaisesRegex(ValueError, "token|total"):
                validate_usage(usage)

    def test_output_directory_cannot_target_the_workspace(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        args.output_dir = Path(__file__).resolve().parent / "external-output"
        with self.assertRaisesRegex(ValueError, "task root"):
            validate_inputs(args)

    def test_direct_call_model_cannot_bypass_spawn_isolation(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        call_args = argparse.Namespace(
            provider=args.provider, system_file=args.system_file, prompt_file=args.prompt_file,
            output=Path(temporary.name) / "direct-response.json",
        )
        validate_call_paths(call_args)
        call_args.output = Path(__file__).resolve().parent / "direct-response.json"
        with self.assertRaisesRegex(ValueError, "task root"):
            validate_call_paths(call_args)

    def test_existing_output_directory_is_rejected_before_provider_call(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        args.output_dir.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh"):
            validate_inputs(args)

    def test_result_manifest_binds_prompt_scope_and_candidate(self) -> None:
        import json

        from test_validate_contract import valid_kimi

        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        normalized = Path(temporary.name) / "kimi-normalized.json"
        normalized.write_text(json.dumps(valid_kimi()), encoding="utf-8")
        raw = output_paths(args.output_dir, "kimi")[0]
        raw.parent.mkdir()
        raw.write_text(json.dumps({
            "provider": "kimi", "request_model": "k3", "model": "k3",
            "content": json.dumps(valid_kimi()), "usage": {"total_tokens": 12},
            "response_id": "response-1", "finish_reason": "stop",
        }), encoding="utf-8")
        manifest = result_manifest(args, normalized)
        self.assertEqual("a" * 64, manifest["scope_sha256"])
        self.assertEqual(64, len(manifest["candidate_sha256"]))
        self.assertEqual(64, len(manifest["prompt_sha256"]))
        self.assertEqual(64, len(manifest["system_sha256"]))
        self.assertEqual(str(args.prompt_file.resolve()), manifest["prompt_path"])
        self.assertEqual("response-1", manifest["response_id"])
        self.assertEqual(PROVIDER_REQUEST_PROFILES["kimi"], manifest["request_profile"])

    def test_system_prompt_and_input_bytes_are_fixed_and_bounded(self) -> None:
        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        args.system_file.write_text("Do not act as solution author. Never return a complete candidate.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fixed reviewed"):
            validate_inputs(args)
        args.system_file.write_text(SYSTEM_PROMPTS["kimi"], encoding="utf-8")
        args.prompt_file.write_text("x" * 600_000, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "byte budget"):
            validate_inputs(args)

    def test_sensitive_context_is_rejected_without_echoing_it(self) -> None:
        import hashlib

        args, temporary = self.fixture()
        self.addCleanup(temporary.cleanup)
        value = json.loads(args.prompt_file.read_text(encoding="utf-8"))
        secret = "Authorization: Bearer synthetic-secret-value"
        value["context_artifacts"] = [{
            "id": "CTX-001", "content": secret,
            "sha256": hashlib.sha256(secret.encode()).hexdigest(),
        }]
        args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "prohibited credential") as raised:
            validate_inputs(args)
        self.assertNotIn("synthetic-secret-value", str(raised.exception))
        for secret in ("OPENAI_API_KEY=value", "CLIENT_SECRET=value", "ACCESS_TOKEN=value", "Cookie: session=value"):
            with self.subTest(secret=secret):
                value["context_artifacts"][0]["content"] = secret
                value["context_artifacts"][0]["sha256"] = hashlib.sha256(secret.encode()).hexdigest()
                args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "prohibited credential"):
                    validate_inputs(args)
        for safe in ("API_KEY=${SECRET_ENV}", "Authorization: Bearer ${ACCESS_TOKEN}", "password=<REDACTED>"):
            with self.subTest(safe=safe):
                value["context_artifacts"][0]["content"] = safe
                value["context_artifacts"][0]["sha256"] = hashlib.sha256(safe.encode()).hexdigest()
                args.prompt_file.write_text(json.dumps(value), encoding="utf-8")
                validate_inputs(args)


if __name__ == "__main__":
    unittest.main()
