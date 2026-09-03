"""Single reversible kill switch for all external model provider calls."""


# Temporarily paused by explicit user request. Keep provider code for later review/re-enable.
EXTERNAL_PROVIDERS_ENABLED = False
PAUSE_MESSAGE = "Kimi and DeepSeek external providers are temporarily paused by policy"


def require_external_providers_enabled() -> None:
    if not EXTERNAL_PROVIDERS_ENABLED:
        raise ValueError(PAUSE_MESSAGE)
