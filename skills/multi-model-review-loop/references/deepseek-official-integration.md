# DeepSeek official external sub-Agent profile

Use this profile only for the isolated DeepSeek reviewer process. It does not replace Codex's native model or `spawn_agent` provider.

## Required request

- Interface: OpenAI-compatible Chat Completions
- Base URL: `https://api.deepseek.com`
- Endpoint: `/chat/completions`
- Model: `deepseek-v4-pro` by default; `deepseek-v4-flash` is the only supported lower-cost override
- Thinking: `{"type":"enabled"}`
- Reasoning effort: `max`
- Response format: `{"type":"json_object"}`
- Streaming: enabled with `stream_options.include_usage=true`; accept only one bounded UTF-8 SSE stream that ends with `data: [DONE]`

The system prompt already contains the word `JSON` and the exact required object schema. The default output budget is 32K tokens and the explicit hard cap is 262,144 tokens. Do not raise it merely because a task is long; first reduce unrelated context. The stream parser rejects identity drift, multiple choices, malformed JSON, a missing completion marker, non-`stop` termination, oversized streams, and a disconnect after output begins. A partial stream is never automatically retried as the same completed review.

Reject retired `deepseek-chat` and `deepseek-reasoner` aliases. Reject custom or compatibility base URLs for this official profile. Do not include user privacy data in provider identifiers or prompts.

## Authority boundary

DeepSeek authors black-box cases and reviews the immutable candidate. It does not edit the workspace, execute the cases, impersonate native Codex GPT, or decide final acceptance. The active Codex GPT rechecks the same candidate and the final validator binds both reviews to one hash.

## Official references

- [Your First API Call](https://api-docs.deepseek.com/zh-cn/guides/function_calling/)
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [JSON Output](https://api-docs.deepseek.com/guides/json_mode)
- [DeepSeek V4 change log](https://api-docs.deepseek.com/updates/)
- [Model list](https://api-docs.deepseek.com/api/list-models)

These references were checked on 2026-08-15. Re-check them before changing model IDs, base URLs, or thinking controls.
