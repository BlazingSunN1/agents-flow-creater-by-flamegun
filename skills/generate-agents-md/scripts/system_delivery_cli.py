from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable


def main(validate_system_delivery_bundle: Callable[..., list[object]]) -> int:
    parser = argparse.ArgumentParser(description="只读聚合并验证每个受影响模块的独立交付闭环")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--allow-passwords", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    issues = validate_system_delivery_bundle(
        manifest_path=args.manifest, project_root=args.project_root, allow_passwords=args.allow_passwords,
    )
    if args.json:
        print(json.dumps({"valid": not issues, "issues": [asdict(item) for item in issues]}, ensure_ascii=False, indent=2))
    else:
        for item in issues:
            print(f"ERROR {item.code} {item.source} {item.message}")
        print(f"errors={len(issues)} valid={str(not issues).lower()}")
    return 1 if issues else 0
