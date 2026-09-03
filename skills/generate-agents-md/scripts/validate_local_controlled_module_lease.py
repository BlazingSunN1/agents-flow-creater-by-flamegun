#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

from local_controlled_module_lease_cli import build_parser, emit
from local_controlled_module_lease_validation import (
    LocalControlledTrustError,
    validate_module_lease_envelope,
)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser(
            "Validate a same-user local-controlled module write lease; this is not runtime proof.",
            "validate",
        ).parse_args(argv)
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
            now=datetime.now(timezone.utc),
        )
    except ValueError:
        emit({"error": "invalid-cli-arguments", "valid": False})
        return 1
    except LocalControlledTrustError as error:
        emit({"error": str(error), "valid": False})
        return 1
    except (OSError, RuntimeError):
        emit({"error": "module-lease-io-error", "valid": False})
        return 1
    emit({"lease_id": payload["lease_id"], "valid": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
