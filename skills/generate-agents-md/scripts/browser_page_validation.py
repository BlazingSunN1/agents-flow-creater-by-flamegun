from __future__ import annotations

import hashlib
import http.client
import ipaddress
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError


PAGE_IDENTITY_FIELDS = {
    "preview_root", "page_artifact_path", "page_artifact_sha256", "observed_response_sha256",
}


def page_identity_issues(
    evidence: dict[str, object],
    transcript: dict[str, object],
    root: Path,
    *,
    code: str,
    expected_path: str | None = None,
    expected_sha256: str | None = None,
    expected_url: str | None = None,
    expected_preview_root: str | None = None,
    require_loopback: bool = False,
) -> list[tuple[str, str]]:
    fields = ("preview_root", "page_artifact_path", "page_artifact_sha256", "observed_response_sha256")
    if any(type(evidence.get(field)) is not str or not evidence.get(field, "").strip() for field in fields):
        return [(code, "页面证据必须声明预览根目录、入口工件路径和 SHA-256")]
    if any(transcript.get(field) != evidence.get(field) for field in fields):
        return [(code, "浏览器转录的页面身份与证据头不一致")]
    preview = _safe_path(str(evidence["preview_root"]), root, allow_dot=True)
    artifact = _safe_path(str(evidence["page_artifact_path"]), root, allow_dot=False)
    if preview is None or artifact is None or not preview.is_dir() or not artifact.is_file():
        return [(code, "页面入口工件或预览根目录不是项目内无符号链接的有效路径")]
    try:
        served_path = artifact.relative_to(preview).as_posix()
    except ValueError:
        return [(code, "页面入口工件不在声明的预览根目录内")]
    expected_hash = str(evidence["page_artifact_sha256"]).casefold()
    actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    parsed_url = urlsplit(str(evidence.get("page_url", "")))
    url_path = unquote(parsed_url.path).lstrip("/")
    observed_hash = str(evidence["observed_response_sha256"]).casefold()
    if expected_hash != actual_hash or url_path != served_path:
        return [(code, "page_url 必须精确指向当前入口工件且绑定其真实 SHA-256")]
    if require_loopback and not _loopback_host(parsed_url.hostname):
        return [(code, "本地泳道页面必须由回环地址提供，不能使用无关远端主机")]
    if expected_url is not None and (
        evidence.get("page_url") != expected_url
        or evidence.get("preview_root") != expected_preview_root
        or evidence.get("page_artifact_path") != expected_path
    ):
        return [("browser-page-authority-mismatch", "浏览器页面必须绑定命令清单声明的当前前端入口")]
    if expected_path is not None and str(evidence["page_artifact_path"]) != expected_path:
        return [(code, "浏览器入口必须是当前系统泳道工件")]
    if expected_sha256 is not None and expected_hash != expected_sha256.casefold():
        return [(code, "浏览器入口哈希必须绑定当前系统泳道哈希")]
    live_hash = _http_response_hash(str(evidence.get("page_url", "")))
    if live_hash != observed_hash or live_hash != actual_hash:
        return [(code, "page_url 必须实时返回当前入口工件的完整响应字节")]
    return []


def _http_response_hash(url: str) -> str | None:
    try:
        request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "generate-agents-md-validator/1"})
        with urlopen(request, timeout=2) as response:
            if response.status != 200 or response.geturl() != url:
                return None
            payload = response.read(10 * 1024 * 1024 + 1)
    except (OSError, URLError, ValueError, TimeoutError, http.client.HTTPException):
        return None
    if len(payload) > 10 * 1024 * 1024:
        return None
    return hashlib.sha256(payload).hexdigest()


def _loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _safe_path(raw: str, root: Path, *, allow_dot: bool) -> Path | None:
    if "\\" in raw or (raw == "." and not allow_dot):
        return None
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or (raw != "." and raw != candidate.as_posix()):
        return None
    if any(part in {"", ".."} for part in candidate.parts):
        return None
    for depth in range(1, len(candidate.parts) + 1):
        if (root / Path(*candidate.parts[:depth])).is_symlink():
            return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved
