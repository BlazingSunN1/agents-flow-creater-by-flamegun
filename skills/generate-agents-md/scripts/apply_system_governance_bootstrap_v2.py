#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from local_controlled_bootstrap_v2 import (
    LocalControlledTrustError,
    apply_bootstrap_v2,
    validate_bootstrap_v2_envelope,
)
from local_controlled_module_lease_cli import StableArgumentParser, emit
from local_controlled_trust_validation import FileReplayGuard


def build_parser() -> argparse.ArgumentParser:
    parser = StableArgumentParser(
        description=(
            "Apply the explicit one-time same-user local-controlled governance bootstrap v2; "
            "this is not runtime proof."
        ),
    )
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--trusted-public-key", required=True, type=Path)
    parser.add_argument("--public-key-fingerprint", required=True)
    parser.add_argument("--agent-handle", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--replay-state", required=True, type=Path)
    parser.add_argument("--agents-replacement", required=True, type=Path)
    parser.add_argument("--governance-replacement", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        payload = validate_bootstrap_v2_envelope(
            envelope_path=arguments.envelope,
            project_root=arguments.project_root,
            trusted_public_key_path=arguments.trusted_public_key,
            expected_public_key_fingerprint=arguments.public_key_fingerprint,
            expected_agent_handle=arguments.agent_handle,
            expected_baseline_sha256=arguments.baseline_sha256,
            now=datetime.now(timezone.utc),
            replay_guard=FileReplayGuard(arguments.replay_state, arguments.project_root),
        )
        result = apply_bootstrap_v2(payload, {
            "AGENTS.md": arguments.agents_replacement,
            "docs/agents/module-agent-governance.md": arguments.governance_replacement,
        })
    except ValueError:
        emit({"error": "invalid-cli-arguments", "valid": False})
        return 1
    except LocalControlledTrustError as error:
        emit({"error": str(error), "valid": False})
        return 1
    except (OSError, RuntimeError):
        emit({"error": "bootstrap-v2-io-error", "valid": False})
        return 1
    emit(result)
    return 0 if result.get("complete") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
