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
- Streaming: disabled so the complete contract can be hashed and validated atomically

The system prompt already contains the word `JSON` and the exact required object schema. Keep `max_tokens` bounded by the Skill even though the provider supports larger outputs.

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
