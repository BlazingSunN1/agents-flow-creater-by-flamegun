#!/usr/bin/env python3
"""Call a configured Kimi or DeepSeek Chat Completions endpoint safely."""

from __future__ import annotations

import argparse
import getpass
import http.client
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

from external_provider_policy import require_external_providers_enabled
from pathlib import Path
from collections.abc import Iterable
from typing import Any

from spawn_external_agent import (
    has_symlink_component, strict_json_loads, task_root, validate_external_input_files,
)
from validate_contract import write_new_private_file


PROVIDERS = {
    "kimi": {
        "key_env": "MOONSHOT_API_KEY",
        "model_env": "KIMI_MODEL",
        "model_default": "k3",
        "base_env": "KIMI_BASE_URL",
        "base_default": "https://api.kimi.com/coding/v1",
        "keychain_service": "codex-multi-model-review-loop-moonshot",
    },
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "model_default": "deepseek-v4-pro",
        "base_env": "DEEPSEEK_BASE_URL",
        "base_default": "https://api.deepseek.com",
        "keychain_service": "codex-multi-model-review-loop-deepseek",
    },
}
DEEPSEEK_OFFICIAL_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_V4_MODELS = {"deepseek-v4-pro", "deepseek-v4-flash"}
MAX_OUTPUT_TOKENS = 262_144
MAX_STREAM_BYTES = 64 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(PROVIDERS))
    parser.add_argument("--system-file", required=True, type=Path)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--deadline", type=float, default=1800.0)
    parser.add_argument("--max-tokens", type=int, default=32768)
    parser.add_argument("--retries", type=int, choices=range(0, 4), default=1)
    return parser.parse_args()


def configured_value(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def keychain_secret(service: str) -> str:
    if sys.platform != "darwin":
        return ""
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-w",
            "-a",
            getpass.getuser(),
            "-s",
            service,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def provider_secret(config: dict[str, str]) -> str:
    secret = configured_value(config["key_env"])
    if not secret:
        secret = keychain_secret(config["keychain_service"])
    if not secret:
        raise ValueError(
            f"credential missing: set {config['key_env']} or the configured Keychain item"
        )
    return secret


def endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if not normalized.startswith("https://"):
        raise ValueError("provider base URL must use HTTPS")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def validate_provider_target(provider: str, base_url: str, model: str) -> None:
    if provider != "deepseek":
        return
    if base_url.rstrip("/") != DEEPSEEK_OFFICIAL_BASE_URL:
        raise ValueError("DeepSeek sub-agent must use the official base URL")
    if model not in DEEPSEEK_V4_MODELS:
        raise ValueError("DeepSeek sub-agent must use an official DeepSeek V4 model")


def validate_call_paths(args: argparse.Namespace) -> None:
    prompt = strict_json_loads(args.prompt_file.read_text("utf-8"))
    task_id = prompt.get("task_id") if isinstance(prompt, dict) else None
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("structured prompt task_id is required")
    root = task_root(args.output)
    if task_root(args.system_file) != root or task_root(args.prompt_file) != root:
        raise ValueError("call_model inputs and output must share one reserved task root")
    if has_symlink_component(args.output.parent, root) or args.output.exists():
        raise ValueError("call_model output must be a fresh non-symlink task-root file")
    validate_external_input_files(args.system_file, args.prompt_file, args.provider, task_id)


def build_request(args: argparse.Namespace) -> tuple[urllib.request.Request, str]:
    if not 1 <= args.max_tokens <= MAX_OUTPUT_TOKENS or not 1 <= args.timeout <= 600 \
            or not args.timeout <= args.deadline <= 7200:
        raise ValueError("max-tokens, idle timeout, or overall deadline is outside its safe range")
    config = PROVIDERS[args.provider]
    api_key = provider_secret(config)
    model = configured_value(config["model_env"], config["model_default"])
    base_url = os.environ.get(config["base_env"], config["base_default"])
    validate_provider_target(args.provider, base_url, model)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": args.system_file.read_text("utf-8")},
            {"role": "user", "content": args.prompt_file.read_text("utf-8")},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if args.provider == "kimi":
        payload["max_completion_tokens"] = args.max_tokens
        payload["reasoning_effort"] = "max"
    else:
        payload["max_tokens"] = args.max_tokens
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = "max"
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint(base_url),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Codex multi-model-review-loop/1.0",
        },
    )
    return request, model


def retryable(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in {408, 409, 429, 500, 502, 503, 504}
    return isinstance(error, (urllib.error.URLError, TimeoutError))


def _stream_identity(chunk: dict[str, Any], state: dict[str, Any]) -> None:
    for name in ("id", "model"):
        value = chunk.get(name)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or state[name] not in (None, value):
            raise ValueError(f"provider stream {name} is invalid or drifted")
        state[name] = value


def _stream_choice(chunk: dict[str, Any], state: dict[str, Any]) -> None:
    choices = chunk.get("choices", [])
    if not isinstance(choices, list) or len(choices) > 1:
        raise ValueError("provider stream choices are invalid")
    if not choices:
        return
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("index") not in (None, 0):
        raise ValueError("provider stream choice is invalid")
    delta = choice.get("delta", {})
    if not isinstance(delta, dict):
        raise ValueError("provider stream delta is invalid")
    piece = delta.get("content")
    if piece is not None:
        if not isinstance(piece, str):
            raise ValueError("provider stream content is invalid")
        state["content"].append(piece)
    finish = choice.get("finish_reason")
    if finish is not None:
        if not isinstance(finish, str) or state["finish"] not in (None, finish):
            raise ValueError("provider stream finish_reason drifted")
        state["finish"] = finish


def parse_provider_stream(
    lines: Iterable[bytes], deadline_at: float | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "id": None, "model": None, "usage": None, "finish": None,
        "content": [], "done": False, "bytes": 0, "events": 0,
    }
    try:
        for raw in lines:
            if deadline_at is not None and time.monotonic() >= deadline_at:
                raise ValueError("provider stream exceeded the overall deadline")
            state["bytes"] += len(raw)
            if state["bytes"] > MAX_STREAM_BYTES:
                raise ValueError("provider stream exceeds the bounded byte budget")
            line = raw.decode("utf-8").strip()
            if not line or line.startswith(":") or line.startswith("event:"):
                continue
            if state["done"] or not line.startswith("data:"):
                raise ValueError("provider stream contains an invalid SSE record")
            payload = line[5:].strip()
            if payload == "[DONE]":
                state["done"] = True
                continue
            chunk = strict_json_loads(payload)
            if not isinstance(chunk, dict):
                raise ValueError("provider stream chunk must be an object")
            state["events"] += 1
            _stream_identity(chunk, state)
            if chunk.get("usage") is not None:
                state["usage"] = chunk["usage"]
            _stream_choice(chunk, state)
    except (OSError, TimeoutError, http.client.HTTPException) as error:
        if state["bytes"]:
            raise ValueError("provider stream disconnected after output began") from error
        raise
    if not state["done"]:
        raise ValueError("provider stream is missing the completion marker")
    if not state["events"] or state["id"] is None or state["model"] is None:
        raise ValueError("provider stream has no response identity")
    return {
        "id": state["id"], "model": state["model"], "usage": state["usage"],
        "choices": [{"message": {"content": "".join(state["content"])},
                     "finish_reason": state["finish"]}],
    }


def post(
    request: urllib.request.Request, timeout: float, retries: int, provider: str,
    deadline: float,
) -> dict[str, Any]:
    context = ssl.create_default_context()
    deadline_at = time.monotonic() + deadline
    for attempt in range(retries + 1):
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            raise ValueError("provider call exceeded the overall deadline")
        try:
            with urllib.request.urlopen(
                request, timeout=min(timeout, remaining), context=context,
            ) as response:
                return parse_provider_stream(response, deadline_at)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            if attempt >= retries or not retryable(error):
                raise
            delay = 2**attempt
            if time.monotonic() + delay >= deadline_at:
                raise ValueError("provider retry would exceed the overall deadline") from error
            time.sleep(delay)
    raise RuntimeError("unreachable retry state")


def extract_result(response: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    try:
        choice = response["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice["finish_reason"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("provider response has no assistant content") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("provider returned empty assistant content")
    if finish_reason != "stop":
        raise ValueError("provider response finish_reason must be stop")
    response_model = response.get("model")
    if not isinstance(response_model, str) or not response_model.strip():
        raise ValueError("provider response model is missing")
    if provider == "deepseek" and response_model != model:
        raise ValueError("DeepSeek response model differs from the requested model")
    return {
        "provider": provider,
        "request_model": model,
        "model": response_model,
        "content": content,
        "usage": response.get("usage"),
        "response_id": response.get("id"),
        "finish_reason": finish_reason,
    }


def safe_error(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"provider HTTP error: {error.code} {error.reason}"
    if isinstance(error, urllib.error.URLError):
        return f"provider connection error: {error.reason}"
    return f"provider call failed: {error}"


def main() -> int:
    args = parse_args()
    try:
        require_external_providers_enabled()
        validate_call_paths(args)
        request, model = build_request(args)
        response = post(request, args.timeout, args.retries, args.provider, args.deadline)
        result = extract_result(response, args.provider, model)
        result.update({
            "transport": "bounded-sse-v1", "idle_timeout_seconds": args.timeout,
            "deadline_seconds": args.deadline, "max_output_tokens": args.max_tokens,
            "retry_limit": args.retries,
        })
        output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        validate_call_paths(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_new_private_file(args.output, output)
        return 0
    except Exception as error:  # CLI boundary: emit a sanitized, actionable failure.
        print(safe_error(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
