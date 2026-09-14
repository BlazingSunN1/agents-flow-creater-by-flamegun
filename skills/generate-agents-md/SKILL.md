---
name: generate-agents-md
description: 从仓库事实和需求生成、更新、拆分、公共化或审查 UTF-8 AGENTS.md；建立可验证的需求追踪、独立验收、进度日志、前端点击验证和阶段泳道门禁，用于稳定交付、约束偏移、模板脱敏及减少 Token。
---

# Agents Flow

## 不可削弱的原则

- 先调查；不得猜测命令、路径、技术栈、版本、环境或部署方式。
- 只写会稳定改变 Agent 行为的项目规则。
- 根级只放全仓规则，子级 `AGENTS.md` 只写作用域差异。
- 产物使用 UTF-8；不得把 RTF、HTML 或含 NUL 的内容当 Markdown。
- 公共模板脱敏。仅在已授权项目任务或明确要求只读审查该策略或隔离效果时读取 `references/sensitive-configuration-policy.md`；只读不授权写入或传播真实值。
- 优先级：需求闭环与稳定交付 > 效率。状态为 `result_candidate → affected_checks_passed → baseline_frozen → hardening → closure_candidate`；成果前只做执行、受影响验收或防不可逆损害检查，冻结后才加载映射的打磨。治理不能替代成果或以无事实收益的机制阻塞验收。

## 模式

- `project`：生成生效规则；禁止占位符、模板注释和待办。
- `public-template`：生成脱敏模板；允许 `{{PLACEHOLDER}}`，禁止真实主体、路径或基础设施标识。
- `review`：只报可复现问题；收到修复要求后再写。

## 工作流

### 1. 最小事实调查

1. 查找当前目录至仓库根、目标子目录的全部 `AGENTS.md`。
2. 按需读 README、依赖、构建、CI、测试、部署、环境配置及现有治理记录；优先 `rg` 和只读命令。
3. 泳道审查入口、调用链、接口、配置和测试，不只复述文档。
4. 仅为解释历史约束读 Git 历史。

### 2. 建立证据与作用域矩阵

写前记录“规则、来源、作用域、稳定性、决定”。硬规则只来自用户要求或已验证代码/配置；冲突、临时状态和未知项不升级为事实。先读 `references/extraction-checklist.md`，再按触发条件加载专项清单。

存在 Dispatcher/长期维护 Agent 体系时读 `references/module-agent-governance.md`。The Dispatcher role is always read-only；层级不授予写权；每模块仅匹配 module/Agent/run/owned paths 的活动租约持有者单写且不得自验。

写前依 `references/task-write-boundary.md` 运行 `python3 scripts/flowctl.py scope ...`；项目 Agent 只写项目根，Skill 维护须本轮授权和精确根；校验不代表 OS 隔离。

### 3. 安全组合与更新

- 根文件用 `assets/AGENTS.template.md`，子目录用 `assets/AGENTS.scoped.template.md`，按需取 `assets/AGENTS.optional-sections.md`。
- 保留根模板 `Machine-Enforced Policy` 固定枚举；项目规则只能补充，不能削弱或冲突。
- 删除或弱化既有规则须有过时、重复、冲突或作用域错误证据。
- 共享记录仅由登记且租约匹配 module、Agent/run、路径和策略哈希的实现/维护 Agent 写；Dispatcher、审查者或重复写者失败关闭。`python3 scripts/flowctl.py record ...` 校验边界并锁/CAS 原子更新；仅支持 POSIX，Windows 用 WSL。它不是 OS 隔离。

- 默认实现/维护写者固定为 Codex 原生 `gpt-5.6-sol`、`reasoning_effort=medium`，并持有当前唯一写租约；所有 GPT-6 角色只读。项目只有在用户明确选择 Local Qwen 写者模式时，才按 `references/local-qwen-code-author.md` 切换到独立的 Qwen 身份与证据闭集；不得自动回退、混用身份或伪造另一 provider 的证明。

### 3.1 候选与通信

- 冻结验收、路径和正式基线后，在任务独占候选区生成并测试；同一候选全部适用门禁通过且授权/基线/哈希未漂移，当前唯一租约写者才应用相同字节。失败、缺证或无法隔离就不应用；只清理本任务候选。
- Agent 间只传最小任务包、实质变化、阻断和可用阶段结果；不转发完整聊天、推理、原始日志或可直接读取的全文。合并进度并优先事件通知/有界等待；交接注明状态、指纹、范围、证据、测试、阻断、责任方及失效结论。

### 4. 建立稳定交付链

- 用追踪模板贯通需求、流程、功能、UI、测试、模块和黑盒；歧义返回基线，不为实现缺陷改需求。
- 最小链是“目标/边界/验收 → 真实入口至业务结果 → 受影响检查 → 当前证据”。冻结后才打磨，回归后重验。见 `references/delivery-orchestration.md`。
- 仅按已证实风险加载方案、泳道、功能、原型、测试和独立验收；不适用只记理由，不建空产物。
- 实现/维护 Agent 用 `gpt-5.6-sol/medium`；Dispatcher、方案、审核、裁决和独立验收用 `gpt-6-astra/high`。后者只读且不持租约；系统聚合是独立的 `gpt-5.6-sol/medium` 写者。修订只由当前唯一租约写者执行，写者不得自验。默认保存本地结构绑定，严格模式才要求宿主证明运行身份。
- 小型任务须影响已知、无行为/契约/流程变化且有定向验证，只复用唯一写者，不增 Agent/全链产物。标准任务最多一个写者和一个只读 `BLACK_BOX` Agent，合并审查、用例复核与黑盒验收；完整多 Agent 仅用于已证实高风险、并发大模块或独立/合规要求。未知先调查。
- 用 delivery contract/gate receipt 模板建立单一决策索引；规划器只读，租约 writer 经 CAS 合并，禁止手改或复用旧门禁。命令模板 `assets/project-commands.template.json`；成果先跑核实入口，冻结前登记；外部绑定见 `references/delivery-orchestration.md`。
- 可写实现/系统聚合 receipt 强制 schema v2：实现 outer 的 `implementation_write_proof` 由 receipt 以 `historical_write_proof` 回显；gate 只读同候选，outer 是唯一预期值来源，replay 失败关闭。v1 仅兼容验证器明确保留的只读 GPT-6 gate/裁决 receipt；strict 再加宿主证明。见 `references/role-specific-local-receipts.md`。
- 聚合验证器仅在闭环候选或完成阶段实时执行且不互签；漂移、失败门禁或开放分歧阻断。
- 仅当 `project` 模式显式选择 `authorization-mode=local-controlled-same-user`，或有已映射的高风险/合规要求时，才调用 `$strict-delivery-security`；默认 `delivery-first-local-coordination` 不加载其严格签名、宿主证明和 bootstrap 流程。核心 Skill 不复制这些细节。

### 5. 同步代码、证据与可视流程

- 开发前更新计划，验证后更新进度；计划绑定需求基线，进度绑定 run 和代码版本。未执行、未验证、失败门禁或开放缺陷不得标记 `completed`；未答疑问不是缺陷或门禁。
- 多模块进度/审查路径含字面 `<module>`、`<run_id>`；路径只认唯一锚定字段。疑问清单中的未答项记为 `P2 pending`/`NON_BLOCKING_P2`，按可逆默认继续，答复后只重跑受影响门禁。
- 计划/基线可先建；交付/完成文档须等同一候选全部适用测试和独立黑盒通过。仅在闭环候选或人工触发时审查当前指纹；变化使审查失效，发现须可复现，修复先补回归再修根因。
- 默认只加载：生效 `AGENTS.md`、进度索引、当前 run、相关追踪行；验证器可从磁盘读取上下文清单。扩展或复用证据时才读 `references/evidence-reuse-policy.md`；`latest.md`、历史日志和大型原始输出不进默认提示。
- 每次修改只判定 `swimlane_applicable=true|false` 和 `flow_impact=none|changed|uncertain`。无适用泳道不建图、不查新鲜度；适用的 `none` 保留，`uncertain` 调查，`changed` 按稳定候选合并，首次依赖或阶段交接前至多更新一次；仅系统边界变化更新总览。
- 泳道或 Web 前端适用时读取 `references/browser-validation-policy.md`，执行应用内浏览器人工式闭环和真实 Playwright/Cypress。移动 Web 在相关范围启用浏览器门禁；原生移动执行 `native_mobile_tests`，跨端两套并行；遗留 `mobile` 由 `frontend_applicable` 区分。
- 仅处理受控敏感配置或明确只读审查其策略/隔离时加载 `references/sensitive-configuration-policy.md`；写入授权以目标 AGENTS.md 为单一来源。

## 失败关闭验证

迭代检查：

```bash
python3 scripts/flowctl.py doctor --quick
```

它不证明闭环。已知标准影响用 `--affected --changed-file <相对路径>`；未知映射升 full。无当前 SHA-256 冻结证明不执行 mutation；稳定后冻结，每个候选至多执行一次 full：

```bash
python3 scripts/flowctl.py doctor --freeze-candidate
python3 scripts/flowctl.py doctor --full
```

源码树外的冻结/full receipt 受 HMAC 和锁保护；通过可复用，变化须重冻，失败/中断/畸形阻断。分发追加 `--distribution --require-direct-skills`；未同步不得发布。

`flowctl.py` 的 `check/plan/gate/record` 分别验证、规划、执行登记命令生成 v2 receipt、锁/CAS 更新；禁手写 receipt。故障、漂移、失败门禁或缺陷阻断；`P2 pending` 不阻断。

## 资源路由

- 根/子/可选规则用 `assets/AGENTS.template.md`、`assets/AGENTS.scoped.template.md`、`assets/AGENTS.optional-sections.md`；复用输入用 `assets/reuse-source-context.template.md`。
- 事实、交付、界面、治理依次读 `references/extraction-checklist.md`、`references/extraction-delivery.md`、`references/extraction-interfaces.md`、`references/module-agent-governance.md`；严格安全和敏感配置只在触发时加载对应专项。
- 原生复核、证据复用、浏览器验收按需读 `references/multi-model-review-policy.md`、`references/evidence-reuse-policy.md`、`references/browser-validation-policy.md`；细则见 `references/delivery-orchestration.md`。
