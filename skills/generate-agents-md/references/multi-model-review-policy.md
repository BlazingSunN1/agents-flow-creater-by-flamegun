# 外部多模型评审契约

仅当用户明确启用 Kimi、DeepSeek 与当前 Codex GPT 的并列评审循环时读取本文件，并同时使用 `$multi-model-review-loop`。

- Kimi 负责首版完整方案和每轮完整修订；不得只返回差异片段。
- DeepSeek 针对同一候选编写成功、拒绝、失败、重试、恢复、权限和边界黑盒用例，并执行缺陷审查；未执行的用例不得标为通过。
- 当前 Codex GPT 独立复核方案、用例覆盖和 DeepSeek findings，只把已接受问题交回 Kimi。
- 范围、脱敏上下文、准则、候选、版本、修订映射、固定提示、原始响应、provider/model/response ID/usage、规范化合同，以及原生 GPT 输入/检查/输出证据，必须由最终 loop-bundle 门禁逐轮绑定；最终通过必须绑定 DeepSeek 与 GPT 审查的同一候选哈希。
- 最多 6 轮；只有 DeepSeek 与 GPT 对同一候选均无缺陷、疑问和阻断时通过。到达上限仍未通过必须机器标记 `incomplete`。
- 外部模型不替代 Codex 原生子 Agent、唯一写者、真实黑盒或运行时门禁，不修改 Codex 默认模型、登录、代理、全局环境或工作区。
- 发送外部模型前先最小化上下文并脱敏；敏感信息不得进入提示、原始响应、规范化产物、日志或证据。
