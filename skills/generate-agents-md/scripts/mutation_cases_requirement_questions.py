from __future__ import annotations


REQUIREMENT_QUESTION_MUTANT_CASES = (
    (
        "question-safe-default-check-disabled",
        "scripts/validate_requirement_questions.py",
        '        if not isinstance(value.get(field), str) or not str(value[field]).strip():\n',
        "        if False:\n",
        "scripts.test_validate_requirement_questions.RequirementQuestionValidatorTests.test_unanswered_question_requires_explicit_default_fallback_and_assumption",
    ),
    (
        "question-non-blocking-p2-disposition-check-disabled",
        "scripts/validate_requirement_questions.py",
        '    if value.get("delivery_disposition") != "NON_BLOCKING_P2":\n',
        "    if False:\n",
        "scripts.test_validate_requirement_questions.RequirementQuestionValidatorTests.test_question_fields_are_closed_and_required",
    ),
    (
        "answered-question-rerun-check-disabled",
        "scripts/validate_requirement_questions.py",
        '            if not _current_rerun(rerun, question, baseline_version, baseline_sha):\n',
        "            if False:\n",
        "scripts.test_validate_requirement_questions.RequirementQuestionValidatorTests.test_answer_requires_current_baseline_and_affected_gate_rerun",
    ),
    (
        "answered-question-baseline-change-check-disabled",
        "scripts/validate_requirement_questions.py",
        '    if pre_version == baseline_version or pre_sha == baseline_sha:\n',
        '    if False:\n',
        "scripts.test_validate_requirement_questions.RequirementQuestionValidatorTests.test_answered_requires_human_evidence_baseline_change_and_closed_receipt",
    ),
    (
        "answered-question-evidence-binding-check-disabled",
        "scripts/validate_requirement_questions.py",
        '    if evidence is None:\n        issues.append(Issue("error", "invalid-answer-evidence", "人工答案证据 locator/SHA 必须指向项目内封闭 JSON"))\n',
        '    if False:\n        issues.append(Issue("error", "invalid-answer-evidence", "人工答案证据 locator/SHA 必须指向项目内封闭 JSON"))\n',
        "scripts.test_validate_requirement_questions.RequirementQuestionValidatorTests.test_answer_and_rerun_evidence_are_bound_and_allow_local_coordination",
    ),
    (
        "answered-question-strict-verifier-check-disabled",
        "scripts/validate_requirement_questions.py",
        '            elif not _verified_rerun(rerun, project_root, verifier):\n',
        '            elif False:\n',
        "scripts.test_validate_requirement_questions.RequirementQuestionValidatorTests.test_strict_verifier_rejection_blocks_answered_rerun",
    ),
)
