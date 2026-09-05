from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


DOM_FIELDS = {"dom_snapshot_path", "dom_snapshot_sha256"}
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _DomParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.visible: set[str] = set()
        self.interactive: set[str] = set()
        self.classes: dict[str, set[str]] = {}
        self.elements: dict[str, dict[str, str]] = {}
        self.text: dict[str, list[str]] = {}
        self.id_stack: list[str | None] = []
        self.hidden_stack: list[bool] = []
        self.disabled_stack: list[bool] = []
        self.style_depth = 0
        self.style_sources: list[tuple[str, object]] = []
        self.current_style: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values, names = dict(attrs), {name.casefold() for name, _ in attrs}
        style = str(values.get("style", "")).replace(" ", "").casefold()
        hidden = _hidden(names, values, style) or bool(self.hidden_stack and self.hidden_stack[-1])
        disabled = _disabled(names, values) or bool(self.disabled_stack and self.disabled_stack[-1])
        identity = values.get("id")
        if identity:
            self._record(tag, str(identity), values, hidden, disabled)
        if tag == "style":
            self.style_depth += 1
            self.current_style = []
            self.style_sources.append(("inline", self.current_style))
        if tag == "link" and "stylesheet" in str(values.get("rel", "")).casefold().split():
            self.style_sources.append(("linked", str(values.get("href", ""))))
        if tag not in VOID_ELEMENTS:
            self.hidden_stack.append(hidden)
            self.disabled_stack.append(disabled or (tag == "fieldset" and "disabled" in names))
            self.id_stack.append(str(identity) if identity else None)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self.style_depth:
            self.style_depth -= 1
            self.current_style = None
        if tag not in VOID_ELEMENTS and self.hidden_stack:
            self.hidden_stack.pop()
            self.disabled_stack.pop()
            self.id_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.style_depth and self.current_style is not None:
            self.current_style.append(data)
        for identity in (item for item in self.id_stack if item):
            self.text.setdefault(identity, []).append(data)

    def _record(self, tag: str, identity: str, values: dict[str, str | None], hidden: bool, disabled: bool) -> None:
        self.ids.add(identity)
        self.classes[identity] = set(str(values.get("class", "")).split())
        self.elements[identity] = {
            **{name: "" if value is None else str(value) for name, value in values.items()}, "@tag": tag,
        }
        if not hidden:
            self.visible.add(identity)
        native = tag in {"button", "input", "select", "textarea", "summary"}
        linked = tag == "a" and bool(values.get("href"))
        scripted = bool(values.get("onclick") or values.get("tabindex") or values.get("role") in {"button", "link"})
        if not hidden and not disabled and (native or linked or scripted):
            self.interactive.add(identity)


def dom_action_issues(evidence: dict[str, object], transcript: dict[str, object], root: Path) -> list[tuple[str, str]]:
    if any(evidence.get(field) != transcript.get(field) for field in DOM_FIELDS):
        return [("browser-dom-evidence-mismatch", "浏览器转录未绑定证据头的 DOM 快照")]
    raw_path, raw_hash = evidence.get("dom_snapshot_path"), evidence.get("dom_snapshot_sha256")
    if type(raw_path) is not str or type(raw_hash) is not str:
        return [("browser-dom-evidence-mismatch", "DOM 快照路径和哈希必须是字符串")]
    payload = _snapshot_payload(raw_path, raw_hash, evidence, root)
    if isinstance(payload, str):
        return [(payload, "DOM 快照必须是绑定当前浏览器运行的 UTF-8 页面状态")]
    parser = _DomParser()
    parser.feed(payload.decode("utf-8"))
    styles, style_issue = combined_styles(parser.style_sources, evidence, root)
    if style_issue:
        return [("browser-dom-action-mismatch", style_issue)]
    hidden_css = css_hidden_ids(styles, parser.elements)
    if "@unsupported-css-import" in hidden_css:
        return [("browser-dom-action-mismatch", "CSS @import 无法作为可重放的本地交互证据")]
    parser.visible -= hidden_css
    parser.interactive -= hidden_css
    return _target_issues(evidence, parser)


def state_snapshot_state(
    raw_path: object, assertion: object, evidence: dict[str, object], root: Path,
) -> tuple[object, bool] | None:
    if type(raw_path) is not str or type(assertion) is not str:
        return None
    snapshot, identity = _safe_file(raw_path, root), _selector_id(assertion)
    if snapshot is None or identity is None:
        return None
    try:
        parser = _DomParser()
        parser.feed(snapshot.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return None
    styles, issue = combined_styles(parser.style_sources, evidence, root)
    if issue:
        return None
    hidden = css_hidden_ids(styles, parser.elements)
    if "@unsupported-css-import" in hidden:
        return None
    if identity not in parser.elements:
        return None
    semantic = tuple(sorted(
        (name, value) for name, value in parser.elements[identity].items()
        if name in {"@tag", "class", "role", "value", "checked", "selected", "open", "hidden", "data-state", "data-status"}
        or name.startswith("aria-")
    ))
    text = " ".join("".join(parser.text.get(identity, [])).split())
    return ((semantic, text), identity not in hidden and identity in parser.visible)


def css_hidden_ids(styles: str, elements: dict[str, dict[str, str]]) -> set[str]:
    states: dict[tuple[str, str], tuple[tuple[int, tuple[int, int, int], int, int], bool]] = {}
    if re.search(r"(?i)@import\b", styles):
        return {"@unsupported-css-import"}
    for order, (selectors, body) in enumerate(re.findall(r"([^{}]+)\{([^{}]*)\}", styles), start=1):
        declarations = _visibility_declarations(body)
        for selector in _split_selector_list(selectors):
            selector = selector.strip()
            targets = [key for key, attrs in elements.items() if _selector_matches(selector, key, attrs)]
            for target in targets:
                for index, (name, hides, important) in enumerate(declarations):
                    priority = (int(important), _specificity(selector), order, index)
                    key = target, name
                    if key not in states or priority >= states[key][0]:
                        states[key] = (priority, hides)
    return {target for (target, _), (_, hides) in states.items() if hides}


def _split_selector_list(selectors: str) -> list[str]:
    parts: list[str] = []
    start = 0
    paren_depth = bracket_depth = 0
    quote = ""
    for index, char in enumerate(selectors):
        if quote:
            if char == quote and (index == 0 or selectors[index - 1] != "\\"):
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif char == "," and paren_depth == bracket_depth == 0:
            parts.append(selectors[start:index])
            start = index + 1
    parts.append(selectors[start:])
    return parts


def _visibility_declarations(body: str) -> list[tuple[str, bool, bool]]:
    decisions: list[tuple[str, bool, bool]] = []
    for name, raw_value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body.casefold()):
        value, important = raw_value.replace(" ", ""), "!important" in raw_value.replace(" ", "")
        if name == "display":
            decisions.append((name, value.startswith("none"), important))
        elif name == "visibility" and (value.startswith("hidden") or value.startswith("visible")):
            decisions.append((name, value.startswith("hidden"), important))
    return decisions


def _selector_matches(selector: str, identity: str, attrs: dict[str, str]) -> bool:
    compound = re.split(r"\s+|[>+~]", selector.strip())[-1]
    exclusions = re.findall(r":not\(([^()]*)\)", compound)
    if any(
        _simple_compound_matches(option.strip(), identity, attrs, unsupported_matches=False)
        for group in exclusions for option in group.split(",") if option.strip()
    ):
        return False
    compound = re.sub(r":not\([^()]*\)", "", compound)
    return _simple_compound_matches(compound, identity, attrs)


def _simple_compound_matches(
    compound: str, identity: str, attrs: dict[str, str], *, unsupported_matches: bool = True,
) -> bool:
    pseudos = re.findall(r":([A-Za-z][\w-]*)", compound)
    disabled = "disabled" in attrs
    checked = "checked" in attrs
    for pseudo in pseudos:
        if pseudo == "disabled" and not disabled:
            return False
        if pseudo == "enabled" and disabled:
            return False
        if pseudo == "checked" and not checked:
            return False
        if pseudo not in {"disabled", "enabled", "checked", "is"} and not unsupported_matches:
            return False
    compound = re.sub(r":(?:disabled|enabled|checked)\b", "", compound)
    ids = re.findall(r"#([A-Za-z_][\w.-]*)", compound)
    if ids and identity not in ids:
        return False
    classes = set(attrs.get("class", "").split())
    if any(name not in classes for name in re.findall(r"\.([A-Za-z_][\w-]*)", compound)):
        return False
    for raw in re.findall(r"\[([^]]+)\]", compound):
        match = re.fullmatch(r"\s*([\w:-]+)(?:\s*=\s*['\"]?([^'\"]+)['\"]?)?\s*", raw)
        if match is None or match.group(1) not in attrs:
            return False
        if match.group(2) is not None and attrs[match.group(1)] != match.group(2):
            return False
    tag = re.match(r"^([A-Za-z][\w-]*)", compound)
    return tag is None or attrs.get("@tag") == tag.group(1).casefold()


def _specificity(selector: str) -> tuple[int, int, int]:
    ids = len(re.findall(r"#[A-Za-z_][\w.-]*", selector))
    classes = len(re.findall(r"\.[A-Za-z_][\w-]*|\[[^]]+\]|:[\w-]+", selector))
    elements = len(re.findall(r"(?:^|[>+~\s])([A-Za-z][\w-]*)", selector))
    return ids, classes, elements


def combined_styles(
    sources: list[tuple[str, object]], evidence: dict[str, object], root: Path,
) -> tuple[str, str | None]:
    page = evidence.get("page_artifact_path")
    if type(page) is not str:
        return "", "页面工件路径缺失"
    payloads: list[str] = []
    for kind, value in sources:
        if kind == "inline":
            payloads.append("".join(value) if isinstance(value, list) else "")
            continue
        href = str(value)
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return "", "外链样式必须是当前项目内相对 UTF-8 文件"
        relative = (Path(page).parent / parsed.path).as_posix()
        stylesheet = _safe_file(relative, root)
        if stylesheet is None:
            return "", "外链样式必须是当前项目内相对 UTF-8 文件"
        try:
            payloads.append(stylesheet.read_text(encoding="utf-8"))
        except UnicodeError:
            return "", "外链样式必须是当前项目内相对 UTF-8 文件"
    return "\n".join(payloads), None


def _snapshot_payload(raw_path: str, raw_hash: str, evidence: dict[str, object], root: Path) -> bytes | str:
    snapshot = _safe_file(raw_path, root)
    payload = snapshot.read_bytes() if snapshot is not None else b""
    if snapshot is None:
        return "browser-dom-evidence-mismatch"
    if hashlib.sha256(payload).hexdigest() != raw_hash.casefold():
        return "browser-dom-page-mismatch"
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return "browser-dom-evidence-mismatch"
    return payload


def _target_issues(evidence: dict[str, object], parser: _DomParser) -> list[tuple[str, str]]:
    click_path, assertions = evidence.get("click_path"), evidence.get("assertions")
    if not isinstance(click_path, list) or not isinstance(assertions, list):
        return [("browser-dom-action-mismatch", "点击路径和断言必须是 CSS id 选择器数组")]
    entry_ids = {_selector_id(item) for item in click_path[:1]}
    click_ids = {_selector_id(item) for item in click_path[1:]}
    assertion_ids = {_selector_id(item) for item in assertions}
    if (None in entry_ids | click_ids | assertion_ids or not entry_ids <= parser.visible
            or not assertion_ids <= parser.visible or not click_ids <= parser.interactive):
        return [("browser-dom-action-mismatch", "点击和断言目标必须在计算状态中可见，点击目标还必须启用并可交互")]
    return []


def _hidden(names: set[str], values: dict[str, str | None], style: str) -> bool:
    return ("hidden" in names or "inert" in names or str(values.get("aria-hidden", "")).casefold() == "true"
            or "display:none" in style or "visibility:hidden" in style
            or str(values.get("type", "")).casefold() == "hidden")


def _disabled(names: set[str], values: dict[str, str | None]) -> bool:
    return "disabled" in names or str(values.get("aria-disabled", "")).casefold() == "true"


def _selector_id(value: object) -> str | None:
    return value[1:] if type(value) is str and value.startswith("#") and len(value) > 1 else None


def _safe_file(raw: str, root: Path) -> Path | None:
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        return None
    if any((root / Path(*candidate.parts[:depth])).is_symlink() for depth in range(1, len(candidate.parts) + 1)):
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved if resolved.is_file() else None
