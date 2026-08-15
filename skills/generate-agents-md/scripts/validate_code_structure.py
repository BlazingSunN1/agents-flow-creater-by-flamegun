from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
MAX_FILE_LINES = 500
MAX_FUNCTION_LINES = 50


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str
    line: int | None = None


def validate_scripts(root: Path = SCRIPT_ROOT) -> list[Issue]:
    paths = sorted(path for path in root.glob("*.py") if not path.name.startswith("test_"))
    issues: list[Issue] = []
    graph: dict[str, set[str]] = {}
    names = {path.stem for path in paths}
    for path in paths:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        if len(lines) > MAX_FILE_LINES:
            issues.append(Issue("file-too-long", str(path), f"{len(lines)} > {MAX_FILE_LINES}"))
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            issues.append(Issue("syntax-error", str(path), str(error), error.lineno))
            continue
        issues.extend(_function_size_issues(path, tree))
        graph[path.stem] = _local_imports(tree, names)
    for cycle in _cycles(graph):
        issues.append(Issue("circular-import", str(root), " -> ".join((*cycle, cycle[0]))))
    return issues


def _function_size_issues(path: Path, tree: ast.AST) -> list[Issue]:
    issues: list[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        span = (node.end_lineno or node.lineno) - node.lineno + 1
        if span > MAX_FUNCTION_LINES:
            issues.append(Issue(
                "function-too-long", str(path),
                f"{node.name}: {span} > {MAX_FUNCTION_LINES}", node.lineno,
            ))
    return issues


def _local_imports(tree: ast.AST, names: set[str]) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        candidates = [alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import) else []
        if isinstance(node, ast.ImportFrom) and node.module:
            candidates.append(node.module.split(".")[0])
        imports.update(name for name in candidates if name in names)
    return imports


def _cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    for start in graph:
        stack: list[tuple[str, tuple[str, ...]]] = [(start, ())]
        while stack:
            node, path = stack.pop()
            if node in path:
                cycle = path[path.index(node):]
                rotations = [cycle[index:] + cycle[:index] for index in range(len(cycle))]
                found.add(min(rotations))
                continue
            stack.extend((child, (*path, node)) for child in graph.get(node, set()))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Skill Python 文件和函数大小及循环依赖")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    issues = validate_scripts()
    if args.json:
        print(json.dumps({"valid": not issues, "issues": [asdict(item) for item in issues]}, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(f"ERROR {issue.code} {issue.path}:{issue.line or '-'} {issue.message}")
        print(f"valid={str(not issues).lower()} issues={len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
