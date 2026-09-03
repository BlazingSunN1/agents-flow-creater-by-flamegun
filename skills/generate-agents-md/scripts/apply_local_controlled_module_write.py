#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

from local_controlled_module_lease_cli import build_parser, emit
from local_controlled_module_lease_validation import (
    LocalControlledTrustError,
    apply_signed_module_write,
    validate_module_lease_envelope,
)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser(
            "Apply one guarded file replacement under an active same-user local-controlled lease.",
            "apply",
        ).parse_args(argv)
        now = datetime.now(timezone.utc)
        payload = validate_module_lease_envelope(
            envelope_path=arguments.envelope,
            project_root=arguments.project_root,
            trusted_public_key_path=arguments.trusted_public_key,
            expected_public_key_fingerprint=arguments.public_key_fingerprint,
            expected_registry_path=arguments.registry_path,
            expected_module_key=arguments.module_key,
            expected_agent_handle=arguments.agent_handle,
            expected_run_id=arguments.run_id,
            expected_code_version=arguments.code_version,
            expected_build_id=arguments.build_id,
            now=now,
        )
        result = apply_signed_module_write(
            payload, arguments.registry_path, arguments.target,
            arguments.replacement, arguments.action, now,
        )
    except ValueError:
        emit({"error": "invalid-cli-arguments", "valid": False})
        return 1
    except LocalControlledTrustError as error:
        emit({"error": str(error), "valid": False})
        return 1
    except (OSError, RuntimeError):
        emit({"error": "module-write-io-error", "valid": False})
        return 1
    emit(result)
    return 0 if result.get("complete") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
