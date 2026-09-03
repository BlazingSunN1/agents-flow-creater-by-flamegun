from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_contract import validate_common, validate_kimi, validate_review, write_new_private_file


EXECUTION_PROFILE = {
    "transport": "bounded-sse-v1", "idle_timeout_seconds": 180.0,
    "deadline_seconds": 1800.0, "max_output_tokens": 32768, "retry_limit": 1,
}


def valid_kimi(version: int = 1) -> dict[str, object]:
    return {
        "candidate_version": version,
        "scope_sha256": "a" * 64,
        "artifact": "A complete implementation plan with ordered steps and verification gates.",
        "assumptions": [],
        "acceptance_criteria_mapping": [{
            "criterion": "AC-001",
            "satisfaction": "The complete plan implements the requested workflow.",
            "evidence": "NOT_VERIFIED",
        }],
        "change_map": [] if version == 1 else [{
            "defect_id": "D-001",
            "change": "Corrected the rejected workflow boundary.",
            "verification": "NOT_VERIFIED",
        }],
        "known_limits": [],
    }


def valid_deepseek() -> dict[str, object]:
    return {
        "candidate_version": 1,
        "scope_sha256": "a" * 64,
        "candidate_sha256": "b" * 64,
        "verdict": "pass",
        "defects": [],
        "black_box_tests": [{
            "id": "BB-001",
            "requirement": "REQ-001",
            "behavior": "success",
            "preconditions": ["service is ready"],
            "steps": ["invoke the public entry"],
            "expected": ["visible success result"],
            "evidence_required": ["runtime transcript"],
        }],
        "coverage": ["REQ-001"],
        "uncertainties": [],
    }


class DeepSeekContractTests(unittest.TestCase):
    def test_kimi_requires_criteria_mapping_and_revision_change_map(self) -> None:
        validate_kimi(valid_kimi())
        for value in (valid_kimi(), valid_kimi(2)):
            with self.subTest(version=value["candidate_version"]), self.assertRaises(ValueError):
                field = "acceptance_criteria_mapping" if value["candidate_version"] == 1 else "change_map"
                value[field] = []
                validate_kimi(value)

    def test_kimi_complete_candidate_and_mapping_reject_placeholders(self) -> None:
        for field in ("artifact", "satisfaction"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "complete|concrete"):
                value = valid_kimi()
                if field == "artifact":
                    value["artifact"] = "TODO"
                else:
                    value["acceptance_criteria_mapping"][0]["satisfaction"] = "TODO"
                validate_kimi(value)

    def test_unknown_top_level_fields_are_rejected(self) -> None:
        value = valid_deepseek()
        value["advisory_only"] = True
        with self.assertRaisesRegex(ValueError, "unknown"):
            validate_common(value, "deepseek")

    def test_provider_wrapper_unknown_fields_and_duplicate_json_keys_are_rejected(self) -> None:
        import json
        from tempfile import TemporaryDirectory

        from validate_contract import load_contract

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "raw.json"
            path.write_text(json.dumps({
                "provider": "deepseek", "request_model": "deepseek-v4-pro",
                "model": "deepseek-v4-pro", "content": json.dumps(valid_deepseek()),
                "usage": None, "response_id": None, "finish_reason": "stop", "untrusted": True,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact"):
                load_contract(path, "deepseek")
            path.write_text('{"candidate_version":1,"candidate_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_contract(path, "gpt")

    def test_pass_requires_structured_black_box_tests(self) -> None:
        validate_review(valid_deepseek(), "deepseek")
        for cases in ([], [{"id": "BB-001"}]):
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                value = valid_deepseek()
                value["black_box_tests"] = cases
                validate_review(value, "deepseek")

    def test_black_box_ids_and_observable_lists_are_strict(self) -> None:
        value = valid_deepseek()
        value["black_box_tests"][0]["steps"] = []
        with self.assertRaisesRegex(ValueError, "steps"):
            validate_review(value, "deepseek")

    def test_pass_requires_deepseek_coverage_and_gpt_independent_checks(self) -> None:
        deepseek = valid_deepseek()
        deepseek["coverage"] = []
        with self.assertRaisesRegex(ValueError, "coverage"):
            validate_review(deepseek, "deepseek")
        gpt = {
            "candidate_version": 1,
            "scope_sha256": "a" * 64,
            "candidate_sha256": "b" * 64,
            "deepseek_review_sha256": "c" * 64,
            "verdict": "pass",
            "deepseek_adjudication": [],
            "additional_defects": [],
            "independent_checks": [],
            "blockers": [],
        }
        with self.assertRaisesRegex(ValueError, "independent"):
            validate_review(gpt, "gpt")
        gpt["independent_checks"] = ["No independent checks were performed."]
        with self.assertRaisesRegex(ValueError, "exact required"):
            validate_review(gpt, "gpt")

    def test_deepseek_wrapper_cannot_impersonate_active_gpt(self) -> None:
        import json
        from tempfile import TemporaryDirectory

        from validate_contract import load_contract

        value = {
            "candidate_version": 1, "scope_sha256": "a" * 64,
            "candidate_sha256": "b" * 64, "deepseek_review_sha256": "c" * 64,
            "verdict": "pass", "deepseek_adjudication": [], "additional_defects": [],
            "independent_checks": [{
                "check_id": "CHK-001", "method": "Inspected the candidate",
                "evidence_path": "/tmp/check.json", "evidence_sha256": "d" * 64,
                "status": "passed",
            }], "blockers": [],
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "raw.json"
            path.write_text(json.dumps({
                "provider": "deepseek", "request_model": "deepseek-v4-pro",
                "model": "deepseek-v4-pro", "content": json.dumps(value),
                "usage": None, "response_id": "r", "finish_reason": "stop",
                **EXECUTION_PROFILE,
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "active Codex"):
                load_contract(path, "gpt")

    def test_private_output_writer_never_follows_existing_symlink(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            victim, output = root / "victim.txt", root / "output.json"
            victim.write_text("preserved", encoding="utf-8")
            output.symlink_to(victim)
            with self.assertRaises(FileExistsError):
                write_new_private_file(output, "replacement")
            self.assertEqual("preserved", victim.read_text(encoding="utf-8"))

    def test_private_output_is_not_published_when_durability_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output.json"
            with patch("validate_contract.os.fsync", side_effect=OSError("synthetic fsync failure")):
                with self.assertRaisesRegex(OSError, "synthetic"):
                    write_new_private_file(output, "complete payload")
            self.assertFalse(output.exists())
            self.assertEqual([], list(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
