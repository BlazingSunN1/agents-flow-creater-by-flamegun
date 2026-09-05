from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from delivery_gate_planner import (
    GatePlanError, build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
)
from strict_json import loads as strict_json_loads
from validate_project_commands import validate_project_commands
from gate_output_files import exclusive_gate_outputs, require_reserved_gate_outputs
from gate_test_results import test_result_passes


class GateExecutionError(ValueError):
    pass


def execute_gate(
    contract_path: Path, command_id: str, *, project_root: Path,
    output_path: str, receipt_path: str, run_id: str,
) -> int:
    root = project_root.resolve()
    contract_file = _existing_file(contract_path, root, "contract")
    contract = _read_object(contract_file, "contract")
    command, fingerprint = _resolve_planned_command(contract, command_id, root)
    output = _output_file(output_path, root, "output")
    receipt = _output_file(receipt_path, root, "receipt")
    if output == receipt or not run_id.strip():
        raise GateExecutionError("output, receipt and run_id must be distinct and non-empty")
    argv = command["argv"]
    working_directory = _existing_directory(command["working_directory"], root)
    with exclusive_gate_outputs(output, receipt) as (output_stream, receipt_stream):
        return _execute_reserved(command_id, argv, working_directory, fingerprint,
                                 output, root, run_id, output_stream, receipt_stream,
                                 command.get('result_kind', 'tests'))


def _execute_reserved(command_id, argv, working_directory, fingerprint,
                      output, root, run_id, output_stream, receipt_stream, result_kind):
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        argv, cwd=working_directory, stdout=output_stream, stderr=subprocess.STDOUT,
        check=False,
    )
    ended = datetime.now(timezone.utc).isoformat()
    output_stream.flush()
    os.fsync(output_stream.fileno())
    require_reserved_gate_outputs(output_stream, receipt_stream)
    output_bytes = output.read_bytes()
    passed = completed.returncode == 0 and test_result_passes(
        command_id, argv, output_bytes, result_kind=result_kind)
    payload = {
        "schema_version": 2,
        "producer": "flowctl-gate-runner",
        "command_id": command_id,
        "gate_input_fingerprint": fingerprint,
        "command_argv": argv,
        "command_argv_sha256": hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest(),
        "started_at": started,
        "ended_at": ended,
        "exit_code": completed.returncode,
        "verdict": "pass" if passed else "fail",
        "run_id": run_id,
        "output_path": output.relative_to(root).as_posix(),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
    }
    receipt_stream.write((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    receipt_stream.flush()
    os.fsync(receipt_stream.fileno())
    if completed.returncode == 0 and not passed:
        print("ERROR gate-test-result-not-pass: expected nonempty passing native test report; see delivery-orchestration.md")
    return completed.returncode if completed.returncode != 0 else (0 if passed else 1)


def _resolve_planned_command(
    contract: dict[str, object], command_id: str, root: Path,
) -> tuple[dict[str, object], str]:
    artifacts = contract.get("artifacts")
    manifest_ref = artifacts.get("command_manifest") if isinstance(artifacts, dict) else None
    if not isinstance(manifest_ref, dict):
        raise GateExecutionError("contract command manifest reference is missing")
    manifest_path = _existing_file(Path(str(manifest_ref.get("path", ""))), root, "command manifest")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_ref.get("sha256"):
        raise GateExecutionError("contract command manifest hash is stale")
    command_issues = validate_project_commands(manifest_path, project_root=root)
    if command_issues:
        raise GateExecutionError(f"command manifest is invalid: {command_issues[0].code}")
    expected_plan = build_gate_plan(
        contract.get("change"), stage=str(contract.get("stage", "")),
        impact_fingerprint=compute_impact_fingerprint(contract, root),
        command_fingerprints=compute_command_fingerprints(contract, root),
    )
    if contract.get("gate_plan") != expected_plan:
        raise GateExecutionError("contract gate plan is stale")
    fingerprints = expected_plan["gate_input_fingerprints"]
    if command_id not in fingerprints:
        raise GateExecutionError("command is not a receipt-bearing gate in the current plan")
    manifest = _read_object(manifest_path, "command manifest")
    commands = manifest.get("commands")
    command = next(
        (item for item in commands if isinstance(item, dict) and item.get("id") == command_id),
        None,
    ) if isinstance(commands, list) else None
    if not isinstance(command, dict) or command.get("applicability") != "required":
        raise GateExecutionError("planned command is not enabled")
    return command, str(fingerprints[command_id])


def _read_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise GateExecutionError(f"{label} is unreadable: {error}") from error
    if not isinstance(value, dict):
        raise GateExecutionError(f"{label} must be a JSON object")
    return value


def _existing_file(path: Path, root: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise GateExecutionError(f"{label} must stay inside project root") from error
    if not resolved.is_file():
        raise GateExecutionError(f"{label} does not exist")
    return resolved


def _existing_directory(raw: object, root: Path) -> Path:
    if not isinstance(raw, str):
        raise GateExecutionError("working directory is invalid")
    path = _existing_file_or_directory(raw, root)
    if not path.is_dir():
        raise GateExecutionError("working directory does not exist")
    return path


def _output_file(raw: str, root: Path, label: str) -> Path:
    path = _existing_file_or_directory(raw, root, allow_missing=True)
    if path.exists() and not path.is_file():
        raise GateExecutionError(f"{label} must be a file")
    return path


def _existing_file_or_directory(raw: str, root: Path, *, allow_missing: bool = False) -> Path:
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise GateExecutionError("project path must be a safe relative path")
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise GateExecutionError("project path must not traverse a symbolic link")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise GateExecutionError("project path escapes project root") from error
    if not allow_missing and not resolved.exists():
        raise GateExecutionError("project path does not exist")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one planned gate and write a bound receipt")
    parser.add_argument("contract", type=Path)
    parser.add_argument("command_id")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--receipt-path", required=True)
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    try:
        return execute_gate(
            arguments.contract, arguments.command_id, project_root=arguments.project_root,
            output_path=arguments.output_path, receipt_path=arguments.receipt_path,
            run_id=arguments.run_id,
        )
    except (GateExecutionError, GatePlanError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR gate-execution {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
