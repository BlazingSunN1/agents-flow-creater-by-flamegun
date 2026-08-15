from __future__ import annotations

from urllib.parse import urlsplit


def is_http_browser_url(value: object) -> bool:
    if type(value) is not str or not value or value != value.strip():
        return False
    if any(ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )
