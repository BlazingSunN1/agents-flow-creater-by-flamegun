from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clarification_validation import apply_default_assumptions, validate_clarification_register
from test_validate_loop_bundle import valid_bundle, valid_scope
from validate_loop_bundle import validate_bundle, validate_scope


def open_register() -> dict[str, object]:
    return {
        "schema_version": 1,
        "draft_objective": "Build a stable review workflow.",
        "resolved_objective": "Build a review workflow that blocks delivery on failed review.",
        "no_questions_reason": "NOT_APPLICABLE",
        "questions": [{
            "id": "Q-001", "priority": "P0", "topic": "acceptance",
            "question": "Must failed external review block delivery?",
            "why_needed": "This changes the terminal status and acceptance gate.",
            "proposed_default": "Yes, failed review blocks delivery.",
            "risk_if_wrong": "Delivery may be delayed until the assumption is corrected.",
            "human_answer": "PENDING", "status": "open",
            "resolution_source": "PENDING",
            "objective_update": "Build a review workflow that blocks delivery on failed review.",
            "criterion_updates": [{
                "criterion_id": "AC-001",
                "final_text": "A failed external review blocks delivery.",
            }],
        }],
    }


def resolved_register() -> dict[str, object]:
    value = open_register()
    value["resolved_objective"] = "Build a review workflow that blocks delivery on failed review."
    question = value["questions"][0]
    question.update({
        "human_answer": "Yes, any failed reviewer blocks delivery.",
        "status": "answered",
        "resolution_source": "human",
        "objective_update": value["resolved_objective"],
        "criterion_updates": [{
            "criterion_id": "AC-001",
            "final_text": "A failed external review blocks delivery.",
        }],
    })
    return value


class ClarificationValidatorTests(unittest.TestCase):
    def test_draft_register_allows_open_human_questions(self) -> None:
        validate_clarification_register(open_register(), allow_open=True)

    def test_missing_human_answer_becomes_auditable_nonblocking_assumption(self) -> None:
        register = apply_default_assumptions(open_register())
        self.assertEqual("assumed", register["questions"][0]["status"])
        self.assertEqual("NOT_PROVIDED", register["questions"][0]["human_answer"])
        scope = valid_scope()
        scope["objective"] = register["resolved_objective"]
        scope["acceptance_criteria"][0]["text"] = "A failed external review blocks delivery."
        scope["clarification_register"] = register
        validate_scope(scope)

    def test_final_scope_requires_resolved_answers_and_exact_updates(self) -> None:
        scope = valid_scope()
        scope["objective"] = "Build a review workflow that blocks delivery on failed review."
        scope["acceptance_criteria"][0]["text"] = "A failed external review blocks delivery."
        scope["clarification_register"] = resolved_register()
        validate_scope(scope)

        scope["clarification_register"] = open_register()
        with self.assertRaisesRegex(ValueError, "open|resolved"):
            validate_scope(scope)

    def test_placeholder_answer_and_unmapped_requirement_change_fail_closed(self) -> None:
        register = resolved_register()
        register["questions"][0]["human_answer"] = "TBD"
        with self.assertRaisesRegex(ValueError, "answer"):
            validate_clarification_register(
                register, allow_open=False,
                criteria={"AC-001": "A failed external review blocks delivery."},
            )

        register = resolved_register()
        register["questions"][0]["criterion_updates"][0]["criterion_id"] = "AC-999"
        with self.assertRaisesRegex(ValueError, "criterion"):
            validate_clarification_register(register, allow_open=False, criteria={"AC-001": "text"})

    def test_answered_objective_must_equal_the_final_scope_objective(self) -> None:
        scope = valid_scope()
        scope["acceptance_criteria"][0]["text"] = "A failed external review blocks delivery."
        scope["clarification_register"] = resolved_register()
        with self.assertRaisesRegex(ValueError, "objective"):
            validate_scope(scope)

    def test_late_human_answer_invalidates_prior_candidate_and_reviews(self) -> None:
        scope, kimi, deepseek, gpt = valid_bundle()
        scope["objective"] = "Build a review workflow that blocks delivery on failed review."
        scope["acceptance_criteria"][0]["text"] = "A failed external review blocks delivery."
        scope["clarification_register"] = resolved_register()
        with self.assertRaisesRegex(ValueError, "scope"):
            validate_bundle(scope, kimi, deepseek, gpt)


if __name__ == "__main__":
    unittest.main()
