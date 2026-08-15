from __future__ import annotations

from html.parser import HTMLParser

from pathlib import Path

from browser_dom_validation import VOID_ELEMENTS, combined_styles, css_hidden_ids


class _SwimlaneParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.entries: dict[str, str | None] = {}
        self.back_targets: set[str | None] = set()
        self.hidden_ids: set[str] = set()
        self.hidden_entries: set[str] = set()
        self.hidden_back = False
        self.hidden_stack: list[bool] = []
        self.classes: dict[str, set[str]] = {}
        self.elements: dict[str, dict[str, str]] = {}
        self.entry_tags: dict[str, str] = {}
        self.entry_ids: dict[str, str] = {}
        self.back_tags: list[str] = []
        self.style_depth = 0
        self.style_sources: list[tuple[str, object]] = []
        self.current_style: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        names = {name.casefold() for name, _ in attrs}
        style = str(values.get("style", "")).replace(" ", "").casefold()
        hidden = (
            "hidden" in names or str(values.get("aria-hidden", "")).casefold() == "true"
            or "display:none" in style or "visibility:hidden" in style
            or bool(self.hidden_stack and self.hidden_stack[-1])
        )
        if tag not in VOID_ELEMENTS:
            self.hidden_stack.append(hidden)
        if values.get("id"):
            identity = str(values["id"])
            self.ids.add(identity)
            self.classes[identity] = set(str(values.get("class", "")).split())
            self.elements[identity] = _css_element(tag, values)
            if hidden:
                self.hidden_ids.add(identity)
        if values.get("data-open-module"):
            module = str(values["data-open-module"])
            self.entries[module] = values.get("href")
            self.entry_tags[module] = tag
            self.entry_ids[module] = str(values.get("id", ""))
            self.elements[f"@entry:{module}"] = _css_element(tag, values)
            if hidden or "disabled" in names or str(values.get("aria-disabled", "")).casefold() == "true":
                self.hidden_entries.add(module)
        if "back-link" in str(values.get("class", "")).split():
            self.back_targets.add(values.get("href"))
            self.back_tags.append(tag)
            self.elements[f"@back:{len(self.back_tags)}"] = _css_element(tag, values)
            self.hidden_back = self.hidden_back or hidden or "disabled" in names
        if tag == "style":
            self.style_depth += 1
            self.current_style = []
            self.style_sources.append(("inline", self.current_style))
        if tag == "link" and "stylesheet" in str(values.get("rel", "")).casefold().split():
            self.style_sources.append(("linked", str(values.get("href", ""))))

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

    def handle_data(self, data: str) -> None:
        if self.style_depth and self.current_style is not None:
            self.current_style.append(data)


def system_drilldown_issues(
    text: str, modules: set[str], diagram: Path | None = None, root: Path | None = None,
) -> list[tuple[str, str]]:
    parser = _SwimlaneParser()
    parser.feed(text)
    evidence = {"page_artifact_path": diagram.relative_to(root).as_posix()} if diagram and root else {}
    styles, style_issue = combined_styles(parser.style_sources, evidence, root) if root else ("", None)
    if style_issue:
        return [("invalid-swimlane-drilldown-control", style_issue)]
    hidden_css = css_hidden_ids(styles, parser.elements)
    if set(parser.entries) != modules:
        return [("swimlane-drilldown-target-mismatch", "系统图模块入口必须精确覆盖当前模块")]
    if (parser.hidden_entries or parser.hidden_back or modules & (parser.hidden_ids | hidden_css)
            or "@unsupported-css-import" in hidden_css
            or any(key.startswith(("@entry:", "@back:")) for key in hidden_css)
            or any(parser.entry_ids.get(module) in hidden_css for module in modules)
            or any(parser.entry_tags.get(module) != "a" for module in modules)
            or any(tag != "a" for tag in parser.back_tags)
            or any(parser.entries[module] != f"#{module}" or module not in parser.ids for module in modules)):
        return [("invalid-swimlane-drilldown-control", "模块入口必须使用 href 指向页面内同名目标 id")]
    if "#system-overview" not in parser.back_targets or "system-overview" not in parser.ids:
        return [("missing-swimlane-drilldown", "系统图缺少可用的返回总览闭环")]
    return []


def _css_element(tag: str, values: dict[str, str | None]) -> dict[str, str]:
    return {**{name: "" if value is None else str(value) for name, value in values.items()}, "@tag": tag}
