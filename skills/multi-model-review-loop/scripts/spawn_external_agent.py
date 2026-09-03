#!/usr/bin/env python3
"""Spawn one isolated Kimi or DeepSeek adviser and validate its contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from clarification_validation import validate_clarification_register
from external_provider_policy import require_external_providers_enabled
from external_agent_resume import resume_existing as _resume_existing
from provider_result_validation import validate_raw_result
from validate_contract import (
    BEHAVIORS,
    DEFECT_FIELDS,
    strict_json_loads,
    write_new_private_file,
)


SKILL_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = {"kimi": "kimi", "deepseek": "deepseek"}
BASE_ENV = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR"}
PROVIDER_ENV = {
    "kimi": {"MOONSHOT_API_KEY", "KIMI_MODEL", "KIMI_BASE_URL"},
    "deepseek": {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"},
}
PROVIDER_REQUEST_PROFILES = {
    "kimi": "kimi-coding-chat-completions-bounded-sse-v2",
    "deepseek": "deepseek-v4-official-chat-completions-bounded-sse-v2",
}
TASK_ROOT_PREFIX = "codex-external-loop."
MAX_SYSTEM_BYTES = 16_384
MAX_PROMPT_BYTES = 524_288
SYSTEM_PROMPTS = {
    "kimi": (
        "You are the solution author. Produce a complete candidate that satisfies every supplied "
        "acceptance criterion. Do not claim execution or verification you did not perform. Return "
        "one JSON object only. On revision, address every accepted defect and return the entire "
        "revised candidate, not only a diff. Emit raw JSON: the first character must be { and the "
        "last character must be }. Do not use Markdown or code fences. Your JSON object must use exactly these top-level "
        "fields and no others: candidate_version, scope_sha256, artifact, assumptions, "
        "acceptance_criteria_mapping, change_map, known_limits. candidate_version is a positive "
        "integer. scope_sha256 is the supplied lowercase SHA-256. artifact is one complete "
        "nonempty string. assumptions and known_limits are arrays of strings. "
        "acceptance_criteria_mapping is a nonempty array of objects with exactly criterion, "
        "satisfaction, evidence, all strings. Each criterion value must be exactly one supplied "
        "acceptance-criterion ID such as AC-001, with no appended title or prose. change_map is an array of objects with exactly "
        "defect_id, change, verification, all strings."
    ),
    "deepseek": (
        "You are an adversarial but evidence-bound reviewer and black-box test author. Inspect the "
        "complete candidate against the supplied objective, acceptance criteria, constraints, and "
        "evidence. A defect must identify a violated criterion or concrete correctness, safety, "
        "compatibility, operability, or verification risk. Write complete black-box cases for "
        "success, rejection, failure, retry, recovery, permission, and boundary behavior that "
        "applies. Do not report subjective preferences as defects or claim that authored cases were "
        "executed. Return one JSON object only. Return pass only when no supported defect remains and "
        "the black-box case set covers every supplied acceptance criterion. Emit raw JSON: the "
        "first character must be { and the last character must be }. Do not use Markdown or code "
        "fences. Your JSON object must "
        "use exactly these top-level fields and no others: candidate_version, scope_sha256, "
        "candidate_sha256, verdict, defects, black_box_tests, coverage, uncertainties. verdict is "
        "pass or fail. defects is an array of objects with exactly id, severity, criterion, "
        "location, evidence, impact, correction, verification; defect IDs must be unique D-* "
        "strings and severity is P0, P1, P2, or P3. "
        "black_box_tests is a nonempty array of objects with exactly id, requirement, behavior, "
        "preconditions, steps, expected, evidence_required; behavior is success, rejection, "
        "failure, retry, recovery, permission, or boundary, and the last four fields are nonempty "
        "arrays of strings; every black-box ID must be a unique BB-* string. Each requirement "
        "value must be exactly one supplied acceptance-criterion ID such as AC-001, with no "
        "appended title or prose. coverage must contain each supplied acceptance-criterion ID "
        "exactly once and no other string; uncertainties is an array of strings. Do not use "
        "black_box_cases, execution_status, a boolean pass field, prose severity names, or an "
        "object for coverage. If a concern does not prevent acceptance, such as authored tests "
        "being intentionally unexecuted or an implementation-phase value already declared as a "
        "known limit, do not list it as an uncertainty. If a concern does prevent acceptance, "
        "report it as a concrete defect and return fail."
    ),
}
CREDENTIAL_INPUT = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z0-9]+_)*(?:password|passwd|token|access[_-]?token|"
    r"refresh[_-]?token|secret|client[_-]?secret|api[_-]?key|private[_-]?key|cookie|"
    r"set-cookie|authorization)[\"']?\s*[:=]\s*[\"']?(?P<value>[^\s#\"']+)", re.IGNORECASE,
)
BEARER_INPUT = re.compile(r"authorization\s*:\s*bearer\s+(?P<value>[^\s\"']+)", re.IGNORECASE)
PRIVATE_KEY_INPUT = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----", re.IGNORECASE)
URI_CREDENTIAL_INPUT = re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:@]+:(?P<value>[^\s/@]+)@", re.IGNORECASE)
PROMPT_FIELDS = {
    "schema_version", "task_id", "provider", "candidate_version", "scope_sha256",
    "objective", "acceptance_criteria", "context_artifacts", "clarification_register",
    "candidate", "candidate_sha256",
    "correction_ids", "corrections",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(CONTRACTS))
    parser.add_argument("--system-file", required=True, type=Path)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--deadline", type=float, default=1800.0)
    parser.add_argument("--max-tokens", type=int, default=32768)
    parser.add_argument("--retries", type=int, choices=range(0, 4), default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def output_paths(root: Path, provider: str) -> tuple[Path, Path, Path]:
    return (
        root / f"{provider}-response.json",
        root / f"{provider}-normalized.json",
        root / f"{provider}-spawn-result.json",
    )


def planned_commands(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    raw, normalized, _ = output_paths(args.output_dir, args.provider)
    call = [
        sys.executable, str(SKILL_ROOT / "scripts/call_model.py"), args.provider,
        "--system-file", str(args.system_file), "--prompt-file", str(args.prompt_file),
        "--output", str(raw), "--timeout", str(args.timeout),
        "--deadline", str(args.deadline),
        "--max-tokens", str(args.max_tokens), "--retries", str(args.retries),
    ]
    validate = [
        sys.executable, str(SKILL_ROOT / "scripts/validate_contract.py"),
        CONTRACTS[args.provider], str(raw), "--output", str(normalized),
    ]
    return call, validate


def task_root(path: Path) -> Path:
    temporary = (Path("/tmp") if os.name == "posix" else Path(tempfile.gettempdir())).resolve()
    resolved = path.resolve(strict=False)
    for candidate in (resolved, *resolved.parents):
        if candidate.parent == temporary and candidate.name.startswith(TASK_ROOT_PREFIX):
            return candidate
    raise ValueError("inputs and output-dir must be under one reserved system temporary task root")


def has_symlink_component(path: Path, root: Path) -> bool:
    absolute = path.absolute()
    parts = absolute.parts
    indexes = [index for index, part in enumerate(parts) if part.startswith(TASK_ROOT_PREFIX)]
    if not indexes:
        return True
    start = indexes[-1]
    current = Path(*parts[: start + 1])
    if current.is_symlink():
        return True
    for part in parts[start + 1 :]:
        current /= part
        if current.exists() and current.is_symlink():
            return True
    try:
        absolute.resolve(strict=False).relative_to(root)
    except ValueError:
        return True
    return False


def _prompt_identity(value: dict[str, object], provider: str, task_id: str) -> int:
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("prompt schema_version must be integer 1")
    if value.get("task_id") != task_id or value.get("provider") != provider:
        raise ValueError("prompt task_id or provider mismatch")
    version = value.get("candidate_version")
    expected = f"{task_id.rsplit('-v', 1)[0]}-v{version}-{provider}"
    if type(version) is not int or version < 1 or task_id != expected:
        raise ValueError("prompt candidate version must match the stable task ID")
    for field in ("scope_sha256", "candidate_sha256"):
        raw = value.get(field)
        if raw != "NOT_APPLICABLE" and (
            not isinstance(raw, str) or len(raw) != 64 or any(c not in "0123456789abcdef" for c in raw)
        ):
            raise ValueError(f"prompt {field} must be a lowercase SHA-256 or NOT_APPLICABLE")
    return version


def _prompt_criteria(value: dict[str, object]) -> None:
    if not isinstance(value.get("objective"), str) or not value["objective"].strip():
        raise ValueError("prompt objective must be non-empty")
    criteria = value.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("prompt acceptance_criteria must be non-empty")
    if any(not isinstance(item, dict) or set(item) != {"id", "text", "behaviors"} for item in criteria):
        raise ValueError("prompt acceptance criteria fields are invalid")
    identifiers = [item["id"] for item in criteria]
    invalid_text = any(not isinstance(item["id"], str) or not item["id"].strip()
                       or not isinstance(item["text"], str) or not item["text"].strip()
                       for item in criteria)
    if len(identifiers) != len(set(identifiers)) or invalid_text:
        raise ValueError("prompt acceptance criteria IDs and text must be unique and non-empty")
    invalid_behaviors = any(not isinstance(item["behaviors"], list) or not item["behaviors"]
                            or len(item["behaviors"]) != len(set(item["behaviors"]))
                            or not set(item["behaviors"]) <= BEHAVIORS for item in criteria)
    if invalid_behaviors:
        raise ValueError("prompt behavior categories are invalid")


def _prompt_artifacts(value: dict[str, object]) -> None:
    artifacts = value.get("context_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) > 64:
        raise ValueError("prompt context_artifacts must be a bounded array")
    identifiers: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"id", "content", "sha256"}:
            raise ValueError("prompt context artifacts must use the exact required fields")
        if not isinstance(item["id"], str) or not item["id"].strip() or not isinstance(item["content"], str):
            raise ValueError("prompt context artifact ID/content types are invalid")
        if item["sha256"] != hashlib.sha256(item["content"].encode("utf-8")).hexdigest():
            raise ValueError("prompt context artifact content hash is stale")
        identifiers.append(item["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("prompt context artifact IDs must be unique")


def _prompt_clarifications(value: dict[str, object]) -> None:
    criteria = {item["id"]: item["text"] for item in value["acceptance_criteria"]}
    register = value.get("clarification_register")
    validate_clarification_register(register, allow_open=False, criteria=criteria)
    if register["resolved_objective"] != value["objective"]:
        raise ValueError("prompt objective differs from the resolved clarification objective")


def _prompt_corrections(value: dict[str, object], provider: str, version: int) -> None:
    identifiers, details = value.get("correction_ids"), value.get("corrections")
    if not isinstance(identifiers, list) or len(identifiers) != len(set(identifiers)) \
            or any(not isinstance(item, str) or not item for item in identifiers):
        raise ValueError("prompt correction_ids must be unique strings")
    if not isinstance(details, list) or any(
        not isinstance(item, dict) or set(item) != DEFECT_FIELDS
        or any(not isinstance(item[field], str) or not item[field].strip() for field in DEFECT_FIELDS)
        or item["severity"] not in {"P0", "P1", "P2", "P3"} for item in details
    ):
        raise ValueError("prompt corrections must contain exact structured defects")
    detail_ids = [item["id"] for item in details]
    if len(detail_ids) != len(set(detail_ids)) or detail_ids != identifiers:
        raise ValueError("prompt correction_ids must exactly match correction details")
    if (provider == "deepseek" or version == 1) and details:
        raise ValueError("initial/reviewer prompt corrections must be empty")
    if provider == "kimi" and version > 1 and not details:
        raise ValueError("revised Kimi prompt requires structured corrections")


def validate_prompt_manifest(value: object, provider: str, task_id: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != PROMPT_FIELDS:
        raise ValueError("prompt must be one exact structured prompt manifest")
    version = _prompt_identity(value, provider, task_id)
    candidate_hash = value["candidate_sha256"]
    if (provider == "deepseek" or version > 1) and candidate_hash == "NOT_APPLICABLE":
        raise ValueError("review/revision prompt must bind the candidate SHA-256")
    if provider == "kimi" and version == 1 and candidate_hash != "NOT_APPLICABLE":
        raise ValueError("initial Kimi prompt candidate SHA-256 must be NOT_APPLICABLE")
    _prompt_criteria(value)
    _prompt_artifacts(value)
    _prompt_clarifications(value)
    _prompt_corrections(value, provider, version)
    if not isinstance(value.get("candidate"), str) or not value["candidate"].strip():
        raise ValueError("prompt candidate must be a non-empty string")
    if (candidate_hash == "NOT_APPLICABLE") != (value["candidate"] == "NOT_APPLICABLE"):
        raise ValueError("prompt candidate and candidate SHA-256 applicability differ")
    return value


def validate_system_prompt(provider: str, text: str) -> None:
    if text.strip() != SYSTEM_PROMPTS[provider]:
        raise ValueError(f"{provider} system prompt must equal the fixed reviewed role prompt")


def _placeholder_secret(value: str) -> bool:
    normalized = value.strip("\"'`<>")
    return bool(re.fullmatch(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)", normalized)) or normalized.upper() in {
        "REDACTED", "REMOVED", "***",
    }


def contains_sensitive_input(text: str) -> bool:
    if PRIVATE_KEY_INPUT.search(text):
        return True
    bearer = list(BEARER_INPUT.finditer(text))
    generic_text = BEARER_INPUT.sub("authorization: REDACTED", text)
    matches = [*CREDENTIAL_INPUT.finditer(generic_text), *bearer, *URI_CREDENTIAL_INPUT.finditer(text)]
    return any(not _placeholder_secret(match.group("value")) for match in matches)


def validate_external_input_files(
    system_path: Path, prompt_path: Path, provider: str, task_id: str,
) -> dict[str, object]:
    if system_path.stat().st_size > MAX_SYSTEM_BYTES or prompt_path.stat().st_size > MAX_PROMPT_BYTES:
        raise ValueError("external system/prompt input exceeds the bounded byte budget")
    system_text, prompt_text = system_path.read_text("utf-8"), prompt_path.read_text("utf-8")
    if contains_sensitive_input(system_text) or contains_sensitive_input(prompt_text):
        raise ValueError("external system/prompt input contains a prohibited credential pattern")
    validate_system_prompt(provider, system_text)
    return validate_prompt_manifest(strict_json_loads(prompt_text), provider, task_id)


def validate_inputs(args: argparse.Namespace) -> None:
    if not args.task_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in args.task_id):
        raise ValueError("task-id must be one stable path segment")
    if not 1 <= args.max_tokens <= 262_144 or not 1 <= args.timeout <= 600 \
            or not args.timeout <= args.deadline <= 7200:
        raise ValueError("max-tokens, idle timeout, or overall deadline is outside its safe range")
    output_root = task_root(args.output_dir)
    for path in (args.system_file, args.prompt_file):
        if task_root(path) != output_root or not path.is_file() or has_symlink_component(path, output_root):
            raise ValueError(f"input must be a regular non-symlink file: {path}")
    validate_external_input_files(args.system_file, args.prompt_file, args.provider, args.task_id)
    if args.output_dir.exists() and args.output_dir.is_symlink():
        raise ValueError("output-dir must not be a symlink")
    if args.output_dir.exists() and not getattr(args, "resume", False):
        raise ValueError("output-dir must be fresh and must not already exist")
    if getattr(args, "resume", False) and (not args.output_dir.is_dir() or args.output_dir.is_symlink()):
        raise ValueError("resume output-dir must be an existing regular directory")
    if has_symlink_component(args.output_dir.parent, output_root):
        raise ValueError("output-dir parent chain must not contain symlinks")


def child_environment(provider: str, source: dict[str, str] | os._Environ[str]) -> dict[str, str]:
    allowed = BASE_ENV | PROVIDER_ENV.get(provider, set())
    return {name: value for name, value in source.items() if name in allowed}


def run_command(
    command: list[str], environment: dict[str, str], timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=SKILL_ROOT, text=True, capture_output=True, check=False,
        env=environment, timeout=timeout,
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_regular_snapshot(path: Path) -> tuple[bytes, tuple[int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode):
            raise ValueError("provider artifact must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read()
        return payload, (identity.st_dev, identity.st_ino)
    finally:
        os.close(descriptor)


def validate_usage(usage: object) -> None:
    if usage is None:
        return
    if not isinstance(usage, dict):
        raise ValueError("raw provider usage must be an object or null")
    names = ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens")
    present = {name: usage[name] for name in names if name in usage}
    if not present or any(type(value) is not int or value < 0 for value in present.values()):
        raise ValueError("raw provider usage token counts must be non-negative integers")
    if "total_tokens" in present:
        component_sum = sum(present.get(name, 0) for name in ("prompt_tokens", "completion_tokens"))
        if present["total_tokens"] < component_sum:
            raise ValueError("raw provider total_tokens cannot be smaller than its components")


def _validate_result_binding(args: argparse.Namespace, value: dict[str, object]) -> None:
    prompt = strict_json_loads(args.prompt_file.read_text("utf-8"))
    if value.get("candidate_version") != prompt.get("candidate_version"):
        raise ValueError("provider candidate version differs from the requested version")
    if value.get("scope_sha256") != prompt.get("scope_sha256"):
        raise ValueError("provider scope hash differs from the requested scope")
    criteria = [item["id"] for item in prompt["acceptance_criteria"]]
    if args.provider == "kimi":
        mapped = [item["criterion"] for item in value.get("acceptance_criteria_mapping", [])]
        if len(mapped) != len(criteria) or set(mapped) != set(criteria):
            raise ValueError("Kimi criterion mapping differs from the requested criteria")
        return
    if value.get("candidate_sha256") != prompt.get("candidate_sha256"):
        raise ValueError("DeepSeek reviewed a different candidate hash")
    coverage = value.get("coverage", [])
    requirements = [item["requirement"] for item in value.get("black_box_tests", [])]
    if len(coverage) != len(criteria) or set(coverage) != set(criteria) \
            or any(item not in criteria for item in requirements):
        raise ValueError("DeepSeek coverage differs from the requested criteria")


def result_manifest(
    args: argparse.Namespace, normalized: Path,
    raw_snapshot: tuple[bytes, tuple[int, int]] | None = None,
) -> dict[str, object]:
    payload = normalized.read_bytes()
    value = strict_json_loads(payload.decode("utf-8"))
    raw = output_paths(args.output_dir, args.provider)[0]
    _validate_result_binding(args, value)
    wrapper, raw_payload, execution = validate_raw_result(
        args, raw, value, raw_snapshot, read_regular_snapshot, validate_usage,
    )
    return {
        "schema_version": 1, "task_id": args.task_id, "provider": args.provider,
        "role": "solution-and-revision-author" if args.provider == "kimi" else "black-box-author-and-defect-reviewer",
        "system_sha256": file_sha256(args.system_file), "prompt_sha256": file_sha256(args.prompt_file),
        "system_path": str(args.system_file.resolve()), "prompt_path": str(args.prompt_file.resolve()),
        "raw_path": str(raw.resolve()), "raw_sha256": hashlib.sha256(raw_payload).hexdigest(),
        "model": wrapper["model"], "request_model": wrapper["request_model"],
        "finish_reason": wrapper["finish_reason"], "response_id": wrapper["response_id"],
        "usage": wrapper["usage"], "request_profile": PROVIDER_REQUEST_PROFILES[args.provider],
        **execution, "candidate_version": value["candidate_version"],
        "scope_sha256": value["scope_sha256"],
        "candidate_sha256": (
            hashlib.sha256(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if args.provider == "kimi" else value["candidate_sha256"]
        ),
        "normalized_path": normalized.name,
        "normalized_sha256": hashlib.sha256(payload).hexdigest(),
        "verdict": value.get("verdict", "candidate"),
    }


def resume_existing(
    args: argparse.Namespace, validate: list[str], environment: dict[str, str],
) -> Path:
    return _resume_existing(
        args, validate, environment, result_manifest, read_regular_snapshot, SKILL_ROOT,
    )


def main() -> int:
    args = parse_args()
    try:
        validate_inputs(args)
        call, validate = planned_commands(args)
        raw, normalized, manifest = output_paths(args.output_dir, args.provider)
        if args.dry_run:
            print(json.dumps({"provider": args.provider, "task_id": args.task_id,
                              "call": call, "validate": validate}, ensure_ascii=False, indent=2))
            return 0
        require_external_providers_enabled()
        environment = child_environment(args.provider, os.environ)
        if args.resume:
            print(resume_existing(args, validate, environment))
            return 0
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if args.output_dir.is_symlink() or task_root(args.output_dir) != task_root(args.system_file):
            raise ValueError("output-dir changed identity while it was being created")
        if any(path.exists() for path in (raw, normalized, manifest)):
            raise ValueError("external-agent output already exists; use a fresh task directory")
        called = run_command(
            call, environment, args.deadline + 30,
        )
        if called.returncode:
            print(called.stderr.strip() or "external provider call failed", file=sys.stderr)
            return called.returncode
        checked = run_command(validate, environment, 60)
        if checked.returncode:
            print(checked.stderr.strip() or "external response contract invalid", file=sys.stderr)
            return checked.returncode
        if manifest.exists() or manifest.is_symlink():
            raise ValueError("external-agent manifest path changed identity")
        write_new_private_file(
            manifest, json.dumps(result_manifest(args, normalized), ensure_ascii=False, indent=2) + "\n",
        )
        print(manifest)
        return 0
    except (
        OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"spawn_external_agent failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
