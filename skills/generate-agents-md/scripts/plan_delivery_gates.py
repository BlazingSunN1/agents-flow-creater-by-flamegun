from __future__ import annotations

import argparse
import json
from pathlib import Path

from delivery_gate_planner import (
    GatePlanError, build_gate_plan, compute_command_fingerprints, compute_impact_fingerprint,
)
from strict_json import loads as strict_json_loads


def planned_contract(path: Path, project_root: Path) -> dict[str, object]:
    data = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("change"), dict):
        raise GatePlanError("contract and change must be objects")
    impact = compute_impact_fingerprint(data, project_root)
    data["gate_plan"] = build_gate_plan(
        data["change"], stage=str(data.get("stage", "")), impact_fingerprint=impact,
        command_fingerprints=compute_command_fingerprints(data, project_root),
    )
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="从交付事实确定性生成最小门禁计划")
    parser.add_argument("path", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        data = planned_contract(arguments.path, arguments.project_root)
        print(json.dumps(data["gate_plan"], ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, GatePlanError) as error:
        print(f"ERROR gate-plan {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
