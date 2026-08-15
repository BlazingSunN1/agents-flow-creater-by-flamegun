#!/usr/bin/env python3
"""Write one reviewed provider system prompt into a reserved task root."""

from __future__ import annotations

import argparse
from pathlib import Path

from spawn_external_agent import (
    SYSTEM_PROMPTS,
    has_symlink_component,
    task_root,
)
from validate_contract import write_new_private_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(SYSTEM_PROMPTS))
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = task_root(args.output)
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit("system prompt output must be fresh")
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if has_symlink_component(args.output.parent, root):
        raise SystemExit("system prompt parent must not contain symlinks")
    write_new_private_file(
        args.output,
        SYSTEM_PROMPTS[args.provider] + "\n",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
