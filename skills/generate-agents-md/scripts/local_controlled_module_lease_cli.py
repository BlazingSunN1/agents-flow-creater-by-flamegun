from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class StableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid-cli-arguments")


def build_parser(description: str, operation: str) -> argparse.ArgumentParser:
    parser = StableArgumentParser(description=description)
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--trusted-public-key", required=True, type=Path)
    parser.add_argument("--public-key-fingerprint", required=True)
    parser.add_argument("--registry-path", required=True, type=Path)
    parser.add_argument("--module-key", required=True)
    parser.add_argument("--agent-handle", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--code-version", required=True)
    parser.add_argument("--build-id", required=True)
    if operation == "apply":
        parser.add_argument("--target", required=True, type=Path)
        parser.add_argument("--replacement", required=True, type=Path)
        parser.add_argument("--action", required=True)
    return parser


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
