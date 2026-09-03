#!/usr/bin/env python3
"""Validate a human-question register or publish its non-blocking AI defaults."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clarification_validation import apply_default_assumptions, validate_clarification_register
from validate_contract import strict_json_loads, write_new_private_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("register", type=Path)
    parser.add_argument("--stage", choices=("draft", "resolved"), required=True)
    parser.add_argument("--apply-defaults-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        value = strict_json_loads(args.register.read_text("utf-8"))
        allow_open = args.stage == "draft"
        validate_clarification_register(value, allow_open=allow_open)
        result = value
        if args.apply_defaults_output:
            if not allow_open:
                raise ValueError("defaults can be applied only to a draft register")
            result = apply_default_assumptions(value)
            write_new_private_file(
                args.apply_defaults_output,
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            )
        statuses = {name: 0 for name in ("open", "answered", "assumed", "confirmed", "dismissed")}
        for item in result["questions"]:
            statuses[item["status"]] += 1
        print(json.dumps({"valid": True, "stage": args.stage, "statuses": statuses}))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "status": "blocked", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
