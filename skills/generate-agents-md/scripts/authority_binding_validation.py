from __future__ import annotations

from pathlib import Path

from agents_authority_matrix_validation import AUTHORITY_MATRIX_SHA256, validate_authority_matrix


AUTHORITY_MATRIX_LOCATOR = "AGENTS.md#machine-enforced-authority-matrix"


def authority_metadata_issues(metadata: dict[str, str]) -> list[tuple[str, str]]:
    if (
        metadata.get("Authority matrix locator", "").strip() == AUTHORITY_MATRIX_LOCATOR
        and metadata.get("Authority matrix SHA-256", "").strip().casefold() == AUTHORITY_MATRIX_SHA256
    ):
        return []
    return [(
        "stale-authority-matrix-binding",
        "权限矩阵 locator 或 canonical SHA-256 与冻结接口不一致",
    )]


def authority_binding_issues(
    metadata: dict[str, str],
    root: Path,
    *,
    effective_agents: list[str] | None = None,
) -> list[tuple[str, str]]:
    issues = authority_metadata_issues(metadata)

    agents = root / "AGENTS.md"
    if agents.is_symlink():
        issues.append(("unsafe-authority-matrix-path", "权限矩阵根 AGENTS.md 不得是符号链接"))
        return issues
    if not agents.is_file():
        issues.append(("missing-authority-matrix-path", "权限矩阵 locator 必须指向现存根 AGENTS.md"))
        return issues
    try:
        text = agents.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        issues.append(("unreadable-authority-matrix", "权限矩阵根 AGENTS.md 必须是可读 UTF-8 文件"))
        return issues
    if validate_authority_matrix(text):
        issues.append(("stale-authority-matrix-binding", "根 AGENTS.md 权限矩阵已缺失、漂移或哈希不一致"))

    if effective_agents is not None:
        identities: set[tuple[int, int]] = set()
        for raw_path in effective_agents:
            candidate = root / Path(raw_path)
            try:
                identity = (candidate.stat().st_dev, candidate.stat().st_ino)
            except OSError:
                continue
            if identity in identities:
                issues.append((
                    "ambiguous-authority-policy-identity",
                    "Effective AGENTS files 不得通过 hardlink 复用同一规则文件身份",
                ))
                break
            identities.add(identity)
    return issues
