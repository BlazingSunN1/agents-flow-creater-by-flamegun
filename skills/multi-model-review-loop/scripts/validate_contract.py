#!/usr/bin/env python3
"""Validate and normalize review-loop JSON contracts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED = {
    "kimi": {
        "candidate_version",
        "scope_sha256",
        "artifact",
        "assumptions",
        "acceptance_criteria_mapping",
        "change_map",
        "known_limits",
    },
    "deepseek": {
        "candidate_version",
        "scope_sha256",
        "candidate_sha256",
        "verdict",
        "defects",
        "black_box_tests",
        "coverage",
        "uncertainties",
    },
    "gpt": {
        "candidate_version",
        "scope_sha256",
        "candidate_sha256",
        "deepseek_review_sha256",
        "verdict",
        "deepseek_adjudication",
        "additional_defects",
        "independent_checks",
        "blockers",
    },
}
HASH_FIELDS = {
    "kimi": ("scope_sha256",),
    "deepseek": ("scope_sha256", "candidate_sha256"),
    "gpt": ("scope_sha256", "candidate_sha256", "deepseek_review_sha256"),
}
PROVIDER_WRAPPER_FIELDS = {
    "provider", "request_model", "model", "content", "usage", "response_id",
    "finish_reason",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", choices=sorted(REQUIRED))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def strict_json_loads(payload: str) -> Any:
    return json.loads(
        payload,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON number: {value}")),
    )


def write_new_private_file(path: Path, payload: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
        directory_flags |= os.O_NOFOLLOW
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    parent = os.open(path.parent, directory_flags)
    try:
        descriptor = os.open(path.name, flags, 0o600, dir_fd=parent)
        try:
            data = payload.encode("utf-8")
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def load_contract(path: Path, contract: str | None = None) -> dict[str, Any]:
    outer = strict_json_loads(path.read_text("utf-8"))
    content = outer.get("content") if isinstance(outer, dict) else None
    if content is not None:
        if set(outer) != PROVIDER_WRAPPER_FIELDS:
            raise ValueError("provider wrapper must use the exact required fields")
        if contract == "gpt":
            raise ValueError("GPT contract must be authored locally by active Codex, not a provider wrapper")
        if outer.get("provider") != contract:
            raise ValueError(f"provider wrapper must identify {contract}")
        if not isinstance(outer.get("model"), str) or not outer["model"].strip():
            raise ValueError("provider wrapper model must be a non-empty string")
        if not isinstance(outer.get("request_model"), str) or not outer["request_model"].strip():
            raise ValueError("provider wrapper request_model must be a non-empty string")
        if outer.get("finish_reason") != "stop":
            raise ValueError("provider wrapper finish_reason must be stop")
    value = strict_json_loads(content) if isinstance(content, str) else outer
    if not isinstance(value, dict):
        raise ValueError("contract must be one JSON object")
    return value


def require_list(value: dict[str, Any], name: str) -> None:
    if not isinstance(value.get(name), list):
        raise ValueError(f"{name} must be an array")


def require_string_list(value: dict[str, Any], name: str, *, nonempty: bool = False) -> None:
    require_list(value, name)
    items = value[name]
    if nonempty and not items:
        raise ValueError(f"{name} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError(f"{name} must contain only non-empty strings")


def validate_independent_checks(value: dict[str, Any]) -> None:
    fields = {"check_id", "method", "evidence_path", "evidence_sha256", "status"}
    checks = value.get("independent_checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("independent_checks must contain structured executed checks")
    identifiers: list[str] = []
    methods: list[str] = []
    for item in checks:
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("independent_checks entries must use the exact required fields")
        if any(not isinstance(item[field], str) or not item[field].strip() for field in fields):
            raise ValueError("independent_checks entries must contain non-empty strings")
        if not item["check_id"].startswith("CHK-") or item["status"] not in {"passed", "failed"}:
            raise ValueError("independent check ID or status is invalid")
        if item["method"] not in GPT_CHECK_METHODS:
            raise ValueError("independent check method is not a supported native review method")
        digest = item["evidence_sha256"]
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("independent check evidence_sha256 must be a lowercase SHA-256")
        identifiers.append(item["check_id"])
        methods.append(item["method"])
    if len(identifiers) != len(set(identifiers)) or len(methods) != len(set(methods)):
        raise ValueError("independent check IDs and methods must be unique")


def validate_object_list(value: dict[str, Any], name: str, fields: set[str]) -> None:
    require_list(value, name)
    for item in value[name]:
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError(f"{name} entries must use the exact required fields")
        if any(not isinstance(item[field], str) or not item[field].strip() for field in fields):
            raise ValueError(f"{name} entries must contain non-empty strings")


def validate_defects(value: dict[str, Any], name: str) -> None:
    validate_object_list(value, name, DEFECT_FIELDS)
    identifiers = [item["id"] for item in value[name]]
    prefix = "D-" if name == "defects" else "G-"
    if len(identifiers) != len(set(identifiers)) or any(not item.startswith(prefix) for item in identifiers):
        raise ValueError(f"{name} IDs must be unique {prefix}* strings")
    if any(item["severity"] not in {"P0", "P1", "P2", "P3"} for item in value[name]):
        raise ValueError(f"{name} severity must be P0, P1, P2, or P3")


def validate_adjudications(value: dict[str, Any]) -> None:
    validate_object_list(value, "deepseek_adjudication", ADJUDICATION_FIELDS)
    entries = value["deepseek_adjudication"]
    identifiers = [item["defect_id"] for item in entries]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("deepseek_adjudication defect IDs must be unique")
    if any(item["decision"] not in {"accepted", "rejected"} for item in entries):
        raise ValueError("deepseek_adjudication decision must be accepted or rejected")


def validate_common(value: dict[str, Any], contract: str) -> None:
    missing = sorted(REQUIRED[contract] - value.keys())
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    extra = sorted(value.keys() - REQUIRED[contract])
    if extra:
        raise ValueError(f"unknown fields: {', '.join(extra)}")
    version = value.get("candidate_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("candidate_version must be a positive integer")
    for field in HASH_FIELDS[contract]:
        raw = value.get(field)
        if not isinstance(raw, str) or len(raw) != 64 or any(c not in "0123456789abcdef" for c in raw):
            raise ValueError(f"{field} must be a lowercase SHA-256")


def validate_kimi(value: dict[str, Any]) -> None:
    artifact = value.get("artifact")
    if not isinstance(artifact, str) or not artifact.strip() or re.fullmatch(
        r"^(?:TODO|TBD|FIXME|N/?A|NOT_VERIFIED|NOT_APPLICABLE|partial patch only)$",
        artifact.strip(), re.IGNORECASE,
    ):
        raise ValueError("artifact must be a complete non-placeholder candidate")
    require_string_list(value, "assumptions")
    require_string_list(value, "known_limits")
    validate_object_list(
        value, "acceptance_criteria_mapping", {"criterion", "satisfaction", "evidence"},
    )
    if not value["acceptance_criteria_mapping"]:
        raise ValueError("acceptance_criteria_mapping must not be empty")
    if any(re.fullmatch(
        r"TODO|TBD|FIXME|N/?A|NOT_VERIFIED|NOT_APPLICABLE", item["satisfaction"].strip(), re.IGNORECASE,
    ) for item in value["acceptance_criteria_mapping"]):
        raise ValueError("acceptance criteria satisfaction must be concrete and non-placeholder")
    validate_object_list(value, "change_map", {"defect_id", "change", "verification"})
    if value["candidate_version"] > 1 and not value["change_map"]:
        raise ValueError("a revised candidate must contain a non-empty change_map")


def validate_review(value: dict[str, Any], contract: str) -> None:
    if value.get("verdict") not in {"pass", "fail"}:
        raise ValueError("verdict must be pass or fail")
    fields = (
        ("defects", "black_box_tests", "coverage", "uncertainties")
        if contract == "deepseek"
        else ("deepseek_adjudication", "additional_defects", "independent_checks", "blockers")
    )
    for field in fields:
        require_list(value, field)
    blocking = ("defects", "uncertainties") if contract == "deepseek" else ("additional_defects", "blockers")
    accepted = contract == "gpt" and any(
        isinstance(item, dict) and item.get("decision") == "accepted"
        for item in value.get("deepseek_adjudication", [])
    )
    has_blocking = any(value[field] for field in blocking) or accepted
    if value["verdict"] == "pass" and has_blocking:
        raise ValueError("pass verdict cannot contain defects, uncertainties, or blockers")
    if value["verdict"] == "fail" and not has_blocking:
        raise ValueError("fail verdict must contain a defect, uncertainty, or blocker")
    if contract == "deepseek":
        validate_black_box_tests(value["black_box_tests"])
        require_string_list(value, "coverage", nonempty=value["verdict"] == "pass")
        validate_defects(value, "defects")
        require_string_list(value, "uncertainties")
    else:
        validate_adjudications(value)
        validate_defects(value, "additional_defects")
        validate_independent_checks(value)
        if value["verdict"] == "pass" and any(
            item["status"] != "passed" for item in value["independent_checks"]
        ):
            raise ValueError("pass verdict requires every independent check to pass")
        if value["verdict"] == "pass" and {item["method"] for item in value["independent_checks"]} != GPT_CHECK_METHODS:
            raise ValueError("pass verdict requires candidate inspection and DeepSeek coverage review")
        require_string_list(value, "blockers")


def validate_black_box_tests(cases: list[Any]) -> None:
    required = {
        "id", "requirement", "behavior", "preconditions", "steps", "expected",
        "evidence_required",
    }
    if not cases:
        raise ValueError("DeepSeek must author at least one black-box test")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError("black-box tests must use the exact required fields")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("BB-") or identifier in seen:
            raise ValueError("black-box test IDs must be unique BB-* strings")
        seen.add(identifier)
        if not isinstance(case.get("requirement"), str) or not case["requirement"].strip():
            raise ValueError("black-box requirement must be non-empty")
        if case.get("behavior") not in BEHAVIORS:
            raise ValueError("black-box behavior must be a supported behavior category")
        for field in ("preconditions", "steps", "expected", "evidence_required"):
            if not isinstance(case.get(field), list) or not case[field] or any(
                not isinstance(item, str) or not item.strip() for item in case[field]
            ):
                raise ValueError(f"black-box {field} must be a non-empty string array")


DEFECT_FIELDS = {
    "id", "severity", "criterion", "location", "evidence", "impact", "correction",
    "verification",
}
ADJUDICATION_FIELDS = {"defect_id", "decision", "reason"}
BEHAVIORS = {"success", "rejection", "failure", "retry", "recovery", "permission", "boundary"}
GPT_CHECK_METHODS = {"candidate-inspection", "deepseek-coverage-review"}


def main() -> int:
    args = parse_args()
    try:
        value = load_contract(args.input, args.contract)
        validate_common(value, args.contract)
        validate_kimi(value) if args.contract == "kimi" else validate_review(value, args.contract)
        output = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_new_private_file(args.output, output)
        else:
            sys.stdout.write(output)
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"contract validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
