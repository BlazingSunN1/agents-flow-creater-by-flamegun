from __future__ import annotations

import re


SHA256_RE = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)


def ordered_actions(actions: list[dict[str, object]], evidence: dict[str, object]) -> bool:
    ranks = {"navigate": 0, "click": 1, "assert": 2, "screenshot": 3}
    click_path = evidence.get("click_path", [])
    screenshots = evidence.get("screenshots", [])
    screenshot_paths = [item.get("path") for item in screenshots if isinstance(item, dict)]
    targets = {
        "navigate": list(click_path[:1]), "click": list(click_path[1:]),
        "assert": list(evidence.get("assertions", [])), "screenshot": screenshot_paths,
    }
    previous = -1
    observed: dict[str, list[str]] = {name: [] for name in ranks}
    for index, item in enumerate(actions, start=1):
        action, target = item.get("action"), item.get("target")
        if (type(item.get("sequence")) is not int or item.get("sequence") != index
                or type(action) is not str or action not in ranks
                or type(target) is not str or target not in targets[action]
                or item.get("visible") is not True or item.get("enabled") is not True
                or ranks[action] < previous):
            return False
        observed[action].append(target)
        previous = ranks[action]
    return all(observed[action] for action in ranks) and all(
        observed[action] == targets[action] for action in ranks
    )


def valid_state_transitions(evidence: dict[str, object]) -> bool:
    transitions = evidence.get("state_transitions")
    click_path = evidence.get("click_path", [])
    assertions = evidence.get("assertions", [])
    if not isinstance(transitions, list) or not isinstance(click_path, list) or not isinstance(assertions, list):
        return False
    expected_clicks = click_path[1:]
    fields = {
        "click_target", "assertion_target", "before_state_path", "before_state_sha256",
        "after_state_path", "after_state_sha256",
    }
    if len(transitions) != len(expected_clicks):
        return False
    previous_path, previous_hash = evidence.get("dom_snapshot_path"), evidence.get("dom_snapshot_sha256")
    for click, item in zip(expected_clicks, transitions):
        if not isinstance(item, dict) or set(item) != fields or item.get("click_target") != click:
            return False
        before, after = item.get("before_state_sha256"), item.get("after_state_sha256")
        if (item.get("assertion_target") not in assertions or type(before) is not str or type(after) is not str
                or item.get("before_state_path") != previous_path or before != previous_hash
                or type(item.get("after_state_path")) is not str
                or not SHA256_RE.fullmatch(before) or not SHA256_RE.fullmatch(after) or before == after):
            return False
        previous_path, previous_hash = item["after_state_path"], after
    return True
