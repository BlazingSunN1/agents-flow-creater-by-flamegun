# 最小工作集与证据复用契约

仅当工作集扩展或任务申请复用既有证据时读取本文件。

- 使用 `assets/context-manifest.template.md`；风险字段恰好记录等级、风险原因、工作集扩展原因三段。
- 缓存键绑定需求基线、完整风险三段、直接依赖边界、代码版本、Build ID、完整生效 AGENTS 链、命令清单、配置、环境、输入和证据指纹。
- 历史上下文使用 `assets/reuse-source-context.template.md`；复用声明使用 `assets/reuse-evidence.template.json`。
- 只能复用不同于当前 run 的既往成功 run。它必须绑定符合正式 execution-run schema 的不可变完成记录及哈希、严格历史上下文路径/哈希、当前缓存键和逐项证据哈希。
- 源 run 的模块、基线、代码、Build ID、验收环境、风险、需求与 Changed files 必须和当前上下文逐项一致；历史记录拒绝重复、未知或隐藏字段。
- 单一源 run 只允许复用给单模块工作集；多模块必须重跑。多项证据路径用逗号分隔，路径中的空格和 `and` 保持字面含义。
- 新增、修改、移动或删除适用的 scoped AGENTS，或工作集路径包含父级/叶子符号链接，都使复用失败关闭。
