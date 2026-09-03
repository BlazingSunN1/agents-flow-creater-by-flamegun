#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from local_controlled_trust_validation import (
    FileReplayGuard,
    LocalControlledTrustError,
    validate_local_controlled_envelope,
)


class StableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid-cli-arguments")


def build_parser() -> argparse.ArgumentParser:
    parser = StableArgumentParser(
        description=(
            "Validate and consume an explicitly authorized same-user local trust receipt. "
            "This does not prove host-native runtime identity."
        ),
    )
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--trusted-public-key", required=True, type=Path)
    parser.add_argument("--public-key-fingerprint", required=True)
    parser.add_argument(
        "--receipt-type", required=True,
    )
    parser.add_argument("--owned-path", action="append", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--authority-matrix-sha256", required=True)
    parser.add_argument(
        "--replay-state", required=True, type=Path,
        help="Exact canonical external ledger path signed as payload.replay_state_path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
    except ValueError:
        print(json.dumps({"valid": False, "error": "invalid-cli-arguments"}, sort_keys=True))
        return 1
    if arguments.receipt_type != "system_governance_bootstrap":
        print(json.dumps({"valid": False, "error": "invalid-receipt-type"}, sort_keys=True))
        return 1
    try:
        value = validate_local_controlled_envelope(
            envelope_path=arguments.envelope,
            project_root=arguments.project_root,
            trusted_public_key_path=arguments.trusted_public_key,
            expected_public_key_fingerprint=arguments.public_key_fingerprint,
            expected_receipt_type=arguments.receipt_type,
            expected_owned_paths=arguments.owned_path,
            expected_bindings={
                "baseline_sha256": arguments.baseline_sha256,
                "policy_sha256": arguments.policy_sha256,
                "candidate_sha256": arguments.candidate_sha256,
                "authority_matrix_sha256": arguments.authority_matrix_sha256,
            },
            now=datetime.now(timezone.utc),
            replay_guard=FileReplayGuard(arguments.replay_state, arguments.project_root),
        )
    except LocalControlledTrustError as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    except (OSError, RuntimeError):
        print(json.dumps({"valid": False, "error": "local-trust-io-error"}, sort_keys=True))
        return 1
    print(json.dumps({
        "valid": True,
        "receipt_id": value["receipt_id"],
        "trust_mode": value["trust_mode"],
        "security_caveat": value["security_caveat"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
