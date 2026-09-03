from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from strict_json import loads as strict_json_loads


ALLOWED_STAGES = {"planning", "implementation", "closure_candidate", "completion"}
PLANNER_VERSION = "delivery-gates-v2"
ALLOWED_SURFACES = {
    "internal", "behavior-change", "user-visible", "ui", "api", "mobile", "touch",
    "responsive", "mobile-web", "native-mobile", "public-api", "auth", "security", "privacy", "migration",
    "persistence", "async", "cross-module", "data-schema",
}
STANDARD_SURFACES = {
    "behavior-change", "user-visible", "ui", "api", "mobile", "mobile-web", "native-mobile", "touch", "responsive",
}
FRONTEND_SURFACES = {"ui", "mobile-web", "touch", "responsive"}
MOBILE_WEB_SURFACES = {"mobile", "mobile-web", "touch", "responsive"}
FINAL_AGGREGATE_COMMANDS = {"delivery_contract", "delivery_bundle", "system_delivery_bundle"}
HIGH_RISK_SURFACES = {
    "public-api", "auth", "security", "privacy", "migration", "persistence",
    "async", "cross-module", "data-schema",
}
RISK_ORDER = {"small": 0, "standard": 1, "high-risk": 2}
FLOW_IMPACTS = {"none", "changed", "uncertain"}
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class GatePlanError(ValueError):
    pass


def build_gate_plan(
    change: object, *, stage: str, impact_fingerprint: str,
    command_fingerprints: dict[str, str] | None = None,
) -> dict[str, object]:
    normalized = _validate_inputs(change, stage, impact_fingerprint)
    surfaces = set(normalized["surfaces"])
    risk = str(normalized["risk_level"])
    tier = _validation_tier(risk, stage, bool(normalized["cross_module"]))
    roles = _independent_roles(
        risk, surfaces, stage, bool(normalized["human_review_triggered"]),
    )
    commands = _required_commands(normalized, surfaces, stage, tier, roles)
    commands = sorted(commands)
    aggregate_commands = sorted(set(commands) & FINAL_AGGREGATE_COMMANDS)
    receipt_commands = sorted(set(commands) - FINAL_AGGREGATE_COMMANDS)
    command_fingerprints = command_fingerprints or {}
    core = {
        "schema_version": 1,
        "planner_version": PLANNER_VERSION,
        "validation_tier": tier,
        "required_command_ids": commands,
        "aggregate_command_ids": aggregate_commands,
        "independent_roles": sorted(roles),
        "impact_fingerprint_sha256": impact_fingerprint,
        "gate_input_fingerprints": {
            command_id: hashlib.sha256(_canonical_json({
                "candidate": impact_fingerprint,
                "command_id": command_id,
                "command": command_fingerprints.get(command_id, "unbound"),
                "planner_version": PLANNER_VERSION,
            })).hexdigest()
            for command_id in receipt_commands
        },
        "invalidation_policy": [
            "baseline-or-requirement-change",
            "workset-file-or-dependency-change",
            "code-build-command-rule-config-environment-or-input-change",
        ],
        "reasons": _reasons(normalized, stage, tier),
    }
    plan_sha = hashlib.sha256(_canonical_json(core)).hexdigest()
    return {**core, "plan_sha256": plan_sha}


def compute_impact_fingerprint(contract: object, project_root: Path) -> str:
    if not isinstance(contract, dict):
        raise GatePlanError("contract must be an object")
    root = project_root.resolve()
    baseline = contract.get("baseline")
    artifacts = contract.get("artifacts")
    change = contract.get("change")
    if not isinstance(baseline, dict) or not isinstance(artifacts, dict) or not isinstance(change, dict):
        raise GatePlanError("contract baseline, artifacts and change must be objects")
    linked = {"baseline": _live_ref(baseline, root)}
    linked.update({
        str(key): _live_ref(value, root)
        for key, value in sorted(artifacts.items())
        if key not in {"progress", "command_manifest"}
    })
    file_sets = {
        field: [_live_path(raw, root) for raw in change.get(field, [])]
        for field in ("changed_files", "configuration_files", "input_files")
        if isinstance(change.get(field), list)
    }
    payload = {
        "stage": contract.get("stage"),
        "baseline_version": baseline.get("version"),
        "linked_artifacts": linked,
        "identity": contract.get("identity"),
        "change": change,
        "live_file_sets": file_sets,
        "planner_version": PLANNER_VERSION,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def compute_command_fingerprints(contract: object, project_root: Path) -> dict[str, str]:
    if not isinstance(contract, dict) or not isinstance(contract.get("artifacts"), dict):
        raise GatePlanError("contract artifacts must be an object")
    manifest_ref = contract["artifacts"].get("command_manifest")
    if not isinstance(manifest_ref, dict) or not isinstance(manifest_ref.get("path"), str):
        raise GatePlanError("command manifest reference is invalid")
    manifest_path = _live_path(manifest_ref["path"], project_root.resolve())
    try:
        manifest = strict_json_loads(
            (project_root.resolve() / manifest_path["path"]).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise GatePlanError(f"command manifest is unreadable: {error}") from error
    commands = manifest.get("commands") if isinstance(manifest, dict) else None
    if not isinstance(commands, list):
        raise GatePlanError("command manifest commands must be an array")
    result: dict[str, str] = {}
    for item in commands:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise GatePlanError("command manifest contains an invalid command")
        command_id = item["id"]
        if command_id in result:
            raise GatePlanError(f"duplicate command id: {command_id}")
        result[command_id] = hashlib.sha256(_canonical_json(item)).hexdigest()
    return result


def _validate_inputs(change: object, stage: str, fingerprint: str) -> dict[str, object]:
    if not isinstance(change, dict):
        raise GatePlanError("change must be an object")
    if stage not in ALLOWED_STAGES:
        raise GatePlanError(f"unsupported stage: {stage}")
    if not isinstance(fingerprint, str) or SHA256_RE.fullmatch(fingerprint) is None:
        raise GatePlanError("impact fingerprint must be a lowercase SHA-256")
    risk = change.get("risk_level")
    surfaces = change.get("surfaces")
    flow = change.get("flow_impact")
    booleans = ("frontend_applicable", "swimlane_applicable", "cross_module", "human_review_triggered")
    if risk not in RISK_ORDER or not isinstance(surfaces, list) or not surfaces:
        raise GatePlanError("risk_level or surfaces is invalid")
    if any(type(change.get(field)) is not bool for field in booleans):
        raise GatePlanError("planner flags must be booleans")
    if any(not isinstance(item, str) or item not in ALLOWED_SURFACES for item in surfaces):
        raise GatePlanError("unknown change surface")
    if len(surfaces) != len(set(surfaces)) or flow not in FLOW_IMPACTS:
        raise GatePlanError("duplicate surfaces or invalid flow impact")
    required = "high-risk" if set(surfaces) & HIGH_RISK_SURFACES else (
        "standard" if set(surfaces) & STANDARD_SURFACES else "small"
    )
    if RISK_ORDER[str(risk)] < RISK_ORDER[required]:
        raise GatePlanError(f"risk underclassified: {risk} < {required}")
    if stage == "completion" and flow == "uncertain":
        raise GatePlanError("completion requires resolved flow impact")
    if flow != "none" and change.get("swimlane_applicable") is not True:
        raise GatePlanError("changed or uncertain flow requires swimlane applicability")
    if set(surfaces) & FRONTEND_SURFACES and change.get("frontend_applicable") is not True:
        raise GatePlanError("frontend surfaces require frontend validation")
    surface_set = set(surfaces)
    browser_surface_present = bool(surface_set & FRONTEND_SURFACES or "mobile" in surface_set)
    if (
        "native-mobile" in surface_set
        and change.get("frontend_applicable") is True
        and not browser_surface_present
    ):
        raise GatePlanError("native-mobile cannot be classified as browser frontend")
    return change


def _validation_tier(risk: str, stage: str, cross_module: bool) -> str:
    if risk == "high-risk" or cross_module:
        return "full"
    if stage in {"closure_candidate", "completion"}:
        return "affected"
    return "affected" if risk == "standard" else "quick"


def _independent_roles(
    risk: str, surfaces: set[str], stage: str, human_review_triggered: bool,
) -> set[str]:
    roles: set[str] = set()
    if human_review_triggered:
        roles.add("CHANGE_REVIEW")
    if risk != "small" and stage in {"closure_candidate", "completion"}:
        roles.add("ACCEPTANCE_CASES")
    if risk != "small" and stage == "completion":
        roles.add("BLACK_BOX")
    if risk in {"standard", "high-risk"} and stage in {"closure_candidate", "completion"}:
        roles.add("CHANGE_REVIEW")
    if risk == "high-risk" and stage in {"closure_candidate", "completion"}:
        roles.update({"REQUIREMENT_REVIEW", "SPECIALIST_REVIEW"})
    if "ui" in surfaces and stage in {"closure_candidate", "completion"}:
        roles.add("UI_UX")
    return roles


def _required_commands(
    change: dict[str, object], surfaces: set[str], stage: str, tier: str, roles: set[str],
) -> set[str]:
    commands = {"delivery_contract", "targeted_tests", "code_standards", "traceability", "context_manifest"}
    if tier == "full":
        commands.add("full_test_or_build")
    if change["swimlane_applicable"] and change["flow_impact"] != "none":
        commands.add("swimlane_evidence")
    elif change["swimlane_applicable"] and stage in {"closure_candidate", "completion"}:
        commands.add("swimlane_freshness")
    if roles:
        commands.add("multi_agent_evidence")
    if stage in {"closure_candidate", "completion"} or change["human_review_triggered"]:
        commands.add("automated_review")
    if change["frontend_applicable"] or surfaces & FRONTEND_SURFACES:
        commands.update({"frontend_evidence", "frontend_e2e"})
    if change["frontend_applicable"] and surfaces & MOBILE_WEB_SURFACES:
        commands.add("mobile_frontend_e2e")
    if "native-mobile" in surfaces or ("mobile" in surfaces and not change["frontend_applicable"]):
        commands.add("native_mobile_tests")
    if roles:
        commands.add("delivery_bundle")
    if change["cross_module"] or "cross-module" in surfaces:
        commands.add("system_delivery_bundle")
    return commands


def _reasons(change: dict[str, object], stage: str, tier: str) -> list[str]:
    reasons = [f"risk={change['risk_level']}", f"stage={stage}", f"tier={tier}"]
    if change["flow_impact"] != "none":
        reasons.append(f"flow_impact={change['flow_impact']}")
    if change["human_review_triggered"]:
        reasons.append("human_review_triggered=true")
    return reasons


def _live_ref(value: object, root: Path) -> dict[str, str]:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise GatePlanError("artifact reference is invalid")
    return _live_path(value["path"], root)


def _live_path(raw: object, root: Path) -> dict[str, str]:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise GatePlanError(f"unsafe project path: {raw}")
    path = root / raw
    if path.is_symlink() or not path.is_file():
        raise GatePlanError(f"missing or aliased project file: {raw}")
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise GatePlanError(f"project path escapes root: {raw}") from error
    return {"path": raw, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
