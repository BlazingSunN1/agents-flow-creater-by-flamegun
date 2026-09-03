# 原生 GPT Sol 并列评审策略

Kimi/DeepSeek 外部 provider 保持暂停，不得调用或恢复 `$multi-model-review-loop`。需要并列评审时使用 `$native-gpt-review-loop`。

- 普通代码增量不启动并列评审；只累计当前 run 的变更与证据。仅在模块闭环候选形成或人工主动触发时审查当前候选；人工触发的快照不能自行关闭模块，审查后发生代码或配置变化则结论失效，下一闭环候选必须重审当前指纹。
- 方案与黑盒审查子 Agent、只读 coordinator/adjudicator 及独立验收 Agent 都通过 Codex 原生调度显式指定 `model=gpt-5.6-sol`、`reasoning_effort=xhigh`；实际实现/维护 Agent 显式指定同一模型与 `reasoning_effort=high`。不支持精确模型或推理强度时失败关闭，不替换或降级。
- 方案角色返回首版完整候选和每轮完整修订；黑盒角色对同一候选哈希独立编写成功、拒绝、失败、重试、恢复、权限和边界用例并审查缺陷。未执行用例不得标为通过。
- 两个方案/审查子 Agent 对 workspace 与共享记录只读。主、父、子层级不授予固有写权；裁决者只裁决并路由门禁，不得执行或自证独立 review、black-box、accept 与 completion。只有匹配 module、Agent/run、owned paths 和唯一活动协调租约的当前模块维护/实现 Agent 是唯一写者；Dispatcher 始终只读。真实黑盒由不同 Agent/run 对同一 candidate/code/build 执行；默认用封闭本地 receipt 绑定，严格模式再宿主证明，不得以多数票关闭分歧。
- 范围、最小输入、角色、模型、推理强度、Agent/run ID、候选版本/哈希、输入输出路径/哈希和原生 spawn 结果必须逐轮绑定；子 Agent 自报模型或推理强度不算机器证据。
- UI/UX、验收用例、变更审查、真实黑盒等独立角色启动前，交付上下文冻结唯一 canonical Requirement Questions locator/SHA，并与当前需求基线绑定。每个 `NOT_PROVIDED` 必须是 `delivery_disposition=NON_BLOCKING_P2`，带可逆默认值、回退与假设，推送人工但继续执行；`ANSWERED` 更新基线后只重跑影响范围。缺失、哈希漂移、基线不一致或事后补问题文件失败关闭，疑问未回答本身不失败。
- 最多 6 轮；同一候选的方案审查只能形成 `reviewed`，不能冒充交付通过。只有另一个独立 Agent/run 的真实黑盒/验收绑定同一候选、代码与构建且通过，completion 才能 `pass`；否则标记 `incomplete` 或 `blocked`。
- 使用 `assets/native-review-loop-evidence.template.json` 和 `scripts/validate_native_review_loop.py` 固化每轮闭合证据；本地 receipt 只作协调证据，项目文件不能自称宿主信任。
- 长任务每轮候选必须写入封闭 `checkpoint_chain`：绑定 workflow/run/round、scope/candidate/code/build、方案输入输出哈希、完成门禁、待处理缺陷、下一动作、UTC 时间、当前 locator/SHA 和前序 locator/SHA；首个前序值为 `null`。压缩、中断或恢复后，本地模式校验同链同候选 receipt，严格模式追加宿主证明；缺失、漂移或乱序失败关闭。
