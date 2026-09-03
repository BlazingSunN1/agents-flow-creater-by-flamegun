"""Strict clarification-register validation shared by scope and CLI gates."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


REGISTER_FIELDS = {
    "schema_version", "draft_objective", "resolved_objective",
    "no_questions_reason", "questions",
}
QUESTION_FIELDS = {
    "id", "priority", "topic", "question", "why_needed", "human_answer",
    "proposed_default", "risk_if_wrong", "resolution_source", "status",
    "objective_update", "criterion_updates",
}
UPDATE_FIELDS = {"criterion_id", "final_text"}
PLACEHOLDER = re.compile(r"^(?:PENDING|TODO|TBD|N/?A|UNKNOWN|UNANSWERED)$", re.IGNORECASE)
PRIORITIES = {"P0": 0, "P1": 1, "P2": 2}


def _text(value: Any, label: str, *, allow_placeholder: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"clarification {label} must be a non-empty string")
    text = value.strip()
    if not allow_placeholder and PLACEHOLDER.fullmatch(text):
        raise ValueError(f"clarification {label} must not be a placeholder")
    return text


def _criterion_updates(value: Any, criteria: dict[str, str] | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("clarification criterion_updates must be an array")
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != UPDATE_FIELDS:
            raise ValueError("clarification criterion update must use the exact fields")
        identifier = _text(item.get("criterion_id"), "criterion ID")
        final_text = _text(item.get("final_text"), "criterion final text")
        if criteria is not None and criteria.get(identifier) != final_text:
            raise ValueError("clarification criterion update is missing from the final scope")
        identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("clarification criterion updates must be unique")
    return value


def _validate_question(
    item: Any, allow_open: bool, criteria: dict[str, str] | None,
    resolved_objective: str,
) -> tuple[str, int, bool]:
    if not isinstance(item, dict) or set(item) != QUESTION_FIELDS:
        raise ValueError("clarification question must use the exact required fields")
    identifier = _text(item.get("id"), "question ID")
    if not re.fullmatch(r"Q-[0-9]{3}", identifier):
        raise ValueError("clarification question ID must use Q-NNN")
    priority = item.get("priority")
    if priority not in PRIORITIES:
        raise ValueError("clarification priority must be P0, P1, or P2")
    for field in ("topic", "question", "why_needed", "proposed_default", "risk_if_wrong"):
        _text(item.get(field), field)
    status = item.get("status")
    if status not in {"open", "answered", "assumed", "confirmed", "dismissed"}:
        raise ValueError("clarification status is invalid")
    updates = _criterion_updates(item.get("criterion_updates"), criteria)
    objective_update = _text(item.get("objective_update"), "objective update", allow_placeholder=True)
    changes_objective = objective_update not in {"NO_CHANGE", "PENDING"}
    if status == "open":
        if not allow_open or item.get("human_answer") != "PENDING" \
                or item.get("resolution_source") != "PENDING":
            raise ValueError("open clarification must identify a pending human response")
        if objective_update == "PENDING" and not updates:
            raise ValueError("open clarification must include a non-blocking default scope update")
        if changes_objective and objective_update != resolved_objective:
            raise ValueError("clarification default objective differs from the resolved objective")
        return identifier, PRIORITIES[priority], changes_objective
    if status == "assumed":
        if item.get("human_answer") != "NOT_PROVIDED" or item.get("resolution_source") != "ai_assumption":
            raise ValueError("assumed clarification must disclose the missing human answer")
    else:
        _text(item.get("human_answer"), "human answer")
        if item.get("resolution_source") != "human":
            raise ValueError("human-resolved clarification must identify its resolution source")
    objective_update = _text(item.get("objective_update"), "objective update")
    if status in {"confirmed", "dismissed"} and (objective_update != "NO_CHANGE" or updates):
        raise ValueError("confirmed or dismissed clarification cannot silently change scope")
    if status == "answered" and objective_update == "NO_CHANGE" and not updates:
        raise ValueError("answered clarification must map to an objective or criterion update")
    changes_objective = objective_update != "NO_CHANGE"
    if changes_objective and objective_update != resolved_objective:
        raise ValueError("clarification objective update differs from the resolved objective")
    return identifier, PRIORITIES[priority], changes_objective


def validate_clarification_register(
    value: Any, *, allow_open: bool, criteria: dict[str, str] | None = None,
) -> None:
    if not isinstance(value, dict) or set(value) != REGISTER_FIELDS \
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("clarification register must use the exact schema_version 1 fields")
    draft = _text(value.get("draft_objective"), "draft objective")
    resolved = _text(value.get("resolved_objective"), "resolved objective", allow_placeholder=allow_open)
    questions = value.get("questions")
    if not isinstance(questions, list) or len(questions) > 12:
        raise ValueError("clarification questions must be a bounded array")
    reason = _text(value.get("no_questions_reason"), "no-questions reason", allow_placeholder=True)
    if questions and reason != "NOT_APPLICABLE":
        raise ValueError("clarification register with questions must use NOT_APPLICABLE reason")
    if not questions and PLACEHOLDER.fullmatch(reason):
        raise ValueError("empty clarification register requires a concrete no-questions reason")
    results = [_validate_question(item, allow_open, criteria, resolved) for item in questions]
    identifiers, priorities = [item[0] for item in results], [item[1] for item in results]
    if len(identifiers) != len(set(identifiers)) or priorities != sorted(priorities):
        raise ValueError("clarification questions must have unique IDs and priority order")
    if not allow_open and any(item.get("status") == "open" for item in questions):
        raise ValueError("final clarification register cannot contain open questions")
    objective_changed = any(item[2] for item in results)
    if (draft != resolved) != objective_changed:
        raise ValueError("resolved objective must be explained by an answered clarification")


def apply_default_assumptions(value: Any) -> dict[str, Any]:
    validate_clarification_register(value, allow_open=True)
    resolved = deepcopy(value)
    for item in resolved["questions"]:
        if item["status"] == "open":
            item["status"] = "assumed"
            item["human_answer"] = "NOT_PROVIDED"
            item["resolution_source"] = "ai_assumption"
    validate_clarification_register(resolved, allow_open=False)
    return resolved
